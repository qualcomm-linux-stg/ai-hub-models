# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

# isort: off
# This verifies aimet is installed, and this must be included first.
from qai_hub_models.models._shared.llm.model import (
    LLMBase,
    PositionProcessorBase,
    LLM_AIMETOnnx,
    DEFAULT_CONTEXT_LENGTH,
    DEFAULT_SEQUENCE_LENGTH,
)

# isort: on
import copy
import json
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import onnx
import torch

if TYPE_CHECKING:
    from aimet_onnx.quantsim import QuantizationSimModel

from packaging.version import Version
from transformers import PretrainedConfig, PreTrainedTokenizer
from transformers.modeling_attn_mask_utils import AttentionMaskConverter
from transformers.models.qwen2 import modeling_qwen2

from qai_hub_models.models._shared.llama3.model import RopeEmbedding

# todo change
from qai_hub_models.models._shared.qwen2.model_adaptations import (
    QcQwen2_apply_rotary_pos_emb,
    QCQwen2ForCausalLM,
    QCQwen2MLP,
    SHAQwen2Attention,
)
from qai_hub_models.utils.aimet.encodings import propagate_memory_encodings

MODEL_ID = __name__.split(".")[-2]
MODEL_ASSET_VERSION = 1

# Configs
AIMET_ENCODINGS_PREFIX = "config"
AIMET_CONFIG = "default_config_qwen"

DATA_DIR = "data"
USE_CACHED_DATA = True

START_HEADER = "<|im_start|>"
END_HEADER = "<|im_end|>"
SYSTEM_ID = "system"
ASSISTANT_ID = "assistant"
USER_ID = "user"
END_TOKENS = {"<|im_end|>", "<|endoftext|>"}

DEFAULT_PROMPT_CONTEXT = "You are a helpful AI assistant"
DEFAULT_USER_PROMPT = "What is gravity? Keep the answer under ten words."

# Genie defaults to -1000 as "-infity" for FP16 attention masks.
# However, Qwen 2.5 1.5B requires -10000 for good results.
# Since Genie currently cannot configure this, to make this model compatible
# with Genie, we have too boost this value inside the network.
QWEN2_ATTENTION_MULTIPLIER = 10


class Qwen2_Optimizations(str, Enum):  # Inherit from str and Enum
    SHA_ATTENTION = "sha_attention"
    RMS_NORM_4_RANK = "rank4_rms_norm"


class Qwen2Base(LLMBase):
    LMClass = modeling_qwen2.Qwen2ForCausalLM
    EmbeddingClass = RopeEmbedding

    @staticmethod
    def get_input_prompt_with_tags(
        user_input_prompt: str = DEFAULT_USER_PROMPT,
        system_context_prompt: str = DEFAULT_PROMPT_CONTEXT,
    ) -> str:
        """Get prompt to set context and initialize prompt-processor"""
        prompt = f"""{START_HEADER}{SYSTEM_ID}
{system_context_prompt}{END_HEADER}
{START_HEADER}{USER_ID}
{user_input_prompt}{END_HEADER}
{START_HEADER}{ASSISTANT_ID}
"""
        return prompt

    @staticmethod
    def monkey_patch(
        skip_optimizations: list[str] | None = None,
    ) -> None:
        if (
            skip_optimizations
            and Qwen2_Optimizations.SHA_ATTENTION in skip_optimizations
        ):
            print("Skip sha_attention optimization")
        else:
            modeling_qwen2.QWEN2_ATTENTION_CLASSES["eager"] = SHAQwen2Attention

        def bypass_RotaryEmbedding(self, x, position_ids, *args, **kwargs):
            return position_ids

        # Bypass rotary_emb module
        if not hasattr(modeling_qwen2.Qwen2RotaryEmbedding, "_original_forward"):
            modeling_qwen2.Qwen2RotaryEmbedding._original_forward = (  # pyright: ignore [reportAttributeAccessIssue]
                modeling_qwen2.Qwen2RotaryEmbedding.forward
            )
            modeling_qwen2.Qwen2RotaryEmbedding.forward = bypass_RotaryEmbedding
        modeling_qwen2.apply_rotary_pos_emb = QcQwen2_apply_rotary_pos_emb

        def Qwen2RMSNorm_forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
            # Raise to rank 4
            hidden_states = hidden_states.unsqueeze(0)
            variance = hidden_states.pow(2).mean(-1, keepdim=True)
            hidden_states = hidden_states * torch.rsqrt(
                variance + self.variance_epsilon
            )
            return (hidden_states * self.weight).squeeze(0)

        if (
            skip_optimizations
            and Qwen2_Optimizations.RMS_NORM_4_RANK in skip_optimizations
        ):
            print("Skip rank4_rms_norm optimization")
        else:
            modeling_qwen2.Qwen2RMSNorm.forward = Qwen2RMSNorm_forward

        modeling_qwen2.Qwen2MLP = QCQwen2MLP
        modeling_qwen2.Qwen2ForCausalLM = QCQwen2ForCausalLM

    def _verify_ckpt(self):
        if (
            not (
                self.llm_config.architectures[0] == "QwenForCausalLM"
                and self.llm_config.model_type == "qwen2"
            )
            and self.llm_config.rope_scaling is not None
            and self.llm_config.rope_scaling["rope_type"] != "qwen2"
        ):
            raise ValueError(
                "Model config is not compatible with this model implementation."
            )

    def forward(
        self,
        input_tokens: torch.Tensor,
        attention_mask: torch.Tensor,
        *rest: torch.Tensor,
    ):
        return super().forward(
            input_tokens,
            QWEN2_ATTENTION_MULTIPLIER * attention_mask,
            *rest,
        )


class QwenPositionProcessor(PositionProcessorBase):
    """Prepares positions (RopeEmbedding and attention mask preparation); used by ORT GenAI."""

    def __init__(
        self,
        context_length: int,
        config: PretrainedConfig,
    ) -> None:
        super().__init__(context_length, config=config)
        self.context_len = context_length
        self.rope_embedding = RopeEmbedding(max_length=self.context_len, config=config)

    def forward(self, attention_mask_before_processor, position_ids):
        position_ids_cos, position_ids_sin = self.rope_embedding.get_embedding(
            position_ids
        )
        attention_mask_converter = AttentionMaskConverter(True)
        attention_mask = attention_mask_converter.to_4d(
            attention_mask_before_processor,
            query_length=position_ids.shape[1],
            key_value_length=attention_mask_before_processor.shape[1],
            dtype=torch.float32,
        )
        attention_mask = attention_mask.clip(-50, 0)
        return attention_mask, position_ids_cos, position_ids_sin


class Qwen2Base_AIMETOnnx(LLM_AIMETOnnx):
    EmbeddingClass = RopeEmbedding

    def __init__(
        self,
        sim_model: QuantizationSimModel,
        host_device: torch.device,
        checkpoint: str | os.PathLike | Path | None = None,
        tokenizer: PreTrainedTokenizer | None = None,
        llm_config: PretrainedConfig | None = None,
        sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
        context_length: int = DEFAULT_CONTEXT_LENGTH,
        attention_mask_min_clip: float | None = None,
    ):
        super().__init__(
            sim_model=sim_model,
            checkpoint=checkpoint,
            tokenizer=tokenizer,
            llm_config=llm_config,
            sequence_length=sequence_length,
            context_length=context_length,
            host_device=host_device,
            attention_mask_min_clip=attention_mask_min_clip,
        )

    get_input_prompt_with_tags = Qwen2Base.get_input_prompt_with_tags

    @staticmethod
    def _get_output_names(num_hidden_layers: int):
        output_names = ["logits"]
        for layer in range(num_hidden_layers):
            output_names.append(f"past_key_{layer}_out")
            output_names.append(f"past_value_{layer}_out")
        return output_names

    def forward(
        self,
        input_tokens: torch.Tensor,
        attention_mask: torch.Tensor,
        *rest: torch.Tensor,
    ):
        return super().forward(
            input_tokens,
            QWEN2_ATTENTION_MULTIPLIER * attention_mask,
            *rest,
        )

    def _adapt_aimet_encodings(
        self, src_encodings_path: str, dst_encodings_path: str, onnx_model_path: str
    ) -> None:
        """Make sure AIMET encodings are ready for ONNX split."""
        with open(src_encodings_path) as f:
            encodings = json.load(f)

        model = onnx.load(onnx_model_path)

        model_input_names = {}
        for node in model.graph.node:
            model_input_names[node.name] = node.input

        uses_lists = Version(encodings["version"]) >= Version("1.0.0")

        if uses_lists:
            # Convert encodings to dictionaries for faster look-ups
            encodings["activation_encodings"] = {
                v["name"]: v for v in encodings["activation_encodings"]
            }
            encodings["param_encodings"] = {
                v["name"]: v for v in encodings["param_encodings"]
            }

        # See _shared/llama3/model.py for why this is needed.
        embed_a_name = "/model/model/embed_tokens/Gather_output_0"
        embed_w_name = "model.model.embed_tokens.weight"
        encodings["activation_encodings"][embed_a_name] = copy.deepcopy(
            encodings["activation_encodings"][embed_w_name]
        )
        for key in encodings["activation_encodings"].keys():
            if "weight" in key:
                encodings["param_encodings"][key] = copy.deepcopy(
                    encodings["activation_encodings"][key]
                )

        if uses_lists:
            encodings["activation_encodings"][embed_a_name]["name"] = embed_a_name

        propagate_memory_encodings(encodings, model)

        if uses_lists:
            # convert back
            encodings["activation_encodings"] = list(
                encodings["activation_encodings"].values()
            )
            encodings["param_encodings"] = list(encodings["param_encodings"].values())

        with open(dst_encodings_path, "w") as write_file:
            json.dump(encodings, write_file, indent=4, sort_keys=True)

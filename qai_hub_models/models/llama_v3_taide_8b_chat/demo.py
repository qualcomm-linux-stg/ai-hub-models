# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from qai_hub_models.models._shared.llama3.model import DEFAULT_USER_PROMPT, END_TOKENS
from qai_hub_models.models._shared.llm.demo import llm_chat_demo
from qai_hub_models.models.llama_v3_taide_8b_chat import MODEL_ID, FP_Model, Model
from qai_hub_models.models.llama_v3_taide_8b_chat.model import (
    HF_REPO_NAME,
    HF_REPO_URL,
    SUPPORTED_PRECISIONS,
)
from qai_hub_models.utils.base_model import BaseModel, TargetRuntime
from qai_hub_models.utils.checkpoint import CheckpointSpec


def llama_v3_taide_8b_chat_demo(
    model_cls: type[BaseModel] = Model,
    fp_model_cls: type[BaseModel] = FP_Model,
    model_id: str = MODEL_ID,
    end_tokens: set = END_TOKENS,
    hf_repo_name: str = HF_REPO_NAME,
    hf_repo_url: str = HF_REPO_URL,
    default_prompt: str = DEFAULT_USER_PROMPT,
    test_checkpoint: CheckpointSpec | None = None,
    available_target_runtimes: list[TargetRuntime] | None = None,
):
    if available_target_runtimes is None:
        available_target_runtimes = [TargetRuntime.QNN_CONTEXT_BINARY]
    llm_chat_demo(
        model_cls=model_cls,
        fp_model_cls=fp_model_cls,
        model_id=model_id,
        end_tokens=end_tokens,
        hf_repo_name=hf_repo_name,
        supported_precisions=SUPPORTED_PRECISIONS,
        hf_repo_url=hf_repo_url,
        default_prompt=default_prompt,
        test_checkpoint=test_checkpoint,
    )


if __name__ == "__main__":
    llama_v3_taide_8b_chat_demo()

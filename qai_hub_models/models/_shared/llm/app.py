# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

import shutil
from collections.abc import Callable
from typing import Any

import torch
from transformers import GenerationConfig, TextStreamer, set_seed

from qai_hub_models.models._shared.llm.generator import LLM_Generator, LLM_Loader
from qai_hub_models.utils.base_model import BaseModel
from qai_hub_models.utils.checkpoint import CheckpointSpec


class IndentedTextStreamer(TextStreamer):
    def __init__(self, line_start, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.terminal_width = shutil.get_terminal_size().columns
        self.printed_width = 0
        self.line_start = line_start

    def on_finalized_text(self, text: str, stream_end: bool = False):
        """Prints the new text to stdout. If the stream is ending, also prints a newline."""
        if len(text) == 0:
            return

        # If the incoming text would cause the printed output to wrap around, start a new line
        if self.printed_width + len(text) >= self.terminal_width:
            print("", flush=True)
            self.printed_width = 0

        # If we are on a new line, print the line starter before the text
        if self.printed_width == 0:
            text = self.line_start + text

        # If there are multiple newlines, make sure that the line starter is present at every new line
        # (except the last one, since that will be taken care of when we try to print the something to that new line
        # for the first time)
        if text.count("\n") > 1:
            last_index = text.rfind("\n")
            before_last = text[:last_index]
            after_last = text[last_index:]
            modified_before_last = before_last.replace("\n", "\n" + self.line_start)
            text = modified_before_last + after_last

        print(text, flush=True, end="" if not stream_end else None)

        # Update the counter of characters on this line
        if text.endswith("\n"):
            self.printed_width = 0
        else:
            self.printed_width += len(text)


class ChatApp:
    """
    This class is a demonstration of how to use Llama model to build a basic ChatApp.
    This App uses two models:
        * Prompt Processor
            - Instantiation with sequence length 128. Used to process user
              prompt.
        * Token Generator
            - Instantiation with sequence length 1. Used to predict
              auto-regressive response.
    """

    def __init__(
        self,
        model_cls: type[BaseModel],
        get_input_prompt_with_tags: Callable,
        tokenizer: Any,
        end_tokens: set[str],
        seed: int = 42,
    ):
        """
        Base ChatApp that generates one response for given input token.

            model_cls: Llama Model class that will be used to instantiate model
            get_input_prompt_with_tags: Function to wrap input prompt with appropriate tags
            prepare_combined_attention_mask: Function to combine and build attention mask,
            tokenizer: Tokenizer to use,
            end_tokens: Set of end tokens to convey end of token generation,
        """
        self.model_cls = model_cls
        self.get_input_prompt_with_tags = get_input_prompt_with_tags
        self.tokenizer = tokenizer
        self.end_tokens = end_tokens
        self.seed = seed

    def generate_output_prompt(
        self,
        input_prompt: str,
        context_length: int,
        max_output_tokens: int,
        checkpoint: CheckpointSpec | None = None,
        model_from_pretrained_extra: dict = None,
    ):
        if model_from_pretrained_extra is None:
            model_from_pretrained_extra = {}
        set_seed(self.seed)
        input_prompt_processed = self.get_input_prompt_with_tags(
            user_input_prompt=input_prompt
        )

        host_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        input_tokens = self.tokenizer(
            input_prompt_processed,
            return_tensors="pt",
        ).to(host_device)

        model_params = {
            "context_length": context_length,
            "host_device": host_device,
            **model_from_pretrained_extra,
        }
        checkpoint = None if checkpoint == "DEFAULT_UNQUANTIZED" else checkpoint
        if checkpoint is not None:
            model_params["checkpoint"] = checkpoint

        models = [
            LLM_Loader(self.model_cls, sequence_length, model_params, host_device)
            for sequence_length in (1, 128)
        ]
        if "fp_model" in model_from_pretrained_extra:
            config = model_from_pretrained_extra["fp_model"].llm_config
        else:
            config = models[-1].load().llm_config

        # TODO: Use instance in model already?
        rope_embedding = self.model_cls.EmbeddingClass(
            max_length=context_length, config=config
        )
        inferencer = LLM_Generator(
            models,
            self.tokenizer,
            rope_embedding,
        )

        # can set temperature, topK, topP, etc here
        end_token_ids = []
        for token in self.end_tokens:
            token_ids = self.tokenizer.encode(token, add_special_tokens=False)
            if len(token_ids) == 1:
                token_id = token_ids[0]
                end_token_ids.append(token_id)
        end_token_ids.append(self.tokenizer.eos_token_id)
        inferencer.generation_config = GenerationConfig(
            max_new_tokens=max_output_tokens,
            eos_token_id=end_token_ids,
            pad_token_id=self.tokenizer.pad_token_id,
            do_sample=True,
            top_k=40,
            top_p=0.95,
            temperature=0.8,
        )

        streamer = IndentedTextStreamer(
            tokenizer=self.tokenizer, skip_prompt=False, line_start="    + "
        )
        inferencer.generate(
            inputs=input_tokens["input_ids"],
            attention_mask=input_tokens["attention_mask"],
            generation_config=inferencer.generation_config,
            streamer=streamer,
        )
        del inferencer

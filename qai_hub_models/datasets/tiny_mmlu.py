# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

import torch
from datasets import IterableDataset, load_dataset
from transformers import PreTrainedTokenizerBase

from qai_hub_models.datasets.common import BaseDataset, DatasetMetadata, DatasetSplit


class TinyMMLU(BaseDataset):
    def __init__(
        self,
        tokenizer: PreTrainedTokenizerBase,
        block_size: int = 128,
        context_length: int = 4096,
        split: DatasetSplit = DatasetSplit.TEST,
        num_samples: int = 0,
    ):
        self.block_size = block_size
        self.context_length = context_length
        self.tokenizer = tokenizer
        self.num_samples = num_samples

        if split == DatasetSplit.TEST:
            self.split_str = "test"
        else:
            raise ValueError("TinyMMLU dataset currently only supports `test` split")

        self.dataset = load_dataset(
            path="tinyBenchmarks/tinyMMLU", split=self.split_str
        )
        self.preprocess_dataset()

    @staticmethod
    def collate_fn(
        batch: list[dict[str, torch.Tensor]],
    ) -> tuple[
        torch.Tensor, torch.Tensor, torch.Tensor | tuple[torch.Tensor, torch.Tensor]
    ]:
        return batch[0]["input_ids"], batch[0]["attention_mask"], batch[0]["label"]

    def __len__(self) -> int:
        if self.num_samples != 0:
            if self.num_samples > 100:
                raise ValueError("This dataset only has 100 samples for evalutaion.")
            return self.num_samples
        return len(self.dataset)

    def preprocess_dataset(self):
        # if a cache file storing the current computation from function can be identified, use it instead of recomputing.
        map_kwargs = {"num_proc": None, "load_from_cache_file": True}

        def tokenize(sample):
            tokenized_question = self.tokenizer(
                sample["input_formatted"],
                return_token_type_ids=False,
                add_special_tokens=True,
            )

            tokenized_question = {
                k: [[field[-self.context_length :]] for field in v]
                for k, v in tokenized_question.items()
            }

            tokenized_answer = self.tokenizer(
                ["Answer: " + chr(ord("A") + answer) for answer in sample["answer"]],
                return_token_type_ids=False,
                add_special_tokens=False,
                return_tensors="pt",
            )

            result = tokenized_question
            # Grab only the last token
            answer_token_ids = tokenized_answer["input_ids"][:, -1:]
            result.update({"label": answer_token_ids})
            return result

        self.dataset = self.dataset.map(
            tokenize,
            batched=True,
            remove_columns=[
                "question",
                "subject",
                "choices",
                "answer",
                "input_formatted",
            ],
            **(map_kwargs if not isinstance(self.dataset, IterableDataset) else {}),
        )

    def __getitem__(self, idx: int):
        return {
            key: torch.Tensor(value).to(dtype=torch.int)
            for key, value in self.dataset[idx].items()
        }

    def _download_data(self) -> None:
        pass

    @staticmethod
    def default_samples_per_job() -> int:
        """The default value for how many samples to run in each inference job."""
        return 1

    @staticmethod
    def get_dataset_metadata() -> DatasetMetadata:
        return DatasetMetadata(
            link="https://huggingface.co/datasets/tinyBenchmarks/tinyMMLU",
            split_description="test split",
        )

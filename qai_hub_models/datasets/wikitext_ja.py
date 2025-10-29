# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from datasets import Dataset, load_dataset

from qai_hub_models.datasets.wikitext import WikiText


class WikiText_Japanese(WikiText):
    def load_raw_dataset(self) -> Dataset:
        dataset = load_dataset("range3/wikipedia-ja-20230101")["train"]
        if self.split_str == "test":
            return dataset[20000:20080]
        if self.split_str == "train":
            return dataset[0:20000]
        raise ValueError(
            "Wikitext Japanese dataset currently only supports `test` and `train` split"
        )

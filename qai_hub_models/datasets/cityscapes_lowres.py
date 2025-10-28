# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from qai_hub_models.datasets.cityscapes import CityscapesDataset
from qai_hub_models.datasets.common import DatasetSplit


class CityscapesLowResDataset(CityscapesDataset):
    def __init__(
        self,
        split: DatasetSplit = DatasetSplit.TRAIN,
        input_images_zip: str | None = None,
        input_gt_zip: str | None = None,
    ):
        super().__init__(split, input_images_zip, input_gt_zip, make_lowres=True)

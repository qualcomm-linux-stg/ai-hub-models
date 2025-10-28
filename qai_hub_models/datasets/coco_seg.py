# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from typing import Literal

import cv2
import numpy as np
import torch
from PIL import Image

from qai_hub_models.datasets.coco import CocoDataset, CocoDatasetClass
from qai_hub_models.datasets.common import DatasetSplit
from qai_hub_models.utils.image_processing import app_to_net_image_inputs
from qai_hub_models.utils.input_spec import InputSpec


class CocoSegDataset(CocoDataset):
    """
    Wrapper class around COCO dataset https://cocodataset.org/

    Contains Segmentation samples and labels spanning 80 or 91 classes.

    This wrapper supports the train and val splits of the 2017 version.
    """

    def __init__(
        self,
        split: DatasetSplit = DatasetSplit.TRAIN,
        input_spec: InputSpec | None = None,
        max_boxes: int = 100,
        num_samples: int = 5000,
        num_classes: CocoDatasetClass = CocoDatasetClass.SUBSET_CLASSES,
        label_types: list[Literal["detections", "segmentations"]] | None = None,
    ):
        super().__init__(
            split,
            input_spec,
            max_boxes,
            num_samples,
            num_classes,
            label_types or ["segmentations"],
        )

    def __getitem__(
        self, index: int
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor, int]]:
        """
        Get dataset item.

        Parameters
        ----------
        index
            Index of the sample to retrieve.


        Returns
        -------
        image
            RGB, range [0-1] network input image.

        ground_truth
            mask_data
                mask data with shape (self.max_boxes, self.target_h, self.target_w)
            labels
                labels with shape (self.max_boxes,)
            bbox_count
                number of actual boxes present
        """
        from fiftyone.core.sample import SampleView

        sample = self.dataset[index : index + 1].first()
        assert isinstance(sample, SampleView)
        image = Image.open(sample.filepath).convert("RGB")
        image = image.resize((self.target_w, self.target_h))
        width, height = image.size

        masks_list = []
        labels_list = []
        if sample.ground_truth is not None:
            for annotation in sample.ground_truth.detections:
                if annotation.label not in self.label_map:
                    print(f"Warning: Invalid label {annotation.label}")
                    continue
                mask = annotation.mask
                x, y, w, h = annotation.bounding_box

                point_x1 = int(x * width)
                point_x2 = point_x1 + int(w * width)
                point_y1 = int(y * height)
                point_y2 = point_y1 + int(h * height)

                mask_resized = cv2.resize(
                    mask.astype(np.uint8),
                    (point_x2 - point_x1, point_y2 - point_y1),
                    interpolation=cv2.INTER_LINEAR,
                )

                # Change mask size from bbox size to image size
                mask_image = np.zeros((height, width))
                mask_image[point_y1:point_y2, point_x1:point_x2] = mask_resized

                masks_list.append(mask_image)
                labels_list.append(self.label_map[annotation.label])

        masks = torch.tensor(masks_list).to(torch.uint8)
        labels = torch.tensor(labels_list).to(torch.uint8)

        num_boxes = len(labels)
        if num_boxes == 0:
            masks = torch.zeros((self.max_boxes, self.target_h, self.target_w)).to(
                torch.uint8
            )
            labels = torch.zeros(self.max_boxes).to(torch.uint8)
        elif num_boxes > self.max_boxes:
            raise ValueError(
                f"Sample has more boxes than max boxes {self.max_boxes}. "
                "Re-initialize the dataset with a larger value for max_boxes."
            )
        else:
            extra_masks = torch.zeros(
                (
                    self.max_boxes - num_boxes,
                    self.target_h,
                    self.target_w,
                )
            ).to(torch.uint8)
            extra_labels = torch.zeros(self.max_boxes - num_boxes).to(torch.uint8)
            masks = torch.concat([masks, extra_masks])
            labels = torch.concat([labels, extra_labels])

        image_pt = app_to_net_image_inputs(image)[1].squeeze(0)
        return image_pt, (masks, labels, num_boxes)

    @staticmethod
    def default_samples_per_job() -> int:
        """The default value for how many samples to run in each inference job."""
        return 100

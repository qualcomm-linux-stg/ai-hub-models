# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from pathlib import Path
from typing import cast

import cv2
import torch

from qai_hub_models.datasets.cocobody import CocoBodyDataset
from qai_hub_models.datasets.common import DatasetSplit
from qai_hub_models.utils.input_spec import InputSpec


class CocoFaceDataset(CocoBodyDataset):
    """
    Wrapper class around CocoFace dataset
    http://images.cocodataset.org/

    COCO keypoints::
        0-16 : 'jawline',
        17-21: 'right eyebrow',
        22-26: 'left eyebrow',
        27-30: 'nose bridge',
        31-35: 'nose bottom',
        36-41: 'right eye',
        42-47: 'left eye',
        48-59: 'outer lips'
        60-67: 'inner lips'
    """

    def __init__(
        self,
        split: DatasetSplit = DatasetSplit.VAL,
        input_spec: InputSpec | None = None,
        num_samples: int = -1,
    ):
        super().__init__(split, input_spec, num_samples)
        self.kpt_db: list[tuple[Path, int, int, torch.Tensor]]

    def _load_kpt_db(self) -> list[tuple[Path, int, int, torch.Tensor]]:
        kpt_db: list[tuple[Path, int, int, torch.Tensor]] = []
        for img_id in self.img_ids:
            img_info = self.cocoGt.loadImgs(img_id)[0]
            ann_ids = self.cocoGt.getAnnIds(imgIds=img_id, catIds=[1], iscrowd=False)
            annotations = self.cocoGt.loadAnns(ann_ids)

            for ann in annotations:
                if ann.get("face_valid", 0) is False:
                    continue  # Keep only persons with valid face

                x1, y1, w, h = ann["face_box"]
                if ann.get("area", 0) > 0 and x1 >= 0 and y1 >= 0:
                    x2 = x1 + w
                    y2 = y1 + h
                    bbox = (x1, y1, x2, y2)

                    img_path = self.image_dir / cast(str, img_info["file_name"])

                    if not img_path.exists():
                        raise FileNotFoundError(f"Image file not found at {img_path}")

                    kpt_db.append(
                        (
                            img_path,
                            img_id,
                            ann.get("category_id", 0),
                            torch.tensor(bbox, dtype=torch.float32),
                        )
                    )
                    break
        return kpt_db

    def __getitem__(
        self, index: int
    ) -> tuple[torch.Tensor, tuple[int, int, torch.Tensor]]:
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
            imageId : int
                The ID of the image.
            category_id : int
                The ground truth category ID
            bbox : torch.Tensor
                The ground truth face bounding box in xyxy format.
                This box is in pixel space.
        """
        file_name, image_id, category_id, bbox = self.kpt_db[index]
        img_path = file_name

        x0, y0, x1, y1 = bbox
        image_array = cv2.imread(cast(str, img_path))

        image_array = cv2.resize(
            image_array[int(y0) : int(y1 + 1), int(x0) : int(x1 + 1)],
            (self.target_h, self.target_w),
            interpolation=cv2.INTER_LINEAR,
        )

        image = torch.from_numpy(image_array).float().permute(2, 0, 1)

        return image, (image_id, category_id, bbox)

    @staticmethod
    def default_samples_per_job() -> int:
        """The default value for how many samples to run in each inference job."""
        return 1000

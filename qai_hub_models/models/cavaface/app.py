# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

from collections.abc import Callable

import numpy as np
import torch
from PIL.Image import Image as PILImage

from qai_hub_models.utils.image_processing import (
    app_to_net_image_inputs,
    resize_pad,
)


class CavaFaceApp:
    """
    Lightweight application for CavaFace face recognition.

    This app processes input images and generates 512-dimensional face embeddings
    using a CavaFace model for face recognition tasks.

    """

    def __init__(
        self,
        model: Callable[[torch.Tensor], torch.Tensor],
        input_height: int,
        input_width: int,
    ):
        self.model = model
        self.input_height = input_height
        self.input_width = input_width

    def predict_features(self, image: PILImage, use_flip: bool = False) -> np.ndarray:
        """
        Generate a face embedding from an input image.

        Args:
            image: Input PIL Image
            use_flip: If True, creates an ensemble by running inference on both
                    the original image and its horizontally flipped version,
                    then averages the resulting embeddings for better accuracy.

        Returns
        -------
            np.ndarray
                Normalized 512-dimensional face embedding
        """
        # Preprocess
        NCHW_torch_images = app_to_net_image_inputs(image)[1]
        img_tensor = resize_pad(
            NCHW_torch_images, (self.input_height, self.input_width)
        )[0]

        if use_flip:
            flipped_tensor = img_tensor.flip(3)
            img_tensor = torch.cat([img_tensor, flipped_tensor], dim=0)

        embeddings = self.model(img_tensor.contiguous())
        if use_flip:
            flipped_tensor = img_tensor.flip(3)
            flipped_embeddings = self.model(flipped_tensor.contiguous())
            embeddings = (embeddings[0] + flipped_embeddings[0]) / 2
        else:
            embeddings = embeddings[0]

        return np.asarray(embeddings)

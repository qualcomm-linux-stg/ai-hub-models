# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import cv2
import numpy as np
import torch

if TYPE_CHECKING:
    from PIL.Image import Image

from qai_hub_models.models.facemap_3dmm.model import FaceMap_3DMM
from qai_hub_models.models.facemap_3dmm.utils import (
    project_landmark,
    transform_landmark_coordinates,
)
from qai_hub_models.utils.image_processing import app_to_net_image_inputs


class FaceMap_3DMMApp:
    """
    This class consists of light-weight "app code" that is required to perform end to end inference with FaceMap_3DMMApp.

    The app uses 1 model:
        * FaceMap_3DMM

    For a given image input, the app will:
        * pre-process the image (convert to RGB of range[0, 1])
        * Run FaceMap_3DMM inference
        * Convert the output parameters into landmark points
        * Display the output lanrmarks on the image
    """

    def __init__(self, model: Callable[[torch.Tensor], torch.Tensor]):
        self.model = model

    def predict(self, *args, **kwargs):
        return self.landmark_prediction(*args, **kwargs)

    def landmark_prediction(
        self,
        pixel_values_or_image: torch.Tensor | np.ndarray | Image,
        x0: np.int32,
        x1: np.int32,
        y0: np.int32,
        y1: np.int32,
    ) -> tuple:
        """
        Return the input image with the predicted lmk overlayed on it.

        Parameters
        ----------
            pixel_values_or_image:
                PIL image(s)
                or
                numpy array (N H W C x uint8) or (H W C x uint8) -- both RGB channel layout
                or
                pyTorch tensor (N C H W x fp32, value range is [0, 1]), RGB channel layout
            x0: numpy int32 -- left coordinate of face bounding box
            x1: numpy int32 -- right coordinate of face bounding box
            y0: numpy int32 -- top coordinate of face bounding box
            y1: numpy int32 -- bottom coordinate of face bounding box

        Returns
        -------
            lmk_images: numpy array -- images with predicted landmarks displayed.
        """
        [image], _ = app_to_net_image_inputs(pixel_values_or_image)

        resized_height, resized_width = FaceMap_3DMM.get_input_spec()["image"][0][2:]

        CHW_fp32_torch_crop_image = (
            torch.from_numpy(
                cv2.resize(
                    image[y0 : y1 + 1, x0 : x1 + 1],
                    (resized_height, resized_width),
                    interpolation=cv2.INTER_LINEAR,
                )
            ).float()
            / 255
        )

        output = self.model(CHW_fp32_torch_crop_image.permute(2, 0, 1).unsqueeze(0))

        landmark = project_landmark(output[0])
        transform_landmark_coordinates(
            landmark,
            (int(x0), int(y0), int(x1), int(y1)),
            resized_height,
            resized_width,
        )

        output_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        # Draw face box
        output_image = cv2.rectangle(
            output_image, (int(x0), int(y0)), (int(x1), int(y1)), (0, 255, 0), 2
        )

        # Draw landmark
        for n in range(landmark.shape[0]):
            output_image = cv2.circle(
                output_image,
                (int(landmark[n, 0]), int(landmark[n, 1])),
                2,
                (0, 0, 255),
                -1,
            )

        return landmark, output_image

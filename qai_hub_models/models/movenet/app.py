# ---------------------------------------------------------------------
# Copyright (c) 2024-2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------


from __future__ import annotations

from collections.abc import Callable

import numpy as np
import torch
from PIL import Image

from qai_hub_models.utils.draw import draw_connections, draw_points
from qai_hub_models.utils.image_processing import (
    app_to_net_image_inputs,
    denormalize_coordinates,
    resize_pad,
)

# Most code here is from the source repo https://github.com/lee-man/movenet-pytorch

PART_NAMES = [
    "nose",
    "leftEye",
    "rightEye",
    "leftEar",
    "rightEar",
    "leftShoulder",
    "rightShoulder",
    "leftElbow",
    "rightElbow",
    "leftWrist",
    "rightWrist",
    "leftHip",
    "rightHip",
    "leftKnee",
    "rightKnee",
    "leftAnkle",
    "rightAnkle",
]

# NUM_KEYPOINTS = len(PART_NAMES)

PART_IDS = {pn: pid for pid, pn in enumerate(PART_NAMES)}
CONNECTED_PART_NAMES = [
    ("leftHip", "leftShoulder"),
    ("leftElbow", "leftShoulder"),
    ("leftElbow", "leftWrist"),
    ("leftHip", "leftKnee"),
    ("leftKnee", "leftAnkle"),
    ("rightHip", "rightShoulder"),
    ("rightElbow", "rightShoulder"),
    ("rightElbow", "rightWrist"),
    ("rightHip", "rightKnee"),
    ("rightKnee", "rightAnkle"),
    ("leftShoulder", "rightShoulder"),
    ("leftHip", "rightHip"),
]
CONNECTED_PART_INDICES = [(PART_IDS[a], PART_IDS[b]) for a, b in CONNECTED_PART_NAMES]


class MovenetApp:
    """
    This class consists of light-weight "app code" that is required to perform end to end inference with Posenet.

    The app uses 1 model:
        * Movenet

    For a given image input, the app will:
        * pre-process the image
        * Run Movenet inference
        * Convert the output into a list of keypoint coordiates
        * Return raw coordinates or an image with keypoints overlayed
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

    def predict(self, *args, **kwargs):
        # See predict_pose_keypoints.
        return self.predict_pose_keypoints(*args, **kwargs)

    def predict_pose_keypoints(
        self,
        image: Image.Image | torch.Tensor | np.ndarray | list[Image.Image],
        raw_output: bool = False,
        confidence_threshold=0.001,
    ) -> list[Image.Image] | np.ndarray:
        """
        Predicts up to 17 pose keypoints for up to 10 people in the image.

        Parameters
        ----------
            image: Image on which to predict pose keypoints.
            raw_output: bool


        Returns
        -------
            If raw_output is true, returns:
                kpt_with_conf: np.ndarray with shape (B, 1, 17, 3)
                    keypoint coordinates with confidence.

            Otherwise, returns:
                predicted_images: PIL.Image.Image with original image size.
                    Image with keypoints drawn.
        """
        NHWC_int_numpy_frames, NCHW_torch_images = app_to_net_image_inputs(image)
        NCHW_torch_images, scale, pad = resize_pad(
            NCHW_torch_images, (self.input_height, self.input_width)
        )

        # Run model, decode coordinates from [0-1] in network input space to original app image input pixel space.
        kpt_with_conf = self.model(NCHW_torch_images)
        denormalize_coordinates(
            kpt_with_conf[..., :2], (self.input_height, self.input_width), scale, pad
        )

        if raw_output:
            return np.array(kpt_with_conf)

        predicted_images = []
        connected_point_idx = torch.tensor(
            CONNECTED_PART_INDICES, dtype=torch.int64
        ).flatten()
        for img, img_kpt in zip(NHWC_int_numpy_frames, kpt_with_conf):
            img_kpt = img_kpt[0]
            img_connected_kpt_pairs = img_kpt[connected_point_idx].view(
                len(connected_point_idx) // 2, 2, 3
            )

            # Filter by confience threshold.
            img_kpt = img_kpt[img_kpt[:, 2] > confidence_threshold, :2]
            img_connected_kpt_pairs = img_connected_kpt_pairs[
                torch.all(
                    img_connected_kpt_pairs[:, :, 2] > confidence_threshold, dim=1
                ),
                :,
                :2,
            ]

            # Draw points and connections.
            draw_points(img, img_kpt)
            draw_connections(img, img_connected_kpt_pairs)
            predicted_images.append(Image.fromarray(img.astype(np.uint8)))

        return predicted_images

# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from typing import cast

import numpy as np
from PIL import Image

from qai_hub_models.models.mediapipe_pose.app import MediaPipePoseApp
from qai_hub_models.models.mediapipe_pose.model import (
    MODEL_ASSET_VERSION,
    MODEL_ID,
    MediaPipePose,
)
from qai_hub_models.utils.args import (
    add_output_dir_arg,
    demo_model_components_from_cli_args,
    get_model_cli_parser,
    get_on_device_demo_parser,
    validate_on_device_demo_args,
)
from qai_hub_models.utils.asset_loaders import CachedWebModelAsset, load_image
from qai_hub_models.utils.camera_capture import capture_and_display_processed_frames
from qai_hub_models.utils.display import display_or_save_image
from qai_hub_models.utils.evaluate import EvalMode

INPUT_IMAGE_ADDRESS = CachedWebModelAsset.from_asset_store(
    MODEL_ID, MODEL_ASSET_VERSION, "pose.jpeg"
)


# Run Mediapipe Pose landmark detection end-to-end on a sample image or camera stream.
# The demo will display output with the predicted landmarks & bounding boxes drawn.
def mediapipe_pose_demo(model_cls: type[MediaPipePose], is_test: bool = False):
    # Demo parameters
    parser = get_model_cli_parser(model_cls)
    parser.add_argument(
        "--image",
        type=str,
        required=False,
        help="image file path or URL. Image spatial dimensions (x and y) must be multiples",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera Input ID",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.75,
        help="Score threshold for NonMaximumSuppression",
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.3,
        help="Intersection over Union (IoU) threshold for NonMaximumSuppression",
    )
    add_output_dir_arg(parser)
    get_on_device_demo_parser(parser)

    print(
        "Note: This demo is running through torch, and not meant to be real-time without dedicated ML hardware."
    )
    print("Use Ctrl+C in your terminal to exit.")

    args = parser.parse_args([] if is_test else None)
    validate_on_device_demo_args(args, MODEL_ID)

    if is_test:
        args.image = INPUT_IMAGE_ADDRESS

    torch_model = model_cls.from_pretrained()
    if args.eval_mode == EvalMode.ON_DEVICE:
        if args.hub_model_id:
            detector, landmark_detector = demo_model_components_from_cli_args(
                MediaPipePose, MODEL_ID, args
            )
        else:
            raise ValueError(
                "If running this demo with on device, must supply hub_model_id."
            )
    else:
        detector = torch_model.pose_detector
        landmark_detector = torch_model.pose_landmark_detector

    # Load app
    app = MediaPipePoseApp(
        detector,  # type: ignore[arg-type]
        landmark_detector,  # type: ignore[arg-type]
        torch_model.pose_detector.anchors,
        torch_model.pose_detector.get_input_spec(),
        torch_model.pose_landmark_detector.get_input_spec(),
    )
    print("Model and App Loaded")

    if args.image:
        image = load_image(args.image).convert("RGB")
        pred_image = app.predict_landmarks_from_image(image)
        assert isinstance(pred_image[0], np.ndarray)
        out_image = Image.fromarray(pred_image[0], "RGB")
        if not is_test:
            display_or_save_image(out_image, args.output_dir)
    else:

        def frame_processor(frame: np.ndarray) -> np.ndarray:
            return cast(np.ndarray, app.predict_landmarks_from_image(frame)[0])

        capture_and_display_processed_frames(
            frame_processor, "QAIHM Mediapipe Pose Demo", args.camera
        )


def main(is_test: bool = False):
    return mediapipe_pose_demo(MediaPipePose, is_test)


if __name__ == "__main__":
    main()

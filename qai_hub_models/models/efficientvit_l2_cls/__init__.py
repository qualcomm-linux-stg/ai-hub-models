# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from qai_hub_models.models._shared.imagenet_classifier.app import (
    ImagenetClassifierApp as App,  # noqa: F401
)

from .model import MODEL_ID  # noqa: F401
from .model import EfficientViT as Model  # noqa: F401

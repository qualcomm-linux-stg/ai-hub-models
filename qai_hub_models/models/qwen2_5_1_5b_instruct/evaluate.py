# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from qai_hub_models.models._shared.llm.evaluate import llm_evaluate
from qai_hub_models.models.qwen2_5_1_5b_instruct import FP_Model, Model
from qai_hub_models.models.qwen2_5_1_5b_instruct.model import SUPPORTED_PRECISIONS

if __name__ == "__main__":
    llm_evaluate(
        quantized_model_cls=Model,
        fp_model_cls=FP_Model,
        supported_precisions=SUPPORTED_PRECISIONS,
    )

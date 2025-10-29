# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from enum import Enum, unique
from typing import Optional

import qai_hub as hub
from typing_extensions import assert_never

from qai_hub_models.models.common import Precision, TargetRuntime
from qai_hub_models.scorecard.envvars import (
    DeploymentEnvvar,
    QAIRTVersionEnvvar,
)
from qai_hub_models.utils.hub_clients import (
    default_hub_client_as,
    get_hub_client_or_raise,
)


@unique
class ScorecardCompilePath(Enum):
    TFLITE = "tflite"
    QNN_DLC = "qnn_dlc"
    QNN_DLC_VIA_QNN_EP = "qnn_dlc_via_qnn_ep"
    QNN_CONTEXT_BINARY = "qnn_context_binary"
    ONNX = "onnx"
    PRECOMPILED_QNN_ONNX = "precompiled_qnn_onnx"
    GENIE = "genie"
    ONNXRUNTIME_GENAI = "onnxruntime_genai"
    ONNX_FP16 = "onnx_fp16"

    def __str__(self):
        return self.name.lower()

    @property
    def enabled(self) -> bool:
        from qai_hub_models.scorecard.path_profile import ScorecardProfilePath

        profile_paths = [
            x for x in ScorecardProfilePath if x.enabled and x.compile_path == self
        ]
        return len(profile_paths) > 0

    @staticmethod
    def all_paths(
        enabled: Optional[bool] = None,
        supports_precision: Optional[Precision] = None,
        is_aot_compiled: Optional[bool] = None,
        include_genai_paths: bool = False,
    ) -> list[ScorecardCompilePath]:
        """
        Get all compile paths that match the given attributes.
        If an attribute is None, it is ignored when filtering paths.
        """
        return [
            path
            for path in ScorecardCompilePath
            if (enabled is None or path.enabled == enabled)
            and (
                supports_precision is None
                or path.supports_precision(supports_precision)
            )
            and (
                is_aot_compiled is None
                or path.runtime.is_aot_compiled == is_aot_compiled
            )
            and (include_genai_paths or (not path.runtime.is_exclusively_for_genai))
        ]

    @property
    def runtime(self) -> TargetRuntime:
        if self == ScorecardCompilePath.TFLITE:
            return TargetRuntime.TFLITE
        if self == ScorecardCompilePath.ONNX or self == ScorecardCompilePath.ONNX_FP16:  # noqa: PLR1714 | Can't merge comparisons and use assert_never
            return TargetRuntime.ONNX
        if self == ScorecardCompilePath.PRECOMPILED_QNN_ONNX:
            return TargetRuntime.PRECOMPILED_QNN_ONNX
        if self == ScorecardCompilePath.QNN_CONTEXT_BINARY:
            return TargetRuntime.QNN_CONTEXT_BINARY
        if (
            self == ScorecardCompilePath.QNN_DLC  # noqa: PLR1714 | Can't merge comparisons and use assert_never
            or self == ScorecardCompilePath.QNN_DLC_VIA_QNN_EP
        ):
            return TargetRuntime.QNN_DLC
        if self == ScorecardCompilePath.GENIE:
            return TargetRuntime.GENIE
        if self == ScorecardCompilePath.ONNXRUNTIME_GENAI:
            return TargetRuntime.ONNXRUNTIME_GENAI
        assert_never(self)

    @property
    def is_universal(self) -> bool:
        """Whether a single asset produced by this path is applicable to any device."""
        return not self.runtime.is_aot_compiled

    def supports_precision(self, precision: Precision) -> bool:
        if self == ScorecardCompilePath.ONNX_FP16:
            return not precision.has_quantized_activations

        return self.runtime.supports_precision(precision)

    @property
    def has_nonstandard_compile_options(self):
        """
        If this path passes additional options beyond what the underlying TargetRuntime
        passes (eg --compute_unit), then it's considered nonstandard.
        """
        return self.value not in TargetRuntime._value2member_map_

    def get_compile_options(
        self,
        precision: Precision = Precision.float,
        device: hub.Device | None = None,
        include_target_runtime: bool = False,
        include_default_qaihm_qnn_version: bool = False,
    ) -> str:
        out = ""
        if include_target_runtime:
            out += self.runtime.aihub_target_runtime_flag

        if self.runtime == TargetRuntime.QNN_CONTEXT_BINARY:
            # Without this flag, graph names are random.
            # Scorecard job caching relies on models keeping the same md5 hash if they haven't changed.
            #
            # By setting this flag, we remove a source of randomness in compiled QNN assets.
            # THIS ONLY APPLIES TO SCORECARD, NOT USERS DIRECTLY CALLING EXPORT.PY
            out += " --qnn_options context_enable_graphs=default_graph"

        if self.runtime.qairt_version_changes_compilation:
            qairt_version_str = QAIRTVersionEnvvar.get()
            with default_hub_client_as(get_hub_client_or_raise(DeploymentEnvvar.get())):
                qairt_version = QAIRTVersionEnvvar.get_qairt_version(
                    self.runtime, qairt_version_str
                )
            if QAIRTVersionEnvvar.is_default(qairt_version_str):
                # We typically don't want the default QAIRT version added here if it matches with the AI Hub models default.
                # This allows the export script (which scorecard relies on) to pass in the default version that users will see when they use the CLI.
                #
                # Static models do need this included explicitly because they don't rely on export scripts.
                if include_default_qaihm_qnn_version:
                    # Certain runtimes use their own default version of QAIRT.
                    # If the user picks our the qaihm_default tag, we need use the runtime's
                    # default QAIRT version instead.
                    out = out + f" {qairt_version.explicit_hub_option}"
            else:
                # The explicit option will always pass `--qairt_version 2.XX`,
                # regardless of whether this is the AI Hub default.
                #
                # This is useful for tracking what QAIRT version applies for scorecard jobs.
                out = out + f" {qairt_version.explicit_hub_option}"

        if self == ScorecardCompilePath.QNN_DLC_VIA_QNN_EP:
            out = out + " --use_qnn_onnx_ep_converter"

        return out.strip()

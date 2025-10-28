# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional, cast

import qai_hub as hub
from pydantic import Field
from qai_hub.client import JobType

from qai_hub_models.configs.tool_versions import ToolVersions
from qai_hub_models.models.common import Precision
from qai_hub_models.scorecard import ScorecardDevice, ScorecardProfilePath
from qai_hub_models.utils.base_config import BaseQAIHMConfig
from qai_hub_models.utils.path_helpers import QAIHM_MODELS_ROOT


class QAIHMModelPerf(BaseQAIHMConfig):
    """Schema for perf.yaml files."""

    class PerformanceDetails(BaseQAIHMConfig):
        class TimeToFirstTokenRangeMillieconds(BaseQAIHMConfig):
            min: float
            max: float

        class PeakMemoryRangeMB(BaseQAIHMConfig):
            min: int
            max: int

            @staticmethod
            def from_bytes(
                mmin: int, mmax: int
            ) -> QAIHMModelPerf.PerformanceDetails.PeakMemoryRangeMB:
                return QAIHMModelPerf.PerformanceDetails.PeakMemoryRangeMB(
                    min=round(mmin / (1 << 20)),
                    max=round(mmax / (1 << 20)),
                )

        class LayerCounts(BaseQAIHMConfig):
            total: int
            npu: int = 0
            gpu: int = 0
            cpu: int = 0

            @staticmethod
            def from_layers(npu: int = 0, gpu: int = 0, cpu: int = 0):
                return QAIHMModelPerf.PerformanceDetails.LayerCounts(
                    total=npu + gpu + cpu,
                    npu=npu,
                    gpu=gpu,
                    cpu=cpu,
                )

            @property
            def primary_compute_unit(self):
                if self.npu == 0 and self.gpu == 0 and self.cpu == 0:
                    return "null"
                compute_unit_for_most_layers = max(self.cpu, self.gpu, self.npu)
                if compute_unit_for_most_layers == self.npu:
                    return "NPU"
                elif compute_unit_for_most_layers == self.gpu:
                    return "GPU"
                return "CPU"

        # Only set for LLMs.
        time_to_first_token_range_milliseconds: Optional[
            QAIHMModelPerf.PerformanceDetails.TimeToFirstTokenRangeMillieconds
        ] = None
        tokens_per_second: Optional[float] = None
        context_length: Optional[int] = None

        # Only set for non-LLMs.
        job_id: Optional[str] = None
        job_status: Optional[str] = None

        # Only set for successful non-LLM jobs.
        inference_time_milliseconds: Optional[float] = None
        estimated_peak_memory_range_mb: Optional[
            QAIHMModelPerf.PerformanceDetails.PeakMemoryRangeMB
        ] = None
        primary_compute_unit: Optional[str] = None
        layer_counts: Optional[QAIHMModelPerf.PerformanceDetails.LayerCounts] = None

        # Can be set for LLMs or for successful jobs.
        # The tool versions used by the profile jobs to execute this model.
        # All jobs will include QAIRT version, + the inference engine version used (tflite, onnx ,etc.)
        tool_versions: ToolVersions = Field(default_factory=ToolVersions)

    class AssetDetails(BaseQAIHMConfig):
        model_id: str
        tool_versions: ToolVersions = Field(default_factory=ToolVersions)

        @staticmethod
        def from_hub_job(job: hub.Job) -> QAIHMModelPerf.AssetDetails:
            """Extract asset details from the given compile or profile job."""
            if job._job_type == JobType.COMPILE:
                job = cast(hub.CompileJob, job)
                assert job.get_status().success, (
                    f"Cannot extract asset details from failed compile job {job.job_id}"
                )
                model_id = cast(hub.Model, job.get_target_model()).model_id
            elif job._job_type == JobType.PROFILE:
                job = cast(hub.ProfileJob, job)
                model_id = job.model.model_id
            else:
                raise NotImplementedError(f"Unsupported job type {job.job_type}")
            return QAIHMModelPerf.AssetDetails(
                model_id=model_id, tool_versions=ToolVersions.from_job(job)
            )

    class ComponentDetails(BaseQAIHMConfig):
        universal_assets: dict[ScorecardProfilePath, QAIHMModelPerf.AssetDetails] = (
            Field(default_factory=dict)
        )
        device_assets: dict[
            ScorecardDevice, dict[ScorecardProfilePath, QAIHMModelPerf.AssetDetails]
        ] = Field(default_factory=dict)
        performance_metrics: dict[
            ScorecardDevice,
            dict[ScorecardProfilePath, QAIHMModelPerf.PerformanceDetails],
        ] = Field(default_factory=dict)

    class PrecisionDetails(BaseQAIHMConfig):
        components: dict[str, QAIHMModelPerf.ComponentDetails] = Field(
            default_factory=dict
        )

    supported_devices: list[ScorecardDevice] = Field(default_factory=list)
    supported_chipsets: list[str] = Field(default_factory=list)
    precisions: dict[Precision, QAIHMModelPerf.PrecisionDetails] = Field(
        default_factory=dict
    )

    @property
    def empty(self):
        return (
            not self.supported_chipsets
            and not self.supported_devices
            and not self.precisions
        )

    def for_each_entry(
        self,
        callback: Callable[
            [
                Precision,
                str,
                ScorecardDevice,
                ScorecardProfilePath,
                QAIHMModelPerf.PerformanceDetails,
            ],
            bool | None,
        ],
        include_paths: Optional[list[ScorecardProfilePath]] = None,
    ) -> None:
        """
        Walk over each valid perf.yaml job entry and call the callback.

        Parameters
        ----------
        callback
            A function to call for each perf.yaml job entry.
            Func Params:
                precision: Precision
                    The precision for this entry,
                component: str
                    Component name. Will be Model Name if there is 1 component.
                device: ScorecardDevice,
                    Device for this entry.
                path: ScorecardProfilePath
                    Path for this entry.
                QAIHMModelPerf.PerformanceDetails
                    Actual entry perf data

            Func Returns:
                Boolean or None.
                If None or True, for_each_entry continues to walk over more entries.
                If False, for_each_entry will stop walking over additional entries.

        include_paths
            Scorecard Profile Paths to loop over. If None, uses all enabled paths.
        """
        for precision, precision_perf in self.precisions.items():
            for component_name, component_detail in precision_perf.components.items():
                for (
                    device,
                    device_detail,
                ) in component_detail.performance_metrics.items():
                    for path, profile_perf_details in device_detail.items():
                        if include_paths and path not in include_paths:
                            continue
                        res = callback(
                            precision,
                            component_name,
                            device,
                            path,
                            profile_perf_details,
                        )
                        # Note that res may be None. We ignore the return value in that case.
                        if res is False:
                            # If res is explicitly false, stop and return
                            return

    @classmethod
    def from_model(
        cls: type[QAIHMModelPerf], model_id: str, not_exists_ok: bool = False
    ) -> QAIHMModelPerf:
        perf_path = QAIHM_MODELS_ROOT / model_id / "perf.yaml"
        if not_exists_ok and not os.path.exists(perf_path):
            return QAIHMModelPerf()
        return cls.from_yaml(perf_path)

    def to_model_yaml(self, model_id: str) -> Path:
        out = QAIHM_MODELS_ROOT / model_id / "perf.yaml"
        self.to_yaml(out)
        return out

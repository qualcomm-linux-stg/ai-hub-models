# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

"""Items defined in this file require that AIMET-ONNX be installed."""

from __future__ import annotations

try:
    import aimet_onnx
    from aimet_common.utils import AimetLogger
    from aimet_onnx.quantsim import QuantizationSimModel as QuantSimOnnx

    aimet_onnx_is_installed = True
except (ImportError, ModuleNotFoundError):
    aimet_onnx_is_installed = False
import contextlib
import gc
import os
import shutil
import sys
from collections.abc import Collection
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import torch
from packaging import version
from qai_hub.client import DatasetEntries
from tqdm.autonotebook import tqdm

from qai_hub_models.evaluators.base_evaluators import _DataLoader
from qai_hub_models.models.common import SampleInputsType
from qai_hub_models.models.protocols import PretrainedHubModelProtocol
from qai_hub_models.utils.aimet.aimet_dummy_model import zip_aimet_model
from qai_hub_models.utils.asset_loaders import CachedWebModelAsset, qaihm_temp_dir
from qai_hub_models.utils.base_model import Precision
from qai_hub_models.utils.dataset_util import DataLoader, dataset_entries_to_dataloader
from qai_hub_models.utils.input_spec import InputSpec
from qai_hub_models.utils.onnx_helpers import kwargs_to_dict, mock_torch_onnx_inference
from qai_hub_models.utils.onnx_torch_wrapper import OnnxSessionTorchWrapper


def ensure_aimet_onnx_installed(
    expected_version: str | None = None, model_id: str | None = None
):
    if not aimet_onnx_is_installed:
        errstr = "AIMET-ONNX is missing but must be installed. "
        if not sys.platform.startswith("linux") and sys.platform not in [
            "win32",
            "cygwin",
        ]:
            errstr += "It is not supported on this operating system. You must use either Linux or Windows Subsystem for Linux to install AIMET-ONNX."
        else:
            if model_id is not None:
                install_target = f'"qai_hub_models[{model_id}]"'
            elif expected_version is not None:
                install_target = f"aimet-onnx=={expected_version}"
            else:
                install_target = '"qai_hub_models[<your_target_model_id_here>]"'

            if sys.platform in ["win32", "cygwin"]:
                errstr += "AIMET-ONNX is not supported on Windows. We suggest using Windows Subsystem for Linux (WSL) to create a python environment compatible with AIMET-ONNX.\nIn a compatible WSL python env, run "
            else:
                errstr += "Run "
            errstr += f"`pip install {install_target}` to install the correct version of AIMET-ONNX."

        if model_id is not None:
            errstr += f"\nAlternatively, for model export, you may run `python -m qai_hub_models.models.{model_id}.export.py --fetch-static-assets` to fetch pre-compiled assets for this model."

        raise RuntimeError(errstr)


def ensure_min_aimet_onnx_version(expected_version: str, model_id: str | None = None):
    ensure_aimet_onnx_installed(expected_version, model_id)
    if version.parse(aimet_onnx.__version__) < version.parse(expected_version):
        raise RuntimeError(
            f"Installed AIMET-ONNX version not supported. Expected >= {expected_version}, got {str(aimet_onnx.__version__)}\n"
            f"Please run `pip install aimet-onnx=={expected_version}`"
        )


def ensure_max_aimet_onnx_version(expected_version: str, model_id: str | None = None):
    ensure_aimet_onnx_installed(expected_version, model_id)
    if version.parse(aimet_onnx.__version__) < version.parse(expected_version):
        raise RuntimeError(
            f"Installed AIMET-ONNX version not supported. Expected=<{expected_version}, got {str(aimet_onnx.__version__)}\n"
            f"Please run `pip install transformers=={expected_version}`"
        )


@contextmanager
def set_aimet_log_level(log_level: int):
    area_log_levels = {}
    for area in AimetLogger.LogAreas:
        area_log_levels[area] = AimetLogger.get_area_logger(area).level

    try:
        AimetLogger.set_level_for_all_areas(log_level)
        yield
    finally:
        for area, level in area_log_levels.items():
            AimetLogger.set_area_logger_level(area, level)


class AIMETOnnxQuantizableMixin(PretrainedHubModelProtocol):
    """
    Mixin that allows a model to be quantized & exported to disk using AIMET.
    Inheritor must implement BaseModel for this mixin to function.
    """

    # For pre-calibrated asset lookup
    model_id: str = ""
    model_asset_version: int = -1

    def __init__(
        self,
        quant_sim: QuantSimOnnx | None,
    ):
        self.quant_sim = quant_sim
        if self.quant_sim is not None:
            self.input_names = [i.name for i in self.quant_sim.session.get_inputs()]
            self.output_names = [
                output.name for output in self.quant_sim.session.get_outputs()
            ]

    def convert_to_torchscript(
        self, input_spec: InputSpec | None = None, check_trace: bool = True
    ) -> Any:
        # This must be defined by the PretrainedHubModelProtocol ABC
        raise ValueError(
            f"Cannot call convert_to_torchscript on {self.__class__.__name__}"
        )

    def get_calibration_data(
        self,
        input_spec: InputSpec | None = None,
        num_samples: int | None = None,
    ) -> DatasetEntries | None:
        """
        Parameters
        ----------
        num_samples: None to use all. Specify `num_samples` to use fewer. If
        `num_samples` are more than available, use all available (same
        behavior as None)

        """
        return None

    @classmethod
    def get_calibrated_aimet_model(cls) -> tuple[str, str]:
        """Returns .onnx and .encodings paths"""
        if not cls.model_id or cls.model_asset_version == -1:
            raise ValueError("model_id and model_asset_version must be defined")

        subfolder = Path(getattr(cls, "default_subfolder", ""))

        # Returns .onnx and .encodings paths
        onnx_file = CachedWebModelAsset.from_asset_store(
            cls.model_id,
            cls.model_asset_version,
            str(subfolder / "model.onnx"),
        ).fetch()
        with contextlib.suppress(Exception):
            _ = CachedWebModelAsset.from_asset_store(
                cls.model_id,
                cls.model_asset_version,
                str(subfolder / "model.data"),
            ).fetch()
        aimet_encodings = CachedWebModelAsset.from_asset_store(
            cls.model_id,
            cls.model_asset_version,
            str(subfolder / "model.encodings"),
        ).fetch()
        return onnx_file, aimet_encodings

    def _apply_seq_mse(self, data: _DataLoader, num_batches: int):
        assert self.quant_sim is not None
        ensure_min_aimet_onnx_version("2.8.0")

        input_names = [inp.name for inp in self.quant_sim.session.get_inputs()]

        onnx_data = []
        for batch in tqdm(data, total=num_batches):
            onnx_data.append(  # noqa: PERF401
                {
                    k: v.cpu().detach().numpy()
                    for k, v in kwargs_to_dict(input_names, *batch).items()
                }
            )

        aimet_onnx.apply_seq_mse(self.quant_sim, onnx_data)

    def _apply_calibration(self, data: DataLoader, num_batches: int):
        assert self.quant_sim is not None

        def _forward(session, _):
            wrapper = OnnxSessionTorchWrapper(session, quantize_io=False)
            assert data.batch_size is not None
            for i, batch in tqdm(enumerate(data), total=num_batches):
                if num_batches and i * data.batch_size >= num_batches:
                    break

                if isinstance(batch, torch.Tensor):
                    batch = (batch,)

                wrapper.forward(*batch)

                gc.collect()
                torch.cuda.empty_cache()

        # TODO: Update AIMET-ONNX version for Stable Diffision.
        # Updae the calibration API to not use the forward calback
        self.quant_sim.compute_encodings(_forward, ())

    def quantize(
        self,
        data: DataLoader | None = None,
        num_samples: int | None = None,
        use_seq_mse: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        - data: If None, create data loader from get_calibration_data(), which
        must be implemented.
        """
        if data is None:
            calib_data = self.get_calibration_data()
            if calib_data is None:
                raise ValueError(
                    "`data` must be specified if get_calibration_data is not defined."
                )
            data = dataset_entries_to_dataloader(calib_data)

        num_iterations = num_samples or len(data)

        if use_seq_mse:
            self._apply_seq_mse(data=data, num_batches=num_iterations)

        print(f"Start QuantSim calibration for {self.__class__.__name__}")
        self._apply_calibration(data=data, num_batches=num_iterations)

    def _sample_inputs_impl(
        self, input_spec: InputSpec | None = None
    ) -> SampleInputsType:
        data = self.get_calibration_data()
        if data is None:
            # Fallback to BaseModel's impl
            data = self._sample_inputs_impl(input_spec)
        assert isinstance(data, dict)
        return data

    def forward(
        self,
        *args: torch.Tensor,
        **kwargs: torch.Tensor,
    ) -> torch.Tensor | Collection[torch.Tensor]:
        """QuantSim forward pass with torch.Tensor"""
        assert self.quant_sim is not None
        return mock_torch_onnx_inference(self.quant_sim.session, *args, **kwargs)

    def save_calibrated_checkpoint(self, output_checkpoint: str) -> None:
        """Save AIMET-ONNX checkpoint to output_checkpoint/subfolder, if"""
        default_subfolder = getattr(self.__class__, "default_subfolder", "")
        export_dir = output_checkpoint
        if default_subfolder:
            export_dir = str(Path(output_checkpoint) / default_subfolder)

        shutil.rmtree(export_dir, ignore_errors=True)
        os.makedirs(export_dir, exist_ok=True)

        print(f"Saving quantized {self.__class__.__name__} to {export_dir}")
        assert self.quant_sim is not None
        self.quant_sim.export(str(export_dir), "model")
        print(f"{self.__class__.__name__} saved to {export_dir}")

    @staticmethod
    def get_ort_providers(
        device: torch.device,
    ) -> list[str | tuple[str, dict[str, int]]]:
        if device.type == "cuda":
            return (
                [
                    ("CUDAExecutionProvider", {"device_id": device.index}),
                    "CPUExecutionProvider",
                ]
                if device.index is not None
                else ["CUDAExecutionProvider", "CPUExecutionProvider"]
            )
        return ["CPUExecutionProvider"]

    def convert_to_onnx_and_aimet_encodings(
        self,
        output_dir: str | Path,
        model_name: str | None = None,
        return_zip: bool = True,
    ) -> str:
        """
        Converts the torch module to a zip file containing an unquantized ONNX model
        and an AIMET quantization encodings file if return_zip is True (default).

        If return_zip is False, the model is exported to a directory.
        In that case, the output directory is set to:

            Path(output_dir) / f"{model_name}.aimet"

        and the existing directory is forcefully removed.
        """
        if model_name is None:
            model_name = self.__class__.__name__

        output_dir = Path(output_dir)

        if return_zip:
            # Ensure output_dir exists and define the zip path.
            os.makedirs(output_dir, exist_ok=True)
            zip_path = output_dir / f"{model_name}.aimet.zip"
            base_dir = Path(f"{model_name}.aimet")

            print(f"Exporting quantized {self.__class__.__name__} to {zip_path}")
            # Use a temporary directory to export the model before zipping.
            with qaihm_temp_dir() as tmpdir:
                export_dir = Path(tmpdir) / base_dir
                os.makedirs(export_dir)
                assert self.quant_sim is not None
                self.quant_sim.export(str(export_dir), "model")

                onnx_file_path = str(export_dir / "model.onnx")
                encoding_file_path = str(export_dir / "model.encodings")

                # Attempt to locate external data file.
                # aimet-onnx<=2.0.0 export external data with model.onnx.data
                # aimet-onnx>=2.3.0 export external data with model.data
                # version between 2.0 - 2.3 are broken on large models
                external_data_file_path = ""
                external_data_file_path2 = export_dir / "model.onnx.data"
                external_data_file_path1 = export_dir / "model.data"
                if external_data_file_path1.exists():
                    external_data_file_path = str(external_data_file_path1)
                elif external_data_file_path2.exists():
                    external_data_file_path = str(external_data_file_path2)

                zip_aimet_model(
                    str(zip_path),
                    base_dir,
                    onnx_file_path,
                    encoding_file_path,
                    external_data_file_path,
                )
            return str(zip_path)
        # Export directly to a directory at output_dir / f"{model_name}.aimet"
        export_dir = output_dir / f"{model_name}.aimet"
        shutil.rmtree(export_dir, ignore_errors=True)
        os.makedirs(export_dir, exist_ok=True)

        print(
            f"Exporting quantized {self.__class__.__name__} to directory {export_dir}"
        )
        assert self.quant_sim is not None
        self.quant_sim.export(str(export_dir), "model")
        return str(export_dir)

    def get_hub_quantize_options(self, precision: Precision) -> str:
        """AI Hub quantize options recommended for the model."""
        return ""

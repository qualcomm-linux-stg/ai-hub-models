# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import qai_hub as hub
import torch
from transformers import AutoConfig

from qai_hub_models.models._shared.llama3 import test
from qai_hub_models.models._shared.llm.evaluate import evaluate
from qai_hub_models.models._shared.llm.export import export_model
from qai_hub_models.models._shared.llm.model import cleanup
from qai_hub_models.models.common import Precision, TargetRuntime
from qai_hub_models.models.llama_v3_8b_instruct import (
    MODEL_ID,
    FP_Model,
    Model,
    PositionProcessor,
)
from qai_hub_models.models.llama_v3_8b_instruct.demo import llama_3_chat_demo
from qai_hub_models.models.llama_v3_8b_instruct.export import (
    DEFAULT_EXPORT_DEVICE,
    NUM_LAYERS_PER_SPLIT,
    NUM_SPLITS,
    SUPPORTED_PRECISION_RUNTIMES,
)
from qai_hub_models.models.llama_v3_8b_instruct.export import main as export_main
from qai_hub_models.models.llama_v3_8b_instruct.model import (
    DEFAULT_CONTEXT_LENGTH,
    MODEL_ASSET_VERSION,
)
from qai_hub_models.scorecard import (
    ScorecardCompilePath,
    ScorecardDevice,
)
from qai_hub_models.scorecard.execution_helpers import (
    get_compile_parameterized_pytest_config,
    pytest_device_idfn,
)
from qai_hub_models.utils.checkpoint import CheckpointSpec
from qai_hub_models.utils.llm_helpers import create_genie_config
from qai_hub_models.utils.model_cache import CacheMode
from qai_hub_models.utils.testing import allow_few_test_devices_for_llms
from qai_hub_models.utils.testing_export_eval import compile_via_export

DEFAULT_EVAL_SEQLEN = 2048


def test_create_genie_config():
    model_name = "meta-llama/Meta-Llama-3-8B-Instruct"
    context_length = 2048
    llm_config = AutoConfig.from_pretrained(model_name)
    model_list = [f"llama_v3_8b_instruct_part_{i}_of_5.bin" for i in range(1, 6)]
    actual_config = create_genie_config(context_length, llm_config, "rope", model_list)
    expected_config: dict[str, Any] = {
        "dialog": {
            "version": 1,
            "type": "basic",
            "context": {
                "version": 1,
                "size": 2048,
                "n-vocab": 128256,
                "bos-token": 128000,
                "eos-token": 128009,
            },
            "sampler": {
                "version": 1,
                "seed": 42,
                "temp": 0.8,
                "top-k": 40,
                "top-p": 0.95,
            },
            "tokenizer": {"version": 1, "path": "tokenizer.json"},
            "engine": {
                "version": 1,
                "n-threads": 3,
                "backend": {
                    "version": 1,
                    "type": "QnnHtp",
                    "QnnHtp": {
                        "version": 1,
                        "use-mmap": True,
                        "spill-fill-bufsize": 0,
                        "mmap-budget": 0,
                        "poll": True,
                        "cpu-mask": "0xe0",
                        "kv-dim": 128,
                        "pos-id-dim": 64,
                        "rope-theta": 500000,
                        "allow-async-init": False,
                    },
                    "extensions": "htp_backend_ext_config.json",
                },
                "model": {
                    "version": 1,
                    "type": "binary",
                    "binary": {
                        "version": 1,
                        "ctx-bins": model_list,
                    },
                },
            },
        }
    }

    assert expected_config == actual_config


@pytest.mark.unmarked
@pytest.mark.parametrize(
    ("skip_inferencing", "skip_profiling", "target_runtime"),
    [
        (True, True, TargetRuntime.GENIE),
        (True, False, TargetRuntime.GENIE),
        (False, True, TargetRuntime.GENIE),
        (False, False, TargetRuntime.GENIE),
        (False, True, TargetRuntime.ONNXRUNTIME_GENAI),
        (False, False, TargetRuntime.ONNXRUNTIME_GENAI),
    ],
)
def test_cli_device_with_skips(
    tmp_path: Path,
    skip_inferencing: bool,
    skip_profiling: bool,
    target_runtime: TargetRuntime,
):
    test.test_cli_device_with_skips(
        export_main,
        Model,
        tmp_path,
        MODEL_ID,
        NUM_SPLITS,
        hub.Device(DEFAULT_EXPORT_DEVICE),
        skip_inferencing,
        skip_profiling,
        target_runtime,
    )


@pytest.mark.unmarked
@pytest.mark.parametrize(
    ("chipset", "context_length", "sequence_length", "target_runtime"),
    [
        ("qualcomm-snapdragon-8gen2", 2048, 256, TargetRuntime.GENIE),
        ("qualcomm-snapdragon-x-elite", 4096, 128, TargetRuntime.GENIE),
        ("qualcomm-snapdragon-8gen2", 2048, 256, TargetRuntime.ONNXRUNTIME_GENAI),
        ("qualcomm-snapdragon-x-elite", 4096, 128, TargetRuntime.ONNXRUNTIME_GENAI),
    ],
)
def test_cli_chipset_with_options(
    tmp_path: Path,
    context_length: int,
    sequence_length: int,
    chipset: str,
    target_runtime: TargetRuntime,
):
    test.test_cli_chipset_with_options(
        export_main,
        Model,
        tmp_path,
        MODEL_ID,
        NUM_SPLITS,
        chipset,
        context_length,
        sequence_length,
        target_runtime,
    )


@pytest.mark.unmarked
@pytest.mark.parametrize(
    ("cache_mode", "skip_download", "skip_summary", "target_runtime"),
    [
        (CacheMode.ENABLE, True, True, TargetRuntime.GENIE),
        (CacheMode.DISABLE, True, False, TargetRuntime.GENIE),
        (CacheMode.OVERWRITE, False, False, TargetRuntime.GENIE),
        (CacheMode.ENABLE, True, True, TargetRuntime.ONNXRUNTIME_GENAI),
        (CacheMode.DISABLE, True, False, TargetRuntime.ONNXRUNTIME_GENAI),
        (CacheMode.OVERWRITE, False, False, TargetRuntime.ONNXRUNTIME_GENAI),
    ],
)
def test_cli_default_device_select_component(
    tmp_path: Path,
    cache_mode: CacheMode,
    skip_download: bool,
    skip_summary: bool,
    target_runtime: TargetRuntime,
):
    test.test_cli_default_device_select_component(
        export_main,
        Model,
        tmp_path,
        MODEL_ID,
        NUM_SPLITS,
        hub.Device(DEFAULT_EXPORT_DEVICE),
        cache_mode,
        skip_download,
        skip_summary,
        target_runtime,
    )


@pytest.mark.evaluate
@pytest.mark.skipif(
    not torch.cuda.is_available(), reason="This test can be run on GPU only."
)
@pytest.mark.parametrize(
    ("task", "expected_metric", "num_samples"),
    [
        ("wikitext", 8.736, 0),
        ("mmlu", 0.618, 1000),
        ("tiny_mmlu", 0.53, 0),
    ],
)
def test_evaluate_default(
    task: str,
    expected_metric: float,
    num_samples: int,
) -> None:
    cleanup()
    actual_metric, _ = evaluate(
        quantized_model_cls=Model,
        fp_model_cls=FP_Model,
        num_samples=num_samples,
        task=task,
        kwargs=dict(
            checkpoint="DEFAULT",
            sequence_length=DEFAULT_EVAL_SEQLEN,
            context_length=DEFAULT_CONTEXT_LENGTH,
        ),
    )
    np.testing.assert_allclose(actual_metric, expected_metric, rtol=1e-02, atol=1e-02)


@pytest.mark.evaluate
@pytest.mark.skipif(
    not torch.cuda.is_available(), reason="This test can be run on GPU only."
)
@pytest.mark.parametrize(
    ("task", "expected_metric", "num_samples"),
    [
        ("wikitext", 7.76, 0),
        ("mmlu", 0.674, 1000),
        ("tiny_mmlu", 0.61, 0),
    ],
)
def test_evaluate_default_unquantized(
    task: str,
    expected_metric: float,
    num_samples: int,
) -> None:
    cleanup()
    actual_metric, _ = evaluate(
        quantized_model_cls=Model,
        fp_model_cls=FP_Model,
        num_samples=num_samples,
        task=task,
        kwargs=dict(
            checkpoint="DEFAULT_UNQUANTIZED",
            sequence_length=DEFAULT_EVAL_SEQLEN,
            context_length=DEFAULT_CONTEXT_LENGTH,
        ),
    )
    np.testing.assert_allclose(actual_metric, expected_metric, rtol=1e-02, atol=1e-02)


@pytest.mark.demo
@pytest.mark.skipif(
    not torch.cuda.is_available(), reason="This test can be run on GPU only."
)
@pytest.mark.parametrize("checkpoint", ["DEFAULT", "DEFAULT_UNQUANTIZED"])
def test_demo_default(checkpoint: CheckpointSpec, capsys) -> None:
    cleanup()
    llama_3_chat_demo(
        fp_model_cls=FP_Model,
        default_prompt="What is the capital of France?",
        test_checkpoint=checkpoint,
    )
    captured = capsys.readouterr()
    assert "Paris" in captured.out


@pytest.mark.skipif(
    not torch.cuda.is_available(),
    reason="This test can be run on GPU only.",
)
@pytest.mark.parametrize(
    ("precision", "scorecard_path", "device"),
    get_compile_parameterized_pytest_config(
        MODEL_ID,
        SUPPORTED_PRECISION_RUNTIMES,
        {},
        can_use_quantize_job=False,
        only_include_genai_paths=True,
    ),
    ids=pytest_device_idfn,
)
@pytest.mark.compile_ram_intensive
def test_compile(
    precision: Precision,
    scorecard_path: ScorecardCompilePath,
    device: ScorecardDevice,
) -> None:
    cleanup()
    allow_few_test_devices_for_llms(scorecard_path.runtime, device)
    genie_bundle_path = f"genie_bundle/{MODEL_ID}/{device.name}_{str(precision)}"
    compile_via_export(
        export_model,
        MODEL_ID,
        precision,
        scorecard_path,
        device,
        extra_model_arguments=dict(
            checkpoint="DEFAULT",
            sequence_length=128,
            context_length=DEFAULT_CONTEXT_LENGTH,
            _skip_quantsim_creation=True,
            model_cls=Model,
            model_name=MODEL_ID,
            model_asset_version=MODEL_ASSET_VERSION,
            num_splits=NUM_SPLITS,
            num_layers_per_split=NUM_LAYERS_PER_SPLIT,
            output_dir=genie_bundle_path,
            fp_model=FP_Model.from_pretrained(
                sequence_length=128, context_length=DEFAULT_CONTEXT_LENGTH
            ),
            position_processor_cls=PositionProcessor,
        ),
        skip_compile_options=True,
        skip_downloading=False,
    )
    assert os.path.exists(genie_bundle_path)
    assert os.path.exists(os.path.join(genie_bundle_path, "tokenizer.json"))
    assert os.path.exists(os.path.join(genie_bundle_path, "genie_config.json"))
    assert os.path.exists(
        os.path.join(genie_bundle_path, "htp_backend_ext_config.json")
    )


@pytest.mark.skipif(
    not torch.cuda.is_available()
    or not importlib.util.find_spec("qdc_public_api_client"),
    reason="This test can be run on GPU only. Also needs QDC package to run.",
)
@pytest.mark.parametrize(
    ("precision", "scorecard_path", "device"),
    get_compile_parameterized_pytest_config(
        MODEL_ID,
        SUPPORTED_PRECISION_RUNTIMES,
        {},
        can_use_quantize_job=False,
        only_include_genai_paths=True,
    ),
    ids=pytest_device_idfn,
)
@pytest.mark.qdc
def test_qdc(
    precision: Precision,
    scorecard_path: ScorecardCompilePath,
    device: ScorecardDevice,
) -> None:
    cleanup()
    allow_few_test_devices_for_llms(scorecard_path.runtime, device)
    genie_bundle_path = f"genie_bundle/{MODEL_ID}/{device.name}_{str(precision)}"
    if scorecard_path.runtime == TargetRuntime.ONNXRUNTIME_GENAI:
        pytest.skip("This test is only valid for Genie runtime.")
    if not os.path.exists(genie_bundle_path):
        pytest.fail("The genie bundle does not exist.")
    test.complete_genie_bundle_and_run_on_device(device, genie_bundle_path)

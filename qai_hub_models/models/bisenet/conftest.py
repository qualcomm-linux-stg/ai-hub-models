# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------
# THIS FILE WAS AUTO-GENERATED. DO NOT EDIT MANUALLY.

import gc
import inspect
import warnings

import pytest
import torch.jit._trace

from qai_hub_models.models.bisenet import Model
from qai_hub_models.utils.testing import skip_clone_repo_check


def pytest_configure(config):
    # pytest is unable to figure out how to silence several PyTorch warning types from pyproject.toml settings,
    # so we apply a manual warning filter here instead.
    warnings.filterwarnings(action="ignore", category=torch.jit._trace.TracerWarning)
    warnings.filterwarnings(action="ignore", category=UserWarning, module="torch.*")
    warnings.filterwarnings(action="ignore", category=FutureWarning, module="torch.*")
    warnings.filterwarnings(
        action="ignore", category=DeprecationWarning, module="torch.*"
    )


# Instantiate the model only once for all tests.
# Mock from_pretrained to always return the initialized model.
# This speeds up tests and limits memory leaks.
@pytest.fixture(scope="module", autouse=True)
def cached_from_pretrained():
    with pytest.MonkeyPatch.context() as mp:
        pretrained_cache: dict[str, Model] = {}
        from_pretrained = Model.from_pretrained
        sig = inspect.signature(from_pretrained)

        @skip_clone_repo_check
        def _cached_from_pretrained(*args, **kwargs):
            cache_key = str(args) + str(kwargs)
            model = pretrained_cache.get(cache_key, None)
            if model:
                return model
            else:
                non_none_model = from_pretrained(*args, **kwargs)
                pretrained_cache[cache_key] = non_none_model
                return non_none_model

        _cached_from_pretrained.__signature__ = sig

        mp.setattr(Model, "from_pretrained", _cached_from_pretrained)
        yield mp


@pytest.fixture(scope="module", autouse=True)
def ensure_gc():
    gc.collect()

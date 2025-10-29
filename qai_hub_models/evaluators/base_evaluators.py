# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Collection
from typing import NamedTuple, Union

import torch
from torch.utils.data.dataloader import DataLoader
from tqdm import tqdm
from typing_extensions import TypeAlias

_ModelIO: TypeAlias = Union[Collection[torch.Tensor], torch.Tensor]
# Typically is a torch DataLoader, but anything with the collection signature is acceptable.
_DataLoader: TypeAlias = Union[
    DataLoader, Collection[Union[_ModelIO, tuple[_ModelIO, _ModelIO]]]
]


class MetricMetadata(NamedTuple):
    name: str
    unit: str
    description: str


class BaseEvaluator(ABC):
    """Evaluates one or more outputs of a model in comparison to a ground truth."""

    @abstractmethod
    def add_batch(
        self,
        output: torch.Tensor
        | torch.NumberType
        | Collection[torch.Tensor | torch.NumberType],
        gt: torch.Tensor
        | torch.NumberType
        | Collection[torch.Tensor | torch.NumberType],
    ) -> None:
        """
        Add a batch of data to this evaluator.

        Parameters
        ----------
        output
            Torch model output(s) for a single inference.

            If the model forward() function has 1 output, this is a tensor.
            If the model forward() function outputs multiple tensors, this is a tuple of tensors.

        gt: torch.Tensor | Collection[torch.Tensor]
            The ground truth(s) for this output.

            Some evaluators may accept only a Collection. Others may accept only a tensor.
            The meaning of the ground truth is dependent on this method's implementation.
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the state of this evaluator."""
        pass

    @abstractmethod
    def get_accuracy_score(self) -> float:
        """Single float value representing model accuracy. Higher is better."""
        pass

    @abstractmethod
    def formatted_accuracy(self) -> str:
        """Formatted string containing the accuracy and any relevant units."""
        pass

    @property
    def is_distance_metric(self) -> bool:
        # If this is true, then the dataset must carry two sets of ground truth:
        # - Real GT
        # - Output of a target model (typically a floating point model)
        return False

    def get_metric_metadata(self) -> MetricMetadata:
        """Metadata about the metric corresponding to get_accuracy_score."""
        raise NotImplementedError()

    def add_from_dataset(
        self,
        model: torch.nn.Module,
        data: _DataLoader,
        eval_iterations: int | None = None,
        device: str = "cpu",
    ):
        """
        Populates this evaluator with data from the provided the data loader.

        Parameters
        ----------
        model
            Model to use to compute model outputs.

        data
            Data loader for the dataset to use for evaluation. Iterator should return:
                tuple(inputs: Collection[torch.Tensor] | torch.Tensor,
                        ground_truth: Collection[torch.Tensor] | torch.Tensor)

        eval_iterations
            Number of samples to use for evaluation. One sample is one iteration from iter(data).
            If none, defaults to the number of samples in the dataset.

        device
            Name of device on which inference should be run.
        """

        def _add_batch(
            _: torch.Tensor, outputs: torch.Tensor, ground_truth: torch.Tensor
        ):
            self.add_batch(outputs, ground_truth)

        _for_each_batch(model, data, eval_iterations, device, True, _add_batch)


def _for_each_batch(
    model: torch.nn.Module,
    data: _DataLoader,
    num_samples: int | None = None,
    device: str = "cpu",
    data_has_gt: bool = False,
    callback: Callable | None = None,
):
    """
    Run the model on each batch of data.

    Parameters
    ----------
    model
        Model to use to compute model outputs.

    data
        Data loader for the dataset. Iterator should return:
            if data_has_gt:
                tuple(inputs: Collection[torch.Tensor] | torch.Tensor,
                        ground_truth: Collection[torch.Tensor] | torch.Tensor)
            else:
                Collection[torch.Tensor] | torch.Tensor

    num_samples
        Number of samples to use for evaluation. One sample is one iteration from iter(data).
        If none, defaults to the number of samples in the dataset.

    device
        Name of device on which inference should be run.

    data_has_gt
        If true, changes the type this function expects the dataloader to return. See `data` parameter.

    callback
        The input, output, and (if provided) ground_truth will be passed to this function after each inference.
    """
    torch_device = torch.device(device)
    model.to(torch_device)
    total_samples = 0
    num_samples = num_samples or len(data)

    batch_size = data.batch_size or 1 if isinstance(data, DataLoader) else 1
    counting_obj = "batches" if batch_size != 1 else "samples"

    with tqdm(
        total=batch_size * num_samples,
        desc=f"Number of {counting_obj} completed",
    ) as pbar:
        for sample in data:
            if data_has_gt:
                inputs, ground_truth, *_ = sample
            else:
                inputs, ground_truth = sample, None

            if len(inputs) > 0:
                if isinstance(inputs, torch.Tensor):
                    inputs = inputs.to(torch_device)
                    outputs = model(inputs)
                else:
                    inputs = [
                        i.to(  # pyright: ignore[reportAttributeAccessIssue]
                            torch_device
                        )
                        for i in inputs
                    ]
                    outputs = model(*inputs)

                if data_has_gt:
                    if isinstance(ground_truth, torch.Tensor):
                        ground_truth = ground_truth.to("cpu")
                    else:
                        assert ground_truth is not None
                        ground_truth = [gt.to("cpu") for gt in ground_truth]

                if callback:
                    if data_has_gt:
                        callback(inputs, outputs, ground_truth)
                    else:
                        callback(inputs, outputs)

            total_samples += 1
            pbar.update(batch_size)
            if total_samples >= num_samples:
                break

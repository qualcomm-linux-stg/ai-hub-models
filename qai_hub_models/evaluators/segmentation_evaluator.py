# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

import torch
import torch.nn.functional as F

from qai_hub_models.evaluators.base_evaluators import BaseEvaluator, MetricMetadata


class SegmentationOutputEvaluator(BaseEvaluator):
    """Evaluator for comparing segmentation output against ground truth."""

    def __init__(self, num_classes: int, resize_to_gt: bool = False):
        self.num_classes = num_classes
        self.resize_to_gt = resize_to_gt
        self.reset()

    def add_batch(self, output: torch.Tensor, gt: torch.Tensor):
        # This evaluator supports only 1 output tensor at a time.
        output = output.cpu()
        if self.resize_to_gt:
            output = F.interpolate(output, gt.shape[-2:], mode="bilinear")
            if len(output.shape) == 4:
                output = output.argmax(1)
        assert gt.shape == output.shape
        self.confusion_matrix += self._generate_matrix(gt, output)

    def reset(self):
        self.confusion_matrix = torch.zeros((self.num_classes, self.num_classes))

    def Pixel_Accuracy(self):
        return torch.diag(self.confusion_matrix).sum() / self.confusion_matrix.sum()

    def Pixel_Accuracy_Class(self):
        Acc = torch.diag(self.confusion_matrix) / self.confusion_matrix.sum(dim=1)
        return torch.nanmean(Acc)

    def Intersection_over_Union(self):
        return torch.diag(self.confusion_matrix) / (
            torch.sum(self.confusion_matrix, dim=1)
            + torch.sum(self.confusion_matrix, dim=0)
            - torch.diag(self.confusion_matrix)
        )

    def Mean_Intersection_over_Union(self):
        return torch.nanmean(self.Intersection_over_Union())

    def Frequency_Weighted_Intersection_over_Union(self):
        freq = torch.sum(self.confusion_matrix, dim=1) / torch.sum(
            self.confusion_matrix
        )
        iu = torch.diag(self.confusion_matrix) / (
            torch.sum(self.confusion_matrix, dim=1)
            + torch.sum(self.confusion_matrix, dim=0)
            - torch.diag(self.confusion_matrix)
        )

        return (freq[freq > 0] * iu[freq > 0]).sum()

    def _generate_matrix(self, gt_image, pre_image):
        mask = (gt_image >= 0) & (gt_image < self.num_classes)
        label = self.num_classes * gt_image[mask].int() + pre_image[mask].int()
        count = torch.bincount(label, minlength=self.num_classes**2)
        return count.reshape(self.num_classes, self.num_classes)

    def get_accuracy_score(self) -> float:
        return self.Mean_Intersection_over_Union()

    def formatted_accuracy(self) -> str:
        return f"{self.get_accuracy_score():.3f} mIOU"

    def get_metric_metadata(self) -> MetricMetadata:
        return MetricMetadata(
            name="Mean Intersection Over Union",
            unit="mIOU",
            description="Overlap of predicted and expected segmentation divided by the union size.",
        )

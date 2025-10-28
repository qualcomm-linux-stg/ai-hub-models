# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

import jiwer
import torch

from qai_hub_models.evaluators.base_evaluators import BaseEvaluator, MetricMetadata
from qai_hub_models.models.huggingface_wavlm_base_plus.app import get_processor


class LibriSpeechEvaluator(BaseEvaluator):
    """Evaluator for transcription-based WER metric on LibriSpeech test-clean dataset."""

    def __init__(self, target_sample_rate: int = 16000):
        """
        Parameters
        ----------
            target_sample_rate: Sample rate to resample audio to (Hz)
        """
        self.target_sample_rate = target_sample_rate
        self.processor = get_processor()
        self.reset()

    def add_batch(
        self,
        output: torch.Tensor,
        target: torch.Tensor,
    ):
        """
        Parameters
        ----------
            output: List of logits [(batch_size, seq_len, vocab_size)] from model
            target: Tensor of shape [max_text_length] containing ASCII character codes for the transcription, padded with zeros if needed.
        """
        output = output[0]

        # Decode predictions
        pred_ids = torch.argmax(output, dim=-1)
        transcriptions = self.processor.batch_decode(pred_ids)

        # Convert ASCII to string
        clean_targets = ["".join(chr(int(i)) for i in t if int(i) != 0) for t in target]

        # Store predictions and trimmed targets
        for transcription, clean_target in zip(transcriptions, clean_targets):
            self.predictions.append(transcription)
            self.references.append(
                clean_target[: len(transcription)]
            )  # Trim extras based on the predictions

    def reset(self):
        """Reset stored predictions and references"""
        self.predictions = []
        self.references = []

    def get_accuracy_score(self) -> float:
        """Return WER as the accuracy score"""
        return jiwer.wer(self.references, self.predictions)

    def formatted_accuracy(self) -> str:
        """Return formatted WER score"""
        wer_score = self.get_accuracy_score()
        return f"Word Error Rate: {wer_score:.3f}"

    def get_metric_metadata(self) -> MetricMetadata:
        return MetricMetadata(
            name="Word Error Rate",
            unit="WER",
            description="The percentage of words incorrectly predicted.",
        )

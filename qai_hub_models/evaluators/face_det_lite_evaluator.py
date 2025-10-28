# ---------------------------------------------------------------------
# Copyright (c) 2025 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause
# ---------------------------------------------------------------------

from __future__ import annotations

from collections.abc import Collection

import torch

# podm comes from the object-detection-metrics pip package
from podm.metrics import BoundingBox

from qai_hub_models.evaluators.detection_evaluator import mAPEvaluator
from qai_hub_models.models.face_det_lite.utils import detect


class FaceDetLiteEvaluator(mAPEvaluator):
    """Evaluator for comparing a batched image output."""

    def __init__(
        self,
        image_height: int,
        image_width: int,
        nms_iou_threshold: float = 0.2,
        score_threshold: float = 0.55,
    ):
        super().__init__()
        self.nms_iou_threshold = nms_iou_threshold
        self.score_threshold = score_threshold
        self.image_height = image_height
        self.image_width = image_width

    def add_batch(self, output: Collection[torch.Tensor], gt: Collection[torch.Tensor]):
        """
        This function handles model prediction result then calculate the performance with provided ground truth data.
        output is the model inference output - (heatmap, bbox, landmard)
        gt is one list to hold ground truth information from dataloader, the order as following
            0 - image_id_tensor
                integer value to represnet image id, not used
                layout - [N], N is batch size
            1 - scale_tensor:
                floating value to represent image scale b/w original size and [self.image_height, self.image_width]
                layout - [N], N is batch size
            2 - padding_tensor
                two integer values to represent padding pixels on x and y axises - [px, py]
                layout - [N, 2], N is batch size
            3 - boundingboxes_tensor
                fixed number (self.max_boxes) bounding boxes on original image size - [self.max_boxes, 4]
                layout - [N, 4], N is batch size
            4 - labels_tensor
                fixed number labels to represnet the label of box - [self.max_boxes]
                layout - [N], N is batch size
            5 - box_numbers_tensor
                fixed number valid box number to represent how many boxes are valid - [self.max_boxes]
                layout - [N], N is batch size
        """
        hm, box, landmark = output
        image_ids, scales, paddings, all_bboxes, all_classes, all_num_boxes = gt

        for i in range(len(image_ids)):
            image_id = image_ids[i]
            bboxes = all_bboxes[i][: int(all_num_boxes[i].item())]
            classes = all_classes[i][: int(all_num_boxes[i].item())]
            if bboxes.numel() == 0:
                continue

            # Collect GT and prediction boxes
            gt_bb_entry = [
                BoundingBox.of_bbox(
                    image_id,
                    int(classes[j]),
                    bboxes[j][0].item(),
                    bboxes[j][1].item(),
                    bboxes[j][2].item(),
                    bboxes[j][3].item(),
                    1.0,
                )
                for j in range(len(bboxes))
                if classes[j] == 0
            ]

            dets = detect(
                hm[i].unsqueeze(0),
                box[i].unsqueeze(0),
                landmark[i].unsqueeze(0),
                threshold=self.score_threshold,
                nms_iou=self.nms_iou_threshold,
                stride=8,
            )

            res = []
            for n in range(0, len(dets)):
                xmin, ymin, w, h = dets[n].xywh
                score = dets[n].score

                L = int(xmin)
                R = int(xmin + w)
                T = int(ymin)
                B = int(ymin + h)
                W = int(w)
                H = int(h)

                if L < 0 or T < 0 or R >= self.image_width or B >= self.image_height:
                    L = max(L, 0)
                    T = max(T, 0)
                    if R >= self.image_width:
                        R = self.image_width - 1
                    if B >= self.image_height:
                        B = self.image_height - 1

                # Enlarge bounding box to cover more face area
                b_Left = L - int(W * 0.05)
                b_Top = T - int(H * 0.05)
                b_Width = int(W * 1.1)
                b_Height = int(H * 1.1)

                if (
                    b_Left >= 0
                    and b_Top >= 0
                    and b_Width - 1 + b_Left < self.image_width
                    and b_Height - 1 + b_Top < self.image_height
                ):
                    L = b_Left
                    T = b_Top
                    W = b_Width
                    H = b_Height
                    R = W - 1 + L
                    B = H - 1 + T

                res.append([L, T, R, B, score])

            pd_bb_entry = [
                BoundingBox.of_bbox(
                    image_id,
                    0,
                    (float(item[0]) - paddings[i][0].item()) / scales[i].item(),
                    (float(item[1]) - paddings[i][1].item()) / scales[i].item(),
                    (float(item[2]) - paddings[i][0].item()) / scales[i].item(),
                    (float(item[3]) - paddings[i][1].item()) / scales[i].item(),
                    item[4],
                )
                for item in res
            ]

            self.store_bboxes_for_eval(gt_bb_entry, pd_bb_entry)

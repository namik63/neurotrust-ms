import numpy as np

from app.core.metrics_voxel import voxel_metrics


def test_perfect_empty_masks_are_technical_agreement():
    gt = np.zeros((8, 8, 8), dtype=bool)
    pred = np.zeros_like(gt)
    metrics = voxel_metrics(gt, pred, (1, 1, 1))
    assert metrics["dice_voxel"] == 1.0
    assert metrics["iou_voxel"] == 1.0


def test_complete_miss_has_zero_dice_and_recall():
    gt = np.zeros((8, 8, 8), dtype=bool)
    pred = np.zeros_like(gt)
    gt[2:4, 2:4, 2:4] = True
    metrics = voxel_metrics(gt, pred, (1, 1, 1))
    assert metrics["dice_voxel"] == 0.0
    assert metrics["sensitivity_voxel"] == 0.0


def test_volume_error_uses_spacing():
    gt = np.zeros((8, 8, 8), dtype=bool)
    pred = np.zeros_like(gt)
    gt[0, 0, 0] = True
    pred[0, 0, 0] = True
    pred[1, 1, 1] = True
    metrics = voxel_metrics(gt, pred, (2, 2, 2))
    assert metrics["gt_volume_mm3"] == 8.0
    assert metrics["pred_volume_mm3"] == 16.0
    assert metrics["absolute_volume_error_mm3"] == 8.0


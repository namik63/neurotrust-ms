import numpy as np

from app.core.metrics_lesion import lesion_metrics


def test_lesion_recall_and_false_positive_count():
    gt = np.zeros((20, 20, 20), dtype=bool)
    pred = np.zeros_like(gt)
    gt[2:5, 2:5, 2:5] = True
    gt[10:13, 10:13, 10:13] = True
    pred[2:5, 2:5, 2:5] = True
    pred[16:18, 16:18, 16:18] = True
    result = lesion_metrics(gt, pred, (1, 1, 1))
    assert result["summary"]["gt_lesion_count"] == 2
    assert result["summary"]["pred_lesion_count"] == 2
    assert result["summary"]["lesion_recall"] == 0.5
    assert result["summary"]["fp_lesions_per_scan"] == 1


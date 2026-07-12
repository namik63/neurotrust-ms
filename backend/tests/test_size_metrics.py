import numpy as np

from app.core.metrics_lesion import lesion_metrics, size_bin


def test_requested_size_bins():
    assert size_bin(14.9) == "tiny"
    assert size_bin(15.0) == "small"
    assert size_bin(50.0) == "medium"
    assert size_bin(250.0) == "large"


def test_size_stratified_recall_counts_missed_tiny():
    gt = np.zeros((20, 20, 20), dtype=bool)
    pred = np.zeros_like(gt)
    gt[1, 1, 1] = True
    gt[10:14, 10:14, 10:14] = True
    pred[10:14, 10:14, 10:14] = True
    result = lesion_metrics(gt, pred, (1, 1, 1))
    assert result["summary"]["tiny_lesion_recall"] == 0.0
    assert result["summary"]["missed_tiny_lesion_count"] == 1
    assert result["summary"]["medium_lesion_recall"] == 1.0

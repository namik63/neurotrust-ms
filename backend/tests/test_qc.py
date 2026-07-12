import numpy as np

from app.core.io import Volume
from app.core.qc import validate_case


def vol(shape):
    return Volume(data=np.zeros(shape), affine=np.eye(4), spacing=(1, 1, 1), shape=shape, source="synthetic")


def test_shape_mismatch_fails_qc():
    qc = validate_case(vol((8, 8, 8)), vol((8, 8, 8)), vol((7, 8, 8)))
    assert qc.status == "failed"
    assert qc.errors


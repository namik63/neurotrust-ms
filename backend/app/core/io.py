from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np


@dataclass
class Volume:
    data: np.ndarray
    affine: np.ndarray
    spacing: tuple[float, float, float]
    shape: tuple[int, int, int]
    source: str


def load_nifti(path: Path) -> Volume:
    img = nib.load(str(path))
    data = np.asarray(img.get_fdata(dtype=np.float32))
    if data.ndim > 3:
        data = np.squeeze(data)
    if data.ndim != 3:
        raise ValueError(f"Expected 3D NIfTI volume, got shape {data.shape}")
    spacing = tuple(float(v) for v in img.header.get_zooms()[:3])
    return Volume(data=data, affine=np.asarray(img.affine), spacing=spacing, shape=tuple(data.shape), source=str(path))


def binary_mask(data: np.ndarray) -> np.ndarray:
    return np.asarray(data > 0, dtype=bool)


def save_nifti(data: np.ndarray, affine: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(np.asarray(data), affine), str(path))


def volume_mm3(mask: np.ndarray, spacing: tuple[float, float, float]) -> float:
    return float(np.count_nonzero(mask) * np.prod(spacing))


def metadata(volume: Volume) -> dict[str, Any]:
    return {
        "shape": list(volume.shape),
        "spacing": [float(v) for v in volume.spacing],
        "affine": np.round(volume.affine, 4).tolist(),
    }

from __future__ import annotations

import re
from pathlib import Path


SAFETY_DISCLAIMER = (
    "NeuroTrust-MS is a validation and quality-assurance support tool for MS lesion segmentation review. "
    "It does not diagnose MS, certify medical devices, replace radiologists, "
    "or provide regulatory approval. Results must be interpreted by qualified clinicians."
)


ALLOWED_EXTENSIONS = {".nii", ".gz", ".mgz", ".csv", ".json", ".txt"}


def sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return base or "uploaded_file"


def is_allowed_upload(name: str) -> bool:
    lower = name.lower()
    if lower.endswith(".nii.gz"):
        return True
    if lower.endswith(".mgz"):
        return True
    return Path(lower).suffix in ALLOWED_EXTENSIONS


def public_path(path: Path) -> str:
    """Avoid exposing full local paths to the frontend."""
    return path.name

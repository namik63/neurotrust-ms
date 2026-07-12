from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel


def _bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class Settings(BaseModel):
    app_name: str = "NeuroTrust-MS"
    data_root: Path = Path(os.getenv("STORAGE_DIR") or os.getenv("NEUROTRUST_DATA_ROOT") or "data")
    hosted_mode: bool = _bool_env("HOSTED_MODE", False)
    hosting_mode: str = os.getenv("HOSTING_MODE", "local")
    max_batch_cases: int = _int_env("MAX_BATCH_CASES", 5)
    max_concurrent_jobs: int = _int_env("MAX_CONCURRENT_JOBS", 1)
    job_ttl_hours: int = _int_env("JOB_TTL_HOURS", 4)
    max_upload_mb: int = _int_env("MAX_UPLOAD_MB", 512)
    viewer_assets_on_demand: bool = _bool_env("VIEWER_ASSETS_ON_DEMAND", False)
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    access_session_hours: int = _int_env("ACCESS_SESSION_HOURS", 8)
    demo_batch_root: Path | None = Path(os.getenv("NEUROTRUST_DEMO_BATCH_ROOT")) if os.getenv("NEUROTRUST_DEMO_BATCH_ROOT") else None
    admin_safety_key: str = os.getenv("NEUROTRUST_ADMIN_SAFETY_KEY", "")
    admin_second_factor: str = os.getenv("NEUROTRUST_ADMIN_SECOND_FACTOR", "")
    connectivity: int = 26
    size_bins_mm3: dict[str, tuple[float, float | None]] = {
        "tiny": (0.0, 15.0),
        "small": (15.0, 50.0),
        "medium": (50.0, 250.0),
        "large": (250.0, None),
    }
    periventricular_distance_mm: float = 3.0
    juxtacortical_distance_mm: float = 3.0
    anisotropy_warning_ratio: float = 3.0
    thick_slice_warning_mm: float = 5.0
    poor_lesion_recall: float = 0.70
    concerning_lesion_recall: float = 0.80
    high_relative_volume_error: float = 0.30
    minimum_cases_for_deployment_call: int = 3


settings = Settings()

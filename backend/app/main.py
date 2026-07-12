from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import shutil
import re
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import settings
from app.core.anatomy import anatomy_analysis, case_difficulty_signature, confidence_metrics
from app.core.blindspot_engine import deployment_recommendation, generate_blindspots
from app.core.io import binary_mask, load_nifti, metadata
from app.core.metrics_hard_cases import classify_hard_case, hard_case_chips, hard_case_metrics
from app.core.metrics_lesion import lesion_metrics
from app.core.metrics_location_capability import compute_location_capability
from app.core.metrics_reliability import reliability_metrics
from app.core.metrics_voxel import voxel_metrics
from app.core.product_features import dice_trap, failure_fingerprint, method_badges, prediction_only_burden_detector, trust_gap_summary
from app.core.qc import validate_case
from app.core.radiologist_watchlist import generate_radiologist_watchlist
from app.core.report_generator import preview_layer_pngs, preview_png, write_csv, write_html_report, write_json
from app.core.safety import SAFETY_DISCLAIMER, is_allowed_upload, sanitize_filename
from app.core.viewer_assets import write_viewer_assets
from sample_data.create_synthetic_case import create_synthetic_case


app = FastAPI(title=settings.app_name, version="0.1.0")
_cors_origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    settings.frontend_origin.rstrip("/"),
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(origin for origin in _cors_origins if origin),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
settings.data_root.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(settings.data_root)), name="static")
_validation_semaphore = threading.BoundedSemaphore(max(1, settings.max_concurrent_jobs))


class AccessLoginRequest(BaseModel):
    email: str
    password: str


class AccessSessionResponse(BaseModel):
    ok: bool
    email: str
    token: str
    expires_at: str
    welcome_back: bool
    login_count: int
    recent_validations: list[dict]
    safety_privacy: dict


def _access_db_path() -> Path:
    configured = os.getenv("NEUROTRUST_ACCESS_DB") or os.getenv("ACCESS_LOG_DB")
    path = Path(configured) if configured else settings.data_root.resolve().parent / "access_log.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _init_access_db() -> None:
    with sqlite3.connect(_access_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS access_log (
                email TEXT NOT NULL,
                logged_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS access_users (
                email TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                login_count INTEGER NOT NULL DEFAULT 0,
                password_salt TEXT,
                password_hash TEXT
            )
            """
        )
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(access_users)").fetchall()}
        if "password_salt" not in existing_columns:
            conn.execute("ALTER TABLE access_users ADD COLUMN password_salt TEXT")
        if "password_hash" not in existing_columns:
            conn.execute("ALTER TABLE access_users ADD COLUMN password_hash TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS access_sessions (
                token_hash TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(email) REFERENCES access_users(email)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS validation_runs (
                run_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TEXT NOT NULL,
                project_id TEXT,
                case_id TEXT,
                mode TEXT,
                model_name TEXT,
                status TEXT,
                source TEXT,
                result_path TEXT,
                summary_json TEXT,
                FOREIGN KEY(email) REFERENCES access_users(email)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_validation_runs_email_created ON validation_runs(email, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_sessions_email ON access_sessions(email)")
        conn.commit()


def _valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return salt.hex(), digest.hex()


def _password_matches(password: str, salt_hex: str | None, stored_hash: str | None) -> bool:
    if not salt_hex or not stored_hash:
        return False
    _, candidate = _hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, stored_hash)


def _session_token_from_request(request: Request) -> str:
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return (request.headers.get("x-neurotrust-session") or "").strip()


def _require_session(request: Request) -> dict:
    token = _session_token_from_request(request)
    if not token:
        raise HTTPException(401, "Please sign in again before running validation.")
    _init_access_db()
    now = _now_iso()
    with sqlite3.connect(_access_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT email, expires_at, active
            FROM access_sessions
            WHERE token_hash = ?
            """,
            (_token_hash(token),),
        ).fetchone()
        if row is None or not int(row["active"]):
            raise HTTPException(401, "Session expired or not recognized. Please sign in again.")
        if str(row["expires_at"]) <= now:
            conn.execute("UPDATE access_sessions SET active = 0 WHERE token_hash = ?", (_token_hash(token),))
            conn.commit()
            raise HTTPException(401, "Session expired. Please sign in again.")
        conn.execute("UPDATE access_users SET last_seen = ? WHERE email = ?", (now, row["email"]))
        conn.commit()
        return {"email": str(row["email"]), "expires_at": str(row["expires_at"])}


def _safety_privacy_payload() -> dict:
    return {
        "stored_login_fields": ["email", "logged_at", "password_hash", "password_salt"],
        "stored_validation_fields": ["run metadata", "result path", "clinical summary JSON"],
        "not_stored": ["raw password", "raw browser fingerprint", "third-party analytics identifier"],
        "database_location": str(_access_db_path()),
        "database_publicly_served": _is_under_data_root(_access_db_path()),
        "session_expiry_hours": settings.access_session_hours,
        "dual_admin_verification": bool(settings.admin_safety_key and settings.admin_second_factor),
    }


def _validation_history_for_email(email: str, limit: int = 20) -> list[dict]:
    _init_access_db()
    with sqlite3.connect(_access_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT run_id, created_at, project_id, case_id, mode, model_name, status, source, summary_json
            FROM validation_runs
            WHERE email = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (email, int(limit)),
        ).fetchall()
    out = []
    for row in rows:
        try:
            summary = json.loads(row["summary_json"] or "{}")
        except Exception:
            summary = {}
        out.append(
            {
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "project_id": row["project_id"],
                "case_id": row["case_id"],
                "mode": row["mode"],
                "model_name": row["model_name"],
                "status": row["status"],
                "source": row["source"],
                "summary": summary,
            }
        )
    return out


def _cleanup_old_job_folders() -> None:
    cutoff = time.time() - max(1, settings.job_ttl_hours) * 3600
    root = settings.data_root.resolve()
    if not root.exists():
        return
    for child in root.iterdir():
        try:
            resolved = child.resolve()
            resolved.relative_to(root)
        except Exception:
            continue
        if not child.is_dir():
            continue
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child)
        except Exception:
            continue


def _acquire_validation_slot() -> None:
    if not _validation_semaphore.acquire(blocking=False):
        raise HTTPException(429, "A validation job is already running. Please wait for it to finish.")
    _cleanup_old_job_folders()


def _release_validation_slot() -> None:
    try:
        _validation_semaphore.release()
    except ValueError:
        pass


@app.post("/api/access/login")
def access_login(payload: AccessLoginRequest) -> dict:
    email = payload.email.strip().lower()
    if not _valid_email(email):
        raise HTTPException(400, "Enter a valid email address.")
    password = payload.password or ""
    if len(password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters.")
    logged_at = _now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=max(1, settings.access_session_hours))).isoformat()
    token = secrets.token_urlsafe(36)
    _init_access_db()
    with sqlite3.connect(_access_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute("SELECT email, login_count, password_salt, password_hash FROM access_users WHERE email = ?", (email,)).fetchone()
        welcome_back = existing is not None
        login_count = int(existing["login_count"]) + 1 if existing else 1
        salt_hex, password_hash = _hash_password(password)
        if existing:
            if existing["password_hash"] and not _password_matches(password, existing["password_salt"], existing["password_hash"]):
                raise HTTPException(401, "Incorrect password for this email.")
            if existing["password_hash"]:
                salt_hex = existing["password_salt"]
                password_hash = existing["password_hash"]
            conn.execute(
                "UPDATE access_users SET last_seen = ?, login_count = ?, password_salt = ?, password_hash = ? WHERE email = ?",
                (logged_at, login_count, salt_hex, password_hash, email),
            )
        else:
            conn.execute(
                "INSERT INTO access_users (email, first_seen, last_seen, login_count, password_salt, password_hash) VALUES (?, ?, ?, ?, ?, ?)",
                (email, logged_at, logged_at, login_count, salt_hex, password_hash),
            )
        conn.execute(
            "INSERT INTO access_log (email, logged_at) VALUES (?, ?)",
            (email, logged_at),
        )
        conn.execute(
            "INSERT INTO access_sessions (token_hash, email, created_at, expires_at, active) VALUES (?, ?, ?, ?, 1)",
            (_token_hash(token), email, logged_at, expires_at),
        )
        conn.commit()
    return {
        "ok": True,
        "email": email,
        "token": token,
        "expires_at": expires_at,
        "welcome_back": welcome_back,
        "login_count": login_count,
        "recent_validations": _validation_history_for_email(email, limit=8),
        "safety_privacy": _safety_privacy_payload(),
    }


@app.get("/api/access/session")
def access_session(request: Request) -> dict:
    session = _require_session(request)
    return {
        "ok": True,
        "email": session["email"],
        "expires_at": session["expires_at"],
        "recent_validations": _validation_history_for_email(session["email"], limit=12),
        "safety_privacy": _safety_privacy_payload(),
    }


@app.post("/api/access/logout")
def access_logout(request: Request) -> dict:
    token = _session_token_from_request(request)
    if token:
        _init_access_db()
        with sqlite3.connect(_access_db_path()) as conn:
            conn.execute("UPDATE access_sessions SET active = 0 WHERE token_hash = ?", (_token_hash(token),))
            conn.commit()
    return {"ok": True}


def _static_url(path: Path) -> str:
    rel = path.relative_to(settings.data_root)
    return f"/static/{rel.as_posix()}"


def _path_from_static_url(url: str | None) -> Path | None:
    if not url or not url.startswith("/static/"):
        return None
    rel = url.removeprefix("/static/")
    path = settings.data_root / rel
    try:
        path.resolve().relative_to(settings.data_root.resolve())
    except Exception:
        return None
    return path


def _summarize_validation_report(report: dict) -> dict:
    metrics = report.get("subject_metrics") or {}
    recommendation = report.get("deployment_recommendation") or {}
    fingerprint = report.get("failure_fingerprint") or {}
    anatomy_qc = report.get("anatomy_qc") or {}
    return {
        "executive_summary": report.get("executive_summary"),
        "mode": report.get("mode"),
        "case_count": metrics.get("successful_case_count") or metrics.get("case_count") or report.get("model_passport", {}).get("number_of_cases_tested"),
        "dice_voxel": metrics.get("dice_voxel"),
        "lesion_recall": metrics.get("lesion_recall"),
        "lesion_precision": metrics.get("lesion_precision"),
        "lesion_f1": metrics.get("lesion_f1"),
        "fp_lesions_per_scan": metrics.get("fp_lesions_per_scan"),
        "fn_lesions_per_scan": metrics.get("fn_lesions_per_scan"),
        "relative_volume_error": metrics.get("relative_volume_error"),
        "high_risk_location_miss_rate": metrics.get("high_risk_location_miss_rate"),
        "primary_failure": fingerprint.get("primary_failure_fingerprint") or (fingerprint.get("primary") or {}).get("tag"),
        "trust_gap_summary": report.get("trust_gap_summary"),
        "recommendation_status": recommendation.get("status"),
        "recommendation_confidence": recommendation.get("confidence_level"),
        "anatomy_status": anatomy_qc.get("status"),
        "download_keys": sorted((report.get("downloads") or {}).keys())[:20],
    }


def _store_validation_record(report: dict, *, email: str, source: str) -> str:
    _init_access_db()
    now = _now_iso()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    downloads = report.get("downloads") or {}
    result_path = (
        _path_from_static_url(downloads.get("full_validation_result_json"))
        or _path_from_static_url(downloads.get("batch_json"))
        or _path_from_static_url(downloads.get("case_json"))
    )
    with sqlite3.connect(_access_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO validation_runs
              (run_id, email, created_at, project_id, case_id, mode, model_name, status, source, result_path, summary_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                email,
                now,
                report.get("project_id"),
                report.get("case_id"),
                report.get("mode"),
                report.get("model_passport", {}).get("model_name") or report.get("model_name") or "Uploaded AI model",
                (report.get("qc") or {}).get("status") or "completed",
                source,
                str(result_path) if result_path else "",
                json.dumps(_summarize_validation_report(report), default=str),
            ),
        )
        conn.commit()
    report["history"] = {
        "run_id": run_id,
        "saved": True,
        "saved_at": now,
        "owner_email": email,
        "source": source,
    }
    return run_id


def _metric(value):
    if value is None:
        return None
    try:
        if value != value:
            return None
    except Exception:
        pass
    return value


def _run_validation(
    *,
    project_id: str,
    case_id: str,
    model_name: str,
    image_path: Path,
    gt_path: Path,
    pred_path: Path,
    expert_2_path: Path | None = None,
    anatomy_labelmap_path: Path | None = None,
    anatomy_lut_path: Path | None = None,
    probability_map_path: Path | None = None,
    uncertainty_map_path: Path | None = None,
    base_image_paths: list[Path] | None = None,
    synthetic: bool = False,
) -> dict:
    run_root = settings.data_root / project_id / "runs" / case_id
    reports_dir = run_root / "reports"
    tables_dir = run_root / "tables"
    preview_dir = run_root / "previews"
    reports_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    image = load_nifti(image_path)
    gt = load_nifti(gt_path)
    pred = load_nifti(pred_path)
    expert2 = load_nifti(expert_2_path) if expert_2_path else None
    probability = load_nifti(probability_map_path) if probability_map_path else None
    uncertainty = load_nifti(uncertainty_map_path) if uncertainty_map_path else None

    qc = validate_case(image, gt, pred, expert2)
    if qc.status == "failed":
        payload = {
            "project_id": project_id,
            "case_id": case_id,
            "model_name": model_name,
            "safety_disclaimer": SAFETY_DISCLAIMER,
            "qc": qc.to_dict(),
            "status": "qc_failed",
            "message": "QC failed; metrics were not computed to avoid misleading output.",
        }
        write_json(reports_dir / "validation_result.json", payload)
        return payload

    gt_mask = binary_mask(gt.data)
    pred_mask = binary_mask(pred.data)
    voxel = voxel_metrics(gt_mask, pred_mask, image.spacing)
    lesion = lesion_metrics(gt_mask, pred_mask, image.spacing, model_name=model_name)
    anatomy = anatomy_analysis(
        image=image,
        gt_mask=gt_mask,
        pred_mask=pred_mask,
        lesion_rows=lesion["lesions"],
        prediction_rows=lesion["predictions"],
        cluster_rows=lesion["clusters"],
        anatomy_path=anatomy_labelmap_path,
        lut_path=anatomy_lut_path,
    )
    conf = confidence_metrics(
        probability=probability if probability is not None and probability.shape == image.shape else None,
        uncertainty=uncertainty if uncertainty is not None and uncertainty.shape == image.shape else None,
        gt_mask=gt_mask,
        pred_mask=pred_mask,
    )

    subject_metrics = {
        "project_id": project_id,
        "case_id": case_id,
        "subject_id": case_id,
        "model_name": model_name,
        "ground_truth_source": "expert_consensus",
        "dataset_name": "synthetic_demo" if synthetic else "local_upload",
        **{k: _metric(v) for k, v in voxel.items()},
        **lesion["summary"],
        **anatomy["subject_fields"],
        **case_difficulty_signature(
            image=image,
            gt_mask=gt_mask,
            lesion_rows=lesion["lesions"],
            anatomy_subject_fields=anatomy["subject_fields"],
        ),
        **conf,
        "high_risk_miss_rate": _high_risk_miss_rate(lesion["lesions"]),
        "qc_status": qc.status,
    }
    hard_groups = classify_hard_case(subject_metrics, lesion["lesions"], lesion["clusters"])
    subject_metrics["hard_case_groups"] = "|".join(hard_groups)
    subject_metrics["hard_case_group_count"] = len(hard_groups)

    expert_variability_rows = []
    if expert2 is not None:
        expert2_mask = binary_mask(expert2.data)
        ev_voxel = voxel_metrics(gt_mask, expert2_mask, image.spacing)
        ev_lesion = lesion_metrics(gt_mask, expert2_mask, image.spacing, model_name="expert_2")
        expert_variability_rows.append(
            {
                "project_id": project_id,
                "case_id": case_id,
                "expert_a": "expert_consensus",
                "expert_b": "expert_2",
                "dice": ev_voxel["dice_voxel"],
                "hd95_mm": ev_voxel["hd95_mm"],
                "assd_mm": ev_voxel["assd_mm"],
                "lesion_recall_a_to_b": ev_lesion["summary"]["lesion_recall"],
                "lesion_f1_symmetric": ev_lesion["summary"]["lesion_f1"],
                "volume_difference_mm3": ev_voxel["signed_volume_error_mm3"],
                "location_agreement": "not evaluated",
                "notes": "Synthetic reader variability" if synthetic else "Local expert pair comparison",
            }
        )

    preview_path = preview_dir / "case_overlay.png"
    preview_png(image.data, gt_mask, pred_mask, preview_path)
    layer_paths = preview_layer_pngs(image.data, gt_mask, pred_mask, preview_dir / "layers")
    base_paths = base_image_paths or [image_path]
    base_volumes = [
        {
            "key": f"mri_{idx + 1}",
            "label": _viewer_label_for_path(path, idx),
            "url": _static_url(path),
        }
        for idx, path in enumerate(base_paths)
        if path.is_file() and _is_under_data_root(path)
    ]
    viewer_manifest, overlays_zip = write_viewer_assets(
        image=image,
        gt_mask=gt_mask,
        pred_mask=pred_mask,
        out_dir=run_root / "viewer_assets",
        base_volumes=base_volumes,
        static_url=_static_url,
        lesion_rows=lesion["lesions"],
        prediction_rows=lesion["predictions"],
        location_masks=anatomy.get("location_masks", {}),
    )

    blindspots = generate_blindspots(subject_metrics, lesion["lesions"], lesion["clusters"], qc.to_dict())
    if anatomy["anatomy_qc"].get("status") in {"missing", "failed"}:
        blindspots.append(
            {
                "severity": "medium",
                "title": "Anatomy-aware validation unavailable",
                "metric_evidence": anatomy["anatomy_qc"].get("reason", "No usable anatomy labelmap."),
                "clinical_meaning": "Location-specific recall and brain topography evidence proxy were skipped.",
                "manual_review_action": "Upload an existing FreeSurfer/SynthSeg labelmap for anatomy-aware evidence.",
            }
        )
    if subject_metrics.get("dis_proxy_match") is False:
        blindspots.append(
            {
                "severity": "high",
                "title": "Brain topography evidence proxy mismatch",
                "metric_evidence": "Predicted topography did not preserve GT topography proxy.",
                "clinical_meaning": "Location evidence deserves focused review.",
                "manual_review_action": "Review Anatomy Capability and watchlist targets.",
            }
        )
    fingerprint = failure_fingerprint(subject_metrics, lesion["lesions"], lesion["predictions"], lesion["clusters"])
    watchlist = generate_radiologist_watchlist(
        subject_id=case_id,
        subject_metrics=subject_metrics,
        lesion_rows=lesion["lesions"],
        pred_rows=lesion["predictions"],
        cluster_rows=lesion["clusters"],
        viewer_manifest=viewer_manifest,
    )
    trap = dice_trap(subject_metrics)
    prediction_burden = prediction_only_burden_detector(subject_metrics)
    deploy = deployment_recommendation(subject_metrics, blindspots, case_count=1)
    subject_metrics["deployment_status"] = deploy["status"]
    subject_metrics["trust_gap_summary"] = trust_gap_summary(subject_metrics, fingerprint)

    passport = {
        "model_vendor_name": model_name,
        "version": "user supplied / unknown",
        "intended_use": "local MS lesion segmentation validation support",
        "number_of_cases_tested": 1,
        "ground_truth_strategy": "expert consensus or uploaded primary expert",
        "modalities_tested": [item["label"] for item in base_volumes] or ["uploaded MRI"],
        "anatomy_availability": anatomy["anatomy_qc"].get("status"),
        "validated_metrics_present": [
            *["voxel", "lesion", "surface", "volume", "topology", "size_stratified", "viewer_assets"],
            *(["anatomy"] if anatomy.get("available") else []),
            *(["probability"] if conf else []),
        ],
        "metrics_unavailable": [
            item
            for item, available in {
                "anatomy localization": anatomy.get("available"),
                "probability calibration": bool(conf),
                "longitudinal change": False,
                "scanner/protocol subgrouping": False,
                "deployment certification packet": False,
            }.items()
            if not available
        ],
        "performance_summary": {
            "dice_voxel": subject_metrics["dice_voxel"],
            "lesion_recall": subject_metrics["lesion_recall"],
            "lesion_precision": subject_metrics["lesion_precision"],
            "lesion_f1": subject_metrics["lesion_f1"],
        },
        "failure_fingerprint": fingerprint,
        "method_version": app.version,
        "outside_current_evidence_scope": [
            "spinal cord lesions unless spinal MRI uploaded",
            "optic nerve lesions unless optic nerve MRI uploaded",
            "longitudinal new lesion tracking unless registered timepoints uploaded",
            "SWI/QSM biomarkers unless appropriate modalities uploaded",
        ],
        "deployment_recommendation": deploy,
        "governance_wording": "Local scientific validation summary for segmentation evidence review.",
    }

    executive = (
        f"{deploy['status'].title()}: {model_name} showed voxel Dice {subject_metrics['dice_voxel']:.3f}, "
        f"lesion recall {subject_metrics['lesion_recall']:.3f}, and lesion precision {subject_metrics['lesion_precision']:.3f}. "
        "Use the watchlist and anatomy tabs for targeted verification."
    )

    report = {
        "project_id": project_id,
        "case_id": case_id,
        "mode": "single",
        "product": "NeuroTrust-MS",
        "safety_disclaimer": SAFETY_DISCLAIMER,
        "synthetic_demo": synthetic,
        "qc": qc.to_dict(),
        "image_metadata": metadata(image),
        "subject_metrics": subject_metrics,
        "lesion_metrics": lesion["lesions"],
        "prediction_lesions": lesion["predictions"],
        "cluster_metrics": lesion["clusters"],
        "expert_variability": expert_variability_rows,
        "blindspots": blindspots,
        "radiologist_watchlist": watchlist,
        "failure_fingerprint": fingerprint,
        "trust_gap_summary": subject_metrics["trust_gap_summary"],
        "dice_trap_detector": trap,
        "prediction_only_burden_detector": prediction_burden,
        "location_metrics": anatomy["location_metrics"],
        "size_location_metrics": anatomy.get("size_location_metrics", []),
        "location_topology_metrics": anatomy.get("location_topology_metrics", []),
        "anatomy_qc": anatomy["anatomy_qc"],
        "anatomy_lesion_assignments": anatomy["assignments"],
        "anatomy_method_card": anatomy["method_card"],
        "model_passport": passport,
        "method_badges": [],
        "viewer": viewer_manifest,
        "deployment_recommendation": deploy,
        "executive_summary": executive,
        "limitations": [
            "Location analysis requires uploaded or generated anatomy labels.",
            "Longitudinal analysis requires registered timepoints and is not inferred.",
            "Single-case validation is reported as case-level evidence; batch confidence increases with uploaded validation set size.",
        ],
    }
    report["method_badges"] = method_badges(report)

    for row in lesion["lesions"]:
        row.update({"project_id": project_id, "case_id": case_id, "subject_id": case_id})
    for row in lesion["predictions"]:
        row.update({"project_id": project_id, "case_id": case_id, "subject_id": case_id})
    for row in lesion["clusters"]:
        row.update({"project_id": project_id, "case_id": case_id, "subject_id": case_id})

    write_csv(tables_dir / "subject_metrics.csv", [subject_metrics])
    write_csv(tables_dir / "size_bin_metrics.csv", _size_bin_rows_from_metrics(subject_metrics, case_id=case_id, model_name=model_name))
    write_csv(tables_dir / "subject_evidence_preservation.csv", [_subject_evidence_row(subject_metrics, case_id=case_id, model_name=model_name)])
    write_csv(tables_dir / "lesion_metrics.csv", lesion["lesions"])
    write_csv(tables_dir / "prediction_lesions.csv", lesion["predictions"])
    write_csv(tables_dir / "cluster_metrics.csv", lesion["clusters"])
    write_csv(tables_dir / "expert_variability.csv", expert_variability_rows)
    write_csv(tables_dir / "location_metrics.csv", anatomy["location_metrics"])
    write_csv(tables_dir / "location_volume_metrics.csv", anatomy["location_metrics"])
    write_csv(tables_dir / "location_capability_metrics.csv", anatomy["location_metrics"])
    write_csv(tables_dir / "size_location_interaction_metrics.csv", anatomy.get("size_location_metrics", []))
    write_csv(tables_dir / "location_topology_metrics.csv", anatomy.get("location_topology_metrics", []))
    write_csv(tables_dir / "anatomy_lesion_assignments.csv", anatomy["assignments"])
    write_csv(tables_dir / "radiologist_watchlist.csv", watchlist)
    write_json(reports_dir / "radiologist_watchlist.json", {"radiologist_watchlist": watchlist})
    write_json(reports_dir / "blindspot_report.json", {"blindspots": blindspots})
    write_json(reports_dir / "model_passport.json", passport)
    write_json(reports_dir / "location_metrics.json", {"location_metrics": anatomy["location_metrics"]})
    write_json(reports_dir / "location_capability_metrics.json", {"location_capability_metrics": anatomy["location_metrics"]})
    write_json(reports_dir / "size_location_interaction_metrics.json", {"size_location_interaction_metrics": anatomy.get("size_location_metrics", [])})
    write_json(reports_dir / "location_topology_metrics.json", {"location_topology_metrics": anatomy.get("location_topology_metrics", [])})
    write_json(reports_dir / "anatomy_qc.json", anatomy["anatomy_qc"])
    write_json(reports_dir / "anatomy_method_card.json", anatomy["method_card"])
    write_json(reports_dir / "failure_fingerprint.json", fingerprint)
    write_json(reports_dir / "viewer_manifest.json", viewer_manifest)
    write_json(reports_dir / "qc_report.json", qc.to_dict())
    write_json(reports_dir / "method_card.json", {"anatomy_method_card": anatomy["method_card"], "model_passport": passport})
    write_json(
        reports_dir / "edge_case_report.json",
        {
            "failure_fingerprint": fingerprint,
            "radiologist_watchlist": watchlist,
            "dice_trap_detector": trap,
            "prediction_only_burden_detector": prediction_burden,
            "trust_gap_summary": subject_metrics["trust_gap_summary"],
        },
    )
    _write_method_summary_html(reports_dir / "method_validation_summary.html", report)
    write_html_report(reports_dir / "validation_report.html", report)

    report["downloads"] = {
        "json": _static_url(reports_dir / "validation_result.json"),
        "html": _static_url(reports_dir / "validation_report.html"),
        "model_passport": _static_url(reports_dir / "model_passport.json"),
        "blindspot_report": _static_url(reports_dir / "blindspot_report.json"),
        "subject_metrics_csv": _static_url(tables_dir / "subject_metrics.csv"),
        "size_bin_metrics_csv": _static_url(tables_dir / "size_bin_metrics.csv"),
        "subject_evidence_preservation_csv": _static_url(tables_dir / "subject_evidence_preservation.csv"),
        "lesion_metrics_csv": _static_url(tables_dir / "lesion_metrics.csv"),
        "prediction_lesions_csv": _static_url(tables_dir / "prediction_lesions.csv"),
        "cluster_metrics_csv": _static_url(tables_dir / "cluster_metrics.csv"),
        "expert_variability_csv": _static_url(tables_dir / "expert_variability.csv"),
        "location_metrics_csv": _static_url(tables_dir / "location_metrics.csv"),
        "location_volume_metrics_csv": _static_url(tables_dir / "location_volume_metrics.csv"),
        "location_capability_metrics_csv": _static_url(tables_dir / "location_capability_metrics.csv"),
        "size_location_interaction_metrics_csv": _static_url(tables_dir / "size_location_interaction_metrics.csv"),
        "location_topology_metrics_csv": _static_url(tables_dir / "location_topology_metrics.csv"),
        "location_metrics_json": _static_url(reports_dir / "location_metrics.json"),
        "location_capability_metrics_json": _static_url(reports_dir / "location_capability_metrics.json"),
        "size_location_interaction_metrics_json": _static_url(reports_dir / "size_location_interaction_metrics.json"),
        "location_topology_metrics_json": _static_url(reports_dir / "location_topology_metrics.json"),
        "anatomy_qc_json": _static_url(reports_dir / "anatomy_qc.json"),
        "anatomy_lesion_assignments_csv": _static_url(tables_dir / "anatomy_lesion_assignments.csv"),
        "anatomy_method_card_json": _static_url(reports_dir / "anatomy_method_card.json"),
        "failure_fingerprint_json": _static_url(reports_dir / "failure_fingerprint.json"),
        "radiologist_watchlist_csv": _static_url(tables_dir / "radiologist_watchlist.csv"),
        "radiologist_watchlist_json": _static_url(reports_dir / "radiologist_watchlist.json"),
        "viewer_manifest_json": _static_url(reports_dir / "viewer_manifest.json"),
        "method_card_json": _static_url(reports_dir / "method_card.json"),
        "derived_overlay_masks_zip": _static_url(overlays_zip),
        "method_validation_summary_html": _static_url(reports_dir / "method_validation_summary.html"),
        "qc_report_json": _static_url(reports_dir / "qc_report.json"),
        "edge_case_report_json": _static_url(reports_dir / "edge_case_report.json"),
        "preview_png": _static_url(preview_path),
    }
    report["downloads"]["full_validation_result_json"] = _static_url(reports_dir / "full_validation_result.json")
    write_json(reports_dir / "validation_result.json", report)
    write_json(reports_dir / "full_validation_result.json", report)
    return report


def _high_risk_miss_rate(lesions: list[dict]) -> float | None:
    high_risk = [r for r in lesions if r.get("high_risk_flag")]
    if not high_risk:
        return None
    missed = [r for r in high_risk if not r.get("lesion_detected")]
    return len(missed) / len(high_risk)


def _size_bin_rows_from_metrics(metrics: dict, *, case_id: str, model_name: str) -> list[dict]:
    rows = []
    for bin_name in ["tiny", "small", "medium", "large"]:
        rows.append(
            {
                "case_id": case_id,
                "subject_id": metrics.get("subject_id", case_id),
                "model_name": model_name,
                "size_bin": bin_name,
                "gt_lesion_count": metrics.get(f"{bin_name}_gt_lesion_count"),
                "lesion_recall": metrics.get(f"{bin_name}_lesion_recall"),
                "lesion_precision": metrics.get(f"{bin_name}_lesion_precision"),
                "missed_lesion_count": metrics.get(f"missed_{bin_name}_lesion_count"),
                "false_positive_lesion_count": metrics.get(f"fp_{bin_name}_lesion_count"),
                "matched_mean_dice": metrics.get(f"{bin_name}_matched_mean_dice"),
                "matched_mean_abs_volume_error_mm3": metrics.get(f"{bin_name}_matched_mean_abs_volume_error_mm3"),
            }
        )
    return rows


def _subject_evidence_row(metrics: dict, *, case_id: str, model_name: str) -> dict:
    keys = [
        "gt_topography_count",
        "pred_topography_count",
        "preserved_location_count",
        "clinical_topography_preservation_ratio",
        "topography_jaccard",
        "topography_exact_match",
        "gt_dis_like_proxy",
        "pred_dis_like_proxy",
        "dis_proxy_match",
        "dis_proxy_false_negative",
        "dis_proxy_false_positive",
        "evidence_distortion_type",
        "evidence_distortion_severity",
        "evidence_distortion_summary",
        "high_risk_location_gt_count",
        "high_risk_location_missed_count",
        "high_risk_location_miss_rate",
    ]
    return {
        "case_id": case_id,
        "subject_id": metrics.get("subject_id", case_id),
        "model_name": model_name,
        **{key: metrics.get(key) for key in keys},
    }


def _is_under_data_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(settings.data_root.resolve())
        return True
    except ValueError:
        return False


def _viewer_label_for_path(path: Path, idx: int) -> str:
    name = path.name.lower()
    if "flair" in name or "_0002" in name:
        return "FLAIR"
    if "t1ce" in name or "t1c" in name or "_0003" in name:
        return "T1CE"
    if "t1" in name or "_0000" in name:
        return "T1"
    if "t2" in name or "_0001" in name:
        return "T2"
    if "pd" in name:
        return "PD"
    return f"MRI {idx + 1}"


def _write_method_summary_html(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    badges = "".join(f"<li>{badge}</li>" for badge in report.get("method_badges", []))
    anatomy_status = report.get("anatomy_qc", {}).get("status", "missing")
    fingerprint = report.get("failure_fingerprint", {}).get("primary", {}).get("tag", "not available")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>NeuroTrust-MS Method Summary</title>
<style>body{{font-family:Inter,Arial,sans-serif;background:#07101c;color:#eef7ff;padding:32px}}.card{{border:1px solid #294155;border-radius:18px;padding:18px;margin:14px 0;background:#0b1725}}</style></head>
<body><h1>Method validation summary</h1>
<div class="card"><h2>Scope</h2><p>Local MS lesion segmentation validation evidence with voxel, lesion, location, topology, and viewer outputs.</p></div>
<div class="card"><h2>Badges</h2><ul>{badges}</ul></div>
<div class="card"><h2>Anatomy</h2><p>{anatomy_status}</p></div>
<div class="card"><h2>Failure fingerprint</h2><p>{fingerprint}</p></div>
<div class="card"><h2>Viewer</h2><p>{report.get("viewer", {}).get("mode", "not available")}</p></div>
</body></html>"""
    path.write_text(html, encoding="utf-8")


def _strip_nifti_suffix(filename: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._+/-]+", "_", filename.replace("\\", "/")).strip("._/")
    clean = clean.replace("/", "_")
    if clean.endswith(".nii.gz"):
        return clean[:-7]
    if clean.endswith(".nii"):
        return clean[:-4]
    if clean.endswith(".mgz"):
        return clean[:-4]
    if clean.endswith(".mgh"):
        return clean[:-4]
    return Path(clean).stem


def _is_freesurfer_lut_upload(upload: UploadFile) -> bool:
    name = (upload.filename or "").lower()
    return "colorlut" in name or "free_surfer_lut" in name or "freesurfer_lut" in name


def _is_freesurfer_manifest_upload(upload: UploadFile) -> bool:
    name = (upload.filename or "").lower()
    return name.endswith(".csv") and ("freesurfer_mask_manifest" in name or "freesurfer" in name and "manifest" in name)


def _upload_freesurfer_group_map(files: list[UploadFile] | None) -> dict[str, list[UploadFile]]:
    grouped: dict[str, list[UploadFile]] = {}
    for upload in files or []:
        if not upload.filename or _is_freesurfer_lut_upload(upload) or _is_freesurfer_manifest_upload(upload):
            continue
        stem = _strip_nifti_suffix(upload.filename)
        key = _case_key_from_stem(stem)
        grouped.setdefault(key, []).append(upload)
    return grouped


def _find_freesurfer_lut(files: list[UploadFile] | None) -> UploadFile | None:
    for upload in files or []:
        if upload.filename and _is_freesurfer_lut_upload(upload):
            return upload
    return None


def _parse_freesurfer_manifest_preferences(files: list[UploadFile] | None) -> dict[str, set[str]]:
    preferences: dict[str, set[str]] = {}
    for upload in files or []:
        if not upload.filename or not _is_freesurfer_manifest_upload(upload):
            continue
        try:
            upload.file.seek(0)
            text = upload.file.read().decode("utf-8", errors="ignore")
            upload.file.seek(0)
        except Exception:
            continue
        for row in csv.DictReader(text.splitlines()):
            case_id = str(row.get("case_id") or "").strip()
            local_path = str(row.get("local_path") or "").strip()
            source_path = str(row.get("source_path") or "").strip()
            note = str(row.get("note") or "").strip().lower()
            if not case_id or not local_path:
                continue
            case_key = _case_key_from_stem(case_id)
            case_digits = re.search(r"(\d{2,5})", case_key)
            native_eval_match = False
            if case_digits:
                digits = case_digits.group(1).lstrip("0") or "0"
                native_eval_match = bool(re.search(rf"/eval_0*{re.escape(digits)}(/|_)", source_path))
            if "native freesurfer mgz" in note or native_eval_match:
                preferences.setdefault(case_key, set()).add(Path(local_path).name)
    return preferences


def _choose_freesurfer_labelmap(paths: list[Path], preferred_names: set[str] | None = None) -> Path | None:
    preferred_names = preferred_names or set()

    def score(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if not (name.endswith(".mgz") or name.endswith(".mgh") or name.endswith(".nii") or name.endswith(".nii.gz")):
            return (99, name)
        normalized = name.replace("+", "_").replace("-", "_")
        if path.name in preferred_names:
            return (-10, name)
        if "_06_aparc_aseg" in normalized:
            return (-1, name)
        if "aparc_aseg" in normalized:
            return (0, name)
        if re.search(r"(^|_)aseg(\.|_|$)", normalized):
            return (1, name)
        if "wmparc" in normalized:
            return (2, name)
        if "ribbon" in normalized:
            return (3, name)
        if "brainmask" in normalized:
            return (4, name)
        return (20, name)

    usable = [path for path in paths if score(path)[0] < 99]
    if not usable:
        return None
    return sorted(usable, key=score)[0]


def _case_key_from_stem(stem: str) -> str:
    key = stem
    for pattern in [
        r"([_-])(flair|t1ce|t1c|t1|t2|pd|adc|dwi|swi|mri|image|anat|aseg|aparc(?:\+|_)aseg|wmparc|ribbon|brainmask)$",
        r"([_-])000[0-9]$",
        r"([_-])modality[0-9]+$",
    ]:
        key = re.sub(pattern, "", key, flags=re.I)
    match = re.search(r"(?:subject|eval|case|patient|sub)[_-]?(\d{2,5})", key, flags=re.I)
    if match:
        return f"subject_{match.group(1)}"
    return key


def _upload_group_map(files: list[UploadFile] | None, label: str) -> dict[str, list[UploadFile]]:
    grouped: dict[str, list[UploadFile]] = {}
    for upload in files or []:
        if not upload.filename:
            continue
        stem = _strip_nifti_suffix(upload.filename)
        key = _case_key_from_stem(stem)
        grouped.setdefault(key, []).append(upload)
    return grouped


def _upload_optional_first_map(files: list[UploadFile] | None, label: str) -> dict[str, UploadFile]:
    grouped: dict[str, UploadFile] = {}
    for upload in files or []:
        if not upload.filename:
            continue
        stem = _strip_nifti_suffix(upload.filename)
        key = _case_key_from_stem(stem)
        grouped.setdefault(key, upload)
    return grouped


def _choose_primary_mri(paths: list[Path]) -> Path:
    def score(path: Path) -> int:
        name = path.name.lower()
        if "flair" in name or "_0002" in name:
            return 0
        if "t2" in name or "_0001" in name:
            return 1
        if "t1ce" in name or "t1c" in name or "_0003" in name:
            return 2
        if "t1" in name or "_0000" in name:
            return 3
        return 9

    return sorted(paths, key=lambda p: (score(p), p.name))[0]


def _upload_map(files: list[UploadFile], label: str) -> dict[str, UploadFile]:
    mapped: dict[str, UploadFile] = {}
    duplicates: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        key = _strip_nifti_suffix(upload.filename)
        if key in mapped:
            duplicates.append(key)
        mapped[key] = upload
    if duplicates:
        raise HTTPException(400, f"Duplicate case filenames in {label}: {sorted(set(duplicates))}")
    return mapped


def _mean_numeric(rows: list[dict], key: str) -> float | None:
    values = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            try:
                if value == value:
                    values.append(float(value))
            except Exception:
                pass
    if not values:
        return None
    return sum(values) / len(values)


def _sum_numeric(rows: list[dict], key: str) -> float | None:
    values = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            try:
                if value == value:
                    values.append(float(value))
            except Exception:
                pass
    if not values:
        return None
    total = sum(values)
    return int(total) if float(total).is_integer() else total


def _aggregate_location_metrics(case_reports: list[dict]) -> list[dict]:
    rows_by_location: dict[str, list[dict]] = {}
    for report in case_reports:
        for row in report.get("location_metrics", []) or []:
            location = row.get("location")
            if location:
                rows_by_location.setdefault(str(location), []).append(row)
    if not rows_by_location:
        return []

    case_count = max(1, len(case_reports))

    def number(row: dict, key: str) -> float:
        value = row.get(key)
        if isinstance(value, bool) or value is None:
            return 0.0
        if isinstance(value, (int, float)):
            try:
                if value == value:
                    return float(value)
            except Exception:
                pass
        return 0.0

    def mean_present(rows: list[dict], key: str) -> float | None:
        values = []
        for row in rows:
            value = row.get(key)
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                try:
                    if value == value:
                        values.append(float(value))
                except Exception:
                    pass
        return float(sum(values) / len(values)) if values else None

    preferred_order = [
        "periventricular",
        "juxtacortical_or_cortical",
        "infratentorial",
        "corpus_callosum",
        "deep_white_matter_or_other",
    ]
    ordered_locations = [loc for loc in preferred_order if loc in rows_by_location]
    ordered_locations += sorted(set(rows_by_location) - set(ordered_locations))

    aggregate_rows = []
    for location in ordered_locations:
        rows = rows_by_location[location]
        gt_count = int(sum(number(row, "location_gt_lesion_count") for row in rows))
        pred_count = int(sum(number(row, "location_pred_lesion_count") for row in rows))
        matched_count = int(sum(number(row, "location_matched_lesion_count") for row in rows))
        fp_count = int(sum(number(row, "location_fp_lesions_per_scan") for row in rows))
        fn_count = int(sum(number(row, "location_fn_lesions_per_scan") for row in rows))
        gt_volume = float(sum(number(row, "location_gt_volume_mm3") for row in rows))
        pred_volume = float(sum(number(row, "location_pred_volume_mm3") for row in rows))
        abs_volume_error = abs(pred_volume - gt_volume)
        recall = matched_count / gt_count if gt_count else None
        precision = (pred_count - fp_count) / pred_count if pred_count else None
        f1 = None if recall is None or precision is None or recall + precision == 0 else 2 * recall * precision / (recall + precision)
        aggregate_rows.append(
            {
                "location": location,
                "location_gt_lesion_count": gt_count,
                "location_pred_lesion_count": pred_count,
                "location_matched_lesion_count": matched_count,
                "location_lesion_recall": recall,
                "location_lesion_precision": precision,
                "location_lesion_f1": f1,
                "location_fp_lesions_per_scan": fp_count / case_count,
                "location_fn_lesions_per_scan": fn_count / case_count,
                "location_gt_volume_mm3": gt_volume,
                "location_pred_volume_mm3": pred_volume,
                "location_absolute_volume_error_mm3": abs_volume_error,
                "location_relative_volume_error": None if gt_volume == 0 else abs_volume_error / gt_volume,
                "location_mean_matched_lesion_dice": mean_present(rows, "location_mean_matched_lesion_dice"),
                "location_mean_matched_lesion_hd95_mm": mean_present(rows, "location_mean_matched_lesion_hd95_mm"),
                "location_mean_matched_lesion_assd_mm": mean_present(rows, "location_mean_matched_lesion_assd_mm"),
            }
        )
    return aggregate_rows


def _batch_summary(
    *,
    project_id: str,
    model_name: str,
    case_reports: list[dict],
    batch_pairing_warnings: dict | None = None,
) -> dict:
    batch_root = settings.data_root / project_id / "batch"
    reports_dir = batch_root / "reports"
    tables_dir = batch_root / "tables"
    reports_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    successful = [r for r in case_reports if r.get("status") != "qc_failed" and r.get("subject_metrics")]
    failed = [r for r in case_reports if r.get("status") == "qc_failed"]
    subject_rows = [r["subject_metrics"] for r in successful]
    expert_variability_rows = [
        row
        for report in successful
        for row in (report.get("expert_variability") or [])
    ]
    all_lesion_rows = [row for report in successful for row in (report.get("lesion_metrics") or [])]
    all_prediction_rows = [row for report in successful for row in (report.get("prediction_lesions") or [])]
    all_cluster_rows = [row for report in successful for row in (report.get("cluster_metrics") or [])]
    batch_capability = compute_location_capability(
        lesion_rows=all_lesion_rows,
        prediction_rows=all_prediction_rows,
        cluster_rows=all_cluster_rows,
        case_count=len(successful) or 1,
    )
    batch_location_metrics = batch_capability["location_metrics"]
    batch_size_location_metrics = batch_capability["size_location_metrics"]
    batch_location_topology_metrics = batch_capability["location_topology_metrics"]
    anatomy_available_count = sum(1 for r in successful if r.get("subject_metrics", {}).get("anatomy_available"))
    if not successful or anatomy_available_count == 0:
        batch_anatomy_status = "missing"
    elif anatomy_available_count == len(successful):
        batch_anatomy_status = "available"
    else:
        batch_anatomy_status = "partial"
    batch_anatomy_qc = {
        "status": "pass" if batch_anatomy_status == "available" else batch_anatomy_status,
        "available_case_count": anatomy_available_count,
        "successful_case_count": len(successful),
        "warnings": (
            []
            if batch_anatomy_status == "available"
            else [f"Anatomy was available for {anatomy_available_count} of {len(successful)} successful cases."]
        ),
    }

    metric_keys = sorted(
        {
            key
            for row in subject_rows
            for key, value in row.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
    )
    aggregate_metrics = {
        "project_id": project_id,
        "case_id": "batch_summary",
        "subject_id": "batch_summary",
        "model_name": model_name,
        "dataset_name": "local_batch_upload",
        "case_count": len(case_reports),
        "successful_case_count": len(successful),
        "qc_failed_case_count": len(failed),
        "anatomy_available_case_count": anatomy_available_count,
        "anatomy_failed_case_count": sum(1 for r in case_reports if r.get("anatomy_qc", {}).get("status") == "failed"),
        "anatomy_status": batch_anatomy_status,
        "anatomy_available": anatomy_available_count > 0,
        "ground_truth_source": "expert_consensus_or_uploaded_primary_expert",
    }
    for key in metric_keys:
        aggregate_metrics[f"mean_{key}"] = _mean_numeric(subject_rows, key)
    aggregate_metrics.update(batch_capability["subject_fields"])

    # Duplicate the most important mean metrics without the mean_ prefix so the existing UI cards work.
    for key in [
        "dice_voxel",
        "iou_voxel",
        "lesion_recall",
        "lesion_precision",
        "lesion_f1",
        "relative_volume_error",
        "fp_lesions_per_scan",
        "fn_lesions_per_scan",
        "gt_lesion_count",
        "pred_lesion_count",
        "matched_lesion_count",
        "lesion_count_error",
        "tiny_gt_lesion_count",
        "small_gt_lesion_count",
        "medium_gt_lesion_count",
        "large_gt_lesion_count",
        "missed_tiny_lesion_count",
        "missed_small_lesion_count",
        "missed_medium_lesion_count",
        "missed_large_lesion_count",
        "fp_tiny_lesion_count",
        "fp_small_lesion_count",
        "fp_medium_lesion_count",
        "fp_large_lesion_count",
        "matched_lesion_mean_dice",
        "matched_lesion_median_dice",
        "matched_lesion_mean_hd95_mm",
        "matched_lesion_median_hd95_mm",
        "matched_lesion_mean_assd_mm",
        "matched_lesion_median_assd_mm",
        "high_risk_miss_rate",
        "clinical_evidence_preservation_ratio",
        "clinical_topography_preservation_ratio",
        "gt_topography_count",
        "pred_topography_count",
        "periventricular_recall",
        "periventricular_precision",
        "periventricular_f1",
        "juxtacortical_cortical_recall",
        "juxtacortical_cortical_precision",
        "juxtacortical_cortical_f1",
        "infratentorial_recall",
        "infratentorial_precision",
        "infratentorial_f1",
        "deep_white_matter_other_recall",
        "deep_white_matter_other_precision",
        "deep_white_matter_other_f1",
    ]:
        aggregate_metrics[key] = aggregate_metrics.get(f"mean_{key}")

    for key in [
        "gt_lesion_count",
        "pred_lesion_count",
        "matched_lesion_count",
        "lesion_count_error",
        "tiny_gt_lesion_count",
        "small_gt_lesion_count",
        "medium_gt_lesion_count",
        "large_gt_lesion_count",
        "missed_tiny_lesion_count",
        "missed_small_lesion_count",
        "missed_medium_lesion_count",
        "missed_large_lesion_count",
        "fp_tiny_lesion_count",
        "fp_small_lesion_count",
        "fp_medium_lesion_count",
        "fp_large_lesion_count",
    ]:
        total = _sum_numeric(subject_rows, key)
        if total is not None:
            aggregate_metrics[key] = total
            aggregate_metrics[f"total_{key}"] = total
    batch_hard_case_metrics = hard_case_metrics(subject_rows)
    batch_hard_case_chips = hard_case_chips(batch_hard_case_metrics)
    reliability = reliability_metrics(subject_rows)
    aggregate_metrics.update(reliability["summary"])

    aggregate_blindspots = generate_blindspots(
        aggregate_metrics,
        [],
        [],
        {"status": "passed", "errors": [], "warnings": []},
    )
    if failed:
        aggregate_blindspots.insert(
            0,
            {
                "severity": "critical",
                "title": "One or more cases failed QC",
                "metric_evidence": f"{len(failed)} of {len(case_reports)} uploaded cases failed QC.",
                "clinical_meaning": "Batch averages exclude failed cases, so the deployment evidence is incomplete.",
                "manual_review_action": "Open each failed case report and correct image/mask mismatch before trusting the batch result.",
            },
        )
    if batch_pairing_warnings:
        aggregate_blindspots.append(
            {
                "severity": "medium",
                "title": "Unmatched batch files were skipped",
                "metric_evidence": f"{len(batch_pairing_warnings)} filename group(s) were not present across raw MRI, GT, and prediction.",
                "clinical_meaning": "Only matched cases are summarized.",
                "manual_review_action": "Check filenames before using batch evidence for deployment decisions.",
            }
        )

    deploy = deployment_recommendation(aggregate_metrics, aggregate_blindspots, case_count=len(successful))
    aggregate_metrics["deployment_status"] = deploy["status"]

    case_rows = []
    case_viewers = []
    for report in case_reports:
        subject = report.get("subject_metrics", {})
        if report.get("viewer"):
            case_viewers.append(
                {
                    "case_id": report.get("case_id"),
                    "viewer": report.get("viewer"),
                    "preview_png": report.get("downloads", {}).get("preview_png"),
                    "case_json": report.get("downloads", {}).get("json"),
                }
            )
        case_rows.append(
            {
                "case_id": report.get("case_id"),
                "status": report.get("status", "computed"),
                "deployment_status": subject.get("deployment_status"),
                "dice_voxel": subject.get("dice_voxel"),
                "lesion_recall": subject.get("lesion_recall"),
                "lesion_precision": subject.get("lesion_precision"),
                "lesion_f1": subject.get("lesion_f1"),
                "relative_volume_error": subject.get("relative_volume_error"),
                "fp_lesions_per_scan": subject.get("fp_lesions_per_scan"),
                "fn_lesions_per_scan": subject.get("fn_lesions_per_scan"),
                "anatomy_status": subject.get("anatomy_status"),
                "trust_gap_summary": subject.get("trust_gap_summary"),
                "preview_png": report.get("downloads", {}).get("preview_png"),
                "case_json": report.get("downloads", {}).get("json"),
                "case_html": report.get("downloads", {}).get("html"),
                "viewer_manifest": report.get("downloads", {}).get("viewer_manifest_json"),
            }
        )

    passport = {
        "model_vendor_name": model_name,
        "version": "user supplied / unknown",
        "intended_use": "local MS lesion segmentation validation support",
        "number_of_cases_tested": len(successful),
        "uploaded_case_count": len(case_reports),
        "ground_truth_strategy": "uploaded expert masks",
        "modalities_tested": sorted(
            {
                label
                for report in successful
                for label in (report.get("model_passport", {}).get("modalities_tested") or [])
            }
        )
        or ["uploaded MRI image per case"],
        "anatomy_available_cases": aggregate_metrics["anatomy_available_case_count"],
        "performance_summary": {
            "mean_dice_voxel": aggregate_metrics.get("dice_voxel"),
            "mean_lesion_recall": aggregate_metrics.get("lesion_recall"),
            "mean_lesion_precision": aggregate_metrics.get("lesion_precision"),
            "mean_lesion_f1": aggregate_metrics.get("lesion_f1"),
        },
        "deployment_recommendation": deploy,
        "failure_fingerprint": failure_fingerprint(aggregate_metrics, all_lesion_rows, all_prediction_rows, all_cluster_rows),
        "governance_wording": "Local batch validation summary for segmentation evidence review.",
    }

    batch_report = {
        "mode": "batch",
        "project_id": project_id,
        "case_id": "batch_summary",
        "product": "NeuroTrust-MS",
        "safety_disclaimer": SAFETY_DISCLAIMER,
        "subject_metrics": aggregate_metrics,
        "case_results": case_rows,
        "location_metrics": batch_location_metrics,
        "size_location_metrics": batch_size_location_metrics,
        "location_topology_metrics": batch_location_topology_metrics,
        "case_viewers": case_viewers,
        "hard_case_metrics": batch_hard_case_metrics,
        "hard_case_summary": batch_hard_case_chips,
        "reliability_metrics": reliability["rows"],
        "reliability_summary": reliability["summary"],
        "anatomy_qc": batch_anatomy_qc,
        "blindspots": aggregate_blindspots,
        "failure_fingerprint": passport["failure_fingerprint"],
        "trust_gap_summary": trust_gap_summary(aggregate_metrics, passport["failure_fingerprint"]),
        "radiologist_watchlist": sorted(
            [item for report in successful for item in report.get("radiologist_watchlist", [])],
            key=lambda row: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(row.get("severity"), 9), row.get("subject_id") or ""),
        )[:10],
        "model_passport": passport,
        "method_badges": [],
        "deployment_recommendation": deploy,
        "anatomy_method_card": {
            "status": batch_anatomy_status,
            "wording": "Batch anatomy rows aggregate per-case FreeSurfer/SynthSeg proxy localization.",
        },
        "executive_summary": (
            f"{deploy['status'].title()}: {model_name} was validated on "
            f"{len(successful)} successful case(s), with {len(failed)} QC failure(s). "
            "Use the watchlist, anatomy, and reliability tabs for targeted verification."
        ),
        "limitations": [
            "Batch validation depends on uploaded masks being correctly paired by filename.",
            "Averages exclude QC-failed cases.",
            "Recommendation confidence is tied to uploaded validation set size and configured evidence thresholds.",
        ],
    }
    batch_report["method_badges"] = method_badges(batch_report)

    write_csv(tables_dir / "batch_subject_metrics.csv", subject_rows)
    write_csv(tables_dir / "batch_case_summary.csv", case_rows)
    write_csv(tables_dir / "batch_size_bin_metrics.csv", _size_bin_rows_from_metrics(aggregate_metrics, case_id="batch_summary", model_name=model_name))
    write_csv(
        tables_dir / "batch_subject_evidence_preservation.csv",
        [_subject_evidence_row(row, case_id=str(row.get("case_id") or row.get("subject_id") or ""), model_name=model_name) for row in subject_rows],
    )
    write_csv(tables_dir / "batch_location_metrics.csv", batch_location_metrics)
    write_csv(tables_dir / "batch_location_volume_metrics.csv", batch_location_metrics)
    write_csv(tables_dir / "batch_location_capability_metrics.csv", batch_location_metrics)
    write_csv(tables_dir / "batch_size_location_interaction_metrics.csv", batch_size_location_metrics)
    write_csv(tables_dir / "batch_location_topology_metrics.csv", batch_location_topology_metrics)
    write_csv(tables_dir / "batch_hard_case_metrics.csv", batch_hard_case_metrics)
    write_csv(tables_dir / "batch_reliability_metrics.csv", reliability["rows"])
    write_csv(tables_dir / "batch_expert_variability.csv", expert_variability_rows)
    write_csv(tables_dir / "batch_radiologist_watchlist.csv", batch_report["radiologist_watchlist"])
    write_json(reports_dir / "batch_radiologist_watchlist.json", {"radiologist_watchlist": batch_report["radiologist_watchlist"]})
    write_json(reports_dir / "batch_validation_result.json", batch_report)
    write_json(reports_dir / "batch_model_passport.json", passport)
    write_json(reports_dir / "batch_blindspot_report.json", {"blindspots": aggregate_blindspots})
    write_json(reports_dir / "batch_qc_report.json", {"pairing_warnings": batch_pairing_warnings or {}, "failed_cases": failed})
    write_json(reports_dir / "batch_failure_fingerprint.json", batch_report["failure_fingerprint"])
    write_json(reports_dir / "batch_location_metrics.json", {"location_metrics": batch_location_metrics})
    write_json(reports_dir / "batch_location_capability_metrics.json", {"location_capability_metrics": batch_location_metrics})
    write_json(reports_dir / "batch_size_location_interaction_metrics.json", {"size_location_interaction_metrics": batch_size_location_metrics})
    write_json(reports_dir / "batch_location_topology_metrics.json", {"location_topology_metrics": batch_location_topology_metrics})
    write_json(reports_dir / "batch_hard_case_metrics.json", {"hard_case_metrics": batch_hard_case_metrics, "summary": batch_hard_case_chips})
    write_json(reports_dir / "batch_reliability_metrics.json", {"reliability_metrics": reliability["rows"], "summary": reliability["summary"]})
    write_json(reports_dir / "batch_anatomy_qc.json", batch_anatomy_qc)
    write_json(reports_dir / "batch_method_card.json", {"anatomy_method_card": batch_report["anatomy_method_card"], "model_passport": passport})

    first_preview = next((row.get("preview_png") for row in case_rows if row.get("preview_png")), None)
    first_viewer = next((r.get("viewer") for r in case_reports if r.get("viewer")), None)
    batch_report["downloads"] = {
        "batch_json": _static_url(reports_dir / "batch_validation_result.json"),
        "batch_subject_metrics_csv": _static_url(tables_dir / "batch_subject_metrics.csv"),
        "batch_case_summary_csv": _static_url(tables_dir / "batch_case_summary.csv"),
        "batch_size_bin_metrics_csv": _static_url(tables_dir / "batch_size_bin_metrics.csv"),
        "batch_subject_evidence_preservation_csv": _static_url(tables_dir / "batch_subject_evidence_preservation.csv"),
        "batch_location_metrics_csv": _static_url(tables_dir / "batch_location_metrics.csv"),
        "batch_location_volume_metrics_csv": _static_url(tables_dir / "batch_location_volume_metrics.csv"),
        "batch_location_capability_metrics_csv": _static_url(tables_dir / "batch_location_capability_metrics.csv"),
        "batch_size_location_interaction_metrics_csv": _static_url(tables_dir / "batch_size_location_interaction_metrics.csv"),
        "batch_location_topology_metrics_csv": _static_url(tables_dir / "batch_location_topology_metrics.csv"),
        "batch_hard_case_metrics_csv": _static_url(tables_dir / "batch_hard_case_metrics.csv"),
        "batch_reliability_metrics_csv": _static_url(tables_dir / "batch_reliability_metrics.csv"),
        "batch_location_metrics_json": _static_url(reports_dir / "batch_location_metrics.json"),
        "batch_location_capability_metrics_json": _static_url(reports_dir / "batch_location_capability_metrics.json"),
        "batch_size_location_interaction_metrics_json": _static_url(reports_dir / "batch_size_location_interaction_metrics.json"),
        "batch_location_topology_metrics_json": _static_url(reports_dir / "batch_location_topology_metrics.json"),
        "batch_hard_case_metrics_json": _static_url(reports_dir / "batch_hard_case_metrics.json"),
        "batch_reliability_metrics_json": _static_url(reports_dir / "batch_reliability_metrics.json"),
        "batch_anatomy_qc_json": _static_url(reports_dir / "batch_anatomy_qc.json"),
        "batch_expert_variability_csv": _static_url(tables_dir / "batch_expert_variability.csv"),
        "batch_model_passport": _static_url(reports_dir / "batch_model_passport.json"),
        "batch_blindspot_report": _static_url(reports_dir / "batch_blindspot_report.json"),
        "batch_qc_report_json": _static_url(reports_dir / "batch_qc_report.json"),
        "batch_failure_fingerprint_json": _static_url(reports_dir / "batch_failure_fingerprint.json"),
        "batch_radiologist_watchlist_csv": _static_url(tables_dir / "batch_radiologist_watchlist.csv"),
        "batch_radiologist_watchlist_json": _static_url(reports_dir / "batch_radiologist_watchlist.json"),
        "batch_method_card_json": _static_url(reports_dir / "batch_method_card.json"),
    }
    if first_preview:
        batch_report["downloads"]["first_case_preview_png"] = first_preview
    if first_viewer:
        batch_report["viewer"] = {
            **first_viewer,
            "label": "NiiVue viewer from the first successfully processed batch case.",
        }

    batch_report["downloads"]["full_validation_result_json"] = _static_url(reports_dir / "full_validation_result.json")
    write_json(reports_dir / "batch_validation_result.json", batch_report)
    write_json(reports_dir / "full_validation_result.json", batch_report)
    return batch_report


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "product": settings.app_name,
        "hosted_mode": settings.hosted_mode,
        "hosting_mode": settings.hosting_mode,
        "max_batch_cases": settings.max_batch_cases,
        "max_concurrent_jobs": settings.max_concurrent_jobs,
        "job_ttl_hours": settings.job_ttl_hours,
        "max_upload_mb": settings.max_upload_mb,
        "storage_dir": str(settings.data_root),
        "viewer_assets_on_demand": settings.viewer_assets_on_demand,
        "safety": SAFETY_DISCLAIMER,
    }


@app.get("/api/validations/history")
def validation_history(request: Request) -> dict:
    session = _require_session(request)
    return {
        "email": session["email"],
        "validations": _validation_history_for_email(session["email"], limit=50),
        "safety_privacy": _safety_privacy_payload(),
    }


@app.get("/api/validations/{run_id}")
def validation_result(run_id: str, request: Request) -> dict:
    session = _require_session(request)
    _init_access_db()
    with sqlite3.connect(_access_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT result_path
            FROM validation_runs
            WHERE run_id = ? AND email = ?
            """,
            (run_id, session["email"]),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Validation run not found for this signed-in user.")
    result_path = Path(str(row["result_path"] or ""))
    if not result_path.is_file():
        raise HTTPException(
            410,
            "Saved record found. The temporary report files were cleaned up, so rerun the demo or validation to regenerate the full report.",
        )
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, f"Stored validation result could not be read: {exc}") from exc


@app.get("/api/admin/database-audit")
def database_audit(request: Request) -> dict:
    admin_key = request.headers.get("x-neurotrust-admin-key", "")
    second_factor = request.headers.get("x-neurotrust-second-factor", "")
    if not settings.admin_safety_key or not settings.admin_second_factor:
        raise HTTPException(403, "Dual verification is not configured for database audit access.")
    if not hmac.compare_digest(admin_key, settings.admin_safety_key) or not hmac.compare_digest(second_factor, settings.admin_second_factor):
        raise HTTPException(403, "Dual verification failed.")
    _init_access_db()
    with sqlite3.connect(_access_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        users = conn.execute("SELECT COUNT(*) AS n FROM access_users").fetchone()["n"]
        logins = conn.execute("SELECT COUNT(*) AS n FROM access_log").fetchone()["n"]
        sessions = conn.execute("SELECT COUNT(*) AS n FROM access_sessions WHERE active = 1").fetchone()["n"]
        validations = conn.execute("SELECT COUNT(*) AS n FROM validation_runs").fetchone()["n"]
    return {
        "ok": True,
        "dual_verification": "passed",
        "counts": {"users": users, "logins": logins, "active_sessions": sessions, "validation_runs": validations},
        "safety_privacy": _safety_privacy_payload(),
    }


@app.post("/api/freesurfer/check")
def freesurfer_check() -> dict:
    return {
        "status": "checked",
        "freesurfer_recon_all": shutil.which("recon-all"),
        "synthseg": shutil.which("mri_synthseg"),
        "default_behavior": "not_run",
        "message": "Upload existing anatomy labelmaps for demo use. Long FreeSurfer/SynthSeg jobs are not started by default.",
        "expected_outputs": ["aparc+aseg.mgz", "aseg.mgz", "wmparc.mgz", "ribbon.mgz", "brainmask.mgz"],
    }


@app.post("/api/freesurfer/run-synthseg")
def freesurfer_run_synthseg() -> dict:
    return {
        "status": "not_started",
        "reason": "Non-blocking anatomy generation is intentionally disabled in the local demo path.",
        "safe_next_step": "Run SynthSeg/FreeSurfer externally, then upload the resulting .mgz/.nii.gz labelmap.",
    }


def _default_demo_batch_candidates() -> list[Path]:
    candidates = []
    if settings.demo_batch_root:
        candidates.append(settings.demo_batch_root)
    candidates.extend(
        [
            Path("/var/lib/neurotrust-ms/demo_data/test_1"),
            Path.home() / "Downloads" / "test 1",
            Path.home() / "Downloads" / "neurotrust_msseg_batch_nnUNet_20260709_123200",
            Path("backend/data/msseg_local_batch_validation_a9539b"),
        ]
    )
    return candidates


def _medical_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        [
            path
            for path in folder.rglob("*")
            if path.is_file() and (path.name.lower().endswith(".nii") or path.name.lower().endswith(".nii.gz") or path.name.lower().endswith(".mgz"))
        ]
    )


def _text_or_metadata_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(
        [
            path
            for path in folder.rglob("*")
            if path.is_file() and path.name.lower().endswith((".csv", ".json", ".txt"))
        ]
    )


def _relative_demo_path(root: Path, path: Path | None) -> str | None:
    if not path:
        return None
    try:
        return path.relative_to(root).as_posix()
    except Exception:
        return str(path)


def _demo_map_first(root: Path, *folders: str) -> dict[str, Path]:
    mapped: dict[str, Path] = {}
    for folder in folders:
        for path in _medical_files(root / folder):
            key = _case_key_from_stem(_strip_nifti_suffix(path.name))
            mapped.setdefault(key, path)
    return mapped


def _demo_map_many(root: Path, *folders: str) -> dict[str, list[Path]]:
    mapped: dict[str, list[Path]] = {}
    for folder in folders:
        for path in _medical_files(root / folder):
            key = _case_key_from_stem(_strip_nifti_suffix(path.name))
            mapped.setdefault(key, []).append(path)
    return mapped


def _demo_upload_fields(root: Path, cases: list[dict]) -> list[dict]:
    field_defs = [
        ("raw_mris", "Raw MRIs", "raw_mris", "Primary MRI volume used for validation geometry and viewer base image."),
        ("gts", "Expert GT masks", "gts", "Primary expert lesion mask used as ground truth."),
        ("predictions", "Prediction masks", "predictions", "One-model prediction mask validated against GT."),
        ("expert_2_masks", "Second expert masks", "expert_2_masks_test_only", "Test-only derived support file for reader-variability features."),
        ("probability_maps", "Probability maps", "probability_maps_test_only", "Test-only derived support file for confidence-map features."),
        ("uncertainty_maps", "Uncertainty maps", "uncertainty_maps_test_only", "Test-only derived support file for uncertainty features."),
        ("freesurfer_files", "FreeSurfer subject files", "freesurfer_subject_files", "Preferred anatomy source for location evidence."),
        ("anatomy_labelmaps", "Optional anatomy labelmaps", "anatomy_labelmaps_optional", "Alternative anatomy labelmap source; not preferred when FreeSurfer subject files are present."),
        ("metadata_csv", "Metadata", "metadata", "Transparency manifest for the prepared demo bundle."),
        ("bundle_documents", "Bundle documents", ".", "README, checksum, and JSON manifest files shipped with the prepared demo bundle."),
    ]
    fields = []
    for key, label, folder, note in field_defs:
        if key == "metadata_csv":
            files = _text_or_metadata_files(root / folder)
        elif key == "bundle_documents":
            files = sorted(
                [
                    path
                    for path in root.iterdir()
                    if path.is_file() and path.name.lower().endswith((".txt", ".json", ".csv"))
                ]
            )
        else:
            files = _medical_files(root / folder)
        fields.append(
            {
                "website_field_key": key,
                "website_field_label": label,
                "source_folder": folder,
                "file_count": len(files),
                "files": [_relative_demo_path(root, path) for path in files[:50]],
                "note": note,
            }
        )
    return fields


def _demo_case_manifest(root: Path, cases: list[dict]) -> list[dict]:
    rows = []
    for case in cases:
        rows.append(
            {
                "case_id": case["case_id"],
                "raw_mris": [_relative_demo_path(root, case.get("raw"))],
                "gts": [_relative_demo_path(root, case.get("gt"))],
                "predictions": [_relative_demo_path(root, case.get("pred"))],
                "expert_2_masks": [_relative_demo_path(root, case.get("expert_2"))] if case.get("expert_2") else [],
                "probability_maps": [_relative_demo_path(root, case.get("probability"))] if case.get("probability") else [],
                "uncertainty_maps": [_relative_demo_path(root, case.get("uncertainty"))] if case.get("uncertainty") else [],
                "freesurfer_files": [_relative_demo_path(root, path) for path in case.get("freesurfer_files", [])],
                "selected_anatomy_labelmap": _relative_demo_path(root, case.get("anatomy")),
            }
        )
    return rows


def _demo_batch_from_root(root: Path) -> list[dict]:
    raw = _demo_map_first(root, "raw_mris")
    gts = _demo_map_first(root, "gts")
    preds = _demo_map_first(root, "predictions")
    expert2 = _demo_map_first(root, "expert_2_masks_test_only", "expert_2_masks")
    probability = _demo_map_first(root, "probability_maps_test_only", "probability_maps")
    uncertainty = _demo_map_first(root, "uncertainty_maps_test_only", "uncertainty_maps")
    freesurfer_by_case = _demo_map_many(root, "freesurfer_subject_files", "freesurfer_clean_upload_neurotrust", "freesurfer_masks")
    optional_anatomy_by_case = _demo_map_many(root, "anatomy_labelmaps_optional", "anatomy_labelmaps")
    cases = []
    for key in sorted(set(raw) & set(gts) & set(preds))[: settings.max_batch_cases]:
        freesurfer_files = freesurfer_by_case.get(key, [])
        optional_anatomy = optional_anatomy_by_case.get(key, [])
        selected_anatomy = _choose_freesurfer_labelmap(freesurfer_files) or _choose_freesurfer_labelmap(optional_anatomy)
        cases.append(
            {
                "case_id": sanitize_filename(key),
                "raw": raw[key],
                "gt": gts[key],
                "pred": preds[key],
                "expert_2": expert2.get(key),
                "probability": probability.get(key),
                "uncertainty": uncertainty.get(key),
                "freesurfer_files": freesurfer_files,
                "optional_anatomy_files": optional_anatomy,
                "anatomy": selected_anatomy,
            }
        )
    return cases


def _copy_demo_file(src: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / sanitize_filename(src.name)
    shutil.copy2(src, target)
    return target


def _copy_demo_files(paths: list[Path], dest: Path) -> list[Path]:
    return [_copy_demo_file(path, dest) for path in paths]


def _copy_demo_bundle_documents(root: Path, dest: Path) -> list[Path]:
    docs = sorted(
        [
            path
            for path in root.iterdir()
            if path.is_file() and path.name.lower().endswith((".txt", ".json", ".csv"))
        ]
    )
    metadata_docs = _text_or_metadata_files(root / "metadata")
    return _copy_demo_files(docs + metadata_docs, dest)


def _rewrite_report_file(report: dict) -> None:
    result_path = _path_from_static_url((report.get("downloads") or {}).get("full_validation_result_json"))
    if result_path:
        write_json(result_path, report)
    json_path = _path_from_static_url((report.get("downloads") or {}).get("batch_json") or (report.get("downloads") or {}).get("json"))
    if json_path:
        write_json(json_path, report)


def _run_five_case_demo(*, email: str) -> dict:
    project_id = "msseg_five_case_demo_" + uuid.uuid4().hex[:6]
    case_reports = []
    transparency: dict[str, object] = {
        "demo_name": "Five-case MS lesion validation demo",
        "model_name": "nnUNet MSSEG demo prediction masks",
        "case_limit": settings.max_batch_cases,
        "input_policy": "raw MRI + expert GT + one-model prediction; optional anatomy labelmap when present",
    }
    for root in _default_demo_batch_candidates():
        if not root:
            continue
        cases = _demo_batch_from_root(root.expanduser())
        if cases:
            expanded_root = root.expanduser()
            copied_docs = _copy_demo_bundle_documents(expanded_root, settings.data_root / project_id / "batch" / "uploads" / "bundle_documents")
            transparency["source"] = str(expanded_root)
            transparency["case_ids"] = [case["case_id"] for case in cases]
            transparency["transparent_upload_simulation"] = True
            transparency["upload_fields"] = _demo_upload_fields(expanded_root, cases)
            transparency["case_upload_manifest"] = _demo_case_manifest(expanded_root, cases)
            transparency["copied_bundle_documents"] = [_static_url(path) for path in copied_docs if _is_under_data_root(path)]
            transparency["test_only_notice"] = (
                "Second expert, probability, and uncertainty files are test-only support files for exercising "
                "reader-variability and confidence-map features; they are not additional clinical ground truth."
            )
            for case in cases:
                case_id = case["case_id"]
                case_dir = settings.data_root / project_id / "cases" / case_id / "uploads"
                image_path = _copy_demo_file(case["raw"], case_dir / "images")
                gt_path = _copy_demo_file(case["gt"], case_dir / "expert_masks")
                pred_path = _copy_demo_file(case["pred"], case_dir / "ai_masks")
                expert2_path = _copy_demo_file(case["expert_2"], case_dir / "expert_masks") if case.get("expert_2") else None
                probability_path = _copy_demo_file(case["probability"], case_dir / "probability") if case.get("probability") else None
                uncertainty_path = _copy_demo_file(case["uncertainty"], case_dir / "probability") if case.get("uncertainty") else None
                copied_freesurfer_paths = _copy_demo_files(case.get("freesurfer_files", []), case_dir / "freesurfer_subject_files")
                copied_optional_anatomy_paths = _copy_demo_files(case.get("optional_anatomy_files", []), case_dir / "anatomy_labelmaps_optional")
                anatomy_path = _choose_freesurfer_labelmap(copied_freesurfer_paths)
                if anatomy_path is None:
                    anatomy_path = _choose_freesurfer_labelmap(copied_optional_anatomy_paths)
                case_reports.append(
                    _run_validation(
                        project_id=project_id,
                        case_id=case_id,
                        model_name="nnUNet MSSEG five-case demo",
                        image_path=image_path,
                        gt_path=gt_path,
                        pred_path=pred_path,
                        expert_2_path=expert2_path,
                        anatomy_labelmap_path=anatomy_path,
                        probability_map_path=probability_path,
                        uncertainty_map_path=uncertainty_path,
                        base_image_paths=[image_path],
                        synthetic=False,
                    )
                )
            report = _batch_summary(project_id=project_id, model_name="nnUNet MSSEG five-case demo", case_reports=case_reports, batch_pairing_warnings={})
            report["demo"] = transparency
            _store_validation_record(report, email=email, source="five_case_demo_dataset")
            _rewrite_report_file(report)
            return report

    expected = [str(path.expanduser()) for path in _default_demo_batch_candidates()]
    raise HTTPException(
        404,
        {
            "message": "Prepared 5-case demo bundle was not found, so no five-case validation was run.",
            "expected_paths": expected,
            "required_folders": [
                "raw_mris",
                "gts",
                "predictions",
                "expert_2_masks_test_only",
                "probability_maps_test_only",
                "uncertainty_maps_test_only",
                "freesurfer_subject_files",
                "anatomy_labelmaps_optional",
                "metadata",
            ],
            "local_path": "~/Downloads/test 1",
            "server_path": "/var/lib/neurotrust-ms/demo_data/test_1",
        },
    )


def _run_simple_demo(*, email: str) -> dict:
    project_id = "synthetic_demo_" + uuid.uuid4().hex[:6]
    case_id = "synthetic_" + uuid.uuid4().hex[:8]
    case_dir = settings.data_root / project_id / "cases" / case_id
    paths = create_synthetic_case(case_dir)
    report = _run_validation(
        project_id=project_id,
        case_id=case_id,
        model_name="Simple generated demo",
        image_path=paths["image"],
        gt_path=paths["ground_truth"],
        pred_path=paths["prediction"],
        expert_2_path=paths["expert_2"],
        anatomy_labelmap_path=paths.get("anatomy"),
        base_image_paths=[paths["image"]],
        synthetic=True,
    )
    report["demo"] = {
        "demo_name": "Simple one-case validation demo",
        "source": "generated synthetic case",
        "input_policy": "one generated MRI, one expert GT, one AI prediction, one optional second expert, one toy anatomy labelmap",
    }
    _store_validation_record(report, email=email, source="simple_demo")
    _rewrite_report_file(report)
    return report


@app.post("/api/demo/run")
def run_demo(request: Request) -> dict:
    session = _require_session(request)
    _acquire_validation_slot()
    try:
        return _run_simple_demo(email=session["email"])
    finally:
        _release_validation_slot()


@app.post("/api/demo/run-five-case")
def run_five_case_demo(request: Request) -> dict:
    session = _require_session(request)
    _acquire_validation_slot()
    try:
        return _run_five_case_demo(email=session["email"])
    finally:
        _release_validation_slot()


async def _save_upload(upload: UploadFile, dest: Path) -> Path:
    if not upload.filename or not is_allowed_upload(upload.filename):
        raise HTTPException(400, f"Unsupported file type: {upload.filename}")
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / sanitize_filename(upload.filename)
    if not _is_under_data_root(target):
        raise HTTPException(400, "Unsafe upload path.")
    limit_bytes = max(1, settings.max_upload_mb) * 1024 * 1024
    total_bytes = 0
    try:
        with open(target, "wb") as f:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > limit_bytes:
                    raise HTTPException(413, f"Upload too large. Maximum per file is {settings.max_upload_mb} MB.")
                f.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    return target


@app.post("/api/validation/upload-run")
async def upload_run(
    request: Request,
    project_name: str = Form("Local validation project"),
    model_name: str = Form("Uploaded AI model"),
    image: UploadFile = File(...),
    ground_truth: UploadFile = File(...),
    prediction: UploadFile = File(...),
    expert_2: UploadFile | None = File(None),
    expert_3: UploadFile | None = File(None),
    anatomy_labelmap: UploadFile | None = File(None),
    anatomy_lut: UploadFile | None = File(None),
    brain_mask: UploadFile | None = File(None),
    probability_map: UploadFile | None = File(None),
    uncertainty_map: UploadFile | None = File(None),
    metadata_json: UploadFile | None = File(None),
) -> dict:
    session = _require_session(request)
    _acquire_validation_slot()
    try:
        project_id = sanitize_filename(project_name).lower()[:40] + "_" + uuid.uuid4().hex[:6]
        case_id = "case_" + uuid.uuid4().hex[:8]
        case_dir = settings.data_root / project_id / "cases" / case_id / "uploads"
        image_path = await _save_upload(image, case_dir / "images")
        gt_path = await _save_upload(ground_truth, case_dir / "expert_masks")
        pred_path = await _save_upload(prediction, case_dir / "ai_masks")
        expert2_path = await _save_upload(expert_2, case_dir / "expert_masks") if expert_2 else None
        if expert_3:
            await _save_upload(expert_3, case_dir / "expert_masks")
        anatomy_path = await _save_upload(anatomy_labelmap, case_dir / "anatomy") if anatomy_labelmap else None
        lut_path = await _save_upload(anatomy_lut, case_dir / "anatomy") if anatomy_lut else None
        if brain_mask:
            await _save_upload(brain_mask, case_dir / "anatomy")
        probability_path = await _save_upload(probability_map, case_dir / "probability") if probability_map else None
        uncertainty_path = await _save_upload(uncertainty_map, case_dir / "probability") if uncertainty_map else None
        if metadata_json:
            await _save_upload(metadata_json, case_dir / "metadata")
        report = _run_validation(
            project_id=project_id,
            case_id=case_id,
            model_name=model_name,
            image_path=image_path,
            gt_path=gt_path,
            pred_path=pred_path,
            expert_2_path=expert2_path,
            anatomy_labelmap_path=anatomy_path,
            anatomy_lut_path=lut_path,
            probability_map_path=probability_path,
            uncertainty_map_path=uncertainty_path,
            base_image_paths=[image_path],
            synthetic=False,
        )
        _store_validation_record(report, email=session["email"], source="single_upload")
        _rewrite_report_file(report)
        return report
    finally:
        _release_validation_slot()


@app.post("/api/validation/upload-batch-run")
async def upload_batch_run(
    request: Request,
    project_name: str = Form("Local batch validation project"),
    model_name: str = Form("Uploaded AI model"),
    raw_mris: list[UploadFile] = File(...),
    gts: list[UploadFile] = File(...),
    predictions: list[UploadFile] = File(...),
    anatomy_labelmaps: list[UploadFile] | None = File(None),
    freesurfer_files: list[UploadFile] | None = File(None),
    probability_maps: list[UploadFile] | None = File(None),
    uncertainty_maps: list[UploadFile] | None = File(None),
    expert_2_masks: list[UploadFile] | None = File(None),
    anatomy_lut: UploadFile | None = File(None),
    metadata_csv: UploadFile | None = File(None),
) -> dict:
    session = _require_session(request)
    _acquire_validation_slot()
    try:
        image_groups = _upload_group_map(raw_mris, "raw_mris")
        gt_groups = _upload_group_map(gts, "gts")
        pred_groups = _upload_group_map(predictions, "predictions")
        anatomy_map = _upload_optional_first_map(anatomy_labelmaps, "anatomy_labelmaps")
        freesurfer_groups = _upload_freesurfer_group_map(freesurfer_files)
        freesurfer_manifest_preferences = _parse_freesurfer_manifest_preferences(freesurfer_files)
        probability_map = _upload_optional_first_map(probability_maps, "probability_maps")
        uncertainty_map = _upload_optional_first_map(uncertainty_maps, "uncertainty_maps")
        expert2_map = _upload_optional_first_map(expert_2_masks, "expert_2_masks")

        duplicate_required = {
            label: sorted(key for key, value in group.items() if len(value) > 1)
            for label, group in {"gts": gt_groups, "predictions": pred_groups}.items()
        }
        duplicate_required = {k: v for k, v in duplicate_required.items() if v}
        if duplicate_required:
            raise HTTPException(400, {"message": "Duplicate GT or prediction files for a case.", "duplicates": duplicate_required})

        common = sorted(set(image_groups) & set(gt_groups) & set(pred_groups))
        all_keys = set(image_groups) | set(gt_groups) | set(pred_groups)
        missing = {
            key: {
                "raw_mri": key in image_groups,
                "gt": key in gt_groups,
                "prediction": key in pred_groups,
            }
            for key in sorted(all_keys - set(common))
        }
        if not common:
            raise HTTPException(
                400,
                {
                    "message": "No matching cases found. File basenames must match across raw_mris, gts, and predictions.",
                    "example": "raw_mris/eval_001.nii.gz, gts/eval_001.nii.gz, predictions/eval_001.nii.gz",
                    "missing": missing,
                },
            )
        if len(common) > settings.max_batch_cases:
            raise HTTPException(400, "Hosted demo limit: maximum 5 cases per validation run.")

        project_id = sanitize_filename(project_name).lower()[:40] + "_" + uuid.uuid4().hex[:6]
        batch_upload_dir = settings.data_root / project_id / "batch" / "uploads"
        lut_path = await _save_upload(anatomy_lut, batch_upload_dir / "anatomy") if anatomy_lut else None
        if lut_path is None:
            fs_lut = _find_freesurfer_lut(freesurfer_files)
            if fs_lut is not None:
                lut_path = await _save_upload(fs_lut, batch_upload_dir / "anatomy")
        for upload in freesurfer_files or []:
            if upload.filename and _is_freesurfer_manifest_upload(upload):
                await _save_upload(upload, batch_upload_dir / "anatomy")
                break
        if metadata_csv:
            await _save_upload(metadata_csv, batch_upload_dir / "metadata")
        case_reports = []
        for key in common:
            case_id = sanitize_filename(key)
            case_dir = settings.data_root / project_id / "cases" / case_id / "uploads"
            image_paths = []
            for upload in image_groups[key]:
                image_paths.append(await _save_upload(upload, case_dir / "images"))
            image_path = _choose_primary_mri(image_paths)
            gt_path = await _save_upload(gt_groups[key][0], case_dir / "expert_masks")
            pred_path = await _save_upload(pred_groups[key][0], case_dir / "ai_masks")
            anatomy_path = await _save_upload(anatomy_map[key], case_dir / "anatomy") if key in anatomy_map else None
            freesurfer_paths = []
            for upload in freesurfer_groups.get(key, []):
                freesurfer_paths.append(await _save_upload(upload, case_dir / "freesurfer_subject_files"))
            selected_freesurfer_labelmap = _choose_freesurfer_labelmap(
                freesurfer_paths,
                preferred_names=freesurfer_manifest_preferences.get(key),
            )
            if anatomy_path is None:
                anatomy_path = selected_freesurfer_labelmap
            probability_path = await _save_upload(probability_map[key], case_dir / "probability") if key in probability_map else None
            uncertainty_path = await _save_upload(uncertainty_map[key], case_dir / "probability") if key in uncertainty_map else None
            expert2_path = await _save_upload(expert2_map[key], case_dir / "expert_masks") if key in expert2_map else None
            case_reports.append(
                _run_validation(
                    project_id=project_id,
                    case_id=case_id,
                    model_name=model_name,
                    image_path=image_path,
                    gt_path=gt_path,
                    pred_path=pred_path,
                    expert_2_path=expert2_path,
                    anatomy_labelmap_path=anatomy_path,
                    anatomy_lut_path=lut_path,
                    probability_map_path=probability_path,
                    uncertainty_map_path=uncertainty_path,
                    base_image_paths=image_paths,
                    synthetic=False,
                )
            )

        report = _batch_summary(project_id=project_id, model_name=model_name, case_reports=case_reports, batch_pairing_warnings=missing)
        _store_validation_record(report, email=session["email"], source="batch_upload")
        _rewrite_report_file(report)
        return report
    finally:
        _release_validation_slot()

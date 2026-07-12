from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .safety import SAFETY_DISCLAIMER


def _json_default(value: Any):
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = sorted({k for row in rows for k in row.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_html_report(path: Path, report: dict) -> None:
    blindspots = "".join(
        f"<li><strong>{b['severity'].upper()} — {b['title']}:</strong> {b['metric_evidence']}<br><em>{b['manual_review_action']}</em></li>"
        for b in report["blindspots"]
    )
    metrics = report["subject_metrics"]
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>NeuroTrust-MS Report</title>
<style>
body{{font-family:Inter,Arial,sans-serif;background:#f7fafc;color:#132330;margin:0;padding:32px}}
.card{{background:white;border:1px solid #dbe5ea;border-radius:18px;padding:22px;margin:18px 0;box-shadow:0 10px 30px rgba(20,40,60,.08)}}
.badge{{display:inline-block;padding:8px 12px;border-radius:999px;background:#eaf4f8;color:#07516b;font-weight:700}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #e5edf2;padding:8px;text-align:left}}
</style></head><body>
<h1>NeuroTrust-MS Local Validation Report</h1>
<p class="badge">{report['deployment_recommendation']['status'].upper()}</p>
<div class="card"><h2>Scope statement</h2><p>{SAFETY_DISCLAIMER}</p></div>
<div class="card"><h2>Executive summary</h2><p>{report['executive_summary']}</p></div>
<div class="card"><h2>Core metrics</h2><table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Voxel Dice</td><td>{metrics.get('dice_voxel')}</td></tr>
<tr><td>Lesion recall</td><td>{metrics.get('lesion_recall')}</td></tr>
<tr><td>Lesion precision</td><td>{metrics.get('lesion_precision')}</td></tr>
<tr><td>Lesion F1</td><td>{metrics.get('lesion_f1')}</td></tr>
<tr><td>Relative volume error</td><td>{metrics.get('relative_volume_error')}</td></tr>
</table></div>
<div class="card"><h2>Validation blind spots</h2><ul>{blindspots}</ul></div>
<div class="card"><h2>Scope notes</h2><ul><li>Location analysis requires anatomical masks.</li><li>Longitudinal change requires registered timepoints.</li><li>Confidence increases with uploaded validation set size.</li></ul></div>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def preview_png(image: np.ndarray, gt: np.ndarray, pred: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    z = image.shape[2] // 2
    base = image[:, :, z]
    base = (base - np.nanmin(base)) / max(np.nanmax(base) - np.nanmin(base), 1e-6)
    rgb = np.stack([base, base, base], axis=-1)
    gt2 = gt[:, :, z].astype(bool)
    pred2 = pred[:, :, z].astype(bool)
    missed = gt2 & ~pred2
    fp = pred2 & ~gt2
    overlap = gt2 & pred2
    rgb[gt2 & ~overlap] = [0.0, 0.62, 0.45]
    rgb[pred2 & ~overlap] = [0.0, 0.45, 0.70]
    rgb[overlap] = [0.95, 0.80, 0.10]
    rgb[missed] = [0.84, 0.20, 0.10]
    rgb[fp] = [0.90, 0.56, 0.00]
    img = Image.fromarray(np.uint8(np.clip(rgb, 0, 1) * 255))
    img = img.resize((512, 512))
    img.save(out_path)


def preview_layer_pngs(image: np.ndarray, gt: np.ndarray, pred: np.ndarray, out_dir: Path) -> dict[str, Path]:
    """Write honest 2D middle-slice viewer layers derived from the uploaded masks."""
    out_dir.mkdir(parents=True, exist_ok=True)
    z = image.shape[2] // 2
    base = image[:, :, z]
    base = (base - np.nanmin(base)) / max(np.nanmax(base) - np.nanmin(base), 1e-6)
    base_rgb = np.stack([base, base, base], axis=-1)
    base_img = Image.fromarray(np.uint8(np.clip(base_rgb, 0, 1) * 255)).resize((512, 512))

    gt2 = gt[:, :, z].astype(bool)
    pred2 = pred[:, :, z].astype(bool)
    masks = {
        "expert_gt": (gt2, (0, 158, 115, 130)),
        "ai_prediction": (pred2, (0, 114, 178, 125)),
        "overlap": (gt2 & pred2, (240, 228, 66, 225)),
        "missed_expert_lesion": (gt2 & ~pred2, (213, 94, 0, 235)),
        "false_positive_prediction": (pred2 & ~gt2, (230, 159, 0, 235)),
    }

    paths = {"base": out_dir / "base_slice.png"}
    base_img.save(paths["base"])
    for name, (mask, rgba) in masks.items():
        layer = np.zeros((*mask.shape, 4), dtype=np.uint8)
        layer[mask] = rgba
        layer_img = Image.fromarray(layer, mode="RGBA").resize((512, 512))
        paths[name] = out_dir / f"{name}.png"
        layer_img.save(paths[name])
    return paths

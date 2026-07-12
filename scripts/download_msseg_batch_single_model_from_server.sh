#!/usr/bin/env bash
set -euo pipefail

# Read-only MSSEG batch downloader.
# Runs on your Mac. It does not create, delete, rename, or modify anything on the server.
#
# Output layout:
#   raw_mris/       one MRI per case, FLAIR preferred
#   gts/            one expert/GT mask per case
#   predictions/    one prediction mask per case from ONE selected model

SERVER="${SERVER:-mm13924@10.224.32.202}"
MODEL_FILTER="${MODEL_FILTER:-nnUNet}"
MAX_CASES="${MAX_CASES:-12}"          # use MAX_CASES=all for every matched case
MODALITY_FILTER="${MODALITY_FILTER:-FLAIR}"
DEST="${DEST:-$HOME/Downloads/neurotrust_msseg_batch_${MODEL_FILTER}_$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$DEST"

echo "Server: $SERVER"
echo "Destination: $DEST"
echo "Model filter: $MODEL_FILTER"
echo "Max cases: $MAX_CASES"
echo "MRI modality preference: $MODALITY_FILTER"
echo

REMOTE_MODEL_ARG="$(printf '%q' "$MODEL_FILTER")"
REMOTE_MAX_ARG="$(printf '%q' "$MAX_CASES")"
REMOTE_MODALITY_ARG="$(printf '%q' "$MODALITY_FILTER")"

ssh "$SERVER" "python3 - $REMOTE_MODEL_ARG $REMOTE_MAX_ARG $REMOTE_MODALITY_ARG" > "$DEST/manifest.json" <<'PY'
from pathlib import Path
import csv
import json
import re
import sys

model_filter = sys.argv[1].strip()
max_cases_arg = sys.argv[2].strip().lower()
modality_filter = sys.argv[3].strip().lower()

raw_candidates = [
    Path("/home/mm13924/nnUNet_raw/Dataset901_MSSEG_CLEAN"),
    Path("/data/mm13924/ms3mod_1000epoch_training_20260708_100437/data/nnUNet_raw/Dataset972_MSSEG_3MOD"),
]

prediction_roots = [
    Path("/data/mm13924/model_c_100epoch_eval1to7/latest"),
    Path("/data/mm13924/augmentation_experiments/nnunet_torchio_msseg/clean_run_20260702_150649"),
    Path("/data/mm13924/model_c_100epoch_lesion_aware"),
    Path("/data/mm13924/ms3mod_1000epoch_training_20260708_100437/results"),
]

def strip_nii(name):
    if name.endswith(".nii.gz"):
        return name[:-7]
    return Path(name).stem

def load_channels(dataset_json):
    if not dataset_json.is_file():
        return {}
    try:
        ds = json.loads(dataset_json.read_text())
        return ds.get("channel_names") or ds.get("modality") or {}
    except Exception:
        return {}

raw = next((p for p in raw_candidates if p.is_dir()), None)
if raw is None:
    print(json.dumps({
        "error": "MSSEG nnUNet_raw dataset not found",
        "checked_raw_roots": [str(p) for p in raw_candidates],
    }, indent=2))
    sys.exit(0)

dataset_json = raw / "dataset.json"
channels = load_channels(dataset_json)

def modality_name(index):
    try:
        idx_int = int(index)
        return str(channels.get(str(idx_int), channels.get(idx_int, f"channel_{index}")))
    except Exception:
        return f"channel_{index}"

def all_labels():
    labels = []
    for split in ("labelsTs", "labelsTr"):
        d = raw / split
        if d.is_dir():
            labels.extend(sorted(d.glob("*.nii.gz")))
    return labels

def images_for(case_id):
    images = []
    for split in ("imagesTs", "imagesTr"):
        d = raw / split
        if not d.is_dir():
            continue
        for p in sorted(d.glob(f"{case_id}_*.nii.gz")):
            idx = p.name.replace(".nii.gz", "").split("_")[-1]
            images.append({
                "path": str(p),
                "split": split,
                "modality_index": idx,
                "modality_name": modality_name(idx),
            })
    return images

def select_image(images):
    if not images:
        return None
    preferred = [
        x for x in images
        if modality_filter and modality_filter in str(x["modality_name"]).lower()
    ]
    if preferred:
        return preferred[0]
    flair = [x for x in images if "flair" in str(x["modality_name"]).lower()]
    if flair:
        return flair[0]
    channel_2 = [x for x in images if x["modality_index"] in ("0002", "2")]
    if channel_2:
        return channel_2[0]
    return images[0]

def gt_for(case_id):
    for split in ("labelsTs", "labelsTr"):
        p = raw / split / f"{case_id}.nii.gz"
        if p.is_file():
            return str(p)
    return None

def model_guess(path):
    s = str(path).lower()
    if "segresnet" in s:
        return "SegResNet"
    if "swinunetr" in s:
        return "SwinUNETR"
    if "modelc" in s or "model_c" in s:
        return "ModelC"
    if "torchio" in s:
        return "TorchIO"
    if "nnunet" in s:
        return "nnUNet"
    return path.parent.name

def is_prediction_path(path):
    s = str(path).lower()
    blocked = [
        "/nnunet_raw/",
        "/nnunet_preprocessed/",
        "/imagestr/",
        "/imagests/",
        "/labelstr/",
        "/labelsts/",
        "/labels/",
        "/gt/",
        "ground_truth",
        "reference",
        "expert",
    ]
    if any(x in s for x in blocked):
        return False
    if re.search(r"_000[0-9]\.nii\.gz$", path.name):
        return False
    return path.name.endswith(".nii.gz")

def model_matches(pred_item):
    needle = model_filter.lower()
    if needle in ("", "auto", "any"):
        return True
    return needle in pred_item["model"].lower() or needle in pred_item["path"].lower()

def prediction_candidates_for(case_id):
    found = []
    for root in prediction_roots:
        if not root.is_dir():
            continue
        try:
            for p in root.rglob(f"*{case_id}*.nii.gz"):
                if is_prediction_path(p):
                    found.append({
                        "path": str(p),
                        "model": model_guess(p),
                        "root": str(root),
                    })
        except Exception:
            pass
    uniq = {}
    for item in found:
        uniq[item["path"]] = item
    return sorted(uniq.values(), key=lambda x: (x["model"], x["path"]))

case_ids = [strip_nii(p.name) for p in all_labels()]
records = []
available_model_counts = {}

for case_id in case_ids:
    images = images_for(case_id)
    image = select_image(images)
    gt = gt_for(case_id)
    candidates = prediction_candidates_for(case_id)
    for c in candidates:
        available_model_counts[c["model"]] = available_model_counts.get(c["model"], 0) + 1
    selected_candidates = [c for c in candidates if model_matches(c)]
    if image and gt and selected_candidates:
        pred = selected_candidates[0]
        records.append({
            "case_id": case_id,
            "raw_mri": image,
            "ground_truth": gt,
            "prediction": pred,
            "all_prediction_count_for_case": len(candidates),
            "selected_model_prediction_count_for_case": len(selected_candidates),
        })

if max_cases_arg not in ("all", "0", "none"):
    try:
        max_cases = int(max_cases_arg)
        if max_cases > 0:
            records = records[:max_cases]
    except ValueError:
        pass

if not records:
    print(json.dumps({
        "error": "No matched cases found for requested single-model batch",
        "dataset_root": str(raw),
        "model_filter": model_filter,
        "modality_filter": modality_filter,
        "checked_prediction_roots": [str(p) for p in prediction_roots],
        "available_model_counts": available_model_counts,
        "case_examples": case_ids[:20],
    }, indent=2))
    sys.exit(0)

manifest = {
    "dataset": "MSSEG",
    "dataset_root": str(raw),
    "dataset_json": str(dataset_json) if dataset_json.is_file() else None,
    "model_filter": model_filter,
    "modality_filter": modality_filter,
    "max_cases_requested": max_cases_arg,
    "matched_case_count": len(records),
    "available_model_counts_seen_during_scan": available_model_counts,
    "records": records,
}

print(json.dumps(manifest, indent=2))
PY

python3 - "$DEST/manifest.json" <<'PY' > "$DEST/files_from_server.txt"
import json
import sys

m = json.load(open(sys.argv[1]))
if "error" in m:
    print(json.dumps(m, indent=2), file=sys.stderr)
    sys.exit(1)

paths = []
if m.get("dataset_json"):
    paths.append(m["dataset_json"])
for record in m["records"]:
    paths.append(record["raw_mri"]["path"])
    paths.append(record["ground_truth"])
    paths.append(record["prediction"]["path"])

seen = set()
for path in paths:
    if path and path not in seen:
        seen.add(path)
        print(path.lstrip("/"))
PY

echo "Downloading batch files..."
rsync -avhP --partial \
  --files-from="$DEST/files_from_server.txt" \
  "$SERVER:/" \
  "$DEST/_server_paths/"

python3 - "$DEST" <<'PY'
from pathlib import Path
import csv
import json
import re
import shutil
import sys

dest = Path(sys.argv[1])
manifest = json.load(open(dest / "manifest.json"))
server_paths = dest / "_server_paths"

raw_dir = dest / "raw_mris"
gt_dir = dest / "gts"
pred_dir = dest / "predictions"
for d in (raw_dir, gt_dir, pred_dir):
    d.mkdir(parents=True, exist_ok=True)

def local_path(remote):
    return server_paths / remote.lstrip("/")

def safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))

def copy(remote, target):
    shutil.copy2(local_path(remote), target)
    return target

rows = []
for record in manifest["records"]:
    case_id = safe(record["case_id"])
    raw_target = copy(record["raw_mri"]["path"], raw_dir / f"{case_id}.nii.gz")
    gt_target = copy(record["ground_truth"], gt_dir / f"{case_id}.nii.gz")
    pred_target = copy(record["prediction"]["path"], pred_dir / f"{case_id}.nii.gz")
    rows.append({
        "case_id": case_id,
        "raw_mri": str(raw_target),
        "ground_truth": str(gt_target),
        "prediction": str(pred_target),
        "selected_model": record["prediction"]["model"],
        "selected_prediction_source": record["prediction"]["path"],
        "raw_mri_source": record["raw_mri"]["path"],
        "gt_source": record["ground_truth"],
        "raw_modality_name": record["raw_mri"]["modality_name"],
        "raw_modality_index": record["raw_mri"]["modality_index"],
    })

if manifest.get("dataset_json"):
    copy(manifest["dataset_json"], dest / "dataset.json")

with open(dest / "case_manifest.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

readme = [
    "NeuroTrust-MS MSSEG batch demo",
    "",
    "This folder has three matched folders:",
    "- raw_mris/       one selected MRI image per case",
    "- gts/            one expert ground-truth lesion mask per case",
    "- predictions/    one prediction mask per case from one selected model",
    "",
    f"Dataset: {manifest.get('dataset')}",
    f"Requested model filter: {manifest.get('model_filter')}",
    f"Requested modality preference: {manifest.get('modality_filter')}",
    f"Matched cases: {manifest.get('matched_case_count')}",
    "",
    "How to use now:",
    "For a case named CASE.nii.gz, upload:",
    "- raw_mris/CASE.nii.gz as MRI image",
    "- gts/CASE.nii.gz as expert/ground-truth mask",
    "- predictions/CASE.nii.gz as AI prediction mask",
    "",
    "See case_manifest.csv for exact case-to-file mapping.",
]
(dest / "README_BATCH_UPLOAD.txt").write_text("\n".join(readme) + "\n")

if not bool(int(__import__("os").environ.get("KEEP_SERVER_PATHS", "0"))):
    shutil.rmtree(server_paths, ignore_errors=True)

print("\n".join(readme))
PY

find "$DEST/raw_mris" "$DEST/gts" "$DEST/predictions" \
  -type f -name "*.nii.gz" -print0 | xargs -0 shasum -a 256 > "$DEST/checksums_sha256.txt"

echo
echo "DONE. Batch demo folder:"
echo "$DEST"
echo
echo "Folder counts:"
find "$DEST/raw_mris" -type f -name "*.nii.gz" | wc -l | awk '{print "raw_mris: " $1}'
find "$DEST/gts" -type f -name "*.nii.gz" | wc -l | awk '{print "gts: " $1}'
find "$DEST/predictions" -type f -name "*.nii.gz" | wc -l | awk '{print "predictions: " $1}'
echo
echo "Open folder:"
echo "open \"$DEST\""

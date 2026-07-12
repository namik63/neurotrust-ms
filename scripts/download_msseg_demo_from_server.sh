#!/usr/bin/env bash
set -euo pipefail

# Read-only MSSEG demo downloader.
# Runs from your Mac. It does not create, delete, or modify anything on the server.

SERVER="${SERVER:-mm13924@10.224.32.202}"
CASE_ID="${CASE_ID:-}"
DEST="${DEST:-$HOME/Downloads/neurotrust_msseg_demo_validation_$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$DEST"

echo "Server: $SERVER"
echo "Destination: $DEST"
if [ -n "$CASE_ID" ]; then
  echo "Requested case: $CASE_ID"
else
  echo "Requested case: auto-select first usable case"
fi
echo

REMOTE_CASE_ARG="$(printf '%q' "$CASE_ID")"
ssh "$SERVER" "python3 - $REMOTE_CASE_ARG" > "$DEST/manifest.json" <<'PY'
from pathlib import Path
import json
import re
import sys

requested = sys.argv[1].strip()

raw_candidates = [
    Path("/home/mm13924/nnUNet_raw/Dataset901_MSSEG_CLEAN"),
    Path("/data/mm13924/ms3mod_1000epoch_training_20260708_100437/data/nnUNet_raw/Dataset972_MSSEG_3MOD"),
]

pred_roots = [
    Path("/data/mm13924/model_c_100epoch_eval1to7/latest"),
    Path("/data/mm13924/augmentation_experiments/nnunet_torchio_msseg/clean_run_20260702_150649"),
    Path("/data/mm13924/model_c_100epoch_lesion_aware"),
    Path("/data/mm13924/ms3mod_1000epoch_training_20260708_100437/results"),
]

raw = next((p for p in raw_candidates if p.is_dir()), None)
if raw is None:
    print(json.dumps({
        "error": "MSSEG nnUNet_raw dataset not found",
        "checked": [str(p) for p in raw_candidates],
    }, indent=2))
    sys.exit(0)

dataset_json = raw / "dataset.json"
channels = {}
if dataset_json.is_file():
    try:
        ds = json.loads(dataset_json.read_text())
        channels = ds.get("channel_names") or ds.get("modality") or {}
    except Exception:
        channels = {}

def strip_nii(name):
    if name.endswith(".nii.gz"):
        return name[:-7]
    return Path(name).stem

labels = []
for split in ("labelsTs", "labelsTr"):
    d = raw / split
    if d.is_dir():
        labels += sorted(d.glob("*.nii.gz"))

case_ids = [strip_nii(p.name) for p in labels]
if requested:
    case_ids = [requested]

def modality_name(index):
    try:
        idx_int = int(index)
        return str(channels.get(str(idx_int), channels.get(idx_int, f"channel_{index}")))
    except Exception:
        return f"channel_{index}"

def images_for(case):
    out = []
    for split in ("imagesTs", "imagesTr"):
        d = raw / split
        if not d.is_dir():
            continue
        for p in sorted(d.glob(f"{case}_*.nii.gz")):
            idx = p.name.replace(".nii.gz", "").split("_")[-1]
            out.append({
                "path": str(p),
                "split": split,
                "modality_index": idx,
                "modality_name": modality_name(idx),
            })
    return out

def gt_for(case):
    for split in ("labelsTs", "labelsTr"):
        p = raw / split / f"{case}.nii.gz"
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

def is_prediction_path(p):
    s = str(p).lower()
    bad_parts = [
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
    if any(x in s for x in bad_parts):
        return False
    if re.search(r"_000[0-9]\.nii\.gz$", p.name):
        return False
    return p.name.endswith(".nii.gz")

def preds_for(case):
    found = []
    for root in pred_roots:
        if not root.is_dir():
            continue
        try:
            for p in root.rglob(f"*{case}*.nii.gz"):
                if is_prediction_path(p):
                    found.append({"path": str(p), "model": model_guess(p)})
        except Exception:
            pass
    uniq = {}
    for item in found:
        uniq[item["path"]] = item
    return sorted(uniq.values(), key=lambda x: (x["model"], x["path"]))[:12]

selected = None
for case in case_ids:
    imgs = images_for(case)
    gt = gt_for(case)
    preds = preds_for(case)
    if imgs and gt and preds:
        selected = {
            "case_id": case,
            "dataset_root": str(raw),
            "dataset_json": str(dataset_json) if dataset_json.is_file() else None,
            "images": imgs,
            "ground_truth": gt,
            "predictions": preds,
        }
        break

if selected is None:
    print(json.dumps({
        "error": "No case found with image + GT + matching prediction",
        "dataset_root": str(raw),
        "requested_case": requested,
        "checked_prediction_roots": [str(p) for p in pred_roots],
        "available_case_examples": case_ids[:20],
    }, indent=2))
else:
    print(json.dumps(selected, indent=2))
PY

python3 - "$DEST/manifest.json" <<'PY' > "$DEST/files_from_server.txt"
import json
import sys

manifest_path = sys.argv[1]
m = json.load(open(manifest_path))
if "error" in m:
    print(json.dumps(m, indent=2), file=sys.stderr)
    sys.exit(1)

paths = []
if m.get("dataset_json"):
    paths.append(m["dataset_json"])
paths.append(m["ground_truth"])
paths += [x["path"] for x in m["images"]]
paths += [x["path"] for x in m["predictions"]]

seen = set()
for p in paths:
    if p and p not in seen:
        seen.add(p)
        print(p.lstrip("/"))
PY

echo "Downloading selected files..."
rsync -avhP --partial \
  --files-from="$DEST/files_from_server.txt" \
  "$SERVER:/" \
  "$DEST/server_paths/"

python3 - "$DEST" <<'PY'
from pathlib import Path
import json
import re
import shutil
import sys

dest = Path(sys.argv[1])
m = json.load(open(dest / "manifest.json"))
base = dest / "server_paths"
case = m["case_id"]

def safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))

def local(remote):
    return base / remote.lstrip("/")

def copy(remote, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local(remote), target)
    return target

if m.get("dataset_json"):
    copy(m["dataset_json"], dest / "dataset.json")

for img in m["images"]:
    name = f"{case}_{img['modality_index']}_{safe(img['modality_name'])}.nii.gz"
    copy(img["path"], dest / "actual_mri" / name)

flair = next((x for x in m["images"] if "flair" in x["modality_name"].lower()), None)
if flair is None:
    flair = next((x for x in m["images"] if x["modality_index"] in ("0002", "2")), m["images"][0])

upload_img = copy(flair["path"], dest / f"UPLOAD_1_image_{safe(flair['modality_name'])}.nii.gz")
upload_gt = copy(m["ground_truth"], dest / "UPLOAD_2_ground_truth.nii.gz")

pred_targets = []
for i, pred in enumerate(m["predictions"], 1):
    target = dest / "predictions" / f"{i:02d}_{safe(pred['model'])}_{case}_prediction.nii.gz"
    pred_targets.append(copy(pred["path"], target))

upload_pred = copy(m["predictions"][0]["path"], dest / f"UPLOAD_3_prediction_{safe(m['predictions'][0]['model'])}.nii.gz")

lines = [
    "MSSEG demo validation download",
    "",
    f"Case: {case}",
    "",
    "Upload these into NeuroTrust-MS:",
    "1. MRI image:",
    f"   {upload_img}",
    "",
    "2. Expert / ground-truth lesion mask:",
    f"   {upload_gt}",
    "",
    "3. AI prediction mask:",
    f"   {upload_pred}",
    "",
    "Other downloaded predictions:",
]
lines.extend(f"- {p}" for p in pred_targets)
lines.extend([
    "",
    "All original downloaded files are preserved under:",
    "server_paths/",
    "",
    "Manifest:",
    "manifest.json",
])

readme = "\n".join(lines) + "\n"
(dest / "README_UPLOAD_ORDER.txt").write_text(readme)
print(readme)
PY

shasum -a 256 "$DEST"/UPLOAD_*.nii.gz "$DEST"/predictions/*.nii.gz > "$DEST/checksums_sha256.txt"

echo
echo "DONE. Demo files downloaded here:"
echo "$DEST"
echo
echo "Open this instruction file:"
echo "$DEST/README_UPLOAD_ORDER.txt"
echo
find "$DEST" -maxdepth 2 -type f | sort

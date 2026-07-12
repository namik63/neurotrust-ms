#!/usr/bin/env bash
set -euo pipefail

# Read-only FreeSurfer/anatomy-mask downloader for an already-downloaded NeuroTrust batch.
# Runs on your Mac. It only searches and downloads from the server.
# It does NOT run recon-all, regenerate FreeSurfer, modify server files, or write anything on the server.

SERVER="${SERVER:-mm13924@10.224.32.202}"
BATCH_DIR="${BATCH_DIR:-}"
DEST="${DEST:-}"
MAX_PER_CASE="${MAX_PER_CASE:-10}"
INCLUDE_MGZ="${INCLUDE_MGZ:-1}"
KEEP_SERVER_PATHS="${KEEP_SERVER_PATHS:-0}"

if [ -z "$BATCH_DIR" ]; then
  BATCH_DIR="$(find "$HOME/Downloads" -maxdepth 1 -type d -name 'neurotrust_msseg_batch_*' | sort | tail -n 1)"
fi

if [ -z "$BATCH_DIR" ] || [ ! -d "$BATCH_DIR" ]; then
  echo "ERROR: No NeuroTrust batch folder found."
  echo "Set BATCH_DIR explicitly, for example:"
  echo 'BATCH_DIR="$HOME/Downloads/neurotrust_msseg_batch_nnUNet_YYYYMMDD_HHMMSS" ./scripts/download_freesurfer_masks_for_batch_from_server.sh'
  exit 1
fi

if [ -z "$DEST" ]; then
  DEST="$BATCH_DIR/freesurfer_masks_download_$(date +%Y%m%d_%H%M%S)"
fi

mkdir -p "$DEST/state" "$DEST/freesurfer_masks"

echo "Server: $SERVER"
echo "Batch folder: $BATCH_DIR"
echo "Destination: $DEST"
echo "Max masks per case: $MAX_PER_CASE"
echo "Include .mgz fallback: $INCLUDE_MGZ"
echo

python3 - "$BATCH_DIR" > "$DEST/state/case_ids.json" <<'PY'
from pathlib import Path
import csv
import json
import sys

batch = Path(sys.argv[1]).expanduser()
case_ids = []

manifest = batch / "case_manifest.csv"
if manifest.is_file():
    with open(manifest, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = (row.get("case_id") or "").strip()
            if cid:
                case_ids.append(cid)

if not case_ids:
    raw = batch / "raw_mris"
    if raw.is_dir():
        for p in sorted(raw.glob("*.nii*")):
            name = p.name
            if name.endswith(".nii.gz"):
                case_ids.append(name[:-7])
            elif name.endswith(".nii"):
                case_ids.append(name[:-4])

case_ids = sorted(dict.fromkeys(case_ids))
if not case_ids:
    raise SystemExit("No case IDs found from case_manifest.csv or raw_mris/*.nii*")

print(json.dumps(case_ids))
PY

CASE_JSON_B64="$(base64 < "$DEST/state/case_ids.json" | tr -d '\n')"
REMOTE_CASES_ARG="$(printf '%q' "$CASE_JSON_B64")"
REMOTE_MAX_ARG="$(printf '%q' "$MAX_PER_CASE")"
REMOTE_MGZ_ARG="$(printf '%q' "$INCLUDE_MGZ")"

echo "Searching server read-only for matching FreeSurfer/anatomy masks..."
ssh "$SERVER" "python3 - $REMOTE_CASES_ARG $REMOTE_MAX_ARG $REMOTE_MGZ_ARG" > "$DEST/state/freesurfer_remote_manifest.json" <<'PY'
from pathlib import Path
import base64
import json
import subprocess
import sys

case_ids = json.loads(base64.b64decode(sys.argv[1]).decode())
max_per_case = int(sys.argv[2])
include_mgz = sys.argv[3] == "1"

search_roots = [
    Path("/home/mm13924/freesurfer_subjects"),
    Path("/home/mm13924/msseg_rebuild/freesurfer_subjects_eval24"),
    Path("/home/mm13924/msseg_rebuild/internal_validation_mslesseg_dataset924_full_1to7/freesurfer_subjects_mslesseg_fold0val_clean4"),
    Path("/data/mm13924"),
]

subject_roots = [
    Path("/home/mm13924/freesurfer_subjects"),
    Path("/home/mm13924/msseg_rebuild/freesurfer_subjects_eval24"),
    Path("/home/mm13924/msseg_rebuild/internal_validation_mslesseg_dataset924_full_1to7/freesurfer_subjects_mslesseg_fold0val_clean4"),
]

mask_terms = [
    "freesurfer",
    "aparc",
    "aseg",
    "wmparc",
    "ribbon",
    "brainmask",
    "brain_mask",
    "parcell",
    "parcel",
    "atlas",
    "anat",
    "anatom",
    "label",
    "region",
    "lobar",
    "cortical",
    "subcortical",
    "lesiongrid",
    "lesion_grid",
    "registered",
    "resampled",
]

skip_terms = [
    "/.cache/",
    "/envs/",
    "/conda_envs/",
    "/node_modules/",
    "/tmp/",
    "/tmp_",
    "/__pycache__/",
]

def allowed_extension(path):
    s = path.name.lower()
    if s.endswith(".nii") or s.endswith(".nii.gz"):
        return True
    if include_mgz and s.endswith(".mgz"):
        return True
    return False

def looks_like_mask(path):
    s = str(path).lower()
    if any(x in s for x in skip_terms):
        return False
    if not allowed_extension(path):
        return False
    return any(term in s for term in mask_terms)

def priority(path):
    s = str(path).lower()
    ext_score = 0 if s.endswith(".nii.gz") else 1 if s.endswith(".nii") else 2
    grid_score = 0 if any(x in s for x in ["lesiongrid", "lesion_grid", "registered", "resampled", "nnunet"]) else 1
    kind_score = 0
    if "aparc" in s and "aseg" in s:
        kind_score = 0
    elif "aseg" in s:
        kind_score = 1
    elif "wmparc" in s:
        kind_score = 2
    elif "brainmask" in s or "brain_mask" in s:
        kind_score = 3
    else:
        kind_score = 4
    return (ext_score, grid_score, kind_score, len(str(path)), str(path))

def case_aliases(case_id):
    aliases = [case_id]
    import re
    m = re.search(r"(\d+)$", case_id)
    if m:
        raw = m.group(1)
        n3 = raw.zfill(3)
        aliases.extend([
            "eval_" + n3,
            "subject_" + n3,
            raw,
            str(int(raw)),
        ])
    out = []
    seen = set()
    for item in aliases:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

def find_case(case_id):
    raw_matches = []
    aliases = case_aliases(case_id)
    for root in search_roots:
        if not root.is_dir():
            continue
        for alias in aliases:
            # Read-only search. The pattern is intentionally case-scoped.
            cmd = [
                "find",
                str(root),
                "-type",
                "f",
                "(",
                "-iname", f"*{alias}*.nii.gz",
                "-o", "-iname", f"*{alias}*.nii",
            ]
            if include_mgz:
                cmd += ["-o", "-iname", f"*{alias}*.mgz"]
            cmd += [")"]
            try:
                proc = subprocess.run(cmd, text=True, capture_output=True, timeout=240)
            except subprocess.TimeoutExpired:
                raw_matches.append({
                    "path": None,
                    "note": f"search timed out under {root}",
                })
                continue
            for line in proc.stdout.splitlines():
                p = Path(line.strip())
                if looks_like_mask(p):
                    raw_matches.append({"path": str(p), "note": f"matched by alias {alias}"})

    # FreeSurfer native files often live inside subject directories and do not include
    # the subject ID in the filename, e.g. subject_001/mri/aparc+aseg.mgz.
    if include_mgz:
        for root in subject_roots:
            if not root.is_dir():
                continue
            for alias in aliases:
                fs_subject = root / alias
                if fs_subject.is_dir():
                    native_candidates = [
                        fs_subject / "mri" / "aparc+aseg.mgz",
                        fs_subject / "mri" / "aseg.mgz",
                        fs_subject / "mri" / "wmparc.mgz",
                        fs_subject / "mri" / "ribbon.mgz",
                        fs_subject / "mri" / "brainmask.mgz",
                    ]
                    for p in native_candidates:
                        if p.is_file():
                            raw_matches.append({"path": str(p), "note": f"native FreeSurfer mgz from subject {alias}; may need conversion/alignment before NeuroTrust use"})

    unique = {}
    notes = []
    for item in raw_matches:
        if item.get("path"):
            unique[item["path"]] = item
        elif item.get("note"):
            notes.append(item["note"])

    matches = sorted(unique.values(), key=lambda item: priority(Path(item["path"])))
    return matches[:max_per_case], notes

records = []
for case_id in case_ids:
    matches, notes = find_case(case_id)
    records.append({
        "case_id": case_id,
        "case_aliases": case_aliases(case_id),
        "match_count": len(matches),
        "matches": matches,
        "notes": notes,
    })

print(json.dumps({
    "case_count": len(case_ids),
    "include_mgz": include_mgz,
    "max_per_case": max_per_case,
    "search_roots": [str(p) for p in search_roots],
    "records": records,
}, indent=2))
PY

python3 - "$DEST/state/freesurfer_remote_manifest.json" > "$DEST/state/files_from_server.txt" <<'PY'
import json
import sys

m = json.load(open(sys.argv[1]))
seen = set()
for record in m.get("records", []):
    for match in record.get("matches", []):
        p = match.get("path")
        if p and p not in seen:
            seen.add(p)
            print(p.lstrip("/"))
PY

COUNT="$(wc -l < "$DEST/state/files_from_server.txt" | tr -d ' ')"
if [ "$COUNT" = "0" ]; then
  echo "No FreeSurfer/anatomy masks were found for the batch case IDs."
  echo "Manifest written to:"
  echo "$DEST/state/freesurfer_remote_manifest.json"
  echo
  echo "If FreeSurfer masks live in a different server folder, paste the manifest here and I will adjust the search roots."
  exit 0
fi

echo "Downloading $COUNT mask file(s)..."
rsync -avhP --partial \
  --files-from="$DEST/state/files_from_server.txt" \
  "$SERVER:/" \
  "$DEST/_server_paths/"

python3 - "$DEST" "$KEEP_SERVER_PATHS" <<'PY'
from pathlib import Path
import csv
import json
import re
import shutil
import sys

dest = Path(sys.argv[1])
keep_server_paths = sys.argv[2] == "1"
server_paths = dest / "_server_paths"
manifest = json.load(open(dest / "state/freesurfer_remote_manifest.json"))

def safe(value):
    return re.sub(r"[^A-Za-z0-9_.+-]+", "_", str(value))

def local_path(remote):
    return server_paths / remote.lstrip("/")

def kind(path):
    s = path.lower()
    if "aparc" in s and "aseg" in s:
        return "aparc_aseg"
    if "aseg" in s:
        return "aseg"
    if "wmparc" in s:
        return "wmparc"
    if "ribbon" in s:
        return "ribbon"
    if "brainmask" in s or "brain_mask" in s:
        return "brainmask"
    if "atlas" in s:
        return "atlas"
    if "label" in s:
        return "label"
    return "freesurfer_mask"

rows = []
for record in manifest.get("records", []):
    case_id = safe(record["case_id"])
    case_dir = dest / "freesurfer_masks" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    for i, match in enumerate(record.get("matches", []), 1):
        remote = match["path"]
        src = local_path(remote)
        suffix = ".nii.gz" if remote.endswith(".nii.gz") else ".nii" if remote.endswith(".nii") else ".mgz"
        target = case_dir / f"{case_id}_{i:02d}_{kind(remote)}{suffix}"
        shutil.copy2(src, target)
        rows.append({
            "case_id": case_id,
            "mask_kind": kind(remote),
            "local_path": str(target),
            "source_path": remote,
            "note": match.get("note", ""),
        })

with open(dest / "freesurfer_mask_manifest.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["case_id", "mask_kind", "local_path", "source_path", "note"])
    writer.writeheader()
    writer.writerows(rows)

readme = [
    "FreeSurfer/anatomy masks downloaded for NeuroTrust validation batch",
    "",
    "Important:",
    "- These files were downloaded read-only from the server.",
    "- No FreeSurfer outputs were regenerated.",
    "- NeuroTrust currently validates MRI + GT + prediction masks; these anatomy masks are downloaded for future anatomy-aware validation/QC.",
    "- Native .mgz files, if included, may require conversion/alignment before direct NeuroTrust use.",
    "",
    "Folder layout:",
    "freesurfer_masks/",
    "  CASE_ID/",
    "    CASE_ID_01_aparc_aseg.nii.gz",
    "    CASE_ID_02_aseg.nii.gz",
    "",
    "Manifest:",
    "freesurfer_mask_manifest.csv",
    "state/freesurfer_remote_manifest.json",
]
(dest / "README_FREESURFER_MASKS.txt").write_text("\n".join(readme) + "\n")

if not keep_server_paths:
    shutil.rmtree(server_paths, ignore_errors=True)

print("\n".join(readme))
PY

find "$DEST/freesurfer_masks" -type f \( -name "*.nii" -o -name "*.nii.gz" -o -name "*.mgz" \) -print0 \
  | xargs -0 shasum -a 256 > "$DEST/checksums_sha256.txt"

echo
echo "DONE. FreeSurfer mask download folder:"
echo "$DEST"
echo
echo "Counts:"
find "$DEST/freesurfer_masks" -type f \( -name "*.nii" -o -name "*.nii.gz" -o -name "*.mgz" \) | wc -l | awk '{print "mask files: " $1}'
find "$DEST/freesurfer_masks" -mindepth 1 -maxdepth 1 -type d | wc -l | awk '{print "cases with folders: " $1}'
echo
echo "Open folder:"
echo "open \"$DEST\""

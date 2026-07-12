#!/usr/bin/env bash
set -euo pipefail

# Read-only FreeSurfer audit for a NeuroTrust validation batch.
# Runs on your Mac. It does not write to the server and does not run recon-all.

SERVER="${SERVER:-mm13924@10.224.32.202}"
BATCH_DIR="${BATCH_DIR:-}"
DEST="${DEST:-}"

if [ -z "$BATCH_DIR" ]; then
  BATCH_DIR="$(find "$HOME/Downloads" -maxdepth 1 -type d -name 'neurotrust_msseg_batch_*' | sort | tail -n 1)"
fi

if [ -z "$BATCH_DIR" ] || [ ! -d "$BATCH_DIR" ]; then
  echo "ERROR: No NeuroTrust batch folder found."
  echo "Set BATCH_DIR explicitly, for example:"
  echo 'BATCH_DIR="$HOME/Downloads/neurotrust_msseg_batch_nnUNet_YYYYMMDD_HHMMSS" ./scripts/audit_freesurfer_on_server_for_batch.sh'
  exit 1
fi

if [ -z "$DEST" ]; then
  DEST="$BATCH_DIR/freesurfer_server_audit_$(date +%Y%m%d_%H%M%S)"
fi

mkdir -p "$DEST"

echo "Server: $SERVER"
echo "Batch folder: $BATCH_DIR"
echo "Audit output: $DEST"
echo

python3 - "$BATCH_DIR" > "$DEST/case_ids.json" <<'PY'
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

CASE_JSON_B64="$(base64 < "$DEST/case_ids.json" | tr -d '\n')"
REMOTE_CASES_ARG="$(printf '%q' "$CASE_JSON_B64")"

echo "Running read-only FreeSurfer audit on server..."
ssh "$SERVER" "python3 - $REMOTE_CASES_ARG" > "$DEST/freesurfer_audit.json" <<'PY'
from pathlib import Path
import base64
import datetime
import getpass
import json
import os
import re
import socket
import subprocess
import sys

case_ids = json.loads(base64.b64decode(sys.argv[1]).decode())

def run(cmd, timeout=60):
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        out, err = proc.communicate(timeout=timeout)
        return {
            "cmd": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout": out.splitlines(),
            "stderr": err.splitlines(),
        }
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        return {
            "cmd": " ".join(cmd),
            "returncode": None,
            "stdout": [],
            "stderr": ["TIMEOUT"],
        }
    except Exception as exc:
        return {
            "cmd": " ".join(cmd),
            "returncode": None,
            "stdout": [],
            "stderr": [repr(exc)],
        }

def norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())

def digits(value):
    found = re.findall(r"\d+", str(value))
    return found[-1].lstrip("0") if found else ""

def looks_like_subject_dir(path):
    p = Path(path)
    return (p / "mri").is_dir() or (p / "scripts" / "recon-all.log").is_file()

def file_info(path):
    p = Path(path)
    try:
        stat = p.stat()
        return {"path": str(p), "size": stat.st_size}
    except Exception:
        return {"path": str(p), "size": None}

def subject_summary(subject_dir):
    p = Path(subject_dir)
    mri = p / "mri"
    key_files = [
        mri / "aparc+aseg.mgz",
        mri / "aseg.mgz",
        mri / "wmparc.mgz",
        mri / "ribbon.mgz",
        mri / "brainmask.mgz",
        mri / "T1.mgz",
        p / "scripts" / "recon-all.log",
    ]
    existing = [file_info(x) for x in key_files if x.is_file()]
    converted = []
    try:
        for x in p.rglob("*"):
            if not x.is_file():
                continue
            s = x.name.lower()
            if (s.endswith(".nii") or s.endswith(".nii.gz")) and any(t in s for t in ["aparc", "aseg", "wmparc", "brainmask", "ribbon", "atlas", "label"]):
                converted.append(file_info(x))
                if len(converted) >= 25:
                    break
    except Exception:
        pass
    return {
        "subject": p.name,
        "path": str(p),
        "key_native_files": existing,
        "converted_nifti_like_files": converted,
    }

fixed_subject_roots = [
    Path("/home/mm13924/freesurfer_subjects"),
    Path("/data/mm13924/freesurfer_subjects"),
    Path("/data/mm13924/FreeSurfer"),
    Path("/data/mm13924/freesurfer"),
]

dir_searches = [
    run(["find", "/home/mm13924", "-maxdepth", "4", "-type", "d", "-iname", "*freesurfer*"], timeout=90),
    run(["find", "/data/mm13924", "-maxdepth", "5", "-type", "d", "-iname", "*freesurfer*"], timeout=180),
]

candidate_roots = []
for p in fixed_subject_roots:
    if p.is_dir():
        candidate_roots.append(p)
for search in dir_searches:
    for line in search.get("stdout", []):
        p = Path(line)
        if p.is_dir():
            candidate_roots.append(p)

unique_roots = []
seen_roots = set()
for root in candidate_roots:
    s = str(root)
    if s not in seen_roots:
        unique_roots.append(root)
        seen_roots.add(s)

subject_dirs = []
for root in unique_roots:
    try:
        for child in root.iterdir():
            if child.is_dir() and looks_like_subject_dir(child):
                subject_dirs.append(child)
    except Exception:
        pass

subject_dirs = sorted(set(subject_dirs), key=lambda p: str(p))
subject_names = [p.name for p in subject_dirs]

case_matches = []
for cid in case_ids:
    n = norm(cid)
    d = digits(cid)
    exact = [p for p in subject_dirs if p.name == cid]
    fuzzy = []
    for p in subject_dirs:
        pn = norm(p.name)
        pd = digits(p.name)
        if p in exact:
            continue
        if n and (n == pn or n in pn or pn in n):
            fuzzy.append(p)
        elif d and pd and d == pd:
            fuzzy.append(p)
    selected = exact + fuzzy[:8]
    case_matches.append({
        "case_id": cid,
        "exact_subject_matches": [subject_summary(p) for p in exact[:5]],
        "fuzzy_subject_matches": [subject_summary(p) for p in fuzzy[:8]],
        "match_count": len(selected),
    })

mask_search = run([
    "find", "/data/mm13924", "/home/mm13924/freesurfer_subjects",
    "-type", "f",
    "(",
    "-iname", "*aparc*aseg*",
    "-o", "-iname", "*aseg*",
    "-o", "-iname", "*wmparc*",
    "-o", "-iname", "*brainmask*",
    "-o", "-iname", "*ribbon*",
    ")",
], timeout=180)

mask_examples = []
for line in mask_search.get("stdout", [])[:300]:
    p = Path(line)
    if p.is_file():
        mask_examples.append(file_info(p))

install_checks = {
    "env": {
        "FREESURFER_HOME": os.environ.get("FREESURFER_HOME"),
        "SUBJECTS_DIR": os.environ.get("SUBJECTS_DIR"),
        "FSFAST_HOME": os.environ.get("FSFAST_HOME"),
        "MNI_DIR": os.environ.get("MNI_DIR"),
    },
    "which_recon_all": run(["bash", "-lc", "command -v recon-all || true"], timeout=30),
    "which_mri_convert": run(["bash", "-lc", "command -v mri_convert || true"], timeout=30),
    "usr_local_freesurfer": run(["find", "/usr/local", "-maxdepth", "4", "-type", "d", "-iname", "freesurfer*"], timeout=60),
}

root_summaries = []
for root in unique_roots:
    count = 0
    examples = []
    try:
        for child in root.iterdir():
            if child.is_dir() and looks_like_subject_dir(child):
                count += 1
                if len(examples) < 20:
                    examples.append(str(child))
    except Exception as exc:
        examples.append("ERROR: " + repr(exc))
    root_summaries.append({
        "root": str(root),
        "subject_like_count": count,
        "subject_examples": examples,
    })

audit = {
    "generated_at": datetime.datetime.now().isoformat(),
    "host": socket.gethostname(),
    "user": getpass.getuser(),
    "case_count": len(case_ids),
    "case_ids": case_ids,
    "install_checks": install_checks,
    "freesurfer_dir_searches": dir_searches,
    "candidate_subject_roots": root_summaries,
    "total_subject_like_dirs_found": len(subject_dirs),
    "subject_name_examples": subject_names[:80],
    "case_subject_matches": case_matches,
    "mask_file_examples": mask_examples,
    "notes": [
        "Read-only audit only. No recon-all, no conversion, no server writes.",
        "If exact matches are empty but fuzzy matches exist, the downloader needs a case-ID mapping.",
        "Native .mgz files may need conversion/alignment before direct NeuroTrust use.",
    ],
}

print(json.dumps(audit, indent=2))
PY

python3 - "$DEST/freesurfer_audit.json" > "$DEST/FREESURFER_AUDIT_SUMMARY.md" <<'PY'
import json
import sys

a = json.load(open(sys.argv[1]))

lines = []
lines.append("# FreeSurfer server audit")
lines.append("")
lines.append(f"- Generated: `{a.get('generated_at')}`")
lines.append(f"- Host: `{a.get('host')}`")
lines.append(f"- User: `{a.get('user')}`")
lines.append(f"- Batch case count: `{a.get('case_count')}`")
lines.append("")

env = a.get("install_checks", {}).get("env", {})
lines.append("## Environment")
for k, v in env.items():
    lines.append(f"- `{k}` = `{v}`")
lines.append("")

lines.append("## Candidate FreeSurfer subject roots")
for root in a.get("candidate_subject_roots", []):
    lines.append(f"- `{root.get('root')}`: `{root.get('subject_like_count')}` subject-like dirs")
    for ex in root.get("subject_examples", [])[:8]:
        lines.append(f"  - `{ex}`")
lines.append("")

lines.append("## Subject name examples")
for name in a.get("subject_name_examples", [])[:40]:
    lines.append(f"- `{name}`")
lines.append("")

lines.append("## Case-to-FreeSurfer matches")
for rec in a.get("case_subject_matches", []):
    exact = rec.get("exact_subject_matches", [])
    fuzzy = rec.get("fuzzy_subject_matches", [])
    lines.append(f"### `{rec.get('case_id')}`")
    lines.append(f"- Exact matches: `{len(exact)}`")
    for item in exact[:3]:
        lines.append(f"  - `{item.get('path')}`")
    lines.append(f"- Fuzzy matches: `{len(fuzzy)}`")
    for item in fuzzy[:3]:
        lines.append(f"  - `{item.get('path')}`")
    if not exact and not fuzzy:
        lines.append("- No subject match found.")
    lines.append("")

lines.append("## Mask file examples")
for item in a.get("mask_file_examples", [])[:80]:
    lines.append(f"- `{item.get('path')}`")
lines.append("")

lines.append("## Notes")
for note in a.get("notes", []):
    lines.append(f"- {note}")

print("\n".join(lines) + "\n")
PY

echo
echo "DONE. Audit files:"
echo "$DEST/FREESURFER_AUDIT_SUMMARY.md"
echo "$DEST/freesurfer_audit.json"
echo
echo "Open summary:"
echo "open \"$DEST/FREESURFER_AUDIT_SUMMARY.md\""

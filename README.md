# NeuroTrust-MS

**NeuroTrust-MS** is a hospital-facing validation platform for multiple-sclerosis lesion segmentation outputs.

It is built for a practical clinical question:

> If a segmentation model gives a lesion mask, where can the reviewer trust it, where does it fail, and which findings deserve manual attention first?

The app accepts brain MRI volumes, expert lesion masks, model prediction masks, and optional anatomy/probability/uncertainty evidence. It turns those files into a structured review report with lesion-level metrics, location-aware behavior, reliability signals, 3D overlays, exports, and saved validation history.

## Why this matters

MS lesion segmentation is not judged well by one global overlap score alone. A model can look acceptable overall while still missing small lesions, overcalling noisy candidates, splitting one lesion into many fragments, merging separate lesions, or underperforming in clinically important regions.

Most workflows focus on producing a segmentation. NeuroTrust-MS focuses on validating the segmentation after it is produced.

That makes it useful for:

- hospital model review;
- research-group benchmarking;
- vendor-neutral model comparison;
- local scanner/protocol validation;
- demonstrating why a model is safe enough, limited, or not ready for a given dataset.

## What the product does

NeuroTrust-MS validates uploaded segmentation outputs against expert reference masks.

Core workflow:

```text
MRI volume
Expert lesion mask
Prediction mask
Optional anatomy / probability / uncertainty / second reader files
        ↓
NeuroTrust-MS validation engine
        ↓
Clinical summary, metrics, 3D viewer, review watchlist, exports, saved history
```

The app does not silently fabricate missing inputs. If required files are absent, mismatched, duplicated, empty, or geometrically incompatible, the backend returns a clear validation error instead of producing a misleading report.

## Main features

### 1. Case and batch validation

Users can validate one to five case-matched subjects per run.

Required inputs:

- raw MRI volumes;
- expert ground-truth lesion masks;
- prediction masks from one segmentation model.

Optional inputs:

- FreeSurfer or SynthSeg anatomy labelmaps;
- FreeSurfer subject-folder files containing `.mgz` anatomy outputs;
- probability maps;
- uncertainty maps;
- second expert masks;
- metadata files.

The app groups files by normalized case ID and reports any pairing problems before running metrics.

### 2. Prepared 5-case demo

The hosted demo can run a prepared 5-case validation bundle. It is designed to behave like a real upload while keeping the demonstration fast.

Expected bundle layout:

```text
test_1/
  raw_mris/
  gts/
  predictions/
  expert_2_masks_test_only/
  probability_maps_test_only/
  uncertainty_maps_test_only/
  freesurfer_subject_files/
  anatomy_labelmaps_optional/
  metadata/
```

The Research Appendix shows exactly which source folders and files were mapped into each upload field, so the demo remains transparent.

### 3. Simple generated demo

A fast one-case generated demo is included for quick UI testing. It creates a synthetic MRI-like volume, expert mask, prediction mask, second-reader support mask, and anatomy labelmap.

### 4. Lesion-level validation

The backend calculates lesion components in 3D and reports:

- total expert lesions;
- total prediction lesions;
- matched lesions;
- missed expert lesions;
- prediction-only lesions;
- lesion recall;
- lesion precision;
- lesion F1;
- false-positive lesions per scan;
- missed lesions per scan;
- split behavior;
- merge behavior;
- component-size behavior.

### 5. Voxel-level validation

The app also calculates standard overlap and distance metrics:

- Dice;
- Jaccard;
- precision;
- recall;
- specificity;
- false-positive volume;
- false-negative volume;
- absolute volume difference;
- relative volume error;
- Hausdorff distance where computable;
- HD95 where computable;
- average surface distance where computable.

Metrics that are not computable for a valid reason are marked unavailable rather than invented.

### 6. Size-bin behavior

Lesions are grouped by physical volume to expose size-dependent model behavior.

Current bins:

- tiny: 0-15 mm³;
- small: 15-50 mm³;
- medium: 50-250 mm³;
- large: above 250 mm³.

This helps show whether a model mainly succeeds on large obvious lesions while missing small clinically relevant findings.

### 7. Anatomy-aware review

When anatomy labels are uploaded, the app calculates location-aware evidence for MS-relevant regions:

- periventricular;
- juxtacortical/cortical;
- infratentorial;
- deep white matter/other;
- corpus callosum where available.

It reports location-specific recall, prediction burden, and topography-preservation signals. If anatomy evidence is missing or incomplete, the app reports that limitation clearly.

### 8. Reliability and second-reader support

Optional second expert masks allow the report to separate model error from reader variability.

Optional probability and uncertainty maps enable:

- confidence spread;
- uncertainty burden;
- low-confidence warning signals;
- probability-map availability checks.

### 9. Review watchlist

The app creates a per-subject clinical watchlist instead of only showing aggregate statistics.

Examples:

- smallest missed expert lesions;
- largest prediction-only candidates;
- low recall by location;
- high false-positive burden;
- geometry or anatomy warnings;
- cases where outputs require focused manual review.

### 10. Viewer and exports

The frontend includes:

- interactive orthogonal/3D-style review;
- overlay toggles for expert mask, prediction mask, overlap, missed lesions, prediction-only lesions, and anatomy-derived masks;
- lightweight PNG fallback previews;
- downloadable JSON, CSV, and HTML evidence exports;
- saved validation history for signed-in users.

## Access and history

The app includes a database-backed email/password access gate.

Behavior:

- first login creates a user record for that email;
- repeat login for the same email requires the same password;
- passwords are salted and hashed;
- raw passwords are not stored;
- sessions use server-side hashed tokens;
- validation history is linked to the signed-in email;
- expired result files are reported as expired rather than silently replaced.

SQLite tables:

- `access_users`;
- `access_log`;
- `access_sessions`;
- `validation_runs`.

## Safety and edge-case handling

NeuroTrust-MS is designed to fail clearly rather than produce misleading evidence.

Implemented safeguards include:

- file-extension allowlist;
- maximum file-size enforcement;
- maximum batch-size enforcement;
- one hosted validation job at a time;
- duplicate required-file rejection;
- case-ID pairing checks;
- image/mask geometry validation;
- empty-mask warnings;
- anisotropic-spacing warnings;
- thick-slice warnings;
- missing-anatomy handling;
- unavailable metric handling;
- expired-result handling;
- temporary job cleanup;
- protected history lookup by signed-in user.

The app validates segmentation evidence. It does not make a diagnosis and does not replace clinical interpretation.

## Architecture

```text
React + Vite frontend
        ↓
FastAPI backend
        ↓
NumPy / SciPy / scikit-image / nibabel metric engine
        ↓
SQLite access and validation-history database
        ↓
Static viewer assets and downloadable reports
```

Deployment scripts are included for a lightweight Ubuntu/Nginx/Uvicorn setup.

## Local setup

```bash
git clone https://github.com/namik63/neurotrust-ms.git
cd neurotrust-ms
chmod +x scripts/start_local.sh
./scripts/start_local.sh
```

Then open:

```text
http://127.0.0.1:5173/
```

Backend:

```text
http://127.0.0.1:8000/
```

## Manual development setup

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Validation checks

Backend tests:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
```

Frontend build:

```bash
npm --prefix frontend run build
```

AWS script syntax:

```bash
bash -n deploy/aws/*.sh
```

## Server deployment

See [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md) for a generic Ubuntu/Nginx deployment guide.

The deployment uses:

- static frontend build served by Nginx;
- FastAPI backend served by Uvicorn;
- systemd service management;
- optional server-level basic auth;
- app-level email/password access;
- temporary job storage under `/var/lib/neurotrust-ms`;
- prepared demo bundle support under `/var/lib/neurotrust-ms/demo_data/test_1`.

## Repository structure

```text
backend/
  app/
    core/                 metric engines and report generation
    config/               anatomy label mappings
    main.py               FastAPI routes and workflow orchestration
  tests/                  backend test suite
frontend/
  src/
    components/           clinical UI panels and viewer
    metrics/              frontend metric labels and explanations
deploy/
  aws/                    Ubuntu/Nginx/systemd deployment scripts
docs/                     supporting technical notes
scripts/                  local helper scripts
```

## Product position

NeuroTrust-MS is not another segmentation model. It is a validation layer for segmentation outputs.

The differentiator is the combination of:

- global metrics;
- lesion-level behavior;
- anatomy-specific behavior;
- topography preservation;
- uncertainty and second-reader context;
- case-level watchlists;
- transparent upload mapping;
- saved validation evidence.

That turns a mask comparison into a clinically usable review workflow.

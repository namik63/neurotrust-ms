# NeuroTrust-MS

**NeuroTrust-MS** is a web-based validation and quality-assurance platform for **multiple sclerosis lesion segmentation AI**. It is designed for hospital AI review workflows where a team already has:

- raw brain MRI volumes;
- expert lesion masks;
- AI-predicted lesion masks from one segmentation model;
- optional FreeSurfer/SynthSeg anatomy labels;
- optional probability, uncertainty, and second-reader masks.

The app turns those files into a structured validation report: lesion misses, false positives, anatomy-specific behavior, reliability spread, review priorities, 3D overlays, downloadable evidence tables, and saved result history.

## Current final-version status

This repository currently contains the database-backed final prototype used for the hackathon demo.

Implemented and verified:

- local FastAPI backend;
- React/Vite frontend;
- email/password access gate;
- SQLite-backed login, session, validation-history, and result-path storage;
- simple one-case generated demo;
- prepared 5-case demo using the explicit `test 1` validation bundle;
- user batch upload mode;
- FreeSurfer `.mgz` anatomy support;
- anatomy-aware PV/JC/cortical/IT/DWM/corpus-callosum location metrics;
- optional probability/uncertainty map handling;
- optional second expert mask handling;
- 3D/orthogonal NiiVue-style viewer with PNG fallback;
- CSV/JSON/HTML exports;
- AWS EC2 deployment scripts.

Latest local verification:

```text
Backend tests: 19 passed
Frontend production build: passed
AWS shell syntax checks: passed
Prepared 5-case demo smoke test: passed
FreeSurfer anatomy available in 5/5 prepared demo cases
```

## Product scope

NeuroTrust-MS validates segmentation outputs. It does **not** run nnU-Net/SwinUNETR/SegResNet inference inside the web app. The intended workflow is:

```text
MRI + expert GT mask + AI prediction mask
        ↓
NeuroTrust-MS validation backend
        ↓
voxel metrics + lesion metrics + anatomy metrics + reliability + viewer assets
        ↓
clinician-facing review report + research exports
```

The product is built to answer:

- Which expert lesions did the AI miss?
- Which AI lesion candidates are prediction-only?
- Does the model behave differently for small lesions?
- Does the model behave differently by brain location?
- Does global Dice hide lesion-level failure?
- Does the output preserve relevant lesion topography?
- Which findings should a radiologist review first?
- Are uploaded files valid, paired, and geometrically compatible?
- Can the same signed-in user reopen recent validation results?

## Main user flows

### 1. Sign in

The app starts with an email/password gate.

Current behavior:

- first login for an email creates that email's password record;
- repeat login for the same email must use the same password;
- raw passwords are never stored;
- salted password hashes are stored in SQLite;
- sessions use server-side hashed tokens;
- recent validation history is tied to the signed-in email.

Database tables include:

- `access_log`;
- `access_users`;
- `access_sessions`;
- `validation_runs`.

Default local database location:

```text
access_log.sqlite3
```

Default hosted database location:

```text
/var/lib/neurotrust-ms/access_log.sqlite3
```

### 2. Simple one-case demo

The simple demo generates a synthetic MRI-like volume, expert mask, prediction mask, optional second expert mask, and toy anatomy labelmap.

Use it only for fastest UI testing.

### 3. Prepared 5-case demo

The 5-case demo is the main polished demonstration workflow.

Local expected folder:

```text
/Users/namikhassan/Downloads/test 1
```

EC2 expected folder:

```text
/var/lib/neurotrust-ms/demo_data/test_1
```

The 5-case demo does **not** silently fall back to fake data. If the prepared folder is missing, the backend returns a clear error listing the expected paths and required folders.

When the 5-case demo finishes, the app opens the **Research Appendix** first so the user immediately sees exactly what was used.

Prepared bundle mapping:

| Website upload field | Source folder in `test 1` | Current demo count | Purpose |
|---|---:|---:|---|
| Raw MRIs | `raw_mris/` | 5 | Base MRI image for geometry, preview, and viewer |
| Expert GT masks | `gts/` | 5 | Primary lesion ground truth |
| AI prediction masks | `predictions/` | 5 | Segmentation output being validated |
| Second expert masks | `expert_2_masks_test_only/` | 5 | Reader-variability feature testing |
| Probability maps | `probability_maps_test_only/` | 5 | Confidence-map feature testing |
| Uncertainty maps | `uncertainty_maps_test_only/` | 5 | Uncertainty-map feature testing |
| FreeSurfer subject files | `freesurfer_subject_files/` | 5 | Preferred anatomy source |
| Optional anatomy labelmaps | `anatomy_labelmaps_optional/` | 5 | Fallback anatomy source |
| Metadata | `metadata/` | 1 | Prepared-bundle manifest |
| Bundle documents | root README/checksum/manifest files | 3 | Transparency and checksum documentation |

Verified case IDs in the prepared bundle:

```text
subject_004
subject_009
subject_011
subject_018
subject_020
```

The app copies the bundle files into the backend job folder exactly like an upload, then reports the copied source-to-field mapping in the Research Appendix:

- source folder;
- website field key;
- website field label;
- source subfolder;
- file count;
- file names;
- case-by-case pairing;
- selected FreeSurfer anatomy labelmap per subject.

Example verified pairing:

```text
subject_004
  Raw MRI:       raw_mris/subject_004.nii.gz
  GT:            gts/subject_004.nii.gz
  Prediction:    predictions/subject_004.nii.gz
  Expert 2:      expert_2_masks_test_only/subject_004.nii.gz
  Probability:   probability_maps_test_only/subject_004.nii.gz
  Uncertainty:   uncertainty_maps_test_only/subject_004.nii.gz
  FreeSurfer:    freesurfer_subject_files/subject_004/subject_004_01_aparc_aseg.mgz
```

### 4. User batch upload

Users can upload their own validation batch.

Required fields:

- raw MRIs;
- expert GT masks;
- AI prediction masks.

Optional fields:

- anatomy labelmaps;
- FreeSurfer subject-folder files;
- FreeSurfer LUT;
- probability maps;
- uncertainty maps;
- second expert masks;
- metadata CSV.

Hosted demo limit:

```text
maximum 5 cases per validation run
one validation job at a time
```

Files are grouped by normalized case ID. For example:

```text
raw_mris/subject_004.nii.gz
gts/subject_004.nii.gz
predictions/subject_004.nii.gz
```

The frontend performs a manual pairing check before upload. The backend repeats case matching and rejects duplicate required GT/prediction files.

## Frontend pages and tabs

### Home

After login, the user can:

- start a new validation;
- run simple demo;
- run 5-case demo;
- open past results;
- open Method Vault if a result is loaded.

The final version intentionally removes decorative brain-cursor/canvas UI. The page is kept clean and functional.

### Workspace

The workspace provides:

- validation mode selector;
- project name;
- model/vendor name;
- upload slots for all supported data fields;
- manual upload safety check;
- run button.

Modes:

```text
simple_demo
five_case_demo
batch
```

### Results

Results are separated into clinician and research views.

Clinician-view tabs:

- Clinical Summary;
- Review Priorities;
- Anatomy Failure Map;
- Hospital Reliability;
- Improvement Plan;
- Safety / Edge / Privacy;
- 3D Viewer;
- Research Appendix;
- Exports;
- Model Comparison when available.

Research-view tabs additionally expose:

- Size × Location;
- Hard Cases;
- Lesions.

### Clinical Summary

Shows:

- main takeaway;
- strongest evidence area;
- weakest/caution area;
- validation guidance;
- confidence level and interval;
- failure fingerprint;
- trust-gap summary;
- Dice-trap signal;
- location cautions.

### Review Priorities

The radiologist watchlist highlights review targets such as:

- smallest missed GT lesion;
- largest missed GT lesion;
- largest prediction-only lesion;
- low-overlap matched lesion;
- anatomy-specific misses;
- topology-related concerns.

### Anatomy Failure Map

Uses uploaded FreeSurfer/SynthSeg-style labels when present.

Current supported anatomy categories:

- periventricular;
- juxtacortical/cortical;
- infratentorial;
- corpus callosum;
- deep white matter / other;
- unknown.

The anatomy engine:

- loads `.nii`, `.nii.gz`, `.mgz`, or `.mgh` labelmaps;
- can use FreeSurfer LUT names when available;
- selects useful FreeSurfer files in priority order;
- resamples anatomy labels to the lesion grid with nearest-neighbor interpolation when geometry differs;
- reports anatomy QC status and warnings;
- skips anatomy metrics instead of fabricating them if labels are unusable.

FreeSurfer file selection priority:

```text
aparc+aseg / aparc_aseg
aseg
wmparc
ribbon
brainmask
```

### Hospital Reliability

For batch runs, the app reports reliability spread across cases instead of only a single global average.

### Improvement Plan

Turns observed model behavior into practical improvement targets, for example:

- small-lesion sensitivity;
- prediction-only burden;
- anatomy-specific misses;
- split/merge topology;
- boundary quality.

### Safety / Edge / Privacy

The final version keeps this tab concise. It reports implemented safeguards and whether they triggered for the current result.

Implemented controls:

- password-protected validation history;
- temporary result cleanup behavior;
- manual filename pairing check;
- wrong-file-in-wrong-field checks;
- geometry and metadata QC;
- small validation cohort handling;
- empty/no-lesion mask handling;
- FreeSurfer/anatomy evidence handling;
- weakest-location signal;
- small-lesion miss risk;
- prediction-only burden;
- probability/uncertainty map availability;
- second expert context;
- 3D viewer fallback.

### 3D Viewer

The viewer uses a static PNG preview first to keep the page responsive. Interactive 3D is loaded only when requested.

Viewer assets include:

- base MRI volume;
- expert GT overlay;
- AI prediction overlay;
- overlap overlay;
- missed GT overlay;
- prediction-only overlay;
- periventricular GT/prediction overlays when present;
- juxtacortical/cortical GT/prediction overlays when present;
- infratentorial GT/prediction overlays when present;
- jump targets.

The viewer supports:

- batch subject selector;
- MRI volume selector when multiple base volumes exist;
- overlay toggles;
- opacity control;
- axial/coronal/sagittal/multiplanar/render modes;
- PNG fallback if WebGL/NiiVue fails.

Overlay color intent:

| Overlay | Meaning |
|---|---|
| Expert GT | Expert lesion mask |
| AI prediction | Uploaded model prediction |
| Overlap | Voxels where GT and prediction overlap |
| Missed GT | Expert lesion voxels not captured by AI |
| Prediction-only | AI lesion voxels without GT overlap |
| PV GT / PV prediction | Periventricular anatomy-specific overlays |
| JC/cortical GT / prediction | Juxtacortical/cortical overlays |
| IT GT / IT prediction | Infratentorial overlays |

### Research Appendix

Shows:

- metric glossary;
- method cards;
- model passport;
- unavailable metrics;
- 5-case demo upload transparency;
- field-to-file mapping;
- case-by-case pairing;
- selected anatomy labelmap;
- exported evidence provenance.

### Exports

The app exposes downloadable JSON, CSV, HTML, PNG, and derived overlay artifacts.

## Backend metrics and logic

### QC checks

The backend checks:

- image/mask shape mismatch;
- affine mismatch warning;
- invalid spacing;
- anisotropic spacing;
- thick slices;
- nonfinite MRI data;
- nonfinite mask data;
- nonbinary mask values;
- empty GT;
- empty prediction;
- both masks empty;
- unusually large GT lesion fraction;
- unusually large prediction fraction;
- prediction identical to GT;
- duplicate required masks in batch mode;
- missing raw/GT/prediction pairing.

Blocking geometry/file errors stop metric calculation for that case. Nonblocking concerns are preserved as QC warnings.

### Voxel-level metrics

The backend computes:

- TP/FP/FN/TN;
- Dice;
- IoU/Jaccard;
- sensitivity/recall;
- specificity;
- PPV/precision;
- NPV;
- balanced accuracy;
- HD95 in mm;
- ASSD in mm;
- GT volume;
- prediction volume;
- signed volume error;
- absolute volume error;
- relative volume error;
- volume ratio.

### Lesion-level metrics

Lesions are measured with 3D connected components using configured connectivity.

The backend computes:

- GT lesion count;
- predicted lesion count;
- matched lesion count;
- lesion count error;
- lesion recall;
- lesion precision;
- lesion F1;
- false-positive lesions per scan;
- false-negative lesions per scan;
- per-lesion centroid;
- per-lesion volume in voxels and mm³;
- lesion size bin;
- matched lesion Dice;
- matched lesion HD95;
- matched lesion ASSD;
- lesion absolute volume error;
- lesion relative volume error.

Current size bins:

```text
tiny:    0–15 mm³
small:   15–50 mm³
medium:  50–250 mm³
large:   ≥250 mm³
```

### Topology metrics

The app detects component behavior such as:

- matched lesion;
- missed lesion;
- false-positive lesion;
- split;
- merge;
- complex topology.

### Anatomy/location metrics

When anatomy labels are available, the backend computes:

- location GT lesion count;
- location predicted lesion count;
- location matched lesion count;
- location lesion recall;
- location lesion precision;
- location lesion F1;
- location FP lesions per scan;
- location FN lesions per scan;
- location GT volume;
- location prediction volume;
- location absolute volume error;
- location relative volume error;
- location mean matched lesion Dice;
- location mean matched lesion HD95;
- location mean matched lesion ASSD;
- size × location interaction rows;
- location topology rows;
- topography preservation ratio;
- DIS-like topography preservation QA proxy.

The DIS-like proxy is a validation signal about whether topographic lesion-location evidence is preserved. It is not a diagnostic criterion inside the app.

### Probability and uncertainty metrics

If compatible probability maps are uploaded:

- probability threshold used;
- mean probability in true-positive voxels;
- mean probability in false-positive voxels;
- mean probability in false-negative voxels;
- high-confidence false-positive voxel count;
- low-confidence true-positive voxel count.

If compatible uncertainty maps are uploaded:

- mean uncertainty;
- mean uncertainty in error voxels;
- mean uncertainty in correct voxels.

### Expert variability

If a second expert mask is uploaded, the backend separately computes expert-vs-expert context:

- expert pair Dice;
- expert pair HD95;
- expert pair ASSD;
- lesion recall from expert A to expert B;
- lesion F1 symmetric context;
- volume difference.

This is reported separately from AI-vs-GT validation.

### Hard-case and reliability logic

The app creates additional evidence from:

- lesion burden;
- lesion count;
- median lesion size;
- tiny/small lesion fraction;
- spacing anisotropy;
- location denominator;
- topographic region count;
- high-risk location miss rate;
- failure fingerprint tags;
- per-case spread in batch validation.

## Backend API endpoints

Current key endpoints:

```text
POST /api/access/login
GET  /api/access/session
POST /api/access/logout
GET  /api/health
GET  /api/validations/history
GET  /api/validations/{run_id}
GET  /api/admin/database-audit
POST /api/freesurfer/check
POST /api/freesurfer/run-synthseg
POST /api/demo/run
POST /api/demo/run-five-case
POST /api/validation/upload-run
POST /api/validation/upload-batch-run
```

Notes:

- `/api/freesurfer/run-synthseg` is intentionally nonblocking and does not start long anatomy jobs in the local demo path.
- `/api/admin/database-audit` requires two configured headers when enabled.

## Output files

Per-case outputs include:

- `validation_result.json`;
- `full_validation_result.json`;
- `validation_report.html`;
- `model_passport.json`;
- `blindspot_report.json`;
- `location_metrics.json`;
- `location_capability_metrics.json`;
- `size_location_interaction_metrics.json`;
- `location_topology_metrics.json`;
- `anatomy_qc.json`;
- `anatomy_method_card.json`;
- `failure_fingerprint.json`;
- `viewer_manifest.json`;
- `qc_report.json`;
- `method_card.json`;
- `edge_case_report.json`;
- `subject_metrics.csv`;
- `size_bin_metrics.csv`;
- `subject_evidence_preservation.csv`;
- `lesion_metrics.csv`;
- `prediction_lesions.csv`;
- `cluster_metrics.csv`;
- `expert_variability.csv`;
- `location_metrics.csv`;
- `location_volume_metrics.csv`;
- `location_capability_metrics.csv`;
- `size_location_interaction_metrics.csv`;
- `location_topology_metrics.csv`;
- `anatomy_lesion_assignments.csv`;
- `radiologist_watchlist.csv`;
- preview PNG;
- derived overlay NIfTI files;
- derived overlay ZIP.

Batch outputs additionally include:

- batch summary JSON;
- batch subject metrics;
- batch lesion metrics;
- batch prediction metrics;
- batch cluster metrics;
- batch reliability metrics;
- batch hard-case metrics;
- batch location metrics;
- batch viewer manifests;
- case-level result links.

## Local development

### One-command local start

```bash
cd "/Users/namikhassan/Documents/New project/neurotrust-ms"
chmod +x scripts/start_local.sh
./scripts/start_local.sh
```

Then open:

```text
http://localhost:5173
```

### Manual backend

```bash
cd "/Users/namikhassan/Documents/New project/neurotrust-ms"
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Manual frontend

Open a second terminal:

```bash
cd "/Users/namikhassan/Documents/New project/neurotrust-ms/frontend"
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Environment variables

Useful variables:

| Variable | Meaning |
|---|---|
| `NEUROTRUST_DATA_ROOT` / `STORAGE_DIR` | Backend output/job folder |
| `ACCESS_SESSION_HOURS` | Login session lifetime |
| `NEUROTRUST_DEMO_BATCH_ROOT` | Prepared 5-case demo folder |
| `NEUROTRUST_ACCESS_DB` | SQLite database location |
| `NEUROTRUST_ADMIN_SAFETY_KEY` | First admin audit key |
| `NEUROTRUST_ADMIN_SECOND_FACTOR` | Second admin audit factor |
| `MAX_BATCH_CASES` | Hosted batch case limit |
| `MAX_CONCURRENT_JOBS` | Concurrent validation jobs |
| `JOB_TTL_HOURS` | Temporary output cleanup age |
| `MAX_UPLOAD_MB` | Per-file upload size limit |
| `VIEWER_ASSETS_ON_DEMAND` | Hosted viewer behavior |
| `FRONTEND_ORIGIN` | CORS frontend origin |

Local `.env.example`:

```text
NEUROTRUST_DATA_ROOT=./backend/data
ACCESS_SESSION_HOURS=8
NEUROTRUST_DEMO_BATCH_ROOT=
NEUROTRUST_ACCESS_DB=
NEUROTRUST_ADMIN_SAFETY_KEY=
NEUROTRUST_ADMIN_SECOND_FACTOR=
BACKEND_PORT=8000
FRONTEND_PORT=5173
```

## AWS EC2 deployment

Primary deployment target used in the project:

```text
EC2 public URL: http://3.109.202.213/
Project path:   /opt/neurotrust-ms
Backend:        127.0.0.1:8000
Frontend:       Nginx static Vite build
Job storage:    /var/lib/neurotrust-ms/jobs
Demo bundle:    /var/lib/neurotrust-ms/demo_data/test_1
Database:       /var/lib/neurotrust-ms/access_log.sqlite3
```

Upload code from Mac:

```bash
rsync -avz --delete --progress \
  -e "ssh -i /Users/namikhassan/Downloads/NeuroTrustMS-Key.pem -o IdentitiesOnly=yes" \
  --exclude "node_modules" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude ".pytest_cache" \
  --exclude ".git" \
  --exclude "data" \
  --exclude "backend/data" \
  --exclude "frontend/dist" \
  "/Users/namikhassan/Documents/New project/neurotrust-ms/" \
  ubuntu@3.109.202.213:/home/ubuntu/neurotrust-ms/
```

Upload prepared 5-case demo bundle from Mac:

```bash
rsync -avz --progress \
  -e "ssh -i /Users/namikhassan/Downloads/NeuroTrustMS-Key.pem -o IdentitiesOnly=yes" \
  "/Users/namikhassan/Downloads/test 1/" \
  ubuntu@3.109.202.213:/home/ubuntu/neurotrust-test-1/
```

On EC2:

```bash
sudo systemctl stop neurotrust-ms || true

sudo rm -rf /opt/neurotrust-ms
sudo mv /home/ubuntu/neurotrust-ms /opt/neurotrust-ms
sudo chown -R ubuntu:ubuntu /opt/neurotrust-ms

sudo mkdir -p /var/lib/neurotrust-ms/demo_data/test_1
sudo rsync -a --delete /home/ubuntu/neurotrust-test-1/ /var/lib/neurotrust-ms/demo_data/test_1/
sudo chown -R ubuntu:ubuntu /var/lib/neurotrust-ms/demo_data/test_1

cd /opt/neurotrust-ms
chmod +x deploy/aws/*.sh
./deploy/aws/update_ec2.sh

sudo sed -i '/^NEUROTRUST_DEMO_BATCH_ROOT=/d' /etc/neurotrust-ms.env
echo 'NEUROTRUST_DEMO_BATCH_ROOT=/var/lib/neurotrust-ms/demo_data/test_1' | sudo tee -a /etc/neurotrust-ms.env

sudo systemctl restart neurotrust-ms
sudo systemctl reload nginx
```

Check EC2:

```bash
curl -i http://127.0.0.1:8000/api/health
sudo systemctl status neurotrust-ms --no-pager
sudo journalctl -u neurotrust-ms -n 120 --no-pager
```

Public URL:

```text
http://3.109.202.213/
```

## Tests and verification

Run backend tests:

```bash
cd "/Users/namikhassan/Documents/New project/neurotrust-ms"
PYTHONPATH=backend .venv/bin/python -m pytest backend/tests -q
```

Build frontend:

```bash
npm --prefix frontend run build
```

Check AWS shell scripts:

```bash
bash -n deploy/aws/setup_ec2.sh deploy/aws/update_ec2.sh deploy/aws/cleanup_jobs.sh deploy/aws/create_basic_auth.sh
```

Smoke-test the 5-case demo locally:

```bash
PYTHONPATH=backend .venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
login = client.post('/api/access/login', json={'email':'smoke@example.com','password':'smoke-pass'})
token = login.json()['token']
result = client.post('/api/demo/run-five-case', headers={'Authorization': f'Bearer {token}'})
print(result.status_code)
payload = result.json()
print(payload.get('demo', {}).get('source'))
print(payload.get('subject_metrics', {}).get('successful_case_count'))
print(payload.get('subject_metrics', {}).get('anatomy_available_case_count'))
for field in payload.get('demo', {}).get('upload_fields', []):
    print(field.get('website_field_key'), field.get('file_count'))
PY
```

Expected local smoke result with `test 1` present:

```text
200
/Users/namikhassan/Downloads/test 1
5
5
raw_mris 5
gts 5
predictions 5
expert_2_masks 5
probability_maps 5
uncertainty_maps 5
freesurfer_files 5
anatomy_labelmaps 5
metadata_csv 1
bundle_documents 3
```

## GitHub upload notes

Recommended files to exclude from GitHub:

```text
node_modules/
.venv/
frontend/dist/
data/
backend/data/
*.sqlite3
__pycache__/
.pytest_cache/
```

Do not upload the prepared `test 1` medical/demo bundle to a public repository. If the repo is private and the files are permitted to be shared, upload them only with clear consent and documentation.

## Repository structure

```text
backend/
  app/
    main.py
    config.py
    core/
      anatomy.py
      blindspot_engine.py
      clinical_evidence.py
      io.py
      lesion_matching.py
      metrics_hard_cases.py
      metrics_lesion.py
      metrics_location_capability.py
      metrics_reliability.py
      metrics_voxel.py
      product_features.py
      qc.py
      radiologist_watchlist.py
      report_generator.py
      safety.py
      viewer_assets.py
  sample_data/
  tests/

frontend/
  src/
    App.tsx
    components/
    metrics/
    styles/
    types.ts

deploy/aws/
  setup_ec2.sh
  update_ec2.sh
  cleanup_jobs.sh
  nginx-neurotrust-ms.conf
  neurotrust-ms.service

docs/
scripts/
```

## Current clinical-use boundary

NeuroTrust-MS is a validation and QA platform for segmentation masks. It is meant to help reviewers inspect model behavior, failure modes, and evidence quality on uploaded validation cases. It should be used as decision-support evidence for AI validation, not as a standalone diagnosis engine or regulatory approval system.


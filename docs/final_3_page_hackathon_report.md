# NeuroTrust-MS Final 3-Page Product Report

## Page 1 — Product Definition and Problem Fit

### Product name

**NeuroTrust-MS** — a hospital-facing validation and quality-assurance web platform for **multiple sclerosis lesion segmentation AI**.

### Core purpose

NeuroTrust-MS does not try to diagnose MS or replace a radiologist. Its purpose is narrower and more clinically realistic: it helps a hospital, research team, or imaging-AI evaluator understand **where an uploaded MS lesion segmentation model is reliable, where it fails, and what a clinician should manually review before trusting the output**.

The app accepts:

- raw MRI volumes in NIfTI format, including multiple MRI files per subject;
- expert ground-truth lesion masks;
- AI-predicted lesion masks from one model;
- optional FreeSurfer/SynthSeg anatomy labelmaps;
- optional FreeSurfer subject-folder files such as `aparc+aseg.mgz`, `aseg.mgz`, `wmparc.mgz`, `ribbon.mgz`, and `brainmask.mgz`;
- optional FreeSurfer LUT text file for label-name mapping;
- optional second expert mask for reader-variability context;
- optional probability and uncertainty maps when available.

The output is a clinically structured validation report: clinical summary, review priorities, anatomy failure map, lesion-level tables, reliability analysis, safety/edge-case handling, 3D viewer, research appendix, and downloadable JSON/CSV/HTML evidence.

### Problem Fit — 20%

MS lesion segmentation AI can appear strong using global overlap metrics while still failing in ways that matter to clinical review. A model may have acceptable Dice but:

- miss tiny or small lesions;
- miss lesions in important MS-related locations;
- overcall prediction-only lesions and inflate lesion count;
- split one lesion into multiple predicted components;
- merge multiple lesions into one component;
- distort total lesion burden volume;
- behave inconsistently across subjects;
- fail silently when masks are misaligned, empty, swapped, duplicated, or named incorrectly.

NeuroTrust-MS directly addresses this clinical validation gap. It converts segmentation outputs into **radiologist-readable failure evidence**, rather than only showing generic benchmark scores. The system emphasizes:

1. **Lesion detection**, not just voxel overlap. It reports lesion recall, lesion precision, lesion F1, false-positive lesions per scan, false-negative lesions per scan, lesion count error, matched lesion Dice, matched lesion HD95, and matched lesion ASSD.
2. **Anatomy-specific behavior**, when anatomy labels are uploaded. It reports periventricular, juxtacortical/cortical, infratentorial, deep-white-matter/other, and corpus-callosum performance signals.
3. **Small-lesion safety**, using size bins configured in the backend: tiny `0–15 mm³`, small `15–50 mm³`, medium `50–250 mm³`, and large `≥250 mm³`.
4. **Clinician review prioritization**, through a radiologist watchlist that identifies the smallest missed lesion, largest missed lesion, largest false positive, low-overlap matched lesion, and anatomy-specific misses.
5. **Hospital deployment evidence**, through recommendation status, confidence level, confidence interval, model passport, failure fingerprint, trust-gap summary, and reliability spread.

This means the app fits a real clinical workflow: before a hospital trusts a lesion segmentation model, it needs to know not only whether the model is “good on average,” but also **which lesion types and brain regions require human attention**.

## Page 2 — Technical Execution, Architecture, and Working Prototype

### Technical Execution — 25%

NeuroTrust-MS is a working full-stack web product. The current architecture is:

```text
React / Vite frontend
        ↓
FastAPI backend
        ↓
Nibabel + NumPy + SciPy + scikit-image metric engine
        ↓
Temporary job storage with JSON, CSV, HTML, PNG, and NIfTI viewer outputs
```

For AWS deployment, the production-demo architecture is:

```text
Nginx on port 80
        ↓
Static React frontend from /opt/neurotrust-ms/frontend/dist
        ↓
Nginx reverse proxy for /api and /static
        ↓
FastAPI / Uvicorn on 127.0.0.1:8000
        ↓
/var/lib/neurotrust-ms/jobs temporary validation storage
```

The EC2 deployment includes:

- Nginx configuration with React fallback routing;
- `/api/` proxy to FastAPI;
- `/static/` proxy for generated reports and viewer assets;
- `client_max_body_size 2048M`;
- 900-second proxy timeouts for large medical-image uploads;
- gzip compression for frontend assets;
- systemd service for automatic backend restart;
- hosted environment file at `/etc/neurotrust-ms.env`;
- runtime storage at `/var/lib/neurotrust-ms/jobs`;
- private login/session/history database at `/var/lib/neurotrust-ms/access_log.sqlite3`;
- cleanup script for expired validation jobs;
- update script for redeploying new code;
- optional Nginx basic-auth gate.

### Backend validation engine

The backend computes:

- voxel confusion matrix: TP, FP, FN, TN;
- Dice;
- IoU/Jaccard;
- voxel sensitivity/recall;
- voxel specificity;
- voxel PPV/precision;
- voxel NPV;
- balanced accuracy;
- HD95 in millimeters;
- ASSD in millimeters;
- ground-truth lesion volume;
- predicted lesion volume;
- signed volume error;
- absolute volume error;
- relative volume error;
- volume ratio.

The lesion engine performs 3D connected-component analysis using configurable 26-connectivity. It computes:

- ground-truth lesion count;
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
- per-lesion size bin;
- matched lesion Dice;
- matched lesion HD95;
- matched lesion ASSD;
- lesion absolute and relative volume error;
- split/merge/complex topology cluster rows.

The anatomy engine uses uploaded anatomy labelmaps when available. It supports:

- FreeSurfer/SynthSeg-style `.nii`, `.nii.gz`, and `.mgz` labelmaps;
- FreeSurfer subject-folder uploads;
- automatic priority selection: `aparc+aseg`, then `aseg`, then `wmparc`, then `ribbon`, then `brainmask`;
- periventricular, juxtacortical/cortical, infratentorial, deep-white-matter/other, and corpus-callosum location tags;
- location recall, precision, F1;
- location FP/FN burden;
- location volume error;
- location boundary quality;
- location capability score;
- size × location analysis;
- location topology analysis;
- topography preservation ratio;
- DIS-like topography preservation proxy, clearly treated as a QA proxy rather than diagnosis.

### Frontend product experience

The current frontend contains clinician and research views with these result tabs:

- **Clinical Summary**
- **Review Priorities**
- **Anatomy Failure Map**
- **Hospital Reliability**
- **Improvement Plan**
- **Safety / Edge / Privacy**
- **3D Viewer**
- **Research Appendix**
- **Exports**
- **Model Comparison**
- research-only tabs for **Size × Location**, **Hard Cases**, and **Lesions**

The 3D viewer uses NiiVue-style medical volume visualization. It supports:

- subject-level viewer selection for batch runs;
- multiple MRI base volumes;
- overlay toggles for expert GT, AI prediction, overlap, missed GT, prediction-only regions, and location-specific masks where available;
- overlay opacity controls;
- jump targets for important review findings;
- orthogonal preview fallback when full 3D loading is unavailable.

### Working status

The current local verification passed:

- Python backend compile check passed.
- Backend tests passed: **19/19**.
- Hosted frontend production build passed.
- Deployment shell scripts passed syntax checks.

The hosted demo is intentionally constrained for reliability:

- maximum 5 validation cases per run;
- one validation job at a time;
- 2048 MB maximum upload size per file;
- automatic cleanup of old jobs after 4 hours;
- no GPU required for validation-only use.

## Page 3 — Design, Responsible AI, Safety, and Innovation

### Design & Usability — 20%

NeuroTrust-MS is designed around how a clinician or hospital reviewer would actually inspect AI segmentation quality.

The workflow is simple:

1. Enter through the access gate.
2. Choose validation mode.
3. Upload raw MRIs, expert GT masks, prediction masks, and optional anatomy/probability/uncertainty/second-reader data.
4. The app performs pre-run pairing checks.
5. The backend runs validation.
6. The user receives a structured clinical behavior profile.

The app avoids forcing clinicians to interpret raw metric tables first. Instead, it surfaces:

- the main clinical takeaway;
- where the model appears strongest;
- where the model requires caution;
- recommendation confidence and interval;
- failure fingerprint;
- trust-gap summary;
- radiologist watchlist;
- anatomy failure map;
- improvement plan;
- 3D visual evidence.

The interface separates **Clinician view** and **Research view**. Clinician view prioritizes summary, watchlist, anatomy, reliability, improvement, safety, viewer, and exports. Research view exposes deeper tables such as lesion analysis, size × location, and hard-case metrics.

Usability details added in the current product:

- protected email/password access gate with repeat-user welcome and saved validation history;
- Past Results panel for reopening retained validation results;
- simple one-case demo;
- prepared five-case demo report using the explicit `test 1` bundle: `raw_mris`, `gts`, `predictions`, `expert_2_masks_test_only`, `probability_maps_test_only`, `uncertainty_maps_test_only`, `freesurfer_subject_files`, optional anatomy labelmaps, and manifest/checksum documents;
- transparent prepared-demo upload simulation in the Research Appendix, showing the exact source folder, website upload field, file count, filenames, and per-case pairing used for the five-case validation;
- batch upload mode for user-supplied validation data;
- batch-first workflow where one subject is simply batch size 1;
- separate upload slots for raw MRIs, GT masks, prediction masks, anatomy labelmaps, FreeSurfer folders, FreeSurfer LUT, probability maps, uncertainty maps, and second expert masks;
- clear manual upload safety checks before computation;
- file pairing by normalized case basename;
- duplicate GT/prediction rejection;
- clear error if no matching cases are found;
- clear error if more than 5 cases are uploaded in hosted demo mode;
- 3D viewer with fast overlay toggles and stronger active-layer highlighting;
- export center for JSON/CSV/HTML evidence.

### Responsible AI & Safety — 20%

Responsible AI is built into the product at the workflow, backend, deployment, and UI levels.

Privacy and access controls:

- the app uses same-origin API calls;
- no external analytics SDK is used by the validation UI;
- no third-party model inference API is required;
- Nginx basic-auth can protect the entire website;
- the in-app access gate requires email plus password;
- the access database stores email, login time, salted password hash, hashed session tokens, validation run metadata, and protected retained result paths;
- raw passwords are not written to the database;
- repeat users see saved validation history after a successful backend login;
- database audit access can require two independent verification headers;
- the access database is stored outside the public static folder at `/var/lib/neurotrust-ms/access_log.sqlite3`;
- uploaded data and generated outputs live in temporary job storage;
- cleanup removes old job folders after the configured TTL.

Upload and file safety:

- allowed hosted upload types are restricted to `.nii`, `.nii.gz`, `.mgz`, `.json`, `.csv`, and `.txt`;
- filenames are sanitized before saving;
- uploads are size-limited;
- unsafe paths are rejected;
- duplicate required GT/prediction masks are rejected;
- unsupported files are rejected;
- batch mismatches are reported rather than silently ignored.

Clinical edge-case handling:

- empty GT mask;
- empty prediction mask;
- both masks empty;
- shape mismatch;
- affine mismatch warning;
- invalid spacing;
- nonfinite MRI or mask data;
- nonbinary mask values;
- anisotropic spacing;
- thick-slice geometry;
- unusually large GT volume fraction;
- unusually large prediction volume fraction;
- prediction identical to GT, which may indicate accidental duplicate upload;
- partial batch where some cases pass and some fail;
- very small validation set;
- absent anatomy labels;
- absent probability/uncertainty maps;
- absent second expert mask;
- split/merge topology behavior;
- weak location-specific denominator.

The product also avoids hidden inference. It validates uploaded AI masks against uploaded expert masks; it does not silently create predictions, fabricate masks, or modify uploaded segmentation masks before metric calculation.

### Innovation — 15%

The core innovation is that NeuroTrust-MS is not another segmentation model and not another Dice dashboard. It is a **clinical trust compiler** for MS lesion segmentation AI.

Instead of asking only “what is the average Dice?”, it asks:

- Which lesions were missed?
- Were the missed lesions tiny or small?
- Did the model fail in periventricular, juxtacortical/cortical, or infratentorial regions?
- Did it create prediction-only lesion burden?
- Did it split or merge lesions in a way that changes lesion count?
- Did total volume look acceptable while lesion-level evidence failed?
- Is the model stable across subjects?
- Which specific findings should a radiologist review first?
- What improvement plan should the AI team follow next?

Differentiated features include:

- radiologist watchlist with actionable review targets;
- failure fingerprint summarizing the dominant model weakness;
- trust-gap summary;
- Dice-trap detector for cases where global overlap hides lesion-level weakness;
- false-positive burden detector;
- anatomy-aware failure map;
- topography preservation ratio;
- DIS-like topography preservation QA proxy;
- hard-case classification;
- hospital reliability spread;
- model passport;
- improvement plan tied to observed evidence;
- 3D viewer with lesion-specific overlays and jump targets.

The result is a product that helps hospitals make safer, more evidence-based decisions about segmentation AI. It turns raw masks into a clinically interpretable validation workflow: not just “the model scored 0.82,” but “this model misses small infratentorial lesions, overcalls prediction-only candidates, and needs targeted review before use.”

### Final one-sentence pitch

**NeuroTrust-MS is a clinically oriented validation platform that transforms MS lesion segmentation outputs into radiologist-ready trust evidence: lesion misses, false positives, anatomy-specific blind spots, reliability, safety checks, 3D review, and deployment guidance in one working web product.**

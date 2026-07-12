# NeuroTrust-MS second-pass rebuild audit

Date: 2026-07-09

## Implemented

- Batch-first validation UI; a single case is handled as batch size 1.
- Optional batch anatomy labelmaps, FreeSurfer LUT, probability maps, uncertainty maps, expert-2 masks, and metadata upload.
- Optional multi-file FreeSurfer subject upload; folder paths such as `eval_004/mri/aparc+aseg.mgz` are preserved for case matching.
- FreeSurfer labelmap priority: `aparc+aseg`, `aseg`, `wmparc`, `ribbon`, then `brainmask`.
- Anatomy-aware lesion localization from `.nii`, `.nii.gz`, `.mgz`, `.mgh` labelmaps.
- Periventricular, juxtacortical/cortical, infratentorial, corpus callosum, deep white matter/other location tags.
- Location-specific recall, precision, F1, FP/FN burden, volume error, and DIS-like QA proxy.
- Derived NIfTI viewer assets: GT, prediction, overlap, missed, false positive, and feasible per-location masks.
- NiiVue 3D/orthogonal viewer with volume selection, overlays, opacity, screenshots, and jump targets.
- Radiologist watchlist, failure fingerprint, trust gap, dice-trap detector, and false-positive burden detector.
- Structured QC categories for geometry, files, masks, anatomy, batch, viewer, and export.
- Safe FreeSurfer/SynthSeg check endpoints; long anatomy generation is not run by default.

## Not implemented

- Longitudinal new/enlarging lesion metrics.
- STAPLE consensus.
- Scanner/protocol subgroup metrics from DICOM metadata.
- Actual local FreeSurfer/SynthSeg execution queue.

## Verification

- `PYTHONPATH=backend pytest backend/tests -q` passed: 10 tests.
- `npm --prefix frontend run build` passed.
- Demo smoke passed: viewer `niivue_3d`, anatomy available, 22 downloads.
- Batch smoke passed with one case and anatomy labelmap.

## Safety

No diagnosis, regulatory approval, clinical certification, or doctor-replacement claim is made.

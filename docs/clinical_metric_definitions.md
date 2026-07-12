# Clinical metric definitions

NeuroTrust-MS reports standard segmentation metrics and derived clinical safety summaries. Derived summaries are not diagnostic criteria and are not regulatory endpoints.

## Voxel Dice

Formula: `2TP / (2TP + FP + FN)`.

Input: binary ground-truth mask and binary prediction mask.

Range: 0 to 1. Higher is better.

Edge cases: if both masks are empty, technical agreement is reported as 1.0 and the report states this is a no-lesion agreement.

## IoU / Jaccard

Formula: `TP / (TP + FP + FN)`.

Range: 0 to 1.

## Voxel recall / sensitivity

Formula: `TP / (TP + FN)`.

Interpretation: fraction of ground-truth lesion voxels detected.

## Voxel precision / PPV

Formula: `TP / (TP + FP)`.

Interpretation: fraction of predicted lesion voxels that overlap expert lesion voxels.

## HD95

Formula: 95th percentile of symmetric surface-to-surface distances in millimeters.

Edge cases: undefined if either mask is empty.

## ASSD

Formula: average symmetric surface distance in millimeters.

Edge cases: undefined if either mask is empty.

## Lesion recall

Formula: `detected GT lesion components / total GT lesion components`.

Connected components use configurable 3D connectivity, defaulting to 26-connectivity.

## Lesion precision

Formula: `matched predicted lesion components / total predicted lesion components`.

## Lesion F1

Formula: `2 * lesion_precision * lesion_recall / (lesion_precision + lesion_recall)`.

## Volume errors

Absolute lesion volume error: `abs(predicted_volume_mm3 - gt_volume_mm3)`.

Relative lesion volume error: `absolute_volume_error_mm3 / gt_volume_mm3`; undefined when GT volume is zero.

## Clinical evidence preservation ratio

Derived safety summary, not diagnostic criteria.

Formula: `preserved MS-relevant topography groups / GT MS-relevant topography groups`.

Relevant QA localization groups are periventricular, juxtacortical/cortical, and infratentorial. If anatomical masks are not provided, location analysis is marked unknown/not evaluated.

## DIS-like preservation proxy

Derived topography-preservation proxy only. This is not MS diagnosis and does not replace McDonald criteria.

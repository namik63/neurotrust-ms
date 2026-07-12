# Validation scope

The current validation suite supports:

- single-case NIfTI validation;
- synthetic demo validation;
- voxel metrics;
- lesion-wise metrics;
- size-bin labels;
- split/merge cluster detection;
- expert variability when a second expert mask is uploaded;
- blind-spot report generation;
- model passport generation;
- JSON, CSV, PNG preview, and HTML report exports.

The validation suite does not silently resample mismatched masks. Shape mismatch fails QC. Affine mismatch is reported as a warning.

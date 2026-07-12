# Safety and limitations

NeuroTrust-MS is a local validation and quality-assurance support tool.

It does not:

- diagnose MS;
- certify a medical device;
- provide regulatory clearance;
- replace radiologists or neurologists;
- prove a model is safe for all hospitals or scanners.

The validation suite reports location and longitudinal features only when the required data are provided. If anatomical masks, spinal/optic nerve imaging, SWI/QSM, contrast imaging, or registered timepoints are absent, the relevant claims are marked not evaluated.

Users should de-identify files before upload. The default deployment is local-only and makes no external API calls.

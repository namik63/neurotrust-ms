import { useMemo, useState } from "react";
import type { ValidationMode } from "../types";
import { DropzoneField } from "./DropzoneField";
import { ModeSelector } from "./ModeSelector";

type FileState = {
  raw_mris: File[];
  gts: File[];
  predictions: File[];
  anatomy_labelmaps: File[];
  freesurfer_files: File[];
  probability_maps: File[];
  uncertainty_maps: File[];
  expert_2_masks: File[];
  anatomy_lut: File[];
};

const emptyFiles: FileState = {
  raw_mris: [],
  gts: [],
  predictions: [],
  anatomy_labelmaps: [],
  freesurfer_files: [],
  probability_maps: [],
  uncertainty_maps: [],
  expert_2_masks: [],
  anatomy_lut: [],
};

type ManualCheck = {
  level: "ok" | "info" | "warn" | "fail";
  title: string;
  detail: string;
};

function cleanUploadName(file: File) {
  const extended = file as File & { webkitRelativePath?: string; relativePath?: string; path?: string };
  return extended.webkitRelativePath || extended.relativePath || extended.path || file.name;
}

function stripMedicalSuffix(name: string) {
  const clean = name.replace(/\\/g, "/").replace(/[^A-Za-z0-9._+/-]+/g, "_").replace(/^[/._]+|[/._]+$/g, "").replaceAll("/", "_");
  const lower = clean.toLowerCase();
  if (lower.endsWith(".nii.gz")) return clean.slice(0, -7);
  if (lower.endsWith(".nii")) return clean.slice(0, -4);
  if (lower.endsWith(".mgz")) return clean.slice(0, -4);
  if (lower.endsWith(".mgh")) return clean.slice(0, -4);
  return clean.replace(/\.[^.]+$/, "");
}

function caseKeyFromStem(stem: string) {
  let key = stem;
  const patterns = [
    /([_-])(flair|t1ce|t1c|t1|t2|pd|adc|dwi|swi|mri|image|anat|aseg|aparc(?:\+|_)aseg|wmparc|ribbon|brainmask)$/i,
    /([_-])000[0-9]$/i,
    /([_-])modality[0-9]+$/i,
  ];
  patterns.forEach((pattern) => {
    key = key.replace(pattern, "");
  });
  const match = key.match(/(?:subject|eval|case|patient|sub)[_-]?(\d{2,5})/i);
  return match ? `subject_${match[1]}` : key;
}

function caseMap(files: File[]) {
  const grouped = new Map<string, string[]>();
  files.forEach((file) => {
    const name = cleanUploadName(file);
    const key = caseKeyFromStem(stripMedicalSuffix(name));
    grouped.set(key, [...(grouped.get(key) || []), name]);
  });
  return grouped;
}

function duplicateCaseKeys(grouped: Map<string, string[]>) {
  return [...grouped.entries()].filter(([, names]) => names.length > 1).map(([key]) => key);
}

function manualUploadChecks(files: FileState): ManualCheck[] {
  const raw = caseMap(files.raw_mris);
  const gt = caseMap(files.gts);
  const pred = caseMap(files.predictions);
  const rawKeys = new Set(raw.keys());
  const gtKeys = new Set(gt.keys());
  const predKeys = new Set(pred.keys());
  const allRequired = new Set([...rawKeys, ...gtKeys, ...predKeys]);
  const matched = [...allRequired].filter((key) => rawKeys.has(key) && gtKeys.has(key) && predKeys.has(key)).sort();
  const missing = [...allRequired].filter((key) => !rawKeys.has(key) || !gtKeys.has(key) || !predKeys.has(key)).sort();
  const duplicateGt = duplicateCaseKeys(gt);
  const duplicatePred = duplicateCaseKeys(pred);
  const checks: ManualCheck[] = [];

  if (!files.raw_mris.length || !files.gts.length || !files.predictions.length) {
    checks.push({
      level: "fail",
      title: "Required upload group missing",
      detail: "Raw MRIs, expert GT masks, and prediction masks are all required before validation can run.",
    });
  } else if (!matched.length) {
    checks.push({
      level: "fail",
      title: "No matched case IDs",
      detail: "No case basename appears across raw MRIs, GT masks, and prediction masks. Rename files so each case has the same ID, for example eval_001_FLAIR.nii.gz, eval_001.nii.gz, eval_001.nii.gz.",
    });
  } else {
    checks.push({
      level: "ok",
      title: "Matched validation cases",
      detail: `${matched.length} case${matched.length === 1 ? "" : "s"} will be validated: ${matched.slice(0, 5).join(", ")}${matched.length > 5 ? ", …" : ""}.`,
    });
  }

  if (duplicateGt.length || duplicatePred.length) {
    checks.push({
      level: "fail",
      title: "Duplicate required masks",
      detail: `Duplicate GT cases: ${duplicateGt.join(", ") || "none"}. Duplicate prediction cases: ${duplicatePred.join(", ") || "none"}. Keep one GT and one prediction mask per case/model.`,
    });
  }

  if (missing.length) {
    checks.push({
      level: matched.length ? "warn" : "fail",
      title: "Some files will not pair",
      detail: `${missing.length} case ID${missing.length === 1 ? "" : "s"} missing a raw MRI, GT, or prediction: ${missing.slice(0, 6).join(", ")}${missing.length > 6 ? ", …" : ""}. Unpaired cases are skipped from aggregate metrics.`,
    });
  }

  const optionalGroups: Array<[string, File[]]> = [
    ["anatomy labelmap", files.anatomy_labelmaps],
    ["FreeSurfer subject file", files.freesurfer_files],
    ["probability map", files.probability_maps],
    ["uncertainty map", files.uncertainty_maps],
    ["second expert mask", files.expert_2_masks],
  ];
  const unmatchedOptional = optionalGroups.flatMap(([label, values]) => {
    if (!values.length) return [];
    return [...caseMap(values).keys()]
      .filter((key) => !matched.includes(key))
      .map((key) => `${label}: ${key}`);
  });
  if (unmatchedOptional.length) {
    checks.push({
      level: "warn",
      title: "Optional sidecar files do not match validated cases",
      detail: `${unmatchedOptional.slice(0, 6).join("; ")}${unmatchedOptional.length > 6 ? "; …" : ""}. These files may be ignored unless their case IDs match the raw/GT/prediction case ID.`,
    });
  }

  checks.push({
    level: "info",
    title: "Content sanity runs after upload",
    detail: "The backend still checks shape, affine, spacing, empty masks, nonbinary labels, NaN/Inf values, unusually large GT/prediction masks, and identical GT/prediction masks.",
  });
  return checks;
}

export function ValidationWorkspace({
  onRunSimpleDemo,
  onRunFiveCaseDemo,
  onRunBatch,
  error,
}: {
  onRunSimpleDemo: () => void;
  onRunFiveCaseDemo: () => void;
  onRunBatch: (form: FormData) => void;
  error?: string;
}) {
  const [mode, setMode] = useState<ValidationMode>("batch");
  const [projectName, setProjectName] = useState("Hospital MS segmentation QA");
  const [modelName, setModelName] = useState("Uploaded AI model");
  const [files, setFiles] = useState<FileState>(emptyFiles);
  const checks = useMemo(() => mode === "batch" ? manualUploadChecks(files) : [], [files, mode]);

  const ready = useMemo(() => {
    if (mode === "simple_demo" || mode === "five_case_demo") return true;
    return files.raw_mris.length && files.gts.length && files.predictions.length && !checks.some((check) => check.level === "fail");
  }, [checks, files, mode]);

  function update(key: keyof FileState, value: File[]) {
    setFiles((prev) => ({ ...prev, [key]: value }));
  }

  function uploadName(file: File) {
    return cleanUploadName(file);
  }

  function appendFiles(form: FormData, field: string, values: File[]) {
    values.forEach((file) => form.append(field, file, uploadName(file)));
  }

  function run() {
    if (mode === "simple_demo") {
      onRunSimpleDemo();
      return;
    }
    if (mode === "five_case_demo") {
      onRunFiveCaseDemo();
      return;
    }
    const form = new FormData();
    form.append("project_name", projectName);
    form.append("model_name", modelName);
    appendFiles(form, "raw_mris", files.raw_mris);
    appendFiles(form, "gts", files.gts);
    appendFiles(form, "predictions", files.predictions);
    appendFiles(form, "anatomy_labelmaps", files.anatomy_labelmaps);
    appendFiles(form, "freesurfer_files", files.freesurfer_files);
    appendFiles(form, "probability_maps", files.probability_maps);
    appendFiles(form, "uncertainty_maps", files.uncertainty_maps);
    appendFiles(form, "expert_2_masks", files.expert_2_masks);
    if (files.anatomy_lut[0]) form.append("anatomy_lut", files.anatomy_lut[0], uploadName(files.anatomy_lut[0]));
    onRunBatch(form);
  }

  return (
    <main className="workspace page-shell">
      <section className="workspace-hero">
        <div>
          <p className="eyebrow">Hospital segmentation QA</p>
          <h1>Build a clinical behavior profile.</h1>
          <p>
            Upload expert masks and AI predictions to find review priorities, anatomy-specific caution areas, and an evidence-backed improvement plan.
          </p>
        </div>
        <div className="workspace-rail">
          <span>Step 1</span><strong>Choose source</strong>
          <span>Step 2</span><strong>Describe model</strong>
          <span>Step 3</span><strong>Upload evidence</strong>
          <span>Step 4</span><strong>Run validation</strong>
        </div>
      </section>

      <section className="glass-section">
        <div className="section-title">
          <span>Step 1</span>
          <h2>Choose validation mode</h2>
        </div>
        <ModeSelector mode={mode} onMode={setMode} />
      </section>

      {mode === "batch" && (
        <section className="glass-section">
          <div className="section-title">
            <span>Step 2</span>
            <h2>Add project and model details</h2>
          </div>
          <div className="field-grid">
            <label>
              Project name
              <input value={projectName} onChange={(e) => setProjectName(e.target.value)} />
            </label>
            <label>
              Model/vendor name
              <input value={modelName} onChange={(e) => setModelName(e.target.value)} />
            </label>
          </div>
        </section>
      )}

      <section className="glass-section">
        <div className="section-title">
          <span>Step 3</span>
          <h2>{mode === "simple_demo" ? "Simple one-case demo" : mode === "five_case_demo" ? "Prepared 5-case demo" : "Upload validation evidence"}</h2>
        </div>
        {mode === "simple_demo" ? (
          <div className="empty-state">The backend generates one demo MRI, expert GT, prediction mask, second expert mask, and toy anatomy labelmap. Use this when you want the fastest possible report.</div>
        ) : mode === "five_case_demo" ? (
          <div className="empty-state">
            The backend loads the prepared 5-case bundle from the configured demo-data folder. The Research Appendix shows exactly
            which source folder was mapped into each upload field before validation runs.
          </div>
        ) : (
          <div className="drop-grid">
            <DropzoneField label="Raw MRIs" detail="all modalities per case; FLAIR preview selected automatically" files={files.raw_mris} onFiles={(v) => update("raw_mris", v)} multiple />
            <DropzoneField label="Expert GT masks" detail="case-matched lesion masks" files={files.gts} onFiles={(v) => update("gts", v)} multiple />
            <DropzoneField label="Prediction masks" detail="one model, matched to GT cases" files={files.predictions} onFiles={(v) => update("predictions", v)} multiple />
            <DropzoneField label="Anatomy labelmaps" detail="optional FreeSurfer/SynthSeg labels for location evidence" files={files.anatomy_labelmaps} onFiles={(v) => update("anatomy_labelmaps", v)} multiple required={false} kind="anatomy" />
            <DropzoneField label="FreeSurfer subject folder" detail="optional: upload the subject folder containing mri/*.mgz files" files={files.freesurfer_files} onFiles={(v) => update("freesurfer_files", v)} multiple required={false} kind="anatomy" directory />
            <DropzoneField label="FreeSurfer LUT" detail="optional FreeSurferColorLUT.txt; used for label-name mapping" files={files.anatomy_lut} onFiles={(v) => update("anatomy_lut", v)} required={false} kind="anatomy" />
            <DropzoneField label="Probability maps" detail="optional model confidence volumes" files={files.probability_maps} onFiles={(v) => update("probability_maps", v)} multiple required={false} />
            <DropzoneField label="Uncertainty maps" detail="optional uncertainty volumes" files={files.uncertainty_maps} onFiles={(v) => update("uncertainty_maps", v)} multiple required={false} />
            <DropzoneField label="Second expert masks" detail="optional reader variability context" files={files.expert_2_masks} onFiles={(v) => update("expert_2_masks", v)} multiple required={false} />
          </div>
        )}
        {mode === "batch" && (
          <div className="manual-check-panel" aria-live="polite">
            <div>
              <span className="eyebrow">Manual upload safety check</span>
              <h3>Before running, NeuroTrust-MS checks common doctor/upload mistakes.</h3>
            </div>
            <div className="manual-check-grid">
              {checks.map((check) => (
                <article className={`manual-check ${check.level}`} key={`${check.level}-${check.title}`}>
                  <span>{check.level}</span>
                  <h4>{check.title}</h4>
                  <p>{check.detail}</p>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>

      <section className="run-panel">
        <div>
          <span>Step 4</span>
          <h2>Run validation</h2>
          <p>{mode === "batch" ? "Files are paired by case ID. One case works; a batch gives stronger validation confidence." : mode === "five_case_demo" ? "Runs the five-case demo validation path." : "Runs the simple one-case demo validation path."}</p>
          {error && <p className="form-error">{error}</p>}
        </div>
        <button className="primary glow" disabled={!ready} onClick={run}>
          {mode === "simple_demo" ? "Run simple demo" : mode === "five_case_demo" ? "Run 5-case demo" : "Run batch validation"}
        </button>
      </section>
    </main>
  );
}

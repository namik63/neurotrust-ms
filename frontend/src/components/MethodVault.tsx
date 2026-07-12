import type { ValidationResult } from "../types";
import { metricDefinitions } from "../metrics/metricDefinitions";

const cards = [
  ["Voxel metrics", "Dice, IoU, sensitivity, specificity, PPV, NPV, balanced accuracy."],
  ["Lesion metrics", "Connected components, detection, FP/FN burden, size-stratified recall."],
  ["Surface metrics", "HD95 and ASSD on matched masks and lesions."],
  ["Volume metrics", "Absolute, signed, relative error and volume ratio."],
  ["Topology", "Split, merge, complex, missed, and false-positive clusters."],
  ["Anatomy localization", "FreeSurfer/SynthSeg labelmap proxy; PV/JC/IT/DWM outputs only when labels exist."],
  ["Expert variability", "Optional second expert mask; no STAPLE claim."],
  ["Data integrity engine", "Geometry, file, mask, anatomy, batch, viewer, and export checks."],
  ["Private processing", "Uploaded files are processed by the configured backend session; exports preserve metric provenance."],
];

function shortList(values: string[] = []) {
  if (!values.length) return "none";
  const visible = values.slice(0, 8).join(", ");
  return values.length > 8 ? `${visible}, +${values.length - 8} more` : visible;
}

function DemoUploadTransparency({ result }: { result: ValidationResult }) {
  const demo = result.demo;
  if (!demo?.transparent_upload_simulation) return null;
  const fields = Array.isArray(demo.upload_fields) ? demo.upload_fields : [];
  const cases = Array.isArray(demo.case_upload_manifest) ? demo.case_upload_manifest : [];
  return (
    <section className="overview-card vault-lead demo-transparency">
      <p className="eyebrow">Prepared upload simulation</p>
      <h3>Exactly what the 5-case demo uploaded</h3>
      <p>
        The prepared demo is treated like a batch upload. These are the source folders and files that were placed into the same
        backend fields a user would normally upload manually.
      </p>
      <div className="demo-source-line">
        <b>Source folder</b>
        <code>{demo.source || "not reported"}</code>
      </div>
      {demo.test_only_notice && <div className="empty-state subtle">{demo.test_only_notice}</div>}
      <div className="upload-field-grid">
        {fields.map((field: any) => (
          <article className="method-card compact-method" key={field.website_field_key || field.website_field_label}>
            <span>{field.file_count ?? 0} file{Number(field.file_count) === 1 ? "" : "s"}</span>
            <h4>{field.website_field_label}</h4>
            <p><b>Website field:</b> <code>{field.website_field_key}</code></p>
            <p><b>Source:</b> <code>{field.source_folder}</code></p>
            <p>{field.note}</p>
            <small>{shortList(field.files || [])}</small>
          </article>
        ))}
      </div>
      <details className="method-card case-upload-manifest">
        <summary>Case-by-case file pairing</summary>
        <div className="case-manifest-grid">
          {cases.map((row: any) => (
            <article key={row.case_id}>
              <h4>{row.case_id}</h4>
              <dl>
                <div><dt>Raw MRI</dt><dd>{shortList(row.raw_mris)}</dd></div>
                <div><dt>GT</dt><dd>{shortList(row.gts)}</dd></div>
                <div><dt>Prediction</dt><dd>{shortList(row.predictions)}</dd></div>
                <div><dt>Second expert</dt><dd>{shortList(row.expert_2_masks)}</dd></div>
                <div><dt>Probability</dt><dd>{shortList(row.probability_maps)}</dd></div>
                <div><dt>Uncertainty</dt><dd>{shortList(row.uncertainty_maps)}</dd></div>
                <div><dt>FreeSurfer files</dt><dd>{shortList(row.freesurfer_files)}</dd></div>
                <div><dt>Selected anatomy</dt><dd>{row.selected_anatomy_labelmap || "none"}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      </details>
    </section>
  );
}

export function MethodVault({ result }: { result: ValidationResult }) {
  return (
    <div className="vault-grid">
      <section className="overview-card vault-lead">
        <h3>Research Appendix</h3>
        <p>Metric definitions, formulas, method provenance, and exportable evidence for the uploaded validation data.</p>
        <div className="badge-row">
          {(result.method_badges || []).map((badge) => <span key={badge}>{badge}</span>)}
        </div>
      </section>
      <section className="overview-card vault-lead">
        <h3>Metric glossary</h3>
        <div className="glossary-grid">
          {Object.values(metricDefinitions).map((metric) => (
            <details className="method-card compact-method" key={metric.key}>
              <summary>{metric.displayName}</summary>
              <p>{metric.plainMeaning}</p>
              <p><b>Clinical use:</b> {metric.clinicalWhyItMatters}</p>
              <p><b>Interpretation:</b> {metric.interpretation}</p>
              <p><b>Limitation:</b> {metric.limitation}</p>
            </details>
          ))}
        </div>
      </section>
      <DemoUploadTransparency result={result} />
      {cards.map(([title, copy]) => (
        <details className="method-card" key={title}>
          <summary>{title}</summary>
          <p>{copy}</p>
        </details>
      ))}
      <section className="overview-card">
        <h3>Unavailable metrics</h3>
        <p>{(result.model_passport?.metrics_unavailable || []).join(", ") || "No unavailable list returned."}</p>
      </section>
    </div>
  );
}

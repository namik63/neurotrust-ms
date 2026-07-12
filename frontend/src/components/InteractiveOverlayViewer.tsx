import { useEffect, useMemo, useRef, useState } from "react";
import type { ValidationResult } from "../types";

const DEFAULT_OVERLAYS = new Set(["gt_mask", "prediction_mask", "missed_mask", "false_positive_mask"]);
const VALID_EXTENSIONS = /\.(nii|nii\.gz|mgz|nrrd|mif)$/i;
const DEFAULT_GLOBAL_OPACITY = 0.62;

function absoluteUrl(url?: string) {
  if (!url) return "";
  try {
    return new URL(url, window.location.origin).href;
  } catch {
    return url;
  }
}

function volumeName(url: string | undefined, fallback: string) {
  let clean = String(url || "").split(/[?#]/)[0];
  try {
    clean = decodeURIComponent(clean);
  } catch {
    // Keep the raw URL if it contains malformed escape characters.
  }
  const leaf = clean.slice(clean.lastIndexOf("/") + 1);
  if (VALID_EXTENSIONS.test(leaf)) return leaf;
  return VALID_EXTENSIONS.test(fallback) ? fallback : `${fallback.replace(/\.+$/, "")}.nii.gz`;
}

function caseLabel(caseId: string | undefined, index: number) {
  return caseId || `case_${String(index + 1).padStart(3, "0")}`;
}

function targetExplanation(target: any) {
  const reason = String(target?.reason || target?.type || target?.target_type || "").toLowerCase();
  if (reason.includes("false") || reason.includes("prediction")) return "Prediction-only region. Review before accepting lesion count or burden.";
  if (reason.includes("boundary")) return "Detected lesion with weaker boundary agreement. Review if volume/burden tracking matters.";
  if (reason.includes("tiny") || reason.includes("small")) return "Tiny/small lesion target. These are the most likely to need focused human review.";
  if (reason.includes("infratentorial")) return "Infratentorial target. Inspect brainstem/cerebellar regions carefully.";
  if (reason.includes("miss")) return "Expert lesion not captured by the prediction. Review as a possible missed lesion.";
  return "Validation target selected from the uploaded masks for focused review.";
}

function overlayAlpha(overlay: any, globalOpacity: number) {
  const nativeOpacity = typeof overlay?.opacity === "number" ? overlay.opacity : DEFAULT_GLOBAL_OPACITY;
  return Math.max(0, Math.min(1, nativeOpacity * (globalOpacity / DEFAULT_GLOBAL_OPACITY)));
}

export function InteractiveOverlayViewer({ result }: { result: ValidationResult }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const nvRef = useRef<any>(null);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [baseKey, setBaseKey] = useState("");
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
  const [opacity, setOpacity] = useState(DEFAULT_GLOBAL_OPACITY);
  const [error, setError] = useState("");
  const [interactiveRequested, setInteractiveRequested] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<any>(null);

  const viewerEntries = useMemo(() => {
    const batchEntries = (result.case_viewers || [])
      .filter((entry) => entry?.viewer)
      .map((entry, index) => ({
        case_id: caseLabel(entry.case_id, index),
        viewer: entry.viewer!,
        preview_png: entry.preview_png,
        case_json: entry.case_json,
      }));
    if (batchEntries.length) return batchEntries;
    if (result.viewer) {
      return [{
        case_id: result.case_id || "current_case",
        viewer: result.viewer,
        preview_png: result.downloads?.preview_png || result.downloads?.first_case_preview_png,
        case_json: result.downloads?.json || result.downloads?.batch_json,
      }];
    }
    return [];
  }, [result.case_viewers, result.viewer, result.case_id, result.downloads]);

  const selectedEntry = useMemo(() => {
    return viewerEntries.find((entry) => entry.case_id === selectedCaseId) || viewerEntries[0];
  }, [viewerEntries, selectedCaseId]);

  const viewer = selectedEntry?.viewer;
  const baseVolumes = useMemo(() => {
    if (viewer?.base_volumes?.length) return viewer.base_volumes;
    if (viewer?.base_volume_url) return [{ key: "mri_1", label: "MRI", url: viewer.base_volume_url }];
    return [];
  }, [viewer]);
  const overlays = useMemo(() => viewer?.overlays || [], [viewer]);
  const selectedBase = useMemo(() => baseVolumes.find((item) => item.key === baseKey) || baseVolumes[0], [baseKey, baseVolumes]);
  const loadableOverlays = useMemo(() => overlays.filter((item) => item.url), [overlays]);
  const fallbackPreview = selectedEntry?.preview_png || result.downloads?.preview_png || result.downloads?.first_case_preview_png;
  const loadSignature = useMemo(
    () => [
      selectedEntry?.case_id || "",
      interactiveRequested ? "interactive" : "preview",
      selectedBase?.url || "",
      ...loadableOverlays.map((overlay) => `${overlay.key}:${overlay.url}`),
    ].join("|"),
    [selectedEntry?.case_id, interactiveRequested, selectedBase?.url, loadableOverlays],
  );

  useEffect(() => {
    if (viewerEntries.length && !viewerEntries.some((entry) => entry.case_id === selectedCaseId)) {
      setSelectedCaseId(viewerEntries[0].case_id);
    }
  }, [viewerEntries, selectedCaseId]);

  useEffect(() => {
    setBaseKey(baseVolumes[0]?.key || "");
  }, [selectedEntry?.case_id, baseVolumes]);

  useEffect(() => {
    const next = Object.fromEntries(overlays.map((overlay) => [overlay.key, DEFAULT_OVERLAYS.has(overlay.key)]));
    setEnabled(next);
    setSelectedTarget(null);
  }, [selectedEntry?.case_id, overlays]);

  useEffect(() => {
    if (!interactiveRequested || !canvasRef.current || !selectedBase?.url) return;
    let cancelled = false;
    async function setup() {
      try {
        setLoading(true);
        setError("");
        const gl = canvasRef.current?.getContext("webgl2");
        if (!gl) {
          setError("WebGL2 is unavailable in this browser session. The static overlay preview is shown instead.");
          setLoading(false);
          return;
        }
        const { Niivue } = await import("@niivue/niivue");
        const nv = new Niivue({
          dragAndDropEnabled: false,
          isResizeCanvas: true,
          scrollRequiresFocus: false,
          loadingText: "Loading NeuroTrust-MS viewer",
          backColor: [0.02, 0.03, 0.06, 1],
          crosshairColor: [0.1, 0.9, 1, 0.8],
          logLevel: "error",
        });
        nv.attachToCanvas(canvasRef.current!);
        const volumeList = [
          {
            url: absoluteUrl(selectedBase.url),
            name: volumeName(selectedBase.url, `${selectedBase.key || "mri"}.nii.gz`),
            colormap: "gray",
          },
          ...loadableOverlays.map((overlay) => ({
            url: absoluteUrl(overlay.url),
            name: volumeName(overlay.url, `${overlay.key || "overlay"}.nii.gz`),
            colormap: overlay.colormap || "red",
            opacity: enabled[overlay.key] ? overlayAlpha(overlay, opacity) : 0,
            cal_min: 0,
            cal_max: 1,
          })),
        ];
        await nv.loadImages(volumeList as any);
        nv.setSliceType(nv.sliceTypeMultiplanar);
        loadableOverlays.forEach((overlay, index) => nv.setOpacity(index + 1, enabled[overlay.key] ? overlayAlpha(overlay, opacity) : 0));
        if (!cancelled) nvRef.current = nv;
      } catch (err: any) {
        if (!cancelled) setError(err?.message || "NiiVue could not load this case. The static overlay preview is shown instead.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    setup();
    return () => {
      cancelled = true;
      try {
        nvRef.current?.cleanup?.();
        nvRef.current?.destroy?.();
      } catch {
        // Some NiiVue builds do not expose destroy; clearing the ref is enough for this local viewer.
      }
      nvRef.current = null;
    };
  }, [loadSignature]);

  useEffect(() => {
    const nv = nvRef.current;
    if (!nv) return;
    loadableOverlays.forEach((overlay, index) => nv.setOpacity(index + 1, enabled[overlay.key] ? overlayAlpha(overlay, opacity) : 0));
  }, [opacity, enabled, loadableOverlays]);

  function toggleOverlay(overlay: any) {
    const next = !enabled[overlay.key];
    const index = loadableOverlays.findIndex((item) => item.key === overlay.key);
    setEnabled((current) => ({ ...current, [overlay.key]: next }));
    const nv = nvRef.current;
    if (nv && index >= 0) {
      try {
        nv.setOpacity(index + 1, next ? overlayAlpha(overlay, opacity) : 0);
        nv.drawScene?.();
      } catch {
        // The React state update above still keeps the manifest and controls correct.
      }
    }
  }

  function setView(kind: "axial" | "coronal" | "sagittal" | "multi" | "render") {
    const nv = nvRef.current;
    if (!nv) return;
    const map = {
      axial: nv.sliceTypeAxial,
      coronal: nv.sliceTypeCoronal,
      sagittal: nv.sliceTypeSagittal,
      multi: nv.sliceTypeMultiplanar,
      render: nv.sliceTypeRender,
    };
    nv.setSliceType(map[kind]);
  }

  function jump(target: any) {
    setSelectedTarget(target);
    const nv: any = nvRef.current;
    const vox = target?.centroid_voxel;
    if (!nv || !vox) return;
    try {
      nv.scene.crosshairPos = nv.vox2frac([vox[0], vox[1], vox[2]], 0);
      nv.drawScene();
    } catch {
      // The target is still shown in the manifest even if an internal NiiVue API changes.
    }
  }

  if (!viewerEntries.length || !selectedBase?.url) {
    return <div className="empty-state">No 3D viewer assets were returned.</div>;
  }

  const toolbar = (
    <div className="viewer-toolbar">
      <div>
        <h3>3D Viewer</h3>
        <p>{viewer?.label || "Orthogonal/3D viewer for the selected validation case."}</p>
      </div>
      <div className="viewer-actions">
        <button onClick={() => setView("multi")}>Multi</button>
        <button onClick={() => setView("axial")}>Axial</button>
        <button onClick={() => setView("coronal")}>Coronal</button>
        <button onClick={() => setView("sagittal")}>Sagittal</button>
        <button onClick={() => setView("render")}>3D</button>
        {!interactiveRequested && <button className="primary small" onClick={() => setInteractiveRequested(true)}>Load interactive 3D</button>}
      </div>
    </div>
  );

  if (error) {
    return (
      <div className="viewer-command">
        {toolbar}
        <div className="viewer-fallback">
          <h3>Orthogonal preview fallback</h3>
          <p>{error}</p>
          <button className="primary small" onClick={() => { setError(""); setInteractiveRequested(true); }}>Retry interactive 3D</button>
          {fallbackPreview ? <img className="fallback-preview" src={fallbackPreview} alt="Fallback overlay preview" loading="lazy" /> : <div className="empty-state">No fallback preview available.</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="viewer-command">
      {toolbar}

      {!interactiveRequested ? (
        <div className="viewer-fallback preview-first">
          <div>
            <h3>Fast preview loaded</h3>
            <p>The static overlay preview is shown first so the page stays responsive. Load the interactive 3D viewer only when you need slicing, overlay toggles, or jump targets.</p>
            <button className="primary glow" onClick={() => setInteractiveRequested(true)}>Load interactive 3D viewer</button>
          </div>
          {fallbackPreview ? <img className="fallback-preview" src={fallbackPreview} alt="Fast overlay preview" loading="lazy" /> : <div className="empty-state">No fallback preview available.</div>}
        </div>
      ) : (
      <div className="viewer-layout niivue-layout">
        <div className="viewer-canvas-wrap">
          <canvas ref={canvasRef} className="niivue-canvas" aria-label="Interactive MRI overlay viewer" />
          {loading && <div className="viewer-loading">Loading 3D volumes…</div>}
        </div>
        <aside className="viewer-side">
          {viewerEntries.length > 1 && (
            <label>
              Subject
              <select value={selectedEntry?.case_id || ""} onChange={(e) => setSelectedCaseId(e.target.value)}>
                {viewerEntries.map((entry) => <option key={entry.case_id} value={entry.case_id}>{entry.case_id}</option>)}
              </select>
            </label>
          )}
          {baseVolumes.length > 1 && (
            <label>
              MRI volume
              <select value={baseKey} onChange={(e) => setBaseKey(e.target.value)}>
                {baseVolumes.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
              </select>
            </label>
          )}
          <label>
            Overlay opacity
            <input type="range" min="0" max="1" step="0.05" value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} />
          </label>
          <div className="layer-list">
            <small className="viewer-note">Only returned, non-empty overlays are listed for this subject.</small>
            {overlays.map((overlay) => (
              <button
                key={overlay.key}
                type="button"
                aria-pressed={Boolean(enabled[overlay.key])}
                className={enabled[overlay.key] ? "enabled" : ""}
                style={{ "--layer-color": overlay.color || "#8deaff" } as React.CSSProperties}
                onClick={() => toggleOverlay(overlay)}
              >
                <span className="dot" style={{ background: overlay.color || "#8deaff" }} />
                {overlay.label}
              </button>
            ))}
          </div>
          <div className="jump-list">
            <h4>Jump targets</h4>
            {(viewer?.jump_targets || []).slice(0, 8).map((target, index) => (
              <button key={`${target.label}-${index}`} onClick={() => jump(target)}>
                <span>{target.severity || "review"}</span>
                {target.label}
              </button>
            ))}
            {!viewer?.jump_targets?.length && <p>No targeted review coordinates returned for this case.</p>}
          </div>
          {selectedTarget && (
            <div className="selected-target-card">
              <span>{selectedTarget.severity || "review"}</span>
              <h4>{selectedTarget.label || "Selected target"}</h4>
              <p>{targetExplanation(selectedTarget)}</p>
            </div>
          )}
        </aside>
      </div>
      )}
    </div>
  );
}

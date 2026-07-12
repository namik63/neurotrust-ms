import { useDropzone } from "react-dropzone";

function isAllowedName(name: string, kind: "nifti" | "anatomy" | "metadata") {
  const lower = name.toLowerCase();
  if (kind === "metadata") return lower.endsWith(".csv") || lower.endsWith(".json") || lower.endsWith(".txt");
  if (kind === "anatomy") return lower.endsWith(".nii") || lower.endsWith(".nii.gz") || lower.endsWith(".mgz") || lower.endsWith(".txt") || lower.endsWith(".json") || lower.endsWith(".csv");
  return lower.endsWith(".nii") || lower.endsWith(".nii.gz");
}

export function DropzoneField({
  label,
  detail,
  files,
  onFiles,
  multiple = false,
  required = true,
  kind = "nifti",
  directory = false,
}: {
  label: string;
  detail: string;
  files: File[];
  onFiles: (files: File[]) => void;
  multiple?: boolean;
  required?: boolean;
  kind?: "nifti" | "anatomy" | "metadata";
  directory?: boolean;
}) {
  const ready = required ? files.length > 0 : true;
  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    multiple,
    onDrop: (accepted) => onFiles(multiple ? accepted : accepted.slice(0, 1)),
    validator: (file) => isAllowedName(file.name, kind) ? null : { code: "file-invalid-type", message: "Unsupported file type" },
  });

  return (
    <div className={`dropzone-card ${isDragActive ? "dragging" : ""} ${ready ? "ready" : "missing"}`} {...getRootProps()}>
      <input
        {...getInputProps({
          accept: kind === "metadata" ? ".csv,.json,.txt" : kind === "anatomy" ? ".nii,.nii.gz,.gz,.mgz,.txt,.json,.csv" : ".nii,.nii.gz,.gz",
          ...(directory ? { webkitdirectory: "true", directory: "true" } : {}),
        } as any)}
      />
      <div>
        <span className="drop-label">{label}</span>
        <p>{detail}</p>
      </div>
      <div className="drop-status">
        <strong>{files.length ? `${files.length} selected` : required ? "missing" : "optional"}</strong>
        <small>{files.length ? files.slice(0, 2).map((f: any) => f.webkitRelativePath || f.path || f.name).join(", ") : directory ? "Drag subject folders or click to choose a folder" : "Drag files here or click to browse"}</small>
        {files.length > 0 && (
          <button
            type="button"
            className="drop-clear"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onFiles([]);
            }}
          >
            Clear upload
          </button>
        )}
      </div>
      {fileRejections.length > 0 && <em>Rejected: unsupported file type</em>}
    </div>
  );
}

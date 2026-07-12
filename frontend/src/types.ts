export type AppView = "home" | "workspace" | "processing" | "results" | "history";
export type ValidationMode = "simple_demo" | "five_case_demo" | "batch";
export type ResultTab = "overview" | "watchlist" | "anatomy" | "reliability" | "improvement" | "edgeCases" | "viewer" | "vault" | "exports" | "sizeLocation" | "hardCases" | "lesions" | "modelComparison";

export type ValidationResult = {
  mode?: string;
  project_id?: string;
  case_id?: string;
  product?: string;
  demo?: Record<string, any>;
  qc?: {
    status?: string;
    errors?: string[];
    warnings?: string[];
    geometry?: any[];
    files?: any[];
    masks?: any[];
    anatomy?: any[];
    batch?: any[];
    viewer?: any[];
    export?: any[];
  };
  subject_metrics?: Record<string, any>;
  lesion_metrics?: any[];
  prediction_lesions?: any[];
  cluster_metrics?: any[];
  case_results?: any[];
  expert_variability?: any[];
  blindspots?: any[];
  radiologist_watchlist?: any[];
  location_metrics?: any[];
  size_location_metrics?: any[];
  location_topology_metrics?: any[];
  hard_case_metrics?: any[];
  hard_case_summary?: any;
  reliability_metrics?: any[];
  reliability_summary?: any;
  case_viewers?: Array<{ case_id: string; viewer: ValidationResult["viewer"]; preview_png?: string; case_json?: string }>;
  model_comparison?: any;
  anatomy_qc?: any;
  anatomy_method_card?: any;
  failure_fingerprint?: any;
  trust_gap_summary?: string;
  method_badges?: string[];
  dice_trap_detector?: any;
  prediction_only_burden_detector?: any;
  model_passport?: any;
  deployment_recommendation?: any;
  downloads?: Record<string, string>;
  viewer?: {
    mode?: string;
    label?: string;
    base_volume_url?: string;
    base_volumes?: Array<{ key: string; label: string; url: string }>;
    overlays?: Array<{ key: string; label: string; url: string; color: string; colormap?: string; opacity?: number }>;
    jump_targets?: Array<{ label: string; lesion_id?: number; slice?: number; centroid_voxel?: number[]; reason?: string; severity?: string }>;
    layers?: Record<string, string>;
    legend?: Record<string, string>;
  };
  executive_summary?: string;
  limitations?: string[];
};

export type ValidationHistoryItem = {
  run_id: string;
  created_at: string;
  project_id?: string;
  case_id?: string;
  mode?: string;
  model_name?: string;
  status?: string;
  source?: string;
  summary?: Record<string, any>;
};

export type AccessSession = {
  email: string;
  token: string;
  expires_at?: string;
  welcome_back?: boolean;
  login_count?: number;
  recent_validations?: ValidationHistoryItem[];
  safety_privacy?: Record<string, any>;
};

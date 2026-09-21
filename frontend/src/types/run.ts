export type RunStatus = 'running' | 'paused' | 'completed' | 'stopped' | 'failed';

export type StopReason = 
  | 'converged'
  | 'stalled'
  | 'hit_safety_ceiling'
  | 'errored'
  | 'user_rejected'
  | 'user_stopped'
  | 'user_paused'
  | 'human_approval_required'
  | 'graph_interrupted'
  | string;

export interface PipelineRun {
  run_id: string;
  created_at?: string;
  updated_at?: string;
  status: RunStatus;
  stop_reason?: StopReason;
  dataset_path: string;
  mode: 'full_pipeline' | 'eda_only' | string;
  guided_mode: boolean | number;
  best_score?: number | null;
  baseline_score?: number | null;
  metric_name?: string | null;
  total_attempts: number;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
  duration_s: number;
  error_count: number;
  is_baseline?: boolean | number;
  tags?: string[] | string;
  labels?: Record<string, string> | string;
  meta_json?: string;
}

export interface RunCreatePayload {
  dataset_path: string;
  mode?: 'full_pipeline' | 'eda_only';
  guided_mode?: boolean;
  metric_name?: string;
  tags?: string[];
  labels?: Record<string, string>;
  user_instructions?: string;
  is_baseline?: boolean;
  baseline_score?: number;
}

export interface ResumePayload {
  approval_status: 'approved' | 'modify' | 'reject';
  modifications?: string;
}

export interface DatasetPreviewResponse {
  run_id: string;
  dataset_path: string;
  is_transformed: boolean;
  columns: string[];
  total_rows: number;
  total_columns: number;
  preview_rows: Record<string, any>[];
}

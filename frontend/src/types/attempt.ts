export interface ModelAttempt {
  seq?: number;
  attempt: number;
  tier: number;
  agent: string;
  model_name: string;
  cv_score: number | null;
  cv_score_str: string;
  delta: number | null;
  delta_str: string;
  decision: string;
  reason: string;
  duration_ms: number;
  has_code: boolean;
  has_diff: boolean;
  has_error: boolean;
  error_signature?: string;
  ts: string;
  // Extended fields for code preview
  code?: string | null;
  stdout?: string | null;
  stderr?: string | null;
  iteration?: number | null;
  success?: boolean;
  failure_reason?: string | null;
  metric_name?: string | null;
  is_improvement?: boolean | null;
}

export interface RunIteration {
  seq?: number;
  ts?: string;
  agent?: string;
  event_type?: string;
  iteration?: number | null;
  model_family?: string | null;
  task_spec?: string | null;
  score?: number | null;
  cv_score_str?: string;
  metric_name?: string | null;
  is_improvement?: boolean | null;
  success?: boolean;
  failure_reason?: string | null;
  code?: string | null;
  stdout?: string | null;
  stderr?: string | null;
  duration_ms?: number | null;
  tier?: number | null;
  decision?: string | null;
}

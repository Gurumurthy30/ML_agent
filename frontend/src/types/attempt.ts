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
}

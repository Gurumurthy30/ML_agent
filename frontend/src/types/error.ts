export interface ErrorGroup {
  error_signature: string;
  count: number;
  agent?: string;
  first_seen: string;
  last_seen: string;
  message: string;
  traceback?: string;
  consecutive_repeat: boolean;
}

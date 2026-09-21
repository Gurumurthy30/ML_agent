import { PipelineRun, RunCreatePayload, ResumePayload } from '../types/run';
import { ModelAttempt } from '../types/attempt';
import { ErrorGroup } from '../types/error';

const API_BASE = '';

export async function createRun(payload: RunCreatePayload): Promise<PipelineRun> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Failed to create run: ${res.status}`);
  }
  return res.json();
}

export async function listRuns(filters?: { tag?: string; is_baseline?: boolean; limit?: number }): Promise<PipelineRun[]> {
  const params = new URLSearchParams();
  if (filters?.limit) params.set('limit', String(filters.limit));
  if (filters?.tag) params.set('tag', filters.tag);
  if (filters?.is_baseline !== undefined) params.set('is_baseline', String(filters.is_baseline));

  const qs = params.toString();
  const url = `${API_BASE}/runs${qs ? `?${qs}` : ''}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to list runs: ${res.statusText}`);
  }
  return res.json();
}

export async function getRun(runId: string): Promise<PipelineRun> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) {
    throw new Error(`Failed to get run ${runId}: ${res.statusText}`);
  }
  return res.json();
}

export async function getRunAttempts(runId: string): Promise<ModelAttempt[]> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/attempts`);
  if (!res.ok) {
    throw new Error(`Failed to get attempts for ${runId}: ${res.statusText}`);
  }
  return res.json();
}

export async function getRunErrors(runId: string): Promise<ErrorGroup[]> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/errors`);
  if (!res.ok) {
    throw new Error(`Failed to get errors for ${runId}: ${res.statusText}`);
  }
  return res.json();
}

export async function resumeRun(runId: string, payload: ResumePayload): Promise<{ run_id: string; status: string; decision: string }> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const errorObj = new Error(err.detail || `Failed to resume run: ${res.status}`);
    (errorObj as any).status = res.status;
    throw errorObj;
  }
  return res.json();
}

export async function pauseRun(runId: string): Promise<{ run_id: string; control: string }> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/pause`, { method: 'POST' });
  if (!res.ok) throw new Error(`Pause failed: ${res.statusText}`);
  return res.json();
}

export async function unpauseRun(runId: string): Promise<{ run_id: string; control: string }> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/unpause`, { method: 'POST' });
  if (!res.ok) throw new Error(`Unpause failed: ${res.statusText}`);
  return res.json();
}

export async function stopRun(runId: string): Promise<{ run_id: string; control: string }> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/stop`, { method: 'POST' });
  if (!res.ok) throw new Error(`Stop failed: ${res.statusText}`);
  return res.json();
}

export async function escapeRun(runId: string): Promise<{ run_id: string; control: string }> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/escape`, { method: 'POST' });
  if (!res.ok) throw new Error(`Escape failed: ${res.statusText}`);
  return res.json();
}

export async function updateRunTags(runId: string, tags: string[]): Promise<PipelineRun> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tags }),
  });
  if (!res.ok) throw new Error(`Update tags failed: ${res.statusText}`);
  return res.json();
}

export async function setRunBaseline(runId: string, is_baseline: boolean, baseline_score?: number): Promise<PipelineRun> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}/baseline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_baseline, baseline_score }),
  });
  if (!res.ok) throw new Error(`Update baseline failed: ${res.statusText}`);
  return res.json();
}

export async function compareRuns(runA: string, runB: string): Promise<any> {
  const res = await fetch(`${API_BASE}/runs/${encodeURIComponent(runA)}/compare/${encodeURIComponent(runB)}`);
  if (!res.ok) throw new Error(`Compare failed: ${res.statusText}`);
  return res.json();
}

export function getExportUrl(runId: string): string {
  return `${API_BASE}/runs/${encodeURIComponent(runId)}/export`;
}

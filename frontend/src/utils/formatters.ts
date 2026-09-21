import { RunStatus, StopReason } from '../types/run';

export function formatScore(score?: number | null): string {
  if (score === null || score === undefined) return '—';
  return score.toFixed(4);
}

export function formatDuration(seconds?: number): string {
  if (!seconds || seconds <= 0) return '0s';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

export function formatCost(costUsd?: number): string {
  if (!costUsd || costUsd <= 0) return '$0.000';
  return `$${costUsd.toFixed(4)}`;
}

export function formatTokens(tokens?: number): string {
  if (!tokens || tokens <= 0) return '0';
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
  return tokens.toLocaleString();
}

export function getStatusColor(status: RunStatus, stopReason?: StopReason): {
  dot: string;
  badgeBg: string;
  badgeText: string;
  label: string;
} {
  if (status === 'running') {
    return {
      dot: 'bg-cyan-400 animate-pulse-fast',
      badgeBg: 'bg-cyan-950/70 border-cyan-500/40',
      badgeText: 'text-cyan-300',
      label: 'Running',
    };
  }

  if (status === 'paused') {
    return {
      dot: 'bg-amber-400 animate-pulse',
      badgeBg: 'bg-amber-950/70 border-amber-500/40',
      badgeText: 'text-amber-300',
      label: stopReason === 'human_approval_required' ? 'Needs Approval' : 'Paused',
    };
  }

  // Terminal states with distinct 5-way stop_reason mapping
  if (stopReason === 'converged') {
    return {
      dot: 'bg-emerald-400',
      badgeBg: 'bg-emerald-950/70 border-emerald-500/40',
      badgeText: 'text-emerald-300',
      label: 'Converged',
    };
  }

  if (stopReason === 'stalled') {
    return {
      dot: 'bg-orange-400',
      badgeBg: 'bg-orange-950/70 border-orange-500/40',
      badgeText: 'text-orange-300',
      label: 'Stalled',
    };
  }

  if (stopReason === 'hit_safety_ceiling') {
    return {
      dot: 'bg-purple-400',
      badgeBg: 'bg-purple-950/70 border-purple-500/40',
      badgeText: 'text-purple-300',
      label: 'Ceiling Hit',
    };
  }

  if (status === 'failed' || stopReason === 'errored') {
    return {
      dot: 'bg-rose-500',
      badgeBg: 'bg-rose-950/70 border-rose-500/40',
      badgeText: 'text-rose-300',
      label: 'Errored',
    };
  }

  if (status === 'stopped' || stopReason === 'user_rejected' || stopReason === 'user_stopped') {
    return {
      dot: 'bg-slate-400',
      badgeBg: 'bg-slate-800/80 border-slate-600/40',
      badgeText: 'text-slate-300',
      label: 'Stopped',
    };
  }

  if (status === 'completed') {
    return {
      dot: 'bg-emerald-400',
      badgeBg: 'bg-emerald-950/70 border-emerald-500/40',
      badgeText: 'text-emerald-300',
      label: 'Completed',
    };
  }

  return {
    dot: 'bg-slate-500',
    badgeBg: 'bg-slate-800 border-slate-600',
    badgeText: 'text-slate-300',
    label: status,
  };
}

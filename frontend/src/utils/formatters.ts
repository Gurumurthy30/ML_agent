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
      dot: 'bg-violet-500 animate-pulse',
      badgeBg: 'bg-violet-50 border-violet-200',
      badgeText: 'text-violet-700',
      label: 'Running',
    };
  }

  if (status === 'paused') {
    return {
      dot: 'bg-amber-500 animate-pulse',
      badgeBg: 'bg-amber-50 border-amber-200',
      badgeText: 'text-amber-700',
      label: stopReason === 'human_approval_required' ? 'Needs Approval' : 'Paused',
    };
  }

  // Terminal states with distinct 5-way stop_reason mapping
  if (stopReason === 'converged') {
    return {
      dot: 'bg-emerald-500',
      badgeBg: 'bg-emerald-50 border-emerald-200',
      badgeText: 'text-emerald-700',
      label: 'Converged',
    };
  }

  if (stopReason === 'stalled') {
    return {
      dot: 'bg-orange-500',
      badgeBg: 'bg-orange-50 border-orange-200',
      badgeText: 'text-orange-700',
      label: 'Stalled',
    };
  }

  if (stopReason === 'hit_safety_ceiling') {
    return {
      dot: 'bg-purple-500',
      badgeBg: 'bg-purple-50 border-purple-200',
      badgeText: 'text-purple-700',
      label: 'Ceiling Hit',
    };
  }

  if (status === 'failed' || stopReason === 'errored') {
    return {
      dot: 'bg-rose-500',
      badgeBg: 'bg-rose-50 border-rose-200',
      badgeText: 'text-rose-700',
      label: 'Errored',
    };
  }

  if (status === 'stopped' || stopReason === 'user_rejected' || stopReason === 'user_stopped') {
    return {
      dot: 'bg-stone-400',
      badgeBg: 'bg-stone-100 border-stone-200',
      badgeText: 'text-stone-600',
      label: 'Stopped',
    };
  }

  if (status === 'completed') {
    return {
      dot: 'bg-emerald-500',
      badgeBg: 'bg-emerald-50 border-emerald-200',
      badgeText: 'text-emerald-700',
      label: 'Completed',
    };
  }

  return {
    dot: 'bg-stone-400',
    badgeBg: 'bg-stone-100 border-stone-200',
    badgeText: 'text-stone-600',
    label: status,
  };
}

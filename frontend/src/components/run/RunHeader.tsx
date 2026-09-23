import React, { useState } from 'react';
import { Award, Tag, Plus, X, Radio, Clock, DollarSign, Cpu, AlertOctagon, AlertTriangle, ArrowRight } from 'lucide-react';
import { PipelineRun } from '../../types/run';
import { RunControls } from './RunControls';
import { formatScore, formatCost, formatTokens, formatDuration, getStatusColor } from '../../utils/formatters';
import { updateRunTags, setRunBaseline } from '../../services/api';

interface RunHeaderProps {
  run: PipelineRun;
  onRefresh: () => void;
  onOpenCompare: () => void;
  isConnectedLive: boolean;
  isReconnecting: boolean;
  onSelectTab?: (tab: 'flow' | 'dataset' | 'feature_plan' | 'leaderboard' | 'all_attempts' | 'judge' | 'logs' | 'errors' | 'report' | 'debug') => void;
  errorsCount?: number;
}

export const RunHeader: React.FC<RunHeaderProps> = ({
  run,
  onRefresh,
  onOpenCompare,
  isConnectedLive,
  isReconnecting,
  onSelectTab,
  errorsCount = 0,
}) => {
  const [newTagInput, setNewTagInput] = useState('');
  const [showTagInput, setShowTagInput] = useState(false);
  const [isUpdatingTag, setIsUpdatingTag] = useState(false);
  const [dismissedAlert, setDismissedAlert] = useState(false);

  // Parse tags list
  let currentTags: string[] = [];
  if (Array.isArray(run.tags)) {
    currentTags = run.tags;
  } else if (typeof run.tags === 'string') {
    try {
      currentTags = JSON.parse(run.tags);
    } catch {
      currentTags = [];
    }
  }

  const handleAddTag = async () => {
    if (!newTagInput.trim() || isUpdatingTag) return;
    const tag = newTagInput.trim();
    if (currentTags.includes(tag)) {
      setNewTagInput('');
      setShowTagInput(false);
      return;
    }
    setIsUpdatingTag(true);
    try {
      await updateRunTags(run.run_id, [...currentTags, tag]);
      setNewTagInput('');
      setShowTagInput(false);
      onRefresh();
    } catch (err) {
      console.error('Failed to add tag:', err);
    } finally {
      setIsUpdatingTag(false);
    }
  };

  const handleRemoveTag = async (tagToRemove: string) => {
    if (isUpdatingTag) return;
    setIsUpdatingTag(true);
    try {
      const updated = currentTags.filter((t) => t !== tagToRemove);
      await updateRunTags(run.run_id, updated);
      onRefresh();
    } catch (err) {
      console.error('Failed to remove tag:', err);
    } finally {
      setIsUpdatingTag(false);
    }
  };

  const handleToggleBaseline = async () => {
    try {
      const willBeBaseline = !Boolean(run.is_baseline);
      await setRunBaseline(run.run_id, willBeBaseline, run.best_score ?? undefined);
      onRefresh();
    } catch (err) {
      console.error('Failed to toggle baseline:', err);
    }
  };

  const statusConfig = getStatusColor(run.status, run.stop_reason);

  const isFailed = run.status === 'failed';
  const hasStopReason = Boolean(run.stop_reason && run.stop_reason !== 'converged');
  const hasActiveAlert = (isFailed || hasStopReason || errorsCount > 0 || (run.error_count && run.error_count > 0)) && !dismissedAlert;

  const getStopReasonExplanation = (reason?: string) => {
    switch (reason) {
      case 'crashed':
        return 'Execution crashed due to an unhandled exception in an agent or script. Inspect error trace below.';
      case 'hit_safety_ceiling':
        return 'Run halted after exceeding the maximum global iteration safety ceiling (budget safeguard).';
      case 'stalled':
        return 'Pipeline halted after multiple consecutive attempts failed to produce metric improvement.';
      case 'errored':
        return 'Execution halted due to terminal errors encountered during code generation or evaluation.';
      case 'user_rejected':
        return 'Human operator rejected the candidate modifications or proposals.';
      case 'user_stopped':
        return 'Pipeline run was manually stopped by operator.';
      case 'human_approval_required':
        return 'Pipeline paused awaiting operator review in the Approval Queue.';
      default:
        return reason ? `Run terminated with condition: ${reason}` : 'Pipeline encountered errors during execution.';
    }
  };

  return (
    <div className="p-4 border-b border-[#E8E6DF] dark:border-slate-800 bg-white dark:bg-[#0F172A] space-y-3 transition-colors">
      {/* Top row: Title, status, and controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="space-y-1">
            <div className="flex items-center space-x-2.5">
              <h2 className="text-base font-semibold font-mono text-stone-900 dark:text-slate-100 tracking-tight">
                {run.run_id}
              </h2>

              {/* Status Badge */}
              <div
                className={`flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full border text-xs font-medium ${statusConfig.badgeBg} ${statusConfig.badgeText}`}
              >
                <span className={`w-2 h-2 rounded-full ${statusConfig.dot}`} />
                <span>{statusConfig.label}</span>
              </div>

              {/* Live SSE indicator */}
              {isConnectedLive && (
                <div className="flex items-center space-x-1 text-[11px] font-mono text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                  <span>LIVE</span>
                </div>
              )}
              {isReconnecting && (
                <div className="flex items-center space-x-1 text-[11px] font-mono text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 px-2 py-0.5 rounded-full border border-amber-200 dark:border-amber-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                  <span>Reconnecting...</span>
                </div>
              )}
            </div>

            <p className="text-xs text-stone-500 dark:text-slate-400">
              Dataset: <span className="font-mono text-stone-700 dark:text-slate-300 font-medium">{run.dataset_path}</span> &bull; Mode:{' '}
              <span className="font-medium text-stone-800 dark:text-slate-200">{run.mode}</span>
              {Boolean(run.guided_mode) && <span className="text-amber-600 dark:text-amber-400 font-medium ml-1">(Guided)</span>}
            </p>
          </div>
        </div>

        {/* Controls (Pause, Unpause, Stop, Escape, Compare, Export) */}
        <RunControls
          runId={run.run_id}
          status={run.status}
          onControlTriggered={onRefresh}
          onOpenCompare={onOpenCompare}
        />
      </div>

      {/* Second row: Quick Telemetry Chips & Tags/Baseline */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2.5 border-t border-[#E8E6DF] dark:border-slate-800 text-xs">
        {/* Metric Cards */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5 bg-[#F5F4EE] dark:bg-slate-800/70 border border-[#E8E6DF] dark:border-slate-700 px-2.5 py-1 rounded-lg">
            <span className="text-stone-500 dark:text-slate-400 text-[11px]">Best Metric:</span>
            <span className="font-mono font-bold text-emerald-700 dark:text-emerald-400">
              {formatScore(run.best_score)}
            </span>
            {run.metric_name && (
              <span className="text-[10px] text-stone-500 dark:text-slate-400 font-mono">({run.metric_name})</span>
            )}
          </div>

          <div className="flex items-center space-x-1.5 bg-[#F5F4EE] dark:bg-slate-800/70 border border-[#E8E6DF] dark:border-slate-700 px-2.5 py-1 rounded-lg text-stone-700 dark:text-slate-300 font-mono">
            <Clock className="w-3.5 h-3.5 text-stone-400 dark:text-slate-500" />
            <span>{formatDuration(run.duration_s)}</span>
          </div>

          <div className="flex items-center space-x-1.5 bg-[#F5F4EE] dark:bg-slate-800/70 border border-[#E8E6DF] dark:border-slate-700 px-2.5 py-1 rounded-lg text-stone-700 dark:text-slate-300 font-mono">
            <DollarSign className="w-3.5 h-3.5 text-stone-400 dark:text-slate-500" />
            <span>{formatCost(run.total_cost_usd)}</span>
          </div>

          <div className="flex items-center space-x-1.5 bg-[#F5F4EE] dark:bg-slate-800/70 border border-[#E8E6DF] dark:border-slate-700 px-2.5 py-1 rounded-lg text-stone-700 dark:text-slate-300 font-mono">
            <Cpu className="w-3.5 h-3.5 text-stone-400 dark:text-slate-500" />
            <span>{formatTokens(run.total_tokens_in + run.total_tokens_out)} toks</span>
          </div>
        </div>

        {/* Tags & Baseline Toggle */}
        <div className="flex items-center space-x-2">
          {/* Baseline Toggle */}
          <button
            onClick={handleToggleBaseline}
            className={`flex items-center space-x-1 px-2.5 py-1 rounded-lg border transition font-medium text-xs ${
              Boolean(run.is_baseline)
                ? 'bg-amber-50 dark:bg-amber-950/40 border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-300'
                : 'bg-white dark:bg-slate-800 border-stone-200 dark:border-slate-700 text-stone-600 dark:text-slate-300 hover:bg-stone-50 dark:hover:bg-slate-700'
            }`}
          >
            <Award className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
            <span>{Boolean(run.is_baseline) ? 'Baseline Set' : 'Set Baseline'}</span>
          </button>

          {/* Tags list */}
          <div className="flex items-center space-x-1.5">
            {currentTags.map((tag) => (
              <span
                key={tag}
                className="flex items-center space-x-1 px-2 py-0.5 rounded-md bg-stone-100 dark:bg-slate-800 border border-stone-200 dark:border-slate-700 text-stone-700 dark:text-slate-300 font-mono text-[11px]"
              >
                <span>#{tag}</span>
                <button
                  onClick={() => handleRemoveTag(tag)}
                  className="hover:text-rose-600 dark:hover:text-rose-400 ml-0.5"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </span>
            ))}

            {/* Add tag button / input */}
            {showTagInput ? (
              <div className="flex items-center space-x-1">
                <input
                  type="text"
                  placeholder="tag..."
                  value={newTagInput}
                  onChange={(e) => setNewTagInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAddTag();
                    if (e.key === 'Escape') setShowTagInput(false);
                  }}
                  autoFocus
                  className="w-20 px-1.5 py-0.5 text-xs bg-white dark:bg-slate-800 text-stone-800 dark:text-slate-100 border border-stone-300 dark:border-slate-600 rounded focus:outline-none"
                />
                <button
                  onClick={handleAddTag}
                  disabled={isUpdatingTag}
                  className="px-1.5 py-0.5 bg-stone-900 dark:bg-violet-600 text-white rounded text-[11px]"
                >
                  Add
                </button>
                <button
                  onClick={() => setShowTagInput(false)}
                  className="text-stone-400 hover:text-stone-600 dark:hover:text-stone-200 text-xs px-1"
                >
                  ✕
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowTagInput(true)}
                className="flex items-center space-x-0.5 px-2 py-0.5 rounded-lg border border-dashed border-stone-300 dark:border-slate-700 text-stone-500 dark:text-slate-400 hover:text-stone-800 dark:hover:text-slate-200 hover:border-stone-400 text-xs transition"
              >
                <Plus className="w-3 h-3" />
                <span>Tag</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Third row: ERROR / FAILURE NOTIFICATION TEXT BOX BANNER */}
      {hasActiveAlert && (
        <div
          role="alert"
          className="relative rounded-xl border border-rose-300 dark:border-rose-900/70 bg-rose-50/90 dark:bg-rose-950/40 p-3.5 text-rose-950 dark:text-rose-200 shadow-xs transition"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start space-x-3">
              <div className="w-8 h-8 rounded-lg bg-rose-100 dark:bg-rose-900/60 border border-rose-200 dark:border-rose-800 flex items-center justify-center flex-shrink-0 mt-0.5">
                <AlertOctagon className="w-4 h-4 text-rose-600 dark:text-rose-400 animate-pulse" />
              </div>
              <div className="space-y-1.5 flex-1 min-w-0">
                <div className="flex items-center flex-wrap gap-2">
                  <span className="font-semibold text-xs tracking-tight uppercase text-rose-800 dark:text-rose-300 font-mono">
                    {isFailed ? 'Execution Failure Alert' : 'Pipeline Execution Notice'}
                  </span>
                  {run.stop_reason && (
                    <span className="font-mono text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-rose-200/80 dark:bg-rose-900/80 text-rose-900 dark:text-rose-200 border border-rose-300 dark:border-rose-800">
                      Reason: {run.stop_reason}
                    </span>
                  )}
                  {errorsCount > 0 && (
                    <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-800">
                      {errorsCount} error signature{errorsCount > 1 ? 's' : ''}
                    </span>
                  )}
                </div>

                {/* Error Text Box */}
                <div className="p-2.5 rounded-lg bg-white/80 dark:bg-slate-900/90 border border-rose-200 dark:border-rose-900/60 font-mono text-[11px] leading-relaxed text-rose-900 dark:text-rose-300 whitespace-pre-wrap overflow-x-auto max-h-36">
                  {getStopReasonExplanation(run.stop_reason)}
                </div>

                {/* Quick tab jump action buttons */}
                {onSelectTab && (
                  <div className="flex items-center space-x-2 pt-1">
                    <button
                      onClick={() => onSelectTab('logs')}
                      className="inline-flex items-center space-x-1 px-2.5 py-1 text-xs font-medium rounded-md bg-rose-600 hover:bg-rose-700 text-white transition shadow-2xs font-sans"
                    >
                      <span>Inspect Logs &amp; LLM Texts</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                    {errorsCount > 0 && (
                      <button
                        onClick={() => onSelectTab('errors')}
                        className="inline-flex items-center space-x-1 px-2.5 py-1 text-xs font-medium rounded-md bg-white dark:bg-slate-800 hover:bg-rose-100 dark:hover:bg-slate-700 text-rose-800 dark:text-rose-300 border border-rose-200 dark:border-slate-700 transition font-sans"
                      >
                        <span>View Errors Ledger ({errorsCount})</span>
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Dismiss Button */}
            <button
              onClick={() => setDismissedAlert(true)}
              className="text-rose-400 hover:text-rose-600 dark:hover:text-rose-200 p-1 rounded-md transition"
              title="Dismiss alert banner"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

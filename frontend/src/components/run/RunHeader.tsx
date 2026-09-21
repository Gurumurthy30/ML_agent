import React, { useState } from 'react';
import { Award, Tag, Plus, X, Radio, Clock, DollarSign, Cpu } from 'lucide-react';
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
}

export const RunHeader: React.FC<RunHeaderProps> = ({
  run,
  onRefresh,
  onOpenCompare,
  isConnectedLive,
  isReconnecting,
}) => {
  const [newTagInput, setNewTagInput] = useState('');
  const [showTagInput, setShowTagInput] = useState(false);
  const [isUpdatingTag, setIsUpdatingTag] = useState(false);

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

  return (
    <div className="p-4 border-b border-slate-800 bg-slate-900/40 space-y-3">
      {/* Top row: Title, status, and controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <div className="space-y-0.5">
            <div className="flex items-center space-x-2.5">
              <h2 className="text-base font-bold font-mono text-slate-100 tracking-tight">
                {run.run_id}
              </h2>

              {/* Status Badge */}
              <div
                className={`flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full border text-xs font-semibold ${statusConfig.badgeBg} ${statusConfig.badgeText}`}
              >
                <span className={`w-2 h-2 rounded-full ${statusConfig.dot}`} />
                <span>{statusConfig.label}</span>
              </div>

              {/* Live SSE indicator */}
              {isConnectedLive && (
                <div className="flex items-center space-x-1 text-[11px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-500/30">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                  <span>LIVE SSE</span>
                </div>
              )}
              {isReconnecting && (
                <div className="flex items-center space-x-1 text-[11px] font-mono text-amber-400 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-500/30">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                  <span>Reconnecting...</span>
                </div>
              )}
            </div>

            <p className="text-xs text-slate-400">
              Dataset: <span className="font-mono text-slate-300">{run.dataset_path}</span> &bull; Mode:{' '}
              <span className="font-semibold text-slate-200">{run.mode}</span>
              {Boolean(run.guided_mode) && <span className="text-amber-400 ml-1">(Guided)</span>}
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
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/60 text-xs">
        {/* Metric Cards */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-1.5 bg-slate-950/60 border border-slate-800 px-2.5 py-1 rounded">
            <span className="text-slate-400 text-[11px]">Best Metric:</span>
            <span className="font-mono font-bold text-emerald-400">
              {formatScore(run.best_score)}
            </span>
            {run.metric_name && (
              <span className="text-[10px] text-slate-400 font-mono">({run.metric_name})</span>
            )}
          </div>

          <div className="flex items-center space-x-1.5 bg-slate-950/60 border border-slate-800 px-2.5 py-1 rounded text-slate-300 font-mono">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>{formatDuration(run.duration_s)}</span>
          </div>

          <div className="flex items-center space-x-1.5 bg-slate-950/60 border border-slate-800 px-2.5 py-1 rounded text-slate-300 font-mono">
            <DollarSign className="w-3.5 h-3.5 text-slate-400" />
            <span>{formatCost(run.total_cost_usd)}</span>
          </div>

          <div className="flex items-center space-x-1.5 bg-slate-950/60 border border-slate-800 px-2.5 py-1 rounded text-slate-300 font-mono">
            <Cpu className="w-3.5 h-3.5 text-slate-400" />
            <span>{formatTokens(run.total_tokens_in + run.total_tokens_out)} toks</span>
          </div>
        </div>

        {/* Tags & Baseline Toggle */}
        <div className="flex items-center space-x-2">
          {/* Baseline Toggle */}
          <button
            onClick={handleToggleBaseline}
            className={`flex items-center space-x-1 px-2.5 py-1 rounded border transition font-medium ${
              Boolean(run.is_baseline)
                ? 'bg-amber-950/80 border-amber-500 text-amber-300'
                : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:text-slate-200'
            }`}
          >
            <Award className="w-3.5 h-3.5" />
            <span>{Boolean(run.is_baseline) ? 'Baseline Set' : 'Set Baseline'}</span>
          </button>

          {/* Tags list */}
          <div className="flex items-center space-x-1.5">
            {currentTags.map((tag) => (
              <span
                key={tag}
                className="flex items-center space-x-1 px-2 py-0.5 rounded bg-indigo-950/50 border border-indigo-500/40 text-indigo-300 font-mono text-[11px]"
              >
                <span>#{tag}</span>
                <button
                  onClick={() => handleRemoveTag(tag)}
                  className="hover:text-rose-400 ml-0.5"
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
                  className="bg-slate-950 border border-slate-700 text-slate-200 px-1.5 py-0.5 text-xs rounded w-20 focus:outline-none focus:border-indigo-500"
                />
                <button
                  onClick={handleAddTag}
                  className="px-1.5 py-0.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-[10px]"
                >
                  Save
                </button>
                <button
                  onClick={() => setShowTagInput(false)}
                  className="text-slate-400 hover:text-slate-200"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowTagInput(true)}
                className="flex items-center space-x-1 text-slate-400 hover:text-slate-200 text-xs px-1.5 py-0.5 rounded border border-dashed border-slate-700"
              >
                <Plus className="w-3 h-3" />
                <span>Tag</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

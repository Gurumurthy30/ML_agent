import React, { useState } from 'react';
import { Search, Tag, Award, Sparkles, Filter, ChevronRight } from 'lucide-react';
import { PipelineRun } from '../../types/run';
import { formatScore, formatDuration, getStatusColor } from '../../utils/formatters';

interface RunListSidebarProps {
  runs: PipelineRun[];
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  isLoading: boolean;
  activeTag: string | null;
  onSelectTag: (tag: string | null) => void;
  onlyBaseline: boolean;
  onToggleOnlyBaseline: (val: boolean) => void;
}

export const RunListSidebar: React.FC<RunListSidebarProps> = ({
  runs,
  selectedRunId,
  onSelectRun,
  isLoading,
  activeTag,
  onSelectTag,
  onlyBaseline,
  onToggleOnlyBaseline,
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  // Extract all unique tags across runs
  const allTags = Array.from(
    new Set(
      runs.flatMap((r) => {
        if (!r.tags) return [];
        if (Array.isArray(r.tags)) return r.tags;
        try {
          const parsed = JSON.parse(r.tags);
          return Array.isArray(parsed) ? parsed : [];
        } catch {
          return [];
        }
      })
    )
  );

  // Filter runs by search, tag, and baseline
  const filteredRuns = runs.filter((r) => {
    if (onlyBaseline && !r.is_baseline) return false;
    if (activeTag) {
      let rTags: string[] = [];
      if (Array.isArray(r.tags)) rTags = r.tags;
      else {
        try {
          rTags = JSON.parse(r.tags || '[]');
        } catch {
          rTags = [];
        }
      }
      if (!rTags.includes(activeTag)) return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchId = r.run_id.toLowerCase().includes(q);
      const matchData = (r.dataset_path || '').toLowerCase().includes(q);
      if (!matchId && !matchData) return false;
    }
    return true;
  });

  return (
    <aside className="w-80 h-full border-r border-slate-800 bg-slate-900/60 flex flex-col flex-shrink-0 select-none">
      {/* Search and Filters Header */}
      <div className="p-3 border-b border-slate-800 space-y-2.5">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search run ID or dataset..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950/70 text-slate-200 pl-9 pr-3 py-1.5 text-xs rounded-md border border-slate-800 focus:outline-none focus:border-indigo-500 transition"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center space-x-2 text-[11px]">
          <button
            onClick={() => onToggleOnlyBaseline(!onlyBaseline)}
            className={`flex items-center space-x-1 px-2 py-1 rounded border transition ${
              onlyBaseline
                ? 'bg-amber-950/60 border-amber-500/50 text-amber-300'
                : 'bg-slate-800/40 border-slate-850 text-slate-400 hover:text-slate-200'
            }`}
          >
            <Award className="w-3 h-3" />
            <span>Baselines</span>
          </button>

          {allTags.length > 0 && (
            <div className="flex items-center space-x-1 overflow-x-auto max-w-[170px] no-scrollbar">
              {allTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => onSelectTag(activeTag === tag ? null : tag)}
                  className={`px-2 py-1 rounded border whitespace-nowrap transition ${
                    activeTag === tag
                      ? 'bg-indigo-950/70 border-indigo-500/60 text-indigo-300'
                      : 'bg-slate-800/40 border-slate-800 text-slate-400 hover:text-slate-200'
                  }`}
                >
                  #{tag}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Runs List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-850/60">
        {isLoading && runs.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">Loading pipeline runs...</div>
        ) : filteredRuns.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">
            No pipeline runs match the current criteria.
          </div>
        ) : (
          filteredRuns.map((run) => {
            const isSelected = run.run_id === selectedRunId;
            const statusConfig = getStatusColor(run.status, run.stop_reason);
            const datasetName = run.dataset_path ? run.dataset_path.split(/[\\/]/).pop() : 'data';

            return (
              <div
                key={run.run_id}
                onClick={() => onSelectRun(run.run_id)}
                className={`p-3 cursor-pointer transition relative ${
                  isSelected
                    ? 'bg-indigo-950/40 border-l-2 border-indigo-500'
                    : 'hover:bg-slate-800/40'
                }`}
              >
                {/* Header row: Status badge + run ID */}
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center space-x-2 truncate">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusConfig.dot}`} />
                    <span className="font-mono text-xs font-semibold text-slate-200 truncate">
                      {run.run_id.length > 20 ? `${run.run_id.slice(0, 18)}...` : run.run_id}
                    </span>
                  </div>
                  {Boolean(run.is_baseline) && (
                    <span className="flex items-center space-x-0.5 text-[10px] text-amber-400 bg-amber-950/60 border border-amber-500/30 px-1 rounded">
                      <Award className="w-2.5 h-2.5" />
                      <span>Base</span>
                    </span>
                  )}
                </div>

                {/* Sub row: dataset and mode */}
                <div className="flex items-center justify-between text-[11px] text-slate-400 mb-2">
                  <span className="truncate max-w-[150px]" title={run.dataset_path}>
                    📁 {datasetName}
                  </span>
                  <span className="font-mono text-[10px] text-slate-400">
                    {run.mode === 'eda_only' ? 'EDA' : 'Full'}
                    {Boolean(run.guided_mode) ? ' (Guided)' : ''}
                  </span>
                </div>

                {/* Metrics pill row */}
                <div className="flex items-center justify-between text-[11px] pt-1.5 border-t border-slate-850/60">
                  <div className="flex items-center space-x-1.5 font-mono">
                    <span className="text-slate-400">Score:</span>
                    <span className="font-semibold text-emerald-400">
                      {formatScore(run.best_score)}
                    </span>
                  </div>
                  <div className="flex items-center space-x-2 text-slate-400 font-mono text-[10px]">
                    <span>{formatDuration(run.duration_s)}</span>
                    <span className={`px-1.5 py-0.2 rounded border text-[9px] ${statusConfig.badgeBg} ${statusConfig.badgeText}`}>
                      {statusConfig.label}
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer stats */}
      <div className="p-2.5 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between bg-slate-950/30">
        <span>{filteredRuns.length} of {runs.length} runs</span>
        <span className="font-mono text-[10px]">Auto-refreshed</span>
      </div>
    </aside>
  );
};

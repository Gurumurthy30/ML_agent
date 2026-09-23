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
    <aside className="w-80 h-full border-r border-[#E8E6DF] dark:border-slate-800 bg-white dark:bg-[#0F172A] flex flex-col flex-shrink-0 select-none transition-colors">
      {/* Search and Filters Header */}
      <div className="p-3 border-b border-[#E8E6DF] dark:border-slate-800 space-y-2.5 bg-white dark:bg-[#0F172A]">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-stone-400 dark:text-slate-500" />
          <input
            type="text"
            placeholder="Search run ID or dataset..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#F5F4EE] dark:bg-slate-800/70 text-stone-800 dark:text-slate-100 placeholder-stone-400 dark:placeholder-slate-500 pl-9 pr-3 py-1.5 text-xs rounded-lg border border-[#E8E6DF] dark:border-slate-700 focus:outline-none focus:border-stone-400 dark:focus:border-slate-500 focus:bg-white dark:focus:bg-slate-800 transition"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex items-center space-x-2 text-[11px]">
          <button
            onClick={() => onToggleOnlyBaseline(!onlyBaseline)}
            className={`flex items-center space-x-1 px-2.5 py-1 rounded-md border transition ${
              onlyBaseline
                ? 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 font-medium'
                : 'bg-stone-50 dark:bg-slate-800/70 border-stone-200 dark:border-slate-700 text-stone-600 dark:text-slate-300 hover:bg-stone-100 dark:hover:bg-slate-700 hover:text-stone-800 dark:hover:text-slate-100'
            }`}
          >
            <Award className="w-3 h-3 text-amber-600 dark:text-amber-400" />
            <span>Baselines</span>
          </button>

          {allTags.length > 0 && (
            <div className="flex items-center space-x-1 overflow-x-auto max-w-[170px] no-scrollbar">
              {allTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => onSelectTag(activeTag === tag ? null : tag)}
                  className={`px-2 py-0.5 rounded-md border text-[10px] whitespace-nowrap transition ${
                    activeTag === tag
                      ? 'bg-stone-900 dark:bg-violet-600 border-stone-900 dark:border-violet-600 text-white font-medium'
                      : 'bg-stone-50 dark:bg-slate-800 border-stone-200 dark:border-slate-700 text-stone-600 dark:text-slate-300 hover:bg-stone-100 dark:hover:bg-slate-700'
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
      <div className="flex-1 overflow-y-auto divide-y divide-[#E8E6DF]/60 dark:divide-slate-800/60">
        {isLoading && runs.length === 0 ? (
          <div className="p-6 text-center text-xs text-stone-400 dark:text-slate-500">Loading pipeline runs...</div>
        ) : filteredRuns.length === 0 ? (
          <div className="p-6 text-center text-xs text-stone-400 dark:text-slate-500">
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
                    ? 'bg-[#F5F4EE] dark:bg-slate-800/90 border-l-3 border-stone-900 dark:border-l-violet-400'
                    : 'hover:bg-[#FAF9F5] dark:hover:bg-slate-800/40'
                }`}
              >
                {/* Header row: Status badge + run ID */}
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center space-x-2 truncate">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusConfig.dot}`} />
                    <span className="font-mono text-xs font-semibold text-stone-900 dark:text-slate-100 truncate">
                      {run.run_id.length > 20 ? `${run.run_id.slice(0, 18)}...` : run.run_id}
                    </span>
                  </div>
                  {Boolean(run.is_baseline) && (
                    <span className="flex items-center space-x-0.5 text-[10px] text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 px-1.5 py-0.2 rounded font-medium">
                      <Award className="w-2.5 h-2.5" />
                      <span>Base</span>
                    </span>
                  )}
                </div>

                {/* Sub row: dataset and mode */}
                <div className="flex items-center justify-between text-[11px] text-stone-500 dark:text-slate-400 mb-2">
                  <span className="truncate max-w-[150px]" title={run.dataset_path}>
                    📁 {datasetName}
                  </span>
                  <span className="font-mono text-[10px] text-stone-400 dark:text-slate-500">
                    {run.mode === 'eda_only' ? 'EDA' : 'Full'}
                    {Boolean(run.guided_mode) ? ' (Guided)' : ''}
                  </span>
                </div>

                {/* Metrics pill row */}
                <div className="flex items-center justify-between text-[11px] pt-1.5 border-t border-[#E8E6DF]/60 dark:border-slate-800/60">
                  <div className="flex items-center space-x-1.5 font-mono">
                    <span className="text-stone-400 dark:text-slate-500">Score:</span>
                    <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                      {formatScore(run.best_score)}
                    </span>
                  </div>
                  <div className="flex items-center space-x-2 text-stone-500 dark:text-slate-400 font-mono text-[10px]">
                    <span>{formatDuration(run.duration_s)}</span>
                    <span className={`px-2 py-0.5 rounded-full border text-[9px] font-medium ${statusConfig.badgeBg} ${statusConfig.badgeText}`}>
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
      <div className="p-2.5 border-t border-[#E8E6DF] dark:border-slate-800 text-[11px] text-stone-500 dark:text-slate-400 flex items-center justify-between bg-[#FAF9F5] dark:bg-slate-900/80">
        <span>{filteredRuns.length} of {runs.length} runs</span>
        <span className="font-mono text-[10px] text-stone-400 dark:text-slate-500">Auto-refreshed</span>
      </div>
    </aside>
  );
};

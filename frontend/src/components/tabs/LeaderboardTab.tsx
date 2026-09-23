import React, { useState } from 'react';
import { Crown, Layers, TrendingUp, TrendingDown, Clock, Code2, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { ModelAttempt } from '../../types/attempt';

interface LeaderboardTabProps {
  attempts: ModelAttempt[];
  metricName?: string | null;
  bestMetric?: number | null;
}

interface LeaderboardRowProps {
  att: ModelAttempt;
  idx: number;
  bestMetric?: number | null;
}

const LeaderboardRow: React.FC<LeaderboardRowProps> = ({ att, idx, bestMetric }) => {
  const [codeOpen, setCodeOpen] = useState(false);

  const isBest =
    bestMetric !== null &&
    bestMetric !== undefined &&
    att.cv_score !== null &&
    Math.abs(att.cv_score - bestMetric) < 0.0001;

  const isFailed = att.cv_score === null || att.success === false;
  const deltaPositive = (att.delta ?? 0) > 0;
  const deltaNegative = (att.delta ?? 0) < 0;

  return (
    <>
      <tr
        className={`transition hover:bg-[#FAF9F5] dark:hover:bg-slate-800/50 ${
          isBest
            ? 'bg-amber-50/40 dark:bg-amber-950/20'
            : isFailed
            ? 'bg-rose-50/30 dark:bg-rose-950/20'
            : ''
        }`}
      >
        {/* Rank */}
        <td className="py-3 px-4 text-center font-mono font-bold">
          {isBest ? (
            <div className="flex items-center justify-center text-amber-500" title="Best Candidate">
              <Crown className="w-4 h-4 fill-current" />
            </div>
          ) : (
            <span className="text-stone-400 dark:text-slate-500 text-xs">{idx + 1}</span>
          )}
        </td>

        {/* Model Name */}
        <td className="py-3 px-4">
          <div className="flex items-center space-x-2">
            <span className={`font-semibold ${isFailed ? 'text-rose-700 dark:text-rose-400' : 'text-stone-900 dark:text-slate-100'}`}>
              {att.model_name || 'Candidate Model'}
            </span>
            {isBest && (
              <span className="text-[9px] uppercase font-mono px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 font-bold">
                Leader
              </span>
            )}
            {isFailed && (
              <span className="text-[9px] uppercase font-mono px-2 py-0.5 rounded-full bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 font-bold">
                Failed
              </span>
            )}
          </div>
          {att.reason && <p className="text-[11px] text-stone-500 dark:text-slate-400 truncate max-w-xs mt-0.5">{att.reason}</p>}
          {att.code && (
            <button
              onClick={() => setCodeOpen((o) => !o)}
              className="mt-1 flex items-center gap-1 text-[11px] text-stone-600 dark:text-slate-400 hover:text-stone-900 dark:hover:text-slate-200 font-mono transition-colors"
            >
              {codeOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
              <Code2 className="w-3 h-3 text-stone-400 dark:text-slate-500" />
              <span>{codeOpen ? 'Hide code' : 'View code'}</span>
            </button>
          )}
        </td>

        {/* Retry Tier */}
        <td className="py-3 px-4 font-mono">
          <span
            className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${
              att.tier === 0
                ? 'bg-stone-100 dark:bg-slate-800 border-stone-200 dark:border-slate-700 text-stone-600 dark:text-slate-300'
                : att.tier === 1
                ? 'bg-violet-50 dark:bg-violet-950/60 border-violet-200 dark:border-violet-800 text-violet-700 dark:text-violet-300'
                : 'bg-purple-50 dark:bg-purple-950/60 border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300'
            }`}
          >
            Tier {att.tier}
          </span>
        </td>

        {/* CV Score */}
        <td className="py-3 px-4 text-right font-mono font-bold">
          <span className={isBest ? 'text-emerald-700 dark:text-emerald-400' : isFailed ? 'text-rose-600 dark:text-rose-400' : 'text-stone-800 dark:text-slate-200'}>
            {isFailed ? 'N/A' : (att.cv_score_str || (att.cv_score !== null ? att.cv_score.toFixed(4) : 'N/A'))}
          </span>
        </td>

        {/* Delta vs Baseline */}
        <td className="py-3 px-4 text-right font-mono">
          {att.delta !== null ? (
            <span
              className={`inline-flex items-center space-x-0.5 ${
                deltaPositive
                  ? 'text-emerald-700 dark:text-emerald-400 font-semibold'
                  : deltaNegative
                  ? 'text-rose-600 dark:text-rose-400'
                  : 'text-stone-500 dark:text-slate-400'
              }`}
            >
              {deltaPositive && <TrendingUp className="w-3 h-3 mr-0.5 text-emerald-600 dark:text-emerald-400" />}
              {deltaNegative && <TrendingDown className="w-3 h-3 mr-0.5 text-rose-500 dark:text-rose-400" />}
              <span>{att.delta_str || (att.delta !== undefined ? `${att.delta > 0 ? '+' : ''}${att.delta.toFixed(4)}` : '—')}</span>
            </span>
          ) : (
            <span className="text-stone-400 dark:text-slate-500">—</span>
          )}
        </td>

        {/* Decision */}
        <td className="py-3 px-4">
          <span
            className={`text-[10px] font-mono px-2 py-0.5 rounded-full border capitalize font-medium ${
              att.decision === 'accepted' || att.decision === 'accept' || att.decision === 'improvement'
                ? 'bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'
                : att.decision === 'reject' || att.decision === 'failed'
                ? 'bg-rose-50 dark:bg-rose-950/60 border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300'
                : 'bg-stone-100 dark:bg-slate-800 border-stone-200 dark:border-slate-700 text-stone-600 dark:text-slate-300'
            }`}
          >
            {att.decision}
          </span>
        </td>

        {/* Duration */}
        <td className="py-3 px-4 text-right font-mono text-stone-500 dark:text-slate-400 text-[11px]">
          {att.duration_ms ? `${(att.duration_ms / 1000).toFixed(2)}s` : '—'}
        </td>
      </tr>

      {/* Code expandable row */}
      {codeOpen && att.code && (
        <tr className="bg-[#FAF9F5] dark:bg-slate-950">
          <td colSpan={7} className="px-6 py-3">
            <pre className="p-3 rounded-lg bg-[#F5F4EE] dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 text-[11px] font-mono text-stone-800 dark:text-emerald-300 overflow-x-auto whitespace-pre-wrap max-h-60">
              {att.code}
            </pre>
          </td>
        </tr>
      )}
    </>
  );
};

export const LeaderboardTab: React.FC<LeaderboardTabProps> = ({
  attempts,
  metricName,
  bestMetric,
}) => {
  const [selectedTierFilter, setSelectedTierFilter] = useState<number | 'all'>('all');

  // Sort attempts by cv_score descending (default optimization)
  const sorted = [...attempts].sort((a, b) => {
    const sA = a.cv_score ?? -999999;
    const sB = b.cv_score ?? -999999;
    return sB - sA;
  });

  const filtered = sorted.filter((att) => {
    if (selectedTierFilter === 'all') return true;
    return att.tier === selectedTierFilter;
  });

  return (
    <div className="p-5 space-y-5 overflow-y-auto max-h-full bg-[#FAF9F5] dark:bg-[#090D16] min-h-full text-stone-900 dark:text-slate-100 transition-colors">
      {/* Header and Filter */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-stone-900 dark:text-slate-100">Model Leaderboard</h3>
          <p className="text-xs text-stone-500 dark:text-slate-400">
            All candidate models and iterations ranked by cross-validation performance.
          </p>
        </div>

        {/* Tier filter pills */}
        <div className="flex items-center space-x-1.5 text-xs">
          <span className="text-stone-500 dark:text-slate-400 text-[11px] mr-1">Filter Tier:</span>
          {(['all', 0, 1, 2] as const).map((tier) => (
            <button
              key={tier}
              onClick={() => setSelectedTierFilter(tier)}
              className={`px-2.5 py-1 rounded-lg border transition font-mono text-xs ${
                selectedTierFilter === tier
                  ? 'bg-stone-900 dark:bg-violet-600 border-stone-900 dark:border-violet-600 text-white font-medium shadow-xs'
                  : 'bg-white dark:bg-slate-800 border-stone-200 dark:border-slate-700 text-stone-600 dark:text-slate-300 hover:bg-stone-50 dark:hover:bg-slate-700'
              }`}
            >
              {tier === 'all' ? 'All Tiers' : `Tier ${tier}`}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="p-10 text-center bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl shadow-xs">
          <Layers className="w-8 h-8 text-stone-300 dark:text-slate-600 mx-auto mb-2" />
          <p className="text-xs text-stone-500 dark:text-slate-400">No model evaluation attempts recorded yet.</p>
        </div>
      ) : (
        <div className="border border-[#E8E6DF] dark:border-slate-800 rounded-xl overflow-hidden bg-white dark:bg-slate-900 shadow-xs transition-colors">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-[#E8E6DF] dark:border-slate-800 bg-[#FAF9F5] dark:bg-slate-950 text-stone-600 dark:text-slate-400 font-mono text-[11px]">
                <th className="py-2.5 px-4 w-12 text-center">#</th>
                <th className="py-2.5 px-4">Model Candidate</th>
                <th className="py-2.5 px-4">Tier</th>
                <th className="py-2.5 px-4 text-right">CV Score</th>
                <th className="py-2.5 px-4 text-right">Delta vs Baseline</th>
                <th className="py-2.5 px-4">Decision</th>
                <th className="py-2.5 px-4 text-right">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E8E6DF] dark:divide-slate-800">
              {filtered.map((att, idx) => (
                <LeaderboardRow
                  key={`${att.attempt}_${att.model_name}_${idx}`}
                  att={att}
                  idx={idx}
                  bestMetric={bestMetric}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

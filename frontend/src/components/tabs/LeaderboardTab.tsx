import React, { useState } from 'react';
import { Crown, Layers, TrendingUp, TrendingDown, Clock, Code, AlertCircle } from 'lucide-react';
import { ModelAttempt } from '../../types/attempt';

interface LeaderboardTabProps {
  attempts: ModelAttempt[];
  metricName?: string | null;
  bestMetric?: number | null;
}

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
    <div className="p-5 space-y-5 overflow-y-auto max-h-full">
      {/* Header and Filter */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Model Leaderboard</h3>
          <p className="text-xs text-slate-400">
            All candidate models and iterations ranked by cross-validation performance.
          </p>
        </div>

        {/* Tier filter pills */}
        <div className="flex items-center space-x-1.5 text-xs">
          <span className="text-slate-400 text-[11px] mr-1">Filter Tier:</span>
          {(['all', 0, 1, 2] as const).map((tier) => (
            <button
              key={tier}
              onClick={() => setSelectedTierFilter(tier)}
              className={`px-2.5 py-1 rounded border transition font-mono ${
                selectedTierFilter === tier
                  ? 'bg-indigo-950/80 border-indigo-500 text-indigo-300 font-bold'
                  : 'bg-slate-800/40 border-slate-700 text-slate-400 hover:text-slate-200'
              }`}
            >
              {tier === 'all' ? 'All Tiers' : `Tier ${tier}`}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="p-10 text-center bg-slate-950/40 border border-slate-800 rounded-xl">
          <Layers className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
          <p className="text-xs text-slate-400">No model evaluation attempts recorded yet.</p>
        </div>
      ) : (
        <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/60 shadow-sm">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/80 text-slate-400 font-mono text-[11px]">
                <th className="py-2.5 px-4 w-12 text-center">#</th>
                <th className="py-2.5 px-4">Model Candidate</th>
                <th className="py-2.5 px-4">Tier</th>
                <th className="py-2.5 px-4 text-right">CV Score</th>
                <th className="py-2.5 px-4 text-right">Delta vs Baseline</th>
                <th className="py-2.5 px-4">Decision</th>
                <th className="py-2.5 px-4 text-right">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-850">
              {filtered.map((att, idx) => {
                const isBest =
                  bestMetric !== null &&
                  bestMetric !== undefined &&
                  att.cv_score !== null &&
                  Math.abs(att.cv_score - bestMetric) < 0.0001;

                const deltaPositive = (att.delta ?? 0) > 0;
                const deltaNegative = (att.delta ?? 0) < 0;

                return (
                  <tr
                    key={`${att.attempt}_${idx}`}
                    className={`transition hover:bg-slate-850/50 ${
                      isBest ? 'bg-indigo-950/20' : ''
                    }`}
                  >
                    {/* Rank */}
                    <td className="py-3 px-4 text-center font-mono font-bold">
                      {isBest ? (
                        <div className="flex items-center justify-center text-amber-400" title="Best Candidate">
                          <Crown className="w-4 h-4 fill-current" />
                        </div>
                      ) : (
                        <span className="text-slate-400">{idx + 1}</span>
                      )}
                    </td>

                    {/* Model Name */}
                    <td className="py-3 px-4">
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold text-slate-200">
                          {att.model_name || 'Candidate Model'}
                        </span>
                        {isBest && (
                          <span className="text-[9px] uppercase font-mono px-1.5 py-0.2 rounded bg-amber-950/80 border border-amber-500/40 text-amber-300 font-bold">
                            Leader
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400 truncate max-w-xs">{att.reason}</p>
                    </td>

                    {/* Retry Tier */}
                    <td className="py-3 px-4 font-mono">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] border ${
                          att.tier === 0
                            ? 'bg-slate-800/80 border-slate-700 text-slate-300'
                            : att.tier === 1
                            ? 'bg-blue-950/70 border-blue-500/40 text-blue-300'
                            : 'bg-purple-950/70 border-purple-500/40 text-purple-300'
                        }`}
                      >
                        Tier {att.tier}
                      </span>
                    </td>

                    {/* CV Score */}
                    <td className="py-3 px-4 text-right font-mono font-bold text-slate-100">
                      <span className={isBest ? 'text-emerald-400' : 'text-slate-200'}>
                        {att.cv_score_str}
                      </span>
                    </td>

                    {/* Delta vs Baseline */}
                    <td className="py-3 px-4 text-right font-mono">
                      {att.delta !== null ? (
                        <span
                          className={`inline-flex items-center space-x-0.5 ${
                            deltaPositive
                              ? 'text-emerald-400 font-semibold'
                              : deltaNegative
                              ? 'text-rose-400'
                              : 'text-slate-400'
                          }`}
                        >
                          {deltaPositive && <TrendingUp className="w-3 h-3 mr-0.5" />}
                          {deltaNegative && <TrendingDown className="w-3 h-3 mr-0.5" />}
                          <span>{att.delta_str}</span>
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>

                    {/* Decision */}
                    <td className="py-3 px-4">
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded border capitalize ${
                          att.decision === 'accepted' || att.decision === 'accept'
                            ? 'bg-emerald-950/70 border-emerald-500/40 text-emerald-300'
                            : att.decision === 'reject'
                            ? 'bg-rose-950/70 border-rose-500/40 text-rose-300'
                            : 'bg-slate-800/80 border-slate-700 text-slate-300'
                        }`}
                      >
                        {att.decision}
                      </span>
                    </td>

                    {/* Duration */}
                    <td className="py-3 px-4 text-right font-mono text-slate-400 text-[11px]">
                      {att.duration_ms ? `${(att.duration_ms / 1000).toFixed(2)}s` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

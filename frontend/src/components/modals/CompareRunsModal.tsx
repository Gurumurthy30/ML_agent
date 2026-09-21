import React, { useState, useEffect } from 'react';
import { X, GitCompare, ArrowRight, Code, Trophy, AlertCircle } from 'lucide-react';
import { PipelineRun } from '../../types/run';
import { compareRuns } from '../../services/api';
import { formatScore, formatCost, formatTokens, formatDuration } from '../../utils/formatters';

interface CompareRunsModalProps {
  isOpen: boolean;
  onClose: () => void;
  runs: PipelineRun[];
  initialRunA?: string | null;
}

export const CompareRunsModal: React.FC<CompareRunsModalProps> = ({
  isOpen,
  onClose,
  runs,
  initialRunA,
}) => {
  const [runIdA, setRunIdA] = useState<string>(initialRunA || (runs[0]?.run_id ?? ''));
  const [runIdB, setRunIdB] = useState<string>(runs[1]?.run_id ?? runs[0]?.run_id ?? '');
  const [comparisonData, setComparisonData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialRunA) setRunIdA(initialRunA);
    if (runs.length > 1 && (!runIdB || runIdB === initialRunA)) {
      const other = runs.find((r) => r.run_id !== initialRunA);
      if (other) setRunIdB(other.run_id);
    }
  }, [initialRunA, runs]);

  useEffect(() => {
    if (!isOpen || !runIdA || !runIdB || runIdA === runIdB) {
      setComparisonData(null);
      return;
    }

    const fetchComparison = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await compareRuns(runIdA, runIdB);
        setComparisonData(data);
      } catch (err: any) {
        setError(err.message || 'Comparison failed.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchComparison();
  }, [isOpen, runIdA, runIdB]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-4xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center space-x-2">
            <GitCompare className="w-5 h-5 text-indigo-400" />
            <h3 className="text-sm font-semibold text-slate-100">Side-by-Side Run Comparison</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Selector row */}
        <div className="p-4 border-b border-slate-800 bg-slate-950/40 grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-400">Run A (Baseline / Reference)</label>
            <select
              value={runIdA}
              onChange={(e) => setRunIdA(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 text-slate-200 p-2 rounded text-xs focus:outline-none focus:border-indigo-500 font-mono"
            >
              {runs.map((r) => (
                <option key={`a_${r.run_id}`} value={r.run_id}>
                  {r.run_id} ({formatScore(r.best_score)}) {r.is_baseline ? '★' : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-400">Run B (Candidate / Comparison)</label>
            <select
              value={runIdB}
              onChange={(e) => setRunIdB(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 text-slate-200 p-2 rounded text-xs focus:outline-none focus:border-indigo-500 font-mono"
            >
              {runs.map((r) => (
                <option key={`b_${r.run_id}`} value={r.run_id}>
                  {r.run_id} ({formatScore(r.best_score)}) {r.is_baseline ? '★' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Content */}
        <div className="p-5 flex-1 overflow-y-auto space-y-6 text-xs">
          {error && (
            <div className="p-3 bg-rose-950/80 border border-rose-500/50 rounded-lg text-rose-200 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4" />
              <span>{error}</span>
            </div>
          )}

          {isLoading ? (
            <div className="p-12 text-center text-slate-400">Calculating comparison metrics...</div>
          ) : !comparisonData ? (
            <div className="p-12 text-center text-slate-400">
              Select two different runs above to compare performance and code diff.
            </div>
          ) : (
            <div className="space-y-6">
              {/* Comparative Metrics Grid */}
              <div className="grid grid-cols-2 gap-4">
                {/* Run A Card */}
                <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <span className="font-mono font-bold text-indigo-400 truncate max-w-[200px]">
                      {comparisonData.run_a.run_id}
                    </span>
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {comparisonData.run_a.status}
                    </span>
                  </div>

                  <div className="space-y-1.5 font-mono text-xs">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Best Metric:</span>
                      <span className="font-bold text-emerald-400 text-sm">
                        {formatScore(comparisonData.run_a.best_score)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Attempts:</span>
                      <span className="text-slate-200">{comparisonData.run_a.total_attempts}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Duration:</span>
                      <span className="text-slate-200">
                        {formatDuration(comparisonData.run_a.duration_s)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Cost:</span>
                      <span className="text-slate-200">
                        {formatCost(comparisonData.run_a.cost_usd)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Run B Card */}
                <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <span className="font-mono font-bold text-cyan-400 truncate max-w-[200px]">
                      {comparisonData.run_b.run_id}
                    </span>
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {comparisonData.run_b.status}
                    </span>
                  </div>

                  <div className="space-y-1.5 font-mono text-xs">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Best Metric:</span>
                      <span className="font-bold text-emerald-400 text-sm">
                        {formatScore(comparisonData.run_b.best_score)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Attempts:</span>
                      <span className="text-slate-200">{comparisonData.run_b.total_attempts}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Duration:</span>
                      <span className="text-slate-200">
                        {formatDuration(comparisonData.run_b.duration_s)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Cost:</span>
                      <span className="text-slate-200">
                        {formatCost(comparisonData.run_b.cost_usd)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Code comparison if available */}
              {(comparisonData.run_a.has_code || comparisonData.run_b.has_code) && (
                <div className="space-y-2">
                  <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    <Code className="w-4 h-4" />
                    <span>Best Model Code Comparison</span>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 max-h-64 overflow-y-auto">
                      <p className="text-[10px] font-mono text-slate-400 mb-1 border-b border-slate-800 pb-1">
                        Run A Code ({comparisonData.run_a.has_code ? 'Present' : 'None'})
                      </p>
                      <pre className="font-mono text-[10px] text-slate-300 overflow-x-auto">
                        {comparisonData.run_a.code || '# No model code saved'}
                      </pre>
                    </div>

                    <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 max-h-64 overflow-y-auto">
                      <p className="text-[10px] font-mono text-slate-400 mb-1 border-b border-slate-800 pb-1">
                        Run B Code ({comparisonData.run_b.has_code ? 'Present' : 'None'})
                      </p>
                      <pre className="font-mono text-[10px] text-slate-300 overflow-x-auto">
                        {comparisonData.run_b.code || '# No model code saved'}
                      </pre>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

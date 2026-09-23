import React, { useState, useEffect, useCallback } from 'react';
import {
  Code2, ChevronDown, ChevronRight, CheckCircle2, XCircle,
  TrendingUp, Minus, RefreshCw, Terminal, AlertTriangle, Layers
} from 'lucide-react';
import { RunIteration } from '../../types/attempt';
import { getRunIterations } from '../../services/api';

interface AllAttemptsTabProps {
  runId: string;
  isLive?: boolean;
  eventsCount?: number;
}

function CodeBlock({ code, label }: { code: string; label: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-xs text-stone-500 dark:text-slate-400 hover:text-stone-700 dark:hover:text-slate-200 transition-colors font-mono"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Code2 className="w-3.5 h-3.5" />
        <span>{label}</span>
      </button>
      {open && (
        <pre className="mt-2 p-3 bg-[#F3F2EF] dark:bg-slate-950 border border-stone-200 dark:border-slate-800 rounded-lg text-[11px] font-mono text-stone-700 dark:text-emerald-300 overflow-x-auto whitespace-pre-wrap max-h-72 leading-relaxed">
          {code}
        </pre>
      )}
    </div>
  );
}

function OutputBlock({ text, label, isError }: { text: string; label: string; isError?: boolean }) {
  const [open, setOpen] = useState(false);
  const trimmed = text.trim();
  if (!trimmed) return null;
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className={`flex items-center gap-1.5 text-xs transition-colors font-mono ${
          isError ? 'text-red-500 hover:text-red-700 dark:text-rose-400' : 'text-stone-500 dark:text-slate-400 hover:text-stone-700 dark:hover:text-slate-200'
        }`}
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        <Terminal className="w-3.5 h-3.5" />
        <span>{label}</span>
      </button>
      {open && (
        <pre
          className={`mt-2 p-3 rounded-lg text-[11px] font-mono overflow-x-auto whitespace-pre-wrap max-h-48 leading-relaxed ${
            isError
              ? 'bg-red-50 dark:bg-rose-950/40 border border-red-200 dark:border-rose-900 text-red-800 dark:text-rose-300'
              : 'bg-[#F3F2EF] dark:bg-slate-950 border border-stone-200 dark:border-slate-800 text-stone-700 dark:text-slate-200'
          }`}
        >
          {trimmed}
        </pre>
      )}
    </div>
  );
}

function IterationCard({
  item,
  index,
  isBest,
}: {
  item: RunIteration;
  index: number;
  isBest: boolean;
}) {
  const isSuccess = item.success !== false && item.score != null;
  const isAttempt = item.event_type === 'attempt_result' || item.event_type === 'modeler_iteration';
  const isDecision = item.event_type === 'loop_decision';

  if (isDecision) {
    return (
      <div className="flex items-center gap-2 py-0.5 pl-12">
        <div className="w-px h-3 bg-stone-200 dark:bg-slate-700" />
        <span className="text-[11px] text-stone-400 dark:text-slate-500 font-mono italic">
          {item.failure_reason || item.decision || 'Decision logged'}
        </span>
      </div>
    );
  }

  const cardClass = isSuccess && isBest
    ? 'border-violet-300 dark:border-violet-700 bg-white dark:bg-slate-900 shadow-sm'
    : isSuccess
    ? 'border-stone-200 dark:border-slate-800 bg-white dark:bg-slate-900'
    : isAttempt
    ? 'border-red-200 dark:border-rose-900 bg-red-50/50 dark:bg-rose-950/20'
    : 'border-stone-200 dark:border-slate-800 bg-stone-50/60 dark:bg-slate-900/60';

  const scoreClass = isSuccess
    ? isBest
      ? 'text-violet-700 dark:text-violet-300 bg-violet-50 dark:bg-violet-950/60 border-violet-200 dark:border-violet-800'
      : 'text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-800'
    : 'text-red-600 dark:text-rose-400 bg-red-50 dark:bg-rose-950/40 border-red-200 dark:border-rose-900';

  const modelLabel =
    item.model_family || (item.task_spec ? item.task_spec.slice(0, 70) : null) || 'Attempt';

  return (
    <div className={`rounded-xl border p-4 transition-shadow hover:shadow-sm ${cardClass}`}>
      <div className="flex items-start justify-between gap-3">
        {/* Left: iteration number + label */}
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-full bg-stone-100 dark:bg-slate-800 border border-stone-200 dark:border-slate-700 flex items-center justify-center flex-shrink-0 mt-0.5">
            <span className="text-[11px] font-bold text-stone-500 dark:text-slate-400 font-mono">
              {item.iteration ?? index + 1}
            </span>
          </div>
          <div className="min-w-0">
            <div className="flex items-center flex-wrap gap-2">
              <span className="font-semibold text-stone-800 dark:text-slate-100 text-sm break-words">{modelLabel}</span>
              {isBest && isSuccess && (
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-violet-100 dark:bg-violet-950 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-800 flex-shrink-0">
                  Best
                </span>
              )}
              {item.tier != null && (
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-stone-100 dark:bg-slate-800 border border-stone-200 dark:border-slate-700 text-stone-500 dark:text-slate-400 flex-shrink-0">
                  Tier {item.tier}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-0.5 text-xs text-stone-400 dark:text-slate-500 font-mono">
              {item.ts && <span>{item.ts.slice(11, 19)}</span>}
              {item.duration_ms && <span>{(item.duration_ms / 1000).toFixed(2)}s</span>}
            </div>
          </div>
        </div>

        {/* Right: score badge */}
        <div
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border font-mono text-sm font-bold flex-shrink-0 ${scoreClass}`}
        >
          {isSuccess ? (
            <>
              {item.is_improvement ? (
                <TrendingUp className="w-3.5 h-3.5" />
              ) : (
                <Minus className="w-3.5 h-3.5" />
              )}
              <span>
                {item.cv_score_str ||
                  (item.score != null ? item.score.toFixed(4) : 'N/A')}
              </span>
            </>
          ) : (
            <>
              <XCircle className="w-3.5 h-3.5" />
              <span>Failed</span>
            </>
          )}
        </div>
      </div>

      {/* Metric info */}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-stone-500">
        {item.metric_name && (
          <span className="font-mono bg-stone-100 px-2 py-0.5 rounded border border-stone-200">
            {item.metric_name}
          </span>
        )}
        {!isSuccess && item.failure_reason && (
          <span className="text-red-500 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            {item.failure_reason}
          </span>
        )}
        {isSuccess && item.is_improvement === false && (
          <span className="text-amber-600 text-[11px]">No improvement vs previous</span>
        )}
      </div>

      {/* Collapsible: code, stdout, stderr */}
      {item.code && <CodeBlock code={item.code} label="View generated code" />}
      {item.stdout && <OutputBlock text={item.stdout} label="View output" />}
      {item.stderr && (
        <OutputBlock text={item.stderr} label="View stderr / error trace" isError />
      )}
    </div>
  );
}

export const AllAttemptsTab: React.FC<AllAttemptsTabProps> = ({
  runId,
  isLive,
  eventsCount,
}) => {
  const [iterations, setIterations] = useState<RunIteration[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [agentFilter, setAgentFilter] = useState<string>('modeler_agent');
  const [error, setError] = useState<string | null>(null);

  const fetchIterations = useCallback(async () => {
    if (!runId) return;
    setError(null);
    try {
      const data = await getRunIterations(runId, agentFilter);
      setIterations(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  }, [runId, agentFilter]);

  useEffect(() => {
    setIsLoading(true);
    fetchIterations();
  }, [fetchIterations]);

  useEffect(() => {
    if (isLive && eventsCount) {
      const timer = setTimeout(fetchIterations, 900);
      return () => clearTimeout(timer);
    }
  }, [eventsCount, isLive, fetchIterations]);

  const bestScore = iterations.reduce<number | null>((best, it) => {
    if (it.score != null && (best === null || it.score > best)) return it.score;
    return best;
  }, null);

  const successCount = iterations.filter(
    (it) => it.success !== false && it.score != null
  ).length;
  const failedCount = iterations.filter(
    (it) =>
      (it.success === false || it.score == null) &&
      it.event_type === 'attempt_result'
  ).length;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#F7F6F3] dark:bg-[#090D16] transition-colors">
      {/* Sticky header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200 dark:border-slate-800 bg-white dark:bg-[#0F172A] flex-shrink-0 transition-colors">
        <div>
          <h2 className="text-base font-semibold text-stone-800 dark:text-slate-100">All Code Executions &amp; Results</h2>
          <p className="text-sm text-stone-500 dark:text-slate-400 mt-0.5">
            Every attempt in execution order — successes and failures.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {!isLoading && iterations.length > 0 && (
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {successCount} scored
              </span>
              {failedCount > 0 && (
                <span className="flex items-center gap-1 text-red-500 dark:text-rose-400 font-medium">
                  <XCircle className="w-3.5 h-3.5" />
                  {failedCount} failed
                </span>
              )}
            </div>
          )}

          <select
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            className="text-xs border border-stone-200 dark:border-slate-700 rounded-lg px-3 py-1.5 text-stone-600 dark:text-slate-200 bg-white dark:bg-slate-800 focus:outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-200 font-mono"
          >
            <option value="modeler_agent">Modeler</option>
            <option value="features_agent">Features</option>
            <option value="eda_agent">EDA</option>
          </select>

          <button
            onClick={fetchIterations}
            className="p-1.5 rounded-lg border border-stone-200 dark:border-slate-700 text-stone-500 dark:text-slate-400 hover:text-stone-700 dark:hover:text-slate-200 hover:bg-stone-50 dark:hover:bg-slate-800 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-violet-500' : ''}`} />
          </button>
        </div>
      </div>

      {/* Scrollable thread */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="flex flex-col items-center justify-center h-48 gap-3">
            <RefreshCw className="w-6 h-6 text-violet-400 animate-spin" />
            <p className="text-sm text-stone-500">Loading execution history…</p>
          </div>
        ) : error ? (
          <div className="p-5 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Error loading iterations</p>
              <p className="text-xs mt-1 text-red-600">{error}</p>
            </div>
          </div>
        ) : iterations.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-3 text-stone-400">
            <Layers className="w-10 h-10 opacity-30" />
            <p className="text-sm font-medium">No execution records yet for <span className="font-mono">{agentFilter}</span>.</p>
            <p className="text-xs text-stone-400">Results will appear here as the pipeline progresses.</p>
          </div>
        ) : (
          <div className="space-y-3 max-w-3xl mx-auto">
            {iterations.map((item, index) => (
              <IterationCard
                key={`${item.seq ?? index}_${index}`}
                item={item}
                index={index}
                isBest={bestScore != null && item.score === bestScore && item.score != null}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

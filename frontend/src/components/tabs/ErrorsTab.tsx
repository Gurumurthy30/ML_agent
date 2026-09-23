import React, { useState } from 'react';
import { AlertOctagon, RefreshCcw, ChevronDown, ChevronRight, Bug, Clock } from 'lucide-react';
import { ErrorGroup } from '../../types/error';

interface ErrorsTabProps {
  errors: ErrorGroup[];
}

export const ErrorsTab: React.FC<ErrorsTabProps> = ({ errors }) => {
  const [expandedSignatures, setExpandedSignatures] = useState<Record<string, boolean>>({});

  const toggleExpand = (sig: string) => {
    setExpandedSignatures((prev) => ({
      ...prev,
      [sig]: !prev[sig],
    }));
  };

  return (
    <div className="p-5 space-y-5 overflow-y-auto max-h-full bg-[#FAF9F5] dark:bg-[#090D16] min-h-full text-stone-900 dark:text-slate-100 transition-colors">
      <div>
        <h3 className="text-sm font-semibold text-stone-900 dark:text-slate-100">Aggregated Pipeline Errors</h3>
        <p className="text-xs text-stone-500 dark:text-slate-400">
          Errors deduplicated by signature with repeat frequency and prompt adaptation tracking.
        </p>
      </div>

      {errors.length === 0 ? (
        <div className="p-10 text-center bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl shadow-xs">
          <Bug className="w-8 h-8 text-stone-300 dark:text-slate-600 mx-auto mb-2" />
          <p className="text-xs text-stone-500 dark:text-slate-400">No runtime errors recorded for this pipeline run.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {errors.map((err, idx) => {
            const isExpanded = expandedSignatures[err.error_signature] ?? false;

            return (
              <div
                key={`${err.error_signature}_${idx}`}
                className="bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl overflow-hidden shadow-xs transition"
              >
                {/* Header */}
                <div
                  onClick={() => toggleExpand(err.error_signature)}
                  className="p-3 bg-white dark:bg-slate-900 hover:bg-[#FAF9F5] dark:hover:bg-slate-800/40 cursor-pointer flex items-center justify-between border-b border-[#E8E6DF] dark:border-slate-800 select-none"
                >
                  <div className="flex items-center space-x-2.5 truncate">
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-stone-400 dark:text-slate-500 flex-shrink-0" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-stone-400 dark:text-slate-500 flex-shrink-0" />
                    )}

                    <AlertOctagon className="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0" />

                    <span className="font-mono text-xs font-semibold text-stone-900 dark:text-slate-100 truncate">
                      {err.error_signature}
                    </span>

                    {/* Consecutive Repeat Badge */}
                    {err.consecutive_repeat && (
                      <span className="flex items-center space-x-1 px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 font-mono text-[10px] font-semibold">
                        <RefreshCcw className="w-2.5 h-2.5 animate-spin" />
                        <span>Repeat Loop</span>
                      </span>
                    )}
                  </div>

                  <div className="flex items-center space-x-3 text-xs font-mono">
                    <span className="px-2 py-0.5 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 rounded-full font-medium">
                      {err.count} {err.count === 1 ? 'occurrence' : 'occurrences'}
                    </span>
                    <span className="text-stone-400 dark:text-slate-500 text-[10px]">
                      Last: {err.last_seen ? err.last_seen.slice(11, 19) : ''}
                    </span>
                  </div>
                </div>

                {/* Body Message */}
                <div className="p-3.5 space-y-2 bg-[#FAF9F5] dark:bg-[#090D16] text-xs">
                  <p className="text-rose-900 dark:text-rose-200 font-mono bg-rose-50/70 dark:bg-rose-950/40 p-3 rounded-lg border border-rose-200 dark:border-rose-900/60 leading-relaxed whitespace-pre-wrap">
                    {err.message}
                  </p>

                  {/* Stack Trace Preview */}
                  {isExpanded && err.traceback && (
                    <div className="space-y-1 pt-2">
                      <span className="text-[11px] font-semibold text-stone-500 dark:text-slate-400 uppercase tracking-wider">
                        Full Stack Trace
                      </span>
                      <pre className="p-3 bg-white dark:bg-slate-950 text-stone-800 dark:text-slate-200 font-mono text-[11px] rounded-lg overflow-x-auto border border-[#E8E6DF] dark:border-slate-800 leading-relaxed max-h-60">
                        {err.traceback}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

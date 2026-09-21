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
    <div className="p-5 space-y-5 overflow-y-auto max-h-full">
      <div>
        <h3 className="text-sm font-semibold text-slate-200">Aggregated Pipeline Errors</h3>
        <p className="text-xs text-slate-400">
          Errors deduplicated by signature with repeat frequency and prompt adaptation tracking.
        </p>
      </div>

      {errors.length === 0 ? (
        <div className="p-10 text-center bg-slate-950/40 border border-slate-800 rounded-xl">
          <Bug className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
          <p className="text-xs text-slate-400">No runtime errors recorded for this pipeline run.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {errors.map((err, idx) => {
            const isExpanded = expandedSignatures[err.error_signature] ?? false;

            return (
              <div
                key={`${err.error_signature}_${idx}`}
                className="bg-slate-950/60 border border-slate-800 rounded-xl overflow-hidden transition"
              >
                {/* Header */}
                <div
                  onClick={() => toggleExpand(err.error_signature)}
                  className="p-3 bg-slate-900/80 hover:bg-slate-850/80 cursor-pointer flex items-center justify-between border-b border-slate-800/80 select-none"
                >
                  <div className="flex items-center space-x-2.5 truncate">
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
                    )}

                    <AlertOctagon className="w-4 h-4 text-rose-400 flex-shrink-0" />

                    <span className="font-mono text-xs font-bold text-slate-200 truncate">
                      {err.error_signature}
                    </span>

                    {/* Consecutive Repeat Badge */}
                    {err.consecutive_repeat && (
                      <span className="flex items-center space-x-1 px-2 py-0.5 rounded bg-amber-950/80 border border-amber-500/50 text-amber-300 font-mono text-[10px] font-bold">
                        <RefreshCcw className="w-2.5 h-2.5 animate-spin" />
                        <span>Consecutive Repeat Loop</span>
                      </span>
                    )}
                  </div>

                  <div className="flex items-center space-x-3 text-xs font-mono">
                    <span className="px-2 py-0.5 bg-rose-950/70 border border-rose-500/40 text-rose-300 rounded font-bold">
                      {err.count} {err.count === 1 ? 'occurrence' : 'occurrences'}
                    </span>
                    <span className="text-slate-400 text-[10px]">
                      Last: {err.last_seen ? err.last_seen.slice(11, 19) : ''}
                    </span>
                  </div>
                </div>

                {/* Body Message */}
                <div className="p-3 space-y-2 bg-slate-950/40 text-xs">
                  <p className="text-rose-200/90 font-mono bg-rose-950/30 p-2.5 rounded border border-rose-900/40 leading-relaxed whitespace-pre-wrap">
                    {err.message}
                  </p>

                  {/* Stack Trace Preview */}
                  {isExpanded && err.traceback && (
                    <div className="space-y-1 pt-2">
                      <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                        Full Stack Trace
                      </span>
                      <pre className="p-3 bg-slate-900 text-slate-300 font-mono text-[10px] rounded-lg overflow-x-auto border border-slate-800 leading-relaxed max-h-60">
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

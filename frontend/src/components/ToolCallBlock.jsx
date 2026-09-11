import React, { useState } from 'react';
import { ChevronRight, Wrench, CheckCircle2, AlertCircle, Clock } from 'lucide-react';

export default function ToolCallBlock({ toolCalls, defaultExpanded = false }) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (!toolCalls || !toolCalls.calls || toolCalls.calls.length === 0) return null;

  return (
    <div className="mb-3 select-text">
      {/* Summary Trigger Pill */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#201F1D] hover:bg-[#2A2926] border border-border/70 text-xs text-muted hover:text-primary transition-colors cursor-pointer group"
        aria-expanded={isExpanded}
      >
        <Wrench className="w-3.5 h-3.5 text-accent flex-shrink-0" />
        <span className="font-sans font-medium">
          {toolCalls.summary || `Used ${toolCalls.calls.length} tool${toolCalls.calls.length > 1 ? 's' : ''}`}
        </span>
        <span className="text-[11px] px-1.5 py-0.2 rounded bg-border/40 text-muted/80 font-mono">
          {toolCalls.calls.length}
        </span>
        <ChevronRight
          className={`w-3.5 h-3.5 text-muted transition-transform duration-200 ease-claude ${
            isExpanded ? 'rotate-90 text-primary' : 'group-hover:text-primary'
          }`}
        />
      </button>

      {/* Expanded sub-cards */}
      <div className={`collapsible-content ${isExpanded ? 'expanded' : ''}`}>
        <div className="collapsible-inner">
          <div className="mt-2.5 space-y-2 pl-2">
            {toolCalls.calls.map((call, idx) => (
              <div
                key={call.id || idx}
                className="bg-card border border-border/80 rounded-lg p-3 text-xs font-mono transition-all"
              >
                <div className="flex items-center justify-between gap-2 pb-2 mb-2 border-b border-border/60">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="text-accent font-semibold">{call.tool}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {call.duration && (
                      <span className="flex items-center gap-1 text-[11px] text-muted">
                        <Clock className="w-3 h-3" />
                        {call.duration}
                      </span>
                    )}
                    {call.status === 'success' ? (
                      <span className="flex items-center gap-1 text-[11px] text-success">
                        <CheckCircle2 className="w-3 h-3" />
                        ok
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[11px] text-error">
                        <AlertCircle className="w-3 h-3" />
                        error
                      </span>
                    )}
                  </div>
                </div>

                {/* Arguments */}
                {call.args && (
                  <div className="mb-2">
                    <div className="text-muted/70 text-[10.5px] uppercase tracking-wider mb-1 font-sans">Input:</div>
                    <pre className="bg-[#181716] p-2 rounded text-[11.5px] text-[#E0DFDC] overflow-x-auto terminal-scroll">
                      {typeof call.args === 'object' ? JSON.stringify(call.args, null, 2) : call.args}
                    </pre>
                  </div>
                )}

                {/* Result */}
                {call.result && (
                  <div>
                    <div className="text-muted/70 text-[10.5px] uppercase tracking-wider mb-1 font-sans">Output:</div>
                    <div className="text-[#C5C4C0] text-[11.5px] bg-[#181716]/60 p-2 rounded border border-border/40 overflow-x-auto terminal-scroll">
                      {call.result}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

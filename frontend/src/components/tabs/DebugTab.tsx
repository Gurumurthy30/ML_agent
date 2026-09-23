import React, { useState } from 'react';
import { Code, ChevronRight, ChevronDown, Copy, Check } from 'lucide-react';
import { PipelineRun } from '../../types/run';
import { PipelineEvent } from '../../types/event';

interface DebugTabProps {
  run: PipelineRun;
  events: PipelineEvent[];
}

export const DebugTab: React.FC<DebugTabProps> = ({ run, events }) => {
  const [copiedSection, setCopiedSection] = useState<string | null>(null);

  // Extract latest state snapshot if present in events
  let latestSnapshot: any = null;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].state_snapshot) {
      latestSnapshot = events[i].state_snapshot;
      break;
    }
  }

  const handleCopy = (key: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSection(key);
    setTimeout(() => setCopiedSection(null), 2000);
  };

  return (
    <div className="p-5 space-y-5 overflow-y-auto max-h-full bg-[#FAF9F5] dark:bg-[#090D16] min-h-full text-stone-900 dark:text-slate-100 transition-colors">
      <div>
        <h3 className="text-sm font-semibold text-stone-900 dark:text-slate-100">Diagnostics &amp; State Debugger</h3>
        <p className="text-xs text-stone-500 dark:text-slate-400">
          Raw SQLite run metadata, AgentState snapshots, fingerprints, and message traces.
        </p>
      </div>

      <div className="space-y-4">
        {/* Section 1: Run Index Record */}
        <div className="bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
          <div className="p-3 bg-[#FAF9F5] dark:bg-slate-950 border-b border-[#E8E6DF] dark:border-slate-800 flex items-center justify-between">
            <span className="text-xs font-mono font-semibold text-stone-800 dark:text-slate-200">
              SQLite Run Metadata Record
            </span>
            <button
              onClick={() => handleCopy('run_meta', JSON.stringify(run, null, 2))}
              className="flex items-center space-x-1 text-[11px] text-stone-500 dark:text-slate-400 hover:text-stone-900 dark:hover:text-slate-200 transition-colors"
            >
              {copiedSection === 'run_meta' ? (
                <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              <span>{copiedSection === 'run_meta' ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <pre className="p-3.5 text-[11px] font-mono text-stone-800 dark:text-slate-300 bg-[#F5F4EE] dark:bg-slate-950/60 overflow-x-auto max-h-64 leading-relaxed">
            {JSON.stringify(run, null, 2)}
          </pre>
        </div>

        {/* Section 2: AgentState Snapshot */}
        <div className="bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
          <div className="p-3 bg-[#FAF9F5] dark:bg-slate-950 border-b border-[#E8E6DF] dark:border-slate-800 flex items-center justify-between">
            <span className="text-xs font-mono font-semibold text-stone-800 dark:text-slate-200">
              AgentState Snapshot (Latest)
            </span>
            <button
              onClick={() =>
                handleCopy(
                  'state_snapshot',
                  JSON.stringify(latestSnapshot || { note: 'No snapshot in events' }, null, 2)
                )
              }
              className="flex items-center space-x-1 text-[11px] text-stone-500 dark:text-slate-400 hover:text-stone-900 dark:hover:text-slate-200 transition-colors"
            >
              {copiedSection === 'state_snapshot' ? (
                <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              <span>{copiedSection === 'state_snapshot' ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <pre className="p-3.5 text-[11px] font-mono text-stone-800 dark:text-slate-300 bg-[#F5F4EE] dark:bg-slate-950/60 overflow-x-auto max-h-80 leading-relaxed">
            {latestSnapshot
              ? JSON.stringify(latestSnapshot, null, 2)
              : 'No state_snapshot attached to recent events.'}
          </pre>
        </div>

        {/* Section 3: Raw Recent Events Payload */}
        <div className="bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl overflow-hidden shadow-xs">
          <div className="p-3 bg-[#FAF9F5] dark:bg-slate-950 border-b border-[#E8E6DF] dark:border-slate-800 flex items-center justify-between">
            <span className="text-xs font-mono font-semibold text-stone-800 dark:text-slate-200">
              Recent Raw Events ({events.length})
            </span>
            <button
              onClick={() => handleCopy('raw_events', JSON.stringify(events.slice(-20), null, 2))}
              className="flex items-center space-x-1 text-[11px] text-stone-500 dark:text-slate-400 hover:text-stone-900 dark:hover:text-slate-200 transition-colors"
            >
              {copiedSection === 'raw_events' ? (
                <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              <span>{copiedSection === 'raw_events' ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <pre className="p-3.5 text-[11px] font-mono text-stone-800 dark:text-slate-300 bg-[#F5F4EE] dark:bg-slate-950/60 overflow-x-auto max-h-80 leading-relaxed">
            {JSON.stringify(events.slice(-20), null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
};

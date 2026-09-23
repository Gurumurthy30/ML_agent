import React, { useState } from 'react';
import { Pause, Play, Square, Zap, Download, GitCompare } from 'lucide-react';
import { RunStatus } from '../../types/run';
import { pauseRun, unpauseRun, stopRun, escapeRun, getExportUrl } from '../../services/api';

interface RunControlsProps {
  runId: string;
  status: RunStatus;
  onControlTriggered: () => void;
  onOpenCompare: () => void;
}

export const RunControls: React.FC<RunControlsProps> = ({
  runId,
  status,
  onControlTriggered,
  onOpenCompare,
}) => {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const canPause = status === 'running';
  const canUnpause = status === 'paused';
  const canStop = status === 'running' || status === 'paused';
  const canEscape = status === 'running';

  const executeControl = async (action: 'pause' | 'unpause' | 'stop' | 'escape') => {
    setLoadingAction(action);
    setActionNotice(null);
    try {
      if (action === 'pause') await pauseRun(runId);
      if (action === 'unpause') await unpauseRun(runId);
      if (action === 'stop') await stopRun(runId);
      if (action === 'escape') {
        await escapeRun(runId);
        setActionNotice('⚡ Escape signal sent — current stuck loop will force-advance!');
      }
      onControlTriggered();
    } catch (err: any) {
      setActionNotice(`Action failed: ${err.message}`);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleExport = () => {
    window.open(getExportUrl(runId), '_blank');
  };

  return (
    <div className="flex flex-col space-y-1.5">
      <div className="flex items-center space-x-2">
        {/* Pause Button */}
        {status === 'paused' ? (
          <button
            onClick={() => executeControl('unpause')}
            disabled={!canUnpause || loadingAction !== null}
            className="flex items-center space-x-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-medium shadow-xs transition disabled:opacity-40 disabled:cursor-not-allowed"
            title="Resume running execution"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Unpause</span>
          </button>
        ) : (
          <button
            onClick={() => executeControl('pause')}
            disabled={!canPause || loadingAction !== null}
            className="flex items-center space-x-1 px-3 py-1.5 bg-white dark:bg-slate-800 hover:bg-stone-50 dark:hover:bg-slate-700 text-stone-700 dark:text-slate-200 border border-stone-200 dark:border-slate-700 rounded-lg text-xs font-medium shadow-xs transition disabled:opacity-40 disabled:cursor-not-allowed"
            title="Pause pipeline execution"
          >
            <Pause className="w-3.5 h-3.5 text-stone-500 dark:text-slate-400" />
            <span>Pause</span>
          </button>
        )}

        {/* Escape Button: Visually distinct from Stop! */}
        <button
          onClick={() => executeControl('escape')}
          disabled={!canEscape || loadingAction !== null}
          className="flex items-center space-x-1.5 px-3 py-1.5 bg-amber-50 dark:bg-amber-950/40 hover:bg-amber-100 dark:hover:bg-amber-900/60 text-amber-800 dark:text-amber-300 rounded-lg text-xs font-medium shadow-xs transition border border-amber-200 dark:border-amber-700/60 disabled:opacity-40 disabled:cursor-not-allowed"
          title="Force-advance stuck loop (skips current retry or exploration attempt without terminating run)"
        >
          <Zap className="w-3.5 h-3.5 fill-amber-500 text-amber-600 dark:text-amber-400" />
          <span>Escape Loop</span>
        </button>

        {/* Stop Button */}
        <button
          onClick={() => executeControl('stop')}
          disabled={!canStop || loadingAction !== null}
          className="flex items-center space-x-1 px-3 py-1.5 bg-rose-50 dark:bg-rose-950/40 hover:bg-rose-100 dark:hover:bg-rose-900/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60 rounded-lg text-xs font-medium shadow-xs transition disabled:opacity-40 disabled:cursor-not-allowed"
          title="Stop and terminate pipeline run completely"
        >
          <Square className="w-3.5 h-3.5 fill-current text-rose-600 dark:text-rose-400" />
          <span>Stop Run</span>
        </button>

        <div className="h-5 w-px bg-stone-200 dark:bg-slate-700 mx-1" />

        {/* Compare */}
        <button
          onClick={onOpenCompare}
          className="flex items-center space-x-1 px-3 py-1.5 bg-white dark:bg-slate-800 hover:bg-stone-50 dark:hover:bg-slate-700 text-stone-700 dark:text-slate-200 border border-stone-200 dark:border-slate-700 rounded-lg text-xs font-medium shadow-xs transition"
          title="Compare this run side-by-side with another"
        >
          <GitCompare className="w-3.5 h-3.5 text-violet-600 dark:text-violet-400" />
          <span>Compare</span>
        </button>

        {/* Export ZIP */}
        <button
          onClick={handleExport}
          className="flex items-center space-x-1 px-3 py-1.5 bg-white dark:bg-slate-800 hover:bg-stone-50 dark:hover:bg-slate-700 text-stone-700 dark:text-slate-200 border border-stone-200 dark:border-slate-700 rounded-lg text-xs font-medium shadow-xs transition"
          title="Download full debug bundle as ZIP"
        >
          <Download className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
          <span>Export</span>
        </button>
      </div>

      {actionNotice && (
        <div className="text-[11px] font-mono text-amber-800 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 px-2.5 py-1 rounded-md border border-amber-200 dark:border-amber-800/60">
          {actionNotice}
        </div>
      )}
    </div>
  );
};

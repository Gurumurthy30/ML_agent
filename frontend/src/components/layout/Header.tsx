import React from 'react';
import { Activity, Plus, Radio, RefreshCw } from 'lucide-react';

interface HeaderProps {
  onNewRun: () => void;
  onRefresh: () => void;
  isRefreshing?: boolean;
  connectedRunsCount: number;
}

export const Header: React.FC<HeaderProps> = ({
  onNewRun,
  onRefresh,
  isRefreshing,
  connectedRunsCount,
}) => {
  return (
    <header className="h-14 border-b border-slate-800 bg-slate-900/90 backdrop-blur px-5 flex items-center justify-between z-20 select-none">
      {/* Brand & Live Connection Indicator */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/40 text-indigo-400">
          <Activity className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-base font-semibold text-slate-100 tracking-tight">ML_agent</h1>
            <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
              Autonomous Pipeline
            </span>
          </div>
        </div>

        <div className="hidden sm:flex items-center ml-4 pl-4 border-l border-slate-800 space-x-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="text-xs text-slate-400 font-mono">Backend Connected (FastAPI :8000)</span>
        </div>
      </div>

      {/* Global Actions */}
      <div className="flex items-center space-x-3">
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium text-slate-300 bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 rounded-md transition disabled:opacity-50"
          title="Refresh runs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`} />
          <span>Refresh</span>
        </button>

        <button
          onClick={onNewRun}
          className="flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-md shadow-sm transition border border-indigo-500/60"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Run</span>
        </button>
      </div>
    </header>
  );
};

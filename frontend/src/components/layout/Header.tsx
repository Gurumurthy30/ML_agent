import React from 'react';
import { Activity, Plus, Radio, RefreshCw, Moon, Sun } from 'lucide-react';

interface HeaderProps {
  onNewRun: () => void;
  onRefresh: () => void;
  isRefreshing?: boolean;
  connectedRunsCount: number;
  isDark?: boolean;
  onToggleDark?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  onNewRun,
  onRefresh,
  isRefreshing,
  connectedRunsCount,
  isDark = true,
  onToggleDark,
}) => {
  return (
    <header className="h-14 border-b border-[#E8E6DF] dark:border-slate-800 bg-white/95 dark:bg-[#0F172A]/95 backdrop-blur px-5 flex items-center justify-between z-20 select-none transition-colors">
      {/* Brand & Live Connection Indicator */}
      <div className="flex items-center space-x-3">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-stone-100 dark:bg-slate-800 border border-stone-200 dark:border-slate-700 text-stone-800 dark:text-slate-100 shadow-xs">
          <Activity className="w-4 h-4 text-violet-600 dark:text-violet-400" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-sm font-semibold text-stone-900 dark:text-slate-100 tracking-tight">ML_agent</h1>
            <span className="text-[10px] font-medium uppercase px-2 py-0.5 rounded-full bg-stone-100 dark:bg-slate-800 text-stone-600 dark:text-slate-300 border border-stone-200 dark:border-slate-700 font-mono">
              Autonomous Studio
            </span>
          </div>
        </div>

        <div className="hidden sm:flex items-center ml-4 pl-4 border-l border-stone-200 dark:border-slate-800 space-x-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="text-xs text-stone-500 dark:text-slate-400 font-mono">Backend Connected (FastAPI :8000)</span>
        </div>
      </div>

      {/* Global Actions */}
      <div className="flex items-center space-x-2.5">
        {/* Dark / Light Mode Toggle */}
        {onToggleDark && (
          <button
            onClick={onToggleDark}
            className="flex items-center space-x-1.5 px-2.5 py-1.5 text-xs font-medium text-stone-700 dark:text-slate-300 bg-white dark:bg-slate-800 hover:bg-stone-50 dark:hover:bg-slate-700 border border-stone-200 dark:border-slate-700 rounded-lg shadow-xs transition"
            title={isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
            aria-label="Toggle theme"
          >
            {isDark ? (
              <>
                <Sun className="w-3.5 h-3.5 text-amber-400" />
                <span className="hidden sm:inline">Light</span>
              </>
            ) : (
              <>
                <Moon className="w-3.5 h-3.5 text-indigo-500" />
                <span className="hidden sm:inline">Dark</span>
              </>
            )}
          </button>
        )}

        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-medium text-stone-700 dark:text-slate-300 bg-white dark:bg-slate-800 hover:bg-stone-50 dark:hover:bg-slate-700 border border-stone-200 dark:border-slate-700 rounded-lg shadow-xs transition disabled:opacity-50"
          title="Refresh runs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin text-stone-600 dark:text-slate-400' : 'text-stone-500 dark:text-slate-400'}`} />
          <span>Refresh</span>
        </button>

        <button
          onClick={onNewRun}
          className="flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-medium text-white bg-stone-900 dark:bg-violet-600 hover:bg-stone-800 dark:hover:bg-violet-500 rounded-lg shadow-xs transition active:scale-[0.98]"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>New Run</span>
        </button>
      </div>
    </header>
  );
};

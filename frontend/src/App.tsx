import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/layout/Header';
import { RunListSidebar } from './components/layout/RunListSidebar';
import { ApprovalQueue } from './components/layout/ApprovalQueue';
import { RunHeader } from './components/run/RunHeader';
import { PipelineFlowTab } from './components/tabs/PipelineFlowTab';
import { FeaturePlanTab } from './components/tabs/FeaturePlanTab';
import { LeaderboardTab } from './components/tabs/LeaderboardTab';
import { JudgeTab } from './components/tabs/JudgeTab';
import { LogsTab } from './components/tabs/LogsTab';
import { ErrorsTab } from './components/tabs/ErrorsTab';
import { ReportTab } from './components/tabs/ReportTab';
import { DebugTab } from './components/tabs/DebugTab';
import { DatasetTab } from './components/tabs/DatasetTab';
import { AllAttemptsTab } from './components/tabs/AllAttemptsTab';
import { CreateRunModal } from './components/modals/CreateRunModal';
import { CompareRunsModal } from './components/modals/CompareRunsModal';

import { PipelineRun } from './types/run';
import { ModelAttempt } from './types/attempt';
import { ErrorGroup } from './types/error';
import { listRuns, getRun, getRunAttempts, getRunErrors } from './services/api';
import { useRunSSE } from './hooks/useRunSSE';
import {
  GitCommit,
  Columns,
  Trophy,
  Gavel,
  Terminal,
  AlertOctagon,
  FileText,
  Code,
  Database,
  Code2,
} from 'lucide-react';

export const App: React.FC = () => {
  // Global runs state
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<PipelineRun | null>(null);

  // Filter states
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [onlyBaseline, setOnlyBaseline] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  // Tab state
  const [activeTab, setActiveTab] = useState<
    'flow' | 'dataset' | 'feature_plan' | 'leaderboard' | 'all_attempts' | 'judge' | 'logs' | 'errors' | 'report' | 'debug'
  >('flow');

  // Attempts and errors ledger
  const [attempts, setAttempts] = useState<ModelAttempt[]>([]);
  const [errors, setErrors] = useState<ErrorGroup[]>([]);

  // Modals state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [isCompareModalOpen, setIsCompareModalOpen] = useState<boolean>(false);

  // Theme state (defaults to dark per user preference)
  const [isDark, setIsDark] = useState<boolean>(() => {
    const saved = localStorage.getItem('ml_agent_theme');
    return saved !== null ? saved === 'dark' : true;
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('ml_agent_theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('ml_agent_theme', 'light');
    }
  }, [isDark]);

  // Real-time SSE hook for the selected run
  const { events, isConnected, isReconnecting } = useRunSSE(selectedRunId);

  // Load runs list
  const fetchRuns = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const data = await listRuns({
        tag: activeTag || undefined,
        is_baseline: onlyBaseline ? true : undefined,
        limit: 50,
      });
      setRuns(data);
      if (!selectedRunId && data.length > 0) {
        setSelectedRunId(data[0].run_id);
      }
    } catch (err) {
      console.error('Failed fetching runs:', err);
    } finally {
      setIsRefreshing(false);
    }
  }, [activeTag, onlyBaseline, selectedRunId]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  // Load selected run metadata, attempts, and errors
  const fetchSelectedRunDetails = useCallback(async (runId: string) => {
    try {
      const [runData, attData, errData] = await Promise.all([
        getRun(runId),
        getRunAttempts(runId).catch(() => []),
        getRunErrors(runId).catch(() => []),
      ]);
      setSelectedRun(runData);
      setAttempts(attData);
      setErrors(errData);
    } catch (err) {
      console.error(`Failed to load details for ${runId}:`, err);
    }
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      fetchSelectedRunDetails(selectedRunId);
    }
  }, [selectedRunId, fetchSelectedRunDetails]);

  // When new events arrive via SSE, periodically refresh metadata & attempts
  useEffect(() => {
    if (selectedRunId && events.length > 0) {
      const timer = setTimeout(() => {
        fetchSelectedRunDetails(selectedRunId);
        fetchRuns();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [events.length, selectedRunId]);

  // Paused runs for Approval Queue
  const pausedRuns = runs.filter(
    (r) => r.status === 'paused' || r.stop_reason === 'human_approval_required'
  );

  interface TabItem {
    id: 'flow' | 'dataset' | 'feature_plan' | 'leaderboard' | 'all_attempts' | 'judge' | 'logs' | 'errors' | 'report' | 'debug';
    label: string;
    icon: any;
    count?: number;
  }

  const tabsConfig: TabItem[] = [
    { id: 'flow', label: 'Pipeline Flow', icon: GitCommit },
    { id: 'dataset', label: 'Dataset', icon: Database },
    { id: 'feature_plan', label: 'Feature Plan', icon: Columns },
    { id: 'leaderboard', label: 'Leaderboard', icon: Trophy, count: attempts.length },
    { id: 'all_attempts', label: 'Code & Results', icon: Code2 },
    { id: 'judge', label: 'Judge', icon: Gavel },
    { id: 'logs', label: 'Logs & Model Text', icon: Terminal, count: events.length },
    { id: 'errors', label: 'Errors', icon: AlertOctagon, count: errors.length },
    { id: 'report', label: 'Report', icon: FileText },
    { id: 'debug', label: 'Debug', icon: Code },
  ];

  return (
    <div className="h-screen w-screen flex flex-col bg-[#FAF9F5] dark:bg-[#090D16] text-stone-900 dark:text-slate-100 font-sans overflow-hidden transition-colors">
      {/* Top Header */}
      <Header
        onNewRun={() => setIsCreateModalOpen(true)}
        onRefresh={fetchRuns}
        isRefreshing={isRefreshing}
        connectedRunsCount={runs.length}
        isDark={isDark}
        onToggleDark={() => setIsDark((prev) => !prev)}
      />

      {/* 3-Region Desktop Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Region 1: Run List Sidebar (Left) */}
        <RunListSidebar
          runs={runs}
          selectedRunId={selectedRunId}
          onSelectRun={(id) => setSelectedRunId(id)}
          isLoading={isRefreshing}
          activeTag={activeTag}
          onSelectTag={(t) => setActiveTag(t)}
          onlyBaseline={onlyBaseline}
          onToggleOnlyBaseline={(b) => setOnlyBaseline(b)}
        />

        {/* Region 2: Run Detail & Tabs (Center) */}
        <main className="flex-1 flex flex-col h-full overflow-hidden bg-[#FAF9F5] dark:bg-[#090D16] transition-colors">
          {!selectedRun ? (
            <div className="flex-1 flex items-center justify-center text-stone-400 dark:text-slate-500 text-xs">
              Select a pipeline run from the left sidebar to inspect telemetry.
            </div>
          ) : (
            <>
              {/* Run Header with quick telemetry & action controls */}
              <RunHeader
                run={selectedRun}
                onRefresh={() => {
                  fetchRuns();
                  if (selectedRunId) fetchSelectedRunDetails(selectedRunId);
                }}
                onOpenCompare={() => setIsCompareModalOpen(true)}
                isConnectedLive={isConnected}
                isReconnecting={isReconnecting}
                onSelectTab={(tab) => setActiveTab(tab)}
                errorsCount={errors.length}
              />

              {/* Tab Navigation */}
              <div className="flex items-center space-x-1 px-4 pt-1.5 border-b border-[#E8E6DF] dark:border-slate-800 bg-white dark:bg-[#0F172A] overflow-x-auto no-scrollbar flex-shrink-0 transition-colors">
                {tabsConfig.map((t) => {
                  const Icon = t.icon;
                  const isActive = activeTab === t.id;

                  return (
                    <button
                      key={t.id}
                      onClick={() => setActiveTab(t.id as any)}
                      className={`flex items-center space-x-1.5 py-2 px-3 border-b-2 text-xs font-medium transition whitespace-nowrap ${
                        isActive
                          ? 'border-stone-900 dark:border-violet-500 text-stone-900 dark:text-slate-100 font-semibold bg-[#F5F4EE]/60 dark:bg-slate-800/80 rounded-t-md'
                          : 'border-transparent text-stone-500 dark:text-slate-400 hover:text-stone-800 dark:hover:text-slate-200 hover:border-stone-300 dark:hover:border-slate-700'
                      }`}
                    >
                      <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-stone-900 dark:text-violet-400' : 'text-stone-400 dark:text-slate-500'}`} />
                      <span>{t.label}</span>
                      {t.count !== undefined && t.count > 0 && (
                        <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-medium ${
                          isActive
                            ? 'bg-stone-200 dark:bg-slate-700 text-stone-800 dark:text-slate-200'
                            : 'bg-stone-100 dark:bg-slate-800 text-stone-500 dark:text-slate-400'
                        }`}>
                          {t.count}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Active Tab Content Area */}
              <div className="flex-1 overflow-y-auto">
                {activeTab === 'flow' && (
                  <PipelineFlowTab
                    events={events}
                    isLive={isConnected}
                    status={selectedRun.status}
                  />
                )}
                {activeTab === 'dataset' && <DatasetTab run={selectedRun} />}
                {activeTab === 'feature_plan' && <FeaturePlanTab events={events} />}
                {activeTab === 'leaderboard' && (
                  <LeaderboardTab
                    attempts={attempts}
                    metricName={selectedRun.metric_name}
                    bestMetric={selectedRun.best_score}
                  />
                )}
                {activeTab === 'all_attempts' && selectedRunId && (
                  <AllAttemptsTab
                    runId={selectedRunId}
                    isLive={isConnected}
                    eventsCount={events.length}
                  />
                )}
                {activeTab === 'judge' && <JudgeTab events={events} />}
                {activeTab === 'logs' && <LogsTab events={events} />}
                {activeTab === 'errors' && <ErrorsTab errors={errors} />}
                {activeTab === 'report' && <ReportTab run={selectedRun} events={events} />}
                {activeTab === 'debug' && <DebugTab run={selectedRun} events={events} />}
              </div>
            </>
          )}
        </main>

        {/* Region 3: Approval Queue (Right) */}
        <ApprovalQueue
          pausedRuns={pausedRuns}
          onActionComplete={() => {
            fetchRuns();
            if (selectedRunId) fetchSelectedRunDetails(selectedRunId);
          }}
          onSelectRun={(id) => setSelectedRunId(id)}
        />
      </div>

      {/* Modals */}
      <CreateRunModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onRunCreated={(newRunId) => {
          setSelectedRunId(newRunId);
          fetchRuns();
        }}
      />

      <CompareRunsModal
        isOpen={isCompareModalOpen}
        onClose={() => setIsCompareModalOpen(false)}
        runs={runs}
        initialRunA={selectedRunId}
      />
    </div>
  );
};

export default App;

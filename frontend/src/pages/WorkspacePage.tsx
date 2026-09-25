import { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderGit2 } from "lucide-react";
import { Header } from "../components/layout/Header";
import { ProjectNav } from "../components/layout/ProjectNav";
import { ArtifactsPanel } from "../components/layout/ArtifactsPanel";
import { AgentActivityFeed } from "../components/views/AgentActivityFeed";
import { DatasetView } from "../components/views/DatasetView";
import { ProfileView } from "../components/views/ProfileView";
import { EDAView } from "../components/views/EDAView";
import { FeaturesView } from "../components/views/FeaturesView";
import { LeaderboardView } from "../components/views/LeaderboardView";
import { EvaluationView } from "../components/views/EvaluationView";
import { ReportView } from "../components/views/ReportView";
import { RunsView } from "../components/views/RunsView";
import { CoderExecutionsView } from "../components/views/CoderExecutionsView";
import { ArtifactViewerModal } from "../components/modals/ArtifactViewerModal";
import { ModelDetailModal } from "../components/modals/ModelDetailModal";
import { TriggerRunModal } from "../components/modals/TriggerRunModal";
import { useUIStore } from "../store/uiStore";
import { api } from "../services/api";
import { useSSE } from "../hooks/useSSE";

export function WorkspacePage() {
  const { id: projectId = "" } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { activeTab, setActiveTab, activeRunId, setActiveRunId, setIsTriggerRunOpen } = useUIStore();
  const [selectedMetric, setSelectedMetric] = useState<string>("f1");
  const [isManualRefreshing, setIsManualRefreshing] = useState(false);

  const invalidateAllProjectQueries = useCallback(() => {
    setIsManualRefreshing(true);
    queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    queryClient.invalidateQueries({ queryKey: ["datasets", projectId] });
    queryClient.invalidateQueries({ queryKey: ["runs", projectId] });
    queryClient.invalidateQueries({ queryKey: ["artifacts", projectId] });
    queryClient.invalidateQueries({ queryKey: ["code-executions", projectId] });
    queryClient.invalidateQueries({ queryKey: ["leaderboard", projectId] });
    queryClient.invalidateQueries({ queryKey: ["evaluation", projectId] });
    queryClient.invalidateQueries({ queryKey: ["report", projectId] });
    queryClient.invalidateQueries({ queryKey: ["artifact-content", projectId] });
    setTimeout(() => setIsManualRefreshing(false), 500);
  }, [queryClient, projectId]);

  // 1. Fetch Project Details
  const {
    data: project,
    isLoading: isProjectLoading,
    isError: isProjectError,
    error: projectError,
  } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    enabled: Boolean(projectId),
  });

  // 2. Fetch Datasets
  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => api.getDatasets(projectId),
    enabled: Boolean(projectId),
  });

  // 3. Fetch Runs (periodic refresh during run cycles)
  const { data: runs = [] } = useQuery({
    queryKey: ["runs", projectId],
    queryFn: () => api.getRuns(projectId),
    enabled: Boolean(projectId),
    refetchInterval: 3000,
  });

  // 4. Fetch Artifacts
  const { data: artifacts = [], isLoading: isArtifactsLoading } = useQuery({
    queryKey: ["artifacts", projectId],
    queryFn: () => api.getArtifacts(projectId),
    enabled: Boolean(projectId),
    refetchInterval: 4000,
  });

  // 5. Fetch Leaderboard
  const { data: leaderboardData, isLoading: isLeaderboardLoading } = useQuery({
    queryKey: ["leaderboard", projectId, selectedMetric],
    queryFn: () => api.getLeaderboard(projectId, selectedMetric),
    enabled: Boolean(projectId),
  });

  // 6. Fetch Code Executions (Coder Agent history)
  const { data: codeExecutions = [] } = useQuery({
    queryKey: ["code-executions", projectId],
    queryFn: () => api.getCodeExecutions(projectId),
    enabled: Boolean(projectId),
    refetchInterval: 3000,
  });

  // Auto-select latest run if none selected
  useEffect(() => {
    if (!activeRunId && runs.length > 0) {
      setActiveRunId(runs[0].id);
    }
  }, [runs, activeRunId, setActiveRunId]);

  const currentRunId = activeRunId || (runs.length > 0 ? runs[0].id : undefined);
  const activeRun = runs.find((r) => r.id === currentRunId);

  // Hook into live SSE events for active run; automatically invalidate all queries when complete
  const { events, isConnected, isCompleted, error: sseError } = useSSE(
    projectId,
    currentRunId,
    invalidateAllProjectQueries
  );

  const handleStageSelect = (stageKey: string) => {
    switch (stageKey) {
      case "profile":
        setActiveTab("profile");
        break;
      case "eda":
        setActiveTab("eda");
        break;
      case "feature_engineering":
      case "features":
        setActiveTab("features");
        break;
      case "model":
      case "models":
        setActiveTab("models");
        break;
      case "evaluator":
      case "evaluation":
        setActiveTab("evaluation");
        break;
      case "report":
        setActiveTab("report");
        break;
      case "coder":
        setActiveTab("coder");
        break;
      default:
        setActiveTab("overview");
        break;
    }
  };

  if (isProjectLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#090d16] text-slate-400 font-mono text-xs animate-pulse">
        Loading project workspace...
      </div>
    );
  }

  if (isProjectError || (!project && !isProjectLoading)) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-[#090d16] text-slate-300 font-sans space-y-4 p-6">
        <div className="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400">
          <FolderGit2 className="w-6 h-6" />
        </div>
        <div className="text-base font-semibold text-slate-100">Project Not Found</div>
        <p className="text-xs text-slate-400 font-mono max-w-sm text-center">
          {(projectError as any)?.message || `Project '${projectId}' does not exist or failed to load.`}
        </p>
        <Link
          to="/"
          className="px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs transition shadow-md shadow-sky-500/10"
        >
          Return to Projects
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#090d16] font-sans text-slate-100">
      {/* Top Header */}
      <Header
        project={project}
        activeRun={activeRun}
        onRefresh={invalidateAllProjectQueries}
        isRefreshing={isManualRefreshing}
      />

      {/* Main Three-Pane Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Nav */}
        <ProjectNav
          runCount={runs.length}
          modelCount={leaderboardData?.leaderboard?.length || 0}
          datasetCount={datasets.length}
          codeCount={codeExecutions.length}
        />

        {/* Center Main Panel */}
        <main className="flex-1 overflow-hidden flex flex-col bg-[#0a0f1d]">
          {activeTab === "overview" && (
            <AgentActivityFeed
              events={events}
              activeRun={activeRun}
              isConnected={isConnected}
              isCompleted={isCompleted}
              error={sseError}
              onSelectStage={handleStageSelect}
            />
          )}

          {activeTab === "dataset" && (
            <DatasetView
              projectId={projectId}
              datasets={datasets}
              onUploadSuccess={invalidateAllProjectQueries}
            />
          )}

          {activeTab === "profile" && <ProfileView projectId={projectId} artifacts={artifacts} />}

          {activeTab === "eda" && <EDAView projectId={projectId} artifacts={artifacts} />}

          {activeTab === "features" && <FeaturesView projectId={projectId} artifacts={artifacts} />}

          {activeTab === "models" && (
            <LeaderboardView
              data={leaderboardData}
              isLoading={isLeaderboardLoading}
              selectedMetric={selectedMetric}
              onSelectMetric={setSelectedMetric}
            />
          )}

          {activeTab === "evaluation" && <EvaluationView projectId={projectId} />}

          {activeTab === "report" && <ReportView projectId={projectId} />}

          {activeTab === "runs" && (
            <RunsView
              projectId={projectId}
              runs={runs}
              onTriggerNewRun={() => setIsTriggerRunOpen(true)}
            />
          )}

          {activeTab === "coder" && <CoderExecutionsView projectId={projectId} />}
        </main>

        {/* Right Artifacts Panel */}
        <ArtifactsPanel
          projectId={projectId}
          artifacts={artifacts}
          isLoading={isArtifactsLoading}
        />
      </div>

      {/* Modals */}
      <ArtifactViewerModal projectId={projectId} />
      <ModelDetailModal projectId={projectId} />
      <TriggerRunModal
        projectId={projectId}
        datasets={datasets}
        onTriggered={(newRunId) => {
          setActiveRunId(newRunId);
          setActiveTab("overview");
          invalidateAllProjectQueries();
        }}
      />
    </div>
  );
}

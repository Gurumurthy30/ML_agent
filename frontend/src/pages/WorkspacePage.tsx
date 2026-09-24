import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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
import { ArtifactViewerModal } from "../components/modals/ArtifactViewerModal";
import { ModelDetailModal } from "../components/modals/ModelDetailModal";
import { TriggerRunModal } from "../components/modals/TriggerRunModal";
import { useUIStore } from "../store/uiStore";
import { api } from "../services/api";
import { useSSE } from "../hooks/useSSE";

export function WorkspacePage() {
  const { id: projectId = "" } = useParams<{ id: string }>();
  const { activeTab, setActiveTab, activeRunId, setActiveRunId, setIsTriggerRunOpen } = useUIStore();
  const [selectedMetric, setSelectedMetric] = useState<string>("f1");

  // 1. Fetch Project Details
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    enabled: Boolean(projectId),
  });

  // 2. Fetch Datasets
  const { data: datasets = [], refetch: refetchDatasets } = useQuery({
    queryKey: ["datasets", projectId],
    queryFn: () => api.getDatasets(projectId),
    enabled: Boolean(projectId),
  });

  // 3. Fetch Runs
  const { data: runs = [], refetch: refetchRuns } = useQuery({
    queryKey: ["runs", projectId],
    queryFn: () => api.getRuns(projectId),
    enabled: Boolean(projectId),
    refetchInterval: 4000,
  });

  // 4. Fetch Artifacts
  const { data: artifacts = [], isLoading: isArtifactsLoading, refetch: refetchArtifacts } = useQuery({
    queryKey: ["artifacts", projectId],
    queryFn: () => api.getArtifacts(projectId),
    enabled: Boolean(projectId),
    refetchInterval: 6000,
  });

  // 5. Fetch Leaderboard
  const { data: leaderboardData, isLoading: isLeaderboardLoading, refetch: refetchLeaderboard } = useQuery({
    queryKey: ["leaderboard", projectId, selectedMetric],
    queryFn: () => api.getLeaderboard(projectId, selectedMetric),
    enabled: Boolean(projectId),
  });

  // Auto-select latest run if none selected
  useEffect(() => {
    if (!activeRunId && runs.length > 0) {
      setActiveRunId(runs[0].id);
    }
  }, [runs, activeRunId, setActiveRunId]);

  const activeRun = runs.find((r) => r.id === activeRunId) || (runs.length > 0 ? runs[0] : undefined);

  // Hook into live SSE events for active run
  const { events, isConnected, isCompleted } = useSSE(projectId, activeRun?.id);

  // Auto-refresh queries when a run completes
  useEffect(() => {
    if (isCompleted) {
      refetchRuns();
      refetchArtifacts();
      refetchLeaderboard();
    }
  }, [isCompleted, refetchRuns, refetchArtifacts, refetchLeaderboard]);

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
      default:
        setActiveTab("overview");
        break;
    }
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#090d16] font-sans text-slate-100">
      {/* Top Header */}
      <Header project={project} activeRun={activeRun} />

      {/* Main Three-Pane Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Nav */}
        <ProjectNav
          runCount={runs.length}
          modelCount={leaderboardData?.leaderboard?.length || 0}
          datasetCount={datasets.length}
        />

        {/* Center Main Panel */}
        <main className="flex-1 overflow-hidden flex flex-col bg-[#0a0f1d]">
          {activeTab === "overview" && (
            <AgentActivityFeed
              events={events}
              activeRun={activeRun}
              isConnected={isConnected}
              isCompleted={isCompleted}
              onSelectStage={handleStageSelect}
            />
          )}

          {activeTab === "dataset" && (
            <DatasetView
              projectId={projectId}
              datasets={datasets}
              onUploadSuccess={() => {
                refetchDatasets();
                refetchArtifacts();
              }}
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
        </main>

        {/* Right Artifacts Panel */}
        <ArtifactsPanel artifacts={artifacts} isLoading={isArtifactsLoading} />
      </div>

      {/* Modals */}
      <ArtifactViewerModal projectId={projectId} />
      <ModelDetailModal />
      <TriggerRunModal
        projectId={projectId}
        datasets={datasets}
        onTriggered={(newRunId) => {
          setActiveRunId(newRunId);
          setActiveTab("overview");
          refetchRuns();
        }}
      />
    </div>
  );
}

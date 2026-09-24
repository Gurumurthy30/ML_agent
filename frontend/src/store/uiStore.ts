import { create } from "zustand";
import { ArtifactIndex, LeaderboardItem } from "../types";

export type WorkspaceTab =
  | "overview"
  | "dataset"
  | "profile"
  | "eda"
  | "features"
  | "models"
  | "evaluation"
  | "report"
  | "runs";

interface UIState {
  activeTab: WorkspaceTab;
  setActiveTab: (tab: WorkspaceTab) => void;
  activeRunId: string | null;
  setActiveRunId: (runId: string | null) => void;
  isArtifactsPanelOpen: boolean;
  toggleArtifactsPanel: () => void;
  setArtifactsPanelOpen: (open: boolean) => void;
  viewingArtifact: ArtifactIndex | null;
  setViewingArtifact: (artifact: ArtifactIndex | null) => void;
  viewingModel: LeaderboardItem | null;
  setViewingModel: (model: LeaderboardItem | null) => void;
  isCreateProjectOpen: boolean;
  setIsCreateProjectOpen: (open: boolean) => void;
  isTriggerRunOpen: boolean;
  setIsTriggerRunOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeTab: "overview",
  setActiveTab: (activeTab) => set({ activeTab }),
  activeRunId: null,
  setActiveRunId: (activeRunId) => set({ activeRunId }),
  isArtifactsPanelOpen: true,
  toggleArtifactsPanel: () => set((state) => ({ isArtifactsPanelOpen: !state.isArtifactsPanelOpen })),
  setArtifactsPanelOpen: (isArtifactsPanelOpen) => set({ isArtifactsPanelOpen }),
  viewingArtifact: null,
  setViewingArtifact: (viewingArtifact) => set({ viewingArtifact }),
  viewingModel: null,
  setViewingModel: (viewingModel) => set({ viewingModel }),
  isCreateProjectOpen: false,
  setIsCreateProjectOpen: (isCreateProjectOpen) => set({ isCreateProjectOpen }),
  isTriggerRunOpen: false,
  setIsTriggerRunOpen: (isTriggerRunOpen) => set({ isTriggerRunOpen }),
}));

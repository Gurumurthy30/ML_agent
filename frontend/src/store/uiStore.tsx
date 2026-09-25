import { createContext, useContext, useState, ReactNode } from "react";
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
  | "runs"
  | "coder";

export interface UIState {
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

const UIContext = createContext<UIState | null>(null);

export function UIProvider({ children }: { children: ReactNode }) {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isArtifactsPanelOpen, setArtifactsPanelOpen] = useState<boolean>(true);
  const [viewingArtifact, setViewingArtifact] = useState<ArtifactIndex | null>(null);
  const [viewingModel, setViewingModel] = useState<LeaderboardItem | null>(null);
  const [isCreateProjectOpen, setIsCreateProjectOpen] = useState<boolean>(false);
  const [isTriggerRunOpen, setIsTriggerRunOpen] = useState<boolean>(false);

  const toggleArtifactsPanel = () => setArtifactsPanelOpen((prev) => !prev);

  const value: UIState = {
    activeTab,
    setActiveTab,
    activeRunId,
    setActiveRunId,
    isArtifactsPanelOpen,
    toggleArtifactsPanel,
    setArtifactsPanelOpen,
    viewingArtifact,
    setViewingArtifact,
    viewingModel,
    setViewingModel,
    isCreateProjectOpen,
    setIsCreateProjectOpen,
    isTriggerRunOpen,
    setIsTriggerRunOpen,
  };

  return <UIContext.Provider value={value}>{children}</UIContext.Provider>;
}

export function useUIStore(): UIState {
  const ctx = useContext(UIContext);
  if (!ctx) {
    throw new Error("useUIStore must be used within a UIProvider");
  }
  return ctx;
}

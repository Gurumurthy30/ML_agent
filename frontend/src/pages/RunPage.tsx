import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useUIStore } from "../store/uiStore";
import { WorkspacePage } from "./WorkspacePage";

export function RunPage() {
  const { runId } = useParams<{ id: string; runId: string }>();
  const { setActiveRunId, setActiveTab } = useUIStore();

  useEffect(() => {
    if (runId) {
      setActiveRunId(runId);
      setActiveTab("overview");
    }
  }, [runId, setActiveRunId, setActiveTab]);

  return <WorkspacePage />;
}

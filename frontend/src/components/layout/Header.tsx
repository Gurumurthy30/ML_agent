import { Link, useNavigate } from "react-router-dom";
import { FolderGit2, Play, PanelRightClose, PanelRightOpen, Cpu } from "lucide-react";
import { useUIStore } from "../../store/uiStore";
import { Project, WorkflowRun } from "../../types";
import { StatusBadge } from "../common/Badge";

interface HeaderProps {
  project?: Project;
  activeRun?: WorkflowRun;
}

export function Header({ project, activeRun }: HeaderProps) {
  const navigate = useNavigate();
  const { isArtifactsPanelOpen, toggleArtifactsPanel, setIsTriggerRunOpen } = useUIStore();

  return (
    <header className="h-14 border-b border-slate-800 bg-[#0b101b] px-4 flex items-center justify-between z-20 select-none">
      {/* Left: Branding & Breadcrumbs */}
      <div className="flex items-center gap-3">
        <Link
          to="/"
          className="flex items-center gap-2 text-slate-100 font-semibold tracking-tight hover:text-sky-400 transition"
        >
          <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
            <Cpu className="w-4 h-4" />
          </div>
          <span className="font-mono text-sm tracking-wider font-bold">ML_AGENT</span>
        </Link>

        {project && (
          <>
            <span className="text-slate-600 font-mono">/</span>
            <div className="flex items-center gap-2">
              <span className="text-slate-200 text-sm font-medium">{project.name}</span>
              <span className="text-xs font-mono text-slate-500">({project.id})</span>
            </div>
          </>
        )}

        {activeRun && (
          <div className="hidden md:flex items-center gap-2 ml-2 pl-3 border-l border-slate-800">
            <span className="text-xs text-slate-400">Run:</span>
            <span className="font-mono text-xs text-slate-300">{activeRun.id}</span>
            <StatusBadge status={activeRun.status} />
          </div>
        )}
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2.5">
        {project && (
          <button
            onClick={() => setIsTriggerRunOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-sky-500 hover:bg-sky-400 text-slate-950 font-medium text-xs shadow-sm shadow-sky-500/20 transition active:scale-95"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>New Run</span>
          </button>
        )}

        <button
          onClick={() => navigate("/")}
          className="px-2.5 py-1.5 rounded-md border border-slate-800 hover:bg-slate-800/60 text-slate-300 text-xs transition"
          title="All Projects"
        >
          <FolderGit2 className="w-4 h-4" />
        </button>

        {project && (
          <button
            onClick={toggleArtifactsPanel}
            className="px-2.5 py-1.5 rounded-md border border-slate-800 hover:bg-slate-800/60 text-slate-300 text-xs transition"
            title={isArtifactsPanelOpen ? "Hide Artifacts Panel" : "Show Artifacts Panel"}
          >
            {isArtifactsPanelOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
          </button>
        )}
      </div>
    </header>
  );
}

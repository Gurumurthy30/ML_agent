import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  FolderGit2,
  Plus,
  ArrowRight,
  Cpu,
  Clock,
  AlertTriangle,
  Trash2,
} from "lucide-react";
import { api } from "../services/api";
import { useUIStore } from "../store/uiStore";
import { ProjectCreateModal } from "../components/modals/ProjectCreateModal";
import { DeleteProjectModal } from "../components/modals/DeleteProjectModal";
import { Project } from "../types";

export function ProjectsPage() {
  const navigate = useNavigate();
  const { setIsCreateProjectOpen } = useUIStore();
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);

  const {
    data: projects = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.getProjects(),
  });

  return (
    <div className="min-h-screen bg-[#090d16] flex flex-col font-sans">
      {/* Top Header */}
      <header className="h-16 border-b border-slate-800 bg-[#0b101b] px-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <div className="font-mono text-sm font-bold tracking-wider text-slate-100 flex items-center gap-2">
              <span>ML_AGENT</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20 font-sans">
                v1.0
              </span>
            </div>
            <div className="text-[11px] text-slate-400">Autonomous Tabular Machine Learning Platform</div>
          </div>
        </div>

        <button
          onClick={() => setIsCreateProjectOpen(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs transition active:scale-95 shadow-md shadow-sky-500/10"
        >
          <Plus className="w-4 h-4" />
          <span>New Project</span>
        </button>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-6xl w-full mx-auto p-6 md:p-8 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-100">Projects</h1>
            <p className="text-xs text-slate-400 mt-1">
              Select an existing workspace to view models and artifacts, or start an autonomous run.
            </p>
          </div>
          <div className="text-xs text-slate-400 font-mono">
            {projects.length} {projects.length === 1 ? "project" : "projects"} registered
          </div>
        </div>

        {isLoading && (
          <div className="py-20 text-center text-xs text-slate-500 font-mono animate-pulse">
            Loading workspaces...
          </div>
        )}

        {isError && (
          <div className="p-8 border border-rose-500/30 rounded-2xl bg-rose-500/5 text-center space-y-3">
            <AlertTriangle className="w-8 h-8 text-rose-400 mx-auto" />
            <div className="text-sm font-semibold text-rose-200">Failed to load workspaces</div>
            <p className="text-xs text-rose-300 font-mono">
              {(error as any)?.message || "A network or server error occurred."}
            </p>
            <button
              onClick={() => refetch()}
              className="mt-2 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 border border-rose-500/40 text-xs font-semibold transition"
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !isError && projects.length === 0 && (
          <div className="p-12 border border-slate-800 rounded-2xl bg-slate-900/30 text-center space-y-3">
            <FolderGit2 className="w-10 h-10 text-slate-600 mx-auto" />
            <div className="text-sm font-semibold text-slate-200">No Projects Found</div>
            <p className="text-xs text-slate-400 max-w-md mx-auto">
              Create your first project by uploading a tabular CSV dataset. The team of agents will autonomously profile, engineer features, train candidates, and evaluate.
            </p>
            <button
              onClick={() => setIsCreateProjectOpen(true)}
              className="mt-2 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold text-xs transition"
            >
              <Plus className="w-4 h-4" />
              <span>Create First Project</span>
            </button>
          </div>
        )}

        {/* Project Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => (
            <div
              key={p.id}
              onClick={() => navigate(`/projects/${p.id}`)}
              className="p-5 rounded-xl border border-slate-800 bg-[#0f172a]/60 hover:bg-[#0f172a] hover:border-slate-700 transition cursor-pointer flex flex-col justify-between group shadow-sm"
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-slate-100 group-hover:text-sky-400 transition text-sm">
                    {p.name}
                  </h3>
                  <ArrowRight className="w-4 h-4 text-slate-600 group-hover:text-sky-400 group-hover:translate-x-0.5 transition flex-shrink-0 mt-0.5" />
                </div>

                <div className="text-xs text-slate-400 line-clamp-2">
                  {p.description || "Autonomous tabular machine learning project."}
                </div>
              </div>

              <div className="pt-4 mt-4 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono text-slate-500">
                <span className="truncate max-w-[120px]">{p.id}</span>
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {new Date(p.created_at).toLocaleDateString()}
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setProjectToDelete(p);
                    }}
                    className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition"
                    title="Delete project"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </main>

      <ProjectCreateModal onCreated={() => refetch()} />
      <DeleteProjectModal
        project={projectToDelete}
        isOpen={Boolean(projectToDelete)}
        onClose={() => setProjectToDelete(null)}
        onDeleted={() => refetch()}
      />
    </div>
  );
}

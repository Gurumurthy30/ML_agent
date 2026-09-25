import { useState } from "react";
import { AlertTriangle, Loader2, Trash2, X } from "lucide-react";
import { Project } from "../../types";
import { api } from "../../services/api";

interface DeleteProjectModalProps {
  project: Project | null;
  isOpen: boolean;
  onClose: () => void;
  onDeleted: () => void;
}

export function DeleteProjectModal({
  project,
  isOpen,
  onClose,
  onDeleted,
}: DeleteProjectModalProps) {
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen || !project) return null;

  const handleDelete = async () => {
    setIsDeleting(true);
    setError(null);
    try {
      await api.deleteProject(project.id);
      onDeleted();
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to delete project");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in font-sans">
      <div className="bg-[#0f172a] border border-rose-500/30 rounded-2xl w-full max-w-md overflow-hidden shadow-2xl shadow-rose-950/40">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-rose-500/5">
          <div className="flex items-center gap-2.5 text-rose-400">
            <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20">
              <Trash2 className="w-4 h-4 text-rose-400" />
            </div>
            <h2 className="font-semibold text-sm text-slate-100">Delete Project</h2>
          </div>
          <button
            onClick={onClose}
            disabled={isDeleting}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition disabled:opacity-50"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 text-xs">
          {error && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-300 flex items-center gap-2 font-mono">
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <p className="text-slate-300 leading-relaxed">
            Are you sure you want to permanently delete{" "}
            <span className="font-semibold text-slate-100 font-mono">
              {project.name}
            </span>{" "}
            (<span className="font-mono text-slate-400">{project.id}</span>)?
          </p>

          <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-[11px] text-slate-400 space-y-1.5">
            <div className="font-semibold text-rose-300 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>This action cannot be undone.</span>
            </div>
            <p>
              All datasets, engineered features, trained models, MLflow experiment runs, and generated reports will be permanently purged.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/60 flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-slate-100 text-xs font-semibold transition disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDelete}
            disabled={isDeleting}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold transition disabled:opacity-50 shadow-md shadow-rose-900/30"
          >
            {isDeleting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Deleting...</span>
              </>
            ) : (
              <>
                <Trash2 className="w-3.5 h-3.5" />
                <span>Delete Project</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

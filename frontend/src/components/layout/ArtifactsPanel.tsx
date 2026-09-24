import { useState } from "react";
import {
  FileCode,
  FileJson,
  FileSpreadsheet,
  FileText,
  ChevronDown,
  ChevronRight,
  ExternalLink,
} from "lucide-react";
import { ArtifactIndex } from "../../types";
import { useUIStore } from "../../store/uiStore";

interface ArtifactsPanelProps {
  artifacts: ArtifactIndex[];
  isLoading?: boolean;
}

export function ArtifactsPanel({ artifacts, isLoading }: ArtifactsPanelProps) {
  const { isArtifactsPanelOpen, setViewingArtifact } = useUIStore();
  const [collapsedStages, setCollapsedStages] = useState<Record<string, boolean>>({});

  if (!isArtifactsPanelOpen) {
    return null;
  }

  const toggleStage = (stage: string) => {
    setCollapsedStages((prev) => ({ ...prev, [stage]: !prev[stage] }));
  };

  // Group artifacts by stage
  const grouped: Record<string, ArtifactIndex[]> = {};
  for (const art of artifacts) {
    const stage = art.stage || "other";
    if (!grouped[stage]) grouped[stage] = [];
    grouped[stage].push(art);
  }

  const getFileIcon = (filePath: string) => {
    const lower = filePath.toLowerCase();
    if (lower.endsWith(".json")) return <FileJson className="w-3.5 h-3.5 text-amber-400" />;
    if (lower.endsWith(".md")) return <FileText className="w-3.5 h-3.5 text-sky-400" />;
    if (lower.endsWith(".parquet") || lower.endsWith(".csv"))
      return <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />;
    return <FileCode className="w-3.5 h-3.5 text-purple-400" />;
  };

  const stageOrder = ["profile", "eda", "features", "models", "evaluations", "reports", "other"];

  return (
    <aside className="w-72 flex-shrink-0 border-l border-slate-800 bg-[#090d16] flex flex-col h-full select-none">
      <div className="p-3 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-slate-200 uppercase tracking-wider font-mono">
            Artifacts
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
            {artifacts.length}
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {isLoading && (
          <div className="p-4 text-center text-xs text-slate-500 animate-pulse">
            Loading artifacts...
          </div>
        )}

        {!isLoading && artifacts.length === 0 && (
          <div className="p-4 text-center text-xs text-slate-500">
            No artifacts generated yet. Run a workflow to create artifacts.
          </div>
        )}

        {stageOrder.map((stage) => {
          const items = grouped[stage];
          if (!items || items.length === 0) return null;
          const isCollapsed = collapsedStages[stage];

          return (
            <div key={stage} className="border border-slate-800/80 rounded-md bg-slate-900/30 overflow-hidden">
              <button
                onClick={() => toggleStage(stage)}
                className="w-full px-2.5 py-1.5 bg-slate-800/50 flex items-center justify-between text-xs font-medium text-slate-300 hover:bg-slate-800 transition"
              >
                <div className="flex items-center gap-1.5 uppercase font-mono text-[11px] text-slate-400">
                  {isCollapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  <span>{stage}</span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">{items.length}</span>
              </button>

              {!isCollapsed && (
                <div className="p-1 space-y-0.5">
                  {items.map((art) => {
                    const filename = art.file_path.split(/[\\/]/).pop() || art.id;
                    return (
                      <button
                        key={art.id}
                        onClick={() => setViewingArtifact(art)}
                        className="w-full text-left px-2 py-1.5 rounded flex items-center justify-between gap-2 text-xs text-slate-300 hover:bg-slate-800/80 hover:text-sky-300 transition group"
                        title={art.summary || art.file_path}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          {getFileIcon(art.file_path)}
                          <span className="truncate font-mono text-[11px]">{filename}</span>
                        </div>
                        <ExternalLink className="w-3 h-3 text-slate-600 opacity-0 group-hover:opacity-100 flex-shrink-0" />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}

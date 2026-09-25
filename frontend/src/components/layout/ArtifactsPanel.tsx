import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileCode,
  FileJson,
  FileSpreadsheet,
  FileText,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Terminal,
  Check,
  Copy,
  AlertCircle,
  Clock,
  Maximize2,
} from "lucide-react";
import { ArtifactIndex, CodeExecution } from "../../types";
import { useUIStore } from "../../store/uiStore";
import { api } from "../../services/api";

interface ArtifactsPanelProps {
  projectId?: string;
  artifacts: ArtifactIndex[];
  isLoading?: boolean;
}

export function ArtifactsPanel({ projectId, artifacts, isLoading }: ArtifactsPanelProps) {
  const { isArtifactsPanelOpen, setViewingArtifact, setActiveTab } = useUIStore();
  const [activePanelTab, setActivePanelTab] = useState<"artifacts" | "executions">("executions");
  const [collapsedStages, setCollapsedStages] = useState<Record<string, boolean>>({});
  const [expandedExecId, setExpandedExecId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<Record<string, "code" | "result">>({});

  // Query code executions
  const { data: executions = [], isLoading: isExecutionsLoading } = useQuery({
    queryKey: ["code-executions", projectId],
    queryFn: () => (projectId ? api.getCodeExecutions(projectId) : Promise.resolve([])),
    enabled: Boolean(projectId),
    refetchInterval: 3000,
  });

  if (!isArtifactsPanelOpen) {
    return null;
  }

  const toggleStage = (stage: string) => {
    setCollapsedStages((prev) => ({ ...prev, [stage]: !prev[stage] }));
  };

  const handleCopyCode = (id: string, code: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(code);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
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
    <aside className="w-80 lg:w-96 flex-shrink-0 border-l border-slate-800 bg-[#090d16] flex flex-col h-full select-none font-sans">
      {/* Top Sidebar Tab Selector */}
      <div className="border-b border-slate-800 bg-[#0b101b] px-2 pt-2 flex items-center gap-1">
        <button
          onClick={() => setActivePanelTab("executions")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-2 text-xs font-mono font-medium rounded-t-lg transition border-b-2 ${
            activePanelTab === "executions"
              ? "border-sky-500 text-sky-300 bg-slate-900/60"
              : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/30"
          }`}
        >
          <Terminal className="w-3.5 h-3.5 text-sky-400" />
          <span>Code Runs</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-300 font-mono">
            {executions.length}
          </span>
        </button>

        <button
          onClick={() => setActivePanelTab("artifacts")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-2 text-xs font-mono font-medium rounded-t-lg transition border-b-2 ${
            activePanelTab === "artifacts"
              ? "border-sky-500 text-sky-300 bg-slate-900/60"
              : "border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/30"
          }`}
        >
          <FileCode className="w-3.5 h-3.5 text-amber-400" />
          <span>Artifacts</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-300 font-mono">
            {artifacts.length}
          </span>
        </button>
      </div>

      {/* Panel Body */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2.5">
        {/* ===================== TAB: CODE EXECUTIONS ===================== */}
        {activePanelTab === "executions" && (
          <div className="space-y-2.5">
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider font-semibold">
                Coder Agent History
              </span>
              <button
                onClick={() => setActiveTab("coder")}
                className="flex items-center gap-1 text-[11px] font-mono text-sky-400 hover:text-sky-300 transition"
                title="Open expanded monitor view"
              >
                <span>Full Monitor</span>
                <Maximize2 className="w-3 h-3" />
              </button>
            </div>

            {isExecutionsLoading && (
              <div className="p-8 text-center text-xs text-slate-500 font-mono animate-pulse">
                Fetching code executions...
              </div>
            )}

            {!isExecutionsLoading && executions.length === 0 && (
              <div className="p-8 border border-slate-800 rounded-xl bg-slate-900/30 text-center space-y-2">
                <Terminal className="w-8 h-8 text-slate-600 mx-auto" />
                <div className="text-xs text-slate-400 font-medium">No code executed yet</div>
                <div className="text-[11px] text-slate-500 font-mono">
                  Trigger an autonomous run to monitor scripts written &amp; run by Coder.
                </div>
              </div>
            )}

            {executions.map((exec: CodeExecution) => {
              const isExpanded = expandedExecId === exec.id;
              const mode = viewMode[exec.id] || "code";

              return (
                <div
                  key={exec.id}
                  className={`border rounded-xl bg-slate-900/70 overflow-hidden transition ${
                    isExpanded ? "border-sky-500/40 shadow-lg shadow-sky-950/20" : "border-slate-800/80 hover:border-slate-700"
                  }`}
                >
                  {/* Card Header */}
                  <div
                    onClick={() => setExpandedExecId(isExpanded ? null : exec.id)}
                    className="p-2.5 cursor-pointer hover:bg-slate-850/50 transition space-y-1.5"
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/20">
                          {exec.stage}
                        </span>
                        <span className="font-mono text-xs font-semibold text-slate-200 truncate">
                          {exec.script_name || "run_task.py"}
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold ${
                            exec.success
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                              : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          }`}
                        >
                          {exec.success ? "SUCCESS" : "FAILED"}
                        </span>
                        {isExpanded ? (
                          <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                        ) : (
                          <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                        )}
                      </div>
                    </div>

                    {exec.task_description && (
                      <p className="text-[11px] text-slate-400 line-clamp-1">
                        {exec.task_description}
                      </p>
                    )}

                    <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-0.5">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {exec.executed_at
                          ? new Date(exec.executed_at).toLocaleTimeString()
                          : "just now"}
                      </span>
                      <span>
                        {exec.duration_ms ? `${(exec.duration_ms / 1000).toFixed(2)}s` : "0s"} • exit {exec.exit_code}
                      </span>
                    </div>
                  </div>

                  {/* Expanded Content: Code & Results */}
                  {isExpanded && (
                    <div className="border-t border-slate-800 bg-[#060a12] p-2 space-y-2">
                      {/* Sub-view switcher: Code vs Results */}
                      <div className="flex items-center justify-between border-b border-slate-800/80 pb-1.5 px-0.5">
                        <div className="flex items-center gap-1 font-mono text-[11px]">
                          <button
                            type="button"
                            onClick={() => setViewMode((prev) => ({ ...prev, [exec.id]: "code" }))}
                            className={`px-2 py-0.5 rounded transition ${
                              mode === "code"
                                ? "bg-slate-800 text-sky-300 font-semibold"
                                : "text-slate-500 hover:text-slate-300"
                            }`}
                          >
                            Code
                          </button>
                          <button
                            type="button"
                            onClick={() => setViewMode((prev) => ({ ...prev, [exec.id]: "result" }))}
                            className={`px-2 py-0.5 rounded transition flex items-center gap-1 ${
                              mode === "result"
                                ? "bg-slate-800 text-sky-300 font-semibold"
                                : "text-slate-500 hover:text-slate-300"
                            }`}
                          >
                            <span>Result</span>
                            {!exec.success && <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
                          </button>
                        </div>

                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={(e) => handleCopyCode(exec.id, exec.code, e)}
                            className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono transition"
                            title="Copy code"
                          >
                            {copiedId === exec.id ? (
                              <>
                                <Check className="w-3 h-3 text-emerald-400" />
                                <span className="text-emerald-400">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3 h-3" />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>

                      {/* Display Code */}
                      {mode === "code" && (
                        <div className="relative">
                          <pre className="p-2.5 rounded-lg bg-[#0b0f19] border border-slate-800/80 font-mono text-[11px] text-slate-200 overflow-x-auto max-h-64 whitespace-pre leading-relaxed select-text">
                            <code>{exec.code || "# No code recorded"}</code>
                          </pre>
                        </div>
                      )}

                      {/* Display Result (Stdout & Stderr) */}
                      {mode === "result" && (
                        <div className="space-y-2">
                          {exec.stderr && (
                            <div className="p-2 rounded-lg bg-rose-950/30 border border-rose-500/30 text-rose-300 font-mono text-[11px] space-y-1">
                              <div className="flex items-center gap-1.5 font-bold text-rose-400">
                                <AlertCircle className="w-3.5 h-3.5" />
                                <span>STDERR / Error Traceback</span>
                              </div>
                              <pre className="overflow-x-auto max-h-40 whitespace-pre-wrap leading-relaxed select-text">
                                {exec.stderr}
                              </pre>
                            </div>
                          )}

                          <div className="p-2.5 rounded-lg bg-[#0b0f19] border border-slate-800/80 space-y-1">
                            <div className="text-[10px] font-mono text-slate-400 uppercase font-semibold flex items-center justify-between">
                              <span>Output (STDOUT)</span>
                              <span className="text-slate-500">Exit Code: {exec.exit_code}</span>
                            </div>
                            <pre className="font-mono text-[11px] text-emerald-300/90 overflow-x-auto max-h-56 whitespace-pre-wrap leading-relaxed select-text">
                              {exec.stdout ? exec.stdout : "(Empty output)"}
                            </pre>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ===================== TAB: ARTIFACTS ===================== */}
        {activePanelTab === "artifacts" && (
          <div className="space-y-3">
            {isLoading && (
              <div className="p-4 text-center text-xs text-slate-500 animate-pulse font-mono">
                Loading artifacts...
              </div>
            )}

            {!isLoading && artifacts.length === 0 && (
              <div className="p-4 text-center text-xs text-slate-500 font-mono">
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
                        const filePath = art.file_path || art.path || "";
                        const filename = filePath.split(/[\\/]/).pop() || art.id;
                        return (
                          <button
                            key={art.id}
                            onClick={() => setViewingArtifact(art)}
                            className="w-full text-left px-2 py-1.5 rounded flex items-center justify-between gap-2 text-xs text-slate-300 hover:bg-slate-800/80 hover:text-sky-300 transition group"
                            title={art.summary || filePath}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              {getFileIcon(filePath)}
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
        )}
      </div>
    </aside>
  );
}

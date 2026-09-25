import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Terminal,
  Check,
  Copy,
  Download,
  AlertCircle,
  Clock,
  CheckCircle2,
  XCircle,
  Code2,
  FileCode,
  Sparkles,
} from "lucide-react";
import { CodeExecution } from "../../types";
import { api } from "../../services/api";

interface CoderExecutionsViewProps {
  projectId: string;
}

export function CoderExecutionsView({ projectId }: CoderExecutionsViewProps) {
  const [selectedExecId, setSelectedExecId] = useState<string | null>(null);
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [activeTab, setActiveTab] = useState<"code" | "output" | "task">("code");
  const [copied, setCopied] = useState(false);

  const {
    data: executions = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["code-executions", projectId],
    queryFn: () => api.getCodeExecutions(projectId),
    enabled: Boolean(projectId),
    refetchInterval: 3000,
  });

  // Filtered list
  const filtered = executions.filter((exec) => {
    if (stageFilter !== "all" && exec.stage.toLowerCase() !== stageFilter.toLowerCase()) {
      return false;
    }
    if (statusFilter === "success" && !exec.success) return false;
    if (statusFilter === "failed" && exec.success) return false;
    return true;
  });

  // Selected item
  const selected = executions.find((e) => e.id === selectedExecId) || filtered[0] || executions[0] || null;

  const handleCopyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleDownloadCode = (exec: CodeExecution) => {
    const blob = new Blob([exec.code], { type: "text/x-python" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = exec.script_name || `coder_${exec.stage}_${exec.id}.py`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const totalRuns = executions.length;
  const successRuns = executions.filter((e) => e.success).length;
  const failedRuns = executions.filter((e) => !e.success).length;
  const stages = Array.from(new Set(executions.map((e) => e.stage)));

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#0a0f1d] font-sans">
      {/* Top Header & Metrics Bar */}
      <div className="p-4 md:p-6 border-b border-slate-800 bg-[#0b101b] space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
                <Terminal className="w-4 h-4" />
              </div>
              <h1 className="text-base font-bold text-slate-100 font-mono tracking-tight">
                Coder Agent Execution Monitor
              </h1>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Inspect generated Python scripts, stdout terminal streams, stderr tracebacks, and execution metrics in real-time.
            </p>
          </div>

          {/* Execution Metrics Summary */}
          <div className="flex items-center gap-3 text-xs font-mono">
            <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 flex items-center gap-2">
              <span className="text-slate-500">Total:</span>
              <span className="font-bold text-slate-200">{totalRuns}</span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-2 text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{successRuns} passed</span>
            </div>
            {failedRuns > 0 && (
              <div className="px-3 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center gap-2 text-rose-400">
                <XCircle className="w-3.5 h-3.5" />
                <span>{failedRuns} failed</span>
              </div>
            )}
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-800/80 text-xs font-mono">
          <span className="text-slate-500 text-[11px] uppercase mr-1">Stage:</span>
          <button
            onClick={() => setStageFilter("all")}
            className={`px-2.5 py-1 rounded-md transition ${
              stageFilter === "all"
                ? "bg-sky-500 text-slate-950 font-bold"
                : "bg-slate-850 hover:bg-slate-800 text-slate-400"
            }`}
          >
            All ({totalRuns})
          </button>
          {stages.map((stg) => (
            <button
              key={stg}
              onClick={() => setStageFilter(stg)}
              className={`px-2.5 py-1 rounded-md transition uppercase ${
                stageFilter === stg
                  ? "bg-sky-500 text-slate-950 font-bold"
                  : "bg-slate-850 hover:bg-slate-800 text-slate-400"
              }`}
            >
              {stg} ({executions.filter((e) => e.stage === stg).length})
            </button>
          ))}

          <span className="text-slate-600 mx-2">|</span>

          <span className="text-slate-500 text-[11px] uppercase mr-1">Status:</span>
          <button
            onClick={() => setStatusFilter("all")}
            className={`px-2.5 py-1 rounded-md transition ${
              statusFilter === "all"
                ? "bg-slate-700 text-slate-100 font-bold"
                : "bg-slate-850 hover:bg-slate-800 text-slate-400"
            }`}
          >
            All
          </button>
          <button
            onClick={() => setStatusFilter("success")}
            className={`px-2.5 py-1 rounded-md transition ${
              statusFilter === "success"
                ? "bg-emerald-500 text-slate-950 font-bold"
                : "bg-slate-850 hover:bg-slate-800 text-slate-400"
            }`}
          >
            Success
          </button>
          <button
            onClick={() => setStatusFilter("failed")}
            className={`px-2.5 py-1 rounded-md transition ${
              statusFilter === "failed"
                ? "bg-rose-500 text-white font-bold"
                : "bg-slate-850 hover:bg-slate-800 text-slate-400"
            }`}
          >
            Failed
          </button>
        </div>
      </div>

      {/* Main Two-Column View */}
      <div className="flex-1 overflow-hidden flex flex-col md:flex-row">
        {/* Left Column: Executions List */}
        <div className="w-full md:w-80 lg:w-96 border-r border-slate-800 overflow-y-auto p-3 space-y-2 bg-[#090d16]/70 flex-shrink-0">
          {isLoading && (
            <div className="p-8 text-center text-xs text-slate-500 font-mono animate-pulse">
              Loading execution history...
            </div>
          )}

          {isError && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono">
              {(error as any)?.message || "Failed to load code executions"}
            </div>
          )}

          {!isLoading && filtered.length === 0 && (
            <div className="p-8 border border-slate-800 rounded-xl bg-slate-900/30 text-center space-y-2">
              <Terminal className="w-7 h-7 text-slate-600 mx-auto" />
              <div className="text-xs text-slate-400 font-medium">No matching executions</div>
              <div className="text-[11px] text-slate-500 font-mono">
                {executions.length === 0
                  ? "Start a run to observe Coder agent activity."
                  : "Try clearing filters to see other executions."}
              </div>
            </div>
          )}

          {filtered.map((exec) => {
            const isSelected = selected?.id === exec.id;
            return (
              <div
                key={exec.id}
                onClick={() => setSelectedExecId(exec.id)}
                className={`p-3 rounded-xl border transition cursor-pointer space-y-2 ${
                  isSelected
                    ? "bg-slate-800/90 border-sky-500 shadow-md shadow-sky-950/30"
                    : "bg-[#0f172a]/60 border-slate-800/80 hover:bg-slate-800/50 hover:border-slate-700"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/20">
                      {exec.stage}
                    </span>
                    <span className="font-mono text-xs font-semibold text-slate-200 truncate">
                      {exec.script_name || "run_task.py"}
                    </span>
                  </div>

                  <span
                    className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-bold flex-shrink-0 ${
                      exec.success
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                    }`}
                  >
                    {exec.success ? "PASS" : "FAIL"}
                  </span>
                </div>

                {exec.task_description && (
                  <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                    {exec.task_description}
                  </p>
                )}

                <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-1 border-t border-slate-800/60">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {exec.executed_at ? new Date(exec.executed_at).toLocaleTimeString() : "just now"}
                  </span>
                  <span>
                    {exec.duration_ms ? `${(exec.duration_ms / 1000).toFixed(2)}s` : "0s"} • exit {exec.exit_code}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right Column: Execution Inspector */}
        <div className="flex-1 overflow-hidden flex flex-col bg-[#080c14]">
          {selected ? (
            <>
              {/* Inspector Header */}
              <div className="p-4 border-b border-slate-800 bg-[#0b101b] flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-sky-400">
                    <FileCode className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 font-mono">
                      <span className="text-sm font-bold text-slate-100">
                        {selected.script_name || "run_task.py"}
                      </span>
                      <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/20">
                        {selected.stage}
                      </span>
                      {selected.attempt && selected.attempt > 1 && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                          Attempt #{selected.attempt}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] font-mono text-slate-500 mt-0.5 flex items-center gap-3">
                      <span>ID: {selected.id}</span>
                      <span>•</span>
                      <span>
                        {selected.duration_ms ? `${(selected.duration_ms / 1000).toFixed(2)}s` : "0s"}
                      </span>
                      <span>•</span>
                      <span className={selected.success ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                        Exit code: {selected.exit_code}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Sub-tab navigation & Actions */}
                <div className="flex items-center gap-2 font-mono text-xs">
                  <div className="flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5">
                    <button
                      onClick={() => setActiveTab("code")}
                      className={`px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${
                        activeTab === "code"
                          ? "bg-slate-800 text-sky-300 font-semibold shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      <Code2 className="w-3.5 h-3.5" />
                      <span>Code</span>
                    </button>
                    <button
                      onClick={() => setActiveTab("output")}
                      className={`px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${
                        activeTab === "output"
                          ? "bg-slate-800 text-sky-300 font-semibold shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      <Terminal className="w-3.5 h-3.5" />
                      <span>Result</span>
                      {!selected.success && <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />}
                    </button>
                    {selected.task_description && (
                      <button
                        onClick={() => setActiveTab("task")}
                        className={`px-3 py-1.5 rounded-md transition flex items-center gap-1.5 ${
                          activeTab === "task"
                            ? "bg-slate-800 text-sky-300 font-semibold shadow-sm"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Prompt</span>
                      </button>
                    )}
                  </div>

                  <button
                    onClick={() => handleCopyCode(selected.code)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-850 hover:bg-slate-800 border border-slate-750 text-slate-200 text-xs transition"
                    title="Copy code"
                  >
                    {copied ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>

                  <button
                    onClick={() => handleDownloadCode(selected)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-850 hover:bg-slate-800 border border-slate-750 text-slate-200 text-xs transition"
                    title="Download python script"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download</span>
                  </button>
                </div>
              </div>

              {/* Inspector Content Body */}
              <div className="flex-1 overflow-y-auto p-4 md:p-6">
                {activeTab === "code" && (
                  <div className="rounded-xl border border-slate-800 bg-[#050810] overflow-hidden shadow-xl">
                    <div className="px-4 py-2 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between text-xs font-mono text-slate-400">
                      <span>Python Script ({selected.code ? selected.code.split("\n").length : 0} lines)</span>
                      <span className="text-slate-500">Standalone Subprocess Sandbox</span>
                    </div>
                    <pre className="p-4 font-mono text-xs text-slate-200 overflow-x-auto leading-relaxed select-text">
                      <code>{selected.code || "# No code recorded"}</code>
                    </pre>
                  </div>
                )}

                {activeTab === "output" && (
                  <div className="space-y-4">
                    {/* Error Box if failed */}
                    {selected.stderr && (
                      <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 overflow-hidden shadow-lg shadow-rose-950/20">
                        <div className="px-4 py-2 bg-rose-500/10 border-b border-rose-500/30 flex items-center justify-between text-xs font-mono text-rose-300">
                          <span className="flex items-center gap-2 font-bold">
                            <AlertCircle className="w-4 h-4 text-rose-400" />
                            <span>STDERR / Error Traceback</span>
                          </span>
                          <span>Exit code {selected.exit_code}</span>
                        </div>
                        <pre className="p-4 font-mono text-xs text-rose-200 overflow-x-auto whitespace-pre-wrap leading-relaxed select-text">
                          {selected.stderr}
                        </pre>
                      </div>
                    )}

                    {/* Standard Output Box */}
                    <div className="rounded-xl border border-slate-800 bg-[#050810] overflow-hidden shadow-xl">
                      <div className="px-4 py-2 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between text-xs font-mono text-slate-400">
                        <span className="flex items-center gap-2">
                          <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Console Output (STDOUT)</span>
                        </span>
                        <span className="text-slate-500">Process return: {selected.exit_code}</span>
                      </div>
                      <pre className="p-4 font-mono text-xs text-emerald-300/90 overflow-x-auto whitespace-pre-wrap leading-relaxed select-text">
                        {selected.stdout ? selected.stdout : "(Execution returned with empty stdout)"}
                      </pre>
                    </div>
                  </div>
                )}

                {activeTab === "task" && (
                  <div className="rounded-xl border border-slate-800 bg-[#050810] p-5 space-y-4">
                    <div className="space-y-1">
                      <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold">
                        Coder Task Description
                      </h3>
                      <p className="text-xs font-mono text-slate-200 whitespace-pre-wrap leading-relaxed p-3 rounded-lg bg-slate-900/60 border border-slate-800">
                        {selected.task_description}
                      </p>
                    </div>

                    <div className="grid grid-cols-2 gap-3 text-xs font-mono text-slate-400 pt-2">
                      <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800">
                        <div className="text-[10px] text-slate-500 uppercase">Target Stage</div>
                        <div className="text-slate-200 font-semibold mt-0.5">{selected.stage}</div>
                      </div>
                      <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800">
                        <div className="text-[10px] text-slate-500 uppercase">Script Filename</div>
                        <div className="text-slate-200 font-semibold mt-0.5">{selected.script_name}</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-3">
              <Terminal className="w-10 h-10 text-slate-700" />
              <div className="text-sm font-semibold text-slate-300">No Execution Selected</div>
              <p className="text-xs text-slate-500 font-mono max-w-sm">
                Select an execution run from the left panel to review its Python code and execution result.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

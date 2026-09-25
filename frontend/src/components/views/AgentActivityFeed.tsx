import { useState, useRef, useEffect } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Terminal,
  Activity,
  AlertCircle,
  Cpu,
  RotateCcw,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { cn as clsx } from "../../utils/cn";
import { PipelineEvent, WorkflowRun } from "../../types";
import { Badge, StatusBadge } from "../common/Badge";

interface AgentActivityFeedProps {
  events: PipelineEvent[];
  activeRun?: WorkflowRun;
  isConnected: boolean;
  isCompleted: boolean;
  error?: string | null;
  onSelectStage?: (stage: string) => void;
}

export function AgentActivityFeed({
  events,
  activeRun,
  isConnected,
  isCompleted,
  error,
  onSelectStage,
}: AgentActivityFeedProps) {
  const [expandedEvents, setExpandedEvents] = useState<Record<string, boolean>>({});
  const feedEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll on new events if connected
  useEffect(() => {
    if (isConnected && feedEndRef.current) {
      feedEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [events.length, isConnected]);

  const toggleExpand = (id: string) => {
    setExpandedEvents((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const stages = [
    { key: "profile", label: "Profile" },
    { key: "eda", label: "EDA" },
    { key: "feature_engineering", label: "Features" },
    { key: "model", label: "Models" },
    { key: "evaluator", label: "Evaluation" },
    { key: "report", label: "Report" },
  ];

  const currentStage = activeRun?.current_stage || (events.length > 0 ? events[events.length - 1].stage : "init");

  const getEventBadge = (event_type: string) => {
    switch (event_type) {
      case "WORKFLOW_STARTED":
      case "WORKFLOW_COMPLETED":
        return <Badge variant="success">{event_type}</Badge>;
      case "SUPERVISOR_DECISION":
        return <Badge variant="purple">SUPERVISOR</Badge>;
      case "AGENT_COMPLETED":
      case "EXPERIMENT_COMPLETED":
        return <Badge variant="info">{event_type}</Badge>;
      case "EVALUATION_FAILED":
        return <Badge variant="warning">IMPROVE LOOP</Badge>;
      default:
        return <Badge variant="neutral">{event_type}</Badge>;
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden bg-[#0a0f1d]">
      {/* Top Banner: Pipeline Stage Stepper */}
      <div className="p-4 border-b border-slate-800/80 bg-slate-900/40 select-none">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-sky-400" />
            <span className="text-xs font-semibold text-slate-200 uppercase font-mono tracking-wider">
              Autonomous Pipeline Execution
            </span>
          </div>

          <div className="flex items-center gap-2">
            {activeRun && (
              <span className="text-xs font-mono text-slate-400">
                Iteration: <span className="text-sky-400 font-bold">{activeRun.iteration || 1}</span>
              </span>
            )}
            {activeRun && <StatusBadge status={activeRun.status} />}
            {isConnected && (
              <span className="flex items-center gap-1.5 text-[11px] font-mono text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                LIVE SSE
              </span>
            )}
          </div>
        </div>

        {/* Stage Progress Stepper */}
        <div className="grid grid-cols-6 gap-2">
          {stages.map((st, idx) => {
            const isCurrent = currentStage.toLowerCase().includes(st.key.toLowerCase());
            const isPast = events.some(
              (e) => e.stage.toLowerCase().includes(st.key.toLowerCase()) && e.event_type === "AGENT_COMPLETED"
            );

            return (
              <div
                key={st.key}
                onClick={() => onSelectStage && onSelectStage(st.key)}
                className={clsx(
                  "px-2.5 py-2 rounded-lg border text-center transition cursor-pointer font-mono text-xs flex flex-col items-center justify-center gap-1",
                  isCurrent
                    ? "border-sky-500 bg-sky-500/10 text-sky-300 font-bold shadow-sm shadow-sky-500/20"
                    : isPast
                    ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-400"
                    : "border-slate-800 bg-slate-900/30 text-slate-500"
                )}
              >
                <div className="flex items-center gap-1">
                  <span className="text-[10px] opacity-60">0{idx + 1}</span>
                  <span className="truncate">{st.label}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Center Event Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {error && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/40 rounded-lg flex items-center gap-2.5 text-xs font-mono text-rose-300">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <div className="flex-1">
              <span className="font-semibold text-rose-200">Execution Alert:</span> {error}
            </div>
          </div>
        )}

        {activeRun?.status === "FAILED" && !error && (
          <div className="p-3 bg-rose-500/10 border border-rose-500/40 rounded-lg flex items-center gap-2.5 text-xs font-mono text-rose-300">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <div className="flex-1">
              <span className="font-semibold text-rose-200">Run Failed:</span>{" "}
              {activeRun.error || "The autonomous workflow failed."}
            </div>
          </div>
        )}

        {events.length === 0 && (
          <div className="h-48 flex flex-col items-center justify-center text-slate-500 font-mono text-xs gap-2">
            <Terminal className="w-6 h-6 text-slate-600 animate-pulse" />
            <span>Waiting for pipeline execution events...</span>
          </div>
        )}

        {events.map((ev) => {
          const isExpanded = expandedEvents[ev.id];
          const hasData = ev.data && Object.keys(ev.data).length > 0;
          const isSupervisor = ev.event_type === "SUPERVISOR_DECISION";
          const isImproveLoop = ev.event_type === "EVALUATION_FAILED";

          return (
            <div
              key={ev.id}
              className={clsx(
                "rounded-lg border text-xs font-mono transition",
                isSupervisor
                  ? "bg-purple-950/20 border-purple-800/40"
                  : isImproveLoop
                  ? "bg-amber-950/20 border-amber-800/40"
                  : "bg-slate-900/60 border-slate-800 hover:border-slate-700"
              )}
            >
              {/* Event Header */}
              <div
                onClick={() => hasData && toggleExpand(ev.id)}
                className={clsx(
                  "p-3 flex items-start justify-between gap-3",
                  hasData && "cursor-pointer select-none"
                )}
              >
                <div className="flex items-start gap-2.5 min-w-0">
                  <div className="mt-0.5 flex-shrink-0">
                    {isSupervisor ? (
                      <Cpu className="w-4 h-4 text-purple-400" />
                    ) : isImproveLoop ? (
                      <RotateCcw className="w-4 h-4 text-amber-400" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4 text-sky-400" />
                    )}
                  </div>

                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="uppercase text-[10px] font-bold tracking-wider px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                        {ev.stage}
                      </span>
                      {getEventBadge(ev.event_type)}
                      <span className="text-[10px] text-slate-500 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(ev.timestamp).toLocaleTimeString()}
                      </span>
                    </div>

                    <div className="text-slate-200 font-sans text-xs leading-relaxed">
                      {ev.message}
                    </div>
                  </div>
                </div>

                {hasData && (
                  <button className="text-slate-500 hover:text-slate-300 transition flex-shrink-0 mt-1">
                    {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                )}
              </div>

              {/* Event Structured Data Details */}
              {isExpanded && hasData && (
                <div className="px-3 pb-3 pt-1 border-t border-slate-800/60 bg-black/30 rounded-b-lg">
                  <div className="text-[10px] text-slate-400 uppercase font-semibold mb-1">
                    Structured Payload
                  </div>
                  <pre className="p-2.5 rounded bg-[#090d16] border border-slate-800 text-sky-300 text-[11px] overflow-x-auto">
                    {JSON.stringify(ev.data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}

        <div ref={feedEndRef} />
      </div>
    </div>
  );
}

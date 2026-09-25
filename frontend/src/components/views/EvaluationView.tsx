import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, AlertTriangle, ArrowRight, ShieldCheck } from "lucide-react";
import { api } from "../../services/api";
import { Badge } from "../common/Badge";
import { cn } from "../../utils/cn";

interface EvaluationViewProps {
  projectId: string;
}

export function EvaluationView({ projectId }: EvaluationViewProps) {
  const {
    data: evaluation,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["evaluation", projectId],
    queryFn: () => api.getEvaluation(projectId),
    enabled: Boolean(projectId),
  });

  if (isLoading) {
    return (
      <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
        Loading evaluation verdicts...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 border border-rose-500/30 rounded-xl bg-rose-500/5 text-center space-y-2 m-6">
        <AlertTriangle className="w-8 h-8 text-rose-400 mx-auto" />
        <div className="text-xs text-rose-300 font-medium font-sans">Failed to load evaluation</div>
        <div className="text-[11px] text-rose-400/80 font-mono">{(error as any)?.message}</div>
      </div>
    );
  }

  const evalJson = evaluation?.json || {};
  const issues = evalJson.issues || [];

  if (!evaluation || !evaluation.json || (!evalJson.verdict && issues.length === 0)) {
    return (
      <div className="p-12 text-center space-y-2">
        <CheckCircle2 className="w-8 h-8 text-slate-600 mx-auto" />
        <div className="text-xs text-slate-400 font-medium font-sans">No evaluation records yet</div>
        <div className="text-[11px] text-slate-500 font-mono">
          Run the pipeline to trigger model validation against quality gates.
        </div>
      </div>
    );
  }

  const verdict = evalJson.verdict || "PASS";
  const recommendations = evalJson.recommendations || [];
  const decision =
    evalJson.decision ||
    (verdict === "IMPROVE"
      ? "Route back to feature_engineering/model"
      : "Accept best model");

  const getSeverityBadge = (sev: string) => {
    switch (sev?.toUpperCase()) {
      case "CRITICAL":
      case "HIGH":
        return <Badge variant="error">{sev}</Badge>;
      case "MEDIUM":
        return <Badge variant="warning">{sev}</Badge>;
      case "LOW":
      default:
        return <Badge variant="neutral">{sev || "INFO"}</Badge>;
    }
  };

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-sky-400" />
          <h2 className="text-base font-bold text-slate-100">Evaluator &amp; Quality Gates</h2>
        </div>
        <p className="text-xs text-slate-400 mt-1">
          Strict metric threshold checks, overfitting/underfitting detection, and loop routing verdicts.
        </p>
      </div>

      {/* Verdict Card */}
      <div
        className={cn(
          "p-5 rounded-xl border flex flex-col md:flex-row md:items-center justify-between gap-4 font-mono",
          verdict === "PASS"
            ? "bg-emerald-950/20 border-emerald-800/40"
            : "bg-amber-950/20 border-amber-800/40"
        )}
      >
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "w-10 h-10 rounded-lg flex items-center justify-center font-bold text-base font-sans",
              verdict === "PASS"
                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
            )}
          >
            {verdict}
          </div>
          <div>
            <div className="text-slate-100 font-bold font-sans text-sm">
              Evaluator Verdict: {verdict}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">{decision}</div>
          </div>
        </div>

        {evalJson.suggested_next_stage && (
          <div className="flex items-center gap-2 text-xs bg-slate-900/80 px-3 py-2 rounded-lg border border-slate-700">
            <span className="text-slate-400">Next Action:</span>
            <span className="text-sky-400 font-bold uppercase">{evalJson.suggested_next_stage}</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
          </div>
        )}
      </div>

      {/* Identified Issues */}
      <div>
        <h3 className="text-xs font-semibold text-slate-300 font-sans mb-3 flex items-center gap-2">
          <span>Quality Gate Checks ({issues.length} Issues Flagged)</span>
        </h3>

        {issues.length === 0 ? (
          <div className="p-4 bg-emerald-950/10 border border-emerald-900/40 rounded-xl text-emerald-300 text-xs font-mono flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>All quality checks passed without warning.</span>
          </div>
        ) : (
          <div className="space-y-3 font-mono text-xs">
            {issues.map((issue: any, idx: number) => (
              <div
                key={idx}
                className="p-4 border border-slate-800 rounded-xl bg-slate-900/40 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-200 font-sans">{issue.check_name}</span>
                  {getSeverityBadge(issue.severity)}
                </div>
                <p className="text-slate-300 text-[11px] leading-relaxed">{issue.details}</p>
                {issue.evidence && (
                  <div className="p-2 bg-slate-950/60 rounded text-[10px] text-slate-400">
                    <span className="text-slate-500 uppercase font-semibold">Evidence:</span>{" "}
                    {issue.evidence}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-300 font-sans mb-3">
            Improvement Recommendations
          </h3>
          <ul className="space-y-2 font-mono text-xs">
            {recommendations.map((rec: string, idx: number) => (
              <li
                key={idx}
                className="p-3 bg-slate-900/40 border border-slate-800 rounded-lg flex items-start gap-2.5 text-slate-300"
              >
                <span className="text-sky-400 font-bold shrink-0">{idx + 1}.</span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

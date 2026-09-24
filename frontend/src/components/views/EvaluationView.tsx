import { useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, XCircle, ArrowRight, ShieldCheck, HelpCircle } from "lucide-react";
import clsx from "clsx";
import { EvaluationResponse } from "../../types";
import { api } from "../../services/api";
import { Badge } from "../common/Badge";

interface EvaluationViewProps {
  projectId: string;
}

export function EvaluationView({ projectId }: EvaluationViewProps) {
  const [evaluation, setEvaluation] = useState<EvaluationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setIsLoading(true);
    api
      .getEvaluation(projectId)
      .then((data) => setEvaluation(data))
      .catch((err) => {
        setError(err.message);
        setEvaluation(null);
      })
      .finally(() => setIsLoading(false));
  }, [projectId]);

  if (isLoading) {
    return (
      <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
        Loading evaluation verdicts...
      </div>
    );
  }

  if (!evaluation || !evaluation.json) {
    return (
      <div className="p-12 text-center space-y-2">
        <CheckCircle2 className="w-8 h-8 text-slate-600 mx-auto" />
        <div className="text-xs text-slate-400 font-medium">No evaluation records yet</div>
        <div className="text-[11px] text-slate-500 font-mono">
          Run the pipeline to trigger model validation against quality gates.
        </div>
      </div>
    );
  }

  const evalJson = evaluation.json;
  const verdict = evalJson.verdict || "PASS";
  const issues = evalJson.issues || [];
  const recommendations = evalJson.recommendations || [];
  const decision = evalJson.decision || (verdict === "IMPROVE" ? "Route back to feature_engineering/model" : "Accept best model");

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
          <h2 className="text-base font-bold text-slate-100">Evaluator & Quality Gates</h2>
        </div>
        <p className="text-xs text-slate-400 mt-1">
          Strict metric threshold checks, overfitting/underfitting detection, and loop routing verdicts.
        </p>
      </div>

      {/* Verdict Card */}
      <div
        className={clsx(
          "p-5 rounded-xl border flex flex-col md:flex-row md:items-center justify-between gap-4 font-mono",
          verdict === "PASS"
            ? "bg-emerald-950/20 border-emerald-800/40"
            : "bg-amber-950/20 border-amber-800/40"
        )}
      >
        <div className="flex items-center gap-3">
          {verdict === "PASS" ? (
            <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0" />
          ) : (
            <AlertTriangle className="w-8 h-8 text-amber-400 flex-shrink-0" />
          )}

          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-slate-100 uppercase tracking-wider">
                Verdict: {verdict}
              </span>
              <span
                className={clsx(
                  "px-2 py-0.5 rounded text-[11px] font-bold font-sans",
                  verdict === "PASS"
                    ? "bg-emerald-500/20 text-emerald-300"
                    : "bg-amber-500/20 text-amber-300"
                )}
              >
                {verdict === "PASS" ? "QUALITY GATES PASSED" : "REFINEMENT REQUIRED"}
              </span>
            </div>
            <div className="text-xs text-slate-300 font-sans mt-1">
              Best candidate: <span className="font-mono text-sky-400 font-bold">{evalJson.best_candidate || "Candidate Model"}</span>
            </div>
          </div>
        </div>

        {/* Supervisor Routing */}
        <div className="p-3 bg-black/40 border border-slate-800 rounded-lg text-xs space-y-1">
          <div className="text-[10px] text-slate-500 uppercase font-semibold">
            Supervisor Routing Decision
          </div>
          <div className="flex items-center gap-1.5 text-purple-300 font-semibold">
            <ArrowRight className="w-3.5 h-3.5" />
            <span>{decision}</span>
          </div>
        </div>
      </div>

      {/* Issues Table */}
      <div>
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono mb-2">
          Detected Quality Issues ({issues.length})
        </h3>
        <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/40">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-800/60 font-mono text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">Issue Type</th>
                <th className="p-3 w-28">Severity</th>
                <th className="p-3">Evidence / Metric Discrepancy</th>
                <th className="p-3">Implication</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 font-mono">
              {issues.map((iss, idx) => (
                <tr key={idx} className="hover:bg-slate-800/30">
                  <td className="p-3 font-semibold text-slate-200">{iss.type}</td>
                  <td className="p-3">{getSeverityBadge(iss.severity)}</td>
                  <td className="p-3 text-slate-300 font-sans">{iss.evidence}</td>
                  <td className="p-3 text-slate-400 font-sans">{iss.implication || "—"}</td>
                </tr>
              ))}
              {issues.length === 0 && (
                <tr>
                  <td colSpan={4} className="p-6 text-center text-slate-500 font-sans">
                    No critical degradation or overfitting issues detected.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider font-mono">
            Evaluator Improvement Suggestions
          </h3>
          <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl space-y-2 text-xs">
            {recommendations.map((rec, idx) => (
              <div key={idx} className="flex items-start gap-2 text-slate-300">
                <span className="text-sky-400 font-bold font-mono">0{idx + 1}.</span>
                <span>{rec}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

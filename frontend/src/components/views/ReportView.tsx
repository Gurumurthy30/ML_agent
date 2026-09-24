import { useEffect, useState } from "react";
import { FileText, Award, Layers, CheckCircle, AlertOctagon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ReportResponse } from "../../types";
import { api } from "../../services/api";

interface ReportViewProps {
  projectId: string;
}

export function ReportView({ projectId }: ReportViewProps) {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    api
      .getReport(projectId)
      .then((data) => setReport(data))
      .catch(() => setReport(null))
      .finally(() => setIsLoading(false));
  }, [projectId]);

  if (isLoading) {
    return (
      <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
        Compiling final executive report...
      </div>
    );
  }

  if (!report || (!report.markdown && Object.keys(report.summary || {}).length === 0)) {
    return (
      <div className="p-12 text-center space-y-2">
        <FileText className="w-8 h-8 text-slate-600 mx-auto" />
        <div className="text-xs text-slate-400 font-medium">No final report generated yet</div>
        <div className="text-[11px] text-slate-500 font-mono">
          The Reporter agent produces the comprehensive final report once the workflow finishes.
        </div>
      </div>
    );
  }

  const summary = report.summary || {};

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-sky-400" />
          <h2 className="text-base font-bold text-slate-100">Final Engineering Report</h2>
        </div>
        <p className="text-xs text-slate-400 mt-1">
          Complete end-to-end synthesis of problem framing, dataset profiling, feature transformations, candidate evaluations, and deployment guidance.
        </p>
      </div>

      {/* Summary Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs">
        <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
          <div className="text-[10px] text-slate-500 uppercase">Selected Model</div>
          <div className="text-sky-400 font-bold text-sm truncate mt-0.5">
            {summary.model_name || "Best Candidate"}
          </div>
        </div>
        <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
          <div className="text-[10px] text-slate-500 uppercase">Best Score ({summary.target_metric || "Metric"})</div>
          <div className="text-emerald-400 font-bold text-sm mt-0.5">
            {typeof summary.best_score === "number" ? summary.best_score.toFixed(4) : "—"}
          </div>
        </div>
        <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
          <div className="text-[10px] text-slate-500 uppercase">Feature Version</div>
          <div className="text-purple-400 font-semibold mt-0.5">
            {summary.feature_version || "feat_v1"}
          </div>
        </div>
        <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
          <div className="text-[10px] text-slate-500 uppercase">Total Iterations</div>
          <div className="text-slate-200 font-semibold mt-0.5">
            {summary.iterations_run || 1}
          </div>
        </div>
      </div>

      {/* Categorized Report Badges */}
      <div className="flex items-center gap-2 text-[11px] font-mono select-none">
        <span className="px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">
          ✓ Verified Facts
        </span>
        <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          ★ Model Results
        </span>
        <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20">
          ⚡ Agent Directives
        </span>
        <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
          ⚠ Known Limitations
        </span>
      </div>

      {/* Markdown Document */}
      <div className="p-6 rounded-xl border border-slate-800 bg-[#090d16] text-slate-200 shadow-sm">
        <article className="prose prose-invert prose-sm max-w-none prose-headings:font-semibold prose-headings:text-slate-100 prose-p:text-slate-300 prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-800 prose-table:border prose-table:border-slate-800 prose-th:bg-slate-800/60 prose-th:p-2 prose-td:p-2">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.markdown}</ReactMarkdown>
        </article>
      </div>
    </div>
  );
}

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, AlertCircle, Lightbulb, Filter } from "lucide-react";
import { ArtifactIndex } from "../../types";
import { api } from "../../services/api";
import { cn } from "../../utils/cn";

interface EDAViewProps {
  projectId: string;
  artifacts: ArtifactIndex[];
}

export function EDAView({ projectId, artifacts }: EDAViewProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");

  const edaArt = artifacts.find(
    (a) =>
      a.stage === "eda" &&
      ((a.file_path || a.path || "").endsWith("findings.json") ||
        (a.file_path || a.path || "").endsWith(".json"))
  );

  const { data: artContent, isLoading } = useQuery({
    queryKey: ["artifact-content", projectId, edaArt?.id],
    queryFn: () => api.getArtifactContent(projectId, edaArt!.id),
    enabled: Boolean(projectId && edaArt?.id),
  });

  const findings: any[] =
    artContent?.type === "json" && artContent.data
      ? Array.isArray(artContent.data)
        ? artContent.data
        : artContent.data.findings || []
      : [];

  const categories = ["ALL", ...Array.from(new Set(findings.map((f) => f.category || "General")))];
  const filtered =
    selectedCategory === "ALL"
      ? findings
      : findings.filter((f) => (f.category || "General") === selectedCategory);

  if (isLoading) {
    return (
      <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
        Loading EDA findings...
      </div>
    );
  }

  if (findings.length === 0) {
    return (
      <div className="p-12 text-center space-y-2">
        <Search className="w-8 h-8 text-slate-600 mx-auto" />
        <div className="text-xs text-slate-400 font-medium">No EDA findings recorded yet</div>
        <div className="text-[11px] text-slate-500 font-mono">
          Run the autonomous pipeline to generate exploratory data analysis.
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      {/* Header & Filter */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Search className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-slate-100">Exploratory Data Analysis</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Task-driven data analysis without static plots — findings structured as verifiable hypotheses.
          </p>
        </div>

        {/* Category Filter */}
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-slate-500" />
          <div className="flex items-center gap-1 overflow-x-auto">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-xs font-mono transition",
                  selectedCategory === cat
                    ? "bg-sky-500 text-slate-950 font-bold"
                    : "bg-slate-900 border border-slate-700 text-slate-400 hover:text-slate-200"
                )}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Findings List */}
      <div className="grid grid-cols-1 gap-4">
        {filtered.map((item, idx) => (
          <div
            key={idx}
            className="p-5 border border-slate-800 rounded-xl bg-slate-900/40 space-y-3 font-mono text-xs"
          >
            <div className="flex items-center justify-between">
              <span className="px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-[10px] text-sky-300 uppercase">
                {item.category || "General"}
              </span>
              <span className="text-[10px] text-slate-500">Finding #{idx + 1}</span>
            </div>

            <div>
              <div className="text-slate-100 font-semibold text-sm font-sans">{item.finding}</div>
              {item.evidence && (
                <div className="mt-2 p-2.5 bg-slate-950/40 border border-slate-800/80 rounded-lg text-slate-300 text-[11px] leading-relaxed">
                  <span className="text-slate-500 font-semibold uppercase text-[10px] block mb-1">
                    Statistical Evidence:
                  </span>
                  {item.evidence}
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1 text-[11px]">
              {item.implication && (
                <div className="p-2.5 bg-amber-500/5 border border-amber-500/20 rounded-lg flex items-start gap-2 text-amber-200">
                  <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-amber-400 block text-[10px] uppercase">
                      Implication:
                    </span>
                    {item.implication}
                  </div>
                </div>
              )}

              {item.recommendation && (
                <div className="p-2.5 bg-emerald-500/5 border border-emerald-500/20 rounded-lg flex items-start gap-2 text-emerald-200">
                  <Lightbulb className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-emerald-400 block text-[10px] uppercase">
                      Recommendation:
                    </span>
                    {item.recommendation}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

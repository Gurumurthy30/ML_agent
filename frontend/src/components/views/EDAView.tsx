import { useEffect, useState } from "react";
import { Search, AlertCircle, Lightbulb, CheckCircle2, Filter } from "lucide-react";
import clsx from "clsx";
import { ArtifactIndex } from "../../types";
import { api } from "../../services/api";

interface EDAViewProps {
  projectId: string;
  artifacts: ArtifactIndex[];
}

export function EDAView({ projectId, artifacts }: EDAViewProps) {
  const [findings, setFindings] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");

  useEffect(() => {
    const edaArt = artifacts.find(
      (a) => a.stage === "eda" && a.file_path.endsWith("findings.json")
    );
    if (!edaArt) return;

    setIsLoading(true);
    api
      .getArtifactContent(projectId, edaArt.id)
      .then((data) => {
        if (data.type === "json" && data.data) {
          const list = Array.isArray(data.data) ? data.data : data.data.findings || [];
          setFindings(list);
        }
      })
      .catch(() => setFindings([]))
      .finally(() => setIsLoading(false));
  }, [projectId, artifacts]);

  const categories = ["ALL", ...Array.from(new Set(findings.map((f) => f.category || "General")))];

  const filtered = selectedCategory === "ALL" ? findings : findings.filter((f) => (f.category || "General") === selectedCategory);

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
            Hypothesis-driven exploratory analysis and findings translated into modeling suggestions.
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
                className={clsx(
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
            className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-3 hover:border-slate-700 transition"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2 font-mono">
                <span className="text-amber-400 font-bold text-xs">#{idx + 1}</span>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-sky-300 text-[11px] font-medium uppercase">
                  {item.category || "General"}
                </span>
              </div>
            </div>

            <div className="text-sm font-semibold text-slate-100">{item.finding}</div>

            {/* Evidence & Implication */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
              {item.evidence && (
                <div className="p-3 bg-black/30 border border-slate-800/80 rounded-lg">
                  <div className="text-[10px] text-slate-500 uppercase font-semibold mb-1">
                    Statistical Evidence
                  </div>
                  <div className="text-slate-300 font-sans">{item.evidence}</div>
                </div>
              )}

              {item.implication && (
                <div className="p-3 bg-black/30 border border-slate-800/80 rounded-lg">
                  <div className="text-[10px] text-slate-500 uppercase font-semibold mb-1">
                    Modeling Implication
                  </div>
                  <div className="text-slate-300 font-sans">{item.implication}</div>
                </div>
              )}
            </div>

            {/* Recommendation */}
            {item.recommendation && (
              <div className="p-3 bg-emerald-950/20 border border-emerald-800/30 rounded-lg flex items-start gap-2 text-xs">
                <Lightbulb className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold text-emerald-400 uppercase text-[10px] font-mono mr-1.5">
                    Recommendation:
                  </span>
                  <span className="text-slate-200">{item.recommendation}</span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

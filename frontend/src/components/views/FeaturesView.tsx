import { useEffect, useState } from "react";
import { SlidersHorizontal, Code2, Layers, CheckCircle2 } from "lucide-react";
import { ArtifactIndex } from "../../types";
import { api } from "../../services/api";

interface FeaturesViewProps {
  projectId: string;
  artifacts: ArtifactIndex[];
}

export function FeaturesView({ projectId, artifacts }: FeaturesViewProps) {
  const [featureSummary, setFeatureSummary] = useState<any>(null);
  const [pipelineCode, setPipelineCode] = useState<string>("");
  const [activeSubTab, setActiveSubTab] = useState<"features" | "code">("features");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const summaryArt = artifacts.find(
      (a) => a.stage === "features" && a.file_path.endsWith("summary.json")
    );
    const codeArt = artifacts.find(
      (a) => a.stage === "features" && (a.file_path.endsWith(".py") || a.file_path.endsWith("pipeline.py"))
    );

    if (summaryArt) {
      setIsLoading(true);
      api
        .getArtifactContent(projectId, summaryArt.id)
        .then((data) => {
          if (data.type === "json" && data.data) {
            setFeatureSummary(data.data);
          }
        })
        .finally(() => setIsLoading(false));
    }

    if (codeArt) {
      api.getArtifactContent(projectId, codeArt.id).then((data) => {
        if (data.content) setPipelineCode(data.content);
      });
    }
  }, [projectId, artifacts]);

  if (isLoading) {
    return (
      <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
        Loading feature engineering records...
      </div>
    );
  }

  if (!featureSummary && !pipelineCode) {
    return (
      <div className="p-12 text-center space-y-2">
        <SlidersHorizontal className="w-8 h-8 text-slate-600 mx-auto" />
        <div className="text-xs text-slate-400 font-medium">No feature engineering artifacts found</div>
        <div className="text-[11px] text-slate-500 font-mono">
          Run the pipeline to engineer domain features and build scikit-learn transformers.
        </div>
      </div>
    );
  }

  const createdFeatures = featureSummary?.created_features || featureSummary?.features || [];

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-slate-100">Feature Engineering</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Engineered feature sets, scikit-learn preprocessing pipelines, and schemas.
          </p>
        </div>

        {/* Toggle between feature list & code */}
        <div className="flex items-center gap-1 p-1 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono">
          <button
            onClick={() => setActiveSubTab("features")}
            className={`px-3 py-1 rounded-md transition ${
              activeSubTab === "features" ? "bg-sky-500 text-slate-950 font-bold" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Features List ({createdFeatures.length})
          </button>
          {pipelineCode && (
            <button
              onClick={() => setActiveSubTab("code")}
              className={`px-3 py-1 rounded-md transition ${
                activeSubTab === "code" ? "bg-sky-500 text-slate-950 font-bold" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Pipeline Code (.py)
            </button>
          )}
        </div>
      </div>

      {activeSubTab === "features" ? (
        <div className="space-y-4 font-mono text-xs">
          {/* Metadata Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
              <div className="text-[10px] text-slate-500 uppercase">Feature Version</div>
              <div className="text-sky-400 font-bold text-sm mt-0.5">
                {featureSummary?.version || "feat_v1"}
              </div>
            </div>
            <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
              <div className="text-[10px] text-slate-500 uppercase">Created Features</div>
              <div className="text-emerald-400 font-bold text-sm mt-0.5">
                {createdFeatures.length}
              </div>
            </div>
            <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
              <div className="text-[10px] text-slate-500 uppercase">Input Dataset</div>
              <div className="text-slate-200 font-semibold mt-0.5">
                {featureSummary?.dataset_version || "dataset_v1"}
              </div>
            </div>
            <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
              <div className="text-[10px] text-slate-500 uppercase">Transformations</div>
              <div className="text-purple-400 font-semibold mt-0.5">
                {featureSummary?.transformations?.length || "Standard/OHE"}
              </div>
            </div>
          </div>

          {/* Features Table */}
          <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/40">
            <table className="w-full text-left border-collapse">
              <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">#</th>
                  <th className="p-3">Feature Name</th>
                  <th className="p-3">Transformation / Formula</th>
                  <th className="p-3">Source Columns</th>
                  <th className="p-3">Rationale</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {createdFeatures.map((f: any, idx: number) => {
                  const name = typeof f === "string" ? f : f.name || f.feature_name || `feat_${idx + 1}`;
                  const formula = typeof f === "object" ? f.formula || f.type || "Engineered" : "Feature";
                  const sources = typeof f === "object" ? f.source_columns || f.sources || ["raw"] : ["data"];
                  const rationale = typeof f === "object" ? f.rationale || f.description || "Generated from EDA" : "EDA recommendation";

                  return (
                    <tr key={idx} className="hover:bg-slate-800/30">
                      <td className="p-3 text-slate-500 font-bold">{idx + 1}</td>
                      <td className="p-3 font-semibold text-slate-100">{name}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-sky-300 text-[11px]">
                          {formula}
                        </span>
                      </td>
                      <td className="p-3 text-slate-300">
                        {Array.isArray(sources) ? sources.join(", ") : String(sources)}
                      </td>
                      <td className="p-3 text-slate-400 font-sans">{rationale}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="border border-slate-800 rounded-xl overflow-hidden">
          <div className="px-4 py-2 bg-slate-800/80 border-b border-slate-800 flex items-center gap-2 font-mono text-xs text-slate-300">
            <Code2 className="w-4 h-4 text-sky-400" />
            <span>pipeline.py (Scikit-Learn ColumnTransformer / Pipeline)</span>
          </div>
          <pre className="p-4 bg-[#090d16] font-mono text-xs text-sky-300 overflow-x-auto leading-relaxed">
            {pipelineCode}
          </pre>
        </div>
      )}
    </div>
  );
}

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SlidersHorizontal, Code2, Layers } from "lucide-react";
import { ArtifactIndex } from "../../types";
import { api } from "../../services/api";

interface FeaturesViewProps {
  projectId: string;
  artifacts: ArtifactIndex[];
}

export function FeaturesView({ projectId, artifacts }: FeaturesViewProps) {
  const [activeSubTab, setActiveSubTab] = useState<"features" | "code">("features");

  const summaryArt = artifacts.find(
    (a) =>
      a.stage === "features" &&
      ((a.file_path || a.path || "").endsWith("feature_schema.json") ||
        (a.file_path || a.path || "").endsWith("schema.json") ||
        (a.file_path || a.path || "").endsWith("summary.json"))
  );

  const codeArt = artifacts.find(
    (a) =>
      a.stage === "features" &&
      ((a.file_path || a.path || "").endsWith(".py") ||
        (a.file_path || a.path || "").endsWith("pipeline.py"))
  );

  const { data: schemaContent, isLoading: isSchemaLoading } = useQuery({
    queryKey: ["artifact-content", projectId, summaryArt?.id],
    queryFn: () => api.getArtifactContent(projectId, summaryArt!.id),
    enabled: Boolean(projectId && summaryArt?.id),
  });

  const { data: codeContent, isLoading: isCodeLoading } = useQuery({
    queryKey: ["artifact-content", projectId, codeArt?.id],
    queryFn: () => api.getArtifactContent(projectId, codeArt!.id),
    enabled: Boolean(projectId && codeArt?.id),
  });

  const isLoading = isSchemaLoading || isCodeLoading;
  const featureSchema = schemaContent?.type === "json" ? schemaContent.data : null;
  const pipelineCode = codeContent?.content || "";

  // Normalize created features list
  let featureItems: { name: string; type: string; transformation?: string; source?: string }[] = [];
  if (featureSchema) {
    if (Array.isArray(featureSchema.created_features)) {
      featureItems = featureSchema.created_features.map((f: any) => ({
        name: f.feature_name || f.name,
        type: f.dtype || f.transformation || "float64",
        transformation: f.transformation,
        source: Array.isArray(f.source_columns) ? f.source_columns.join(", ") : f.source_columns,
      }));
    } else if (typeof featureSchema === "object") {
      featureItems = Object.entries(featureSchema).map(([name, dtype]) => ({
        name,
        type: String(dtype),
      }));
    }
  }

  if (isLoading) {
    return (
      <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
        Loading feature engineering records...
      </div>
    );
  }

  if (featureItems.length === 0 && !pipelineCode) {
    return (
      <div className="p-12 text-center space-y-2">
        <SlidersHorizontal className="w-8 h-8 text-slate-600 mx-auto" />
        <div className="text-xs text-slate-400 font-medium">No feature engineering artifacts found</div>
        <div className="text-[11px] text-slate-500 font-mono">
          Run the pipeline to engineer domain features and build reproducible scikit-learn transformers.
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto font-mono text-xs">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-slate-100 font-sans">Feature Engineering</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1 font-sans">
            Versioned feature pipelines, transformations, scalers, and column schemas.
          </p>
        </div>

        {/* Toggle between feature list & code */}
        <div className="flex items-center gap-1 p-1 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono">
          <button
            onClick={() => setActiveSubTab("features")}
            className={`px-3 py-1 rounded-md transition ${
              activeSubTab === "features"
                ? "bg-sky-500 text-slate-950 font-bold"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Features Schema ({featureItems.length})
          </button>
          {pipelineCode && (
            <button
              onClick={() => setActiveSubTab("code")}
              className={`px-3 py-1 rounded-md transition flex items-center gap-1.5 ${
                activeSubTab === "code"
                  ? "bg-sky-500 text-slate-950 font-bold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Code2 className="w-3.5 h-3.5" />
              <span>pipeline.py</span>
            </button>
          )}
        </div>
      </div>

      {activeSubTab === "features" ? (
        <div className="space-y-4">
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-sky-400" />
              <span className="font-semibold text-slate-200 font-sans">
                Transformed Features Dataset
              </span>
            </div>
            <span className="text-slate-400 text-[11px]">
              Total Features: <strong className="text-sky-300">{featureItems.length}</strong>
            </span>
          </div>

          <div className="border border-slate-800 rounded-xl overflow-x-auto bg-slate-900/40">
            <table className="w-full text-left text-xs border-collapse min-w-[650px]">
              <thead className="bg-slate-800/80 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3 w-12 text-center">#</th>
                  <th className="p-3">Feature Name</th>
                  <th className="p-3">Data Type</th>
                  {featureItems.some((f) => f.transformation) && (
                    <th className="p-3">Transformation</th>
                  )}
                  {featureItems.some((f) => f.source) && <th className="p-3">Source Column</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {featureItems.map((item, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/30">
                    <td className="p-3 text-center text-slate-500">{idx + 1}</td>
                    <td className="p-3 font-semibold text-slate-200">{item.name}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px]">
                        {item.type}
                      </span>
                    </td>
                    {featureItems.some((f) => f.transformation) && (
                      <td className="p-3 text-slate-300">{item.transformation || "—"}</td>
                    )}
                    {featureItems.some((f) => f.source) && (
                      <td className="p-3 text-slate-400 text-[11px]">{item.source || "—"}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* Python Pipeline Code View */
        <div className="space-y-3">
          <div className="flex items-center justify-between text-slate-400 text-[11px]">
            <span>Reproducible Scikit-Learn Feature Pipeline</span>
            <span>features/feature_pipeline.py</span>
          </div>
          <div className="border border-slate-800 rounded-xl bg-slate-950 p-4 overflow-x-auto text-[11px] leading-relaxed text-slate-200 font-mono">
            <pre>{pipelineCode}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Info, AlertCircle, FileCheck, Layers } from "lucide-react";
import { ArtifactIndex } from "../../types";
import { api } from "../../services/api";

interface ProfileViewProps {
  projectId: string;
  artifacts: ArtifactIndex[];
}

export function ProfileView({ projectId, artifacts }: ProfileViewProps) {
  const [profileData, setProfileData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // Find profile artifact
    const profileArt = artifacts.find(
      (a) => a.stage === "profile" && a.file_path.endsWith("summary.json")
    );
    if (!profileArt) return;

    setIsLoading(true);
    api
      .getArtifactContent(projectId, profileArt.id)
      .then((data) => {
        if (data.type === "json" && data.data) {
          setProfileData(data.data);
        }
      })
      .catch(() => setProfileData(null))
      .finally(() => setIsLoading(false));
  }, [projectId, artifacts]);

  if (isLoading) {
    return (
      <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
        Loading data profiling results...
      </div>
    );
  }

  if (!profileData) {
    return (
      <div className="p-12 text-center space-y-2">
        <Info className="w-8 h-8 text-slate-600 mx-auto" />
        <div className="text-xs text-slate-400 font-medium">No profiling summary found</div>
        <div className="text-[11px] text-slate-500 font-mono">
          Run the pipeline to generate automated data profiling.
        </div>
      </div>
    );
  }

  const columns = profileData.columns || {};
  const targetInfo = profileData.target || {};
  const datasetInfo = profileData.dataset || {};

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto font-mono text-xs">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Info className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-slate-100 font-sans">Data Profile & Schema</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1 font-sans">
            Automated column data type discovery, missing values, and target validation.
          </p>
        </div>

        {targetInfo.task_type && (
          <span className="px-3 py-1 rounded-full bg-sky-500/10 border border-sky-500/30 text-sky-400 text-xs font-semibold uppercase">
            Task: {targetInfo.task_type}
          </span>
        )}
      </div>

      {/* Target Column Overview */}
      {targetInfo.name && (
        <div className="p-4 bg-sky-950/20 border border-sky-800/40 rounded-xl space-y-2">
          <div className="flex items-center gap-2 text-sky-300 font-semibold font-sans">
            <FileCheck className="w-4 h-4" />
            <span>Target Column: {targetInfo.name}</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs pt-1">
            <div>
              <span className="text-slate-500 text-[10px] uppercase">Data Type</span>
              <div className="text-slate-200 mt-0.5">{targetInfo.dtype || "N/A"}</div>
            </div>
            <div>
              <span className="text-slate-500 text-[10px] uppercase">Distinct Values</span>
              <div className="text-slate-200 mt-0.5">{targetInfo.distinct_count ?? "N/A"}</div>
            </div>
            <div>
              <span className="text-slate-500 text-[10px] uppercase">Missing Values</span>
              <div className="text-slate-200 mt-0.5">{targetInfo.null_count ?? 0}</div>
            </div>
            <div>
              <span className="text-slate-500 text-[10px] uppercase">Recommended Metric</span>
              <div className="text-amber-400 font-bold mt-0.5">{targetInfo.recommended_metric || "f1"}</div>
            </div>
          </div>
        </div>
      )}

      {/* Column Schema Table */}
      <div>
        <div className="flex items-center gap-2 mb-3 text-slate-300 font-sans font-semibold">
          <Layers className="w-4 h-4 text-purple-400" />
          <span>Feature Columns Breakdown ({Object.keys(columns).length})</span>
        </div>

        <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/40">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">Column Name</th>
                <th className="p-3">Data Type</th>
                <th className="p-3">Missing (Count / %)</th>
                <th className="p-3">Distinct Values</th>
                <th className="p-3">Stats / Sample</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {Object.entries(columns).map(([colName, col]: [string, any]) => {
                const nullPct = col.null_percentage !== undefined ? `${col.null_percentage.toFixed(1)}%` : "0%";
                const isHighNull = (col.null_percentage || 0) > 30;

                return (
                  <tr key={colName} className="hover:bg-slate-800/30">
                    <td className="p-3 font-semibold text-slate-200">{colName}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[11px]">
                        {col.dtype || col.type || "string"}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={isHighNull ? "text-amber-400 font-bold" : "text-slate-300"}>
                        {col.null_count || 0} ({nullPct})
                      </span>
                    </td>
                    <td className="p-3 text-slate-300">{col.distinct_count ?? "—"}</td>
                    <td className="p-3 text-slate-400 text-[11px] truncate max-w-xs">
                      {col.sample_values ? JSON.stringify(col.sample_values.slice(0, 3)) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Info, FileCheck, Layers } from "lucide-react";
import { ArtifactIndex } from "../../types";
import { api } from "../../services/api";

interface ProfileViewProps {
  projectId: string;
  artifacts: ArtifactIndex[];
}

export function ProfileView({ projectId, artifacts }: ProfileViewProps) {
  // Find profile artifact (.json)
  const profileArt = artifacts.find(
    (a) =>
      a.stage === "profile" &&
      ((a.file_path || a.path || "").endsWith("profile.json") ||
        (a.file_path || a.path || "").endsWith(".json"))
  );

  const { data: artContent, isLoading } = useQuery({
    queryKey: ["artifact-content", projectId, profileArt?.id],
    queryFn: () => api.getArtifactContent(projectId, profileArt!.id),
    enabled: Boolean(projectId && profileArt?.id),
  });

  if (isLoading) {
    return (
      <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
        Loading data profiling results...
      </div>
    );
  }

  const profileData = artContent?.type === "json" ? artContent.data : null;

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

  // Normalize column list (array or object)
  const rawCols = profileData.columns;
  const columnsList: any[] = Array.isArray(rawCols)
    ? rawCols
    : typeof rawCols === "object" && rawCols !== null
    ? Object.entries(rawCols).map(([name, val]: [string, any]) => ({ name, ...(val || {}) }))
    : [];

  const targetName = profileData.target_column || profileData.target?.name || "Target";
  const taskType = profileData.task_type_guess || profileData.target?.task_type;
  const targetDist = profileData.target_distribution || {};

  return (
    <div className="p-6 space-y-6 h-full overflow-y-auto font-mono text-xs">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Info className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-slate-100 font-sans">Data Profile &amp; Schema</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1 font-sans">
            Automated column data type discovery, missing values, and target validation.
          </p>
        </div>

        {taskType && (
          <span className="self-start sm:self-auto px-3 py-1 rounded-full bg-sky-500/10 border border-sky-500/30 text-sky-400 text-xs font-semibold uppercase font-sans">
            Task: {taskType}
          </span>
        )}
      </div>

      {/* Dataset Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
          <div className="text-slate-500 text-[10px] uppercase font-sans">Total Rows</div>
          <div className="text-slate-100 font-semibold text-sm mt-0.5">
            {profileData.row_count ?? "—"}
          </div>
        </div>
        <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
          <div className="text-slate-500 text-[10px] uppercase font-sans">Total Columns</div>
          <div className="text-slate-100 font-semibold text-sm mt-0.5">
            {profileData.column_count ?? columnsList.length}
          </div>
        </div>
        <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
          <div className="text-slate-500 text-[10px] uppercase font-sans">Duplicates</div>
          <div className="text-slate-100 font-semibold text-sm mt-0.5">
            {profileData.duplicates_count ?? 0}
          </div>
        </div>
        <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
          <div className="text-slate-500 text-[10px] uppercase font-sans">Missing Values %</div>
          <div className="text-amber-400 font-semibold text-sm mt-0.5">
            {profileData.missing_total_pct !== undefined ? `${profileData.missing_total_pct}%` : "0%"}
          </div>
        </div>
      </div>

      {/* Target Column Overview */}
      {targetName && (
        <div className="p-4 bg-sky-950/20 border border-sky-800/40 rounded-xl space-y-2">
          <div className="flex items-center gap-2 text-sky-300 font-semibold font-sans">
            <FileCheck className="w-4 h-4" />
            <span>Target Column: {targetName}</span>
          </div>
          <div className="text-xs pt-1">
            {Object.keys(targetDist).length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {Object.entries(targetDist).map(([k, v]) => (
                  <div key={k}>
                    <span className="text-slate-500 text-[10px] uppercase font-sans">{k}</span>
                    <div className="text-slate-200 font-semibold mt-0.5">{String(v)}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-slate-400 font-sans">No target distribution details available.</div>
            )}
          </div>
        </div>
      )}

      {/* Column Schema Table */}
      <div>
        <div className="flex items-center gap-2 mb-3 text-slate-300 font-sans font-semibold">
          <Layers className="w-4 h-4 text-purple-400" />
          <span>Feature Columns ({columnsList.length})</span>
        </div>

        <div className="border border-slate-800 rounded-xl overflow-x-auto bg-slate-900/40">
          <table className="w-full text-left text-xs border-collapse min-w-[700px]">
            <thead className="bg-slate-800/80 text-slate-400 border-b border-slate-800">
              <tr>
                <th className="p-3">Column Name</th>
                <th className="p-3">Data Type</th>
                <th className="p-3">Missing (Count / %)</th>
                <th className="p-3">Distinct Values</th>
                <th className="p-3">Sample Values</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80">
              {columnsList.map((col: any) => {
                const colName = col.name || col.column_name || "—";
                const nullCount = col.missing_count ?? col.null_count ?? 0;
                const nullPct =
                  col.missing_pct !== undefined
                    ? `${Number(col.missing_pct).toFixed(1)}%`
                    : col.null_percentage !== undefined
                    ? `${Number(col.null_percentage).toFixed(1)}%`
                    : "0%";
                const isHighNull = (col.missing_pct || col.null_percentage || 0) > 30;
                const distinctVal = col.unique_count ?? col.distinct_count ?? "—";

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
                        {nullCount} ({nullPct})
                      </span>
                    </td>
                    <td className="p-3 text-slate-300">{distinctVal}</td>
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

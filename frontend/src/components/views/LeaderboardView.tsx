import { useState, useMemo } from "react";
import { Trophy, ArrowUpDown, ChevronRight, Info, AlertTriangle } from "lucide-react";
import { LeaderboardResponse, LeaderboardItem } from "../../types";
import { useUIStore } from "../../store/uiStore";
import { cn } from "../../utils/cn";

interface LeaderboardViewProps {
  data?: LeaderboardResponse;
  isLoading: boolean;
  selectedMetric: string;
  onSelectMetric: (metric: string) => void;
}

export function LeaderboardView({
  data,
  isLoading,
  selectedMetric,
  onSelectMetric,
}: LeaderboardViewProps) {
  const { setViewingModel } = useUIStore();
  const [sortField, setSortField] = useState<string>("default");
  const [sortAsc, setSortAsc] = useState<boolean>(false);

  const direction = data?.direction || "max";
  const isHigherBetter = direction === "max";

  const availableMetrics = ["f1", "accuracy", "roc_auc", "precision", "recall", "rmse", "mae", "r2"];

  const items = useMemo(() => {
    if (!data?.leaderboard) return [];
    const list = [...data.leaderboard];

    if (sortField === "default") {
      // Backend returns pre-sorted per metric direction (higher-is-better vs lower-is-better)
      return list;
    }

    list.sort((a, b) => {
      let valA: any = a[sortField as keyof LeaderboardItem];
      let valB: any = b[sortField as keyof LeaderboardItem];

      if (sortField === "score") {
        valA = a.score !== undefined && a.score !== null ? a.score : a.metric_value;
        valB = b.score !== undefined && b.score !== null ? b.score : b.metric_value;
      }

      if (valA === undefined || valA === null) return 1;
      if (valB === undefined || valB === null) return -1;

      if (typeof valA === "number" && typeof valB === "number") {
        return sortAsc ? valA - valB : valB - valA;
      }
      return sortAsc ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
    });

    return list;
  }, [data, sortField, sortAsc]);

  const toggleSort = (field: string) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      if (field === "score") {
        // Higher-better defaults to descending (highest top), lower-better defaults to ascending (lowest top)
        setSortAsc(!isHigherBetter);
      } else {
        setSortAsc(true);
      }
    }
  };

  return (
    <div className="p-6 space-y-5 h-full overflow-y-auto">
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Trophy className="w-5 h-5 text-amber-400" />
            <h2 className="text-base font-bold text-slate-100">Model Leaderboard</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Ranked directly from MLflow runs. Direction:{" "}
            <span className="font-mono text-sky-400 uppercase font-semibold">
              {direction === "max" ? "Higher is better (MAX)" : "Lower is better (MIN)"}
            </span>
          </p>
        </div>

        {/* Metric Selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 font-mono">Rank by Metric:</span>
          <select
            value={selectedMetric}
            onChange={(e) => {
              onSelectMetric(e.target.value);
              setSortField("default");
            }}
            className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono text-slate-100 focus:outline-none focus:border-sky-500"
          >
            {availableMetrics.map((m) => (
              <option key={m} value={m}>
                {m.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
      </div>

      {data?.error && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center gap-2 text-xs font-mono text-amber-300">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
          <span>MLflow note: {data.error}</span>
        </div>
      )}

      {isLoading && (
        <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
          Querying MLflow experiments...
        </div>
      )}

      {!isLoading && items.length === 0 && (
        <div className="p-12 border border-slate-800 rounded-xl bg-slate-900/30 text-center space-y-2">
          <Info className="w-8 h-8 text-slate-600 mx-auto" />
          <div className="text-xs text-slate-400 font-medium">No trained models found for this project</div>
          <div className="text-[11px] text-slate-500">Run the workflow to train scikit-learn candidates</div>
        </div>
      )}

      {/* Leaderboard Table (Column Order: Model | Metric | Score | Feature Version | Dataset Version | Experiment | Training Time | Status) */}
      {!isLoading && items.length > 0 && (
        <div className="border border-slate-800 rounded-xl overflow-x-auto bg-slate-900/50 shadow-sm">
          <table className="w-full text-left text-xs border-collapse min-w-[820px]">
            <thead className="bg-slate-800/80 font-mono text-slate-400 border-b border-slate-800 select-none">
              <tr>
                <th
                  onClick={() => toggleSort("model_name")}
                  className="p-3 cursor-pointer hover:text-slate-200 transition"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Model</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="p-3 font-medium">Metric</th>
                <th
                  onClick={() => toggleSort("score")}
                  className="p-3 cursor-pointer hover:text-slate-200 transition text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Score</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="p-3 font-medium">Feature Version</th>
                <th className="p-3 font-medium">Dataset Version</th>
                <th className="p-3 font-medium">Experiment</th>
                <th
                  onClick={() => toggleSort("duration_seconds")}
                  className="p-3 cursor-pointer hover:text-slate-200 transition text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>Training Time</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="p-3 font-medium text-center">Status</th>
                <th className="p-3 w-8"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 font-mono">
              {items.map((m, idx) => {
                const isBest = idx === 0 && sortField === "default";
                const rawScore =
                  typeof m.score === "number" && !isNaN(m.score)
                    ? m.score
                    : typeof m.metric_value === "number" && !isNaN(m.metric_value)
                    ? m.metric_value
                    : null;
                const formattedScore = rawScore !== null ? rawScore.toFixed(4) : "—";
                const metricName = (m.target_metric || selectedMetric).toUpperCase();

                return (
                  <tr
                    key={m.run_id}
                    onClick={() => setViewingModel(m)}
                    className={cn(
                      "hover:bg-slate-800/50 cursor-pointer transition group",
                      isBest && "bg-amber-500/[0.04]"
                    )}
                  >
                    {/* 1. Model */}
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-100 group-hover:text-sky-300 transition">
                          {m.model_name || m.run_id.slice(0, 12)}
                        </span>
                        {isBest && (
                          <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                            BEST
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {m.model_type || "sklearn"}
                      </div>
                    </td>

                    {/* 2. Metric */}
                    <td className="p-3 text-slate-300">
                      <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700/60 text-[11px] text-slate-300">
                        {metricName}
                      </span>
                    </td>

                    {/* 3. Score (Numeric, Right-aligned) */}
                    <td className="p-3 text-right">
                      <div className="font-bold text-sm text-sky-400">
                        {formattedScore}
                      </div>
                    </td>

                    {/* 4. Feature Version */}
                    <td className="p-3 text-slate-300">
                      <span className="px-2 py-0.5 rounded bg-slate-800/80 text-[11px] text-slate-300">
                        {m.feature_version || "feat_v1"}
                      </span>
                    </td>

                    {/* 5. Dataset Version */}
                    <td className="p-3 text-slate-300">
                      <span className="px-2 py-0.5 rounded bg-slate-800/80 text-[11px] text-slate-300">
                        {m.dataset_version || "dataset_v1"}
                      </span>
                    </td>

                    {/* 6. Experiment */}
                    <td className="p-3 text-slate-400 text-[11px] truncate max-w-[120px]" title={m.experiment_id}>
                      {m.experiment_id ? m.experiment_id.slice(0, 10) : m.run_id.slice(0, 8)}
                    </td>

                    {/* 7. Training Time (Numeric, Right-aligned) */}
                    <td className="p-3 text-right text-slate-300 text-[11px]">
                      {m.duration_seconds !== null && m.duration_seconds !== undefined
                        ? `${m.duration_seconds.toFixed(2)}s`
                        : "—"}
                    </td>

                    {/* 8. Status */}
                    <td className="p-3 text-center">
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-sans font-medium">
                        {m.status || "FINISHED"}
                      </span>
                    </td>

                    <td className="p-3 text-right">
                      <ChevronRight className="w-4 h-4 text-slate-600 group-hover:text-slate-300 transition" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

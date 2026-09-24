import { useState, useMemo } from "react";
import { Trophy, ArrowUpDown, ChevronRight, Info } from "lucide-react";
import clsx from "clsx";
import { LeaderboardResponse, LeaderboardItem } from "../../types";
import { useUIStore } from "../../store/uiStore";

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
  const [sortField, setSortField] = useState<string>("score");
  const [sortAsc, setSortAsc] = useState<boolean>(false);

  const direction = data?.direction || "max";

  const availableMetrics = ["f1", "accuracy", "roc_auc", "precision", "recall", "rmse", "mae", "r2"];

  const items = useMemo(() => {
    if (!data?.leaderboard) return [];
    const list = [...data.leaderboard];

    list.sort((a, b) => {
      let valA: any = a[sortField as keyof LeaderboardItem];
      let valB: any = b[sortField as keyof LeaderboardItem];

      if (sortField === "score") {
        valA = a.score;
        valB = b.score;
      }

      if (valA === undefined || valA === null) return 1;
      if (valB === undefined || valB === null) return -1;

      if (typeof valA === "number" && typeof valB === "number") {
        return sortAsc ? valA - valB : valB - valA;
      }
      return sortAsc ? String(valA).localeCompare(String(valB)) : String(valB).localeCompare(String(valA));
    });

    return list;
  }, [data?.leaderboard, sortField, sortAsc]);

  const toggleSort = (field: string) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      // For score default to direction: if direction is min, ascending is better; if max, descending is better
      if (field === "score") {
        setSortAsc(direction === "min");
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
            Ranked directly from MLflow runs. Target direction:{" "}
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
            onChange={(e) => onSelectMetric(e.target.value)}
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

      {/* Leaderboard Table (NO CHARTS) */}
      {!isLoading && items.length > 0 && (
        <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/50 shadow-sm">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-slate-800/60 font-mono text-slate-400 border-b border-slate-800 select-none">
              <tr>
                <th className="p-3 w-12 text-center">#</th>
                <th
                  onClick={() => toggleSort("model_name")}
                  className="p-3 cursor-pointer hover:text-slate-200 transition"
                >
                  <div className="flex items-center gap-1.5">
                    <span>Model Candidate</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th
                  onClick={() => toggleSort("score")}
                  className="p-3 cursor-pointer hover:text-slate-200 transition text-right"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span>{selectedMetric.toUpperCase()} Score</span>
                    <ArrowUpDown className="w-3 h-3" />
                  </div>
                </th>
                <th className="p-3 font-medium">Feature Version</th>
                <th className="p-3 font-medium">Dataset Version</th>
                <th className="p-3 font-medium">Duration</th>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/80 font-mono">
              {items.map((m, idx) => {
                const isBest = idx === 0;
                return (
                  <tr
                    key={m.run_id}
                    onClick={() => setViewingModel(m)}
                    className={clsx(
                      "hover:bg-slate-800/40 cursor-pointer transition group",
                      isBest && "bg-amber-500/[0.03]"
                    )}
                  >
                    <td className="p-3 text-center text-slate-500 font-bold">
                      {isBest ? <span className="text-amber-400 font-bold">01</span> : `0${idx + 1}`}
                    </td>

                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-100 group-hover:text-sky-300 transition">
                          {m.model_name || m.run_id.slice(0, 10)}
                        </span>
                        {isBest && (
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 font-sans border border-amber-500/30">
                            BEST
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono">
                        Exp: {m.experiment_id.slice(0, 12)}
                      </div>
                    </td>

                    <td className="p-3 text-right">
                      <span className="font-bold text-sm text-sky-400">{m.score.toFixed(4)}</span>
                    </td>

                    <td className="p-3 text-slate-300">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-[11px]">
                        {m.feature_version || "feat_v1"}
                      </span>
                    </td>

                    <td className="p-3 text-slate-300">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-[11px]">
                        {m.dataset_version}
                      </span>
                    </td>

                    <td className="p-3 text-slate-400 text-[11px]">
                      {m.duration_seconds ? `${m.duration_seconds.toFixed(2)}s` : "—"}
                    </td>

                    <td className="p-3">
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-sans font-medium">
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

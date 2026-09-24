import { X, Trophy, Sliders, CheckCircle } from "lucide-react";
import { useUIStore } from "../../store/uiStore";

export function ModelDetailModal() {
  const { viewingModel, setViewingModel } = useUIStore();

  if (!viewingModel) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#0f172a] border border-slate-700 rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-2.5">
            <Trophy className="w-5 h-5 text-amber-400" />
            <div>
              <div className="font-mono text-base font-semibold text-slate-100">
                {viewingModel.model_name || viewingModel.run_id}
              </div>
              <div className="text-xs text-slate-400 font-mono">
                {viewingModel.target_metric.toUpperCase()}:{" "}
                <span className="text-sky-400 font-bold">{viewingModel.score.toFixed(4)}</span>
              </div>
            </div>
          </div>

          <button
            onClick={() => setViewingModel(null)}
            className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs font-mono">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
              <div className="text-slate-500 text-[10px] uppercase">Dataset Version</div>
              <div className="text-slate-200 font-semibold mt-0.5">{viewingModel.dataset_version}</div>
            </div>
            <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
              <div className="text-slate-500 text-[10px] uppercase">Feature Version</div>
              <div className="text-slate-200 font-semibold mt-0.5">
                {viewingModel.feature_version || "feat_v1"}
              </div>
            </div>
            <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
              <div className="text-slate-500 text-[10px] uppercase">Experiment ID</div>
              <div className="text-slate-200 font-semibold mt-0.5">{viewingModel.experiment_id}</div>
            </div>
            <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
              <div className="text-slate-500 text-[10px] uppercase">Duration</div>
              <div className="text-slate-200 font-semibold mt-0.5">
                {viewingModel.duration_seconds ? `${viewingModel.duration_seconds.toFixed(2)}s` : "N/A"}
              </div>
            </div>
          </div>

          {/* Metrics Table */}
          <div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 mb-2">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
              <span>Logged Metrics</span>
            </div>
            <div className="border border-slate-800 rounded-lg overflow-hidden">
              <table className="w-full text-left">
                <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="p-2.5">Metric</th>
                    <th className="p-2.5">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {Object.entries(viewingModel.metrics || {}).map(([key, val]) => (
                    <tr key={key} className="hover:bg-slate-800/30">
                      <td className="p-2.5 text-slate-300 font-medium">{key}</td>
                      <td className="p-2.5 text-sky-400 font-bold">
                        {typeof val === "number" ? val.toFixed(4) : String(val)}
                      </td>
                    </tr>
                  ))}
                  {Object.keys(viewingModel.metrics || {}).length === 0 && (
                    <tr>
                      <td colSpan={2} className="p-4 text-center text-slate-500">
                        No metrics recorded
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Hyperparameters Table */}
          <div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 mb-2">
              <Sliders className="w-3.5 h-3.5 text-purple-400" />
              <span>Hyperparameters</span>
            </div>
            <div className="border border-slate-800 rounded-lg overflow-hidden">
              <table className="w-full text-left">
                <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="p-2.5">Parameter</th>
                    <th className="p-2.5">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/80">
                  {Object.entries(viewingModel.params || {}).map(([key, val]) => (
                    <tr key={key} className="hover:bg-slate-800/30">
                      <td className="p-2.5 text-slate-300 font-medium">{key}</td>
                      <td className="p-2.5 text-slate-400">{String(val)}</td>
                    </tr>
                  ))}
                  {Object.keys(viewingModel.params || {}).length === 0 && (
                    <tr>
                      <td colSpan={2} className="p-4 text-center text-slate-500">
                        No parameters recorded
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import { useState, useId } from "react";
import { useParams } from "react-router-dom";
import { X, Trophy, Sliders, CheckCircle, Upload, Download, Loader2, AlertCircle, FileSpreadsheet } from "lucide-react";
import { useUIStore } from "../../store/uiStore";
import { api } from "../../services/api";

interface ModelDetailModalProps {
  projectId?: string;
}

export function ModelDetailModal({ projectId: propProjectId }: ModelDetailModalProps) {
  const { id: urlProjectId } = useParams<{ id: string }>();
  const projectId = propProjectId || urlProjectId || "";
  const { viewingModel, setViewingModel } = useUIStore();
  const fileInputId = useId();

  const [activeTab, setActiveTab] = useState<"details" | "predict">("details");
  const [testFile, setTestFile] = useState<File | null>(null);
  const [idColumn, setIdColumn] = useState<string>("");
  const [isPredicting, setIsPredicting] = useState<boolean>(false);
  const [predictError, setPredictError] = useState<string | null>(null);
  const [csvResult, setCsvResult] = useState<string | null>(null);
  const [previewRows, setPreviewRows] = useState<{ id: string; pred: string }[]>([]);
  const [previewHeaders, setPreviewHeaders] = useState<[string, string]>(["id", "prediction"]);
  const [totalRowCount, setTotalRowCount] = useState<number>(0);

  if (!viewingModel) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const f = e.target.files[0];
      setTestFile(f);
      setPredictError(null);
      setCsvResult(null);
      setPreviewRows([]);
    }
  };

  const handleGeneratePredictions = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testFile) {
      setPredictError("Please select a test CSV file.");
      return;
    }

    setIsPredicting(true);
    setPredictError(null);

    try {
      const experimentIdOrRunId = viewingModel.run_id || viewingModel.experiment_id;
      const csvText = await api.predictModel(
        projectId,
        experimentIdOrRunId,
        testFile,
        idColumn.trim() || undefined
      );

      setCsvResult(csvText);

      // Parse preview rows from CSV text
      const lines = csvText.trim().split(/\r?\n/).filter(Boolean);
      if (lines.length > 0) {
        const headerParts = lines[0].split(",");
        const col0 = headerParts[0] || "id";
        const col1 = headerParts[1] || "prediction";
        setPreviewHeaders([col0, col1]);

        const rows: { id: string; pred: string }[] = [];
        for (let i = 1; i < Math.min(lines.length, 21); i++) {
          const parts = lines[i].split(",");
          rows.push({
            id: parts[0] ?? "",
            pred: parts.slice(1).join(",") ?? "",
          });
        }
        setPreviewRows(rows);
        setTotalRowCount(Math.max(0, lines.length - 1));
      }
    } catch (err: any) {
      setPredictError(err.message || "Failed to generate predictions.");
      setCsvResult(null);
      setPreviewRows([]);
    } finally {
      setIsPredicting(false);
    }
  };

  const handleDownloadCsv = () => {
    if (!csvResult) return;
    const blob = new Blob([csvResult], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `submission_${viewingModel.model_name || "model"}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#0f172a] border border-slate-700 rounded-xl w-full max-w-3xl max-h-[88vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <Trophy className="w-4 h-4" />
            </div>
            <div>
              <div className="font-mono text-sm font-semibold text-slate-100 flex items-center gap-2">
                <span>{viewingModel.model_name || viewingModel.run_id}</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 font-sans">
                  {viewingModel.model_type || "Model"}
                </span>
              </div>
              <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                {viewingModel.target_metric.toUpperCase()}:{" "}
                <span className="text-sky-400 font-bold">
                  {typeof viewingModel.score === "number" && !isNaN(viewingModel.score)
                    ? viewingModel.score.toFixed(4)
                    : typeof viewingModel.metric_value === "number" && !isNaN(viewingModel.metric_value)
                    ? viewingModel.metric_value.toFixed(4)
                    : "—"}
                </span>
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

        {/* Sub-tab Navigation */}
        <div className="flex items-center gap-2 px-5 pt-3 border-b border-slate-800/80 bg-slate-900/40 text-xs font-mono">
          <button
            onClick={() => setActiveTab("details")}
            className={`px-3 py-2 border-b-2 font-medium transition ${
              activeTab === "details"
                ? "border-sky-400 text-sky-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            Model Details
          </button>
          <button
            onClick={() => setActiveTab("predict")}
            className={`px-3 py-2 border-b-2 font-medium transition flex items-center gap-1.5 ${
              activeTab === "predict"
                ? "border-sky-400 text-sky-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>Predict / Submission</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-5 text-xs font-mono">
          {activeTab === "details" ? (
            <div className="space-y-6">
              {/* Metadata Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
                  <div className="text-slate-500 text-[10px] uppercase font-sans">Dataset Version</div>
                  <div className="text-slate-200 font-semibold mt-0.5">{viewingModel.dataset_version}</div>
                </div>
                <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
                  <div className="text-slate-500 text-[10px] uppercase font-sans">Feature Version</div>
                  <div className="text-slate-200 font-semibold mt-0.5">
                    {viewingModel.feature_version || "feat_v1"}
                  </div>
                </div>
                <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
                  <div className="text-slate-500 text-[10px] uppercase font-sans">Experiment ID</div>
                  <div className="text-slate-200 font-semibold mt-0.5 truncate" title={viewingModel.experiment_id}>
                    {viewingModel.experiment_id}
                  </div>
                </div>
                <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-lg">
                  <div className="text-slate-500 text-[10px] uppercase font-sans">Training Time</div>
                  <div className="text-slate-200 font-semibold mt-0.5">
                    {viewingModel.duration_seconds ? `${viewingModel.duration_seconds.toFixed(2)}s` : "—"}
                  </div>
                </div>
              </div>

              {/* Metrics Table */}
              <div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 mb-2 font-sans">
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Validation Metrics</span>
                </div>
                <div className="border border-slate-800 rounded-lg overflow-hidden bg-slate-900/40">
                  <table className="w-full text-left">
                    <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800">
                      <tr>
                        <th className="p-2.5">Metric</th>
                        <th className="p-2.5 text-right">Score</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/80">
                      {Object.entries(viewingModel.metrics || {}).map(([key, val]) => (
                        <tr key={key} className="hover:bg-slate-800/30">
                          <td className="p-2.5 text-slate-300 font-medium">{key}</td>
                          <td className="p-2.5 text-sky-400 font-bold text-right">
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
                <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 mb-2 font-sans">
                  <Sliders className="w-3.5 h-3.5 text-purple-400" />
                  <span>Hyperparameters</span>
                </div>
                <div className="border border-slate-800 rounded-lg overflow-hidden bg-slate-900/40">
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
          ) : (
            /* Predict Tab */
            <div className="space-y-5">
              <div className="p-3.5 bg-sky-950/20 border border-sky-800/40 rounded-lg text-slate-300 space-y-1">
                <div className="font-semibold text-sky-300 font-sans flex items-center gap-1.5">
                  <FileSpreadsheet className="w-4 h-4" />
                  <span>Kaggle-Style Submission Generator</span>
                </div>
                <p className="text-[11px] text-slate-400 font-mono">
                  Upload an unlabeled test CSV. The pipeline applies the model&apos;s feature transformations and generates predictions formatted as <code className="text-sky-300">&lt;id_column&gt;,&lt;target&gt;</code>.
                </p>
              </div>

              {predictError && (
                <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg flex items-start gap-2.5 text-rose-300 text-xs">
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  <div className="space-y-0.5">
                    <span className="font-semibold font-sans">Prediction Error:</span>
                    <div className="font-mono text-[11px] break-all">{predictError}</div>
                  </div>
                </div>
              )}

              <form onSubmit={handleGeneratePredictions} className="space-y-4">
                {/* File Upload */}
                <div>
                  <label className="block text-slate-300 font-medium mb-1 font-sans">
                    Test Dataset CSV <span className="text-rose-400">*</span>
                  </label>
                  <div className="flex items-center gap-3">
                    <input
                      id={fileInputId}
                      type="file"
                      accept=".csv"
                      onChange={handleFileChange}
                      className="hidden"
                    />
                    <label
                      htmlFor={fileInputId}
                      className="flex items-center gap-2 px-3 py-2 bg-slate-900 border border-slate-700 hover:border-sky-500 rounded-lg cursor-pointer text-slate-200 transition"
                    >
                      <Upload className="w-4 h-4 text-sky-400" />
                      <span>{testFile ? testFile.name : "Choose CSV File..."}</span>
                    </label>
                    {testFile && (
                      <span className="text-slate-400 text-[11px]">
                        ({(testFile.size / 1024).toFixed(1)} KB)
                      </span>
                    )}
                  </div>
                </div>

                {/* ID Column Input */}
                <div>
                  <label className="block text-slate-300 font-medium mb-1 font-sans">
                    ID Column Name <span className="text-slate-500 font-normal">(Optional)</span>
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Id, PassengerId (leave blank to auto-detect or use row indices)"
                    value={idColumn}
                    onChange={(e) => setIdColumn(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 font-mono text-xs"
                  />
                </div>

                {/* Submit Button */}
                <div className="flex items-center justify-between pt-2">
                  <button
                    type="submit"
                    disabled={!testFile || isPredicting}
                    className="flex items-center gap-2 px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold font-sans rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-sky-500/10"
                  >
                    {isPredicting ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Running Transformation &amp; Inference...</span>
                      </>
                    ) : (
                      <>
                        <FileSpreadsheet className="w-4 h-4" />
                        <span>Generate Predictions</span>
                      </>
                    )}
                  </button>

                  {csvResult && (
                    <button
                      type="button"
                      onClick={handleDownloadCsv}
                      className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold font-sans rounded-lg transition shadow-md shadow-emerald-500/10"
                    >
                      <Download className="w-4 h-4" />
                      <span>Download submission.csv</span>
                    </button>
                  )}
                </div>
              </form>

              {/* Predictions Preview Table */}
              {previewRows.length > 0 && (
                <div className="space-y-2 pt-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-200 font-sans flex items-center gap-2">
                      <span>Preview ({previewRows.length} of {totalRowCount} rows)</span>
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Total records: {totalRowCount}
                    </span>
                  </div>

                  <div className="border border-slate-800 rounded-lg overflow-x-auto bg-slate-900/50">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-800/80 text-slate-400 border-b border-slate-800">
                        <tr>
                          <th className="p-2 w-12 text-center">#</th>
                          <th className="p-2 font-medium">{previewHeaders[0]}</th>
                          <th className="p-2 font-medium text-right">{previewHeaders[1]}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono">
                        {previewRows.map((row, idx) => (
                          <tr key={idx} className="hover:bg-slate-800/30">
                            <td className="p-2 text-center text-slate-500">{idx + 1}</td>
                            <td className="p-2 text-slate-200">{row.id}</td>
                            <td className="p-2 text-sky-400 font-semibold text-right">{row.pred}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

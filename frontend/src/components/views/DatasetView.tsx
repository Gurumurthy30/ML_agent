import { useState, useEffect } from "react";
import { Database, Upload, Search, Loader2, AlertCircle } from "lucide-react";
import { Dataset, DatasetPreview } from "../../types";
import { api } from "../../services/api";

interface DatasetViewProps {
  projectId: string;
  datasets: Dataset[];
  onUploadSuccess?: () => void;
}

export function DatasetView({ projectId, datasets, onUploadSuccess }: DatasetViewProps) {
  const [selectedVersion, setSelectedVersion] = useState<string>(
    datasets.length > 0 ? datasets[0].version : "dataset_v1"
  );
  const [preview, setPreview] = useState<DatasetPreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const pageSize = 25;

  useEffect(() => {
    if (datasets.length > 0 && !datasets.some((d) => d.version === selectedVersion)) {
      setSelectedVersion(datasets[0].version);
    }
  }, [datasets, selectedVersion]);

  useEffect(() => {
    if (!selectedVersion || datasets.length === 0) return;
    setIsLoading(true);
    api
      .previewDataset(projectId, selectedVersion)
      .then((data) => setPreview(data))
      .catch(() => setPreview(null))
      .finally(() => setIsLoading(false));
  }, [projectId, selectedVersion, datasets.length]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (!file.name.toLowerCase().endsWith(".csv")) {
        setUploadError("Only tabular .csv files are supported.");
        return;
      }

      setIsUploading(true);
      setUploadError(null);
      try {
        await api.uploadDataset(projectId, file);
        if (onUploadSuccess) onUploadSuccess();
      } catch (err: any) {
        setUploadError(err.message || "Failed to upload dataset.");
      } finally {
        setIsUploading(false);
      }
    }
  };

  const currentDataset = datasets.find((d) => d.version === selectedVersion);

  const filteredRows = (preview?.rows || []).filter((r) => {
    if (!search.trim()) return true;
    return Object.values(r).some((v) => String(v).toLowerCase().includes(search.toLowerCase()));
  });

  return (
    <div className="p-6 space-y-5 h-full overflow-y-auto">
      {/* Top Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-slate-100">Dataset Explorer</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Immutable versioned tabular records. Prior versions are never overwritten.
          </p>
        </div>

        {/* Actions & Version Selector */}
        <div className="flex items-center gap-2.5">
          <select
            value={selectedVersion}
            onChange={(e) => {
              setSelectedVersion(e.target.value);
              setPage(0);
            }}
            className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs font-mono text-slate-100 focus:outline-none focus:border-sky-500"
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.version}>
                {d.version} ({d.row_count} rows, {d.col_count} cols)
              </option>
            ))}
          </select>

          <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-xs font-medium text-slate-200 cursor-pointer transition">
            {isUploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
            <span>Upload New Version</span>
            <input type="file" accept=".csv" onChange={handleFileUpload} className="hidden" />
          </label>
        </div>
      </div>

      {uploadError && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-lg flex items-center gap-2 text-xs font-mono text-rose-300">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{uploadError}</span>
        </div>
      )}

      {datasets.length === 0 && (
        <div className="p-12 border border-slate-800 rounded-xl bg-slate-900/30 text-center space-y-3">
          <Database className="w-8 h-8 text-slate-600 mx-auto" />
          <div className="text-xs text-slate-300 font-medium">No datasets uploaded yet</div>
          <p className="text-[11px] text-slate-500 max-w-sm mx-auto">
            Upload a tabular CSV file to initialize dataset_v1 and begin automated exploration.
          </p>
          <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 text-xs font-semibold cursor-pointer transition">
            {isUploading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
            <span>Upload First Dataset</span>
            <input type="file" accept=".csv" onChange={handleFileUpload} className="hidden" />
          </label>
        </div>
      )}

      {/* Dataset Summary Cards */}
      {currentDataset && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
            <div className="text-[10px] text-slate-500 uppercase">Version Tag</div>
            <div className="text-sky-400 font-bold text-sm mt-0.5">{currentDataset.version}</div>
          </div>
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
            <div className="text-[10px] text-slate-500 uppercase">Original Filename</div>
            <div className="text-slate-200 font-semibold truncate mt-0.5">{currentDataset.filename}</div>
          </div>
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
            <div className="text-[10px] text-slate-500 uppercase">Total Rows</div>
            <div className="text-emerald-400 font-bold text-sm mt-0.5">{currentDataset.row_count}</div>
          </div>
          <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg">
            <div className="text-[10px] text-slate-500 uppercase">Features / Columns</div>
            <div className="text-purple-400 font-bold text-sm mt-0.5">{currentDataset.col_count}</div>
          </div>
        </div>
      )}

      {/* Table Preview */}
      {datasets.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search table preview..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
                className="w-full pl-8 pr-3 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 font-mono"
              />
            </div>

          {preview && (
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
              <span>
                {filteredRows.length} rows matched (showing {page * pageSize + 1}-
                {Math.min((page + 1) * pageSize, filteredRows.length)})
              </span>
              <div className="flex items-center gap-1">
                <button
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  className="px-2 py-1 rounded bg-slate-800 disabled:opacity-40 text-slate-300 hover:bg-slate-700"
                >
                  Prev
                </button>
                <button
                  disabled={(page + 1) * pageSize >= filteredRows.length}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-2 py-1 rounded bg-slate-800 disabled:opacity-40 text-slate-300 hover:bg-slate-700"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>

        {isLoading && (
          <div className="p-12 text-center text-xs text-slate-500 font-mono animate-pulse">
            Loading dataset preview...
          </div>
        )}

        {!isLoading && preview && preview.columns && (
          <div className="border border-slate-800 rounded-xl overflow-x-auto bg-slate-900/40">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-slate-800/60 font-mono text-slate-300 border-b border-slate-800">
                <tr>
                  <th className="p-2.5 w-10 text-center text-slate-500 font-mono">#</th>
                  {preview.columns.map((col) => (
                    <th key={col} className="p-2.5 font-medium truncate max-w-[180px]">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80 font-mono">
                {filteredRows.slice(page * pageSize, (page + 1) * pageSize).map((row, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/30">
                    <td className="p-2.5 text-center text-slate-600 text-[10px]">
                      {page * pageSize + idx + 1}
                    </td>
                    {preview.columns.map((col) => (
                      <td key={col} className="p-2.5 text-slate-300 truncate max-w-[180px]">
                        {String(row[col] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}
    </div>
  );
}

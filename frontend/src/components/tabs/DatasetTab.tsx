import React, { useState, useEffect, useCallback } from 'react';
import { Database, RefreshCw, AlertCircle, FileSpreadsheet, CheckCircle, ArrowRight } from 'lucide-react';
import { PipelineRun, DatasetPreviewResponse } from '../../types/run';
import { getDatasetPreview } from '../../services/api';

interface DatasetTabProps {
  run: PipelineRun;
}

export const DatasetTab: React.FC<DatasetTabProps> = ({ run }) => {
  const [preview, setPreview] = useState<DatasetPreviewResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState<number>(50);

  const fetchPreview = useCallback(async () => {
    if (!run?.run_id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getDatasetPreview(run.run_id, limit);
      setPreview(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load dataset preview');
    } finally {
      setLoading(false);
    }
  }, [run?.run_id, limit]);

  useEffect(() => {
    fetchPreview();
  }, [fetchPreview]);

  return (
    <div className="p-5 space-y-5 flex flex-col h-full overflow-hidden" data-testid="dataset-tab">
      {/* Tab Header & Telemetry Badges */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4 flex-shrink-0">
        <div>
          <div className="flex items-center space-x-2">
            <h3 className="text-sm font-semibold text-slate-200">Dataset Preview</h3>
            {preview && (
              <span
                className={`text-[11px] px-2 py-0.5 rounded-full font-medium border ${
                  preview.is_transformed
                    ? 'bg-emerald-950/60 border-emerald-500/50 text-emerald-300'
                    : 'bg-blue-950/60 border-blue-500/50 text-blue-300'
                }`}
              >
                {preview.is_transformed ? 'Transformed (Features Output)' : 'Original (Source)'}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 font-mono mt-1 break-all">
            {preview ? preview.dataset_path : run.dataset_path}
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-3">
          {preview && (
            <div className="flex items-center space-x-2 text-xs text-slate-400 bg-slate-900/60 border border-slate-800 px-2.5 py-1 rounded-lg">
              <span>Rows: <strong className="text-slate-200">{preview.total_rows.toLocaleString()}</strong></span>
              <span className="text-slate-600">|</span>
              <span>Cols: <strong className="text-slate-200">{preview.total_columns}</strong></span>
            </div>
          )}

          <div className="flex items-center space-x-1.5 text-xs text-slate-400">
            <span>Limit:</span>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              disabled={loading}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-2 py-1 outline-none focus:border-indigo-500 disabled:opacity-50"
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>

          <button
            onClick={fetchPreview}
            disabled={loading}
            className="flex items-center space-x-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded border border-slate-700 transition disabled:opacity-50"
            title="Refresh preview"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-400' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {loading && !preview ? (
          <div className="flex-1 flex flex-col items-center justify-center space-y-3 text-slate-400">
            <RefreshCw className="w-7 h-7 animate-spin text-indigo-400" />
            <p className="text-xs">Loading dataset preview from disk...</p>
          </div>
        ) : error ? (
          <div className="p-6 bg-rose-950/20 border border-rose-800/40 rounded-xl space-y-3 text-center my-auto">
            <AlertCircle className="w-8 h-8 text-rose-400 mx-auto" />
            <h4 className="text-sm font-semibold text-rose-300">Dataset Preview Unavailable</h4>
            <p className="text-xs text-rose-300/80 max-w-lg mx-auto font-mono bg-rose-950/40 p-2.5 rounded border border-rose-900/50">
              {error}
            </p>
            <button
              onClick={fetchPreview}
              className="px-3 py-1.5 bg-rose-900/60 hover:bg-rose-800/70 text-white rounded text-xs font-medium transition"
            >
              Try Again
            </button>
          </div>
        ) : !preview || preview.preview_rows.length === 0 ? (
          <div className="p-8 text-center bg-slate-950/40 border border-slate-800 rounded-xl my-auto">
            <FileSpreadsheet className="w-8 h-8 text-slate-500 mx-auto mb-2 opacity-50" />
            <p className="text-xs text-slate-400">No data rows found in dataset file.</p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-slate-900/40 border border-slate-800/80 rounded-xl">
            {/* Scrollable Table Container */}
            <div className="flex-1 overflow-auto">
              <table className="w-full text-left text-xs text-slate-300 border-collapse">
                <thead className="bg-slate-900/90 text-slate-400 uppercase tracking-wider text-[11px] sticky top-0 z-10 border-b border-slate-800 backdrop-blur-sm">
                  <tr>
                    <th className="py-2.5 px-3 w-12 font-mono text-slate-500 text-center border-r border-slate-800/50">
                      #
                    </th>
                    {preview.columns.map((col) => (
                      <th key={col} className="py-2.5 px-3 font-semibold text-slate-200 border-r border-slate-800/50 whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/40 font-mono text-[11px]">
                  {preview.preview_rows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-indigo-950/20 transition-colors">
                      <td className="py-2 px-3 text-center text-slate-500 select-none border-r border-slate-800/40 bg-slate-950/30">
                        {idx + 1}
                      </td>
                      {preview.columns.map((col) => {
                        const val = row[col];
                        const isNull = val === null || val === undefined;
                        return (
                          <td
                            key={col}
                            className={`py-2 px-3 border-r border-slate-800/40 whitespace-nowrap ${
                              isNull ? 'text-slate-500 italic' : 'text-slate-300'
                            }`}
                          >
                            {isNull ? (
                              <span className="text-[10px] px-1 py-0.5 rounded bg-slate-800/70 text-slate-400">
                                null
                              </span>
                            ) : typeof val === 'object' ? (
                              JSON.stringify(val)
                            ) : (
                              String(val)
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Table Footer summary */}
            <div className="px-4 py-2 border-t border-slate-800/80 bg-slate-950/60 flex items-center justify-between text-[11px] text-slate-400">
              <span>
                Displaying first <strong className="text-slate-300">{preview.preview_rows.length}</strong> rows of{' '}
                <strong className="text-slate-300">{preview.total_rows.toLocaleString()}</strong> total
              </span>
              <span>
                <strong className="text-slate-300">{preview.columns.length}</strong> columns detected
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

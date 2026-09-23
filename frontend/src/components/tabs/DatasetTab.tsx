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
    <div className="p-5 space-y-5 flex flex-col h-full overflow-hidden bg-[#FAF9F5] dark:bg-[#090D16] text-stone-900 dark:text-slate-100 transition-colors" data-testid="dataset-tab">
      {/* Tab Header & Telemetry Badges */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E8E6DF] dark:border-slate-800 pb-4 flex-shrink-0">
        <div>
          <div className="flex items-center space-x-2">
            <h3 className="text-sm font-semibold text-stone-900 dark:text-slate-100">Dataset Preview</h3>
            {preview && (
              <span
                className={`text-[11px] px-2.5 py-0.5 rounded-full font-medium border ${
                  preview.is_transformed
                    ? 'bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'
                    : 'bg-violet-50 dark:bg-violet-950/60 border-violet-200 dark:border-violet-800 text-violet-700 dark:text-violet-300'
                }`}
              >
                {preview.is_transformed ? 'Transformed (Features Output)' : 'Original (Source)'}
              </span>
            )}
          </div>
          <p className="text-xs text-stone-500 dark:text-slate-400 font-mono mt-1 break-all">
            {preview ? preview.dataset_path : run.dataset_path}
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-3">
          {preview && (
            <div className="flex items-center space-x-2 text-xs text-stone-600 dark:text-slate-300 bg-[#F5F4EE] dark:bg-slate-800 border border-[#E8E6DF] dark:border-slate-700 px-2.5 py-1 rounded-lg">
              <span>Rows: <strong className="text-stone-900 dark:text-slate-100">{preview.total_rows.toLocaleString()}</strong></span>
              <span className="text-stone-300 dark:text-slate-600">|</span>
              <span>Cols: <strong className="text-stone-900 dark:text-slate-100">{preview.total_columns}</strong></span>
            </div>
          )}

          <div className="flex items-center space-x-1.5 text-xs text-stone-500 dark:text-slate-400">
            <span>Limit:</span>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              disabled={loading}
              className="bg-white dark:bg-slate-800 border border-stone-200 dark:border-slate-700 text-stone-800 dark:text-slate-200 text-xs rounded-lg px-2 py-1 outline-none focus:border-stone-400 dark:focus:border-slate-500 disabled:opacity-50"
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>

          <button
            onClick={fetchPreview}
            disabled={loading}
            className="flex items-center space-x-1 px-2.5 py-1 bg-white dark:bg-slate-800 hover:bg-stone-50 dark:hover:bg-slate-700 text-stone-700 dark:text-slate-200 text-xs rounded-lg border border-stone-200 dark:border-slate-700 shadow-xs transition disabled:opacity-50"
            title="Refresh preview"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-stone-600 dark:text-slate-400' : 'text-stone-500 dark:text-slate-400'}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {loading && !preview ? (
          <div className="flex-1 flex flex-col items-center justify-center space-y-3 text-stone-400 dark:text-slate-500">
            <RefreshCw className="w-7 h-7 animate-spin text-stone-400 dark:text-slate-500" />
            <p className="text-xs">Loading dataset preview from disk...</p>
          </div>
        ) : error ? (
          <div className="p-6 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-xl space-y-3 text-center my-auto">
            <AlertCircle className="w-8 h-8 text-rose-600 dark:text-rose-400 mx-auto" />
            <h4 className="text-sm font-semibold text-rose-800 dark:text-rose-300">Dataset Preview Unavailable</h4>
            <p className="text-xs text-rose-700 dark:text-rose-300 max-w-lg mx-auto font-mono bg-rose-100/50 dark:bg-rose-900/40 p-2.5 rounded-lg border border-rose-200 dark:border-rose-800">
              {error}
            </p>
            <button
              onClick={fetchPreview}
              className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-medium transition"
            >
              Try Again
            </button>
          </div>
        ) : !preview || preview.preview_rows.length === 0 ? (
          <div className="p-8 text-center bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl shadow-xs my-auto">
            <FileSpreadsheet className="w-8 h-8 text-stone-300 dark:text-slate-600 mx-auto mb-2" />
            <p className="text-xs text-stone-500 dark:text-slate-400">No data rows found in dataset file.</p>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl shadow-xs">
            {/* Scrollable Table Container */}
            <div className="flex-1 overflow-auto">
              <table className="w-full text-left text-xs text-stone-800 dark:text-slate-200 border-collapse">
                <thead className="bg-[#FAF9F5] dark:bg-slate-950 text-stone-600 dark:text-slate-400 uppercase tracking-wider text-[11px] sticky top-0 z-10 border-b border-[#E8E6DF] dark:border-slate-800">
                  <tr>
                    <th className="py-2.5 px-3 w-12 font-mono text-stone-400 dark:text-slate-500 text-center border-r border-[#E8E6DF]/60 dark:border-slate-800/60">
                      #
                    </th>
                    {preview.columns.map((col) => (
                      <th key={col} className="py-2.5 px-3 font-semibold text-stone-800 dark:text-slate-200 border-r border-[#E8E6DF]/60 dark:border-slate-800/60 whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E8E6DF]/60 dark:divide-slate-800/60 font-mono text-[11px]">
                  {preview.preview_rows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-[#FAF9F5] dark:hover:bg-slate-800/40 transition-colors">
                      <td className="py-2 px-3 text-center text-stone-400 dark:text-slate-500 select-none border-r border-[#E8E6DF]/60 dark:border-slate-800/60 bg-[#FAF9F5]/40 dark:bg-slate-950/40">
                        {idx + 1}
                      </td>
                      {preview.columns.map((col) => {
                        const val = row[col];
                        const isNull = val === null || val === undefined;
                        return (
                          <td
                            key={col}
                            className={`py-2 px-3 border-r border-[#E8E6DF]/60 dark:border-slate-800/60 whitespace-nowrap ${
                              isNull ? 'text-stone-400 dark:text-slate-600 italic' : 'text-stone-800 dark:text-slate-200'
                            }`}
                          >
                            {isNull ? (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-stone-100 dark:bg-slate-800 text-stone-500 dark:text-slate-400">
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
            <div className="px-4 py-2 border-t border-[#E8E6DF] dark:border-slate-800 bg-[#FAF9F5] dark:bg-slate-950 flex items-center justify-between text-[11px] text-stone-500 dark:text-slate-400">
              <span>
                Displaying first <strong className="text-stone-700 dark:text-slate-200">{preview.preview_rows.length}</strong> rows of{' '}
                <strong className="text-stone-700 dark:text-slate-200">{preview.total_rows.toLocaleString()}</strong> total
              </span>
              <span>
                <strong className="text-stone-700 dark:text-slate-200">{preview.columns.length}</strong> columns detected
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

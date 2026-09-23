import React, { useState } from 'react';
import { X, Play, AlertCircle, ShieldAlert, CheckCircle2, ChevronRight, FileSpreadsheet } from 'lucide-react';
import { RunCreatePayload } from '../../types/run';
import { createRun, inspectDataset } from '../../services/api';

interface CreateRunModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRunCreated: (runId: string) => void;
}

export const CreateRunModal: React.FC<CreateRunModalProps> = ({
  isOpen,
  onClose,
  onRunCreated,
}) => {
  const [datasetPath, setDatasetPath] = useState('smoke_data/tiny.csv');
  const [targetColumn, setTargetColumn] = useState('target');
  const [excludeColumns, setExcludeColumns] = useState('');
  const [mode, setMode] = useState<'full_pipeline' | 'eda_only'>('full_pipeline');
  const [guidedMode, setGuidedMode] = useState(false);
  const [metricName, setMetricName] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [userInstructions, setUserInstructions] = useState('');
  const [isBaseline, setIsBaseline] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Leakage confirmation state
  const [detectedLeakage, setDetectedLeakage] = useState<string[]>([]);
  const [showLeakageConfirm, setShowLeakageConfirm] = useState(false);

  if (!isOpen) return null;

  const doSubmit = async (overrideExcludeCols?: string[]) => {
    setErrorMessage(null);
    setIsSubmitting(true);

    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const effectiveExcludes = overrideExcludeCols !== undefined
      ? overrideExcludeCols
      : excludeColumns
          .split(',')
          .map((c) => c.trim())
          .filter(Boolean);

    const payload: RunCreatePayload = {
      dataset_path: datasetPath.trim(),
      target_column: targetColumn.trim(),
      exclude_columns: effectiveExcludes.length > 0 ? effectiveExcludes : undefined,
      mode,
      guided_mode: guidedMode,
      metric_name: metricName.trim() || undefined,
      tags: tags.length > 0 ? tags : undefined,
      user_instructions: userInstructions.trim() || undefined,
      is_baseline: isBaseline,
    };

    try {
      const created = await createRun(payload);
      onRunCreated(created.run_id);
      setShowLeakageConfirm(false);
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to start pipeline run.');
      setShowLeakageConfirm(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const trimmedTarget = targetColumn.trim();
    if (!trimmedTarget) {
      setErrorMessage('Target Column * is required. Please specify the column to predict.');
      return;
    }

    const userExcludes = excludeColumns
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean);

    // If user left exclude columns blank, auto-detect candidates first
    if (userExcludes.length === 0) {
      setIsSubmitting(true);
      try {
        const inspectRes = await inspectDataset({
          dataset_path: datasetPath.trim(),
          target_column: trimmedTarget,
        });

        if (inspectRes.leakage_candidates && inspectRes.leakage_candidates.length > 0) {
          setDetectedLeakage(inspectRes.leakage_candidates);
          setShowLeakageConfirm(true);
          setIsSubmitting(false);
          return;
        }
      } catch (err) {
        // If inspection fails (e.g. non-existent file or offline), proceed to let createRun validate
        console.warn('Dataset inspection preflight skipped:', err);
      } finally {
        setIsSubmitting(false);
      }
    }

    // Direct submit
    await doSubmit();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-fadeIn text-stone-900 dark:text-slate-100 transition-colors">
        {/* Modal Header */}
        <div className="p-4 border-b border-[#E8E6DF] dark:border-slate-800 flex items-center justify-between bg-[#FAF9F5] dark:bg-slate-950">
          <div className="flex items-center space-x-2.5">
            <div className="p-1.5 rounded-lg bg-stone-100 dark:bg-slate-800 text-stone-800 dark:text-slate-200 border border-stone-200 dark:border-slate-700">
              <Play className="w-3.5 h-3.5 fill-current text-violet-700 dark:text-violet-400" />
            </div>
            <h3 className="text-sm font-semibold text-stone-900 dark:text-slate-100">Initialize New Pipeline Run</h3>
          </div>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-600 dark:hover:text-slate-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4 text-xs">
          {errorMessage && (
            <div className="p-3 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-lg text-rose-800 dark:text-rose-300 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Leakage Confirmation Dialog */}
          {showLeakageConfirm && (
            <div className="p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 rounded-xl space-y-3 animate-fadeIn">
              <div className="flex items-start space-x-2.5">
                <ShieldAlert className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-amber-900 dark:text-amber-200 text-xs">
                    Potential Target Leakage Detected
                  </h4>
                  <p className="text-[11px] text-amber-800 dark:text-amber-300 mt-1 leading-relaxed">
                    The following column(s) have a 1:1 bijective encoding with target <span className="font-mono font-bold">"{targetColumn}"</span> and will cause trivial label leakage if used as features:
                  </p>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {detectedLeakage.map((col) => (
                      <span key={col} className="px-2 py-0.5 rounded bg-amber-200 dark:bg-amber-900 text-amber-950 dark:text-amber-100 font-mono font-semibold text-[10px] border border-amber-300 dark:border-amber-700">
                        {col}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end space-x-2 pt-2 border-t border-amber-200 dark:border-amber-800/40">
                <button
                  type="button"
                  onClick={() => setShowLeakageConfirm(false)}
                  className="px-2.5 py-1 text-stone-600 dark:text-slate-400 hover:text-stone-900 dark:hover:text-slate-200 text-[11px]"
                >
                  Edit Inputs
                </button>
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => doSubmit([])}
                  className="px-2.5 py-1 rounded bg-stone-200 dark:bg-slate-800 hover:bg-stone-300 dark:hover:bg-slate-700 text-stone-800 dark:text-slate-200 font-medium text-[11px]"
                >
                  Keep as Features
                </button>
                <button
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => doSubmit(detectedLeakage)}
                  className="px-3 py-1 rounded bg-amber-600 dark:bg-amber-500 hover:bg-amber-700 dark:hover:bg-amber-400 text-white font-medium text-[11px] shadow-xs flex items-center space-x-1"
                >
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Exclude & Launch</span>
                </button>
              </div>
            </div>
          )}

          {/* Dataset Path */}
          <div className="space-y-1">
            <label className="font-medium text-stone-700 dark:text-slate-300">Dataset File Path *</label>
            <div className="relative">
              <input
                type="text"
                required
                value={datasetPath}
                onChange={(e) => setDatasetPath(e.target.value)}
                placeholder="e.g. smoke_data/tiny.csv or path/to/dataset.csv"
                className="w-full bg-[#F5F4EE] dark:bg-slate-800 border border-[#E8E6DF] dark:border-slate-700 text-stone-900 dark:text-slate-100 p-2 rounded-lg focus:outline-none focus:border-stone-400 dark:focus:border-slate-500 font-mono"
              />
            </div>
            <p className="text-[10px] text-stone-500 dark:text-slate-400">Must be a valid local .csv or .parquet file path.</p>
          </div>

          {/* Target Column * & Leakage Excludes */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="font-medium text-stone-700 dark:text-slate-300 flex items-center justify-between">
                <span>Target Column *</span>
                <span className="text-[10px] text-amber-600 dark:text-amber-400 font-semibold">Required</span>
              </label>
              <input
                type="text"
                required
                value={targetColumn}
                onChange={(e) => setTargetColumn(e.target.value)}
                placeholder="e.g. target or label"
                className="w-full bg-[#F5F4EE] dark:bg-slate-800 border border-stone-300 dark:border-slate-700 text-stone-900 dark:text-slate-100 p-2 rounded-lg focus:outline-none focus:border-violet-500 dark:focus:border-violet-400 font-mono font-medium"
              />
            </div>

            <div className="space-y-1">
              <label className="font-medium text-stone-700 dark:text-slate-300">Leakage / ID Columns to Exclude</label>
              <input
                type="text"
                value={excludeColumns}
                onChange={(e) => setExcludeColumns(e.target.value)}
                placeholder="e.g. species, id (optional)"
                className="w-full bg-[#F5F4EE] dark:bg-slate-800 border border-[#E8E6DF] dark:border-slate-700 text-stone-900 dark:text-slate-100 p-2 rounded-lg focus:outline-none focus:border-stone-400 dark:focus:border-slate-500 font-mono"
              />
            </div>
          </div>

          {/* Mode & Metric */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="font-medium text-stone-700 dark:text-slate-300">Execution Mode</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as any)}
                className="w-full bg-[#F5F4EE] dark:bg-slate-800 border border-[#E8E6DF] dark:border-slate-700 text-stone-800 dark:text-slate-200 p-2 rounded-lg focus:outline-none focus:border-stone-400 dark:focus:border-slate-500"
              >
                <option value="full_pipeline">Full Pipeline (EDA + Features + Modeling)</option>
                <option value="eda_only">EDA Only</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="font-medium text-stone-700 dark:text-slate-300">Target Metric (Optional)</label>
              <input
                type="text"
                value={metricName}
                onChange={(e) => setMetricName(e.target.value)}
                placeholder="e.g. accuracy, f1, rmse"
                className="w-full bg-[#F5F4EE] dark:bg-slate-800 border border-[#E8E6DF] dark:border-slate-700 text-stone-900 dark:text-slate-100 p-2 rounded-lg focus:outline-none focus:border-stone-400 dark:focus:border-slate-500 font-mono"
              />
            </div>
          </div>

          {/* Guided Mode & Baseline */}
          <div className="grid grid-cols-2 gap-3 pt-1">
            <label className="flex items-center space-x-2.5 bg-[#FAF9F5] dark:bg-slate-800/60 p-2.5 rounded-lg border border-[#E8E6DF] dark:border-slate-700 cursor-pointer hover:border-stone-400 dark:hover:border-slate-500">
              <input
                type="checkbox"
                checked={guidedMode}
                onChange={(e) => setGuidedMode(e.target.checked)}
                className="rounded border-stone-300 dark:border-slate-600 text-violet-600 focus:ring-0"
              />
              <div>
                <span className="font-semibold text-stone-800 dark:text-slate-200">Guided Mode</span>
                <p className="text-[10px] text-stone-500 dark:text-slate-400">Pause for approval on each step</p>
              </div>
            </label>

            <label className="flex items-center space-x-2.5 bg-[#FAF9F5] dark:bg-slate-800/60 p-2.5 rounded-lg border border-[#E8E6DF] dark:border-slate-700 cursor-pointer hover:border-stone-400 dark:hover:border-slate-500">
              <input
                type="checkbox"
                checked={isBaseline}
                onChange={(e) => setIsBaseline(e.target.checked)}
                className="rounded border-stone-300 dark:border-slate-600 text-violet-600 focus:ring-0"
              />
              <div>
                <span className="font-semibold text-stone-800 dark:text-slate-200">Mark as Baseline</span>
                <p className="text-[10px] text-stone-500 dark:text-slate-400">Benchmark reference for future runs</p>
              </div>
            </label>
          </div>

          {/* Tags */}
          <div className="space-y-1">
            <label className="font-medium text-stone-700 dark:text-slate-300">Tags (Comma Separated)</label>
            <input
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="e.g. baseline, v1, randomforest"
              className="w-full bg-[#F5F4EE] dark:bg-slate-800 border border-[#E8E6DF] dark:border-slate-700 text-stone-900 dark:text-slate-100 p-2 rounded-lg focus:outline-none focus:border-stone-400 dark:focus:border-slate-500"
            />
          </div>

          {/* User instructions */}
          <div className="space-y-1">
            <label className="font-medium text-stone-700 dark:text-slate-300">Custom Prompt Instructions (Optional)</label>
            <textarea
              value={userInstructions}
              onChange={(e) => setUserInstructions(e.target.value)}
              placeholder="e.g. Prioritize tree-based models and handle skewed numeric features..."
              rows={2}
              className="w-full bg-[#F5F4EE] dark:bg-slate-800 border border-[#E8E6DF] dark:border-slate-700 text-stone-900 dark:text-slate-100 p-2 rounded-lg focus:outline-none focus:border-stone-400 dark:focus:border-slate-500"
            />
          </div>

          {/* Buttons */}
          <div className="pt-3 flex items-center justify-end space-x-2.5 border-t border-[#E8E6DF] dark:border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-3.5 py-1.5 bg-stone-100 dark:bg-slate-800 hover:bg-stone-200 dark:hover:bg-slate-700 text-stone-700 dark:text-slate-300 rounded-lg font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || showLeakageConfirm}
              className="px-4 py-1.5 bg-stone-900 dark:bg-violet-600 hover:bg-stone-800 dark:hover:bg-violet-500 text-white rounded-lg font-medium transition shadow-xs disabled:opacity-50 flex items-center space-x-1.5"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isSubmitting ? 'Starting...' : 'Launch Run'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

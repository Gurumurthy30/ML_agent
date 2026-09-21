import React, { useState } from 'react';
import { X, Play, AlertCircle, FileSpreadsheet } from 'lucide-react';
import { RunCreatePayload } from '../../types/run';
import { createRun } from '../../services/api';

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
  const [mode, setMode] = useState<'full_pipeline' | 'eda_only'>('full_pipeline');
  const [guidedMode, setGuidedMode] = useState(false);
  const [metricName, setMetricName] = useState('');
  const [tagsInput, setTagsInput] = useState('');
  const [userInstructions, setUserInstructions] = useState('');
  const [isBaseline, setIsBaseline] = useState(false);
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsSubmitting(true);

    const tags = tagsInput
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const payload: RunCreatePayload = {
      dataset_path: datasetPath.trim(),
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
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to start pipeline run.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg shadow-2xl overflow-hidden animate-fadeIn">
        {/* Modal Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center space-x-2">
            <div className="p-1.5 rounded-md bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <Play className="w-4 h-4 fill-current" />
            </div>
            <h3 className="text-sm font-semibold text-slate-100">Initialize New Pipeline Run</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4 text-xs">
          {errorMessage && (
            <div className="p-3 bg-rose-950/80 border border-rose-500/50 rounded-lg text-rose-200 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Dataset Path */}
          <div className="space-y-1">
            <label className="font-medium text-slate-300">Dataset File Path *</label>
            <div className="relative">
              <input
                type="text"
                required
                value={datasetPath}
                onChange={(e) => setDatasetPath(e.target.value)}
                placeholder="e.g. smoke_data/tiny.csv or path/to/dataset.csv"
                className="w-full bg-slate-950 border border-slate-700 text-slate-200 p-2 rounded focus:outline-none focus:border-indigo-500 font-mono"
              />
            </div>
            <p className="text-[10px] text-slate-400">Must be a valid local .csv or .parquet file path.</p>
          </div>

          {/* Mode & Metric */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="font-medium text-slate-300">Execution Mode</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as any)}
                className="w-full bg-slate-950 border border-slate-700 text-slate-200 p-2 rounded focus:outline-none focus:border-indigo-500"
              >
                <option value="full_pipeline">Full Pipeline (EDA + Features + Modeling)</option>
                <option value="eda_only">EDA Only</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="font-medium text-slate-300">Target Metric (Optional)</label>
              <input
                type="text"
                value={metricName}
                onChange={(e) => setMetricName(e.target.value)}
                placeholder="e.g. accuracy, f1, rmse"
                className="w-full bg-slate-950 border border-slate-700 text-slate-200 p-2 rounded focus:outline-none focus:border-indigo-500 font-mono"
              />
            </div>
          </div>

          {/* Guided Mode & Baseline */}
          <div className="grid grid-cols-2 gap-3 pt-1">
            <label className="flex items-center space-x-2 bg-slate-950/60 p-2.5 rounded border border-slate-800 cursor-pointer hover:border-slate-700">
              <input
                type="checkbox"
                checked={guidedMode}
                onChange={(e) => setGuidedMode(e.target.checked)}
                className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0"
              />
              <div>
                <span className="font-semibold text-slate-200">Guided Mode</span>
                <p className="text-[10px] text-slate-400">Pause for human approval on every step</p>
              </div>
            </label>

            <label className="flex items-center space-x-2 bg-slate-950/60 p-2.5 rounded border border-slate-800 cursor-pointer hover:border-slate-700">
              <input
                type="checkbox"
                checked={isBaseline}
                onChange={(e) => setIsBaseline(e.target.checked)}
                className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0"
              />
              <div>
                <span className="font-semibold text-slate-200">Mark as Baseline</span>
                <p className="text-[10px] text-slate-400">Benchmark reference for future runs</p>
              </div>
            </label>
          </div>

          {/* Tags */}
          <div className="space-y-1">
            <label className="font-medium text-slate-300">Tags (Comma Separated)</label>
            <input
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder="e.g. baseline, v1, randomforest"
              className="w-full bg-slate-950 border border-slate-700 text-slate-200 p-2 rounded focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* User instructions */}
          <div className="space-y-1">
            <label className="font-medium text-slate-300">Custom Prompt Instructions (Optional)</label>
            <textarea
              value={userInstructions}
              onChange={(e) => setUserInstructions(e.target.value)}
              placeholder="e.g. Prioritize tree-based models and handle skewed numeric features..."
              rows={2}
              className="w-full bg-slate-950 border border-slate-700 text-slate-200 p-2 rounded focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Buttons */}
          <div className="pt-2 flex items-center justify-end space-x-2 border-t border-slate-800">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded font-semibold transition disabled:opacity-50 flex items-center space-x-1.5"
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

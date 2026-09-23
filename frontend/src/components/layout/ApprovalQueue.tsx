import React, { useState } from 'react';
import { AlertCircle, CheckCircle, Edit3, XCircle, AlertTriangle, ShieldAlert } from 'lucide-react';
import { PipelineRun } from '../../types/run';
import { resumeRun } from '../../services/api';

interface ApprovalQueueProps {
  pausedRuns: PipelineRun[];
  onActionComplete: () => void;
  onSelectRun: (runId: string) => void;
}

export const ApprovalQueue: React.FC<ApprovalQueueProps> = ({
  pausedRuns,
  onActionComplete,
  onSelectRun,
}) => {
  // State for modification input per run_id
  const [modifyingRunId, setModifyingRunId] = useState<string | null>(null);
  const [modificationText, setModificationText] = useState<string>('');
  
  // Loading and error states per run_id
  const [submittingRunId, setSubmittingRunId] = useState<string | null>(null);
  const [actionErrors, setActionErrors] = useState<Record<string, { message: string; code?: number }>>({});
  const [successNotices, setSuccessNotices] = useState<Record<string, string>>({});

  const handleDecision = async (
    runId: string,
    decision: 'approved' | 'modify' | 'reject',
    modifications?: string
  ) => {
    setSubmittingRunId(runId);
    setActionErrors((prev) => {
      const copy = { ...prev };
      delete copy[runId];
      return copy;
    });

    try {
      await resumeRun(runId, {
        approval_status: decision,
        modifications: decision === 'modify' ? modifications : undefined,
      });

      setSuccessNotices((prev) => ({
        ...prev,
        [runId]: `Successfully resumed with verdict: ${decision.toUpperCase()}`,
      }));
      setModifyingRunId(null);
      setModificationText('');

      // Notify parent to refresh runs list
      setTimeout(() => {
        onActionComplete();
      }, 500);
    } catch (err: any) {
      const statusCode = err.status || (err.message?.includes('409') ? 409 : err.message?.includes('400') ? 400 : undefined);
      let displayMessage = err.message || 'Action failed.';

      if (statusCode === 409) {
        displayMessage = '⚠️ Run was already resumed elsewhere or is no longer in paused state.';
      } else if (statusCode === 400) {
        displayMessage = `⚠️ Invalid approval request: ${err.message}`;
      }

      setActionErrors((prev) => ({
        ...prev,
        [runId]: { message: displayMessage, code: statusCode },
      }));
    } finally {
      setSubmittingRunId(null);
    }
  };

  return (
    <aside className="w-80 h-full border-l border-[#E8E6DF] dark:border-slate-800 bg-white dark:bg-[#0F172A] flex flex-col flex-shrink-0 select-none transition-colors">
      {/* Queue Header */}
      <div className="p-3.5 border-b border-[#E8E6DF] dark:border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <ShieldAlert className="w-4 h-4 text-amber-600 dark:text-amber-400" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-stone-900 dark:text-slate-100">
            Approval Queue
          </h2>
        </div>
        <span
          data-testid="pending-count"
          className="px-2 py-0.5 text-[11px] font-mono font-semibold rounded-full bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300"
        >
          {pausedRuns.length} pending
        </span>
      </div>

      {/* Queue List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-[#FAF9F5] dark:bg-[#090D16]">
        {pausedRuns.length === 0 ? (
          <div className="h-48 flex flex-col items-center justify-center text-center p-4 text-stone-400 dark:text-slate-500">
            <CheckCircle className="w-8 h-8 text-stone-300 dark:text-slate-600 mb-2" />
            <p className="text-xs font-medium text-stone-700 dark:text-slate-300">Queue is Clear</p>
            <p className="text-[11px] text-stone-500 dark:text-slate-400 mt-0.5">
              No pipeline runs are currently waiting for human intervention.
            </p>
          </div>
        ) : (
          pausedRuns.map((run) => {
            const isSubmitting = submittingRunId === run.run_id;
            const error = actionErrors[run.run_id];
            const success = successNotices[run.run_id];
            const isModifying = modifyingRunId === run.run_id;

            return (
              <div
                key={run.run_id}
                className="bg-white dark:bg-slate-800/90 border border-[#E8E6DF] dark:border-slate-700 rounded-xl p-3.5 space-y-2.5 shadow-xs"
              >
                {/* Run Title */}
                <div className="flex items-center justify-between">
                  <button
                    onClick={() => onSelectRun(run.run_id)}
                    className="font-mono text-xs font-semibold text-stone-900 dark:text-slate-100 hover:text-violet-600 dark:hover:text-violet-400 truncate max-w-[170px]"
                    title={run.run_id}
                  >
                    {run.run_id}
                  </button>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 font-medium">
                    Gate
                  </span>
                </div>

                {/* Reason description */}
                <div className="text-[11px] text-stone-700 dark:text-slate-300 bg-[#F5F4EE] dark:bg-slate-900/80 p-2.5 rounded-lg border border-[#E8E6DF] dark:border-slate-700 space-y-1">
                  <div className="flex items-center space-x-1.5 text-amber-800 dark:text-amber-300 font-medium">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                    <span>Action Requires Approval</span>
                  </div>
                  <p className="text-stone-500 dark:text-slate-400 text-[10px]">
                    Dataset: <span className="text-stone-700 dark:text-slate-300 font-medium">{run.dataset_path.split(/[\\/]/).pop()}</span>
                  </p>
                </div>

                {/* Error Banner */}
                {error && (
                  <div
                    data-testid="approval-error-banner"
                    className="p-2 rounded-lg bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-300 text-[11px] flex items-start space-x-1.5"
                  >
                    <AlertCircle className="w-4 h-4 text-rose-600 dark:text-rose-400 flex-shrink-0 mt-0.5" />
                    <span>{error.message}</span>
                  </div>
                )}

                {/* Success Banner */}
                {success && (
                  <div className="p-2 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 text-[11px] flex items-center space-x-1.5">
                    <CheckCircle className="w-4 h-4 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
                    <span>{success}</span>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="space-y-2 pt-1">
                  {!isModifying ? (
                    <div className="grid grid-cols-3 gap-1.5">
                      <button
                        onClick={() => handleDecision(run.run_id, 'approved')}
                        disabled={isSubmitting}
                        className="flex items-center justify-center space-x-1 py-1.5 px-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-medium shadow-xs transition disabled:opacity-50"
                      >
                        <CheckCircle className="w-3 h-3" />
                        <span>Approve</span>
                      </button>

                      <button
                        onClick={() => {
                          setModifyingRunId(run.run_id);
                          setModificationText('');
                        }}
                        disabled={isSubmitting}
                        className="flex items-center justify-center space-x-1 py-1.5 px-2 bg-stone-900 dark:bg-violet-600 hover:bg-stone-800 dark:hover:bg-violet-500 text-white rounded-lg text-xs font-medium shadow-xs transition disabled:opacity-50"
                      >
                        <Edit3 className="w-3 h-3" />
                        <span>Modify</span>
                      </button>

                      <button
                        onClick={() => handleDecision(run.run_id, 'reject')}
                        disabled={isSubmitting}
                        className="flex items-center justify-center space-x-1 py-1.5 px-2 bg-rose-50 dark:bg-rose-950/40 hover:bg-rose-100 dark:hover:bg-rose-900/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800/60 rounded-lg text-xs font-medium shadow-xs transition disabled:opacity-50"
                      >
                        <XCircle className="w-3 h-3" />
                        <span>Reject</span>
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2 pt-1">
                      <textarea
                        data-testid="modification-input"
                        placeholder="Provide specific modification instructions (e.g. keep missing columns, use standard scaling)..."
                        value={modificationText}
                        onChange={(e) => setModificationText(e.target.value)}
                        rows={3}
                        className="w-full bg-white dark:bg-slate-900 border border-stone-300 dark:border-slate-700 text-stone-800 dark:text-slate-100 text-xs p-2 rounded-lg focus:outline-none focus:border-stone-500 dark:focus:border-violet-400"
                      />
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleDecision(run.run_id, 'modify', modificationText)}
                          disabled={isSubmitting || !modificationText.trim()}
                          className="flex-1 py-1.5 px-2 bg-stone-900 dark:bg-violet-600 hover:bg-stone-800 dark:hover:bg-violet-500 text-white rounded-lg text-xs font-medium transition disabled:opacity-50"
                        >
                          Submit Modification
                        </button>
                        <button
                          onClick={() => setModifyingRunId(null)}
                          className="py-1.5 px-2 bg-stone-100 dark:bg-slate-700 hover:bg-stone-200 dark:hover:bg-slate-600 text-stone-700 dark:text-slate-200 rounded-lg text-xs font-medium transition"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};

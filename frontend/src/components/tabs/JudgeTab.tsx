import React from 'react';
import { Gavel, CheckCircle2, XCircle, AlertTriangle, MessageSquare, History } from 'lucide-react';
import { PipelineEvent } from '../../types/event';

interface JudgeTabProps {
  events: PipelineEvent[];
}

interface JudgeVerdictHistory {
  verdict: 'accept' | 'reject' | string;
  feedback?: string;
  reasoning?: string;
  retryTier?: number;
  rejectedFamily?: string;
  timestamp: string;
}

export const JudgeTab: React.FC<JudgeTabProps> = ({ events }) => {
  // Extract judge events from event list
  const verdicts: JudgeVerdictHistory[] = [];

  for (const ev of events) {
    if (ev.agent === 'judge_agent') {
      const v = ev.decision || (ev.verdict as string);
      if (v) {
        verdicts.push({
          verdict: v.toLowerCase(),
          feedback: ev.feedback || ev.judge_feedback || ev.reason,
          reasoning: ev.reasoning || ev.intent,
          retryTier: ev.retry_tier ?? ev.tier,
          rejectedFamily: ev.rejected_family || (ev as any).rejected_family,
          timestamp: ev.ts || '',
        });
      }
    }
  }

  const latestVerdict = verdicts.length > 0 ? verdicts[verdicts.length - 1] : null;

  return (
    <div className="p-5 space-y-6 overflow-y-auto max-h-full bg-[#FAF9F5] dark:bg-[#090D16] min-h-full text-stone-900 dark:text-slate-100 transition-colors">
      <div>
        <h3 className="text-sm font-semibold text-stone-900 dark:text-slate-100">Judge Agent Evaluation &amp; Verdict</h3>
        <p className="text-xs text-stone-500 dark:text-slate-400">
          Executive quality verification of candidate models, safety backstops, and iteration decisions.
        </p>
      </div>

      {!latestVerdict ? (
        <div className="p-8 text-center bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl shadow-xs">
          <Gavel className="w-8 h-8 text-stone-300 dark:text-slate-600 mx-auto mb-2" />
          <p className="text-xs text-stone-500 dark:text-slate-400">The Judge agent has not evaluated this run yet.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Latest Verdict Card */}
          <div
            className={`p-5 rounded-xl border shadow-xs ${
              latestVerdict.verdict === 'accept'
                ? 'bg-emerald-50/40 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800'
                : 'bg-rose-50/40 dark:bg-rose-950/20 border-rose-200 dark:border-rose-900'
            }`}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-3">
                {latestVerdict.verdict === 'accept' ? (
                  <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                    <CheckCircle2 className="w-5 h-5" />
                  </div>
                ) : (
                  <div className="p-2 rounded-lg bg-rose-100 dark:bg-rose-900/60 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
                    <XCircle className="w-5 h-5" />
                  </div>
                )}
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-mono uppercase text-stone-500 dark:text-slate-400">Latest Verdict</span>
                    <span
                      className={`text-xs font-bold font-mono uppercase px-2 py-0.5 rounded-full border ${
                        latestVerdict.verdict === 'accept'
                          ? 'bg-emerald-100 dark:bg-emerald-950/60 border-emerald-300 dark:border-emerald-700 text-emerald-800 dark:text-emerald-300'
                          : 'bg-rose-100 dark:bg-rose-950/60 border-rose-300 dark:border-rose-700 text-rose-800 dark:text-rose-300'
                      }`}
                    >
                      {latestVerdict.verdict}
                    </span>
                  </div>
                  <h4 className="text-sm font-semibold text-stone-900 dark:text-slate-100 mt-0.5">
                    {latestVerdict.verdict === 'accept'
                      ? 'Model Performance Approved for Final Reporting'
                      : 'Candidate Performance Insufficient — Iteration Required'}
                  </h4>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row items-end sm:items-center space-y-1 sm:space-y-0 sm:space-x-3 text-right font-mono text-xs">
                {latestVerdict.rejectedFamily && (
                  <div className="text-stone-500 dark:text-slate-400">
                    <span>Rejected: </span>
                    <span className="text-rose-700 dark:text-rose-300 font-bold bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 px-2 py-0.5 rounded-full">
                      {latestVerdict.rejectedFamily}
                    </span>
                  </div>
                )}
                {latestVerdict.retryTier !== undefined && (
                  <div className="text-stone-500 dark:text-slate-400">
                    <span>Target Retry: </span>
                    <span className="text-violet-700 dark:text-violet-300 font-bold">Tier {latestVerdict.retryTier}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Feedback prose */}
            <div className="space-y-2 bg-white dark:bg-slate-900 p-4 rounded-lg border border-[#E8E6DF] dark:border-slate-800 shadow-xs">
              <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-stone-600 dark:text-slate-300">
                <MessageSquare className="w-3.5 h-3.5 text-violet-600 dark:text-violet-400" />
                <span>Executive Reasoning &amp; Feedback</span>
              </div>
              <p className="text-xs text-stone-800 dark:text-slate-200 leading-relaxed whitespace-pre-wrap">
                {latestVerdict.feedback ||
                  latestVerdict.reasoning ||
                  'No detailed feedback was attached to this verdict.'}
              </p>
            </div>
          </div>

          {/* Historical Verdicts List */}
          {verdicts.length > 1 && (
            <div className="space-y-3">
              <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-stone-500 dark:text-slate-400">
                <History className="w-3.5 h-3.5 text-stone-400 dark:text-slate-500" />
                <span>Evaluation History ({verdicts.length} rounds)</span>
              </div>

              <div className="space-y-2">
                {verdicts.map((v, idx) => (
                  <div
                    key={`v_${idx}`}
                    className="p-3 bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-lg flex items-center justify-between text-xs shadow-xs transition-colors"
                  >
                    <div className="flex items-center space-x-3">
                      <span className="font-mono text-stone-400 dark:text-slate-500">Round {idx + 1}</span>
                      <span
                        className={`font-mono uppercase font-bold text-[10px] px-2 py-0.5 rounded-full border ${
                          v.verdict === 'accept'
                            ? 'bg-emerald-50 dark:bg-emerald-950/60 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'
                            : 'bg-rose-50 dark:bg-rose-950/60 border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300'
                        }`}
                      >
                        {v.verdict}
                      </span>
                      {v.rejectedFamily && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-300 font-medium">
                          Rejected: {v.rejectedFamily}
                        </span>
                      )}
                      <span className="text-stone-700 dark:text-slate-300 truncate max-w-lg">
                        {v.feedback || v.reasoning || 'Round evaluated.'}
                      </span>
                    </div>
                    <span className="font-mono text-[10px] text-stone-400 dark:text-slate-500">
                      {v.timestamp.slice(11, 19)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

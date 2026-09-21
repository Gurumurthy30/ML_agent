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
          timestamp: ev.ts || '',
        });
      }
    }
  }

  const latestVerdict = verdicts.length > 0 ? verdicts[verdicts.length - 1] : null;

  return (
    <div className="p-5 space-y-6 overflow-y-auto max-h-full">
      <div>
        <h3 className="text-sm font-semibold text-slate-200">Judge Agent Evaluation & Verdict</h3>
        <p className="text-xs text-slate-400">
          Executive quality verification of candidate models, safety backstops, and iteration decisions.
        </p>
      </div>

      {!latestVerdict ? (
        <div className="p-8 text-center bg-slate-950/40 border border-slate-800 rounded-xl">
          <Gavel className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
          <p className="text-xs text-slate-400">The Judge agent has not evaluated this run yet.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Latest Verdict Card */}
          <div
            className={`p-5 rounded-xl border ${
              latestVerdict.verdict === 'accept'
                ? 'bg-emerald-950/40 border-emerald-500/40'
                : 'bg-rose-950/40 border-rose-500/40'
            }`}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-3">
                {latestVerdict.verdict === 'accept' ? (
                  <div className="p-2 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                ) : (
                  <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/30">
                    <XCircle className="w-6 h-6" />
                  </div>
                )}
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-mono uppercase text-slate-400">Latest Verdict</span>
                    <span
                      className={`text-xs font-bold font-mono uppercase px-2 py-0.5 rounded border ${
                        latestVerdict.verdict === 'accept'
                          ? 'bg-emerald-900/60 border-emerald-500/50 text-emerald-200'
                          : 'bg-rose-900/60 border-rose-500/50 text-rose-200'
                      }`}
                    >
                      {latestVerdict.verdict}
                    </span>
                  </div>
                  <h4 className="text-sm font-semibold text-slate-100 mt-0.5">
                    {latestVerdict.verdict === 'accept'
                      ? 'Model Performance Approved for Final Reporting'
                      : 'Candidate Performance Insufficient — Iteration Required'}
                  </h4>
                </div>
              </div>

              {latestVerdict.retryTier !== undefined && (
                <div className="text-right font-mono text-xs text-slate-400">
                  <span>Target Retry Tier: </span>
                  <span className="text-indigo-300 font-bold">Tier {latestVerdict.retryTier}</span>
                </div>
              )}
            </div>

            {/* Feedback prose */}
            <div className="space-y-2 bg-slate-900/80 p-4 rounded-lg border border-slate-800">
              <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-slate-300">
                <MessageSquare className="w-3.5 h-3.5 text-indigo-400" />
                <span>Executive Reasoning & Feedback</span>
              </div>
              <p className="text-xs text-slate-200 leading-relaxed">
                {latestVerdict.feedback ||
                  latestVerdict.reasoning ||
                  'No detailed feedback was attached to this verdict.'}
              </p>
            </div>
          </div>

          {/* Historical Verdicts List */}
          {verdicts.length > 1 && (
            <div className="space-y-3">
              <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                <History className="w-3.5 h-3.5" />
                <span>Evaluation History ({verdicts.length} rounds)</span>
              </div>

              <div className="space-y-2">
                {verdicts.map((v, idx) => (
                  <div
                    key={`v_${idx}`}
                    className="p-3 bg-slate-900/50 border border-slate-800 rounded-lg flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center space-x-3">
                      <span className="font-mono text-slate-400">Round {idx + 1}</span>
                      <span
                        className={`font-mono uppercase font-bold text-[10px] px-1.5 py-0.5 rounded border ${
                          v.verdict === 'accept'
                            ? 'bg-emerald-950/70 border-emerald-500/40 text-emerald-300'
                            : 'bg-rose-950/70 border-rose-500/40 text-rose-300'
                        }`}
                      >
                        {v.verdict}
                      </span>
                      <span className="text-slate-300 truncate max-w-lg">
                        {v.feedback || v.reasoning || 'Round evaluated.'}
                      </span>
                    </div>
                    <span className="font-mono text-[10px] text-slate-400">
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

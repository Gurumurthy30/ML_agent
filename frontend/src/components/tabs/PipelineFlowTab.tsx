import React from 'react';
import { ArrowRight, CheckCircle2, RefreshCw, AlertTriangle, ShieldCheck, Flame } from 'lucide-react';
import { PipelineEvent } from '../../types/event';

interface PipelineFlowTabProps {
  events: PipelineEvent[];
  isLive: boolean;
  status: string;
}

interface StepNode {
  id: string;
  agent: string;
  phase?: string;
  retryNumber?: number;
  status: 'completed' | 'active' | 'pending' | 'rejected';
  summary: string;
  timestamp: string;
  durationMs?: number;
}

export const PipelineFlowTab: React.FC<PipelineFlowTabProps> = ({ events, isLive, status }) => {
  // Aggregate executed nodes from event sequence
  const steps: StepNode[] = [];
  const agentVisitCount: Record<string, number> = {};

  for (const ev of events) {
    const agent = ev.agent;
    if (!agent || agent === 'system') continue;

    // Track when an agent finishes or starts a primary step
    const isStepEnd = ev.event_type === 'step_end' || ev.event === 'step_end';
    const isJudgeVerdict = (ev.event_type === 'verdict' || ev.event === 'verdict' || ev.decision !== undefined || (ev as any).verdict !== undefined) && ev.agent === 'judge_agent';
    const isHumanApproval = ev.agent === 'human_approval';

    if (isStepEnd || isJudgeVerdict || isHumanApproval) {
      agentVisitCount[agent] = (agentVisitCount[agent] || 0) + 1;
      const count = agentVisitCount[agent];

      const decisionVal = ev.decision ?? (ev as any).verdict;
      let nodeStatus: StepNode['status'] = 'completed';
      if (decisionVal === 'reject' || decisionVal === 'rejected') {
        nodeStatus = 'rejected';
      }

      const summaryText =
        ev.reason ||
        ev.feedback ||
        (ev as any).judge_feedback ||
        ev.task_spec ||
        ev.step ||
        ev.intent ||
        decisionVal ||
        'Completed step execution';

      steps.push({
        id: `${agent}_${ev.seq || steps.length}`,
        agent,
        phase: ev.phase,
        retryNumber: count > 1 ? count - 1 : undefined,
        status: nodeStatus,
        summary: summaryText,
        timestamp: ev.ts || '',
        durationMs: ev.duration_ms,
      });
    }
  }

  // If running and live, mark last step or active step
  const activeAgent = events.length > 0 ? events[events.length - 1].agent : null;

  return (
    <div className="p-5 space-y-6 overflow-y-auto max-h-full bg-[#FAF9F5] dark:bg-[#090D16] min-h-full text-stone-900 dark:text-slate-100 transition-colors">
      {/* Top Description */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-stone-900 dark:text-slate-100">Executed Pipeline Sequence</h3>
          <p className="text-xs text-stone-500 dark:text-slate-400">
            Real-time executed agent sequence with explicit retry cycles and decision branches.
          </p>
        </div>
        {status === 'running' && (
          <div className="flex items-center space-x-2 bg-violet-50 dark:bg-violet-950/60 border border-violet-200 dark:border-violet-800 px-3 py-1 rounded-full text-xs font-mono text-violet-700 dark:text-violet-300">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            <span>Active: {activeAgent || 'graph_executing'}</span>
          </div>
        )}
      </div>

      {/* Horizontal / Wrapped Flow Nodes (The Flowchart Box) */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl shadow-xs transition-colors">
        {steps.length === 0 ? (
          <div className="p-4 text-xs text-stone-400 dark:text-slate-500">No executed pipeline steps recorded yet.</div>
        ) : (
          steps.map((node, index) => {
            const isLast = index === steps.length - 1;
            const isRejected = node.status === 'rejected';

            return (
              <React.Fragment key={node.id}>
                <div
                  className={`p-3 rounded-xl border flex flex-col space-y-1.5 transition min-w-[140px] max-w-[180px] shadow-xs ${
                    isRejected
                      ? 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-900/60 text-rose-800 dark:text-rose-200'
                      : isLast && status === 'running'
                      ? 'bg-violet-50/70 dark:bg-violet-950/40 border-violet-300 dark:border-violet-700 text-violet-900 dark:text-violet-200 animate-pulse'
                      : 'bg-white dark:bg-slate-950 border-[#E8E6DF] dark:border-slate-800 text-stone-800 dark:text-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold uppercase tracking-wider text-stone-800 dark:text-slate-100">
                      {node.agent.replace('_agent', '')}
                    </span>
                    {node.retryNumber !== undefined && (
                      <span className="px-1.5 py-0.5 rounded-full bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 font-mono text-[9px] font-semibold">
                        R{node.retryNumber}
                      </span>
                    )}
                  </div>

                  <p className="text-[11px] text-stone-500 dark:text-slate-400 line-clamp-2" title={node.summary}>
                    {node.summary}
                  </p>

                  <div className="flex items-center justify-between text-[10px] text-stone-400 dark:text-slate-500 pt-1 border-t border-stone-100 dark:border-slate-800 font-mono">
                    <span>
                      {node.durationMs ? `${(node.durationMs / 1000).toFixed(1)}s` : 'done'}
                    </span>
                    {isRejected ? (
                      <span className="text-rose-600 dark:text-rose-400 font-semibold">REJECT</span>
                    ) : (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                    )}
                  </div>
                </div>

                {!isLast && <ArrowRight className="w-4 h-4 text-stone-400 dark:text-slate-600 flex-shrink-0" />}
              </React.Fragment>
            );
          })
        )}
      </div>

      {/* Execution Timeline Detail List */}
      <div className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-stone-500 dark:text-slate-400">
          Step-by-Step Ledger
        </h4>
        <div className="space-y-2">
          {steps.map((node, i) => (
            <div
              key={`detail_${node.id}_${i}`}
              className="p-3 bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl flex items-center justify-between text-xs shadow-xs transition-colors"
            >
              <div className="flex items-center space-x-3">
                <span className="font-mono text-stone-400 dark:text-slate-500 text-[11px] w-6">#{i + 1}</span>
                <span className="font-mono font-semibold text-stone-900 dark:text-slate-100">
                  {node.agent}
                </span>
                {node.retryNumber !== undefined && (
                  <span className="text-[10px] px-2 py-0.5 bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 rounded-full font-mono font-medium">
                    Iteration {node.retryNumber + 1}
                  </span>
                )}
                <span className="text-stone-600 dark:text-slate-300 truncate max-w-md">{node.summary}</span>
              </div>
              <div className="flex items-center space-x-3 font-mono text-[11px] text-stone-500 dark:text-slate-400">
                {node.durationMs && <span>{(node.durationMs / 1000).toFixed(2)}s</span>}
                <span className="text-[10px] text-stone-400 dark:text-slate-500">{node.timestamp.slice(11, 19)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

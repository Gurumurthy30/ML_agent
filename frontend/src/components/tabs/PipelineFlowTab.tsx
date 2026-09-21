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
    const isDecision = ev.decision !== undefined && ev.agent === 'judge_agent';
    const isHumanApproval = ev.agent === 'human_approval';

    if (isStepEnd || isDecision || isHumanApproval) {
      agentVisitCount[agent] = (agentVisitCount[agent] || 0) + 1;
      const count = agentVisitCount[agent];

      let nodeStatus: StepNode['status'] = 'completed';
      if (ev.decision === 'reject') {
        nodeStatus = 'rejected';
      }

      steps.push({
        id: `${agent}_${ev.seq || steps.length}`,
        agent,
        phase: ev.phase,
        retryNumber: count > 1 ? count - 1 : undefined,
        status: nodeStatus,
        summary: ev.reason || ev.intent || ev.decision || 'Completed step execution',
        timestamp: ev.ts || '',
        durationMs: ev.duration_ms,
      });
    }
  }

  // If running and live, mark last step or active step
  const activeAgent = events.length > 0 ? events[events.length - 1].agent : null;

  return (
    <div className="p-5 space-y-6 overflow-y-auto max-h-full">
      {/* Top Description */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Executed Pipeline Sequence</h3>
          <p className="text-xs text-slate-400">
            Real-time executed agent sequence with explicit retry cycles and decision branches.
          </p>
        </div>
        {status === 'running' && (
          <div className="flex items-center space-x-2 bg-cyan-950/60 border border-cyan-500/40 px-3 py-1 rounded text-xs font-mono text-cyan-300">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            <span>Active: {activeAgent || 'graph_executing'}</span>
          </div>
        )}
      </div>

      {/* Horizontal / Wrapped Flow Nodes */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-slate-950/60 border border-slate-800 rounded-xl">
        {steps.length === 0 ? (
          <div className="p-4 text-xs text-slate-400">No executed pipeline steps recorded yet.</div>
        ) : (
          steps.map((node, index) => {
            const isLast = index === steps.length - 1;
            const isRejected = node.status === 'rejected';

            return (
              <React.Fragment key={node.id}>
                <div
                  className={`p-3 rounded-lg border flex flex-col space-y-1.5 transition min-w-[140px] max-w-[180px] ${
                    isRejected
                      ? 'bg-rose-950/60 border-rose-500/50 text-rose-200'
                      : isLast && status === 'running'
                      ? 'bg-cyan-950/60 border-cyan-500/60 text-cyan-200 shadow-md shadow-cyan-950/40 animate-pulse'
                      : 'bg-slate-900/80 border-slate-700/70 text-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-bold uppercase tracking-wider text-slate-300">
                      {node.agent.replace('_agent', '')}
                    </span>
                    {node.retryNumber !== undefined && (
                      <span className="px-1.5 py-0.5 rounded bg-amber-950/80 border border-amber-500/50 text-amber-300 font-mono text-[9px] font-semibold">
                        Retry {node.retryNumber}
                      </span>
                    )}
                  </div>

                  <p className="text-[11px] text-slate-400 line-clamp-2" title={node.summary}>
                    {node.summary}
                  </p>

                  <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-slate-800 font-mono">
                    <span>
                      {node.durationMs ? `${(node.durationMs / 1000).toFixed(1)}s` : 'done'}
                    </span>
                    {isRejected ? (
                      <span className="text-rose-400 font-semibold">REJECT</span>
                    ) : (
                      <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    )}
                  </div>
                </div>

                {!isLast && <ArrowRight className="w-4 h-4 text-slate-400 flex-shrink-0" />}
              </React.Fragment>
            );
          })
        )}
      </div>

      {/* Execution Timeline Detail List */}
      <div className="space-y-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Step-by-Step Ledger
        </h4>
        <div className="space-y-2">
          {steps.map((node, i) => (
            <div
              key={`detail_${node.id}_${i}`}
              className="p-3 bg-slate-900/50 border border-slate-800 rounded-lg flex items-center justify-between text-xs"
            >
              <div className="flex items-center space-x-3">
                <span className="font-mono text-slate-400 text-[11px] w-6">#{i + 1}</span>
                <span className="font-mono font-semibold text-slate-200">
                  {node.agent}
                </span>
                {node.retryNumber !== undefined && (
                  <span className="text-[10px] px-2 py-0.5 bg-amber-950/60 border border-amber-500/40 text-amber-300 rounded font-mono">
                    Loop Iteration {node.retryNumber + 1}
                  </span>
                )}
                <span className="text-slate-400 truncate max-w-md">{node.summary}</span>
              </div>
              <div className="flex items-center space-x-3 font-mono text-[11px] text-slate-400">
                {node.durationMs && <span>{(node.durationMs / 1000).toFixed(2)}s</span>}
                <span className="text-[10px]">{node.timestamp.slice(11, 19)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

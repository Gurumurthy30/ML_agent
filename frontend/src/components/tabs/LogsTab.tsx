import React, { useState } from 'react';
import { Terminal, ChevronRight, ChevronDown, Search, Filter, Bug, Code, AlertCircle } from 'lucide-react';
import { PipelineEvent } from '../../types/event';

interface LogsTabProps {
  events: PipelineEvent[];
}

interface GroupedTurn {
  id: string;
  turnKey: string;
  parentAgent: string;
  iteration?: number;
  events: PipelineEvent[];
  startTime: string;
  hasErrors: boolean;
}

export const LogsTab: React.FC<LogsTabProps> = ({ events }) => {
  const [filterText, setFilterText] = useState('');
  const [selectedAgent, setSelectedAgent] = useState<string>('all');
  const [expandedTurns, setExpandedTurns] = useState<Record<string, boolean>>({});

  // Group events by parent_agent & iteration (or agent itself for top-level turns)
  const turns: GroupedTurn[] = [];
  let currentTurn: GroupedTurn | null = null;

  for (const ev of events) {
    const parent = ev.parent_agent || ev.agent;
    const iter = ev.parent_iteration || ev.iteration;
    const turnKey = `${parent}_${iter ?? 'main'}`;

    if (!currentTurn || currentTurn.turnKey !== turnKey) {
      if (currentTurn) turns.push(currentTurn);
      currentTurn = {
        id: `${turnKey}_${turns.length}`,
        turnKey,
        parentAgent: parent,
        iteration: iter,
        events: [ev],
        startTime: ev.ts || '',
        hasErrors: Boolean(ev.error || ev.stderr),
      };
    } else {
      currentTurn.events.push(ev);
      if (ev.error || ev.stderr) {
        currentTurn.hasErrors = true;
      }
    }
  }
  if (currentTurn) turns.push(currentTurn);

  const toggleTurn = (turnId: string) => {
    setExpandedTurns((prev) => ({
      ...prev,
      [turnId]: !prev[turnId],
    }));
  };

  const filteredTurns = turns.filter((turn) => {
    if (selectedAgent !== 'all' && turn.parentAgent !== selectedAgent) return false;
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      const matchParent = turn.parentAgent.toLowerCase().includes(q);
      const matchChild = turn.events.some((e) =>
        (e.event_type || e.intent || e.reason || e.error || '').toLowerCase().includes(q)
      );
      if (!matchParent && !matchChild) return false;
    }
    return true;
  });

  const uniqueAgents = Array.from(new Set(events.map((e) => e.parent_agent || e.agent).filter(Boolean)));

  return (
    <div className="p-5 space-y-4 overflow-y-auto max-h-full">
      {/* Header and Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">Hierarchical Event & Execution Logs</h3>
          <p className="text-xs text-slate-400">
            Coder sub-steps and tool operations nested beneath the invoking agent turn.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-slate-400" />
            <input
              type="text"
              placeholder="Search logs..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              className="bg-slate-950 text-slate-200 pl-8 pr-3 py-1 text-xs rounded border border-slate-800 focus:outline-none focus:border-indigo-500 w-44"
            />
          </div>

          {/* Agent Filter */}
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            className="bg-slate-950 text-slate-300 py-1 px-2 text-xs rounded border border-slate-800 focus:outline-none font-mono"
          >
            <option value="all">All Agents</option>
            {uniqueAgents.map((ag) => (
              <option key={ag} value={ag}>
                {ag}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Logs Tree */}
      {filteredTurns.length === 0 ? (
        <div className="p-10 text-center bg-slate-950/40 border border-slate-800 rounded-xl">
          <Terminal className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
          <p className="text-xs text-slate-400">No events found matching the filter criteria.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredTurns.map((turn) => {
            const isExpanded = expandedTurns[turn.id] ?? true; // expanded by default

            return (
              <div
                key={turn.id}
                className="bg-slate-950/60 border border-slate-800 rounded-lg overflow-hidden transition"
              >
                {/* Parent Agent Turn Header */}
                <div
                  onClick={() => toggleTurn(turn.id)}
                  className="p-2.5 bg-slate-900/80 hover:bg-slate-850/80 cursor-pointer flex items-center justify-between border-b border-slate-800/80 text-xs select-none"
                >
                  <div className="flex items-center space-x-2">
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                    <span className="font-mono font-bold text-indigo-400">
                      {turn.parentAgent}
                    </span>
                    {turn.iteration !== undefined && (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 font-mono">
                        Iter {turn.iteration}
                      </span>
                    )}
                    <span className="text-slate-400 text-[11px]">
                      ({turn.events.length} {turn.events.length === 1 ? 'event' : 'events'})
                    </span>
                    {turn.hasErrors && (
                      <span className="flex items-center space-x-1 text-[10px] text-rose-400 bg-rose-950/60 border border-rose-500/40 px-1.5 py-0.2 rounded font-mono">
                        <AlertCircle className="w-2.5 h-2.5" />
                        <span>Has Error</span>
                      </span>
                    )}
                  </div>

                  <span className="font-mono text-[10px] text-slate-400">
                    {turn.startTime.slice(11, 19)}
                  </span>
                </div>

                {/* Nested Sub-Events */}
                {isExpanded && (
                  <div className="p-2 space-y-1.5 pl-6 bg-slate-950/40 divide-y divide-slate-850/40">
                    {turn.events.map((ev, eIdx) => {
                      const isCoder = ev.agent === 'coder_agent';
                      const hasErr = Boolean(ev.error || ev.stderr);

                      return (
                        <div
                          key={`ev_${ev.seq || eIdx}`}
                          className="pt-1.5 first:pt-0 font-mono text-[11px] space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center space-x-2">
                              <span className="text-slate-400 w-6">#{ev.seq ?? eIdx}</span>
                              <span
                                className={`font-semibold ${
                                  isCoder ? 'text-amber-400' : 'text-slate-300'
                                }`}
                              >
                                {ev.agent}
                              </span>
                              <span className="text-slate-400 font-mono text-[10px] uppercase px-1 rounded bg-slate-900 border border-slate-800">
                                {ev.event_type || ev.event || 'event'}
                              </span>
                              {ev.attempt && (
                                <span className="text-slate-400 text-[10px]">
                                  (Attempt {ev.attempt})
                                </span>
                              )}
                            </div>
                            <span className="text-slate-400 text-[10px]">
                              {ev.ts ? ev.ts.slice(11, 19) : ''}
                            </span>
                          </div>

                          {/* Message / summary */}
                          {(ev.reason || ev.intent || ev.decision) && (
                            <p className="text-slate-300 pl-8 text-xs font-sans">
                              {ev.reason || ev.intent || `Decision: ${ev.decision}`}
                            </p>
                          )}

                          {/* Error Callout */}
                          {hasErr && (
                            <div className="ml-8 p-2 rounded bg-rose-950/50 border border-rose-500/40 text-rose-300 text-[10px] overflow-x-auto whitespace-pre-wrap">
                              {ev.error || ev.stderr}
                            </div>
                          )}

                          {/* Code Preview if present */}
                          {ev.code && (
                            <div className="ml-8 p-2 rounded bg-slate-900 border border-slate-800 text-slate-300 text-[10px] overflow-x-auto max-h-32">
                              <code>{ev.code}</code>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

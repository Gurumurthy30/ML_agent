import React, { useState, useMemo } from 'react';
import {
  Terminal,
  ChevronRight,
  ChevronDown,
  Search,
  Filter,
  Bug,
  Code,
  AlertCircle,
  Copy,
  Check,
  BookOpen,
  ListTree,
  FileText,
  Gavel,
  Cpu,
  Sparkles,
  Maximize2,
  Minimize2,
} from 'lucide-react';
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

interface ModelTextItem {
  id: string;
  seq: number;
  ts: string;
  agent: string;
  category: 'code' | 'judge_feedback' | 'decision' | 'report' | 'plan' | 'eda' | 'output';
  categoryLabel: string;
  title: string;
  text: string;
  metadata?: string;
  iteration?: number;
  hasError?: boolean;
}

export const LogsTab: React.FC<LogsTabProps> = ({ events }) => {
  const [viewMode, setViewMode] = useState<'hierarchy' | 'reader'>('hierarchy');
  const [filterText, setFilterText] = useState('');
  const [selectedAgent, setSelectedAgent] = useState<string>('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [expandedTurns, setExpandedTurns] = useState<Record<string, boolean>>({});
  const [expandedModelItems, setExpandedModelItems] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Copy to clipboard helper
  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => {
      setCopiedId((curr) => (curr === id ? null : curr));
    }, 2000);
  };

  // Group events by parent_agent & iteration (or agent itself for top-level turns)
  const turns: GroupedTurn[] = useMemo(() => {
    const res: GroupedTurn[] = [];
    let currentTurn: GroupedTurn | null = null;

    for (const ev of events) {
      const parent = ev.parent_agent || ev.agent;
      const iter = ev.parent_iteration || ev.iteration;
      const turnKey = `${parent}_${iter ?? 'main'}`;

      if (!currentTurn || currentTurn.turnKey !== turnKey) {
        if (currentTurn) res.push(currentTurn);
        currentTurn = {
          id: `${turnKey}_${res.length}`,
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
    if (currentTurn) res.push(currentTurn);
    return res;
  }, [events]);

  // Extract all model text items for the Model Text Reader
  const modelTextItems: ModelTextItem[] = useMemo(() => {
    const items: ModelTextItem[] = [];

    events.forEach((ev, idx) => {
      const seq = ev.seq ?? idx + 1;
      const ts = ev.ts ? ev.ts.slice(11, 19) : '';
      const iter = ev.iteration ?? ev.parent_iteration;

      // 1. Full report text
      if (ev.report) {
        items.push({
          id: `report_${seq}`,
          seq,
          ts,
          agent: ev.agent || 'reporter_agent',
          category: 'report',
          categoryLabel: 'Final Report Markdown',
          title: 'Executive ML Report Written by Reporter Model',
          text: ev.report,
          iteration: iter,
        });
      }

      // 2. Generated Code
      if (ev.code) {
        items.push({
          id: `code_${seq}`,
          seq,
          ts,
          agent: ev.agent || 'coder_agent',
          category: 'code',
          categoryLabel: 'Generated Python Script',
          title: ev.intent || `Implementation Code (Attempt ${ev.attempt ?? 1})`,
          text: ev.code,
          metadata: ev.attempt ? `Attempt ${ev.attempt}` : undefined,
          iteration: iter,
          hasError: Boolean(ev.error || ev.stderr),
        });
      }

      // 3. Judge Feedback & Reasons
      const judgeText = ev.feedback || ev.judge_feedback;
      if (judgeText) {
        items.push({
          id: `judge_${seq}`,
          seq,
          ts,
          agent: ev.agent || 'judge_agent',
          category: 'judge_feedback',
          categoryLabel: 'Quality Verdict & Feedback',
          title: `Judge Evaluation (Decision: ${ev.decision || 'verdict'})`,
          text: `${judgeText}${ev.reason ? `\n\n[Reasoning]: ${ev.reason}` : ''}${ev.rejected_family ? `\n[Rejected Family]: ${ev.rejected_family}` : ''}`,
          iteration: iter,
        });
      } else if (ev.agent === 'judge_agent' && ev.reason) {
        items.push({
          id: `judge_reason_${seq}`,
          seq,
          ts,
          agent: 'judge_agent',
          category: 'judge_feedback',
          categoryLabel: 'Judge Rationale',
          title: `Judge Verdict (${ev.decision || 'evaluated'})`,
          text: ev.reason,
          iteration: iter,
        });
      }

      // 4. Modeler Hypothesis & Task Specification
      if (ev.task_spec) {
        items.push({
          id: `task_spec_${seq}`,
          seq,
          ts,
          agent: ev.agent || 'modeler_agent',
          category: 'decision',
          categoryLabel: 'Model Task Specification',
          title: ev.intent || `Model Exploration Strategy (${ev.model_family || 'spec'})`,
          text: ev.task_spec + (ev.reason ? `\n\n[Rationale]: ${ev.reason}` : ''),
          iteration: iter,
        });
      } else if ((ev.agent === 'modeler_agent' || ev.event_type === 'loop_decision') && (ev.reason || ev.intent)) {
        items.push({
          id: `modeler_reason_${seq}`,
          seq,
          ts,
          agent: ev.agent || 'modeler_agent',
          category: 'decision',
          categoryLabel: 'Modeler Hypothesis & Decision',
          title: `Loop Decision: ${ev.decision || 'advance'}`,
          text: [ev.intent, ev.reason].filter(Boolean).join('\n\n'),
          iteration: iter,
        });
      }

      // 5. Features Plan & Transformations
      if (ev.feature_plan?.description || ev.feature_plan?.code) {
        items.push({
          id: `feature_plan_${seq}`,
          seq,
          ts,
          agent: ev.agent || 'features_agent',
          category: 'plan',
          categoryLabel: 'Feature Engineering Plan',
          title: ev.feature_plan.description || 'Feature Transformation Proposal',
          text: `${ev.feature_plan.description || ''}${ev.feature_plan.code ? `\n\n[Code]:\n${ev.feature_plan.code}` : ''}`,
          iteration: iter,
        });
      }

      // 6. Operator modifications / instructions
      if (ev.modifications) {
        items.push({
          id: `mods_${seq}`,
          seq,
          ts,
          agent: ev.agent || 'supervisor',
          category: 'plan',
          categoryLabel: 'Operator Instructions',
          title: 'Acknowledged Human Operator Modifications',
          text: ev.modifications,
          iteration: iter,
        });
      }

      // 7. Execution Stdout or Stderr (if substantial)
      if (ev.stdout && ev.stdout.trim().length > 10) {
        items.push({
          id: `stdout_${seq}`,
          seq,
          ts,
          agent: ev.agent || 'coder_agent',
          category: 'output',
          categoryLabel: 'Execution Output (Stdout)',
          title: `Execution Log for Attempt ${ev.attempt ?? ''}`,
          text: ev.stdout,
          iteration: iter,
        });
      }
      if (ev.error || ev.stderr) {
        const errText = ev.error || ev.stderr || '';
        if (errText.trim().length > 0) {
          items.push({
            id: `stderr_${seq}`,
            seq,
            ts,
            agent: ev.agent || 'coder_agent',
            category: 'output',
            categoryLabel: 'Execution Error (Stderr)',
            title: `Failure Trace for Attempt ${ev.attempt ?? ''}`,
            text: errText,
            iteration: iter,
            hasError: true,
          });
        }
      }
    });

    return items;
  }, [events]);

  const toggleTurn = (turnId: string) => {
    setExpandedTurns((prev) => ({
      ...prev,
      [turnId]: !prev[turnId],
    }));
  };

  const toggleModelItem = (itemId: string) => {
    setExpandedModelItems((prev) => ({
      ...prev,
      [itemId]: !prev[itemId],
    }));
  };

  const expandAllModelItems = () => {
    const next: Record<string, boolean> = {};
    modelTextItems.forEach((it) => {
      next[it.id] = true;
    });
    setExpandedModelItems(next);
  };

  const collapseAllModelItems = () => {
    setExpandedModelItems({});
  };

  // Filter turns for hierarchy view
  const filteredTurns = turns.filter((turn) => {
    if (selectedAgent !== 'all' && turn.parentAgent !== selectedAgent) return false;
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      const matchParent = turn.parentAgent.toLowerCase().includes(q);
      const matchChild = turn.events.some((e) =>
        (e.event_type || e.intent || e.reason || e.error || e.code || e.task_spec || e.feedback || '').toLowerCase().includes(q)
      );
      if (!matchParent && !matchChild) return false;
    }
    return true;
  });

  // Filter model texts for reader view
  const filteredModelItems = modelTextItems.filter((item) => {
    if (selectedAgent !== 'all' && item.agent !== selectedAgent) return false;
    if (selectedCategory !== 'all' && item.category !== selectedCategory) return false;
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      const matchTitle = item.title.toLowerCase().includes(q);
      const matchText = item.text.toLowerCase().includes(q);
      const matchAgent = item.agent.toLowerCase().includes(q);
      if (!matchTitle && !matchText && !matchAgent) return false;
    }
    return true;
  });

  const uniqueAgents = Array.from(new Set(events.map((e) => e.parent_agent || e.agent).filter(Boolean)));

  const getAgentBadgeColor = (agent: string) => {
    switch (agent) {
      case 'modeler_agent':
        return 'bg-violet-50 dark:bg-violet-950/60 text-violet-700 dark:text-violet-300 border-violet-200 dark:border-violet-800';
      case 'coder_agent':
        return 'bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800';
      case 'judge_agent':
        return 'bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800';
      case 'reporter_agent':
        return 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800';
      case 'features_agent':
        return 'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800';
      case 'eda_agent':
        return 'bg-cyan-50 dark:bg-cyan-950/60 text-cyan-700 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800';
      default:
        return 'bg-stone-50 dark:bg-slate-800 text-stone-700 dark:text-slate-300 border-stone-200 dark:border-slate-700';
    }
  };

  return (
    <div className="p-5 space-y-4 overflow-y-auto max-h-full bg-[#FAF9F5] dark:bg-[#090D16] min-h-full text-stone-900 dark:text-slate-100 transition-colors">
      {/* Header and Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-[#E8E6DF] dark:border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <h3 className="text-sm font-semibold text-stone-900 dark:text-slate-100">
              Hierarchical Event &amp; Execution Logs
            </h3>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-stone-100 dark:bg-slate-800 text-stone-600 dark:text-slate-400 border border-stone-200 dark:border-slate-700">
              {events.length} events
            </span>
          </div>
          <p className="text-xs text-stone-500 dark:text-slate-400 mt-0.5">
            Coder sub-steps and tool operations nested beneath the invoking agent turn.
          </p>
        </div>

        {/* View Mode Toggle Pill */}
        <div className="flex items-center space-x-2">
          <div className="flex items-center bg-stone-100 dark:bg-slate-800 p-0.5 rounded-lg border border-stone-200 dark:border-slate-700">
            <button
              onClick={() => setViewMode('hierarchy')}
              className={`flex items-center space-x-1.5 px-3 py-1 text-xs font-medium rounded-md transition ${
                viewMode === 'hierarchy'
                  ? 'bg-white dark:bg-slate-900 text-stone-900 dark:text-slate-100 shadow-xs'
                  : 'text-stone-500 dark:text-slate-400 hover:text-stone-800 dark:hover:text-slate-200'
              }`}
            >
              <ListTree className="w-3.5 h-3.5" />
              <span>Event Tree</span>
            </button>
            <button
              onClick={() => setViewMode('reader')}
              className={`flex items-center space-x-1.5 px-3 py-1 text-xs font-medium rounded-md transition ${
                viewMode === 'reader'
                  ? 'bg-white dark:bg-slate-900 text-violet-700 dark:text-violet-300 font-semibold shadow-xs'
                  : 'text-stone-500 dark:text-slate-400 hover:text-stone-800 dark:hover:text-slate-200'
              }`}
            >
              <BookOpen className="w-3.5 h-3.5 text-violet-600 dark:text-violet-400" />
              <span>Model Text Reader</span>
              <span className="ml-1 text-[10px] px-1.5 py-0.2 rounded-full bg-violet-100 dark:bg-violet-950 text-violet-800 dark:text-violet-200 font-mono">
                {modelTextItems.length}
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-stone-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder={viewMode === 'reader' ? "Search model text, code, feedback..." : "Search logs..."}
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              className="bg-white dark:bg-slate-800 text-stone-800 dark:text-slate-100 placeholder-stone-400 dark:placeholder-slate-500 pl-8 pr-3 py-1.5 text-xs rounded-lg border border-[#E8E6DF] dark:border-slate-700 focus:outline-none focus:border-stone-400 dark:focus:border-slate-500 w-56 transition"
            />
          </div>

          {/* Agent Filter */}
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            className="bg-white dark:bg-slate-800 text-stone-700 dark:text-slate-200 py-1.5 px-2.5 text-xs rounded-lg border border-[#E8E6DF] dark:border-slate-700 focus:outline-none font-mono"
          >
            <option value="all">All Agents</option>
            {uniqueAgents.map((ag) => (
              <option key={ag} value={ag}>
                {ag}
              </option>
            ))}
          </select>

          {/* Category Filter for Reader Mode */}
          {viewMode === 'reader' && (
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="bg-white dark:bg-slate-800 text-stone-700 dark:text-slate-200 py-1.5 px-2.5 text-xs rounded-lg border border-[#E8E6DF] dark:border-slate-700 focus:outline-none font-mono"
            >
              <option value="all">All Content Types</option>
              <option value="decision">Hypotheses &amp; Task Specs</option>
              <option value="code">Generated Code</option>
              <option value="judge_feedback">Judge Feedback &amp; Verdicts</option>
              <option value="report">Executive Reports</option>
              <option value="plan">Feature Plans &amp; Ops</option>
              <option value="output">Exec Output &amp; Stderr</option>
            </select>
          )}
        </div>

        {/* Reader view batch expand controls */}
        {viewMode === 'reader' && (
          <div className="flex items-center space-x-1.5 text-xs">
            <button
              onClick={expandAllModelItems}
              className="px-2.5 py-1 text-stone-600 dark:text-slate-300 hover:bg-stone-200/60 dark:hover:bg-slate-800 rounded border border-stone-200 dark:border-slate-700 transition"
            >
              Expand All
            </button>
            <button
              onClick={collapseAllModelItems}
              className="px-2.5 py-1 text-stone-600 dark:text-slate-300 hover:bg-stone-200/60 dark:hover:bg-slate-800 rounded border border-stone-200 dark:border-slate-700 transition"
            >
              Collapse All
            </button>
          </div>
        )}
      </div>

      {/* VIEW 1: MODEL TEXT & OUTPUTS READER VIEW */}
      {viewMode === 'reader' && (
        <div className="space-y-3">
          {filteredModelItems.length === 0 ? (
            <div className="p-10 text-center bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl shadow-xs">
              <BookOpen className="w-8 h-8 text-stone-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-stone-500 dark:text-slate-400">
                No model texts found matching your filter criteria.
              </p>
            </div>
          ) : (
            filteredModelItems.map((item) => {
              const isExpanded = expandedModelItems[item.id] ?? true;
              const wordCount = item.text.trim().split(/\s+/).filter(Boolean).length;
              const charCount = item.text.length;
              const isCopied = copiedId === item.id;
              const isCode = item.category === 'code';

              return (
                <div
                  key={item.id}
                  className="bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl overflow-hidden shadow-xs transition"
                >
                  {/* Card Header */}
                  <div className="p-3 bg-white dark:bg-slate-900 hover:bg-[#FAF9F5] dark:hover:bg-slate-800/40 flex items-center justify-between border-b border-[#E8E6DF] dark:border-slate-800 text-xs">
                    <div
                      onClick={() => toggleModelItem(item.id)}
                      className="flex items-center space-x-2.5 cursor-pointer flex-1 min-w-0"
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-stone-400 dark:text-slate-500 flex-shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-stone-400 dark:text-slate-500 flex-shrink-0" />
                      )}

                      {/* Agent Badge */}
                      <span
                        className={`px-2 py-0.5 rounded-md font-mono text-[10px] font-semibold border ${getAgentBadgeColor(
                          item.agent
                        )}`}
                      >
                        {item.agent}
                      </span>

                      {/* Category Label */}
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-stone-100 dark:bg-slate-800 text-stone-600 dark:text-slate-300 border border-stone-200 dark:border-slate-700">
                        {item.categoryLabel}
                      </span>

                      {/* Title */}
                      <span className="font-semibold text-stone-800 dark:text-slate-200 truncate">
                        {item.title}
                      </span>

                      {item.iteration !== undefined && (
                        <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-stone-100 dark:bg-slate-800 text-stone-500 dark:text-slate-400 font-mono">
                          Iter {item.iteration}
                        </span>
                      )}
                    </div>

                    {/* Actions and Stats */}
                    <div className="flex items-center space-x-3 ml-2 flex-shrink-0">
                      <span className="text-[10px] text-stone-400 dark:text-slate-500 font-mono hidden sm:inline">
                        {wordCount} words &bull; {charCount} chars
                      </span>
                      <span className="font-mono text-[10px] text-stone-400 dark:text-slate-500">
                        {item.ts}
                      </span>

                      {/* Copy Button */}
                      <button
                        onClick={() => handleCopy(item.id, item.text)}
                        className="flex items-center space-x-1 px-2 py-1 text-[11px] font-medium rounded-md border border-stone-200 dark:border-slate-700 bg-stone-50 dark:bg-slate-800 text-stone-700 dark:text-slate-200 hover:bg-stone-100 dark:hover:bg-slate-700 transition"
                        title="Copy full text"
                      >
                        {isCopied ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                            <span className="text-emerald-600 dark:text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3 text-stone-500 dark:text-slate-400" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Card Body with Full Model Text */}
                  {isExpanded && (
                    <div className="p-4 bg-[#FAF9F5] dark:bg-[#090D16]">
                      {isCode ? (
                        <pre className="p-3.5 bg-white dark:bg-slate-950 border border-[#E8E6DF] dark:border-slate-800 rounded-lg text-[12px] font-mono leading-relaxed text-stone-800 dark:text-emerald-300 overflow-x-auto whitespace-pre max-h-[500px]">
                          <code>{item.text}</code>
                        </pre>
                      ) : item.category === 'report' ? (
                        <div className="p-4 bg-white dark:bg-slate-950 border border-[#E8E6DF] dark:border-slate-800 rounded-lg text-xs leading-relaxed text-stone-800 dark:text-slate-200 whitespace-pre-wrap font-sans max-h-[600px] overflow-y-auto">
                          {item.text}
                        </div>
                      ) : (
                        <div
                          className={`p-3.5 rounded-lg border leading-relaxed text-xs whitespace-pre-wrap ${
                            item.hasError
                              ? 'bg-rose-50 dark:bg-rose-950/40 border-rose-200 dark:border-rose-900/60 text-rose-900 dark:text-rose-200 font-mono text-[11px]'
                              : 'bg-white dark:bg-slate-950 border-[#E8E6DF] dark:border-slate-800 text-stone-800 dark:text-slate-200 font-sans'
                          }`}
                        >
                          {item.text}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* VIEW 2: HIERARCHICAL LOGS TREE VIEW */}
      {viewMode === 'hierarchy' && (
        <>
          {filteredTurns.length === 0 ? (
            <div className="p-10 text-center bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl shadow-xs">
              <Terminal className="w-8 h-8 text-stone-300 dark:text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-stone-500 dark:text-slate-400">
                No events found matching the filter criteria.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredTurns.map((turn) => {
                const isExpanded = expandedTurns[turn.id] ?? true; // expanded by default

                return (
                  <div
                    key={turn.id}
                    className="bg-white dark:bg-slate-900 border border-[#E8E6DF] dark:border-slate-800 rounded-xl overflow-hidden shadow-xs transition"
                  >
                    {/* Parent Agent Turn Header */}
                    <div
                      onClick={() => toggleTurn(turn.id)}
                      className="p-3 bg-white dark:bg-slate-900 hover:bg-[#FAF9F5] dark:hover:bg-slate-800/40 cursor-pointer flex items-center justify-between border-b border-[#E8E6DF] dark:border-slate-800 text-xs select-none"
                    >
                      <div className="flex items-center space-x-2">
                        {isExpanded ? (
                          <ChevronDown className="w-4 h-4 text-stone-400 dark:text-slate-500" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-stone-400 dark:text-slate-500" />
                        )}
                        <span className="font-mono font-bold text-stone-900 dark:text-slate-100">
                          {turn.parentAgent}
                        </span>
                        {turn.iteration !== undefined && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-stone-100 dark:bg-slate-800 text-stone-700 dark:text-slate-300 font-mono font-medium">
                            Iter {turn.iteration}
                          </span>
                        )}
                        <span className="text-stone-400 dark:text-slate-500 text-[11px]">
                          ({turn.events.length} {turn.events.length === 1 ? 'event' : 'events'})
                        </span>
                        {turn.hasErrors && (
                          <span className="flex items-center space-x-1 text-[10px] text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-900 px-2 py-0.5 rounded-full font-mono font-medium">
                            <AlertCircle className="w-2.5 h-2.5" />
                            <span>Has Error</span>
                          </span>
                        )}
                      </div>

                      <span className="font-mono text-[10px] text-stone-400 dark:text-slate-500">
                        {turn.startTime.slice(11, 19)}
                      </span>
                    </div>

                    {/* Nested Sub-Events */}
                    {isExpanded && (
                      <div className="p-3 space-y-2.5 pl-6 bg-[#FAF9F5] dark:bg-[#090D16] divide-y divide-[#E8E6DF]/60 dark:divide-slate-800/60">
                        {turn.events.map((ev, eIdx) => {
                          const isCoder = ev.agent === 'coder_agent';
                          const hasErr = Boolean(ev.error || ev.stderr);
                          const hasModelText = Boolean(
                            ev.task_spec || ev.feedback || ev.judge_feedback || ev.report || ev.code
                          );

                          return (
                            <div
                              key={`ev_${ev.seq || eIdx}`}
                              className="pt-2 first:pt-0 font-mono text-[11px] space-y-1.5"
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center space-x-2">
                                  <span className="text-stone-400 dark:text-slate-500 w-6">#{ev.seq ?? eIdx}</span>
                                  <span
                                    className={`font-semibold ${
                                      isCoder ? 'text-amber-700 dark:text-amber-400' : 'text-stone-800 dark:text-slate-200'
                                    }`}
                                  >
                                    {ev.agent}
                                  </span>
                                  <span className="text-stone-500 dark:text-slate-400 font-mono text-[10px] uppercase px-1.5 py-0.2 rounded bg-stone-100 dark:bg-slate-800 border border-stone-200 dark:border-slate-700">
                                    {ev.event_type || ev.event || 'event'}
                                  </span>
                                  {ev.attempt && (
                                    <span className="text-stone-400 dark:text-slate-500 text-[10px]">
                                      (Attempt {ev.attempt})
                                    </span>
                                  )}
                                  {hasModelText && (
                                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-violet-100 dark:bg-violet-950/60 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-800">
                                      Model Text
                                    </span>
                                  )}
                                </div>
                                <span className="text-stone-400 dark:text-slate-500 text-[10px]">
                                  {ev.ts ? ev.ts.slice(11, 19) : ''}
                                </span>
                              </div>

                              {/* Message / summary */}
                              {(ev.reason || ev.intent || ev.decision) && (
                                <p className="text-stone-700 dark:text-slate-300 pl-8 text-xs font-sans">
                                  {ev.reason || ev.intent || `Decision: ${ev.decision}`}
                                </p>
                              )}

                              {/* Task Spec / Instructions */}
                              {ev.task_spec && (
                                <div className="ml-8 p-2 rounded-lg bg-violet-50/70 dark:bg-violet-950/30 border border-violet-200 dark:border-violet-900 text-violet-900 dark:text-violet-200 text-[11px] whitespace-pre-wrap font-sans">
                                  <span className="font-semibold font-mono text-[10px] uppercase block mb-1 text-violet-700 dark:text-violet-400">
                                    Task Spec:
                                  </span>
                                  {ev.task_spec}
                                </div>
                              )}

                              {/* Judge Feedback if present */}
                              {(ev.feedback || ev.judge_feedback) && (
                                <div className="ml-8 p-2 rounded-lg bg-blue-50/70 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900 text-blue-900 dark:text-blue-200 text-[11px] whitespace-pre-wrap font-sans">
                                  <span className="font-semibold font-mono text-[10px] uppercase block mb-1 text-blue-700 dark:text-blue-400">
                                    Judge Feedback:
                                  </span>
                                  {ev.feedback || ev.judge_feedback}
                                </div>
                              )}

                              {/* Error Callout */}
                              {hasErr && (
                                <div className="ml-8 p-2.5 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-300 text-[11px] overflow-x-auto whitespace-pre-wrap font-mono">
                                  {ev.error || ev.stderr}
                                </div>
                              )}

                              {/* Code Preview if present */}
                              {ev.code && (
                                <div className="ml-8 p-2.5 rounded-lg bg-white dark:bg-slate-950 border border-[#E8E6DF] dark:border-slate-800 text-stone-800 dark:text-emerald-300 text-[11px] overflow-x-auto max-h-48">
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
        </>
      )}
    </div>
  );
};

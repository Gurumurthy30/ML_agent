import React, { useState, useEffect } from 'react';
import { X, Bot, Cpu, CheckCircle2, Activity } from 'lucide-react';

export default function AgentsModal({ isOpen, onClose }) {
  const [providerData, setProviderData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      fetch('/api/providers')
        .then((res) => res.json())
        .then((data) => {
          setProviderData(data);
          setLoading(false);
        })
        .catch((err) => {
          console.error('Failed to fetch provider info:', err);
          setLoading(false);
        });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const usageCounts = providerData?.usage?.call_counts || {};

  const agents = [
    {
      id: 'data_explorer',
      name: 'Data Explorer',
      role: 'Deterministic dataset profiling, class balance, correlation checking, and leak detection',
      model: 'Python Native / Scipy',
      badge: 'Statistical Engine',
      color: '#46A758',
      tools: ['column_profiler', 'correlation_matrix', 'anova_stats'],
      calls: 'Auto',
    },
    {
      id: 'planner',
      name: 'Planner Agent',
      role: 'Designs model family variants, cross-validation recipes, and manages human clarifications',
      model: providerData?.deep_thinking || 'DeepSeek-V3 (NVIDIA NIM)',
      badge: 'Tree-of-Thoughts',
      color: '#DA7756',
      tools: ['search_library_docs', 'search_technique_cheatsheet'],
      calls: `${usageCounts[providerData?.deep_thinking] || 0} calls`,
    },
    {
      id: 'coder',
      name: 'Coder Agent',
      role: 'Generates robust training pipelines, preprocessing, and model serialization code',
      model: providerData?.primary || 'Groq / Llama 3.3',
      badge: 'Code Synthesis',
      color: '#3E63DD',
      tools: ['validate_code', 'search_library_docs'],
      calls: `${usageCounts[providerData?.primary] || 0} calls`,
    },
    {
      id: 'execute',
      name: 'Execute Agent',
      role: 'Subprocess code runner in session workspace with timeout guards and metric parsing',
      model: 'Local Sandbox / Python 3.11',
      badge: 'Local Env MCP',
      color: '#F7CE46',
      tools: ['execute_code', 'image_scanner'],
      calls: 'Direct Subprocess',
    },
    {
      id: 'selector',
      name: 'Selector & Judge',
      role: 'Evaluates CV improvements, detects plateaus, and decides strategic redirects or convergence',
      model: providerData?.deep_thinking || 'DeepSeek-V3 (NVIDIA NIM)',
      badge: 'Statistical Judge',
      color: '#9050E9',
      tools: ['check_plateau_and_variance'],
      calls: 'Rule-Engine + LLM',
    },
  ];

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-2xl max-w-2xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-border/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 flex items-center justify-center">
              <Bot className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h2 className="text-[16px] font-semibold text-primary">Active Agent Swarm</h2>
              <p className="text-xs text-muted">Specialized agents collaborating on the LangGraph pipeline</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Agent Cards */}
        <div className="overflow-y-auto py-4 space-y-3 flex-1 pr-1">
          {loading ? (
            <div className="text-center py-8 text-xs text-muted font-mono">
              Fetching provider stats from backend...
            </div>
          ) : (
            agents.map((agent) => (
              <div
                key={agent.id}
                className="bg-[#242321] border border-border/80 rounded-xl p-4 hover:border-border-strong transition-all"
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex items-center gap-2.5">
                    <span
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: agent.color, boxShadow: `0 0 10px ${agent.color}66` }}
                    />
                    <span className="font-medium text-[14.5px] text-primary">{agent.name}</span>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-border/40 text-muted border border-border/60">
                      {agent.badge}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-success font-mono">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>online</span>
                  </div>
                </div>

                <p className="text-xs text-muted leading-relaxed mb-3">{agent.role}</p>

                <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/40 text-xs font-mono text-muted/80">
                  <div className="flex items-center gap-1.5">
                    <Cpu className="w-3 h-3 text-accent" />
                    <span>Model: {agent.model}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Activity className="w-3 h-3 text-muted" />
                    <span>Usage: {agent.calls}</span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-border/60 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl bg-border/60 hover:bg-border text-xs text-primary font-medium transition-colors cursor-pointer"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

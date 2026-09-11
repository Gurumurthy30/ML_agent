import React from 'react';
import { X, Bot, Cpu, CheckCircle2, Shield } from 'lucide-react';
import { MOCK_AGENTS } from '../data/mockData';

export default function AgentsModal({ isOpen, onClose }) {
  if (!isOpen) return null;

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
              <p className="text-xs text-muted">Specialized LLM agents collaborating on ML workflows</p>
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
          {MOCK_AGENTS.map((agent) => (
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
                  <Shield className="w-3 h-3 text-muted" />
                  <span>Tools: {agent.tools.join(', ')}</span>
                </div>
              </div>
            </div>
          ))}
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

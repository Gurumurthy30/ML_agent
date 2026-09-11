import React from 'react';
import { X, Wrench, CheckCircle2, Terminal, BookOpen, Sliders, Database } from 'lucide-react';
import { MOCK_TOOLS } from '../data/mockData';

export default function ToolsModal({ isOpen, onClose }) {
  if (!isOpen) return null;

  const getToolIcon = (category) => {
    switch (category) {
      case 'Execution':
        return Terminal;
      case 'Information Retrieval':
        return BookOpen;
      case 'Architecture':
        return Sliders;
      default:
        return Database;
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-2xl max-w-2xl w-full p-6 shadow-2xl animate-in fade-in zoom-in-95 flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-border/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent/20 border border-accent/40 flex items-center justify-center">
              <Wrench className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h2 className="text-[16px] font-semibold text-primary">Model Context Protocol (MCP) Tools</h2>
              <p className="text-xs text-muted">Connected servers providing execution, RAG, and schema profiling</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tool Cards */}
        <div className="overflow-y-auto py-4 space-y-3 flex-1 pr-1">
          {MOCK_TOOLS.map((tool) => {
            const Icon = getToolIcon(tool.category);
            return (
              <div
                key={tool.id}
                className="bg-[#242321] border border-border/80 rounded-xl p-4 hover:border-border-strong transition-all"
              >
                <div className="flex items-start justify-between gap-3 mb-1.5">
                  <div className="flex items-center gap-2.5">
                    <div className="p-1.5 rounded-md bg-[#181716] border border-border/60">
                      <Icon className="w-4 h-4 text-accent" />
                    </div>
                    <div>
                      <div className="font-medium text-[14px] text-primary">{tool.name}</div>
                      <div className="text-[11px] font-mono text-muted/70">{tool.category}</div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-muted px-2 py-0.5 rounded bg-border/40">
                      {tool.callsCount} calls
                    </span>
                    <span className="flex items-center gap-1 text-xs text-success font-mono">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      active
                    </span>
                  </div>
                </div>

                <p className="text-xs text-muted leading-relaxed mb-2.5">{tool.description}</p>

                <div className="text-[11px] font-mono text-accent/80 bg-[#181716] px-2.5 py-1.5 rounded border border-border/50 truncate">
                  {tool.endpoint}
                </div>
              </div>
            );
          })}
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

import React, { useState } from 'react';
import { ChevronRight, Sparkles, Clock } from 'lucide-react';

export default function ThinkingBlock({ thinking, defaultExpanded = false }) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (!thinking) return null;

  const duration = thinking.duration || 'Thought for 12s';
  const summary = thinking.summary || 'Reasoning process';

  return (
    <div className="mb-3 select-text">
      {/* Claude-style Minimal Thinking Pill */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#201F1D] hover:bg-[#2A2926] border border-border/70 text-xs text-muted hover:text-primary transition-colors cursor-pointer group"
        aria-expanded={isExpanded}
      >
        <Sparkles className="w-3.5 h-3.5 text-accent/80 flex-shrink-0" />
        <span className="font-sans font-medium">{duration}</span>
        {summary && (
          <>
            <span className="text-muted/40">•</span>
            <span className="truncate max-w-[280px] sm:max-w-[420px] text-muted/80 font-normal">
              {summary}
            </span>
          </>
        )}
        <ChevronRight
          className={`w-3.5 h-3.5 text-muted transition-transform duration-200 ease-claude ${
            isExpanded ? 'rotate-90 text-primary' : 'group-hover:text-primary'
          }`}
        />
      </button>

      {/* Expanded reasoning trace */}
      <div className={`collapsible-content ${isExpanded ? 'expanded' : ''}`}>
        <div className="collapsible-inner">
          <div className="mt-2.5 pl-3.5 ml-2 border-l-2 border-border text-[13px] leading-relaxed text-muted/90 space-y-1.5 font-sans bg-[#1B1A19]/50 py-2 pr-3 rounded-r-lg">
            {Array.isArray(thinking.trace) ? (
              thinking.trace.map((step, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="text-muted/50 font-mono text-[11px] pt-0.5 select-none">•</span>
                  <p className="flex-1">{step}</p>
                </div>
              ))
            ) : (
              <p className="whitespace-pre-wrap">{thinking.trace}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

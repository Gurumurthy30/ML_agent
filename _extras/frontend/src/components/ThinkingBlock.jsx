import React, { useState } from 'react';
import { Terminal, Copy, Check, ChevronDown, ChevronRight, Code2, Sparkles } from 'lucide-react';

export default function ThinkingBlock({ thinking, defaultExpanded = false }) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [isCopied, setIsCopied] = useState(false);

  if (!thinking) return null;

  const duration = thinking.duration || 'Thinking trace';
  const summary = thinking.summary || 'Reasoning process';

  // Normalize trace to an array of lines
  let traceLines = [];
  if (Array.isArray(thinking.trace)) {
    traceLines = thinking.trace;
  } else if (typeof thinking.trace === 'string') {
    traceLines = thinking.trace.split('\n');
  } else if (typeof thinking.content === 'string') {
    traceLines = thinking.content.split('\n');
  } else {
    traceLines = [summary];
  }

  // Filter empty trailing lines
  traceLines = traceLines.filter((l) => typeof l === 'string' && l.trim().length > 0);
  if (traceLines.length === 0) {
    traceLines = [summary];
  }

  const handleCopy = (e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(traceLines.join('\n'));
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  // Syntax-like token highlighter for trace strings
  const formatTraceLine = (line) => {
    const trimmed = line.trim();

    // Check for "Key: Value" pattern
    const kvMatch = trimmed.match(/^([^:]+):\s*(.*)$/);
    if (kvMatch) {
      const key = kvMatch[1];
      const val = kvMatch[2];
      const isSuccess = /pass|success|none|balanced|explicit/i.test(val);
      const isWarn = /fail|warn|error|imbalance|leakage|defaulted/i.test(val);

      return (
        <span>
          <span className="text-[#DA7756] font-semibold">{key}: </span>
          <span
            className={
              isSuccess
                ? 'text-[#46A758]'
                : isWarn
                ? 'text-[#F5A623]'
                : 'text-[#E0DED9]'
            }
          >
            {val}
          </span>
        </span>
      );
    }

    // Check for comment-style or decision
    if (trimmed.startsWith('//') || trimmed.startsWith('#')) {
      return <span className="text-muted/70 italic">{line}</span>;
    }

    return <span className="text-[#D8D6D1]">{line}</span>;
  };

  return (
    <div className="my-2 select-text font-mono text-[12.5px] rounded-xl border border-border/80 bg-[#161514] overflow-hidden shadow-sm transition-all duration-200">
      {/* Code Editor / Terminal Header Bar */}
      <div
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center justify-between px-3.5 py-2 bg-[#201F1D] hover:bg-[#252422] border-b border-border/60 transition-colors cursor-pointer select-none group"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          {/* Editor Dots */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span className="w-2.5 h-2.5 rounded-full bg-[#E5484D]/70 group-hover:bg-[#E5484D] transition-colors" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#F5A623]/70 group-hover:bg-[#F5A623] transition-colors" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#46A758]/70 group-hover:bg-[#46A758] transition-colors" />
          </div>

          {/* Prompt Icon & Filename Badge */}
          <div className="flex items-center gap-1.5 pl-1.5">
            <Code2 className="w-3.5 h-3.5 text-[#DA7756]" />
            <span className="text-xs font-semibold text-primary/90 tracking-wide uppercase">
              THINKING
            </span>
            <span className="text-muted/40">•</span>
            <span className="text-xs text-[#DA7756] font-mono truncate max-w-[260px] sm:max-w-[380px]">
              {summary}
            </span>
          </div>
        </div>

        {/* Action Buttons: Line Count & Copy & Toggle */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="hidden sm:inline-block px-2 py-0.5 rounded text-[11px] bg-border/40 text-muted font-mono">
            {traceLines.length} {traceLines.length === 1 ? 'line' : 'lines'}
          </span>

          {isExpanded && (
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-2 py-1 rounded text-muted hover:text-primary hover:bg-border/50 transition-colors cursor-pointer text-[11px]"
              title="Copy thinking trace"
            >
              {isCopied ? (
                <>
                  <Check className="w-3 h-3 text-[#46A758]" />
                  <span className="text-[#46A758]">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          )}

          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            className="p-1 text-muted group-hover:text-primary transition-colors cursor-pointer"
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
          >
            {isExpanded ? (
              <ChevronDown className="w-4 h-4 text-muted" />
            ) : (
              <ChevronRight className="w-4 h-4 text-muted" />
            )}
          </button>
        </div>
      </div>

      {/* Code Body: Lines with Numbers */}
      {isExpanded && (
        <div className="p-3.5 overflow-x-auto bg-[#141312] terminal-scroll">
          <table className="w-full border-collapse">
            <tbody>
              {traceLines.map((line, idx) => (
                <tr key={idx} className="leading-[1.75] hover:bg-white/[0.02]">
                  {/* Line Number */}
                  <td className="w-9 pr-3 text-right text-[11px] text-muted/40 select-none align-top font-mono">
                    {String(idx + 1).padStart(2, '0')}
                  </td>
                  {/* Prompt Glyph */}
                  <td className="w-4 pr-1.5 text-accent/70 select-none align-top text-[11.5px]">
                    ›
                  </td>
                  {/* Line Content with Syntax Highlighting */}
                  <td className="whitespace-pre-wrap break-words text-[12.5px] leading-relaxed">
                    {formatTraceLine(line)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

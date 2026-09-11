import React, { useState } from 'react';
import { Terminal, Copy, Check, ChevronDown, ChevronUp } from 'lucide-react';

export default function CodeOutputCard({ card }) {
  const [isCopied, setIsCopied] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  if (!card || !card.lines) return null;

  const lines = card.lines;
  const maxInitialLines = 7;
  const isTruncated = lines.length > maxInitialLines;
  const displayedLines = isExpanded || !isTruncated ? lines : lines.slice(0, maxInitialLines);

  const handleCopy = () => {
    navigator.clipboard.writeText(lines.join('\n'));
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const getLineColor = (line) => {
    const l = line.toLowerCase();
    if (l.includes('[error]') || l.includes('failed') || l.includes('traceback') || l.includes('exception')) {
      return 'text-error';
    }
    if (l.includes('[warn]') || l.includes('warning')) {
      return 'text-warning';
    }
    if (l.includes('[success]') || l.includes('completed with exit code 0')) {
      return 'text-success';
    }
    if (l.includes('$ ') || l.includes('[train]') || l.includes('[info]')) {
      return 'text-[#D0CECA]';
    }
    return 'text-[#BAB9B5]';
  };

  return (
    <div className="my-3 rounded-lg bg-card border border-border overflow-hidden select-text text-[13px] font-mono shadow-sm">
      {/* Card Header */}
      <div className="flex items-center justify-between px-3.5 py-2 bg-[#242321] border-b border-border/70 text-xs">
        <div className="flex items-center gap-2 text-muted">
          <Terminal className="w-3.5 h-3.5 text-accent" />
          <span className="font-sans font-medium text-primary/90">
            {card.title || 'Terminal Execution Output'}
          </span>
          {card.language && (
            <span className="px-1.5 py-0.5 rounded bg-border/40 text-[10.5px] uppercase tracking-wider text-muted">
              {card.language}
            </span>
          )}
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-1 rounded text-muted hover:text-primary hover:bg-border/40 transition-colors cursor-pointer text-xs"
          title="Copy code to clipboard"
        >
          {isCopied ? (
            <>
              <Check className="w-3 h-3 text-success" />
              <span className="text-success text-[11px]">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span className="text-[11px]">Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Terminal lines with line numbers */}
      <div className="p-3 overflow-x-auto terminal-scroll bg-[#1D1C1B]">
        <table className="w-full border-collapse">
          <tbody>
            {displayedLines.map((line, idx) => (
              <tr key={idx} className="leading-[1.7] hover:bg-white/[0.02]">
                <td className="w-10 pr-3.5 text-right text-[11.5px] text-muted/50 select-none align-top font-mono">
                  {idx + 1}
                </td>
                <td className={`whitespace-pre pl-1 text-[12.5px] ${getLineColor(line)}`}>
                  {line}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Truncation / Show More footer */}
      {isTruncated && (
        <div className="border-t border-border/40 bg-[#242321]/80 px-3.5 py-1.5 flex items-center justify-between">
          <span className="text-[11.5px] text-muted font-sans">
            Showing {displayedLines.length} of {lines.length} lines
          </span>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1 text-[12px] font-sans font-medium text-accent hover:text-accent-hover transition-colors cursor-pointer"
          >
            {isExpanded ? (
              <>
                <span>Show less</span>
                <ChevronUp className="w-3.5 h-3.5" />
              </>
            ) : (
              <>
                <span>Show more</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

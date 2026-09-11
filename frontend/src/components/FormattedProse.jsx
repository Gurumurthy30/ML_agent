import React from 'react';

/**
 * Lightweight, safe parser for Claude-style prose:
 * - Turns `code` into terracotta-colored pills on dark background
 * - Handles **bold**, headers (#, ##, ###), lists (*, 1.)
 * - Preserves line breaks and clean paragraph structure
 */
export default function FormattedProse({ text }) {
  if (!text) return null;

  // Split into paragraphs / blocks
  const paragraphs = text.split('\n\n');

  const renderInline = (line) => {
    // Process inline code: `code`
    const parts = line.split(/(`[^`]+`)/g);
    return parts.map((part, idx) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        const codeText = part.slice(1, -1);
        return (
          <code
            key={idx}
            className="font-mono text-accent bg-[#181716]/90 border border-border/60 px-1.5 py-0.5 rounded text-[13px] mx-0.5"
          >
            {codeText}
          </code>
        );
      }

      // Process bold: **text**
      const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
      return boldParts.map((bPart, bIdx) => {
        if (bPart.startsWith('**') && bPart.endsWith('**')) {
          return (
            <strong key={`${idx}-${bIdx}`} className="font-semibold text-[#FFFFFF]">
              {bPart.slice(2, -2)}
            </strong>
          );
        }
        return bPart;
      });
    });
  };

  return (
    <div className="chat-prose space-y-3 select-text">
      {paragraphs.map((para, pIdx) => {
        const trimmed = para.trim();

        // Header 3: ###
        if (trimmed.startsWith('### ')) {
          return (
            <h3 key={pIdx} className="text-[15.5px] font-semibold text-primary pt-2 pb-1 border-b border-border/30">
              {renderInline(trimmed.replace('### ', ''))}
            </h3>
          );
        }

        // Header 2: ##
        if (trimmed.startsWith('## ')) {
          return (
            <h2 key={pIdx} className="text-[17px] font-semibold text-primary pt-2">
              {renderInline(trimmed.replace('## ', ''))}
            </h2>
          );
        }

        // Unordered list items: lines starting with * or -
        const lines = para.split('\n');
        const isList = lines.every((l) => /^\s*[\*\-]\s+/.test(l) || l.trim() === '');
        if (isList) {
          return (
            <ul key={pIdx} className="space-y-1.5 my-2">
              {lines
                .filter((l) => l.trim().length > 0)
                .map((line, lIdx) => (
                  <li key={lIdx} className="flex items-start gap-2.5">
                    <span className="text-accent text-[14px] leading-relaxed select-none">•</span>
                    <span className="flex-1 leading-[1.6]">
                      {renderInline(line.replace(/^\s*[\*\-]\s+/, ''))}
                    </span>
                  </li>
                ))}
            </ul>
          );
        }

        // Numbered list items: lines starting with 1. 2. etc
        const isNumbered = lines.every((l) => /^\s*\d+\.\s+/.test(l) || l.trim() === '');
        if (isNumbered) {
          return (
            <ol key={pIdx} className="space-y-1.5 my-2">
              {lines
                .filter((l) => l.trim().length > 0)
                .map((line, lIdx) => {
                  const match = line.match(/^\s*(\d+)\.\s+(.*)/);
                  const num = match ? match[1] : lIdx + 1;
                  const content = match ? match[2] : line;
                  return (
                    <li key={lIdx} className="flex items-start gap-2.5">
                      <span className="text-muted/80 text-[12.5px] font-mono select-none pt-0.5 w-4 text-right">
                        {num}.
                      </span>
                      <span className="flex-1 leading-[1.6]">{renderInline(content)}</span>
                    </li>
                  );
                })}
            </ol>
          );
        }

        // Standard prose paragraph
        return (
          <p key={pIdx} className="leading-[1.65]">
            {lines.map((l, lIdx) => (
              <React.Fragment key={lIdx}>
                {renderInline(l)}
                {lIdx < lines.length - 1 && <br />}
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

import React from 'react';

/**
 * Enhanced Markdown Prose Parser for Claude-style UI:
 * - Pixel-perfect markdown table rendering (headers, alignment, zebra-striping, monospace data)
 * - Headers (##, ###) with accent underlines
 * - Bullet lists (*) and Numbered lists (1.)
 * - Inline formatting: bold (**), inline code (`), and badges
 * - Special monospace visualization for ASCII distribution bars (█ / ░)
 */
export default function FormattedProse({ text }) {
  if (!text) return null;

  // Inline formatting renderer
  const renderInline = (line) => {
    if (!line) return null;

    // Process inline code: `code`
    const parts = line.split(/(`[^`]+`)/g);
    return parts.map((part, idx) => {
      if (part.startsWith('`') && part.endsWith('`')) {
        const codeText = part.slice(1, -1);
        return (
          <code
            key={idx}
            className="font-mono text-accent bg-[#181716]/95 border border-border/70 px-1.5 py-0.5 rounded text-[12.5px] mx-0.5"
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
            <strong key={`${idx}-${bIdx}`} className="font-semibold text-primary">
              {bPart.slice(2, -2)}
            </strong>
          );
        }
        return bPart;
      });
    });
  };

  // Helper to split row by pipe into trimmed cell strings
  const parseCells = (row) => {
    let trimmed = row.trim();
    if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
    if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1);
    return trimmed.split('|').map((c) => c.trim());
  };

  const isSeparatorLine = (line) => {
    const cells = parseCells(line);
    return (
      cells.length > 0 &&
      cells.every((c) => /^:?-+:?$/.test(c.trim()))
    );
  };

  const isTableRow = (line) => {
    const trimmed = line.trim();
    return trimmed.startsWith('|') && trimmed.includes('|') && trimmed.length > 2;
  };

  // Break document into blocks (headers, tables, lists, paragraphs)
  const lines = text.split('\n');
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i++;
      continue;
    }

    // Check if line starts a markdown table (current line is row and next is separator)
    if (isTableRow(line) && i + 1 < lines.length && isSeparatorLine(lines[i + 1])) {
      const headerRow = parseCells(line);
      const separatorRow = parseCells(lines[i + 1]);

      // Detect column alignments (:---, :---:, ---:)
      const alignments = separatorRow.map((sep) => {
        const s = sep.trim();
        if (s.startsWith(':') && s.endsWith(':')) return 'center';
        if (s.endsWith(':')) return 'right';
        return 'left';
      });

      i += 2; // skip header and separator
      const dataRows = [];

      while (i < lines.length && isTableRow(lines[i])) {
        dataRows.push(parseCells(lines[i]));
        i++;
      }

      blocks.push({
        type: 'table',
        headers: headerRow,
        alignments,
        rows: dataRows,
      });
      continue;
    }

    // Header 3: ###
    if (trimmed.startsWith('### ')) {
      blocks.push({ type: 'h3', content: trimmed.replace('### ', '') });
      i++;
      continue;
    }

    // Header 2: ##
    if (trimmed.startsWith('## ')) {
      blocks.push({ type: 'h2', content: trimmed.replace('## ', '') });
      i++;
      continue;
    }

    // Unordered List item (* or -)
    if (/^\s*[\*\-]\s+/.test(line)) {
      const listItems = [];
      while (i < lines.length && (/^\s*[\*\-]\s+/.test(lines[i]) || (lines[i].trim() === '' && i + 1 < lines.length && /^\s*[\*\-]\s+/.test(lines[i + 1])))) {
        if (lines[i].trim()) {
          listItems.push(lines[i].replace(/^\s*[\*\-]\s+/, ''));
        }
        i++;
      }
      blocks.push({ type: 'ul', items: listItems });
      continue;
    }

    // Numbered List item (1. 2. etc)
    if (/^\s*\d+\.\s+/.test(line)) {
      const listItems = [];
      while (i < lines.length && (/^\s*\d+\.\s+/.test(lines[i]) || (lines[i].trim() === '' && i + 1 < lines.length && /^\s*\d+\.\s+/.test(lines[i + 1])))) {
        if (lines[i].trim()) {
          const match = lines[i].match(/^\s*(\d+)\.\s+(.*)/);
          listItems.push({
            num: match ? match[1] : listItems.length + 1,
            text: match ? match[2] : lines[i],
          });
        }
        i++;
      }
      blocks.push({ type: 'ol', items: listItems });
      continue;
    }

    // Plain prose paragraph (collect until blank line or special block)
    const paraLines = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith('## ') &&
      !lines[i].trim().startsWith('### ') &&
      !isTableRow(lines[i]) &&
      !/^\s*[\*\-]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }

    if (paraLines.length > 0) {
      blocks.push({ type: 'p', lines: paraLines });
    }
  }

  return (
    <div className="chat-prose space-y-3.5 select-text text-[14px]">
      {blocks.map((block, bIdx) => {
        // Table Block
        if (block.type === 'table') {
          return (
            <div
              key={bIdx}
              className="overflow-x-auto my-3.5 rounded-xl border border-border/80 bg-[#161514] shadow-md shadow-black/20 terminal-scroll"
            >
              <table className="w-full text-left border-collapse text-[13px]">
                <thead>
                  <tr className="bg-[#201F1D] border-b border-border/90 text-[11.5px] uppercase tracking-wider text-muted font-mono">
                    {block.headers.map((h, hIdx) => {
                      const align = block.alignments[hIdx] || 'left';
                      return (
                        <th
                          key={hIdx}
                          className={`px-4 py-2.5 font-semibold text-primary/95 whitespace-nowrap ${
                            align === 'right'
                              ? 'text-right'
                              : align === 'center'
                              ? 'text-center'
                              : 'text-left'
                          }`}
                        >
                          {renderInline(h)}
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40 font-mono text-[12.5px]">
                  {block.rows.map((row, rIdx) => (
                    <tr
                      key={rIdx}
                      className="hover:bg-white/[0.03] transition-colors odd:bg-transparent even:bg-white/[0.015]"
                    >
                      {row.map((cell, cIdx) => {
                        const align = block.alignments[cIdx] || 'left';
                        return (
                          <td
                            key={cIdx}
                            className={`px-4 py-2 text-primary/85 whitespace-nowrap ${
                              align === 'right'
                                ? 'text-right font-mono'
                                : align === 'center'
                                ? 'text-center'
                                : 'text-left'
                            }`}
                          >
                            {renderInline(cell)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        // Header 2
        if (block.type === 'h2') {
          return (
            <h2
              key={bIdx}
              className="text-[17px] font-semibold text-primary pt-2 pb-1 border-b border-border/40"
            >
              {renderInline(block.content)}
            </h2>
          );
        }

        // Header 3
        if (block.type === 'h3') {
          return (
            <h3
              key={bIdx}
              className="text-[15px] font-semibold text-primary pt-2 pb-0.5 text-accent"
            >
              {renderInline(block.content)}
            </h3>
          );
        }

        // Unordered List
        if (block.type === 'ul') {
          return (
            <ul key={bIdx} className="space-y-1.5 my-2">
              {block.items.map((item, lIdx) => {
                const isBar = item.includes('█') || item.includes('░');
                return (
                  <li
                    key={lIdx}
                    className={`flex items-start gap-2.5 ${
                      isBar
                        ? 'bg-[#181716] px-3 py-1.5 rounded-lg border border-border/50 font-mono text-[12px]'
                        : ''
                    }`}
                  >
                    {!isBar && (
                      <span className="text-accent text-[14px] leading-relaxed select-none">
                        •
                      </span>
                    )}
                    <span className="flex-1 leading-[1.6]">
                      {renderInline(item)}
                    </span>
                  </li>
                );
              })}
            </ul>
          );
        }

        // Numbered List
        if (block.type === 'ol') {
          return (
            <ol key={bIdx} className="space-y-1.5 my-2">
              {block.items.map((item, lIdx) => (
                <li key={lIdx} className="flex items-start gap-2.5">
                  <span className="text-muted/80 text-[12px] font-mono select-none pt-0.5 w-4 text-right">
                    {item.num}.
                  </span>
                  <span className="flex-1 leading-[1.6]">
                    {renderInline(item.text)}
                  </span>
                </li>
              ))}
            </ol>
          );
        }

        // Standard Paragraph
        if (block.type === 'p') {
          return (
            <p key={bIdx} className="leading-[1.65] text-primary/90">
              {block.lines.map((l, lIdx) => (
                <React.Fragment key={lIdx}>
                  {renderInline(l)}
                  {lIdx < block.lines.length - 1 && <br />}
                </React.Fragment>
              ))}
            </p>
          );
        }

        return null;
      })}
    </div>
  );
}

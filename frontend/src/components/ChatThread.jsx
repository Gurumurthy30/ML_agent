import React, { useRef, useEffect, useState } from 'react';
import { ChevronDown, FileText, Sparkles, Bot } from 'lucide-react';
import ThinkingBlock from './ThinkingBlock';
import ToolCallBlock from './ToolCallBlock';
import CodeOutputCard from './CodeOutputCard';
import FormattedProse from './FormattedProse';
import ArtifactCard from './ArtifactCard';

export default function ChatThread({ messages = [], isGenerating = false, activeStatusText = '' }) {
  const scrollContainerRef = useRef(null);
  const bottomAnchorRef = useRef(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  // Monitor scroll position for floating scroll-to-bottom button
  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    setShowScrollBottom(distanceFromBottom > 160);
  };

  const scrollToBottom = (smooth = true) => {
    bottomAnchorRef.current?.scrollIntoView({
      behavior: smooth ? 'smooth' : 'auto',
    });
  };

  useEffect(() => {
    scrollToBottom(false);
  }, [messages.length, isGenerating]);

  return (
    <div
      ref={scrollContainerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 md:px-6 py-6 select-text scroll-smooth relative"
    >
      {/* Centered chat column: max-w-[760px] */}
      <div className="max-w-chat mx-auto space-y-7">
        {messages.map((msg) => {
          // ── USER MESSAGE (Right side) ──
          if (msg.sender === 'user') {
            return (
              <div key={msg.id} className="flex justify-end pt-1">
                <div className="max-w-[85%] md:max-w-[75%] bg-[#2D2C2A] border border-border/80 rounded-2xl rounded-tr-sm px-4 py-3 text-[15px] text-primary shadow-sm space-y-2.5">
                  <div className="leading-relaxed whitespace-pre-wrap">
                    {msg.content}
                  </div>

                  {/* Attachment chips */}
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-2 border-t border-border/50">
                      {msg.attachments.map((att, aIdx) => (
                        <div
                          key={aIdx}
                          className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[#201F1D] border border-border/70 text-xs text-primary"
                        >
                          <FileText className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                          <span className="font-mono text-[12px] truncate max-w-[190px]">
                            {att.name}
                          </span>
                          {att.size && (
                            <span className="text-[11px] text-muted font-mono">
                              ({att.size})
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          }

          // ── ASSISTANT MESSAGE (Left side, Linear Timeline) ──
          return (
            <div key={msg.id} className="flex gap-3.5 pt-1 group">
              {/* Claude / ML Agent Avatar */}
              <div className="w-6 h-6 rounded-md bg-[#DA7756] flex items-center justify-center flex-shrink-0 mt-1 shadow-sm">
                <Sparkles className="w-3.5 h-3.5 text-white" strokeWidth={2.2} />
              </div>

              {/* Message Content Container */}
              <div className="flex-1 min-w-0 space-y-3">
                {/* Header: Agent Attribution + Timestamp */}
                <div className="flex items-center gap-2 pb-0.5 select-none">
                  <span className="font-medium text-[13.5px] text-primary">
                    {msg.agents ? msg.agents.join(' · ') : 'ML Agent Swarm'}
                  </span>
                  <span className="text-[11px] font-mono text-muted/70">
                    {msg.timestamp || 'Just now'}
                  </span>
                </div>

                {/* 1. Linear Stack: Collapsible Thinking Block */}
                {msg.thinking && (
                  <ThinkingBlock thinking={msg.thinking} />
                )}

                {/* 2. Linear Stack: Collapsible Tool Call Block */}
                {msg.toolCalls && (
                  <ToolCallBlock toolCalls={msg.toolCalls} />
                )}

                {/* 3. Linear Stack: Primary Response Text */}
                {msg.prose && (
                  <FormattedProse text={msg.prose} />
                )}

                {/* 4. Linear Stack: Terminal / Execution Trace */}
                {msg.terminalCard && (
                  <CodeOutputCard card={msg.terminalCard} />
                )}

                {/* 5. Linear Stack: Final Model Deliverable / Download Card */}
                {msg.artifact && (
                  <ArtifactCard artifact={msg.artifact} />
                )}

                {/* 6. Linear Stack: Closing notes */}
                {msg.closingProse && (
                  <FormattedProse text={msg.closingProse} />
                )}
              </div>
            </div>
          );
        })}

        {/* Live Generation State (Claude-style subtle loading) */}
        {isGenerating && (
          <div className="flex gap-3.5 pt-1">
            <div className="w-6 h-6 rounded-md bg-[#DA7756] flex items-center justify-center flex-shrink-0 mt-1 animate-pulse">
              <Sparkles className="w-3.5 h-3.5 text-white animate-spin" />
            </div>
            <div className="flex-1 space-y-2">
              <div className="flex items-center gap-2 select-none">
                <span className="font-medium text-[13.5px] text-primary">
                  ML Agent Swarm
                </span>
                <span className="text-[11px] font-mono text-accent animate-pulse">
                  Working...
                </span>
              </div>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#242321] border border-border/80 text-xs text-muted">
                <span className="w-2 h-2 rounded-full bg-accent animate-ping" />
                <span className="font-mono text-[11.5px]">
                  {activeStatusText || 'Orchestrating planner and training model in sandbox...'}
                </span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomAnchorRef} className="h-4" />
      </div>

      {/* Floating Scroll-to-bottom button */}
      {showScrollBottom && (
        <button
          onClick={() => scrollToBottom(true)}
          className="fixed bottom-24 right-6 md:right-12 z-20 w-8 h-8 rounded-full bg-card border border-border shadow-xl flex items-center justify-center text-muted hover:text-primary hover:bg-[#343330] transition-all duration-200 cursor-pointer hover:scale-105 active:scale-95"
          title="Scroll to bottom"
        >
          <ChevronDown className="w-4 h-4 text-accent" />
        </button>
      )}
    </div>
  );
}

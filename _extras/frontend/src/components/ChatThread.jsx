import React, { useRef, useEffect, useState } from 'react';
import {
  Sparkles,
  FileText,
  FileSpreadsheet,
  BarChart3,
  GitCompare,
  Terminal,
  HelpCircle,
  AlertTriangle,
  Scale,
  Send,
  ChevronDown,
} from 'lucide-react';
import ThinkingBlock from './ThinkingBlock';
import ToolCallBlock from './ToolCallBlock';
import CodeOutputCard from './CodeOutputCard';
import FormattedProse from './FormattedProse';
import ChartBlock from './ChartBlock';
import PipelineTracker from './PipelineTracker';
import MessageInput from './MessageInput';

export default function ChatThread({
  messages = [],
  isRunning = false,
  activeNode = null,
  pendingHumanQuestion: _pendingHumanQuestion = null,
  onSendMessage,
  uploadFile,
  sessionId: _sessionId = null,
}) {
  const scrollContainerRef = useRef(null);
  const bottomAnchorRef = useRef(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const [prefillPrompt, setPrefillPrompt] = useState('');
  const [humanReplyText, setHumanReplyText] = useState('');

  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    setShowScrollBottom(scrollHeight - scrollTop - clientHeight > 160);
  };

  const scrollToBottom = (smooth = true) => {
    bottomAnchorRef.current?.scrollIntoView({
      behavior: smooth ? 'smooth' : 'auto',
    });
  };

  useEffect(() => {
    scrollToBottom(false);
  }, [messages.length, isRunning]);

  const suggestionChips = [
    {
      icon: FileSpreadsheet,
      title: 'Upload a CSV',
      description: 'Auto-detect target column, task type, and metric',
      prompt:
        'I am uploading a tabular dataset. Please profile the schema, identify the target column, and configure the optimal evaluation metric.',
    },
    {
      icon: BarChart3,
      title: 'Explore my data',
      description: 'Get a full EDA report with charts before modeling',
      prompt:
        'Please run a comprehensive Exploratory Data Analysis (EDA) on this dataset, checking class balance, missing values, and feature correlations with visualizations.',
    },
    {
      icon: Sparkles,
      title: 'Train a classifier',
      description: 'Describe your prediction goal in plain English',
      prompt:
        'Train an end-to-end gradient boosted classifier using 5-fold cross validation. Optimize for ROC-AUC, generate feature importance plots, and serialize the best model.',
    },
    {
      icon: GitCompare,
      title: 'Compare approaches',
      description: 'Evaluate multiple model families to find the best',
      prompt:
        'Compare multiple model families (LightGBM, CatBoost, Scikit-Learn) with cross validation and report performance across rounds.',
    },
  ];

  // ──────────────────────────────────────────────────────────────────────────
  // 1. Empty State: Claude-Style Home Screen (Headline + Subtext + Composer + Chips)
  // ──────────────────────────────────────────────────────────────────────────
  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col justify-center items-center px-4 md:px-8 py-10 select-text overflow-y-auto">
        <div className="w-full max-w-[720px] mx-auto flex flex-col items-center text-center space-y-6 animate-in fade-in zoom-in-95 duration-300">
          {/* Greeting Icon / Logo */}
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#DA7756] to-[#b85b3b] flex items-center justify-center shadow-lg shadow-accent/25">
            <Sparkles className="w-6 h-6 text-white" strokeWidth={2.2} />
          </div>

          {/* Headline & Subtext */}
          <div className="space-y-2">
            <h1 className="text-3xl sm:text-4xl font-semibold text-primary tracking-tight">
              What are we building today?
            </h1>
            <p className="text-sm sm:text-base text-muted max-w-[560px] leading-relaxed mx-auto">
              Upload a dataset or describe your prediction task — I'll handle EDA, modeling, and
              evaluation end to end.
            </p>
          </div>

          {/* Centered Composer */}
          <div className="w-full text-left pt-2">
            <MessageInput
              onSendMessage={onSendMessage}
              uploadFile={uploadFile}
              isGenerating={isRunning}
              prefilledText={prefillPrompt}
              onClearPrefill={() => setPrefillPrompt('')}
              variant="centered"
            />
          </div>

          {/* Claude-Style Suggestion Chips Grid */}
          <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-4 text-left">
            {suggestionChips.map((chip, idx) => {
              const Icon = chip.icon;
              return (
                <button
                  key={idx}
                  onClick={() => setPrefillPrompt(chip.prompt)}
                  className="p-3.5 rounded-xl bg-card hover:bg-[#343330] border border-border/80 hover:border-accent/50 transition-all flex items-start gap-3 group cursor-pointer text-left shadow-sm active:scale-[0.99]"
                >
                  <div className="w-8 h-8 rounded-lg bg-[#1F1E1D] border border-border/60 flex items-center justify-center flex-shrink-0 mt-0.5 group-hover:border-accent/40 transition-colors">
                    <Icon className="w-4 h-4 text-accent" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-primary group-hover:text-accent transition-colors">
                      {chip.title}
                    </div>
                    <div className="text-[11.5px] text-muted leading-snug mt-0.5">
                      {chip.description}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  // ──────────────────────────────────────────────────────────────────────────
  // 2. Active Session: Live Stream of Events
  // ──────────────────────────────────────────────────────────────────────────
  return (
    <div
      ref={scrollContainerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 md:px-6 py-6 select-text scroll-smooth relative"
    >
      <div className="max-w-chat mx-auto space-y-6">
        {/* Pipeline stage tracker when running */}
        {isRunning && (
          <PipelineTracker activeNode={activeNode} isRunning={isRunning} />
        )}

        {messages.map((item) => {
          // ── USER MESSAGE ──
          if (item.type === 'user_message' || item.sender === 'user') {
            return (
              <div key={item.id} className="flex justify-end pt-1">
                <div className="max-w-[85%] md:max-w-[75%] bg-[#2D2C2A] border border-border/80 rounded-2xl rounded-tr-sm px-4 py-3 text-[15px] text-primary shadow-sm space-y-2.5">
                  <div className="leading-relaxed whitespace-pre-wrap">{item.content}</div>

                  {/* Attachment chips */}
                  {item.attachmentDetails && item.attachmentDetails.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-2 border-t border-border/50">
                      {item.attachmentDetails.map((att, aIdx) => (
                        <div
                          key={aIdx}
                          className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[#201F1D] border border-border/70 text-xs text-primary"
                        >
                          <FileText className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                          <span className="font-mono text-[12px] truncate max-w-[190px]">
                            {att.name}
                          </span>
                          {att.size && (
                            <span className="text-[11px] text-muted font-mono">({att.size})</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          }

          // ── THINKING EVENT ──
          if (item.type === 'thinking') {
            return (
              <div key={item.id} className="pl-9">
                <ThinkingBlock
                  thinking={{
                    summary: item.summary,
                    duration: item.duration || (item.node ? `${item.node} reasoning` : 'Thought process'),
                    trace: item.trace,
                  }}
                />
              </div>
            );
          }

          // ── EDA REPORT EVENT ──
          if (item.type === 'eda_report') {
            return (
              <div key={item.id} className="flex gap-3.5 pt-1">
                <div className="w-6 h-6 rounded-md bg-[#46A758] flex items-center justify-center flex-shrink-0 mt-1 shadow-sm">
                  <BarChart3 className="w-3.5 h-3.5 text-white" strokeWidth={2.2} />
                </div>
                <div className="flex-1 min-w-0 space-y-3">
                  <div className="flex items-center gap-2 pb-0.5 select-none text-xs font-mono text-muted">
                    <span className="font-medium text-primary">Data Explorer</span>
                    <span>•</span>
                    <span>{item.summary || 'EDA Profiling Complete'}</span>
                  </div>

                  {/* Charts if present */}
                  {item.charts && Object.keys(item.charts).length > 0 && (
                    <ChartBlock edaCharts={item.charts} />
                  )}

                  {/* Prose Markdown */}
                  {item.contentMarkdown && (
                    <FormattedProse text={item.contentMarkdown} />
                  )}
                </div>
              </div>
            );
          }

          // ── TOOL CALL / TOOL RESULT ──
          if (item.type === 'tool_call' || item.type === 'tool_result') {
            const calls = [
              {
                id: item.id,
                tool: item.tool,
                args: item.input,
                result: item.output ? JSON.stringify(item.output, null, 2) : undefined,
                status: 'success',
              },
            ];
            return (
              <div key={item.id} className="pl-9">
                <ToolCallBlock
                  toolCalls={{
                    summary: `Called tool: ${item.tool} (${item.node || 'mcp'})`,
                    calls,
                  }}
                />
              </div>
            );
          }

          // ── CODE BLOCK EVENT ──
          if (item.type === 'code_block') {
            const card = {
              title: `Pipeline Implementation — ${item.node || 'coder'}`,
              language: item.language || 'python',
              lines: (item.content || '').split('\n'),
            };
            return (
              <div key={item.id} className="pl-9">
                <CodeOutputCard card={card} />
              </div>
            );
          }

          // ── EXECUTION RESULT EVENT ──
          if (item.type === 'execution_result') {
            const cvMean = typeof item.cv_mean === 'number' ? item.cv_mean.toFixed(4) : '0.0000';
            const cvStd = typeof item.cv_std === 'number' ? item.cv_std.toFixed(4) : '0.0000';
            const statusColor = item.status === 'success' ? 'text-success' : 'text-error';

            return (
              <div key={item.id} className="flex gap-3.5 pt-1">
                <div className="w-6 h-6 rounded-md bg-[#F7CE46] flex items-center justify-center flex-shrink-0 mt-1 shadow-sm">
                  <Terminal className="w-3.5 h-3.5 text-[#181716]" strokeWidth={2.2} />
                </div>
                <div className="flex-1 min-w-0 space-y-2.5">
                  <div className="flex items-center gap-2 select-none text-xs font-mono">
                    <span className="font-medium text-primary">Execute Agent</span>
                    <span className="text-muted">•</span>
                    <span className="text-muted">{item.experiment_id}</span>
                    <span className={`capitalize font-semibold ${statusColor}`}>
                      [{item.status || 'success'}]
                    </span>
                  </div>

                  {/* Real Metrics Banner */}
                  <div className="p-3 rounded-xl bg-[#201F1D] border border-border/80 flex flex-wrap items-center gap-4 text-xs font-mono">
                    <div>
                      <span className="text-muted">CV Mean: </span>
                      <span className="text-accent font-bold text-sm">{cvMean}</span>
                    </div>
                    <div>
                      <span className="text-muted">CV Std: </span>
                      <span className="text-primary font-medium">±{cvStd}</span>
                    </div>
                    <div className="ml-auto text-[11px] text-muted">
                      Status: <span className={statusColor}>{item.status}</span>
                    </div>
                  </div>

                  {/* Stdout / Stderr logs if available */}
                  {(item.stdout_tail || item.stderr_tail) && (
                    <CodeOutputCard
                      card={{
                        title: `Execution Log (${item.experiment_id})`,
                        language: 'shell',
                        lines: (item.stdout_tail || item.stderr_tail || '').split('\n').filter(Boolean),
                      }}
                    />
                  )}
                </div>
              </div>
            );
          }

          // ── CHART EVENT ──
          if (item.type === 'chart') {
            return (
              <div key={item.id} className="pl-9">
                <ChartBlock chart={item} />
              </div>
            );
          }

          // ── SELECTOR VERDICT EVENT ──
          if (item.type === 'selector_verdict') {
            const isConverged = item.decision === 'converge';
            return (
              <div key={item.id} className="flex gap-3.5 pt-1">
                <div
                  className={`w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-1 shadow-sm ${
                    isConverged ? 'bg-success' : 'bg-[#9050E9]'
                  }`}
                >
                  <Scale className="w-3.5 h-3.5 text-white" strokeWidth={2.2} />
                </div>
                <div className="flex-1 min-w-0 space-y-2">
                  <div className="flex items-center gap-2 select-none text-xs font-mono">
                    <span className="font-medium text-primary">Selector & Judge</span>
                    <span className="text-muted">•</span>
                    <span
                      className={`font-semibold uppercase tracking-wider ${
                        isConverged ? 'text-success' : 'text-[#9050E9]'
                      }`}
                    >
                      {item.decision}
                    </span>
                  </div>

                  <div className="p-3.5 rounded-xl bg-[#242321] border border-border/80 text-xs space-y-1.5 shadow-sm">
                    <div className="text-primary font-medium">{item.detail}</div>
                    {item.methodology_note && (
                      <div className="text-muted text-[11.5px] leading-relaxed pt-1 border-t border-border/40 font-sans">
                        <span className="text-muted/70 font-mono text-[10.5px] uppercase tracking-wider block mb-0.5">
                          Methodology Soundness:
                        </span>
                        {item.methodology_note}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          }

          // ── HUMAN INPUT REQUEST EVENT ──
          if (item.type === 'human_input_request') {
            return (
              <div key={item.id} className="flex gap-3.5 pt-1">
                <div className="w-6 h-6 rounded-md bg-[#DA7756] flex items-center justify-center flex-shrink-0 mt-1 shadow-sm">
                  <HelpCircle className="w-3.5 h-3.5 text-white" strokeWidth={2.2} />
                </div>
                <div className="flex-1 min-w-0 space-y-3">
                  <div className="flex items-center gap-2 select-none text-xs font-mono text-accent">
                    <span className="font-medium">Human Clarification Required</span>
                  </div>

                  <div className="p-4 rounded-xl bg-[#242321] border border-accent/60 text-xs space-y-3 shadow-md">
                    <div className="text-primary text-[13.5px] font-medium leading-relaxed">
                      {item.question}
                    </div>
                    {item.context && (
                      <div className="text-muted font-mono text-[11px] bg-[#181716] p-2 rounded border border-border/50">
                        Context: {item.context}
                      </div>
                    )}

                    {/* Quick Clarification Input */}
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="text"
                        value={humanReplyText}
                        onChange={(e) => setHumanReplyText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && humanReplyText.trim()) {
                            onSendMessage({ content: humanReplyText.trim(), attachments: [] });
                            setHumanReplyText('');
                          }
                        }}
                        placeholder="Type your clarification answer…"
                        className="flex-1 bg-[#181716] border border-border focus:border-accent rounded-lg px-3 py-1.5 text-xs text-primary focus:outline-none"
                      />
                      <button
                        onClick={() => {
                          if (humanReplyText.trim()) {
                            onSendMessage({ content: humanReplyText.trim(), attachments: [] });
                            setHumanReplyText('');
                          }
                        }}
                        className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accent-hover text-white text-xs font-medium transition-all flex items-center gap-1 cursor-pointer"
                      >
                        <Send className="w-3 h-3" />
                        <span>Reply</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          }

          // ── ASSISTANT PROSE MESSAGE ──
          if (item.type === 'assistant_message' || item.sender === 'assistant') {
            return (
              <div key={item.id} className="flex gap-3.5 pt-1 group">
                <div className="w-6 h-6 rounded-md bg-[#DA7756] flex items-center justify-center flex-shrink-0 mt-1 shadow-sm">
                  <Sparkles className="w-3.5 h-3.5 text-white" strokeWidth={2.2} />
                </div>
                <div className="flex-1 min-w-0 space-y-3">
                  <div className="flex items-center gap-2 pb-0.5 select-none text-xs font-mono text-muted">
                    <span className="font-medium text-primary">ML Agent Swarm</span>
                    <span>•</span>
                    <span>{item.timestamp || 'Just now'}</span>
                  </div>
                  <FormattedProse text={item.content} />
                </div>
              </div>
            );
          }

          // ── ERROR EVENT ──
          if (item.type === 'error') {
            return (
              <div key={item.id} className="flex gap-3.5 pt-1">
                <div className="w-6 h-6 rounded-md bg-error flex items-center justify-center flex-shrink-0 mt-1 shadow-sm">
                  <AlertTriangle className="w-3.5 h-3.5 text-white" strokeWidth={2.2} />
                </div>
                <div className="flex-1 min-w-0 space-y-1.5">
                  <div className="text-xs font-mono text-error font-medium">
                    Error encountered ({item.node || 'pipeline'})
                  </div>
                  <div className="p-3 rounded-xl bg-error/10 border border-error/30 text-xs text-error font-mono whitespace-pre-wrap">
                    {item.message}
                  </div>
                </div>
              </div>
            );
          }

          return null;
        })}

        {/* Live Running Indicator */}
        {isRunning && (
          <div className="flex gap-3.5 pt-1 items-center animate-pulse">
            <div className="w-6 h-6 rounded-md bg-[#DA7756] flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-3.5 h-3.5 text-white animate-spin" />
            </div>
            <div className="text-xs font-mono text-muted flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-accent animate-ping" />
              <span>Orchestrating agents: {activeNode || 'planning pipeline'}...</span>
            </div>
          </div>
        )}

        <div ref={bottomAnchorRef} className="h-4" />
      </div>

      {/* Floating Scroll-to-bottom button */}
      {showScrollBottom && (
        <button
          onClick={() => scrollToBottom(true)}
          className="fixed bottom-24 right-8 p-2 rounded-full bg-card border border-border/80 text-muted hover:text-primary shadow-lg transition-all hover:scale-105 cursor-pointer z-20"
          title="Scroll to bottom"
        >
          <ChevronDown className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

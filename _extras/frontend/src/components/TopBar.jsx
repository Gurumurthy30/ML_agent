import React, { useState, useRef, useEffect } from 'react';
import {
  ChevronDown,
  Share2,
  PanelLeftClose,
  PanelLeft,
  Cpu,
  Check,
  Download,
  Copy,
  Edit2,
  Trash2,
} from 'lucide-react';

export default function TopBar({
  title,
  mode = 'Cloud API · Multi-Provider',
  isSidebarOpen,
  onToggleSidebar,
  onRenameTitle,
  onClearChat,
  onExportChat,
  onOpenSettings,
}) {
  const [isTitleMenuOpen, setIsTitleMenuOpen] = useState(false);
  const [isModeMenuOpen, setIsModeMenuOpen] = useState(false);
  const [currentMode, setCurrentMode] = useState(mode);
  const [isShareModalOpen, setIsShareModalOpen] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [newTitle, setNewTitle] = useState(title);
  const [copiedLink, setCopiedLink] = useState(false);

  const titleMenuRef = useRef(null);
  const modeMenuRef = useRef(null);

  useEffect(() => {
    setCurrentMode(mode);
  }, [mode]);

  useEffect(() => {
    setNewTitle(title);
  }, [title]);

  // Click outside to close menus
  useEffect(() => {
    function handleClickOutside(event) {
      if (titleMenuRef.current && !titleMenuRef.current.contains(event.target)) {
        setIsTitleMenuOpen(false);
      }
      if (modeMenuRef.current && !modeMenuRef.current.contains(event.target)) {
        setIsModeMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSaveTitle = (e) => {
    e.preventDefault();
    if (newTitle.trim()) {
      onRenameTitle(newTitle.trim());
    }
    setIsEditingTitle(false);
    setIsTitleMenuOpen(false);
  };

  const handleCopyShareLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  };

  return (
    <header className="h-14 border-b border-border/80 bg-shell/95 backdrop-blur-sm px-4 flex items-center justify-between z-20 flex-shrink-0 select-none">
      {/* Left: Sidebar toggle + Title dropdown */}
      <div className="flex items-center gap-2 min-w-0">
        <button
          onClick={onToggleSidebar}
          className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-card/70 transition-colors cursor-pointer"
          title={isSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {isSidebarOpen ? (
            <PanelLeftClose className="w-4 h-4" />
          ) : (
            <PanelLeft className="w-4 h-4 text-accent" />
          )}
        </button>

        {/* Title dropdown */}
        <div className="relative" ref={titleMenuRef}>
          {isEditingTitle ? (
            <form onSubmit={handleSaveTitle} className="flex items-center gap-1.5">
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                autoFocus
                onBlur={handleSaveTitle}
                className="bg-card border border-accent/60 rounded px-2 py-0.5 text-sm text-primary focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </form>
          ) : (
            <button
              onClick={() => setIsTitleMenuOpen(!isTitleMenuOpen)}
              className="flex items-center gap-1.5 px-2 py-1 rounded-lg hover:bg-card/60 transition-colors text-left max-w-[280px] sm:max-w-[420px] md:max-w-[500px] cursor-pointer group"
            >
              <span className="text-[14px] font-medium text-primary truncate group-hover:text-white">
                {title}
              </span>
              <ChevronDown
                className={`w-3.5 h-3.5 text-muted transition-transform duration-150 flex-shrink-0 ${
                  isTitleMenuOpen ? 'rotate-180 text-primary' : ''
                }`}
              />
            </button>
          )}

          {/* Title dropdown menu */}
          {isTitleMenuOpen && !isEditingTitle && (
            <div className="absolute top-full left-0 mt-1 w-56 bg-card border border-border rounded-xl shadow-2xl py-1.5 z-50 text-xs animate-in fade-in zoom-in-95">
              <button
                onClick={() => {
                  setIsEditingTitle(true);
                  setIsTitleMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-muted hover:text-primary hover:bg-border/30 transition-colors text-left cursor-pointer"
              >
                <Edit2 className="w-3.5 h-3.5 text-accent" />
                <span>Rename session</span>
              </button>
              <button
                onClick={() => {
                  onExportChat && onExportChat();
                  setIsTitleMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-muted hover:text-primary hover:bg-border/30 transition-colors text-left cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export transcript (JSON)</span>
              </button>
              <div className="h-[1px] bg-border/40 my-1" />
              <button
                onClick={() => {
                  onClearChat && onClearChat();
                  setIsTitleMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-error hover:bg-error/10 transition-colors text-left cursor-pointer"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Reset conversation</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Right: Runtime mode pill + Share/Export */}
      <div className="flex items-center gap-2.5 flex-shrink-0">
        {/* Mode pill */}
        <div className="relative" ref={modeMenuRef}>
          <button
            onClick={() => setIsModeMenuOpen(!isModeMenuOpen)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-card hover:bg-[#343330] border border-border/80 text-[12px] text-muted hover:text-primary transition-all cursor-pointer font-sans"
            title="Active Model Runtime"
          >
            <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
            <span className="font-mono text-[11px] text-primary/90">{currentMode}</span>
            <ChevronDown className="w-3 h-3 text-muted/80 ml-0.5" />
          </button>

          {isModeMenuOpen && (
            <div className="absolute top-full right-0 mt-1 w-64 bg-card border border-border rounded-xl shadow-2xl p-2 z-50 text-xs">
              <div className="px-2 py-1 text-[11px] font-mono text-muted uppercase tracking-wider">
                Execution Target
              </div>
              <div className="space-y-1 mt-1">
                {[
                  {
                    name: 'Cloud API · Multi-Provider',
                    desc: 'Groq + Google Gemini + NVIDIA NIM (Active)',
                    active: currentMode.includes('API') || currentMode.includes('Cloud') || currentMode.includes('Live'),
                  },
                  {
                    name: 'Local · Ollama',
                    desc: 'Local endpoint & model configuration',
                    active: currentMode.includes('Ollama'),
                  },
                ].map((item, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setCurrentMode(item.name);
                      setIsModeMenuOpen(false);
                      if (item.name.includes('Ollama') && onOpenSettings) {
                        onOpenSettings();
                      }
                    }}
                    className={`w-full flex items-start justify-between p-2 rounded-lg text-left transition-colors cursor-pointer ${
                      item.active ? 'bg-border/60 text-primary' : 'hover:bg-border/30 text-muted hover:text-primary'
                    }`}
                  >
                    <div>
                      <div className="font-medium text-[12.5px]">{item.name}</div>
                      <div className="text-[11px] text-muted">{item.desc}</div>
                    </div>
                    {item.active && <Check className="w-3.5 h-3.5 text-accent mt-0.5" />}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Share Button */}
        <button
          onClick={() => setIsShareModalOpen(true)}
          className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-card/70 transition-colors cursor-pointer"
          title="Share session"
        >
          <Share2 className="w-4 h-4" />
        </button>
      </div>

      {/* Share Modal Dialog */}
      {isShareModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl max-w-md w-full p-5 shadow-2xl animate-in fade-in zoom-in-95">
            <h3 className="text-[16px] font-semibold text-primary mb-1">Share Session</h3>
            <p className="text-xs text-muted leading-relaxed mb-4">
              Export or copy an interactive snapshot of this multi-agent run including thinking traces, tool outputs, and generated ML models.
            </p>

            <div className="flex items-center gap-2 bg-[#181716] border border-border/80 rounded-xl p-2 mb-4">
              <input
                type="text"
                readOnly
                value={window.location.href}
                className="bg-transparent border-none text-xs text-muted flex-1 font-mono focus:outline-none"
              />
              <button
                onClick={handleCopyShareLink}
                className="px-2.5 py-1 rounded-lg bg-accent text-white text-xs font-medium hover:bg-accent-hover transition-colors flex items-center gap-1 cursor-pointer"
              >
                {copiedLink ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                <span>{copiedLink ? 'Copied' : 'Copy'}</span>
              </button>
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setIsShareModalOpen(false)}
                className="px-4 py-1.5 rounded-lg text-xs text-muted hover:text-primary hover:bg-border/30 transition-colors cursor-pointer"
              >
                Close
              </button>
              <button
                onClick={() => {
                  onExportChat && onExportChat();
                  setIsShareModalOpen(false);
                }}
                className="px-4 py-1.5 rounded-lg bg-border/60 hover:bg-border text-xs text-primary font-medium transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download JSON</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

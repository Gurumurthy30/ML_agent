import React from 'react';
import {
  Plus,
  Bot,
  Wrench,
  Layers,
  FolderArchive,
  Settings,
  Folder,
  Pin,
  MessageSquare,
  Sparkles,
  ChevronRight,
  ExternalLink,
} from 'lucide-react';

export default function Sidebar({
  isOpen,
  activeNav = 'runs',
  onSelectNav,
  projects = [],
  pinnedSessions = [],
  recentSessions = [],
  currentSessionId,
  onSelectSession,
  onNewTask,
  user = { name: 'Gurumurthy', tier: 'Pro · Local GPU', avatar: 'G' },
}) {
  const primaryNavItems = [
    { id: 'agents', label: 'Agents', icon: Bot },
    { id: 'tools', label: 'Tools', icon: Wrench },
    { id: 'runs', label: 'Runs / Sessions', icon: Layers },
    { id: 'artifacts', label: 'Artifacts', icon: FolderArchive },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-30 w-[260px] bg-sidebar border-r border-border flex flex-col transition-transform duration-300 ease-claude select-none ${
        isOpen ? 'translate-x-0' : '-translate-x-full'
      } md:static md:translate-x-0 flex-shrink-0`}
    >
      {/* 1. Logo & App Wordmark */}
      <div className="p-3.5 pb-2">
        <div className="flex items-center gap-2.5 px-1 py-1 mb-3">
          {/* Logo Mark */}
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#DA7756] to-[#b85b3b] flex items-center justify-center shadow-md shadow-accent/20">
            <Sparkles className="w-4 h-4 text-[#FFFFFF]" strokeWidth={2.2} />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="font-semibold text-[15.5px] text-primary tracking-tight">
              ML Agent
            </span>
            <span className="text-[11px] font-mono text-muted/70 tracking-tight">
              v2.4
            </span>
          </div>
        </div>

        {/* New Task / New Chat Button */}
        <button
          onClick={onNewTask}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl border border-border bg-[#21201E] hover:bg-[#2A2926] hover:border-border-strong text-[13.5px] text-primary font-medium transition-all shadow-sm group cursor-pointer active:scale-[0.98]"
        >
          <Plus className="w-4 h-4 text-accent transition-transform group-hover:rotate-90 duration-200" />
          <span>New task</span>
        </button>
      </div>

      {/* 2. Primary Navigation List */}
      <div className="px-2 py-1 space-y-0.5">
        {primaryNavItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeNav === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectNav(item.id)}
              className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-all cursor-pointer ${
                isActive
                  ? 'border-l-2 border-accent text-primary bg-card/40 font-medium pl-[10px]'
                  : 'text-muted hover:text-primary hover:bg-card/30 font-normal'
              }`}
            >
              <Icon
                className={`w-4 h-4 ${
                  isActive ? 'text-accent' : 'text-muted/80'
                }`}
              />
              <span className="flex-1 text-left">{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* Scrollable Center Section */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-4">
        {/* 3. Projects / Workspaces */}
        <div>
          <div className="flex items-center justify-between px-3 py-1 text-[11px] font-medium text-muted/70 uppercase tracking-wider">
            <span>Workspaces</span>
            <span className="text-[10px] font-mono">{projects.length}</span>
          </div>
          <div className="space-y-0.5 mt-0.5">
            {projects.map((proj) => (
              <button
                key={proj.id}
                className="w-full flex items-center gap-2 px-3 py-1.5 rounded-md text-xs text-muted hover:text-primary hover:bg-card/30 transition-colors text-left truncate cursor-pointer group"
              >
                <Folder className="w-3.5 h-3.5 text-muted/70 group-hover:text-accent transition-colors flex-shrink-0" />
                <span className="truncate flex-1">{proj.name}</span>
                <span className="text-[10px] text-muted/50 font-mono">
                  {proj.chatsCount}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* 4. Pinned Runs */}
        {pinnedSessions.length > 0 && (
          <div>
            <div className="flex items-center justify-between px-3 py-1 text-[11px] font-medium text-muted/70 uppercase tracking-wider">
              <span className="flex items-center gap-1.5">
                <Pin className="w-3 h-3 text-accent" />
                Pinned
              </span>
            </div>
            <div className="space-y-0.5 mt-0.5">
              {pinnedSessions.map((session) => {
                const isSelected = currentSessionId === session.id;
                return (
                  <button
                    key={session.id}
                    onClick={() => onSelectSession(session.id)}
                    className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-md text-xs transition-all text-left truncate cursor-pointer ${
                      isSelected
                        ? 'border-l-2 border-accent text-primary bg-card/50 font-medium pl-[10px]'
                        : 'text-muted hover:text-primary hover:bg-card/30'
                    }`}
                    title={session.title}
                  >
                    <span className="truncate flex-1">{session.title}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* 5. Recent Chats / Task Runs */}
        <div>
          <div className="px-3 py-1 text-[11px] font-medium text-muted/70 uppercase tracking-wider">
            Recent
          </div>
          <div className="space-y-0.5 mt-0.5">
            {recentSessions.map((session) => {
              const isSelected = currentSessionId === session.id;
              return (
                <button
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  className={`w-full flex items-center gap-2 px-3 py-1.5 rounded-md text-xs transition-all text-left truncate cursor-pointer ${
                    isSelected
                      ? 'border-l-2 border-accent text-primary bg-card/50 font-medium pl-[10px]'
                      : 'text-muted hover:text-primary hover:bg-card/30'
                  }`}
                  title={session.title}
                >
                  <MessageSquare className="w-3 h-3 text-muted/60 flex-shrink-0" />
                  <span className="truncate flex-1">{session.title}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* 6. User Account Row (Pinned Bottom) */}
      <div className="p-2.5 border-t border-border bg-sidebar/95">
        <div className="flex items-center gap-2.5 p-1.5 rounded-xl hover:bg-card/50 transition-colors cursor-pointer group">
          {/* Avatar Circle */}
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[#3A3936] to-[#4A4844] border border-border flex items-center justify-center text-xs font-semibold text-primary">
            {user.avatar || 'G'}
          </div>
          {/* User Info */}
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium text-primary truncate group-hover:text-white">
              {user.name}
            </div>
            <div className="text-[11px] text-muted truncate font-sans">
              {user.tier}
            </div>
          </div>
          <ChevronRight className="w-3.5 h-3.5 text-muted/60 group-hover:text-primary transition-colors" />
        </div>
      </div>
    </aside>
  );
}

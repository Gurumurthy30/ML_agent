import React, { useState, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import ChatThread from './components/ChatThread';
import MessageInput from './components/MessageInput';
import AgentsModal from './components/AgentsModal';
import ToolsModal from './components/ToolsModal';
import ArtifactsModal from './components/ArtifactsModal';
import SettingsModal from './components/SettingsModal';
import { useAgentSession } from './hooks/useAgentSession';

const createSessionId = () => 'session_' + Math.random().toString(36).slice(2, 10);

export default function App() {
  const [sessions, setSessions] = useState(() => {
    const initialId = createSessionId();
    return [
      {
        id: initialId,
        title: 'New ML Task',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ];
  });

  const [currentSessionId, setCurrentSessionId] = useState(() => sessions[0].id);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [activeNav, setActiveNav] = useState('runs');

  // Modals state
  const [isAgentsModalOpen, setIsAgentsModalOpen] = useState(false);
  const [isToolsModalOpen, setIsToolsModalOpen] = useState(false);
  const [isArtifactsModalOpen, setIsArtifactsModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);

  // Live WebSocket session connection
  const {
    messages,
    isConnected,
    isRunning,
    activeNode,
    pendingHumanQuestion,
    experiments,
    uploadFile,
    sendMessage,
    clearMessages,
  } = useAgentSession(currentSessionId);

  const currentSession = sessions.find((s) => s.id === currentSessionId) || {
    id: currentSessionId,
    title: 'New ML Task',
  };

  // Update session title after first message if it's default
  const handleSendMessage = useCallback(
    ({ content, attachments = [], attachmentDetails = [] }) => {
      if (currentSession.title === 'New ML Task' && content) {
        const autoTitle = content.slice(0, 32).trim() + (content.length > 32 ? '…' : '');
        setSessions((prev) =>
          prev.map((s) => (s.id === currentSessionId ? { ...s, title: autoTitle } : s))
        );
      }
      sendMessage({ content, attachments, attachmentDetails });
    },
    [currentSession.title, currentSessionId, sendMessage]
  );

  const handleSelectNav = (navId) => {
    setActiveNav(navId);
    if (navId === 'agents') setIsAgentsModalOpen(true);
    else if (navId === 'tools') setIsToolsModalOpen(true);
    else if (navId === 'artifacts') setIsArtifactsModalOpen(true);
    else if (navId === 'settings') setIsSettingsModalOpen(true);
  };

  const handleSelectSession = (sessionId) => {
    setCurrentSessionId(sessionId);
    setActiveNav('runs');
  };

  const handleNewTask = () => {
    const newId = createSessionId();
    const newSession = {
      id: newId,
      title: 'New ML Task',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setSessions((prev) => [newSession, ...prev]);
    setCurrentSessionId(newId);
    setActiveNav('runs');
  };

  const handleRenameTitle = (newTitle) => {
    setSessions((prev) =>
      prev.map((s) => (s.id === currentSessionId ? { ...s, title: newTitle } : s))
    );
  };

  const handleClearChat = () => {
    clearMessages();
  };

  const handleExportChat = () => {
    const transcript = {
      session_id: currentSessionId,
      title: currentSession.title,
      exported_at: new Date().toISOString(),
      messages,
      experiments,
    };
    const dataStr =
      'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(transcript, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute(
      'download',
      `${currentSession.title.replace(/[\s/\\?%*:|"<>]+/g, '_')}_transcript.json`
    );
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  // Derive observed tool calls map from live messages for ToolsModal
  const observedToolCalls = messages.reduce((acc, m) => {
    if ((m.type === 'tool_call' || m.type === 'tool_result') && m.tool) {
      acc[m.tool] = (acc[m.tool] || 0) + 1;
    }
    return acc;
  }, {});

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-shell text-primary antialiased font-sans">
      {/* 1. Left Sidebar */}
      <Sidebar
        isOpen={isSidebarOpen}
        activeNav={activeNav}
        onSelectNav={handleSelectNav}
        projects={[]}
        pinnedSessions={[]}
        recentSessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewTask={handleNewTask}
      />

      {/* 2. Main Chat Panel */}
      <div className="flex-1 flex flex-col min-w-0 bg-chat relative overflow-hidden">
        {/* Top bar */}
        <TopBar
          title={currentSession.title}
          mode={isConnected ? 'Cloud API · Multi-Provider' : 'Connecting…'}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          onRenameTitle={handleRenameTitle}
          onClearChat={handleClearChat}
          onExportChat={handleExportChat}
          onOpenSettings={() => setIsSettingsModalOpen(true)}
        />

        {/* Message Thread (Renders empty state or live event stream) */}
        <ChatThread
          messages={messages}
          isRunning={isRunning}
          activeNode={activeNode}
          pendingHumanQuestion={pendingHumanQuestion}
          onSendMessage={handleSendMessage}
          uploadFile={uploadFile}
          sessionId={currentSessionId}
        />

        {/* Sticky Message Input at bottom (only visible when there are messages in the thread) */}
        {messages.length > 0 && (
          <MessageInput
            onSendMessage={handleSendMessage}
            uploadFile={uploadFile}
            isGenerating={isRunning}
            placeholder={
              pendingHumanQuestion ? 'Type your clarification reply…' : 'Message the agent…'
            }
          />
        )}
      </div>

      {/* Modals */}
      <AgentsModal
        isOpen={isAgentsModalOpen}
        onClose={() => {
          setIsAgentsModalOpen(false);
          setActiveNav('runs');
        }}
      />
      <ToolsModal
        isOpen={isToolsModalOpen}
        observedToolCalls={observedToolCalls}
        onClose={() => {
          setIsToolsModalOpen(false);
          setActiveNav('runs');
        }}
      />
      <ArtifactsModal
        isOpen={isArtifactsModalOpen}
        sessionId={currentSessionId}
        experiments={experiments}
        onClose={() => {
          setIsArtifactsModalOpen(false);
          setActiveNav('runs');
        }}
      />
      <SettingsModal
        isOpen={isSettingsModalOpen}
        onClose={() => {
          setIsSettingsModalOpen(false);
          setActiveNav('runs');
        }}
      />
    </div>
  );
}

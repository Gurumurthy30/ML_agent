import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import ChatThread from './components/ChatThread';
import MessageInput from './components/MessageInput';
import AgentsModal from './components/AgentsModal';
import ToolsModal from './components/ToolsModal';
import ArtifactsModal from './components/ArtifactsModal';
import SettingsModal from './components/SettingsModal';
import {
  INITIAL_CONVERSATIONS,
  MOCK_PROJECTS,
  MOCK_PINNED_SESSIONS,
  MOCK_RECENT_SESSIONS,
} from './data/mockData';

export default function App() {
  const [conversations, setConversations] = useState(INITIAL_CONVERSATIONS);
  const [currentSessionId, setCurrentSessionId] = useState('session-rainfall');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [activeNav, setActiveNav] = useState('runs');

  // Modals state
  const [isAgentsModalOpen, setIsAgentsModalOpen] = useState(false);
  const [isToolsModalOpen, setIsToolsModalOpen] = useState(false);
  const [isArtifactsModalOpen, setIsArtifactsModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);

  // Live generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [activeStatusText, setActiveStatusText] = useState('');

  const currentSession = conversations[currentSessionId] || {
    id: currentSessionId,
    title: 'New Session',
    mode: 'Local · Ollama',
    messages: [],
  };

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
    const newId = `session-${Date.now()}`;
    const newSession = {
      id: newId,
      title: 'New ML Task',
      mode: 'Local · Ollama',
      messages: [
        {
          id: `msg-${Date.now()}`,
          sender: 'assistant',
          timestamp: 'Just now',
          agents: ['ML Agent'],
          thinking: {
            summary: 'Initialized workspace and mounted local Python 3.11 environment',
            duration: 'Thought for 2s',
            trace: [
              'Environment ready: LightGBM, XGBoost, Scikit-Learn, Polars available.',
              'Awaiting dataset upload or problem formulation from user.'
            ]
          },
          prose: `Welcome to **ML Agent Studio**.

Upload your dataset or specify your prediction objective. The agent swarm will autonomously:
1. Profile schema, null values, and class balance
2. Configure 5-fold cross validation with proper metric optimization
3. Train the model inside the local sandbox
4. Produce a **downloadable model artifact** with ready-to-run inference code.`
        }
      ]
    };

    setConversations((prev) => ({
      ...prev,
      [newId]: newSession,
    }));
    setCurrentSessionId(newId);
    setActiveNav('runs');
  };

  const handleRenameTitle = (newTitle) => {
    setConversations((prev) => ({
      ...prev,
      [currentSessionId]: {
        ...prev[currentSessionId],
        title: newTitle,
      },
    }));
  };

  const handleClearChat = () => {
    setConversations((prev) => ({
      ...prev,
      [currentSessionId]: {
        ...prev[currentSessionId],
        messages: [],
      },
    }));
  };

  const handleExportChat = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(currentSession, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `${currentSession.title.replace(/\s+/g, '_')}_transcript.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  // User sends message -> Linear Assistant Response with Deliverable
  const handleSendMessage = ({ content, attachments }) => {
    const userMsgId = `msg-u-${Date.now()}`;
    const userMsg = {
      id: userMsgId,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      content,
      attachments,
    };

    // Append user message on right side
    setConversations((prev) => ({
      ...prev,
      [currentSessionId]: {
        ...prev[currentSessionId],
        messages: [...(prev[currentSessionId]?.messages || []), userMsg],
      },
    }));

    setIsGenerating(true);
    setActiveStatusText('Profiling dataset and decomposing pipeline tasks...');

    // Progress status update
    setTimeout(() => {
      setActiveStatusText('Executing 5-Fold Stratified LightGBM in sandbox container...');
    }, 1200);

    // Complete response generation
    setTimeout(() => {
      const isRainfall = content.toLowerCase().includes('rain') || attachments?.some(a => a.name.includes('rain') || a.name.includes('train'));
      const targetName = isRainfall ? 'rainfall' : 'target';
      const modelFileName = isRainfall ? 'rainfall_lightgbm_v2.booster' : 'model_optimized_v1.booster';

      const assistantMsgId = `msg-a-${Date.now()}`;
      const assistantMsg = {
        id: assistantMsgId,
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        agents: ['Planner Agent', 'Coder Agent', 'Evaluator Agent'],
        thinking: {
          summary: `Decomposed instructions, verified 5-fold cross-validation scheme for target "${targetName}"`,
          duration: 'Thought for 9s',
          trace: [
            `1. Prompt: "${content.slice(0, 80)}${content.length > 80 ? '...' : ''}"`,
            `2. Attached files: ${attachments?.map(a => a.name).join(', ') || 'reusing active session data'}.`,
            '3. Configured StratifiedKFold validation with early stopping on log-loss to avoid overfitting.',
            `4. Serialized trained model weights to ${modelFileName} and verified single-sample inference latency.`
          ]
        },
        toolCalls: {
          summary: 'Ran 2 MCP tools (local_env execution, profiler)',
          calls: [
            {
              id: `call-${Date.now()}-1`,
              tool: 'local_env_mcp.run_python',
              args: { script: 'train_model.py', target: targetName, folds: 5 },
              duration: '3.4s',
              status: 'success',
              result: `Process exited with code 0. Serialized weights to ./${modelFileName}`
            }
          ]
        },
        prose: `I have trained and evaluated an updated **5-Fold Stratified LightGBM Pipeline** tailored to your dataset.

### Pipeline Highlights:
* **Validation Strategy**: Stratified 5-Fold Cross Validation ensuring balanced out-of-fold probability calibration.
* **Feature Handling**: Automated median imputation for missing weather features and target encoding for categorical columns.
* **Convergence**: All 5 folds converged within 180 iterations without numerical instability.`,
        terminalCard: {
          id: `term-${Date.now()}`,
          title: 'Live Sandbox Log — train_model.py',
          language: 'python',
          lines: [
            `$ python train_model.py --target ${targetName} --folds 5 --seed 42`,
            `[INFO] Ingested dataset with target: "${targetName}" (Binary Classification)`,
            '[TRAIN] Fold 1/5: Early stopping at iter 148 — Val ROC-AUC: 0.8945 | F1: 0.824',
            '[TRAIN] Fold 2/5: Early stopping at iter 162 — Val ROC-AUC: 0.8978 | F1: 0.829',
            '[TRAIN] Fold 3/5: Early stopping at iter 141 — Val ROC-AUC: 0.8910 | F1: 0.818',
            '[TRAIN] Fold 4/5: Early stopping at iter 158 — Val ROC-AUC: 0.8992 | F1: 0.831',
            '[TRAIN] Fold 5/5: Early stopping at iter 150 — Val ROC-AUC: 0.8960 | F1: 0.826',
            '[SUCCESS] 5-Fold Mean ROC-AUC: 0.8957 (±0.0028) | Mean F1: 0.8256',
            `[SUCCESS] Model serialized -> ./${modelFileName} (4.2 MB)`
          ]
        },
        artifact: {
          name: modelFileName,
          filename: modelFileName,
          type: 'LightGBM Binary Classifier',
          size: '4.2 MB',
          description: `Deliverable booster trained on "${targetName}" with 5-fold cross-validation.`,
          metrics: {
            'ROC-AUC': '0.8957',
            'F1-Score': '0.8256',
            'Latency': '1.3ms',
            'Folds': '5-Fold CV'
          },
          codeSnippet: `import lightgbm as lgb
import pandas as pd

# Load the deliverable booster
model = lgb.Booster(model_file="${modelFileName}")

# Predict on new test sample
sample = pd.DataFrame([{ "humidity_3pm": 81.0, "pressure_3pm": 1009.1 }])
prob = model.predict(sample)[0]
print(f"Predicted Probability: {prob:.2%}")`
        },
        closingProse: `Click **Download (.booster)** above to download the model file directly to your machine. You can also view the Python inference code or export to ONNX runtime.`
      };

      setConversations((prev) => ({
        ...prev,
        [currentSessionId]: {
          ...prev[currentSessionId],
          messages: [...(prev[currentSessionId]?.messages || []), assistantMsg],
        },
      }));

      setIsGenerating(false);
      setActiveStatusText('');
    }, 2200);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-shell text-primary antialiased font-sans">
      {/* 1. Left Sidebar */}
      <Sidebar
        isOpen={isSidebarOpen}
        activeNav={activeNav}
        onSelectNav={handleSelectNav}
        projects={MOCK_PROJECTS}
        pinnedSessions={MOCK_PINNED_SESSIONS}
        recentSessions={MOCK_RECENT_SESSIONS}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewTask={handleNewTask}
      />

      {/* 2. Main Chat Panel */}
      <div className="flex-1 flex flex-col min-w-0 bg-chat relative overflow-hidden">
        {/* Top bar */}
        <TopBar
          title={currentSession.title}
          mode={currentSession.mode || 'Local · Ollama'}
          isSidebarOpen={isSidebarOpen}
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          onRenameTitle={handleRenameTitle}
          onClearChat={handleClearChat}
          onExportChat={handleExportChat}
        />

        {/* Message Thread (Linear by time) */}
        <ChatThread
          messages={currentSession.messages}
          isGenerating={isGenerating}
          activeStatusText={activeStatusText}
        />

        {/* Sticky Message Input */}
        <MessageInput
          onSendMessage={handleSendMessage}
          isGenerating={isGenerating}
        />
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
        onClose={() => {
          setIsToolsModalOpen(false);
          setActiveNav('runs');
        }}
      />
      <ArtifactsModal
        isOpen={isArtifactsModalOpen}
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

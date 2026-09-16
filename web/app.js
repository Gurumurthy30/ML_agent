/**
 * Multi-Agent ML Pipeline UI
 * Claude.ai-style live monitoring and interactive orchestration.
 */

// Application State
let currentRunId = null;
let currentEventSource = null;
let activeTurnCards = {}; // agentName -> element
let activeCoderAttempts = {}; // agentName -> container
let activeThinkingSections = {}; // agentName -> { element, text }
let activeStreamingTarget = null;
let isUserScrolledUp = false;
let traceEvents = [];

// DOM Elements
const feedContainer = document.getElementById('feed-container');
const turnsFeed = document.getElementById('turns-feed');
const configCard = document.getElementById('config-card');
const runConfigForm = document.getElementById('run-config-form');
const datasetInput = document.getElementById('dataset-input');
const modeSelect = document.getElementById('mode-select');
const guidedModeToggle = document.getElementById('guided-mode-toggle');
const startRunBtn = document.getElementById('start-run-btn');
const newRunBtn = document.getElementById('new-run-btn');
const runsList = document.getElementById('runs-list');
const refreshRunsBtn = document.getElementById('refresh-runs-btn');
const headerRunId = document.getElementById('header-run-id');
const headerRunStatusPill = document.getElementById('header-run-status-pill');
const scrollBottomContainer = document.getElementById('scroll-bottom-container');
const scrollDownBtn = document.getElementById('scroll-down-btn');
const themeToggleBtn = document.getElementById('theme-toggle-btn');
const themeIcon = document.getElementById('theme-icon');
const themeLabel = document.getElementById('theme-label');
const toggleTraceBtn = document.getElementById('toggle-trace-btn');
const closeTraceBtn = document.getElementById('close-trace-btn');
const rightDrawer = document.getElementById('right-drawer');
const traceTimeline = document.getElementById('trace-timeline');

// Agent display metadata
const AGENT_META = {
  supervisor: { label: 'Supervisor', role: 'Orchestrator', icon: '🧠', color: 'bg-purple-100 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300' },
  profiler: { label: 'Profiler Specialist', role: 'Data Profiling', icon: '📊', color: 'bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300' },
  profiler_agent: { label: 'Profiler Specialist', role: 'Data Profiling', icon: '📊', color: 'bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300' },
  eda_agent: { label: 'EDA Specialist', role: 'Exploratory Analysis', icon: '🔍', color: 'bg-cyan-100 dark:bg-cyan-950/40 text-cyan-700 dark:text-cyan-300' },
  features: { label: 'Feature Engineer', role: 'Transformation & Diff', icon: '⚡', color: 'bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300' },
  features_agent: { label: 'Feature Engineer', role: 'Transformation & Diff', icon: '⚡', color: 'bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300' },
  modeler: { label: 'Model Trainer', role: 'Candidate Selection', icon: '🤖', color: 'bg-indigo-100 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300' },
  modeler_agent: { label: 'Model Trainer', role: 'Candidate Selection', icon: '🤖', color: 'bg-indigo-100 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300' },
  judge: { label: 'Quality Judge', role: 'Evaluation & Verdict', icon: '⚖️', color: 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300' },
  judge_agent: { label: 'Quality Judge', role: 'Evaluation & Verdict', icon: '⚖️', color: 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300' },
  human_approval: { label: 'Human Review', role: 'Interactive Gate', icon: '👤', color: 'bg-orange-100 dark:bg-orange-950/40 text-orange-700 dark:text-orange-300' },
  reporter: { label: 'Final Reporter', role: 'Synthesis & Metrics', icon: '📝', color: 'bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300' },
  reporter_agent: { label: 'Final Reporter', role: 'Synthesis & Metrics', icon: '📝', color: 'bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300' },
  coder_agent: { label: 'Coder Sub-Agent', role: 'Code Generation & Exec', icon: '💻', color: 'bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300' },
};

function getAgentMeta(name) {
  if (!name) return { label: 'System Agent', role: 'Pipeline', icon: '⚙️', color: 'bg-stone-100 dark:bg-zinc-800 text-stone-700' };
  const cleanName = name.replace(/\(.*\)/, '').trim().toLowerCase();
  return AGENT_META[cleanName] || AGENT_META[name] || { label: name, role: 'Specialist', icon: '🤖', color: 'bg-stone-100 dark:bg-zinc-800 text-stone-700' };
}

// --------------------------------------------------------------------------
// Theme & UI Initialization
// --------------------------------------------------------------------------

function initTheme() {
  const savedTheme = localStorage.getItem('theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
    document.documentElement.classList.add('dark');
    themeIcon.textContent = '☀️';
    themeLabel.textContent = 'Light Mode';
  } else {
    document.documentElement.classList.remove('dark');
    themeIcon.textContent = '🌙';
    themeLabel.textContent = 'Dark Mode';
  }
}

themeToggleBtn.addEventListener('click', () => {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  themeIcon.textContent = isDark ? '☀️' : '🌙';
  themeLabel.textContent = isDark ? 'Light Mode' : 'Dark Mode';
});

// Quick chips handler
document.querySelectorAll('.quick-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    datasetInput.value = chip.getAttribute('data-path');
  });
});

// Trace drawer toggle
toggleTraceBtn.addEventListener('click', () => {
  rightDrawer.classList.toggle('hidden');
});
closeTraceBtn.addEventListener('click', () => {
  rightDrawer.classList.add('hidden');
});

// --------------------------------------------------------------------------
// Auto-Scroll Handling (Claude Pattern)
// --------------------------------------------------------------------------

feedContainer.addEventListener('scroll', () => {
  const threshold = 80;
  const isNearBottom = feedContainer.scrollHeight - feedContainer.scrollTop - feedContainer.clientHeight < threshold;
  if (isNearBottom) {
    isUserScrolledUp = false;
    scrollBottomContainer.classList.add('hidden');
  } else {
    isUserScrolledUp = true;
    scrollBottomContainer.classList.remove('hidden');
  }
});

scrollDownBtn.addEventListener('click', () => {
  isUserScrolledUp = false;
  scrollBottomContainer.classList.add('hidden');
  feedContainer.scrollTo({ top: feedContainer.scrollHeight, behavior: 'smooth' });
});

function scrollToBottomIfNeeded() {
  if (!isUserScrolledUp) {
    feedContainer.scrollTo({ top: feedContainer.scrollHeight, behavior: 'smooth' });
  }
}

// --------------------------------------------------------------------------
// Past Runs Management
// --------------------------------------------------------------------------

async function fetchRecentRuns() {
  try {
    const res = await fetch('/api/runs');
    if (!res.ok) return;
    const runs = await res.json();
    renderRunsList(runs);
  } catch (err) {
    console.error('Failed to fetch past runs:', err);
  }
}

function renderRunsList(runs) {
  if (!runs || runs.length === 0) {
    runsList.innerHTML = '<div class="p-3 text-center text-xs text-stone-400 dark:text-stone-500 italic">No past runs recorded</div>';
    return;
  }

  runsList.innerHTML = '';
  runs.slice().reverse().forEach(run => {
    const btn = document.createElement('button');
    const isCurrent = run.run_id === currentRunId;
    btn.className = `w-full text-left p-2.5 rounded-xl border text-xs transition-all ${
      isCurrent
        ? 'bg-stone-200/70 dark:bg-zinc-700/60 border-stone-300 dark:border-zinc-600 font-medium'
        : 'bg-white/60 dark:bg-[#202024]/60 hover:bg-stone-100 dark:hover:bg-zinc-800 border-stone-200/60 dark:border-zinc-800 text-stone-600 dark:text-stone-300'
    }`;

    let statusPill = '<span class="w-2 h-2 rounded-full bg-stone-400"></span>';
    if (run.status === 'running') statusPill = '<span class="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>';
    else if (run.status === 'paused_for_approval') statusPill = '<span class="w-2 h-2 rounded-full bg-amber-500"></span>';
    else if (run.status === 'completed') statusPill = '<span class="w-2 h-2 rounded-full bg-emerald-500"></span>';
    else if (run.status === 'error') statusPill = '<span class="w-2 h-2 rounded-full bg-red-500"></span>';

    const datasetName = run.dataset_path ? run.dataset_path.split(/[\\/]/).pop() : 'dataset';
    btn.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2 truncate">
          ${statusPill}
          <span class="font-mono text-[11px] truncate">${run.run_id.slice(0, 12)}...</span>
        </div>
        <span class="text-[10px] text-stone-400 uppercase">${run.mode === 'eda_only' ? 'EDA' : 'Full'}</span>
      </div>
      <div class="text-[10px] text-stone-400 dark:text-stone-500 mt-1 truncate pl-4">
        📄 ${datasetName}
      </div>
    `;

    btn.addEventListener('click', () => {
      loadRunDetails(run.run_id, run.status);
    });
    runsList.appendChild(btn);
  });
}

refreshRunsBtn.addEventListener('click', fetchRecentRuns);

newRunBtn.addEventListener('click', () => {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  currentRunId = null;
  headerRunId.textContent = 'New Pipeline Run';
  headerRunStatusPill.className = 'hidden';
  turnsFeed.innerHTML = '';
  configCard.classList.remove('hidden');
  feedContainer.scrollTo({ top: 0, behavior: 'smooth' });
  fetchRecentRuns();
});

// --------------------------------------------------------------------------
// Run Execution & SSE Connection
// --------------------------------------------------------------------------

runConfigForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const datasetPath = datasetInput.value.trim();
  const mode = modeSelect.value;
  const guidedMode = guidedModeToggle.checked;

  if (!datasetPath) {
    alert('Please specify a dataset path.');
    return;
  }

  startRunBtn.disabled = true;
  startRunBtn.innerHTML = `
    <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
    </svg>
    <span>Initializing Pipeline...</span>
  `;

  try {
    const res = await fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_path: datasetPath,
        mode: mode,
        guided_mode: guidedMode,
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to start run');
    }

    const data = await res.json();
    currentRunId = data.run_id;

    // Reset feed and active maps
    turnsFeed.innerHTML = '';
    activeTurnCards = {};
    activeCoderAttempts = {};
    activeThinkingSections = {};
    activeStreamingTarget = null;
    traceEvents = [];
    traceTimeline.innerHTML = '';

    // Update Header
    updateHeaderStatus(currentRunId, 'running');
    fetchRecentRuns();

    // Connect to SSE stream
    connectToRunStream(currentRunId);

  } catch (err) {
    alert(`Error: ${err.message}`);
  } finally {
    startRunBtn.disabled = false;
    startRunBtn.innerHTML = `
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <span>Run Pipeline</span>
    `;
  }
});

function updateHeaderStatus(runId, status) {
  headerRunId.textContent = runId || 'No active run';
  headerRunStatusPill.classList.remove('hidden');

  if (status === 'running') {
    headerRunStatusPill.className = 'px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-100 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 animate-pulse-subtle';
    headerRunStatusPill.textContent = 'Running';
  } else if (status === 'paused_for_approval') {
    headerRunStatusPill.className = 'px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 dark:bg-amber-950/50 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800';
    headerRunStatusPill.textContent = 'Awaiting Approval';
  } else if (status === 'completed') {
    headerRunStatusPill.className = 'px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800';
    headerRunStatusPill.textContent = 'Completed';
  } else if (status === 'error') {
    headerRunStatusPill.className = 'px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-100 dark:bg-red-950/50 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800';
    headerRunStatusPill.textContent = 'Error';
  }
}

function connectToRunStream(runId) {
  if (currentEventSource) {
    currentEventSource.close();
  }

  const sse = new EventSource(`/api/runs/${runId}/stream`);
  currentEventSource = sse;

  sse.onmessage = (e) => {
    if (!e.data || e.data === ': ping') return;
    try {
      const evt = JSON.parse(e.data);
      handlePipelineEvent(evt);
    } catch (err) {
      console.error('Error parsing SSE event:', err, e.data);
    }
  };

  sse.onerror = (err) => {
    console.warn('SSE stream closed or encountered an error:', err);
    sse.close();
    fetchRecentRuns();
  };
}

async function loadRunDetails(runId, status) {
  currentRunId = runId;
  updateHeaderStatus(runId, status);

  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  turnsFeed.innerHTML = '';
  activeTurnCards = {};
  activeCoderAttempts = {};
  activeThinkingSections = {};

  if (status === 'running' || status === 'paused_for_approval') {
    connectToRunStream(runId);
  } else {
    // Completed or error run: fetch report
    try {
      const res = await fetch(`/api/runs/${runId}/report`);
      if (res.ok) {
        const data = await res.json();
        if (data.report) {
          renderFinalReportCard({ report: data.report, artifact_path: data.artifact_path, run_id: runId });
        }
      }
    } catch (err) {
      console.error('Failed to load run report:', err);
    }
  }
  fetchRecentRuns();
}

// --------------------------------------------------------------------------
// Core Event Dispatcher
// --------------------------------------------------------------------------

function handlePipelineEvent(evt) {
  const type = evt.type || evt.event;
  const agent = evt.agent || evt.node || 'system';

  // Add to chronological trace drawer
  if (type === 'step_start' || type === 'step_end' || type === 'step_error') {
    addTraceStep(evt);
  }

  switch (type) {
    case 'profile_ready':
      handleProfileReady(evt);
      break;

    case 'supervisor_routed':
      handleSupervisorRouted(evt);
      break;

    case 'node_start':
      handleNodeStart(evt);
      break;

    case 'node_end':
      handleNodeEnd(evt);
      break;

    case 'token':
      handleToken(evt);
      break;

    case 'loop_decision':
      handleLoopDecision(evt);
      break;

    case 'run_memory_lookup':
      handleRunMemoryLookup(evt);
      break;

    case 'attempt_result':
      handleAttemptResult(evt);
      break;

    case 'judge_verdict':
      handleJudgeVerdict(evt);
      break;

    case 'approval_required':
      handleApprovalRequired(evt);
      break;

    case 'report_ready':
      handleReportReady(evt);
      break;

    case 'run_complete':
      handleRunComplete(evt);
      break;

    case 'run_error':
      handleRunError(evt);
      break;

    default:
      // Pass-through handler for any specialist events
      break;
  }

  scrollToBottomIfNeeded();
}

// --------------------------------------------------------------------------
// Turn Card Creation & Management
// --------------------------------------------------------------------------

function getOrCreateTurnCard(agentName) {
  const meta = getAgentMeta(agentName);
  const cardKey = `${agentName}_${Date.now()}`;

  // If there's an already active card for this node that is still "running", reuse it
  if (activeTurnCards[agentName]) {
    return activeTurnCards[agentName];
  }

  const card = document.createElement('article');
  card.className = 'bg-white dark:bg-[#202024] border border-stone-200/80 dark:border-zinc-800/90 rounded-2xl shadow-sm p-5 space-y-4 animate-card-in';
  card.id = `turn-${cardKey}`;

  card.innerHTML = `
    <!-- Card Header Row -->
    <div class="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-zinc-800/60">
      <div class="flex items-center space-x-3">
        <span class="w-8 h-8 rounded-xl flex items-center justify-center text-sm shadow-sm ${meta.color}">
          ${meta.icon}
        </span>
        <div>
          <div class="flex items-center space-x-2">
            <h3 class="text-sm font-semibold text-stone-900 dark:text-stone-100">${meta.label}</h3>
            <span class="status-pill inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-stone-100 dark:bg-zinc-800 text-stone-600 dark:text-stone-300">
              <span class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse mr-1.5"></span>
              Running
            </span>
          </div>
          <p class="text-[11px] text-stone-400 dark:text-stone-500">${meta.role}</p>
        </div>
      </div>
      <div class="text-right">
        <span class="duration-pill text-[11px] font-mono text-stone-400">0.0s</span>
      </div>
    </div>

    <!-- Thinking Block (Claude Style - Collapsible) -->
    <div class="thinking-container hidden space-y-2">
      <button type="button" class="thinking-toggle w-full flex items-center justify-between px-3 py-1.5 rounded-lg bg-stone-50 dark:bg-zinc-800/50 hover:bg-stone-100 dark:hover:bg-zinc-800 text-stone-500 dark:text-stone-400 text-xs transition-colors">
        <div class="flex items-center space-x-2">
          <svg class="chevron-rotate w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
          </svg>
          <span class="font-medium text-stone-700 dark:text-stone-300">Thinking</span>
          <span class="thinking-preview text-[11px] text-stone-400 italic truncate max-w-xs"></span>
        </div>
        <span class="thinking-badge text-[10px] px-1.5 py-0.5 rounded bg-stone-200/60 dark:bg-zinc-700/60 text-stone-600 dark:text-stone-300">Reasoning</span>
      </button>
      <div class="thinking-content hidden px-3.5 py-3 rounded-xl bg-stone-50/80 dark:bg-zinc-900/50 border border-stone-200/50 dark:border-zinc-800 text-xs text-stone-600 dark:text-stone-400 italic leading-relaxed whitespace-pre-wrap font-mono"></div>
    </div>

    <!-- Primary Content Area -->
    <div class="card-content-area space-y-3 text-xs text-stone-800 dark:text-stone-200"></div>
  `;

  // Wire up thinking toggle
  const thinkingToggle = card.querySelector('.thinking-toggle');
  const thinkingContent = card.querySelector('.thinking-content');
  const chevron = card.querySelector('.chevron-rotate');

  thinkingToggle.addEventListener('click', () => {
    const isHidden = thinkingContent.classList.contains('hidden');
    if (isHidden) {
      thinkingContent.classList.remove('hidden');
      chevron.classList.add('expanded');
    } else {
      thinkingContent.classList.add('hidden');
      chevron.classList.remove('expanded');
    }
  });

  card.startTime = performance.now();
  turnsFeed.appendChild(card);
  activeTurnCards[agentName] = card;

  return card;
}

function handleNodeStart(evt) {
  const node = evt.node || evt.agent;
  const card = getOrCreateTurnCard(node);
  card.startTime = performance.now();
  const statusPill = card.querySelector('.status-pill');
  if (statusPill) {
    statusPill.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse mr-1.5"></span>Running';
  }
}

function handleSupervisorRouted(evt) {
  const card = getOrCreateTurnCard('supervisor');
  const contentArea = card.querySelector('.card-content-area');
  const nextMeta = getAgentMeta(evt.next_agent);

  const routeBox = document.createElement('div');
  routeBox.className = 'p-3.5 rounded-xl border border-purple-200/80 dark:border-purple-900/50 bg-purple-50/40 dark:bg-purple-950/20 space-y-2.5';
  routeBox.innerHTML = `
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-2">
        <span class="text-xs font-semibold text-purple-900 dark:text-purple-200">Routing Decision:</span>
        <span class="px-2.5 py-0.5 rounded-full text-xs font-bold ${nextMeta.color}">
          ${nextMeta.icon} Next: ${nextMeta.label}
        </span>
      </div>
      ${evt.retry_tier ? `<span class="px-2 py-0.5 rounded bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300 text-[10px] font-semibold">Tier ${evt.retry_tier} Retry</span>` : ''}
    </div>
    ${evt.reasoning ? `<p class="text-xs text-stone-700 dark:text-stone-300 leading-relaxed italic">"${escapeHtml(evt.reasoning)}"</p>` : ''}
    ${evt.task_instructions ? `<div class="text-[11px] text-stone-500 dark:text-stone-400 font-mono bg-white/70 dark:bg-zinc-900/60 p-2 rounded-lg border border-stone-200/60 dark:border-zinc-800">📋 Instructions: ${escapeHtml(evt.task_instructions)}</div>` : ''}
  `;
  contentArea.appendChild(routeBox);
  addRawDebugInspector(card, evt);
}

function handleProfileReady(evt) {
  const card = getOrCreateTurnCard('profiler_agent');
  const contentArea = card.querySelector('.card-content-area');
  const profile = evt.profile || {};
  const features = profile.features || [];
  const flags = evt.flags || profile.data_quality_flags || [];

  const profBox = document.createElement('div');
  profBox.className = 'space-y-3';
  profBox.innerHTML = `
    <!-- Key Statistics Grid -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
      <div class="p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/60 border border-stone-200/70 dark:border-zinc-700/60">
        <span class="text-[10px] text-stone-400 block uppercase font-medium">Dataset Shape</span>
        <span class="font-bold text-stone-800 dark:text-stone-100 font-mono text-sm">${profile.rows || 0} rows × ${profile.columns || 0} cols</span>
      </div>
      <div class="p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/60 border border-stone-200/70 dark:border-zinc-700/60">
        <span class="text-[10px] text-stone-400 block uppercase font-medium">Target Column</span>
        <span class="font-bold text-terracotta font-mono text-sm truncate block">${evt.target_column || profile.target_column || 'None'}</span>
      </div>
      <div class="p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/60 border border-stone-200/70 dark:border-zinc-700/60">
        <span class="text-[10px] text-stone-400 block uppercase font-medium">Inferred Task</span>
        <span class="font-bold text-stone-800 dark:text-stone-100 uppercase text-xs">${evt.task_type || profile.task_type || 'Classification'}</span>
      </div>
      <div class="p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/60 border border-stone-200/70 dark:border-zinc-700/60">
        <span class="text-[10px] text-stone-400 block uppercase font-medium">Metric</span>
        <span class="font-bold text-emerald-600 dark:text-emerald-400 font-mono text-sm">${evt.metric || profile.recommended_metric || 'accuracy'}</span>
      </div>
    </div>

    <!-- Data Quality Flags -->
    ${flags.length > 0 ? `
      <div class="space-y-1.5 pt-1">
        <span class="text-[11px] font-semibold text-stone-700 dark:text-stone-300">Data Quality Insights:</span>
        <div class="flex flex-wrap gap-1.5">
          ${flags.map(f => `<span class="px-2 py-0.5 rounded-md text-[11px] bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 border border-amber-200/60 dark:border-amber-900/40">⚠️ ${escapeHtml(f)}</span>`).join('')}
        </div>
      </div>
    ` : ''}

    <!-- Features Breakdown Table -->
    ${features.length > 0 ? `
      <details class="group mt-2 text-xs border border-stone-200 dark:border-zinc-800 rounded-xl overflow-hidden bg-white dark:bg-zinc-900/40">
        <summary class="px-3.5 py-2 font-medium text-stone-700 dark:text-stone-300 cursor-pointer bg-stone-50/80 dark:bg-zinc-800/50 flex items-center justify-between select-none">
          <span>Feature Statistics & Modalities (${features.length} columns)</span>
          <span class="text-[10px] text-stone-400 group-open:rotate-180 transition-transform">▼</span>
        </summary>
        <div class="overflow-x-auto max-h-64 p-2">
          <table class="w-full text-[11px] text-left border-collapse">
            <thead>
              <tr class="border-b border-stone-200 dark:border-zinc-800 text-stone-400 text-[10px] uppercase font-mono">
                <th class="py-1.5 px-2">Column</th>
                <th class="py-1.5 px-2">Type</th>
                <th class="py-1.5 px-2">Modality</th>
                <th class="py-1.5 px-2">Null %</th>
                <th class="py-1.5 px-2">Unique</th>
                <th class="py-1.5 px-2">Outliers</th>
                <th class="py-1.5 px-2">Notes</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-stone-100 dark:divide-zinc-800/60 font-mono">
              ${features.map(f => `
                <tr class="hover:bg-stone-50 dark:hover:bg-zinc-800/30">
                  <td class="py-1 px-2 font-semibold text-stone-800 dark:text-stone-200">${escapeHtml(f.name)}</td>
                  <td class="py-1 px-2 text-stone-500">${escapeHtml(f.type || '')}</td>
                  <td class="py-1 px-2 text-stone-500">${escapeHtml(f.modality || '')}</td>
                  <td class="py-1 px-2 ${f.null_pct > 0 ? 'text-amber-500 font-semibold' : 'text-stone-400'}">${f.null_pct}%</td>
                  <td class="py-1 px-2 text-stone-500">${f.cardinality || 0}</td>
                  <td class="py-1 px-2 ${f.outliers ? 'text-amber-500 font-semibold' : 'text-stone-400'}">${f.outliers || 0}</td>
                  <td class="py-1 px-2 text-[10px] text-stone-400 font-sans truncate max-w-xs">${escapeHtml(f.notes || '')}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </details>
    ` : ''}
  `;
  contentArea.appendChild(profBox);
  addRawDebugInspector(card, evt);
}

function handleNodeEnd(evt) {
  const node = evt.node || evt.agent;
  const card = activeTurnCards[node];
  if (!card) return;

  const statusPill = card.querySelector('.status-pill');
  if (statusPill) {
    statusPill.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>Done';
    statusPill.className = 'status-pill inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200/50 dark:border-emerald-800/40';
  }

  const durationPill = card.querySelector('.duration-pill');
  if (durationPill && card.startTime) {
    const elapsed = ((performance.now() - card.startTime) / 1000).toFixed(1);
    durationPill.textContent = `${elapsed}s`;
  }

  // Display specialist return outputs inside card content area
  const contentArea = card.querySelector('.card-content-area');
  const update = evt.state_update || {};

  // EDA Findings display
  if (update.eda_findings && update.eda_findings.narrative) {
    const edaBox = document.createElement('div');
    edaBox.className = 'p-3 rounded-xl bg-cyan-50/50 dark:bg-cyan-950/20 border border-cyan-200/60 dark:border-cyan-900/40 space-y-2';
    edaBox.innerHTML = `
      <div class="font-semibold text-xs text-cyan-900 dark:text-cyan-200">EDA Narrative Synthesis:</div>
      <p class="text-xs text-stone-700 dark:text-stone-300 leading-relaxed">${escapeHtml(update.eda_findings.narrative)}</p>
    `;
    contentArea.appendChild(edaBox);
  }

  // Feature Engineering Steps display
  if (update.feature_set && update.feature_set.steps && update.feature_set.steps.length > 0) {
    const featBox = document.createElement('div');
    featBox.className = 'p-3 rounded-xl bg-amber-50/50 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-900/40 space-y-2';
    featBox.innerHTML = `
      <div class="font-semibold text-xs text-amber-900 dark:text-amber-200">Feature Engineering Steps (${update.feature_set.iterations_run} iterations):</div>
      <ul class="list-disc pl-4 space-y-1 text-xs text-stone-700 dark:text-stone-300">
        ${update.feature_set.steps.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
      </ul>
      ${update.transformed_dataset_path ? `<div class="text-[10px] font-mono text-stone-400 pt-1">Saved transformed: ${escapeHtml(update.transformed_dataset_path)}</div>` : ''}
    `;
    contentArea.appendChild(featBox);
  }

  // Candidate Models Leaderboard display
  if (update.candidate_models && update.candidate_models.length > 0) {
    const modelBox = document.createElement('div');
    modelBox.className = 'p-3.5 rounded-xl bg-indigo-50/50 dark:bg-indigo-950/20 border border-indigo-200/60 dark:border-indigo-900/40 space-y-2.5';
    modelBox.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="font-semibold text-xs text-indigo-900 dark:text-indigo-200">Trained Candidate Models Leaderboard</span>
        ${update.best_metric !== undefined ? `<span class="px-2 py-0.5 rounded-md font-bold text-xs bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300 font-mono">Best Score: ${update.best_metric}</span>` : ''}
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-[11px] text-left border-collapse">
          <thead>
            <tr class="border-b border-indigo-200 dark:border-indigo-900 text-stone-500 dark:text-stone-400 font-mono text-[10px]">
              <th class="py-1 px-2">Model Family</th>
              <th class="py-1 px-2">Metric</th>
              <th class="py-1 px-2">Validation Score</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-indigo-100 dark:divide-indigo-900/40 font-mono">
            ${update.candidate_models.map((m, idx) => `
              <tr class="${m.score === update.best_metric ? 'bg-indigo-100/50 dark:bg-indigo-900/30 font-bold' : ''}">
                <td class="py-1.5 px-2">${escapeHtml(m.model_family || `Model ${idx+1}`)} ${m.score === update.best_metric ? '⭐' : ''}</td>
                <td class="py-1.5 px-2 text-stone-500">${escapeHtml(m.metric_name || 'score')}</td>
                <td class="py-1.5 px-2 ${m.score === update.best_metric ? 'text-emerald-600 dark:text-emerald-400' : 'text-stone-700 dark:text-stone-300'}">${m.score !== undefined ? m.score : 'N/A'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    contentArea.appendChild(modelBox);
  }

  // Add raw debug inspector to every completed turn card
  addRawDebugInspector(card, evt);

  // Release from active tracker so next cycle creates a fresh card if visited again
  delete activeTurnCards[node];
}

function addRawDebugInspector(card, payload) {
  if (!card || card.querySelector('.debug-inspector')) return;
  const contentArea = card.querySelector('.card-content-area');
  if (!contentArea) return;

  const inspector = document.createElement('details');
  inspector.className = 'debug-inspector group mt-3 text-[11px] border border-stone-200/60 dark:border-zinc-800 rounded-xl overflow-hidden bg-stone-50/40 dark:bg-zinc-900/20';
  inspector.innerHTML = `
    <summary class="px-3 py-1.5 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 cursor-pointer flex items-center justify-between select-none font-mono text-[10px]">
      <span>🔍 Inspect Raw Tool & Agent Output (Debug)</span>
      <span class="group-open:rotate-180 transition-transform">▼</span>
    </summary>
    <div class="p-2 border-t border-stone-200/50 dark:border-zinc-800/60 bg-[#121214]">
      <pre class="m-0 text-[10px] text-zinc-300 font-mono overflow-x-auto max-h-48 whitespace-pre-wrap"><code>${escapeHtml(JSON.stringify(payload, null, 2))}</code></pre>
    </div>
  `;
  contentArea.appendChild(inspector);
}


// --------------------------------------------------------------------------
// Thinking / Reasoning Block
// --------------------------------------------------------------------------

function appendThinkingText(agentName, text) {
  const card = getOrCreateTurnCard(agentName);
  const container = card.querySelector('.thinking-container');
  const content = card.querySelector('.thinking-content');
  const preview = card.querySelector('.thinking-preview');

  container.classList.remove('hidden');
  content.textContent += text;
  preview.textContent = content.textContent.slice(0, 45) + '...';
}

function handleLoopDecision(evt) {
  const agent = evt.agent || 'loop';
  const reasoning = evt.reasoning || '';
  const decision = evt.decision || 'continue';
  const iteration = evt.iteration || 1;
  const taskSpec = evt.task_spec || '';

  const card = getOrCreateTurnCard(agent);

  // 1. Append to Thinking/Reasoning block
  if (reasoning) {
    const container = card.querySelector('.thinking-container');
    const content = card.querySelector('.thinking-content');
    const preview = card.querySelector('.thinking-preview');

    container.classList.remove('hidden');
    content.textContent += `\n[Iteration ${iteration} Decision: ${decision.toUpperCase()}]\n${reasoning}\n${taskSpec ? `Task Spec: ${taskSpec}\n` : ''}`;
    preview.textContent = `Iter ${iteration}: ${decision.toUpperCase()} — ${reasoning.slice(0, 35)}...`;
  }

  // 2. Render prominent AI decision block in turn card
  const contentArea = card.querySelector('.card-content-area');
  if (contentArea) {
    const decisionEl = document.createElement('div');
    decisionEl.className = 'p-3.5 rounded-xl border border-stone-200/80 dark:border-zinc-800 bg-stone-50/70 dark:bg-zinc-900/40 space-y-2 text-xs animate-card-in';
    const isStop = decision === 'stop';
    decisionEl.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <span class="font-bold text-[11px] px-2.5 py-0.5 rounded-full ${isStop ? 'bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300' : 'bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300'}">
            Iteration ${iteration}: ${isStop ? '⏹ Stop (Hand off)' : '▶ Continue'}
          </span>
          <span class="text-stone-500 dark:text-stone-400 font-medium">AI Exploration Step</span>
        </div>
      </div>
      ${reasoning ? `<div class="text-stone-700 dark:text-stone-300 italic text-[11px] leading-relaxed pl-1">"${escapeHtml(reasoning)}"</div>` : ''}
      ${taskSpec ? `<div class="text-[11px] font-mono text-stone-600 dark:text-stone-400 bg-white/80 dark:bg-zinc-800/70 p-2 rounded-lg border border-stone-200/60 dark:border-zinc-700/60">🎯 Planned Task: ${escapeHtml(taskSpec)}</div>` : ''}
    `;
    contentArea.appendChild(decisionEl);
    addRawDebugInspector(card, evt);
  }
}

// --------------------------------------------------------------------------
// Token Streaming Handler
// --------------------------------------------------------------------------

function handleToken(evt) {
  const agent = evt.agent || '';
  const text = evt.text || '';

  // Check if token belongs to coder, reporter, or specialist
  if (agent.includes('coder_agent')) {
    // Append to active coder attempt stream
    if (activeStreamingTarget) {
      activeStreamingTarget.textContent += text;
    }
  } else if (agent.includes('reporter')) {
    // Streaming report preview
    appendThinkingText('reporter', text);
  } else {
    appendThinkingText(agent, text);
  }
}

// --------------------------------------------------------------------------
// Coder Sub-Agent Call Handler (Attempt, Code, Terminal stdout/stderr)
// --------------------------------------------------------------------------

function handleAttemptResult(evt) {
  const card = getOrCreateTurnCard('coder_agent');
  const contentArea = card.querySelector('.card-content-area');

  const attemptNum = evt.attempt || 1;
  const isSuccess = evt.success;
  const code = evt.code || '# Generated code';
  const stdout = evt.stdout || '';
  const stderr = evt.stderr || '';

  const attemptBlock = document.createElement('div');
  attemptBlock.className = 'space-y-2 border border-stone-200/70 dark:border-zinc-800 rounded-xl p-3.5 bg-stone-50/40 dark:bg-zinc-900/30';

  // Badge & status header
  const badgeColor = isSuccess
    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
    : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300';

  attemptBlock.innerHTML = `
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-2">
        <span class="px-2 py-0.5 rounded-full font-semibold text-[10px] ${badgeColor}">
          Attempt ${attemptNum}
        </span>
        <span class="text-[11px] font-medium text-stone-600 dark:text-stone-400">
          ${isSuccess ? '✓ Executed successfully' : '⚠ Failed with error'}
        </span>
      </div>
      <button class="copy-code-btn text-[10px] text-stone-400 hover:text-stone-600 dark:hover:text-stone-300 flex items-center space-x-1">
        <span>Copy Code</span>
      </button>
    </div>

    <!-- Syntax Highlighted Code Box -->
    <div class="rounded-lg overflow-hidden border border-stone-200/80 dark:border-zinc-800">
      <pre class="m-0 p-3 bg-[#18181C] text-stone-100 text-xs font-mono overflow-x-auto"><code class="language-python">${escapeHtml(code)}</code></pre>
    </div>

    <!-- Terminal Window for stdout/stderr -->
    <div class="terminal-window mt-2">
      <div class="terminal-header">
        <div class="terminal-dots">
          <div class="terminal-dot bg-red-500/80"></div>
          <div class="terminal-dot bg-yellow-500/80"></div>
          <div class="terminal-dot bg-green-500/80"></div>
        </div>
        <span class="text-[10px] text-zinc-400 font-mono">python execution output</span>
      </div>
      <div class="p-3 font-mono text-xs space-y-1.5 max-h-48 overflow-y-auto">
        ${stdout ? `<div class="text-emerald-400 whitespace-pre-wrap">${escapeHtml(stdout)}</div>` : ''}
        ${stderr ? `<div class="text-rose-400 whitespace-pre-wrap font-semibold">${escapeHtml(stderr)}</div>` : ''}
        ${!stdout && !stderr ? '<div class="text-zinc-500 italic">(No output)</div>' : ''}
      </div>
    </div>
  `;

  // Syntax highlight
  const codeEl = attemptBlock.querySelector('pre code');
  if (window.hljs && codeEl) {
    hljs.highlightElement(codeEl);
  }

  // Copy code handler
  const copyBtn = attemptBlock.querySelector('.copy-code-btn');
  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(code);
    copyBtn.innerHTML = '<span>✓ Copied</span>';
    setTimeout(() => { copyBtn.innerHTML = '<span>Copy Code</span>'; }, 2000);
  });

  contentArea.appendChild(attemptBlock);
}

// --------------------------------------------------------------------------
// RAG Run Memory Results Pill
// --------------------------------------------------------------------------

function handleRunMemoryLookup(evt) {
  const agent = evt.agent || 'eda_agent';
  const card = getOrCreateTurnCard(agent);
  const contentArea = card.querySelector('.card-content-area');

  const results = evt.results || [];
  const count = results.length || evt.n_results || 0;
  const query = evt.query || '';

  if (count === 0) {
    const coldStartEl = document.createElement('div');
    coldStartEl.className = 'inline-flex items-center space-x-2 px-3 py-1 rounded-full text-[11px] font-medium bg-stone-100/80 dark:bg-zinc-800/60 text-stone-500 dark:text-stone-400 border border-dashed border-stone-300 dark:border-zinc-700 mt-2';
    coldStartEl.innerHTML = `
      <span>📎</span>
      <span>RAG: 0 prior runs in memory (cold start / fresh dataset)</span>
    `;
    contentArea.appendChild(coldStartEl);
    addRawDebugInspector(card, evt);
    return;
  }

  const ragContainer = document.createElement('div');
  ragContainer.className = 'space-y-2 mt-2';

  ragContainer.innerHTML = `
    <button type="button" class="rag-toggle inline-flex items-center space-x-2 px-2.5 py-1 rounded-full text-xs font-medium bg-stone-100 dark:bg-zinc-800 hover:bg-stone-200 dark:hover:bg-zinc-700 text-stone-700 dark:text-stone-300 border border-stone-200 dark:border-zinc-700 transition-colors">
      <span>📎</span>
      <span>${count} similar past run${count > 1 ? 's' : ''} retrieved</span>
      <svg class="rag-chevron w-3 h-3 text-stone-400 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
      </svg>
    </button>
    <div class="rag-details hidden space-y-2 pt-1">
      ${query ? `<div class="text-[10px] font-mono text-stone-400 bg-stone-100/50 dark:bg-zinc-900/50 p-1.5 rounded border border-stone-200/50 dark:border-zinc-800">🔍 Query: ${escapeHtml(query)}</div>` : ''}
      ${results.map(r => {
        const simPercent = Math.min(100, Math.round((r.similarity || 0) * 100));
        return `
          <div class="p-2.5 rounded-xl border border-stone-200/80 dark:border-zinc-800 bg-stone-50/50 dark:bg-zinc-900/40 space-y-1.5">
            <div class="flex items-center justify-between text-[11px]">
              <span class="font-mono text-stone-500 dark:text-stone-400">Run ${r.run_id ? r.run_id.slice(0, 10) : 'prior'}</span>
              <span class="font-semibold text-terracotta">${simPercent}% Match (score: ${r.similarity})</span>
            </div>
            <div class="w-full bg-stone-200 dark:bg-zinc-800 h-1.5 rounded-full overflow-hidden">
              <div class="bg-[#D97757] h-full rounded-full" style="width: ${simPercent}%"></div>
            </div>
            <p class="text-[11px] text-stone-600 dark:text-stone-300 leading-relaxed">${escapeHtml(r.text || '')}</p>
          </div>
        `;
      }).join('')}
    </div>
  `;

  const ragToggle = ragContainer.querySelector('.rag-toggle');
  const ragDetails = ragContainer.querySelector('.rag-details');
  const ragChevron = ragContainer.querySelector('.rag-chevron');

  ragToggle.addEventListener('click', () => {
    const isHidden = ragDetails.classList.contains('hidden');
    if (isHidden) {
      ragDetails.classList.remove('hidden');
      ragChevron.classList.add('rotate-180');
    } else {
      ragDetails.classList.add('hidden');
      ragChevron.classList.remove('rotate-180');
    }
  });

  contentArea.appendChild(ragContainer);
  addRawDebugInspector(card, evt);
}

// --------------------------------------------------------------------------
// Judge Verdict Handler
// --------------------------------------------------------------------------

function handleJudgeVerdict(evt) {
  const card = getOrCreateTurnCard('judge_agent');
  const contentArea = card.querySelector('.card-content-area');

  const verdict = evt.verdict;
  const isAccepted = verdict === 'accept';
  const retryTier = evt.retry_tier;
  const feedback = evt.feedback || evt.reasoning || '';

  const verdictBox = document.createElement('div');
  verdictBox.className = `p-4 rounded-xl border space-y-2.5 ${
    isAccepted
      ? 'bg-emerald-50/60 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/60 text-emerald-900 dark:text-emerald-100'
      : 'bg-amber-50/60 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/60 text-amber-900 dark:text-amber-100'
  }`;

  verdictBox.innerHTML = `
    <div class="flex items-center space-x-2">
      <span class="text-base">${isAccepted ? '✅' : '⚠️'}</span>
      <span class="font-semibold text-sm">
        ${isAccepted ? 'Verdict: Accepted' : `Verdict: Rejected → Retry Tier ${retryTier}`}
      </span>
    </div>
    ${feedback ? `<p class="text-xs leading-relaxed ${isAccepted ? 'text-emerald-800 dark:text-emerald-200' : 'text-amber-800 dark:text-amber-200'}">${escapeHtml(feedback)}</p>` : ''}
  `;

  contentArea.appendChild(verdictBox);
}

// --------------------------------------------------------------------------
// Inline Human-Approval Hard-Block Panel
// --------------------------------------------------------------------------

function handleApprovalRequired(evt) {
  updateHeaderStatus(currentRunId, 'paused_for_approval');

  const card = getOrCreateTurnCard('human_approval');
  const contentArea = card.querySelector('.card-content-area');

  const reason = evt.reason || 'destructive_action';
  const plan = evt.feature_plan || {};
  const code = plan.code || '';
  const description = plan.description || '';
  const diff = plan.structural_diff || {};
  const assessment = plan.destructive_self_assessment || false;

  const panel = document.createElement('div');
  panel.className = 'border-l-4 border-amber-500 bg-amber-50/70 dark:bg-amber-950/20 p-4 rounded-r-xl border-y border-r border-amber-200/80 dark:border-amber-900/50 space-y-3';

  let diffText = '';
  if (diff.dropped_columns && diff.dropped_columns.length > 0) {
    diffText += `<span class="inline-block px-2 py-0.5 rounded bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300 font-mono text-[10px] mr-1">Dropped columns: ${diff.dropped_columns.join(', ')}</span>`;
  }
  if (diff.row_delta !== undefined && diff.row_delta !== 0) {
    diffText += `<span class="inline-block px-2 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 font-mono text-[10px]">Row delta: ${diff.row_delta}</span>`;
  }

  panel.innerHTML = `
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-2">
        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-amber-200 dark:bg-amber-800 text-amber-900 dark:text-amber-100">
          Approval Required
        </span>
        <span class="text-xs font-semibold text-stone-800 dark:text-stone-200">
          ${reason === 'guided_mode' ? 'Guided Mode Step Review' : 'Destructive Feature Operation Detected'}
        </span>
      </div>
    </div>

    ${description ? `<p class="text-xs text-stone-700 dark:text-stone-300">${escapeHtml(description)}</p>` : ''}
    ${diffText ? `<div class="pt-1">${diffText}</div>` : ''}

    ${code ? `
      <div class="rounded-lg overflow-hidden border border-stone-200 dark:border-zinc-700 text-xs">
        <pre class="m-0 p-2.5 bg-[#18181C] text-stone-100 font-mono overflow-x-auto"><code class="language-python">${escapeHtml(code)}</code></pre>
      </div>
    ` : ''}

    <div class="approval-actions flex items-center space-x-2.5 pt-2">
      <button type="button" class="btn-approve px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-xs shadow-sm transition-colors">
        Approve
      </button>
      <button type="button" class="btn-modify px-3.5 py-1.5 rounded-lg bg-stone-200 hover:bg-stone-300 dark:bg-zinc-700 dark:hover:bg-zinc-600 text-stone-800 dark:text-stone-200 font-medium text-xs transition-colors">
        Modify
      </button>
      <button type="button" class="btn-reject px-3.5 py-1.5 rounded-lg border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950/40 font-medium text-xs transition-colors">
        Reject
      </button>
    </div>
    <div class="approval-result-status text-xs font-medium hidden"></div>
  `;

  // Syntax highlight code if present
  const codeEl = panel.querySelector('pre code');
  if (window.hljs && codeEl) {
    hljs.highlightElement(codeEl);
  }

  // Handle Button Clicks
  const btnApprove = panel.querySelector('.btn-approve');
  const btnModify = panel.querySelector('.btn-modify');
  const btnReject = panel.querySelector('.btn-reject');
  const actionsContainer = panel.querySelector('.approval-actions');
  const resultStatus = panel.querySelector('.approval-result-status');

  async function sendApproval(decision) {
    btnApprove.disabled = true;
    btnModify.disabled = true;
    btnReject.disabled = true;

    try {
      const res = await fetch(`/api/runs/${currentRunId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_status: decision })
      });

      if (!res.ok) {
        throw new Error('Approval request failed');
      }

      actionsContainer.classList.add('hidden');
      resultStatus.classList.remove('hidden');
      resultStatus.textContent = `✓ Submitted decision: ${decision.toUpperCase()} — resuming execution...`;
      resultStatus.className = 'approval-result-status text-xs font-semibold text-emerald-600 dark:text-emerald-400';
      updateHeaderStatus(currentRunId, 'running');

    } catch (err) {
      alert(`Error submitting decision: ${err.message}`);
      btnApprove.disabled = false;
      btnModify.disabled = false;
      btnReject.disabled = false;
    }
  }

  btnApprove.addEventListener('click', () => sendApproval('approved'));
  btnModify.addEventListener('click', () => sendApproval('modify'));
  btnReject.addEventListener('click', () => sendApproval('reject'));

  contentArea.appendChild(panel);
}

// --------------------------------------------------------------------------
// Final Report Card
// --------------------------------------------------------------------------

function handleReportReady(evt) {
  renderFinalReportCard(evt);
}

function renderFinalReportCard(evt) {
  // Check if report card already rendered
  if (document.getElementById('final-report-card')) return;

  const card = document.createElement('article');
  card.id = 'final-report-card';
  card.className = 'bg-white dark:bg-[#202024] border-t-4 border-[#D97757] border-x border-b border-stone-200/80 dark:border-zinc-800 rounded-2xl shadow-md p-6 space-y-5 animate-card-in';

  const reportMarkdown = evt.report || '# Pipeline Run Report\n\nNo content generated.';
  const artifactPath = evt.artifact_path || '';

  card.innerHTML = `
    <div class="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-zinc-800">
      <div class="flex items-center space-x-2.5">
        <span class="w-8 h-8 rounded-xl bg-orange-100 dark:bg-orange-950/40 text-[#D97757] flex items-center justify-center font-bold text-sm">
          📑
        </span>
        <div>
          <h2 class="text-base font-semibold text-stone-900 dark:text-stone-100">Final Pipeline Report</h2>
          <p class="text-[11px] text-stone-400 dark:text-stone-500">Autonomous Synthesis</p>
        </div>
      </div>
      <div>
        <button id="download-report-btn" class="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-[#D97757] hover:bg-[#C85A32] text-white text-xs font-medium shadow-sm transition-colors">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
          </svg>
          <span>Download (.md)</span>
        </button>
      </div>
    </div>

    <!-- Rendered Markdown Body -->
    <div class="prose-report prose dark:prose-invert max-w-none text-xs">
      ${window.marked ? marked.parse(reportMarkdown) : `<pre>${escapeHtml(reportMarkdown)}</pre>`}
    </div>

    ${artifactPath ? `<div class="pt-2 text-[11px] font-mono text-stone-400">Artifact path: ${escapeHtml(artifactPath)}</div>` : ''}
  `;

  const downloadBtn = card.querySelector('#download-report-btn');
  downloadBtn.addEventListener('click', () => {
    const blob = new Blob([reportMarkdown], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${evt.run_id || 'pipeline'}_report.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  turnsFeed.appendChild(card);
}

// --------------------------------------------------------------------------
// Run Completion / Error
// --------------------------------------------------------------------------

function handleRunComplete(evt) {
  updateHeaderStatus(currentRunId, 'completed');
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  fetchRecentRuns();
}

function handleRunError(evt) {
  updateHeaderStatus(currentRunId, 'error');
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }

  const errBanner = document.createElement('div');
  errBanner.className = 'p-4 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-200 text-xs space-y-1';
  errBanner.innerHTML = `
    <div class="font-semibold text-sm">Execution Error</div>
    <p class="font-mono text-[11px] whitespace-pre-wrap">${escapeHtml(evt.error || 'An unexpected error occurred during the pipeline run.')}</p>
  `;
  turnsFeed.appendChild(errBanner);
  fetchRecentRuns();
}

// --------------------------------------------------------------------------
// Chronological Trace Drawer
// --------------------------------------------------------------------------

function addTraceStep(evt) {
  const agent = evt.agent || 'system';
  const step = evt.step || 'step';
  const duration = evt.duration_sec ? `${evt.duration_sec}s` : 'active';
  const isError = evt.type === 'step_error' || evt.event === 'step_error';

  // Only render once per step end or error to avoid duplication
  if (evt.type === 'step_start' || evt.event === 'step_start') return;

  const barWidth = evt.duration_sec ? Math.min(100, Math.max(8, Math.round(evt.duration_sec * 30))) : 15;

  const row = document.createElement('div');
  row.className = 'p-2 rounded-lg bg-white/70 dark:bg-zinc-800/70 border border-stone-200/50 dark:border-zinc-700/50 text-[11px] space-y-1 animate-card-in';

  row.innerHTML = `
    <div class="flex items-center justify-between">
      <span class="font-medium text-stone-800 dark:text-stone-200 truncate max-w-[140px]">${escapeHtml(agent)}</span>
      <span class="font-mono text-[10px] ${isError ? 'text-rose-500 font-bold' : 'text-stone-400'}">${duration}</span>
    </div>
    <div class="text-[10px] text-stone-500 dark:text-stone-400 truncate">${escapeHtml(step)}</div>
    <div class="w-full bg-stone-100 dark:bg-zinc-900 h-1 rounded-full overflow-hidden">
      <div class="${isError ? 'bg-rose-500' : 'bg-[#D97757]'} h-full rounded-full" style="width: ${barWidth}%"></div>
    </div>
  `;

  if (traceTimeline.children.length === 1 && traceTimeline.firstElementChild.classList.contains('italic')) {
    traceTimeline.innerHTML = '';
  }
  traceTimeline.appendChild(row);
}

// --------------------------------------------------------------------------
// Utility Helpers
// --------------------------------------------------------------------------

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initial Boot
initTheme();
fetchRecentRuns();

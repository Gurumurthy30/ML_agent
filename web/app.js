/**
 * Multi-Agent ML Pipeline — Debug UI
 *
 * Bug fixes applied in this version:
 *   Bug 1+2: canonicalNode() normalizes all turn-card keys so profiler_agent vs profiler
 *            use the same map entry; "Attempt N" badge via nodeVisitCounts.
 *   Bug 3:   handleRunMemoryLookup reads evt.triggering_agent to nest inside parent card.
 *   Bug 4:   activeStreamingTarget assigned lazily in handleToken for coder_agent(attempt N);
 *            finalized in handleAttemptResult.
 *   Bug 5:   hard_block case added to switch.
 *   Bug 6:   approval panel reads evt.diff.dropped_columns (backend now sends this key).
 *   Bug 7:   handleAttemptResult reads evt.parent_agent to nest coder sub-cards.
 *
 * New features:
 *   - State Inspector (field-aware merge matching state.py reducer annotations)
 *   - Raw Event Log (filterable, expandable JSON)
 *   - Loop Visualizer (per-agent iteration progress)
 *   - Dataset upload (drag-drop → POST /api/datasets/upload → fills path input)
 *   - Drawer tab system (Trace | State | Events | Loops)
 *   - MCP fallback badge in coder attempt cards
 *   - Full output link for truncated coder outputs
 */

'use strict';

// ---------------------------------------------------------------------------
// Run state — all mutable state must be reset in _resetRunState()
// ---------------------------------------------------------------------------
let currentRunId = null;
let currentEventSource = null;
let currentStatus = 'ready';
let activeTurnCards = {};           // canonicalNode → DOM element
let activeCoderAttempts = {};       // parent_agent → container el (legacy)
let activeThinkingSections = {};    // agentName → { element, text }
let activeStreamingTarget = null;   // live <code> element for current coder token stream
let activeCoderStreams = {};        // attempt_key (string) → { liveBlock, codeEl, parentAgent }
let nodeVisitCounts = {};           // canonicalNode → integer visit count
let isUserScrolledUp = false;
let traceEvents = [];

// Debug console state
let rawEventLog = [];               // all SSE events
let currentState = {};              // live merged state (field-aware)
let loopProgress = {};              // agent → { iteration, ceiling, exitReason }
let iterationLedger = [];           // iteration metrics ledger: [{ iteration, agent, task_spec, best_metric, metric_delta, is_stall }]
let isDrawerOpen = true;            // drawer open state
let activeDrawerTab = 'trace';      // current active drawer tab

// Reducer fields in state.py (Annotated[list, operator.add]):
// node_end state_update carries only the delta — we must concat these, not overwrite.
const REDUCER_FIELDS = new Set(['candidate_models', 'metric_history', 'run_memory', 'messages']);

// ---------------------------------------------------------------------------
// canonicalNode — Bug 1+2 fix
// ---------------------------------------------------------------------------
const NODE_NAME_MAP = {
  profiler_agent: 'profiler',
  features_agent: 'features',
  modeler_agent: 'modeler',
  judge_agent: 'judge',
  reporter_agent: 'reporter',
};

function canonicalNode(name) {
  if (!name) return name;
  // Strip parenthetical suffixes like "(attempt 1)" before looking up
  const base = name.toLowerCase().replace(/\s*\(.*\)\s*$/, '').trim();
  return NODE_NAME_MAP[base] || base;
}

// ---------------------------------------------------------------------------
// State reset — called on new run OR loadRunDetails switch
// Guarantees non-stale data across runs by purging both JS state and DOM elements
// ---------------------------------------------------------------------------
function _resetRunState() {
  activeTurnCards = {};
  activeCoderAttempts = {};
  activeThinkingSections = {};
  activeStreamingTarget = null;
  activeCoderStreams = {};
  nodeVisitCounts = {};
  traceEvents = [];
  rawEventLog = [];
  currentState = {};
  loopProgress = {};
  iterationLedger = [];
  currentStatus = 'ready';

  // Purge DOM elements to prevent stale views across runs
  if (traceTimeline) {
    traceTimeline.innerHTML = '<div class="p-3 text-center text-xs text-stone-400 dark:text-stone-500 italic">No events logged yet</div>';
  }
  if (eventLogList) {
    eventLogList.innerHTML = '<div class="text-stone-400 dark:text-stone-500 italic p-2">No events yet</div>';
  }
  if (eventLogCount) {
    eventLogCount.textContent = '0 events';
  }
  if (loopVizContainer) {
    loopVizContainer.innerHTML = '<div class="text-xs text-stone-400 dark:text-stone-500 italic">No loop activity yet</div>';
  }
  const ledgerEl = document.getElementById('loop-ledger-container');
  if (ledgerEl) {
    ledgerEl.innerHTML = '<div class="text-xs text-stone-400 dark:text-stone-500 italic">No iteration metrics recorded yet</div>';
  }
  const stopReasonBox = document.getElementById('state-stop-reason-box');
  if (stopReasonBox) {
    stopReasonBox.classList.add('hidden');
  }

  // Reset state inspector fields
  const iterEl = document.getElementById('state-iter-count');
  if (iterEl) iterEl.textContent = '0 / 200';
  const bmEl = document.getElementById('state-best-metric');
  if (bmEl) bmEl.textContent = '—';
  const trendEl = document.getElementById('state-metric-trend');
  if (trendEl) trendEl.textContent = '';
  const stagesEl = document.getElementById('state-stages');
  if (stagesEl) stagesEl.innerHTML = '';
  const modelsEl = document.getElementById('state-models');
  if (modelsEl) modelsEl.innerHTML = '<div class="text-stone-400 dark:text-stone-500 italic">No models yet</div>';
  const rawEl = document.getElementById('state-raw-dump');
  if (rawEl) rawEl.textContent = '';

  ['tier1', 'tier2'].forEach(t => {
    const bar = document.getElementById(`state-${t}-bar`);
    if (bar) {
      bar.querySelectorAll('span').forEach(cell => {
        cell.className = 'w-4 h-4 rounded-sm bg-stone-200 dark:bg-zinc-600';
      });
    }
  });

  if (typeof updateTelemetryHeader === 'function') {
    updateTelemetryHeader();
  }
}

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------
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
const toggleDebugBtn = document.getElementById('toggle-debug-btn');
const closeTraceBtn = document.getElementById('close-trace-btn');
const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
const leftSidebar = document.getElementById('left-sidebar');
const rightDrawer = document.getElementById('right-drawer');
const traceTimeline = document.getElementById('trace-timeline');

// Telemetry strip DOM refs
const telemetryStrip = document.getElementById('telemetry-strip');
const telemetryStages = document.getElementById('telemetry-stages');
const telemetryAgentDot = document.getElementById('telemetry-agent-dot');
const telemetryActiveAgent = document.getElementById('telemetry-active-agent');
const telemetryIter = document.getElementById('telemetry-iter');
const telemetryT1Count = document.getElementById('telemetry-t1-count');
const telemetryT2Count = document.getElementById('telemetry-t2-count');
const telemetryRunStatus = document.getElementById('telemetry-run-status');

// Debug panels & Ledger
const eventFilterInput = document.getElementById('event-filter-input');
const eventLogList = document.getElementById('event-log-list');
const eventLogCount = document.getElementById('event-log-count');
const clearEventLogBtn = document.getElementById('clear-event-log-btn');
const loopVizContainer = document.getElementById('loop-viz-container');
const loopLedgerContainer = document.getElementById('loop-ledger-container');
const stateStopReasonBox = document.getElementById('state-stop-reason-box');
const stateStopReasonText = document.getElementById('state-stop-reason-text');

// Debug report export
const exportDebugReportBtn = document.getElementById('export-debug-report-btn');
const downloadDebugReportBtn = document.getElementById('download-debug-report-btn');

// ---------------------------------------------------------------------------
// Agent display metadata
// ---------------------------------------------------------------------------
const AGENT_META = {
  supervisor: { label: 'Supervisor', role: 'Orchestrator', icon: '🧠', color: 'bg-purple-100 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300' },
  profiler: { label: 'Profiler Specialist', role: 'Data Profiling', icon: '📊', color: 'bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300' },
  eda_agent: { label: 'EDA Specialist', role: 'Exploratory Analysis', icon: '🔍', color: 'bg-cyan-100 dark:bg-cyan-950/40 text-cyan-700 dark:text-cyan-300' },
  features: { label: 'Feature Engineer', role: 'Transformation & Diff', icon: '⚡', color: 'bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300' },
  modeler: { label: 'Model Trainer', role: 'Candidate Selection', icon: '🤖', color: 'bg-indigo-100 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300' },
  judge: { label: 'Quality Judge', role: 'Evaluation & Verdict', icon: '⚖️', color: 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300' },
  human_approval: { label: 'Human Review', role: 'Interactive Gate', icon: '👤', color: 'bg-orange-100 dark:bg-orange-950/40 text-orange-700 dark:text-orange-300' },
  reporter: { label: 'Final Reporter', role: 'Synthesis & Metrics', icon: '📝', color: 'bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300' },
  coder_agent: { label: 'Coder Sub-Agent', role: 'Code Generation & Exec', icon: '💻', color: 'bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300' },
};

function getAgentMeta(name) {
  if (!name) return { label: 'System Agent', role: 'Pipeline', icon: '⚙️', color: 'bg-stone-100 dark:bg-zinc-800 text-stone-700' };
  const cleanName = canonicalNode(name);
  return AGENT_META[cleanName] || { label: name, role: 'Specialist', icon: '🤖', color: 'bg-stone-100 dark:bg-zinc-800 text-stone-700' };
}

// ---------------------------------------------------------------------------
// Theme & UI Initialization
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Drawer tabs & Unified Drawer State Management
// ---------------------------------------------------------------------------
const TABS = ['trace', 'state', 'loops', 'events'];

function activateTab(tabId) {
  activeDrawerTab = tabId;
  TABS.forEach(t => {
    const btn = document.getElementById(`tab-${t}`);
    const panel = document.getElementById(`panel-${t}`);
    if (!btn || !panel) return;
    if (t === tabId) {
      btn.classList.add('drawer-tab-active');
      btn.classList.remove('border-transparent', 'text-stone-500', 'dark:text-stone-400');
      panel.classList.remove('hidden');
    } else {
      btn.classList.remove('drawer-tab-active');
      btn.classList.add('border-transparent', 'text-stone-500', 'dark:text-stone-400');
      panel.classList.add('hidden');
    }
  });

  // Highlight corresponding header button when drawer is open
  if (isDrawerOpen) {
    if (tabId === 'trace') {
      toggleTraceBtn?.classList.add('btn-header-active');
      toggleDebugBtn?.classList.remove('btn-header-active');
    } else {
      toggleDebugBtn?.classList.add('btn-header-active');
      toggleTraceBtn?.classList.remove('btn-header-active');
    }
  }

  localStorage.setItem('active_drawer_tab', tabId);
}

function setDrawerOpen(isOpen, tabId = null) {
  isDrawerOpen = isOpen;
  if (!rightDrawer) return;

  if (isDrawerOpen) {
    rightDrawer.style.display = 'flex';
    rightDrawer.classList.remove('hidden');
    activateTab(tabId || activeDrawerTab || 'trace');
  } else {
    rightDrawer.style.display = 'none';
    rightDrawer.classList.add('hidden');
    toggleTraceBtn?.classList.remove('btn-header-active');
    toggleDebugBtn?.classList.remove('btn-header-active');
  }
  localStorage.setItem('drawer_open', isDrawerOpen ? '1' : '0');
}

TABS.forEach(t => {
  const btn = document.getElementById(`tab-${t}`);
  if (btn) {
    btn.addEventListener('click', () => {
      if (!isDrawerOpen) {
        setDrawerOpen(true, t);
      } else {
        activateTab(t);
      }
    });
  }
});

// Trace header button toggle: toggles drawer or switches to 'trace' tab
toggleTraceBtn?.addEventListener('click', () => {
  if (isDrawerOpen && activeDrawerTab === 'trace') {
    setDrawerOpen(false);
  } else {
    setDrawerOpen(true, 'trace');
  }
});

// Debug header button toggle: toggles drawer or switches to 'state' (or last non-trace tab)
toggleDebugBtn?.addEventListener('click', () => {
  if (isDrawerOpen && activeDrawerTab !== 'trace') {
    setDrawerOpen(false);
  } else {
    const target = (activeDrawerTab === 'trace' ? 'state' : activeDrawerTab) || 'state';
    setDrawerOpen(true, target);
  }
});

// Close button on drawer header
closeTraceBtn?.addEventListener('click', () => {
  setDrawerOpen(false);
});

// Mobile Left Sidebar Toggle
toggleSidebarBtn?.addEventListener('click', () => {
  if (!leftSidebar) return;
  leftSidebar.classList.toggle('hidden');
});

// ---------------------------------------------------------------------------
// Dataset Upload & Selection
// ---------------------------------------------------------------------------
const uploadDropZone = document.getElementById('upload-drop-zone');
const uploadFileInput = document.getElementById('upload-file-input');
const uploadStatusText = document.getElementById('upload-status-text');

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

async function uploadDataset(file) {
  if (!file) return;
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  if (!['csv', 'parquet', 'pq'].includes(ext)) {
    if (uploadStatusText) {
      uploadStatusText.innerHTML = `✗ Unsupported file type: <strong>.${ext}</strong> (allowed: .csv, .parquet)`;
      uploadStatusText.className = 'text-xs text-rose-500';
    }
    return;
  }

  const sizeStr = formatFileSize(file.size);
  if (uploadStatusText) {
    uploadStatusText.innerHTML = `<span class="inline-flex items-center gap-1.5"><svg class="w-3.5 h-3.5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>Uploading <strong>${file.name}</strong> (${sizeStr})…</span>`;
    uploadStatusText.className = 'text-xs text-[#D97757]';
  }

  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/datasets/upload', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    if (datasetInput) {
      datasetInput.value = data.path;
      datasetInput.dispatchEvent(new Event('input', { bubbles: true }));
      datasetInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (uploadStatusText) {
      uploadStatusText.innerHTML = `✓ <span class="font-semibold">${file.name}</span> (${formatFileSize(data.size_bytes)}) uploaded — path set below`;
      uploadStatusText.className = 'text-xs text-emerald-600 dark:text-emerald-400 font-medium';
    }
    // Deselect quick chips
    document.querySelectorAll('.quick-chip').forEach(c => {
      c.classList.remove('border-[#D97757]', 'text-[#D97757]', 'bg-orange-50', 'dark:bg-orange-950/30');
    });
  } catch (err) {
    if (uploadStatusText) {
      uploadStatusText.textContent = `✗ Upload failed: ${err.message}`;
      uploadStatusText.className = 'text-xs text-rose-500 font-medium';
    }
  }
}

// Click on drop zone opens file picker
if (uploadDropZone && uploadFileInput) {
  uploadDropZone.addEventListener('click', (e) => {
    // Only trigger if clicking zone directly, not interactive children
    if (e.target.tagName !== 'BUTTON' && e.target.tagName !== 'A') {
      uploadFileInput.value = '';
      uploadFileInput.click();
    }
  });

  uploadFileInput.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadDataset(file);
    }
    uploadFileInput.value = '';
  });

  // Drag & drop handling with counter to prevent dragleave flicker on children
  let dragCounter = 0;
  uploadDropZone.addEventListener('dragenter', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter++;
    uploadDropZone.classList.add('border-[#D97757]', 'bg-orange-50/40', 'dark:bg-orange-950/20');
  });

  uploadDropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
  });

  uploadDropZone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter--;
    if (dragCounter <= 0) {
      dragCounter = 0;
      uploadDropZone.classList.remove('border-[#D97757]', 'bg-orange-50/40', 'dark:bg-orange-950/20');
    }
  });

  uploadDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter = 0;
    uploadDropZone.classList.remove('border-[#D97757]', 'bg-orange-50/40', 'dark:bg-orange-950/20');
    const file = e.dataTransfer?.files?.[0];
    if (file) {
      uploadDataset(file);
    }
  });
}

// Prevent browser from opening files dragged anywhere else on page
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => e.preventDefault());

// Backward-compatibility fallback
window.handleFileDrop = function(event) {
  event.preventDefault();
  event.stopPropagation();
  const file = event.dataTransfer?.files?.[0];
  if (file) uploadDataset(file);
};

// Quick Select Chips (e.g. train.csv Churn demo)
document.querySelectorAll('.quick-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const path = chip.getAttribute('data-path');
    if (!path || !datasetInput) return;
    datasetInput.value = path;
    datasetInput.dispatchEvent(new Event('input', { bubbles: true }));
    datasetInput.dispatchEvent(new Event('change', { bubbles: true }));

    document.querySelectorAll('.quick-chip').forEach(c => {
      c.classList.remove('border-[#D97757]', 'text-[#D97757]', 'bg-orange-50', 'dark:bg-orange-950/30');
    });
    chip.classList.add('border-[#D97757]', 'text-[#D97757]', 'bg-orange-50', 'dark:bg-orange-950/30');

    if (uploadStatusText) {
      uploadStatusText.textContent = `✓ Selected: ${chip.textContent.trim()}`;
      uploadStatusText.className = 'text-xs text-emerald-600 dark:text-emerald-400 font-medium';
    }
  });
});

if (datasetInput) {
  datasetInput.addEventListener('input', () => {
    // If typing custom path, clear active chip highlighting
    document.querySelectorAll('.quick-chip').forEach(c => {
      c.classList.remove('border-[#D97757]', 'text-[#D97757]', 'bg-orange-50', 'dark:bg-orange-950/30');
    });
  });
}

// ---------------------------------------------------------------------------
// Scroll Behavior
// ---------------------------------------------------------------------------
feedContainer.addEventListener('scroll', () => {
  const threshold = 200;
  const distFromBottom = feedContainer.scrollHeight - feedContainer.scrollTop - feedContainer.clientHeight;
  isUserScrolledUp = distFromBottom > threshold;
  scrollBottomContainer.classList.toggle('hidden', !isUserScrolledUp);
});

scrollDownBtn.addEventListener('click', () => {
  feedContainer.scrollTo({ top: feedContainer.scrollHeight, behavior: 'smooth' });
});

function scrollToBottomIfNeeded() {
  if (!isUserScrolledUp) {
    feedContainer.scrollTo({ top: feedContainer.scrollHeight, behavior: 'smooth' });
  }
}

// ---------------------------------------------------------------------------
// Header Status
// ---------------------------------------------------------------------------
function updateHeaderStatus(runId, status) {
  if (runId) {
    currentRunId = runId;
    headerRunId.textContent = `run: ${String(runId).slice(-8)}`;
  }
  currentStatus = status || 'ready';
  const pill = headerRunStatusPill;
  if (pill) {
    pill.classList.remove('hidden');
    const STATUS_CLASSES = {
      ready: 'bg-stone-100 dark:bg-zinc-800 text-stone-700 dark:text-stone-300',
      running: 'bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300',
      paused_for_approval: 'bg-orange-100 dark:bg-orange-950/40 text-orange-700 dark:text-orange-300',
      completed: 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300',
      converged: 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300',
      stalled: 'bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300',
      hit_safety_ceiling: 'bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300',
      global_iteration_ceiling: 'bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300',
      user_rejected: 'bg-orange-100 dark:bg-orange-950/40 text-orange-700 dark:text-orange-300',
      error: 'bg-rose-100 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300',
    };
    pill.className = `px-2 py-0.5 rounded-full text-[10px] font-semibold ${STATUS_CLASSES[status] || 'bg-stone-100 text-stone-700'}`;
    const STATUS_LABELS = {
      ready: '○ Ready',
      running: '● Running',
      paused_for_approval: '⏸ Awaiting Approval',
      completed: '✓ Completed',
      converged: '✓ Converged',
      stalled: '⚠️ Stalled',
      hit_safety_ceiling: '🛑 Safety Ceiling',
      global_iteration_ceiling: '🛑 Ceiling Hit',
      user_rejected: '✕ Rejected',
      error: '✗ Error',
    };
    pill.textContent = STATUS_LABELS[status] || status;
  }
  updateTelemetryHeader();
}

// ---------------------------------------------------------------------------
// Developer Telemetry Header Strip
// ---------------------------------------------------------------------------
const PIPELINE_STAGES = ['profiler', 'eda_agent', 'features', 'modeler', 'judge', 'reporter'];

function updateTelemetryHeader(activeAgent = null) {
  if (!telemetryStrip) return;

  // 1. Stage progression pills
  const stageElements = telemetryStages ? telemetryStages.querySelectorAll('.telemetry-stage-pill') : [];
  
  const completedStages = new Set();
  if (currentState.profile && Object.keys(currentState.profile).length > 0) completedStages.add('profiler');
  if (currentState.eda_findings && Object.keys(currentState.eda_findings).length > 0) completedStages.add('eda_agent');
  if (currentState.feature_set && Object.keys(currentState.feature_set).length > 0) completedStages.add('features');
  if ((currentState.candidate_models || []).length > 0) completedStages.add('modeler');
  if (currentState.last_verdict) completedStages.add('judge');
  if (currentState.final_report) completedStages.add('reporter');

  const activeKey = activeAgent ? canonicalNode(activeAgent) : null;

  stageElements.forEach(pill => {
    const stage = pill.getAttribute('data-stage');
    if (stage === activeKey) {
      pill.className = 'telemetry-stage-pill px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 ring-1 ring-blue-500 shadow-xs';
    } else if (completedStages.has(stage)) {
      pill.className = 'telemetry-stage-pill px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300';
    } else {
      pill.className = 'telemetry-stage-pill px-2 py-0.5 rounded text-[10px] font-medium bg-stone-200/60 dark:bg-zinc-800 text-stone-600 dark:text-stone-400';
    }
  });

  // 2. Active agent dot and label
  if (telemetryActiveAgent && telemetryAgentDot) {
    if (activeKey && activeKey !== 'system' && currentStatus === 'running') {
      const meta = getAgentMeta(activeKey);
      telemetryActiveAgent.textContent = meta.label || activeKey;
      telemetryAgentDot.className = 'w-2 h-2 rounded-full bg-emerald-500 pulse-dot-live';
    } else if (currentStatus === 'running') {
      telemetryActiveAgent.textContent = 'Orchestrating';
      telemetryAgentDot.className = 'w-2 h-2 rounded-full bg-blue-500 pulse-dot-live';
    } else if (currentStatus === 'paused_for_approval') {
      telemetryActiveAgent.textContent = 'Human Review';
      telemetryAgentDot.className = 'w-2 h-2 rounded-full bg-orange-500';
    } else {
      telemetryActiveAgent.textContent = 'Idle';
      telemetryAgentDot.className = 'w-2 h-2 rounded-full bg-stone-400';
    }
  }

  // 3. Global iteration count vs ceiling
  if (telemetryIter) {
    telemetryIter.textContent = currentState.iteration ?? 0;
  }

  // 4. Retry budgets (Tier 1 modeler, Tier 2 features)
  const rc = currentState.retry_counts || {};
  if (telemetryT1Count) telemetryT1Count.textContent = rc[1] || 0;
  if (telemetryT2Count) telemetryT2Count.textContent = rc[2] || 0;

  // 5. Run status badge (with stop_reason support)
  if (telemetryRunStatus) {
    let effectiveStatus = currentStatus;
    if (currentState.stop_reason) {
      effectiveStatus = currentState.stop_reason;
    }
    const STATUS_BADGES = {
      ready: { cls: 'bg-stone-200 text-stone-700 dark:bg-zinc-800 dark:text-stone-300', text: 'Ready' },
      running: { cls: 'bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300 font-bold', text: '● Running' },
      paused_for_approval: { cls: 'bg-orange-100 text-orange-700 dark:bg-orange-950/50 dark:text-orange-300 font-bold', text: '⏸ Awaiting Review' },
      completed: { cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 font-bold', text: '✓ Completed' },
      converged: { cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 font-bold', text: '✓ Converged' },
      stalled: { cls: 'bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300 font-bold', text: '⚠️ Stalled' },
      hit_safety_ceiling: { cls: 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 font-bold', text: '🛑 Safety Ceiling' },
      global_iteration_ceiling: { cls: 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 font-bold', text: '🛑 Ceiling Hit' },
      user_rejected: { cls: 'bg-orange-100 text-orange-700 dark:bg-orange-950/50 dark:text-orange-300 font-bold', text: '✕ Rejected' },
      error: { cls: 'bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 font-bold', text: '✗ Error' },
    };
    const badge = STATUS_BADGES[effectiveStatus] || { cls: 'bg-stone-200 text-stone-700', text: effectiveStatus };
    telemetryRunStatus.className = `px-2 py-0.5 rounded font-semibold text-[10px] ${badge.cls}`;
    telemetryRunStatus.textContent = badge.text;
  }
}

// ---------------------------------------------------------------------------
// Turn Card Management — Bug 1+2 fix applied via canonicalNode
// ---------------------------------------------------------------------------

function getOrCreateTurnCard(agentName) {
  const key = canonicalNode(agentName);
  if (activeTurnCards[key]) return activeTurnCards[key];

  const meta = getAgentMeta(key);
  const visitCount = nodeVisitCounts[key] || 1;

  const card = document.createElement('article');
  card.className = 'bg-white dark:bg-[#202024] border border-stone-200/80 dark:border-zinc-800 rounded-2xl shadow-sm overflow-hidden animate-card-in';
  card.setAttribute('data-agent', key);

  card.innerHTML = `
    <div class="flex items-start justify-between p-4 pb-3">
      <div class="flex items-center space-x-3">
        <div class="flex-shrink-0 w-8 h-8 rounded-xl ${meta.color} flex items-center justify-center text-base">
          ${meta.icon}
        </div>
        <div>
          <div class="flex items-center space-x-2">
            <h3 class="text-sm font-semibold text-stone-900 dark:text-stone-100">${escapeHtml(meta.label)}</h3>
            ${visitCount > 1 ? `<span class="px-1.5 py-0.5 rounded-md text-[10px] font-bold bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400">Attempt ${visitCount}</span>` : ''}
          </div>
          <p class="text-[11px] text-stone-400 dark:text-stone-500">${escapeHtml(meta.role)}</p>
        </div>
      </div>
      <div class="status-pill flex items-center text-[11px] font-medium px-2 py-1 rounded-full bg-blue-50 dark:bg-blue-950/30 text-blue-600 dark:text-blue-400">
        <span class="w-1.5 h-1.5 rounded-full bg-blue-500 mr-1.5 animate-pulse"></span>
        Active
      </div>
    </div>
    <div class="card-content-area px-4 pb-4 space-y-3"></div>
  `;

  turnsFeed.appendChild(card);
  activeTurnCards[key] = card;
  scrollToBottomIfNeeded();
  return card;
}

function closeCard(agentName) {
  const key = canonicalNode(agentName);
  const card = activeTurnCards[key];
  if (!card) return;
  const pill = card.querySelector('.status-pill');
  if (pill) {
    pill.classList.remove('bg-blue-50', 'dark:bg-blue-950/30', 'text-blue-600', 'dark:text-blue-400');
    pill.classList.add('bg-stone-50', 'dark:bg-zinc-800/50', 'text-stone-400', 'dark:text-stone-500');
    pill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-stone-400 mr-1.5"></span>Done`;
  }
  delete activeTurnCards[key];
}

// ---------------------------------------------------------------------------
// Thinking / narrative stream rendering
// ---------------------------------------------------------------------------

function appendThinkingText(agentName, text) {
  const key = canonicalNode(agentName);
  const card = getOrCreateTurnCard(key);
  const contentArea = card.querySelector('.card-content-area');

  if (!activeThinkingSections[key]) {
    const section = document.createElement('div');
    section.className = 'thinking-section border-l-2 border-stone-200 dark:border-zinc-700 pl-3 py-1 space-y-1';
    section.innerHTML = `<p class="text-[11px] font-medium text-stone-400 dark:text-stone-500 uppercase tracking-wider">Reasoning</p>
      <p class="thinking-text text-xs text-stone-600 dark:text-stone-300 leading-relaxed whitespace-pre-wrap"></p>`;
    contentArea.appendChild(section);
    activeThinkingSections[key] = { element: section, text: '' };
  }

  activeThinkingSections[key].text += text;
  const textEl = activeThinkingSections[key].element.querySelector('.thinking-text');
  if (textEl) textEl.textContent = activeThinkingSections[key].text;
  scrollToBottomIfNeeded();
}

// ---------------------------------------------------------------------------
// SSE Connection
// ---------------------------------------------------------------------------

function startEventStream(runId) {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  _resetRunState();
  currentRunId = runId;
  updateHeaderStatus(runId, 'running');

  const es = new EventSource(`/api/runs/${runId}/stream`);
  currentEventSource = es;

  es.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      handlePipelineEvent(data);
    } catch (e) {
      console.error('Event parse error:', e, ev.data);
    }
  };
  es.onerror = (err) => {
    console.error('SSE error:', err);
    if (currentEventSource === es) {
      updateHeaderStatus(runId, 'error');
    }
  };
}

// ---------------------------------------------------------------------------
// Central Event Router
// ---------------------------------------------------------------------------

function handlePipelineEvent(evt) {
  const type = evt.type || evt.event || '';

  // Push every event to the raw log (before switch)
  rawEventLog.push({ ...evt, _idx: rawEventLog.length });
  renderRawEventLog();

  switch (type) {
    case 'node_start':         handleNodeStart(evt); break;
    case 'node_end':           handleNodeEnd(evt); break;
    case 'token':              handleToken(evt); break;
    case 'step_start':
    case 'step_end':
    case 'step_error':         addTraceStep(evt); break;
    case 'profile_ready':      handleProfileReady(evt); break;
    case 'loop_decision':      handleLoopDecision(evt); break;
    case 'loop_end':           handleLoopEnd(evt); break;
    case 'iteration_result':   handleIterationResult(evt); break;
    case 'run_stop_reason':    handleRunStopReason(evt); break;
    case 'attempt_result':     handleAttemptResult(evt); break;
    case 'mcp_fallback':       handleMcpFallback(evt); break;
    case 'judge_verdict':      handleJudgeVerdict(evt); break;
    case 'supervisor_routed':  handleSupervisorRouted(evt); break;
    case 'hard_block':         handleHardBlock(evt); break;  // Bug 5 fix
    case 'approval_required':  handleApprovalRequired(evt); break;
    case 'approval_resumed':   handleApprovalResumed(evt); break;
    case 'run_memory_lookup':  handleRunMemoryLookup(evt); break;  // Bug 3 fix
    case 'report_ready':       handleReportReady(evt); break;
    case 'run_complete':       handleRunComplete(evt); break;
    case 'run_error':          handleRunError(evt); break;
    case 'retry_cap_override':
    case 'stalled_retry_escalation':
    case 'global_iteration_ceiling': handleSupervisorOverride(evt); break;
    default:
      // Unknown types still appear in the raw event log
      break;
  }
}

// ---------------------------------------------------------------------------
// Node lifecycle — tracks visit counts for "Attempt N" badge
// ---------------------------------------------------------------------------

function handleNodeStart(evt) {
  const node = canonicalNode(evt.node || evt.agent);
  if (!node || node === '__start__' || node === '__end__') return;
  // Increment visit count
  nodeVisitCounts[node] = (nodeVisitCounts[node] || 0) + 1;
  updateTelemetryHeader(node);
}

function handleNodeEnd(evt) {
  const node = canonicalNode(evt.node || evt.agent);
  if (!node) return;
  // Merge state update with field-aware logic (Bug 5 / State Inspector)
  if (evt.state_update && typeof evt.state_update === 'object') {
    mergeStateUpdate(evt.state_update);
  }
  closeCard(node);
  addTraceStep({ ...evt, agent: node, step: node, duration_sec: evt.duration_sec });
  updateTelemetryHeader(null);
}

// ---------------------------------------------------------------------------
// Token streaming — Bug 4 fix: lazy element creation in handleToken
// ---------------------------------------------------------------------------

function handleToken(evt) {
  const agent = evt.agent || '';
  const text = evt.text || evt.token || '';
  if (!text) return;

  // Coder sub-agent tokens: "coder_agent(attempt N)"
  if (agent.toLowerCase().startsWith('coder_agent')) {
    const attemptMatch = agent.match(/attempt\s*(\d+)/i);
    const attemptKey = attemptMatch ? attemptMatch[1] : '1';
    const parentAgent = canonicalNode(evt.parent_agent || '');

    if (!activeCoderStreams[attemptKey]) {
      // Lazily create the live streaming element the first time a token arrives
      const hostCard = parentAgent
        ? getOrCreateTurnCard(parentAgent)
        : getOrCreateTurnCard('coder_agent');
      const liveBlock = document.createElement('div');
      liveBlock.className = 'coder-live-stream rounded-xl overflow-hidden border border-zinc-700/60';
      liveBlock.dataset.attemptKey = attemptKey;
      liveBlock.innerHTML = `
        <div class="flex items-center px-3 py-1.5 bg-zinc-800 text-zinc-400 text-[10px] font-mono">
          <span class="animate-pulse mr-2 text-[#D97757]">●</span>
          Generating code (attempt ${attemptKey})…
        </div>
        <pre class="m-0 p-3 bg-[#18181C] text-stone-100 text-xs font-mono overflow-x-auto max-h-64 whitespace-pre-wrap"><code></code></pre>
      `;
      hostCard.querySelector('.card-content-area').appendChild(liveBlock);
      const codeEl = liveBlock.querySelector('code');
      activeCoderStreams[attemptKey] = { liveBlock, codeEl, parentAgent };
      activeStreamingTarget = codeEl;
    } else {
      // Update streaming target to current attempt's code element
      activeStreamingTarget = activeCoderStreams[attemptKey].codeEl;
    }

    if (activeStreamingTarget) {
      activeStreamingTarget.textContent += text;
    }
    scrollToBottomIfNeeded();
    return;
  }

  // All other tokens → narrative thinking text for the agent's card
  appendThinkingText(agent, text);
}

// ---------------------------------------------------------------------------
// Coder attempt result — Bug 4+7 fix: finalize live stream, nest in parent card
// ---------------------------------------------------------------------------

function handleAttemptResult(evt) {
  const attempt = String(evt.attempt || 1);
  const parentAgent = canonicalNode(evt.parent_agent || '');

  // Finalize and remove the live streaming element (replace with static block)
  const liveStream = activeCoderStreams[attempt];
  if (liveStream) {
    liveStream.liveBlock.remove();
    delete activeCoderStreams[attempt];
  }
  if (Object.keys(activeCoderStreams).length === 0) {
    activeStreamingTarget = null;
  }

  // Determine host card — nest under parent agent if present (Bug 7 fix)
  const hostCard = parentAgent
    ? getOrCreateTurnCard(parentAgent)
    : getOrCreateTurnCard('coder_agent');
  const contentArea = hostCard.querySelector('.card-content-area');

  const success = evt.success;
  const code = evt.code || '';
  const stdout = evt.stdout || '';
  const stderr = evt.stderr || '';
  const isTruncated = stdout.includes('[... ') && stdout.includes('characters truncated');
  const mcpFallback = evt.mcp_fallback || false;

  const block = document.createElement('div');
  block.className = 'rounded-xl overflow-hidden border border-zinc-700/60 text-xs';
  block.innerHTML = `
    <div class="flex items-center justify-between px-3 py-1.5 bg-zinc-800 text-zinc-300">
      <div class="flex items-center space-x-2 font-mono">
        <span class="${success ? 'text-emerald-400' : 'text-rose-400'}">${success ? '✓' : '✗'}</span>
        <span>Attempt ${attempt}</span>
        ${mcpFallback ? `<span class="px-1.5 py-0.5 rounded text-[9px] bg-amber-900/60 text-amber-300 font-semibold">MCP FALLBACK</span>` : ''}
      </div>
      <button class="toggle-code-btn text-zinc-500 hover:text-zinc-300 text-[10px] underline">show code</button>
    </div>
    <div class="code-block hidden bg-[#18181C]">
      <pre class="p-3 overflow-x-auto max-h-60"><code class="language-python">${escapeHtml(code)}</code></pre>
    </div>
    ${stdout ? `<div class="p-3 bg-zinc-900 border-t border-zinc-700/50">
      <p class="text-[10px] text-zinc-500 mb-1 font-semibold uppercase">stdout</p>
      <pre class="text-[11px] text-stone-300 whitespace-pre-wrap max-h-40 overflow-y-auto">${escapeHtml(stdout)}</pre>
      ${isTruncated ? `<a href="/api/runs/${currentRunId}/events/${rawEventLog.length - 1}/full_output" target="_blank" class="text-[10px] text-[#D97757] underline mt-1 block">View full output ↗</a>` : ''}
    </div>` : ''}
    ${!success && stderr ? `<div class="p-3 bg-rose-950/40 border-t border-zinc-700/50">
      <p class="text-[10px] text-rose-400 mb-1 font-semibold uppercase">stderr</p>
      <pre class="text-[11px] text-rose-300 whitespace-pre-wrap max-h-32 overflow-y-auto">${escapeHtml(stderr)}</pre>
    </div>` : ''}
  `;

  // Toggle code visibility
  const toggleBtn = block.querySelector('.toggle-code-btn');
  const codeBlock = block.querySelector('.code-block');
  toggleBtn.addEventListener('click', () => {
    const hidden = codeBlock.classList.toggle('hidden');
    toggleBtn.textContent = hidden ? 'show code' : 'hide code';
    if (!hidden && window.hljs) {
      block.querySelectorAll('code.language-python').forEach(el => hljs.highlightElement(el));
    }
  });

  contentArea.appendChild(block);
  scrollToBottomIfNeeded();
}

// ---------------------------------------------------------------------------
// MCP fallback badge in trace
// ---------------------------------------------------------------------------

function handleMcpFallback(evt) {
  addTraceStep({ ...evt, agent: 'coder_agent', step: 'mcp_fallback', type: 'step_error' });
}

// ---------------------------------------------------------------------------
// Profile ready
// ---------------------------------------------------------------------------

function handleProfileReady(evt) {
  // Bug 1 fix: use canonicalNode — 'profiler_agent' → 'profiler'
  const card = getOrCreateTurnCard('profiler');
  const contentArea = card.querySelector('.card-content-area');
  const profile = evt.profile || {};
  const rows = profile.rows ?? evt.rows;
  const cols = profile.columns ?? evt.columns;

  const summaryDiv = document.createElement('div');
  summaryDiv.className = 'grid grid-cols-2 gap-3 text-[11px]';
  summaryDiv.innerHTML = `
    <div class="p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/60 border border-stone-100 dark:border-zinc-700/50">
      <p class="text-[10px] font-medium text-stone-400 uppercase tracking-wider">Rows</p>
      <p class="text-lg font-bold font-mono text-stone-900 dark:text-stone-100">${rows?.toLocaleString() ?? '—'}</p>
    </div>
    <div class="p-2.5 rounded-xl bg-stone-50 dark:bg-zinc-800/60 border border-stone-100 dark:border-zinc-700/50">
      <p class="text-[10px] font-medium text-stone-400 uppercase tracking-wider">Columns</p>
      <p class="text-lg font-bold font-mono text-stone-900 dark:text-stone-100">${cols?.toLocaleString() ?? '—'}</p>
    </div>
    ${evt.task_type ? `<div class="col-span-2 p-2 rounded-xl bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-300 text-xs font-medium">
      Task Type: <strong>${escapeHtml(evt.task_type)}</strong> — Metric: <strong>${escapeHtml(evt.recommended_metric || '—')}</strong>
    </div>` : ''}
    ${(evt.data_quality_flags || []).length ? `<div class="col-span-2 space-y-1">
      <p class="text-[10px] font-medium text-stone-400 uppercase tracking-wider">Quality Flags</p>
      <div class="flex flex-wrap gap-1">
        ${(evt.data_quality_flags || []).map(f => `<span class="px-2 py-0.5 rounded-full text-[10px] bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200/60">${escapeHtml(String(f))}</span>`).join('')}
      </div>
    </div>` : ''}
  `;
  contentArea.appendChild(summaryDiv);
  scrollToBottomIfNeeded();
}

// ---------------------------------------------------------------------------
// Loop decision — Bug 1 fix: canonicalNode sweep (this is the real source of
// EDA/Features/Modeler duplicate cards, not just handleProfileReady)
// ---------------------------------------------------------------------------

function handleLoopDecision(evt) {
  // Bug 1 fix: canonicalNode on evt.agent ("features_agent" → "features", etc.)
  const key = canonicalNode(evt.agent);
  const card = getOrCreateTurnCard(key);
  const contentArea = card.querySelector('.card-content-area');

  const iteration = evt.iteration;
  const ceiling = evt.ceiling;
  const decision = evt.decision;
  const reasoning = evt.reasoning;

  const row = document.createElement('div');
  row.className = `flex items-start space-x-2 text-[11px] py-1.5 border-b border-stone-50 dark:border-zinc-800/50 last:border-0`;
  row.innerHTML = `
    <span class="flex-shrink-0 w-5 h-5 rounded-full ${decision === 'stop' ? 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700' : 'bg-blue-100 dark:bg-blue-950/40 text-blue-700'} flex items-center justify-center text-[10px] font-bold">
      ${decision === 'stop' ? '✓' : iteration}
    </span>
    <div class="flex-1 min-w-0">
      <div class="text-stone-700 dark:text-stone-300 font-medium">${decision === 'stop' ? 'Stop decided' : `Iter ${iteration}${ceiling ? ` / ${ceiling}` : ''}`}</div>
      ${reasoning ? `<div class="text-stone-400 dark:text-stone-500 truncate">${escapeHtml(reasoning.slice(0, 120))}</div>` : ''}
    </div>
  `;
  contentArea.appendChild(row);

  // Update loop visualizer
  updateLoopViz(key, iteration, ceiling || null, null);
  scrollToBottomIfNeeded();
}

function handleLoopEnd(evt) {
  const key = canonicalNode(evt.agent);
  const exitReason = evt.exit_reason;
  updateLoopViz(key, evt.iterations, null, exitReason);
}

// ---------------------------------------------------------------------------
// Hard block — Bug 5 fix: this case was missing entirely
// ---------------------------------------------------------------------------

function handleHardBlock(evt) {
  const card = getOrCreateTurnCard('features');
  const contentArea = card.querySelector('.card-content-area');
  const banner = document.createElement('div');
  banner.className = 'p-3.5 rounded-xl border-2 border-rose-500 bg-rose-50 dark:bg-rose-950/40 text-rose-900 dark:text-rose-100 space-y-1.5';
  banner.innerHTML = `
    <div class="flex items-center space-x-2">
      <span class="text-xl">🚫</span>
      <span class="font-bold text-sm">Hard Block — Destructive Action Detected</span>
    </div>
    <p class="text-xs">Reason: <strong>${escapeHtml(evt.reason || 'destructive_action')}</strong> — pausing for human review…</p>
    ${evt.diff ? `<div class="text-[10px] font-mono text-rose-700 dark:text-rose-300 bg-rose-100/60 dark:bg-rose-900/30 rounded p-2 overflow-x-auto">
      Diff: ${escapeHtml(JSON.stringify(evt.diff))}
    </div>` : ''}
  `;
  contentArea.appendChild(banner);
  scrollToBottomIfNeeded();
}

// ---------------------------------------------------------------------------
// Supervisor override events (retry cap, stall, ceiling)
// ---------------------------------------------------------------------------

function handleSupervisorOverride(evt) {
  const type = evt.type || evt.event;
  const LABELS = {
    retry_cap_override: { icon: '🛑', label: 'Retry Cap Override', color: 'border-rose-500 bg-rose-50 dark:bg-rose-950/40 text-rose-900 dark:text-rose-100' },
    stalled_retry_escalation: { icon: '⚠️', label: 'Stalled Retry — Escalating', color: 'border-amber-500 bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-100' },
    global_iteration_ceiling: { icon: '🔒', label: 'Global Iteration Ceiling Reached', color: 'border-purple-500 bg-purple-50 dark:bg-purple-950/40 text-purple-900 dark:text-purple-100' },
  };
  const meta = LABELS[type] || { icon: '⚙️', label: type, color: 'border-stone-400 bg-stone-50 dark:bg-zinc-800' };
  const card = getOrCreateTurnCard('supervisor');
  const contentArea = card.querySelector('.card-content-area');
  const banner = document.createElement('div');
  banner.className = `p-3 rounded-xl border-2 ${meta.color} space-y-1 text-xs animate-card-in`;
  banner.innerHTML = `
    <div class="flex items-center space-x-2 font-semibold text-sm">
      <span>${meta.icon}</span><span>${meta.label}</span>
    </div>
    ${evt.reason ? `<p>Reason: ${escapeHtml(evt.reason)}</p>` : ''}
    ${evt.llm_wanted ? `<p>LLM wanted → <code class="font-mono">${escapeHtml(evt.llm_wanted)}</code></p>` : ''}
    ${evt.tier !== undefined ? `<p>Tier: ${evt.tier} / Count: ${evt.count}</p>` : ''}
    ${evt.iteration !== undefined ? `<p>Iteration: ${evt.iteration} / Ceiling: ${evt.ceiling}</p>` : ''}
  `;
  contentArea.appendChild(banner);

  addTraceStep({ agent: 'supervisor', step: meta.label, type: 'step_error' });
  if (type === 'stalled_retry_escalation') {
    handleIterationResult({
      type: 'iteration_result',
      agent: 'supervisor',
      iteration: currentState.iteration ?? 0,
      best_metric: currentState.best_metric,
      metric_delta: 0.0,
      is_stall: true,
      task_spec: `Escalation: ${evt.reason || 'Stalled retry detected'}`,
    });
  }
  updateTelemetryHeader();
  scrollToBottomIfNeeded();
}

// ---------------------------------------------------------------------------
// Iteration Result & Ledger (Loop Tab)
// ---------------------------------------------------------------------------

function handleIterationResult(evt) {
  iterationLedger.push(evt);

  if (!loopLedgerContainer) return;
  if (loopLedgerContainer.querySelector('.italic')) {
    loopLedgerContainer.innerHTML = '';
  }

  const iter = evt.iteration ?? iterationLedger.length;
  const agentKey = canonicalNode(evt.agent || 'modeler');
  const meta = getAgentMeta(agentKey);
  const metric = evt.best_metric != null ? Number(evt.best_metric).toFixed(4) : '—';
  const delta = evt.metric_delta;
  const isStall = !!evt.is_stall;
  const taskSpec = evt.task_spec || '';

  let deltaPill = '';
  if (delta != null) {
    const numDelta = Number(delta);
    if (numDelta > 0.001) {
      deltaPill = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300">+${numDelta.toFixed(4)}</span>`;
    } else if (Math.abs(numDelta) <= 0.001) {
      deltaPill = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300">±${Math.abs(numDelta).toFixed(4)}</span>`;
    } else {
      deltaPill = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-100 dark:bg-rose-950/60 text-rose-700 dark:text-rose-300">${numDelta.toFixed(4)}</span>`;
    }
  } else {
    deltaPill = `<span class="px-1.5 py-0.5 rounded text-[10px] text-stone-400 bg-stone-100 dark:bg-zinc-800">baseline</span>`;
  }

  const row = document.createElement('div');
  row.className = `p-2.5 rounded-xl border ${isStall ? 'border-amber-400/80 bg-amber-50/50 dark:bg-amber-950/20' : 'border-stone-200/70 dark:border-zinc-800 bg-white dark:bg-zinc-850'} space-y-1.5 animate-card-in`;
  row.innerHTML = `
    <div class="flex items-center justify-between">
      <div class="flex items-center space-x-1.5">
        <span class="font-bold font-mono text-stone-800 dark:text-stone-200">#${iter}</span>
        <span class="text-stone-400">·</span>
        <span class="font-medium text-stone-700 dark:text-stone-300 text-xs">${meta.icon} ${escapeHtml(meta.label)}</span>
      </div>
      <div class="flex items-center space-x-1.5 font-mono">
        <span class="text-stone-700 dark:text-stone-200 font-bold">${metric}</span>
        ${deltaPill}
      </div>
    </div>
    ${taskSpec ? `<div class="text-[10px] text-stone-500 dark:text-stone-400 truncate">${escapeHtml(taskSpec)}</div>` : ''}
    ${isStall ? `<div class="pt-0.5"><span class="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-extrabold bg-rose-500 text-white animate-pulse">⚠️ STALL WARNING: Δ &lt; 0.001</span></div>` : ''}
  `;

  loopLedgerContainer.appendChild(row);
  loopLedgerContainer.scrollTop = loopLedgerContainer.scrollHeight;
  updateTelemetryHeader();
}

// ---------------------------------------------------------------------------
// Run Stop Reason Handler
// ---------------------------------------------------------------------------

function handleRunStopReason(evt) {
  const reason = evt.reason || 'converged';
  const detail = evt.detail || '';
  if (currentState) {
    currentState.stop_reason = reason;
  }

  if (stateStopReasonBox && stateStopReasonText) {
    stateStopReasonBox.classList.remove('hidden');
    const REASON_CONFIG = {
      converged: {
        border: 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200',
        label: '✓ CONVERGED — Optimization criteria satisfied',
      },
      stalled: {
        border: 'border-amber-500 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200',
        label: '⚠️ STALLED — Diminishing returns or repeated output',
      },
      hit_safety_ceiling: {
        border: 'border-rose-500 bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-200',
        label: '🛑 HIT SAFETY CEILING — Max iteration limit reached',
      },
      global_iteration_ceiling: {
        border: 'border-rose-500 bg-rose-50 dark:bg-rose-950/40 text-rose-800 dark:text-rose-200',
        label: '🛑 GLOBAL ITERATION CEILING — Safety ceiling reached',
      },
      user_rejected: {
        border: 'border-orange-500 bg-orange-50 dark:bg-orange-950/40 text-orange-800 dark:text-orange-200',
        label: '✕ USER REJECTED — Rejected at human review gate',
      },
      error: {
        border: 'border-rose-600 bg-rose-50 dark:bg-rose-950/40 text-rose-900 dark:text-rose-100',
        label: '✗ EXECUTION ERROR — Pipeline failed',
      },
    };
    const cfg = REASON_CONFIG[reason] || { border: 'border-stone-400 bg-stone-50 dark:bg-zinc-800 text-stone-800 dark:text-stone-200', label: reason.toUpperCase() };
    stateStopReasonBox.className = `p-3 rounded-xl border-2 ${cfg.border} space-y-1 shadow-xs animate-card-in`;
    stateStopReasonText.innerHTML = `<div class="font-bold">${escapeHtml(cfg.label)}</div>${detail ? `<div class="text-[10px] opacity-80 mt-1 font-normal">${escapeHtml(detail)}</div>` : ''}`;
  }

  updateHeaderStatus(currentRunId, reason);
  updateTelemetryHeader();
}

// ---------------------------------------------------------------------------
// RAG memory lookup — Bug 3 fix: nest under triggering agent's card
// ---------------------------------------------------------------------------

function handleRunMemoryLookup(evt) {
  // Use triggering_agent (set by calling_agent param in run_memory.py)
  // to find the correct parent card instead of creating a "run_memory" card.
  const parentKey = canonicalNode(evt.triggering_agent || evt.agent || 'run_memory');
  const card = getOrCreateTurnCard(parentKey);
  const contentArea = card.querySelector('.card-content-area');

  const results = evt.results || [];
  if (!results.length) return;

  const memDiv = document.createElement('div');
  memDiv.className = 'rounded-xl border border-stone-200 dark:border-zinc-700/70 overflow-hidden text-[11px]';
  memDiv.innerHTML = `
    <div class="px-3 py-2 bg-stone-50 dark:bg-zinc-800/60 border-b border-stone-100 dark:border-zinc-700/50 font-medium text-stone-500 dark:text-stone-400 flex items-center space-x-1.5">
      <span>🗄️</span><span>Prior Run Memory (${results.length} relevant)</span>
    </div>
    <div class="p-2 space-y-1.5">
      ${results.map(r => `
        <div class="p-2 rounded-lg bg-stone-50/60 dark:bg-zinc-800/40 space-y-0.5">
          <div class="flex justify-between">
            <span class="font-mono text-[10px] text-stone-500">${escapeHtml(r.run_id || '—')}</span>
            <span class="text-[10px] text-stone-400">${r.similarity != null ? `sim: ${r.similarity}` : ''}</span>
          </div>
          <p class="text-stone-700 dark:text-stone-300 leading-relaxed">${escapeHtml((r.text || '').slice(0, 200))}</p>
        </div>
      `).join('')}
    </div>
  `;
  contentArea.appendChild(memDiv);
  scrollToBottomIfNeeded();
}

// ---------------------------------------------------------------------------
// Judge verdict — Bug 1 fix: canonicalNode
// ---------------------------------------------------------------------------

function handleJudgeVerdict(evt) {
  // Bug 1 fix: 'judge_agent' → 'judge'
  const card = getOrCreateTurnCard('judge');
  const contentArea = card.querySelector('.card-content-area');
  const verdict = evt.verdict;
  const isAccept = verdict === 'accept';

  const verdictEl = document.createElement('div');
  verdictEl.className = `p-3.5 rounded-xl border-2 ${isAccept ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/40' : 'border-rose-500 bg-rose-50 dark:bg-rose-950/40'} space-y-2`;
  verdictEl.innerHTML = `
    <div class="flex items-center space-x-2">
      <span class="text-xl">${isAccept ? '✅' : '❌'}</span>
      <div>
        <span class="font-bold text-sm ${isAccept ? 'text-emerald-800 dark:text-emerald-200' : 'text-rose-800 dark:text-rose-200'}">
          ${isAccept ? 'ACCEPTED' : `REJECTED — Retry Tier ${evt.retry_tier || '?'}`}
        </span>
      </div>
    </div>
    ${evt.feedback ? `<p class="text-xs ${isAccept ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300'}">${escapeHtml(evt.feedback)}</p>` : ''}
    ${evt.best_metric != null ? `<p class="text-xs font-mono text-stone-500">Best metric: <strong>${evt.best_metric}</strong></p>` : ''}
  `;
  contentArea.appendChild(verdictEl);
  scrollToBottomIfNeeded();
}

// ---------------------------------------------------------------------------
// Supervisor routing hint
// ---------------------------------------------------------------------------

function handleSupervisorRouted(evt) {
  const card = getOrCreateTurnCard('supervisor');
  const contentArea = card.querySelector('.card-content-area');
  const pill = document.createElement('div');
  pill.className = 'text-[11px] flex items-center space-x-2 text-stone-500 dark:text-stone-400 py-1';
  pill.innerHTML = `<span>→</span><span class="font-mono font-medium text-stone-700 dark:text-stone-300">${escapeHtml(evt.next_agent || '—')}</span>
    ${evt.retry_tier ? `<span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 font-semibold">Tier ${evt.retry_tier}</span>` : ''}
    <span class="flex-1 truncate text-stone-400">${escapeHtml((evt.reasoning || '').slice(0, 80))}</span>`;
  contentArea.appendChild(pill);
  if (evt.next_agent) {
    updateTelemetryHeader(evt.next_agent);
  }
}

// ---------------------------------------------------------------------------
// Approval Required panel — Bug 6 fix: dropped_columns key now matches backend
// ---------------------------------------------------------------------------

function handleApprovalRequired(evt) {
  updateHeaderStatus(currentRunId, 'paused_for_approval');
  const runIdToApprove = evt.run_id || currentRunId;
  const featurePlan = evt.feature_plan || {};
  const diff = featurePlan.structural_diff || {};
  const reason = evt.reason || 'unknown';

  const card = getOrCreateTurnCard('human_approval');
  const statusPill = card.querySelector('.status-pill');
  if (statusPill) {
    statusPill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-orange-500 mr-1.5 animate-pulse"></span>Awaiting Decision`;
    statusPill.className = 'status-pill flex items-center text-[11px] font-medium px-2 py-1 rounded-full bg-orange-50 dark:bg-orange-950/30 text-orange-600 dark:text-orange-400';
  }

  const contentArea = card.querySelector('.card-content-area');

  const REASON_LABELS = {
    destructive_action: '⚠️ Destructive Action Detected',
    unresolved_exploration: '🔄 Exploration Didn\'t Converge',
    global_iteration_ceiling: '🔒 Global Iteration Ceiling Reached',
    hard_block: '🚫 Hard Block',
  };

  const panel = document.createElement('div');
  panel.className = 'space-y-3';
  panel.innerHTML = `
    <div class="p-3.5 rounded-xl border border-orange-200 dark:border-orange-900/50 bg-orange-50 dark:bg-orange-950/30 space-y-2">
      <div class="font-semibold text-sm text-orange-900 dark:text-orange-200">
        ${REASON_LABELS[reason] || '⏸ Human Approval Required'}
      </div>
      ${featurePlan.description ? `<p class="text-xs text-orange-800 dark:text-orange-300">${escapeHtml(featurePlan.description)}</p>` : ''}
    </div>

    ${(diff.dropped_columns && diff.dropped_columns.length) || diff.row_delta !== undefined ? `
    <div class="rounded-xl border border-stone-200 dark:border-zinc-700 p-3 space-y-2 text-xs">
      <p class="font-semibold text-stone-700 dark:text-stone-300">Dataset Diff</p>
      ${diff.dropped_columns && diff.dropped_columns.length ? `
        <div>
          <span class="text-stone-500">Dropped columns (${diff.dropped_columns.length}):</span>
          <div class="flex flex-wrap gap-1 mt-1">
            ${diff.dropped_columns.map(c => `<code class="px-1.5 py-0.5 rounded bg-rose-100 dark:bg-rose-950/50 text-rose-700 dark:text-rose-300 text-[10px]">${escapeHtml(c)}</code>`).join('')}
          </div>
        </div>
      ` : ''}
      ${diff.row_delta !== undefined && diff.row_delta !== 0 ? `
        <p class="text-stone-500">Row delta: <strong class="${diff.row_delta < 0 ? 'text-rose-600' : 'text-emerald-600'}">${diff.row_delta > 0 ? '+' : ''}${diff.row_delta}</strong></p>
      ` : ''}
    </div>
    ` : ''}

    <div class="approval-actions grid grid-cols-3 gap-2">
      <button id="approve-btn-${runIdToApprove}" class="col-span-1 py-2 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition-colors">✓ Approve</button>
      <button id="modify-btn-${runIdToApprove}" class="col-span-1 py-2 px-3 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-medium transition-colors">✎ Modify</button>
      <button id="reject-btn-${runIdToApprove}" class="col-span-1 py-2 px-3 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium transition-colors">✗ Reject</button>
    </div>
    <div class="approval-result-status hidden text-xs font-semibold text-emerald-600 dark:text-emerald-400"></div>
  `;

  async function sendApproval(decision) {
    const btnApprove = document.getElementById(`approve-btn-${runIdToApprove}`);
    const btnModify = document.getElementById(`modify-btn-${runIdToApprove}`);
    const btnReject = document.getElementById(`reject-btn-${runIdToApprove}`);
    const actionsContainer = panel.querySelector('.approval-actions');
    const resultStatus = panel.querySelector('.approval-result-status');
    [btnApprove, btnModify, btnReject].forEach(b => { if (b) b.disabled = true; });
    try {
      const res = await fetch(`/api/runs/${runIdToApprove}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_status: decision }),
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server returned HTTP ${res.status}`);
      }
      actionsContainer.classList.add('hidden');
      resultStatus.classList.remove('hidden');
      resultStatus.textContent = `✓ Submitted decision: ${decision.toUpperCase()} — resuming execution…`;
      resultStatus.className = 'approval-result-status text-xs font-semibold text-emerald-600 dark:text-emerald-400';
      updateHeaderStatus(runIdToApprove, 'running');
    } catch (err) {
      alert(`Error submitting decision: ${err.message}`);
      [btnApprove, btnModify, btnReject].forEach(b => { if (b) b.disabled = false; });
    }
  }

  const btnA = panel.querySelector(`#approve-btn-${runIdToApprove}`);
  const btnM = panel.querySelector(`#modify-btn-${runIdToApprove}`);
  const btnR = panel.querySelector(`#reject-btn-${runIdToApprove}`);
  if (btnA) btnA.addEventListener('click', () => sendApproval('approved'));
  if (btnM) btnM.addEventListener('click', () => sendApproval('modify'));
  if (btnR) btnR.addEventListener('click', () => sendApproval('reject'));

  contentArea.appendChild(panel);
  scrollToBottomIfNeeded();
}

function handleApprovalResumed(evt) {
  const targetRunId = evt.run_id || currentRunId;
  updateHeaderStatus(targetRunId, 'running');
  const card = activeTurnCards['human_approval'];
  if (card) {
    const actionsContainer = card.querySelector('.approval-actions');
    const resultStatus = card.querySelector('.approval-result-status');
    if (actionsContainer) actionsContainer.classList.add('hidden');
    if (resultStatus) {
      resultStatus.classList.remove('hidden');
      resultStatus.textContent = `✓ Decision: ${(evt.decision || 'approved').toUpperCase()} — Resumed`;
      resultStatus.className = 'approval-result-status text-xs font-semibold text-emerald-600 dark:text-emerald-400';
    }
    const statusPill = card.querySelector('.status-pill');
    if (statusPill) {
      statusPill.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>Approved`;
    }
  }
}

// ---------------------------------------------------------------------------
// Final Report Card
// ---------------------------------------------------------------------------

function handleReportReady(evt) {
  renderFinalReportCard(evt);
}

function renderFinalReportCard(evt) {
  if (document.getElementById('final-report-card')) return;

  const card = document.createElement('article');
  card.id = 'final-report-card';
  card.className = 'bg-white dark:bg-[#202024] border-t-4 border-[#D97757] border-x border-b border-stone-200/80 dark:border-zinc-800 rounded-2xl shadow-md p-6 space-y-5 animate-card-in';

  const reportMarkdown = evt.report || '# Pipeline Run Report\n\nNo content generated.';
  const artifactPath = evt.artifact_path || '';

  card.innerHTML = `
    <div class="flex items-center justify-between pb-3 border-b border-stone-100 dark:border-zinc-800">
      <div class="flex items-center space-x-2.5">
        <span class="w-8 h-8 rounded-xl bg-orange-100 dark:bg-orange-950/40 text-[#D97757] flex items-center justify-center font-bold text-sm">📑</span>
        <div>
          <h2 class="text-base font-semibold text-stone-900 dark:text-stone-100">Final Pipeline Report</h2>
          <p class="text-[11px] text-stone-400 dark:text-stone-500">Autonomous Synthesis</p>
        </div>
      </div>
      <button id="download-report-btn" class="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-[#D97757] hover:bg-[#C85A32] text-white text-xs font-medium shadow-sm transition-colors">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
        </svg>
        <span>Download (.md)</span>
      </button>
    </div>
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
  scrollToBottomIfNeeded();
  // Load artifacts list
  fetchRunArtifacts(evt.run_id || currentRunId);
}

// ---------------------------------------------------------------------------
// Run Completion / Error
// ---------------------------------------------------------------------------

function handleRunComplete(evt) {
  const stopReason = evt.stop_reason || currentState.stop_reason || 'completed';
  currentState.stop_reason = stopReason;
  updateHeaderStatus(currentRunId, stopReason);
  handleRunStopReason({ reason: stopReason });
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  fetchRecentRuns();
  updateTelemetryHeader();
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

// ---------------------------------------------------------------------------
// Chronological Trace Drawer
// ---------------------------------------------------------------------------

function addTraceStep(evt) {
  const agent = evt.agent || 'system';
  const step = evt.step || 'step';
  const duration = evt.duration_sec ? `${evt.duration_sec}s` : 'active';
  const isError = evt.type === 'step_error' || evt.event === 'step_error';

  traceEvents.push({ ...evt, timestamp: Date.now() });

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

  if (traceTimeline && traceTimeline.children.length === 1 && traceTimeline.firstElementChild.classList.contains('italic')) {
    traceTimeline.innerHTML = '';
  }
  traceTimeline?.appendChild(row);
}

// ---------------------------------------------------------------------------
// State Inspector — field-aware merge (Bug C5 fix)
// ---------------------------------------------------------------------------

function mergeStateUpdate(update) {
  for (const [key, val] of Object.entries(update)) {
    if (REDUCER_FIELDS.has(key) && Array.isArray(val)) {
      // Concat — node_end carries only the delta for reducer fields
      currentState[key] = (currentState[key] || []).concat(val);
    } else {
      currentState[key] = val;
    }
  }
  renderStateInspector();
}

function renderStateInspector() {
  // Retry budget bars
  const rc = currentState.retry_counts || {};
  ['tier1', 'tier2'].forEach((t, i) => {
    const bar = document.getElementById(`state-${t}-bar`);
    if (!bar) return;
    const count = rc[i + 1] || 0;
    const cells = bar.querySelectorAll('span');
    cells.forEach((cell, ci) => {
      cell.className = ci < count
        ? 'w-4 h-4 rounded-sm bg-amber-400 dark:bg-amber-500'
        : 'w-4 h-4 rounded-sm bg-stone-200 dark:bg-zinc-600';
    });
  });

  // Iteration count
  const iterEl = document.getElementById('state-iter-count');
  if (iterEl) iterEl.textContent = `${currentState.iteration ?? 0} / 200`;

  // Best metric
  const bmEl = document.getElementById('state-best-metric');
  if (bmEl) bmEl.textContent = currentState.best_metric != null ? Number(currentState.best_metric).toFixed(4) : '—';

  const trendEl = document.getElementById('state-metric-trend');
  if (trendEl) {
    const hist = currentState.metric_history || [];
    trendEl.textContent = hist.length ? hist.slice(-5).map(v => Number(v).toFixed(3)).join(' → ') : '';
  }

  // Stage pills
  const stagesEl = document.getElementById('state-stages');
  if (stagesEl) {
    const stages = [
      { key: 'profile', label: 'Profile', short: 'P' },
      { key: 'eda_findings', label: 'EDA', short: 'E' },
      { key: 'feature_set', label: 'Features', short: 'F' },
      { key: 'candidate_models', label: 'Models', short: 'M' },
    ];
    stagesEl.innerHTML = stages.map(s => {
      const done = s.key === 'candidate_models'
        ? (currentState[s.key] || []).length > 0
        : (currentState[s.key] && Object.keys(currentState[s.key]).length > 0);
      return `<div class="rounded-lg py-1 text-[10px] font-bold ${done ? 'bg-emerald-100 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300' : 'bg-stone-100 dark:bg-zinc-800 text-stone-400 dark:text-stone-500'}" title="${s.label}">${s.short}</div>`;
    }).join('');
  }

  // Stop reason box
  if (currentState.stop_reason && stateStopReasonBox) {
    stateStopReasonBox.classList.remove('hidden');
    if (stateStopReasonText) {
      stateStopReasonText.textContent = String(currentState.stop_reason).toUpperCase();
    }
  }

  // Model leaderboard
  const modelsEl = document.getElementById('state-models');
  if (modelsEl) {
    const models = (currentState.candidate_models || []).slice().sort((a, b) => (b.cv_score || 0) - (a.cv_score || 0));
    if (models.length) {
      modelsEl.innerHTML = models.map((m, i) => `
        <div class="flex items-center justify-between px-2 py-1 rounded-lg ${i === 0 ? 'bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200/60 dark:border-emerald-800/40' : 'bg-stone-50 dark:bg-zinc-800/50'}">
          <span class="font-mono text-stone-700 dark:text-stone-300">${i === 0 ? '🏆 ' : ''}${escapeHtml(m.model_family || '?')}</span>
          <span class="font-mono font-bold text-stone-900 dark:text-stone-100">${Number(m.cv_score).toFixed(4)}</span>
        </div>
      `).join('');
    } else {
      modelsEl.innerHTML = '<div class="text-stone-400 dark:text-stone-500 italic">No models yet</div>';
    }
  }

  // Raw dump
  const rawEl = document.getElementById('state-raw-dump');
  if (rawEl) {
    const displayState = { ...currentState };
    delete displayState.messages;  // usually large
    rawEl.textContent = JSON.stringify(displayState, null, 2);
  }

  updateTelemetryHeader();
}

// ---------------------------------------------------------------------------
// Raw Event Log
// ---------------------------------------------------------------------------

function renderRawEventLog() {
  if (!eventLogList) return;
  const filter = (eventFilterInput?.value || '').toLowerCase();
  const filtered = filter
    ? rawEventLog.filter(e => (e.agent || '').toLowerCase().includes(filter) || (e.type || '').toLowerCase().includes(filter))
    : rawEventLog;

  if (eventLogCount) eventLogCount.textContent = `${rawEventLog.length} events`;

  // Only re-render last 200 for performance
  const visible = filtered.slice(-200);
  if (!visible.length) {
    eventLogList.innerHTML = '<div class="text-stone-400 dark:text-stone-500 italic p-2">No events yet</div>';
    return;
  }

  // Incremental: just append if only new events added (no filter change)
  eventLogList.innerHTML = '';
  visible.forEach(ev => {
    const row = document.createElement('div');
    const isError = ev.type === 'step_error' || ev.type === 'run_error';
    row.className = `px-2 py-1 rounded-lg cursor-pointer hover:bg-stone-100 dark:hover:bg-zinc-800/60 ${isError ? 'text-rose-500' : 'text-stone-600 dark:text-stone-300'}`;
    row.innerHTML = `
      <span class="text-stone-400">#${ev._idx ?? ''}</span>
      <span class="ml-1 font-semibold">${escapeHtml(ev.agent || '—')}</span>
      <span class="text-stone-400"> · </span>
      <span>${escapeHtml(ev.type || ev.event || '?')}</span>
    `;
    row.addEventListener('click', () => {
      // Expand JSON inline
      if (row.querySelector('.ev-expanded')) {
        row.querySelector('.ev-expanded').remove();
        return;
      }
      const pre = document.createElement('pre');
      pre.className = 'ev-expanded mt-1 p-2 rounded bg-zinc-900 text-zinc-300 text-[9px] overflow-x-auto max-h-40';
      pre.textContent = JSON.stringify(ev, null, 2);
      row.appendChild(pre);
    });
    eventLogList.appendChild(row);
  });
  eventLogList.scrollTop = eventLogList.scrollHeight;
}

if (eventFilterInput) {
  eventFilterInput.addEventListener('input', renderRawEventLog);
}
if (clearEventLogBtn) {
  clearEventLogBtn.addEventListener('click', () => {
    rawEventLog = [];
    renderRawEventLog();
  });
}

// ---------------------------------------------------------------------------
// Debug Report Export & Download
// ---------------------------------------------------------------------------

function generateDebugReport() {
  return {
    run_id: currentRunId,
    exported_at: new Date().toISOString(),
    status: currentStatus,
    stop_reason: currentState.stop_reason || null,
    dataset_path: datasetInput ? datasetInput.value : null,
    mode: modeSelect ? modeSelect.value : null,
    telemetry: {
      global_iteration: currentState.iteration ?? 0,
      best_metric: currentState.best_metric ?? null,
      retry_counts: currentState.retry_counts ?? {},
      metric_history: currentState.metric_history ?? [],
    },
    candidate_models: currentState.candidate_models ?? [],
    iteration_ledger: iterationLedger,
    loop_progress: loopProgress,
    trace_events: traceEvents,
    raw_event_count: rawEventLog.length,
    raw_events: rawEventLog,
  };
}

if (exportDebugReportBtn) {
  exportDebugReportBtn.addEventListener('click', async () => {
    try {
      const report = generateDebugReport();
      await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
      const originalText = exportDebugReportBtn.innerHTML;
      exportDebugReportBtn.innerHTML = '✓ Copied!';
      exportDebugReportBtn.classList.add('bg-emerald-500', 'text-white');
      setTimeout(() => {
        exportDebugReportBtn.innerHTML = originalText;
        exportDebugReportBtn.classList.remove('bg-emerald-500', 'text-white');
      }, 2000);
    } catch (err) {
      alert(`Clipboard write failed: ${err.message}`);
    }
  });
}

if (downloadDebugReportBtn) {
  downloadDebugReportBtn.addEventListener('click', () => {
    try {
      const report = generateDebugReport();
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `debug_report_${currentRunId || 'run'}_${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Download failed: ${err.message}`);
    }
  });
}

// ---------------------------------------------------------------------------
// Loop Visualizer
// ---------------------------------------------------------------------------

function updateLoopViz(agentKey, iteration, ceiling, exitReason) {
  if (!loopVizContainer) return;
  const key = canonicalNode(agentKey);
  if (!loopProgress[key]) {
    loopProgress[key] = { iteration: 0, ceiling: ceiling, exitReason: null };
    // Clear placeholder
    if (loopVizContainer.querySelector('.italic')) loopVizContainer.innerHTML = '';
  }
  if (iteration != null) loopProgress[key].iteration = iteration;
  if (ceiling != null) loopProgress[key].ceiling = ceiling;
  if (exitReason) loopProgress[key].exitReason = exitReason;

  // Re-render all
  loopVizContainer.innerHTML = '';
  for (const [aKey, prog] of Object.entries(loopProgress)) {
    const meta = getAgentMeta(aKey);
    const pct = prog.ceiling ? Math.min(100, Math.round((prog.iteration / prog.ceiling) * 100)) : 50;
    const EXIT_BADGES = {
      llm_stop: { cls: 'bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700', label: '✓ LLM Stop' },
      hard_block: { cls: 'bg-rose-100 dark:bg-rose-950/40 text-rose-700', label: '🚫 Hard Block' },
      plateau: { cls: 'bg-amber-100 dark:bg-amber-950/40 text-amber-700', label: '↔ Plateau' },
      ceiling: { cls: 'bg-orange-100 dark:bg-orange-950/40 text-orange-700', label: '⚠ Ceiling Hit' },
    };
    const badge = prog.exitReason ? EXIT_BADGES[prog.exitReason] : null;

    const row = document.createElement('div');
    row.className = 'space-y-1';
    row.innerHTML = `
      <div class="flex items-center justify-between text-[11px]">
        <span class="flex items-center space-x-1">
          <span>${meta.icon}</span>
          <span class="font-medium text-stone-700 dark:text-stone-300">${escapeHtml(meta.label)}</span>
        </span>
        ${badge ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-semibold ${badge.cls}">${badge.label}</span>` : ''}
        <span class="font-mono text-stone-400">${prog.iteration}${prog.ceiling ? ` / ${prog.ceiling}` : ''}</span>
      </div>
      <div class="w-full bg-stone-100 dark:bg-zinc-800 h-2 rounded-full overflow-hidden">
        <div class="bg-[#D97757] h-full rounded-full transition-all duration-300" style="width: ${pct}%"></div>
      </div>
    `;
    loopVizContainer.appendChild(row);
  }
}

// ---------------------------------------------------------------------------
// Artifacts panel
// ---------------------------------------------------------------------------

async function fetchRunArtifacts(runId) {
  if (!runId) return;
  try {
    const res = await fetch(`/api/runs/${runId}/artifacts`);
    if (!res.ok) return;
    const data = await res.json();
    // Could render in a dedicated panel; for now just log to raw events
    rawEventLog.push({ _idx: rawEventLog.length, type: 'artifacts_loaded', agent: 'server', ...data });
  } catch (e) {
    // Non-critical
  }
}

// ---------------------------------------------------------------------------
// Run Form Submission
// ---------------------------------------------------------------------------

runConfigForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const datasetPath = datasetInput.value.trim();
  if (!datasetPath) {
    alert('Please enter a dataset file path or upload a file first.');
    return;
  }

  startRunBtn.disabled = true;
  startRunBtn.innerHTML = `<svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg><span>Starting…</span>`;

  // Reset all client state for the new run
  _resetRunState();
  turnsFeed.innerHTML = '';

  try {
    const res = await fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_path: datasetPath,
        mode: modeSelect.value,
        guided_mode: guidedModeToggle.checked,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    startEventStream(data.run_id);
    fetchRecentRuns();
  } catch (err) {
    alert(`Failed to start run: ${err.message}`);
  } finally {
    startRunBtn.disabled = false;
    startRunBtn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg><span>Run Pipeline</span>`;
  }
});

// ---------------------------------------------------------------------------
// New Run Button
// ---------------------------------------------------------------------------

newRunBtn.addEventListener('click', () => {
  _resetRunState();
  turnsFeed.innerHTML = '';
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  currentRunId = null;
  headerRunId.textContent = 'No active run';
  headerRunStatusPill.classList.add('hidden');
  configCard.scrollIntoView({ behavior: 'smooth' });
});

// ---------------------------------------------------------------------------
// Recent Runs Sidebar
// ---------------------------------------------------------------------------

async function fetchRecentRuns() {
  try {
    const res = await fetch('/api/runs');
    if (!res.ok) return;
    const runs = await res.json();
    renderRunsList(runs);
  } catch (e) {
    // Server not yet ready
  }
}

function renderRunsList(runs) {
  if (!runs.length) {
    runsList.innerHTML = '<div class="p-3 text-center text-xs text-stone-400 dark:text-stone-500 italic">No past runs recorded</div>';
    return;
  }
  const STATUS_DOTS = {
    running: 'bg-blue-500 animate-pulse',
    paused_for_approval: 'bg-orange-500',
    completed: 'bg-emerald-500',
    error: 'bg-rose-500',
  };
  runsList.innerHTML = runs.slice().reverse().map(r => `
    <button class="run-list-item w-full text-left px-3 py-2.5 rounded-xl hover:bg-white dark:hover:bg-zinc-800 transition-colors border border-transparent hover:border-stone-200 dark:hover:border-zinc-700 space-y-1" data-run-id="${escapeHtml(r.run_id)}">
      <div class="flex items-center justify-between">
        <span class="font-mono text-[11px] font-medium text-stone-700 dark:text-stone-300 truncate">${escapeHtml(r.run_id.slice(-8))}</span>
        <span class="flex-shrink-0 w-2 h-2 rounded-full ${STATUS_DOTS[r.status] || 'bg-stone-400'}"></span>
      </div>
      <div class="text-[10px] text-stone-400 dark:text-stone-500 truncate">${escapeHtml(r.dataset_path.split(/[/\\]/).pop())}</div>
    </button>
  `).join('');

  runsList.querySelectorAll('.run-list-item').forEach(btn => {
    btn.addEventListener('click', () => loadRunDetails(btn.getAttribute('data-run-id')));
  });
}

async function loadRunDetails(runId) {
  _resetRunState();
  turnsFeed.innerHTML = '';
  currentRunId = runId;

  try {
    const res = await fetch(`/api/runs/${runId}/report`);
    if (res.ok) {
      const data = await res.json();
      updateHeaderStatus(runId, data.status);
      if (data.report) {
        renderFinalReportCard({ report: data.report, artifact_path: data.artifact_path, run_id: runId });
      }
    }
  } catch (e) { /* noop */ }

  // Re-attach SSE if still running, or populate stop reason and state
  try {
    const listRes = await fetch('/api/runs');
    if (listRes.ok) {
      const runs = await listRes.json();
      const run = runs.find(r => r.run_id === runId);
      if (run) {
        if (run.stop_reason) {
          handleRunStopReason({ reason: run.stop_reason });
        }
        if (run.status === 'running') {
          startEventStream(runId);
        } else {
          updateHeaderStatus(runId, run.stop_reason || run.status);
        }
      }
    }
  } catch (e) { /* noop */ }
}

refreshRunsBtn.addEventListener('click', fetchRecentRuns);

// ---------------------------------------------------------------------------
// Utility Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ---------------------------------------------------------------------------
// Initial Boot
// ---------------------------------------------------------------------------
initTheme();
const savedDrawerOpen = localStorage.getItem('drawer_open');
if (savedDrawerOpen !== null) {
  setDrawerOpen(savedDrawerOpen === '1', localStorage.getItem('active_drawer_tab') || 'trace');
} else {
  // Default open on desktop viewports
  setDrawerOpen(window.innerWidth >= 1024, 'trace');
}
fetchRecentRuns();
updateTelemetryHeader();

/* ================================================================
   ML Agent v2 — WebSocket Client & Block Renderer
   ================================================================ */

'use strict';

// ── Session ──────────────────────────────────────────────────────────────────
const sessionId = 'session_' + Math.random().toString(36).slice(2, 10);
let ws = null;
let pendingHandles = [];    // {handle, filename}
let isRunning = false;
let isWaitingForHuman = false;
let currentAssistantBlocks = null;  // DOM container for current assistant turn's blocks

// ── DOM refs ──────────────────────────────────────────────────────────────────
const transcript    = document.getElementById('transcript');
const welcomeState  = document.getElementById('welcome-state');
const input         = document.getElementById('message-input');
const sendBtn       = document.getElementById('send-btn');
const fileInput     = document.getElementById('file-input');
const attachChips   = document.getElementById('attachment-chips');
const statusDot     = document.querySelector('.status-dot');
const statusText    = document.getElementById('status-text');
const sessionLabel  = document.getElementById('session-label');
const dropOverlay   = document.getElementById('drop-overlay');
const expList       = document.getElementById('experiments-list');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebar       = document.getElementById('sidebar');

// ── Session label ─────────────────────────────────────────────────────────────
sessionLabel.textContent = 'Session ' + sessionId.slice(8, 14);

// ── Sidebar toggle ────────────────────────────────────────────────────────────
sidebarToggle.addEventListener('click', () => {
  sidebar.classList.toggle('collapsed');
});

// ── Textarea auto-resize ──────────────────────────────────────────────────────
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 200) + 'px';
  sendBtn.disabled = input.value.trim() === '' && pendingHandles.length === 0;
});

// ── Keyboard send ─────────────────────────────────────────────────────────────
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled) handleSend();
  }
});

// ── File attachment via button ────────────────────────────────────────────────
fileInput.addEventListener('change', async () => {
  for (const file of fileInput.files) {
    await uploadFile(file);
  }
  fileInput.value = '';
});

// ── Drag-and-drop ─────────────────────────────────────────────────────────────
const composerEl = document.getElementById('composer');

['dragenter', 'dragover'].forEach(evt => {
  composerEl.addEventListener(evt, (e) => {
    e.preventDefault();
    dropOverlay.classList.add('active');
  });
});
['dragleave', 'drop'].forEach(evt => {
  composerEl.addEventListener(evt, (e) => {
    e.preventDefault();
    dropOverlay.classList.remove('active');
  });
});
composerEl.addEventListener('drop', async (e) => {
  for (const file of e.dataTransfer.files) {
    await uploadFile(file);
  }
});

// ── Example chips ─────────────────────────────────────────────────────────────
function setExample(text) {
  input.value = text;
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 200) + 'px';
  sendBtn.disabled = false;
  input.focus();
}

// ── Upload file to /upload ─────────────────────────────────────────────────────
async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    if (!res.ok) throw new Error('Upload failed');
    const data = await res.json();
    pendingHandles.push({ handle: data.handle, filename: data.filename });
    renderAttachChip(data.handle, data.filename);
    sendBtn.disabled = false;
  } catch (err) {
    console.error('Upload error:', err);
  }
}

function renderAttachChip(handle, filename) {
  const chip = document.createElement('div');
  chip.className = 'attach-chip';
  chip.dataset.handle = handle;
  chip.innerHTML = `
    <span class="chip-icon">${getFileIcon(filename)}</span>
    <span>${filename}</span>
    <span class="chip-remove" title="Remove">✕</span>
  `;
  chip.querySelector('.chip-remove').addEventListener('click', () => {
    pendingHandles = pendingHandles.filter(h => h.handle !== handle);
    chip.remove();
    sendBtn.disabled = input.value.trim() === '' && pendingHandles.length === 0;
  });
  attachChips.appendChild(chip);
}

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const map = {
    csv: '📊', parquet: '📦', json: '📋', jsonl: '📋',
    tsv: '📊', xlsx: '📊', arrow: '📦',
    png: '🖼️', jpg: '🖼️', jpeg: '🖼️',
    wav: '🎵', mp3: '🎵',
  };
  return map[ext] || '📄';
}

// ── WebSocket connection ───────────────────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/session/${sessionId}`);

  ws.onopen = () => setStatus('idle', 'Ready');
  ws.onclose = () => {
    setStatus('error', 'Disconnected');
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => setStatus('error', 'Connection error');
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleEvent(msg);
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };
}

connectWS();

// ── Send handler ──────────────────────────────────────────────────────────────
document.getElementById('send-btn').addEventListener('click', handleSend);

function handleSend() {
  const text = input.value.trim();
  if (!text && pendingHandles.length === 0) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    alert('Not connected. Please wait.');
    return;
  }

  // Hide welcome state on first send
  if (welcomeState) welcomeState.style.display = 'none';

  const handles = pendingHandles.map(h => h.handle);

  // Clear composer
  input.value = '';
  input.style.height = 'auto';
  pendingHandles = [];
  attachChips.innerHTML = '';
  sendBtn.disabled = true;

  // Send message
  ws.send(JSON.stringify({ type: 'user_message', content: text, attachments: handles }));

  // Start a fresh assistant turn
  startAssistantTurn();
  setStatus('running', 'Processing…');
  isRunning = true;
}

// ── Event dispatcher ──────────────────────────────────────────────────────────
function handleEvent(event) {
  switch (event.type) {

    case 'user_message':
      renderUserMessage(event.content, event.attachments || []);
      break;

    case 'node_start':
      updatePipelineStep(event.node, 'running');
      break;

    case 'node_end':
      updatePipelineStep(event.node, 'done');
      break;

    case 'eda_report':
      appendBlock(buildEDABlock(event));
      break;

    case 'thinking':
      appendBlock(buildThinkingBlock(event));
      break;

    case 'tool_call':
    case 'tool_result':
      appendBlock(buildToolBlock(event));
      break;

    case 'code_block':
      appendBlock(buildCodeBlock(event));
      break;

    case 'execution_result':
      appendBlock(buildExecutionResultBlock(event));
      addExperiment(event);
      break;

    case 'selector_verdict':
      appendBlock(buildVerdictBlock(event));
      if (event.decision === 'converge') {
        setStatus('done', 'Complete');
        isRunning = false;
      }
      break;

    case 'human_input_request':
      appendBlock(buildHumanInputBlock(event));
      setStatus('waiting', 'Waiting for your input');
      isWaitingForHuman = true;
      break;

    case 'assistant_message':
      appendBlock(buildProseBlock(event.content));
      break;

    case 'error':
      appendBlock(buildErrorBlock(event));
      setStatus('error', 'Error');
      isRunning = false;
      break;

    case 'pong':
      break;

    default:
      console.log('Unknown event:', event.type, event);
  }

  // Scroll transcript to bottom
  transcript.scrollTop = transcript.scrollHeight;
}

// ── Transcript rendering ──────────────────────────────────────────────────────
function renderUserMessage(content, handles) {
  // Find any uploaded filenames for the chips
  const chipHtml = handles.length
    ? handles.map(h => `<span class="attach-chip"><span class="chip-icon">📄</span>${h}</span>`).join('')
    : '';

  const turn = document.createElement('div');
  turn.className = 'turn turn-user';
  turn.innerHTML = `
    <div class="bubble">
      ${chipHtml ? `<div style="margin-bottom:4px;display:flex;gap:6px;flex-wrap:wrap">${chipHtml}</div>` : ''}
      ${escHtml(content)}
    </div>
  `;
  transcript.appendChild(turn);
}

function startAssistantTurn() {
  const turn = document.createElement('div');
  turn.className = 'turn turn-assistant';
  turn.innerHTML = `
    <div class="agent-header">
      <div class="agent-avatar">🤖</div>
      <span class="agent-name">ML Agent</span>
    </div>
    <div class="blocks-stack" id="current-blocks"></div>
  `;
  transcript.appendChild(turn);
  currentAssistantBlocks = turn.querySelector('#current-blocks');
}

function appendBlock(el) {
  if (!currentAssistantBlocks) startAssistantTurn();
  currentAssistantBlocks.appendChild(el);
  transcript.scrollTop = transcript.scrollHeight;
}

// ── Block builders ────────────────────────────────────────────────────────────

function buildCollapsibleBlock(cls, iconEmoji, labelHtml, bodyHtml, startExpanded = false) {
  const el = document.createElement('div');
  el.className = `block ${cls}`;
  if (startExpanded) el.classList.add('expanded');
  el.innerHTML = `
    <div class="block-header">
      <span class="block-icon">${iconEmoji}</span>
      <span class="block-label">${labelHtml}</span>
      <span class="block-chevron">›</span>
    </div>
    <div class="block-body">${bodyHtml}</div>
  `;
  el.querySelector('.block-header').addEventListener('click', () => {
    el.classList.toggle('expanded');
  });
  return el;
}

function buildThinkingBlock(event) {
  const preview = (event.content || '').slice(0, 120).replace(/\n/g, ' ');
  const fullContent = `<div class="thinking-content">${escHtml(event.content || '')}</div>`;
  return buildCollapsibleBlock(
    'block-thinking',
    '💭',
    `<span class="block-icon-label">Thinking…</span>`,
    fullContent,
    false  // collapsed by default
  );
}

function buildEDABlock(event) {
  const summary = event.summary || 'Explored the data';
  const mdHtml = renderMarkdown(event.content_markdown || '');
  const body = `<div class="eda-content">${mdHtml}</div>`;
  return buildCollapsibleBlock(
    'block-eda',
    '📊',
    `<span class="label-strong">${escHtml(summary)}</span>`,
    body,
    false  // collapsed by default
  );
}

function buildToolBlock(event) {
  const isCall = event.type === 'tool_call';
  const icon = isCall ? '🔧' : '✅';
  const dirLabel = isCall ? 'Called' : 'Result';
  const label = `<span class="label-strong">${escHtml(event.tool)}</span> — ${dirLabel}`;
  const payload = isCall ? event.input : event.output;
  const body = `<div class="tool-content"><pre style="white-space:pre-wrap;font-size:11px">${escHtml(JSON.stringify(payload, null, 2))}</pre></div>`;
  return buildCollapsibleBlock('block-tool', icon, label, body, false);
}

function buildCodeBlock(event) {
  const lines = (event.content || '').split('\n');
  const collapsed = lines.length > 30;
  const body = `<pre class="code-content"><code class="language-python">${escHtml(event.content || '')}</code></pre>`;
  const label = `<span class="label-strong">Generated code</span> — ${lines.length} lines`;
  const el = buildCollapsibleBlock('block-code', '💻', label, body, !collapsed);
  // Syntax highlight
  setTimeout(() => {
    const codeEl = el.querySelector('code');
    if (codeEl && window.hljs) {
      hljs.highlightElement(codeEl);
    }
  }, 50);
  return el;
}

function buildExecutionResultBlock(event) {
  const ok = event.status === 'success';
  const cvMean = (event.cv_mean || 0).toFixed(4);
  const cvStd  = (event.cv_std  || 0).toFixed(4);
  const stdoutTail = event.stdout_tail || '';
  const stderrTail = event.stderr_tail || '';
  const expId  = event.experiment_id || '?';

  const metricHtml = ok
    ? `<div class="metric-item">
        <div class="metric-label">CV Score</div>
        <div class="metric-value">${cvMean}</div>
       </div>
       <div class="metric-item">
        <div class="metric-label">Std Dev</div>
        <div class="metric-value" style="font-size:15px;color:var(--text-secondary)">±${cvStd}</div>
       </div>`
    : `<div class="metric-item">
        <div class="metric-label">Status</div>
        <div class="metric-value error-val">Failed</div>
       </div>`;

  const stdoutSection = stdoutTail
    ? `<div class="stdout-section">
        <div class="stdout-label">Stdout (tail)</div>
        <div class="stdout-content">${escHtml(stdoutTail)}</div>
       </div>`
    : '';

  const stderrSection = stderrTail
    ? `<div class="stdout-section">
        <div class="stdout-label">Stderr</div>
        <div class="stdout-content" style="color:var(--accent-red)">${escHtml(stderrTail)}</div>
       </div>`
    : '';

  const body = `
    <div class="result-metrics">${metricHtml}</div>
    ${stdoutSection}${stderrSection}
  `;

  const label = `<span class="label-strong">${expId}</span> — ${ok ? `CV: ${cvMean} ± ${cvStd}` : 'Execution failed'}`;
  const el = buildCollapsibleBlock(
    ok ? 'block-result' : 'block-result error',
    ok ? '✅' : '❌',
    label,
    body,
    true  // expanded by default — metrics are the key output
  );
  return el;
}

function buildVerdictBlock(event) {
  const decision = event.decision || 'redirect';
  const el = document.createElement('div');
  el.className = 'block-verdict';
  el.innerHTML = `
    <div class="verdict-header">
      <span class="verdict-badge">Selector Verdict</span>
      <span class="verdict-decision ${decision}">${decision === 'converge' ? '✅ Converge' : '↩️ Continue'}</span>
    </div>
    <div class="verdict-body">
      <div class="verdict-detail">${escHtml(event.detail || '')}</div>
      ${event.methodology_note ? `<div class="verdict-methodology">${escHtml(event.methodology_note)}</div>` : ''}
    </div>
  `;
  return el;
}

function buildHumanInputBlock(event) {
  const el = document.createElement('div');
  el.className = 'block-human-input';
  const question = event.question || 'Clarification needed.';
  el.innerHTML = `
    <div class="human-input-header">
      <span class="waiting-badge">⏸ Waiting for input</span>
    </div>
    <div class="human-input-body">
      <div class="human-question">${renderMarkdown(question)}</div>
      <div class="inline-reply">
        <textarea class="inline-reply-input" placeholder="Type your answer…" rows="1"></textarea>
        <button class="inline-reply-send">Send</button>
      </div>
    </div>
  `;

  const replyInput = el.querySelector('.inline-reply-input');
  const replySend = el.querySelector('.inline-reply-send');

  function submitReply() {
    const answer = replyInput.value.trim();
    if (!answer) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'user_message', content: answer, attachments: [] }));
    el.querySelector('.human-input-body').innerHTML = `<div class="verdict-detail" style="color:var(--text-secondary)">✓ Replied: "${escHtml(answer)}"</div>`;
    el.classList.remove('block-human-input');
    el.style.animation = 'none';
    isWaitingForHuman = false;
    setStatus('running', 'Processing…');
  }

  replyInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitReply(); }
  });
  replySend.addEventListener('click', submitReply);
  setTimeout(() => replyInput.focus(), 100);
  return el;
}

function buildProseBlock(content) {
  const el = document.createElement('div');
  el.className = 'message-prose';
  el.innerHTML = renderMarkdown(content || '');
  return el;
}

function buildErrorBlock(event) {
  const el = document.createElement('div');
  el.className = 'block-error';
  el.innerHTML = `
    <div class="error-header"><span class="error-badge">⚠ Error${event.node ? ` in ${event.node}` : ''}</span></div>
    <div class="error-message">${escHtml(event.message || 'Unknown error')}</div>
  `;
  return el;
}

// ── Sidebar helpers ──────────────────────────────────────────────────────────

function updatePipelineStep(node, state) {
  const stepEl = document.getElementById(`step-${node}`);
  if (!stepEl) return;
  stepEl.classList.remove('active', 'running', 'done');
  stepEl.classList.add(state === 'running' ? 'running' : (state === 'done' ? 'done' : 'active'));
}

function addExperiment(event) {
  const empty = expList.querySelector('.exp-empty');
  if (empty) empty.remove();

  const entry = document.createElement('div');
  entry.className = 'exp-entry';
  entry.innerHTML = `
    <div class="exp-id">${escHtml(event.experiment_id || '?')}</div>
    <div class="exp-score">CV ${(event.cv_mean || 0).toFixed(4)} ± ${(event.cv_std || 0).toFixed(4)}</div>
  `;
  expList.appendChild(entry);
}

// ── Status bar ───────────────────────────────────────────────────────────────
function setStatus(state, label) {
  statusDot.className = `status-dot ${state}`;
  statusText.textContent = label;
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderMarkdown(md) {
  if (window.marked) {
    try {
      return marked.parse(md || '', { breaks: true, gfm: true });
    } catch (e) {
      return escHtml(md);
    }
  }
  // Minimal fallback: bold, code, newlines
  return escHtml(md || '')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

// ── Initial state: enable send when there's content ──────────────────────────
input.addEventListener('input', () => {
  sendBtn.disabled = input.value.trim() === '' && pendingHandles.length === 0;
});

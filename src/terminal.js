// =====================================================================
// Claude HQ — embedded terminal panel.
// Hosts one xterm.js Terminal per HQ-spawned agent. The Rust side owns
// the actual PTYs (see src-tauri/src/pty.rs) and streams output through
// Tauri events; we just render bytes here and ship input back via invoke.
// =====================================================================

const TauriCore  = (window.__TAURI__ && window.__TAURI__.core)  || null;
const TauriEvent = (window.__TAURI__ && window.__TAURI__.event) || null;
const invoke = TauriCore ? TauriCore.invoke : null;

const TermXterm = window.Terminal;
const TermFitAddon = (window.FitAddon && window.FitAddon.FitAddon) || null;

// One persistent xterm per session id. We never tear them down on
// minimize — only on PTY exit — so scrollback survives hide/show.
const Sessions = new Map(); // id -> { term, fit, cwd, mounted: bool, agentKey }

const panel    = document.getElementById('term-panel');
const titleEl  = panel?.querySelector('.title');
const cwdEl    = panel?.querySelector('.cwd');
const hostEl   = panel?.querySelector('.term-host');
const minBtn   = document.getElementById('term-minimize');
const killBtn  = document.getElementById('term-kill');
const titlebar = panel?.querySelector('.titlebar');
const resizeEl = panel?.querySelector('.resize');

let activeId = null;
let outputUnlisten = null;
let exitUnlisten = null;

// ---- Panel geometry (persisted) ----

const STORAGE_KEY = 'claudeHqTermPanel';
const DEFAULT_GEOM = { x: 200, y: 120, w: 640, h: 420 };
let geom = loadGeom();

function loadGeom() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_GEOM };
    const g = JSON.parse(raw);
    return {
      x: Number.isFinite(g.x) ? g.x : DEFAULT_GEOM.x,
      y: Number.isFinite(g.y) ? g.y : DEFAULT_GEOM.y,
      w: Number.isFinite(g.w) ? g.w : DEFAULT_GEOM.w,
      h: Number.isFinite(g.h) ? g.h : DEFAULT_GEOM.h,
    };
  } catch { return { ...DEFAULT_GEOM }; }
}
function saveGeom() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(geom)); } catch {}
}
function applyGeom() {
  if (!panel) return;
  // Keep on-screen.
  const margin = 8;
  const maxX = Math.max(margin, window.innerWidth  - geom.w - margin);
  const maxY = Math.max(margin, window.innerHeight - geom.h - margin);
  geom.x = Math.min(Math.max(geom.x, margin), maxX);
  geom.y = Math.min(Math.max(geom.y, margin), maxY);
  panel.style.left   = geom.x + 'px';
  panel.style.top    = geom.y + 'px';
  panel.style.width  = geom.w + 'px';
  panel.style.height = geom.h + 'px';
}

// ---- Tauri event wiring (set up once) ----

async function setupTauriListeners() {
  if (!TauriEvent || outputUnlisten) return;
  outputUnlisten = await TauriEvent.listen('pty:output', (e) => {
    const { session_id, data_b64 } = e.payload || {};
    const sess = Sessions.get(session_id);
    if (!sess) return;
    const bytes = base64ToBytes(data_b64 || '');
    sess.term.write(bytes);
  });
  exitUnlisten = await TauriEvent.listen('pty:exit', (e) => {
    const { session_id } = e.payload || {};
    const sess = Sessions.get(session_id);
    if (!sess) return;
    try { sess.term.write('\r\n\x1b[2m[process exited]\x1b[0m\r\n'); } catch {}
    // Let the renderer release the agent. The xterm itself is kept around
    // briefly so the panel doesn't blink — it's reaped on next close().
    setTimeout(() => closeSession(session_id), 0);
  });
}

function base64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function bytesToBase64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

// ---- Session lifecycle ----

function createTerminal(sessionId) {
  const term = new TermXterm({
    fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
    fontSize: 12,
    cursorBlink: true,
    convertEol: false,
    scrollback: 4000,
    theme: {
      background: '#0a0814',
      foreground: '#e2dcc4',
      cursor:     '#e2dcc4',
      selectionBackground: '#3a3450',
    },
  });
  const fit = TermFitAddon ? new TermFitAddon() : null;
  if (fit) term.loadAddon(fit);

  // Input: encode UTF-8 → base64 → invoke.
  term.onData((data) => {
    if (!invoke) return;
    const enc = new TextEncoder();
    const bytes = enc.encode(data);
    invoke('pty_write', { sessionId, dataB64: bytesToBase64(bytes) }).catch(() => {});
  });
  // PTY resize on xterm resize.
  term.onResize(({ rows, cols }) => {
    if (!invoke) return;
    invoke('pty_resize', { sessionId, rows, cols }).catch(() => {});
  });

  return { term, fit, mounted: false };
}

async function spawn({ cwd }) {
  if (!invoke) throw new Error('Tauri invoke not available');
  await setupTauriListeners();
  const sessionId = await invoke('pty_spawn', { cwd, args: null, rows: 30, cols: 100 });
  const sess = createTerminal(sessionId);
  sess.cwd = cwd;
  Sessions.set(sessionId, sess);
  show(sessionId);
  return sessionId;
}

function setPanelVisible(visible) {
  if (!panel) return;
  // Use visibility (not display:none) when toggling an active session so
  // xterm's renderer keeps its dimensions and doesn't repaint as a black
  // canvas on re-show. We only use display:none when there's no session
  // bound, so the empty panel doesn't intercept the mouse.
  if (visible) {
    panel.style.display = 'flex';
    panel.style.visibility = 'visible';
    panel.style.pointerEvents = 'auto';
  } else {
    panel.style.visibility = 'hidden';
    panel.style.pointerEvents = 'none';
  }
}

function show(sessionId) {
  const sess = Sessions.get(sessionId);
  if (!sess || !panel) return;
  // If switching from another session, detach its DOM (keep its state).
  if (activeId && activeId !== sessionId) {
    const cur = Sessions.get(activeId);
    if (cur && cur.mounted) {
      try { cur.term.element && cur.term.element.parentElement && cur.term.element.parentElement.removeChild(cur.term.element); } catch {}
      cur.mounted = false;
    }
  }
  activeId = sessionId;
  setPanelVisible(true);
  applyGeom();
  titleEl.textContent = 'claude';
  cwdEl.textContent = sess.cwd ? shortPath(sess.cwd) : '';
  if (!sess.mounted) {
    sess.term.open(hostEl);
    sess.mounted = true;
  }
  // Fit + force-refresh after layout settles. Double rAF: the first frame
  // flushes the visibility/display change; the second guarantees the host
  // has its final dimensions when fit() measures.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    try { sess.fit && sess.fit.fit(); } catch {}
    try { sess.term.refresh(0, Math.max(0, sess.term.rows - 1)); } catch {}
    sess.term.focus();
  }));
}

function hide() {
  if (!panel) return;
  setPanelVisible(false);
}

function isVisibleFor(sessionId) {
  return panel
    && activeId === sessionId
    && panel.style.display !== 'none'
    && panel.style.visibility !== 'hidden';
}

function toggle(sessionId) {
  if (isVisibleFor(sessionId)) hide();
  else show(sessionId);
}

async function kill(sessionId) {
  if (!invoke) return;
  try { await invoke('pty_kill', { sessionId }); } catch {}
  // closeSession will fire when the waiter thread emits pty:exit.
}

function closeSession(sessionId) {
  const sess = Sessions.get(sessionId);
  if (!sess) return;
  try { sess.term.dispose(); } catch {}
  Sessions.delete(sessionId);
  if (activeId === sessionId) {
    activeId = null;
    // Fully detach so the empty panel doesn't intercept clicks.
    if (panel) {
      panel.style.display = 'none';
      panel.style.visibility = '';
      panel.style.pointerEvents = '';
    }
  }
}

function has(sessionId) { return Sessions.has(sessionId); }

function shortPath(p) {
  if (!p) return '';
  const home = (window.__TAURI__ && window.__TAURI__.path) ? null : null;
  const parts = String(p).replace(/\/+$/, '').split('/').filter(Boolean);
  if (parts.length <= 3) return '/' + parts.join('/');
  return '…/' + parts.slice(-3).join('/');
}

// ---- Panel chrome (drag, resize, buttons) ----

if (panel) {
  applyGeom();

  let drag = null;
  titlebar.addEventListener('mousedown', (e) => {
    if (e.target.closest('.btn')) return;
    drag = { x: e.clientX, y: e.clientY, ox: geom.x, oy: geom.y };
    titlebar.classList.add('dragging');
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!drag) return;
    geom.x = drag.ox + (e.clientX - drag.x);
    geom.y = drag.oy + (e.clientY - drag.y);
    applyGeom();
  });
  window.addEventListener('mouseup', () => {
    if (!drag) return;
    drag = null;
    titlebar.classList.remove('dragging');
    saveGeom();
  });

  let rz = null;
  resizeEl.addEventListener('mousedown', (e) => {
    rz = { x: e.clientX, y: e.clientY, ow: geom.w, oh: geom.h };
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!rz) return;
    geom.w = Math.max(320, rz.ow + (e.clientX - rz.x));
    geom.h = Math.max(180, rz.oh + (e.clientY - rz.y));
    applyGeom();
    if (activeId) {
      const sess = Sessions.get(activeId);
      try { sess && sess.fit && sess.fit.fit(); } catch {}
    }
  });
  window.addEventListener('mouseup', () => {
    if (!rz) return;
    rz = null;
    saveGeom();
  });

  minBtn.addEventListener('click', hide);
  killBtn.addEventListener('click', () => { if (activeId) kill(activeId); });

  window.addEventListener('resize', () => {
    applyGeom();
    if (activeId) {
      const sess = Sessions.get(activeId);
      try { sess && sess.fit && sess.fit.fit(); } catch {}
    }
  });
}

// Expose a tiny API.
window.HQTerm = { spawn, show, hide, toggle, kill, has, isVisibleFor };

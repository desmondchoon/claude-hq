// git.js — git management floating panel for Claude HQ
(() => {
  const TauriCore = window.__TAURI__ && window.__TAURI__.core;
  const invoke = TauriCore ? TauriCore.invoke.bind(TauriCore) : null;

  // ---- DOM references ----
  const panel      = document.getElementById('git-panel');
  const titlebar   = panel && panel.querySelector('.titlebar');
  const resizeEl   = panel && panel.querySelector('.resize');
  const branchEl   = document.getElementById('git-panel') && panel.querySelector('.git-branch');
  const fileList   = document.getElementById('git-file-list');
  const diffWrap   = document.getElementById('git-diff-wrap');
  const diffView   = document.getElementById('git-diff-view');
  const logList    = document.getElementById('git-log-list');
  const commitMsg  = document.getElementById('git-commit-msg');
  const commitBtn  = document.getElementById('git-commit-btn');
  const stageBtn   = document.getElementById('git-stage-all');
  const refreshBtn = document.getElementById('git-refresh');
  const minBtn     = document.getElementById('git-minimize');
  const pullBtn    = document.getElementById('git-pull-btn');
  const pushBtn    = document.getElementById('git-push-btn');
  const msgEl      = document.getElementById('git-msg');
  const branchSel   = document.getElementById('git-branch-select');
  const checkoutBtn = document.getElementById('git-checkout-btn');
  const mergeBtn    = document.getElementById('git-merge-btn');
  const newBranchIn = document.getElementById('git-new-branch');
  const newBranchBtn= document.getElementById('git-new-branch-btn');
  const stashList   = document.getElementById('git-stash-list');
  const stashBtn    = document.getElementById('git-stash-push');

  if (!panel) return; // DOM not ready (shouldn't happen)

  // ---- Geometry (localStorage) ----
  const GEOM_KEY = 'claudeHqGitPanel';
  const DEFAULT_GEOM = { x: 860, y: 120, w: 480, h: 540 };

  function loadGeom() {
    try {
      const raw = localStorage.getItem(GEOM_KEY);
      if (raw) {
        const g = JSON.parse(raw);
        if (typeof g.x === 'number') return g;
      }
    } catch {}
    return { ...DEFAULT_GEOM };
  }

  function saveGeom() {
    try { localStorage.setItem(GEOM_KEY, JSON.stringify(geom)); } catch {}
  }

  function applyGeom() {
    if (!panel) return;
    const mw = window.innerWidth, mh = window.innerHeight;
    geom.x = Math.max(0, Math.min(geom.x, mw - 80));
    geom.y = Math.max(0, Math.min(geom.y, mh - 40));
    geom.w = Math.max(320, Math.min(geom.w, mw));
    geom.h = Math.max(200, Math.min(geom.h, mh));
    panel.style.left   = geom.x + 'px';
    panel.style.top    = geom.y + 'px';
    panel.style.width  = geom.w + 'px';
    panel.style.height = geom.h + 'px';
  }

  let geom = loadGeom();
  applyGeom();

  // Apply initial hidden state; panel stays display:flex once opened
  panel.style.visibility = 'hidden';
  panel.style.pointerEvents = 'none';

  // ---- State ----
  let currentCwd = null;
  let isVisible  = false;
  let msgTimer   = null;

  // ---- Visibility ----
  function setVisible(v) {
    isVisible = v;
    panel.style.display = 'flex';
    panel.style.visibility = v ? 'visible' : 'hidden';
    panel.style.pointerEvents = v ? 'auto' : 'none';
    window.dispatchEvent(new CustomEvent('hq:gitVisibilityChanged', { detail: { visible: v } }));
  }

  function open()   { setVisible(true); applyGeom(); if (currentCwd) doRefresh(); }
  function close()  { setVisible(false); }
  function toggle() { isVisible ? close() : open(); }

  // ---- Git helper ----
  async function gitExec(args) {
    if (!invoke || !currentCwd) return { stdout: '', stderr: 'no working directory', code: -1 };
    return invoke('git_exec', { cwd: currentCwd, args });
  }

  // ---- Status message ----
  function showMsg(text, isErr) {
    clearTimeout(msgTimer);
    msgEl.textContent = text;
    msgEl.className = 'git-msg' + (isErr ? ' err' : '');
    msgTimer = setTimeout(() => { msgEl.textContent = ''; msgEl.className = 'git-msg'; }, 5000);
  }

  // ---- Diff rendering ----
  function renderDiff(raw) {
    diffView.innerHTML = '';
    for (const line of raw.split('\n')) {
      const span = document.createElement('span');
      span.textContent = line + '\n';
      if (line.startsWith('+') && !line.startsWith('+++')) span.className = 'add';
      else if (line.startsWith('-') && !line.startsWith('---')) span.className = 'del';
      else if (line.startsWith('@@')) span.className = 'hunk';
      diffView.appendChild(span);
    }
    diffWrap.style.display = 'block';
  }

  // ---- File status ----
  function statusClass(xy) {
    const c = xy.trim()[0];
    if (c === 'M') return 'st-M';
    if (c === 'A') return 'st-A';
    if (c === 'D') return 'st-D';
    if (c === 'R') return 'st-R';
    return 'st-U';
  }

  async function loadStatus() {
    const [branchRes, statusRes] = await Promise.all([
      gitExec(['branch', '--show-current']),
      gitExec(['status', '--porcelain=v1']),
    ]);

    // Not a git repo
    if (statusRes.code !== 0) {
      const gitBranch = panel.querySelector('.git-branch');
      if (gitBranch) gitBranch.textContent = 'git — not a repository';
      fileList.innerHTML = '<div style="padding:8px;font:10px ui-monospace,monospace;color:#6b6896">not a git repository</div>';
      return;
    }

    const branch = branchRes.stdout.trim() || 'HEAD';
    const gitBranch = panel.querySelector('.git-branch');
    if (gitBranch) gitBranch.textContent = `git  ·  ${branch}`;

    fileList.innerHTML = '';
    const lines = statusRes.stdout.split('\n').filter(l => l.length > 0);
    if (lines.length === 0) {
      fileList.innerHTML = '<div style="padding:6px 8px;font:10px ui-monospace,monospace;color:#6b6896">clean</div>';
      return;
    }

    for (const line of lines) {
      const xy = line.slice(0, 2);
      const file = line.slice(3);
      const row = document.createElement('div');
      row.className = 'file-row';
      row.innerHTML = `<span class="st ${statusClass(xy)}">${xy.trim()}</span><span>${file}</span>`;
      row.addEventListener('click', async () => {
        const isStaged = xy[0] !== ' ' && xy[0] !== '?';
        const args = isStaged
          ? ['diff', '--cached', '--', file]
          : ['diff', '--', file];
        const res = await gitExec(args);
        if (res.stdout.trim()) {
          renderDiff(res.stdout);
        } else {
          diffWrap.style.display = 'none';
        }
      });
      fileList.appendChild(row);
    }
  }

  async function loadLog() {
    const res = await gitExec(['log', '--oneline', '-20']);
    logList.innerHTML = '';
    if (res.code !== 0 || !res.stdout.trim()) return;
    for (const line of res.stdout.trim().split('\n')) {
      const sp = line.indexOf(' ');
      const hash = sp > 0 ? line.slice(0, sp) : line;
      const subject = sp > 0 ? line.slice(sp + 1) : '';
      const row = document.createElement('div');
      row.className = 'log-row';
      row.innerHTML = `<span class="hash">${hash}</span><span class="subject">${subject}</span>`;
      logList.appendChild(row);
    }
  }

  async function loadBranches() {
    if (!branchSel) return;
    const [curRes, listRes] = await Promise.all([
      gitExec(['branch', '--show-current']),
      gitExec(['branch', '--format=%(refname:short)']),
    ]);
    if (listRes.code !== 0) {
      branchSel.innerHTML = '';
      return;
    }
    const current = curRes.stdout.trim();
    const branches = listRes.stdout.split('\n').map(s => s.trim()).filter(Boolean);
    const prev = branchSel.value;
    branchSel.innerHTML = '';
    for (const b of branches) {
      const opt = document.createElement('option');
      opt.value = b;
      opt.textContent = b === current ? `${b}  (current)` : b;
      if (b === current) opt.disabled = true;
      branchSel.appendChild(opt);
    }
    // Restore previous selection if still valid and not current; else pick first non-current.
    if (prev && branches.includes(prev) && prev !== current) {
      branchSel.value = prev;
    } else {
      const firstOther = branches.find(b => b !== current);
      if (firstOther) branchSel.value = firstOther;
    }
  }

  async function loadStashes() {
    if (!stashList) return;
    const res = await gitExec(['stash', 'list', '--format=%gd|%s']);
    stashList.innerHTML = '';
    if (res.code !== 0 || !res.stdout.trim()) {
      const empty = document.createElement('div');
      empty.className = 'stash-empty';
      empty.textContent = 'no stashes';
      stashList.appendChild(empty);
      return;
    }
    for (const line of res.stdout.trim().split('\n')) {
      const bar = line.indexOf('|');
      const ref = bar > 0 ? line.slice(0, bar) : line;
      const subject = bar > 0 ? line.slice(bar + 1) : '';
      const row = document.createElement('div');
      row.className = 'stash-row';
      const refEl = document.createElement('span');
      refEl.className = 'stash-ref';
      refEl.textContent = ref;
      const subjEl = document.createElement('span');
      subjEl.className = 'stash-subject';
      subjEl.textContent = subject;
      const popBtn   = mkStashBtn('pop',   () => stashAct('pop', ref));
      const applyBtn = mkStashBtn('apply', () => stashAct('apply', ref));
      const dropBtn  = mkStashBtn('drop',  () => stashAct('drop', ref), 'drop');
      row.appendChild(refEl);
      row.appendChild(subjEl);
      row.appendChild(popBtn);
      row.appendChild(applyBtn);
      row.appendChild(dropBtn);
      stashList.appendChild(row);
    }
  }

  function mkStashBtn(label, onClick, extraClass) {
    const b = document.createElement('button');
    b.textContent = label;
    if (extraClass) b.className = extraClass;
    b.addEventListener('click', onClick);
    return b;
  }

  async function doRefresh() {
    diffWrap.style.display = 'none';
    await Promise.all([loadStatus(), loadLog(), loadBranches(), loadStashes()]);
  }

  async function refreshFor(cwd) {
    currentCwd = cwd;
    if (isVisible) await doRefresh();
  }

  // ---- Write operations ----
  async function stageAll() {
    const res = await gitExec(['add', '-A']);
    if (res.code !== 0) { showMsg(res.stderr.trim() || 'stage failed', true); return; }
    showMsg('staged all changes');
    await doRefresh();
  }

  async function doCommit() {
    const msg = commitMsg.value.trim();
    if (!msg) return;
    commitBtn.disabled = true;
    const res = await gitExec(['commit', '-m', msg]);
    commitBtn.disabled = false;
    if (res.code !== 0) { showMsg(res.stderr.trim() || 'commit failed', true); return; }
    commitMsg.value = '';
    showMsg('committed');
    await doRefresh();
  }

  async function doPush() {
    pushBtn.disabled = true;
    const res = await gitExec(['push']);
    pushBtn.disabled = false;
    if (res.code !== 0) {
      const msg = res.stderr.trim() || res.stdout.trim() || 'push failed';
      if (res.code === 128 && res.stderr.includes('no upstream')) {
        // Get branch name and suggest the set-upstream command
        const br = await gitExec(['branch', '--show-current']);
        const branch = br.stdout.trim();
        showMsg(`no upstream — try: git push --set-upstream origin ${branch}`, true);
      } else {
        showMsg(msg, true);
      }
      return;
    }
    showMsg(res.stdout.trim() || 'pushed');
    await doRefresh();
  }

  async function doPull() {
    pullBtn.disabled = true;
    const res = await gitExec(['pull']);
    pullBtn.disabled = false;
    if (res.code !== 0) { showMsg(res.stderr.trim() || 'pull failed', true); return; }
    showMsg(res.stdout.trim() || 'pulled');
    await doRefresh();
  }

  async function doCheckout() {
    const b = branchSel && branchSel.value;
    if (!b) return;
    const res = await gitExec(['checkout', b]);
    if (res.code !== 0) { showMsg(res.stderr.trim() || 'checkout failed', true); return; }
    showMsg(`checked out ${b}`);
    await doRefresh();
  }

  async function doMerge() {
    const b = branchSel && branchSel.value;
    if (!b) return;
    const res = await gitExec(['merge', '--no-edit', b]);
    if (res.code !== 0) {
      const m = (res.stderr.trim() || res.stdout.trim() || 'merge failed');
      showMsg(m.split('\n')[0], true);
      await doRefresh();
      return;
    }
    showMsg(`merged ${b}`);
    await doRefresh();
  }

  async function doNewBranch() {
    const name = newBranchIn && newBranchIn.value.trim();
    if (!name) return;
    const res = await gitExec(['checkout', '-b', name]);
    if (res.code !== 0) { showMsg(res.stderr.trim() || 'new branch failed', true); return; }
    newBranchIn.value = '';
    showMsg(`created ${name}`);
    await doRefresh();
  }

  async function doStashPush() {
    const res = await gitExec(['stash', 'push']);
    if (res.code !== 0) { showMsg(res.stderr.trim() || 'stash failed', true); return; }
    showMsg(res.stdout.trim().split('\n')[0] || 'stashed');
    await doRefresh();
  }

  async function stashAct(act, ref) {
    const res = await gitExec(['stash', act, ref]);
    if (res.code !== 0) {
      showMsg((res.stderr.trim() || res.stdout.trim() || `stash ${act} failed`).split('\n')[0], true);
      await doRefresh();
      return;
    }
    showMsg(`stash ${act}: ${ref}`);
    await doRefresh();
  }

  // ---- Button wiring ----
  if (stageBtn)   stageBtn.addEventListener('click', stageAll);
  if (refreshBtn) refreshBtn.addEventListener('click', () => { if (currentCwd) doRefresh(); });
  if (minBtn)     minBtn.addEventListener('click', close);
  if (pullBtn)    pullBtn.addEventListener('click', doPull);
  if (pushBtn)    pushBtn.addEventListener('click', doPush);
  if (commitBtn)  commitBtn.addEventListener('click', doCommit);
  if (commitMsg) {
    commitMsg.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { doCommit(); e.preventDefault(); }
    });
  }
  if (checkoutBtn)  checkoutBtn.addEventListener('click', doCheckout);
  if (mergeBtn)     mergeBtn.addEventListener('click', doMerge);
  if (newBranchBtn) newBranchBtn.addEventListener('click', doNewBranch);
  if (newBranchIn) {
    newBranchIn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { doNewBranch(); e.preventDefault(); }
    });
  }
  if (stashBtn)     stashBtn.addEventListener('click', doStashPush);

  // ---- Drag titlebar ----
  if (titlebar) {
    let drag = null;
    titlebar.addEventListener('mousedown', (e) => {
      if (e.target.tagName === 'BUTTON') return;
      drag = { mx: e.clientX, my: e.clientY, gx: geom.x, gy: geom.y };
      titlebar.classList.add('dragging');
      e.preventDefault();
    });
    window.addEventListener('mousemove', (e) => {
      if (!drag) return;
      geom.x = drag.gx + (e.clientX - drag.mx);
      geom.y = drag.gy + (e.clientY - drag.my);
      applyGeom();
    });
    window.addEventListener('mouseup', () => {
      if (!drag) return;
      drag = null;
      titlebar.classList.remove('dragging');
      saveGeom();
    });
  }

  // ---- Resize handle ----
  if (resizeEl) {
    let rsz = null;
    resizeEl.addEventListener('mousedown', (e) => {
      rsz = { mx: e.clientX, my: e.clientY, gw: geom.w, gh: geom.h };
      e.preventDefault();
    });
    window.addEventListener('mousemove', (e) => {
      if (!rsz) return;
      geom.w = Math.max(320, rsz.gw + (e.clientX - rsz.mx));
      geom.h = Math.max(200, rsz.gh + (e.clientY - rsz.my));
      applyGeom();
    });
    window.addEventListener('mouseup', () => {
      if (!rsz) return;
      rsz = null;
      saveGeom();
    });
  }

  window.addEventListener('resize', () => { applyGeom(); });

  // ---- Auto-follow active agent CWD ----
  window.addEventListener('hq:activeCwdChanged', (e) => {
    const cwd = e.detail && e.detail.cwd;
    if (cwd && cwd !== currentCwd) refreshFor(cwd);
  });

  // ---- Public API ----
  window.HQGit = { open, close, toggle, refreshFor, isOpen: () => isVisible };
})();

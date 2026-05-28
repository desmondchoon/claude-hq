// =====================================================================
// Claude HQ renderer — top-down pixel-art office.
// Single floor view. Agents enter from the door, walk to an assigned seat,
// animate state at the seat, and walk to the exit when done.
// =====================================================================

const cv = document.getElementById('canvas');
const ctx = cv.getContext('2d');
const hud = document.getElementById('hud');
ctx.imageSmoothingEnabled = false;

// Logical floor size. Rendered to an offscreen canvas, then scaled to fit
// the window with nearest-neighbor.
const FLOOR_W = 800;
const FLOOR_H = 500;
const HEADER_H = 14;

const off = document.createElement('canvas');
off.width = FLOOR_W; off.height = FLOOR_H;
const offCtx = off.getContext('2d');
offCtx.imageSmoothingEnabled = false;

let TICK = 0;
let CONNECTED = false;
let ASSETS_READY = false;   // flips true once Sprites.load() finishes
let ZOOM = parseFloat(localStorage.getItem('claudeHqZoom')) || 1.0;
let PAN_X = parseFloat(localStorage.getItem('claudeHqPanX')) || 0;
let PAN_Y = parseFloat(localStorage.getItem('claudeHqPanY')) || 0;
let CANVAS_W = 640, CANVAS_H = 480;

// Left agent-roster panel: animated portrait + status + model + directory.
const SIDEBAR_MIN = 130, SIDEBAR_MAX = 360;
let SIDEBAR_W = parseInt(localStorage.getItem('claudeHqSidebarW'), 10);
if (!Number.isFinite(SIDEBAR_W)) SIDEBAR_W = 150;
SIDEBAR_W = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, SIDEBAR_W));
const OFFICE_MIN_CANVAS = 360;  // hide the office below this window width (sidebar always shown)
let ROSTER_SCROLL = 0;          // vertical scroll offset (px)
// Hit-test boxes recomputed each frame so canvas clicks can find rows/buttons.
let ROSTER_HITS = [];           // [{ agent, x, y, w, h }]
let DISMISS_HITS = [];          // [{ sessionId, x, y, w, h }] — × on external rows
let SHOW_HIDDEN_HIT = null;     // { x, y, w, h } for "show hidden (N)" footer link
let ADD_HIT = null;             // { x, y, w, h } for the + button
function officeVisible() { return CANVAS_W >= OFFICE_MIN_CANVAS; }
// The office is rendered into this viewport (right of the sidebar).
function officeViewport() {
  return { x: SIDEBAR_W, y: HEADER_H, w: CANVAS_W - SIDEBAR_W, h: CANVAS_H - HEADER_H };
}

// ----- Palette (bright "productive office") -----
const PAL = {
  bg:         '#0d0d12',  // canvas backdrop outside the floor
  floor1:     '#ece6d4',  // main floor tile (warm off-white)
  floor2:     '#dcd4be',  // alt tile (subtle checkerboard)
  floorEdge:  '#9a9078',  // tile/skirting shadow
  wall:       '#1a1620',  // outer wall
  wallTop:    '#2e2834',  // wall shadow band
  carpet1:    '#3a6a90',  // productivity carpet (blue)
  carpet2:    '#4a82a8',
  carpetEdge: '#23486a',
  wood1:      '#8a5e34',  // desk wood
  wood2:      '#aa7848',
  woodDark:   '#5a3818',
  metal:      '#a8a8b4',
  metalDark:  '#6a6a76',
  monBlack:   '#1a1a28',
  monBezel:   '#2a2a40',
  cushion:    '#3a6e94',  // sofa blue
  cushion2:   '#5a8eb0',
  green:      '#5fb474',
  text:       '#e2dcc4',  // light text (header on dark bg)
  textDim:    '#a89e84',  // muted on dark bg
  floorText:  '#5a4f3c',  // dark text on light floor (zone labels)
  skin:       '#f4c590',
  skinSh:     '#c89060',
  hair:       '#2d2438',
  hairAlt:    '#7a4530',
  hairAlt2:   '#d4a060',
};
const STATE = {
  idle:        { primary: '#6770b0', shade: '#454a82', glow: '#a8aedc', label: 'idle' },
  thinking:    { primary: '#d4a13a', shade: '#9b7423', glow: '#f0c876', label: 'thinking' },
  typing:      { primary: '#4ab574', shade: '#2e7a4e', glow: '#82d4a3', label: 'output' },
  tool:        { primary: '#5a8fd4', shade: '#3b6da8', glow: '#9ec0e9', label: 'tool' },
  done:        { primary: '#7fc864', shade: '#558a3f', glow: '#b1e095', label: 'done' },
  error:       { primary: '#d05858', shade: '#8a3838', glow: '#ec9090', label: 'error' },
  permission:  { primary: '#f0a040', shade: '#a06820', glow: '#ffd070', label: 'awaiting you' },
  compacting:  { primary: '#9070d0', shade: '#5a4080', glow: '#c0a0f0', label: 'compacting' },
  asking:      { primary: '#5fbac0', shade: '#3c7c80', glow: '#9be0e6', label: 'asking' },
};

const IDLE_TIMEOUT_MS = 2000;
const SLOW_TOOL_MS    = 10000;

// Sessions the user has hidden via the × on an external roster row. Persisted
// so hook events from that session ID stay suppressed across reloads — useful
// for orphaned external sessions whose source process never emits SessionEnd.
const DISMISSED_KEY = 'claudeHqDismissedSessions';
const DISMISSED = (() => {
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch { return new Set(); }
})();
function saveDismissed() {
  try { localStorage.setItem(DISMISSED_KEY, JSON.stringify([...DISMISSED])); } catch {}
}
// States that don't auto-decay to 'idle'. thinking/tool/compacting represent
// in-progress work; while Claude is generating, no events fire (the JSONL
// transcript only writes on completed assistant blocks), so we must NOT treat
// the silence as idleness. The Stop hook → 'done', or the tailer's 180s stale
// sweep, is what brings the agent back to idle.
const STICKY_STATES   = new Set(['done', 'error', 'permission', 'asking', 'thinking', 'tool', 'compacting']);
const WALK_SPEED      = 1.4;

function toolKind(tool) {
  if (!tool) return 'other';
  const t = tool.toLowerCase();
  if (t.startsWith('bash') || t.startsWith('shell')) return 'bash';
  if (t.startsWith('read') || t.startsWith('notebook')) return 'read';
  if (t.startsWith('write')) return 'write';
  if (t.startsWith('edit') || t.startsWith('multiedit')) return 'edit';
  if (t.startsWith('grep') || t.startsWith('search') || t.startsWith('glob')) return 'grep';
  if (t.startsWith('web') || t.startsWith('fetch')) return 'web';
  if (t.startsWith('task') || t.startsWith('agent') || t.startsWith('sub')) return 'task';
  return 'other';
}

// ----- Floor layout -----
//
// One large room divided into 4 zones, viewed top-down with slight depth tilt.
// The entrance is on the left wall. Agents walk in along a corridor.
//
//   ┌────────────────────────────────────────────────────┐
//   │  [CUBICLE ROW — 4 desks against top wall]          │
//   │                                                    │
//   │  [OPEN DESKS — 3 free-standing desks]              │
//   │                                                    │
//   │ ▷                                                  │
//   │ door                                               │
//   │                                  [CONFERENCE TABLE]│
//   │                                                    │
//   │  [LOUNGE — 2 sofas]                                │
//   └────────────────────────────────────────────────────┘

const DOOR = { x: 0, y: 244, w: 30, h: 64 };
const ENTRY_POINT = { x: 56, y: 278 };

// Each seat has a sit-position (where the sprite is drawn), facing direction,
// and an approach-point used as the last waypoint before the sit-position.
// Coordinates retuned in v3 for the larger (48px) characters and furniture.
const SEATS = [
  // Cubicle row (against top wall) — face UP toward their wall monitors (backs to viewer)
  { id: 'c1', zone: 'cubicles', kind: 'cubicle', x: 140, y: 96,  approach: { x: 140, y: 170 }, facing: 'up' },
  { id: 'c2', zone: 'cubicles', kind: 'cubicle', x: 300, y: 96,  approach: { x: 300, y: 170 }, facing: 'up' },
  { id: 'c3', zone: 'cubicles', kind: 'cubicle', x: 460, y: 96,  approach: { x: 460, y: 170 }, facing: 'up' },
  { id: 'c4', zone: 'cubicles', kind: 'cubicle', x: 620, y: 96,  approach: { x: 620, y: 170 }, facing: 'up' },

  // Open desk row (free-standing pods) — face DOWN out toward the room (faces visible)
  { id: 'd1', zone: 'desks', kind: 'desk', x: 150, y: 240, approach: { x: 150, y: 300 }, facing: 'down' },
  { id: 'd2', zone: 'desks', kind: 'desk', x: 320, y: 240, approach: { x: 320, y: 300 }, facing: 'down' },
  { id: 'd3', zone: 'desks', kind: 'desk', x: 490, y: 240, approach: { x: 490, y: 300 }, facing: 'down' },

  // Conference table (glass room, right) — table centre (678,254)
  { id: 'm1', zone: 'meeting', kind: 'meeting', x: 624, y: 224, approach: { x: 600, y: 224 }, facing: 'right' },
  { id: 'm2', zone: 'meeting', kind: 'meeting', x: 732, y: 224, approach: { x: 612, y: 224 }, facing: 'left' },
  { id: 'm3', zone: 'meeting', kind: 'meeting', x: 624, y: 290, approach: { x: 600, y: 290 }, facing: 'right' },
  { id: 'm4', zone: 'meeting', kind: 'meeting', x: 732, y: 290, approach: { x: 612, y: 290 }, facing: 'left' },

  // Lounge (bottom-left) — two 2-seat sofas
  { id: 'l1', zone: 'lounge', kind: 'sofa', x: 130, y: 402, approach: { x: 130, y: 350 }, facing: 'down' },
  { id: 'l2', zone: 'lounge', kind: 'sofa', x: 180, y: 402, approach: { x: 180, y: 350 }, facing: 'down' },
  { id: 'l3', zone: 'lounge', kind: 'sofa', x: 275, y: 402, approach: { x: 275, y: 350 }, facing: 'down' },
  { id: 'l4', zone: 'lounge', kind: 'sofa', x: 325, y: 402, approach: { x: 325, y: 350 }, facing: 'down' },
];
// Preferred order by zone (working zones first).
const ZONE_PRIORITY = ['cubicles', 'desks', 'meeting', 'lounge'];

// ----- Data-driven office map (consumed by the asset renderer) -----
// Coordinates were validated against the generated art in a full-scene
// preview. Cubicle/desk stations are derived from SEATS; everything else
// (rugs + decor + shared furniture) lives here so the layout is editable
// without touching draw code.
const RUGS = [
  { x: 70,  y: 52,  w: 640, h: 98  },  // cubicle row carpet
  { x: 95,  y: 200, w: 470, h: 96  },  // open-desk carpet
  { x: 80,  y: 362, w: 312, h: 108 },  // lounge carpet
  { x: 30,  y: 264, w: 122, h: 28  },  // entry runner (door → floor)
];
// Decor is drawn back-to-front (roughly top of the room first). Each entry
// places a furniture sprite by its atlas anchor.
const DECOR = [
  { piece: 'plant_big',   x: 40,  y: 130 },  // left wall, above door
  { piece: 'watercooler', x: 40,  y: 208 },
  { piece: 'whiteboard',  x: 300, y: 175 },  // team board (between zones)
  { piece: 'plant_big',   x: 544, y: 340 },  // fills gap between desks/meeting/lounge
  { piece: 'printer',     x: 40,  y: 382 },  // left wall, below door
  { piece: 'bookshelf',   x: 40,  y: 468 },
  { piece: 'table',       x: 678, y: 254 },  // conference table (anchor center)
  { piece: 'sofa',        x: 155, y: 410 },
  { piece: 'sofa',        x: 300, y: 410 },
  { piece: 'pingpong',    x: 425, y: 432 },
  { piece: 'counter',     x: 498, y: 372 },  // kitchenette (anchor top-left)
  { piece: 'plant',       x: 470, y: 356 },
  { piece: 'plant',       x: 765, y: 474 },  // bottom-right corner
];

// ----- Walls / rooms -----
// Each wall is drawn either 'back' (behind agents) or 'front' (over agents,
// for depth/occlusion). 'glass' walls are translucent. This turns the open
// floor into a real office: a glass conference room + structural partitions.
const WALL_COL = '#4a4658', WALL_TOP = '#6c6878', WALL_SH = '#2a2736';
const GLASS_FRAME = '#8aa6bc';
const WALLS = [
  // glass conference room around the meeting zone (door gap on left wall, y200..288)
  { x: 566, y: 146, w: 224, h: 8,  kind: 'glass', layer: 'back'  },  // top
  { x: 566, y: 146, w: 8,   h: 54, kind: 'glass', layer: 'back'  },  // left-upper
  { x: 566, y: 288, w: 8,   h: 74, kind: 'glass', layer: 'back'  },  // left-lower
  { x: 782, y: 146, w: 8,   h: 216,kind: 'glass', layer: 'back'  },  // right
  { x: 566, y: 360, w: 224, h: 8,  kind: 'glass', layer: 'front' },  // bottom (front)
  // cubicle backsplash + lounge partition (solid)
  { x: 70,  y: 46,  w: 640, h: 6,   kind: 'solid', layer: 'back' },  // cubicle top
  { x: 74,  y: 356, w: 320, h: 6,   kind: 'solid', layer: 'back' },  // lounge top
  { x: 388, y: 356, w: 6,   h: 116, kind: 'solid', layer: 'back' },  // lounge right
];

function drawWallSeg(w) {
  if (w.kind === 'glass') {
    offCtx.save();
    offCtx.globalAlpha = 0.26;
    rect(offCtx, w.x, w.y, w.w, w.h, '#96cae6');
    offCtx.restore();
    // frame + mullion posts
    rect(offCtx, w.x, w.y, w.w, 1, GLASS_FRAME);
    rect(offCtx, w.x, w.y + w.h - 1, w.w, 1, GLASS_FRAME);
    rect(offCtx, w.x, w.y, 1, w.h, GLASS_FRAME);
    rect(offCtx, w.x + w.w - 1, w.y, 1, w.h, GLASS_FRAME);
    if (w.w > w.h) { for (let x = w.x + 18; x < w.x + w.w - 2; x += 18) rect(offCtx, x, w.y, 1, w.h, GLASS_FRAME); }
    else           { for (let y = w.y + 18; y < w.y + w.h - 2; y += 18) rect(offCtx, w.x, y, w.w, 1, GLASS_FRAME); }
  } else {
    rect(offCtx, w.x, w.y, w.w, w.h, WALL_COL);
    rect(offCtx, w.x, w.y, w.w, 2, WALL_TOP);
    rect(offCtx, w.x, w.y + w.h - 1, w.w, 1, WALL_SH);
  }
}
function drawWalls(layer) { for (const w of WALLS) if (w.layer === layer) drawWallSeg(w); }

// Soft cast shadow grounded at a furniture piece's base.
function pieceShadow(name, px, py) {
  const img = Sprites._state.pieces[name];
  const anch = (Sprites._state.office.anchors || {})[name] || [0, 0];
  if (!img) return;
  const cx = px - anch[0] + img.width / 2;
  const baseY = py - anch[1] + img.height - 4;
  offCtx.save();
  offCtx.globalAlpha = 0.16;
  offCtx.fillStyle = '#000';
  offCtx.beginPath();
  offCtx.ellipse(cx, baseY, img.width * 0.42, 5, 0, 0, Math.PI * 2);
  offCtx.fill();
  offCtx.restore();
}

// Draw the whole office from loaded assets (walls, floor, rugs, furniture).
function drawEnvironment() {
  Sprites.fillWall(offCtx, 0, 0, FLOOR_W, FLOOR_H);
  Sprites.fillFloor(offCtx, 8, 8, FLOOR_W - 16, FLOOR_H - 16);
  for (const r of RUGS) Sprites.drawRug(offCtx, r.x, r.y, r.w, r.h);

  drawWalls('back');

  Sprites.drawPiece(offCtx, 'door', 0, DOOR.y + 25);
  for (const d of DECOR) { pieceShadow(d.piece, d.x, d.y); Sprites.drawPiece(offCtx, d.piece, d.x, d.y); }
  for (const s of SEATS) {
    if (s.zone === 'cubicles') { pieceShadow('cubicle', s.x, s.y); Sprites.drawPiece(offCtx, 'cubicle', s.x, s.y); }
    // Up-facing desks render the desk behind the agent; down-facing desks
    // get a "front desk" drawn over the agent in drawFrontFurniture().
    else if (s.zone === 'desks' && s.facing === 'up') { pieceShadow('desk', s.x, s.y); Sprites.drawPiece(offCtx, 'desk', s.x, s.y); }
  }

  // Zone labels (kept; drawn over the floor, clear of agent chips)
  fillText(offCtx, 'CUBICLES',    60,  18,  PAL.floorText, 8);
  fillText(offCtx, 'OPEN DESKS',  100, 184, PAL.floorText, 8);
  fillText(offCtx, 'MEETING',     712, 130, PAL.floorText, 8);
  fillText(offCtx, 'LOUNGE',      84,  344, PAL.floorText, 8);
  fillText(offCtx, 'KITCHEN',     502, 360, PAL.floorText, 8);
}

// Choose the animation + frame for an agent's current motion/state.
const SIT_BUSY = new Set(['thinking', 'typing', 'tool', 'compacting', 'asking']);
function agentAnim(a) {
  const f = a.facing;
  if (a.walking) return { anim: 'walk_' + f, frame: Math.floor(a.walkFrame) % 4 };
  if (a.seatId && !a.exiting) {
    const busy = SIT_BUSY.has(a.state);
    return { anim: 'sit_' + f, frame: busy ? (Math.floor(TICK / 12) % 2) : 0 };
  }
  return { anim: 'idle_' + f, frame: 0 };
}

// ----- Agent state -----
const Agents = new Map();
const occupiedSeats = new Set();

function agentKey(sessionId, agentId) { return `${sessionId}::${agentId || ''}`; }

function pickSeat() {
  for (const zone of ZONE_PRIORITY) {
    const s = SEATS.find(seat => seat.zone === zone && !occupiedSeats.has(seat.id));
    if (s) { occupiedSeats.add(s.id); return s; }
  }
  return null;
}

function exitPath(from) {
  // Walk back to entry, then off-screen.
  return [
    { x: from.x, y: from.y },                    // current
    { x: ENTRY_POINT.x, y: from.y },             // out to corridor
    { x: ENTRY_POINT.x, y: ENTRY_POINT.y },      // along corridor
    { x: -20, y: ENTRY_POINT.y },                // through door
  ];
}

function enterPath(seat) {
  // Door → corridor → approach → seat
  return [
    { x: ENTRY_POINT.x, y: ENTRY_POINT.y },
    { x: seat.approach.x, y: seat.approach.y },
    { x: seat.x, y: seat.y },
  ];
}

// Hair palette — index order MUST match the generated agent_base_h{0..4}.png
// sheets so the sprite hair color matches the procedural fallback color.
const HAIR_PALETTE = [PAL.hair, PAL.hairAlt, PAL.hairAlt2, '#56a0c0', '#c05a90'];
function hashKey(key) {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
  return Math.abs(h);
}
// Hair picked once per agent so they're visually distinct.
function pickHair(key)      { return HAIR_PALETTE[hashKey(key) % HAIR_PALETTE.length]; }
function pickHairIndex(key) { return hashKey(key) % HAIR_PALETTE.length; }

function ensureAgent(sessionId, agentId) {
  if (DISMISSED.has(sessionId)) return null;
  const k = agentKey(sessionId, agentId);
  let a = Agents.get(k);
  if (!a) {
    const seat = pickSeat();
    a = {
      key: k,
      sessionId,
      agentId: agentId || null,
      // HQ-spawned PTY sessions use ids prefixed with "hq-" (see
      // src-tauri/src/pty.rs). For these, clicking the roster row toggles
      // the embedded terminal and we keep the agent seated until the PTY
      // exits (not just until Claude says `done`).
      hqOwned: typeof sessionId === 'string' && sessionId.startsWith('hq-'),
      state: 'idle',
      tool: null,
      toolKind: null,
      toolStart: 0,
      slow: false,
      planMode: false,
      model: null,
      chars: 0,
      created: performance.now(),
      lastActivity: performance.now(),
      removeAt: null,
      seatId: seat ? seat.id : null,
      x: -10, y: ENTRY_POINT.y,
      path: seat ? enterPath(seat) : [{ x: 60, y: ENTRY_POINT.y }],
      facing: 'right',
      walking: true,
      walkFrame: 0,
      sitTime: 0,
      hair: pickHair(k),
      hairIndex: pickHairIndex(k),
      apHash: hashKey(k),          // identity → skin/hair/style/accessory
      cwd: null,                   // working directory (from 'cwd' event)
      exiting: false,
    };
    Agents.set(k, a);
  }
  return a;
}

function releaseAgent(k) {
  const a = Agents.get(k);
  if (!a) return;
  if (a.seatId) occupiedSeats.delete(a.seatId);
  Agents.delete(k);
}

// User dismissed an external session from the roster. Persist the sessionId
// so further hook events stay ignored, and walk out any agents already on the
// floor that share it (covers subagents under the same session).
function dismissSession(sessionId) {
  if (!sessionId) return;
  DISMISSED.add(sessionId);
  saveDismissed();
  const now = performance.now();
  for (const ag of Agents.values()) {
    if (ag.sessionId === sessionId && !ag.exiting) ag.removeAt = now - 1;
  }
}

function clearDismissed() {
  DISMISSED.clear();
  saveDismissed();
}

function seatById(id) { return SEATS.find(s => s.id === id) || null; }

// ----- Walk update -----
function updateAgent(a) {
  if (!a.path || a.path.length === 0) {
    a.walking = false;
    a.sitTime++;
    return;
  }
  const target = a.path[0];
  const dx = target.x - a.x;
  const dy = target.y - a.y;
  const d = Math.hypot(dx, dy);
  if (d < WALK_SPEED) {
    a.x = target.x; a.y = target.y;
    a.path.shift();
    if (a.path.length === 0) {
      a.walking = false;
      // Snap facing to seat facing on arrival.
      if (a.seatId && !a.exiting) {
        const s = seatById(a.seatId);
        if (s) a.facing = s.facing;
      }
    }
    return;
  }
  a.x += (dx / d) * WALK_SPEED;
  a.y += (dy / d) * WALK_SPEED;
  a.walking = true;
  a.facing = Math.abs(dx) > Math.abs(dy)
    ? (dx > 0 ? 'right' : 'left')
    : (dy > 0 ? 'down' : 'up');
  a.walkFrame = (a.walkFrame + 0.18) % 4;
}

// ----- Drawing helpers -----
function rect(c, x, y, w, h, color) {
  c.fillStyle = color;
  c.fillRect(x | 0, y | 0, w | 0, h | 0);
}
function fillText(c, str, x, y, color, size = 9, family = 'ui-monospace, monospace') {
  c.fillStyle = color;
  c.font = `${size}px ${family}`;
  c.textBaseline = 'top';
  c.fillText(str, x | 0, y | 0);
}

// =====================================================================
// Floor + furniture
// =====================================================================

function drawFloor() {
  // Walls (outer border)
  rect(offCtx, 0, 0, FLOOR_W, FLOOR_H, PAL.wall);
  rect(offCtx, 8, 8, FLOOR_W - 16, FLOOR_H - 16, PAL.floor1);
  // Floor tile pattern
  for (let y = 8; y < FLOOR_H - 8; y += 24) {
    for (let x = 8; x < FLOOR_W - 8; x += 24) {
      if (((x / 24) | 0) + ((y / 24) | 0) & 1) rect(offCtx, x, y, 24, 24, PAL.floor2);
    }
  }
  // Wall top trim (3D-ish)
  rect(offCtx, 0, 0, FLOOR_W, 8, PAL.wallTop);
  rect(offCtx, 0, FLOOR_H - 6, FLOOR_W, 6, PAL.wallTop);
  rect(offCtx, 0, 0, 8, FLOOR_H, PAL.wallTop);
  rect(offCtx, FLOOR_W - 8, 0, 8, FLOOR_H, PAL.wallTop);
  // Door opening on left wall
  rect(offCtx, 0, DOOR.y, 8, DOOR.h, PAL.bg);
  rect(offCtx, 4, DOOR.y, 4, DOOR.h, PAL.metalDark);
  // Door frame
  rect(offCtx, 8, DOOR.y - 2, 2, DOOR.h + 4, PAL.metal);
  fillText(offCtx, 'IN', 12, DOOR.y + DOOR.h / 2 - 4, PAL.textDim, 7);

  // Carpet under cubicle row
  rect(offCtx, 70, 52, 640, 98, PAL.carpetEdge);
  rect(offCtx, 72, 54, 636, 94, PAL.carpet2);
  // Carpet under desks
  rect(offCtx, 95, 200, 470, 96, PAL.carpetEdge);
  rect(offCtx, 97, 202, 466, 92, PAL.carpet1);
  // Carpet in lounge
  rect(offCtx, 80, 362, 312, 108, PAL.carpetEdge);
  rect(offCtx, 82, 364, 308, 104, PAL.carpet2);

  // Zone labels
  fillText(offCtx, 'CUBICLES',        60, 18, PAL.floorText, 8);
  fillText(offCtx, 'OPEN DESKS',     100, 184, PAL.floorText, 8);
  fillText(offCtx, 'MEETING',        650, 132, PAL.floorText, 8);
  fillText(offCtx, 'LOUNGE',          84, 344, PAL.floorText, 8);
}

function drawCubicleStation(s) {
  // Top-wall cubicle. Cubicle wall pieces + desk against the wall + monitor.
  const x = s.x, y = s.y;
  // Cubicle partitions (L-shape behind desk)
  rect(offCtx, x - 40, y - 30, 80, 4, PAL.metalDark);
  rect(offCtx, x - 40, y - 30, 4, 30, PAL.metalDark);
  rect(offCtx, x + 36, y - 30, 4, 30, PAL.metalDark);
  // Desk top
  rect(offCtx, x - 40, y - 5, 80, 18, PAL.wood1);
  rect(offCtx, x - 40, y - 5, 80, 2, PAL.wood2);
  rect(offCtx, x - 40, y + 11, 80, 2, PAL.woodDark);
  // Monitor (top-down: black slab with screen patch)
  rect(offCtx, x - 18, y - 28, 36, 18, PAL.monBlack);
  rect(offCtx, x - 15, y - 25, 30, 12, PAL.monBezel);
  // Chair (below desk)
  rect(offCtx, x - 10, y + 14, 20, 6, PAL.metal);
  rect(offCtx, x - 10, y + 20, 20, 2, PAL.metalDark);
  rect(offCtx, x - 2, y + 22, 4, 6, PAL.metalDark);
  rect(offCtx, x - 8, y + 28, 16, 2, PAL.metalDark);
}

function drawOpenDesk(s) {
  // Free-standing desk (monitor on near edge, agent sits on far side facing up)
  const x = s.x, y = s.y;
  // Desk
  rect(offCtx, x - 36, y - 4, 72, 22, PAL.wood1);
  rect(offCtx, x - 36, y - 4, 72, 2, PAL.wood2);
  rect(offCtx, x - 36, y + 16, 72, 2, PAL.woodDark);
  // Legs
  rect(offCtx, x - 34, y + 18, 4, 8, PAL.woodDark);
  rect(offCtx, x + 30, y + 18, 4, 8, PAL.woodDark);
  // Monitor (smaller, off-center)
  rect(offCtx, x - 14, y - 18, 28, 14, PAL.monBlack);
  rect(offCtx, x - 12, y - 16, 24, 10, PAL.monBezel);
  // Chair
  rect(offCtx, x - 8, y + 22, 16, 4, PAL.metal);
}

function drawSofa(s, mate) {
  // Draw once per pair (only for the leftmost seat).
  if (mate && s.x > mate.x) return;
  const x1 = s.x - 14;
  const x2 = (mate ? mate.x : s.x) + 14;
  const y = s.y;
  const w = x2 - x1;
  // Sofa body
  rect(offCtx, x1, y - 8, w, 26, PAL.cushion);
  // Back
  rect(offCtx, x1, y - 16, w, 10, PAL.cushion2);
  // Arms
  rect(offCtx, x1 - 4, y - 14, 4, 28, PAL.cushion2);
  rect(offCtx, x1 + w, y - 14, 4, 28, PAL.cushion2);
  // Cushion seam
  rect(offCtx, (x1 + x2) / 2 - 1, y - 6, 2, 22, PAL.cushion2);
}

function drawConferenceTable() {
  // One big table for all m1..m4 (centre ~678,254)
  rect(offCtx, 600, 180, 156, 148, PAL.woodDark);
  rect(offCtx, 604, 184, 148, 140, PAL.wood1);
  rect(offCtx, 604, 184, 148, 2, PAL.wood2);
  rect(offCtx, 604, 322, 148, 2, PAL.woodDark);
  // Center decoration
  rect(offCtx, 669, 243, 18, 22, PAL.metalDark);
  rect(offCtx, 673, 247, 10, 14, PAL.green);
  // Chairs around (m1..m4 positions)
  for (const s of SEATS.filter(s => s.zone === 'meeting')) {
    rect(offCtx, s.x - 7, s.y - 7, 14, 14, PAL.metal);
    rect(offCtx, s.x - 7, s.y - 7, 14, 2, PAL.metalDark);
  }
}

function drawKitchenette() {
  // Bottom-right corner — a counter with coffee/snacks (decor)
  rect(offCtx, 498, 372, 294, 112, PAL.wood1);
  rect(offCtx, 498, 372, 294, 2, PAL.wood2);
  rect(offCtx, 498, 482, 294, 2, PAL.woodDark);
  // Coffee machine
  rect(offCtx, 520, 384, 30, 30, PAL.metalDark);
  rect(offCtx, 524, 388, 22, 8, '#000');
  rect(offCtx, 528, 400, 14, 10, PAL.metalDark);
  rect(offCtx, 530, 404, 10, 4, '#5d3a18');
  // Plant
  rect(offCtx, 758, 388, 22, 22, PAL.woodDark);
  rect(offCtx, 756, 376, 26, 14, PAL.green);
  rect(offCtx, 762, 370, 14, 10, '#76c89a');
  // Snack bowl
  rect(offCtx, 600, 394, 30, 12, PAL.wood2);
  rect(offCtx, 604, 392, 22, 4, '#e8c060');
  fillText(offCtx, 'KITCHEN', 502, 360, PAL.floorText, 8);
}

function drawAllFurniture() {
  // Cubicles
  for (const s of SEATS.filter(s => s.zone === 'cubicles')) drawCubicleStation(s);
  // Open desks
  for (const s of SEATS.filter(s => s.zone === 'desks')) drawOpenDesk(s);
  // Conference (table drawn once)
  drawConferenceTable();
  // Lounge sofas (drawn per pair: l1+l2, l3+l4)
  const lounges = SEATS.filter(s => s.zone === 'lounge');
  for (let i = 0; i < lounges.length; i += 2) {
    drawSofa(lounges[i], lounges[i + 1]);
  }
  drawKitchenette();
}

// =====================================================================
// Agent sprite
// =====================================================================

// Agent drawing is split into two passes so "front" furniture (a desk a
// down-facing worker sits behind) can be layered between the body and the
// status overlays: body → front desks/walls → overlays.
function drawAgentBodyPass(a) {
  const c = offCtx;
  const sc = STATE[a.state] || STATE.idle;
  const x = Math.round(a.x), y = Math.round(a.y);

  // Shadow (dark translucent — reads well on light floor). Sized/placed for
  // the 48px sprite whose feet sit ~13px below the (x,y) pivot.
  c.globalAlpha = 0.26;
  c.fillStyle = '#000';
  c.beginPath();
  c.ellipse(x, y + 13, 9, 3.5, 0, 0, Math.PI * 2);
  c.fill();
  c.globalAlpha = 1;

  // Body: sprite when assets are loaded, otherwise the procedural fallback.
  if (ASSETS_READY) {
    const { anim, frame } = agentAnim(a);
    Sprites.drawAgentSprite(c, a.x, a.y, anim, frame, a.apHash, sc.primary);
  } else {
    drawAgentBody(a, sc, x, y);
  }
}

function drawAgentOverlay(a) {
  const c = offCtx;
  const sc = STATE[a.state] || STATE.idle;
  const x = Math.round(a.x), y = Math.round(a.y);

  // Status chip (icon + small text) above head (skip while walking in/out).
  // Offset raised for the taller 48px sprite (head top ~26px above pivot).
  if (!a.walking) {
    drawStatusChip(a, x, y - 32, sc);
  }
  // Plan-mode badge — tiny clipboard floating to the right of head
  if (a.planMode) {
    rect(c, x + 12, y - 26, 6, 8, '#e8e2c8');
    rect(c, x + 12, y - 26, 6, 1, '#a09060');
    rect(c, x + 13, y - 27, 4, 1, '#a09060');
  }
  // Model name plate below the agent (only when seated)
  if (a.model && !a.walking) {
    drawNamePlate(a, x, y + 17);
  }
}

// Furniture drawn OVER agents: a down-facing worker sits behind this desk.
function drawFrontFurniture() {
  for (const s of SEATS) {
    if (s.zone === 'desks' && s.facing === 'down') {
      pieceShadow('desk_front', s.x, s.y);
      Sprites.drawPiece(offCtx, 'desk_front', s.x, s.y);
    }
  }
}

// Procedural fallback body (used only when sprite assets fail to load).
function drawAgentBody(a, sc, x, y) {
  const c = offCtx;
  const bob = a.walking ? (Math.sin(a.walkFrame * Math.PI) > 0 ? -1 : 0) : 0;
  const shirt = sc.primary, shirtSh = sc.shade;
  const skin = PAL.skin, skinSh = PAL.skinSh, hair = a.hair;

  // Per-facing sprite. Each sprite is roughly 12 wide × 18 tall, centered on (x, y).
  switch (a.facing) {
    case 'down': {
      // Hair top
      rect(c, x - 4, y - 14 + bob, 8, 4, hair);
      rect(c, x - 3, y - 16 + bob, 6, 2, hair);
      // Face
      rect(c, x - 4, y - 10 + bob, 8, 4, skin);
      rect(c, x - 2, y - 9 + bob, 1, 1, '#222');  // eye L
      rect(c, x + 1, y - 9 + bob, 1, 1, '#222');  // eye R
      // Neck
      rect(c, x - 1, y - 6 + bob, 2, 1, skinSh);
      // Torso
      rect(c, x - 5, y - 5, 10, 8, shirt);
      rect(c, x - 5, y - 5, 10, 1, sc.glow);
      rect(c, x - 5, y + 2, 10, 1, shirtSh);
      // Arms
      rect(c, x - 7, y - 4, 2, 6, shirt);
      rect(c, x + 5, y - 4, 2, 6, shirt);
      rect(c, x - 7, y + 2, 2, 1, skin);
      rect(c, x + 5, y + 2, 2, 1, skin);
      // Legs (walk cycle: alternate Y)
      const lf = a.walking ? ((a.walkFrame | 0) % 2) : 0;
      rect(c, x - 4, y + 3, 3, 6 + lf, '#3a3268');
      rect(c, x + 1, y + 3, 3, 6 + (1 - lf), '#3a3268');
      // Shoes
      rect(c, x - 4, y + 9 + lf, 3, 1, '#000');
      rect(c, x + 1, y + 9 + (1 - lf), 3, 1, '#000');
      break;
    }
    case 'up': {
      // Back of head (no face)
      rect(c, x - 4, y - 14 + bob, 8, 6, hair);
      rect(c, x - 3, y - 16 + bob, 6, 2, hair);
      // Torso
      rect(c, x - 5, y - 8, 10, 11, shirt);
      rect(c, x - 5, y - 8, 10, 1, sc.glow);
      rect(c, x - 5, y + 2, 10, 1, shirtSh);
      // Arms
      rect(c, x - 7, y - 7, 2, 8, shirt);
      rect(c, x + 5, y - 7, 2, 8, shirt);
      // Legs
      const lf = a.walking ? ((a.walkFrame | 0) % 2) : 0;
      rect(c, x - 4, y + 3, 3, 6 + lf, '#3a3268');
      rect(c, x + 1, y + 3, 3, 6 + (1 - lf), '#3a3268');
      rect(c, x - 4, y + 9 + lf, 3, 1, '#000');
      rect(c, x + 1, y + 9 + (1 - lf), 3, 1, '#000');
      break;
    }
    case 'left':
    case 'right': {
      const flip = a.facing === 'left' ? -1 : 1;
      // Hair (side profile)
      rect(c, x - 3, y - 14 + bob, 6, 4, hair);
      rect(c, x - 3 + (flip > 0 ? 0 : 1), y - 16 + bob, 5, 2, hair);
      // Face (one eye visible on the facing side)
      rect(c, x - 3, y - 10 + bob, 6, 4, skin);
      rect(c, x + (flip > 0 ? 1 : -2), y - 9 + bob, 1, 1, '#222');
      // Torso
      rect(c, x - 4, y - 5, 8, 8, shirt);
      rect(c, x - 4, y - 5, 8, 1, sc.glow);
      // Arm closer to camera swings
      const armBob = a.walking ? ((a.walkFrame | 0) % 2) : 0;
      rect(c, x + flip * 3, y - 4 + armBob, 2, 6, shirt);
      // Legs
      const lf = a.walking ? ((a.walkFrame | 0) % 2) : 0;
      rect(c, x - 3, y + 3, 3, 6 + lf, '#3a3268');
      rect(c, x + 1, y + 3, 3, 6 + (1 - lf), '#3a3268');
      rect(c, x - 3, y + 9 + lf, 3, 1, '#000');
      rect(c, x + 1, y + 9 + (1 - lf), 3, 1, '#000');
      break;
    }
  }
}

// Small pixel status icon centered at (cx, cy). Draws on `c` (defaults to the
// offscreen office canvas; the roster passes the main ctx for screen-space).
function drawStateIcon(cx, cy, stateName, color, c) {
  c = c || offCtx;
  cx |= 0; cy |= 0;
  const px = (x, y, w = 1, h = 1) => rect(c, cx + x, cy + y, w, h, color);
  switch (stateName) {
    case 'thinking':                       // three dots
      px(-3, 0); px(-1, 0); px(1, 0); px(3, 0); break;
    case 'tool':                           // gear (plus + corner nubs)
      px(0, -3, 1, 7); px(-3, 0, 7, 1);
      px(-2, -2); px(2, -2); px(-2, 2); px(2, 2); break;
    case 'typing':                         // output lines
      px(-3, -1, 7, 1); px(-3, 1, 5, 1); break;
    case 'done':                           // checkmark
      px(-3, 0); px(-2, 1); px(-1, 2); px(0, 1); px(1, 0); px(2, -1); px(3, -2); break;
    case 'error':                          // exclamation
      px(0, -3, 1, 4); px(0, 2); break;
    case 'permission':                     // pause bars
      px(-2, -3, 2, 7); px(1, -3, 2, 7); break;
    case 'compacting': {                   // rotating dot
      const ang = TICK * 0.2;
      px(Math.round(Math.cos(ang) * 2.5), Math.round(Math.sin(ang) * 2.5));
      px(0, 0); break;
    }
    case 'asking':
      fillText(c, '?', cx - 2, cy - 4, color, 9); break;
    case 'idle':
    default:
      fillText(c, 'z', cx - 2, cy - 4, color, 8); break;
  }
}

// Status chip: icon + small text label, above an agent's head.
function drawStatusChip(a, ax, ay, sc) {
  const c = offCtx;
  const isAttn = a.state === 'permission' || a.state === 'asking' || a.state === 'error';
  const pulse = isAttn && ((TICK / 12) | 0) % 2 === 0;
  const border = pulse ? sc.glow : sc.primary;

  let text = '';
  if (a.state === 'tool') { text = a.tool || 'tool'; if (a.slow) text += ' (slow)'; }
  else if (a.state !== 'idle') { text = sc.label; }
  if (text.length > 16) text = text.slice(0, 15) + '…';

  c.font = '7px ui-monospace, monospace';
  const tw = text ? Math.ceil(c.measureText(text).width) : 0;
  const iconW = 8, padX = 3, gap = text ? 3 : 0;
  const w = padX + iconW + gap + tw + padX;
  const h = 12;
  const bx = (ax - w / 2) | 0;
  const by = (ay - h) | 0;

  // bubble body (rounded look)
  rect(c, bx + 1, by, w - 2, h, '#ffffff');
  rect(c, bx, by + 1, w, h - 2, '#ffffff');
  // border
  rect(c, bx + 1, by, w - 2, 1, border);
  rect(c, bx + 1, by + h - 1, w - 2, 1, border);
  rect(c, bx, by + 1, 1, h - 2, border);
  rect(c, bx + w - 1, by + 1, 1, h - 2, border);
  // tail
  rect(c, ax - 2, by + h, 4, 2, '#ffffff');
  rect(c, ax - 1, by + h + 2, 2, 2, '#ffffff');
  rect(c, ax - 2, by + h, 1, 2, border);
  rect(c, ax + 1, by + h, 1, 2, border);
  // icon + text
  drawStateIcon(bx + padX + 4, (by + h / 2) | 0, a.state, sc.shade);
  if (text) fillText(c, text, bx + padX + iconW + gap, by + 3, sc.shade, 7);
}

function drawThoughtBubble(a, ax, ay, sc) {
  const c = offCtx;
  // What to write in the bubble.
  let label = sc.label;
  if (a.state === 'tool' && a.tool) label = `${sc.label}: ${a.tool}`;
  if (a.slow) label += ' (slow)';
  // Trim very long tool names.
  if (label.length > 18) label = label.slice(0, 17) + '…';

  // Measure
  c.font = '7px ui-monospace, monospace';
  const tw = c.measureText(label).width;
  const w = Math.ceil(tw) + 10;
  const h = 12;
  const bx = (ax - w / 2) | 0;
  const by = (ay - h) | 0;

  // Animated states pulse the border color.
  const tick = TICK;
  const isAttn = a.state === 'permission' || a.state === 'asking';
  const pulse = isAttn && ((tick / 12) | 0) % 2 === 0;
  const border = pulse ? sc.glow : sc.primary;
  const fill = pulse ? sc.glow : '#ffffff';

  // Bubble body (rounded rect look)
  rect(c, bx + 1, by, w - 2, h, fill);
  rect(c, bx, by + 1, w, h - 2, fill);
  // Border outline
  rect(c, bx + 1, by, w - 2, 1, border);
  rect(c, bx + 1, by + h - 1, w - 2, 1, border);
  rect(c, bx, by + 1, 1, h - 2, border);
  rect(c, bx + w - 1, by + 1, 1, h - 2, border);

  // Text — choose contrast against fill
  const textColor = pulse ? '#000000' : sc.shade;
  fillText(c, label, bx + 5, by + 3, textColor, 7);

  // Tail — 2 small puffs leading down to the head
  rect(c, ax - 2, by + h, 4, 2, fill);
  rect(c, ax - 2, by + h, 4, 1, border);
  rect(c, ax - 1, by + h + 2, 2, 2, fill);
  rect(c, ax - 1, by + h + 2, 2, 1, border);

  // Tiny in-bubble icon for states without a textual cue (compacting spiral, etc.)
  if (a.state === 'compacting') {
    for (let i = 0; i < 4; i++) {
      const ang = tick * 0.15 + i * (Math.PI / 2);
      const r = 3 - i * 0.5;
      rect(c, bx + w - 6 + Math.cos(ang) * r, by + 6 + Math.sin(ang) * r, 1, 1, sc.shade);
    }
  }
}

function drawNamePlate(a, ax, ay) {
  const c = offCtx;
  c.font = '7px ui-monospace, monospace';
  const tw = c.measureText(a.model).width;
  const w = Math.ceil(tw) + 6;
  const h = 9;
  const bx = (ax - w / 2) | 0;
  rect(c, bx, ay, w, h, '#1a1620');
  rect(c, bx, ay, w, 1, '#3a3450');
  fillText(c, a.model, bx + 3, ay + 1, '#e2dcc4', 7);
}

// =====================================================================
// Top-level render
// =====================================================================

function drawHeader() {
  rect(ctx, 0, 0, CANVAS_W, HEADER_H, '#120e26');
  rect(ctx, 0, HEADER_H - 1, CANVAS_W, 1, '#3a3a70');
  rect(ctx, 6, 4, 6, 6, CONNECTED ? '#7fc864' : '#d05858');
  fillText(ctx, CONNECTED ? 'connected' : 'no daemon', 16, 3, PAL.textDim, 9);
  const n = Agents.size;
  const right = `${n}/${SEATS.length}  ·  ${Math.round(ZOOM * 100)}%`;
  fillText(ctx, right, CANVAS_W - 6 - right.length * 5.5, 3, PAL.text, 9);
}

// =====================================================================
// Left agent-roster sidebar
// =====================================================================

function ellipsize(str, maxW, size) {
  str = String(str == null ? '' : str);
  ctx.font = `${size}px ui-monospace, monospace`;
  if (ctx.measureText(str).width <= maxW) return str;
  while (str.length > 1 && ctx.measureText(str + '…').width > maxW) str = str.slice(0, -1);
  return str + '…';
}

// Compact a path to its last couple of segments for the roster line.
function shortDir(p) {
  if (!p) return '—';
  const parts = String(p).replace(/\/+$/, '').split('/').filter(Boolean);
  if (parts.length === 0) return '/';
  if (parts.length <= 2) return '/' + parts.join('/');
  return '…/' + parts.slice(-2).join('/');
}

// Portraits always face the viewer (so we see the face); hands type when busy.
function portraitAnim(a) {
  if (a.walking) return { anim: 'walk_down', frame: Math.floor(a.walkFrame) % 4 };
  const busy = SIT_BUSY.has(a.state);
  return { anim: 'sit_down', frame: busy ? (Math.floor(TICK / 12) % 2) : 0 };
}

function drawRosterRow(a, x, ry, w, rowH) {
  const sc = STATE[a.state] || STATE.idle;
  // state-colored left accent
  rect(ctx, x, ry + 3, 3, rowH - 6, sc.primary);
  // portrait box
  const pbx = x + 9, pby = ry + 5, pbw = 34, pbh = rowH - 12;
  rect(ctx, pbx, pby, pbw, pbh, '#0f0c1e');
  rect(ctx, pbx, pby, pbw, 1, '#2a2440');
  if (ASSETS_READY) {
    ctx.save();
    ctx.beginPath(); ctx.rect(pbx, pby, pbw, pbh); ctx.clip();
    const { anim, frame } = portraitAnim(a);
    // Scale the 48px sprite down so the whole character fits the portrait box.
    const psc = 0.72;
    ctx.translate(pbx + pbw / 2, pby + pbh - 10);
    ctx.scale(psc, psc);
    Sprites.drawAgentSprite(ctx, 0, 0, anim, frame, a.apHash, sc.primary);
    ctx.restore();
  } else {
    rect(ctx, pbx + pbw / 2 - 4, pby + pbh / 2 - 4, 8, 8, sc.primary);
  }
  // text column
  const tx = pbx + pbw + 7;
  // Reserve a uniform right-edge column for the per-row chip(s) — `>_` on
  // HQ-owned rows, "ext" + `×` on external rows — so text wrapping is the
  // same width in both cases.
  const rightPad = 18;
  const tw = (x + w) - tx - rightPad;
  // status: icon + label
  drawStateIcon(tx + 3, ry + 11, a.state, sc.primary, ctx);
  let label = a.state === 'tool' ? (a.tool || 'tool') : sc.label;
  if (a.slow) label += ' (slow)';
  fillText(ctx, ellipsize(label, tw - 11, 9), tx + 11, ry + 7, sc.glow, 9);
  // model
  fillText(ctx, ellipsize(a.model || '—', tw, 8), tx, ry + 20, PAL.textDim, 8);
  // directory
  fillText(ctx, ellipsize(shortDir(a.cwd), tw, 8), tx, ry + 31, '#8a84a8', 8);
  if (a.hqOwned) {
    // Terminal affordance: a small `>_` chip on rows that have a terminal we
    // can open. Lights up when its panel is currently visible.
    const isOpen = window.HQTerm && window.HQTerm.isVisibleFor && window.HQTerm.isVisibleFor(a.sessionId);
    const cx = x + w - 14, cy = ry + rowH / 2 - 6;
    rect(ctx, cx, cy, 12, 12, isOpen ? '#2e3e5e' : '#1a1a28');
    rect(ctx, cx, cy, 12, 1, isOpen ? '#5a8fd4' : '#3a3450');
    fillText(ctx, '>_', cx + 2, cy + 2, isOpen ? '#9ec0e9' : '#8a84a8', 8);
  } else {
    // External (non-HQ-owned) row: small dim "ext" pill marks it as a session
    // HQ doesn't own, and an `×` button dismisses it (walks the agent out and
    // mutes future events from this session id).
    const px = x + w - 17, py = ry + 6;
    rect(ctx, px, py, 14, 8, '#231d36');
    fillText(ctx, 'ext', px + 2, py + 1, '#8a84a8', 7);
    const cx = x + w - 14, cy = ry + rowH / 2 - 1;
    rect(ctx, cx, cy, 12, 12, '#2a1a24');
    rect(ctx, cx, cy, 12, 1, '#5a3848');
    fillText(ctx, '×', cx + 3, cy + 2, '#d09898', 9);
    DISMISS_HITS.push({ sessionId: a.sessionId, x: cx, y: cy, w: 12, h: 12 });
  }
  // row separator
  rect(ctx, x + 8, ry + rowH - 1, w - 16, 1, '#201b34');
}

function drawSidebar(x, y, w, h) {
  rect(ctx, x, y, w, h, '#15122a');
  rect(ctx, x + w - 1, y, 1, h, '#2a2440');     // divider
  const agents = Array.from(Agents.values()).sort((a, b) => a.created - b.created);
  fillText(ctx, 'AGENTS', x + 10, y + 7, PAL.text, 9);
  // Count, then a `+` button at the right edge.
  const countStr = String(agents.length);
  const addSize = 16;
  const addX = x + w - 8 - addSize;
  const addY = y + 4;
  // count sits just to the left of the +
  fillText(ctx, countStr, addX - 4 - countStr.length * 6, y + 7, PAL.textDim, 9);
  // + button
  rect(ctx, addX, addY, addSize, addSize, '#2a2440');
  rect(ctx, addX, addY, addSize, 1, '#3a3450');
  fillText(ctx, '+', addX + 5, addY + 3, '#c0b8e0', 11);
  ADD_HIT = { x: addX, y: addY, w: addSize, h: addSize };
  rect(ctx, x + 8, y + 20, w - 16, 1, '#2a2440');

  const footerH = DISMISSED.size > 0 ? 16 : 0;
  const top = y + 24, vh = h - 24 - footerH, rowH = 46;
  const contentH = agents.length * rowH;
  const maxScroll = Math.max(0, contentH - vh);
  ROSTER_SCROLL = Math.max(0, Math.min(maxScroll, ROSTER_SCROLL));

  ctx.save();
  ctx.beginPath(); ctx.rect(x, top, w, vh); ctx.clip();
  let ry = top - ROSTER_SCROLL;
  ROSTER_HITS = [];
  DISMISS_HITS = [];
  for (const a of agents) {
    if (ry + rowH >= top && ry <= top + vh) {
      drawRosterRow(a, x, ry, w, rowH);
      ROSTER_HITS.push({ agent: a, x, y: ry, w, h: rowH });
    }
    ry += rowH;
  }
  ctx.restore();

  if (agents.length === 0) {
    fillText(ctx, 'no agents yet', x + 10, top + 8, PAL.textDim, 9);
  }
  // scrollbar
  if (maxScroll > 0) {
    const thumbH = Math.max(20, vh * vh / contentH);
    const thumbY = top + (ROSTER_SCROLL / maxScroll) * (vh - thumbH);
    rect(ctx, x + w - 4, top, 2, vh, '#241f3a');
    rect(ctx, x + w - 4, thumbY | 0, 2, thumbH | 0, '#5a5478');
  }

  // Footer: "show hidden (N)" link when there are dismissed sessions. Click
  // unhides everything — they'll reappear on the next event from their source.
  SHOW_HIDDEN_HIT = null;
  if (footerH > 0) {
    const fy = y + h - footerH;
    rect(ctx, x, fy, w, 1, '#2a2440');
    rect(ctx, x, fy + 1, w, footerH - 1, '#15122a');
    const txt = `show hidden (${DISMISSED.size})`;
    fillText(ctx, txt, x + 10, fy + 4, '#9ec0e9', 9);
    SHOW_HIDDEN_HIT = { x, y: fy, w, h: footerH };
  }
}

function render() {
  TICK++;

  const now = performance.now();
  // Reap + state decay + slow detection + walk update
  for (const [k, a] of Agents) {
    if (a.removeAt && now > a.removeAt && !a.exiting) {
      // Start walking out instead of vanishing immediately.
      if (a.seatId) occupiedSeats.delete(a.seatId);
      a.seatId = null;
      a.exiting = true;
      a.path = exitPath(a);
      a.walking = true;
      a.removeAt = null;
    }
    if (a.exiting && (!a.path || a.path.length === 0)) {
      Agents.delete(k);
      continue;
    }
    if (a.state === 'tool' && a.toolStart && now - a.toolStart > SLOW_TOOL_MS) {
      a.slow = true;
    }
    if (!a.exiting && !STICKY_STATES.has(a.state)) {
      const sinceActivity = now - a.lastActivity;
      if (sinceActivity > IDLE_TIMEOUT_MS && a.state !== 'idle') {
        a.state = 'idle';
        a.tool = null; a.toolKind = null; a.slow = false;
      } else if (a.state === 'typing' && sinceActivity > 600) {
        a.state = 'thinking';
      }
    }
    updateAgent(a);
  }

  // Draw floor offscreen — assets when loaded, procedural otherwise.
  rect(offCtx, 0, 0, FLOOR_W, FLOOR_H, PAL.bg);
  if (ASSETS_READY) {
    drawEnvironment();
  } else {
    drawFloor();
    drawAllFurniture();
  }
  // Agents sorted by Y for fake depth. Body first, then "front" furniture a
  // down-facing worker sits behind, then walls, then status overlays on top.
  const agentsArr = Array.from(Agents.values());
  agentsArr.sort((a, b) => a.y - b.y);
  for (const a of agentsArr) drawAgentBodyPass(a);

  if (ASSETS_READY) { drawFrontFurniture(); drawWalls('front'); }

  for (const a of agentsArr) drawAgentOverlay(a);

  // Composite to main canvas
  rect(ctx, 0, 0, CANVAS_W, CANVAS_H, PAL.bg);
  if (officeVisible()) {
    const vp = officeViewport();
    const baseScale = Math.min(vp.w / FLOOR_W, vp.h / FLOOR_H);
    const s = baseScale * ZOOM;
    const w = FLOOR_W * s, h = FLOOR_H * s;
    const ox = vp.x + (vp.w - w) / 2 + PAN_X;
    const oy = vp.y + (vp.h - h) / 2 + PAN_Y;
    ctx.save();
    ctx.beginPath(); ctx.rect(vp.x, vp.y, vp.w, vp.h); ctx.clip();
    ctx.drawImage(off, Math.floor(ox), Math.floor(oy), Math.floor(w), Math.floor(h));
    if (Agents.size === 0) {
      fillText(ctx, 'Empty office. Run `claude ...` to send the first agent in.',
        (vp.x + vp.w / 2 - 170) | 0, (CANVAS_H - 28) | 0, PAL.textDim, 11);
    }
    ctx.restore();
  }

  // Sidebar always shown; header on top
  drawSidebar(0, HEADER_H, SIDEBAR_W, CANVAS_H - HEADER_H);
  drawHeader();

  requestAnimationFrame(render);
}

// =====================================================================
// Sizing / zoom / input
// =====================================================================

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const w = window.innerWidth, h = window.innerHeight;
  cv.style.width = w + 'px';
  cv.style.height = h + 'px';
  cv.width = (w * dpr) | 0;
  cv.height = (h * dpr) | 0;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.imageSmoothingEnabled = false;
  CANVAS_W = w; CANVAS_H = h;
}
function setZoom(z) {
  ZOOM = Math.max(0.5, Math.min(4, z));
  localStorage.setItem('claudeHqZoom', String(ZOOM));
  if (ZOOM <= 1) { PAN_X = 0; PAN_Y = 0; savePan(); }
  else clampPan();
  hud.textContent = `zoom: ${Math.round(ZOOM * 100)}%`;
  clearTimeout(setZoom._hide);
  setZoom._hide = setTimeout(() => { hud.textContent = ''; }, 900);
}

function savePan() {
  localStorage.setItem('claudeHqPanX', String(PAN_X));
  localStorage.setItem('claudeHqPanY', String(PAN_Y));
}

function clampPan() {
  const vp = officeViewport();
  const baseScale = Math.min(vp.w / FLOOR_W, vp.h / FLOOR_H);
  const s = baseScale * ZOOM;
  const w = FLOOR_W * s, h = FLOOR_H * s;
  const maxX = Math.max(0, (w - vp.w) / 2);
  const maxY = Math.max(0, (h - vp.h) / 2);
  PAN_X = Math.max(-maxX, Math.min(maxX, PAN_X));
  PAN_Y = Math.max(-maxY, Math.min(maxY, PAN_Y));
  savePan();
}

window.addEventListener('resize', () => { resizeCanvas(); clampPan(); positionSidebarHandle(); });

// ----- Sidebar resize -----
const sidebarHandle = document.getElementById('sidebar-resize');
function positionSidebarHandle() {
  if (sidebarHandle) sidebarHandle.style.left = SIDEBAR_W + 'px';
}
positionSidebarHandle();
if (sidebarHandle) {
  let sr = null;
  sidebarHandle.addEventListener('mousedown', (e) => {
    sr = { x: e.clientX, w: SIDEBAR_W };
    sidebarHandle.classList.add('dragging');
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  window.addEventListener('mousemove', (e) => {
    if (!sr) return;
    let w = sr.w + (e.clientX - sr.x);
    // Snap to window-relative bounds too so the office viewport never collapses.
    const maxByWindow = Math.max(SIDEBAR_MIN, window.innerWidth - 160);
    w = Math.min(SIDEBAR_MAX, Math.min(maxByWindow, Math.max(SIDEBAR_MIN, w)));
    SIDEBAR_W = w;
    positionSidebarHandle();
    clampPan();
  });
  window.addEventListener('mouseup', () => {
    if (!sr) return;
    sr = null;
    sidebarHandle.classList.remove('dragging');
    document.body.style.userSelect = '';
    try { localStorage.setItem('claudeHqSidebarW', String(SIDEBAR_W)); } catch {}
  });
}
window.addEventListener('keydown', (e) => {
  if (!(e.metaKey || e.ctrlKey)) return;
  if (e.key === '=' || e.key === '+') { setZoom(ZOOM * 1.25); e.preventDefault(); }
  else if (e.key === '-' || e.key === '_') { setZoom(ZOOM / 1.25); e.preventDefault(); }
  else if (e.key === '0') { setZoom(1); e.preventDefault(); }
  else if (e.key === 'g' || e.key === 'G') { if (window.HQGit) { window.HQGit.toggle(); e.preventDefault(); } }
});
window.addEventListener('wheel', (e) => {
  // Plain wheel over the sidebar scrolls the roster.
  if (!(e.metaKey || e.ctrlKey)) {
    if (e.clientX < SIDEBAR_W) {
      ROSTER_SCROLL += e.deltaY;
      e.preventDefault();
    }
    return;
  }
  setZoom(ZOOM * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
  e.preventDefault();
}, { passive: false });

// Drag-to-pan when zoomed in (ignore drags that start on the sidebar)
let _drag = null;
let _didPan = false;
cv.addEventListener('mousedown', (e) => {
  if (e.clientX < SIDEBAR_W) return;
  _didPan = false;
  if (ZOOM <= 1) return;
  _drag = { x: e.clientX, y: e.clientY, panX: PAN_X, panY: PAN_Y };
  cv.style.cursor = 'grabbing';
  e.preventDefault();
});
window.addEventListener('mousemove', (e) => {
  if (!_drag) return;
  const dx = e.clientX - _drag.x, dy = e.clientY - _drag.y;
  if (!_didPan && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) _didPan = true;
  PAN_X = _drag.panX + dx;
  PAN_Y = _drag.panY + dy;
  clampPan();
});
window.addEventListener('mouseup', () => {
  if (!_drag) return;
  _drag = null;
  cv.style.cursor = '';
  savePan();
});

// =====================================================================
// WS event handlers
// =====================================================================

window.addEventListener('claudeConnected', () => { CONNECTED = true; });
window.addEventListener('claudeDisconnected', () => { CONNECTED = false; });

window.addEventListener('claudeEvent', (e) => {
  const ev = e.detail;
  const sessionId = ev.session_id || 'default';
  const agentId = ev.agent_id || null;
  const agent = ensureAgent(sessionId, agentId);
  if (!agent) return; // session is in the dismissed set
  agent.lastActivity = performance.now();
  agent.removeAt = null;

  const sc = STATE;
  switch (ev.type) {
    case 'start':
      agent.state = 'idle';
      agent.chars = 0; agent.tool = null; agent.toolKind = null;
      agent.slow = false; agent.planMode = false;
      break;
    case 'thinking':
      if (agent.state !== 'thinking') agent.state = 'thinking';
      agent.slow = false;
      break;
    case 'tool_call':
      agent.state = 'tool';
      agent.tool = ev.tool || 'tool';
      agent.toolKind = toolKind(agent.tool);
      agent.toolStart = performance.now();
      agent.slow = false;
      break;
    case 'output':
      agent.state = 'typing';
      agent.chars += ev.chars || 0;
      break;
    case 'awaiting_permission':
      agent.state = 'permission';
      break;
    case 'compacting':
      agent.state = 'compacting';
      break;
    case 'asking':
      agent.state = 'asking';
      break;
    case 'plan_mode_enter':
      agent.planMode = true;
      break;
    case 'plan_mode_exit':
      agent.planMode = false;
      break;
    case 'model':
      if (ev.name) agent.model = ev.name;
      break;
    case 'cwd':
      if (ev.path) agent.cwd = ev.path;
      break;
    case 'done':
      agent.planMode = false;
      // HQ-spawned sessions stay seated until the PTY itself exits — the
      // user might run another prompt in the same terminal. Between turns
      // Claude emits Stop after each reply, so for hqOwned we drop straight
      // to idle instead of pinning the sticky green 'done' chip.
      if (agent.hqOwned) {
        agent.state = 'idle';
        agent.tool = null; agent.toolKind = null; agent.slow = false;
      } else {
        agent.state = 'done';
        agent.removeAt = performance.now() + 4000;
      }
      break;
    case 'error':
      agent.state = 'error';
      // For hqOwned, the PTY is still alive — let the user inspect the
      // terminal and retry. The pty:exit event below schedules walk-out.
      if (!agent.hqOwned) agent.removeAt = performance.now() + 6000;
      break;
    case 'session_end':
      // SessionEnd hook fired — the source `claude` process is terminating.
      // Walk out regardless of hqOwned; for HQ-spawned sessions, pty:exit
      // would do the same shortly after anyway.
      agent.state = 'done';
      agent.removeAt = performance.now() + 1500;
      break;
  }
});

// =====================================================================
// Sidebar interaction: + button, click-on-row to toggle terminal panel.
// =====================================================================

function rosterHitAt(clientX, clientY) {
  for (const hb of ROSTER_HITS) {
    if (clientX >= hb.x && clientX < hb.x + hb.w &&
        clientY >= hb.y && clientY < hb.y + hb.h) return hb;
  }
  return null;
}
function inAddButton(clientX, clientY) {
  return ADD_HIT && clientX >= ADD_HIT.x && clientX < ADD_HIT.x + ADD_HIT.w
    && clientY >= ADD_HIT.y && clientY < ADD_HIT.y + ADD_HIT.h;
}

// Convert a screen-space point to floor coordinates using the current transform.
function screenToFloor(clientX, clientY) {
  if (!officeVisible()) return null;
  const vp = officeViewport();
  const baseScale = Math.min(vp.w / FLOOR_W, vp.h / FLOOR_H);
  const s = baseScale * ZOOM;
  const ox = vp.x + (vp.w - FLOOR_W * s) / 2 + PAN_X;
  const oy = vp.y + (vp.h - FLOOR_H * s) / 2 + PAN_Y;
  return { x: (clientX - ox) / s, y: (clientY - oy) / s };
}

// Return the hqOwned agent under a screen-space click in the office, or null.
const AGENT_HIT_R = 22; // floor-pixel radius around the agent pivot
function officeAgentAt(clientX, clientY) {
  if (clientX < SIDEBAR_W) return null;
  const fp = screenToFloor(clientX, clientY);
  if (!fp) return null;
  let best = null, bestD2 = AGENT_HIT_R * AGENT_HIT_R;
  for (const a of Agents.values()) {
    if (!a.hqOwned) continue;
    const dx = fp.x - a.x, dy = fp.y - a.y;
    const d2 = dx * dx + dy * dy;
    if (d2 <= bestD2) { best = a; bestD2 = d2; }
  }
  return best;
}

function inHit(hit, cx, cy) {
  return hit && cx >= hit.x && cx < hit.x + hit.w && cy >= hit.y && cy < hit.y + hit.h;
}
function dismissHitAt(cx, cy) {
  for (const hb of DISMISS_HITS) if (inHit(hb, cx, cy)) return hb;
  return null;
}

cv.addEventListener('click', (e) => {
  // Sidebar clicks: + button, dismiss × on a row, show-hidden footer, or roster row toggle.
  if (e.clientX < SIDEBAR_W) {
    if (inAddButton(e.clientX, e.clientY)) {
      openSpawnDialog();
      return;
    }
    const dh = dismissHitAt(e.clientX, e.clientY);
    if (dh) {
      dismissSession(dh.sessionId);
      return;
    }
    if (inHit(SHOW_HIDDEN_HIT, e.clientX, e.clientY)) {
      clearDismissed();
      return;
    }
    const hit = rosterHitAt(e.clientX, e.clientY);
    if (hit && hit.agent && hit.agent.hqOwned && window.HQTerm) {
      window.HQTerm.toggle(hit.agent.sessionId);
    }
    return;
  }
  // Office clicks: clicking a character opens/focuses their terminal.
  if (_didPan) return;
  const agent = officeAgentAt(e.clientX, e.clientY);
  if (agent && window.HQTerm) {
    window.HQTerm.toggle(agent.sessionId);
  }
});

// Pointer cursor over clickable sidebar zones (+ button, HQ-owned rows) and office agents.
cv.addEventListener('mousemove', (e) => {
  if (_drag) return; // panning the office, leave cursor alone
  if (e.clientX < SIDEBAR_W) {
    if (inAddButton(e.clientX, e.clientY)
        || dismissHitAt(e.clientX, e.clientY)
        || inHit(SHOW_HIDDEN_HIT, e.clientX, e.clientY)) {
      cv.style.cursor = 'pointer'; return;
    }
    const hit = rosterHitAt(e.clientX, e.clientY);
    cv.style.cursor = (hit && hit.agent && hit.agent.hqOwned) ? 'pointer' : '';
    return;
  }
  cv.style.cursor = officeAgentAt(e.clientX, e.clientY) ? 'pointer' : '';
});

// =====================================================================
// Spawn dialog
// =====================================================================

const dlg          = document.getElementById('spawn-dialog');
const dlgCwd       = document.getElementById('spawn-cwd');
const dlgErr       = document.getElementById('spawn-err');
const dlgGo        = document.getElementById('spawn-go');
const dlgX         = document.getElementById('spawn-cancel');
const dlgRecents   = document.getElementById('spawn-recents');
const dlgRecentsLb = document.getElementById('spawn-recents-label');
const dlgSuggest   = document.getElementById('spawn-suggest');
const dlgBypass    = document.getElementById('spawn-bypass');
const RECENTS_KEY  = 'claudeHqRecentCwds';
const RECENTS_MAX  = 8;

const TauriInvoke = (window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke) || null;
let homeDirCached = null;
async function getHomeDir() {
  if (homeDirCached) return homeDirCached;
  if (window.__TAURI__ && window.__TAURI__.path) {
    try { homeDirCached = (await window.__TAURI__.path.homeDir()).replace(/\/+$/, ''); } catch {}
  }
  return homeDirCached || '';
}
function expandHome(p, home) {
  if (!p || !home) return p;
  if (p === '~') return home;
  if (p.startsWith('~/')) return home + p.slice(1);
  return p;
}

function loadRecents() {
  try {
    const raw = localStorage.getItem(RECENTS_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter(s => typeof s === 'string') : [];
  } catch { return []; }
}
function saveRecents(list) {
  try { localStorage.setItem(RECENTS_KEY, JSON.stringify(list)); } catch {}
}
function pushRecent(cwd) {
  if (!cwd) return;
  const normalized = String(cwd).replace(/\/+$/, '') || '/';
  const list = loadRecents().filter(p => p !== normalized);
  list.unshift(normalized);
  saveRecents(list.slice(0, RECENTS_MAX));
}

function splitLeaf(p) {
  const parts = String(p).replace(/\/+$/, '').split('/').filter(Boolean);
  if (parts.length === 0) return { leaf: '/', parent: '' };
  const leaf = parts[parts.length - 1];
  const parent = parts.length > 1 ? '/' + parts.slice(0, -1).join('/') : '/';
  return { leaf, parent };
}

function renderRecents() {
  if (!dlgRecents) return;
  const list = loadRecents();
  dlgRecents.innerHTML = '';
  if (list.length === 0) {
    dlgRecents.style.display = 'none';
    dlgRecentsLb.style.display = 'none';
    return;
  }
  dlgRecents.style.display = 'block';
  dlgRecentsLb.style.display = 'block';
  for (const p of list) {
    const { leaf, parent } = splitLeaf(p);
    const row = document.createElement('div');
    row.className = 'recent-item';
    row.title = p;
    const leafEl = document.createElement('span');
    leafEl.className = 'leaf';
    leafEl.textContent = leaf;
    const parEl = document.createElement('span');
    parEl.className = 'parent';
    parEl.textContent = parent === '/' ? '' : '— ' + parent;
    row.appendChild(leafEl);
    row.appendChild(parEl);
    row.addEventListener('click', () => {
      dlgCwd.value = p;
      submitSpawn();
    });
    dlgRecents.appendChild(row);
  }
}

async function defaultCwd() {
  const list = loadRecents();
  if (list.length > 0) return list[0];
  if (window.__TAURI__ && window.__TAURI__.path) {
    try { return await window.__TAURI__.path.homeDir(); } catch {}
  }
  return '';
}

async function openSpawnDialog() {
  if (!dlg) return;
  dlgErr.textContent = '';
  dlgCwd.value = await defaultCwd();
  if (dlgBypass) dlgBypass.checked = false;
  renderRecents();
  hideSuggest();
  dlg.style.display = 'flex';
  setTimeout(() => { dlgCwd.focus(); dlgCwd.select(); }, 0);
}
function closeSpawnDialog() {
  if (dlg) dlg.style.display = 'none';
  hideSuggest();
}

// ----- Path autocomplete -----

let suggestItems = [];     // array of full paths (strings)
let suggestParent = '';    // resolved parent dir used for the current items
let suggestActive = -1;    // highlighted index, -1 if none
let suggestSeq = 0;        // monotonically increasing token; latest wins

function hideSuggest() {
  if (!dlgSuggest) return;
  dlgSuggest.style.display = 'none';
  dlgSuggest.innerHTML = '';
  suggestItems = [];
  suggestActive = -1;
}

function renderSuggest() {
  if (!dlgSuggest) return;
  dlgSuggest.innerHTML = '';
  if (suggestItems.length === 0) { dlgSuggest.style.display = 'none'; return; }
  suggestItems.forEach((full, idx) => {
    const leaf = full.split('/').filter(Boolean).pop() || full;
    const row = document.createElement('div');
    row.className = 'item' + (idx === suggestActive ? ' active' : '');
    row.textContent = leaf + '/';
    row.title = full;
    row.addEventListener('mousedown', (e) => {
      // mousedown (not click) so the input doesn't blur first and hide us.
      e.preventDefault();
      acceptSuggest(idx);
    });
    dlgSuggest.appendChild(row);
  });
  dlgSuggest.style.display = 'block';
  // Keep the active row visible.
  const active = dlgSuggest.children[suggestActive];
  if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest' });
}

function splitForSuggest(value) {
  // Need at least one slash to know the parent.
  const i = value.lastIndexOf('/');
  if (i < 0) return null;
  const parent = i === 0 ? '/' : value.slice(0, i);
  const prefix = value.slice(i + 1);
  return { parent, prefix };
}

async function updateSuggestions() {
  if (!TauriInvoke || !dlgSuggest) return;
  const raw = dlgCwd.value;
  const split = splitForSuggest(raw);
  if (!split) { hideSuggest(); return; }
  const home = await getHomeDir();
  const parentResolved = expandHome(split.parent, home);
  const prefix = split.prefix;
  const myTok = ++suggestSeq;
  let names = [];
  try {
    names = await TauriInvoke('list_dir', {
      path: parentResolved,
      includeHidden: prefix.startsWith('.'),
    });
  } catch {
    if (myTok !== suggestSeq) return;
    hideSuggest();
    return;
  }
  if (myTok !== suggestSeq) return;
  const lower = prefix.toLowerCase();
  const matches = names
    .filter(n => !lower || n.toLowerCase().startsWith(lower))
    .slice(0, 40)
    .map(n => (parentResolved === '/' ? '/' + n : parentResolved + '/' + n));
  suggestItems = matches;
  suggestParent = parentResolved;
  suggestActive = matches.length > 0 ? 0 : -1;
  renderSuggest();
}

function acceptSuggest(idx) {
  if (idx < 0 || idx >= suggestItems.length) return;
  // Preserve the user's `~` prefix if they typed one — replace only the leaf.
  const raw = dlgCwd.value;
  const i = raw.lastIndexOf('/');
  const userParent = i < 0 ? '' : (i === 0 ? '/' : raw.slice(0, i));
  const picked = suggestItems[idx];
  const leaf = picked.split('/').filter(Boolean).pop() || '';
  const joined = userParent === '/' ? '/' + leaf : (userParent + '/' + leaf);
  dlgCwd.value = joined + '/';
  // Re-trigger to show children of the freshly-picked dir.
  updateSuggestions();
}

async function submitSpawn() {
  const cwd = dlgCwd.value.trim();
  const bypassPermissions = !!(dlgBypass && dlgBypass.checked);
  dlgErr.textContent = '';
  dlgGo.disabled = true;
  try {
    if (!window.HQTerm) throw new Error('terminal module not loaded');
    const sid = await window.HQTerm.spawn({ cwd: cwd || null, bypassPermissions });
    if (cwd) pushRecent(cwd);
    closeSpawnDialog();
  } catch (e) {
    dlgErr.textContent = String(e && e.message || e);
  } finally {
    dlgGo.disabled = false;
  }
}

if (dlg) {
  dlgGo.addEventListener('click', submitSpawn);
  dlgX .addEventListener('click', closeSpawnDialog);

  // Debounced suggestions as the user types.
  let suggestTimer = null;
  dlgCwd.addEventListener('input', () => {
    if (suggestTimer) clearTimeout(suggestTimer);
    suggestTimer = setTimeout(updateSuggestions, 80);
  });
  dlgCwd.addEventListener('focus', updateSuggestions);
  dlgCwd.addEventListener('blur', () => {
    // Delay so a mousedown on a suggestion still registers.
    setTimeout(hideSuggest, 120);
  });

  dlgCwd.addEventListener('keydown', (e) => {
    const open = dlgSuggest && dlgSuggest.style.display !== 'none' && suggestItems.length > 0;
    if (e.key === 'ArrowDown' && open) {
      e.preventDefault();
      suggestActive = (suggestActive + 1) % suggestItems.length;
      renderSuggest();
    } else if (e.key === 'ArrowUp' && open) {
      e.preventDefault();
      suggestActive = (suggestActive - 1 + suggestItems.length) % suggestItems.length;
      renderSuggest();
    } else if (e.key === 'Tab' && open) {
      e.preventDefault();
      acceptSuggest(suggestActive < 0 ? 0 : suggestActive);
    } else if (e.key === 'Enter' && open && suggestActive >= 0) {
      // Enter on a highlighted suggestion: accept it instead of submitting.
      e.preventDefault();
      e.stopPropagation();
      acceptSuggest(suggestActive);
    } else if (e.key === 'Escape' && open) {
      e.preventDefault();
      e.stopPropagation();
      hideSuggest();
    }
  });

  dlg.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSpawnDialog();
    else if (e.key === 'Enter') submitSpawn();
  });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) closeSpawnDialog(); });
}

// =====================================================================
// PTY exit → walk the agent out and release.
// =====================================================================

if (window.__TAURI__ && window.__TAURI__.event) {
  window.__TAURI__.event.listen('pty:exit', (e) => {
    const sid = e.payload && e.payload.session_id;
    if (!sid) return;
    for (const [k, a] of Agents) {
      if (a.sessionId !== sid) continue;
      a.state = 'done';
      // Small grace so the user sees the final state before they leave.
      a.removeAt = performance.now() + 1500;
    }
  });
}

// Kick off asset loading; flips ASSETS_READY when sprites/tiles are ready.
// Until then (or if it fails) the render loop uses the procedural fallback.
if (typeof Sprites !== 'undefined') {
  Sprites.load('assets').then((ok) => { ASSETS_READY = ok; });
}

resizeCanvas();
render();

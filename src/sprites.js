// =====================================================================
// Claude HQ — sprite/asset engine (v2, layered characters).
//
// Loads PNG spritesheets + JSON atlases at runtime and provides draw
// helpers for animated characters and tiled/placed office furniture.
//
// Characters are composed from separable layers so each agent is a
// distinct, polished person while state stays glanceable:
//   outline_{style}_{acc}.png : dark 1px shape ring (per silhouette)
//   agent_shirt.png           : grayscale shirt+sleeves  → tinted to STATE color
//   body_skin{0..3}.png       : skin head+face+hands, pants, shoes (fixed)
//   hair_{style}.png          : grayscale hair          → tinted to HAIR color
//   acc_{glasses,headphones}  : accessory (fixed colors)
// Draw order: outline, shirt(state), body(skin), hair(haircolor), accessory.
//
// Degrades gracefully: if assets fail to load, Sprites.ready stays false
// and renderer.js falls back to its procedural drawing.
// =====================================================================

const Sprites = (() => {
  const state = {
    ready: false,
    base: 'assets',
    char: null,          // characters/agent.json
    office: null,        // office/office.json
    bodySheets: [],      // Image[] per skin index
    hairSheets: {},      // style -> Image (grayscale)
    shirtSheet: null,    // Image (grayscale)
    accSheets: {},       // accName -> Image
    outlineSheets: {},   // "style|acc" -> Image
    tiles: {},           // name -> Image (floor/rug/wall)
    pieces: {},          // name -> Image (furniture)
    shirtTint: new Map(),// colorString -> canvas (whole tinted shirt sheet)
    hairTint: new Map(), // "style|color" -> canvas (whole tinted hair sheet)
  };

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error('img load failed: ' + url));
      img.src = url;
    });
  }
  async function loadJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error('json load failed: ' + url);
    return res.json();
  }

  async function load(basePath = 'assets') {
    state.base = basePath;
    try {
      const charDir = `${basePath}/characters`;
      const offDir  = `${basePath}/office`;
      const [char, office] = await Promise.all([
        loadJSON(`${charDir}/agent.json`),
        loadJSON(`${offDir}/office.json`),
      ]);
      state.char = char;
      state.office = office;
      const L = char.layers;

      // ---- character layers ----
      const bodyJobs = [];
      for (let s = 0; s < char.skinCount; s++)
        bodyJobs.push(loadImage(`${charDir}/${L.body.replace('{skin}', s)}`));
      const styleNames = char.hairStyles;
      const hairJobs = styleNames.map(st => loadImage(`${charDir}/${L.hair.replace('{style}', st)}`));
      const accNames = char.accessories.filter(a => a !== 'none');
      const accJobs = accNames.map(a => loadImage(`${charDir}/${L.acc.replace('{acc}', a)}`));
      const outlineKeys = [];
      const outlineJobs = [];
      for (const st of styleNames) for (const a of char.accessories) {
        outlineKeys.push(`${st}|${a}`);
        outlineJobs.push(loadImage(`${charDir}/${L.outline.replace('{style}', st).replace('{acc}', a)}`));
      }

      const [bodies, hairs, shirt, accs, outlines] = await Promise.all([
        Promise.all(bodyJobs),
        Promise.all(hairJobs),
        loadImage(`${charDir}/${L.shirt}`),
        Promise.all(accJobs),
        Promise.all(outlineJobs),
      ]);
      state.bodySheets = bodies;
      styleNames.forEach((st, i) => { state.hairSheets[st] = hairs[i]; });
      state.shirtSheet = shirt;
      accNames.forEach((a, i) => { state.accSheets[a] = accs[i]; });
      outlineKeys.forEach((k, i) => { state.outlineSheets[k] = outlines[i]; });

      // ---- office tiles + furniture ----
      const tileEntries = Object.entries(office.tiles || {});
      const tileImgs = await Promise.all(tileEntries.map(([, f]) => loadImage(`${offDir}/${f}`)));
      tileEntries.forEach(([name], i) => { state.tiles[name] = tileImgs[i]; });
      const pieceNames = Object.keys(office.anchors || {});
      const pieceImgs = await Promise.all(pieceNames.map(n => loadImage(`${offDir}/${n}.png`)));
      pieceNames.forEach((n, i) => { state.pieces[n] = pieceImgs[i]; });

      state.ready = true;
      return true;
    } catch (err) {
      console.warn('[Sprites] asset load failed, using procedural fallback:', err);
      state.ready = false;
      return false;
    }
  }

  // ---- generic tinting (multiply + alpha-mask restore), cached ----
  function tintSheet(srcImg, color) {
    const cv = document.createElement('canvas');
    cv.width = srcImg.width; cv.height = srcImg.height;
    const c = cv.getContext('2d');
    c.imageSmoothingEnabled = false;
    c.clearRect(0, 0, cv.width, cv.height);
    c.globalCompositeOperation = 'source-over';
    c.drawImage(srcImg, 0, 0);
    c.globalCompositeOperation = 'multiply';
    c.fillStyle = color;
    c.fillRect(0, 0, cv.width, cv.height);
    c.globalCompositeOperation = 'destination-in';
    c.drawImage(srcImg, 0, 0);
    c.globalCompositeOperation = 'source-over';
    return cv;
  }
  function shirtTinted(color) {
    let cv = state.shirtTint.get(color);
    if (!cv) { cv = tintSheet(state.shirtSheet, color); state.shirtTint.set(color, cv); }
    return cv;
  }
  function hairTinted(style, color) {
    const key = style + '|' + color;
    let cv = state.hairTint.get(key);
    if (!cv) { cv = tintSheet(state.hairSheets[style], color); state.hairTint.set(key, cv); }
    return cv;
  }

  // ---- deterministic appearance from an integer hash ----
  function pickAppearance(h) {
    const ch = state.char;
    h = Math.abs(h | 0);
    const skin = h % ch.skinCount;
    const style = ch.hairStyles[((h / ch.skinCount) | 0) % ch.hairStyles.length];
    const colorHex = ch.hairColors[((h / (ch.skinCount * ch.hairStyles.length)) | 0) % ch.hairColors.length];
    // accessory: ~50% none, then glasses / headphones / cap
    const roll = ((h / 97) | 0) % 6;
    const acc = roll === 3 ? 'glasses' : roll === 4 ? 'headphones' : roll === 5 ? 'cap' : 'none';
    return { skin, style, colorHex, acc };
  }

  function cellOf(animName, frameIdx) {
    const anims = state.char.anims;
    const a = anims[animName] || anims['idle_down'];
    const col = a.cols ? a.cols[frameIdx % a.cols.length] : a.frames[frameIdx % a.frames.length];
    return { sx: col * state.char.cell, sy: a.row * state.char.cell, cell: state.char.cell };
  }
  function hasAnim(name) { return state.ready && state.char.anims[name]; }

  // Compose + draw an agent. apHash = integer identity; color = STATE css color.
  function drawAgentSprite(ctx, x, y, animName, frameIdx, apHash, color) {
    const ap = pickAppearance(apHash);
    const { sx, sy, cell } = cellOf(animName, frameIdx);
    const [ax, ay] = state.char.anchor;
    const dx = Math.round(x - ax), dy = Math.round(y - ay);
    const blit = (img) => ctx.drawImage(img, sx, sy, cell, cell, dx, dy, cell, cell);
    blit(state.outlineSheets[`${ap.style}|${ap.acc}`]);
    blit(shirtTinted(color));
    blit(state.bodySheets[ap.skin]);
    blit(hairTinted(ap.style, ap.colorHex));
    if (ap.acc !== 'none' && state.accSheets[ap.acc]) blit(state.accSheets[ap.acc]);
  }

  // ---- environment helpers ----
  function tileRegion(ctx, img, x, y, w, h) {
    if (!img) return;
    ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
    const tw = img.width, th = img.height;
    for (let ty = y; ty < y + h; ty += th)
      for (let tx = x; tx < x + w; tx += tw) ctx.drawImage(img, tx, ty);
    ctx.restore();
  }
  function fillFloor(ctx, x, y, w, h) { tileRegion(ctx, state.tiles.floor, x, y, w, h); }
  function fillWall(ctx, x, y, w, h)  { tileRegion(ctx, state.tiles.wall,  x, y, w, h); }
  function drawRug(ctx, x, y, w, h) {
    const e = state.office.rugEdge || [35, 72, 106];
    ctx.fillStyle = `rgb(${e[0]},${e[1]},${e[2]})`;
    ctx.fillRect(x, y, w, h);
    tileRegion(ctx, state.tiles.rug, x + 2, y + 2, w - 4, h - 4);
  }
  function drawPiece(ctx, name, px, py) {
    const img = state.pieces[name];
    const anch = (state.office.anchors && state.office.anchors[name]) || [0, 0];
    if (!img) return;
    ctx.drawImage(img, Math.round(px - anch[0]), Math.round(py - anch[1]));
  }

  return {
    get ready() { return state.ready; },
    load, drawAgentSprite, hasAnim, pickAppearance,
    fillFloor, fillWall, drawRug, drawPiece, tileRegion,
    _state: state,
  };
})();

// Interactive structural plans – K-400 (foundations & piles).
// Data: data/plans/k400.json (tools/plans/build_k400.py) · display constants: data/config/plans.json
import { pileElevation, pileSection, beamSection, beamElevation, role, col } from './sketch.js';

const $ = (s) => document.querySelector(s);
const NS = 'http://www.w3.org/2000/svg';
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const f2 = (v) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2);
const n1 = (v) => (Math.round(v * 10) / 10).toLocaleString('he-IL', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const n2 = (v) => v.toLocaleString('he-IL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const n0 = (v) => Math.round(v).toLocaleString('he-IL');

const ZONE = { basement: 'בתחתית המרתף', ground: 'מחוץ למרתף (קומת קרקע / חומות)' };
const LAYER_HE = { groundBeams: 'קורות יסוד – מרתף (K-11)', groundFloorBeams: 'קורות יסוד – קומת קרקע (K-21)', ceilingBeams: 'קורות מעל המרתף (K-21)' };
const ROLE_HE = {
  long: ['מוטות אורך', 'השלד הראשי. רצים לכל האורך ונושאים את הכוחות'],
  top: ['ברזל עליון', 'מוטות בחלק העליון של הקורה'],
  tie: ['חישוקים / ספירלה', '"טבעות" שעוטפות את המוטות ומחזיקות אותם במקום'],
  ring: ['טבעות חיזוק', 'שומרות על צורת כלוב הברזל בזמן ההרמה וההכנסה לקידוח'],
  start: ['קוצים', 'מוטות שבולטים מהבטון ונכנסים לאלמנט הבא (קורה / קיר)'],
};

const state = { cfg: null, D: null, data: null, view: null, sel: null, layers: {}, colorMode: 'dia', measure: null, els: new Map() };

/* ---------- geometry: ITM → K-400 sheet pt ---------- */
let G;
function toSheet(E, N) {
  const dE = E - G.tx, dN = N - G.ty, c = Math.cos(G.theta_rad), s = Math.sin(G.theta_rad);
  const X = dE * c + dN * s, Y = -dE * s + dN * c;
  return [X * G.ptPerM, -Y * G.ptPerM];
}
const ringPath = (r) => r.map(([E, N], i) => { const [x, y] = toSheet(E, N); return (i ? 'L' : 'M') + x.toFixed(2) + ',' + y.toFixed(2); }).join('') + 'Z';
function beamRing(b) {
  const [[E1, N1], [E2, N2]] = b.axisITM; const L = Math.hypot(E2 - E1, N2 - N1);
  const nx = -(N2 - N1) / L * b.width_m / 2, ny = (E2 - E1) / L * b.width_m / 2;
  return [[E1 + nx, N1 + ny], [E2 + nx, N2 + ny], [E2 - nx, N2 - ny], [E1 - nx, N1 - ny]];
}

/* ---------- boot ---------- */
async function boot() {
  const cfg = await (await fetch('data/config/plans.json')).json();
  const sheet = cfg.sheets['K-400'];
  const data = await (await fetch(sheet.data)).json();
  Object.assign(state, { cfg, D: cfg.display, data, sheet });
  G = data.georeference;
  state.piles = Object.fromEntries(data.piles.map((p) => [p.id, p]));
  state.beams = Object.fromEntries(data.beams.map((b) => [b.id, b]));
  buildSheets(); buildSvg(); buildLayers(); bindUi(); legend();
  const [ax, ay] = toSheet(G.tx, G.ty), [bx, by] = toSheet(G.tx, G.ty + 1);
  $('#pl-north i').style.transform = `rotate(${Math.atan2(bx - ax, -(by - ay)) * 180 / Math.PI}deg)`;
  fit(); fromHash();
  $('#pl-loading').hidden = true;
  window.__plansReady = true;
}

function buildSheets() {
  const nav = $('#pl-sheets');
  nav.innerHTML = `<button class="on" type="button" aria-pressed="true">K-400 יסודות</button>` +
    state.cfg.upcoming.map((s) => `<button type="button" disabled title="בשלב הבא">${s}<small>בקרוב</small></button>`).join('');
}

function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}

function buildSvg() {
  const svg = $('#pl-svg'), D = state.D, d = state.data, C = D.colors;
  const bg = state.sheet.background; const [bx, by, bw, bh] = bg.crop_pt;
  state.world = el('g', { id: 'world' }, svg);
  const gBg = el('g', { 'data-layer': 'bg' }, state.world);
  el('image', { href: bg.image, x: bx, y: by, width: bw, height: bh, class: 'bg', opacity: D.bgOpacity, preserveAspectRatio: 'none' }, gBg);
  state.bgImg = gBg.firstChild;
  const layer = (id) => el('g', { 'data-layer': id }, state.world);
  const L = { plot: layer('plot'), walls: layer('walls'), footings: layer('footings'), groundBeams: layer('groundBeams'),
    groundFloorBeams: layer('groundFloorBeams'), ceilingBeams: layer('ceilingBeams'), caps: layer('caps'), piles: layer('piles'), labels: layer('labels') };
  state.L = L;
  el('path', { d: ringPath(d.plot.ringITM), fill: 'none', stroke: C.plot, 'stroke-width': 2, 'stroke-dasharray': '10 6' }, L.plot);
  const add = (g, key, kind, id, build) => {
    const a = el('g', { class: 'el', 'data-key': key, tabindex: 0, role: 'button', 'aria-label': `${kind} ${id}` }, g);
    build(a); state.els.set(key, a); return a;
  };
  for (const w of d.basementWalls) {
    add(L.walls, 'wall:' + w.id, 'קיר מרתף', w.id, (a) => {
      const rings = (w.parts && w.parts.length ? w.parts.map((p) => p.ringITM) : [w.footprintITM]);
      el('path', { d: rings.map(ringPath).join(''), class: 'shape', fill: C.wall, 'fill-opacity': .45, stroke: C.wall, 'stroke-width': 1, 'fill-rule': 'evenodd' }, a);
    });
  }
  for (const f of d.footings) {
    add(L.footings, 'footing:' + f.id, 'יסוד חומה', f.id, (a) => {
      el('path', { d: ringPath(f.ringITM), class: 'shape', fill: C.wall, 'fill-opacity': .18, stroke: C.wall, 'stroke-width': 1 }, a);
    });
  }
  for (const b of d.beams) {
    const c = b.layer === 'groundBeams' ? C.beamK11 : b.layer === 'ceilingBeams' ? C.beamCeil : C.beamK21;
    add(L[b.layer] || L.groundFloorBeams, 'beam:' + b.id, 'קורה', b.id, (a) => {
      el('path', { d: ringPath(beamRing(b)), class: 'shape', fill: c, 'fill-opacity': D.beamOpacity, stroke: c, 'stroke-width': 1 }, a);
    });
    const [[E1, N1], [E2, N2]] = b.axisITM; const [x, y] = toSheet((E1 + E2) / 2, (N1 + N2) / 2);
    el('text', { x, y: y - 6, class: 'lbl', 'text-anchor': 'middle', 'data-for': b.layer }, L.labels).textContent = b.id;
  }
  for (const c of d.pileCaps) {
    add(L.caps, 'cap:' + c.id, 'ראש כלונס כפול', c.id, (a) => {
      el('path', { d: ringPath(c.ringITM), class: 'shape', fill: C.cap, 'fill-opacity': .35, stroke: C.cap, 'stroke-width': 1.2 }, a);
    });
  }
  for (const p of d.piles) {
    const [x, y] = toSheet(p.E, p.N); const r = p.diameter_m / 2 * G.ptPerM;
    p._xy = [x, y];
    add(L.piles, 'pile:' + p.id, 'כלונס', p.id, (a) => {
      el('circle', { cx: x, cy: y, r: Math.max(r, 12), fill: 'transparent' }, a);   // easier to hit on a phone
      el('circle', { cx: x, cy: y, r, class: 'shape', 'stroke-width': D.pileStroke_pt, 'fill-opacity': .55 }, a);
    });
    el('text', { x: x + r + 3, y: y - r - 2, class: 'lbl', 'data-for': 'piles' }, L.labels).textContent = p.id;
  }
  state.mLayer = el('g', {}, state.world);
  colorPiles();
}

/* ---------- pile colouring ---------- */
function scaleColor(t) {   // 0..1 → blue → amber → red (sequential, readable in both themes)
  const stops = [[37, 99, 235], [217, 119, 6], [185, 28, 28]];
  const i = Math.min(1, Math.floor(t * 2)), u = t * 2 - i; const a = stops[i], b = stops[i + 1];
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * u)).join(',')})`;
}
function colorPiles() {
  const C = state.D.colors, m = state.colorMode, ps = state.data.piles;
  const val = { head: (p) => p.headRel, load: (p) => p.designLoad_t, length: (p) => p.length_m }[m];
  let lo = 0, hi = 1;
  if (val) { lo = Math.min(...ps.map(val)); hi = Math.max(...ps.map(val)); }
  state.colorRange = [lo, hi];
  for (const p of ps) {
    const c = m === 'dia' ? (p.diameter_m >= 0.6 ? C.pile60 : C.pile50) : scaleColor(hi > lo ? (val(p) - lo) / (hi - lo) : 0);
    const s = state.els.get('pile:' + p.id).querySelector('.shape');
    s.setAttribute('fill', c); s.setAttribute('stroke', p.overAllowed ? C.sel : c);
  }
  legend();
}
function legend() {
  const C = state.D.colors, m = state.colorMode, box = $('#pl-legend');
  if (!state.data) return;
  if (m === 'dia') {
    const c = (d) => state.data.piles.filter((p) => p.diameter_m === d).length;
    box.innerHTML = `<div class="row"><span class="dot" style="background:${C.pile50}"></span>כלונס ø50 <b>(${c(0.5)})</b></div>` +
      `<div class="row"><span class="dot" style="background:${C.pile60}"></span>כלונס ø60 <b>(${c(0.6)})</b></div>`;
  } else {
    const [lo, hi] = state.colorRange; const u = { head: "מ'", load: 'טון', length: "מ'" }[m];
    const fmt = (v) => (m === 'head' ? f2(v) : String(v));
    box.innerHTML = `<div class="row"><b>${{ head: 'מפלס ראש', load: 'עומס תכנון', length: 'אורך' }[m]}</b></div>` +
      `<div class="row"><span class="dot" style="background:${scaleColor(0)}"></span>${fmt(lo)} ${u}</div>` +
      `<div class="row"><span class="dot" style="background:${scaleColor(.5)}"></span>${fmt((lo + hi) / 2)} ${u}</div>` +
      `<div class="row"><span class="dot" style="background:${scaleColor(1)}"></span>${fmt(hi)} ${u}</div>`;
  }
  const over = state.data.piles.filter((p) => p.overAllowed).length;
  if (over) box.innerHTML += `<div class="row"><span class="dot" style="background:transparent;border:2px solid ${C.sel}"></span>מעל העומס המותר <b>(${over})</b></div>`;
}

/* ---------- layers panel ---------- */
function buildLayers() {
  const C = state.D.colors;
  const defs = [
    ['bg', 'הגיליון המקורי (רקע)', '#999'], ['piles', 'כלונסאות', C.pile50], ['groundBeams', LAYER_HE.groundBeams, C.beamK11],
    ['groundFloorBeams', LAYER_HE.groundFloorBeams, C.beamK21], ['ceilingBeams', LAYER_HE.ceilingBeams, C.beamCeil], ['caps', 'ראש כלונס כפול', C.cap],
    ['walls', 'קירות מרתף', C.wall], ['footings', 'יסודות חומות', C.wall], ['plot', 'גבול המגרש', C.plot], ['labels', 'מספרים ותוויות', '#888'],
  ];
  let saved = {}; try { saved = JSON.parse(localStorage.getItem('plans.layers') || '{}'); } catch { /* storage blocked */ }
  const box = $('#pl-layers');
  box.innerHTML = '<h4>שכבות</h4>' + defs.map(([id, he, c]) =>
    `<label><input type="checkbox" id="ly-${id}" data-ly="${id}" ${saved[id] === false ? '' : 'checked'}><span class="sw" style="background:${c}"></span>${he}</label>`).join('') +
    `<h4>שקיפות הגיליון</h4><input type="range" id="ly-bg-op" min="0" max="1" step="0.05" value="${state.D.bgOpacity}" aria-label="שקיפות הגיליון">`;
  box.addEventListener('change', (e) => {
    const ly = e.target.dataset.ly;
    if (ly) { state.layers[ly] = e.target.checked; applyLayers(); try { localStorage.setItem('plans.layers', JSON.stringify(state.layers)); } catch { /* ignore */ } }
  });
  $('#ly-bg-op').addEventListener('input', (e) => state.bgImg.setAttribute('opacity', e.target.value));
  for (const [id] of defs) state.layers[id] = saved[id] !== false;
  applyLayers();
}
function applyLayers() {
  for (const g of state.world.querySelectorAll('[data-layer]')) g.style.display = state.layers[g.dataset.layer] === false ? 'none' : '';
  for (const t of state.L.labels.querySelectorAll('[data-for]')) t.style.display = state.layers[t.dataset.for] === false ? 'none' : '';
}

/* ---------- view (pan / zoom on the viewBox) ----------
   One view {x, y, w} in sheet pt; applied once per animation frame. Pinch keeps the sheet point that was under
   the fingers' midpoint at the start under the current midpoint (zoom + pan together, no drift). */
let rect = null, rafId = 0, pendingView = null, anim = null;
function measure() { rect = $('#pl-svg').getBoundingClientRect(); }
function clampW(w) { return Math.min(Math.max(w, state.wMin), state.wMax); }
function applyView() {
  rafId = 0; const v = pendingView; if (!v) return; pendingView = null;
  const h = v.w * (rect.height / Math.max(rect.width, 1));
  $('#pl-svg').setAttribute('viewBox', `${v.x.toFixed(2)} ${v.y.toFixed(2)} ${v.w.toFixed(2)} ${h.toFixed(2)}`);
  const ptPerPx = v.w / Math.max(rect.width, 1); const m = 110 * ptPerPx / G.ptPerM;   // scale bar ≈ 110 px
  const nice = [0.5, 1, 2, 5, 10, 20].find((x) => x >= m * 0.6) || 20;
  const sb = $('#pl-scale'); sb.style.width = (nice * G.ptPerM / ptPerPx) + 'px'; sb.textContent = nice + " מ'";
}
function setView(v, now) {
  state.view = v; pendingView = v;
  if (now) { if (rafId) cancelAnimationFrame(rafId); applyView(); } else if (!rafId) rafId = requestAnimationFrame(applyView);
}
const toWorld = (px, py, v = state.view) => [v.x + (px - rect.left) / rect.width * v.w, v.y + (py - rect.top) / rect.width * v.w];
function viewKeeping(wx, wy, px, py, w) {   // view of width w that puts sheet point (wx, wy) under screen point (px, py)
  return { x: wx - (px - rect.left) / rect.width * w, y: wy - (py - rect.top) / rect.width * w, w };
}
function stopAnim() { if (anim) { cancelAnimationFrame(anim); anim = null; } }
function animateTo(target, ms = 260) {
  stopAnim();
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { setView(target); return; }
  const from = { ...state.view }, t0 = performance.now();
  const step = (t) => {
    const u = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - u, 3);
    // interpolate the zoom geometrically so the motion looks even
    const w = from.w * Math.pow(target.w / from.w, e);
    const k = (from.w === target.w) ? e : (w - from.w) / (target.w - from.w);
    setView({ x: from.x + (target.x - from.x) * k, y: from.y + (target.y - from.y) * k, w }, true);
    anim = u < 1 ? requestAnimationFrame(step) : null;
  };
  anim = requestAnimationFrame(step);
}
function fit(animated) {
  measure();
  const b = state.fitBox; const pad = 140;
  const w = Math.max(b.width + 2 * pad, (b.height + 2 * pad) * rect.width / Math.max(rect.height, 1));
  const h = w * rect.height / Math.max(rect.width, 1);
  const v = { x: b.x + b.width / 2 - w / 2, y: b.y + b.height / 2 - h / 2, w };
  if (animated === true) animateTo(v); else setView(v, true);
}
function zoomAt(px, py, k, animated) {
  const [wx, wy] = toWorld(px, py); const v = viewKeeping(wx, wy, px, py, clampW(state.view.w / k));
  if (animated) animateTo(v); else setView(v);
}
function svgPoint(ev) { measure(); return toWorld(ev.clientX, ev.clientY); }
function centerOn(x, y) {
  measure(); const v = state.view; const h = v.w * rect.height / rect.width;
  animateTo({ x: x - v.w / 2, y: y - h / 2, w: v.w });
}

/* ---------- UI ---------- */
function bindUi() {
  const svg = $('#pl-svg'); const ptrs = new Map();
  let drag = null, moved = false, pinch = null, lastTap = 0, vel = [0, 0], lastMove = null, fling = 0;
  measure();
  const b = state.L.piles.getBBox(); state.fitBox = b;
  const base = b.width + 280; state.wMin = base / state.D.maxZoom; state.wMax = base / state.D.minZoom;
  new ResizeObserver(() => { measure(); if (state.view) setView(state.view, true); }).observe(svg);

  // wheel / trackpad: accumulate per frame; ctrl+wheel = trackpad pinch (small deltas)
  let wheelAcc = 0, wheelAt = null, wheelRaf = 0;
  svg.addEventListener('wheel', (e) => {
    e.preventDefault(); stopAnim(); cancelAnimationFrame(fling);
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? rect.height : 1;
    wheelAcc += e.deltaY * unit * (e.ctrlKey ? 4 : 1); wheelAt = [e.clientX, e.clientY];
    if (!wheelRaf) wheelRaf = requestAnimationFrame(() => {
      wheelRaf = 0; const k = Math.exp(-Math.max(-300, Math.min(300, wheelAcc)) * 0.0022); wheelAcc = 0;
      zoomAt(wheelAt[0], wheelAt[1], k);
    });
  }, { passive: false });

  const startPinch = () => {
    const [a, c] = [...ptrs.values()]; const mx = (a[0] + c[0]) / 2, my = (a[1] + c[1]) / 2;
    pinch = { d: Math.max(Math.hypot(a[0] - c[0], a[1] - c[1]), 1), w: state.view.w, world: toWorld(mx, my) };
  };
  svg.addEventListener('pointerdown', (e) => {
    stopAnim(); cancelAnimationFrame(fling); measure(); if (e.pointerType !== 'mouse') $('#pl-tip').hidden = true;
    ptrs.set(e.pointerId, [e.clientX, e.clientY]); try { svg.setPointerCapture(e.pointerId); } catch { /* ignore */ }
    if (ptrs.size === 1) { moved = false; drag = { x: e.clientX, y: e.clientY, v: { ...state.view }, target: e.target }; vel = [0, 0]; lastMove = [e.clientX, e.clientY, performance.now()]; }
    if (ptrs.size === 2) { startPinch(); drag = null; moved = true; }
  });
  svg.addEventListener('pointermove', (e) => {
    if (!ptrs.has(e.pointerId)) { if (e.pointerType === 'mouse') hover(e); return; }
    ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    if (pinch && ptrs.size >= 2) {
      const [a, c] = [...ptrs.values()]; const d = Math.max(Math.hypot(a[0] - c[0], a[1] - c[1]), 1);
      const mx = (a[0] + c[0]) / 2, my = (a[1] + c[1]) / 2;
      setView(viewKeeping(pinch.world[0], pinch.world[1], mx, my, clampW(pinch.w * pinch.d / d)));
      return;
    }
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!moved && Math.hypot(dx, dy) > 6) { moved = true; svg.classList.add('drag'); }
      if (moved) {
        const k = drag.v.w / rect.width; setView({ x: drag.v.x - dx * k, y: drag.v.y - dy * k, w: drag.v.w });
        const t = performance.now(), dt = Math.max(t - lastMove[2], 1);
        vel = [0.8 * vel[0] + 0.2 * (e.clientX - lastMove[0]) / dt, 0.8 * vel[1] + 0.2 * (e.clientY - lastMove[1]) / dt];
        lastMove = [e.clientX, e.clientY, t];
      }
    }
  });
  const up = (e) => {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.delete(e.pointerId); svg.classList.remove('drag');
    if (ptrs.size === 1) {          // pinch → one finger left: continue as a pan from here, no jump
      pinch = null; const [p] = [...ptrs.values()];
      drag = { x: p[0], y: p[1], v: { ...state.view }, target: null }; lastMove = [p[0], p[1], performance.now()]; vel = [0, 0];
      return;
    }
    if (ptrs.size === 0) {
      pinch = null;
      if (drag && !moved) {
        const now = performance.now();
        if (e.pointerType === 'touch' && now - lastTap < 300 && !state.measure) { zoomAt(e.clientX, e.clientY, 2, true); lastTap = 0; }
        else { lastTap = now; click(e, drag.target); }
      } else if (drag && moved && performance.now() - lastMove[2] < 80 && Math.hypot(...vel) > 0.25
        && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
        let [vx, vy] = vel; let t0 = performance.now();      // inertia (px per ms, decaying)
        const glide = (t) => {
          const dt = t - t0; t0 = t; const k = state.view.w / rect.width;
          setView({ x: state.view.x - vx * dt * k, y: state.view.y - vy * dt * k, w: state.view.w }, true);
          const f = Math.pow(0.94, dt / 16); vx *= f; vy *= f;
          fling = Math.hypot(vx, vy) > 0.02 ? requestAnimationFrame(glide) : 0;
        };
        fling = requestAnimationFrame(glide);
      }
      drag = null;
    }
  };
  svg.addEventListener('pointerup', up);
  svg.addEventListener('pointercancel', (e) => { ptrs.delete(e.pointerId); if (!ptrs.size) { drag = null; pinch = null; } });
  // Safari: stop the page-level pinch gesture from zooming the whole page
  for (const ev of ['gesturestart', 'gesturechange']) svg.addEventListener(ev, (e) => e.preventDefault());
  $('#pl-zin').addEventListener('click', () => { measure(); zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, 1.8, true); });
  $('#pl-zout').addEventListener('click', () => { measure(); zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, 1 / 1.8, true); });
  svg.addEventListener('pointerleave', () => { $('#pl-tip').hidden = true; });
  svg.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.dataset?.key) select(e.target.dataset.key); });
  $('#pl-fit').addEventListener('click', () => fit(true));
  $('#pl-layers-btn').addEventListener('click', () => {
    const p = $('#pl-layers'); p.hidden = !p.hidden; $('#pl-layers-btn').classList.toggle('on', !p.hidden); $('#pl-layers-btn').setAttribute('aria-expanded', String(!p.hidden));
  });
  $('#pl-measure').addEventListener('click', toggleMeasure);
  $('#pl-color').addEventListener('change', (e) => { state.colorMode = e.target.value; colorPiles(); });
  $('#pl-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') search(e.target.value); });
  $('#pl-q').addEventListener('search', (e) => search(e.target.value));
  $('#pl-grip').addEventListener('click', () => $('#pl-panel').classList.toggle('big'));
  $('#pl-card').addEventListener('click', (e) => {
    const k = e.target.closest('[data-go]')?.dataset.go; if (k) { select(k, true); return; }
    if (e.target.closest('[data-close]')) select(null);
  });
  window.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'Escape') { if (state.measure) toggleMeasure(); else select(null); }
    if (e.key === 'f' || e.key === 'F') fit(true);
    if (e.key === '+' || e.key === '=') $('#pl-zin').click();
    if (e.key === '-') $('#pl-zout').click();
    if (e.key === 'm' || e.key === 'M') toggleMeasure();
  });
  window.addEventListener('hashchange', fromHash);
}

function keyOf(target) { return target?.closest?.('.el')?.dataset.key || null; }
function hover(e) {
  const k = keyOf(e.target), tip = $('#pl-tip');
  if (!k || state.measure) { tip.hidden = true; return; }
  const r = $('#pl-main').getBoundingClientRect();
  tip.textContent = shortLabel(k); tip.hidden = false;
  tip.style.left = (e.clientX - r.left) + 'px'; tip.style.top = (e.clientY - r.top) + 'px';
  tip.style.transform = `translate(${e.clientX - r.left > r.width / 2 ? '0' : '-100%'}, -130%)`;
}
function shortLabel(k) {
  const [t, id] = k.split(':');
  if (t === 'pile') { const p = state.piles[id]; return `כלונס ${id} · ø${Math.round(p.diameter_m * 100)} · L=${p.length_m} · ראש ${f2(p.headRel)}`; }
  if (t === 'beam') { const b = state.beams[id]; return `קורה ${id} · ${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)} · ${n2(b.length_m)} מ'`; }
  if (t === 'wall') return `קיר מרתף ${id}`;
  if (t === 'footing') return `יסוד חומה ${id}`;
  return `ראש כלונס כפול ${id}`;
}
function click(e, target) {
  if (state.measure) { measureClick(svgPoint(e)); return; }
  select(keyOf(target));
}
function search(q) {
  q = (q || '').trim().toUpperCase(); if (!q) return;
  const k = state.piles[q] ? 'pile:' + q : state.beams[q] ? 'beam:' + q : state.beams['B-' + q] ? 'beam:B-' + q :
    [...state.els.keys()].find((x) => x.split(':')[1].toUpperCase() === q);
  if (k) select(k, true); else { $('#pl-status').textContent = `לא נמצא "${q}" – אפשר לחפש מספר כלונס (12, 6A) או קורה (B-39)`; }
}

/* ---------- selection ---------- */
function select(key, center) {
  for (const a of state.world.querySelectorAll('.el.sel, .el.hl')) a.classList.remove('sel', 'hl');
  state.world.querySelector('.halo')?.remove();
  state.sel = key;
  if (!key) { renderSummary(); setHash(''); return; }
  const a = state.els.get(key); if (!a) return;
  a.classList.add('sel');
  const [t, id] = key.split(':');
  const rel = related(t, id);
  for (const k of rel) state.els.get(k)?.classList.add('hl');
  const bb = a.getBBox();
  el('rect', { x: bb.x - 8, y: bb.y - 8, width: bb.width + 16, height: bb.height + 16, rx: 6, class: 'halo' }, state.world);
  if (center) centerOn(bb.x + bb.width / 2, bb.y + bb.height / 2);
  renderCard(t, id);
  setHash(key.replace(':', '-'));
  $('#pl-panel').scrollTop = 0;
}
function related(t, id) {
  if (t === 'pile') { const p = state.piles[id]; return [...p.beams.map((b) => 'beam:' + b), ...p.walls.map((w) => 'wall:' + w), ...p.footings.map((f) => 'footing:' + f)]; }
  if (t === 'beam') return state.beams[id].piles.map((q) => 'pile:' + q.id);
  if (t === 'wall') return state.data.piles.filter((p) => p.walls.includes(id)).map((p) => 'pile:' + p.id);
  if (t === 'footing') return (state.data.footings.find((f) => f.id === id)?.piles || []).map((q) => 'pile:' + q);
  if (t === 'cap') return (state.data.pileCaps.find((c) => c.id === id)?.piles || []).map((q) => 'pile:' + q);
  return [];
}
function setHash(h) {
  const want = h ? '#' + h.replace(/[^A-Za-z0-9-]/g, '') : '';
  if (location.hash !== want) history.replaceState(null, '', want || location.pathname + location.search);
}
function fromHash() {
  const h = location.hash.slice(1); if (!h) { renderSummary(); return; }
  const m = h.match(/^(pile|beam|wall|footing|cap)-(.+)$/);
  if (m) select(m[1] + ':' + m[2], true); else renderSummary();
}

/* ---------- cards ---------- */
const go = (k, txt) => `<button type="button" data-go="${esc(k)}">${esc(txt)}</button>`;
const kv = (rows) => `<dl class="kv">${rows.filter(Boolean).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
const head = (kind, title, chips) => `<div class="c-head"><div><div class="kind">${kind}</div><h2>${esc(title)}</h2></div><button class="x" type="button" data-close aria-label="סגירה">✕</button></div>` +
  (chips?.length ? `<div class="chips">${chips.join('')}</div>` : '');

function rebarTable(rows, note) {
  if (!rows?.length) return '<p class="note">אין נתוני ברזל לאלמנט הזה במקורות.</p>';
  let tot = 0, totM = 0; const byDia = {};
  const body = rows.map((r) => {
    if (r.kg == null) return `<tr><td colspan="6">${esc(r.desc)}<small>${esc(r.src)} · לא מפורט בגיליון – בכתב הכמויות לפי יחס ק"ג/מ"ק (הערכה)</small></td></tr>`;
    const ro = role(r.desc); tot += r.kg; totM += r.total_m; byDia[r.dia] = (byDia[r.dia] || 0) + r.kg;
    const est = r.status === 'provisional' ? '<span class="est" title="כולל הנחה שלא כתובה בגיליון">הערכה</span>' : '';
    return `<tr><td><span class="swb" style="background:${col(ro)}"></span><b>${ROLE_HE[ro][0]}</b>${est}<small>${esc(r.desc)}</small></td>` +
      `<td class="n">${n0(r.count)}</td><td class="n">${r.dia}</td><td class="n">${n2(r.length_m)}</td><td class="n">${n1(r.total_m)}</td><td class="n">${n1(r.kg)}</td></tr>`;
  }).join('');
  const dias = Object.entries(byDia).sort((a, b) => b[0] - a[0]).map(([d, kg]) => `ø${d}: ${n1(kg)} ק"ג`).join(' · ');
  return `<div class="tbl-wrap"><table class="rb"><thead><tr><th>סוג</th><th>כמות</th><th>קוטר מ"מ</th><th>אורך יח' מ'</th><th>סה"כ מ'</th><th>ק"ג</th></tr></thead><tbody>${body}` +
    `<tr class="tot"><td>סה"כ ברזל</td><td></td><td></td><td></td><td class="n">${n1(totM)}</td><td class="n">${n1(tot)}</td></tr></tbody></table></div>` +
    (dias ? `<p class="note">לפי קוטר: ${dias}</p>` : '') + (note ? `<p class="note">${note}</p>` : '');
}
function roleLegend(rows) {
  const used = [...new Set(rows.filter((r) => r.kg != null).map((r) => role(r.desc)))];
  return `<dl class="kv">${used.map((ro) => `<dt><span class="swb" style="display:inline-block;width:14px;height:4px;border-radius:2px;background:${col(ro)}"></span> ${ROLE_HE[ro][0]}</dt><dd style="font-family:inherit">${ROLE_HE[ro][1]}</dd>`).join('')}</dl>`;
}
const kgSum = (rows) => rows.reduce((s, r) => s + (r.kg || 0), 0);
const srcLine = (s) => `<p class="src">מקור: ${esc(s)}</p>`;

function renderCard(t, id) {
  const box = $('#pl-card'), d = state.data, H0 = d.H0;
  if (t === 'pile') {
    const p = state.piles[id], det = d.pileDetail, beam = p.beams.length ? state.beams[p.beams[0]] : null;
    const chips = [`<span class="chip">${ZONE[p.zone] || p.zone}</span>`, `<span class="chip">ø${Math.round(p.diameter_m * 100)} · L=${p.length_m}</span>`];
    if (p.overAllowed) chips.push('<span class="chip warn">מעל העומס המותר – לבדיקה מול הקונסטרוקטור</span>');
    if (p.xlsxCheck?.match) chips.push('<span class="chip ok">תואם לטבלת הכלונסאות</span>');
    const tb = p.table || {};
    box.innerHTML = head('כלונס', 'כלונס ' + p.id, chips) +
      `<div class="plain">עמוד בטון עגול שיוצקים בתוך קידוח באדמה. <b>קוטר ${Math.round(p.diameter_m * 100)} ס"מ, אורך ${p.length_m} מ'</b>. ` +
      `הראש שלו במפלס <b class="num">${f2(p.headRel)}</b> (${(H0 + p.headRel).toFixed(2)} מעל פני הים) והתחתית במפלס <b class="num">${f2(p.tipRel)}</b>. ` +
      `הוא מתוכנן לשאת <b>${p.designLoad_t} טון</b>. בתוכו כלוב ברזל של ${det.longBars[String(p.diameter_m)]} מוטות ø16 שעטוף בספירלה ø8.</div>` +
      `<div class="sec"><h3>איך הוא נראה</h3><div class="sketches"><figure class="sk">${pileElevation(p, det, beam, H0)}<figcaption>מבט צד (הרוחב מוגדל לשם ההמחשה)</figcaption></figure>` +
      `<figure class="sk">${pileSection(p, det)}<figcaption>חתך רוחב A-A</figcaption></figure></div></div>` +
      `<div class="sec"><h3>מה הברזל בתוכו</h3>${roleLegend(p.rebar)}</div>` +
      `<div class="sec"><h3>כמויות ברזל</h3>${rebarTable(p.rebar, 'אותו חישוב של כתב הכמויות. "הערכה" = אורך העיגון בקורה והקטע הצפוף של הספירלה לא כתובים בגיליון.')}</div>` +
      `<div class="sec"><h3>מידות ומפלסים</h3>${kv([
        ['קוטר', `${Math.round(p.diameter_m * 100)} ס"מ`], ['אורך (בקרקע טבעית)', `${p.length_m.toFixed(2)} מ'`],
        ['מפלס ראש', `${f2(p.headRel)} · ${(H0 + p.headRel).toFixed(2)}`], ['מפלס תחתית', `${f2(p.tipRel)} · ${(H0 + p.tipRel).toFixed(2)}`],
        ['עומס תכנון', `${p.designLoad_t} טון`], p.xlsxCheck ? ['עומס מותר (xlsx)', `${p.xlsxCheck.allowed} טון`] : null,
        ['נפח בטון', `${n2(p.volume_m3)} מ"ק (ב-30)`], ['מיקום ITM', `E ${p.E.toFixed(3)} · N ${p.N.toFixed(3)}`],
      ])}</div>` +
      `<div class="sec"><h3>מחובר אל</h3><div class="links">${[...p.beams.map((b) => go('beam:' + b, b)), ...p.walls.map((w) => go('wall:' + w, 'קיר ' + w)), ...p.footings.map((f) => go('footing:' + f, 'יסוד ' + f))].join('') || '<span class="note">לא שויך לקורה או לקיר בתוכנית הזו</span>'}</div></div>` +
      `<div class="sec"><h3>השורה בטבלת הכלונסאות (K-400)</h3>${kv(d.pileTableColumns.filter((c) => c.key !== 'id').map((c) => [esc(c.label), esc(tb[c.key] ?? '—')]))}` +
      `<p class="note warn">שימו לב: בטבלה הכותרות "זיון כלונס" ו"קוצים לעמודים" נראות מוחלפות. ${det.longBars[String(p.diameter_m)]}Φ16 תואם את חתך A-A (זיון הכלונס). לבירור מול הקונסטרוקטור.</p></div>` +
      `<p class="note">${esc(p.tipNote || '')}</p>` + srcLine(p.source);
  } else if (t === 'beam') {
    const b = state.beams[id];
    const tie = b.rebar.find((r) => role(r.desc) === 'tie');
    const sp = tie && (tie.desc.match(/@(\d+)/) || [])[1];
    const chips = [`<span class="chip">${LAYER_HE[b.layer] || b.sheet}</span>`, `<span class="chip">${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)}</span>`];
    if (b.status !== 'source') chips.push('<span class="chip warn">מיקום בקירוב</span>');
    box.innerHTML = head('קורה', 'קורה ' + b.id, chips) +
      `<div class="plain">"גשר" של בטון מזוין שמחבר בין ראשי הכלונסאות ונושא את הרצפה והקירות שמעליו. ` +
      `<b>רוחב ${Math.round(b.width_m * 100)} ס"מ, גובה ${Math.round(b.depth_m * 100)} ס"מ, אורך ${n2(b.length_m)} מ'</b>. ` +
      `הפנים העליונות במפלס <b class="num">${f2(b.topRel)}</b> והתחתונות במפלס <b class="num">${f2(b.bottomRel)}</b>. ` +
      (b.piles.length ? `יושבת על ${b.piles.length === 1 ? 'כלונס' : b.piles.length + ' כלונסאות'}: ${b.piles.map((q) => q.id).join(', ')}.` : 'לא נמצא כלונס ישירות מתחתיה בתוכנית.') + `</div>` +
      `<div class="sec"><h3>איך היא נראית</h3><div class="sketches wide"><figure class="sk">${beamSection(b, d.beamCover_m.value)}<figcaption>חתך רוחב (ס"מ)</figcaption></figure>` +
      `<figure class="sk">${beamElevation(b, state.piles, sp ? sp / 100 : null)}<figcaption>מבט צד + הכלונסאות שמתחת (סכמטי)</figcaption></figure></div></div>` +
      `<div class="sec"><h3>מה הברזל בתוכה</h3>${roleLegend(b.rebar)}</div>` +
      `<div class="sec"><h3>כמויות ברזל</h3>${rebarTable(b.rebar, b.rebarSheet ? `מתוך ${b.rebarSheet} (פריסת ברזל קורות). כמות החישוקים = אורך הקורה ÷ הפסיעה.` : '')}</div>` +
      `<div class="sec"><h3>מידות</h3>${kv([['רוחב × גובה', `${Math.round(b.width_m * 100)} × ${Math.round(b.depth_m * 100)} ס"מ`], ['אורך (ציר)', `${n2(b.length_m)} מ'`],
        ['מפלס עליון O.K', `${f2(b.topRel)} · ${(H0 + b.topRel).toFixed(2)}`], ['מפלס תחתון', `${f2(b.bottomRel)} · ${(H0 + b.bottomRel).toFixed(2)}`],
        ['נפח בטון', `${n2(b.volume_m3)} מ"ק`], ['כיסוי בטון', `${d.beamCover_m.value * 100} ס"מ`]])}</div>` +
      (b.section ? `<div class="sec"><h3>מה כתוב בחתך בגיליון</h3><p class="num note">${esc(b.section.texts.join(' · ')).replace(/ï/g, 'ø')}</p></div>` : '') +
      `<div class="sec"><h3>כלונסאות מתחת</h3><div class="links">${b.piles.map((q) => go('pile:' + q.id, q.id)).join('') || '<span class="note">—</span>'}</div></div>` +
      srcLine(b.source + ' · ' + (b.geometrySource || ''));
  } else if (t === 'wall') {
    const w = d.basementWalls.find((x) => x.id === id);
    const ps = d.piles.filter((p) => p.walls.includes(id));
    box.innerHTML = head('קיר בטון – מרתף', 'קיר ' + w.id, [`<span class="chip">${f2(w.bottomRel)} עד ${f2(w.topRel)}</span>`, w.status !== 'source' ? '<span class="chip warn">זמני</span>' : '']) +
      `<div class="plain">קיר בטון מזוין שעוטף את המרתף ומחזיק את האדמה מבחוץ. <b>גובה ${n2(w.topRel - w.bottomRel)} מ'</b> – מראשי הכלונסאות (${f2(w.bottomRel)}) עד תחתית תקרת הקרקע (${f2(w.topRel)}). ` +
      `שטח טביעת הרגל ${n2(w.area_m2)} מ"ר${w.openings?.length ? `, פתחים: ${w.openings.join(', ')}` : ''}.</div>` +
      `<div class="sec"><h3>כמויות ברזל</h3>${rebarTable(w.rebar)}</div>` +
      `<div class="sec"><h3>כלונסאות מתחת</h3><div class="links">${ps.map((p) => go('pile:' + p.id, p.id)).join('') || '<span class="note">—</span>'}</div></div>` +
      `<p class="note">${esc(w.note || '')}</p>` + srcLine(w.source);
  } else if (t === 'footing') {
    const f = d.footings.find((x) => x.id === id), s = d.perimeterSection;
    box.innerHTML = head('יסוד חומה היקפית', 'יסוד ' + f.id, [`<span class="chip">רוחב ${Math.round(f.width_m * 100)} · עובי ${Math.round(f.thickness_m * 100)}</span>`]) +
      `<div class="plain">רצועת בטון לאורך גבול המגרש שעליה עומדת החומה. היא יושבת על הכלונסאות ${f.piles.join(', ')}. ` +
      `<b>רוחב ${Math.round(f.width_m * 100)} ס"מ, עובי ${Math.round(f.thickness_m * 100)} ס"מ</b>, תחתית ${f2(f.bottomRel)}, ראש ${f2(f.topRel)}.</div>` +
      `<div class="sec"><h3>כמויות ברזל</h3>${rebarTable(f.rebar)}</div>` +
      `<div class="sec"><h3>חתך החומה (K-400)</h3>${kv([['B', s.B_m], ['b', s.b_m], ['a', s.a_m], ['h', s.h_m], ['שורת הטבלה', esc(s.tableRow)]])}</div>` +
      `<div class="sec"><h3>כלונסאות</h3><div class="links">${f.piles.map((q) => go('pile:' + q, q)).join('')}</div></div>` + srcLine(f.source);
  } else if (t === 'cap') {
    const c = d.pileCaps.find((x) => x.id === id);
    box.innerHTML = head('ראש כלונס כפול', c.id, [`<span class="chip">${c.size_m.map((v) => n2(v)).join(' × ')} מ'</span>`]) +
      `<div class="plain">גוש בטון שמחבר שני כלונסאות צמודים (${c.piles.join(' + ')}) לנקודת סמך אחת. <b>${c.size_m.map((v) => Math.round(v * 100)).join('×')} ס"מ, גובה ${Math.round(c.depth_m * 100)} ס"מ</b>, ראש ${f2(c.topRel)}.</div>` +
      `<div class="sec"><h3>מה הברזל בתוכו</h3>${roleLegend(c.rebar)}</div>` +
      `<div class="sec"><h3>כמויות ברזל</h3>${rebarTable(c.rebar)}</div>` +
      `<div class="sec"><h3>כלונסאות</h3><div class="links">${c.piles.map((q) => go('pile:' + q, q)).join('')}</div></div>` + `<p class="note">${esc(c.note || '')}</p>` + srcLine(c.source);
  }
}

function renderSummary() {
  const d = state.data, ps = d.piles, bs = d.beams;
  const pk = ps.reduce((s, p) => s + kgSum(p.rebar), 0), bk = bs.reduce((s, b) => s + kgSum(b.rebar), 0);
  const ck = d.pileCaps.reduce((s, c) => s + kgSum(c.rebar), 0);
  const pl = ps.reduce((s, p) => s + p.length_m, 0), pv = ps.reduce((s, p) => s + p.volume_m3, 0), bv = bs.reduce((s, b) => s + b.volume_m3, 0);
  const byDia = (dd) => ps.filter((p) => p.diameter_m === dd);
  $('#pl-card').innerHTML =
    `<div class="c-head"><div><div class="kind">גיליון</div><h2>K-400 · תכנית יסודות וכלונסאות</h2></div></div>` +
    `<div class="plain">התוכנית <b>חיה</b>: לוחצים על כלונס, קורה, קיר או יסוד ומקבלים את כל המידע עליו – מידות, מפלסים, סקיצה ופירוט הברזל. החיפוש למעלה מוצא לפי מספר.</div>` +
    `<div class="tiles"><div class="tile"><div class="v">${ps.length}</div><div class="l">כלונסאות (ø50: ${byDia(0.5).length} · ø60: ${byDia(0.6).length})</div></div>` +
    `<div class="tile"><div class="v">${n0(pl)} מ'</div><div class="l">אורך קידוח כולל</div></div>` +
    `<div class="tile"><div class="v">${n1(pv)} מ"ק</div><div class="l">בטון כלונסאות</div></div>` +
    `<div class="tile"><div class="v">${n0(pk)} ק"ג</div><div class="l">ברזל כלונסאות</div></div>` +
    `<div class="tile"><div class="v">${bs.length}</div><div class="l">קורות (${n1(bs.reduce((s, b) => s + b.length_m, 0))} מ')</div></div>` +
    `<div class="tile"><div class="v">${n0(bk + ck)} ק"ג</div><div class="l">ברזל קורות + ראש כפול · ${n1(bv)} מ"ק בטון</div></div></div>` +
    `<div class="sec"><h3>כלונסאות</h3><div class="list">${ps.map((p) => go('pile:' + p.id, p.id)).join('')}</div></div>` +
    `<div class="sec"><h3>קורות</h3><div class="list">${bs.map((b) => go('beam:' + b.id, b.id)).join('')}</div></div>` +
    `<div class="sec"><h3>דרישות הגיליון</h3><p class="note">${esc(d.requirements)}</p></div>` +
    `<details class="glossary"><summary>מילון מונחים לשרטוט</summary><dl>` +
    `<dt>ø12</dt><dd>מוט ברזל בקוטר 12 מ"מ</dd><dt>@15</dt><dd>כל 15 ס"מ (מרווח בין מוטות / חישוקים)</dd>` +
    `<dt>L=310</dt><dd>אורך המוט: 310 ס"מ</dd><dt>ב.ת / ב.ע</dt><dd>ברזל תחתון / ברזל עליון</dd>` +
    `<dt>O.K</dt><dd>מפלס עליון (פני הבטון העליונים)</dd><dt>±0.00</dt><dd>מפלס הכניסה של הבית = ${d.H0.toFixed(2)} מעל פני הים</dd>` +
    `<dt>25/60</dt><dd>רוחב 25 ס"מ, גובה 60 ס"מ</dd><dt>N= 22 ton</dt><dd>העומס שהכלונס מתוכנן לשאת</dd>` +
    `<dt>חישוק לוליני</dt><dd>ספירלה – "קפיץ" ברזל שעוטף את מוטות הכלונס</dd><dt>כיסוי</dt><dd>שכבת הבטון שמגינה על הברזל מבחוץ</dd></dl></details>` +
    srcLine(state.sheet.source + ' · ' + d._doc);
}

/* ---------- measuring ---------- */
function toggleMeasure() {
  state.measure = state.measure ? null : { pts: [] };
  $('#pl-measure').classList.toggle('on', !!state.measure); $('#pl-svg').classList.toggle('measure', !!state.measure);
  state.mLayer.innerHTML = ''; $('#pl-measure-out').hidden = !state.measure;
  $('#pl-measure-out').textContent = 'לחיצה על נקודה ראשונה…';
}
function measureClick(pt) {
  const m = state.measure; if (m.pts.length === 2) { m.pts = []; state.mLayer.innerHTML = ''; }
  m.pts.push(pt); el('circle', { cx: pt[0], cy: pt[1], r: 4, class: 'mdot' }, state.mLayer);
  if (m.pts.length === 2) {
    const [a, b] = m.pts; const dist = Math.hypot(b[0] - a[0], b[1] - a[1]) / G.ptPerM;
    el('line', { x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: 'mline' }, state.mLayer);
    el('text', { x: (a[0] + b[0]) / 2, y: (a[1] + b[1]) / 2 - 6, class: 'mtxt', 'text-anchor': 'middle' }, state.mLayer).textContent = dist.toFixed(3) + " מ'";
    $('#pl-measure-out').textContent = `מרחק: ${dist.toFixed(3)} מ'`;
  } else $('#pl-measure-out').textContent = 'לחיצה על נקודה שנייה…';
}

boot().catch((e) => { $('#pl-loading').textContent = 'שגיאה בטעינת התוכנית: ' + e.message; console.error(e); });

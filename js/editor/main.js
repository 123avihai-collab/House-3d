// 2D pipe editor – stage 1: plan view per floor in the house axes, architect background (consultant DXF), structure for
// clash checks, pipe layers (proposal = data/plumbing/routes.json, consultant = network.json read only), show / hide /
// lock, grid + snap, pick → info card. Editing, saving and the 3D link come in stages 2–4 (docs/plumbing/editor.md).
import { View, bboxOf } from './view.js';
import { loadEditorData, buildModel, systemsOf } from './model.js';
import { drawGrid, drawBackground, drawStructure, drawPipes, drawNodes, drawSnap } from './draw.js';
import { snapPoint, hitTest } from './pick.js';
import { Layers, buildPanel } from './layers.js';

const $ = (id) => document.getElementById(id);
window.__editorErrors = [];
window.addEventListener('error', e => window.__editorErrors.push(String(e.message)));

const fmtRel = (r) => r == null ? '–' : `${r >= 0 ? '+' : '−'}${Math.abs(r).toFixed(2)}`;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function start() {
  const D = await loadEditorData();
  const cfg = D.planEditor, M = buildModel(D), sys = systemsOf(D);
  const defaults = { 'cons.superseded': false, nodes: true, grid: true };
  for (const [k, st] of Object.entries(cfg.background)) defaults['bg.' + k] = st.on;
  for (const [k, st] of Object.entries(cfg.structure)) defaults['st.' + k] = st.on;
  const L = new Layers(defaults);
  const canvas = $('ed-canvas'), ctx = canvas.getContext('2d'), v = new View(canvas, cfg);
  const S = { floor: new URLSearchParams(location.search).get('floor') || cfg.defaultFloor, sel: null, hover: null, snap: null, snapOn: true, step: cfg.snap.defaultStep_m };
  if (!M.floors[S.floor]) S.floor = cfg.defaultFloor;

  // ---- what is on the current floor
  const itemsOf = (fid) => {
    const F = M.floors[fid], out = [];
    for (const p of M.pipes) { const mode = M.showsOn(p, fid); if (mode) out.push({ p, mode, band: F.band }); }
    return out;
  };
  const nodesOf = (fid) => M.nodes.filter(n => n.floor === fid || (M.floors[fid].cfg.alsoRuns || []).includes(n.floor));
  const visibleItems = () => cur.items.filter(it => L.on(it.p.layer + '.' + it.p.system) && (it.p.layer !== 'cons' || !it.p.superseded || L.on('cons.superseded')));
  let cur;
  const setFloor = (fid, fit = true) => {
    S.floor = fid; S.sel = null; hideInfo();
    cur = { F: M.floors[fid], items: itemsOf(fid), nodes: nodesOf(fid) };
    for (const b of $('ed-floors').children) b.classList.toggle('on', b.dataset.floor === fid);
    const counts = {};
    for (const it of cur.items) { const k = it.p.layer + '.' + it.p.system; if (!it.p.superseded) counts[k] = (counts[k] || 0) + 1; }
    for (const [k, list] of Object.entries(cur.F.structure)) counts['st.' + k] = list.length || null;
    for (const [k, list] of Object.entries(cur.F.background)) counts['bg.' + k] = list.length || null;
    counts.nodes = cur.nodes.length; counts['cons.superseded'] = cur.items.filter(it => it.p.superseded).length;
    buildPanel($('ed-panel'), L, cfg, sys, counts);
    if (fit) fitFloor();
    try { history.replaceState(null, '', `?floor=${fid}`); } catch { /* sandboxed */ }
    redraw();
  };
  const fitFloor = () => {
    const F = cur.F, polys = [...F.structure.concreteWalls, ...F.structure.blocks, ...F.structure.columns].map(e => e.poly);
    v.fit(bboxOf(polys.length ? polys : F.background.walls));
  };

  // ---- floor tabs, snap controls
  for (const [i, f] of cfg.floors.entries()) {
    const b = Object.assign(document.createElement('button'), { textContent: f.label, onclick: () => setFloor(f.id), title: `${f.label} (${i + 1})` });
    b.dataset.floor = f.id; $('ed-floors').append(b);
  }
  const stepSel = $('ed-snap-step');
  for (const s of cfg.snap.steps_m) stepSel.append(new Option(`רשת ${s >= 0.1 ? s.toFixed(1) : (s * 100).toFixed(0) + ' ס"מ'}${s >= 0.1 ? ' מ\'' : ''}`, s, false, s === S.step));
  stepSel.onchange = () => { S.step = +stepSel.value; };
  $('ed-snap-on').onchange = (e) => { S.snapOn = e.target.checked; S.snap = null; redraw(); };
  $('ed-fit').onclick = () => { fitFloor(); redraw(); };
  $('ed-layers-btn').onclick = () => document.body.classList.toggle('panel-open');
  L.onChange(() => { setFloor(S.floor, false); });

  // ---- rendering
  let raf = 0;
  function redraw() { if (!raf) raf = requestAnimationFrame(paint); }
  function paint() {
    raf = 0; ctx.setTransform(v.dpr, 0, 0, v.dpr, 0, 0); ctx.clearRect(0, 0, v.w, v.h);
    const on = (k) => L.on(k);
    if (on('grid')) drawGrid(ctx, v, cfg);
    drawBackground(ctx, v, cfg, cur.F.background, on);
    drawStructure(ctx, v, cfg, cur.F.structure, on);
    const items = visibleItems();
    drawPipes(ctx, v, cfg, items, sys, S.sel?.type === 'pipe' ? S.sel.obj : null, S.hover?.type === 'pipe' ? S.hover.obj : null);
    if (on('nodes')) drawNodes(ctx, v, cfg, cur.nodes, S.sel?.type === 'node' ? S.sel.obj : null, S.hover?.type === 'node' ? S.hover.obj : null);
    drawSnap(ctx, v, S.snap);
    // compass (true north = grid north + convergence, data/site/origin.json) and scale bar
    const a = M.frame.gridNorthAngle() + (D.origin.trueNorthGridAzimuth_deg || 0) * Math.PI / 180;
    $('ed-compass').style.transform = `rotate(${a}rad)`;
    const target = 120 / v.k, pow = Math.pow(10, Math.floor(Math.log10(target))), nice = [1, 2, 5, 10].map(m => m * pow).find(m => m >= target * 0.6) || pow;
    $('ed-scale').style.width = `${nice * v.k}px`; $('ed-scale').textContent = `${nice >= 1 ? nice : nice.toFixed(2)} מ'`;
    window.__editorPaints = (window.__editorPaints || 0) + 1;
  }
  const resize = () => { v.resize(); redraw(); };
  new ResizeObserver(resize).observe(canvas);

  // ---- info card
  function hideInfo() { $('ed-info').classList.add('hidden'); }
  function showInfo(hit) {
    const rows = []; let title, color = null, src, warn = null;
    if (hit.type === 'node') {
      const n = hit.obj; title = `${n.id} – ${n.title || n.kind}`; src = n.source;
      rows.push(['סוג', n.kind], ['קומה', n.floor], ['גובה', n.H != null ? `${n.H.toFixed(2)} (${fmtRel(n.H - M.H0)})` : '–'], ['ITM', `E ${n.E.toFixed(3)} · N ${n.N.toFixed(3)}`]);
      if (n.D_mm) rows.push(['קוטר', `ø${n.D_mm}`]);
      if (n.cold != null) rows.push(['מים', [n.cold && 'קרים', n.hot && 'חמים'].filter(Boolean).join(' + ') || '–']);
      rows.push(['סטטוס', n.status]);
    } else {
      const p = hit.obj, r = p.ref; color = (sys[p.system] || {}).color; title = `${p.id} – ${(sys[p.system] || {}).label || p.system}`;
      const plan = p.pts.reduce((s, q, i) => i ? s + Math.hypot(q[0] - p.pts[i - 1][0], q[1] - p.pts[i - 1][1]) : 0, 0);
      rows.push(['שכבה', p.layer === 'prop' ? 'הצעה (routes.json)' : 'תוכנית היועץ – קריאה בלבד']);
      if (r.D_mm) rows.push(['קוטר / חומר', `ø${r.D_mm}${r.material ? ' · ' + r.material : ''}`]);
      if (r.from || r.to) rows.push(['מ → אל', `${r.from || '?'} → ${r.to || '?'}`]);
      rows.push(['קומה', p.floor === 'multi' ? (p.floors || []).join(', ') : p.floor]);
      rows.push(['אורך במבט על', `${plan.toFixed(2)} מ'`]);
      if (r.length_m != null) rows.push(['אורך (3D)', `${r.length_m.toFixed(2)} מ'`]);
      const Hs = (p.H || []).filter(x => x != null);
      if (Hs.length) rows.push(['מפלס', `${fmtRel(Math.min(...Hs) - M.H0)} … ${fmtRel(Math.max(...Hs) - M.H0)}`]);
      if (r.ILup != null) rows.push(['I.L', `${r.ILup.toFixed(2)} → ${r.ILdown.toFixed(2)}`]);
      if (r.slope != null) rows.push(['שיפוע', `${(r.slope * 100).toFixed(1)}%`]);
      if (r.insulation_mm) rows.push(['בידוד', `${r.insulation_mm} מ"מ`]);
      if (r.simplify) rows.push(['נקודות פנייה', `${r.simplify.ptsAfter} (מתוך ${r.simplify.ptsBefore}, סטייה ≤ ${(r.simplify.maxDev_m * 1000).toFixed(0)} מ"מ)`]);
      rows.push(['סטטוס', r.status || r.levelStatus || '–']);
      if (p.superseded) warn = 'ההצעה מחליפה קו זה';
      if (r.levelStatus && r.levelStatus !== 'source') warn = (warn ? warn + ' · ' : '') + `מפלס: ${r.levelStatus}`;
      src = r.source;
    }
    $('ed-info').innerHTML = `<button class="x" aria-label="סגירה">✕</button><h3>${color ? `<span class="sw" style="background:${color}"></span>` : ''}${esc(title)}</h3>
      <table>${rows.map(([a, b]) => `<tr><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')}</table>
      ${warn ? `<div class="warn">⚠ ${esc(warn)}</div>` : ''}<div class="src">מקור: ${esc(src)}</div>`;
    $('ed-info').querySelector('.x').onclick = () => { S.sel = null; hideInfo(); redraw(); };
    $('ed-info').classList.remove('hidden');
  }

  // ---- pointer: pan (drag / two fingers), zoom (wheel / pinch), hover snap, tap = pick
  const pts = new Map(); let drag = null, pinch = null, moved = 0;
  const local = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  const status = (s, px) => {
    const [E, N] = M.frame.toITM(s.x, s.y);
    const kind = { grid: 'רשת', vertex: 'פינה', edge: 'על קו', node: 'נקודה', free: '' }[s.kind];
    $('ed-status').textContent = `x ${s.x.toFixed(3)}  y ${s.y.toFixed(3)} (צירי הבית) · E ${E.toFixed(3)}  N ${N.toFixed(3)}${kind ? ' · הצמדה: ' + kind : ''}`;
  };
  canvas.addEventListener('pointerdown', (e) => {
    canvas.setPointerCapture(e.pointerId); pts.set(e.pointerId, local(e)); moved = 0;
    if (pts.size === 1) drag = { p: local(e) };
    if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), m: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] }; drag = null; }
  });
  canvas.addEventListener('pointermove', (e) => {
    const p = local(e);
    if (pts.has(e.pointerId)) pts.set(e.pointerId, p);
    if (pinch && pts.size === 2) {
      const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]), m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      v.pan(m[0] - pinch.m[0], m[1] - pinch.m[1]); v.zoomAt(m[0], m[1], d / pinch.d); pinch = { d, m }; moved += 10; redraw(); return;
    }
    if (drag) { const dx = p[0] - drag.p[0], dy = p[1] - drag.p[1]; moved += Math.abs(dx) + Math.abs(dy); v.pan(dx, dy); drag.p = p; redraw(); return; }
    const [x, y] = v.toLocal(...p), r = cfg.snap.radius_px / v.k;
    S.snap = S.snapOn ? snapPoint(x, y, r, { step: S.step }, cur.F, visibleItems(), L.on('nodes') ? cur.nodes : [], (k) => L.on(k)) : { kind: 'free', x, y };
    status(S.snap, p);
    S.hover = hitTest(x, y, r, visibleItems(), L.on('nodes') ? cur.nodes : [], (k) => L.locked(k));
    canvas.style.cursor = S.hover ? 'pointer' : 'crosshair';
    redraw();
  });
  const up = (e) => {
    const p = pts.get(e.pointerId); pts.delete(e.pointerId);
    if (pts.size < 2) pinch = null;
    if (pts.size === 0) {
      if (drag && moved < 6 && p) {
        const [x, y] = v.toLocal(...p), r = (cfg.snap.radius_px * (e.pointerType === 'touch' ? 1.8 : 1)) / v.k;
        const hit = hitTest(x, y, r, visibleItems(), L.on('nodes') ? cur.nodes : [], (k) => L.locked(k));
        S.sel = hit; if (hit) showInfo(hit); else hideInfo(); redraw();
      }
      drag = null;
    }
  };
  canvas.addEventListener('pointerup', up); canvas.addEventListener('pointercancel', up);
  canvas.addEventListener('pointerleave', () => { S.snap = null; S.hover = null; redraw(); });
  canvas.addEventListener('wheel', (e) => { e.preventDefault(); const p = local(e); v.zoomAt(p[0], p[1], Math.exp(-e.deltaY * 0.0015)); redraw(); }, { passive: false });
  window.addEventListener('keydown', (e) => {
    if (e.target.closest('input,select,textarea')) return;
    if (e.key === 'f' || e.key === 'F') { fitFloor(); redraw(); }
    if (e.key === 's' || e.key === 'S') { $('ed-snap-on').click(); }
    if (e.key === 'Escape') { S.sel = null; hideInfo(); redraw(); }
    const i = ['1', '2', '3', '4'].indexOf(e.key); if (i >= 0 && cfg.floors[i]) setFloor(cfg.floors[i].id);
  });

  v.resize(); setFloor(S.floor);
  $('ed-loading').classList.add('hidden');
  // hooks for tests (tests/editor.mjs)
  window.__editor = { D, M, S, L, v, cfg, setFloor, current: () => cur, visibleItems, toScreen: (x, y) => [v.sx(x), v.sy(y)], showInfo };
  window.__editorReady = true;
}

start().catch(err => { console.error(err); window.__editorErrors.push(String(err)); $('ed-loading').textContent = 'שגיאה בטעינה: ' + err.message; });

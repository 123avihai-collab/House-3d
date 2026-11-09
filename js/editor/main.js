// 2D pipe editor (editor.html) – plan view per floor in the house axes; architect background; structure; proposal pipes
// (data/plumbing/routes.json + saved edits, editable) and consultant pipes (network.json, read only).
// Stage 2: properties, drag segment / corner (orthogonal), add / delete corner, straighten to the house axes, slope,
// new pipe, undo / redo, autosave (artifact db, else this browser), export routes.json. See docs/plumbing/editor.md.
import { View, bboxOf } from './view.js';
import { loadEditorData, buildModel, systemsOf } from './model.js';
import { drawGrid, drawBackground, drawStructure, drawPipes, drawNodes, drawSnap, drawHandles, drawDraft } from './draw.js';
import { snapPoint, hitTest } from './pick.js';
import { Layers, buildPanel } from './layers.js';
import { RouteStore } from './store.js';
import * as OP from './ops.js';
import { askConfirm } from '../core/dialog.js';
import { buildObstacles, checkRun, checkConnections } from './checks.js';
import { drawIssues, drawBadges, manifoldScreen, drawPoints } from './draw.js';

const $ = (id) => document.getElementById(id);
window.__editorErrors = [];
window.addEventListener('error', e => window.__editorErrors.push(String(e.message)));

const fmtRel = (r) => r == null ? '–' : `${r >= 0 ? '+' : '−'}${Math.abs(r).toFixed(2)}`;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const r3 = (v) => Math.round(v * 1000) / 1000;

async function start() {
  const D = await loadEditorData();
  const cfg = D.planEditor, E = cfg.edit, M = buildModel(D), sys = systemsOf(D), fr = M.frame;
  const store = new RouteStore(D.routes);
  // ---- live checks (stage 3): per run + connections, recomputed after every change, and for the dragged run live
  const CH = { fr, H0: M.H0, obstacles: buildObstacles(D, fr), cfg, cat: D.plumbingCatalog.pipes };
  let issues = { runs: {}, conn: [] };
  const recheck = () => { const runs = store.runs(), t0 = performance.now(); issues = { runs: Object.fromEntries(runs.map(r => [r.id, checkRun(r, CH)])), conn: checkConnections(runs, M.nodes, D.plumbing.nodes, CH, [...D.plumbing.runs, ...D.plumbing.lines3d]) }; window.__checkMs = performance.now() - t0; };
  recheck();
  M.setRuns(store.runs());
  const defaults = { 'cons.superseded': false, nodes: true, grid: true, cpoints: true, 'labels.points': true };
  for (const [k, st] of Object.entries(cfg.background)) defaults['bg.' + k] = st.on;
  for (const [k, st] of Object.entries(cfg.structure)) defaults['st.' + k] = st.on;
  const L = new Layers(defaults);
  const canvas = $('ed-canvas'), ctx = canvas.getContext('2d'), v = new View(canvas, cfg);
  const S = { floor: new URLSearchParams(location.search).get('floor') || cfg.defaultFloor, sel: null, hover: null, snap: null, snapOn: true,
    step: cfg.snap.defaultStep_m, ortho: true, mode: 'select', draft: null, preview: null };
  if (!M.floors[S.floor]) S.floor = cfg.defaultFloor;
  const opt = () => ({ ortho: S.ortho, axisEps_deg: E.axisEps_deg, orthoSimplify_m: E.orthoSimplify_m, minSeg_m: E.minSeg_m });
  const toast = (t) => { const el = $('ed-toast'); el.textContent = t; el.classList.remove('hidden'); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.add('hidden'), 2600); };

  // ---- what is on the current floor
  let cur;
  const itemsOf = (fid) => { const F = M.floors[fid], out = []; for (const p of M.pipes) { const mode = M.showsOn(p, fid); if (mode) out.push({ p, mode, band: F.band }); } return out; };
  const nodesOf = (fid) => M.nodes.filter(n => n.floor === fid || (M.floors[fid].cfg.alsoRuns || []).includes(n.floor));
  const cnodesOf = (fid) => M.consNodes.filter(n => n.floor === fid || (M.floors[fid].cfg.alsoRuns || []).includes(n.floor));
  const isFixtureOrManifold = (n) => n.kind === 'manifold' || (cfg.points.kinds[n.kind] || [])[0] === 'fixture';
  const pickNodes = () => [...(L.on('nodes') ? cur.nodes : []), ...(L.on('cpoints') ? cur.cnodes : [])];
  const kindName = (k) => (cfg.points.kinds[k] || [null, k])[1];
  // what a point connects to: consultant + proposal lines that name it, with the other end
  const pointLinks = (n) => {
    const out = [];
    for (const r of D.plumbing.runs) if (r.from === n.id || r.to === n.id) out.push({ id: r.id, sys: r.system, D: r.D_mm, mat: r.material, other: r.from === n.id ? r.to : r.from, dir: r.from === n.id ? 'יוצא אל' : 'נכנס מ', layer: 'יועץ', IL: r.ILup != null ? `${r.ILup.toFixed(2)}→${r.ILdown.toFixed(2)}` : null, superseded: D.routes.superseded.runs.includes(r.id) });
    for (const r of store.runs()) if (r.from === n.id || r.to === n.id) out.push({ id: r.id, sys: r.system, D: r.D_mm, mat: r.material, other: r.from === n.id ? r.to : r.from, dir: r.from === n.id ? 'יוצא אל' : 'נכנס מ', layer: 'הצעה' });
    return out;
  };
  const visibleItems = () => cur.items.filter(it => L.on(it.p.layer + '.' + it.p.system) && (it.p.layer !== 'cons' || !it.p.superseded || L.on('cons.superseded')));
  // edited only on the floor where it is drawn in plan (a riser passing through another floor is shown there, not edited)
  const editable = (p) => p && p.layer === 'prop' && store.canEdit && !L.locked('prop.' + p.system) && cur.items.some(it => it.mode === 'plan' && it.p.layer === 'prop' && it.p.id === p.id);
  const nodeEditable = (n) => n && n.layer !== 'cons' && store.canEdit && !L.locked('nodes');
  const nodeRuns = (n) => {   // proposal runs connected to the point (by name or by an end within connectTol)
    const P = n.xy, tol = cfg.checks.connectTol_m;
    const water = ['cold', 'hot', 'return'];   // a manifold pulls only water lines that end at it (risers in the shaft pass right by)
    return store.runs().filter(r => r.from === n.id || r.to === n.id || ((n.kind !== 'manifold' || water.includes(r.system)) && [r.vertices[0], r.vertices[r.vertices.length - 1]].some(v => { const q = fr.toLocal(v[0], v[1]); return Math.hypot(q[0] - P[0], q[1] - P[1]) <= tol; })));
  };
  const moveNode = (n, dx, dy) => OP.moveNodeSystem(n, nodeRuns(n), dx, dy, { fr, opt: opt(), zone: n.kind === 'manifold' ? E.manifoldZone_m : E.stationTol_m, connectTol: cfg.checks.connectTol_m, stationTol: E.stationTol_m });
  // outlets of a manifold ↔ the runs they feed (by destination, else the run that starts at the outlet)
  const manifoldRows = (n) => {
    if (!n?.outletsXY) return [];
    const runs = nodeRuns(n), rows = [];
    for (const k of ['cold', 'hot']) (n.outletsXY[k] || []).forEach((o, i) => {
      let r = runs.find(x => x.system === k && (x.to === o.to || x.from === o.to));
      if (!r) r = runs.find(x => x.system === k && (() => { const q = fr.toLocal(x.vertices[0][0], x.vertices[0][1]); return Math.hypot(q[0] - o.xy[0], q[1] - o.xy[1]) <= cfg.checks.connectTol_m; })());
      rows.push({ k, i, o, run: r || null, label: `${k === 'cold' ? 'ק' : 'ח'}${i + 1}` });
    });
    return rows;
  };
  const runLen = (r) => r.vertices.reduce((s2, q, i) => i && q[2] != null && r.vertices[i - 1][2] != null ? s2 + Math.hypot(q[0] - r.vertices[i - 1][0], q[1] - r.vertices[i - 1][1], q[2] - r.vertices[i - 1][2]) : s2, 0);
  const commitNodeMove = (n, res, label) => {
    const ch = { ['node:' + n.id]: res.node, ...res.runs };
    store.apply(ch, label || `${n.id}: הזזה עם ${Object.keys(res.runs).length} צינורות`);
  };
  const refresh = () => {   // rebuild after a store change, keep the selection by id
    M.setRuns(store.runs()); M.setNodes(store.nodes()); recheck();
    const selId = S.sel?.type === 'pipe' ? S.sel.obj.id : null, selLayer = S.sel?.obj?.layer;
    cur.items = itemsOf(S.floor); cur.nodes = nodesOf(S.floor);
    if (S.sel?.type === 'node') { const n = cur.nodes.find(x => x.id === S.sel.obj.id); if (n) { S.sel.obj = n; showInfo(S.sel); } else { S.sel = null; hideInfo(); } }
    if (selId) {
      const it = cur.items.find(i => i.p.id === selId && i.p.layer === selLayer);
      if (it) { S.sel.obj = it.p; if (S.sel.vtx != null && S.sel.vtx >= stOf(it.p).length) S.sel.vtx = null; showInfo(S.sel); } else { S.sel = null; hideInfo(); }
    }
    renderIssues(); syncTools(); redraw();
  };
  // issues shown on this floor: of runs drawn here in plan, and of points on this floor
  const floorIssues = () => {
    const here = new Set(cur.items.filter(it => it.mode === 'plan' && it.p.layer === 'prop').map(it => it.p.id)), nodeIds = new Set(cur.nodes.map(n => n.id));
    return [...[...here].flatMap(id => issues.runs[id] || []), ...issues.conn.filter(i => (i.run && here.has(i.run)) || (i.node && nodeIds.has(i.node)))];
  };
  // infrastructure / connection points of this view, grouped: name, what it is for, what it connects to
  const INFRA = ['utility', 'sewage', 'pump', 'rain', 'pool', 'water', 'hot'];
  function renderInfra() {
    let box = $('ed-infra'); if (!box) { box = document.createElement('div'); box.id = 'ed-infra'; $('ed-issues')?.after(box) || $('ed-panel').prepend(box); }
    const all = [...cur.cnodes, ...cur.nodes.filter(n => !isFixtureOrManifold(n))].filter(n => INFRA.includes((cfg.points.kinds[n.kind] || [])[0]) && !['waterJoint'].includes(n.kind));
    const by = {}; for (const n of all) (by[(cfg.points.kinds[n.kind] || ['water'])[0]] ||= []).push(n);
    const open = box.querySelector('details')?.open ?? false;
    box.innerHTML = `<details ${open ? 'open' : ''}><summary><h4 style="display:inline">נקודות חיבור ותשתיות <span class="ct">${all.length}</span></h4></summary>` +
      INFRA.filter(g => by[g]).map(g => `<div class="inf-g"><b style="color:${cfg.points.groups[g].color}">${esc(cfg.points.groups[g].label)}</b><ol class="infra">${by[g].map(n => {
        const L2 = pointLinks(n).filter(l => !l.superseded), lv = n.TL != null ? ` · T.L ${n.TL.toFixed(2)}${n.IL != null ? ' / I.L ' + n.IL.toFixed(2) : ''}` : '';
        return `<li data-id="${esc(n.id)}" data-l="${n.layer || 'prop'}"><b>${esc(n.id.split('@')[0])}</b> ${esc(kindName(n.kind))} – <span class="muted">${esc(n.title || '')}${lv}</span>${L2.length ? `<br><span class="muted">↔ ${L2.map(l => esc((l.other || '?').split('@')[0])).join(', ')}</span>` : ''}</li>`; }).join('')}</ol></div>`).join('') + '</details>';
    box.querySelectorAll('li').forEach(li => li.onclick = () => {
      const n = (li.dataset.l === 'cons' ? cur.cnodes : cur.nodes).find(x => x.id === li.dataset.id); if (!n) return;
      v.cx = n.xy[0]; v.cy = n.xy[1]; v.k = Math.max(v.k, 90); S.sel = { type: 'node', obj: n, vtx: null, seg: null }; showInfo(S.sel); S.flash = { at: n.xy }; redraw(); document.body.classList.remove('panel-open');
    });
  }
  function renderIssues() {
    let box = $('ed-issues'); if (!box) { box = document.createElement('div'); box.id = 'ed-issues'; $('ed-panel').prepend(box); }
    const list = floorIssues(), n = { error: 0, warn: 0, info: 0 }; list.forEach(i => n[i.sev]++);
    const icon = { error: '⛔', warn: '⚠', info: 'ℹ' };
    box.innerHTML = `<h4>בדיקות בקומה <span class="ct">⛔ ${n.error} · ⚠ ${n.warn}${n.info ? ' · ℹ ' + n.info : ''}</span></h4>` +
      (list.length ? `<ol class="issues">${list.slice(0, 200).map((i, k) => `<li class="sev-${i.sev}" data-k="${k}">${icon[i.sev]} <b>${esc((i.run || i.node || '').split('@')[0])}</b> ${esc(i.text)}</li>`).join('')}</ol>` : '<p class="note">✓ אין ממצאים בקומה</p>');
    box.querySelectorAll('li').forEach(li => li.onclick = () => {
      const i = list[+li.dataset.k]; v.cx = i.at[0]; v.cy = i.at[1]; v.k = Math.max(v.k, cfg.zoom.max_pxPerM / 6);
      const it = i.run && cur.items.find(x => x.p.id === i.run && x.p.layer === 'prop');
      if (it) { S.sel = { type: 'pipe', obj: it.p, vtx: null, seg: null }; showInfo(S.sel); }
      S.flash = { at: i.at, t: performance.now() }; redraw(); document.body.classList.remove('panel-open');
    });
  }
  store.onChange(() => { if (!S.drag) refresh(); else syncTools(); });
  const setFloor = (fid, fit = true) => {
    S.floor = fid; S.sel = null; S.draft = null; hideInfo();
    cur = { F: M.floors[fid], items: itemsOf(fid), nodes: nodesOf(fid), cnodes: cnodesOf(fid) };
    for (const b of $('ed-floors').children) b.classList.toggle('on', b.dataset.floor === fid);
    const counts = {};
    for (const it of cur.items) { const k = it.p.layer + '.' + it.p.system; if (!it.p.superseded) counts[k] = (counts[k] || 0) + 1; }
    for (const [k, list] of Object.entries(cur.F.structure)) counts['st.' + k] = list.length || null;
    for (const [k, list] of Object.entries(cur.F.background)) counts['bg.' + k] = list.length || null;
    counts.nodes = cur.nodes.length; counts['cons.superseded'] = cur.items.filter(it => it.p.superseded).length;
    buildPanel($('ed-panel'), L, cfg, sys, counts); renderIssues(); renderInfra();
    if (fit) fitFloor();
    try { history.replaceState(null, '', `?floor=${fid}`); } catch { /* sandboxed */ }
    syncDrawbar(); redraw();
  };
  const fitFloor = () => { const F = cur.F, polys = [...F.structure.concreteWalls, ...F.structure.blocks, ...F.structure.columns].map(e => e.poly); v.fit(bboxOf(polys.length ? polys : F.background.walls)); };
  const stOf = (p) => OP.stations(p.ref, fr, E.stationTol_m);

  // ---- top bar
  for (const [i, f] of cfg.floors.entries()) { const b = Object.assign(document.createElement('button'), { textContent: f.label, onclick: () => setFloor(f.id), title: `${f.label} (${i + 1})` }); b.dataset.floor = f.id; $('ed-floors').append(b); }
  const stepSel = $('ed-snap-step');
  for (const s of cfg.snap.steps_m) stepSel.append(new Option(`רשת ${s >= 0.1 ? s.toFixed(1) + " מ'" : (s * 100).toFixed(0) + ' ס"מ'}`, s, false, s === S.step));
  stepSel.onchange = () => { S.step = +stepSel.value; };
  $('ed-snap-on').onchange = (e) => { S.snapOn = e.target.checked; S.snap = null; redraw(); };
  $('ed-ortho').onchange = (e) => { S.ortho = e.target.checked; };
  $('ed-fit').onclick = () => { fitFloor(); redraw(); };
  $('ed-layers-btn').onclick = () => document.body.classList.toggle('panel-open');
  $('ed-mode-select').onclick = () => setMode('select');
  $('ed-mode-draw').onclick = () => setMode('draw');
  $('ed-undo').onclick = () => { const l = store.undo(); if (l) toast('בוטל: ' + l); };
  $('ed-redo').onclick = () => { const l = store.redo(); if (l) toast('חזרה: ' + l); };
  $('ed-export').onclick = exportRoutes;
  L.onChange(() => { setFloor(S.floor, false); });
  function syncTools() {
    $('ed-undo').disabled = !store.undoS.length; $('ed-redo').disabled = !store.redoS.length;
    $('ed-mode-draw').disabled = !store.canEdit;
    const el = $('ed-save'), n = store.editedCount();
    const txt = { saving: 'שומר…', saved: n ? `✓ נשמר במודל (${n} קווים ערוכים)` : '✓ מחובר למודל', error: '⚠ שמירה נכשלה – נשמר בדפדפן', timeout: '⚠ המודל לא ענה – נשמר בדפדפן', local: `נשמר בדפדפן בלבד (${n})`, idle: n ? `נשמר בדפדפן בלבד (${n})` : '' }[store.state] || '';
    el.textContent = store.canEdit ? txt : '🔒 צפייה בלבד'; el.className = 'ed-save' + (store.state === 'error' || store.state === 'timeout' ? ' err' : store.state === 'saved' ? ' ok' : '');
  }
  function setMode(m) {
    if (m === 'draw' && !store.canEdit) return;
    S.mode = m; S.draft = null; $('ed-mode-select').classList.toggle('on', m === 'select'); $('ed-mode-draw').classList.toggle('on', m === 'draw');
    if (m === 'draw') { S.sel = null; hideInfo(); }
    syncDrawbar(); redraw();
  }

  // ---- new-pipe bar (draw mode): system, diameter, material, level
  const cat = D.plumbingCatalog.pipes;
  const draw = { system: 'cold', material: 'PEX', D_mm: 20, Hrel: null };
  function syncDrawbar() {
    const bar = $('ed-drawbar'); if (S.mode !== 'draw') { bar.classList.add('hidden'); return; }
    bar.classList.remove('hidden');
    const sizes = Object.keys(cat[draw.material]?.sizes || {}).map(Number);
    bar.innerHTML = `<b>צינור חדש:</b>
      <select id="dw-sys">${cfg.systems.order.map(s => `<option value="${s}" ${s === draw.system ? 'selected' : ''}>${esc(sys[s].label)}</option>`).join('')}</select>
      <select id="dw-mat">${Object.keys(cat).map(m => `<option ${m === draw.material ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select>
      <select id="dw-d">${sizes.map(d => `<option value="${d}" ${d === draw.D_mm ? 'selected' : ''}>ø${d}</option>`).join('')}</select>
      <label>מפלס ציר (יחסי ל-±0.00) <input id="dw-h" type="number" step="0.01" value="${draw.Hrel ?? ''}" placeholder="מנקודת ההתחלה"></label>
      <span>${S.draft ? `${S.draft.pts.length} נקודות` : 'לחיצה = נקודה, לחיצה כפולה / Enter = סיום, Esc = ביטול'}</span>
      ${S.draft ? '<button id="dw-done">✓ סיום</button><button id="dw-cancel">✕ ביטול</button>' : ''}`;
    $('dw-sys').onchange = (e) => { draw.system = e.target.value; };
    $('dw-mat').onchange = (e) => { draw.material = e.target.value; const sz = Object.keys(cat[draw.material].sizes).map(Number); if (!sz.includes(draw.D_mm)) draw.D_mm = sz[0]; syncDrawbar(); };
    $('dw-d').onchange = (e) => { draw.D_mm = +e.target.value; };
    $('dw-h').onchange = (e) => { draw.Hrel = e.target.value === '' ? null : +e.target.value; };
    if (S.draft) { $('dw-done').onclick = finishDraft; $('dw-cancel').onclick = () => { S.draft = null; syncDrawbar(); redraw(); }; }
  }
  const snapH = (s) => {  // level of what the cursor snapped to (node / pipe vertex), absolute
    if (s?.kind === 'node' && s.ref?.H != null) return s.ref.H;
    if (s?.kind === 'vertex' && s.ref?.layer === 'prop') { const p = s.ref; let best = null; p.pts.forEach((q, i) => { const d = Math.hypot(q[0] - s.x, q[1] - s.y); if (p.H[i] != null && (!best || d < best.d)) best = { d, h: p.H[i] }; }); return best?.h ?? null; }
    return null;
  };
  function addDraftPoint(s) {
    let x = s.x, y = s.y;
    if (!S.draft) {
      const h = draw.Hrel != null ? M.H0 + draw.Hrel : snapH(s);
      if (h == null) { toast('אין מפלס: התחל מנקודה / צינור קיים, או הזן מפלס ציר'); return; }
      S.draft = { pts: [[x, y]], H: h, from: s.kind === 'node' ? s.ref.id : null };
    } else {
      const a = S.draft.pts[S.draft.pts.length - 1];
      if (S.ortho) { if (Math.abs(x - a[0]) >= Math.abs(y - a[1])) y = a[1]; else x = a[0]; }
      if (Math.hypot(x - a[0], y - a[1]) < E.minSeg_m) return;
      S.draft.pts.push([x, y]); if (s.kind === 'node') S.draft.to = s.ref.id;
    }
    syncDrawbar(); redraw();
  }
  function finishDraft() {
    const d = S.draft; if (!d || d.pts.length < 2) { toast('צריך לפחות שתי נקודות'); return; }
    let n = 1; const pre = `${E.newIdPrefix}-${draw.system}`; while (store.get(`${pre}${n}@${S.floor}`)) n++;
    const run = { id: `${pre}${n}@${S.floor}`, kind: 'run', system: draw.system, floor: S.floor, D_mm: draw.D_mm, material: draw.material, from: d.from || null, to: d.to || null,
      vertices: d.pts.map(([x, y]) => { const [E_, N_] = fr.toITM(x, y); return [r3(E_), r3(N_), r3(d.H)]; }), source: 'עורך הצנרת – שורטט ידנית' };
    store.apply({ [run.id]: run }, `צינור חדש ${run.id}`); S.draft = null; setMode('select');
    const it = cur.items.find(i => i.p.id === run.id); if (it) { S.sel = { type: 'pipe', obj: it.p, vtx: null, seg: null }; showInfo(S.sel); }
    toast(`נוסף ${run.id}`); redraw();
  }

  // ---- rendering
  let raf = 0;
  function redraw() { if (!raf) raf = requestAnimationFrame(paint); }
  function paint() {
    raf = 0; ctx.setTransform(v.dpr, 0, 0, v.dpr, 0, 0); ctx.clearRect(0, 0, v.w, v.h);
    const on = (k) => L.on(k);
    if (on('grid')) drawGrid(ctx, v, cfg);
    drawBackground(ctx, v, cfg, cur.F.background, on);
    drawStructure(ctx, v, cfg, cur.F.structure, on);
    let items = visibleItems(), selP = S.sel?.type === 'pipe' ? S.sel.obj : null;
    if (S.preview) { items = items.map(it => it.p.id === S.preview.p.id && it.p.layer === 'prop' ? { ...it, p: S.preview.p } : it); selP = S.preview.p; }
    if (S.npreview) { const R = S.npreview.res.runs; items = items.map(it => it.p.layer === 'prop' && R[it.p.id] ? { ...it, p: { ...it.p, ref: R[it.p.id], pts: R[it.p.id].vertices.map(q => fr.toLocal(q[0], q[1])), verticals: [] } } : it); }
    // pipes with an error are drawn red (live for the run being dragged)
    const liveRun = S.preview ? checkRun(S.preview.run, CH) : null;
    const errIds = new Set(Object.entries(issues.runs).filter(([id, l]) => (S.preview && id === S.preview.run.id ? liveRun : l).some(i => i.sev === 'error')).map(([id]) => id));
    if (S.preview && liveRun.some(i => i.sev === 'error')) errIds.add(S.preview.run.id);
    const nLive = S.npreview ? Object.fromEntries(Object.entries(S.npreview.res.runs).map(([id, r]) => [id, checkRun(r, CH)])) : {};
    for (const [id, li] of Object.entries(nLive)) { if (li.some(i => i.sev === 'error')) errIds.add(id); else errIds.delete(id); }
    const focusN = S.sel?.type === 'node' && S.sel.obj.kind === 'manifold' ? S.sel.obj : null;
    const focusRows = focusN ? manifoldRows(S.npreview ? { ...focusN, outletsXY: Object.fromEntries(Object.entries(S.npreview.res.node.outlets || {}).map(([k, l]) => [k, l.map(o => ({ ...o, xy: fr.toLocal(o.E, o.N) }))])) } : focusN) : [];
    const focus = focusN ? new Set(nodeRuns(focusN).map(r => r.id)) : null;
    drawPipes(ctx, v, cfg, items, sys, selP, S.hover?.type === 'pipe' ? S.hover.obj : null, errIds, focus);
    let fi = floorIssues(); if (S.preview) fi = [...fi.filter(i => i.run !== S.preview.run.id), ...liveRun];
    if (S.npreview) for (const [id, li] of Object.entries(nLive)) fi = [...fi.filter(i => i.run !== id), ...li];
    drawIssues(ctx, v, cfg, fi, S.flash);
    const nodesNow = S.npreview ? cur.nodes.map(n => n.id === S.npreview.n.id ? { ...n, xy: S.npreview.xy } : n) : cur.nodes;
    const nodesShown = S.npreview ? nodesNow.map(n => n.id === S.npreview.n.id ? { ...n, outletsXY: Object.fromEntries(Object.entries(S.npreview.res.node.outlets || {}).map(([k, l]) => [k, l.map(o => ({ ...o, xy: fr.toLocal(o.E, o.N) }))])) } : n) : nodesNow;
    const selN = S.sel?.type === 'node' ? S.sel.obj : null, hovN = S.hover?.type === 'node' ? S.hover.obj : null;
    if (on('cpoints')) drawPoints(ctx, v, cfg, cur.cnodes, selN, hovN, on('labels.points'));
    if (on('nodes')) drawPoints(ctx, v, cfg, nodesShown.filter(n => !isFixtureOrManifold(n)), selN, hovN, on('labels.points'));
    if (on('nodes')) drawNodes(ctx, v, cfg, nodesShown.filter(isFixtureOrManifold), S.sel?.type === 'node' ? (S.npreview ? nodesNow.find(n => n.id === S.sel.obj.id) : S.sel.obj) : null, S.hover?.type === 'node' ? S.hover.obj : null);
    if (focusN && focusRows.length) {   // numbers: at the fixture end of every outlet's run, and on the outlet when zoomed in
      const mn = nodesShown.find(n => n.id === focusN.id), ms = mn?.outletsXY ? manifoldScreen(v, cfg, mn) : null, B = [];
      for (const x of focusRows) {
        const col = x.k === 'cold' ? '#1f6fd1' : '#cf3a2c', r = x.run && (S.npreview?.res.runs[x.run.id] || x.run);
        if (r) { const far = r.from === focusN.id || r.to !== focusN.id ? r.vertices[r.vertices.length - 1] : r.vertices[0]; const q = fr.toLocal(far[0], far[1]); B.push({ xy: [v.sx(q[0]), v.sy(q[1]) - cfg.manifold.badge_px - 4], text: String(x.i + 1), color: col }); }
        if (ms && v.k >= cfg.manifold.outletLabelMinK) { const p0 = ms.pos[`${x.k}:${x.i}`]; B.push({ xy: [p0[0] + ms.nm[0] * (x.k === 'cold' ? -1 : 1) * (cfg.manifold.badge_px + 6), p0[1] + ms.nm[1] * (x.k === 'cold' ? -1 : 1) * (cfg.manifold.badge_px + 6)], text: String(x.i + 1), color: col }); }
      }
      drawBadges(ctx, cfg, B);
    }
    if (selP && editable(selP)) drawHandles(ctx, v, cfg, S.preview ? S.preview.S : stOf(selP), S.sel.vtx, S.sel.seg, (sys[selP.system] || {}).color);
    if (S.draft) drawDraft(ctx, v, S.draft.pts, S.snap ? draftCursor(S.snap) : null, sys[draw.system].color);
    drawSnap(ctx, v, S.snap);
    const a = fr.gridNorthAngle() + (D.origin.trueNorthGridAzimuth_deg || 0) * Math.PI / 180;
    $('ed-compass').style.transform = `rotate(${a}rad)`;
    const target = 120 / v.k, pow = Math.pow(10, Math.floor(Math.log10(target))), nice = [1, 2, 5, 10].map(m => m * pow).find(m => m >= target * 0.6) || pow;
    $('ed-scale').style.width = `${nice * v.k}px`; $('ed-scale').textContent = `${nice >= 1 ? nice : nice.toFixed(2)} מ'`;
    window.__editorPaints = (window.__editorPaints || 0) + 1;
  }
  const draftCursor = (s) => { let x = s.x, y = s.y; const a = S.draft.pts[S.draft.pts.length - 1]; if (S.ortho) { if (Math.abs(x - a[0]) >= Math.abs(y - a[1])) y = a[1]; else x = a[0]; } return [x, y]; };
  new ResizeObserver(() => { v.resize(); redraw(); }).observe(canvas);

  // ---- info / properties card
  function hideInfo() { $('ed-info').classList.add('hidden'); }
  function showInfo(hit) {
    const rows = []; let title, color = null, src, warn = null, form = '', acts = '';
    if (hit.type === 'node') {
      const n = hit.obj, grp = cfg.points.groups[(cfg.points.kinds[n.kind] || [])[0]];
      title = `${n.id.split('@')[0]} – ${kindName(n.kind)}`; src = n.source; color = grp?.color || null;
      rows.push(['ייעוד', n.title || kindName(n.kind)], ['קבוצה', grp?.label || '–'], ['שכבה', n.layer === 'cons' ? 'תוכנית היועץ' : 'הצעה'], ['קומה', n.floor]);
      if (n.TL != null) rows.push(['T.L (מכסה)', `${n.TL.toFixed(2)} (${fmtRel(n.TL - M.H0)})`]);
      if (n.IL != null) rows.push(['I.L (תחתית)', `${n.IL.toFixed(2)} (${fmtRel(n.IL - M.H0)})${n.TL != null ? ` · עומק ${(n.TL - n.IL).toFixed(2)} מ'` : ''}`]);
      if (n.D_m != null) rows.push(['קוטר', `ø${(n.D_m * 100).toFixed(0)} ס"מ`]);
      const links = pointLinks(n);
      if (links.length) rows.push(['מתחבר', links.map(l => `${l.dir} ${(l.other || '?').split('@')[0]} – ${l.id.split('@')[0]}${l.D ? ' ø' + l.D : ''}${l.mat ? ' ' + l.mat : ''}${l.IL ? ' (I.L ' + l.IL + ')' : ''} [${l.layer}${l.superseded ? ', הוחלף' : ''}]`).join(' | ')]);
      if (n.status && n.status !== 'source') warn = `סטטוס: ${n.status}`;
      rows.push(['ITM', `E ${n.E.toFixed(3)} · N ${n.N.toFixed(3)}`]);
      if (n.H != null) rows.push(['גובה', `${n.H.toFixed(2)} (${fmtRel(n.H - M.H0)})`]);
      if (n.D_mm) rows.push(['קוטר', `ø${n.D_mm}`]);
      if (n.cold != null) rows.push(['מים', [n.cold && 'קרים', n.hot && 'חמים'].filter(Boolean).join(' + ') || '–']);
      rows.push(['סטטוס', n.status]);
      if (nodeEditable(n)) {
        const conn = nodeRuns(n);
        rows.push(['מחובר', conn.length ? conn.map(r => r.id.split('@')[0]).join(', ') : '–']);
        form = `<div class="form">
          <label>הזזה בצירי הבית</label><div class="row2"><input id="nf-dx" type="number" step="0.01" placeholder="x מ'"><input id="nf-dy" type="number" step="0.01" placeholder="y מ'"><button id="nf-go">הזז</button></div></div>`;
        if (n.kind === 'manifold' && n.outletsXY) {
          const R = manifoldRows(n), other = conn.filter(r => !R.some(x => x.run && x.run.id === r.id));
          const sect = (k, title, col, h) => { const L = R.filter(x => x.k === k); if (!L.length) return '';
            const W = Math.max(160, L.length * 26 + 20);
            const svg = `<svg class="mf-svg" viewBox="0 0 ${W} 46" width="${W}" height="46"><line x1="8" y1="12" x2="${W - 8}" y2="12" stroke="${col}" stroke-width="6" stroke-linecap="round"/>${L.map((x, j) => `<g class="mf-o" data-run="${x.run?.id || ''}"><line x1="${18 + j * 26}" y1="12" x2="${18 + j * 26}" y2="28" stroke="${col}" stroke-width="2.5"/><circle cx="${18 + j * 26}" cy="36" r="9" fill="${x.run ? col : '#999'}"/><text x="${18 + j * 26}" y="40" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">${x.i + 1}</text></g>`).join('')}</svg>`;
            return `<div class="mf-sec"><b style="color:${col}">${title}</b> <span class="muted">(${h != null ? '+' + h.toFixed(2) + ' מעל הרצפה' : ''})</span>${svg}
              <table class="mf-t">${L.map(x => `<tr data-run="${x.run?.id || ''}"><td><span class="mf-n" style="background:${x.run ? col : '#999'}">${x.label}</span></td><td>ø${x.o.D_mm ?? '?'}</td><td>${esc(x.o.to.split('@')[0])}</td><td>${x.run ? runLen(x.run).toFixed(1) + " מ'" : '⚠ אין קו'}</td></tr>`).join('')}</table></div>`; };
          form = `<div class="mf">${sect('cold', 'מים קרים', '#1f6fd1', n.coldH)}${sect('hot', 'מים חמים', '#cf3a2c', n.hotH)}
            ${other.length ? `<div class="mf-sec"><b>מחובר גם</b> <span class="muted">(הזנה / סחרור)</span><table class="mf-t">${other.map(r => `<tr data-run="${r.id}"><td><span class="mf-n" style="background:${(sys[r.system] || {}).color}">↔</span></td><td>ø${r.D_mm ?? '?'}</td><td>${esc(r.id.split('@')[0])}</td><td>${runLen(r).toFixed(1)} מ'</td></tr>`).join('')}</table></div>` : ''}</div>` + form;
        }
        acts = `<div class="note">${n.kind === 'manifold' ? 'גרירת המחלק מזיזה אותו יחד עם כל היציאות והצנרת שמחוברת אליו (כמערכת אחת); הצנרת נשארת מחוברת.' : 'גרירת הנקודה מזיזה איתה את קצוות הצנרת שמחוברים אליה.'}</div>`;
      }
    } else {
      const p = hit.obj, r = p.ref; color = (sys[p.system] || {}).color; title = `${p.id} – ${(sys[p.system] || {}).label || p.system}`;
      const plan = p.pts.reduce((s, q, i) => i ? s + Math.hypot(q[0] - p.pts[i - 1][0], q[1] - p.pts[i - 1][1]) : 0, 0);
      const len3 = r.vertices ? r.vertices.reduce((s, q, i) => i && q[2] != null && r.vertices[i - 1][2] != null ? s + Math.hypot(q[0] - r.vertices[i - 1][0], q[1] - r.vertices[i - 1][1], q[2] - r.vertices[i - 1][2]) : s, 0) : r.length_m;
      rows.push(['שכבה', p.layer === 'prop' ? (r.status === 'manual' ? 'הצעה – נערך ידנית' : 'הצעה (routes.json)') : 'תוכנית היועץ – קריאה בלבד']);
      if (p.layer !== 'prop' || !editable(p)) { if (r.D_mm) rows.push(['קוטר / חומר', `ø${r.D_mm}${r.material ? ' · ' + r.material : ''}`]); if (r.from || r.to) rows.push(['מ → אל', `${r.from || '?'} → ${r.to || '?'}`]); }
      rows.push(['קומה', p.floor === 'multi' ? (p.floors || []).join(', ') : p.floor]);
      rows.push(['אורך במבט על', `${plan.toFixed(2)} מ'`]);
      if (len3) rows.push(['אורך (3D)', `${len3.toFixed(2)} מ'`]);
      const Hs = (p.H || []).filter(x => x != null);
      if (Hs.length) rows.push(['מפלס', `${fmtRel(Math.min(...Hs) - M.H0)} … ${fmtRel(Math.max(...Hs) - M.H0)}`]);
      if (r.ILup != null && p.layer === 'cons') rows.push(['I.L', `${r.ILup.toFixed(2)} → ${r.ILdown.toFixed(2)}`]);
      if (r.slope != null && !editable(p)) rows.push(['שיפוע', `${(r.slope * 100).toFixed(1)}%`]);
      if (r.insulation_mm) rows.push(['בידוד', `${r.insulation_mm} מ"מ`]);
      if (p.layer === 'prop') { const st = stOf(p), bad = st.slice(1).filter((q, i) => !OP.isAxisAligned(st[i], q, E.axisEps_deg)).length; rows.push(['מקטעים', `${st.length - 1}${bad ? ` (${bad} לא בצירי הבית)` : ' – כולם בצירי הבית'}`]); }
      if (p.superseded) warn = 'ההצעה מחליפה קו זה';
      if (p.layer === 'prop') { const li = [...(issues.runs[p.id] || []), ...issues.conn.filter(i => i.run === p.id)]; if (li.length) rows.push(['בדיקות', li.map(i => ({ error: '⛔', warn: '⚠', info: 'ℹ' }[i.sev] + ' ' + i.text)).join(' | ')]); else rows.push(['בדיקות', '✓ תקין']); }
      if (r.levelStatus && r.levelStatus !== 'source') warn = (warn ? warn + ' · ' : '') + `מפלס: ${r.levelStatus}`;
      src = r.source;
      if (editable(p)) {
        const mats = [...new Set([...Object.keys(cat), r.material].filter(Boolean))];
        const sizes = [...new Set([...Object.keys(cat[r.material]?.sizes || {}).map(Number), r.D_mm].filter(x => x != null))].sort((a, b) => a - b);
        const st = stOf(p), vtx = hit.vtx, grav = E.gravitySystems.includes(r.system);
        const vH = vtx != null ? st[vtx].H : null;
        form = `<div class="form">
          <label>מערכת</label><select data-f="system">${cfg.systems.order.map(s => `<option value="${s}" ${s === r.system ? 'selected' : ''}>${esc(sys[s].label)}</option>`).join('')}</select>
          <label>חומר</label><select data-f="material">${!r.material ? '<option value="" selected>– לא ידוע –</option>' : ''}${mats.map(m => `<option ${m === r.material ? 'selected' : ''}>${esc(m)}</option>`).join('')}</select>
          <label>קוטר</label><select data-f="D_mm">${r.D_mm == null ? '<option value="" selected>– לא ידוע –</option>' : ''}${sizes.map(d => `<option value="${d}" ${d === r.D_mm ? 'selected' : ''}>ø${d}</option>`).join('')}</select>
          <label>מ-</label><input data-f="from" value="${esc(r.from || '')}">
          <label>אל</label><input data-f="to" value="${esc(r.to || '')}">
          ${grav ? `<label>שיפוע %</label><div class="row2"><input id="pf-slope" type="number" step="0.1" value="${r.slope != null ? r3(r.slope * 100) : ''}"><button id="pf-slope-go" title="מפלסים מחדש מהקצה העליון לאורך הקו">החל</button></div>` : ''}
          <label>הזזת גובה</label><div class="row2"><input id="pf-dh" type="number" step="0.01" placeholder="± מ'"><button id="pf-dh-go">הזז את כל הקו</button></div>
          ${vtx != null ? `<label>נקודה ${vtx + 1}</label><div class="row2"><input id="pf-vh" type="number" step="0.01" value="${vH.length === 1 && vH[0] != null ? r3(vH[0] - M.H0) : ''}" ${vH.length > 1 ? 'disabled title="קטע אנכי – גובה לכל קצה בנפרד"' : ''} placeholder="מפלס יחסי"><button id="pf-vh-go" ${vH.length > 1 ? 'disabled' : ''}>קבע</button></div>` : ''}
          <label>הערה</label><input data-f="note" value="${esc(r.note || '')}">
        </div>`;
        acts = `<div class="acts">
          <button id="pf-ortho" title="פישוט ויישור כל המקטעים לצירי הבית">⟂ יישור לצירי הבית</button>
          ${hit.seg != null ? '<button id="pf-ins" title="נקודת פנייה באמצע המקטע המסומן">＋ נקודה במקטע</button>' : ''}
          ${vtx != null ? '<button id="pf-del-v">− מחק נקודה</button>' : ''}
          ${grav ? '<button id="pf-rev" title="היפוך כיוון הזרימה">⇄ כיוון זרימה</button>' : ''}
          ${store.over[p.id] && D.routes.runs.some(b => b.id === p.id) ? '<button id="pf-revert">↺ החזר למקור</button>' : ''}
          <button id="pf-del" class="danger">🗑 מחק צינור</button></div>
          <div class="note">גרירת מקטע מזיזה אותו במקביל; גרירת ריבוע מזיזה פינה; לחיצה כפולה על מקטע מוסיפה פינה; Delete מוחק פינה.</div>`;
      } else if (p.layer === 'cons' && store.canEdit) acts = '<div class="acts"><button id="pf-copy" title="יוצר קו הצעה חדש באותו תוואי – הקו של היועץ נשאר">⧉ העתק להצעה</button></div>';
    }
    const ed = hit.obj?.ref?.edited;
    $('ed-info').innerHTML = `<button class="x" aria-label="סגירה">✕</button><h3>${color ? `<span class="sw" style="background:${color}"></span>` : ''}${esc(title)}</h3>
      <table>${rows.map(([a, b]) => `<tr><td>${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')}</table>
      ${ed ? `<div class="edited">✎ נערך ${esc(new Date(ed.at).toLocaleString('he-IL'))}</div>` : ''}
      ${warn ? `<div class="warn">⚠ ${esc(warn)}</div>` : ''}${form}${acts}<div class="src">מקור: ${esc(src)}</div>`;
    $('ed-info').querySelector('.x').onclick = () => { S.sel = null; hideInfo(); redraw(); };
    wireForm(hit);
    $('ed-info').classList.remove('hidden');
  }
  const change = (run, label) => store.apply({ [run.id]: run }, label);
  function wireForm(hit) {
    if (hit.type === 'node') {
      $('ed-info').querySelectorAll('[data-run]').forEach(el => { if (!el.dataset.run) return; el.style.cursor = 'pointer'; el.onclick = () => {
        const it = cur.items.find(i => i.p.id === el.dataset.run && i.p.layer === 'prop'); if (!it) { toast('הקו בקומה אחרת'); return; }
        S.sel = { type: 'pipe', obj: it.p, vtx: null, seg: null }; showInfo(S.sel); redraw(); }; });
      const go = $('ed-info').querySelector('#nf-go'); if (!go) return;
      go.onclick = () => { const dx = +$('nf-dx').value || 0, dy = +$('nf-dy').value || 0; if (!dx && !dy) return; commitNodeMove(hit.obj, moveNode(hit.obj, dx, dy)); toast(`${hit.obj.id} הוזז עם הצנרת שמחוברת אליו`); };
      return;
    }
    const box = $('ed-info'), p = hit.obj, r = p?.ref; if (!r) return;
    box.querySelectorAll('[data-f]').forEach(el => el.onchange = () => {
      const f = el.dataset.f; let val = el.value; if (f === 'D_mm') val = val === '' ? null : +val; if (val === '' && f !== 'D_mm') val = null;
      change({ ...store.get(r.id), [f]: val }, `${r.id}: ${f}`);
    });
    const on = (id, fn) => { const el = box.querySelector('#' + id); if (el) el.onclick = fn; };
    on('pf-slope-go', () => { const s = +box.querySelector('#pf-slope').value / 100; if (!(s > 0)) { toast('שיפוע חייב להיות חיובי'); return; } const res = OP.applySlope(store.get(r.id), s); if (res.why) toast(res.why); else change(res.run, `${r.id}: שיפוע ${(s * 100).toFixed(1)}%`); });
    on('pf-dh-go', () => { const dh = +box.querySelector('#pf-dh').value; if (!dh) return; change(OP.shiftH(store.get(r.id), dh), `${r.id}: גובה ${dh > 0 ? '+' : ''}${dh}`); });
    on('pf-vh-go', () => { const h = box.querySelector('#pf-vh').value; if (h === '') return; const st = stOf(p); st[hit.vtx] = { ...st[hit.vtx], H: [M.H0 + +h] }; change(OP.fromStations(store.get(r.id), st, fr), `${r.id}: גובה נקודה`); });
    on('pf-ortho', () => { const st = OP.orthogonalize(stOf(p), opt()); S.sel.vtx = null; S.sel.seg = null; change(OP.fromStations(store.get(r.id), st, fr), `${r.id}: יישור לצירי הבית`); toast('יושר לצירי הבית – בדוק את התוואי'); });
    on('pf-ins', () => { const st = stOf(p), a = st[hit.seg], b = st[hit.seg + 1]; change(OP.fromStations(store.get(r.id), OP.insertStation(st, hit.seg, (a.x + b.x) / 2, (a.y + b.y) / 2), fr), `${r.id}: נקודה חדשה`); S.sel.vtx = hit.seg + 1; S.sel.seg = null; });
    on('pf-del-v', () => delVertex());
    on('pf-rev', () => { const x = store.get(r.id); change({ ...x, vertices: [...x.vertices].reverse(), from: x.to, to: x.from }, `${r.id}: היפוך כיוון`); });
    on('pf-revert', () => { store.revert(r.id); toast('הוחזר למקור'); });
    on('pf-del', async () => { if (!(await askConfirm(`למחוק את ${r.id}?`, { ok: 'מחק', danger: true }))) return; store.apply({ [r.id]: null }, `מחיקת ${r.id}`); S.sel = null; hideInfo(); toast(`נמחק ${r.id} (ביטול: Ctrl+Z)`); });
    on('pf-copy', () => copyToProposal(p));
  }
  function delVertex() {
    const p = S.sel?.obj; if (!editable(p) || S.sel.vtx == null) return;
    const res = OP.deleteStation(stOf(p), S.sel.vtx); if (res.why) { toast(res.why); return; }
    S.sel.vtx = null; change(OP.fromStations(store.get(p.id), res.S, fr), `${p.id}: מחיקת נקודה`);
  }
  function copyToProposal(p) {   // consultant run -> new proposal run, centre line = invert + OD/2 (catalog), else "by the ground"
    const r = p.ref, mat = r.material, od = cat[mat]?.sizes?.[String(r.D_mm)]?.OD;
    const P = r.pts || r.pts3d; let acc = 0; const Ls = P.map((q, i) => (acc += i ? Math.hypot(q[0] - P[i - 1][0], q[1] - P[i - 1][1]) : 0));
    const H = (i) => r.pts3d ? r.pts3d[i][2] : (r.ILup != null && r.ILdown != null && od ? r3(r.ILup + (r.ILdown - r.ILup) * (acc ? Ls[i] / acc : 0) + od / 2) : null);
    const id = `${r.id}~P`; if (store.get(id)) { toast(`${id} כבר קיים`); return; }
    const run = { id, kind: 'run', system: r.system, floor: p.floor === 'multi' ? S.floor : p.floor, D_mm: r.D_mm ?? null, material: mat ?? null, from: r.from || null, to: r.to || null,
      vertices: P.map((q, i) => [q[0], q[1], H(i)]), slope: r.slope ?? null, replaces: r.id, source: `העתק מ-data/plumbing/network.json ${r.id}${od ? '' : ' (בלי מפלס – לפי פני הקרקע)'}` };
    store.apply({ [id]: run }, `העתקה ${r.id}`); toast(`נוצר ${id} בהצעה`);
  }
  async function exportRoutes() {
    const text = store.exportJson(), name = 'routes.json';
    const dl = window.claude?.use ? await window.claude.use('downloads').catch(() => null) : null;
    if (dl) { try { await dl.save({ filename: name, data: text }); } catch (e) { toast('הייצוא בוטל'); } return; }
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' })); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  // ---- pointer
  const pts = new Map(); let gesture = null, pinch = null;
  const local = (e) => { const rc = canvas.getBoundingClientRect(); return [e.clientX - rc.left, e.clientY - rc.top]; };
  const status = (s) => {
    const [E_, N_] = fr.toITM(s.x, s.y), kind = { grid: 'רשת', vertex: 'פינה', edge: 'על קו', node: 'נקודה', free: '' }[s.kind];
    $('ed-status').textContent = `x ${s.x.toFixed(3)}  y ${s.y.toFixed(3)} (צירי הבית) · E ${E_.toFixed(3)}  N ${N_.toFixed(3)}${kind ? ' · הצמדה: ' + kind : ''}${S.ortho ? ' · אורתו' : ''}`;
  };
  const snapAt = (x, y, exclude) => {
    if (!S.snapOn) return { kind: 'free', x, y };
    const items = exclude ? visibleItems().filter(it => it.p !== exclude) : visibleItems();
    return snapPoint(x, y, cfg.snap.radius_px / v.k, { step: S.step }, cur.F, items, pickNodes(), (k) => L.on(k));
  };
  const handleHit = (x, y, touch) => {   // on the selected editable run: station or segment
    const p = S.sel?.type === 'pipe' ? S.sel.obj : null; if (!editable(p)) return null;
    const st = stOf(p), rh = (E.hitHandle_px * (touch ? 1.7 : 1)) / v.k;
    let best = null; st.forEach((q, i) => { const d = Math.hypot(q.x - x, q.y - y); if (d <= rh && (!best || d < best.d)) best = { d, kind: 'vtx', i }; });
    if (best) return best;
    for (let i = 0; i + 1 < st.length; i++) { const a = st[i], b = st[i + 1], dx = b.x - a.x, dy = b.y - a.y, L2 = dx * dx + dy * dy; if (!L2) continue; const t = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / L2)); const d = Math.hypot(a.x + t * dx - x, a.y + t * dy - y); if (d <= rh * 0.8 && (!best || d < best.d)) best = { d, kind: 'seg', i }; }
    return best;
  };
  canvas.addEventListener('pointerdown', (e) => {
    canvas.setPointerCapture(e.pointerId); const p = local(e); pts.set(e.pointerId, p);
    if (pts.size === 2) { const [a, b] = [...pts.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), m: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] }; gesture = null; S.preview = null; return; }
    const [x, y] = v.toLocal(...p), touch = e.pointerType === 'touch';
    let h = S.mode === 'select' ? handleHit(x, y, touch) : null;
    if (!h && S.mode === 'select' && S.sel?.type === 'node' && nodeEditable(S.sel.obj)) {
      const n = S.sel.obj; if (Math.hypot(n.xy[0] - x, n.xy[1] - y) <= (E.hitHandle_px * (touch ? 1.7 : 1)) / v.k) h = { kind: 'node', node: n };
    }
    gesture = { p0: p, p: p, moved: 0, xy0: [x, y], handle: h, touch };
  });
  canvas.addEventListener('pointermove', (e) => {
    const p = local(e); if (pts.has(e.pointerId)) pts.set(e.pointerId, p);
    if (pinch && pts.size === 2) { const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]), m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; v.pan(m[0] - pinch.m[0], m[1] - pinch.m[1]); v.zoomAt(m[0], m[1], d / pinch.d); pinch = { d, m }; redraw(); return; }
    const [x, y] = v.toLocal(...p);
    if (gesture) {
      gesture.moved += Math.abs(p[0] - gesture.p[0]) + Math.abs(p[1] - gesture.p[1]);
      if (gesture.handle?.kind === 'node' && gesture.moved > E.dragThreshold_px) {   // move a point with its pipes
        S.drag = true; const n = gesture.handle.node;
        let tx = x - gesture.xy0[0] + n.xy[0], ty = y - gesture.xy0[1] + n.xy[1];
        if (S.snapOn && S.step) { tx = Math.round(tx / S.step) * S.step; ty = Math.round(ty / S.step) * S.step; }
        const res = moveNode(n, tx - n.xy[0], ty - n.xy[1]);
        S.npreview = { n, res, xy: [tx, ty] }; status({ kind: S.snapOn ? 'grid' : 'free', x: tx, y: ty }); redraw(); gesture.p = p; return;
      }
      if (gesture.handle && gesture.moved > E.dragThreshold_px) {          // edit drag
        S.drag = true; const sel = S.sel.obj, st = stOf(sel), sp = snapAt(x, y, sel); S.snap = sp; status(sp);
        let S2;
        if (gesture.handle.kind === 'vtx') S2 = OP.dragStation(st, gesture.handle.i, sp.x, sp.y, opt());
        else { const g = S.snapOn && sp.kind !== 'free' ? [sp.x, sp.y] : [x, y]; S2 = OP.dragSegment(st, gesture.handle.i, g[0] - gesture.xy0[0], g[1] - gesture.xy0[1], opt()); }
        const run2 = OP.fromStations(sel.ref, S2, fr);
        S.preview = { S: S2, run: run2, p: { ...sel, ref: run2, pts: S2.flatMap(q => q.H.map(() => [q.x, q.y])), verticals: [] } };
        redraw(); gesture.p = p; return;
      }
      if (!gesture.handle && gesture.moved > E.dragThreshold_px) { v.pan(p[0] - gesture.p[0], p[1] - gesture.p[1]); gesture.p = p; redraw(); return; }
      gesture.p = p;
    }
    S.snap = snapAt(x, y); status(S.snap);
    if (S.mode === 'select') {
      S.hover = hitTest(x, y, cfg.snap.radius_px / v.k, visibleItems(), pickNodes(), (k) => k === 'nodes' ? false : L.locked(k));
      const hh = handleHit(x, y, false), onNode = S.sel?.type === 'node' && nodeEditable(S.sel.obj) && Math.hypot(S.sel.obj.xy[0] - x, S.sel.obj.xy[1] - y) <= E.hitHandle_px / v.k;
      canvas.style.cursor = hh || onNode ? (onNode || hh.kind === 'vtx' ? 'move' : 'grab') : S.hover ? 'pointer' : 'crosshair';
    } else canvas.style.cursor = 'crosshair';
    redraw();
  });
  const up = (e) => {
    const p = pts.get(e.pointerId) || local(e); pts.delete(e.pointerId);
    if (pts.size < 2) pinch = null;
    const g = gesture; if (pts.size) return; gesture = null;
    if (!g) return;
    if (S.npreview) { const { n, res } = S.npreview; S.npreview = null; S.drag = false; commitNodeMove(n, res); return; }
    if (S.preview) {   // commit a drag
      const pr = S.preview, id = pr.run.id; S.preview = null; S.drag = false;
      const same = pr.S.length === stOf(S.sel.obj).length; S.sel.vtx = g.handle.kind === 'vtx' && same ? g.handle.i : null; S.sel.seg = g.handle.kind === 'seg' && same ? g.handle.i : null;
      change(pr.run, `${id}: ${g.handle.kind === 'vtx' ? 'הזזת פינה' : 'הזזת מקטע'}`); return;
    }
    S.drag = false;
    if (g.moved >= E.dragThreshold_px * (g.touch ? 2 : 1)) return;
    const [x, y] = v.toLocal(...p);
    if (S.mode === 'draw') { addDraftPoint(S.snapOn ? snapAt(x, y) : { kind: 'free', x, y }); return; }
    if (g.handle) { S.sel.vtx = g.handle.kind === 'vtx' ? g.handle.i : null; S.sel.seg = g.handle.kind === 'seg' ? g.handle.i : null; showInfo(S.sel); redraw(); return; }
    const r = (cfg.snap.radius_px * (g.touch ? 1.8 : 1)) / v.k;
    const hit = hitTest(x, y, r, visibleItems(), pickNodes(), (k) => k === 'nodes' ? false : L.locked(k));
    S.sel = hit ? { ...hit, vtx: null, seg: null } : null; if (hit) showInfo(S.sel); else hideInfo(); redraw();
  };
  canvas.addEventListener('pointerup', up);
  canvas.addEventListener('pointercancel', (e) => { pts.delete(e.pointerId); gesture = null; pinch = null; S.preview = null; S.npreview = null; S.drag = false; redraw(); });
  canvas.addEventListener('pointerleave', () => { if (!gesture) { S.snap = null; S.hover = null; redraw(); } });
  canvas.addEventListener('dblclick', (e) => {
    const [x, y] = v.toLocal(...local(e));
    if (S.mode === 'draw') { finishDraft(); return; }
    const h = handleHit(x, y, false); if (!h || h.kind !== 'seg') return;
    const p = S.sel.obj, st = stOf(p), a = st[h.i], b = st[h.i + 1], dx = b.x - a.x, dy = b.y - a.y, t = ((x - a.x) * dx + (y - a.y) * dy) / (dx * dx + dy * dy);
    change(OP.fromStations(store.get(p.id), OP.insertStation(st, h.i, a.x + t * dx, a.y + t * dy), fr), `${p.id}: נקודה חדשה`); S.sel.vtx = h.i + 1; S.sel.seg = null;
  });
  canvas.addEventListener('wheel', (e) => { e.preventDefault(); const p = local(e); v.zoomAt(p[0], p[1], Math.exp(-e.deltaY * 0.0015)); redraw(); }, { passive: false });
  window.addEventListener('keydown', (e) => {
    if (e.target.closest('input,select,textarea')) return;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); e.shiftKey ? $('ed-redo').click() : $('ed-undo').click(); return; }
    if ((e.ctrlKey || e.metaKey) && k === 'y') { e.preventDefault(); $('ed-redo').click(); return; }
    if (k === 'f') { fitFloor(); redraw(); }
    if (k === 's') $('ed-snap-on').click();
    if (k === 'o') $('ed-ortho').click();
    if (k === 'n') setMode('draw');
    if (k === 'v') setMode('select');
    if (e.key === 'Enter' && S.draft) finishDraft();
    if (e.key === 'Delete' || e.key === 'Backspace') delVertex();
    if (e.key === 'Escape') { if (S.draft) { S.draft = null; syncDrawbar(); } else if (S.mode === 'draw') setMode('select'); else { S.sel = null; hideInfo(); } redraw(); }
    const i = ['1', '2', '3', '4'].indexOf(e.key); if (i >= 0 && cfg.floors[i]) setFloor(cfg.floors[i].id);
  });

  v.resize(); setFloor(S.floor); syncTools();
  $('ed-loading').classList.add('hidden');
  store.connect().then(() => refresh());
  // hooks for tests (tests/editor.mjs)
  window.__editor = { D, M, S, L, v, cfg, store, OP, CH, nodeRuns, moveNode, manifoldRows, handleHit: (x, y) => handleHit(x, y, false), issues: () => issues, floorIssues, checkRun, setFloor, setMode, current: () => cur, visibleItems, toScreen: (x, y) => [v.sx(x), v.sy(y)], showInfo, stOf, refresh };
  window.__editorReady = true;
}

start().catch(err => { console.error(err); window.__editorErrors.push(String(err)); $('ed-loading').textContent = 'שגיאה בטעינה: ' + err.message; });

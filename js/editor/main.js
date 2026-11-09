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
  M.setRuns(store.runs());
  const defaults = { 'cons.superseded': false, nodes: true, grid: true };
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
  const visibleItems = () => cur.items.filter(it => L.on(it.p.layer + '.' + it.p.system) && (it.p.layer !== 'cons' || !it.p.superseded || L.on('cons.superseded')));
  // edited only on the floor where it is drawn in plan (a riser passing through another floor is shown there, not edited)
  const editable = (p) => p && p.layer === 'prop' && store.canEdit && !L.locked('prop.' + p.system) && cur.items.some(it => it.mode === 'plan' && it.p.layer === 'prop' && it.p.id === p.id);
  const refresh = () => {   // rebuild after a store change, keep the selection by id
    M.setRuns(store.runs());
    const selId = S.sel?.type === 'pipe' ? S.sel.obj.id : null, selLayer = S.sel?.obj?.layer;
    cur.items = itemsOf(S.floor);
    if (selId) {
      const it = cur.items.find(i => i.p.id === selId && i.p.layer === selLayer);
      if (it) { S.sel.obj = it.p; if (S.sel.vtx != null && S.sel.vtx >= stOf(it.p).length) S.sel.vtx = null; showInfo(S.sel); } else { S.sel = null; hideInfo(); }
    }
    syncTools(); redraw();
  };
  store.onChange(() => { if (!S.drag) refresh(); else syncTools(); });
  const setFloor = (fid, fit = true) => {
    S.floor = fid; S.sel = null; S.draft = null; hideInfo();
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
    drawPipes(ctx, v, cfg, items, sys, selP, S.hover?.type === 'pipe' ? S.hover.obj : null);
    if (on('nodes')) drawNodes(ctx, v, cfg, cur.nodes, S.sel?.type === 'node' ? S.sel.obj : null, S.hover?.type === 'node' ? S.hover.obj : null);
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
      const n = hit.obj; title = `${n.id} – ${n.title || n.kind}`; src = n.source;
      rows.push(['סוג', n.kind], ['קומה', n.floor], ['גובה', n.H != null ? `${n.H.toFixed(2)} (${fmtRel(n.H - M.H0)})` : '–'], ['ITM', `E ${n.E.toFixed(3)} · N ${n.N.toFixed(3)}`]);
      if (n.D_mm) rows.push(['קוטר', `ø${n.D_mm}`]);
      if (n.cold != null) rows.push(['מים', [n.cold && 'קרים', n.hot && 'חמים'].filter(Boolean).join(' + ') || '–']);
      rows.push(['סטטוס', n.status]);
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
    return snapPoint(x, y, cfg.snap.radius_px / v.k, { step: S.step }, cur.F, items, L.on('nodes') ? cur.nodes : [], (k) => L.on(k));
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
    const h = S.mode === 'select' ? handleHit(x, y, touch) : null;
    gesture = { p0: p, p: p, moved: 0, xy0: [x, y], handle: h, touch };
  });
  canvas.addEventListener('pointermove', (e) => {
    const p = local(e); if (pts.has(e.pointerId)) pts.set(e.pointerId, p);
    if (pinch && pts.size === 2) { const [a, b] = [...pts.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]), m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; v.pan(m[0] - pinch.m[0], m[1] - pinch.m[1]); v.zoomAt(m[0], m[1], d / pinch.d); pinch = { d, m }; redraw(); return; }
    const [x, y] = v.toLocal(...p);
    if (gesture) {
      gesture.moved += Math.abs(p[0] - gesture.p[0]) + Math.abs(p[1] - gesture.p[1]);
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
      S.hover = hitTest(x, y, cfg.snap.radius_px / v.k, visibleItems(), L.on('nodes') ? cur.nodes : [], (k) => L.locked(k));
      const hh = handleHit(x, y, false); canvas.style.cursor = hh ? (hh.kind === 'vtx' ? 'move' : 'grab') : S.hover ? 'pointer' : 'crosshair';
    } else canvas.style.cursor = 'crosshair';
    redraw();
  });
  const up = (e) => {
    const p = pts.get(e.pointerId) || local(e); pts.delete(e.pointerId);
    if (pts.size < 2) pinch = null;
    const g = gesture; if (pts.size) return; gesture = null;
    if (!g) return;
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
    const hit = hitTest(x, y, r, visibleItems(), L.on('nodes') ? cur.nodes : [], (k) => L.locked(k));
    S.sel = hit ? { ...hit, vtx: null, seg: null } : null; if (hit) showInfo(S.sel); else hideInfo(); redraw();
  };
  canvas.addEventListener('pointerup', up);
  canvas.addEventListener('pointercancel', (e) => { pts.delete(e.pointerId); gesture = null; pinch = null; S.preview = null; S.drag = false; redraw(); });
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
  window.__editor = { D, M, S, L, v, cfg, store, OP, setFloor, setMode, current: () => cur, visibleItems, toScreen: (x, y) => [v.sx(x), v.sy(y)], showInfo, stOf, refresh };
  window.__editorReady = true;
}

start().catch(err => { console.error(err); window.__editorErrors.push(String(err)); $('ed-loading').textContent = 'שגיאה בטעינה: ' + err.message; });

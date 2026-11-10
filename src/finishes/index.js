import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Finishes layer (separate module): plaster by type, waterproofing of the wet rooms, tiling preparation, room names.
// Data (derived from the model geometry – tools/finishes/derive_finishes.py): data/finishes/plaster/surfaces.json,
// data/finishes/tiling/surfaces.json, data/architecture/rooms.json. Decisions: data/finishes/plaster/types.json
// (types, colours, parameters, prices), overrides.json (Avihai's type per surface). Changes made in the model are kept in
// the artifact database (collection "plaster", read by Claude with ArtifactData) – outside claude.ai in this browser.
// Display constants: data/config/display.json → finishes. No dimension is written here.

const LS = 'house3d.plaster';
const FLOOR_HE = { unit: 'יחידת דיור', ground: 'קרקע', first: "קומה א'", roof: 'גג', site: 'מגרש' };
const FACADE_HE = { N: 'צפון', E: 'מזרח', S: 'דרום', W: 'מערב' };
const TYPE_ROOM_HE = { dry: 'יבש', wet: 'רטוב', kitchen: 'מטבח', mamad: 'ממ"ד', basement: 'מרתף', stairs: 'חדר מדרגות', court: 'חצר אנגלית', outdoor: 'חוץ', unknown: 'לא מסווג' };
const CAT_HE = { wall: 'פני קיר', ceiling: 'תקרה', top: 'ראש קיר / מעקה' };
const f2 = (v) => (Math.round(v * 100) / 100).toLocaleString('he-IL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const hash = (s) => { let x = 2166136261; for (const c of s) { x ^= c.charCodeAt(0); x = Math.imul(x, 16777619); } return 'p' + (x >>> 0).toString(36); };
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'value') e.value = v; else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};

export function buildFinishes(ctx) {
  const { data, coords, registry, scene } = ctx;
  const P = data.plaster, T = data.plasterTypes, TL = data.tiling, R = data.rooms;
  if (!P || !T) return null;
  const D = data.display.finishes;
  const F = new Finishes(ctx, P, T, TL, R, D);
  F.build();
  return F;
}

class Finishes {
  constructor(ctx, P, T, TL, R, D) {
    Object.assign(this, { ctx, P, T, TL, R, D });
    this.types = T.types; this.typeBy = Object.fromEntries(T.types.map(t => [t.id, t]));
    this.rooms = Object.fromEntries(R.rooms.map(r => [r.key, r]));
    this.surf = [
      ...P.walls.map(s => ({ ...s, cat: 'wall', amount: s.net })),
      ...P.ceilings.map(s => ({ ...s, cat: 'ceiling', amount: s.net })),
      ...P.tops.map(s => ({ ...s, cat: 'top', amount: s.area })),
    ];
    this.byKey = Object.fromEntries(this.surf.map(s => [s.key, s]));
    this.live = {};          // overrides made in the model (db / this browser): key -> type
    this.prices = {};        // type / extra id -> price per unit
    this.items = []; this.sel = new THREE.Group(); ctx.scene.add(this.sel);
    try { const l = JSON.parse(localStorage.getItem(LS) || '{}'); this.live = l.live || {}; this.prices = l.prices || {}; } catch {}
    this.state = 'local';
    this.mats = {};
  }
  typeOf(s) { return this.live[s.key] ?? s.type; }
  overridden(s) { return this.live[s.key] != null ? this.live[s.key] !== s.defaultType : s.overridden; }
  mat(color, extra = {}) {
    const k = color + JSON.stringify(extra);
    return this.mats[k] ||= new THREE.MeshStandardMaterial({ color, roughness: this.D.roughness, metalness: 0, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2, ...extra });
  }
  // ITM + relative height -> scene
  V(E, N, z) { const c = this.ctx.coords; return [E - c.E0, z, -(N - c.N0)]; }

  // ---------------------------------------------------------------- geometry builders (positions + triangle -> surface map)
  wallTris(s, off, z0 = s.z0, z1 = s.z1, holes = s.openings) {
    const [ax, ay] = s.a, [bx, by] = s.b, L = Math.hypot(bx - ax, by - ay), ux = (bx - ax) / L, uy = (by - ay) / L;
    const [nx, ny] = s.normal;
    // grid of cells cut by the openings (robust where an opening reaches the face edge – doors)
    const us = [0, L], vs = [z0, z1];
    const hs = (holes || []).filter(o => o.z1 > z0 && o.z0 < z1);
    for (const o of hs) { us.push(Math.max(0, o.s0), Math.min(L, o.s1)); vs.push(Math.max(z0, o.z0), Math.min(z1, o.z1)); }
    const U = [...new Set(us.map(v => +v.toFixed(4)))].sort((a, b) => a - b), Z = [...new Set(vs.map(v => +v.toFixed(4)))].sort((a, b) => a - b);
    const out = [];
    const pt = (u, v) => this.V(ax + ux * u + nx * off, ay + uy * u + ny * off, v);
    for (let i = 0; i < U.length - 1; i++) for (let j = 0; j < Z.length - 1; j++) {
      const um = (U[i] + U[i + 1]) / 2, vm = (Z[j] + Z[j + 1]) / 2;
      if (hs.some(o => um > o.s0 && um < o.s1 && vm > o.z0 && vm < o.z1)) continue;
      const p00 = pt(U[i], Z[j]), p10 = pt(U[i + 1], Z[j]), p11 = pt(U[i + 1], Z[j + 1]), p01 = pt(U[i], Z[j + 1]);
      out.push(p00, p10, p11, p00, p11, p01);
    }
    return out;
  }
  ringTris(ring, holes, z) {
    const v2 = (r) => r.map(([x, y]) => new THREE.Vector2(x, y));
    const C = v2(ring), Hs = (holes || []).map(v2);
    if (THREE.ShapeUtils.isClockWise(C)) C.reverse();
    Hs.forEach(hh => { if (!THREE.ShapeUtils.isClockWise(hh)) hh.reverse(); });
    const all = [...C, ...Hs.flat()];
    const tri = THREE.ShapeUtils.triangulateShape(C, Hs);
    const out = [];
    for (const t of tri) for (const i of t) out.push(this.V(all[i].x, all[i].y, z));
    return out;
  }
  mesh(triPts, map, material) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(triPts.flat(), 3));
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, material); m.receiveShadow = true; m.userData.keep = true; m.userData.faceMap = map;
    return m;
  }

  build() {
    const { registry, scene } = this.ctx;
    const plasterLayers = this.types.map(t => 'plaster_' + t.id);
    registry.defer([...plasterLayers], () => this.buildPlaster());
    registry.defer(['waterproofing'], () => this.buildWaterproofing());
    registry.defer(['tilingPrep'], () => this.buildTiling());
    registry.defer(['roomLabels'], () => this.buildLabels());
  }
  add(obj, tags, meta) {
    this.ctx.scene.add(obj);
    const it = this.ctx.registry.add(obj, { system: 'finishes', stage: 'finishes', ...tags }, meta);
    this.items.push(it); return it;
  }
  buildPlaster() {
    const off = this.D.offset_m;
    const groups = {};
    for (const s of this.surf) {
      const ty = this.typeOf(s), fl = s.floor;
      const g = groups[ty + '|' + fl] ||= { ty, fl, pts: [], map: [] };
      const tris = s.cat === 'wall' ? this.wallTris(s, off) : s.cat === 'ceiling' ? this.ringTris(s.ringITM, s.holesITM, s.z - off) : this.ringTris(s.ringITM, [], s.z + off);
      for (let i = 0; i < tris.length; i += 3) { g.pts.push(tris[i], tris[i + 1], tris[i + 2]); g.map.push(s.key); }
    }
    this.plasterItems = [];
    for (const g of Object.values(groups)) {
      if (!g.pts.length) continue;
      const t = this.typeBy[g.ty];
      const m = this.mesh(g.pts, g.map, this.mat(t.color));
      const it = this.add(m, { floor: g.fl, step: 'plaster', layer: 'plaster_' + g.ty }, {
        name: `${t.label} – ${FLOOR_HE[g.fl]}`, kind: 'plaster', id: 'PL-' + g.ty + '-' + g.fl, pickable: true,
        rows: [], source: 'data/finishes/plaster/surfaces.json (נגזר מהגיאומטריה – tools/finishes/derive_finishes.py)',
        onClick: (hit) => this.pick(hit) });
      this.plasterItems.push(it);
    }
  }
  rebuildPlaster() {
    if (!this.plasterItems) return;   // never shown yet: built with the current types when first switched on
    this.ctx.registry.remove(this.plasterItems); this.items = this.items.filter(i => !this.plasterItems.includes(i));
    this.buildPlaster();
    this.app?.store && this.ctx.registry.apply(this.app.store.get());
    this.app?.viewer.invalidate();
  }
  buildWaterproofing() {
    const off = this.D.waterproofOffset_m, byFl = {};
    for (const w of this.P.waterproofing) {
      const g = byFl[w.floor] ||= { pts: [], map: [] };
      const tris = this.wallTris(w, off, w.z0, w.z1, []);
      for (let i = 0; i < tris.length; i += 3) { g.pts.push(tris[i], tris[i + 1], tris[i + 2]); g.map.push('wp:' + w.owner); }
    }
    for (const r of this.TL.rooms.filter(r => r.roomType === 'wet' && r.ringITM.length >= 3)) {
      const z = Math.min(...this.P.walls.filter(s => s.room === r.room).map(s => s.z0)) + off;
      const g = byFl[r.floor] ||= { pts: [], map: [] };
      const tris = this.ringTris(r.ringITM, [], z);
      for (let i = 0; i < tris.length; i += 3) { g.pts.push(tris[i], tris[i + 1], tris[i + 2]); g.map.push('wpf:' + r.room); }
    }
    for (const [fl, g] of Object.entries(byFl)) {
      const m = this.mesh(g.pts, g.map, this.mat(this.T.waterproofing.color));
      const a = this.P.waterproofing.filter(w => w.floor === fl);
      this.add(m, { floor: fl, step: 'wetProofing', layer: 'waterproofing' }, {
        name: `איטום חדרים רטובים – ${FLOOR_HE[fl]}`, kind: 'waterproofing', id: 'WP-' + fl,
        rows: [['קירות', `${f2(a.reduce((s, w) => s + w.area, 0))} מ"ר (${a.filter(w => w.shower).length} קירות מקלחת עד ${this.T.waterproofing.showerHeight_m} מ')`],
          ['רצפות', `${f2(this.TL.rooms.filter(r => r.floor === fl && r.roomType === 'wet').reduce((s, r) => s + r.area, 0))} מ"ר`],
          ['כלל', this.T.waterproofing.note]],
        source: 'data/finishes/plaster/surfaces.json → waterproofing', note: 'קירות המקלחת לפי מיקום נקודת המקלחת בתוכנית האינסטלציה – זמני עד סימון של אביחי' });
    }
  }
  buildTiling() {
    const off = this.D.tilingOffset_m, byFl = {};
    for (const r of this.TL.rooms) {
      if (r.ringITM.length < 3 || r.finishRel == null || ['court', 'outdoor'].includes(r.roomType)) continue;
      const g = byFl[r.floor] ||= { pts: [], map: [], rooms: [] };
      const tris = this.ringTris(r.ringITM, [], r.finishRel + off);
      for (let i = 0; i < tris.length; i += 3) { g.pts.push(tris[i], tris[i + 1], tris[i + 2]); g.map.push('tile:' + r.room); }
      g.rooms.push(r);
    }
    for (const [fl, g] of Object.entries(byFl)) {
      const m = this.mesh(g.pts, g.map, this.mat('#b0866a', { transparent: true, opacity: 0.85 }));
      this.add(m, { floor: fl, step: 'tiling', layer: 'tilingPrep' }, {
        name: `ריצוף (הכנה) – ${FLOOR_HE[fl]}`, kind: 'tiling', id: 'TL-' + fl,
        rows: [['שטח ריצוף', `${f2(g.rooms.reduce((s, r) => s + r.area, 0))} מ"ר`], ['פנלים', `${f2(g.rooms.reduce((s, r) => s + r.skirting_m, 0))} מ"א`],
          ['פני ריצוף', this.ctx.coords.fmtRel(g.rooms[0].finishRel)], ['סוג אריח', 'טרם הוחלט']],
        source: 'data/finishes/tiling/surfaces.json', onClick: (hit) => this.pickTile(hit) });
    }
  }
  buildLabels() {
    for (const r of this.R.rooms) {
      const ring = r.ringITM; let cx = 0, cy = 0; ring.forEach(([x, y]) => { cx += x; cy += y; }); cx /= ring.length; cy /= ring.length;
      const tl = this.TL.rooms.find(t => t.room === r.key);
      const z = (tl?.finishRel ?? Math.min(...this.P.walls.filter(s => s.room === r.key).map(s => s.z0).concat([0]))) + this.D.roomLabelHeight_m;
      const d = h('div', { class: 'lbl room' + (r.type === 'unknown' ? ' unk' : '') }, `${r.name || 'חדר ללא שם'} · ${TYPE_ROOM_HE[r.type] || r.type} · ${f2(r.area_m2)} מ"ר`);
      const o = new CSS2DObject(d); o.position.set(...this.V(cx, cy, z)); o.userData.annotation = true;
      const g = new THREE.Group(); g.add(o);
      this.add(g, { floor: r.floor, step: 'plaster', layer: 'roomLabels' }, { name: r.name || 'חדר', kind: 'room', pickable: false });
    }
  }

  // ---------------------------------------------------------------- selection
  surfaceAt(hit) { return this.byKey[hit.object.userData.faceMap?.[hit.faceIndex]]; }
  highlight(s) {
    this.sel.clear();
    if (s) {
      const tris = s.cat === 'wall' ? this.wallTris(s, this.D.offset_m * 1.6, s.z0, s.z1, []) : s.cat === 'ceiling' ? this.ringTris(s.ringITM, s.holesITM, s.z - this.D.offset_m * 1.6) : this.ringTris(s.ringITM, [], s.z + this.D.offset_m * 1.6);
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(tris.flat(), 3));
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(g, 1), new THREE.LineBasicMaterial({ color: this.D.selectColor, depthTest: false }));
      e.renderOrder = 30; this.sel.add(e);
    }
    this.app?.viewer.invalidate();
  }
  rowsOf(s) {
    const room = this.rooms[s.room], c = this.ctx.coords, ty = this.typeBy[this.typeOf(s)];
    const rows = [['משטח', `${CAT_HE[s.cat]}${s.cat === 'wall' ? (s.side === 'in' ? ' (פנים)' : ` (חוץ – חזית ${FACADE_HE[s.facade] || ''})`) : ''}`],
      ['קומה', FLOOR_HE[s.floor]], ['חדר', room ? `${room.name || 'ללא שם'} (${TYPE_ROOM_HE[room.type]})` : '—'],
      ['סוג טיח', `${ty.label}${this.overridden(s) ? ' · דריסה ידנית' : ' · ברירת מחדל'}`], ['כלל ברירת המחדל', `${this.typeBy[s.defaultType].label} – ${s.typeReason}`]];
    if (s.cat === 'wall') {
      rows.push(['רכיב', `${s.owner} (${({ block: 'בלוקים', concrete: 'בטון', column: 'עמוד' })[s.ownerKind] || s.ownerKind}${s.thickness ? `, ${Math.round(s.thickness * 100)} ס"מ` : ''})`],
        ['אורך × גובה', `${f2(s.length)} × ${f2(s.z1 - s.z0)} מ' (${c.fmtRel(s.z0)} עד ${c.fmtRel(s.z1)})`],
        ['ברוטו / פתחים / נטו', `${f2(s.gross)} / ${f2(s.openingsArea)} / ${f2(s.net)} מ"ר`]);
      if (s.openings.length) rows.push(['פתחים', s.openings.map(o => o.id).join(', ')]);
      if (s.meshV_m || s.meshH_m) rows.push(['רשת פיברגלס', `${f2((s.meshV_m || 0) + (s.meshH_m || 0))} מ"א`]);
      if (s.beads_m) rows.push(['זוויתנים', `${f2(s.beads_m)} מ"א`]);
    } else rows.push(['שטח', `${f2(s.amount)} מ"ר${s.beamSides ? ` (כולל דפנות קורות ${f2(s.beamSides)})` : ''}`], ['מפלס', c.fmtRel(s.z)]);
    rows.push(['פיגום', s.scaffold ? `דורש פיגום (מעל ${this.T.params.scaffoldAbove_m} מ') – ${f2(s.scaffoldArea || 0)} מ"ר מעל הגובה` : 'לא']);
    if (s.status === 'provisional') rows.push(['מעמד', 'זמני – ' + (s.zSource || '')]);
    rows.push(['מפתח', s.key]);
    return rows;
  }
  pick(hit) { const s = this.surfaceAt(hit); if (s) this.showSurface(s); }
  showSurface(s) {
    this.selected = s; this.highlight(s);
    const sel = h('select', { onchange: (e) => this.setType(s, e.target.value) }, this.types.map(t => { const o = h('option', { value: t.id }, t.label); if (t.id === this.typeOf(s)) o.selected = true; return o; }));
    const extra = h('div', { class: 'plaster-edit' }, h('b', {}, 'שינוי סוג: '), sel,
      this.overridden(s) ? h('button', { class: 'small', onclick: () => this.setType(s, s.defaultType) }, 'חזרה לברירת המחדל') : '',
      h('div', { class: 'muted' }, this.state === 'online' ? 'נשמר במסד הנתונים של הארטיפקט – קלוד יסנכרן לקובץ overrides.json' : 'נשמר בדפדפן הזה'));
    this.app.ui.showInfo({ title: `טיח · ${CAT_HE[s.cat]} · ${f2(s.amount)} מ"ר`, rows: this.rowsOf(s), source: s.source, extra });
  }
  pickTile(hit) {
    const k = hit.object.userData.faceMap?.[hit.faceIndex]?.slice(5); const r = this.TL.rooms.find(x => x.room === k); if (!r) return;
    const room = this.rooms[k];
    this.app.ui.showInfo({ title: `ריצוף (הכנה) · ${room?.name || 'חדר'}`, rows: [['קומה', FLOOR_HE[r.floor]], ['סוג חדר', TYPE_ROOM_HE[r.roomType]],
      ['שטח ריצוף', `${f2(r.area)} מ"ר`], ['פנלים (היקף פחות דלתות)', `${f2(r.skirting_m)} מ"א`], ['פני ריצוף', this.ctx.coords.fmtRel(r.finishRel)],
      ['חיפוי קירות', r.wallTiling ? 'נדרש – גובה טרם הוחלט' : '—'], ['סוג אריח', 'טרם הוחלט'], ['מפתח', r.room]], source: 'data/finishes/tiling/surfaces.json' });
  }

  // ---------------------------------------------------------------- persistence (artifact db, else this browser)
  saveLocal() { try { localStorage.setItem(LS, JSON.stringify({ live: this.live, prices: this.prices })); } catch {} }
  async connect() {
    const use = window.claude?.use; const db = use ? await use('db').catch(() => null) : null;
    if (!db) return;
    this.col = db.collection('plaster'); this.state = 'online';
    this.col.onSnapshot((snap) => {
      const live = {}; let prices = null;
      for (const d of snap.docs) { const x = d.data(); if (x.kind === 'prices') prices = x.prices; else if (x.key && x.type) live[x.key] = x.type; }
      const changed = JSON.stringify(live) !== JSON.stringify(this.live);
      this.live = live; if (prices) this.prices = prices; this.saveLocal();
      if (changed) this.rebuildPlaster();
      this.app.ui.refreshPanel('finishes');
    }, () => { this.state = 'local'; });
  }
  async setType(s, ty) {
    if (ty === s.type && this.live[s.key] == null) return;
    this.live[s.key] = ty; this.saveLocal();
    if (this.col) { try { await this.col.doc(hash(s.key)).set({ key: s.key, type: ty, defaultType: s.defaultType, at: new Date().toISOString() }); } catch { this.app.ui.toast('השמירה במסד נכשלה – נשמר בדפדפן'); } }
    this.rebuildPlaster(); this.showSurface(s); this.app.ui.refreshPanel('finishes');
  }
  async setPrice(id, v) {
    if (v === '' || v == null) delete this.prices[id]; else this.prices[id] = +v;
    this.saveLocal();
    if (this.col) { try { await this.col.doc('prices').set({ kind: 'prices', prices: this.prices, at: new Date().toISOString() }); } catch {} }
  }

  // ---------------------------------------------------------------- quantities
  totals() {
    const T = { byType: {}, byFloor: {}, byRoom: {}, byFacade: {}, scaffold: {} };
    const add = (o, k, ty, v) => { const x = (o[k] ||= {}); x[ty] = (x[ty] || 0) + v; };
    for (const s of this.surf) {
      const ty = this.typeOf(s);
      T.byType[ty] = (T.byType[ty] || 0) + s.amount;
      add(T.byFloor, s.floor, ty, s.amount);
      if (s.room) add(T.byRoom, s.room, ty, s.amount);
      if (s.cat === 'wall' && s.side === 'out' && s.facade) add(T.byFacade, s.facade, ty, s.amount);
      if (s.scaffoldArea) add(T.scaffold, s.floor, ty, s.scaffoldArea);
    }
    const rev = this.P.reveals.reduce((a, r) => a + r.area, 0);
    const mesh = this.P.walls.reduce((a, s) => a + (s.meshV_m || 0) + (s.meshH_m || 0), 0);
    const beads = this.P.walls.reduce((a, s) => a + (s.beads_m || 0), 0) + this.P.reveals.reduce((a, r) => a + (r.beads || 0), 0);
    const wpW = this.P.waterproofing.reduce((a, w) => a + w.area, 0), wpF = this.TL.rooms.filter(r => r.roomType === 'wet').reduce((a, r) => a + r.area, 0);
    T.extras = { reveals: rev, mesh, beads, waterproofing: wpW + wpF, waterproofWalls: wpW, waterproofFloors: wpF };
    T.tiling = { area: this.TL.rooms.filter(r => !['court', 'outdoor'].includes(r.roomType)).reduce((a, r) => a + r.area, 0), skirting: this.TL.rooms.reduce((a, r) => a + r.skirting_m, 0) };
    const price = (id) => this.prices[id];
    T.cost = { byType: {}, byFloor: {}, total: 0, missing: [] };
    for (const [ty, v] of Object.entries(T.byType)) { if (price(ty) == null) { if (ty !== 'none') T.cost.missing.push(this.typeBy[ty].label); continue; } T.cost.byType[ty] = v * price(ty); T.cost.total += v * price(ty); }
    for (const [fl, o] of Object.entries(T.byFloor)) T.cost.byFloor[fl] = Object.entries(o).reduce((a, [ty, v]) => a + (price(ty) != null ? v * price(ty) : 0), 0);
    for (const [id, v] of [['reveals', rev], ['mesh', mesh], ['beads', beads], ['waterproofing', wpW + wpF]]) { if (price(id) != null) T.cost.total += v * price(id); }
    return T;
  }

  // ---------------------------------------------------------------- panel (tab "טיח וריצוף")
  panel(ui) {
    const app = this.app, s = app.store.get(), T = this.totals();
    const setLayers = (patch) => app.store.set({ layers: { ...app.store.get().layers, ...patch } }, { label: 'layers' });
    const allPl = Object.fromEntries(this.types.map(t => ['plaster_' + t.id, true]));
    const anyOn = this.types.some(t => s.layers['plaster_' + t.id] !== false);
    const wrap = h('div', { class: 'finishes' });
    wrap.append(h('p', { class: 'muted' }, 'כל משטח קיר ותקרה נגזר מהגיאומטריה של המודל (קירות, פתחים, תקרות, קורות). הסוג נקבע לפי כללים (צד הקיר, סוג החדר) ואפשר לדרוס אותו: לחיצה על משטח במצב "מידות".'),
      h('div', { class: 'btns' },
        h('button', { class: anyOn ? 'on' : '', onclick: () => setLayers(anyOn ? Object.fromEntries(Object.keys(allPl).map(k => [k, false])) : allPl) }, anyOn ? 'הסתר טיח' : 'הצג טיח'),
        h('button', { class: s.layers.waterproofing !== false ? 'on' : '', onclick: () => setLayers({ waterproofing: s.layers.waterproofing === false }) }, 'איטום'),
        h('button', { class: s.layers.tilingPrep !== false ? 'on' : '', onclick: () => setLayers({ tilingPrep: s.layers.tilingPrep === false }) }, 'ריצוף (הכנה)'),
        h('button', { class: s.layers.roomLabels !== false ? 'on' : '', onclick: () => setLayers({ roomLabels: s.layers.roomLabels === false }) }, 'שמות חדרים')));
    // interior view: one floor, horizontal cut above its floor, no ceilings above
    const fls = ['unit', 'ground', 'first', 'roof'];
    const lvl = { unit: -2.6, ground: 0, first: 3.85, roof: 6.9 };
    wrap.append(h('div', { class: 'btns' }, h('span', { class: 'muted' }, 'מבט פנימי:'),
      fls.map(fl => h('button', { class: 'small', onclick: () => {
        const floors = Object.fromEntries(Object.entries(app.store.get().floors).map(([k, v]) => [k, { ...v, visible: k === fl }]));
        app.store.set({ floors, section: { ...app.store.get().section, hOn: true, hideBeams: true, hLevel: +(lvl[fl] + this.D.interiorCutAbove_m).toFixed(2) } }, { label: 'interior' });
      } }, FLOOR_HE[fl])),
      h('button', { class: 'small', onclick: () => {
        const floors = Object.fromEntries(Object.entries(app.store.get().floors).map(([k, v]) => [k, { ...v, visible: true }]));
        app.store.set({ floors, section: { ...app.store.get().section, hOn: false } }, { label: 'interior' });
      } }, 'הכול')));
    // legend + quantities + prices
    const priceIn = (id) => h('input', { type: 'number', min: 0, step: 1, class: 'price', placeholder: '₪', value: this.prices[id] ?? '', onchange: (e) => { this.setPrice(id, e.target.value); ui.refreshPanel('finishes'); } });
    const scaf = (ty) => Object.values(T.scaffold).reduce((a, o) => a + (o[ty] || 0), 0);
    wrap.append(h('h4', {}, 'מקרא וכמויות'), h('table', { class: 'qty' },
      h('tr', {}, h('th', {}, ''), h('th', {}, 'סוג'), h('th', {}, 'נטו מ"ר'), h('th', {}, 'מזה בפיגום'), h('th', {}, 'מחיר ליח\''), h('th', {}, 'עלות')),
      this.types.map(t => {
        const lid = 'plaster_' + t.id, on = s.layers[lid] !== false;
        return h('tr', {}, h('td', {}, h('label', { class: 'sw' }, h('input', { type: 'checkbox', checked: on, onchange: (e) => setLayers({ [lid]: e.target.checked }) }), h('i', { style: `background:${t.color}` }))),
          h('td', { title: `${t.applies} · שכבות: ${t.layers.join(' + ') || '—'}` }, t.label), h('td', {}, f2(T.byType[t.id] || 0)), h('td', {}, f2(scaf(t.id))),
          h('td', {}, priceIn(t.id)), h('td', {}, T.cost.byType[t.id] != null ? f2(T.cost.byType[t.id]) : '—'));
      }),
      [['waterproofing', this.T.waterproofing.label, T.extras.waterproofing, 'מ"ר'], ['reveals', 'ספלטות וגליפים', T.extras.reveals, 'מ"ר'], ['mesh', 'רשת פיברגלס (בלוק / בטון)', T.extras.mesh, 'מ"א'], ['beads', 'פינות מגן (זוויתנים)', T.extras.beads, 'מ"א']]
        .map(([id, label, v, u]) => h('tr', {}, h('td', {}, id === 'waterproofing' ? h('i', { class: 'swc', style: `background:${this.T.waterproofing.color}` }) : ''), h('td', {}, label), h('td', {}, `${f2(v)} ${u === 'מ"א' ? 'מ"א' : ''}`), h('td', {}, ''),
          h('td', {}, priceIn(id)), h('td', {}, this.prices[id] != null ? f2(v * this.prices[id]) : '—'))),
      h('tr', { class: 'tot' }, h('td', {}, ''), h('td', {}, 'סה"כ עלות'), h('td', {}, ''), h('td', {}, ''), h('td', {}, ''), h('td', {}, T.cost.total ? f2(T.cost.total) + ' ₪' : '—'))));
    if (T.cost.missing.length) wrap.append(h('div', { class: 'muted' }, 'חסר מחיר: ' + T.cost.missing.join(', ')));
    // by floor
    wrap.append(h('h4', {}, 'לפי קומה (מ"ר)'), h('table', { class: 'qty' },
      h('tr', {}, h('th', {}, 'קומה'), this.types.filter(t => T.byType[t.id]).map(t => h('th', {}, t.label)), h('th', {}, 'עלות')),
      Object.entries(T.byFloor).map(([fl, o]) => h('tr', {}, h('td', {}, FLOOR_HE[fl]), this.types.filter(t => T.byType[t.id]).map(t => h('td', {}, o[t.id] ? f2(o[t.id]) : '')), h('td', {}, T.cost.byFloor[fl] ? f2(T.cost.byFloor[fl]) : '—')))));
    wrap.append(h('h4', {}, 'טיח חוץ לפי חזית (מ"ר)'), h('table', { class: 'qty' },
      Object.entries(T.byFacade).sort().map(([fc, o]) => h('tr', {}, h('td', {}, FACADE_HE[fc]), h('td', {}, Object.entries(o).map(([ty, v]) => `${this.typeBy[ty].label}: ${f2(v)}`).join(' · '))))));
    wrap.append(h('h4', {}, 'ריצוף – הכנה'), h('div', {}, `שטח רצפות: ${f2(T.tiling.area)} מ"ר · פנלים: ${f2(T.tiling.skirting)} מ"א · סוגי אריחים וגובה חיפוי – טרם הוחלטו.`));
    // rooms
    wrap.append(h('h4', {}, 'לפי חדר'), h('table', { class: 'qty' },
      h('tr', {}, h('th', {}, 'קומה'), h('th', {}, 'חדר'), h('th', {}, 'סוג'), h('th', {}, 'רצפה מ"ר'), h('th', {}, 'טיח מ"ר')),
      this.R.rooms.map(r => { const o = T.byRoom[r.key] || {}; const tl = this.TL.rooms.find(x => x.room === r.key);
        return h('tr', {}, h('td', {}, FLOOR_HE[r.floor]), h('td', { title: r.key }, r.name || 'ללא שם'), h('td', { class: r.type === 'unknown' ? 'warn' : '' }, TYPE_ROOM_HE[r.type]),
          h('td', {}, f2(tl?.area || 0)), h('td', {}, Object.entries(o).map(([ty, v]) => `${this.typeBy[ty].label} ${f2(v)}`).join(' · '))); })));
    const nOv = this.surf.filter(x => this.overridden(x)).length;
    wrap.append(h('div', { class: 'btns' }, h('button', { onclick: () => this.exportXlsx() }, '⬇ ייצוא ל-Excel (xlsx)'),
      h('span', { class: 'muted' }, `${this.surf.length} משטחים · ${nOv} דריסות · ${this.state === 'online' ? 'השינויים נשמרים במסד הארטיפקט' : 'השינויים נשמרים בדפדפן הזה'}`)));
    return wrap;
  }

  // ---------------------------------------------------------------- Excel export (SheetJS, vendor/xlsx)
  async loadXlsx() {
    if (window.XLSX) return window.XLSX;
    await new Promise((res, rej) => { const sc = document.createElement('script'); sc.src = 'vendor/xlsx/xlsx.mini.min.js'; sc.onload = res; sc.onerror = rej; document.head.append(sc); });
    return window.XLSX;
  }
  async exportXlsx() {
    let X; try { X = await this.loadXlsx(); } catch { this.app.ui.toast('טעינת ספריית האקסל נכשלה'); return; }
    const T = this.totals(), wb = X.utils.book_new();
    const sheet = (name, rows) => { const ws = X.utils.aoa_to_sheet(rows); ws['!cols'] = rows[0].map(() => ({ wch: 16 })); ws['!views'] = [{ RTL: true }]; X.utils.book_append_sheet(wb, ws, name); };
    const tl = (id) => this.typeBy[id]?.label || id;
    sheet('סיכום', [['סוג', 'כמות', 'יחידה', 'מזה בפיגום', 'מחיר ליחידה', 'עלות'],
      ...this.types.map(t => [t.label, +(T.byType[t.id] || 0).toFixed(2), 'מ"ר', +Object.values(T.scaffold).reduce((a, o) => a + (o[t.id] || 0), 0).toFixed(2), this.prices[t.id] ?? '', T.cost.byType[t.id] != null ? +T.cost.byType[t.id].toFixed(2) : '']),
      [this.T.waterproofing.label, +T.extras.waterproofing.toFixed(2), 'מ"ר', '', this.prices.waterproofing ?? '', this.prices.waterproofing != null ? +(T.extras.waterproofing * this.prices.waterproofing).toFixed(2) : ''],
      ['ספלטות וגליפים', +T.extras.reveals.toFixed(2), 'מ"ר', '', this.prices.reveals ?? '', this.prices.reveals != null ? +(T.extras.reveals * this.prices.reveals).toFixed(2) : ''],
      ['רשת פיברגלס', +T.extras.mesh.toFixed(2), 'מ"א', '', this.prices.mesh ?? '', this.prices.mesh != null ? +(T.extras.mesh * this.prices.mesh).toFixed(2) : ''],
      ['פינות מגן', +T.extras.beads.toFixed(2), 'מ"א', '', this.prices.beads ?? '', this.prices.beads != null ? +(T.extras.beads * this.prices.beads).toFixed(2) : ''],
      ['סה"כ', '', '', '', '', +T.cost.total.toFixed(2)],
      [], ['ריצוף – שטח רצפות (הכנה)', +T.tiling.area.toFixed(2), 'מ"ר'], ['פנלים', +T.tiling.skirting.toFixed(2), 'מ"א']]);
    sheet('לפי קומה', [['קומה', ...this.types.map(t => t.label), 'עלות'], ...Object.entries(T.byFloor).map(([fl, o]) => [FLOOR_HE[fl], ...this.types.map(t => +(o[t.id] || 0).toFixed(2)), +(T.cost.byFloor[fl] || 0).toFixed(2)])]);
    sheet('חוץ לפי חזית', [['חזית', ...this.types.map(t => t.label)], ...Object.entries(T.byFacade).map(([fc, o]) => [FACADE_HE[fc], ...this.types.map(t => +(o[t.id] || 0).toFixed(2))])]);
    sheet('לפי חדר', [['קומה', 'חדר', 'סוג חדר', 'רצפה מ"ר', ...this.types.map(t => t.label)], ...this.R.rooms.map(r => { const o = T.byRoom[r.key] || {}; return [FLOOR_HE[r.floor], r.name || r.key, TYPE_ROOM_HE[r.type], +(this.TL.rooms.find(x => x.room === r.key)?.area || 0).toFixed(2), ...this.types.map(t => +(o[t.id] || 0).toFixed(2))]; })]);
    sheet('משטחים', [['מפתח', 'קומה', 'משטח', 'צד', 'חזית', 'חדר', 'רכיב', 'סוג', 'ברירת מחדל', 'דריסה', 'אורך', 'מגובה', 'עד גובה', 'ברוטו', 'פתחים', 'נטו', 'פיגום', 'שטח בפיגום', 'רשת מ"א', 'זוויתנים מ"א'],
      ...this.surf.map(s => [s.key, FLOOR_HE[s.floor], CAT_HE[s.cat], s.side === 'in' ? 'פנים' : s.side === 'out' ? 'חוץ' : '', FACADE_HE[s.facade] || '', this.rooms[s.room]?.name || '', s.owner || s.slab || '', tl(this.typeOf(s)), tl(s.defaultType), this.overridden(s) ? 'כן' : '',
        s.length ?? '', s.z0 ?? s.z, s.z1 ?? '', s.gross ?? s.amount, s.openingsArea ?? 0, +s.amount.toFixed(3), s.scaffold ? 'כן' : '', s.scaffoldArea || 0, +((s.meshV_m || 0) + (s.meshH_m || 0)).toFixed(3), s.beads_m || 0])]);
    sheet('גליפים', [['פתח', 'סוג', 'קומה', 'רוחב', 'גובה', 'עומק', 'היקף', 'שטח', 'זוויתנים'], ...this.P.reveals.map(r => [r.opening, r.kind, FLOOR_HE[r.floor], r.width, r.height, r.depth, r.perimeter, r.area, r.beads])]);
    sheet('איטום', [['קומה', 'חדר', 'רכיב', 'כלל', 'מגובה', 'עד גובה', 'שטח'], ...this.P.waterproofing.map(w => [FLOOR_HE[w.floor], this.rooms[w.room]?.name || w.room, w.owner, w.rule, w.z0, w.z1, w.area]),
      ...this.TL.rooms.filter(r => r.roomType === 'wet').map(r => [FLOOR_HE[r.floor], this.rooms[r.room]?.name || r.room, 'רצפה', 'רצפת חדר רטוב', '', '', r.area])]);
    sheet('ריצוף', [['קומה', 'חדר', 'סוג חדר', 'שטח מ"ר', 'פנלים מ"א', 'פני ריצוף', 'חיפוי קירות', 'סוג אריח'], ...this.TL.rooms.map(r => [FLOOR_HE[r.floor], this.rooms[r.room]?.name || r.room, TYPE_ROOM_HE[r.roomType], r.area, r.skirting_m, r.finishRel ?? '', r.wallTiling ? 'טרם הוחלט' : '', 'טרם הוחלט'])]);
    const name = 'plaster-tiling-5187.xlsx';
    const buf = X.write(wb, { type: 'array', bookType: 'xlsx' });
    const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    // inside claude.ai the frame cannot download directly: the downloads capability asks the viewer to save
    const dl = window.claude?.use ? await window.claude.use('downloads').catch(() => null) : null;
    if (dl) { try { await dl.save({ filename: name, data: blob }); } catch (e) { this.app.ui.toast(e?.code === 'declined' ? 'הייצוא בוטל' : 'הייצוא נכשל'); } return; }
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  attach(app) { this.app = app; this.connect(); }
}

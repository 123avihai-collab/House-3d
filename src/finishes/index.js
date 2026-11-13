import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { TilingWorkshop } from '../tiling/workshop.js';

// Finishes layer (separate module): cement plaster (one light grey – the plaster stage, not the finish), reveals and
// exposed beams, waterproofing of the wet rooms, the floor build-up (fill / screed / adhesive / tile placeholder),
// exterior cladding (own category, off) and room names.
// Data (derived from the model geometry – tools/finishes/derive_finishes.py): data/finishes/plaster/surfaces.json,
// data/finishes/tiling/surfaces.json, data/architecture/rooms.json. Decisions: data/finishes/plaster/types.json
// (types, colours, parameters, prices), overrides.json (Avihai's type per surface). Changes made in the model are kept in
// the artifact database (collection "plaster", read by Claude with ArtifactData) – outside claude.ai in this browser.
// Display constants: data/config/display.json → finishes. No dimension is written here.

const LS = 'house3d.plaster';
const FLOOR_HE = { unit: 'יחידת דיור', ground: 'קרקע', first: "קומה א'", roof: 'גג', site: 'מגרש' };
const FACADE_HE = { N: 'צפון', E: 'מזרח', S: 'דרום', W: 'מערב' };
const TYPE_ROOM_HE = { dry: 'יבש', wet: 'רטוב', kitchen: 'מטבח', mamad: 'ממ"ד', basement: 'מרתף', stairs: 'חדר מדרגות', court: 'חצר אנגלית', outdoor: 'חוץ', balcony: 'מרפסת', unknown: 'לא מסווג' };
const CAT_HE = { wall: 'פני קיר', ceiling: 'תקרה', top: 'ראש קיר / מעקה', reveal: 'גליף (צדי פתח / משקוף)', beam: 'קורה גלויה', patch: 'השלמה (אדן / שפה / קצה / תחתית)', filler: 'מילוי תצוגה (סדק מ"מ, לא בכמויות)' };
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
  const P = data.plaster, T = data.plasterTypes, TL = data.tiling, R = data.rooms; ctx.cladding = data.cladding;
  if (!P || !T) return null;
  const D = data.display.finishes;
  // doorway strips (floor in the wall thickness under the doors – tools/finishes/door_strips.py): each joins its zone as
  // one more part, so the floor build-up and the tiles continue through the door (Avihai 13.11.2026)
  for (const s of data.tilingDoorStrips?.strips || []) {
    const r = TL.rooms.find(x => x.room === s.room); if (!r || r.parts.some(p => p.doorStrip === s.id)) continue;
    r.parts.push({ ringITM: s.ringITM, holesITM: [], doorStrip: s.id });
    r.doorStrips_m2 = +((r.doorStrips_m2 || 0) + s.area_m2).toFixed(3); r.area = +(r.area + s.area_m2).toFixed(3);
  }
  const F = new Finishes(ctx, P, T, TL, R, D);
  if (data.tilingCatalog) F.tiling = new TilingWorkshop(F);   // tiling workshop (src/tiling): the tile layer of the floor build-up
  F.build();
  return F;
}

class Finishes {
  constructor(ctx, P, T, TL, R, D) {
    Object.assign(this, { ctx, P, T, TL, R, D });
    this.types = T.types; this.typeBy = Object.fromEntries(T.types.map(t => [t.id, t]));
    this.drawn = T.types.filter(t => t.drawn !== false);   // plaster that is shown (no plaster on membrane / cladding / neighbour side)
    this.CL = ctx.cladding; this.BU = TL.buildUp;
    this.rooms = Object.fromEntries(R.rooms.map(r => [r.key, r]));
    this.surf = [
      ...P.walls.map(s => ({ ...s, cat: 'wall', amount: s.net })),
      ...P.ceilings.map(s => ({ ...s, cat: 'ceiling', amount: s.net })),
      ...P.tops.map(s => ({ ...s, cat: 'top', amount: s.area })),
      ...(P.reveals || []).map(s => ({ ...s, cat: 'reveal', amount: s.area })),
      ...(P.beams || []).map(s => ({ ...s, cat: 'beam', amount: s.area })),
      ...(P.patches || []).map(s => ({ ...s, cat: 'patch', amount: s.area })),   // round 4: the exposed skin nothing else covers (tools/finishes/skin.py)
      ...(P.fillers || []).map(s => ({ ...s, cat: 'filler', amount: 0 })),       // display only: mm slits between pieces (tools/finishes/flatten.py)
    ];
    this.byKey = Object.fromEntries(this.surf.map(s => [s.key, s]));
    this.live = {};          // overrides made in the model (db / this browser): key -> type
    this.prices = {};        // type / extra id -> price per unit
    this.items = []; this.sel = new THREE.Group(); ctx.scene.add(this.sel);
    const W = T.waterproofing; this.wpDef = { wet: W.wetRoomHeight_m, shower: W.showerHeight_m };
    this.wpH = { ...this.wpDef };   // waterproofing heights – defaults from types.json (provisional), changed from the layers panel
    try { const l = JSON.parse(localStorage.getItem(LS) || '{}'); this.live = l.live || {}; this.prices = l.prices || {}; if (l.wp) this.wpH = { ...this.wpH, ...l.wp }; } catch {}
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
  // s.shift: the plaster brought forward to the plane of its wall surface (tools/finishes/flatten.py – one plane, varying
  // thickness); s.ext: [at a, at b] – the face extended to meet the next one at an outer corner (no slit)
  wallTris(s, off, z0 = s.z0, z1 = s.z1, holes = s.openings) {
    const [ax, ay] = s.a, [bx, by] = s.b, L = Math.hypot(bx - ax, by - ay), ux = (bx - ax) / L, uy = (by - ay) / L;
    const [nx, ny] = s.normal; off += s.shift || 0;
    // + a hair of overlap at every edge (display.json seamOverlap_m): neighbouring sheets do not share vertices – without it
    // the joint rasterises with pin-holes (a dotted dark line)
    const ov = this.D.seamOverlap_m || 0, ea = Math.max(ov, s.ext?.[0] || 0), eb = Math.max(ov, s.ext?.[1] || 0);
    // grid of cells cut by the openings (robust where an opening reaches the face edge – doors)
    const us = [-ea, L + eb], vs = [z0 - ov, z1 + ov];
    const hs = (holes || []).filter(o => o.z1 > z0 && o.z0 < z1);
    for (const o of hs) { us.push(Math.max(-ea, o.s0), Math.min(L + eb, o.s1)); vs.push(Math.max(z0 - ov, o.z0), Math.min(z1 + ov, o.z1)); }
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
  quadTris(q, off = 0, n = null) {   // q: 4 corners [E, N, z]; optional offset along a plan normal
    const P = q.map(([E, N, z]) => this.V(E + (n ? n[0] * off : 0), N + (n ? n[1] * off : 0), z));
    return [P[0], P[1], P[2], P[0], P[2], P[3]];
  }
  // the strip a head / sill / ledge gains up to the plane of a wall face brought forward (tools/finishes/flatten.py)
  growTris(s, z) { return (s.grow || []).flatMap(r => this.ringTris(r, [], z)); }
  surfTris(s, off) {
    if (s.hidden) return [];   // a step face inside the thickened plaster (one plane – tools/finishes/flatten.py): in the quantities, not drawn
    if (s.cat === 'wall') return this.wallTris(s, off);
    if (s.cat === 'ceiling') return this.ringTris(s.ringITM, s.holesITM, s.z - off);
    if (s.cat === 'top') return [...this.ringTris(s.ringITM, s.holesITM || [], s.z + off), ...this.growTris(s, s.z + off)];
    if (s.cat === 'reveal') return s.quads.flatMap(q => this.quadTris(q.q));
    if (s.cat === 'filler') return this.wallTris(s, off, s.z0, s.z1, []);
    if (s.cat === 'patch') return s.vertical ? this.wallTris(s, off, s.z0, s.z1, []) : [...this.ringTris(s.ringITM, s.holesITM, s.up ? s.z + off : s.z - off), ...this.growTris(s, s.up ? s.z + off : s.z - off)];
    if (s.cat === 'beam') return [...s.sides.filter(x => !x.hidden).flatMap(x => this.wallTris(x, off, x.z0, x.z1, [])),
      ...s.flats.flatMap(x => { const z = x.part === 'soffit' ? x.z - off : x.z + off; return [...this.ringTris(x.ringITM, [], z), ...this.growTris(x, z)]; })];
    return [];
  }
  mesh(triPts, map, material) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(triPts.flat(), 3));
    g.computeVertexNormals();
    // casts too: the sheets close the mm slits between the skeleton pieces in the shadow map (else sun lines on a shaded facade)
    const m = new THREE.Mesh(g, material); m.receiveShadow = true; m.castShadow = true; m.userData.keep = true; m.userData.faceMap = map;
    return m;
  }

  build() {
    const { registry, scene } = this.ctx;
    const plasterLayers = this.drawn.map(t => 'plaster_' + t.id);
    registry.defer([...plasterLayers], () => this.buildPlaster());
    registry.defer(['wetProofing'], () => this.buildWaterproofing());
    registry.defer(this.BU.layers.map(l => l.id), () => this.buildFloors());
    registry.defer((this.CL?.kinds || []).map(k => k.id), () => this.buildCladding());
    registry.defer(['roomLabels'], () => this.buildLabels());
    if (this.ctx.data.droppedCeiling) registry.defer(['droppedCeiling'], () => this.buildDropped());
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
      if (this.typeBy[ty]?.drawn === false) continue;   // no plaster there (membrane, cladding, neighbour side, "ללא")
      const g = groups[ty + '|' + fl] ||= { ty, fl, pts: [], map: [], over: {} };
      // overhead plaster (ceiling, soffit, exposed beam) hangs a few mm under its slab / beam: a horizontal cut just under the
      // slab removed the concrete but left the plaster sheet over the whole room (Avihai 13.11.2026). It is kept as separate
      // pieces that are hidden together with the concrete above them (syncOverhead)
      const o = this.overheadOf(s);
      const dst = o ? (g.over[o.key] ||= { ...o, pts: [], map: [] }) : g;
      const tris = this.surfTris(s, off);
      for (let i = 0; i < tris.length; i += 3) { dst.pts.push(tris[i], tris[i + 1], tris[i + 2]); dst.map.push(s.key); }
    }
    this.plasterItems = []; this.overhead = [];
    for (const g of Object.values(groups)) {
      const over = Object.values(g.over).filter(o => o.pts.length);
      if (!g.pts.length && !over.length) continue;
      const t = this.typeBy[g.ty];
      const m = this.mesh(g.pts, g.map, this.mat(t.color));
      for (const o of over) {
        const c = this.mesh(o.pts, o.map, m.material); c.userData.overhead = o; m.add(c); this.overhead.push(c);
      }
      const it = this.add(m, { floor: g.fl, step: 'plaster', layer: 'plaster_' + g.ty }, {
        name: `${t.label} – ${FLOOR_HE[g.fl]}`, kind: 'plaster', id: 'PL-' + g.ty + '-' + g.fl, pickable: true,
        rows: [], source: 'data/finishes/plaster/surfaces.json (נגזר מהגיאומטריה – tools/finishes/derive_finishes.py)', note: this.T.scratchNote,
        onClick: (hit) => this.pick(hit) });
      this.plasterItems.push(it);
    }
  }
  // the concrete a downward-facing plaster surface hangs from: { key, z } (slab bottom – ceilings, soffit patches) or
  // { key, beam, bottom, top } (an exposed beam: follows that beam's concrete)
  overheadOf(s) {
    if (s.cat === 'ceiling') return { key: 'z' + s.z.toFixed(3), z: s.z };
    if (s.cat === 'patch' && !s.vertical && !s.up && s.part === 'soffit') return { key: 'z' + s.z.toFixed(3), z: s.z };
    if (s.cat === 'beam') return { key: 'b' + s.beam + '@' + s.bottom.toFixed(3), beam: s.beam, bottom: s.bottom, top: s.top, z: s.bottom };
    return null;
  }
  // after every visibility change: overhead plaster shows only while the concrete above it does
  //  · a horizontal cut at or under the slab bottom / beam bottom removes the slab / beam – and its plaster
  //  · an exposed beam follows its concrete beam (hidden with "הסתר את הקורות של הקומה החתוכה", the floors tab switches, steps)
  //  · a ceiling follows the "תקרה" switch of the floors tab (the slab layer whose underside is at that level)
  syncOverhead() {
    const app = this.app; if (!app) return;
    // the dropped ceiling sheet: hidden while its own floor is cut horizontally (its edge line stays – where the ceiling is)
    if (this.dropItems?.length) {
      const sec0 = app.store.get().section || {}, cf = sec0.hOn ? app.tools.section?.floorAt(sec0.hLevel)?.id : null;
      for (const it of this.dropItems) it.object.traverse(o => { if (o.userData.dropSheet) o.visible = cf !== it.tags.floor; });
    }
    if (!this.overhead?.length) return;
    const st = app.store.get(), sec = st.section || {}, cut = sec.hOn ? sec.hLevel : Infinity, eps = 0.003;
    const reg = this.ctx.registry;
    if (!this._beamIdx) {   // concrete beams by name, with their height range (built once – beams are not deferred)
      this._beamIdx = {}; const b = new THREE.Box3();
      for (const it of reg.items) {
        if (!/Beams$/.test(it.tags.layer) || it.tags.system !== 'structure') continue;
        const id = String(it.meta.name || '').split(/[ ·]/)[0]; if (!id) continue;
        b.setFromObject(it.object); if (b.isEmpty()) continue;
        (this._beamIdx[id] ||= []).push({ it, y0: b.min.y, y1: b.max.y });
      }
    }
    if (!this._slabAt) {   // slab underside level -> the slab items there (the "תקרה" switch hides them)
      this._slabAt = []; const b = new THREE.Box3();
      const L = new Set(app.data.display.sectionCut?.wallCut?.ceilingSlabLayers || []);
      for (const it of reg.items) if (L.has(it.tags.layer)) { b.setFromObject(it.object); if (!b.isEmpty()) this._slabAt.push({ it, y0: b.min.y, y1: b.max.y }); }
    }
    for (const c of this.overhead) {
      const o = c.userData.overhead;
      let on = cut > o.z + eps;
      if (on && o.beam) {
        const cand = (this._beamIdx[o.beam] || []).filter(x => x.y0 < o.top - 0.01 && x.y1 > o.bottom + 0.01);
        if (cand.length) on = cand.some(x => x.it.object.visible);
      } else if (on) {
        const sl = this._slabAt.filter(x => Math.abs(x.y0 - o.z) < 0.02);
        if (sl.length) on = sl.some(x => x.it.object.visible);
      }
      c.visible = on;
    }
  }
  // ---------------------------------------------------------------- dropped ceiling (provisional – data/finishes/dropped-ceiling.json)
  // the gypsum ceiling of a floor at its height (editable in the model: state.dropCeiling overrides the data value); the area =
  // the floor's own ceilings (under the slab above it – not the double-height void) minus the excluded room types (mamad)
  dropHeight(fl) {
    const o = this.app?.store.get().dropCeiling?.[fl];
    return o != null ? o : this.ctx.data.droppedCeiling.floors[fl]?.height_rel;
  }
  buildDropped() {
    const DC = this.ctx.data.droppedCeiling, tags = this.ctx.data.tags.floors;
    this.dropItems = [];
    for (const [fl, cfg] of Object.entries(DC.floors)) {
      const hh = this.dropHeight(fl); if (hh == null) continue;
      const lv = tags.find(f => f.id === fl)?.level, above = tags.filter(f => f.level != null && f.level > lv).map(f => f.level).sort((a, b) => a - b)[0] ?? Infinity;
      const ex = new Set(cfg.excludeRoomTypes || []);
      const ceils = this.P.ceilings.filter(c => c.floor === fl && c.z < above && !ex.has(c.roomType));
      if (!ceils.length) continue;
      const pts = [], map = [], lines = [];
      for (const c of ceils) {
        const tris = this.ringTris(c.ringITM, c.holesITM, hh);
        for (let i = 0; i < tris.length; i += 3) { pts.push(tris[i], tris[i + 1], tris[i + 2]); map.push(c.key); }
        for (const r of [c.ringITM, ...(c.holesITM || [])]) r.forEach((q, i) => { const n = r[(i + 1) % r.length]; lines.push(...this.V(q[0], q[1], hh - 0.003), ...this.V(n[0], n[1], hh - 0.003)); });
      }
      const grp = new THREE.Group();
      const sheet = this.mesh(pts, map, this.mat(this.D.droppedCeilingColor)); sheet.userData.dropSheet = true; grp.add(sheet);
      const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.Float32BufferAttribute(lines, 3));
      const ls = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ color: this.D.droppedCeilingEdge })); ls.userData.keep = true; grp.add(ls);
      const area = ceils.reduce((a, c) => a + c.area, 0), c = this.ctx.coords;
      const it = this.add(grp, { floor: fl, step: 'finishes', layer: 'droppedCeiling' }, {
        name: `הנמכת תקרה – ${FLOOR_HE[fl]} (זמני)`, kind: 'droppedCeiling', id: 'DC-' + fl, status: 'provisional', pickable: true,
        source: `data/finishes/dropped-ceiling.json – ${cfg.source}`,
        rows: [['גובה תחתית ההנמכה', `${c.fmtRel(hh)} (${(hh + c.H0).toFixed(2)})`], ['מקום מעל ההנמכה', ceils.map(x => x.z).filter((v, i, a) => a.indexOf(v) === i).map(z => `${Math.round((z - hh) * 100)} ס"מ (תקרה ${c.fmtRel(z)})`).join(' · ')],
          ['שטח', `${f2(area)} מ"ר`], ['סטטוס', '⚠ זמני – אין גובה הנמכה בתוכניות (open-issues)']],
        onClick: () => this.showDropped(fl) });
      this.dropItems.push(it);
    }
  }
  showDropped(fl) {
    const c = this.ctx.coords, hh = this.dropHeight(fl), base = this.ctx.data.droppedCeiling.floors[fl].height_rel;
    const inp = h('input', { type: 'number', step: 0.01, value: hh.toFixed(2), style: 'width:6em' });
    const extra = h('div', { class: 'plaster-edit' }, h('b', {}, 'גובה ההנמכה (יחסית ל-±0.00): '), inp,
      h('button', { class: 'small', onclick: () => this.setDrop(fl, +inp.value) }, 'עדכן'),
      hh !== base ? h('button', { class: 'small', onclick: () => this.setDrop(fl, null) }, `חזרה ל-${c.fmtRel(base)}`) : '',
      h('div', { class: 'muted' }, 'נשמר בהגדרות התצוגה שלך (גם בקישור 🔗). ערך הבסיס – data/finishes/dropped-ceiling.json.'));
    const it = this.dropItems?.find(x => x.meta.id === 'DC-' + fl);
    this.app.ui.showInfo({ title: it?.meta.name || 'הנמכת תקרה', rows: it?.meta.rows || [], source: it?.meta.source, extra });
  }
  setDrop(fl, v) {
    if (v != null && !Number.isFinite(v)) return;
    const st = this.app.store.get(), cur = { ...(st.dropCeiling || {}) };
    if (v == null) delete cur[fl]; else cur[fl] = +v.toFixed(3);
    this.app.store.set({ dropCeiling: cur }, { label: 'dropCeiling' });
  }
  rebuildDropped() {
    if (!this.dropItems) return;   // not shown yet: built with the current heights when first switched on
    this.ctx.registry.remove(this.dropItems); this.items = this.items.filter(i => !this.dropItems.includes(i));
    this.buildDropped();
    this.ctx.registry.apply(this.app.store.get());
    if (this.app.ui.app && document.querySelector('#info:not(.hidden)')) { const fl = this.dropItems[0]?.tags.floor; if (fl) this.showDropped(fl); }
    this.app.viewer.invalidate();
  }
  rebuildPlaster() {
    if (!this.plasterItems) return;   // never shown yet: built with the current types when first switched on
    this.ctx.registry.remove(this.plasterItems); this.items = this.items.filter(i => !this.plasterItems.includes(i));
    this.buildPlaster();
    this.app?.store && this.ctx.registry.apply(this.app.store.get());
    this.app?.viewer.invalidate();
  }
  buildWaterproofing() {
    const W = this.T.waterproofing, off = this.D.waterproofOffset_m, byFl = {};
    const lineMat = new THREE.LineBasicMaterial({ color: W.colorFloor });
    const all = this.wpAll(); this.wpItems = [];
    for (const w of all) {
      const g = byFl[w.floor] ||= { wall: [], wmap: [], floor: [], fmap: [], lines: [], labels: [] };
      if (w.kind === 'floor') {
        const tris = this.ringTris(w.ringITM, w.holesITM, w.z + 0.002);
        for (let i = 0; i < tris.length; i += 3) { g.floor.push(tris[i], tris[i + 1], tris[i + 2]); g.fmap.push('wpf:' + w.room); }
        continue;
      }
      const tris = this.wallTris(w, off, w.z0, w.z1, w.openings || []);
      for (let i = 0; i < tris.length; i += 3) { g.wall.push(tris[i], tris[i + 1], tris[i + 2]); g.wmap.push('wp:' + w.owner); }
      // the top edge of the waterproofing on the wall + its height
      const o2 = off * 1.4 + (w.shift || 0), [nx, ny] = w.normal;
      const A = this.V(w.a[0] + nx * o2, w.a[1] + ny * o2, w.z1), B = this.V(w.b[0] + nx * o2, w.b[1] + ny * o2, w.z1);
      g.lines.push(...A, ...B);
      if (Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]) > 0.35) g.labels.push({ p: A.map((v, i) => (v + B[i]) / 2), t: w.label });
    }
    for (const [fl, g] of Object.entries(byFl)) {
      const grp = new THREE.Group();
      // a bold colour (data: types.json waterproofing) with a little glow, so it reads over the plaster / blocks
      if (g.wall.length) { const m = this.mesh(g.wall, g.wmap, this.mat(W.colorWall, { emissive: W.colorWall, emissiveIntensity: this.D.waterproofGlow })); grp.add(m); }
      if (g.floor.length) { const m = this.mesh(g.floor, g.fmap, this.mat(W.colorFloor, { emissive: W.colorFloor, emissiveIntensity: this.D.waterproofGlow })); grp.add(m); }
      if (g.lines.length) {
        const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.Float32BufferAttribute(g.lines, 3));
        const ls = new THREE.LineSegments(lg, lineMat); ls.userData.keep = true; grp.add(ls);
      }
      for (const L of g.labels) { const d = h('div', { class: 'lbl wp' }, L.t); const o = new CSS2DObject(d); o.position.set(L.p[0], L.p[1] + 0.03, L.p[2]); grp.add(o); }
      const a = all.filter(w => w.floor === fl);
      const it = this.add(grp, { floor: fl, step: 'wetProofing', layer: 'wetProofing' }, {
        name: `איטום חדרים רטובים – ${FLOOR_HE[fl]}`, kind: 'waterproofing', id: 'WP-' + fl,
        rows: [['חומר', W.label], ['קירות', `${f2(a.filter(w => w.kind === 'wall').reduce((s, w) => s + w.area, 0))} מ"ר – ${Math.round(this.wpH.wet * 100)} ס"מ מפני הריצוף, אזור המקלחת עד ${f2(this.wpH.shower)} מ'`],
          ['גבהים', `זמני – ברירת מחדל ${Math.round(this.wpDef.wet * 100)} ס"מ / ${f2(this.wpDef.shower)} מ'; שינוי: שכבות ← איטום`],
          ['רצפות', `${f2(a.filter(w => w.kind === 'floor').reduce((s, w) => s + w.area, 0))} מ"ר – כל רצפת החדר`], ['כלל', W.note]],
        source: 'data/finishes/plaster/surfaces.json → waterproofing', status: 'provisional', note: 'גבהים זמניים (open-issues #166). אזור המקלחת – ±0.9 מ\' לאורך הקיר מנקודת המקלחת בתוכנית האינסטלציה (זמני, #156)' });
      this.wpItems.push(it);
    }
  }
  // the floor build-up over the slab: fill / screed / adhesive / tile placeholder – one layer each (no plaster on floors)
  buildFloors() {
    const byLayer = {}; const n0 = this.items.length;
    for (const r of this.TL.rooms) for (const l of r.layers || []) for (const p of r.parts) {
      if (l.id === 'floorTile' && this.tiling?.has(r.room)) continue;   // tiles chosen in the workshop – drawn by src/tiling instead of the placeholder
      const g = byLayer[l.id + '|' + r.floor] ||= { l, fl: r.floor, pts: [], map: [], rooms: new Set() };
      const top = this.ringTris(p.ringITM, p.holesITM, l.z1), bot = this.ringTris(p.ringITM, p.holesITM, l.z0 + 0.0005);
      const ring = p.ringITM, sides = [];
      for (let i = 0; i < ring.length; i++) { const a = ring[i], b = ring[(i + 1) % ring.length];
        sides.push(...this.quadTris([[a[0], a[1], l.z0], [b[0], b[1], l.z0], [b[0], b[1], l.z1], [a[0], a[1], l.z1]])); }
      for (const t of [top, bot, sides]) for (let i = 0; i < t.length; i += 3) { g.pts.push(t[i], t[i + 1], t[i + 2]); g.map.push('floor:' + r.room); }
      g.rooms.add(r.room);
    }
    const def = Object.fromEntries(this.BU.layers.map(l => [l.id, l]));
    for (const g of Object.values(byLayer)) {
      const d = def[g.l.id];
      // a textured layer (the sumsum + sand fill: small stones – data/materials/materials.json) gets UVs in metres:
      // top / bottom faces from plan, sides along the edge – so the layer is recognisable in a section / interior view
      const tex = d.material ? this.ctx.materials.get(d.material) : null; if (tex) tex.side = THREE.DoubleSide;
      // no polygon offset on the floor layers: stacked 0.5–4 cm apart, an offset made the lower layer (adhesive / screed) win over the tile from a distance
      const mat = tex || (d.color ? this.mat(d.color, { polygonOffset: false }) : this.mat('#ffffff', { transparent: true, opacity: 0.12, depthWrite: false, polygonOffset: false }));
      const m = this.mesh(g.pts, g.map, mat);
      if (tex) {
        const P = m.geometry.attributes.position.array, N = m.geometry.attributes.normal.array, uv = new Float32Array(P.length / 3 * 2);
        for (let i = 0, k = 0; i < P.length; i += 3, k += 2) {
          if (Math.abs(N[i + 1]) > 0.5) { uv[k] = P[i]; uv[k + 1] = P[i + 2]; } else { uv[k] = Math.abs(N[i]) > Math.abs(N[i + 2]) ? P[i + 2] : P[i]; uv[k + 1] = P[i + 1]; }
        }
        m.geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
      }
      const grp = new THREE.Group(); grp.add(m);
      if (!d.color) { const e = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 30), new THREE.LineBasicMaterial({ color: '#90a4ae' })); e.userData.keep = true; grp.add(e); }
      const rs = this.TL.rooms.filter(r => g.rooms.has(r.room)), area = rs.reduce((a, r) => a + r.area, 0);
      this.add(grp, { floor: g.fl, step: 'tiling', layer: g.l.id }, {
        name: `${d.label} – ${FLOOR_HE[g.fl]}`, kind: 'floorLayer', id: g.l.id + '-' + g.fl,
        rows: [['שכבה', d.label], ['שטח', `${f2(area)} מ"ר`], ['עובי', `${f2(g.l.thickness_m * 100)} ס"מ (${d.status === 'placeholder' ? 'מקום שמור' : 'זמני'})`],
          ['נפח', `${f2(area * g.l.thickness_m)} מ"ק`], ['סדר', 'יציקה → סומסום → טיט / מדה → דבק → אריח']],
        source: 'data/finishes/floors/buildup.json; data/finishes/tiling/surfaces.json', note: this.BU._doc });
    }
    this.tiling?.build3D();
    this.floorItems = this.items.slice(n0);
  }
  // the floor layers again (a tile chosen / changed in the workshop): placeholder + tiles
  rebuildFloors() {
    if (!this.floorItems) return;
    this.ctx.registry.remove(this.floorItems); this.items = this.items.filter(i => !this.floorItems.includes(i));
    if (this.tiling) this.tiling.items = [];
    this.buildFloors();
    this.app?.store && this.ctx.registry.apply(this.app.store.get());
    this.app?.viewer.invalidate();
  }
  // exterior cladding – own category (off): known items only (the street side of the street wall – stone)
  buildCladding() {
    for (const k of this.CL?.kinds || []) {
      const it = this.CL.items.filter(x => x.kind === k.id); if (!it.length) continue;
      const pts = [], map = [];
      for (const x of it) { const t = this.wallTris(x, this.D.offset_m * 2, x.z0, x.z1, []); for (const p of t) pts.push(p); for (let i = 0; i < t.length; i += 3) map.push('clad:' + x.owner); }
      const m = this.mesh(pts, map, this.mat(k.color || '#b9ad9a'));
      this.add(m, { floor: 'site', step: 'cladding', layer: k.id }, { name: `${k.label} (חיפויי חוץ)`, kind: 'cladding', id: k.id,
        rows: [['משטחים', it.map(x => x.owner).join(', ')], ['שטח', `${f2(it.reduce((a, x) => a + x.area, 0))} מ"ר`], ['צבע / דגם', 'טרם נקבע – לפי האדריכל']],
        source: it[0].source, note: 'אזורי החיפוי של הבית – לפי האדריכל (data/finishes/cladding/zones.json)' });
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
      const tris = s.cat === 'wall' ? this.wallTris(s, this.D.offset_m * 1.6, s.z0, s.z1, []) : this.surfTris(s, this.D.offset_m * 1.6);
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
      if (s.ownerKind === 'concrete' || s.ownerKind === 'column') rows.push(['הכנה', this.T.scratchNote]);
    } else if (s.cat === 'reveal') rows.push(['פתח', `${s.opening} (${s.openingKind}) · רוחב ${f2(s.width)} · גובה ${f2(s.height)} · עומק ${f2(s.depth)} מ'`], ['חלקים', s.quads.map(q => q.part === 'jamb' ? 'צד' : 'משקוף').join(' + ') + ' (בלי אדן)'], ['שטח', `${f2(s.amount)} מ"ר`]);
    else if (s.cat === 'beam' && s.edge) rows.push(['שפת תקרה', `${s.beam} · ${c.fmtRel(s.bottom)} עד ${c.fmtRel(s.top)}`], ['שטח', `${f2(s.amount)} מ"ר`], ['הכנה', this.T.scratchNote]);
    else if (s.cat === 'beam') rows.push(['קורה', `${s.beam}${s.pergola ? ' (פרגולה)' : ''} · ${c.fmtRel(s.bottom)} עד ${c.fmtRel(s.top)}`], ['דפנות / תחתית / ראש', `${f2(s.sides.reduce((a, x) => a + x.area, 0))} / ${f2(s.flats.filter(x => x.part === 'soffit').reduce((a, x) => a + x.area, 0))} / ${f2(s.flats.filter(x => x.part === 'top').reduce((a, x) => a + x.area, 0))} מ"ר`], ['הכנה', this.T.scratchNote]);
    else if (s.cat === 'patch') rows.push(['חלק', ({ side: 'פן אנכי', sill: 'אדן', top: 'ראש / מדף', soffit: 'תחתית' })[s.part] || s.part], ['רכיב', s.owner || '—'], ['שטח', `${f2(s.amount)} מ"ר`],
      ['מפלס', s.vertical ? `${c.fmtRel(s.z0)} עד ${c.fmtRel(s.z1)}` : c.fmtRel(s.z)], ['למה', 'פן חשוף של השלד שאף משטח טיח אחר לא כיסה (בדיקת כיסוי 2 ס"מ – docs/verification/finishes-coverage.md)']);
    else if (s.cat === 'filler') rows.push(['למה', s.typeReason], ['מפלס', `${c.fmtRel(s.z0)} עד ${c.fmtRel(s.z1)}`]);
    else rows.push(['שטח', `${f2(s.amount)} מ"ר`], ['מפלס', c.fmtRel(s.z)]);
    if (s.shift > 0.0005) rows.push(['מישור אחד', `הטיח מוקדם ב-${f2(s.shift * 100)} ס"מ למישור הקיר (טיח עבה במקום המדרגה – ${s.shift > 0.02 ? 'עם רשת' : 'בלי רשת'}; השלד לא שונה)`]);
    rows.push(['פיגום', s.scaffold ? `דורש פיגום (מעל ${this.T.params.scaffoldAbove_m} מ') – ${f2(s.scaffoldArea || 0)} מ"ר מעל הגובה` : 'לא']);
    if (s.status === 'provisional') rows.push(['מעמד', 'זמני – ' + (s.zSource || '')]);
    rows.push(['מפתח', s.key]);
    return rows;
  }
  pick(hit) { const s = this.surfaceAt(hit); if (s) this.showSurface(s); }
  showSurface(s) {
    this.selected = s; this.highlight(s);
    const sel = h('select', { onchange: (e) => this.setType(s, e.target.value) }, [...this.drawn, this.typeBy.none].map(t => { const o = h('option', { value: t.id }, t.label); if (t.id === this.typeOf(s)) o.selected = true; return o; }));
    const extra = h('div', { class: 'plaster-edit' }, h('b', {}, 'שינוי סוג: '), sel,
      this.overridden(s) ? h('button', { class: 'small', onclick: () => this.setType(s, s.defaultType) }, 'חזרה לברירת המחדל') : '',
      h('div', { class: 'muted' }, this.state === 'online' ? 'נשמר במסד הנתונים של הארטיפקט – קלוד יסנכרן לקובץ overrides.json' : 'נשמר בדפדפן הזה'));
    this.app.ui.showInfo({ title: `טיח · ${s.edge ? 'שפת תקרה' : CAT_HE[s.cat]} · ${f2(s.amount)} מ"ר`, rows: this.rowsOf(s), source: s.source, extra });
  }
  // ---------------------------------------------------------------- persistence (artifact db, else this browser)
  saveLocal() { try { localStorage.setItem(LS, JSON.stringify({ live: this.live, prices: this.prices, wp: this.wpH })); } catch {} }
  async connect() {
    const use = window.claude?.use; const db = use ? await use('db').catch(() => null) : null;
    if (!db) return;
    this.col = db.collection('plaster'); this.state = 'online';
    this.col.onSnapshot((snap) => {
      const live = {}; let prices = null, wp = null;
      for (const d of snap.docs) { const x = d.data(); if (x.kind === 'prices') prices = x.prices; else if (x.kind === 'wpHeights') wp = { wet: x.wet, shower: x.shower }; else if (x.key && x.type) live[x.key] = x.type; }
      const changed = JSON.stringify(live) !== JSON.stringify(this.live);
      const wpChanged = wp && JSON.stringify(wp) !== JSON.stringify(this.wpH);
      this.live = live; if (prices) this.prices = prices; if (wp) this.wpH = wp; this.saveLocal();
      if (changed) this.rebuildPlaster();
      if (wpChanged) this.rebuildWaterproofing();
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

  async setWp(patch) {   // waterproofing heights (m): { wet, shower } – null = back to the default
    for (const [k, v] of Object.entries(patch)) this.wpH[k] = v == null || v === '' || !(+v >= 0) ? this.wpDef[k] : +(+v).toFixed(3);
    this.saveLocal(); this.rebuildWaterproofing();
    if (this.col) { try { await this.col.doc('wpHeights').set({ kind: 'wpHeights', ...this.wpH, defaults: this.wpDef, at: new Date().toISOString() }); } catch {} }
    this.app?.ui.refreshPanel('finishes'); this.app?.ui.refreshPanel('layers');
  }
  // the waterproofing faces at the current heights: up to finish + height (shower zone / rest), never above the wall face
  wpWalls() {
    return this.P.waterproofing.filter(w => w.kind === 'wall').map(w => {
      const H = w.shower ? this.wpH.shower : this.wpH.wet, z1 = +Math.min(w.faceTop ?? w.z1, (w.finish ?? (w.z1 - w.height_m)) + H).toFixed(3);
      const doors = (w.openings || []).reduce((a, o) => a + Math.max(0, o.s1 - o.s0), 0);
      return { ...w, z1, height_m: H, area: Math.max(0, (w.s1 - w.s0 - doors) * (z1 - w.z0)), label: `איטום ${Math.round(H * 100)} ס"מ`,
        rule: w.shower ? `אזור מקלחת – עד ${H.toFixed(2)} מ' מפני הריצוף` : `${H.toFixed(2)} מ' מפני הריצוף` };
    }).filter(w => w.z1 > w.z0 + 0.001);
  }
  wpAll() { return [...this.wpWalls(), ...this.P.waterproofing.filter(w => w.kind === 'floor')]; }
  rebuildWaterproofing() {
    if (!this.wpItems) return;   // never shown yet: built with the current heights when first switched on
    this.ctx.registry.remove(this.wpItems); this.items = this.items.filter(i => !this.wpItems.includes(i));
    this.buildWaterproofing();
    this.app?.store && this.ctx.registry.apply(this.app.store.get());
    this.app?.viewer.invalidate();
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
    const rev = this.surf.filter(s => s.cat === 'reveal').reduce((a, r) => a + r.amount, 0), beam = this.surf.filter(s => s.cat === 'beam').reduce((a, r) => a + r.amount, 0);
    const mesh = this.P.walls.reduce((a, s) => a + (s.meshV_m || 0) + (s.meshH_m || 0), 0);
    const beads = this.P.walls.reduce((a, s) => a + (s.beads_m || 0), 0) + (this.P.reveals || []).reduce((a, r) => a + (r.beads || 0), 0);
    const wpW = this.wpWalls().reduce((a, w) => a + w.area, 0), wpF = this.P.waterproofing.filter(w => w.kind === 'floor').reduce((a, w) => a + w.area, 0);
    T.extras = { reveals: rev, beams: beam, mesh, beads, waterproofing: wpW + wpF, waterproofWalls: wpW, waterproofFloors: wpF };
    T.floors = Object.fromEntries(this.BU.layers.map(l => [l.id, this.TL.rooms.reduce((a, r) => a + ((r.layers || []).some(x => x.id === l.id) ? r.area : 0), 0)]));
    T.tiling = { area: this.TL.rooms.filter(r => !['court', 'outdoor'].includes(r.roomType)).reduce((a, r) => a + r.area, 0), skirting: this.TL.rooms.reduce((a, r) => a + r.skirting_m, 0) };
    const price = (id) => this.prices[id];
    T.cost = { byType: {}, byFloor: {}, total: 0, missing: [] };
    for (const [ty, v] of Object.entries(T.byType)) { if (price(ty) == null) { if (this.typeBy[ty]?.drawn !== false) T.cost.missing.push(this.typeBy[ty].label); continue; } T.cost.byType[ty] = v * price(ty); T.cost.total += v * price(ty); }
    for (const [fl, o] of Object.entries(T.byFloor)) T.cost.byFloor[fl] = Object.entries(o).reduce((a, [ty, v]) => a + (price(ty) != null ? v * price(ty) : 0), 0);
    for (const [id, v] of [['mesh', mesh], ['beads', beads], ['wetProofing', wpW + wpF]]) { if (price(id) != null) T.cost.total += v * price(id); }
    return T;
  }

  // ---------------------------------------------------------------- layer controls (layers panel: plaster / tiling domains)
  // display only – no quantities or prices here (Avihai 11.11: those are data, tab "נתונים ← טיח, איטום וריצוף")
  controls(groupId) {
    const app = this.app;
    const wrap = h('div', { class: 'finishes ctl' });
    if (groupId === 'plaster') wrap.append(h('p', { class: 'muted' }, 'טיח צמנטי באפור אחד – על כל פני הקירות (בלוק ובטון, פנים וחוץ), קורות ועמודים גלויים, גליפים ותקרות; בלי טיח על רצפות. ' + this.T.scratchNote + '. דריסה: לחיצה על משטח במצב "מידות".'));
    if (groupId === 'tiling') wrap.append(h('p', { class: 'muted' }, 'מעל היציקה: מילוי סומסום וחול → טיט / מדה → דבק → אריח. האריח נבחר לכל אזור בסדנת הריצוף (מקום שמור באזור שלא נבחר). העוביים זמניים – ' + (this.BU.status === 'provisional' ? 'open-issues #163' : '') + '.'),
      this.tiling ? h('div', { class: 'btns' }, h('button', { class: 'small primary', onclick: () => app.store.set({ mode: 'tiling' }, { label: 'mode' }) }, '▦ סדנת ריצוף')) : null);
    if (groupId === 'waterproofingGroup') {   // the wet-room waterproofing heights (defaults – provisional)
      const inp = (k, unit, step) => h('input', { type: 'number', min: 0, step, class: 'price wp-h', 'data-k': k,
        value: unit === 'cm' ? Math.round(this.wpH[k] * 100) : this.wpH[k], onchange: (e) => this.setWp({ [k]: e.target.value === '' ? null : unit === 'cm' ? +e.target.value / 100 : +e.target.value }) });
      const dflt = this.wpH.wet === this.wpDef.wet && this.wpH.shower === this.wpDef.shower;
      wrap.append(h('div', { class: 'wp-ctl' }, h('b', {}, 'גובה האיטום בחדרים הרטובים'),
        h('div', { class: 'row' }, h('span', {}, 'הגבהה על הקירות (ס"מ):'), inp('wet', 'cm', 1)),
        h('div', { class: 'row' }, h('span', {}, "קירות המקלחת (מ'):"), inp('shower', 'm', 0.05)),
        h('div', { class: 'btns' }, h('button', { class: 'small', disabled: dflt, onclick: () => this.setWp({ wet: null, shower: null }) }, `ברירת מחדל (${Math.round(this.wpDef.wet * 100)} ס"מ / ${f2(this.wpDef.shower)} מ')`)),
        h('div', { class: 'warn' }, '⚠ ברירות מחדל זמניות – לא נסגרו סופית (open-issues #166). אזור המקלחת – ±0.9 מ\' סביב נקודת המקלחת (#156).'),
        h('div', { class: 'muted' }, `רצפה: כל רצפת החדר. ${this.state === 'online' ? 'נשמר במסד הארטיפקט.' : 'נשמר בדפדפן הזה.'}`)));
    }
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
    return wrap;
  }

  // ---------------------------------------------------------------- panel (tab "נתונים ← טיח, איטום וריצוף"): quantities, prices, rooms, Excel
  panel(ui) {
    const app = this.app, s = app.store.get(), T = this.totals();
    const setLayers = (patch) => app.store.set({ layers: { ...app.store.get().layers, ...patch } }, { label: 'layers' });
    const wrap = h('div', { class: 'finishes' });
    wrap.append(h('p', { class: 'muted' }, 'כמויות נגזרות מהגיאומטריה של המודל (קירות, פתחים, תקרות, קורות). הצגה / הסתרה של הטיח, האיטום והריצוף – בלשונית "שכבות".'));
    // legend + quantities + prices
    const priceIn = (id) => h('input', { type: 'number', min: 0, step: 1, class: 'price', placeholder: '₪', value: this.prices[id] ?? '', onchange: (e) => { this.setPrice(id, e.target.value); ui.refreshPanel('finishes'); } });
    const scaf = (ty) => Object.values(T.scaffold).reduce((a, o) => a + (o[ty] || 0), 0);
    wrap.append(h('h4', {}, 'מקרא וכמויות'), h('table', { class: 'qty' },
      h('tr', {}, h('th', {}, ''), h('th', {}, 'סוג'), h('th', {}, 'נטו מ"ר'), h('th', {}, 'מזה בפיגום'), h('th', {}, 'מחיר ליח\''), h('th', {}, 'עלות')),
      this.types.map(t => {
        const lid = 'plaster_' + t.id, on = s.layers[lid] !== false;
        return h('tr', {}, h('td', {}, t.drawn === false ? h('i', { class: 'swc off', title: 'לא מוצג כטיח' }) : h('i', { class: 'swc', style: `background:${t.color}`, title: on ? 'מוצג (לשונית שכבות)' : 'כבוי (לשונית שכבות)' })),
          h('td', { title: `${t.applies} · שכבות: ${t.layers.join(' + ') || '—'}` }, t.label), h('td', {}, f2(T.byType[t.id] || 0)), h('td', {}, f2(scaf(t.id))),
          h('td', {}, priceIn(t.id)), h('td', {}, T.cost.byType[t.id] != null ? f2(T.cost.byType[t.id]) : '—'));
      }),
      [['wetProofing', this.T.waterproofing.label, T.extras.waterproofing, 'מ"ר'], ['mesh', 'רשת פיברגלס (בלוק / בטון)', T.extras.mesh, 'מ"א'], ['beads', 'פינות מגן (זוויתנים)', T.extras.beads, 'מ"א']]
        .map(([id, label, v, u]) => h('tr', {}, h('td', {}, id === 'wetProofing' ? h('i', { class: 'swc', style: `background:${this.T.waterproofing.colorWall}` }) : ''), h('td', {}, label), h('td', {}, `${f2(v)} ${u === 'מ"א' ? 'מ"א' : ''}`), h('td', {}, ''),
          h('td', {}, priceIn(id)), h('td', {}, this.prices[id] != null ? f2(v * this.prices[id]) : '—'))),
      h('tr', { class: 'tot' }, h('td', {}, ''), h('td', {}, 'סה"כ עלות'), h('td', {}, ''), h('td', {}, ''), h('td', {}, ''), h('td', {}, T.cost.total ? f2(T.cost.total) + ' ₪' : '—'))));
    wrap.append(h('div', { class: 'muted' }, `כולל גליפים ${f2(T.extras.reveals)} מ"ר וקורות גלויות ${f2(T.extras.beams)} מ"ר.`));
    if (T.cost.missing.length) wrap.append(h('div', { class: 'muted' }, 'חסר מחיר: ' + T.cost.missing.join(', ')));
    // by floor
    wrap.append(h('h4', {}, 'לפי קומה (מ"ר)'), h('table', { class: 'qty' },
      h('tr', {}, h('th', {}, 'קומה'), this.types.filter(t => T.byType[t.id]).map(t => h('th', {}, t.label)), h('th', {}, 'עלות')),
      Object.entries(T.byFloor).map(([fl, o]) => h('tr', {}, h('td', {}, FLOOR_HE[fl]), this.types.filter(t => T.byType[t.id]).map(t => h('td', {}, o[t.id] ? f2(o[t.id]) : '')), h('td', {}, T.cost.byFloor[fl] ? f2(T.cost.byFloor[fl]) : '—')))));
    wrap.append(h('h4', {}, 'טיח חוץ לפי חזית (מ"ר)'), h('table', { class: 'qty' },
      Object.entries(T.byFacade).sort().map(([fc, o]) => h('tr', {}, h('td', {}, FACADE_HE[fc]), h('td', {}, Object.entries(o).map(([ty, v]) => `${this.typeBy[ty].label}: ${f2(v)}`).join(' · '))))));
    wrap.append(h('h4', {}, 'שכבות רצפה'), h('table', { class: 'qty' }, this.BU.layers.map(l => h('tr', {}, h('td', {}, l.color ? h('i', { class: 'swc', style: `background:${l.color}` }) : h('i', { class: 'swc off' })),
        h('td', {}, l.label), h('td', {}, `${f2(T.floors[l.id] || 0)} מ"ר`), h('td', {}, l.thickness_m != null ? `${f2(l.thickness_m * 100)} ס"מ` : 'השארית'), h('td', { class: 'muted' }, l.status === 'placeholder' ? 'מקום שמור' : 'עובי זמני')))),
      h('div', { class: 'muted' }, `פנלים: ${f2(T.tiling.skirting)} מ"א · סוג אריח וגובה חיפוי – טרם הוחלטו · ${this.BU._wetProofingOn}`));
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
      [this.T.waterproofing.label, +T.extras.waterproofing.toFixed(2), 'מ"ר', '', this.prices.wetProofing ?? '', this.prices.wetProofing != null ? +(T.extras.waterproofing * this.prices.wetProofing).toFixed(2) : ''],
      ['מזה גליפים (כלול בסוגים)', +T.extras.reveals.toFixed(2), 'מ"ר'], ['מזה קורות גלויות (כלול בסוגים)', +T.extras.beams.toFixed(2), 'מ"ר'],
      ['רשת פיברגלס', +T.extras.mesh.toFixed(2), 'מ"א', '', this.prices.mesh ?? '', this.prices.mesh != null ? +(T.extras.mesh * this.prices.mesh).toFixed(2) : ''],
      ['פינות מגן', +T.extras.beads.toFixed(2), 'מ"א', '', this.prices.beads ?? '', this.prices.beads != null ? +(T.extras.beads * this.prices.beads).toFixed(2) : ''],
      ['סה"כ', '', '', '', '', +T.cost.total.toFixed(2)],
      [], ...this.BU.layers.map(l => [l.label, +(T.floors[l.id] || 0).toFixed(2), 'מ"ר', l.thickness_m != null ? `${l.thickness_m * 100} ס"מ – ${l.status === 'placeholder' ? 'מקום שמור' : 'זמני'}` : 'השארית – זמני']),
      ['פנלים', +T.tiling.skirting.toFixed(2), 'מ"א'], [], [this.T.scratchNote]]);
    sheet('לפי קומה', [['קומה', ...this.types.map(t => t.label), 'עלות'], ...Object.entries(T.byFloor).map(([fl, o]) => [FLOOR_HE[fl], ...this.types.map(t => +(o[t.id] || 0).toFixed(2)), +(T.cost.byFloor[fl] || 0).toFixed(2)])]);
    sheet('חוץ לפי חזית', [['חזית', ...this.types.map(t => t.label)], ...Object.entries(T.byFacade).map(([fc, o]) => [FACADE_HE[fc], ...this.types.map(t => +(o[t.id] || 0).toFixed(2))])]);
    sheet('לפי חדר', [['קומה', 'חדר', 'סוג חדר', 'רצפה מ"ר', ...this.types.map(t => t.label)], ...this.R.rooms.map(r => { const o = T.byRoom[r.key] || {}; return [FLOOR_HE[r.floor], r.name || r.key, TYPE_ROOM_HE[r.type], +(this.TL.rooms.find(x => x.room === r.key)?.area || 0).toFixed(2), ...this.types.map(t => +(o[t.id] || 0).toFixed(2))]; })]);
    sheet('משטחים', [['מפתח', 'קומה', 'משטח', 'צד', 'חזית', 'חדר', 'רכיב', 'סוג', 'ברירת מחדל', 'דריסה', 'אורך', 'מגובה', 'עד גובה', 'ברוטו', 'פתחים', 'נטו', 'פיגום', 'שטח בפיגום', 'רשת מ"א', 'זוויתנים מ"א'],
      ...this.surf.map(s => [s.key, FLOOR_HE[s.floor], CAT_HE[s.cat], s.side === 'in' ? 'פנים' : s.side === 'out' ? 'חוץ' : '', FACADE_HE[s.facade] || '', this.rooms[s.room]?.name || '', s.owner || s.slab || s.opening || s.beam || '', tl(this.typeOf(s)), tl(s.defaultType), this.overridden(s) ? 'כן' : '',
        s.length ?? s.width ?? '', s.z0 ?? s.z ?? s.bottom, s.z1 ?? s.top ?? '', s.gross ?? s.amount, s.openingsArea ?? 0, +s.amount.toFixed(3), s.scaffold ? 'כן' : '', s.scaffoldArea || 0, +((s.meshV_m || 0) + (s.meshH_m || 0)).toFixed(3), s.beads_m || 0])]);
    sheet('גליפים', [['פתח', 'סוג', 'קומה', 'רוחב', 'גובה', 'עומק', 'חלקים', 'שטח', 'זוויתנים'], ...(this.P.reveals || []).map(r => [r.opening, r.openingKind, FLOOR_HE[r.floor], r.width, r.height, r.depth, r.quads.map(q => q.part).join('+'), r.area, r.beads])]);
    sheet('קורות', [['קורה', 'קומה', 'תחתית', 'ראש', 'פרגולה', 'שטח', 'סוג'], ...(this.P.beams || []).map(b => [b.beam, FLOOR_HE[b.floor], b.bottom, b.top, b.pergola ? 'כן' : '', b.area, tl(this.typeOf(b))])]);
    sheet('איטום', [['קומה', 'חדר', 'רכיב', 'כלל', 'מגובה', 'עד גובה', 'שטח'], ...this.wpAll().map(w => [FLOOR_HE[w.floor], this.rooms[w.room]?.name || w.room, w.owner || 'רצפה', w.rule, w.z0 ?? w.z, w.z1 ?? '', w.area])]);
    sheet('רצפות', [['קומה', 'חדר', 'סוג חדר', 'שטח מ"ר', 'פנלים מ"א', 'פני בטון', 'פני ריצוף', ...this.BU.layers.map(l => l.label + " (מ')"), 'סוג אריח'],
      ...this.TL.rooms.map(r => [FLOOR_HE[r.floor], r.zoneName || this.rooms[r.room]?.name || r.roomName || r.room, TYPE_ROOM_HE[r.roomType], r.area, r.skirting_m, r.slabTop ?? '', r.finishRel ?? '', ...this.BU.layers.map(l => (r.layers || []).find(x => x.id === l.id)?.thickness_m ?? ''), this.tiling?.choice[r.room] ? `${this.tiling.sizeOf(this.tiling.choice[r.room]).label} ${this.tiling.finBy[this.tiling.choice[r.room].finish]?.label || ''}` : 'טרם הוחלט'])]);
    const name = 'plaster-tiling-5187.xlsx';
    const buf = X.write(wb, { type: 'array', bookType: 'xlsx' });
    const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    // inside claude.ai the frame cannot download directly: the downloads capability asks the viewer to save
    const dl = window.claude?.use ? await window.claude.use('downloads').catch(() => null) : null;
    if (dl) { try { await dl.save({ filename: name, data: blob }); } catch (e) { this.app.ui.toast(e?.code === 'declined' ? 'הייצוא בוטל' : 'הייצוא נכשל'); } return; }
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  attach(app) { this.app = app; this.connect(); this.tiling?.connect(app); app.registry.onChange(() => this.syncOverhead());
    let last = JSON.stringify(app.store.get().dropCeiling || {});
    app.store.on((st) => { const k = JSON.stringify(st.dropCeiling || {}); if (k !== last) { last = k; this.rebuildDropped(); } }); }
}

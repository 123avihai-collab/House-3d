import * as THREE from 'three';
import { layoutZone, optimize, quantities, frameOf, area } from './layout.js';

// Tiling workshop ("סדנת ריצוף", mode "ריצוף"): a tile per zone (room floor) – size, finish, pattern, direction, origin,
// joint, fine shift – laid out over the zone polygon (src/tiling/layout.js), drawn in 3D on the tile layer of the floor
// build-up (fill → screed → adhesive → tile) and counted (tiles, cuts, boxes, adhesive, grout, skirting).
// Data: data/finishes/tiling/catalog.json (options + consumption rates, provisional), layout.json (the choices kept in the
// repo), the zones = data/finishes/tiling/surfaces.json rooms. Avihai's choices are kept in the artifact database
// (collection "tiling", read by Claude with ArtifactData) – outside claude.ai in this browser. No dimension is written here.

const LS = 'house3d.tiling';
const FLOOR_HE = { unit: 'יחידת דיור', ground: 'קרקע', first: "קומה א'", roof: 'גג' };
const f2 = (v) => (Math.round(v * 100) / 100).toLocaleString('he-IL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const f0 = (v) => Math.round(v).toLocaleString('he-IL');
const hash = (s) => { let x = 2166136261; for (const c of s) { x ^= c.charCodeAt(0); x = Math.imul(x, 16777619); } return 't' + (x >>> 0).toString(36); };
const rnd = (i, j) => { let x = Math.imul(i * 73856093 ^ j * 19349663, 2654435761) >>> 0; x ^= x >>> 13; x = Math.imul(x, 1274126177) >>> 0; return ((x >>> 0) % 10000) / 10000; };
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'value') e.value = v; else if (k === 'selected' || k === 'checked') e[k] = !!v;
    else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};
const SVGNS = 'http://www.w3.org/2000/svg';
const s = (tag, attrs = {}) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };

export class TilingWorkshop {
  constructor(F) {
    this.F = F; const data = F.ctx.data;
    this.C = data.tilingCatalog; this.D = data.display.tiling || {};
    this.sizeBy = Object.fromEntries(this.C.sizes.map(x => [x.id, x]));
    this.finBy = Object.fromEntries(this.C.finishes.map(x => [x.id, x]));
    this.patBy = Object.fromEntries(this.C.patterns.map(x => [x.id, x]));
    this.dirBy = Object.fromEntries(this.C.directions.map(x => [x.id, x]));
    const ex = new Set(this.C.excludeRoomTypes || []);
    this.zones = F.TL.rooms.filter(r => r.layers?.length && r.area > 0.05 && r.parts?.length && !ex.has(r.roomType)).map(r => ({
      key: r.room, r, floor: r.floor, name: F.rooms[r.room]?.name || r.roomName || 'ללא שם',
      parts: r.parts.map(p => [p.ringITM, ...(p.holesITM || [])]),
      tileLayer: r.layers.find(l => l.id === 'floorTile'),
    }));
    this.zoneBy = Object.fromEntries(this.zones.map(z => [z.key, z]));
    this.choice = { ...(data.tilingLayout?.rooms || {}) };
    try { const l = JSON.parse(localStorage.getItem(LS) || '{}'); if (l.choice) this.choice = { ...this.choice, ...l.choice }; this.sel = l.sel; this.showCuts = l.showCuts ?? true; } catch { this.showCuts = true; }
    for (const k of Object.keys(this.choice)) if (!this.zoneBy[k] || !this.choice[k]) delete this.choice[k];
    if (!this.zoneBy[this.sel]) this.sel = this.zones[0]?.key;
    this.state = 'local'; this.cache = new Map(); this.items = []; this.mats = {};
    this.outline = new THREE.Group(); this.outline.visible = false; F.ctx.scene.add(this.outline);
  }
  saveLocal() { try { localStorage.setItem(LS, JSON.stringify({ choice: this.choice, sel: this.sel, showCuts: this.showCuts })); } catch {} }
  has(key) { return !!this.choice[key]; }

  // ---------------------------------------------------------------- persistence (artifact db, else this browser)
  async connect(app) {
    this.app = app;
    const use = window.claude?.use; const db = use ? await use('db').catch(() => null) : null;
    if (!db) return;
    this.col = db.collection('tiling'); this.state = 'online';
    this.col.onSnapshot((snap) => {
      const next = { ...(this.F.ctx.data.tilingLayout?.rooms || {}) };
      for (const d of snap.docs) { const x = d.data(); if (x.kind !== 'zone' || !this.zoneBy[x.room]) continue; if (x.cleared) delete next[x.room]; else next[x.room] = x.choice; }
      if (JSON.stringify(next) === JSON.stringify(this.choice)) return;
      this.choice = next; this.saveLocal(); this.rebuild(); this.refresh();
    }, () => { this.state = 'local'; });
  }
  async setChoice(key, patch, { rebuild = true } = {}) {
    if (patch === null) delete this.choice[key];
    else this.choice[key] = { ...this.C.defaults, ...(this.choice[key] || {}), ...patch };
    this.saveLocal();
    if (rebuild) { this.rebuild(); this.refresh(); }
    if (this.col) {
      const doc = patch === null ? { kind: 'zone', room: key, cleared: true } : { kind: 'zone', room: key, name: this.zoneBy[key].name, floor: this.zoneBy[key].floor, choice: this.choice[key] };
      try { await this.col.doc(hash(key)).set({ ...doc, at: new Date().toISOString() }); } catch { this.app?.ui.toast('השמירה במסד נכשלה – נשמר בדפדפן'); }
    }
  }

  // ---------------------------------------------------------------- layout of a zone (memo)
  bigPart(z) { return z.parts.reduce((a, p) => (Math.abs(area(p[0])) > Math.abs(area(a[0])) ? p : a), z.parts[0]); }
  sizeOf(c) {
    if (c.size === 'custom') return { id: 'custom', label: `${c.w_cm}×${c.l_cm}`, w_m: (+c.w_cm || 60) / 100, l_m: (+c.l_cm || 60) / 100, thick_m: 0.01, perBox: +c.perBox || 1, status: 'provisional' };
    return this.sizeBy[c.size] || this.sizeBy[this.C.defaults.size];
  }
  layout(key, c = this.choice[key]) {
    const z = this.zoneBy[key]; if (!z || !c) return null;
    const ck = key + JSON.stringify(c);
    if (this.cache.has(ck)) return this.cache.get(ck);
    const size = this.sizeOf(c), pat = this.patBy[c.pattern] || this.C.patterns[0], dir = this.dirBy[c.direction] || this.C.directions[0];
    const tile = { l_m: size.l_m, w_m: size.w_m };
    // one frame for all the parts of a zone (the zone's largest part sets the direction and the centre)
    const big = this.bigPart(z);
    const F = frameOf(big, c, pat, dir);
    const parts = z.parts.map(p => layoutZone(p, tile, c, pat, dir, this.C.cuts, F));
    const lay = { frame: F, pieces: parts.flatMap(p => p.pieces), tile: parts[0].tile, start: parts[0].start, size, pat, dir,
      stats: parts.reduce((a, p) => { for (const k of ['pieces', 'full', 'cut', 'slivers', 'narrow', 'tileArea_m2', 'zoneArea_m2', 'score']) a[k] = (a[k] || 0) + p.stats[k];
        a.minCut_m = p.stats.minCut_m == null ? a.minCut_m : a.minCut_m == null ? p.stats.minCut_m : Math.min(a.minCut_m, p.stats.minCut_m); return a; }, { minCut_m: null }) };
    lay.q = quantities(lay, size, c, this.C.consumption, z.r.skirting_m || 0);
    if (this.cache.size > 200) this.cache.clear();
    this.cache.set(ck, lay);
    return lay;
  }
  optimizeZone(key) {
    const z = this.zoneBy[key], c = this.choice[key]; if (!c) return null;
    const size = this.sizeOf(c), pat = this.patBy[c.pattern], dir = this.dirBy[c.direction];
    const big = this.bigPart(z);
    const r = optimize(big, { l_m: size.l_m, w_m: size.w_m }, { ...c, du_cm: 0, dv_cm: 0 }, pat, dir, this.C.cuts);
    return r;
  }

  // ---------------------------------------------------------------- 3D: the tiles of every zone with a choice (layer floorTile)
  // tile material: finish colour × vertex colour (per-tile shade); textured finishes (concrete, wood) with PBR maps.
  // The joints are drawn in the shader from the position inside the tile (attribute tileXY: u, v from the tile corner,
  // tile L, W; tileJ: half joint) – at least ~1 px wide at any distance / angle, the real width up close.
  matOf(fin) {
    const k = fin.id;
    if (this.mats[k]) return this.mats[k];
    const m = new THREE.MeshStandardMaterial({ color: '#ffffff', vertexColors: true, roughness: fin.roughness ?? 0.5, metalness: 0, side: THREE.DoubleSide,
      envMapIntensity: this.D.envMapIntensity ?? 0.9, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -2 });
    if (fin.texture) {
      const ld = (f, srgb) => { const tx = new THREE.TextureLoader().load(`${fin.texture}/${f}`, () => this.F.ctx.viewer?.invalidate());
        tx.wrapS = tx.wrapT = THREE.RepeatWrapping; if (srgb) tx.colorSpace = THREE.SRGBColorSpace; tx.repeat.set(1 / fin.texSize_m, 1 / fin.texSize_m); return tx; };
      m.map = ld('color.webp', true);
      if (fin.pbr) { m.normalMap = ld('normal.jpg', false); m.roughnessMap = ld('roughness.webp', false); m.normalScale.set(0.6, 0.6); }
    }
    const grout = new THREE.Color(this.D.groutColor || '#8f8b84'), px = this.D.jointMinPx ?? 1.1;
    m.onBeforeCompile = (sh) => {
      sh.uniforms.uGrout = { value: grout };
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nattribute vec4 tileXY;\nattribute float tileJ;\nvarying vec4 vTile;\nvarying float vJ;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvTile = tileXY; vJ = tileJ;');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nuniform vec3 uGrout;\nvarying vec4 vTile;\nvarying float vJ;')
        .replace('#include <color_fragment>', `#include <color_fragment>
        if (vTile.z > 0.0) {
          vec2 q = vTile.xy;
          float d = min(min(q.x, vTile.z - q.x), min(q.y, vTile.w - q.y));
          float fw = max(fwidth(d), 1e-5);
          float jw = max(vJ, fw * ${(px / 2).toFixed(2)});
          float fade = smoothstep(6.0, 18.0, min(vTile.z, vTile.w) / fw);
          float line = (1.0 - smoothstep(jw, jw + fw, d)) * fade * 0.85;
          float bevel = 1.0 - 0.08 * fade * (1.0 - smoothstep(vJ, vJ + 0.004, d));
          diffuseColor.rgb = mix(diffuseColor.rgb * bevel, uGrout, line);
        }`);
    };
    m.customProgramCacheKey = () => 'tileJoints';
    return (this.mats[k] = m);
  }
  build3D() {
    this.built = true;
    const F = this.F, V = (E, N, z) => F.V(E, N, z);
    const grout = F.mat(this.D.groutColor || '#8f8b84');
    const cutCol = { 1: new THREE.Color(this.D.narrowColor || '#ffa726'), 2: new THREE.Color(this.D.sliverColor || '#e53935') };
    const mark = this.showCuts && this.app?.store.get().mode === 'tiling';
    for (const z of this.zones) {
      const c = this.choice[z.key]; if (!c) continue;
      const lay = this.layout(z.key); const fin = this.finBy[c.finish] || this.C.finishes[0];
      const z1 = z.tileLayer.z1, z0 = z.tileLayer.z0, zt = z0 + 0.0008;   // grout / joint bottom: on the adhesive (a full tile thickness under the face – no depth fight at a distance)
      const pos = [], col = [], uv = [], map = [], txy = [], tj = [];
      const L = lay.tile.L, Wd = lay.tile.W, jh = lay.tile.j / 2, grain = !!fin.grainAlongLength;
      const base = new THREE.Color(fin.color), tmp = new THREE.Color();
      const W = (u, v, zz) => { const [E, N] = lay.frame.toWorld([u, v]); return V(E, N, zz); };
      for (const p of lay.pieces) {
        const k = 1 + (rnd(p.i, p.j) - 0.5) * 2 * (fin.vary || 0);
        tmp.copy(base).multiplyScalar(k);
        if (mark && p.sev) tmp.lerp(cutCol[p.sev], 0.65);
        const ou = rnd(p.j, p.i) * 7, ov = rnd(p.i + 11, p.j) * 7;   // texture offset per tile (no repeated pattern)
        const pts = p.poly.filter((q, i, a) => { const n = a[(i + 1) % a.length]; return Math.hypot(n[0] - q[0], n[1] - q[1]) > 1e-6; });
        if (pts.length < 3) continue;
        const C2 = pts.map(([u, v]) => new THREE.Vector2(u, v)), Hs = (p.holes || []).map(hh => hh.map(([u, v]) => new THREE.Vector2(u, v)));
        if (THREE.ShapeUtils.isClockWise(C2)) C2.reverse();
        Hs.forEach(hh => { if (!THREE.ShapeUtils.isClockWise(hh)) hh.reverse(); });
        const all = [...C2, ...Hs.flat()];
        // top face: uv in metres (+ offset per tile; wood – grain along the tile length), tileXY = place inside the tile
        const push = (u, v, zz, top = true) => { pos.push(...W(u, v, zz)); col.push(tmp.r, tmp.g, tmp.b);
          const lu = u - p.x0, lv = v - p.y0; uv.push(grain ? lv + ou : u + ou, grain ? lu + ov : v + ov);
          if (top) txy.push(lu, lv, L, Wd); else txy.push(0, 0, 0, 0); tj.push(jh); };
        for (const t of THREE.ShapeUtils.triangulateShape(C2, Hs)) { for (const i of t) push(all[i].x, all[i].y, z1); map.push(z.key); }
        // tile edges down to the joint (seen up close / in a section)
        for (let i = 0; i < C2.length; i++) {
          const a = C2[i], b = C2[(i + 1) % C2.length];
          push(a.x, a.y, zt, false); push(b.x, b.y, zt, false); push(b.x, b.y, z1, false);
          push(a.x, a.y, zt, false); push(b.x, b.y, z1, false); push(a.x, a.y, z1, false);
          map.push(z.key, z.key);
        }
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
      g.setAttribute('tileXY', new THREE.Float32BufferAttribute(txy, 4));
      g.setAttribute('tileJ', new THREE.Float32BufferAttribute(tj, 1));
      g.computeVertexNormals();
      const m = new THREE.Mesh(g, this.matOf(fin)); m.receiveShadow = true; m.userData.keep = true; m.userData.faceMap = map;
      // the grout under the joints (the zone polygon, a hair below the tile face)
      const gp = [], gm = [];
      for (const part of z.parts) { const t = F.ringTris(part[0], part.slice(1), zt); gp.push(...t); }
      const gg = new THREE.BufferGeometry(); gg.setAttribute('position', new THREE.Float32BufferAttribute(gp.flat(), 3)); gg.computeVertexNormals();
      const gmsh = new THREE.Mesh(gg, grout); gmsh.receiveShadow = true; gmsh.userData.keep = true;
      const grp = new THREE.Group(); grp.add(gmsh, m);
      const q = lay.q, sz = lay.size;
      const it = F.add(grp, { floor: z.floor, step: 'tiling', layer: 'floorTile' }, {
        name: `ריצוף ${sz.label} ${fin.label} – ${z.name}`, kind: 'tiles', id: 'TL-' + hash(z.key), pickable: true,
        rows: [['אזור', `${z.name} (${FLOOR_HE[z.floor]})`], ['אריח', `${sz.label} ס"מ · ${fin.label} · ${lay.pat.label} · ${lay.dir.label}`], ['פוגה', `${c.joint_mm} מ"מ`],
          ['שטח', `${f2(q.area_m2)} מ"ר`], ['אריחים', `${q.full} שלמים + ${q.cut} חתוכים${q.slivers ? ` (${q.slivers} צרים מ-5 ס"מ!)` : ''}`],
          ['להזמנה', `${q.order} אריחים = ${q.boxes} קרטונים (${f2(q.order_m2)} מ"ר, כולל ${c.spare_pct}% רזרבה ופנלים)`]],
        source: 'src/tiling (סדנת ריצוף) – data/finishes/tiling/catalog.json; אזור: data/finishes/tiling/surfaces.json', note: 'מקדמי צריכה – זמניים (open-issues #178)',
        onClick: () => { this.select(z.key); this.app?.ui.openTab('tiling'); } });
      this.items.push(it);
    }
  }
  rebuild() {
    if (!this.built) return;   // never shown yet: built with the current choices when the tile layer is first switched on
    this.F.rebuildFloors();
  }
  removeItems() { const reg = this.F.ctx.registry; reg.remove(this.items); this.F.items = this.F.items.filter(i => !this.items.includes(i)); this.items = []; }

  // the selected zone, outlined (tiling mode only)
  drawOutline() {
    this.outline.clear();
    const z = this.zoneBy[this.sel], on = this.app?.store.get().mode === 'tiling';
    this.outline.visible = !!(z && on);
    if (!z || !on) return;
    const pts = [];
    for (const part of z.parts) for (const ring of part) for (let i = 0; i < ring.length; i++) {
      const a = ring[i], b = ring[(i + 1) % ring.length], zz = z.tileLayer.z1 + 0.01;
      pts.push(...this.F.V(a[0], a[1], zz), ...this.F.V(b[0], b[1], zz));
    }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    const l = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: this.F.D.selectColor, depthTest: false }));
    l.renderOrder = 10; this.outline.add(l);
    this.app.viewer.invalidate();
  }
  select(key) { this.sel = key; this.saveLocal(); this.drawOutline(); this.refresh(); }
  refresh() { this.app?.ui.refreshPanel('tiling'); this.app?.ui.refreshPanel('finishes'); this.app?.viewer.invalidate(); }

  // ---------------------------------------------------------------- mode: enter / leave
  enter() {
    const app = this.app; if (!app) return;
    const st = app.store.get();
    app.store.set({ layers: { ...st.layers, floorTile: true }, stageIndex: app.data.tags.sequence.length - 1 }, { label: 'tiling', record: false });
    if (this.built) this.rebuild();   // cut pieces marked in this mode
    this.drawOutline();
    app.ui.openTab('tiling', !app.ui.isMobile());
  }
  leave() { this.outline.visible = false; if (this.built) this.rebuild(); }
  // interior view of the zone: its floor only, a horizontal cut above the floor, the camera above the zone
  showZone(key = this.sel) {
    const app = this.app, z = this.zoneBy[key]; if (!app || !z) return;
    const st = app.store.get();
    const floors = Object.fromEntries(Object.entries(st.floors).map(([k, v]) => [k, { ...v, visible: k === z.floor }]));
    const fin = z.tileLayer.z1;
    app.store.set({ floors, layers: { ...st.layers, floorTile: true }, section: { ...st.section, hOn: true, hideBeams: true, hLevel: +(fin + this.F.D.interiorCutAbove_m).toFixed(2) } }, { label: 'tiling view' });
    const F = frameOf(z.parts[0], {}, null, null);
    const t = new THREE.Vector3(...this.F.V(F.cx, F.cy, fin));
    const R = Math.max(...F.size) * (this.D.viewDistance ?? 1.1) + 2;
    app.viewer.flyTo(t, t.clone().add(new THREE.Vector3(R * 0.25, R, R * 0.35)));
  }

  // ---------------------------------------------------------------- 2D plan of the zone (drag = shift the layout)
  plan(key) {
    const z = this.zoneBy[key], c = this.choice[key]; const lay = c ? this.layout(key) : null;
    const F = lay?.frame || frameOf(z.parts[0], {}, null, null);
    const loc = z.parts.map(p => p.map(r => r.map(F.toLocal)));
    let u0 = Infinity, u1 = -Infinity, v0 = Infinity, v1 = -Infinity;
    for (const p of loc) for (const [u, v] of p[0]) { u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v); }
    const m = 0.35, W = u1 - u0 + 2 * m, H = v1 - v0 + 2 * m;
    const svg = s('svg', { viewBox: `${u0 - m} ${-v1 - m} ${W} ${H}`, class: 'tile-plan', preserveAspectRatio: 'xMidYMid meet' });
    const P = (pts) => pts.map(([u, v]) => `${u.toFixed(4)},${(-v).toFixed(4)}`).join(' ');
    const gz = s('g');
    for (const p of loc) { let d = ''; for (const r of p) d += 'M' + P(r).replace(/ /g, 'L') + 'Z'; gz.append(s('path', { d, fill: this.D.groutColor || '#8f8b84', 'fill-rule': 'evenodd', stroke: 'none' })); }
    svg.append(gz);
    const gp = s('g'); svg.append(gp);
    const fin = c ? this.finBy[c.finish] : null;
    const drawPieces = (L) => {
      gp.replaceChildren();
      for (const p of L.pieces) {
        const fill = p.sev === 2 ? (this.D.sliverColor || '#e53935') : p.sev === 1 ? (this.D.narrowColor || '#ffa726') : (fin.swatch || fin.color);
        gp.append(s('polygon', { points: P(p.poly), fill, 'fill-opacity': p.full ? 1 : 0.8, stroke: '#00000033', 'stroke-width': 0.004 }));
        if (p.sev && p.cut != null && Math.max(p.bw, p.bh) > 0.12) { const t = s('text', { x: (p.poly.reduce((a, q) => a + q[0], 0) / p.poly.length).toFixed(3), y: (-p.poly.reduce((a, q) => a + q[1], 0) / p.poly.length).toFixed(3), 'font-size': 0.11, 'text-anchor': 'middle', 'dominant-baseline': 'middle', fill: '#000' }); t.textContent = Math.round(p.cut * 100); gp.append(t); }
      }
      // tile origin (the start tile) – a small cross
      const [su, sv] = L.start; const cs = Math.min(L.tile.L, L.tile.W) * 0.25;
      gp.append(s('path', { d: `M${su - cs},${-sv}L${su + cs},${-sv}M${su},${-sv - cs}L${su},${-sv + cs}`, stroke: '#1565c0', 'stroke-width': 0.02 }));
    };
    if (lay) drawPieces(lay);
    for (const p of loc) for (const r of p) svg.append(s('polygon', { points: P(r), fill: 'none', stroke: '#222', 'stroke-width': 0.025 }));
    // north arrow (true north is ~0.2° off grid north – not drawn)
    const na = F.a; const nu = Math.sin(na), nv = Math.cos(na); const ax = u1 + m * 0.5, ay = -(v1 + m * 0.5) + 0.25;
    svg.append(s('path', { d: `M${ax},${ay}L${ax + nu * 0.22},${ay - nv * 0.22}`, stroke: '#1565c0', 'stroke-width': 0.03 }));
    const nt = s('text', { x: ax + nu * 0.3, y: ay - nv * 0.3, 'font-size': 0.14, 'text-anchor': 'middle', 'dominant-baseline': 'middle', fill: '#1565c0' }); nt.textContent = 'N'; svg.append(nt);
    if (!lay) return svg;
    // drag on the plan: shift the layout (du / dv); saved on release
    let drag = null;
    svg.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY, du: c.du_cm || 0, dv: c.dv_cm || 0, k: W / svg.getBoundingClientRect().width }; svg.setPointerCapture(e.pointerId); e.preventDefault(); });
    svg.addEventListener('pointermove', (e) => {
      if (!drag) return;
      const du = +(drag.du + (e.clientX - drag.x) * drag.k * 100).toFixed(1), dv = +(drag.dv - (e.clientY - drag.y) * drag.k * 100).toFixed(1);
      drag.now = { du_cm: du, dv_cm: dv };
      if (!drag.raf) drag.raf = requestAnimationFrame(() => { drag.raf = 0; if (!drag?.now) return; const L = this.layout(key, { ...c, ...drag.now }); drawPieces(L); this.statsEl && this.statsEl.replaceWith(this.statsEl = this.statsBox(L)); });
    });
    const end = () => { if (drag?.now) this.setChoice(key, drag.now); drag = null; };
    svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end);
    return svg;
  }
  statsBox(lay) {
    const q = lay.q;
    return h('div', { class: 'tile-stats' },
      h('span', {}, `${q.full} שלמים`), h('span', {}, `${q.cut} חתוכים`),
      h('span', { class: q.slivers ? 'bad' : '' }, `${q.slivers} צרים מ-${Math.round(this.C.cuts.hardMin_m * 100)} ס"מ`),
      h('span', { class: q.narrow ? 'mid' : '' }, `${q.narrow} מתחת לשליש`),
      h('span', {}, `חיתוך מינימלי: ${q.minCut_m != null ? Math.round(q.minCut_m * 1000) / 10 + ' ס"מ' : '—'}`),
      h('span', {}, `פחת חיתוך: ${f2(q.waste_pct)}%`));
  }

  // ---------------------------------------------------------------- panel ("נתונים ← סדנת ריצוף")
  panel(ui) {
    const app = this.app, st = app.store.get(), on = st.mode === 'tiling';
    const wrap = h('div', { class: 'finishes tiling' });
    wrap.append(h('p', { class: 'muted' }, 'סדנת ריצוף: בוחרים לכל אזור אריח (מידה, גימור, דוגמה, כיוון, נקודת התחלה, פוגה), רואים את הפריסה בתוכנית ובמודל, ומקבלים כמויות להזמנה. גרירה על התוכנית מזיזה את הפריסה; "פריסה מושלמת" מחפשת את ההזזה עם הכי מעט חיתוכים צרים.'),
      h('div', { class: 'fix-conn ' + (this.state === 'online' ? 'ok' : 'warn') }, this.state === 'online' ? 'מחובר: הבחירות נשמרות במודל וקלוד קורא אותן.' : 'לא מחובר (מחוץ ל-claude.ai): הבחירות נשמרות בדפדפן הזה בלבד.'),
      h('div', { class: 'btns' },
        h('button', { class: on ? 'on primary' : 'primary', onclick: () => app.store.set({ mode: on ? 'view' : 'tiling' }, { label: 'mode' }) }, on ? '✓ מצב ריצוף פעיל (יציאה)' : '▦ כניסה למצב ריצוף'),
        h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: this.showCuts, onchange: (e) => { this.showCuts = e.target.checked; this.saveLocal(); this.rebuild(); } }), ' סימון חיתוכים צרים במודל')));
    // the build-up under the tile (layers): fill (sumsum + sand) → screed → adhesive → tile
    const BU = this.F.BU;
    wrap.append(h('h4', {}, 'שכבות הרצפה'), h('div', { class: 'btns layers-chips' }, BU.layers.map(l => {
      const v = st.layers[l.id] !== false;
      return h('button', { class: 'small' + (v ? ' on' : ''), title: l.label, onclick: () => app.store.set({ layers: { ...app.store.get().layers, [l.id]: !v } }, { label: 'layers' }) },
        l.color ? h('i', { class: 'swc', style: `background:${l.color}` }) : h('i', { class: 'swc off' }), ' ', l.short || l.label);
    })), h('div', { class: 'muted' }, 'עוביים: ' + BU.layers.map(l => `${l.short || l.label} ${l.thickness_m != null ? f2(l.thickness_m * 100) + ' ס"מ' : 'השארית'}`).join(' · ') + ' – זמני (open-issues #163).'));

    // zones
    const byFl = {};
    for (const z of this.zones) (byFl[z.floor] ||= []).push(z);
    wrap.append(h('h4', {}, 'אזורים'), h('table', { class: 'qty zones' },
      h('tr', {}, h('th', {}, 'אזור'), h('th', {}, 'מ"ר'), h('th', {}, 'אריח'), h('th', {}, 'חיתוכים')),
      Object.entries(byFl).flatMap(([fl, zs]) => [h('tr', { class: 'grp' }, h('td', { colspan: 4 }, FLOOR_HE[fl])), ...zs.map(z => {
        const c = this.choice[z.key], L = c ? this.layout(z.key) : null;
        return h('tr', { class: 'zone-row' + (z.key === this.sel ? ' sel' : ''), 'data-room': z.key, onclick: () => this.select(z.key) },
          h('td', {}, z.name), h('td', {}, f2(z.r.area)),
          h('td', {}, c ? [h('i', { class: 'swc', style: `background:${(this.finBy[c.finish]?.swatch || this.finBy[c.finish]?.color)}` }), ' ', this.sizeOf(c).label] : h('span', { class: 'muted' }, 'לא נבחר')),
          h('td', {}, L ? (L.q.slivers ? h('span', { class: 'bad' }, `⚠ ${L.q.slivers} צרים`) : L.q.narrow ? h('span', { class: 'mid' }, `${L.q.narrow} מתחת לשליש`) : '✓') : ''));
      })])));

    // the selected zone
    const z = this.zoneBy[this.sel];
    if (z) wrap.append(this.zoneEditor(z));
    wrap.append(this.totalsBox());
    return wrap;
  }
  zoneEditor(z) {
    const c = this.choice[z.key];
    const box = h('div', { class: 'zone-ed' });
    box.append(h('h4', {}, `${z.name} – ${FLOOR_HE[z.floor]} (${f2(z.r.area)} מ"ר)`),
      h('div', { class: 'btns' }, h('button', { class: 'small', onclick: () => this.showZone(z.key) }, '👁 הצג במודל (מבט מלמעלה)')));
    if (!c) {
      box.append(h('p', { class: 'muted' }, 'לא נבחר אריח לאזור הזה.'),
        h('div', { class: 'btns' }, h('button', { class: 'primary', onclick: () => this.setChoice(z.key, {}) }, `+ ריצוף ${this.sizeBy[this.C.defaults.size].label} (ואז לשנות)`),
          h('button', { onclick: () => this.applyAll({ ...this.C.defaults }, (x) => !this.choice[x.key]) }, `${this.sizeBy[this.C.defaults.size].label} לכל האזורים שלא נבחרו`)),
        this.plan(z.key));
      return box;
    }
    const set = (k, cast = (v) => v) => (e) => this.setChoice(z.key, { [k]: cast(e.target.value) });
    const sel = (k, opts, cast) => h('select', { 'data-k': k, onchange: set(k, cast) }, opts.map(([v, l]) => h('option', { value: v, selected: String(c[k]) === String(v) }, l)));
    const num = (k, step, min, max) => h('input', { type: 'number', class: 'price', 'data-k': k, step, min, max, value: c[k] ?? '', onchange: set(k, (v) => v === '' ? 0 : +v) });
    const row = (label, ...el) => h('div', { class: 'row' }, h('span', {}, label), ...el);
    box.append(...[
      row('מידה (ס"מ):', sel('size', [...this.C.sizes.map(x => [x.id, x.label]), ['custom', 'מידה אחרת…']])),
      c.size === 'custom' ? row('רוחב × אורך (ס"מ), באריזה:', num('w_cm', 1, 5, 300), ' × ', num('l_cm', 1, 5, 300), ' · ', num('perBox', 1, 1, 100)) : null,
      row('גימור:', sel('finish', this.C.finishes.map(x => [x.id, x.label])), h('i', { class: 'swc', style: `background:${(this.finBy[c.finish]?.swatch || this.finBy[c.finish]?.color)}` })),
      row('דוגמה:', sel('pattern', this.C.patterns.map(x => [x.id, x.label]))),
      row('כיוון:', sel('direction', this.C.directions.map(x => [x.id, x.label]))),
      row('נקודת התחלה:', sel('origin', this.C.origins.map(x => [x.id, x.label]))),
      row('פוגה (מ"מ):', sel('joint_mm', this.C.joints_mm.map(v => [v, String(v)]), (v) => +v)),
      row('הזזה (ס"מ) לאורך / לרוחב:', num('du_cm', 0.5), num('dv_cm', 0.5)),
      row('רזרבה (%):', num('spare_pct', 1, 0, 30))].filter(Boolean));
    box.append(h('div', { class: 'btns' },
      h('button', { class: 'primary', 'data-act': 'optimize', onclick: () => {
        this.app.ui.toast('מחפש את הפריסה הטובה…');
        setTimeout(() => { const r = this.optimizeZone(z.key); if (r) { this.setChoice(z.key, { du_cm: r.du_cm, dv_cm: r.dv_cm }); this.app.ui.toast(`פריסה מושלמת: הזזה ${r.du_cm} / ${r.dv_cm} ס"מ (ציון ${f2(r.before)} → ${f2(r.score)})`); } }, 30);
      } }, '⚡ פריסה מושלמת'),
      h('button', { class: 'small', onclick: () => this.setChoice(z.key, { du_cm: 0, dv_cm: 0 }) }, 'איפוס הזזה'),
      h('button', { class: 'small', onclick: () => this.applyAll(c, (x) => x.floor === z.floor && x.key !== z.key) }, `העתק לכל ${FLOOR_HE[z.floor]}`),
      h('button', { class: 'small', onclick: () => this.applyAll(c, (x) => x.r.roomType === z.r.roomType && x.key !== z.key) }, 'העתק לחדרים מאותו סוג'),
      h('button', { class: 'small x', onclick: () => this.setChoice(z.key, null) }, 'הסר ריצוף')));
    const lay = this.layout(z.key);
    box.append(this.plan(z.key), this.statsEl = this.statsBox(lay),
      h('div', { class: 'muted legend' }, h('i', { class: 'swc', style: `background:${(this.finBy[c.finish]?.swatch || this.finBy[c.finish]?.color)}` }), ' שלם/חתוך · ', h('i', { class: 'swc', style: `background:${this.D.narrowColor}` }), ' מתחת לשליש אריח · ',
        h('i', { class: 'swc', style: `background:${this.D.sliverColor}` }), ` צר מ-${Math.round(this.C.cuts.hardMin_m * 100)} ס"מ (המספר = רוחב החיתוך בס"מ) · ✚ אריח ההתחלה · גרירה = הזזה`));
    const q = lay.q;
    box.append(h('table', { class: 'qty' },
      [['שטח האזור', `${f2(q.area_m2)} מ"ר`], ['אריחים בפריסה', `${q.layTiles} (${q.full} שלמים + ${q.cut} חתוכים)`], ['אריחים לפנלים', `${q.skirtingTiles} (${f2(z.r.skirting_m)} מ"א, גובה ${Math.round(this.C.consumption.skirtingHeight_m * 100)} ס"מ)`],
        ['להזמנה', `${q.order} אריחים · ${q.boxes} קרטונים × ${q.perBox} · ${f2(q.order_m2)} מ"ר (רזרבה ${c.spare_pct}%)`],
        ['דבק', `${f0(q.adhesive_kg)} ק"ג · ${q.adhesiveBags} שקים × ${this.C.consumption.adhesiveBag_kg}`], ['רובה', `${f2(q.grout_kg)} ק"ג · ${q.groutBags} שקים × ${this.C.consumption.groutBag_kg}`],
        ...z.r.layers.filter(l => l.id === 'floorFill' || l.id === 'floorScreed').map(l => [this.F.BU.layers.find(x => x.id === l.id)?.short || l.id, `${f2(z.r.area * l.thickness_m)} מ"ק (${f2(l.thickness_m * 100)} ס"מ, זמני)`])]
        .map(([k, v]) => h('tr', {}, h('td', {}, k), h('td', {}, v)))),
      h('div', { class: 'muted' }, 'מקדמי צריכה (דבק, רובה, אריחים בקרטון, גובה פנל) – זמניים, לפי היצרן שייבחר (open-issues #178).'));
    return box;
  }
  applyAll(c, pred) {
    const tgt = this.zones.filter(pred);
    for (const z of tgt) this.setChoice(z.key, { ...c, du_cm: 0, dv_cm: 0 }, { rebuild: false });
    this.rebuild(); this.refresh();
    this.app.ui.toast(`הוחל על ${tgt.length} אזורים (הזזה מאופסת – אפשר "פריסה מושלמת" לכל אזור)`);
  }

  // ---------------------------------------------------------------- totals (order list)
  totals() {
    const zones = [], order = {};
    for (const z of this.zones) {
      const c = this.choice[z.key]; if (!c) continue;
      const L = this.layout(z.key), fin = this.finBy[c.finish];
      zones.push({ z, c, L, fin });
      const k = L.size.label + '|' + fin.label;
      const o = order[k] ||= { size: L.size.label, finish: fin.label, color: fin.swatch || fin.color, area: 0, tiles: 0, order: 0, boxes: 0, perBox: L.q.perBox, adh: 0, grout: 0, zones: 0 };
      o.area += L.q.area_m2; o.tiles += L.q.layTiles + L.q.skirtingTiles; o.order += L.q.order; o.zones++; o.adh += L.q.adhesive_kg; o.grout += L.q.grout_kg;
    }
    for (const o of Object.values(order)) o.boxes = Math.ceil(o.order / o.perBox);
    return { zones, order: Object.values(order), area: zones.reduce((a, x) => a + x.L.q.area_m2, 0), all: this.zones.reduce((a, z) => a + z.r.area, 0) };
  }
  totalsBox() {
    const T = this.totals(), cons = this.C.consumption;
    const box = h('div', {});
    box.append(h('h4', {}, `כמויות להזמנה (${T.zones.length} מתוך ${this.zones.length} אזורים · ${f2(T.area)} מתוך ${f2(T.all)} מ"ר)`));
    if (T.order.length) box.append(h('table', { class: 'qty' },
      h('tr', {}, h('th', {}, ''), h('th', {}, 'אריח'), h('th', {}, 'מ"ר'), h('th', {}, 'אריחים'), h('th', {}, 'קרטונים'), h('th', {}, 'דבק ק"ג'), h('th', {}, 'רובה ק"ג')),
      T.order.map(o => h('tr', {}, h('td', {}, h('i', { class: 'swc', style: `background:${o.color}` })), h('td', {}, `${o.size} ${o.finish}`), h('td', {}, f2(o.area)), h('td', {}, o.order), h('td', {}, o.boxes), h('td', {}, f0(o.adh)), h('td', {}, f2(o.grout)))),
      h('tr', { class: 'tot' }, h('td', {}, ''), h('td', {}, 'סה"כ'), h('td', {}, f2(T.area)), h('td', {}, T.order.reduce((a, o) => a + o.order, 0)), h('td', {}, T.order.reduce((a, o) => a + o.boxes, 0)),
        h('td', {}, `${f0(T.order.reduce((a, o) => a + o.adh, 0))} (${Math.ceil(T.order.reduce((a, o) => a + o.adh, 0) / cons.adhesiveBag_kg)} שקים)`), h('td', {}, `${f2(T.order.reduce((a, o) => a + o.grout, 0))} (${Math.ceil(T.order.reduce((a, o) => a + o.grout, 0) / cons.groutBag_kg)} שקים)`))));
    // the fill / screed under all the zones (with or without a tile) – m³
    const vol = {};
    for (const z of this.zones) for (const l of z.r.layers) if (l.thickness_m) vol[l.id] = (vol[l.id] || 0) + z.r.area * l.thickness_m;
    box.append(h('div', { class: 'muted' }, 'מתחת לריצוף (כל האזורים): ' + this.F.BU.layers.filter(l => ['floorFill', 'floorScreed'].includes(l.id)).map(l => `${l.short || l.label} ${f2(vol[l.id] || 0)} מ"ק`).join(' · ') + ' (עוביים זמניים)'));
    box.append(h('div', { class: 'btns' }, h('button', { onclick: () => this.exportXlsx() }, '⬇ ייצוא ל-Excel (xlsx)')));
    return box;
  }
  async exportXlsx() {
    let X; try { X = await this.F.loadXlsx(); } catch { this.app.ui.toast('טעינת ספריית האקסל נכשלה'); return; }
    const T = this.totals(), wb = X.utils.book_new();
    const sheet = (name, rows) => { const ws = X.utils.aoa_to_sheet(rows); ws['!cols'] = rows[0].map((_, i) => ({ wch: i < 2 ? 26 : 13 })); X.utils.book_append_sheet(wb, ws, name); };
    sheet('אזורים', [['קומה', 'אזור', 'שטח מ"ר', 'אריח (ס"מ)', 'גימור', 'דוגמה', 'כיוון', 'התחלה', 'פוגה מ"מ', 'הזזה ס"מ', 'שלמים', 'חתוכים', 'צרים מ-5 ס"מ', 'מתחת לשליש', 'חיתוך מינימלי ס"מ', 'פחת חיתוך %', 'אריחים לפנלים', 'פנלים מ"א', 'רזרבה %', 'להזמנה (אריחים)', 'קרטונים', 'מ"ר להזמנה', 'דבק ק"ג', 'רובה ק"ג'],
      ...T.zones.map(({ z, c, L, fin }) => [FLOOR_HE[z.floor], z.name, +L.q.area_m2.toFixed(2), L.size.label, fin.label, L.pat.label, L.dir.label, this.C.origins.find(o => o.id === c.origin)?.label, c.joint_mm, `${c.du_cm || 0} / ${c.dv_cm || 0}`,
        L.q.full, L.q.cut, L.q.slivers, L.q.narrow, L.q.minCut_m != null ? +(L.q.minCut_m * 100).toFixed(1) : '', +L.q.waste_pct.toFixed(1), L.q.skirtingTiles, +(z.r.skirting_m || 0).toFixed(2), c.spare_pct, L.q.order, L.q.boxes, +L.q.order_m2.toFixed(2), +L.q.adhesive_kg.toFixed(1), +L.q.grout_kg.toFixed(2)]),
      ...this.zones.filter(z => !this.choice[z.key]).map(z => [FLOOR_HE[z.floor], z.name, +z.r.area.toFixed(3), 'לא נבחר'])]);
    sheet('הזמנה', [['אריח', 'גימור', 'מ"ר', 'אריחים', 'קרטונים', 'באריזה', 'דבק ק"ג', 'רובה ק"ג', 'אזורים'], ...T.order.map(o => [o.size, o.finish, +o.area.toFixed(2), o.order, o.boxes, o.perBox, +o.adh.toFixed(1), +o.grout.toFixed(2), o.zones]),
      [], ['מקדמי צריכה – זמניים (data/finishes/tiling/catalog.json, open-issues #178)']]);
    sheet('שכבות רצפה', [['קומה', 'אזור', 'שטח מ"ר', ...this.F.BU.layers.map(l => `${l.short || l.label} (ס"מ)`), ...this.F.BU.layers.filter(l => l.id !== 'floorTile').map(l => `${l.short || l.label} מ"ק`)],
      ...this.zones.map(z => [FLOOR_HE[z.floor], z.name, +z.r.area.toFixed(3), ...this.F.BU.layers.map(l => +((z.r.layers.find(x => x.id === l.id)?.thickness_m || 0) * 100).toFixed(1)),
        ...this.F.BU.layers.filter(l => l.id !== 'floorTile').map(l => +(z.r.area * (z.r.layers.find(x => x.id === l.id)?.thickness_m || 0)).toFixed(3))])]);
    const name = 'tiling-5187.xlsx';
    const buf = X.write(wb, { type: 'array', bookType: 'xlsx' });
    const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const dl = window.claude?.use ? await window.claude.use('downloads').catch(() => null) : null;
    if (dl) { try { await dl.save({ filename: name, data: blob }); } catch (e) { this.app.ui.toast(e?.code === 'declined' ? 'הייצוא בוטל' : 'הייצוא נכשל'); } return; }
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
}

import * as THREE from 'three';
import { layoutCoping, cutList } from './coping.js';

// Pool tiling + coping ("סדנת ריצוף ← בריכה"): one tile for the pool (floor / walls / steps + platform, each its own colour),
// a contrasting strip on the step edges, and the coping on the pool wall tops (material, piece length, thickness,
// overhang, joint, edge). Geometry: data/finishes/pool/surfaces.json (tools/finishes/derive_pool_finish.py ← pool.json);
// options: data/finishes/pool/catalog.json (provisional); the choice kept in the repo: data/finishes/pool/layout.json, the live
// one in the artifact database (collection "tiling", doc kind "pool"). No dimension is written here.

const LS = 'house3d.poolTiling';
const DOC = 'pool';
const f2 = (v) => (Math.round(v * 100) / 100).toLocaleString('he-IL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const f0 = (v) => Math.round(v).toLocaleString('he-IL');
const f1 = (v) => (Math.round(v * 10) / 10).toLocaleString('he-IL', { maximumFractionDigits: 1 });
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
const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);

export class PoolFinish {
  constructor(F) {
    this.F = F; const data = F.ctx.data;
    this.S = data.poolSurfaces; this.C = data.poolCatalog;
    this.tileBy = Object.fromEntries(this.C.tiles.map(x => [x.id, x]));
    this.colBy = Object.fromEntries(this.C.colors.map(x => [x.id, x]));
    this.copBy = Object.fromEntries(this.C.coping.materials.map(x => [x.id, x]));
    this.saved = data.poolLayout?.pool || null;
    this.choice = this.saved;
    try { const l = JSON.parse(localStorage.getItem(LS) || 'null'); if (l?.choice) this.choice = l.choice; } catch {}
    this.state = 'local'; this.items = []; this.mats = {}; this.texs = {};
    // pool frame: u along the long side of the water face from the first inner corner, v across (into the water)
    const R = this.S.innerRingITM, a = this.S.axis_deg * Math.PI / 180;
    this.o = R[0]; this.du = [Math.cos(a), Math.sin(a)];
    const c = R.reduce((s, p) => [s[0] + p[0] / R.length, s[1] + p[1] / R.length], [0, 0]);
    const n = [-this.du[1], this.du[0]]; const side = (c[0] - this.o[0]) * n[0] + (c[1] - this.o[1]) * n[1] > 0 ? 1 : -1;
    this.dv = [n[0] * side, n[1] * side];
  }
  // the effective choice: defaults ← the saved / live choice (null = not chosen yet: the defaults are shown, marked provisional)
  get c() { const d = this.C.defaults, x = this.choice || {}; return { ...d, ...x, coping: { ...d.coping, ...(x.coping || {}) } }; }
  chosen() { return !!this.choice; }
  saveLocal() { try { localStorage.setItem(LS, JSON.stringify({ choice: this.choice })); } catch {} }
  async connect(app) {
    this.app = app;
    const use = window.claude?.use; const db = use ? await use('db').catch(() => null) : null;
    if (!db) return;
    this.col = db.collection('tiling'); this.state = 'online';
    this.col.onSnapshot((snap) => {
      let next = this.saved;
      for (const d of snap.docs) { const x = d.data(); if (x.kind !== 'pool') continue; next = x.cleared ? null : x.choice; }
      if (JSON.stringify(next) === JSON.stringify(this.choice)) return;
      this.choice = next; this.saveLocal(); this.rebuild(); this.refresh();
    }, () => { this.state = 'local'; });
  }
  async set(patch) {
    const cur = this.choice || {};
    this.choice = patch === null ? null : { ...cur, ...patch, coping: { ...(cur.coping || {}), ...(patch.coping || {}) } };
    this.saveLocal(); this.rebuild(); this.refresh();
    if (this.col) {
      const doc = this.choice === null ? { kind: 'pool', cleared: true } : { kind: 'pool', choice: this.choice };
      try { await this.col.doc(DOC).set({ ...doc, at: new Date().toISOString() }); } catch { this.app?.ui.toast('השמירה במסד נכשלה – נשמר בדפדפן'); }
    }
  }
  refresh() { this.app?.ui.refreshPanel('tiling'); this.app?.viewer.invalidate(); }

  // ---------------------------------------------------------------- geometry helpers (ITM + absolute height → scene)
  V(E, N, H) { return this.F.V(E, N, H - this.F.ctx.coords.H0); }
  uv([E, N]) { const x = E - this.o[0], y = N - this.o[1]; return [x * this.du[0] + y * this.du[1], x * this.dv[0] + y * this.dv[1]]; }
  copingBottom() { return this.S.copingTop - this.c.coping.thick_m; }
  surfColor(k) { const c = this.c; return this.colBy[(k === 'walls' ? c.wallColor : k === 'steps' ? c.stepColor : '') || c.color] || this.C.colors[0]; }

  // ---------------------------------------------------------------- quantities
  quantities() {
    const S = this.S, A = S.areas, c = this.c, t = this.tileBy[c.tile] || this.C.tiles[0], cons = this.C.consumption;
    const wallH = this.copingBottom() - S.floor;
    const walls = A.perimeterInner_m * wallH - A.wallCoveredByBlocks_m2;
    const edge = c.stepEdge ? this.edgeRuns().reduce((s, e) => s + e.len, 0) : 0;
    const edgeW = c.stepEdge ? c.stepEdgeWidth_m : 0;
    const steps = A.blockTops_m2 + A.blockSides_m2;
    const total = A.floorNet_m2 + walls + steps;
    const spare = 1 + (c.spare_pct || 0) / 100;
    const units = (m2) => Math.ceil(m2 * spare / t.unit_m2);
    const mosaic = t.unit === 'sheet';
    const cop = this.copingPieces();
    const cm = this.copBy[c.coping.material] || this.C.coping.materials[0];
    return {
      tile: t, wallH, floor: A.floorNet_m2, walls, steps, edge_m: edge, edge_m2: edge * edgeW, total,
      units: units(total), unitLabel: mosaic ? 'רשתות' : 'קרטונים', order_m2: units(total) * t.unit_m2,
      adhesive_kg: total * (mosaic ? cons.adhesive_kg_m2.mosaic : cons.adhesive_kg_m2.tile), epoxy_kg: total * (cons.epoxy_kg_m2[t.id] ?? 0.5),
      coping: (() => { const L = this.copingLayout(), len = L.runs.reduce((s, r) => s + (r.outer_m + r.pieces.reduce((a, p) => a + p.inner_m, 0) + (r.pieces.length - 1) * L.opt.joint_m) / 2, 0);
        const cuts = L.pieces.reduce((a, p) => a + p.cuts.length, 0), mj = L.runs.reduce((a, r) => a + r.joints.filter(j => j.movement).length, 0);
        return { mat: cm, lay: L, pieces: L.pieces.length, runs: cop.runs, len_m: len, width_m: L.W, cuts, stock: L.stock, order: Math.ceil(L.stock.units * spare),
          movement: mj + L.corners.length, sealant_m: mj * L.W + L.corners.reduce((a, x) => a + x.length_m, 0), mortar_kg: len * cons.copingMortar_kg_m, area_m2: len * L.W }; })(),
    };
  }

  // the step edges: the top edge of every step riser + the exposed edges of the platform (contrast strip, inward)
  edgeRuns() {
    const S = this.S, byId = Object.fromEntries(S.blocks.map(b => [b.id, b]));
    return S.blockFaces.filter(f => f.riser || byId[f.block].kind === 'platform').map(f => ({ a: f.a, b: f.b, n: f.normal, top: f.z1, len: dist(f.a, f.b), face: f }));
  }

  // coping layout (src/tiling/coping.js): mitre / butt corners, symmetric from the middle of each side, cut list, stock
  copingLayout() {
    const c = this.c.coping, k = JSON.stringify(c);
    if (this._cop?.k === k) return this._cop.lay;
    const lay = layoutCoping({ ring: this.S.innerRingITM, wt: this.S.wallThickness_m, oh: c.overhang_m, stockW: c.stockW_m,
      opt: { ...this.C.coping.rules, corner: c.corner, layout: c.layout, length_m: c.length_m, joint_mm: c.joint_mm, edge: c.edge } });
    this._cop = { k, lay }; return lay;
  }
  copingPieces() { const L = this.copingLayout(); return { runs: L.runs.map(r => ({ i: r.side, len: r.outer_m, k: r.pieces.length, piece_m: Math.max(...r.pieces.map(p => p.outer_m)), long: r.long })), pieces: L.pieces }; }

  // ---------------------------------------------------------------- materials
  // tile texture: a canvas of n × m tiles with joints in the grout colour and a shade per tile; a bump map from the same
  // layout (joints recessed). UV in metres / the repeat of the canvas.
  tileTex(t, col) {
    const k = t.id + '|' + col.id;
    if (this.texs[k]) return this.texs[k];
    const mu = t.l_m + t.joint_mm / 1000, mv = t.w_m + t.joint_mm / 1000;
    const nu = Math.max(2, Math.round(0.45 / mu)), nv = Math.max(2, Math.round(0.45 / mv));
    const W = 512, Hh = Math.max(64, Math.round(W * (nv * mv) / (nu * mu)));
    const pxm = W / (nu * mu), jp = Math.max(1.4, (t.joint_mm / 1000) * pxm);
    const mk = () => { const cv = document.createElement('canvas'); cv.width = W; cv.height = Hh; return [cv, cv.getContext('2d')]; };
    const [cv, g] = mk(), [bv, bg] = mk();
    g.fillStyle = col.grout; g.fillRect(0, 0, W, Hh); bg.fillStyle = '#000'; bg.fillRect(0, 0, W, Hh);
    const base = new THREE.Color(col.color), tmp = new THREE.Color();
    for (let i = 0; i < nu; i++) for (let jj = 0; jj < nv; jj++) {
      const kf = 1 + (rnd(i + 3, jj + 7) - 0.5) * 2 * (col.vary || 0);
      tmp.copy(base).multiplyScalar(kf);
      const x0 = i * mu * pxm + jp / 2, y0 = jj * mv * pxm + jp / 2, w = mu * pxm - jp, hh = mv * pxm - jp;
      g.fillStyle = '#' + tmp.getHexString(); g.fillRect(x0, y0, w, hh);
      bg.fillStyle = '#fff'; bg.fillRect(x0, y0, w, hh);
    }
    const tx = new THREE.CanvasTexture(cv), bx = new THREE.CanvasTexture(bv);
    for (const x of [tx, bx]) { x.wrapS = x.wrapT = THREE.RepeatWrapping; x.anisotropy = 8; x.repeat.set(1 / (nu * mu), 1 / (nv * mv)); }
    tx.colorSpace = THREE.SRGBColorSpace;
    return (this.texs[k] = { map: tx, bump: bx });
  }
  tileMat(t, col) {
    const k = 't|' + t.id + '|' + col.id;
    if (this.mats[k]) return this.mats[k];
    const T = this.tileTex(t, col), glass = t.unit === 'sheet';
    return (this.mats[k] = new THREE.MeshStandardMaterial({ map: T.map, bumpMap: T.bump, bumpScale: 0.6, roughness: glass ? 0.12 : 0.35, metalness: 0, envMapIntensity: 1.0,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
  }
  copMat(cm) {
    const k = 'c|' + cm.id;
    if (this.mats[k]) return this.mats[k];
    const m = new THREE.MeshStandardMaterial({ color: '#ffffff', vertexColors: true, roughness: cm.roughness ?? 0.7, metalness: 0, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    if (cm.texture) {
      const ld = (f) => { const tx = new THREE.TextureLoader().load(`${cm.texture}/${f}`, () => this.F.ctx.viewer?.invalidate()); tx.wrapS = tx.wrapT = THREE.RepeatWrapping; tx.repeat.set(1 / cm.texSize_m, 1 / cm.texSize_m); return tx; };
      m.normalMap = ld('normal.jpg'); m.normalScale.set(0.5, 0.5); m.roughnessMap = ld('roughness.webp');
    }
    return (this.mats[k] = m);
  }

  // ---------------------------------------------------------------- 3D
  mesh(pos, uv, mat, col) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    if (col) g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, mat); m.receiveShadow = true; m.castShadow = !!col; m.userData.keep = true; return m;
  }
  build3D() {
    this.built = true; this.removeItems();
    const S = this.S, c = this.c, t = this.tileBy[c.tile] || this.C.tiles[0], off = 0.001;
    const zb = this.copingBottom();
    const G = { floor: { pos: [], uv: [] }, walls: { pos: [], uv: [] }, steps: { pos: [], uv: [] }, edge: { pos: [], uv: [] } };
    const quad = (g, P, U) => { for (const i of [0, 1, 2, 0, 2, 3]) { g.pos.push(...P[i]); g.uv.push(...U[i]); } };
    const flat = (g, ring, H) => {   // horizontal polygon at H (absolute), uv in the pool frame
      const pts = ring.map(p => new THREE.Vector2(p[0], p[1])); if (THREE.ShapeUtils.isClockWise(pts)) pts.reverse();
      for (const tr of THREE.ShapeUtils.triangulateShape(pts, [])) for (const i of tr) { const p = [pts[i].x, pts[i].y]; g.pos.push(...this.V(p[0], p[1], H)); g.uv.push(...this.uv(p)); }
    };
    // floor (the whole water face; under the steps / platform it is hidden by them)
    flat(G.floor, S.innerRingITM, S.floor + off);
    // walls: the water face from the floor to the coping underside – u along the perimeter, v down from the top (a full row under the coping)
    const R = S.innerRingITM; let s = 0;
    const ctr = R.reduce((q, p) => [q[0] + p[0] / R.length, q[1] + p[1] / R.length], [0, 0]);
    for (let i = 0; i < R.length; i++) {
      const a = R[i], b = R[(i + 1) % R.length], L = dist(a, b);
      const ia = [a[0] + (ctr[0] - a[0]) * off / dist(a, ctr), a[1] + (ctr[1] - a[1]) * off / dist(a, ctr)], ib = [b[0] + (ctr[0] - b[0]) * off / dist(b, ctr), b[1] + (ctr[1] - b[1]) * off / dist(b, ctr)];
      quad(G.walls, [this.V(...ia, S.floor), this.V(...ib, S.floor), this.V(...ib, zb), this.V(...ia, zb)], [[s, zb - S.floor], [s + L, zb - S.floor], [s + L, 0], [s, 0]]);
      s += L;
    }
    // steps + platform: tops (pool frame) and exposed sides (u across the pool – the joints line up with the treads, v down from the top)
    for (const bl of S.blocks) flat(G.steps, bl.ringITM, bl.top + off);
    for (const f of S.blockFaces) {
      const a = [f.a[0] + f.normal[0] * off, f.a[1] + f.normal[1] * off], b = [f.b[0] + f.normal[0] * off, f.b[1] + f.normal[1] * off];
      const ua = f.riser ? this.uv(f.a)[1] : this.uv(f.a)[0], ub = f.riser ? this.uv(f.b)[1] : this.uv(f.b)[0];
      const g = c.stepEdge && f.riser ? G.edge : G.steps;
      quad(g, [this.V(...a, f.z0), this.V(...b, f.z0), this.V(...b, f.z1), this.V(...a, f.z1)], [[ua, f.z1 - f.z0], [ub, f.z1 - f.z0], [ub, 0], [ua, 0]]);
    }
    // contrast strip on the step / platform edges (on the tread, inward from the edge)
    if (c.stepEdge) for (const e of this.edgeRuns()) {
      const w = c.stepEdgeWidth_m, a = e.a, b = e.b, ia = [a[0] - e.n[0] * w, a[1] - e.n[1] * w], ib = [b[0] - e.n[0] * w, b[1] - e.n[1] * w], H = e.top + 2 * off;
      quad(G.edge, [this.V(...a, H), this.V(...b, H), this.V(...ib, H), this.V(...ia, H)], [this.uv(a), this.uv(b), this.uv(ib), this.uv(ia)]);
    }
    const q = this.quantities(), prov = this.chosen() ? '' : ' (ברירת מחדל – טרם נבחר)';
    const meta = (name, rows) => ({ name, kind: 'poolTiles', id: 'POOL-' + name, pickable: true, status: 'provisional', rows,
      source: 'src/tiling/pool.js – data/finishes/pool/catalog.json; משטחים: data/finishes/pool/surfaces.json ← data/structure/pool.json', note: 'מידות אריח, אריזה ומקדמי צריכה – זמניים (open-issues #194).',
      onClick: () => this.app?.ui.openTab('tiling') });
    const add = (g, col, name, rows) => {
      if (!g.pos.length) return;
      const grp = new THREE.Group(); grp.add(this.mesh(g.pos, g.uv, this.tileMat(t, col)));
      this.items.push(this.F.add(grp, { floor: 'unit', step: 'tiling', layer: 'poolTile' }, meta(name, rows)));
    };
    add(G.floor, this.surfColor('floor'), 'ריצוף רצפת הבריכה' + prov, [['אריח', `${t.label} · ${this.surfColor('floor').label}`], ['שטח (נטו)', `${f2(q.floor)} מ"ר`], ['מפלס', this.F.ctx.coords.fmtH(S.floor)]]);
    add(G.walls, this.surfColor('walls'), 'ריצוף קירות הבריכה' + prov, [['אריח', `${t.label} · ${this.surfColor('walls').label}`], ['גובה', `${f2(q.wallH)} מ' (רצפה → תחתית הקופינג)`], ['שטח', `${f2(q.walls)} מ"ר`]]);
    add(G.steps, this.surfColor('steps'), 'ריצוף מדרגות ומשטח רביצה' + prov, [['אריח', `${t.label} · ${this.surfColor('steps').label}`], ['שטח', `${f2(q.steps)} מ"ר (שלחים, רומים, צדדים)`]]);
    add(G.edge, this.colBy[c.stepEdgeColor] || this.C.colors[0], 'פס סימון בשפת המדרגות' + prov, [['צבע', this.colBy[c.stepEdgeColor]?.label], ['אורך', `${f2(q.edge_m)} מ"א · רוחב ${Math.round(c.stepEdgeWidth_m * 100)} ס"מ + הרום`]]);
    this.buildCoping(q, prov);
  }
  buildCoping(q, prov) {
    const c = this.c.coping, cm = this.copBy[c.material] || this.C.coping.materials[0], L = q.coping.lay;
    const zt = this.S.copingTop, zb = zt - c.thick_m, r = c.edge === 'bull' ? c.thick_m / 2 : 0, wt = this.S.wallThickness_m, oh = c.overhang_m;
    // the water edge profile (t, z) from the bottom up: square – straight; bullnose – a half round of radius thickness / 2
    const prof = r ? Array.from({ length: 9 }, (_, k) => { const f = -Math.PI / 2 + k * Math.PI / 8; return [-oh + r - r * Math.cos(f), zt - r + r * Math.sin(f)]; }) : [[-oh, zb], [-oh, zt]];
    const pos = [], uv = [], col = [], base = new THREE.Color(cm.color), tmp = new THREE.Color(), cutTint = new THREE.Color(this.D?.copingCutColor || '#ffb74d');
    const mark = this.app?.store.get().mode === 'tiling' && this.showCopingCuts;
    for (const p of L.pieces) {
      const run = L.runs[p.side];
      const W = (sv, tv, z) => this.V(run.a[0] + run.d[0] * sv + run.n[0] * tv, run.a[1] + run.d[1] * sv + run.n[1] * tv, z);
      const sA = (t) => p.A.c + p.A.k * t, sB = (t) => p.B.c + p.B.k * t;
      tmp.copy(base).multiplyScalar(1 + (rnd(p.side + 5, p.q + 9) - 0.5) * 2 * (cm.vary || 0));
      if (mark && p.type !== 'full') tmp.lerp(cutTint, 0.45);
      const ou = rnd(p.q, p.side) * 5;
      const push = (P3, u, v) => { pos.push(...P3); uv.push(u + ou, v); col.push(tmp.r, tmp.g, tmp.b); };
      const quad = (P0, P1, P2, P3) => { for (const [P3d, u, v] of [P0, P1, P2, P0, P2, P3]) push(P3d, u, v); };
      // rings from the bottom to the top: [water A, water B, outer B, outer A] at each profile point
      const ring = ([te, z]) => [[W(sA(te), te, z), sA(te), te], [W(sB(te), te, z), sB(te), te], [W(sB(wt), wt, z), sB(wt), wt], [W(sA(wt), wt, z), sA(wt), wt]];
      const rings = prof.map(ring);
      // outer (gutter side) and the ends span the profile heights too: add the outer bottom / top
      for (let k = 0; k + 1 < rings.length; k++) {
        const r0 = rings[k], r1 = rings[k + 1], z0 = prof[k][1], z1 = prof[k + 1][1];
        quad(...[[r0[0][0], r0[0][1], z0], [r0[1][0], r0[1][1], z0], [r1[1][0], r1[1][1], z1], [r1[0][0], r1[0][1], z1]]);   // water edge
        quad(...[[r0[1][0], r0[1][2], z0], [r0[2][0], r0[2][2], z0], [r1[2][0], r1[2][2], z1], [r1[1][0], r1[1][2], z1]]);   // end B
        quad(...[[r0[2][0], r0[2][1], z0], [r0[3][0], r0[3][1], z0], [r1[3][0], r1[3][1], z1], [r1[2][0], r1[2][1], z1]]);   // outer
        quad(...[[r0[3][0], r0[3][2], z0], [r0[0][0], r0[0][2], z0], [r1[0][0], r1[0][2], z1], [r1[3][0], r1[3][2], z1]]);   // end A
      }
      const top = rings.at(-1), bot = rings[0];
      quad(...top.map(x => [x[0], x[1], x[2]]));
      quad(...[bot[3], bot[2], bot[1], bot[0]].map(x => [x[0], x[1], x[2]]));
    }
    const grp = new THREE.Group(); grp.add(this.mesh(pos, uv, this.copMat(cm), col));
    const st = L.stock, cnt = (t) => L.pieces.filter(p => p.type === t).length;
    this.items.push(this.F.add(grp, { floor: 'unit', step: 'tiling', layer: 'poolCoping' }, { name: `קופינג – ${cm.label}${prov}`, kind: 'poolCoping', id: 'POOL-coping', pickable: true, status: 'provisional',
      rows: [['חומר', cm.label], ['חתך', `רוחב ${f1(L.W * 100)} ס"מ (קיר ${f1(wt * 100)} + בליטה ${f1(oh * 100)}) · עובי ${f1(c.thick_m * 100)} ס"מ · ${this.C.coping.edges.find(e => e.id === c.edge)?.label}`],
        ['פינות / פריסה', `${this.C.coping.corners.find(x => x.id === c.corner)?.label} · ${this.C.coping.layouts.find(x => x.id === c.layout)?.label}`],
        ['ראש', `${this.F.ctx.coords.fmtH(zt)} (= המשטח המרוצף)`],
        ['יחידות', `${L.pieces.length}: ${cnt('full')} שלמות, ${cnt('cut')} חתוכות, ${cnt('miterStart') + cnt('miterEnd') + cnt('miter2')} פינה`],
        ['מלאי', `${st.units} יחידות ${f1(c.length_m * 100)}×${f1(c.stockW_m * 100)}${st.miterPairs ? ` (${st.miterPairs} זוגות פינה מיחידה אחת)` : ''}`], ['אורך', `${f2(q.coping.len_m)} מ"א`]],
      source: 'src/tiling/coping.js + pool.js – data/finishes/pool/catalog.json; ראש 280.48 – חתכי הבריכה (sources/structure/pool-walls/)', note: 'כללי פריסה מקובלים – אין מפרט קופינג במקורות; ראש בטון הקיר – לא כתוב (open-issues #194).',
      onClick: () => this.app?.ui.openTab('tiling') }));
  }
  removeItems() { const reg = this.F.ctx.registry; if (!this.items.length) return; reg.remove(this.items); this.F.items = this.F.items.filter(i => !this.items.includes(i)); this.items = []; }
  rebuild() { if (!this.built) return; this.build3D(); this.app?.store && this.F.ctx.registry.apply(this.app.store.get()); this.app?.viewer.invalidate(); }

  // ---------------------------------------------------------------- panel (inside the tiling workshop)
  panel() {
    const app = this.app, st = app.store.get(), c = this.c, q = this.quantities();
    const box = h('div', { class: 'zone-ed pool-ed' });
    box.append(h('h4', {}, `בריכה – ריצוף וקופינג${this.chosen() ? '' : ' (ברירת מחדל – טרם נבחר)'}`));
    const lay = ['poolTile', 'poolCoping'];
    box.append(h('div', { class: 'btns' },
      lay.map(id => { const v = st.layers[id] !== false; return h('button', { class: 'small' + (v ? ' on' : ''), onclick: () => app.store.set({ layers: { ...app.store.get().layers, [id]: !v } }, { label: 'layers' }) }, id === 'poolTile' ? 'ריצוף הבריכה' : 'קופינג'); }),
      h('button', { class: 'small', onclick: () => this.show() }, '👁 הצג במודל')));
    const set = (k, cast = (v) => v) => (e) => this.set({ [k]: cast(e.target.value) });
    const setC = (k, cast = (v) => v) => (e) => this.set({ coping: { [k]: cast(e.target.value) } });
    const sel = (val, opts, on) => h('select', { onchange: on }, opts.map(([v, l]) => h('option', { value: v, selected: String(val) === String(v) }, l)));
    const sw = (col) => h('i', { class: 'swc', style: `background:${col}` });
    const row = (label, ...el) => h('div', { class: 'row' }, h('span', {}, label), ...el);
    const colors = this.C.colors.map(x => [x.id, x.label]);
    box.append(
      row('אריח:', sel(c.tile, this.C.tiles.map(x => [x.id, x.label]), set('tile'))),
      row('צבע – רצפה:', sel(c.color, colors, set('color')), sw(this.surfColor('floor').color)),
      row('צבע – קירות:', sel(c.wallColor, [['', 'כמו הרצפה'], ...colors], set('wallColor')), sw(this.surfColor('walls').color)),
      row('צבע – מדרגות:', sel(c.stepColor, [['', 'כמו הרצפה'], ...colors], set('stepColor')), sw(this.surfColor('steps').color)),
      row('פס בשפת המדרגות:', h('input', { type: 'checkbox', checked: c.stepEdge, onchange: (e) => this.set({ stepEdge: e.target.checked }) }), c.stepEdge ? sel(c.stepEdgeColor, colors, set('stepEdgeColor')) : null, c.stepEdge ? sw(this.colBy[c.stepEdgeColor]?.color) : null),
      row('רזרבה (%):', h('input', { type: 'number', class: 'price', step: 1, min: 0, max: 30, value: c.spare_pct, onchange: set('spare_pct', (v) => +v || 0) })),
      h('h4', {}, 'קופינג'),
      row('חומר:', sel(c.coping.material, this.C.coping.materials.map(x => [x.id, x.label]), setC('material')), sw(this.copBy[c.coping.material]?.color)),
      row('פינות:', sel(c.coping.corner, this.C.coping.corners.map(x => [x.id, x.label]), setC('corner'))),
      row('פריסה:', sel(c.coping.layout, this.C.coping.layouts.map(x => [x.id, x.label]), setC('layout'))),
      row('יחידת מלאי – אורך (ס"מ):', sel(c.coping.length_m, this.C.coping.lengths_m.map(v => [v, Math.round(v * 100)]), setC('length_m', (v) => +v))),
      row('יחידת מלאי – רוחב (ס"מ):', sel(c.coping.stockW_m, this.C.coping.stockWidths_m.map(v => [v, Math.round(v * 100)]), setC('stockW_m', (v) => +v))),
      row('עובי (ס"מ):', sel(c.coping.thick_m, this.C.coping.thicknesses_m.map(v => [v, Math.round(v * 100)]), setC('thick_m', (v) => +v))),
      row('בליטה לבריכה (ס"מ):', sel(c.coping.overhang_m, this.C.coping.overhangs_m.map(v => [v, Math.round(v * 100)]), setC('overhang_m', (v) => +v))),
      row('פוגה (מ"מ):', sel(c.coping.joint_mm, this.C.coping.joint_mm.map(v => [v, v]), setC('joint_mm', (v) => +v))),
      row('שפה:', sel(c.coping.edge, this.C.coping.edges.map(x => [x.id, x.label]), setC('edge'))));
    box.append(h('div', { class: 'btns' },
      this.chosen() ? null : h('button', { class: 'primary', onclick: () => this.set({}) }, '✓ אשר בחירה זו'),
      this.chosen() ? h('button', { class: 'small x', onclick: () => this.set(null) }, 'חזרה לברירת המחדל') : null));
    const t = q.tile, cons = this.C.consumption;
    box.append(h('table', { class: 'qty' }, [
      ['רצפה (נטו, בלי המדרגות)', `${f2(q.floor)} מ"ר`],
      ['קירות', `${f2(q.walls)} מ"ר (גובה ${f2(q.wallH)} מ', היקף ${f2(this.S.areas.perimeterInner_m)} מ')`],
      ['מדרגות ומשטח רביצה', `${f2(q.steps)} מ"ר`],
      c.stepEdge ? ['מתוכם פס בשפה', `${f2(q.edge_m)} מ"א`] : null,
      ['סה"כ ריצוף', `${f2(q.total)} מ"ר`],
      ['להזמנה', `${q.units} ${q.unitLabel} × ${f2(t.unit_m2)} מ"ר = ${f2(q.order_m2)} מ"ר (רזרבה ${c.spare_pct}%)`],
      ['דבק לבריכות', `${f0(q.adhesive_kg)} ק"ג · ${Math.ceil(q.adhesive_kg / cons.adhesiveBag_kg)} שקים × ${cons.adhesiveBag_kg}`],
      ['רובה אפוקסי', `${f2(q.epoxy_kg)} ק"ג · ${Math.ceil(q.epoxy_kg / cons.epoxyPack_kg)} אריזות × ${cons.epoxyPack_kg}`],
].filter(Boolean).map(([k, v]) => h('tr', {}, h('td', {}, k), h('td', {}, v)))),
      h('div', { class: 'muted' }, `רצפה ${this.F.ctx.coords.fmtH(this.S.floor)}, ראש קופינג ${this.F.ctx.coords.fmtH(this.S.copingTop)} – מחתכי הבריכה. מידות אריח, אריזה, עובי וחתך קופינג ומקדמי צריכה – זמניים (open-issues #194).`));
    box.append(this.copingBox(q));
    return box;
  }
  // ---------------------------------------------------------------- coping: plan with dimensions, cut list, stock
  copingBox(q) {
    const L = q.coping.lay, c = this.c.coping, R = this.C.coping.rules, cl = cutList(L), st = L.stock;
    const TYPE = { full: 'שלמה', cut: 'חתוכה (ישר)', miterStart: 'פינה – מיטר בתחילת הצלע', miterEnd: 'פינה – מיטר בסוף הצלע', miter2: 'מיטר משני הצדדים' };
    const MODE = { 'center-joint': 'פוגה במרכז', 'center-piece': 'יחידה במרכז', equal: 'יחידות שוות', single: 'יחידה אחת' };
    const box = h('div', { class: 'coping-ed' });
    box.append(h('h4', {}, `קופינג – פריסה (${L.pieces.length} יחידות, ${f2(q.coping.len_m)} מ"א)`),
      h('div', { class: 'btns' }, h('label', { class: 'chk' }, h('input', { type: 'checkbox', checked: !!this.showCopingCuts, onchange: (e) => { this.showCopingCuts = e.target.checked; this.rebuild(); } }), ' סימון יחידות חתוכות במודל')),
      this.copingPlan(L));
    box.append(h('table', { class: 'qty' },
      h('tr', {}, h('th', {}, 'צלע'), h('th', {}, 'אורך חוץ'), h('th', {}, 'פריסה'), h('th', {}, 'קצוות (חוץ / מים)'), h('th', {}, 'תפרים')),
      L.runs.map(r => { const e0 = r.pieces[0], e1 = r.pieces.at(-1);
        return h('tr', {}, h('td', {}, `${r.side + 1}${r.long ? ' (ארוכה)' : ''}`), h('td', {}, `${f1(r.outer_m * 100)} ס"מ`),
          h('td', {}, `${MODE[r.mode]}${r.fallback ? ' (כלל 3)' : ''} · ${r.pieces.length} יח'`), h('td', {}, `${f1(e0.outer_m * 100)} / ${f1(e0.inner_m * 100)}${e1 !== e0 ? ` · ${f1(e1.outer_m * 100)} / ${f1(e1.inner_m * 100)}` : ''}`),
          h('td', {}, String(r.joints.filter(j => j.movement).length))); })));
    box.append(h('h4', {}, 'רשימת חיתוכים'), h('table', { class: 'qty' },
      h('tr', {}, h('th', {}, 'סוג'), h('th', {}, 'חוץ'), h('th', {}, 'צד מים'), h('th', {}, 'חיתוך'), h('th', {}, 'כמות'), h('th', {}, 'צלעות')),
      cl.map(x => { const bySide = {}; for (const w of x.where) { const sd = w.split('.')[0]; bySide[sd] = (bySide[sd] || 0) + 1; }
        return h('tr', {}, h('td', {}, TYPE[x.type]), h('td', {}, f1(x.outer_m * 100)), h('td', {}, f1(x.inner_m * 100)),
          h('td', {}, x.cuts.filter(t => !t.startsWith('חיתוך לאורך')).join(' + ') || '—'), h('td', {}, String(x.qty)), h('td', { class: 'muted' }, Object.entries(bySide).map(([k, v]) => `${k}:${v}`).join(' '))); })),
      h('div', { class: 'muted' }, `ס"מ · רוחב כל היחידות ${f1(L.W * 100)} ס"מ${L.rip ? ` – חיתוך לאורך בכל יחידה (מלאי ${f1(c.stockW_m * 100)})` : ''} · צלעות = מספר הצלע בתוכנית : כמות`));
    box.append(h('table', { class: 'qty' }, [
      ['חתך היחידה', `${f1(L.W * 100)} × ${f1(c.thick_m * 100)} ס"מ (קיר ${f1(this.S.wallThickness_m * 100)} + בליטה ${f1(c.overhang_m * 100)}) · ראש ${this.F.ctx.coords.fmtH(this.S.copingTop)}`],
      ['יחידות מלאי', `${st.units} × ${f1(c.length_m * 100)}×${f1(c.stockW_m * 100)} ס"מ (${st.full} שלמות · ${st.cutBins} לחיתוכים ישרים · ${st.miterStocks + st.both} לפינות${st.miterPairs ? `, מתוכן ${st.miterPairs} זוגות מיחידה אחת` : ''})`],
      ['להזמנה', `${q.coping.order} יחידות (רזרבה ${this.c.spare_pct}%) · ${f2(q.coping.order * c.length_m * c.stockW_m)} מ"ר`],
      ['חיתוכים', `${q.coping.cuts} (${L.rip ? `כולל חיתוך לאורך בכל יחידה – מ-${f1(c.stockW_m * 100)} ל-${f1(L.W * 100)}` : 'בלי חיתוך לאורך'})`],
      ['תפרי התפשטות', `${q.coping.movement} (4 פינות + כל ≤ ${f1(R.movementMax_m)} מ') · מילוי גמיש ${f2(q.coping.sealant_m)} מ"א`],
      ['דבק לקופינג', `${f0(q.coping.mortar_kg)} ק"ג`]].map(([k, v]) => h('tr', {}, h('td', {}, k), h('td', {}, v)))));
    box.append(h('div', { class: 'muted' }, `כללי הפריסה (אין מפרט במקורות – כללים מקובלים, זמני): פינות ${c.corner === 'miter' ? 'במיטר 45°' : 'ישרות'}; סימטריה סביב אמצע כל צלע – פוגה או יחידה במרכז, הנבחרת = יחידות הקצה הגדולות יותר; (כלל 3) יחידת פינה ≥ ${Math.round(R.minEndFrac * 100)}% מהמלאי בצד החוץ וגם ≥ ${Math.round((R.minInnerFrac || 0) * 100)}% (ולפחות ${f1(R.minEdge_m * 100)} ס"מ) בצד המים, אחרת יחידות שוות לאורך הצלע; אף יחידה לא ארוכה מהמלאי; פוגה ${c.joint_mm} מ"מ; תפר התפשטות בכל פינה וכל ≤ ${f1(R.movementMax_m)} מ'; מסור ${R.kerf_mm} מ"מ. מידות במילימטר: אורך חוץ = הצלע הפונה לתעלת הגלישה, צד מים = השפה מעל הבריכה. מיקום = צלע.יחידה (בתוכנית).`));
    return box;
  }
  copingPlan(L) {
    const SV = 'http://www.w3.org/2000/svg', sv = (t, a = {}) => { const e = document.createElementNS(SV, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
    const pts = [], polys = [];
    const pt = (run, sv_, tv) => { const E = run.a[0] + run.d[0] * sv_ + run.n[0] * tv, N = run.a[1] + run.d[1] * sv_ + run.n[1] * tv; const [u, v] = this.uv([E, N]); return [u, v]; };
    const wt = this.S.wallThickness_m, oh = this.c.coping.overhang_m;
    for (const p of L.pieces) { const run = L.runs[p.side];
      const P4 = [pt(run, p.A.c - p.A.k * oh, -oh), pt(run, p.B.c - p.B.k * oh, -oh), pt(run, p.B.c + p.B.k * wt, wt), pt(run, p.A.c + p.A.k * wt, wt)];
      polys.push({ p, P4, run }); pts.push(...P4); }
    const xs = pts.map(q => q[0]), ys = pts.map(q => q[1]), x0 = Math.min(...xs) - 0.5, x1 = Math.max(...xs) + 0.5, y0 = Math.min(...ys) - 0.55, y1 = Math.max(...ys) + 0.55;
    const svg = sv('svg', { class: 'coping-plan', viewBox: `${x0} ${y0} ${x1 - x0} ${y1 - y0}`, width: '100%' });
    svg.style.background = '#fff'; svg.style.border = '1px solid #ccc'; svg.style.direction = 'ltr';
    const cm = this.copBy[this.c.coping.material]; const col = { full: cm?.color || '#ddd', cut: '#ffcc80', miterStart: '#ffe0b2', miterEnd: '#ffe0b2', miter2: '#ffab91' };
    const water = this.S.innerRingITM.map(q => this.uv(q));
    svg.append(sv('polygon', { points: water.map(q => q.join(',')).join(' '), fill: '#cfe8f3', stroke: '#7aa', 'stroke-width': 0.01 }));
    const fs = 0.075;
    for (const { p, P4, run } of polys) {
      svg.append(sv('polygon', { points: P4.map(q => q.join(',')).join(' '), fill: col[p.type], stroke: '#333', 'stroke-width': 0.006 }));
      const c0 = P4.reduce((a, q) => [a[0] + q[0] / 4, a[1] + q[1] / 4], [0, 0]);
      const ang = Math.atan2(run.d[0] * this.dv[0] + run.d[1] * this.dv[1], run.d[0] * this.du[0] + run.d[1] * this.du[1]) * 180 / Math.PI;
      const a2 = ((ang % 180) + 270) % 180 - 90;
      const t = sv('text', { x: c0[0], y: c0[1], 'font-size': fs, 'text-anchor': 'middle', 'dominant-baseline': 'central', transform: `rotate(${a2} ${c0[0]} ${c0[1]})`, fill: '#222' });
      t.textContent = (Math.round(p.outer_m * 1000) / 10).toString(); svg.append(t);
    }
    // movement joints (red) – along the joint line across the coping
    for (const run of L.runs) for (const j of run.joints) if (j.movement) {
      const a = pt(run, j.s, -oh - 0.04), b = pt(run, j.s, wt + 0.04); svg.append(sv('line', { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: '#d32f2f', 'stroke-width': 0.02 }));
    }
    // overall dimension of each side (outer edge), outside the coping
    for (const run of L.runs) {
      const a = pt(run, run.S0, wt + 0.22), b = pt(run, run.S1, wt + 0.22), m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      svg.append(sv('line', { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: '#1565c0', 'stroke-width': 0.008 }));
      for (const q of [a, b]) svg.append(sv('circle', { cx: q[0], cy: q[1], r: 0.02, fill: '#1565c0' }));
      const ang = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI, a2 = ((ang % 180) + 270) % 180 - 90;
      const t = sv('text', { x: m[0], y: m[1] - 0.05, 'font-size': fs * 1.15, 'text-anchor': 'middle', fill: '#1565c0', transform: `rotate(${a2} ${m[0]} ${m[1]})` });
      t.textContent = `${run.side + 1}: ${(Math.round(run.outer_m * 1000) / 10)}`; svg.append(t);
    }
    for (const run of L.runs) {   // side number, inside the water
      const m = pt(run, (run.S0 + run.S1) / 2, -oh - 0.25);
      const t = sv('text', { x: m[0], y: m[1], 'font-size': fs * 2, 'text-anchor': 'middle', 'dominant-baseline': 'central', fill: '#0d47a1', 'font-weight': 'bold' }); t.textContent = String(run.side + 1); svg.append(t);
    }
    const legend = h('div', { class: 'muted legend' }, h('i', { class: 'swc', style: `background:${col.full}` }), ' שלמה · ', h('i', { class: 'swc', style: `background:${col.cut}` }), ' חתוכה · ',
      h('i', { class: 'swc', style: `background:${col.miterStart}` }), ' פינה (מיטר) · ', h('i', { class: 'swc', style: 'background:#d32f2f' }), ' תפר התפשטות · מספרים = אורך חוץ בס"מ, בכחול – אורך הצלע');
    const big = () => {   // full-screen view of the plan + the side strips
      const ov = h('div', { class: 'coping-overlay', style: 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.6);overflow:auto;padding:16px;direction:rtl', onclick: (e) => { if (e.target === ov) ov.remove(); } },
        h('div', { style: 'background:#fff;color:#111;max-width:1400px;margin:0 auto;padding:12px;border-radius:8px' },
          h('div', { class: 'btns' }, h('button', { class: 'primary', onclick: () => ov.remove() }, '✕ סגירה'), h('b', {}, ' קופינג – תוכנית פריסה ורצועות לפי צלע (מידות בס"מ)')),
          svg.cloneNode(true), ...L.runs.map(r => this.copingStrip(L, r, true))));
      document.body.append(ov);
    };
    return h('div', {}, svg, legend, h('div', { class: 'btns' }, h('button', { class: 'small primary', onclick: big }, '⤢ תוכנית גדולה + רצועות')),
      ...L.runs.map(r => this.copingStrip(L, r, false)));
  }
  // one side unrolled (shop drawing): every piece with its long / short edge, the joints, the movement joints, the chain of
  // dimensions along the outer edge (from the corner), the cuts
  copingStrip(L, run, big) {
    const SV = 'http://www.w3.org/2000/svg', sv = (t, a = {}) => { const e = document.createElementNS(SV, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };
    const wt = this.S.wallThickness_m, oh = this.c.coping.overhang_m, Wd = wt + oh;
    const len = run.outer_m, padX = 0.15, x = (sv_) => sv_ - run.S0 + padX, Y = (t) => (wt - t);   // outer edge on top (gutter side), water below
    const H = Wd, fs = big ? 0.075 : Math.max(0.06, len / 70);
    const svg = sv('svg', { viewBox: `0 ${-0.42} ${len + 2 * padX} ${H + 0.8}`, width: '100%', class: 'coping-strip' });
    svg.style.background = '#fff'; svg.style.direction = 'ltr'; svg.style.border = '1px solid #ddd'; svg.style.marginTop = '4px';
    const cm = this.copBy[this.c.coping.material]; const col = { full: cm?.color || '#ddd', cut: '#ffcc80', miterStart: '#ffe0b2', miterEnd: '#ffe0b2', miter2: '#ffab91' };
    // water / gutter hints
    svg.append(sv('rect', { x: 0, y: Y(-oh), width: len + 2 * padX, height: 0.06, fill: '#cfe8f3' }));
    let acc = [];
    run.pieces.forEach((p, i) => {
      const P4 = [[x(p.A.c + p.A.k * wt), Y(wt)], [x(p.B.c + p.B.k * wt), Y(wt)], [x(p.B.c - p.B.k * oh), Y(-oh)], [x(p.A.c - p.A.k * oh), Y(-oh)]];
      svg.append(sv('polygon', { points: P4.map(q => q.join(',')).join(' '), fill: col[p.type], stroke: '#333', 'stroke-width': 0.004 }));
      const cx = (P4[0][0] + P4[1][0] + P4[2][0] + P4[3][0]) / 4;
      const t1 = sv('text', { x: cx, y: H * 0.42, 'font-size': fs, 'text-anchor': 'middle', fill: '#111' }); t1.textContent = (Math.round(p.outer_m * 1000) / 10).toString(); svg.append(t1);
      if (p.type !== 'full' && p.type !== 'cut') { const t2 = sv('text', { x: cx, y: H * 0.85, 'font-size': fs * 0.8, 'text-anchor': 'middle', fill: '#6d4c41' }); t2.textContent = (Math.round(p.inner_m * 1000) / 10).toString(); svg.append(t2); }
      const tn = sv('text', { x: cx, y: -0.05, 'font-size': fs * 0.75, 'text-anchor': 'middle', fill: '#777' }); tn.textContent = `${run.side + 1}.${i + 1}`; svg.append(tn);
      acc.push(p.s1);
      if (i < run.joints.length && run.joints[i].movement) { const jx = x(run.joints[i].s); svg.append(sv('line', { x1: jx, y1: -0.02, x2: jx, y2: H + 0.02, stroke: '#d32f2f', 'stroke-width': 0.012 })); }
    });
    // chain of dimensions from the corner (outer edge, cumulative to each piece end) + the total
    const yD = H + 0.2;
    svg.append(sv('line', { x1: x(run.S0), y1: yD, x2: x(run.S1), y2: yD, stroke: '#1565c0', 'stroke-width': 0.004 }));
    for (const q of [run.S0, ...run.pieces.map(p => p.s1)]) svg.append(sv('line', { x1: x(q), y1: yD - 0.03, x2: x(q), y2: yD + 0.03, stroke: '#1565c0', 'stroke-width': 0.006 }));
    const tt = sv('text', { x: (x(run.S0) + x(run.S1)) / 2, y: yD + 0.14, 'font-size': fs * 1.1, 'text-anchor': 'middle', fill: '#1565c0' });
    const MODE = { 'center-joint': 'פוגה במרכז', 'center-piece': 'יחידה במרכז', equal: 'יחידות שוות', single: 'יחידה אחת' };
    tt.textContent = `צלע ${run.side + 1}: חוץ ${Math.round(run.outer_m * 1000) / 10} · ${run.pieces.length} יח' · ${MODE[run.mode]} · פוגה ${this.c.coping.joint_mm} מ"מ`; svg.append(tt);
    return svg;
  }
  // camera: above the pool, looking down into it
  show() {
    const app = this.app; if (!app) return;
    const st = app.store.get();
    // the floors above (pergola over the pool, the house) hidden – the pool seen from above
    const floors = Object.fromEntries(Object.entries(st.floors).map(([k, v]) => [k, { ...v, visible: k === 'unit' || k === 'site' }]));
    app.store.set({ floors, layers: { ...st.layers, poolTile: true, poolCoping: true, pool: true }, stageIndex: app.data.tags.sequence.length - 1 }, { label: 'pool view' });
    const R = this.S.innerRingITM, c = R.reduce((s, p) => [s[0] + p[0] / R.length, s[1] + p[1] / R.length], [0, 0]);
    const tgt = this.F.ctx.coords.toLocal(c[0], c[1], this.S.floor);
    const cam = this.F.ctx.coords.toLocal(c[0] - this.dv[0] * 6 + this.du[0] * 2, c[1] - this.dv[1] * 6 + this.du[1] * 2, this.S.copingTop + 6);
    app.viewer.flyTo(tgt, cam);
    app.viewer.invalidate();
  }
}

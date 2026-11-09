import * as THREE from 'three';

// Object snap (like AutoCAD OSNAP) for the measuring tool: from a ray hit, find the nearest
//   corner (vertex of a real edge) > edge midpoint > nearest point on an edge > the surface itself,
// within a radius in screen pixels. Real edges = THREE.EdgesGeometry (faces meeting at more than the
// threshold angle), so the diagonals of flat quads are not snapped to. Edges are built lazily per
// geometry (WeakMap) and kept in a uniform grid for a fast local search; instanced meshes use the
// instance matrix. Points cut away by the section planes are skipped.
// Constants: data/config/display.json "measure".
export const SNAP_KIND = { vertex: 'פינה', mid: 'אמצע', edge: 'קצה', face: 'משטח' };

export class Snapper {
  constructor(app) {
    this.app = app;
    this.C = app.display.measure || {};
    this.cache = new WeakMap();
    this._m = new THREE.Matrix4(); this._mi = new THREE.Matrix4(); this._im = new THREE.Matrix4();
    this._v = new THREE.Vector3(); this._a = new THREE.Vector3(); this._b = new THREE.Vector3();
  }

  // edges of one geometry: { pos: Float32Array (a,b pairs, local), cell, grid: Map(key -> [edge index]) } or null (too big)
  edgesOf(geo) {
    if (this.cache.has(geo)) return this.cache.get(geo);
    let out = null;
    const tris = geo.index ? geo.index.count / 3 : (geo.attributes.position?.count || 0) / 3;
    if (geo.attributes.position && tris > 0 && tris <= (this.C.maxSnapTriangles ?? 600000)) {
      const eg = new THREE.EdgesGeometry(geo, this.C.edgeThresholdDeg ?? 20);
      const pos = eg.attributes.position.array; eg.dispose();
      const cell = this.C.gridCell_m ?? 1; const grid = new Map();
      const n = pos.length / 6;
      for (let i = 0; i < n; i++) {
        const o = i * 6;
        const x0 = Math.floor(Math.min(pos[o], pos[o + 3]) / cell), x1 = Math.floor(Math.max(pos[o], pos[o + 3]) / cell);
        const y0 = Math.floor(Math.min(pos[o + 1], pos[o + 4]) / cell), y1 = Math.floor(Math.max(pos[o + 1], pos[o + 4]) / cell);
        const z0 = Math.floor(Math.min(pos[o + 2], pos[o + 5]) / cell), z1 = Math.floor(Math.max(pos[o + 2], pos[o + 5]) / cell);
        if ((x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1) > 4000) continue;   // a huge diagonal edge – skip (never a corner of a building part)
        for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) for (let z = z0; z <= z1; z++) {
          const k = x + ',' + y + ',' + z; let arr = grid.get(k); if (!arr) grid.set(k, arr = []); arr.push(i);
        }
      }
      out = { pos, cell, grid };
    }
    this.cache.set(geo, out);
    return out;
  }

  worldMatrix(hit) {
    const m = this._m.copy(hit.object.matrixWorld);
    if (hit.object.isInstancedMesh && hit.instanceId != null) { hit.object.getMatrixAt(hit.instanceId, this._im); m.multiply(this._im); }
    return m;
  }

  // screen position (px, relative to the canvas) of a world point
  toScreen(p, out = { x: 0, y: 0 }) {
    const v = this._v.copy(p).project(this.app.viewer.camera);
    const el = this.app.viewer.renderer.domElement;
    out.x = (v.x + 1) / 2 * el.clientWidth; out.y = (1 - v.y) / 2 * el.clientHeight; out.z = v.z;
    return out;
  }

  clipped(p) { return (this.app.viewer.renderer.clippingPlanes || []).some(pl => pl.distanceToPoint(p) < -0.001); }

  // hit: raycaster intersection, px: {x,y} pointer on the canvas, touch: bigger radius. -> { point, kind, hit }
  snap(hit, px, { touch = false, enabled = true, hits = null } = {}) {
    if (!hit) return null;
    const face = { point: hit.point.clone(), kind: 'face', hit };
    if (!enabled) return face;
    const R = touch ? (this.C.snapPx_touch ?? 30) : (this.C.snapPx_mouse ?? 14);
    const cam = this.app.viewer.camera; const el = this.app.viewer.renderer.domElement;
    // world size of one pixel at the hit depth -> search radius around the hit point
    const dist = cam.position.distanceTo(hit.point);
    const perPx = cam.isPerspectiveCamera ? 2 * dist * Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2) / el.clientHeight : (cam.top - cam.bottom) / cam.zoom / el.clientHeight;
    const Rw = R * perPx * 1.6;
    const best = { vertex: null, mid: null, edge: null };
    const bestD = { vertex: R, mid: R, edge: R * 0.75 };
    const s = { x: 0, y: 0 };
    const consider = (kind, wp) => {
      this.toScreen(wp, s);
      if (s.z > 1) return;
      const d = Math.hypot(s.x - px.x, s.y - px.y);
      if (d < bestD[kind] && !this.clipped(wp)) { bestD[kind] = d; best[kind] = wp.clone(); }
    };
    const a = this._a, b = this._b, w = new THREE.Vector3(), seg = new THREE.Line3(), q = new THREE.Vector3();
    const search = (hc) => {
    const E = this.edgesOf(hc.object.geometry);
    const M = this.worldMatrix(hc).clone(); const Mi = this._mi.copy(M).invert();
    const scale = M.getMaxScaleOnAxis() || 1;
    const lp = this._v.copy(hc.point).applyMatrix4(Mi); const lx = lp.x, ly = lp.y, lz = lp.z;
    const Rl = Rw / scale;
    if (E) {
      const { pos, cell, grid } = E; const seen = new Set();
      const c0x = Math.floor((lx - Rl) / cell), c1x = Math.floor((lx + Rl) / cell);
      const c0y = Math.floor((ly - Rl) / cell), c1y = Math.floor((ly + Rl) / cell);
      const c0z = Math.floor((lz - Rl) / cell), c1z = Math.floor((lz + Rl) / cell);
      const qp = new THREE.Vector3(lx, ly, lz);
      const ray = this.rayAt(px), wa = new THREE.Vector3(), wb = new THREE.Vector3(), onSeg = new THREE.Vector3();
      for (let x = c0x; x <= c1x; x++) for (let y = c0y; y <= c1y; y++) for (let z = c0z; z <= c1z; z++) {
        const arr = grid.get(x + ',' + y + ',' + z); if (!arr) continue;
        for (const i of arr) {
          if (seen.has(i)) continue; seen.add(i);
          const o = i * 6;
          a.set(pos[o], pos[o + 1], pos[o + 2]); b.set(pos[o + 3], pos[o + 4], pos[o + 5]);
          seg.set(a, b); seg.closestPointToPoint(qp, true, q);
          if (q.distanceTo(qp) > Rl) continue;
          consider('vertex', w.copy(a).applyMatrix4(M));
          consider('vertex', w.copy(b).applyMatrix4(M));
          consider('mid', w.copy(a).add(b).multiplyScalar(0.5).applyMatrix4(M));
          // nearest point on the edge to the pointer ray (not to the hit point): the edge may sit in front of / behind the face
          wa.copy(a).applyMatrix4(M); wb.copy(b).applyMatrix4(M);
          ray.distanceSqToSegment(wa, wb, null, onSeg);
          consider('edge', onSeg);
        }
      }
    } else if (hc.face) {
      // geometry too big for full edges: the corners of the hit triangle
      const P = hc.object.geometry.attributes.position;
      for (const k of ['a', 'b', 'c']) consider('vertex', w.fromBufferAttribute(P, hc.face[k]).applyMatrix4(M));
    }
    };
    // 1) the hit part + other parts the ray meets right behind it (a corner shared by a beam and a wall)
    const keys = new Set();
    const add = (o) => { const k = o.object.uuid + ':' + o.instanceId; if (keys.has(k)) return; keys.add(k); search(o); };
    add(hit);
    for (const o of hits || []) { if (keys.size >= 4 || o.distance > hit.distance + Math.max(0.5, Rw * 3)) break; add(o); }
    // 2) no corner yet: the parts under 4 rays around the pointer (the cursor just beside a corner hits the part behind it)
    if (!best.vertex && this.pickables) {
      const objs = this.pickables();
      for (const [ox, oy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        this.rayAt({ x: px.x + ox * R * 0.8, y: px.y + oy * R * 0.8 });
        const h2 = this._rc.intersectObjects(objs, false).find(x => !this.clipped(x.point));
        if (h2) add(h2);
      }
    }
    for (const kind of ['vertex', 'mid', 'edge']) if (best[kind]) return { point: best[kind], kind, hit };
    return face;
  }

  rayAt(px) {
    if (!this._ray) { this._ray = new THREE.Ray(); this._rc = new THREE.Raycaster(); this._ndc = new THREE.Vector2(); }
    const el = this.app.viewer.renderer.domElement;
    this._ndc.set(px.x / el.clientWidth * 2 - 1, -(px.y / el.clientHeight) * 2 + 1);
    this._rc.setFromCamera(this._ndc, this.app.viewer.camera);
    return this._ray.copy(this._rc.ray);
  }
}

// House axes: the dominant wall direction of the ground floor (length-weighted histogram of the wall
// footprint edges, mod 90°), from data/structure/floor-ground.json walls[].footprintITM – nothing typed in code.
// Returns { deg: angle of axis X from grid East (counter-clockwise, -45..45), u1, u2 (scene unit vectors), up }.
export function houseAxes(data, binDeg = 0.5) {
  const walls = data.floorGround?.walls || [];
  const nb = Math.round(90 / binDeg); const hist = new Float64Array(nb); const segs = [];
  for (const w of walls) {
    const r = w.footprintITM || [];
    for (let i = 0; i < r.length; i++) {
      const p = r[i], q = r[(i + 1) % r.length];
      const dE = q[0] - p[0], dN = q[1] - p[1]; const L = Math.hypot(dE, dN); if (L < 0.05) continue;
      let a = Math.atan2(dN, dE) * 180 / Math.PI; a = ((a % 90) + 90) % 90;
      hist[Math.min(nb - 1, Math.floor(a / binDeg))] += L; segs.push([a, L]);
    }
  }
  let deg = 0;
  if (segs.length) {
    let bi = 0; for (let i = 1; i < nb; i++) if (hist[i] > hist[bi]) bi = i;
    const peak = (bi + 0.5) * binDeg;
    // refine: length-weighted mean of the edges within 2 bins of the peak (wrapping at 0/90)
    let sw = 0, sa = 0;
    for (const [a, L] of segs) { let d = a - peak; if (d > 45) d -= 90; if (d < -45) d += 90; if (Math.abs(d) <= 2 * binDeg) { sw += L; sa += L * d; } }
    deg = peak + (sw ? sa / sw : 0);
    if (deg > 45) deg -= 90;
  }
  return axesFromDeg(deg);
}
export function axesFromDeg(deg) {
  const r = deg * Math.PI / 180;
  // ITM (E, N) -> scene (x = E, z = -N)
  return { deg, u1: new THREE.Vector3(Math.cos(r), 0, -Math.sin(r)), u2: new THREE.Vector3(-Math.sin(r), 0, -Math.cos(r)), up: new THREE.Vector3(0, 1, 0) };
}

// ---- element axes / element box (Avihai 09.11: "a wall that is not on one axis – its exact length") ----
// The registry item under the pointer (one wall, beam, slab, block run …): its own horizontal direction = the
// length-weighted dominant direction of its real horizontal edges (mod 90°); the longer of the two plan extents is
// "length" (u1), the other "width" (u2), Z = height. Instanced parts (blocks) use their instance matrices.
const _elemCache = new WeakMap();
function itemRoot(obj) { let o = obj; while (o) { if (o.userData?.component) return o.userData.component.object || o; o = o.parent; } return obj; }
function eachMeshMatrix(root, f, maxInst = 400) {
  root.updateMatrixWorld(true);
  const im = new THREE.Matrix4(), m = new THREE.Matrix4();
  root.traverse((o) => {
    if (!o.isMesh || !o.geometry?.attributes?.position || o.visible === false) return;
    if (o.isInstancedMesh) { const n = Math.min(o.count, maxInst); for (let i = 0; i < n; i++) { o.getMatrixAt(i, im); f(o.geometry, m.copy(o.matrixWorld).multiply(im)); } }
    else f(o.geometry, o.matrixWorld);
  });
}
export function elementOf(hit) { return hit?.object ? itemRoot(hit.object) : null; }
export function elementAxes(snapper, hit, binDeg = 0.5, maxVerts = 300000) {
  const root = elementOf(hit); if (!root) return null;
  if (_elemCache.has(root)) return _elemCache.get(root);
  const nb = Math.round(90 / binDeg), hist = new Float64Array(nb), segs = [];
  const a = new THREE.Vector3(), b = new THREE.Vector3(); let nv = 0, tooBig = false;
  eachMeshMatrix(root, (geo, M) => {
    nv += geo.attributes.position.count; if (nv > maxVerts) { tooBig = true; return; }
    const E = snapper.edgesOf(geo); if (!E) return;
    const p = E.pos;
    for (let o = 0; o < p.length; o += 6) {
      a.set(p[o], p[o + 1], p[o + 2]).applyMatrix4(M); b.set(p[o + 3], p[o + 4], p[o + 5]).applyMatrix4(M);
      const dx = b.x - a.x, dN = -(b.z - a.z), dy = b.y - a.y, L = Math.hypot(dx, dN);
      if (L < 0.02 || Math.abs(dy) > 0.05 * L) continue;     // horizontal edges only
      let ang = Math.atan2(dN, dx) * 180 / Math.PI; ang = ((ang % 90) + 90) % 90;
      hist[Math.min(nb - 1, Math.floor(ang / binDeg))] += L; segs.push([ang, L]);
    }
  });
  let res = null;
  if (!tooBig && segs.length) {
    let bi = 0; for (let i = 1; i < nb; i++) if (hist[i] > hist[bi]) bi = i;
    const peak = (bi + 0.5) * binDeg; let sw = 0, sa = 0;
    for (const [ang, L] of segs) { let d = ang - peak; if (d > 45) d -= 90; if (d < -45) d += 90; if (Math.abs(d) <= 2 * binDeg) { sw += L; sa += L * d; } }
    let deg = peak + (sw ? sa / sw : 0); if (deg > 45) deg -= 90;
    let ax = axesFromDeg(deg);
    const box = elementBox(root, ax);
    if (box && box.w > box.l) { ax = axesFromDeg(deg > 0 ? deg - 90 : deg + 90); }   // u1 = the longer plan extent
    res = { ...ax, element: true };
  }
  _elemCache.set(root, res);
  return res;
}
// oriented box of the item in the given axes: { l, w, h, a0, a1, b0, b1, y0, y1 }
export function elementBox(root, ax, maxVerts = 300000) {
  let a0 = Infinity, a1 = -Infinity, b0 = Infinity, b1 = -Infinity, y0 = Infinity, y1 = -Infinity, nv = 0, tooBig = false;
  const v = new THREE.Vector3();
  eachMeshMatrix(root, (geo, M) => {
    const P = geo.attributes.position; nv += P.count; if (nv > maxVerts) { tooBig = true; return; }
    for (let i = 0; i < P.count; i++) {
      v.fromBufferAttribute(P, i).applyMatrix4(M);
      const a = v.dot(ax.u1), b = v.dot(ax.u2);
      if (a < a0) a0 = a; if (a > a1) a1 = a; if (b < b0) b0 = b; if (b > b1) b1 = b; if (v.y < y0) y0 = v.y; if (v.y > y1) y1 = v.y;
    }
  });
  if (tooBig || !isFinite(a0)) return null;
  return { l: a1 - a0, w: b1 - b0, h: y1 - y0, a0, a1, b0, b1, y0, y1 };
}

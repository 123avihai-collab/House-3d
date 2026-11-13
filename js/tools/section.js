import * as THREE from 'three';

// Section planes: horizontal (keep below level) and vertical (east-west or north-south), movable.
// Section fill (Avihai 13.11.2026: "a full wall – from above and from the side"): a real cap ON the cut plane, by stencil.
// For every kind in display.json sectionCut.caps (concrete / column / beam / block / lintel) the closed solids of that kind
// are drawn once more into the stencil buffer only – back faces +1, front faces −1. Where a plane cuts a solid open the
// camera sees more back faces than front ones: the count stays ≠ 0 exactly over the cut face. A plane on the cut, drawn
// only where the count ≠ 0, then fills the section flat in the colour of the kind – solid from every angle.
// The helpers are children of the meshes they copy (same visibility), draw no colour / depth / shadow and are not pickable.
const ORDER = 10000;   // after the whole opaque scene
export class SectionTool {
  constructor(app) {
    this.app = app;
    this.hPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
    this.vPlane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
    const C = app.data.display.sectionCut || { caps: [], wallCut: {} };
    this.C = C;
    this.kinds = C.caps.map((c, i) => {
      const st = (side, op) => new THREE.MeshBasicMaterial({ side, colorWrite: false, depthWrite: false, depthTest: false,
        stencilWrite: true, stencilFunc: THREE.AlwaysStencilFunc, stencilFail: op, stencilZFail: op, stencilZPass: op });
      const base = ORDER + i * 10;
      // cap: drawn where the count ≠ 0 (depth-tested – nearer geometry still hides it); reset: count back to 0 for the next kind
      const cap = new THREE.MeshBasicMaterial({ color: c.color, side: THREE.DoubleSide, toneMapped: false,
        stencilWrite: true, stencilRef: 0, stencilFunc: THREE.NotEqualStencilFunc,
        stencilFail: THREE.KeepStencilOp, stencilZFail: THREE.KeepStencilOp, stencilZPass: THREE.KeepStencilOp });
      const reset = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide, colorWrite: false, depthWrite: false, depthTest: false,
        stencilWrite: true, stencilRef: 0, stencilFunc: THREE.AlwaysStencilFunc,
        stencilFail: THREE.ReplaceStencilOp, stencilZFail: THREE.ReplaceStencilOp, stencilZPass: THREE.ReplaceStencilOp });
      return { ...c, base, back: st(THREE.BackSide, THREE.IncrementWrapStencilOp), front: st(THREE.FrontSide, THREE.DecrementWrapStencilOp), cap, reset };
    });
    this.kindOf = new Map(); for (const k of this.kinds) for (const l of k.layers) this.kindOf.set(l, k);
    // the cap planes: one horizontal + one vertical per kind (+ their stencil reset), moved onto the section planes
    const big = 1000;
    this.capGroup = new THREE.Group(); this.capGroup.name = 'sectionCaps'; app.viewer.scene.add(this.capGroup);
    this.capPlanes = { h: [], v: [] };
    for (const k of this.kinds) for (const ax of ['h', 'v']) {
      const geo = new THREE.PlaneGeometry(big, big);
      const mk = (mat, ord) => { const m = new THREE.Mesh(geo, mat); m.renderOrder = ord; m.frustumCulled = false; m.userData.sectionCap = true; m.raycast = () => {}; m.visible = false; this.capGroup.add(m); return m; };
      // with both planes on, the nearer cap is drawn over the farther one (depth test), the reset comes after both
      this.capPlanes[ax].push(mk(k.cap, k.base + 2 + (ax === 'v' ? 1 : 0)), mk(k.reset, k.base + 5));
    }
    this.helpers = [];
    this.capped = new WeakSet();
    this.capsOn = false;
    app.store.on(s => this.apply(s.section));
    app.registry.onChange(() => { if (this.capsOn) this.addCaps(); this.beamsAbove(); });   // components built later (deferred layers), step changes
    // beams above a horizontal cut: their plan outline as a dashed line on the floor of the cut floor (as in a drawing)
    this.beamLines = new THREE.Group(); this.beamLines.name = 'beamsAbove'; app.viewer.scene.add(this.beamLines);
    this.apply(app.store.get().section);
  }
  apply(sec) {
    const planes = [];
    if (sec.hOn) { this.hPlane.set(new THREE.Vector3(0, -1, 0), sec.hLevel); planes.push(this.hPlane); }
    if (sec.vOn) {
      // axis 'E': plane perpendicular to east axis at E = E0 + pos ; 'N': perpendicular to north axis
      const sgn = sec.vFlip ? -1 : 1;
      if (sec.vAxis === 'E') this.vPlane.set(new THREE.Vector3(-sgn, 0, 0), sgn * sec.vPos);
      else this.vPlane.set(new THREE.Vector3(0, 0, sgn), sgn * sec.vPos); // scene z = -(N-N0)
      planes.push(this.vPlane);
    }
    this.app.viewer.renderer.clippingPlanes = planes;
    this.capsOn = planes.length > 0 && sec.fill !== false;
    // black plan: every fill in one colour (display.json sectionCut.mono)
    const M = this.C.mono;
    for (const k of this.kinds) k.cap.color.set(sec.mono && M ? M.color : k.color);
    if (this._dash) this._dash.color.set(sec.mono && M ? M.beamsAboveColor : this.C.beamsAbove.color);
    if (this.capsOn) this.addCaps();
    for (const c of this.helpers) c.visible = this.capsOn;
    // cap planes a hair inside the kept side of their plane (exactly on it they would be clipped by it)
    const eps = 0.0005;
    for (const m of this.capPlanes.h) { m.visible = this.capsOn && !!sec.hOn; m.rotation.set(-Math.PI / 2, 0, 0); m.position.set(0, sec.hLevel - eps, 0); }
    for (const m of this.capPlanes.v) {
      m.visible = this.capsOn && !!sec.vOn;
      const n = this.vPlane.normal, p = n.clone().multiplyScalar(-this.vPlane.constant + eps);
      m.position.copy(p); m.lookAt(p.clone().add(n));
    }
    this.beamsAbove();
    this.app.viewer.invalidate();
  }
  // legend of the fill: one row per colour (display.json legendHide drops kinds sharing a colour) + the dashed beam line
  legend() {
    const hide = new Set(this.C.legendHide || []), B = this.C.beamsAbove;
    return [...this.C.caps.filter(c => !hide.has(c.id)).map(c => ({ label: c.label, style: `background:${c.color}` })),
      ...(B ? [{ label: B.label, style: `background: repeating-linear-gradient(90deg, ${B.color} 0 4px, transparent 4px 7px); border-color: transparent` }] : [])];
  }
  // plan outline (2D convex hull, scene x/z) of a beam component – cached; beams are straight prisms
  hullOf(it) {
    if (it._hull !== undefined) return it._hull;
    const pts = [], v = new THREE.Vector3(); let y0 = Infinity, y1 = -Infinity;
    it.object.updateMatrixWorld(true);
    it.object.traverse(o => {
      if (!o.isMesh || o.userData.sectionCap || o.isInstancedMesh || !o.geometry?.attributes?.position) return;
      const P = o.geometry.attributes.position;
      for (let i = 0; i < P.count; i++) { v.fromBufferAttribute(P, i).applyMatrix4(o.matrixWorld); pts.push([v.x, v.z]); y0 = Math.min(y0, v.y); y1 = Math.max(y1, v.y); }
    });
    if (pts.length < 3) return (it._hull = null);
    pts.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lo = [], up = [];
    for (const p of pts) { while (lo.length > 1 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
    for (const p of pts.slice().reverse()) { while (up.length > 1 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
    return (it._hull = { ring: lo.slice(0, -1).concat(up.slice(0, -1)), y0, y1 });
  }
  // beams of the cut floor that lie wholly above the cut (bottom over the plane, up to its ceiling): dashed outline on its floor
  beamsAbove() {
    const B = this.C.beamsAbove; if (!B) return;
    const st = this.app.store.get(), sec = st.section || {};
    this.beamLines.clear();
    if (!sec.hOn || sec.fill === false) return;
    const fl = this.floorAt(sec.hLevel); if (!fl) return;
    const beamKind = this.kinds.find(k => k.id === 'beam'); if (!beamKind) return;
    const L = new Set(beamKind.layers), reg = this.app.registry, si = st.stageIndex, pts = [];
    for (const it of reg.items) {
      if (!L.has(it.tags.layer) || st.layers[it.tags.layer] === false || st.floors?.[it.tags.floor]?.visible === false) continue;
      const [from, to] = reg.range(it.tags); if (si < from || si > to) continue;
      const hh = this.hullOf(it); if (!hh) continue;
      if (hh.y0 < sec.hLevel || hh.y0 > fl.top + 0.01) continue;   // cut by the plane (filled) / belongs to a higher ceiling
      const y = fl.level + B.lift_m, r = hh.ring;
      r.forEach((p, i) => { const q = r[(i + 1) % r.length]; pts.push(p[0], y, p[1], q[0], y, q[1]); });
    }
    if (!pts.length) return;
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    const ls = new THREE.LineSegments(g, this._dash ||= new THREE.LineDashedMaterial({ color: sec.mono && this.C.mono ? this.C.mono.beamsAboveColor : B.color, dashSize: B.dash_m, gapSize: B.gap_m, depthTest: true }));
    ls.computeLineDistances(); ls.raycast = () => {}; ls.renderOrder = 5;
    this.beamLines.add(ls);
  }
  addCaps() {
    for (const it of this.app.registry.items) {
      if (this.capped.has(it)) continue;
      const k = this.kindOf.get(it.tags.layer);
      if (!k) { this.capped.add(it); continue; }
      const meshes = [];
      it.object.traverse(o => {
        if (!o.isMesh || o.userData.sectionCap || Array.isArray(o.material)) return;
        const m = o.material;
        // closed solids only: one-sided lit materials (labels / markers are MeshBasic, sheets are double-sided)
        if (!(m.isMeshStandardMaterial || m.isMeshPhysicalMaterial) || m.side !== THREE.FrontSide || m.transparent) return;
        meshes.push(o);
      });
      if (!meshes.length) continue;   // not built yet (deferred layer) – try again on the next change
      this.capped.add(it);
      for (const o of meshes) for (const [mat, ord] of [[k.back, k.base], [k.front, k.base + 1]]) {
        let c;
        if (o.isInstancedMesh) { c = new THREE.InstancedMesh(o.geometry, mat, o.count); c.instanceMatrix = o.instanceMatrix; c.count = o.count; }
        else c = new THREE.Mesh(o.geometry, mat);
        c.userData = { sectionCap: true, keep: true };
        c.renderOrder = ord; c.castShadow = false; c.receiveShadow = false;
        c.raycast = () => {};
        c.frustumCulled = o.frustumCulled;
        c.visible = this.capsOn;
        o.add(c);
        this.helpers.push(c);
      }
    }
  }
  // floors that have walls: [{ id, label, level, top }] – top = highest wall / column of the floor in the model (rel. to ±0.00)
  wallFloors() {
    if (this._wf) return this._wf;
    const W = new Set(this.C.wallCut?.wallLayers || []), S = new Set(this.C.wallCut?.ceilingSlabLayers || []);
    const box = new THREE.Box3(), tmp = new THREE.Box3();
    const bbox = (it) => { box.makeEmpty(); it.object.traverse(o => { if (o.isMesh && !o.userData.sectionCap && o.geometry) { tmp.setFromObject(o); box.union(tmp); } }); return box; };
    const top = {}, slabBottom = {};
    this.app.viewer.scene.updateMatrixWorld(true);
    for (const it of this.app.registry.items) {
      if (W.has(it.tags.layer) && !bbox(it).isEmpty()) top[it.tags.floor] = Math.max(top[it.tags.floor] ?? -Infinity, box.max.y);
      if (S.has(it.tags.layer) && !bbox(it).isEmpty()) slabBottom[it.tags.layer] = Math.min(slabBottom[it.tags.layer] ?? Infinity, box.min.y);
    }
    const out = this.app.data.tags.floors.filter(f => f.level != null && top[f.id] != null).map(f => {
      const ceil = Math.min(...(f.ceilingLayers || []).filter(l => slabBottom[l] != null).map(l => slabBottom[l]));
      return { id: f.id, label: f.label, level: f.level, top: +Math.min(top[f.id], ceil).toFixed(3) };
    });
    // cache only once every wall layer was built (blocks are a deferred layer)
    if (this.app.registry.items.some(it => it.tags.layer === 'blockWalls')) this._wf = out;
    return out;
  }
  // a preset of the "גובה קיר" row (display.json sectionCut.wallCut.presets) -> cut level (rel. to ±0.00), or null when the
  // floor has no such level (no lintels / no dropped ceiling)
  presetLevel(floorId, p) {
    const fl = this.wallFloors().find(x => x.id === floorId); if (!fl) return null;
    if (p.h_m != null) return Math.min(fl.top - 0.001, fl.level + p.h_m);
    if (p.id === 'full') return fl.top - 0.001;
    if (p.id === 'drop') { const d = this.app.modules?.finishes?.dropHeight?.(floorId); return d != null && d > fl.level && d < fl.top ? d + 0.002 : null; }
    if (p.id === 'lintel') {
      // the middle of the lintel band of the floor: median bottom / top of its lintels (measured from the model)
      const lo = [], hi = [], b = new THREE.Box3(), t = new THREE.Box3();
      for (const it of this.app.registry.items) {
        if (it.tags.layer !== 'lintels' || it.tags.floor !== floorId) continue;
        it.object.traverse(o => { if (o.isMesh && !o.userData.sectionCap) {
          if (o.isInstancedMesh) { const M = new THREE.Matrix4(); o.geometry.computeBoundingBox(); for (let i = 0; i < o.count; i++) { o.getMatrixAt(i, M); t.copy(o.geometry.boundingBox).applyMatrix4(M).applyMatrix4(o.matrixWorld); lo.push(t.min.y); hi.push(t.max.y); } }
          else { b.setFromObject(o); lo.push(b.min.y); hi.push(b.max.y); } } });
      }
      if (!lo.length) return null;
      const med = (a) => a.sort((x, y) => x - y)[a.length >> 1];
      return (med(lo) + med(hi)) / 2;
    }
    return null;
  }
  // the floor a cut level belongs to: highest floor level at or below it
  floorAt(hLevel) {
    const fl = this.wallFloors();
    let best = null; for (const f of fl) if (f.level <= hLevel + 1e-6 && (!best || f.level > best.level)) best = f;
    return best || fl[0] || null;
  }
}

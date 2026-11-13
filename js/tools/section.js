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
    app.registry.onChange(() => { if (this.capsOn) this.addCaps(); });   // components built later (deferred layers)
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
    this.app.viewer.invalidate();
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

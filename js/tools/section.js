import * as THREE from 'three';

// Section planes: horizontal (keep below level) and vertical (east-west or north-south), movable.
// Section fill (Avihai 13.11.2026: "a full wall from above – the hollow wall confuses"): every solid element of the kinds in
// display.json sectionCut.caps gets a twin that draws only its BACK faces in one flat colour. Where a plane cuts the element
// the camera looks into it and sees those back faces – the cut reads as a solid fill, coloured by kind (concrete / column /
// beam / block / lintel). Uncut elements are unchanged (their back faces stay hidden behind the front faces).
// The twins exist only once a section was switched on, are hidden with it, never cast shadows and are not pickable.
export class SectionTool {
  constructor(app) {
    this.app = app;
    this.hPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
    this.vPlane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
    const C = app.data.display.sectionCut || { caps: [], wallCut: {} };
    this.C = C;
    this.capOf = new Map();   // layer -> cap material
    for (const c of C.caps) {
      const m = new THREE.MeshBasicMaterial({ color: c.color, side: THREE.BackSide, toneMapped: false });
      m.name = 'sectionCap:' + c.id;
      for (const l of c.layers) this.capOf.set(l, m);
    }
    this.caps = [];
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
    for (const c of this.caps) c.visible = this.capsOn;
    this.app.viewer.invalidate();
  }
  addCaps() {
    for (const it of this.app.registry.items) {
      if (this.capped.has(it)) continue;
      const mat = this.capOf.get(it.tags.layer);
      if (!mat) { this.capped.add(it); continue; }
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
      for (const o of meshes) {
        let cap;
        if (o.isInstancedMesh) { cap = new THREE.InstancedMesh(o.geometry, mat, o.count); cap.instanceMatrix = o.instanceMatrix; cap.count = o.count; }
        else cap = new THREE.Mesh(o.geometry, mat);
        cap.userData = { sectionCap: true, keep: true };
        cap.castShadow = false; cap.receiveShadow = false;
        cap.raycast = () => {};
        cap.frustumCulled = o.frustumCulled;
        cap.visible = this.capsOn;
        o.add(cap);
        this.caps.push(cap);
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
  // the floor a cut level belongs to: highest floor level at or below it
  floorAt(hLevel) {
    const fl = this.wallFloors();
    let best = null; for (const f of fl) if (f.level <= hLevel + 1e-6 && (!best || f.level > best.level)) best = f;
    return best || fl[0] || null;
  }
}

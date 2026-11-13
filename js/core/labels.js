import * as THREE from 'three';

// Which CSS labels are shown. Over 280 labels overlap at the overview, so by default only the labels of what is added at the
// current construction step are shown (+ a few always-on layers, + the selected / searched element), within a distance of
// the camera, and never beyond a section plane. Modes (quality.labelMode): 'step' (default) | 'all'; quality.labels=false = none.
// Occlusion (review 13.11.2026): a label hidden behind solid geometry (a boundary point behind the house, a far wall's tag)
// is not drawn through it. Tested once the camera rests (labels.occlusion.idle_ms) against the opaque meshes of the visible
// built elements; the selected element's labels are never hidden. A marker dot (userData.marker) follows its label.
// Constants: data/config/display.json "labels".
export class LabelManager {
  constructor(app) {
    this.app = app; this.selected = null; this.v = new THREE.Vector3();
    this.ray = new THREE.Raycaster(); this.camKey = ''; this.occ = new WeakMap(); this.occluders = null;
    app.viewer.beforeLabels = () => this.update();
    app.store.on(() => { this.occluders = null; this.schedule(); });
  }
  select(item) { this.selected = item || null; this.app.viewer.invalidate(); }
  opts() { return { enabled: true, idle_ms: 180, margin_m: 0.3, systems: ['structure', 'walls', 'finishes'], skipLayers: [], ...(this.app.display.labels?.occlusion || {}) }; }
  schedule() {
    clearTimeout(this.t);
    this.t = setTimeout(() => { this.computeOcclusion(); this.app.viewer.invalidate(); }, this.opts().idle_ms);
  }
  // opaque, visible meshes of built elements (rebuilt after any state change: stage, layers, floors, opacity)
  collectOccluders() {
    const O = this.opts(); const sys = new Set(O.systems), skip = new Set(O.skipLayers); const list = [];
    for (const it of this.app.registry.items) {
      if (!it.object.visible || !sys.has(it.tags.system) || skip.has(it.tags.layer)) continue;
      it.object.traverseVisible(o => {
        if (!o.isMesh || o.isInstancedMesh && !o.count) return;
        const m = Array.isArray(o.material) ? o.material[0] : o.material;
        if (!m || m.visible === false || (m.transparent && m.opacity < 0.9) || m.colorWrite === false || m.depthWrite === false) return;
        o.userData._occItem = it; list.push(o);
      });
    }
    return list;
  }
  computeOcclusion() {
    const O = this.opts(); if (!O.enabled) return;
    const { app } = this; const cam = app.viewer.camera; cam.updateMatrixWorld();
    if (!this.occluders) this.occluders = this.collectOccluders();
    const planes = app.viewer.renderer.clippingPlanes || []; const origin = cam.getWorldPosition(new THREE.Vector3());
    const dir = new THREE.Vector3(), P = new THREE.Vector3();
    for (const it of app.registry.items) {
      if (!it.object.visible || !it._labels?.length) continue;
      for (const o of it._labels) {
        if (!o.userData._wantVis) continue;
        o.getWorldPosition(P); dir.subVectors(P, origin); const d = dir.length(); if (d < 0.5) { this.occ.set(o, false); continue; }
        this.ray.set(origin, dir.multiplyScalar(1 / d)); this.ray.far = d - O.margin_m;
        let hidden = false;
        for (const hit of this.ray.intersectObjects(this.occluders, false)) {
          if (hit.object.userData._occItem === it) continue;                         // the element the label belongs to
          if (planes.some(p => p.distanceToPoint(hit.point) < -0.01)) continue;       // cut away by a section
          hidden = true; break;
        }
        this.occ.set(o, hidden);
      }
    }
  }
  update() {
    const { app } = this; const s = app.store.get(); const R = app.registry; const D = app.display.labels || {};
    const cam = app.viewer.camera.position; const planes = app.viewer.renderer.clippingPlanes || [];
    const mode = s.quality.labelMode || 'step'; const si = s.stageIndex;
    const always = new Set(D.alwaysLayers || []); const maxD = D.maxDistance_m ?? Infinity;
    // camera moved -> occlusion is re-tested once it rests (the previous result is kept while moving)
    const e = app.viewer.camera.matrixWorld.elements; const key = e.map(x => x.toFixed(3)).join(',');
    if (key !== this.camKey) { this.camKey = key; this.schedule(); }
    for (const it of R.items) {
      if (!it.object.visible) continue;
      if (!it._labels) { it._labels = []; it.object.traverse(o => { if (o.isCSS2DObject) it._labels.push(o); }); }
      if (!it._labels.length) continue;
      const lo = !!s.labelsOff?.[it.tags.layer];
      const sel = it === this.selected; const alw = always.has(it.tags.layer);
      const base = !lo && (sel || alw || mode === 'all' || R.range(it.tags)[0] === si);
      for (const o of it._labels) {
        let vis = base && !o.userData.ocHide;   // ocHide: a red proposal tag in plan mode (js/tools/proposals.js)
        if (vis && (!sel || planes.length)) {
          o.getWorldPosition(this.v);
          if (!sel && !alw && this.v.distanceTo(cam) > maxD) vis = false;
          if (vis && planes.some(p => p.distanceToPoint(this.v) < -0.01)) vis = false;
        }
        o.userData._wantVis = vis;
        if (vis && !sel && this.occ.get(o)) vis = false;
        o.visible = vis;
        if (o.userData.marker) o.userData.marker.visible = base && !o.userData.ocHide;
      }
    }
  }
}

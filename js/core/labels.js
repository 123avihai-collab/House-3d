import * as THREE from 'three';

// Which CSS labels are shown. Over 280 labels overlap at the overview, so by default only the labels of what is added at the
// current construction step are shown (+ a few always-on layers, + the selected / searched element), within a distance of
// the camera, and never beyond a section plane. Modes (quality.labelMode): 'step' (default) | 'all'; quality.labels=false = none.
// Constants: data/config/display.json "labels".
export class LabelManager {
  constructor(app) {
    this.app = app; this.selected = null; this.v = new THREE.Vector3();
    app.viewer.beforeLabels = () => this.update();
  }
  select(item) { this.selected = item || null; this.app.viewer.invalidate(); }
  update() {
    const { app } = this; const s = app.store.get(); const R = app.registry; const D = app.display.labels || {};
    const cam = app.viewer.camera.position; const planes = app.viewer.renderer.clippingPlanes || [];
    const mode = s.quality.labelMode || 'step'; const si = s.stageIndex;
    const always = new Set(D.alwaysLayers || []); const maxD = D.maxDistance_m ?? Infinity;
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
        o.visible = vis;
      }
    }
  }
}

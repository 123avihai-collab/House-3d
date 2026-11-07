import * as THREE from 'three';

// Search an element by its name / id ("B7" = "B-7", "gw19", "c9", "PF5", "BW1"): the matches are listed, the chosen one is
// outlined, its labels shown, the camera flies to it, and – if it is hidden by the step / layer / floor – it is made visible.
export class SearchTool {
  constructor(app) {
    this.app = app; this.sel = new THREE.Group(); app.viewer.scene.add(this.sel);
  }
  static norm(s) { return String(s || '').toUpperCase().replace(/[\s\-_.·'"׳]/g, ''); }
  find(q) {
    const n = SearchTool.norm(q); if (!n) return [];
    const res = new Map();
    for (const it of this.app.registry.items) {
      const m = it.meta; if (m.kind === 'ghost') continue;
      const id = SearchTool.norm(m.id), nm = SearchTool.norm(m.name);
      let score = 0;
      if (id && id === n) score = 100;
      else if (id && id.startsWith(n) && /\d$/.test(n) === false) score = 50;
      else if (nm.includes(n) && n.length >= 2) score = 10 + (new RegExp(`(^|[^0-9A-Z])${n}([^0-9]|$)`).test(nm) ? 20 : 0);
      if (score && (!res.has(it) || res.get(it) < score)) res.set(it, score);
    }
    return [...res.entries()].sort((a, b) => b[1] - a[1]).slice(0, 30).map(([it]) => it);
  }
  describe(it) {
    const { app } = this; const t = it.tags;
    const fl = app.data.tags.floors.find(f => f.id === t.floor)?.label || '';
    const step = app.data.tags.sequence[app.registry.range(t)[0]]?.label || '—';
    return `${fl} · שלב: ${step}`;
  }
  highlight(it) {
    this.sel.clear();
    if (!it) { this.app.labels?.select(null); this.app.viewer.invalidate(); return; }
    it.object.updateMatrixWorld(true);
    it.object.traverse(o => {
      if (!o.isMesh) return;
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry, 25), new THREE.LineBasicMaterial({ color: '#ffd600', depthTest: false }));
      e.applyMatrix4(o.matrixWorld); e.renderOrder = 21; this.sel.add(e);
    });
    this.app.labels?.select(it);
    this.app.viewer.invalidate();
  }
  // make the item visible (step range, layer, floor, floor switches, system filter), outline it and fly to it
  show(it) {
    const { app } = this; const s = app.store.get(); const R = app.registry; const t = it.tags;
    const [from, to] = R.range(t);
    const patch = {};
    if (s.stageIndex < from || s.stageIndex > to) patch.stageIndex = to >= from ? to : from;
    if (s.layers[t.layer] === false) patch.layers = { ...s.layers, [t.layer]: true };
    const floors = structuredClone(s.floors); let fch = false;
    if (floors[t.floor] && !floors[t.floor].visible) { floors[t.floor].visible = true; fch = true; }
    for (const [f, k] of R.switchOf?.[t.layer] || []) if (floors[f]?.[k] === false) { floors[f][k] = true; fch = true; }
    if (fch) patch.floors = floors;
    if (s.systemFilter && !s.systemFilter.includes(t.system)) patch.systemFilter = null;
    if (Object.keys(patch).length) { app.store.set(patch, { label: 'search' }); app.ui.toast('האלמנט הוסתר – הוצג (שלב / שכבה / קומה)'); }
    const box = new THREE.Box3().setFromObject(it.object);
    if (box.isEmpty()) return;
    const c = box.getCenter(new THREE.Vector3()), sz = box.getSize(new THREE.Vector3()).length();
    const d = Math.max(4, sz * 1.3);
    app.viewer.flyTo(c, c.clone().add(new THREE.Vector3(d * 0.6, d * 0.55, d * 0.6)));
    this.highlight(it);
    app.ui.showInfoFor?.(it);
  }
}

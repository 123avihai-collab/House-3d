// Component registry. Every model component is registered with tags
// {floor, system, stage, stageTo?, layer} and metadata (name, source, ...).
// Visibility = layer on  AND  floor visible  AND  stage reached  AND  system passes filter  AND  owner-change variant matches.
export class Registry {
  constructor(tagsConfig) {
    this.items = [];
    this.stages = tagsConfig.stages.map(s => s.id);
    this.steps = tagsConfig.sequence;            // construction-step slider (data/config/tags.json)
    this.listeners = [];
    this.ceilingOf = {};                         // layer -> floor whose ceiling it is
    for (const f of tagsConfig.floors) for (const l of f.ceilingLayers || []) this.ceilingOf[l] = f.id;
  }
  add(object3d, tags, meta = {}) {
    for (const k of ['floor', 'system', 'stage', 'layer']) {
      if (!tags[k]) throw new Error(`component "${meta.name}" missing tag ${k}`);
    }
    const item = { object: object3d, tags, meta };
    object3d.userData.component = item;
    object3d.traverse(o => { o.userData.component = item; });
    this.items.push(item);
    return item;
  }
  stageIndex(id) { return this.stages.indexOf(id); }
  stepById(id) {
    if (id === 'skeletonEnd') return this.steps.findIndex(s => s.id === 'finishes') - 1;
    return this.steps.findIndex(s => s.id === id);
  }
  // step of a {floor, stage} pair: an include naming the floor wins over a stage-only include
  stepIndex(stage, floor) {
    const exact = this.steps.findIndex(s => s.includes.some(x => x.stage === stage && x.floor === floor));
    return exact >= 0 ? exact : this.steps.findIndex(s => s.includes.some(x => x.stage === stage && !x.floor));
  }
  range(t) {
    const from = t.step ? this.stepById(t.step) : this.stepIndex(t.stage, t.floor);
    const to = t.stepTo ? this.stepById(t.stepTo) : t.stageTo ? this.stepIndex(t.stageTo, t.floor) : this.steps.length - 1;
    return [from, to];
  }
  apply(state) {
    const si = state.stageIndex;   // index into the step sequence
    const sec = state.section || {};
    const cutFloor = sec.hOn && sec.hideBeams !== false ? this.cutFloor(sec.hLevel) : null;
    for (const it of this.items) {
      const t = it.tags;
      const [from, to] = this.range(t);
      const layerOn = state.layers[t.layer] !== false;
      const floor = state.floors[t.floor] || { visible: true, opacity: 1 };
      const sysOn = !state.systemFilter || state.systemFilter.includes(t.system);
      // owner-change variants: "original" shows while the change is off, "changed" while it is on
      const v = it.meta.variant;
      const varOn = !v || ((state.ownerChanges?.[v.change] ?? true) === (v.show === 'changed'));
      let visible = layerOn && floor.visible && sysOn && varOn && si >= from && si <= to;
      // horizontal floor section: the beams of the floor being cut (the ceiling beams under / on the slab you stand on) are hidden
      if (visible && cutFloor && t.layer.endsWith('CeilingBeams') && t.floor === cutFloor) visible = false;
      // "תקרה" switch of the floors tab: the layers of a floor's ceiling (tags.json floors[].ceilingLayers)
      const cf = this.ceilingOf[t.layer];
      if (visible && cf && state.floors[cf]?.ceiling === false) visible = false;
      it.object.visible = visible;
      // per-layer label switch: hide only the labels and marking lines (userData.annotation) of the layer, keep the objects
      if (visible) { const lo = !!state.labelsOff?.[t.layer]; it.object.traverse(o => { if (o.isCSS2DObject || o.userData.annotation) o.visible = !lo; }); }
      if (visible) this.applyOpacity(it, floor.opacity);
    }
    this.listeners.forEach(f => f());
  }
  applyOpacity(it, opacity) {
    // materials are shared between components of all floors (one concrete for every wall/slab): a floor's transparency
    // must not leak to the others, so a component gets its own copy of a material the first time it is made transparent
    it.object.traverse(o => {
      if (!o.material) return;
      if (opacity < 0.999 && !o.userData.ownMat) {
        o.userData.sharedMat = o.material;
        o.material = Array.isArray(o.material) ? o.material.map(m => m.clone()) : o.material.clone();
        o.userData.ownMat = true;
      }
      if (!o.userData.ownMat) return;   // fully opaque and never changed: keep the shared material untouched
      const base = Array.isArray(o.userData.sharedMat) ? o.userData.sharedMat : [o.userData.sharedMat];
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      mats.forEach((m, i) => {
        const b = base[i] || base[0];
        m.opacity = b.opacity * opacity;
        m.transparent = b.transparent || m.opacity < 0.999;
        m.depthWrite = b.transparent ? b.depthWrite : !m.transparent;
        m.needsUpdate = true;
      });
    });
  }
  pickables() {
    const out = [];
    for (const it of this.items) {
      if (!it.object.visible || it.meta.pickable === false) continue;
      it.object.traverse(o => { if (o.isMesh && o.visible) out.push(o); });
    }
    return out;
  }
  // floor levels of the slabs that carry ceiling beams: { floorTag: slab top (rel) } – e.g. ground ceiling = floor A slab
  beamLevels() {
    if (!this._beamLevels) {
      this._beamLevels = {};
      for (const it of this.items) if (it.tags.layer.endsWith('CeilingBeams') && it.meta.ceilTopRel != null)
        this._beamLevels[it.tags.floor] = Math.max(this._beamLevels[it.tags.floor] ?? -Infinity, it.meta.ceilTopRel);
    }
    return this._beamLevels;
  }
  // the floor whose slab is the highest one at or below the cut level
  cutFloor(hLevel) {
    let best = null, bz = -Infinity;
    for (const [f, z] of Object.entries(this.beamLevels())) if (z <= hLevel + 0.01 && z > bz) { best = f; bz = z; }
    return best;
  }
  byKind(kind) { return this.items.filter(i => i.meta.kind === kind); }
  onChange(f) { this.listeners.push(f); }
}

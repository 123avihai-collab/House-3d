// Component registry. Every model component is registered with tags
// {floor, system, stage, stageTo?, layer} and metadata (name, source, ...).
// Visibility = layer on  AND  floor visible  AND  stage reached  AND  system passes filter.
export class Registry {
  constructor(tagsConfig) {
    this.items = [];
    this.stages = tagsConfig.stages.map(s => s.id);
    this.listeners = [];
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
  apply(state) {
    const si = state.stageIndex;
    for (const it of this.items) {
      const t = it.tags;
      const from = this.stageIndex(t.stage);
      const to = t.stageTo ? this.stageIndex(t.stageTo) : this.stages.length - 1;
      const layerOn = state.layers[t.layer] !== false;
      const floor = state.floors[t.floor] || { visible: true, opacity: 1 };
      const sysOn = !state.systemFilter || state.systemFilter.includes(t.system);
      const visible = layerOn && floor.visible && sysOn && si >= from && si <= to;
      it.object.visible = visible;
      if (visible) this.applyOpacity(it, floor.opacity);
    }
    this.listeners.forEach(f => f());
  }
  applyOpacity(it, opacity) {
    it.object.traverse(o => {
      const mats = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
      for (const m of mats) {
        if (m.userData.baseOpacity === undefined) {
          m.userData.baseOpacity = m.opacity;
          m.userData.baseTransparent = m.transparent;
        }
        const op = m.userData.baseOpacity * opacity;
        m.opacity = op;
        m.transparent = m.userData.baseTransparent || op < 0.999;
        m.depthWrite = !m.transparent || m.userData.baseTransparent === false;
      }
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
  byKind(kind) { return this.items.filter(i => i.meta.kind === kind); }
  onChange(f) { this.listeners.push(f); }
}

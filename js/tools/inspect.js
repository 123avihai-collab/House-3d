import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { nearestOnSegment } from '../geometry/tin.js';

// Dimensions tool: click a component -> its dimensions, source, and distances from the clicked
// point to the nearest boundaries (lot lines now; walls once they exist).
export class InspectTool {
  constructor(app) {
    this.app = app;
    this.group = new THREE.Group();
    app.viewer.scene.add(this.group);
    this.highlight = null;
  }
  activate() { this.app.ui.hint('מידות: לחץ על רכיב כדי לראות מידות, מקור ומרחקים'); }
  deactivate() { this.clear(); }
  clear() { this.group.clear(); this.app.viewer.invalidate(); }
  handleClick(hit) {
    this.clear();
    if (!hit) { this.app.ui.showInfo(null); return; }
    const comp = hit.object.userData.component;
    const { coords } = this.app;
    const P = coords.fromLocal(hit.point);
    const rows = [];
    const m = comp?.meta || {};
    rows.push(['נקודה (ITM)', coords.fmtEN(P.E, P.N)]);
    rows.push(['גובה', coords.fmtH(P.H)]);
    if (m.area != null) rows.push(['שטח', `${Number(m.area).toFixed(2)} מ"ר`]);
    if (m.hMin != null) rows.push(['גובה מינ׳/מקס׳', `${coords.fmtH(m.hMin)} / ${coords.fmtH(m.hMax)}`]);
    if (m.height != null) rows.push(['גובה מעטפת', `${m.height} מ'${m.provisional ? ' (זמני)' : ''}`]);
    if (m.base != null) rows.push(['מפלס בסיס', coords.fmtH(m.base)]);
    if (m.edgeKinds) rows.push(['סיווג גבולות', Object.entries(m.edgeKinds).map(([k, v]) => `${({ front: 'קדמי', side: 'צידי', rear: 'אחורי' })[k]}: ${v.join(', ')}`).join(' · ')]);
    if (m.controlCount != null) rows.push(['נקודות בקרה לגובה', `${m.controlCount} (${m.interp})`]);
    if (comp?.object) {
      const box = new THREE.Box3().setFromObject(comp.object);
      const s = box.getSize(new THREE.Vector3());
      rows.push(['מידות תוחמות (מזרח×צפון×גובה)', `${s.x.toFixed(2)} × ${s.z.toFixed(2)} × ${s.y.toFixed(2)}`]);
    }
    // distances from the clicked point to the nearest edges of lot 5187 (and walls in later stages)
    const ring = this.app.data.plot.ring;
    const d = [];
    for (let i = 0; i < ring.length; i++) {
      const [ax, ay] = ring[i], [bx, by] = ring[(i + 1) % ring.length];
      d.push(nearestOnSegment(ax, ay, bx, by, P.E, P.N));
    }
    d.sort((a, b) => a.dist - b.dist);
    const walls = this.app.registry.items.filter(it => it.tags.system === 'walls' && it.object.visible);
    rows.push(['מרחק לגבולות מגרש 5187', d.slice(0, 2).map(x => `${x.dist.toFixed(3)} מ'`).join(' · ')]);
    if (!walls.length) rows.push(['מרחק לקירות', 'בקרוב – אין עדיין קירות במודל']);
    for (const x of d.slice(0, 2)) {
      const a = hit.point.clone(), b = coords.toLocal(x.x, x.y, P.H);
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), new THREE.LineBasicMaterial({ color: '#ffea00', depthTest: false }));
      line.renderOrder = 11;
      const div = document.createElement('div'); div.className = 'lbl measure'; div.textContent = `${x.dist.toFixed(2)} מ'`;
      const l = new CSS2DObject(div); l.position.copy(a).lerp(b, 0.5);
      this.group.add(line, l);
    }
    this.app.ui.showInfo({ title: m.name || 'רכיב', rows, tags: comp?.tags, source: m.source, note: m.note });
    this.app.viewer.invalidate();
  }
}

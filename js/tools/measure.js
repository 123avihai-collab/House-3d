import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Free measurement: click two points on the model -> 3D distance, horizontal distance, height difference.
export class MeasureTool {
  constructor(app) {
    this.app = app;
    this.group = new THREE.Group();
    this.group.renderOrder = 10;
    app.viewer.scene.add(this.group);
    this.first = null;
    this.items = [];
    this.mat = new THREE.LineBasicMaterial({ color: '#00e5ff', depthTest: false, transparent: true });
    this.dotGeo = new THREE.SphereGeometry(0.09, 12, 8);
    this.dotMat = new THREE.MeshBasicMaterial({ color: '#00e5ff', depthTest: false, transparent: true });
  }
  activate() { this.first = null; this.app.ui.hint('מדידה: לחץ על נקודה ראשונה'); }
  deactivate() { this.clearPending(); }
  clearPending() { if (this.first?.dot) this.group.remove(this.first.dot); this.first = null; }
  handleClick(hit) {
    if (!hit) return;
    const p = hit.point.clone();
    const dot = new THREE.Mesh(this.dotGeo, this.dotMat); dot.position.copy(p); dot.renderOrder = 10;
    this.group.add(dot);
    if (!this.first) { this.first = { p, dot }; this.app.ui.hint('מדידה: לחץ על נקודה שנייה'); this.app.viewer.invalidate(); return; }
    const a = this.first.p, b = p;
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, b]), this.mat); line.renderOrder = 10;
    const d3 = a.distanceTo(b), dh = Math.hypot(b.x - a.x, b.z - a.z), dz = b.y - a.y;
    const div = document.createElement('div'); div.className = 'lbl measure';
    div.innerHTML = `<b>${d3.toFixed(3)} מ'</b><br>אופקי ${dh.toFixed(3)} · ΔH ${dz >= 0 ? '+' : '−'}${Math.abs(dz).toFixed(3)}`;
    const lbl = new CSS2DObject(div); lbl.position.copy(a).lerp(b, 0.5);
    this.group.add(line, lbl);
    const A = this.app.coords.fromLocal(a), B = this.app.coords.fromLocal(b);
    this.items.push({ d3, dh, dz, A, B, objs: [this.first.dot, dot, line, lbl] });
    this.first = null;
    this.app.ui.hint(`מרחק ${d3.toFixed(3)} מ' · אופקי ${dh.toFixed(3)} מ' · הפרש גובה ${dz.toFixed(3)} מ'. לחץ להמשך מדידה.`);
    this.app.ui.refreshPanel('tools');
    this.app.viewer.invalidate();
  }
  clearAll() {
    this.clearPending();
    for (const it of this.items) it.objs.forEach(o => this.group.remove(o));
    this.items = [];
    this.app.viewer.invalidate();
    this.app.ui.refreshPanel('tools');
  }
}

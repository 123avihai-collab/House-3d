import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Notes / punch list: click a component, write a note. Notes live in the settings state
// (exported/imported, undo/redo) and are listed with a "copy all" button.
export class NotesTool {
  constructor(app) {
    this.app = app;
    this.group = new THREE.Group();
    app.viewer.scene.add(this.group);
    app.store.on(() => this.renderPins());
    this.renderPins();
  }
  activate() { this.app.ui.hint('הערה: לחץ על רכיב במודל כדי להוסיף הערה'); }
  deactivate() {}
  handleClick(hit) {
    if (!hit) return;
    const P = this.app.coords.fromLocal(hit.point);
    const comp = hit.object.userData.component;
    this.app.ui.openNoteEditor({ E: P.E, N: P.N, H: P.H, component: comp?.meta?.name || '' }, (text) => {
      if (!text.trim()) return;
      const notes = this.app.store.get().notes.slice();
      notes.push({ id: Date.now().toString(36), text: text.trim(), E: +P.E.toFixed(3), N: +P.N.toFixed(3), H: +P.H.toFixed(3),
        component: comp?.meta?.name || '', created: new Date().toISOString(), done: false });
      this.app.store.set({ notes }, { label: 'note' });
    });
  }
  renderPins() {
    this.group.clear();
    const notes = this.app.store.get().notes;
    notes.forEach((n, i) => {
      const div = document.createElement('div');
      div.className = 'lbl note-pin' + (n.done ? ' done' : '');
      div.textContent = String(i + 1); div.title = n.text;
      const o = new CSS2DObject(div);
      o.position.copy(this.app.coords.toLocal(n.E, n.N, n.H));
      this.group.add(o);
    });
    this.app.viewer.invalidate();
  }
  toText() {
    const c = this.app.coords;
    return this.app.store.get().notes.map((n, i) =>
      `${i + 1}. ${n.done ? '[בוצע] ' : ''}${n.text}\n   רכיב: ${n.component || '—'} · E ${n.E.toFixed(3)} N ${n.N.toFixed(3)} · גובה ${c.fmtH(n.H)} · ${n.created.slice(0, 10)}`
    ).join('\n');
  }
}

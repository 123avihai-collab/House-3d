import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Edit mode – correction notes for Claude (model fixes only; questions for the architect / engineer stay in "הערות").
// Click an element: it is highlighted and a note is written with what to fix. Notes are kept in the artifact's database
// (collection "fixes", read by Claude with ArtifactData); outside the claude.ai viewer they fall back to this browser.
const ACTIONS = [
  ['move', 'להזיז'], ['delete', 'למחוק'], ['height', 'לשנות גובה / מפלס'], ['size', 'לשנות מידה / עובי'],
  ['add', 'להוסיף אלמנט'], ['split', 'לפצל / לחבר'], ['stage', 'שלב בנייה שגוי'], ['other', 'אחר'],
];
const LS = 'house3d.fixes';
const ID_RE = /\b(?:GW|FW|RW|GS|FS|RS|BW|BS|PW|PF|ST|PIL|C|W)\d+[A-Z]?\b|\bB-\d+\b|\b[UGF]\d{2}\b/;

export class FixTool {
  constructor(app) {
    this.app = app;
    this.items = [];
    this.online = false; this.state = 'loading';
    this.group = new THREE.Group(); this.sel = new THREE.Group();
    app.viewer.scene.add(this.group, this.sel);
    this.local = () => { try { return JSON.parse(localStorage.getItem(LS) || '[]'); } catch { return []; } };
    this.saveLocal = (arr) => { try { localStorage.setItem(LS, JSON.stringify(arr)); } catch {} };
    this.items = this.local(); this.render();
    this.connect();
    // pins follow the pin switch (fixPins: open | all | off) and the global labels switch (🏷 off hides them too)
    let last = '';
    app.store.on((s) => { const k = `${s.fixPins || 'open'}|${s.quality?.labels !== false}`; if (k !== last) { last = k; this.render(); } });
  }
  pinMode() { const s = this.app.store.get(); return s.quality?.labels === false ? 'off' : (s.fixPins || 'open'); }
  static actions() { return ACTIONS; }
  async connect() {
    const use = window.claude?.use;
    const db = use ? await use('db').catch(() => null) : null;
    if (!db) { this.state = 'local'; this.app.ui.refreshPanel('fixes'); return; }
    this.db = db; this.col = db.collection('fixes');
    const user = await use('user').catch(() => null);
    this.uid = user ? await user.id?.().catch(() => null) : null;
    const timer = setTimeout(() => { if (this.state === 'loading') { this.state = 'slow'; this.app.ui.refreshPanel('fixes'); } }, 10000);
    this.col.orderBy('createdAt').onSnapshot((snap) => {
      if (!snap.metadata.fromCache) clearTimeout(timer);
      this.items = snap.docs.map(d => ({ ...d.data(), id: d.id }));
      this.online = true; this.state = 'online'; this.render(); this.app.ui.refreshPanel('fixes');
    }, (e) => { clearTimeout(timer); this.state = 'error:' + e.code; this.app.ui.refreshPanel('fixes'); });
  }
  activate() { this.app.ui.hint('מצב עריכה: לחץ על קורה / רצפה / קיר / עמוד כדי לכתוב הוראת תיקון לקלוד'); }
  deactivate() { this.sel.clear(); this.app.viewer.invalidate(); }
  highlight(obj) {
    this.sel.clear();
    if (!obj) return;
    obj.updateMatrixWorld(true);
    obj.traverse(o => {
      if (!o.isMesh) return;
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry, 25), new THREE.LineBasicMaterial({ color: '#00e5ff', depthTest: false }));
      e.applyMatrix4(o.matrixWorld); e.renderOrder = 20; this.sel.add(e);
    });
    this.app.viewer.invalidate();
  }
  handleClick(hit) {
    if (!hit) { this.sel.clear(); this.app.viewer.invalidate(); return; }
    const comp = hit.object.userData.component; const m = comp?.meta || {}; const t = comp?.tags || {};
    this.highlight(comp?.object);
    const P = this.app.coords.fromLocal(hit.point);
    const step = this.app.data.tags.sequence[this.app.store.get().stageIndex];
    const ctx = {
      elementId: m.id || (String(m.name || '').match(ID_RE) || [''])[0], elementName: m.name || 'רכיב',
      layer: t.layer || '', floor: t.floor || '', stage: t.stage || '', system: t.system || '', status: m.status || '',
      source: m.source || '', E: +P.E.toFixed(3), N: +P.N.toFixed(3), H: +P.H.toFixed(3), step: step?.label || '',
    };
    this.app.ui.openFixEditor(ctx, (text, action) => this.add({ ...ctx, text, action }));
  }
  async add(f) {
    if (!f.text.trim()) return;
    const rec = { ...f, text: f.text.trim(), state: 'open', reply: '', createdAt: new Date().toISOString(), author: this.uid || '' };
    if (this.online) {
      try { await this.col.add(rec); this.app.ui.toast('נשמר – קלוד יקרא את התיקון'); }
      catch (e) { this.app.ui.toast(e.code === 'invalid_argument' ? 'אין הרשאת כתיבה במודל הזה' : 'השמירה נכשלה – נסה שוב'); }
    } else {
      this.items = [...this.items, { ...rec, id: Date.now().toString(36) }]; this.saveLocal(this.items); this.render();
      this.app.ui.toast('נשמר בדפדפן הזה בלבד – העתק ושלח לקלוד'); this.app.ui.refreshPanel('fixes');
    }
  }
  async patch(id, data) {
    if (this.online) { try { await this.col.doc(id).update(data); } catch { this.app.ui.toast('העדכון נכשל'); } return; }
    this.items = this.items.map(x => x.id === id ? { ...x, ...data } : x); this.saveLocal(this.items); this.render(); this.app.ui.refreshPanel('fixes');
  }
  async remove(id) {
    if (this.online) { try { await this.col.doc(id).delete(); } catch { this.app.ui.toast('המחיקה נכשלה'); } return; }
    this.items = this.items.filter(x => x.id !== id); this.saveLocal(this.items); this.render(); this.app.ui.refreshPanel('fixes');
  }
  render() {
    this.group.clear();
    const mode = this.pinMode();
    this.items.forEach((n, i) => {
      if (mode === 'off' || (mode === 'open' && n.state === 'done')) return;   // fixed notes stay in the list, not on the model
      const div = document.createElement('div');
      div.className = 'lbl fix-pin' + (n.state === 'done' ? ' done' : n.state === 'question' ? ' q' : '');
      div.textContent = `ק${i + 1}`; div.title = `${n.elementId || n.elementName}: ${n.text}`;
      const o = new CSS2DObject(div); o.position.copy(this.app.coords.toLocal(n.E, n.N, n.H)); this.group.add(o);
    });
    this.app.viewer.invalidate();
  }
  toText() {
    const A = Object.fromEntries(ACTIONS);
    return this.items.map((n, i) => `ק${i + 1}. [${A[n.action] || n.action}] ${n.elementId || ''} ${n.elementName}\n   ${n.text}\n   E ${n.E} N ${n.N} H ${n.H} · שכבה ${n.layer} · שלב ${n.step}${n.state === 'done' ? ' · תוקן' : ''}`).join('\n');
  }
}

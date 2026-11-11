import * as THREE from 'three';

// Proposals layer – the red markings (owner changes OC-n not yet approved with the architect) in a layer of their own
// (chat prompt docs/chat-prompts/2026-11-11-שכבת-הצעות-לשינוי.md):
//  - plan mode (default, state.proposals = false): the model exactly as the plans – no change that is waiting, no red marking
//  - proposals mode: the waiting changes are shown, in red (as they were drawn by the geometry modules)
//  - a status per change: pending (ממתין לאדריכל) / approved (אושר – joins the base plan, no red, in both modes) / rejected
//    (נדחה – never shown). Default: owner-changes.json proposalStatus; changed in the model: artifact db (collection
//    "proposals", read by Claude with ArtifactData and synced to owner-changes.json), outside claude.ai – this browser.
// Nothing is deleted: the geometry modules still build both variants (meta.variant); this module only decides which one
// shows (registry.ocChanged) and hides / neutralises the red parts of every item that belongs to a change.
// Which variant is "the proposal": owner-changes.json proposalVariant (default 'changed'; OC-12 / OC-13 – 'original').
const LS = 'house3d.proposals';
export const STATUS_HE = { pending: 'ממתין לאדריכל', approved: 'אושר', rejected: 'נדחה' };
const LABEL_RE = /\b(oc-tag|removed|removed-q|change)\b/;
const OC_RE = /OC-?(\d+)/;

export class Proposals {
  constructor(app) {
    this.app = app;
    const D = app.display; const F = D.framing, P = D.proposals || {};
    this.red = new Set([F.ownerChangeColor, F.ownerChangeRemovedColor].map(c => new THREE.Color(c).getHex()));
    this.neutral = new THREE.MeshStandardMaterial({ color: P.approvedColor || '#a7adb2', roughness: 0.8 });
    this.list = (app.data.ownerChanges?.changes || []).filter(c => c.kind !== 'query');
    this.byId = Object.fromEntries(this.list.map(c => [c.id, c]));
    this.live = {};   // id -> status changed in the model
    try { this.live = JSON.parse(localStorage.getItem(LS) || '{}').status || {}; } catch {}
    this.where = 'local';
    app.registry.ocChanged = (id, s) => this.changedShown(id, s);
    app.registry.onChange(() => this.paint());
    this.connect();
  }
  status(id) { const c = this.byId[id]; if (!c) return null; return this.live[id] || c.proposalStatus || (c.kind === 'applied' ? 'approved' : 'pending'); }
  pending() { return this.list.filter(c => c.kind !== 'applied' && this.status(c.id) === 'pending'); }
  // is the proposal of change id shown now? approved: always; rejected: never; pending: in proposals mode (unless hidden one by one)
  proposalOn(id, s = this.app.store.get()) {
    const st = this.status(id);
    return st === 'approved' || (st === 'pending' && !!s.proposals && s.proposalShow?.[id] !== false);
  }
  // registry: does the 'changed' variant of change id show?
  changedShown(id, s) {
    const c = this.byId[id]; if (!c) return false;
    const on = this.proposalOn(id, s);
    return (c.proposalVariant || 'changed') === 'changed' ? on : !on;
  }
  // red marks show only for a waiting change in proposals mode
  marksOn(id, s = this.app.store.get()) { return !!s.proposals && this.status(id) === 'pending'; }

  // ---------------------------------------------------------------- the red parts of each item of a change
  changeOf(it) {
    const v = it.meta.variant;
    if (v?.change) return v.change;
    if (v?.all) return v.all.map(x => x.change).find(x => this.byId[x]) || null;
    const m = OC_RE.exec(`${it.meta.id || ''} ${it.meta.name || ''}`);
    return m && this.byId['OC-' + m[1]] ? 'OC-' + m[1] : null;
  }
  scan(it) {
    it._oc = { id: this.changeOf(it), lines: [], basic: [], meshes: [], labels: [] };
    if (!it._oc.id) return;
    it.object.traverse(o => {
      if (o.isCSS2DObject) { if (LABEL_RE.test(o.element.className)) it._oc.labels.push(o); return; }
      const m = o.material; if (!m || Array.isArray(m) || !m.color || !this.red.has(m.color.getHex())) return;
      if (o.isLine || o.isLineSegments) it._oc.lines.push(o);
      else if (o.isMesh && m.isMeshBasicMaterial) it._oc.basic.push(o);               // ghosts / zone boxes / markers
      else if (o.isMesh) it._oc.meshes.push({ o, red: m });   // an element drawn red (new, or the changed one as drawn) – neutral without marks
    });
    // an item that is only a red ghost (the removed element, a zone box): hidden once the change is approved
    let other = false; it.object.traverse(o => { if (o.isMesh && !it._oc.basic.includes(o) && !it._oc.meshes.some(x => x.o === o)) other = true; });
    it._oc.ghost = it._oc.basic.length > 0 && !other && !it._oc.meshes.length;
  }
  paint() {
    const s = this.app.store.get();
    for (const it of this.app.registry.items) {
      if (!it._oc) this.scan(it);
      const id = it._oc.id; if (!id) continue;
      const on = this.marksOn(id, s);
      for (const o of it._oc.lines) o.visible = on;
      for (const o of it._oc.basic) o.visible = on;
      for (const o of it._oc.labels) o.userData.ocHide = !on;   // js/core/labels.js
      for (const x of it._oc.meshes) { const want = on ? x.red : this.neutral; if (x.o.material !== want) x.o.material = want; }
      if (it._oc.ghost && !on) it.object.visible = false;
    }
  }

  // ---------------------------------------------------------------- persistence (artifact db, else this browser)
  saveLocal() { try { localStorage.setItem(LS, JSON.stringify({ status: this.live })); } catch {} }
  async connect() {
    const use = window.claude?.use; const db = use ? await use('db').catch(() => null) : null;
    if (!db) return;
    this.col = db.collection('proposals'); this.where = 'db';
    this.col.onSnapshot((snap) => {
      const live = {};
      for (const d of snap.docs) { const x = d.data(); if (x.id && STATUS_HE[x.status]) live[x.id] = x.status; }
      if (JSON.stringify(live) === JSON.stringify(this.live)) return;
      this.live = live; this.saveLocal(); this.refresh();
    }, () => { this.where = 'local'; });
  }
  async setStatus(id, st) {
    const c = this.byId[id]; if (!c || !STATUS_HE[st]) return;
    if (st === (c.proposalStatus || 'pending')) delete this.live[id]; else this.live[id] = st;
    this.saveLocal(); this.refresh();
    if (this.col) { try { await this.col.doc(id).set({ id, status: st, title: c.title, at: new Date().toISOString() }); } catch { this.app.ui.toast('השמירה במסד נכשלה – נשמר בדפדפן'); } }
  }
  refresh() { const a = this.app; a.registry.apply(a.store.get()); a.viewer.invalidate(); a.ui.syncTop?.(); a.ui.refreshPanel('notes'); a.ui.refreshPanel('layers'); }
  setMode(on) { this.app.store.set({ proposals: !!on }, { label: 'proposals' }); }

  // ---------------------------------------------------------------- jump to a change (its step and place)
  go(c, t = c) {
    const a = this.app;
    if (this.status(c.id) === 'pending' && !a.store.get().proposals) a.store.set({ proposals: true }, { label: 'proposals' });
    if (a.store.get().proposalShow?.[c.id] === false) a.store.set({ proposalShow: { ...a.store.get().proposalShow, [c.id]: true } }, { label: 'proposals' });
    const si = t.showStep ? a.registry.stepById(t.showStep) : a.registry.stepIndex(t.showStage || c.showStage, 'unit');
    if (si >= 0) a.store.set({ stageIndex: si }, { label: 'stage' });
    if (!t.locationITM) return;
    const P = { E: t.locationITM[0], N: t.locationITM[1], H: a.coords.H0 + (t.locationRel ?? 0) };
    if (t.viewOffset) { const tg = a.coords.toLocal(P.E, P.N, P.H); a.viewer.flyTo(tg, tg.clone().add(new THREE.Vector3(...t.viewOffset))); } else a.flyToPoint(P);
  }
}

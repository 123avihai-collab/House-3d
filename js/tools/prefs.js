// Per-user view preferences that survive reloads and new versions (Avihai 08.11.2026: "every time the model opens it is back
// to the start and I tick the layers again"):
//   last     – the viewer's last layers / labels / floors (/ step) – restored on open
//   presets  – named layer views: save, apply, update, rename, delete; one may be marked as the start view
//   open     – which layer groups are expanded
//   seen     – layer ids that existed when the viewer last opened the model: a layer added later is OFF in their saved views and
//              marked "חדש" until they touch it (Avihai 11.11: "every time something new is added it resets")
//   binned   – layers moved out of their domain list into "מוסתרות" (off; can be put back)
//   dropped  – layers removed from this viewer's model (never shown; the data and sources stay; restore in "תצוגה ← הגדרות")
// Stored privately per viewer in the artifact db (data/users/<id>/prefs – nobody else, not even the owner, reads it);
// outside the claude.ai viewer (or before it answers) in this browser's localStorage.
const LS = 'house3d-5187-prefs-v1';
const KEYS = ['layers', 'labelsOff', 'floors', 'stageIndex'];

export class Prefs {
  constructor(app) {
    this.app = app; this.where = 'local';
    this.p = this.readLocal() || { last: null, presets: [], start: null, open: {} };
    this.p.presets ||= []; this.p.open ||= {};
    this.initLists(this.p);
    this.restore(this.p);
    this.lastSaved = JSON.stringify(this.snapshot(true));
    app.store.on(() => this.scheduleSave());
    this.connect();
  }
  readLocal() { try { return JSON.parse(localStorage.getItem(LS) || 'null'); } catch { return null; } }
  writeLocal() { try { localStorage.setItem(LS, JSON.stringify(this.p)); } catch { /* private mode */ } }
  allIds() { return this.app.data.layers.groups.flatMap(g => g.layers.map(l => l.id)); }
  initLists(p) {
    p.binned ||= []; p.dropped ||= [];
    const all = this.allIds();
    if (!p.seen) p.seen = all;                       // first time: nothing is "new"
    this.fresh = new Set(all.filter(id => !p.seen.includes(id)));
  }
  isNew(id) { return this.fresh?.has(id); }
  markSeen(ids) {
    let ch = false;
    for (const id of [].concat(ids)) { this.fresh.delete(id); if (!this.p.seen.includes(id)) { this.p.seen.push(id); ch = true; } }
    if (ch) this.persist();
  }
  isBinned(id) { return this.p.binned.includes(id); }
  isDropped(id) { return this.p.dropped.includes(id); }
  hidden(id) { return this.isBinned(id) || this.isDropped(id); }
  bin(id) { if (!this.isBinned(id)) this.p.binned.push(id); this.off(id); this.persist(); }
  unbin(id) { this.p.binned = this.p.binned.filter(x => x !== id); this.persist(); }
  drop(id) { this.p.binned = this.p.binned.filter(x => x !== id); if (!this.isDropped(id)) this.p.dropped.push(id); this.off(id); this.persist(); }
  undrop(id) { this.p.dropped = this.p.dropped.filter(x => x !== id); this.persist(); }
  off(id) { const L = this.app.store.get().layers; if (L[id] !== false) this.app.store.set({ layers: { ...L, [id]: false } }, { label: 'layer' }); }
  // the part of the state a view keeps
  snapshot(withStage) {
    const s = this.app.store.get(), o = {};
    for (const k of KEYS) if (k !== 'stageIndex' || withStage) o[k] = structuredClone(s[k]);
    return o;
  }
  apply(v, { record = true } = {}) {
    if (!v) return;
    const s = this.app.store.get(), patch = {};
    // a layer added after the view was saved is OFF (marked "חדש" in the panel) – the view never "resets"; removed layers stay off
    if (v.layers) {
      patch.layers = { ...s.layers, ...v.layers };
      for (const id of this.allIds()) if (!(id in v.layers) || this.hidden?.(id)) patch.layers[id] = false;
    }
    if (v.labelsOff) patch.labelsOff = { ...v.labelsOff };
    if (v.floors) patch.floors = Object.fromEntries(Object.entries(s.floors).map(([k, f]) => [k, { ...f, ...(v.floors[k] || {}) }]));
    if (v.stageIndex != null && v.stageIndex < this.app.data.tags.sequence.length) patch.stageIndex = v.stageIndex;
    this.app.store.set(patch, { record, label: 'view' });
  }
  // one-time fix (08.11): a "last" saved while the automatic pipe view was on hides the whole skeleton – drop it once
  heal(p) {
    if (p.healed1) return;
    p.healed1 = true;
    const ids = (this.app.data.layers.groups.find(g => g.id === 'structure')?.layers || []).map(l => l.id);
    if (p.last?.layers && ids.length && ids.every(id => p.last.layers[id] === false)) p.last = null;
  }
  // one-time cleanup (review 13.11.2026): the street contour lines crossed the neighbouring lots – off once in the last view
  heal2(p) {
    if (p.healed2) return;
    p.healed2 = true;
    if (p.last?.layers && p.last.layers.contours !== false) p.last.layers.contours = false;
  }
  restore(p) {
    this.heal(p); this.heal2(p);
    const start = p.start && p.presets.find(x => x.id === p.start);
    this.apply(start ? start.view : p.last, { record: false });
    // layers moved to "מוסתרות" / removed from the model stay off even with no saved view
    const L = this.app.store.get().layers, off = [...(p.binned || []), ...(p.dropped || [])].filter(id => L[id] !== false);
    if (off.length) this.app.store.set({ layers: { ...L, ...Object.fromEntries(off.map(id => [id, false])) } }, { record: false });
  }
  async connect() {
    const use = window.claude?.use; if (!use) return;
    const [db, user] = await Promise.all([use('db').catch(() => null), use('user').catch(() => null)]);
    const uid = user ? await user.id?.().catch(() => null) : null;
    if (!db || !uid) return;
    this.ref = db.doc(`data/users/${uid}/prefs`);
    try {
      const snap = await this.ref.get();
      if (snap.exists) {
        const d = snap.data();
        // groups opened / closed before the account answered keep this session's state
        this.p = { last: d.last || null, presets: d.presets || [], start: d.start || null, open: { ...(d.open || {}), ...(this.sessionOpen || {}) }, healed1: d.healed1, healed2: d.healed2,
          seen: d.seen || this.p.seen, binned: d.binned || this.p.binned || [], dropped: d.dropped || this.p.dropped || [] };
        this.initLists(this.p);
        this.restore(this.p); this.writeLocal(); this.persist();
      } else await this.ref.set({ ...this.p, updatedAt: Date.now() });   // first time: carry this browser's views over
      this.where = 'db'; this.lastSaved = JSON.stringify(this.snapshot(true));
      this.app.ui.refreshPanel('layers');
    } catch { this.where = 'local'; }
  }
  scheduleSave() {
    clearTimeout(this.t);
    this.t = setTimeout(() => {
      const cur = JSON.stringify(this.snapshot(true)); if (cur === this.lastSaved) return;
      this.lastSaved = cur; this.p.last = JSON.parse(cur); this.persist();
    }, 1500);
  }
  async persist() {
    this.writeLocal();
    if (!this.ref) return;
    if (this.busy) { this.again = true; return; }
    this.busy = true;
    try { await this.ref.set({ ...this.p, updatedAt: Date.now() }); } catch { /* keep local copy */ }
    this.busy = false; if (this.again) { this.again = false; this.persist(); }
  }
  // ---- named views ----
  list() { return this.p.presets; }
  save(name, withStage, asStart = false) {
    const id = 'v' + Date.now().toString(36);
    this.p.presets.push({ id, name, view: this.snapshot(withStage), withStage: !!withStage, savedAt: Date.now() });
    if (asStart) this.p.start = id;
    this.current = id;
    this.persist(); return id;
  }
  update(id) { const x = this.p.presets.find(v => v.id === id); if (!x) return; x.view = this.snapshot(x.withStage); x.savedAt = Date.now(); this.persist(); }
  rename(id, name) { const x = this.p.presets.find(v => v.id === id); if (x && name) { x.name = name; this.persist(); } }
  remove(id) { this.p.presets = this.p.presets.filter(v => v.id !== id); if (this.p.start === id) this.p.start = null; this.persist(); }
  use(id) { const x = this.p.presets.find(v => v.id === id); if (x) { this.apply(x.view); this.current = id; } }
  setStart(id) { this.p.start = this.p.start === id ? null : id; this.persist(); }
  // ---- expanded groups ----
  isOpen(g, dflt) { return this.p.open[g] ?? dflt; }
  setOpen(g, v) { (this.sessionOpen ||= {})[g] = v; if (this.p.open[g] === v) return; this.p.open[g] = v; this.persist(); }
}

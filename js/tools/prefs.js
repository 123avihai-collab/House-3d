// Per-user view preferences that survive reloads and new versions (Avihai 08.11.2026: "every time the model opens it is back
// to the start and I tick the layers again"):
//   last     – the viewer's last layers / labels / floors (/ step) – restored on open
//   presets  – named layer views: save, apply, update, rename, delete; one may be marked as the start view
//   open     – which layer groups are expanded
// Stored privately per viewer in the artifact db (data/users/<id>/prefs – nobody else, not even the owner, reads it);
// outside the claude.ai viewer (or before it answers) in this browser's localStorage.
const LS = 'house3d-5187-prefs-v1';
const KEYS = ['layers', 'labelsOff', 'floors', 'stageIndex'];

export class Prefs {
  constructor(app) {
    this.app = app; this.where = 'local';
    this.p = this.readLocal() || { last: null, presets: [], start: null, open: {} };
    this.p.presets ||= []; this.p.open ||= {};
    this.restore(this.p);
    this.lastSaved = JSON.stringify(this.snapshot(true));
    app.store.on(() => this.scheduleSave());
    this.connect();
  }
  readLocal() { try { return JSON.parse(localStorage.getItem(LS) || 'null'); } catch { return null; } }
  writeLocal() { try { localStorage.setItem(LS, JSON.stringify(this.p)); } catch { /* private mode */ } }
  // the part of the state a view keeps
  snapshot(withStage) {
    const s = this.app.store.get(), o = {};
    for (const k of KEYS) if (k !== 'stageIndex' || withStage) o[k] = structuredClone(s[k]);
    return o;
  }
  apply(v, { record = true } = {}) {
    if (!v) return;
    const s = this.app.store.get(), patch = {};
    // keep layers added after the view was saved at their current state
    if (v.layers) patch.layers = { ...s.layers, ...v.layers };
    if (v.labelsOff) patch.labelsOff = { ...v.labelsOff };
    if (v.floors) patch.floors = Object.fromEntries(Object.entries(s.floors).map(([k, f]) => [k, { ...f, ...(v.floors[k] || {}) }]));
    if (v.stageIndex != null && v.stageIndex < this.app.data.tags.sequence.length) patch.stageIndex = v.stageIndex;
    this.app.store.set(patch, { record, label: 'view' });
  }
  restore(p) {
    const start = p.start && p.presets.find(x => x.id === p.start);
    this.apply(start ? start.view : p.last, { record: false });
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
        this.p = { last: d.last || null, presets: d.presets || [], start: d.start || null, open: d.open || {} };
        this.restore(this.p); this.writeLocal();
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
  save(name, withStage) {
    const id = 'v' + Date.now().toString(36);
    this.p.presets.push({ id, name, view: this.snapshot(withStage), withStage: !!withStage, savedAt: Date.now() });
    this.persist(); return id;
  }
  update(id) { const x = this.p.presets.find(v => v.id === id); if (!x) return; x.view = this.snapshot(x.withStage); x.savedAt = Date.now(); this.persist(); }
  rename(id, name) { const x = this.p.presets.find(v => v.id === id); if (x && name) { x.name = name; this.persist(); } }
  remove(id) { this.p.presets = this.p.presets.filter(v => v.id !== id); if (this.p.start === id) this.p.start = null; this.persist(); }
  use(id) { const x = this.p.presets.find(v => v.id === id); if (x) { this.apply(x.view); this.current = id; } }
  setStart(id) { this.p.start = this.p.start === id ? null : id; this.persist(); }
  // ---- expanded groups ----
  isOpen(g, dflt) { return this.p.open[g] ?? dflt; }
  setOpen(g, v) { if (this.p.open[g] === v) return; this.p.open[g] = v; this.persist(); }
}

// Route store: the routes.json in the repository is the baseline; every edit is a per-run override (or a deletion)
// kept in the artifact database, collection "routes" (one document per run – shared, written by Editors / owner),
// so the 3D model can read the same edits (stage 4). Outside the claude.ai viewer the overrides live in localStorage.
// "ייצוא routes.json" merges baseline + overrides into a file to commit.
const LS = 'house3d.planEditor.routes.v1';
const COL = 'routes';
const keyOf = (id) => id.replace(/[^\w@.-]/g, '_');

export class RouteStore {
  constructor(base) {
    this.base = base; this.over = {}; this.undoS = []; this.redoS = []; this.listeners = [];
    this.where = 'local'; this.state = 'idle'; this.canEdit = true; this.uid = null;
    this.pending = new Map(); this.busy = false;
    try { const s = JSON.parse(localStorage.getItem(LS) || 'null'); if (s?.over) this.over = s.over; } catch { /* no storage */ }
  }
  // ---- merged view
  runs() {
    const out = [], seen = new Set();
    for (const r of this.base.runs) { seen.add(r.id); const o = this.over[r.id]; if (o?.deleted) continue; out.push(o?.run || r); }
    for (const [id, o] of Object.entries(this.over)) if (!seen.has(id) && !o.deleted && o.run) out.push(o.run);
    return out;
  }
  get(id) { return this.runs().find(r => r.id === id) || null; }
  nodes() { return this.base.nodes.map(n => this.over['node:' + n.id]?.node || n); }
  editedCount() { return Object.keys(this.over).length; }
  // ---- changes: map id -> new run | null (deleted); one undo step
  apply(changes, label) {
    const before = {}, after = {};
    // keys: a run id, or "node:<id>" for a point (manifold, fixture …) – same collection, same undo step
    for (const [id, val] of Object.entries(changes)) { before[id] = this.over[id] ? structuredClone(this.over[id]) : null; after[id] = val ? (id.startsWith('node:') ? { node: this.stamp(val) } : { run: this.stamp(val) }) : { deleted: true, at: new Date().toISOString(), by: this.uid || 'local' }; }
    this.undoS.push({ before, after, label }); if (this.undoS.length > 200) this.undoS.shift(); this.redoS = [];
    this.setOver(after);
  }
  stamp(run) { return { ...run, status: 'manual', edited: { by: this.uid || 'local', at: new Date().toISOString() } }; }
  undo() { const h = this.undoS.pop(); if (!h) return null; this.redoS.push(h); this.setOver(h.before); return h.label; }
  redo() { const h = this.redoS.pop(); if (!h) return null; this.undoS.push(h); this.setOver(h.after); return h.label; }
  setOver(map) {
    for (const [id, o] of Object.entries(map)) { if (o) this.over[id] = o; else delete this.over[id]; this.pending.set(id, o); }
    this.saveLocal(); this.flush(); this.emit();
  }
  revert(id) { if (!this.over[id]) return; const before = { [id]: structuredClone(this.over[id]) }; this.undoS.push({ before, after: { [id]: null }, label: 'החזרה למקור' }); this.redoS = []; this.setOver({ [id]: null }); }
  onChange(f) { this.listeners.push(f); }
  emit() { this.listeners.forEach(f => f()); }
  saveLocal() { try { localStorage.setItem(LS, JSON.stringify({ over: this.over })); } catch { /* ignore */ } }
  // ---- artifact db
  async connect() {
    const use = window.claude?.use; if (!use) return;
    const [db, user] = await Promise.all([use('db').catch(() => null), use('user').catch(() => null)]);
    if (!db) return;
    this.uid = user ? await user.id?.().catch(() => null) : null;
    const ce = user ? await Promise.resolve(user.canEdit?.()).catch(() => null) : null;
    this.canEdit = ce !== false; this.db = db; this.col = db.collection(COL);
    const timer = setTimeout(() => { this.state = 'timeout'; this.emit(); }, 10000);
    try {
      const snap = await this.col.get(); clearTimeout(timer);
      const remote = {}; for (const d of snap.docs) { const v = d.data(); if (v?.id) remote[v.id] = v.o; }
      // edits made in this browser before the db answered (or while offline) are carried over, the db wins otherwise
      const localOnly = Object.fromEntries(Object.entries(this.over).filter(([id]) => !(id in remote)));
      this.over = { ...remote, ...localOnly };
      for (const id of Object.keys(localOnly)) this.pending.set(id, this.over[id]);
      this.where = 'db'; this.state = 'saved'; this.saveLocal(); this.emit(); this.flush();
      this.unsub = this.col.onSnapshot((qs) => {
        const docs = qs.docs || []; let changed = false;
        const ids = new Set();
        for (const d of docs) { const v = d.data(); if (!v?.id) continue; ids.add(v.id); if (this.pending.has(v.id)) continue; if (JSON.stringify(this.over[v.id]) !== JSON.stringify(v.o)) { this.over[v.id] = v.o; changed = true; } }
        for (const id of Object.keys(this.over)) if (!ids.has(id) && !this.pending.has(id)) { delete this.over[id]; changed = true; }
        if (changed) { this.saveLocal(); this.emit(); }
      }, () => { this.state = 'error'; this.emit(); });
    } catch (e) { clearTimeout(timer); this.where = 'local'; this.state = 'error'; this.err = e?.code || String(e); this.emit(); }
  }
  async flush() {
    if (!this.col || this.busy || !this.pending.size) { if (!this.col) this.state = this.editedCount() ? 'local' : 'idle'; this.emit(); return; }
    this.busy = true; this.state = 'saving'; this.emit();
    while (this.pending.size) {
      const [id, o] = this.pending.entries().next().value;
      try {
        const ref = this.col.doc(keyOf(id));
        if (o) await ref.set({ id, o, at: Date.now() }); else await ref.delete();
        if (this.pending.get(id) === o) this.pending.delete(id);
      } catch (e) { this.state = 'error'; this.err = e?.code || String(e); this.busy = false; this.emit(); return; }
    }
    this.busy = false; this.state = 'saved'; this.emit();
  }
  // ---- export: baseline + overrides -> routes.json content
  exportJson() {
    const out = { ...this.base, runs: this.runs(), nodes: this.nodes(), exportedAt: new Date().toISOString(),
      edits: Object.entries(this.over).map(([id, o]) => ({ id, deleted: !!o.deleted, at: (o.run || o.node)?.edited?.at || o.at })) };
    delete out.__path; return JSON.stringify(out, null, 1);
  }
}

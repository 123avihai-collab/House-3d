// Application settings state with undo/redo, localStorage autosave, export/import.
const STORAGE_KEY = 'house3d-5187-settings-v1';
const MAX_HISTORY = 150;

export class StateStore {
  constructor(defaults) {
    this.defaults = structuredClone(defaults);
    this.state = structuredClone(defaults);
    this.undoStack = [];
    this.redoStack = [];
    this.listeners = [];
    this.load();
  }
  get() { return this.state; }
  // patch: object merged shallowly at top level (nested objects replaced). record=false for transient updates.
  set(patch, { record = true, label = '' } = {}) {
    if (record) {
      this.undoStack.push({ state: structuredClone(this.state), label });
      if (this.undoStack.length > MAX_HISTORY) this.undoStack.shift();
      this.redoStack = [];
    }
    this.state = { ...this.state, ...structuredClone(patch) };
    this.emit();
  }
  // coalesce slider drags: first call records, following calls within ms do not
  setCoalesced(key, patch, ms = 600) {
    const now = performance.now();
    const rec = !(this._coKey === key && now - this._coT < ms);
    this._coKey = key; this._coT = now;
    this.set(patch, { record: rec, label: key });
  }
  undo() {
    const e = this.undoStack.pop(); if (!e) return false;
    this.redoStack.push({ state: structuredClone(this.state), label: e.label });
    this.state = e.state; this.emit(); return true;
  }
  redo() {
    const e = this.redoStack.pop(); if (!e) return false;
    this.undoStack.push({ state: structuredClone(this.state), label: e.label });
    this.state = e.state; this.emit(); return true;
  }
  canUndo() { return this.undoStack.length > 0; }
  canRedo() { return this.redoStack.length > 0; }
  on(f) { this.listeners.push(f); }
  emit() { this.save(); this.listeners.forEach(f => f(this.state)); }
  save() { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(this.state)); } catch (e) { /* private mode */ } }
  load() {
    try {
      const s = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (s && s.version === this.defaults.version) this.state = deepMerge(structuredClone(this.defaults), s);
    } catch (e) { /* ignore */ }
  }
  exportJson() {
    return JSON.stringify({ app: 'house3d-5187', exported: new Date().toISOString(), settings: this.state }, null, 1);
  }
  importJson(text) {
    const o = JSON.parse(text);
    if (!o || o.app !== 'house3d-5187' || !o.settings) throw new Error('קובץ הגדרות לא תקין');
    this.set(deepMerge(structuredClone(this.defaults), o.settings), { label: 'import' });
  }
  reset() { this.set(structuredClone(this.defaults), { label: 'reset' }); }
}

function deepMerge(a, b) {
  for (const k of Object.keys(b)) {
    if (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object' && !Array.isArray(a[k])) {
      a[k] = deepMerge(a[k], b[k]);
    } else a[k] = b[k];
  }
  return a;
}

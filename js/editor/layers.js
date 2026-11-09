// Layer state of the plan editor: visible / locked per layer, kept per viewer in localStorage (a convenience only –
// the page works the same without it). Keys: bg.<group>, st.<structure>, prop.<system>, cons.<system>, cons.superseded, nodes, grid.
const KEY = 'house3d.planEditor.layers.v1';

export class Layers {
  constructor(defaults) {
    this.vis = { ...defaults }; this.lock = {}; this.listeners = [];
    try { const s = JSON.parse(localStorage.getItem(KEY) || 'null'); if (s) { Object.assign(this.vis, s.vis || {}); Object.assign(this.lock, s.lock || {}); } } catch { /* storage unavailable */ }
  }
  on(k) { return this.vis[k] !== false; }
  locked(k) { return !!this.lock[k] || !this.on(k); }
  set(k, v) { this.vis[k] = v; this.save(); }
  setLock(k, v) { this.lock[k] = v; this.save(); }
  save() { try { localStorage.setItem(KEY, JSON.stringify({ vis: this.vis, lock: this.lock })); } catch { /* ignore */ } this.listeners.forEach(f => f()); }
  onChange(f) { this.listeners.push(f); }
}

const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v != null && v !== false) e.setAttribute(k, v === true ? '' : v); }
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
};

export function buildPanel(el, L, cfg, sys, counts) {
  el.innerHTML = '';
  const row = (key, label, sw, opts = {}) => {
    const eye = h('button', { class: L.on(key) ? '' : 'off', title: 'הצג / הסתר', 'data-k': key, onclick: () => { L.set(key, !L.on(key)); } }, '👁');
    const lk = h('button', { class: 'lk' + (L.lock[key] ? '' : ' off'), title: 'נעילה (לא ניתן לבחור / לערוך)', 'data-lock': key, onclick: () => { L.setLock(key, !L.lock[key]); } }, L.lock[key] ? '🔒' : '🔓');
    return h('div', { class: 'lyr' + (opts.ro ? ' ro' : ''), 'data-layer': key }, eye, opts.ro ? null : lk, sw ? h('span', { class: 'sw' + (opts.fill ? ' fill' : ''), style: `background:${sw}` }) : null, h('span', { class: 'nm' }, label), counts[key] != null ? h('span', { class: 'ct' }, counts[key]) : null);
  };
  el.append(h('h4', {}, 'צנרת – ההצעה (לעריכה)'));
  for (const s of cfg.systems.order) el.append(row('prop.' + s, sys[s].label, sys[s].color));
  el.append(row('nodes', 'נקודות צריכה ומחלקים', '#1d2329'));
  el.append(h('h4', {}, 'צנרת – תוכנית היועץ (קריאה בלבד)'));
  for (const s of cfg.systems.order) if (counts['cons.' + s]) el.append(row('cons.' + s, sys[s].label, sys[s].color, { ro: true }));
  el.append(row('cons.superseded', 'גם קווים שההצעה מחליפה (מקווקו)', null, { ro: true }));
  el.append(row('cpoints', 'נקודות היועץ – שוחות, ק.ב, מונה, ברזים…', '#8b5a2b', { ro: true }));
  el.append(row('labels.points', 'שמות הנקודות', null, { ro: true }));
  el.append(h('h4', {}, 'שלד – לבדיקת התנגשויות'));
  for (const [k, st] of Object.entries(cfg.structure)) if (counts['st.' + k]) el.append(row('st.' + k, st.label, st.fill || st.stroke, { ro: true, fill: !!st.fill }));
  el.append(h('h4', {}, 'רקע אדריכלי (DXF היועץ)'));
  for (const [k, st] of Object.entries(cfg.background)) if (counts['bg.' + k]) el.append(row('bg.' + k, st.label, st.color, { ro: true }));
  el.append(h('h4', {}, 'עזר'));
  el.append(row('grid', 'רשת (צירי הבית)', '#9aa', { ro: true }));
  el.append(h('p', { class: 'note' }, 'התוכנית מסובבת לצירי הבית. נעילה מונעת בחירה ועריכה של השכבה. העריכה עצמה – בשלב 2.'));
}

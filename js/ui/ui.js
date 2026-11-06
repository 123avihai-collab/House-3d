import { fmtMin } from '../tools/sun.js';

const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};
const soon = (txt = 'בקרוב') => h('span', { class: 'soon' }, txt);

export class UI {
  constructor(app) {
    this.app = app;
    this.tab = 'layers';
    this.$ = (id) => document.getElementById(id);
    this.buildTop();
    this.buildToolbar();
    this.buildPanel();
    this.buildStageBar();
    app.store.on(() => { this.refreshPanel(); this.syncStageBar(); this.syncTop(); });
    this.syncTop();
  }

  // ---------------- top bar ----------------
  buildTop() {
    const { app } = this; const top = this.$('topbar');
    const modes = h('div', { class: 'seg', id: 'modes' }, app.data.tools.modes.map(m =>
      h('button', { 'data-mode': m.id, class: m.implemented ? '' : 'na', title: m.implemented ? m.label : `${m.label} – בקרוב`,
        onclick: () => m.implemented ? app.store.set({ mode: m.id }, { label: 'mode' }) : this.toast(`מצב "${m.label}" – בקרוב`) }, m.label)));
    const ws = h('select', { class: 'ws', title: 'סדנאות', onchange: (e) => { const w = app.data.tools.workshops.find(x => x.id === e.target.value); if (w) this.toast(`סדנת ${w.label} – בקרוב`); e.target.value = ''; } },
      h('option', { value: '' }, 'סדנאות ▾'), app.data.tools.workshops.map(w => h('option', { value: w.id }, `${w.label} (בקרוב)`)));
    const btn = (icon, title, fn, id) => h('button', { class: 'icon', title, onclick: fn, id }, icon);
    const fileIn = h('input', { type: 'file', accept: '.json,application/json', style: 'display:none', onchange: async (e) => {
      const f = e.target.files[0]; if (!f) return;
      try { app.store.importJson(await f.text()); this.toast('ההגדרות יובאו'); } catch (err) { this.toast('ייבוא נכשל: ' + err.message); }
      e.target.value = '';
    } });
    top.append(
      h('div', { class: 'brand' }, h('b', {}, app.data.manifest.project.name), h('small', {}, app.data.manifest.project.stageLabel)),
      modes, ws,
      (this.ocBadge = h('button', { class: 'oc-badge', title: 'שינויים של אביחי: הפעלה / כיבוי של כל השינויים (להשוואה מול התוכניות)', onclick: () => {
        const cur = app.store.get().ownerChanges || {}; const anyOn = Object.values(cur).some(Boolean);
        app.store.set({ ownerChanges: Object.fromEntries(Object.keys(cur).map(k => [k, !anyOn])) }, { label: 'ownerChanges' });
        this.toast(anyOn ? 'מוצג לפי התוכניות (שינויים כבויים)' : 'מוצגים השינויים של אביחי');
      } }, '')),
      h('div', { class: 'actions' },
        btn('↶', 'ביטול (Ctrl+Z)', () => app.store.undo(), 'undo'),
        btn('↷', 'חזרה (Ctrl+Y)', () => app.store.redo(), 'redo'),
        btn('⤓', 'ייצוא הגדרות (JSON)', () => download(`house3d-5187-settings-${new Date().toISOString().slice(0, 10)}.json`, app.store.exportJson())),
        btn('⤒', 'ייבוא הגדרות', () => fileIn.click()),
        btn('📷', 'צילום מסך (PNG)', () => { const a = h('a', { href: app.viewer.screenshot(), download: `house3d-5187-${Date.now()}.png` }); a.click(); }),
        btn('🔗', 'העתק קישור לתצוגה הנוכחית', () => { navigator.clipboard?.writeText(app.viewLink()); this.toast('הקישור הועתק'); }),
        btn('☰', 'פאנל', () => document.body.classList.toggle('panel-open'), 'panelToggle'),
        fileIn));
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if ((e.ctrlKey || e.metaKey) && e.code === 'KeyZ' && !e.shiftKey) { app.store.undo(); e.preventDefault(); }
      if ((e.ctrlKey || e.metaKey) && (e.code === 'KeyY' || (e.code === 'KeyZ' && e.shiftKey))) { app.store.redo(); e.preventDefault(); }
      if (e.code === 'Escape') { app.nav.stopWalk(); app.setTool('inspect'); }
    });
  }
  syncTop() {
    if (this.ocBadge) {
      const cur = this.app.store.get().ownerChanges || {}; const n = Object.keys(cur).length, on = Object.values(cur).filter(Boolean).length;
      this.ocBadge.style.display = n ? '' : 'none';
      this.ocBadge.textContent = on ? `שינויים: פעילים (${on})` : 'לפי התוכניות';
      this.ocBadge.classList.toggle('off', !on);
    }
    const s = this.app.store.get();
    document.querySelectorAll('#modes button').forEach(b => b.classList.toggle('on', b.dataset.mode === s.mode));
    this.$('undo').disabled = !this.app.store.canUndo();
    this.$('redo').disabled = !this.app.store.canRedo();
  }

  // ---------------- floating toolbar ----------------
  buildToolbar() {
    const { app } = this; const tb = this.$('toolbar');
    const tools = [
      ['inspect', '⌖', 'מידות: לחיצה על רכיב מציגה מידות ומרחקים'],
      ['measure', '📏', 'מדידה חופשית בין שתי נקודות'],
      ['note', '📝', 'הוספת הערה לרכיב'],
      ['walk', '🚶', 'הליכה בגובה עיניים'],
    ];
    for (const [id, icon, title] of tools) {
      tb.append(h('button', { 'data-tool': id, title, onclick: () => id === 'walk' ? (app.nav.walking ? app.nav.stopWalk() : app.nav.startWalk()) : app.setTool(id) }, icon));
    }
    tb.append(h('button', { title: 'חתך', onclick: () => { this.openTab('section'); } }, '✂'));
    tb.append(h('button', { title: 'מבט כללי', onclick: () => app.nav.goTo(app.nav.viewpoints()[0]) }, '⌂'));
    tb.append(h('button', { title: 'מבט על', onclick: () => app.nav.goTo(app.nav.viewpoints()[1]) }, '⊙'));
  }
  setActiveTool(id) { document.querySelectorAll('#toolbar [data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === id)); }
  setWalkUI(on) {
    document.body.classList.toggle('walking', on);
    document.querySelector('#toolbar [data-tool="walk"]')?.classList.toggle('on', on);
  }

  // ---------------- side panel with tabs ----------------
  buildPanel() {
    const p = this.$('panel');
    this.tabs = [
      ['layers', 'שכבות'], ['floors', 'קומות'], ['sun', 'שמש וצל'], ['section', 'חתך'], ['tools', 'מדידה'],
      ['nav', 'ניווט'], ['notes', 'הערות'], ['quantities', 'כמויות'], ['electric', 'חשמל'], ['settings', 'תצוגה'],
    ];
    this.tabBar = h('nav', { class: 'tabs' }, this.tabs.map(([id, label]) => h('button', { 'data-tab': id, onclick: () => this.openTab(id) }, label)));
    this.body = h('div', { class: 'panel-body' });
    p.append(this.tabBar, this.body);
    this.openTab(this.tab, false);
  }
  openTab(id, show = true) {
    this.tab = id;
    this.tabBar.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.tab === id));
    if (show) document.body.classList.add('panel-open');
    this.refreshPanel();
  }
  refreshPanel(only) {
    if (only && only !== this.tab) return;
    const fn = this['panel_' + this.tab];
    const scroll = this.body.scrollTop;
    this.body.replaceChildren(fn ? fn.call(this) : h('div'));
    this.body.scrollTop = scroll;
  }

  panel_layers() {
    const { app } = this; const s = app.store.get();
    const wrap = h('div', {}, h('p', { class: 'muted' }, 'הדלקה וכיבוי לכל שכבה. 🏷 = הסתרת התוויות וקווי הסימון של השכבה בלבד (למשל הקו האדום של הדיפון) – הרכיבים נשארים. מערכות שעוד אין להן נתונים מסומנות "בקרוב".'));
    const colors = Object.fromEntries(app.data.tags.systems.map(x => [x.id, x.color]));
    for (const g of app.data.layers.groups) {
      const sw = h('i', { class: 'sw', style: `background:${colors[g.system]}` });
      const box = h('details', { class: 'grp', open: g.implemented }, h('summary', {}, sw, g.label, g.implemented ? '' : soon()));
      for (const l of g.layers) {
        const impl = g.implemented && l.implemented !== false;
        const on = s.layers[l.id] !== false;
        const lblOff = !!(s.labelsOff || {})[l.id];
        box.append(h('div', { class: 'row lrow' + (impl ? '' : ' na') },
          h('label', {}, h('input', { type: 'checkbox', checked: impl && on, disabled: !impl,
            onchange: (e) => app.store.set({ layers: { ...s.layers, [l.id]: e.target.checked } }, { label: 'layer' }) }), l.label, impl ? '' : soon()),
          impl ? h('button', { class: 'tagbtn' + (lblOff ? ' off' : ''), title: lblOff ? 'הצג תוויות וקווי סימון' : 'הסתר תוויות וקווי סימון (הרכיבים נשארים)',
            onclick: () => app.store.set({ labelsOff: { ...(s.labelsOff || {}), [l.id]: !lblOff } }, { label: 'labels' }) }, '🏷') : ''));
      }
      wrap.append(box);
    }
    wrap.append(h('div', { class: 'btns' },
      h('button', { onclick: () => app.store.set({ layers: Object.fromEntries(Object.keys(s.layers).map(k => [k, true])) }, { label: 'layers' }) }, 'הצג הכול'),
      h('button', { onclick: () => app.store.set({ layers: structuredClone(app.defaults.layers) }, { label: 'layers' }) }, 'ברירת מחדל'),
      h('button', { onclick: () => app.store.set({ labelsOff: {} }, { label: 'labels' }) }, '🏷 כל התוויות')));
    return wrap;
  }

  panel_floors() {
    const { app } = this; const s = app.store.get();
    const wrap = h('div', {}, h('p', { class: 'muted' }, 'הצגה, הסתרה ושקיפות לכל קומה. בשלב 1 יש רכיבים רק ב"מגרש וסביבה".'));
    for (const f of app.data.tags.floors) {
      const st = s.floors[f.id];
      const count = app.registry.items.filter(i => i.tags.floor === f.id).length;
      wrap.append(h('div', { class: 'floor' },
        h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: st.visible, onchange: (e) => app.store.set({ floors: { ...s.floors, [f.id]: { ...st, visible: e.target.checked } } }, { label: 'floor' }) }),
          h('b', {}, f.label), f.level != null ? h('small', {}, ` (${app.coords.fmtRel(f.level)})`) : '', count ? '' : soon('אין עדיין רכיבים')),
        h('div', { class: 'row' }, 'שקיפות', h('input', { type: 'range', min: 0.1, max: 1, step: 0.05, value: st.opacity,
          oninput: (e) => app.store.setCoalesced('floorOp' + f.id, { floors: { ...app.store.get().floors, [f.id]: { ...st, opacity: +e.target.value } } }) })),
        h('button', { class: 'small', onclick: () => app.store.set({ floors: Object.fromEntries(app.data.tags.floors.map(x => [x.id, { ...s.floors[x.id], visible: x.id === f.id }])) }, { label: 'solo' }) }, 'רק קומה זו')));
    }
    return wrap;
  }

  panel_sun() {
    const { app } = this; const s = app.store.get(); const sun = s.sun;
    const pos = app.sun.last || {};
    const rs = app.sun.riseSet(sun.date);
    const d = new Date(sun.date + 'T12:00:00');
    const doy = Math.round((d - new Date(d.getFullYear(), 0, 1)) / 864e5) + 1;
    const setDate = (val) => { const dt = new Date(d.getFullYear(), 0, 1); dt.setDate(+val); const iso = dt.toLocaleDateString('sv-SE'); app.store.setCoalesced('sunDate', { sun: { ...app.store.get().sun, date: iso } }); };
    return h('div', {},
      h('p', { class: 'muted' }, `מיקום השמש מחושב לקואורדינטות המגרש (${app.coords.lat.toFixed(5)}°, ${app.coords.lon.toFixed(5)}°), שעון ישראל, צפון אמיתי.`),
      h('label', { class: 'col' }, `תאריך: ${d.toLocaleDateString('he-IL', { day: 'numeric', month: 'long', year: 'numeric' })}`,
        h('input', { type: 'range', min: 1, max: 365, value: doy, oninput: (e) => setDate(e.target.value) })),
      h('label', { class: 'col' }, `שעה: ${fmtMin(sun.minutes)}`,
        h('input', { type: 'range', min: 240, max: 1260, step: 5, value: sun.minutes, oninput: (e) => app.store.setCoalesced('sunTime', { sun: { ...app.store.get().sun, minutes: +e.target.value } }) })),
      h('div', { class: 'btns' },
        h('input', { type: 'date', value: sun.date, onchange: (e) => e.target.value && app.store.set({ sun: { ...sun, date: e.target.value } }, { label: 'sun' }) }),
        h('button', { onclick: () => { const n = new Date(); app.store.set({ sun: { ...sun, date: n.toLocaleDateString('sv-SE'), minutes: n.getHours() * 60 + n.getMinutes() } }, { label: 'sun' }); } }, 'עכשיו'),
        h('button', { onclick: () => app.toggleSunPlay() }, app.sunPlaying ? '⏸ עצור' : '▶ הנפשת יום')),
      h('div', { class: 'btns' }, [['21.06', 'יום ארוך'], ['21.12', 'יום קצר'], ['21.03', 'שוויון']].map(([dm, lab]) =>
        h('button', { class: 'small', onclick: () => app.store.set({ sun: { ...sun, date: `${d.getFullYear()}-${dm.split('.')[1]}-${dm.split('.')[0]}` } }, { label: 'sun' }) }, lab))),
      h('table', { class: 'kv' },
        tr('אזימוט (מצפון אמיתי)', pos.azimuth != null ? `${pos.azimuth.toFixed(1)}°` : '—'),
        tr('גובה השמש', pos.elevation != null ? `${pos.elevation.toFixed(1)}°` : '—'),
        tr('זריחה / שקיעה', `${fmtMin(rs.rise)} / ${fmtMin(rs.set)}`)));
  }

  panel_section() {
    const { app } = this; const s = app.store.get(); const sec = s.section;
    const set = (patch, key) => app.store.setCoalesced(key || 'sec', { section: { ...app.store.get().section, ...patch } });
    return h('div', {},
      h('p', { class: 'muted' }, 'מישורי חתך שאפשר להזיז. הגובה יחסי ל-±0.00.'),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: sec.hOn, onchange: (e) => app.store.set({ section: { ...sec, hOn: e.target.checked } }, { label: 'section' }) }), h('b', {}, 'חתך אופקי')),
      h('label', { class: 'col' }, `מפלס: ${app.coords.fmtRel(sec.hLevel)} (${(sec.hLevel + app.coords.H0).toFixed(2)})`,
        h('input', { type: 'range', min: -6, max: 12, step: 0.05, value: sec.hLevel, oninput: (e) => set({ hLevel: +e.target.value }, 'secH') })),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: sec.vOn, onchange: (e) => app.store.set({ section: { ...sec, vOn: e.target.checked } }, { label: 'section' }) }), h('b', {}, 'חתך אנכי')),
      h('div', { class: 'seg small' },
        h('button', { class: sec.vAxis === 'E' ? 'on' : '', onclick: () => app.store.set({ section: { ...sec, vAxis: 'E' } }, { label: 'section' }) }, 'חתך צפון–דרום'),
        h('button', { class: sec.vAxis === 'N' ? 'on' : '', onclick: () => app.store.set({ section: { ...sec, vAxis: 'N' } }, { label: 'section' }) }, 'חתך מזרח–מערב'),
        h('button', { onclick: () => app.store.set({ section: { ...sec, vFlip: !sec.vFlip } }, { label: 'section' }) }, '⇄ הפוך צד')),
      h('label', { class: 'col' }, `מיקום: ${sec.vAxis === 'E' ? 'E' : 'N'} ${((sec.vAxis === 'E' ? app.coords.E0 : app.coords.N0) + sec.vPos).toFixed(2)}`,
        h('input', { type: 'range', min: -40, max: 40, step: 0.05, value: sec.vPos, oninput: (e) => set({ vPos: +e.target.value }, 'secV') })));
  }

  panel_tools() {
    const { app } = this; const m = app.tools.measure;
    return h('div', {},
      h('p', { class: 'muted' }, 'מדידה חופשית: לחיצה על שתי נקודות במודל מציגה מרחק תלת-ממדי, מרחק אופקי והפרש גובה.'),
      h('div', { class: 'btns' },
        h('button', { class: app.activeTool === 'measure' ? 'on' : '', onclick: () => app.setTool('measure') }, '📏 התחל מדידה'),
        h('button', { onclick: () => m.clearAll() }, 'נקה מדידות'),
        h('button', { class: app.activeTool === 'inspect' ? 'on' : '', onclick: () => app.setTool('inspect') }, '⌖ מידות רכיב')),
      m.items.length ? h('table', { class: 'kv' }, m.items.map((it, i) => tr(`#${i + 1}`, `${it.d3.toFixed(3)} מ' · אופקי ${it.dh.toFixed(3)} · ΔH ${it.dz.toFixed(3)}`))) : h('p', { class: 'muted' }, 'אין מדידות.'));
  }

  panel_nav() {
    const { app } = this; const s = app.store.get();
    const vps = app.nav.viewpoints();
    return h('div', {},
      h('h4', {}, 'חדרים'), h('p', { class: 'muted' }, 'רשימת החדרים עם קפיצה לחדר: ', soon(), ' (מנתוני הבית, משלב 3 ואילך)'),
      h('h4', {}, 'נקודות מבט'),
      h('div', { class: 'list' }, vps.map(v => h('button', { class: 'li', onclick: () => app.nav.goTo(v) }, v.label))),
      h('h4', {}, 'מבטים שמורים'),
      h('div', { class: 'list' }, s.bookmarks.map((b, i) => h('div', { class: 'li2' },
        h('button', { class: 'li', onclick: () => app.restoreView(b) }, b.name),
        h('button', { class: 'x', title: 'מחק', onclick: () => app.store.set({ bookmarks: s.bookmarks.filter((_, j) => j !== i) }, { label: 'bm' }) }, '✕')))),
      h('button', { onclick: () => { const name = prompt('שם למבט:', `מבט ${s.bookmarks.length + 1}`); if (name) app.store.set({ bookmarks: [...s.bookmarks, { name, ...app.currentView() }] }, { label: 'bm' }); } }, '＋ שמור מבט נוכחי'),
      h('h4', {}, 'הליכה'),
      h('p', { class: 'muted' }, 'הליכה בגובה עיניים על פני השטח (ובהמשך גם במדרגות בין קומות). מחשב: חיצים/WASD וגרירה. טלפון: ג׳ויסטיק.'),
      h('button', { onclick: () => app.nav.walking ? app.nav.stopWalk() : app.nav.startWalk() }, app.nav.walking ? 'יציאה מהליכה' : '🚶 התחל הליכה'));
  }

  panel_notes() {
    const { app } = this; const s = app.store.get();
    return h('div', {},
      h('p', { class: 'muted' }, 'לחיצה על רכיב במצב "הערה" פותחת חלון כתיבה. כל ההערות נאספות לרשימת התיקונים.'),
      h('div', { class: 'btns' },
        h('button', { class: app.activeTool === 'note' ? 'on' : '', onclick: () => app.setTool('note') }, '📝 הוסף הערה'),
        h('button', { onclick: () => { navigator.clipboard?.writeText(app.tools.notes.toText()); this.toast('כל ההערות הועתקו'); } }, '📋 העתק את כל ההערות')),
      h('h4', {}, 'שינויים של אביחי (מעבר לתוכניות)'),
      ...(app.data.ownerChanges?.changes || []).map(c => h('div', { class: 'oc' },
        h('b', {}, `${c.id} · ${c.title}`), h('div', {}, c.description),
        h('small', {}, `${c.date} · ממתין לאישור: ${c.approvals.filter(a => a.status === 'pending').map(a => a.who).join(', ')}`),
        h('div', { class: 'ocseg' },
          h('button', { class: (s.ownerChanges?.[c.id] ?? true) ? '' : 'on', onclick: () => app.store.set({ ownerChanges: { ...s.ownerChanges, [c.id]: false } }, { label: 'ownerChanges' }) }, 'לפי התוכניות'),
          h('button', { class: (s.ownerChanges?.[c.id] ?? true) ? 'on' : '', onclick: () => app.store.set({ ownerChanges: { ...s.ownerChanges, [c.id]: true } }, { label: 'ownerChanges' }) }, 'עם השינוי')),
        h('div', { class: 'muted' }, (s.ownerChanges?.[c.id] ?? true) ? `${c.removedLabel || ''} → ${c.addedLabel || ''}` : 'מוצג כמו בתוכניות המקור'),
        h('div', { class: 'btns' }, h('button', { class: 'small', onclick: () => { app.store.set({ stageIndex: app.registry.stepIndex(c.showStage, 'unit') }, { label: 'stage' }); app.flyToPoint({ E: c.locationITM[0], N: c.locationITM[1], H: app.coords.H0 + c.locationRel }); } }, 'הצג')))),
      h('h4', {}, 'הערות ותיקונים'),
      s.notes.length ? h('ol', { class: 'notes' }, s.notes.map((n, i) => h('li', { class: n.done ? 'done' : '' },
        h('div', {}, n.text), h('small', {}, `${n.component || '—'} · ${app.coords.fmtH(n.H)}`),
        h('div', { class: 'btns' },
          h('button', { class: 'small', onclick: () => app.flyToPoint(n) }, 'הצג'),
          h('button', { class: 'small', onclick: () => app.store.set({ notes: s.notes.map((x, j) => j === i ? { ...x, done: !x.done } : x) }, { label: 'note' }) }, n.done ? 'פתח מחדש' : 'סמן כבוצע'),
          h('button', { class: 'small', onclick: () => { const t = prompt('עריכת הערה:', n.text); if (t != null) app.store.set({ notes: s.notes.map((x, j) => j === i ? { ...x, text: t } : x) }, { label: 'note' }); } }, 'ערוך'),
          h('button', { class: 'small x', onclick: () => app.store.set({ notes: s.notes.filter((_, j) => j !== i) }, { label: 'note' }) }, 'מחק'))))) : h('p', { class: 'muted' }, 'אין הערות עדיין.'));
  }

  panel_quantities() {
    const { app } = this; const q = app.quantities || {}; const P = q.piles, X = q.excavation;
    const piles = app.data.piles.piles;
    const over = piles.filter(p => p.overAllowed).map(p => p.id);
    return h('div', {},
      h('p', { class: 'muted' }, 'כמויות מחושבות מהגיאומטריה במודל (נפחים תיאורטיים, ללא פחת).'),
      h('h4', {}, 'כלונסאות (K-400)'),
      P ? h('table', { class: 'kv' },
        tr('מספר כלונסאות', String(P.count)),
        ...Object.entries(P.byType).sort().map(([k, v]) => tr(k, `${v} יח'`)),
        tr('מטר קידוח כולל', `${P.drill_m.toFixed(0)} מ'`),
        tr('נפח בטון תיאורטי', `${P.concrete_m3.toFixed(2)} מ"ק`),
        tr('מעל המותר – לבדיקה מול הקונסטרוקטור', over.length ? over.join(', ') : '—')) : h('p', { class: 'muted' }, '—'),
      h('h4', {}, 'חפירה ליחידת הדיור'),
      X ? h('table', { class: 'kv' },
        tr('נפח חפירה (מול קרקע 2025)', `${X.volume_m3.toFixed(1)} מ"ק`),
        tr('מתוכו: בור המרתף / תעלות קורות (זמני)', `${X.pitVolume_m3.toFixed(1)} / ${X.trenchVolume_m3.toFixed(1)} מ"ק`),
        tr('שטח תחתית', `${X.bottomArea_m2.toFixed(1)} מ"ר`),
        tr('מפלס תחתית', app.coords.fmtH(app.data.excavation.bottomAbs)),
        tr('עומק מקסימלי', `${X.maxDepth_m.toFixed(2)} מ'`),
        tr('דיפון (זמני – חסר תכנון)', `${X.shoringLength_m.toFixed(1)} מ' · גובה עד ${X.shoringMaxHeight_m.toFixed(2)} מ' · ${X.shoringArea_m2.toFixed(1)} מ"ר`)) : h('p', { class: 'muted' }, '—'),
      h('h4', {}, 'יסודות ומרתף (זמני – עד IFC)'),
      q.foundations ? h('table', { class: 'kv' },
        tr('קורות יסוד ששורטטו', `${q.foundations.beamsCount} · ${q.foundations.beams_m3.toFixed(2)} מ"ק`),
        tr('רצפת מרתף (תלויה)', `${q.foundations.slabs_m3.toFixed(2)} מ"ק`),
        tr('קירות מרתף', `${q.foundations.walls_m3.toFixed(2)} מ"ק`),
        tr('חסרים (ללא מיקום/מפלס)', q.foundations.beamsMissing.join(', ') || '—')) : h('p', { class: 'muted' }, '—'),
      h('h4', {}, 'שלד קומת הקרקע (עד IFC)'),
      q.groundFloor ? h('table', { class: 'kv' },
        tr('רצפת הקרקע', `${q.groundFloor.slab_m3.toFixed(2)} מ"ק`),
        tr('קירות קומת הקרקע', `${q.groundFloor.walls_m3.toFixed(2)} מ"ק`),
        tr('תקרת הקרקע (+3.70)', `${q.groundFloor.ceiling_m3.toFixed(2)} מ"ק`),
        tr('קורות התקרה', `${q.groundFloor.beams_m3.toFixed(2)} מ"ק`),
        tr('קורות בלי גיאומטריה', q.groundFloor.beamsMissing.join(', ') || '—')) : h('p', { class: 'muted' }, '—'),
      h('div', { class: 'btns' }, h('button', { onclick: () => { navigator.clipboard?.writeText(this.body.innerText); this.toast('הכמויות הועתקו'); } }, '📋 העתק')));
  }

  panel_electric() {
    const { app } = this; const el = app.data.tools.electrical;
    return h('div', {},
      h('h4', {}, 'תכנון חשמל ', soon()),
      h('p', { class: 'muted' }, 'הצבת שקעים, מפסקים, נקודות תאורה ותקשורת לפי גבהים סטנדרטיים, עם כתב כמויות נקודות.'),
      h('div', { class: 'list' }, el.pointTypes.map(p => h('button', { class: 'li na', disabled: true }, p.label))),
      h('p', { class: 'muted' }, el.note),
      h('h4', {}, 'כתב כמויות נקודות'), h('table', { class: 'kv' }, el.pointTypes.map(p => tr(p.label, '0'))));
  }

  panel_settings() {
    const { app } = this; const s = app.store.get();
    const q = s.quality;
    return h('div', {},
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: q.ao, onchange: (e) => app.store.set({ quality: { ...q, ao: e.target.checked } }, { label: 'q' }) }), 'Ambient Occlusion'),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: q.shadows, onchange: (e) => app.store.set({ quality: { ...q, shadows: e.target.checked } }, { label: 'q' }) }), 'צללים'),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: q.labels, onchange: (e) => app.store.set({ quality: { ...q, labels: e.target.checked } }, { label: 'q' }) }), 'תוויות'),
      h('label', { class: 'col' }, `חשיפה: ${q.exposure.toFixed(2)}`, h('input', { type: 'range', min: 0.4, max: 1.8, step: 0.05, value: q.exposure, oninput: (e) => app.store.setCoalesced('exp', { quality: { ...app.store.get().quality, exposure: +e.target.value } }) })),
      h('div', { class: 'btns' },
        h('button', { onclick: () => { if (confirm('לאפס את כל ההגדרות (כולל הערות ומבטים שמורים)?')) app.store.reset(); } }, 'איפוס הגדרות')),
      h('h4', {}, 'מקורות הנתונים'),
      h('p', { class: 'muted' }, 'כל רכיב מציג את קובץ המקור שלו בלחיצה (כלי "מידות"). פירוט מלא: sources/README.md ו-docs/verification/stage-1.md.'));
  }

  // ---------------- stage bar ----------------
  buildStageBar() {
    const { app } = this; const bar = this.$('stagebar');
    const st = app.data.tags.sequence;
    this.stageRange = h('input', { type: 'range', min: 0, max: st.length - 1, step: 1, oninput: (e) => { app.store.setCoalesced('stage', { stageIndex: +e.target.value }); this.hint(st[+e.target.value].hint || ''); clearTimeout(this._hintT); this._hintT = setTimeout(() => this.hint(''), 4000); } });
    this.stageLabel = h('b', {});
    const ticks = h('div', { class: 'ticks' }, st.map(s => h('span', {}, s.label)));
    bar.append(h('div', { class: 'stg-head' }, 'שלב בנייה: ', this.stageLabel,
      h('div', { class: 'btns' },
        h('button', { class: 'small', onclick: () => app.store.set({ stageIndex: app.registry.stepById('skeletonEnd'), systemFilter: app.data.tags.skeletonSystems }, { label: 'skeleton' }) }, 'רק שלד'),
        h('button', { class: 'small', onclick: () => app.store.set({ stageIndex: st.length - 1, systemFilter: null }, { label: 'all' }) }, 'הכול'))),
      this.stageRange, ticks);
    this.syncStageBar();
  }
  syncStageBar() {
    const s = this.app.store.get(); const st = this.app.data.tags.sequence;
    this.stageRange.value = s.stageIndex;
    this.stageLabel.textContent = st[s.stageIndex].label + (s.systemFilter ? ' · רק שלד' : '');
  }

  // ---------------- info card, hints, toasts, note editor ----------------
  showInfo(info) {
    const el = this.$('info');
    if (!info) { el.classList.add('hidden'); return; }
    const tagNames = (t) => {
      if (!t) return '';
      const f = this.app.data.tags.floors.find(x => x.id === t.floor)?.label;
      const sy = this.app.data.tags.systems.find(x => x.id === t.system)?.label;
      const sg = this.app.data.tags.stages.find(x => x.id === t.stage)?.label;
      return `קומה: ${f} · מערכת: ${sy} · שלב: ${sg}`;
    };
    el.replaceChildren(
      h('button', { class: 'x close', onclick: () => el.classList.add('hidden') }, '✕'),
      h('h3', {}, info.title), h('div', { class: 'tags' }, tagNames(info.tags)),
      h('table', { class: 'kv' }, info.rows.map(([k, v]) => tr(k, v))),
      info.note ? h('div', { class: 'warn' }, '⚠ ', info.note) : '',
      info.source ? h('div', { class: 'src' }, 'מקור: ', info.source) : '');
    el.classList.remove('hidden');
  }
  hint(text) { const el = this.$('hint'); el.textContent = text; el.classList.toggle('hidden', !text); }
  toast(text) {
    const t = h('div', { class: 'toast' }, text); document.body.append(t);
    setTimeout(() => t.classList.add('out'), 2200); setTimeout(() => t.remove(), 2700);
  }
  openNoteEditor(ctx, onSave) {
    const ta = h('textarea', { rows: 4, placeholder: 'כתוב הערה / תיקון…' });
    const dlg = h('div', { class: 'modal' }, h('div', { class: 'dlg' },
      h('h3', {}, 'הערה חדשה'), h('small', {}, `${ctx.component || 'רכיב'} · E ${ctx.E.toFixed(2)} N ${ctx.N.toFixed(2)} · ${this.app.coords.fmtH(ctx.H)}`), ta,
      h('div', { class: 'btns' }, h('button', { class: 'primary', onclick: () => { onSave(ta.value); dlg.remove(); } }, 'שמור'), h('button', { onclick: () => dlg.remove() }, 'ביטול'))));
    document.body.append(dlg); ta.focus();
  }
  status(text) { this.$('status').textContent = text; }
}

function tr(k, v) { return h('tr', {}, h('th', {}, k), h('td', {}, v)); }
function download(name, text) {
  const a = h('a', { href: URL.createObjectURL(new Blob([text], { type: 'application/json' })), download: name }); a.click();
}
export { h };

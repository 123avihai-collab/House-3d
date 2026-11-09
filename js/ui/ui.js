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
    app.store.on(() => { this.refreshPanel(); this.syncStageBar(); this.syncTop(); this.syncWalkSpeed(); });
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
    const modeSel = h('select', { class: 'mode-sel', title: 'מצב', onchange: (e) => app.store.set({ mode: e.target.value }, { label: 'mode' }) },
      app.data.tools.modes.filter(m => m.implemented).map(m => h('option', { value: m.id }, m.label)));
    this.modeSel = modeSel;
    // element search: "B7" = "B-7", "gw19", "c9"
    const results = h('div', { class: 'search-res hidden' });
    const runSearch = (q, go) => {
      const r = app.tools.search.find(q);
      if (go && r.length === 1) { results.classList.add('hidden'); app.tools.search.show(r[0]); return; }
      results.replaceChildren(...(r.length ? r.map(it => h('button', { class: 'li', onclick: () => { results.classList.add('hidden'); app.tools.search.show(it); } },
        h('b', {}, it.meta.id || ''), ' ', it.meta.name || '', h('small', {}, app.tools.search.describe(it)))) : [h('div', { class: 'muted' }, q ? 'לא נמצא אלמנט בשם הזה' : '')]));
      results.classList.toggle('hidden', !q);
    };
    const sInput = h('input', { type: 'search', class: 'search', placeholder: '🔍 חיפוש: B7, GW19, C9…', title: 'חיפוש אלמנט לפי שם / מזהה – מסמן אותו במודל',
      oninput: (e) => runSearch(e.target.value, false), onkeydown: (e) => { if (e.key === 'Enter') runSearch(e.target.value, true); if (e.key === 'Escape') { e.target.value = ''; results.classList.add('hidden'); app.tools.search.highlight(null); } } });
    this.searchInput = sInput;
    top.append(
      h('div', { class: 'brand' }, h('b', {}, app.data.manifest.project.name), h('small', {}, app.data.manifest.project.stageLabel)),
      modes, modeSel, h('div', { class: 'search-wrap' }, sInput, results), ws,
      (this.ocBadge = h('button', { class: 'oc-badge', title: 'שינויים של אביחי: הפעלה / כיבוי של כל השינויים (להשוואה מול התוכניות)', onclick: () => {
        const cur = app.store.get().ownerChanges || {}; const anyOn = Object.values(cur).some(Boolean);
        app.store.set({ ownerChanges: Object.fromEntries(Object.keys(cur).map(k => [k, !anyOn])) }, { label: 'ownerChanges' });
        this.toast(anyOn ? 'מוצג לפי התוכניות (שינויים כבויים)' : 'מוצגים השינויים של אביחי');
      } }, '')),
      // floors made see-through in the "קומות" tab (saved in the browser): shown here, one click restores
      (this.opBadge = h('button', { class: 'oc-badge op-badge', title: 'יש קומה שקופה (לשונית "קומות"). לחיצה – החזרת כל הקומות לאטומות', onclick: () => {
        const f = app.store.get().floors;
        app.store.set({ floors: Object.fromEntries(Object.entries(f).map(([k, v]) => [k, { ...v, opacity: 1 }])) }, { label: 'opacityReset' });
        this.toast('כל הקומות אטומות');
      } }, '')),
      // ceilings removed in the "קומות" tab: shown here, one click puts them back
      (this.ceBadge = h('button', { class: 'oc-badge op-badge', title: 'יש קומה שהתקרה שלה מוסתרת (לשונית "קומות"). לחיצה – החזרת כל התקרות', onclick: () => {
        const f = app.store.get().floors;
        app.store.set({ floors: Object.fromEntries(Object.entries(f).map(([k, v]) => [k, { ...v, ceiling: true }])) }, { label: 'ceilings' });
        this.toast('כל התקרות מוצגות');
      } }, '')),
      h('div', { class: 'actions' },
        btn('↶', 'ביטול (Ctrl+Z)', () => app.store.undo(), 'undo'),
        btn('↷', 'חזרה (Ctrl+Y)', () => app.store.redo(), 'redo'),
        btn('⤓', 'ייצוא הגדרות (JSON)', () => download(`house3d-5187-settings-${new Date().toISOString().slice(0, 10)}.json`, app.store.exportJson())),
        btn('⤒', 'ייבוא הגדרות', () => fileIn.click()),
        btn('📷', 'צילום מסך (PNG)', () => { const a = h('a', { href: app.viewer.screenshot(), download: `house3d-5187-${Date.now()}.png` }); a.click(); }),
        btn('🔗', 'העתק קישור לתצוגה הנוכחית', () => this.copy(app.viewLink(), 'הקישור הועתק')),
        btn('☰', 'פאנל: פתיחה / סגירה', () => this.togglePanel(), 'panelToggle'),
        fileIn));
    top.prepend(this.$('panelToggle'));   // panel button at the right edge of the bar (RTL start), next to the panel itself
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if ((e.ctrlKey || e.metaKey) && e.code === 'KeyZ' && !e.shiftKey) { app.store.undo(); e.preventDefault(); }
      if ((e.ctrlKey || e.metaKey) && (e.code === 'KeyY' || (e.code === 'KeyZ' && e.shiftKey))) { app.store.redo(); e.preventDefault(); }
      if (e.code === 'Escape') { if (app.activeTool === 'measure' && app.tools.measure.undoPoint()) return; app.nav.stopWalk(); app.setTool('inspect'); }
      if (e.code === 'F8' && app.activeTool === 'measure') { const m = app.tools.measure; m.setOpt('ortho', !m.opts.ortho); this.toast(m.opts.ortho ? 'אורתו: פועל – הנקודה השנייה ננעלת לציר' : 'אורתו: כבוי'); e.preventDefault(); }
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
    if (this.opBadge) {
      const see = this.app.data.tags.floors.filter(f => (s.floors[f.id]?.opacity ?? 1) < 0.999);
      this.opBadge.style.display = see.length ? '' : 'none';
      this.opBadge.textContent = `שקיפות: ${see.map(f => f.label).join(', ')} · איפוס`;
    }
    if (this.ceBadge) {
      const off = this.app.data.tags.floors.filter(f => f.ceilingLayers && s.floors[f.id]?.ceiling === false);
      this.ceBadge.style.display = off.length ? '' : 'none';
      this.ceBadge.textContent = `בלי תקרה: ${off.map(f => f.label).join(', ')} · החזרה`;
    }
    document.querySelectorAll('#modes button').forEach(b => b.classList.toggle('on', b.dataset.mode === s.mode));
    if (this.modeSel) this.modeSel.value = s.mode;
    this.$('undo').disabled = !this.app.store.canUndo();
    this.$('redo').disabled = !this.app.store.canRedo();
  }

  // ---------------- floating toolbar ----------------
  buildToolbar() {
    const { app } = this; const tb = this.$('toolbar');
    const tools = [
      ['inspect', '⌖', 'מידות: לחיצה על רכיב מציגה מידות ומרחקים'],
      ['measure', '📏', 'מדידה: נצמד לפינות / אמצע / קצוות, מציג קו ישיר + פירוק לצירי הבית X / Y / Z'],
      ['note', '📝', 'הוספת הערה לרכיב'],
      ['walk', '🚶', 'הליכה בגובה עיניים'],
    ];
    for (const [id, icon, title] of tools) {
      tb.append(h('button', { 'data-tool': id, title, onclick: () => id === 'walk' ? (app.nav.walking ? app.nav.stopWalk() : app.nav.startWalk()) : app.setTool(id) }, icon));
    }
    tb.querySelector('[data-tool="measure"]').addEventListener('click', () => { if (app.activeTool === 'measure' && !this.isMobile()) this.openTab('tools'); });
    tb.append(h('button', { title: 'חתך', onclick: () => { this.openTab('section'); } }, '✂'));
    tb.append(h('button', { title: 'מבט כללי', onclick: () => app.nav.goTo(app.nav.viewpoints()[0]) }, '⌂'));
    tb.append(h('button', { title: 'מבט על', onclick: () => app.nav.goTo(app.nav.viewpoints()[1]) }, '⊙'));
    const setMap = (on) => { const q = app.store.get().quality; app.store.set({ quality: { ...q, minimap: on } }, { label: 'minimap' }); };
    tb.append(h('button', { 'data-k': 'minimap', title: 'מפה קטנה: הצגה / הסתרה', onclick: () => setMap(app.store.get().quality.minimap === false) }, '🗺'));
    // labels: of the current step -> all -> none
    tb.append(h('button', { 'data-k': 'labels', title: 'תוויות: של השלב הנוכחי / כל התוויות / בלי', onclick: () => {
      const q = app.store.get().quality; const mode = !q.labels ? 'step' : (q.labelMode || 'step') === 'step' ? 'all' : 'off';
      app.store.set({ quality: { ...q, labels: mode !== 'off', labelMode: mode === 'off' ? (q.labelMode || 'step') : mode } }, { label: 'labels' });
      this.toast({ step: 'תוויות: רק של השלב הנוכחי (+ האלמנט שנבחר)', all: 'תוויות: הכול', off: 'בלי תוויות' }[mode]);
    } }, '🏷'));
    // concealed pipes (under the slabs / in the walls) with half see-through concrete – in every step (Avihai's note 4)
    tb.append(h('button', { 'data-k': 'xray', title: 'צנרת מוסתרת: הצגת הצנרת מתחת לרצפות ובתוך הקירות (בטון שקוף למחצה)', onclick: () => {
      const on = !app.store.get().showHidden; app.store.set({ showHidden: on }, { label: 'xray' }); this.toast(on ? 'צנרת מוסתרת: מוצגת (בטון שקוף למחצה)' : 'צנרת מוסתרת: כבוי');
    } }, '🔧'));
    app.store.on((s) => document.querySelector('#toolbar [data-k="xray"]')?.classList.toggle('on', !!s.showHidden));
    document.getElementById('minimapClose')?.addEventListener('click', () => setMap(false));
    this.buildMeasureBar();
  }
  // floating bar of the measuring tool (only while it is active): snap, ortho, axes, undo point, clear, done
  buildMeasureBar() {
    const { app } = this; const m = () => app.tools.measure;
    // icon + text (the text is hidden on a phone, so the bar fits in one row)
    const lb = (icon, text) => [h('span', { class: 'i' }, icon), h('span', { class: 't' }, text)];
    const tg = (k, icon, text, title) => h('button', { 'data-o': k, title, onclick: () => { m().setOpt(k, !m().opts[k]); } }, lb(icon, text));
    this.measureBar = h('div', { id: 'measurebar', class: 'hidden' },
      tg('snap', '🧲', 'הצמדה', 'הצמדה לפינה ■ / אמצע ▲ / קצה ◆ (כבוי = נקודה חופשית על המשטח)'),
      tg('ortho', '⊾', 'אורתו', 'אורתו (F8): הנקודה השנייה ננעלת לציר הקרוב – X / Y / Z'),
      h('div', { class: 'seg small', title: 'צירי הפירוק: צירי הבית (כיוון הקירות) או רשת ITM' },
        h('button', { 'data-ax': 'house', onclick: () => { m().setOpt('axes', 'house'); m().redraw(); } }, 'בית'),
        h('button', { 'data-ax': 'itm', onclick: () => { m().setOpt('axes', 'itm'); m().redraw(); } }, 'ITM')),
      h('button', { title: 'ביטול הנקודה הראשונה (Esc)', onclick: () => m().undoPoint() }, lb('↶', 'נקודה')),
      h('button', { title: 'מחיקת כל המדידות', onclick: () => m().clearAll() }, lb('🗑', 'נקה')),
      h('button', { title: 'סיום מדידה', onclick: () => app.setTool('inspect') }, lb('✓', 'סיום')));
    this.$('viewport').append(this.measureBar);
  }
  syncMeasureBar() {
    const m = this.app.tools.measure; if (!this.measureBar || !m) return;
    this.measureBar.classList.toggle('hidden', this.app.activeTool !== 'measure');
    document.body.classList.toggle('measuring', this.app.activeTool === 'measure');
    this.measureBar.querySelectorAll('[data-o]').forEach(b => b.classList.toggle('on', !!m.opts[b.dataset.o]));
    this.measureBar.querySelectorAll('[data-ax]').forEach(b => b.classList.toggle('on', m.opts.axes === b.dataset.ax));
  }
  setActiveTool(id) { document.querySelectorAll('#toolbar [data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === id)); this.syncMeasureBar(); }
  setWalkUI(on) {
    document.body.classList.toggle('walking', on);
    document.querySelector('#toolbar [data-tool="walk"]')?.classList.toggle('on', on);
    if (!this.walkSpeedBar) {
      const C = this.app.display.camera;
      this.walkSpeedBar = h('div', { id: 'walkspeed', class: 'seg small', title: 'מהירות הליכה (מקשים 1 / 2 / 3)' },
        (C.walkSpeeds_mps || []).map((v, i) => h('button', { 'data-i': i, onclick: () => this.app.nav.setSpeed(i) }, `${C.walkSpeedLabels?.[i] || i + 1}`)));
      document.getElementById('viewport').append(this.walkSpeedBar);
    }
    this.syncWalkSpeed();
  }
  syncWalkSpeed() {
    const i = this.app.store.get().quality.walkSpeed ?? 1;
    this.walkSpeedBar?.querySelectorAll('button').forEach(b => b.classList.toggle('on', +b.dataset.i === i));
  }

  // ---------------- side panel with tabs ----------------
  buildPanel() {
    const p = this.$('panel');
    this.tabs = [
      ['fixes', 'תיקונים לקלוד'], ['layers', 'שכבות'], ['floors', 'קומות'], ['rebar', 'ביקורת ברזל'], ['sun', 'שמש וצל'], ['section', 'חתך'], ['tools', 'מדידה'],
      ['nav', 'ניווט'], ['notes', 'הערות'], ['quantities', 'כמויות'], ['electric', 'חשמל'], ['settings', 'תצוגה'],
    ];
    this.tabBar = h('nav', { class: 'tabs' }, this.tabs.map(([id, label]) => h('button', { 'data-tab': id, onclick: () => this.openTab(id) }, label)));
    this.body = h('div', { class: 'panel-body' });
    this.wideBtn = h('button', { class: 'small', title: 'הרחבה / כיווץ של הפאנל', onclick: () => this.setPanel(this.panelOpen(), !document.body.classList.contains('panel-wide')) }, '⇤');
    const head = h('div', { class: 'panel-head' }, h('b', {}, 'פאנל'), this.wideBtn,
      h('button', { class: 'small', title: 'סגירת הפאנל', onclick: () => this.setPanel(false) }, '✕'));
    p.append(head, this.tabBar, this.body);
    let saved = {}; try { saved = JSON.parse(localStorage.getItem('panelState') || '{}'); } catch {}
    this.isMobile = () => window.matchMedia('(max-width: 760px)').matches;
    this.setPanel(this.isMobile() ? false : saved.open !== false, !!saved.wide, false);
    this.openTab(this.tab, false);
  }
  panelOpen() { return this.isMobile() ? document.body.classList.contains('panel-open') : !document.body.classList.contains('panel-closed'); }
  togglePanel() { this.setPanel(!this.panelOpen()); }
  setPanel(open, wide = document.body.classList.contains('panel-wide'), persist = true) {
    const b = document.body.classList;
    b.toggle('panel-open', open); b.toggle('panel-closed', !open); b.toggle('panel-wide', wide);
    this.wideBtn.textContent = wide ? '⇥' : '⇤';
    this.wideBtn.title = wide ? 'כיווץ הפאנל' : 'הרחבת הפאנל';
    this.$('panelToggle')?.classList.toggle('on', open);
    if (persist) try { localStorage.setItem('panelState', JSON.stringify({ open, wide })); } catch {}
    const rs = () => window.dispatchEvent(new Event('resize'));
    requestAnimationFrame(rs); setTimeout(rs, 260);
  }
  openTab(id, show = true) {
    this.tab = id;
    this.tabBar.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.tab === id));
    if (show && !this.panelOpen()) this.setPanel(true);
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
    const { app } = this; const s = app.store.get(); const P = app.prefs;
    const colors = Object.fromEntries(app.data.tags.systems.map(x => [x.id, x.color]));
    const setLayers = (patch, label = 'layers') => app.store.set({ layers: { ...app.store.get().layers, ...patch } }, { label });
    const implLayers = (g) => g.implemented ? g.layers.filter(l => l.implemented !== false) : [];
    const wrap = h('div', { class: 'layers' });
    // ---- saved views ----
    if (P) {
      const vs = P.list();
      const name = h('input', { type: 'text', placeholder: 'שם לתצוגה חדשה (למשל: שלד בלבד, אינסטלציה)', class: 'vname' });
      const stage = h('input', { type: 'checkbox' });
      const save = () => { const n = name.value.trim(); if (!n) { name.focus(); return; } P.current = P.save(n, stage.checked); this.refreshPanel('layers'); };
      name.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); });
      wrap.append(h('div', { class: 'views' },
        h('h4', {}, 'תצוגות שמורות ', h('small', { class: 'muted' }, P.where === 'db' ? '· נשמר בחשבון שלך – בכל מכשיר' : '· נשמר בדפדפן הזה')),
        vs.length ? h('div', { class: 'vlist' }, ...vs.map(v => h('div', { class: 'vrow' + (P.current === v.id ? ' cur' : '') },
          h('button', { class: 'vuse', title: 'הצג את התצוגה', onclick: () => { P.use(v.id); this.refreshPanel('layers'); } }, v.name, v.withStage ? h('small', {}, ' · כולל שלב') : ''),
          h('button', { class: 'small' + (P.p.start === v.id ? ' on' : ''), title: P.p.start === v.id ? 'נפתחת אוטומטית – לחץ לביטול' : 'פתח את המודל תמיד בתצוגה הזו', onclick: () => { P.setStart(v.id); this.refreshPanel('layers'); } }, '★'),
          h('button', { class: 'small', title: 'עדכן לפי הבחירה הנוכחית', onclick: () => { P.update(v.id); this.hint(`"${v.name}" עודכנה`); } }, '⟳'),
          h('button', { class: 'small', title: 'שנה שם', onclick: () => { const n = prompt('שם חדש', v.name); if (n?.trim()) { P.rename(v.id, n.trim()); this.refreshPanel('layers'); } } }, '✎'),
          h('button', { class: 'small', title: 'מחק', onclick: () => { if (confirm(`למחוק את "${v.name}"?`)) { P.remove(v.id); this.refreshPanel('layers'); } } }, '🗑'))))
          : h('p', { class: 'muted' }, 'עוד אין תצוגות. סמן שכבות ושמור כאן בשם – תחזור אליהן בלחיצה. ★ = התצוגה שבה המודל נפתח.'),
        h('div', { class: 'row vsave' }, name, h('label', { title: 'לשמור גם את שלב הבנייה' }, stage, 'כולל שלב'), h('button', { onclick: save }, 'שמור תצוגה')),
        h('p', { class: 'muted' }, 'הבחירה האחרונה נשמרת אוטומטית ותחזור בפתיחה הבאה' + (P.p.start ? ' (אלא אם סומנה ★ – אז נפתחת התצוגה המסומנת).' : '.'))));
    }
    // ---- navigation tools ----
    const q = h('input', { type: 'search', placeholder: 'חיפוש שכבה…', class: 'lsearch', value: this.layerQ || '' });
    const only = h('input', { type: 'checkbox', checked: !!this.layerOnlyOn });
    const filter = () => {
      this.layerQ = q.value; this.layerOnlyOn = only.checked; const t = q.value.trim();
      for (const d of wrap.querySelectorAll('details.grp')) {
        let any = false;
        for (const r of d.querySelectorAll('.lrow')) {
          const ok = (!t || r.dataset.label.includes(t) || d.dataset.label.includes(t)) && (!only.checked || r.dataset.on === '1');
          r.style.display = ok ? '' : 'none'; any ||= ok;
        }
        d.style.display = any || (!t && !only.checked) ? '' : 'none';
        if ((t || only.checked) && any) d.open = true;
      }
    };
    q.addEventListener('input', filter); only.addEventListener('change', filter);
    const allGroups = () => [...wrap.querySelectorAll('details.grp')];
    wrap.append(h('div', { class: 'ltools' }, q,
      h('label', { title: 'להציג רק שכבות דלוקות' }, only, 'רק הדלוקות'),
      h('button', { class: 'small', onclick: () => allGroups().forEach(d => { d.open = true; (this.grpOpen ||= {})[d.dataset.id] = true; P?.setOpen(d.dataset.id, true); }) }, 'פתח הכול'),
      h('button', { class: 'small', onclick: () => allGroups().forEach(d => { d.open = false; (this.grpOpen ||= {})[d.dataset.id] = false; P?.setOpen(d.dataset.id, false); }) }, 'כווץ הכול')));
    // ---- groups: header checkbox = all its layers (partly on = –) ----
    for (const g of app.data.layers.groups) {
      const L = implLayers(g), n = L.filter(l => s.layers[l.id] !== false).length;
      const gcb = h('input', { type: 'checkbox', checked: L.length > 0 && n === L.length, disabled: !L.length, title: 'סמן / בטל את כל השכבות בקבוצה',
        onclick: (e) => e.stopPropagation(),
        onchange: (e) => setLayers(Object.fromEntries(L.map(l => [l.id, e.target.checked])), 'group') });
      gcb.indeterminate = n > 0 && n < L.length;
      const box = h('details', { class: 'grp', 'data-id': g.id, 'data-label': g.label },
        h('summary', {}, gcb, h('i', { class: 'sw', style: `background:${colors[g.system] || '#888'}` }), g.label,
          L.length ? h('small', { class: 'cnt' }, ` ${n}/${L.length}`) : soon(),
          L.length ? h('button', { class: 'small solo', title: 'רק הקבוצה הזו', onclick: (e) => { e.preventDefault(); e.stopPropagation();
            const all = app.data.layers.groups.flatMap(implLayers); setLayers(Object.fromEntries(all.map(l => [l.id, L.includes(l)])), 'solo'); } }, 'רק זו') : ''));
      // open / collapsed: what was set in this session wins over the saved state (it loads a moment after opening)
      this.grpOpen ||= {};
      box.open = this.grpOpen[g.id] ?? (P ? P.isOpen(g.id, false) : g.implemented);
      box.addEventListener('toggle', () => { if (!box.isConnected) return; this.grpOpen[g.id] = box.open; P?.setOpen(g.id, box.open); });
      for (const l of g.layers) {
        const impl = g.implemented && l.implemented !== false;
        const on = s.layers[l.id] !== false;
        const lblOff = !!(s.labelsOff || {})[l.id];
        box.append(h('div', { class: 'row lrow' + (impl ? '' : ' na'), 'data-label': l.label, 'data-on': impl && on ? '1' : '0' },
          h('label', {}, h('input', { type: 'checkbox', checked: impl && on, disabled: !impl,
            onchange: (e) => setLayers({ [l.id]: e.target.checked }, 'layer') }), l.label, impl ? '' : soon()),
          impl ? h('button', { class: 'tagbtn' + (lblOff ? ' off' : ''), title: lblOff ? 'הצג תוויות וקווי סימון' : 'הסתר תוויות וקווי סימון (הרכיבים נשארים)',
            onclick: () => app.store.set({ labelsOff: { ...(s.labelsOff || {}), [l.id]: !lblOff } }, { label: 'labels' }) }, '🏷') : ''));
      }
      if (g.id === 'environment' && app.environment) box.querySelector('summary').after(app.environment.panel());
      if (app.modules?.[g.id]?.panel) box.querySelector('summary').after(app.modules[g.id].panel());
      wrap.append(box);
    }
    wrap.append(h('div', { class: 'btns' },
      h('button', { onclick: () => app.store.set({ layers: Object.fromEntries(Object.keys(s.layers).map(k => [k, true])) }, { label: 'layers' }) }, 'הצג הכול'),
      h('button', { onclick: () => app.store.set({ layers: Object.fromEntries(Object.keys(s.layers).map(k => [k, false])) }, { label: 'layers' }) }, 'הסתר הכול'),
      h('button', { onclick: () => app.store.set({ layers: structuredClone(app.defaults.layers) }, { label: 'layers' }) }, 'ברירת מחדל'),
      h('button', { onclick: () => app.store.set({ labelsOff: {} }, { label: 'labels' }) }, '🏷 כל התוויות')),
      h('p', { class: 'muted' }, '🏷 = הסתרת התוויות וקווי הסימון של השכבה בלבד – הרכיבים נשארים. "בקרוב" = מערכות שעוד אין להן נתונים.'));
    if (this.layerQ || this.layerOnlyOn) setTimeout(filter);
    return wrap;
  }

  panel_floors() {
    const { app } = this; const s = app.store.get();
    const wrap = h('div', {}, h('p', { class: 'muted' }, 'הצגה, הסתרה ושקיפות לכל קומה (נשמר בדפדפן).'),
      h('div', { class: 'btns' }, h('button', { onclick: () => app.store.set({ floors: Object.fromEntries(Object.entries(s.floors).map(([k, v]) => [k, { ...v, opacity: 1 }])) }, { label: 'opacityReset' }) }, 'איפוס שקיפות – כל הקומות אטומות'),
        h('button', { onclick: () => { const on = app.data.tags.floors.some(f => f.ceilingLayers && s.floors[f.id]?.ceiling === false);
          app.store.set({ floors: Object.fromEntries(Object.entries(s.floors).map(([k, v]) => [k, { ...v, ceiling: on }])) }, { label: 'ceilings' }); } },
          app.data.tags.floors.some(f => f.ceilingLayers && s.floors[f.id]?.ceiling === false) ? 'להחזיר את כל התקרות' : 'להסיר את כל התקרות'),
        h('button', { onclick: () => { const on = app.data.tags.floors.some(f => f.floorLayers && s.floors[f.id]?.slab === false);
          app.store.set({ floors: Object.fromEntries(Object.entries(s.floors).map(([k, v]) => [k, { ...v, slab: on }])) }, { label: 'slabs' }); } },
          app.data.tags.floors.some(f => f.floorLayers && s.floors[f.id]?.slab === false) ? 'להחזיר את כל הרצפות' : 'להסיר את כל הרצפות')));
    for (const f of app.data.tags.floors) {
      const st = s.floors[f.id];
      const count = app.registry.items.filter(i => i.tags.floor === f.id).length;
      wrap.append(h('div', { class: 'floor' },
        h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: st.visible, onchange: (e) => app.store.set({ floors: { ...s.floors, [f.id]: { ...st, visible: e.target.checked } } }, { label: 'floor' }) }),
          h('b', {}, f.label), f.level != null ? h('small', {}, ` (${app.coords.fmtRel(f.level)})`) : '', count ? '' : soon('אין עדיין רכיבים')),
        f.floorLayers ? h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: st.slab !== false, onchange: (e) => app.store.set({ floors: { ...s.floors, [f.id]: { ...st, slab: e.target.checked } } }, { label: 'slab' }) }),
          'רצפה', h('small', { class: 'muted' }, ` – ${f.floorLabel}`)) : '',
        f.ceilingLayers ? h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: st.ceiling !== false, onchange: (e) => app.store.set({ floors: { ...s.floors, [f.id]: { ...st, ceiling: e.target.checked } } }, { label: 'ceiling' }) }),
          'תקרה', h('small', { class: 'muted' }, ` – ${f.ceilingLabel}`)) : '',
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
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: sec.hideBeams !== false, onchange: (e) => app.store.set({ section: { ...sec, hideBeams: e.target.checked } }, { label: 'section' }) }),
        'הסתר את הקורות של הקומה החתוכה'),
      (() => {
        // quick floor plans: cut 1.20 m above the slab of each floor (the floor is shown without its beams)
        // floor levels: tags.json floors[].level (unit -2.60 finish / ground ±0.00 / first +3.70 / roof +6.90)
        const plans = app.data.tags.floors.filter(f => f.level != null).map(f => [f.label, f.level]);
        return h('div', { class: 'btns' }, h('span', { class: 'muted' }, 'תוכנית קומה:'), plans.map(([n, z]) =>
          h('button', { class: 'small', title: `חתך ב-${app.coords.fmtRel(z + 1.2)} (1.20 מ' מעל הרצפה)`, onclick: () => app.store.set({ section: { ...sec, hOn: true, hideBeams: true, hLevel: +(z + 1.2).toFixed(2) } }, { label: 'section' }) }, n)));
      })(),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: sec.vOn, onchange: (e) => app.store.set({ section: { ...sec, vOn: e.target.checked } }, { label: 'section' }) }), h('b', {}, 'חתך אנכי')),
      h('div', { class: 'seg small' },
        h('button', { class: sec.vAxis === 'E' ? 'on' : '', onclick: () => app.store.set({ section: { ...sec, vAxis: 'E' } }, { label: 'section' }) }, 'חתך צפון–דרום'),
        h('button', { class: sec.vAxis === 'N' ? 'on' : '', onclick: () => app.store.set({ section: { ...sec, vAxis: 'N' } }, { label: 'section' }) }, 'חתך מזרח–מערב'),
        h('button', { onclick: () => app.store.set({ section: { ...sec, vFlip: !sec.vFlip } }, { label: 'section' }) }, '⇄ הפוך צד')),
      h('label', { class: 'col' }, `מיקום: ${sec.vAxis === 'E' ? 'E' : 'N'} ${((sec.vAxis === 'E' ? app.coords.E0 : app.coords.N0) + sec.vPos).toFixed(2)}`,
        h('input', { type: 'range', min: -40, max: 40, step: 0.05, value: sec.vPos, oninput: (e) => set({ vPos: +e.target.value }, 'secV') })));
  }

  panel_tools() {
    const { app } = this; const m = app.tools.measure; const n = m.axisNames();
    const on = app.activeTool === 'measure';
    const kind = (k) => ({ vertex: '■', mid: '▲', edge: '◆', face: '●' })[k.split('+')[0]] + (k.includes('ortho') ? '⊾' : '');
    return h('div', { class: 'measure-panel' },
      h('p', { class: 'muted' }, 'לוחצים על שתי נקודות. הסמן נצמד לפינה ■, לאמצע ▲ או לקצה ◆ (אחרת ● משטח). הקו הישיר (האלכסוני) הוא המידה הראשית, והקווים המקווקווים מפרקים אותו לצירי הבית: ',
        h('b', { class: 'ax-x' }, n.x), ' · ', h('b', { class: 'ax-y' }, n.y), ' · ', h('b', { class: 'ax-z' }, n.z), '. אורתו (F8) – מדידה ישרה לאורך ציר. Esc – ביטול נקודה.'),
      h('div', { class: 'btns' },
        h('button', { class: on ? 'on' : 'primary', onclick: () => app.setTool(on ? 'inspect' : 'measure') }, on ? '✓ מודד – לחץ לסיום' : '📏 התחל מדידה'),
        h('button', { class: m.opts.snap ? 'on' : '', onclick: () => m.setOpt('snap', !m.opts.snap) }, '🧲 הצמדה'),
        h('button', { class: m.opts.ortho ? 'on' : '', onclick: () => m.setOpt('ortho', !m.opts.ortho) }, '⊾ אורתו')),
      h('div', { class: 'btns' }, h('span', { class: 'muted' }, 'צירים:'),
        h('div', { class: 'seg small' },
          h('button', { class: m.opts.axes === 'house' ? 'on' : '', onclick: () => { m.setOpt('axes', 'house'); m.redraw(); } }, 'צירי בית'),
          h('button', { class: m.opts.axes === 'itm' ? 'on' : '', onclick: () => { m.setOpt('axes', 'itm'); m.redraw(); } }, 'רשת ITM'))),
      h('p', { class: 'muted' }, m.axesText()),
      m.items.length ? h('table', { class: 'mtable' },
        h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'ישיר'), h('th', { class: 'ax-x' }, n.x), h('th', { class: 'ax-y' }, n.y), h('th', { class: 'ax-z' }, n.z), h('th', {}, ''))),
        h('tbody', {}, m.items.map((it, i) => h('tr', {},
          h('td', { title: `מ: ${kind(it.ka)}  עד: ${kind(it.kb)}` }, `${i + 1}`, h('small', {}, ` ${kind(it.ka)}${kind(it.kb)}`)),
          h('td', { title: `אופקי ${it.dh.toFixed(3)}` }, h('b', {}, it.d3.toFixed(3))),
          h('td', {}, Math.abs(it.dx).toFixed(3)), h('td', {}, Math.abs(it.dy).toFixed(3)), h('td', {}, m.sgn(it.dz)),
          h('td', { class: 'acts' }, h('button', { class: 'small', title: 'הצג במודל', onclick: () => m.focus(i) }, '👁'), h('button', { class: 'small x', title: 'מחק', onclick: () => m.remove(i) }, '✕'))))))
        : h('p', { class: 'muted' }, 'אין מדידות.'),
      h('div', { class: 'btns' },
        h('button', { disabled: !m.items.length, onclick: () => this.copy(m.toText(), 'המדידות הועתקו') }, '📋 העתק מדידות'),
        h('button', { disabled: !m.items.length, onclick: () => m.clearAll() }, '🗑 נקה הכול'),
        h('button', { class: app.activeTool === 'inspect' ? 'on' : '', onclick: () => app.setTool('inspect') }, '⌖ מידות רכיב')));
  }

  panel_nav() {
    const { app } = this; const s = app.store.get();
    const vps = app.nav.viewpoints();
    return h('div', {},
      h('h4', {}, 'חדרים'), h('p', { class: 'muted' }, 'רשימת החדרים עם קפיצה לחדר: ', soon(), ' (מתוכניות האדריכל – שלב 4)'),
      h('h4', {}, 'נקודות מבט'),
      h('div', { class: 'list' }, vps.map(v => h('button', { class: 'li', onclick: () => app.nav.goTo(v) }, v.label))),
      h('h4', {}, 'מבטים שמורים'),
      h('div', { class: 'list' }, s.bookmarks.map((b, i) => h('div', { class: 'li2' },
        h('button', { class: 'li', onclick: () => app.restoreView(b) }, b.name),
        h('button', { class: 'x', title: 'מחק', onclick: () => app.store.set({ bookmarks: s.bookmarks.filter((_, j) => j !== i) }, { label: 'bm' }) }, '✕')))),
      h('button', { onclick: () => { const name = prompt('שם למבט:', `מבט ${s.bookmarks.length + 1}`); if (name) app.store.set({ bookmarks: [...s.bookmarks, { name, ...app.currentView() }] }, { label: 'bm' }); } }, '＋ שמור מבט נוכחי'),
      h('h4', {}, 'הליכה'),
      h('p', { class: 'muted' }, 'הליכה בגובה עיניים על הרצפות, הפודסטים, המדרגות והקרקע (מה שמוצג בשלב הנוכחי), בלי לעבור דרך קירות. מתחילים בנקודה שבמרכז המסך. מחשב: חיצים/WASD, גרירה להסתכלות, 1/2/3 מהירות, Shift האצה. טלפון: ג׳ויסטיק וגרירה.'),
      h('div', { class: 'seg small' }, (app.display.camera.walkSpeeds_mps || []).map((v, i) => h('button', { class: (s.quality.walkSpeed ?? 1) === i ? 'on' : '', onclick: () => app.nav.setSpeed(i) },
        `${app.display.camera.walkSpeedLabels?.[i] || ''} ${v} מ'/ש'`))),
      h('button', { onclick: () => app.nav.walking ? app.nav.stopWalk() : app.nav.startWalk() }, app.nav.walking ? 'יציאה מהליכה' : '🚶 התחל הליכה'));
  }

  panel_notes() {
    const { app } = this; const s = app.store.get();
    return h('div', {},
      h('p', { class: 'muted' }, 'הערות ושאלות לאדריכל / לקונסטרוקטור: לחיצה על רכיב במצב "הערה" פותחת חלון כתיבה. הוראות תיקון למודל – בלשונית "תיקונים לקלוד".'),
      h('div', { class: 'btns' },
        h('button', { class: app.activeTool === 'note' ? 'on' : '', onclick: () => app.setTool('note') }, '📝 הוסף הערה'),
        h('button', { onclick: () => this.copy(app.tools.notes.toText(), 'כל ההערות הועתקו') }, '📋 העתק את כל ההערות')),
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

  panel_fixes() {
    const { app } = this; const T = app.tools.fixes; if (!T) return h('div', {});
    const A = Object.fromEntries(T.constructor.actions());
    const st = T.state;
    const conn = st === 'online' ? ['ok', 'מחובר: התיקונים נשמרים במודל וקלוד קורא אותם ישירות.']
      : st === 'local' ? ['warn', 'לא מחובר לשרת (פתיחה מחוץ ל-claude.ai): התיקונים נשמרים בדפדפן הזה בלבד – העתק ושלח לקלוד.']
      : st === 'loading' ? ['', 'מתחבר…'] : st === 'slow' ? ['warn', 'החיבור איטי – התיקונים עלולים לא להתעדכן עדיין.'] : ['warn', 'אין חיבור לשמירת תיקונים.'];
    const editing = app.store.get().mode === 'edit';
    const list = T.items;
    return h('div', {},
      h('p', { class: 'muted' }, 'מצב עריכה לשלד: בוחרים אלמנט (קורה, רצפה, קיר, עמוד) וכותבים לקלוד מה לתקן במודל. שאלות לאדריכל / לקונסטרוקטור – בלשונית "הערות".'),
      h('div', { class: 'fix-conn ' + conn[0] }, conn[1]),
      h('div', { class: 'btns' },
        h('button', { class: editing ? 'on primary' : 'primary', onclick: () => app.store.set({ mode: editing ? 'view' : 'edit' }, { label: 'mode' }) }, editing ? '✓ מצב עריכה פעיל – לחץ על אלמנט' : '✎ היכנס למצב עריכה'),
        h('button', { onclick: () => this.copy(T.toText(), 'כל התיקונים הועתקו') }, '📋 העתק הכול')),
      h('div', { class: 'btns seg', role: 'group', 'aria-label': 'סימני תיקונים במודל' }, h('span', { class: 'muted' }, 'סימני תיקונים במודל:'),
        ...[['all', 'הכול'], ['open', 'רק פתוחים'], ['off', 'כבוי']].map(([k, l]) => h('button', { class: 'small' + ((app.store.get().fixPins || 'open') === k ? ' on' : ''),
          onclick: () => { app.store.set({ fixPins: k }, { label: 'fix pins' }); this.refreshPanel('fixes'); } }, l))),
      h('h4', {}, `תיקונים (${list.filter(x => x.state !== 'done').length} פתוחים מתוך ${list.length})`),
      list.length ? h('ol', { class: 'notes fixes' }, list.map((n, i) => h('li', { class: n.state === 'done' ? 'done' : '' },
        h('div', {}, h('b', {}, `ק${i + 1} · ${A[n.action] || n.action || ''} · ${n.elementId || ''}`), ' ', n.text),
        h('small', {}, `${n.elementName} · ${app.coords.fmtH(n.H)} · שלב: ${n.step || '—'}`),
        n.reply ? h('div', { class: 'fix-reply' }, `קלוד: ${n.reply}`) : null,
        h('div', { class: 'btns' },
          h('button', { class: 'small', onclick: () => app.flyToPoint(n) }, 'הצג'),
          h('button', { class: 'small', onclick: () => T.patch(n.id, { state: n.state === 'done' ? 'open' : 'done' }) }, n.state === 'done' ? 'פתח מחדש' : 'סמן כתוקן'),
          h('button', { class: 'small', onclick: () => { const t = prompt('עריכת התיקון:', n.text); if (t != null && t.trim()) T.patch(n.id, { text: t.trim() }); } }, 'ערוך'),
          h('button', { class: 'small x', onclick: () => { if (confirm('למחוק את התיקון?')) T.remove(n.id); } }, 'מחק'))))) : h('p', { class: 'muted' }, 'אין תיקונים עדיין.'));
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
      h('h4', {}, 'שלד קומת הקרקע'),
      q.groundFloor ? (() => {
        const zv = {}; for (const s of app.data.floorGround.slab) { const k = s.zone === 'mamad' ? 'ממ"ד' : ['house', 'entry'].includes(s.zone) ? 'בית וכניסה' : 'חוץ'; zv[k] = (zv[k] || 0) + s.area_m2 * s.thickness_m; }
        return h('table', { class: 'kv' },
          tr('רצפת הקרקע', `${q.groundFloor.slab_m3.toFixed(2)} מ"ק (${Object.entries(zv).map(([k, v]) => `${k} ${v.toFixed(2)}`).join(' · ')})`),
          tr('קירות / עמודים', `${q.groundFloor.walls_m3.toFixed(2)} / ${(q.groundFloor.columns_m3 || 0).toFixed(2)} מ"ק`),
          tr('תקרת הקרקע (+3.70)', `${q.groundFloor.ceiling_m3.toFixed(2)} מ"ק`),
          tr('קורות התקרה (מתחת לתקרה)', `${q.groundFloor.beams_m3.toFixed(2)} מ"ק`),
          tr('קורות בלי גיאומטריה', q.groundFloor.beamsMissing.join(', ') || '—'));
      })() : h('p', { class: 'muted' }, '—'),
      h('h4', {}, "קומה א' וגג"),
      h('table', { class: 'kv' },
        q.firstFloor ? tr("קירות / עמודים קומה א'", `${q.firstFloor.walls_m3.toFixed(2)} / ${(q.firstFloor.columns_m3 || 0).toFixed(2)} מ"ק`) : '',
        q.firstFloor ? tr('תקרת הגג (+6.90)', `${q.firstFloor.ceiling_m3.toFixed(2)} מ"ק`) : '',
        q.roof ? tr('מעקות וקירות מעל הגג', `${q.roof.walls_m3.toFixed(2)} מ"ק`) : '',
        q.roof ? tr('קורות גג ופרגולות', `${q.roof.beams_m3.toFixed(2)} מ"ק`) : ''),
      h('h4', {}, 'מדרגות, חומות ופילר'),
      h('table', { class: 'kv' },
        q.stairs ? tr('מדרגות בטון', `${q.stairs.concrete_m3.toFixed(2)} מ"ק`) : '',
        q.perimeter ? tr('יסודות חומות / חומות', `${q.perimeter.footings_m3.toFixed(2)} / ${q.perimeter.walls_m3.toFixed(2)} מ"ק`) : ''),
      h('h4', {}, 'בנייה בבלוקים (איטונג 60×25)'),
      q.blocks ? h('table', { class: 'kv' },
        ...(() => { const B = app.data.blocksCfg?.block, face = B ? B.length_m * B.height_m : 0.15; const W = app.data.blocksCfg?.waste_pct?.value ?? 0;
          return [...Object.entries(q.blocks.byThickness).sort((a, b) => +a[0] - +b[0]).map(([t, v]) => tr(`עובי ${t} ס"מ`, `${v.area_m2.toFixed(1)} מ"ר ≈ ${Math.round(v.area_m2 / face)} בלוקים (בקיר: ${v.full} שלמים + ${v.cut} חתוכים)`)),
            tr('סה"כ להזמנה', `${Math.round(q.blocks.area_m2 / face * (1 + W / 100))} בלוקים (${q.blocks.area_m2.toFixed(1)} מ"ר + ${W}% פחת, זמני)`)]; })(),
        tr('משקופים (בלוק משקוף)', `${q.blocks.lintels || 0} · ${(q.blocks.lintel_m || 0).toFixed(2)} מ' (הישענות זמנית)`),
        tr('ארגזי תריס גלילה', `${q.blocks.boxes}`)) : h('p', { class: 'muted' }, '—'),
      h('h4', {}, 'ביוב וניקוז'),
      q.plumbing ? h('table', { class: 'kv' }, tr('שוחות', `${q.plumbing.chambers}`), tr('קווים', `${q.plumbing.pipes} · ${q.plumbing.pipeLength_m.toFixed(1)} מ'`), tr('שרוולים נדרשים', `${q.plumbing.sleeves}`)) : '',
      (() => {
        const v = [P?.concrete_m3, q.foundations?.beams_m3, q.foundations?.slabs_m3, q.foundations?.walls_m3, q.groundFloor?.slab_m3, q.groundFloor?.walls_m3, q.groundFloor?.columns_m3, q.groundFloor?.ceiling_m3,
          q.groundFloor?.beams_m3, q.firstFloor?.walls_m3, q.firstFloor?.columns_m3, q.firstFloor?.ceiling_m3, q.roof?.walls_m3, q.roof?.beams_m3, q.stairs?.concrete_m3,
          q.perimeter?.footings_m3, q.perimeter?.walls_m3].filter(x => x != null).reduce((a, b) => a + b, 0);
        return h('table', { class: 'kv total' }, tr('סה"כ בטון שלד (כולל כלונסאות, בלי הבריכה)', `${v.toFixed(1)} מ"ק`));
      })(),
      h('div', { class: 'btns' }, h('button', { onclick: () => this.copy(this.body.innerText, 'הכמויות הועתקו') }, '📋 העתק')));
  }

  panel_rebar() {
    const { app } = this; const T = app.tools.rebar; if (!T) return h('div', {});
    const s = app.store.get(); const seq = app.data.tags.sequence;
    const i = this.rebarStep ?? s.stageIndex;
    const list = T.itemsOfStep(i);
    const done = list.filter(x => T.checks[x.key]?.ok).length;
    const sel = h('select', { onchange: (e) => { this.rebarStep = +e.target.value; app.store.set({ stageIndex: +e.target.value }, { label: 'stage' }); } },
      seq.map((st, k) => h('option', { value: k, selected: k === i }, `${k + 1}. ${st.label}`)));
    return h('div', {},
      h('p', { class: 'muted' }, 'ביקורת ברזל בסיור שטח: האלמנטים שנבנים בשלב, עם הברזל מגיליונות הקונסטרוקטור (K-12/K-22/K-32/K-42 קורות, K-13/K-23/K-33/K-43 רצפות). מסמנים "נבדק" ורושמים הערה.'),
      h('div', { class: 'fix-conn ' + (T.state === 'online' ? 'ok' : 'warn') }, T.state === 'online' ? 'הסימונים נשמרים במודל (משותף).' : 'הסימונים נשמרים בדפדפן הזה בלבד.'),
      h('label', { class: 'col' }, 'שלב:', sel),
      h('h4', {}, `${seq[i]?.label || ''} · נבדקו ${done} מתוך ${list.length}`),
      list.length ? h('ol', { class: 'notes rebar' }, list.map(({ item, info, key }) => {
        const c = T.checks[key] || {};
        return h('li', { class: c.ok ? 'done' : '' },
          h('div', {}, h('b', {}, item.meta.id || ''), ' ', item.meta.name || ''),
          h('table', { class: 'kv' }, info.map(([k, v]) => tr(k, v))),
          c.note ? h('div', { class: 'fix-reply' }, `הערה: ${c.note}`) : null,
          c.at && c.ok ? h('small', {}, `נבדק ${new Date(c.at).toLocaleString('he-IL')}`) : null,
          h('div', { class: 'btns' },
            h('button', { class: 'small' + (c.ok ? ' on' : ''), onclick: () => T.setCheck(key, { ok: !c.ok, element: item.meta.id || '', name: item.meta.name || '', step: seq[i]?.id }) }, c.ok ? '✓ נבדק' : 'סמן נבדק'),
            h('button', { class: 'small', onclick: () => { const t = prompt('הערת ביקורת:', c.note || ''); if (t != null) T.setCheck(key, { note: t.trim(), element: item.meta.id || '', name: item.meta.name || '', step: seq[i]?.id }); } }, 'הערה'),
            h('button', { class: 'small', onclick: () => app.tools.search.show(item) }, 'הצג')));
      })) : h('p', { class: 'muted' }, 'אין בשלב הזה אלמנטים עם נתוני ברזל (חפירה, מילוי, צנרת, פיתוח – או שהאלמנטים עוד בלי גיליון ברזל).'),
      h('div', { class: 'btns' }, h('button', { onclick: () => this.copy(list.map(({ item, info, key }) => `${T.checks[key]?.ok ? '✓' : '☐'} ${item.meta.id || ''} ${item.meta.name || ''}\n` + info.map(([k, v]) => `   ${k}: ${v}`).join('\n') + (T.checks[key]?.note ? `\n   הערה: ${T.checks[key].note}` : '')).join('\n'), 'רשימת הביקורת הועתקה') }, '📋 העתק רשימה')));
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
      h('div', { class: 'seg small' },
        h('button', { class: (q.labelMode || 'step') === 'step' ? 'on' : '', onclick: () => app.store.set({ quality: { ...q, labels: true, labelMode: 'step' } }, { label: 'q' }) }, 'תוויות השלב הנוכחי'),
        h('button', { class: q.labelMode === 'all' ? 'on' : '', onclick: () => app.store.set({ quality: { ...q, labels: true, labelMode: 'all' } }, { label: 'q' }) }, 'כל התוויות')),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: q.minimap !== false, onchange: (e) => app.store.set({ quality: { ...q, minimap: e.target.checked } }, { label: 'q' }) }), 'מפה קטנה'),
      h('label', { class: 'col' }, `חשיפה: ${q.exposure.toFixed(2)}`, h('input', { type: 'range', min: 0.4, max: 1.8, step: 0.05, value: q.exposure, oninput: (e) => app.store.setCoalesced('exp', { quality: { ...app.store.get().quality, exposure: +e.target.value } }) })),
      h('div', { class: 'btns' },
        h('button', { onclick: () => { if (confirm('לאפס את כל ההגדרות (כולל הערות ומבטים שמורים)?')) app.store.reset(); } }, 'איפוס הגדרות')),
      h('h4', {}, 'קבצים'),
      h('div', { class: 'btns' },
        h('button', { onclick: () => download(`house3d-5187-settings-${new Date().toISOString().slice(0, 10)}.json`, app.store.exportJson()) }, '⤓ ייצוא הגדרות'),
        h('button', { onclick: () => document.querySelector('#topbar input[type=file]')?.click() }, '⤒ ייבוא הגדרות'),
        h('button', { onclick: () => { const a = h('a', { href: app.viewer.screenshot(), download: `house3d-5187-${Date.now()}.png` }); a.click(); } }, '📷 צילום מסך')),
      h('h4', {}, 'מקורות הנתונים'),
      h('p', { class: 'muted' }, 'כל רכיב מציג את קובץ המקור שלו בלחיצה (כלי "מידות"), כולל הברזל מגיליונות הקונסטרוקטור. פירוט: sources/README.md ו-docs/verification/ (שלבים 1, 2, 2ב, 3).'));
  }

  // ---------------- stage bar ----------------
  buildStageBar() {
    const { app } = this; const bar = this.$('stagebar');
    const st = app.data.tags.sequence;
    const go = (i) => app.store.set({ stageIndex: Math.max(0, Math.min(st.length - 1, i)) }, { label: 'stage' });
    this.stageRange = h('input', { type: 'range', min: 0, max: st.length - 1, step: 1, oninput: (e) => app.store.setCoalesced('stage', { stageIndex: +e.target.value }) });
    this.stageSel = h('select', { class: 'stg-sel', title: 'קפיצה לשלב', onchange: (e) => go(+e.target.value) }, st.map((s, i) => h('option', { value: i }, `${i + 1}/${st.length} · ${s.label}`)));
    // ticks: one mark per step at its exact slider position (labels in the list / tooltip – 24 names do not fit in a row)
    const ticks = h('div', { class: 'ticks2' }, st.map((s, i) => h('i', { title: s.label, style: `inset-inline-start: calc(${(i / (st.length - 1)) * 100}% - 1px)`, onclick: () => go(i) })));
    bar.append(h('div', { class: 'stg-head' },
      h('button', { class: 'small stg-nav', title: 'השלב הקודם', onclick: () => go(app.store.get().stageIndex - 1) }, '›'),
      this.stageSel,
      h('button', { class: 'small stg-nav', title: 'השלב הבא', onclick: () => go(app.store.get().stageIndex + 1) }, '‹'),
      h('div', { class: 'btns' },
        h('button', { class: 'small', onclick: () => app.store.set({ stageIndex: app.registry.stepById('skeletonEnd'), systemFilter: app.data.tags.skeletonSystems }, { label: 'skeleton' }) }, 'רק שלד'),
        h('button', { class: 'small', onclick: () => app.store.set({ stageIndex: st.length - 1, systemFilter: null }, { label: 'all' }) }, 'הכול'))),
      h('div', { class: 'stg-track' }, this.stageRange, ticks));
    this.syncStageBar();
  }
  syncStageBar() {
    const s = this.app.store.get(); const st = this.app.data.tags.sequence;
    this.stageRange.value = s.stageIndex;
    this.stageSel.value = s.stageIndex;
    this.stageSel.title = (st[s.stageIndex]?.hint || '') + (s.systemFilter ? ' · רק שלד' : '');
    this.stageSel.classList.toggle('skel', !!s.systemFilter);
    // the hint of the step on every change (slider, buttons, list, viewpoints, search)
    if (this._lastStage !== undefined && this._lastStage !== s.stageIndex) {
      this.hint(`${s.stageIndex + 1}. ${st[s.stageIndex].label}: ${st[s.stageIndex].hint || ''}`);
      clearTimeout(this._hintT); this._hintT = setTimeout(() => this.hint(''), 5000);
      this.rebarStep = undefined;
    }
    this._lastStage = s.stageIndex;
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
  showInfoFor(item) { this.app.tools.inspect?.showFor(item); }
  hint(text) { const el = this.$('hint'); el.textContent = text; el.classList.toggle('hidden', !text); }
  // copy to the clipboard; where the browser does not allow it (http, old phones) the text is shown for a manual copy
  copy(text, ok = 'הועתק') {
    const manual = () => {
      const ta = h('textarea', { rows: 10, readonly: true }); ta.value = text;
      const dlg = h('div', { class: 'modal' }, h('div', { class: 'dlg' }, h('h3', {}, 'העתקה'), h('small', {}, 'סמן והעתק (Ctrl+C / לחיצה ארוכה):'), ta,
        h('div', { class: 'btns' }, h('button', { onclick: () => dlg.remove() }, 'סגור'))));
      document.body.append(dlg); ta.focus(); ta.select();
    };
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(() => this.toast(ok), manual); else manual();
  }
  toast(text) {
    const t = h('div', { class: 'toast' }, text); document.body.append(t);
    setTimeout(() => t.classList.add('out'), 2200); setTimeout(() => t.remove(), 2700);
  }
  openFixEditor(ctx, onSave) {
    const { app } = this; let action = 'other';
    const ta = h('textarea', { rows: 4, placeholder: 'מה לתקן? למשל: "הקיר צריך להיגמר בקורה B-27", "הרצפה צריכה להיות 20 ס\"מ נמוכה יותר", "למחוק – אין קיר כאן"' });
    const chips = h('div', { class: 'chips' }, app.tools.fixes.constructor.actions().map(([id, label]) =>
      h('button', { class: 'small' + (id === action ? ' on' : ''), onclick: (e) => { action = id; chips.querySelectorAll('button').forEach(b => b.classList.remove('on')); e.target.classList.add('on'); } }, label)));
    const close = () => { dlg.remove(); app.tools.fixes.highlight(null); };
    const dlg = h('div', { class: 'modal' }, h('div', { class: 'dlg' },
      h('h3', {}, 'תיקון לקלוד'),
      h('table', { class: 'kv' }, tr('אלמנט', `${ctx.elementName}${ctx.elementId ? ` (${ctx.elementId})` : ''}`), tr('שכבה / קומה', `${ctx.layer} · ${ctx.floor}`),
        tr('נקודה', `E ${ctx.E.toFixed(2)} N ${ctx.N.toFixed(2)} · ${app.coords.fmtH(ctx.H)}`), tr('שלב בנייה במסך', ctx.step || '—')),
      chips, ta,
      h('div', { class: 'btns' }, h('button', { class: 'primary', onclick: () => { onSave(ta.value, action); close(); } }, 'שמור תיקון'), h('button', { onclick: close }, 'ביטול'))));
    document.body.append(dlg); ta.focus();
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

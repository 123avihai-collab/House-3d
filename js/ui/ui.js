import { askConfirm, askText } from '../core/dialog.js';
import * as THREE from 'three';
import { fmtMin } from '../tools/sun.js';
import { STATUS_HE } from '../tools/proposals.js';

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
    if (matchMedia('(pointer: coarse)').matches) this.status('גע ברכיב כדי לראות מידות · ☰ שכבות ותצוגה');
  }

  // ---------------- top bar ----------------
  buildTop() {
    const { app } = this; const top = this.$('topbar');
    // only working modes are buttons (review 13.11.2026: "ריהוט" / "קופינג" were dead buttons that pushed the bar over)
    const modes = h('div', { class: 'seg', id: 'modes' }, app.data.tools.modes.filter(m => m.implemented).map(m =>
      h('button', { 'data-mode': m.id, class: m.implemented ? '' : 'na', title: m.implemented ? m.label : `${m.label} – בקרוב`,
        onclick: () => m.implemented ? app.store.set({ mode: m.id }, { label: 'mode' }) : this.toast(`מצב "${m.label}" – בקרוב`) }, m.label)));
    const ws = h('select', { class: 'ws', title: 'סדנאות', onchange: (e) => { const w = app.data.tools.workshops.find(x => x.id === e.target.value);
      if (w?.implemented && w.mode) app.store.set({ mode: w.mode }, { label: 'mode' }); else if (w) this.toast(`סדנת ${w.label} – בקרוב`); e.target.value = ''; } },
      h('option', { value: '' }, 'סדנאות ▾'), app.data.tools.workshops.map(w => h('option', { value: w.id }, w.implemented ? w.label : `${w.label} (בקרוב)`)));
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
    const sInput = h('input', { type: 'search', class: 'search', placeholder: '🔍 חיפוש: B7, C9…', title: 'חיפוש אלמנט לפי שם / מזהה – מסמן אותו במודל',
      oninput: (e) => runSearch(e.target.value, false), onkeydown: (e) => { if (e.key === 'Enter') runSearch(e.target.value, true); if (e.key === 'Escape') { e.target.value = ''; results.classList.add('hidden'); app.tools.search.highlight(null); } } });
    this.searchInput = sInput;
    top.append(
      h('div', { class: 'brand', title: `${app.data.manifest.project.name}\n${app.data.manifest.project.stageLabel}` }, h('b', {}, app.data.manifest.project.name), h('small', {}, app.data.manifest.project.stageLabel)),
      modes, modeSel, h('div', { class: 'search-wrap' }, sInput, results), ws,
      // proposals layer (js/tools/proposals.js): plan mode / proposals mode – the red markings of changes waiting for the architect
      (this.ocBadge = h('button', { class: 'oc-badge', title: 'שכבת הצעות לשינוי: מצב תוכנית (לפי תוכנית האדריכל, בלי אדום) / מצב הצעות (השינויים הממתינים – באדום). הרשימה: בקרה ← הערות', onclick: () => {
        const on = !app.store.get().proposals; app.proposals.setMode(on);
        this.toast(on ? 'מצב הצעות – השינויים הממתינים מוצגים באדום' : 'מצב תוכנית – לפי תוכנית האדריכל, בלי סימונים אדומים');
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
      const P = this.app.proposals, on = !!this.app.store.get().proposals, n = P ? P.pending().length : 0;
      this.ocBadge.style.display = P?.list.length ? '' : 'none';
      this.ocBadge.textContent = on ? `מצב הצעות (${n})` : 'מצב תוכנית';
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
      ['walk', '🚶', 'הליכה בגובה עיניים'],
    ];
    for (const [id, icon, title] of tools) {
      tb.append(h('button', { 'data-tool': id, title, onclick: () => id === 'walk' ? (app.nav.walking ? app.nav.stopWalk() : app.nav.startWalk()) : app.setTool(id) }, icon));
    }
    tb.querySelector('[data-tool="measure"]').addEventListener('click', () => { if (app.activeTool === 'measure' && !this.isMobile()) this.openTab('tools'); });
    // 📝 = quick access to edit mode (Avihai 11.11): click an element -> all its data + write a correction note; again = exit.
    // A note at a free point stays in "בקרה ← הערות". The section tool is in "תצוגה ← חתך" (no toolbar button).
    tb.insertBefore(h('button', { 'data-k': 'edit', title: 'מצב עריכה: לחיצה על אלמנט – כל המידע + כתיבת הערה / תיקון (לחיצה נוספת – יציאה)', onclick: () => {
      const on = app.store.get().mode === 'edit'; app.store.set({ mode: on ? 'view' : 'edit' }, { label: 'mode' });
      if (!on) this.openTab('fixes', !this.isMobile());
    } }, '📝'), tb.querySelector('[data-tool="walk"]'));
    app.store.on((st) => document.querySelector('#toolbar [data-k="edit"]')?.classList.toggle('on', st.mode === 'edit'));
    // view buttons: in a group that folds behind ⋯ on a phone (review 13.11.2026 – nine 40 px buttons filled the screen height)
    const more = h('div', { class: 'tb-more' });
    tb.append(h('button', { 'data-k': 'more', title: 'עוד כלי תצוגה: מבט כללי, מבט על, תוכנית, מפה, תוויות', onclick: () => {
      const on = !document.body.classList.contains('tb-open'); document.body.classList.toggle('tb-open', on);
      tb.querySelector('[data-k="more"]').classList.toggle('on', on);
    } }, '⋯'), more);
    more.append(h('button', { title: 'מבט כללי', onclick: () => app.nav.goTo(app.nav.viewpoints()[0]) }, '⌂'));
    more.append(h('button', { title: 'מבט על', onclick: () => app.nav.goTo(app.nav.viewpoints()[1]) }, '⊙'));
    // plan view (Avihai 13.11.2026): straight down, no perspective – walls are lines, for furniture planning
    more.append(h('button', { 'data-k': 'plan', title: 'מבט תוכנית: ישר מלמעלה בזווית 90°, בלי פרספקטיבה, הקירות לאורך המסך (לחיצה נוספת – יציאה)', onclick: () => app.nav.planView() }, '▣'));
    const setMap = (on) => { const q = app.store.get().quality; app.store.set({ quality: { ...q, minimap: on } }, { label: 'minimap' }); };
    more.append(h('button', { 'data-k': 'minimap', title: 'מפה קטנה: הצגה / הסתרה', onclick: () => setMap(app.store.get().quality.minimap === false) }, '🗺'));
    // labels: of the current step -> all -> none
    more.append(h('button', { 'data-k': 'labels', title: 'תוויות: של השלב הנוכחי / כל התוויות / בלי', onclick: () => {
      const q = app.store.get().quality; const mode = !q.labels ? 'step' : (q.labelMode || 'step') === 'step' ? 'all' : 'off';
      app.store.set({ quality: { ...q, labels: mode !== 'off', labelMode: mode === 'off' ? (q.labelMode || 'step') : mode } }, { label: 'labels' });
      this.toast({ step: 'תוויות: רק של השלב הנוכחי (+ האלמנט שנבחר)', all: 'תוויות: הכול', off: 'בלי תוויות' }[mode]);
    } }, '🏷'));
    // a view button chosen on a phone folds the group again
    more.addEventListener('click', () => { if (this.isMobile?.()) { document.body.classList.remove('tb-open'); tb.querySelector('[data-k="more"]').classList.remove('on'); } });
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
      tg('track', '∥', 'מעקב', 'מעקב צירים: נקודה חופשית קרובה לציר (עד 3°) ננעלת עליו – אורך / רוחב / גובה'),
      h('button', { 'data-box': 1, title: 'מידות אלמנט: לחיצה על קיר / קורה / רצפה – אורך × רוחב × גובה בכיוון האלמנט (גם Shift+לחיצה)', onclick: () => { m().boxMode = !m().boxMode; this.syncMeasureBar(); } }, lb('📦', 'אלמנט')),
      h('div', { class: 'seg small', title: 'צירי הפירוק: כיוון האלמנט שנלחץ (קיר בכל זווית), צירי הבית או רשת ITM' },
        h('button', { 'data-ax': 'element', onclick: () => { m().setOpt('axes', 'element'); m().redraw(); } }, 'אלמנט'),
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
    this.measureBar.querySelector('[data-box]')?.classList.toggle('on', !!m.boxMode);
  }
  setActiveTool(id) { document.querySelectorAll('#toolbar [data-tool]').forEach(b => b.classList.toggle('on', b.dataset.tool === id)); this.syncMeasureBar(); }
  setWalkUI(on) {
    document.body.classList.toggle('walking', on);
    document.querySelector('#toolbar [data-tool="walk"]')?.classList.toggle('on', on);
    if (!this.walkSpeedBar) {
      const C = this.app.display.camera;
      this.walkSpeedBar = h('div', { id: 'walkspeed', class: 'seg small', title: 'מהירות הליכה (מקשים 1 / 2 / 3)' },
        (C.walkSpeeds_mps || []).map((v, i) => h('button', { 'data-i': i, onclick: () => this.app.nav.setSpeed(i) }, `${C.walkSpeedLabels?.[i] || i + 1}`)));
      // field of view: human / wide / very wide (the mouse wheel in between) – to see more of a narrow room from the same point
      this.walkSpeedBar.append(h('span', { class: 'wfov-sep' }, '👁'), ...(C.walkFovs_deg || []).map((f, i) => h('button', { 'data-fov': f, title: `זווית ראייה ${f}° (גלגלת – בין ${C.walkFovRange_deg?.join('° ל-')}°)`, onclick: () => this.app.nav.setWalkFov(f) }, C.walkFovLabels?.[i] || `${f}°`)),
        this.walkFovVal = h('small', { class: 'wfov-val' }));
      document.getElementById('viewport').append(this.walkSpeedBar);
    }
    this.syncWalkSpeed();
  }
  syncWalkSpeed() {
    const i = this.app.store.get().quality.walkSpeed ?? 1;
    this.walkSpeedBar?.querySelectorAll('button[data-i]').forEach(b => b.classList.toggle('on', +b.dataset.i === i));
    const f = this.app.nav?.walkFov?.();
    this.walkSpeedBar?.querySelectorAll('button[data-fov]').forEach(b => b.classList.toggle('on', +b.dataset.fov === f));
    if (this.walkFovVal && f != null) this.walkFovVal.textContent = `${f}°`;
  }

  // ---------------- side panel with tabs ----------------
  // Panel (Avihai 11.11): main button -> sub-topic -> its list. Tab ids are unchanged, so openTab('fixes' / 'sun' / 'tools' …)
  // keeps working from anywhere and selects the right main button.
  buildPanel() {
    const p = this.$('panel');
    this.sections = [
      { id: 'layers', icon: '▦', label: 'שכבות', tabs: [['layers', 'שכבות']] },
      { id: 'view', icon: '👁', label: 'תצוגה', tabs: [['floors', 'קומות'], ['sun', 'שמש וצל'], ['section', 'חתך'], ['nav', 'ניווט'], ['settings', 'הגדרות']] },
      { id: 'review', icon: '📋', label: 'בקרה', tabs: [['fixes', 'תיקונים לקלוד'], ['notes', 'הערות'], ['tools', 'מדידה'], ['rebar', 'ביקורת ברזל']] },
      { id: 'data', icon: '📊', label: 'נתונים', tabs: [['quantities', 'כמויות'], ['finishes', 'טיח, איטום וריצוף'], ['tiling', 'סדנת ריצוף'], ['electric', 'חשמל']] },
    ];
    // a panel_* added later and not placed above shows under "נתונים" (it never disappears)
    const placed = new Set(this.sections.flatMap(x => x.tabs.map(t => t[0])));
    for (const k of Object.getOwnPropertyNames(Object.getPrototypeOf(this))) if (k.startsWith('panel_') && !placed.has(k.slice(6))) this.sections[3].tabs.push([k.slice(6), k.slice(6)]);
    this.tabs = this.sections.flatMap(x => x.tabs);
    try { this.lastTab = JSON.parse(localStorage.getItem('panelTabs') || '{}'); } catch { this.lastTab = {}; }
    this.mainBar = h('nav', { class: 'mainbar' }, this.sections.map(x => h('button', { 'data-sec': x.id, title: x.tabs.map(t => t[1]).join(' · '),
      onclick: () => this.openTab(this.lastTab[x.id] && x.tabs.some(t => t[0] === this.lastTab[x.id]) ? this.lastTab[x.id] : x.tabs[0][0]) }, h('span', { class: 'i' }, x.icon), h('span', {}, x.label))));
    this.tabBar = h('nav', { class: 'tabs subtabs' });
    this.body = h('div', { class: 'panel-body' });
    this.wideBtn = h('button', { class: 'small', title: 'הרחבה / כיווץ של הפאנל', onclick: () => this.setPanel(this.panelOpen(), !document.body.classList.contains('panel-wide')) }, '⇤');
    const head = h('div', { class: 'panel-head' }, h('b', {}, 'פאנל'), this.wideBtn,
      h('button', { class: 'small', title: 'סגירת הפאנל', onclick: () => this.setPanel(false) }, '✕'));
    p.append(head, this.mainBar, this.tabBar, this.body);
    let saved = {}; try { saved = JSON.parse(localStorage.getItem('panelState') || '{}'); } catch {}
    this.isMobile = () => window.matchMedia('(max-width: 760px)').matches;
    this.setPanel(this.isMobile() ? false : saved.open !== false, !!saved.wide, false);
    this.openTab(this.tab, false);
  }
  sectionOf(id) { return this.sections.find(x => x.tabs.some(t => t[0] === id)) || this.sections[0]; }
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
    const sec = this.sectionOf(id);
    this.lastTab[sec.id] = id; try { localStorage.setItem('panelTabs', JSON.stringify(this.lastTab)); } catch {}
    this.mainBar.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.sec === sec.id));
    this.tabBar.replaceChildren(...(sec.tabs.length > 1 ? sec.tabs.map(([t, label]) => h('button', { 'data-tab': t, class: t === id ? 'on' : '', onclick: () => this.openTab(t) }, label)) : []));
    this.tabBar.classList.toggle('hidden', sec.tabs.length < 2);
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

  // Layers (Avihai 11.11): a button per domain; clicking it shows below it what is on / off in that domain, with the domain's
  // "all / none / only this" at the top of its list. Saved views on one row ("שמור תצוגה" = the view the model opens with).
  // A layer can be moved to "מוסתרות" or removed from this viewer's model (⋯); a layer added later is off and marked "חדש".
  panel_layers() {
    const { app } = this; const s = app.store.get(); const P = app.prefs;
    const colors = Object.fromEntries(app.data.tags.systems.map(x => [x.id, x.color]));
    const setLayers = (patch, label = 'layers') => app.store.set({ layers: { ...app.store.get().layers, ...patch } }, { label });
    const hidden = (id) => !!P?.hidden(id);
    // a layer that is on but shows nothing (Avihai 14.11.2026 – "דלוק ולא רואים"): why – its floor hidden, the construction
    // step slider before its step, or a system filter – and the patch that brings it back
    const blocked = (id, st = app.store.get()) => {
      const its = app.registry.items.filter(i => i.tags.layer === id); if (!its.length || its.some(i => i.object.visible)) return null;
      const why = [], patch = {};
      const fl = [...new Set(its.map(i => i.tags.floor))].filter(f => st.floors[f] && st.floors[f].visible === false);
      if (fl.length) { why.push('הקומה ' + fl.map(f => `"${app.data.tags.floors.find(x => x.id === f)?.label || f}"`).join(', ') + ' מוסתרת'); patch.floors = { ...st.floors, ...Object.fromEntries(fl.map(f => [f, { ...st.floors[f], visible: true }])) }; }
      const from = Math.min(...its.map(i => app.registry.range(i.tags)[0]));
      if (st.stageIndex < from) { why.push(`סרגל השלבים לפני שלב "${app.data.tags.sequence[from]?.label || ''}"`); patch.stageIndex = app.data.tags.sequence.length - 1; }
      if (st.systemFilter && !its.some(i => st.systemFilter.includes(i.tags.system))) { why.push('מסנן מערכות פעיל'); patch.systemFilter = null; }
      return why.length ? { why, patch } : null;
    };
    const implLayers = (g) => g.implemented ? g.layers.filter(l => l.implemented !== false && !hidden(l.id)) : [];
    const groups = app.data.layers.groups.filter(g => implLayers(g).length);
    const waiting = app.data.layers.groups.filter(g => !implLayers(g).length && !g.layers.every(l => hidden(l.id)));
    const binned = app.data.layers.groups.flatMap(g => g.layers.filter(l => P?.isBinned(l.id)).map(l => ({ l, g })));
    const wrap = h('div', { class: 'layers' });
    // ---- saved views: one row ----
    if (P) {
      const vs = P.list(); const cur = vs.find(v => v.id === P.current);
      const sel = h('select', { class: 'vsel', title: 'תצוגות שמורות', onchange: (e) => { if (e.target.value) { P.use(e.target.value); this.refreshPanel('layers'); } } },
        h('option', { value: '' }, vs.length ? '— בחר תצוגה —' : 'אין תצוגות שמורות'),
        vs.map(v => h('option', { value: v.id, selected: v.id === P.current }, (P.p.start === v.id ? '★ ' : '') + v.name)));
      const saveNew = async () => {
        const n = await askText('שם לתצוגה (תיפתח כך בכל כניסה)', cur ? '' : 'התצוגה שלי'); if (!n?.trim()) return;
        P.save(n.trim(), !!this.viewWithStage, true); this.toast(`"${n.trim()}" נשמרה – המודל ייפתח בה`); this.refreshPanel('layers');
      };
      wrap.append(h('div', { class: 'vbar' }, sel,
        h('button', { class: 'primary', title: 'שמירת השכבות המסומנות כתצוגה – היא לא תתאפס ותיפתח בכניסה הבאה', onclick: saveNew }, '💾 שמור תצוגה'),
        cur ? h('button', { title: `עדכון "${cur.name}" לפי הסימון הנוכחי`, onclick: () => { P.update(cur.id); this.toast(`"${cur.name}" עודכנה`); } }, '⟳ עדכן') : '',
        h('details', { class: 'vmore' }, h('summary', { title: 'ניהול תצוגות' }, '⋯'),
          h('div', { class: 'vmenu' },
            h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: !!this.viewWithStage, onchange: (e) => { this.viewWithStage = e.target.checked; } }), 'לשמור גם את שלב הבנייה'),
            cur ? h('button', { class: 'small' + (P.p.start === cur.id ? ' on' : ''), onclick: () => { P.setStart(cur.id); this.refreshPanel('layers'); } }, P.p.start === cur.id ? '★ נפתחת בכניסה – ביטול' : '★ לפתוח בכניסה') : '',
            cur ? h('button', { class: 'small', onclick: async () => { const n = await askText('שם חדש', cur.name); if (n?.trim()) { P.rename(cur.id, n.trim()); this.refreshPanel('layers'); } } }, '✎ שינוי שם') : '',
            cur ? h('button', { class: 'small x', onclick: async () => { if (await askConfirm(`למחוק את "${cur.name}"?`, { ok: 'מחק', danger: true })) { P.remove(cur.id); P.current = null; this.refreshPanel('layers'); } } }, '🗑 מחיקה') : '',
            h('div', { class: 'muted' }, P.where === 'db' ? 'נשמר בחשבון שלך – בכל מכשיר.' : 'נשמר בדפדפן הזה.')))));
    }
    // ---- domain buttons ----
    const ids = [...groups.map(g => g.id), ...(binned.length ? ['__bin'] : [])];
    if (!ids.includes(this.domain)) { try { this.domain = localStorage.getItem('layerDomain'); } catch {} }
    if (!ids.includes(this.domain)) this.domain = groups.find(g => g.id === 'structure')?.id || ids[0];
    const pick = (id) => { this.domain = id; try { localStorage.setItem('layerDomain', id); } catch {} this.refreshPanel('layers'); };
    wrap.append(h('div', { class: 'domains' }, groups.map(g => {
      const L = implLayers(g), n = L.filter(l => s.layers[l.id] !== false).length, fresh = L.some(l => P?.isNew(l.id));
      return h('button', { class: 'dom' + (g.id === this.domain ? ' cur' : '') + (n === 0 ? ' none' : n < L.length ? ' part' : ' all'), title: g.label, onclick: () => pick(g.id) },
        h('i', { class: 'sw', style: `background:${colors[g.system] || '#888'}` }), h('span', { class: 'dl' }, g.short || g.label.replace(/\s*\(שלב \d+\)/, '').replace(/\s*[–(].*$/, '')), h('small', {}, `${n}/${L.length}`), fresh ? h('b', { class: 'newdot', title: 'יש שכבה חדשה' }) : '');
    }), binned.length ? h('button', { class: 'dom bin' + (this.domain === '__bin' ? ' cur' : ''), onclick: () => pick('__bin') }, h('span', { class: 'dl' }, 'מוסתרות'), h('small', {}, `${binned.length}`)) : ''));
    // ---- the chosen domain: its layers ----
    const box = h('div', { class: 'dbody' });
    if (this.domain === '__bin') {
      box.append(h('p', { class: 'muted' }, 'שכבות שהוצאו מהרשימות. הן כבויות במודל. "החזר" מחזיר את השכבה לתחום שלה.'),
        ...binned.map(({ l, g }) => h('div', { class: 'row lrow' }, h('span', {}, l.label, h('small', { class: 'muted' }, ` · ${g.label}`)),
          h('button', { class: 'small', onclick: () => { P.unbin(l.id); this.refreshPanel('layers'); } }, 'החזר'))));
    } else {
      const g = groups.find(x => x.id === this.domain); const L = implLayers(g);
      const all = groups.flatMap(implLayers);
      box.append(h('div', { class: 'dhead' }, h('b', {}, g.label),
        h('div', { class: 'btns' },
          h('button', { class: 'small', onclick: () => setLayers(Object.fromEntries(L.map(l => [l.id, true])), 'group') }, '☑ סמן הכול'),
          h('button', { class: 'small', onclick: () => setLayers(Object.fromEntries(L.map(l => [l.id, false])), 'group') }, '☐ נקה הכול'),
          h('button', { class: 'small', title: 'רק התחום הזה דלוק, כל השאר כבויים', onclick: () => setLayers(Object.fromEntries(all.map(l => [l.id, L.includes(l)])), 'solo') }, '◎ רק התחום הזה'))));
      // domain controls (no quantities / prices here – those are in "נתונים")
      if (g.id === 'environment' && app.environment) box.append(app.environment.panel());
      const pl = app.modules?.plumbing;
      if (['plumbing', 'sewage', 'drainage'].includes(g.id)) box.append(h('div', { class: 'btns' },
        pl?.toggle ? h('button', { class: pl.isOn?.() ? 'on' : '', title: 'כל שכבות הצנרת דלוקות, קרקע שקופה, בלי שלד וסביבה (לחיצה נוספת – חזרה)', onclick: () => pl.toggle() }, pl.isOn?.() ? '↩ חזרה לתצוגה רגילה' : '🔧 הצג את כל הצנרת') : '',
        h('button', { class: s.showHidden ? 'on' : '', title: 'צנרת מתחת לרצפות ובתוך הקירות (בטון שקוף למחצה)', onclick: () => app.store.set({ showHidden: !s.showHidden }, { label: 'xray' }) }, s.showHidden ? '✓ צנרת מוסתרת' : 'צנרת מוסתרת')));
      if (g.id === 'plumbing' && pl?.panel) box.append(pl.panel());
      else if (g.id !== 'environment' && app.modules?.[g.id]?.panel && !['finishes'].includes(g.id)) box.append(app.modules[g.id].panel());
      if (app.proposals && g.layers.some(l => l.id === 'ownerChanges')) box.append(h('div', { class: 'btns' }, h('span', { class: 'muted' }, 'הצעות לשינוי:'),
        h('div', { class: 'ocseg' }, h('button', { class: s.proposals ? '' : 'on', onclick: () => app.proposals.setMode(false) }, 'מצב תוכנית'),
          h('button', { class: s.proposals ? 'on' : '', onclick: () => app.proposals.setMode(true) }, 'מצב הצעות')),
        h('button', { class: 'small', onclick: () => this.openTab('notes') }, 'רשימת השינויים')));
      if (['plaster', 'tilingInterior', 'tilingExterior', 'waterproofingGroup'].includes(g.id) && app.modules?.finishes?.controls) box.append(app.modules.finishes.controls(g.id));
      const blk = {};
      for (const l of L) {
        const on = s.layers[l.id] !== false; const lblOff = !!(s.labelsOff || {})[l.id]; const fresh = P?.isNew(l.id);
        box.append(h('div', { class: 'row lrow' + (on ? ' on' : '') },
          h('label', {}, h('input', { type: 'checkbox', checked: on, onchange: (e) => { P?.markSeen(l.id); setLayers({ [l.id]: e.target.checked }, 'layer');
            if (e.target.checked) { const b = blocked(l.id); if (b) { app.store.set(b.patch, { label: 'layer' }); this.toast(`"${l.label}" לא נראתה (${b.why.join('; ')}) – תוקן`); this.refreshPanel('layers'); } } } }), l.label,
            fresh ? h('b', { class: 'newtag', title: 'שכבה שנוספה אחרי התצוגה השמורה – כבויה עד שתסמן' }, 'חדש') : ''),
          h('button', { class: 'tagbtn' + (lblOff ? ' off' : ''), title: lblOff ? 'הצג תוויות וקווי סימון' : 'הסתר תוויות וקווי סימון (הרכיבים נשארים)',
            onclick: () => app.store.set({ labelsOff: { ...(s.labelsOff || {}), [l.id]: !lblOff } }, { label: 'labels' }) }, '🏷'),
          P ? h('details', { class: 'lmore' }, h('summary', { title: 'הוצאה מהרשימה / מהמודל' }, '⋯'),
            h('div', { class: 'lmenu' },
              h('button', { class: 'small', onclick: () => { P.bin(l.id); this.toast(`"${l.label}" הועברה ל"מוסתרות"`); this.refreshPanel('layers'); } }, 'העבר ל"מוסתרות"'),
              h('button', { class: 'small x', onclick: async () => { if (await askConfirm(`להסיר את "${l.label}" מהמודל שלך? (הנתונים לא נמחקים – אפשר להחזיר ב"תצוגה ← הגדרות")`, { ok: 'הסר', danger: true })) { P.drop(l.id); this.refreshPanel('layers'); } } }, 'הסר מהמודל'))) : ''));
        const bl = on ? blocked(l.id, s) : null;
        if (bl) { const k = bl.why.join('; '), e = (blk[k] ||= { why: k, patch: {}, names: [] }); e.names.push(l.label); Object.assign(e.patch, bl.patch); }
      }
      // one note per reason, above the list (not one per row)
      const notes = Object.values(blk).map(e => h('div', { class: 'warn lblocked' }, `⚠ ${e.names.length === 1 ? `"${e.names[0]}" דלוקה` : `${e.names.length} שכבות דלוקות`} אבל לא נראות: ${e.why}. `,
        h('button', { class: 'small primary', onclick: () => { app.store.set(e.patch, { label: 'layer' }); this.refreshPanel('layers'); } }, 'להציג')));
      if (notes.length) { const first = box.querySelector('.lrow'); notes.forEach(n => first ? box.insertBefore(n, first) : box.append(n)); }
      if (L.some(l => P?.isNew(l.id))) box.append(h('button', { class: 'small', onclick: () => { P.markSeen(L.map(l => l.id)); this.refreshPanel('layers'); } }, 'סמן כנקרא (בלי "חדש")'));
    }
    wrap.append(box);
    // ---- all domains ----
    wrap.append(h('div', { class: 'btns lfoot' },
      h('button', { class: 'small', onclick: () => setLayers(Object.fromEntries(groups.flatMap(implLayers).map(l => [l.id, true]))) }, 'הצג הכול'),
      h('button', { class: 'small', onclick: () => setLayers(Object.fromEntries(Object.keys(s.layers).map(k => [k, false]))) }, 'הסתר הכול'),
      h('button', { class: 'small', onclick: () => { const d = structuredClone(app.defaults.layers); for (const k in d) if (hidden(k)) d[k] = false; app.store.set({ layers: d }, { label: 'layers' }); } }, 'ברירת מחדל'),
      h('button', { class: 'small', title: 'הצגת התוויות של כל השכבות', onclick: () => app.store.set({ labelsOff: {} }, { label: 'labels' }) }, '🏷 כל התוויות')),
      waiting.length ? h('p', { class: 'muted' }, 'בהכנה (עוד אין נתונים): ' + waiting.map(g => g.label).join(', ')) : '');
    return wrap;
  }

  // "מגרש וסביבה" in the floors tab (Avihai 14.11.2026): the garden inside the lot and the street in front of the lot, each one
  // switch – on = its layers on, its floor shown and opaque (they looked see-through with no way back)
  siteParts(s) {
    const { app } = this;
    const parts = [
      { id: 'garden', label: 'גינה בתוך המגרש', note: 'מילוי, מצע ודשא סינטטי (OC-17)', on: ['gardenFill', 'gardenBase', 'gardenTurf'] },
      { id: 'front', label: 'רחוב מול המגרש בלבד', note: 'הרחוב בחזית בלבד – בלי שאר רחובות הסביבה', on: ['frontStreet'], off: ['street'] },
    ];
    const isOn = (p) => p.on.every(id => s.layers[id] !== false) && (p.off || []).every(id => s.layers[id] === false);
    const set = (p, v) => {
      const st = app.store.get(), layers = { ...st.layers, ...Object.fromEntries(p.on.map(id => [id, v])) };
      const patch = { layers };
      if (v) {
        for (const id of p.off || []) layers[id] = false;
        const fl = new Set(app.registry.items.filter(i => p.on.includes(i.tags.layer)).map(i => i.tags.floor));
        patch.floors = Object.fromEntries(Object.entries(st.floors).map(([k, x]) => [k, fl.has(k) ? { ...x, visible: true, opacity: 1 } : x]));
        if (st.stageIndex < app.data.tags.sequence.length - 1) patch.stageIndex = app.data.tags.sequence.length - 1;
      }
      app.store.set(patch, { label: 'siteParts' }); this.refreshPanel();
    };
    return h('div', { class: 'site-parts' }, parts.map(p => h('label', { class: 'row', 'data-part': p.id },
      h('input', { type: 'checkbox', checked: isOn(p), onchange: (e) => set(p, e.target.checked) }), p.label, h('small', { class: 'muted' }, ` – ${p.note}`))));
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
        f.id === 'site' ? this.siteParts(s) : '',
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
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: sec.fill !== false, onchange: (e) => app.store.set({ section: { ...sec, fill: e.target.checked } }, { label: 'section' }) }),
        'מילוי חתך – אלמנט חתוך נראה מלא, בצבע לפי סוג'),
      h('div', { class: 'cut-legend', style: 'flex-wrap: wrap' }, app.tools.section.legend().map(c => h('span', {}, h('i', { style: c.style }), h('small', {}, c.label)))),
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
    const kind = (k) => (({ vertex: '■', mid: '▲', edge: '◆', face: '●', box: '📦' })[k.split('+')[0]] || '') + (k.includes('ortho') ? '⊾' : k.includes('track') ? '∥' : '');
    return h('div', { class: 'measure-panel' },
      h('p', { class: 'muted' }, 'לוחצים על שתי נקודות. הסמן נצמד לפינה ■, לאמצע ▲ או לקצה ◆ (אחרת ● משטח); ליד הסמן מוצגים E / N / H, ואחרי הנקודה הראשונה – הפירוק לצירים. בצירי "אלמנט" הכיוון נלקח מהאלמנט שנלחץ ראשון – קיר בכל זווית נמדד לאורכו, והמידה מקבלת שם: ',
        h('b', { class: 'ax-x' }, n.x), ' · ', h('b', { class: 'ax-y' }, n.y), ' · ', h('b', { class: 'ax-z' }, n.z), '. 📦 (או Shift+לחיצה) – אורך × רוחב × גובה של אלמנט. אורתו (F8) – נעילה לציר. Esc – ביטול נקודה.'),
      h('div', { class: 'btns' },
        h('button', { class: on ? 'on' : 'primary', onclick: () => app.setTool(on ? 'inspect' : 'measure') }, on ? '✓ מודד – לחץ לסיום' : '📏 התחל מדידה'),
        h('button', { class: m.opts.snap ? 'on' : '', onclick: () => m.setOpt('snap', !m.opts.snap) }, '🧲 הצמדה'),
        h('button', { class: m.opts.ortho ? 'on' : '', onclick: () => m.setOpt('ortho', !m.opts.ortho) }, '⊾ אורתו'),
        h('button', { class: m.opts.track ? 'on' : '', onclick: () => m.setOpt('track', !m.opts.track) }, '∥ מעקב'),
        h('button', { class: m.boxMode ? 'on' : '', onclick: () => { m.boxMode = !m.boxMode; if (!on) app.setTool('measure'); else { this.syncMeasureBar(); this.refreshPanel('tools'); } } }, '📦 מידות אלמנט')),
      h('div', { class: 'btns' }, h('span', { class: 'muted' }, 'צירים:'),
        h('div', { class: 'seg small' },
          h('button', { class: m.opts.axes === 'element' ? 'on' : '', onclick: () => { m.setOpt('axes', 'element'); m.redraw(); } }, 'אלמנט'),
          h('button', { class: m.opts.axes === 'house' ? 'on' : '', onclick: () => { m.setOpt('axes', 'house'); m.redraw(); } }, 'צירי בית'),
          h('button', { class: m.opts.axes === 'itm' ? 'on' : '', onclick: () => { m.setOpt('axes', 'itm'); m.redraw(); } }, 'רשת ITM'))),
      h('p', { class: 'muted' }, m.axesText()),
      m.items.length ? h('table', { class: 'mtable' },
        h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'מידה'), h('th', {}, 'ישיר'), h('th', { class: 'ax-x' }, n.x), h('th', { class: 'ax-y' }, n.y), h('th', { class: 'ax-z' }, n.z), h('th', {}, ''))),
        h('tbody', {}, m.items.map((it, i) => h('tr', {},
          h('td', { title: `מ: ${kind(it.ka)}  עד: ${kind(it.kb)}` }, `${i + 1}`, h('small', {}, ` ${kind(it.ka)}${kind(it.kb)}`)),
          h('td', { title: it.box ? it.name : '' }, it.box ? '📦 תיבה' : it.what || 'ישיר'),
          h('td', { title: `אופקי ${it.dh.toFixed(3)}` }, it.box ? '' : h('b', {}, it.d3.toFixed(3))),
          ...(it.box ? [h('td', {}, h('b', {}, it.box.l.toFixed(3))), h('td', {}, h('b', {}, it.box.w.toFixed(3))), h('td', {}, h('b', {}, it.box.h.toFixed(3)))]
            : [h('td', {}, Math.abs(it.dx).toFixed(3)), h('td', {}, Math.abs(it.dy).toFixed(3)), h('td', {}, m.sgn(it.dz))]),
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
      h('button', { onclick: async () => { const name = await askText('שם למבט:', `מבט ${s.bookmarks.length + 1}`); if (name) app.store.set({ bookmarks: [...s.bookmarks, { name, ...app.currentView() }] }, { label: 'bm' }); } }, '＋ שמור מבט נוכחי'),
      h('h4', {}, 'הליכה'),
      h('p', { class: 'muted' }, 'הליכה בגובה עיניים על הרצפות, הפודסטים, המדרגות והקרקע (מה שמוצג בשלב הנוכחי), בלי לעבור דרך קירות. מתחילים בנקודה שבמרכז המסך. מחשב: חיצים/WASD, גרירה להסתכלות, 1/2/3 מהירות, Shift האצה. טלפון: ג׳ויסטיק וגרירה.'),
      h('div', { class: 'seg small' }, (app.display.camera.walkSpeeds_mps || []).map((v, i) => h('button', { class: (s.quality.walkSpeed ?? 1) === i ? 'on' : '', onclick: () => app.nav.setSpeed(i) },
        `${app.display.camera.walkSpeedLabels?.[i] || ''} ${v} מ'/ש'`))),
      h('button', { onclick: () => app.nav.walking ? app.nav.stopWalk() : app.nav.startWalk() }, app.nav.walking ? 'יציאה מהליכה' : '🚶 התחל הליכה'));
  }

  // the proposals layer: mode switch + the list of changes (name, note, status; click = jump to it) + the queries
  proposalsBox() {
    const { app } = this; const s = app.store.get(), P = app.proposals;
    if (!P) return '';
    const on = !!s.proposals;
    const box = h('div', { class: 'proposals' },
      h('h4', {}, 'הצעות לשינוי (הסימונים האדומים)'),
      h('div', { class: 'ocseg' },
        h('button', { class: on ? '' : 'on', onclick: () => P.setMode(false) }, 'מצב תוכנית'),
        h('button', { class: on ? 'on' : '', onclick: () => P.setMode(true) }, `מצב הצעות (${P.pending().length})`)),
      h('div', { class: 'muted' }, on ? 'מוצגים השינויים שממתינים לאדריכל – באדום. שינוי שאושר – חלק מהתוכנית, בלי אדום. שינוי שנדחה – לא מוצג.'
        : 'המודל לפי תוכנית האדריכל. השינויים הממתינים כבויים; שינוי שאושר כבר בתוכנית הבסיס.'));
    const row = (c) => {
      const st = P.status(c.id), applied = c.kind === 'applied', shown = s.proposalShow?.[c.id] !== false;
      const sel = h('select', { class: 'pstatus ' + st, disabled: applied, title: applied ? 'בוצע במודל באישור אביחי' : 'סטטוס מול האדריכל', onchange: (e) => P.setStatus(c.id, e.target.value) },
        Object.entries(STATUS_HE).map(([k, v]) => { const o = h('option', { value: k }, applied && k === 'approved' ? 'אושר (בוצע במודל)' : v); if (k === st) o.selected = true; return o; }));
      return h('div', { class: 'oc ' + st },
        h('a', { href: '#', class: 'ptitle', title: 'הצג במודל', onclick: (e) => { e.preventDefault(); P.go(c); } }, `${c.id} · ${c.title}`),
        h('div', { class: 'prow' }, sel,
          st === 'pending' && !applied ? h('label', { class: 'pshow', title: 'במצב הצעות: להציג את השינוי הזה' }, h('input', { type: 'checkbox', checked: shown,
            onchange: (e) => app.store.set({ proposalShow: { ...s.proposalShow, [c.id]: e.target.checked } }, { label: 'proposals' }) }), 'מוצג') : '',
          ...(c.targets?.length ? c.targets.map(t => h('button', { class: 'small', onclick: () => P.go(c, t) }, `הצג ${t.label}`)) : [h('button', { class: 'small', onclick: () => P.go(c) }, 'הצג')])),
        h('details', {}, h('summary', {}, 'הערה'), h('div', {}, c.description),
          c.changed ? h('div', {}, h('small', {}, 'מה השתנה: ' + c.changed)) : null,
          c.removedLabel || c.addedLabel ? h('div', { class: 'muted' }, `${c.removedLabel || ''} → ${c.addedLabel || ''}`) : null,
          h('small', {}, `${c.date} · מי צריך לאשר:`),
          h('ul', { class: 'appr' }, ...(c.approvals || []).map(a => h('li', {}, `${a.who}${a.what ? ' – ' + a.what : ''}${a.status === 'pending' ? '' : ' ✔'}`))),
          c.link ? h('div', {}, h('a', { href: c.link.url, target: '_blank', rel: 'noopener' }, c.link.label)) : null));
    };
    box.append(...P.list.map(row));
    const qs = (app.data.ownerChanges?.changes || []).filter(c => c.kind === 'query');
    if (qs.length) box.append(h('h4', {}, 'לבירור (לא בשכבת ההצעות)'), ...qs.map(c => h('div', { class: 'oc query' },
      h('a', { href: '#', class: 'ptitle', onclick: (e) => { e.preventDefault(); P.go(c); } }, `${c.id} · ${c.title}`), h('details', {}, h('summary', {}, 'הערה'), h('div', {}, c.description)))));
    box.append(h('div', { class: 'muted' }, P.where === 'db' ? 'הסטטוסים נשמרים במסד הארטיפקט – קלוד יסנכרן ל-owner-changes.json.' : 'הסטטוסים נשמרים בדפדפן הזה.'));
    return box;
  }

  panel_notes() {
    const { app } = this; const s = app.store.get();
    return h('div', {},
      h('p', { class: 'muted' }, 'הערות ושאלות לאדריכל / לקונסטרוקטור: לחיצה על רכיב במצב "הערה" פותחת חלון כתיבה. הוראות תיקון למודל – בלשונית "תיקונים לקלוד".'),
      h('div', { class: 'btns' },
        h('button', { class: app.activeTool === 'note' ? 'on' : '', onclick: () => app.setTool('note') }, '📝 הוסף הערה'),
        h('button', { onclick: () => this.copy(app.tools.notes.toText(), 'כל ההערות הועתקו') }, '📋 העתק את כל ההערות')),
      this.proposalsBox(),
      h('h4', {}, 'הערות ותיקונים'),
      s.notes.length ? h('ol', { class: 'notes' }, s.notes.map((n, i) => h('li', { class: n.done ? 'done' : '' },
        h('div', {}, n.text), h('small', {}, `${n.component || '—'} · ${app.coords.fmtH(n.H)}`),
        h('div', { class: 'btns' },
          h('button', { class: 'small', onclick: () => app.flyToPoint(n) }, 'הצג'),
          h('button', { class: 'small', onclick: () => app.store.set({ notes: s.notes.map((x, j) => j === i ? { ...x, done: !x.done } : x) }, { label: 'note' }) }, n.done ? 'פתח מחדש' : 'סמן כבוצע'),
          h('button', { class: 'small', onclick: async () => { const t = await askText('עריכת הערה:', n.text); if (t != null) app.store.set({ notes: s.notes.map((x, j) => j === i ? { ...x, text: t } : x) }, { label: 'note' }); } }, 'ערוך'),
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
          h('button', { class: 'small', onclick: async () => { const t = await askText('עריכת התיקון:', n.text); if (t != null && t.trim()) T.patch(n.id, { text: t.trim() }); } }, 'ערוך'),
          h('button', { class: 'small x', onclick: async () => { if (await askConfirm('למחוק את התיקון?', { ok: 'מחק', danger: true })) T.remove(n.id); } }, 'מחק'))))) : h('p', { class: 'muted' }, 'אין תיקונים עדיין.'));
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
            tr('סה"כ להזמנה', `${Math.round(q.blocks.area_m2 / face * (1 + W / 100))} בלוקים (${q.blocks.area_m2.toFixed(1)} מ"ר + ${W}% פחת; לפי הפריסה בפועל – באקסל)`)]; })(),
        tr('טיט מלט – נדבך ראשון', `${Math.round(q.blocks.mortar_l || 0)} ליטר נטו (${Math.round((app.data.blocksCfg?.bonding?.firstCourse?.calc_m || 0) * 100)} ס"מ)`),
        tr('דבק בלוקים – שכבה דקה', `${Math.round(q.blocks.adhesive_l || 0)} ליטר נטו (${Math.round((app.data.blocksCfg?.bonding?.adhesive?.calc_m || 0) * 1000)} מ"מ; פירוט ושקים באקסל)`),
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
            h('button', { class: 'small', onclick: async () => { const t = await askText('הערת ביקורת:', c.note || ''); if (t != null) T.setCheck(key, { note: t.trim(), element: item.meta.id || '', name: item.meta.name || '', step: seq[i]?.id }); } }, 'הערה'),
            h('button', { class: 'small', onclick: () => app.tools.search.show(item) }, 'הצג')));
      })) : h('p', { class: 'muted' }, 'אין בשלב הזה אלמנטים עם נתוני ברזל (חפירה, מילוי, צנרת, פיתוח – או שהאלמנטים עוד בלי גיליון ברזל).'),
      h('div', { class: 'btns' }, h('button', { onclick: () => this.copy(list.map(({ item, info, key }) => `${T.checks[key]?.ok ? '✓' : '☐'} ${item.meta.id || ''} ${item.meta.name || ''}\n` + info.map(([k, v]) => `   ${k}: ${v}`).join('\n') + (T.checks[key]?.note ? `\n   הערה: ${T.checks[key].note}` : '')).join('\n'), 'רשימת הביקורת הועתקה') }, '📋 העתק רשימה')));
  }

  panel_tiling() { return this.app.modules?.finishes?.tiling?.panel(this) || h('div', { class: 'muted' }, 'אין נתוני ריצוף'); }
  panel_finishes() { return this.app.modules?.finishes?.panel(this) || h('div', { class: 'muted' }, 'אין נתוני גמרים'); }
  panel_electric() {
    const { app } = this; const el = app.data.tools.electrical;
    const S = app.data.electricalSupply, ED = app.data.electricalDisplay, E = app.modules.electrical;
    const goStep = (st) => {   // construction step of the supply + only the systems that matter for it, then frame the feeder
      const cur = app.store.get();   // ground and concrete see-through (the conduits are buried / cast in)
      app.store.set({ stageIndex: app.registry.stepById(st.step), systemFilter: ED.stepFilter, layers: { ...cur.layers, elSupply: true }, plumbing: { ...(cur.plumbing || {}), xray: true }, showHidden: true }, { label: 'elStep' });
      const it = E?.items.find(i => i.meta.kind === 'elFeeder'); if (it) app.tools.search.show(it);
    };
    const supply = S ? h('div', {},
      h('h4', {}, `ח1 – חיבור מהפילר ללוח הראשי (${S.approval ? 'אושר ' + S.approval.date.split('-').reverse().join('.') : 'הצעה'})`),
      h('table', { class: 'kv' }, tr('גודל חיבור', `${S.connection.size} – ${S.connection.note}`), tr('כבל', S.feeder.cable.type),
        tr('צנרת', S.feeder.conduits.map(c => `ø${c.D_mm} ${c.role}`).join(' + ')), tr('אורך', `${S.feeder.length_m.toFixed(1)} מ'`),
        ...S.feeder.pulls.map(p => tr(`משיכה: ${p.name}`, `${p.length_m.toFixed(1)} מ' · ${p.bends_deg}°`)),
        tr('תא משיכה', `${S.pullPit.id} – ${S.pullPit.location}, עומק ${S.pullPit.depth_m.toFixed(2)} מ'`),
        tr('בדיקות', `${S.summary.checks} · נכשלו ${S.summary.failed}`)),
      h('p', { class: 'muted' }, 'שלב אחר שלב – לחיצה מעבירה את המודל לשלב הבנייה:'),
      h('div', { class: 'list' }, S.steps.map(st => h('button', { class: 'li', title: st.text, onclick: () => goStep(st) }, `${st.n}. ${st.title}`))),
      h('div', { class: 'btns' }, h('button', { class: 'small', onclick: () => app.store.set({ systemFilter: null }, { label: 'all' }) }, 'הצג את כל המערכות'))) : null;
    const UN = app.data.electricalUnits;
    const units = UN ? h('div', {},
      h('h4', {}, 'ח1ב – לוח לכל יחידת דיור (הצעה)'),
      h('table', { class: 'kv' }, ...UN.units.map(u => tr(`${u.panel.id} · ${u.name}`, `ליד ${u.door} · ${u.feeder.protection} · ${u.feeder.length_m.toFixed(1)} מ'${u.warning ? ' · ⚠' : ''}`)),
        tr('מוני משנה', `${UN.subMeter.count} × ${UN.subMeter.type} – ${UN.subMeter.where}`), tr('בדיקות', `${UN.summary.checks} · נכשלו ${UN.summary.failed}`)),
      h('div', { class: 'list' }, UN.units.map(u => h('button', { class: 'li', onclick: () => {
        const cur = app.store.get(); app.store.set({ stageIndex: app.registry.stepById('finishes'), systemFilter: ED.stepFilter, layers: { ...cur.layers, elSupply: true }, plumbing: { ...(cur.plumbing || {}), xray: true }, showHidden: true }, { label: 'elUnit' });
        const it = E?.items.find(i => i.meta.id === u.panel.id); if (it) app.tools.search.show(it); } }, `הצג את ${u.panel.id}`)))) : null;
    return h('div', {}, supply, units,
      h('h4', {}, 'נקודות חשמל ', soon()),
      h('p', { class: 'muted' }, 'הצבת שקעים, מפסקים, נקודות תאורה ותקשורת לפי גבהים סטנדרטיים, עם כתב כמויות נקודות.'),
      h('div', { class: 'list' }, el.pointTypes.map(p => h('button', { class: 'li na', disabled: true }, p.label))),
      h('p', { class: 'muted' }, el.note),
      h('h4', {}, 'כתב כמויות נקודות'), h('table', { class: 'kv' }, el.pointTypes.map(p => tr(p.label, '0'))));
  }

  panel_settings() {
    const { app } = this; const s = app.store.get();
    const q = s.quality; const P = app.prefs;
    const dropped = P ? app.data.layers.groups.flatMap(g => g.layers.filter(l => P.isDropped(l.id))) : [];
    return h('div', {},
      dropped.length ? h('div', { class: 'views' }, h('h4', {}, 'שכבות שהוסרו מהמודל שלך'),
        ...dropped.map(l => h('div', { class: 'row lrow' }, h('span', {}, l.label), h('button', { class: 'small', onclick: () => { P.undrop(l.id); this.refreshPanel('settings'); } }, 'החזר למודל')))) : '',
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: q.ao, onchange: (e) => app.store.set({ quality: { ...q, ao: e.target.checked } }, { label: 'q' }) }), 'Ambient Occlusion'),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: q.shadows, onchange: (e) => app.store.set({ quality: { ...q, shadows: e.target.checked } }, { label: 'q' }) }), 'צללים'),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: q.labels, onchange: (e) => app.store.set({ quality: { ...q, labels: e.target.checked } }, { label: 'q' }) }), 'תוויות'),
      h('div', { class: 'seg small' },
        h('button', { class: (q.labelMode || 'step') === 'step' ? 'on' : '', onclick: () => app.store.set({ quality: { ...q, labels: true, labelMode: 'step' } }, { label: 'q' }) }, 'תוויות השלב הנוכחי'),
        h('button', { class: q.labelMode === 'all' ? 'on' : '', onclick: () => app.store.set({ quality: { ...q, labels: true, labelMode: 'all' } }, { label: 'q' }) }, 'כל התוויות')),
      h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: q.minimap !== false, onchange: (e) => app.store.set({ quality: { ...q, minimap: e.target.checked } }, { label: 'q' }) }), 'מפה קטנה'),
      h('label', { class: 'col' }, `חשיפה: ${q.exposure.toFixed(2)}`, h('input', { type: 'range', min: 0.4, max: 1.8, step: 0.05, value: q.exposure, oninput: (e) => app.store.setCoalesced('exp', { quality: { ...app.store.get().quality, exposure: +e.target.value } }) })),
      h('div', { class: 'btns' },
        h('button', { onclick: async () => { if (await askConfirm('לאפס את כל ההגדרות (כולל הערות ומבטים שמורים)?', { ok: 'איפוס', danger: true })) app.store.reset(); } }, 'איפוס הגדרות')),
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
      h('div', { class: 'stg-track' }, this.stageRange, ticks),
      this.buildCutRow());
    bar.querySelector('.stg-head .btns').prepend(this.cutBtn);
    this.syncStageBar();
  }
  // "גובה קיר" (Avihai 13.11.2026): horizontal cut of one floor, from sectionCut.wallCut.min_m above the floor finish up to the
  // full height of its walls – the walls are shown solid from above (section fill, js/tools/section.js), coloured by kind
  buildCutRow() {
    const { app } = this; const ST = app.tools.section; const W = ST.C.wallCut || {};
    const setCut = (f, hRel) => {
      const fl = ST.wallFloors().find(x => x.id === f); if (!fl) return;
      const top = fl.top - fl.level;
      const hh = Math.max(W.min_m, Math.min(top, hRel));
      // at full height the plane sits 1 mm under the wall tops: the ceiling slab above is cut away, the walls show their fill
      const lvl = hh >= top ? fl.top - 0.001 : fl.level + hh;
      app.store.setCoalesced('wallCut', { section: { ...app.store.get().section, hOn: true, hideBeams: true, wFloor: f, hLevel: +lvl.toFixed(3) } });
    };
    this.cutFloorSel = h('select', { class: 'cut-sel', title: 'הקומה החתוכה', onchange: (e) => setCut(e.target.value, +this.cutRange.value) });
    this.cutRange = h('input', { type: 'range', step: W.step_m, oninput: (e) => setCut(this.cutFloorSel.value, +e.target.value) });
    this.cutVal = h('b', { class: 'cut-val' });
    this.cutBtn = h('button', { class: 'small cut-btn', title: 'חתך אופקי של קומה – קירות מלאים מלמעלה, גובה הקיר מ-20 ס"מ מעל הריצוף ועד הגובה המלא', onclick: () => {
      const sec = app.store.get().section;
      if (sec.hOn) { app.store.set({ section: { ...sec, hOn: false } }, { label: 'wallCut' }); return; }
      const f = (ST.floorAt(sec.hLevel) || ST.wallFloors().find(x => x.id === 'ground'))?.id;
      const fl = ST.wallFloors().find(x => x.id === f); if (fl) setCut(f, fl.top - fl.level);
    } }, '✂ גובה קיר');
    const legend = h('span', { class: 'cut-legend' }, ST.legend().map(c => h('span', { title: c.label }, h('i', { style: c.style }), h('small', {}, c.label))));
    // six fixed states (Avihai 13.11.2026): 10 / 40 / 120 cm, lintel band, dropped ceiling, full height
    const goPreset = (p) => {
      const f = this.cutFloorSel.value, lvl = ST.presetLevel(f, p); if (lvl == null) return;
      app.store.set({ section: { ...app.store.get().section, hOn: true, hideBeams: true, wFloor: f, hLevel: +lvl.toFixed(3) } }, { label: 'wallCut' });
    };
    this.cutPresets = (W.presets || []).map(p => { const b = h('button', { class: 'small cut-pre', onclick: () => goPreset(p) }, p.label); b._p = p; return b; });
    // the dropped-ceiling height of the cut floor – provisional, changed here (finishes module, state.dropCeiling)
    this.dropInp = h('input', { type: 'number', step: 0.01, class: 'cut-drop', title: 'גובה הנמכת התקרה (זמני) – יחסית ל-±0.00', onchange: (e) => app.modules.finishes?.setDrop(this.cutFloorSel.value, +e.target.value) });
    this.dropBox = h('label', { class: 'cut-dropbox', title: 'הנמכת תקרה – זמני, אין גובה בתוכניות' }, '⚠ הנמכה', this.dropInp);
    // black plan (Avihai 13.11.2026): every fill black – an architect's plan, pleasant from above for furniture planning
    this.monoBtn = h('button', { class: 'small cut-mono', title: 'תוכנית בשחור: כל המילויים בשחור (לתכנון ריהוט) – לחיצה נוספת: צבעים לפי סוג', onclick: () => {
      const sec = app.store.get().section; app.store.set({ section: { ...sec, mono: !sec.mono } }, { label: 'mono' }); } }, ST.C.mono?.label || '◼');
    this.cutRow = h('div', { class: 'stg-cut' }, this.cutFloorSel, h('span', { class: 'cut-pres' }, this.cutPresets), this.cutRange, this.cutVal, this.dropBox, this.monoBtn, legend);
    return this.cutRow;
  }
  syncCutRow() {
    const { app } = this; const ST = app.tools.section; const sec = app.store.get().section;
    const on = !!sec.hOn;
    this.cutBtn.classList.toggle('on', on);
    this.cutRow.classList.toggle('hidden', !on);
    this.monoBtn.classList.toggle('on', !!sec.mono); this.cutRow.classList.toggle('mono', !!sec.mono);
    if (document.body.classList.contains('cutrow') !== on) { document.body.classList.toggle('cutrow', on); app.viewer.resize(); }
    if (!on) return;
    const fls = ST.wallFloors();
    const fl = fls.find(x => x.id === sec.wFloor && sec.hLevel >= x.level - 1e-6 && sec.hLevel <= x.top + 1e-6) || ST.floorAt(sec.hLevel);
    if (!fl) return;
    if (this.cutFloorSel.options.length !== fls.length) this.cutFloorSel.replaceChildren(...fls.map(f => h('option', { value: f.id }, f.label)));
    this.cutFloorSel.value = fl.id;
    const top = +(fl.top - fl.level).toFixed(3); const hRel = sec.hLevel - fl.level;
    this.cutRange.min = this.app.tools.section.C.wallCut.min_m; this.cutRange.max = top;
    this.cutRange.value = Math.min(top, hRel);
    const full = hRel >= top - 0.002;
    for (const b of this.cutPresets) { const l = ST.presetLevel(fl.id, b._p); b.disabled = l == null; b.classList.toggle('on', l != null && Math.abs(l - sec.hLevel) < 0.002);
      if (l != null) b.title = `${b._p.id === 'drop' ? 'הנמכת תקרה (זמני)' : b._p.id === 'lintel' ? 'אמצע רצועת המשקופים' : b._p.id === 'full' ? 'גובה מלא – תחתית התקרה' : b._p.label + ' ס"מ מעל הריצוף'} · ${Math.round((l - fl.level) * 100)} ס"מ מעל הריצוף (${app.coords.fmtRel(l)})`; }
    const dh = app.modules.finishes?.dropHeight?.(fl.id);
    this.dropBox.classList.toggle('hidden', dh == null);
    if (dh != null && document.activeElement !== this.dropInp) this.dropInp.value = dh.toFixed(2);
    this.cutVal.textContent = full ? `מלא · ${top.toFixed(2)} מ'` : hRel < 0 || hRel > top ? app.coords.fmtRel(sec.hLevel) : `${Math.round(hRel * 100)} ס"מ מעל הריצוף`;
  }
  syncStageBar() {
    const s = this.app.store.get(); const st = this.app.data.tags.sequence;
    this.stageRange.value = s.stageIndex;
    this.stageSel.value = s.stageIndex;
    this.stageSel.title = (st[s.stageIndex]?.hint || '') + (s.systemFilter ? ' · רק שלד' : '');
    this.stageSel.classList.toggle('skel', !!s.systemFilter);
    this.syncCutRow();
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
      info.source ? h('div', { class: 'src' }, 'מקור: ', info.source) : '',
      info.extra || '');
    el.classList.remove('hidden');
  }
  showInfoFor(item) { this.app.tools.inspect?.showFor(item); }
  // the hint fades by itself (display.json ui.hintFade_ms) – a new hint (a step, a measured point) shows it again
  hint(text) {
    const el = this.$('hint'); el.textContent = text; el.classList.toggle('hidden', !text);
    clearTimeout(this._hintFade); const ms = this.app.display.ui?.hintFade_ms ?? 7000;
    if (text && ms > 0) this._hintFade = setTimeout(() => el.classList.add('hidden'), ms);
  }
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

// Controls of the "אינסטלציה – תוכנית היועץ" group in the layers panel: floor filter, x-ray, findings list.
// State is kept in the app store (key "plumbing") so it is saved, exported and undoable.
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};

export function buildPanel(app, pl) {
  const D = app.data.plumbingDisplay, N = pl.network;
  const st = () => app.store.get().plumbing || {};
  const set = (patch, label = 'plumbing') => app.store.set({ plumbing: { ...st(), ...patch } }, { label });
  const flyTo = (it) => {
    const f = it.meta.finding; const p = app.coords.toLocal(f.at[0], f.at[1], f.at[2]);
    app.viewer.flyTo(p, p.clone().add({ x: 4, y: 3.5, z: 4 }));
    app.ui.showInfo({ title: it.meta.name, rows: it.meta.rows, tags: it.tags, source: it.meta.source, note: it.meta.note });
  };
  // one click: every pipe visible – plumbing layers + proposal on, x-ray, structure / surroundings off, overview camera
  // the orange button toggles: pipe view <-> the view it replaced (Avihai 08.11: "the model is gone")
  let before = null;
  const restore = () => {
    if (!before) return;
    app.store.set({ ...before }, { label: 'אינסטלציה – חזרה לתצוגה הקודמת' }); before = null; sync();
  };
  const pipeView = () => {
    const cur = app.store.get(), L = { ...cur.layers };
    before = { layers: structuredClone(cur.layers), labelsOff: structuredClone(cur.labelsOff || {}), plumbing: structuredClone(cur.plumbing || {}) };
    for (const g of app.data.layers.groups) for (const l of g.layers) {
      if (g.id === 'plumbing') L[l.id] = l.id !== 'plFindings';
      else if (g.id === 'site') L[l.id] = ['topoPlanned', 'plotBoundary'].includes(l.id);
      else L[l.id] = false;
    }
    const lo = { ...(cur.labelsOff || {}) }; for (const id of ['plSewage', 'plCold', 'plRain', 'plPumped', 'plHot', 'plProposal', 'plChambers', 'plotBoundary']) lo[id] = true;
    app.store.set({ layers: L, labelsOff: lo, plumbing: { ...st(), xray: true, proposal: true, floors: {} } }, { label: 'אינסטלציה – הצג את כל הצנרת' });
    const c = app.plotCenter.clone(); app.viewer.flyTo(c, c.clone().add({ x: D.view.camOffset_m[0], y: D.view.camOffset_m[1], z: D.view.camOffset_m[2] }));
    sync();
  };
  const fab = document.createElement('button');
  fab.className = 'pl-fab';
  const sync = () => {
    fab.textContent = before ? '↺ חזרה למודל' : '🔧 הצג את כל הצנרת';
    fab.title = before ? 'מחזיר את השכבות שהיו לפני תצוגת הצנרת' : 'מדליק את כל שכבות האינסטלציה וההצעה, קרקע שקופה, מסתיר שלד וסביבה (לחיצה נוספת מחזירה)';
  };
  sync();
  fab.addEventListener('click', () => (before ? restore() : pipeView()));
  (document.getElementById('viewport') || document.body).append(fab);
  return {
    pipeView,
    panel() {
      const s = st(); const floors = s.floors || {}; const sev = s.severity || {};
      const S = N.summary.findings;
      const ids = app.data.layers.groups.find(g => g.id === 'plumbing').layers.map(l => l.id);
      const layers = app.store.get().layers;
      const anyOn = ids.some(id => layers[id] !== false);
      const box = h('div', { class: 'plbox' },
        h('button', { class: 'pl-all', onclick: pipeView }, '🔧 הצג את כל הצנרת (רנטגן, בלי שלד וסביבה)'),
        h('a', { class: 'pl-editor', href: 'editor.html', title: 'עורך צנרת דו-ממדי במבט על – אותם נתונים (data/plumbing/routes.json)' }, '✏️ עורך צנרת דו-ממדי (מבט על)'),
        h('label', { class: 'plmaster' }, h('input', { type: 'checkbox', checked: anyOn,
          onchange: (e) => app.store.set({ layers: { ...app.store.get().layers, ...Object.fromEntries(ids.map(id => [id, e.target.checked])) } }, { label: 'plumbing' }) }),
          anyOn ? 'שכבת האינסטלציה מוצגת – לחיצה מכבה את כולה' : 'שכבת האינסטלציה כבויה – לחיצה מדליקה את כולה'),
        h('p', { class: 'muted' }, `${N.summary.runs} קטעי צנרת · ${pl.totalLen.toFixed(0)} מ' · ${N.summary.nodes} צמתים. `,
          'צינור עם גוון כתום = מפלס זמני (לא כתוב בתוכנית); נקודה אדומה = סוף תכנון / קצה פתוח. לחיצה על רכיב מציגה סוג, קוטר, חומר, מפלסים, שיפוע ומאיפה לאן.'),
        pl.proposal ? h('div', { class: 'row plprop' }, h('b', {}, 'תצוגה: '),
          h('label', {}, h('input', { type: 'radio', name: 'plprop', checked: !s.proposal, onchange: () => set({ proposal: false }) }), 'לפי היועץ'),
          h('label', {}, h('input', { type: 'radio', name: 'plprop', checked: !!s.proposal, onchange: () => { set({ proposal: true }); app.store.set({ layers: { ...app.store.get().layers, plProposal: true } }, { label: 'plumbing' }); } }),
            `עם ההצעה (${pl.proposal.summary.stacksMoved} קולטנים, ${pl.proposal.summary.points} נקודות, ${pl.proposal.summary.sleeves} מעברים${pl.proposal.summary.site ? `; פיתוח: ${pl.proposal.summary.site.chambers} מכסים, ${pl.proposal.summary.site.drops} מפלים, גלגלון, חיבור מונה` : ''})`)) : null,
        pl.proposal && app.data.plumbingProposal?.rain ? h('div', { class: 'row plprop' }, h('b', {}, 'מי גשם (להשוואה): '),
          ...app.data.plumbingProposal.rain.alternatives.map(a => h('label', { title: a.facts.join(' · ') }, h('input', { type: 'radio', name: 'plrain', checked: (s.rainAlt || 1) === a.id,
            onchange: () => { set({ rainAlt: a.id, proposal: true }); app.store.set({ layers: { ...app.store.get().layers, plProposal: true } }, { label: 'plumbing' }); } }),
            `${a.id} – ${a.title.split('–')[1].trim()} (${a.length_m.toFixed(0)} מ')`))) : null,
        h('div', { class: 'row plfl' }, h('b', {}, 'קומות: '), ...Object.entries(D.floors).map(([id, lbl]) =>
          h('label', {}, h('input', { type: 'checkbox', checked: floors[id] !== false, onchange: (e) => set({ floors: { ...floors, [id]: e.target.checked } }) }), lbl))),
        h('div', { class: 'btns' },
          h('button', { class: s.xray ? 'on' : '', onclick: () => set({ xray: !s.xray }) }, s.xray ? '✓ רנטגן: קרקע שקופה' : 'רנטגן: קרקע שקופה'),
          h('button', { onclick: () => { const c = app.plotCenter.clone(); app.viewer.flyTo(c, c.clone().add({ x: D.view.camOffset_m[0], y: D.view.camOffset_m[1], z: D.view.camOffset_m[2] })); } }, 'מבט על האינסטלציה')),
        h('div', { class: 'row plsev' }, h('b', {}, 'ממצאים: '), ...Object.entries(D.severity).map(([id, v]) =>
          h('label', { style: `--c:${v.color}` }, h('input', { type: 'checkbox', checked: sev[id] !== false, onchange: (e) => set({ severity: { ...sev, [id]: e.target.checked } }) }), `${v.label} (${S[id] || 0})`))),
        h('details', { class: 'plfind' }, h('summary', {}, `רשימת הממצאים (${N.findings.length}) – לחיצה מעבירה לממצא`),
          h('ol', {}, ...pl.findingItems.filter(it => sev[it.meta.plSeverity] !== false).map(it =>
            h('li', { class: `sev-${it.meta.plSeverity}`, onclick: () => flyTo(it) }, it.meta.name)))),
      );
      return box;
    },
  };
}

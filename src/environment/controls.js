import { overviewView } from './index.js';

// Controls of the "סביבה" group in the layers panel: show/hide neighbours, envelope transparency,
// overview camera. State is kept in the app store (key "environment") so it is saved, exported and undoable.
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

const NEIGHBOUR_LAYERS = ['neighborBuildingLines', 'neighborLabels', 'neighborFences', 'neighborYards'];
const VOL = ['neighborHouses', 'neighborEnvelopes', 'neighborSheet04', 'neighborParking', 'neighborEntrances'];
const MODES = [
  ['detail', 'מפורט', { neighborHouses: true, neighborEnvelopes: false, neighborSheet04: false, neighborParking: false, neighborEntrances: false }],
  ['envelope', 'מעטפות מקס\'', { neighborHouses: false, neighborEnvelopes: true, neighborSheet04: false, neighborParking: true, neighborEntrances: true }],
  ['sheet04', 'גיליון 04', { neighborHouses: false, neighborEnvelopes: false, neighborSheet04: true, neighborParking: true, neighborEntrances: true }],
  ['both', 'מפורט + מעטפות', { neighborHouses: true, neighborEnvelopes: true, neighborSheet04: false, neighborParking: false, neighborEntrances: false }],
];

export function buildControls(app, env) {
  const D = app.data.envDisplay;
  const [lo, hi] = D.envelopeOpacityRange;
  const opacity = () => app.store.get().environment?.envelopeOpacity ?? D.envelopeDefaultOpacity;

  const applyOpacity = () => {
    const op = Math.min(hi, Math.max(lo, opacity()));
    const floor = app.store.get().floors?.site?.opacity ?? 1;
    for (const { material } of env.volumes) {
      material.userData.baseOpacity = op;
      material.userData.baseTransparent = op < 0.999;
      material.opacity = op * floor;
      material.transparent = material.opacity < 0.999;
      material.depthWrite = !material.transparent;
      material.needsUpdate = true;
    }
    const ghost = !!app.store.get().environment?.housesGhost;
    for (const m of env.details?.houseMaterials || []) {
      m.userData.baseOpacity = ghost ? 0.35 : 1; m.userData.baseTransparent = ghost;
      m.opacity = (ghost ? 0.35 : 1) * floor; m.transparent = m.opacity < 0.999; m.depthWrite = !m.transparent; m.needsUpdate = true;
    }
    app.viewer.invalidate();
  };
  app.store.on(applyOpacity);
  applyOpacity();

  return {
    panel() {
      const s = app.store.get();
      const on = NEIGHBOUR_LAYERS.every(id => s.layers[id] !== false) && VOL.some(id => s.layers[id] === true);
      const mode = (MODES.find(([, , l]) => Object.entries(l).every(([k, v]) => (s.layers[k] === true) === v)) || [])[0];
      const pct = Math.round(opacity() * 100);
      const wrap = h('div', { class: 'env-ctl' });
      wrap.append(
        h('label', { class: 'row env-main' },
          h('input', { type: 'checkbox', checked: on, onchange: (e) => {
            const layers = { ...s.layers }; for (const id of NEIGHBOUR_LAYERS) layers[id] = e.target.checked;
            if (e.target.checked) { if (!VOL.some(id => layers[id] === true)) Object.assign(layers, MODES[0][2]); }
            else for (const id of VOL) layers[id] = false;
            app.store.set({ layers }, { label: 'neighbours' });
          } }), 'הצג שכנים (בתים, חניות, קווי בניין, תוויות)'),
        h('div', { class: 'env-seg', role: 'group', 'aria-label': 'מה להציג לשכנים' }, MODES.map(([id, lbl, l]) =>
          h('button', { class: mode === id ? 'on' : '', onclick: () => app.store.set({ layers: { ...app.store.get().layers, ...l } }, { label: 'neighbour mode' }) }, lbl))),
        h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: !!app.store.get().environment?.housesGhost,
          onchange: (e) => app.store.set({ environment: { ...(app.store.get().environment || {}), housesGhost: e.target.checked } }, { label: 'houses ghost' }) }), 'בתים מפורטים שקופים (לראות צל)'),
        h('label', { class: 'row env-slider' }, `שקיפות מעטפות: ${100 - pct}%`,
          h('input', { type: 'range', min: Math.round(lo * 100), max: Math.round(hi * 100), step: 5, value: pct,
            title: 'אטימות המעטפות. הצל שהמעטפות מטילות נשאר מלא בכל ערך – כך רואים את הצל על המגרש דרך המעטפה',
            oninput: (e) => app.store.setCoalesced('envOpacity', { environment: { ...(app.store.get().environment || {}), envelopeOpacity: +e.target.value / 100 } }) })),
        h('div', { class: 'btns' },
          h('button', { onclick: () => { const v = overviewView(app); app.viewer.flyTo(v.target, v.cam); } }, 'מבט על השכונה'),
          h('button', { onclick: () => app.ui.openTab('sun') }, 'שמש וצל…')),
        h('p', { class: 'muted' }, 'מפורט = הבית מגיליון 04 (מיושר, בקווי הבניין, ±0.00+8.00) עם חלונות ודלת להמחשה, חומות לפי A_1 §14 ונספח 009, חצר, עצים ותאורה. מעטפת = נפח מקסימלי לפי תמל/1016.'),
      );
      return wrap;
    },
  };
}

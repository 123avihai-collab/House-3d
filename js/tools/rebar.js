// Reinforcement of every element, from the engineer's rebar sheets (data/structure/rebar.json, tools/extract_rebar.py):
//  beams  – bars of the plan callouts ("3 Ø12 L=700 ב.ע"), stirrups / side bars of the beam section (or the typical section)
//  walls / columns – the section on the rebar sheet (by wall tag / column size) + the bar callouts of the plan
//  slabs  – meshes and extra bars of the slab sheets (K-x3) that fall in the slab
// and a rebar-inspection checklist per construction step (site visit: "ביקורת ברזל"). Checks are kept in the artifact's
// database (collection "rebarChecks"); outside the claude.ai viewer in this browser.
const SHEET_OF_LAYER = { groundBeams: 'K-12', groundFloorBeams: 'K-22', ceilingBeams: 'K-22', groundCeilingBeams: 'K-32', roofCeilingBeams: 'K-42' };
const SHEET_OF_FLOOR = { unit: 'K-12', ground: 'K-22', first: 'K-32', roof: 'K-42' };
const SLAB_FLOOR = { slabs: 'unit', groundSlab: 'ground', groundOutdoorSlabs: 'ground', groundMamad: 'ground', groundCeiling: 'groundCeiling', firstCeiling: 'roof' };
const LS = 'house3d.rebarChecks';
const fmt = (t) => String(t).replace(/ï\s*/g, 'Ø').replace(/\s+/g, ' ').trim();

export class RebarTool {
  constructor(app) {
    this.app = app; this.R = app.data.rebar || { beams: [], sections: [], plan: [], slabs: [] };
    this.checks = {}; this.state = 'loading';
    try { this.checks = JSON.parse(localStorage.getItem(LS) || '{}'); } catch {}
    this.connect();
  }
  async connect() {
    const use = window.claude?.use;
    const db = use ? await use('db').catch(() => null) : null;
    if (!db) { this.state = 'local'; return; }
    this.col = db.collection('rebarChecks');
    this.col.onSnapshot((snap) => {
      this.checks = Object.fromEntries(snap.docs.map(d => [d.id, d.data()])); this.state = 'online'; this.app.ui.refreshPanel('rebar');
    }, () => { this.state = 'local'; });
  }
  async setCheck(key, data) {
    const rec = { ...(this.checks[key] || {}), ...data, at: new Date().toISOString() };
    this.checks[key] = rec;
    if (this.state === 'online') { try { await this.col.doc(key).set(rec); } catch { this.app.ui.toast('השמירה נכשלה'); } }
    else try { localStorage.setItem(LS, JSON.stringify(this.checks)); } catch {}
    this.app.ui.refreshPanel('rebar');
  }
  key(item) { return `${item.tags.layer}:${item.meta.id || item.meta.name}`.replace(/[^\w:.\-א-ת]/g, '_'); }

  // ---- reinforcement of one registry item -> rows for the info card
  info(item) {
    const t = item.tags, m = item.meta, R = this.R;
    const rows = [];
    const sec = (s) => {
      if (!s) return;
      const st = (s.stirrups || []).filter(x => /@/.test(x)).map(fmt);
      const bars = (s.bars || []).map(fmt);
      if (st.length) rows.push(['חישוקים / ברזל צד (חתך)', [...new Set(st)].join(' · ')]);
      if (bars.length) rows.push(['ברזל (חתך)', [...new Set(bars)].join(' · ')]);
    };
    const sheet = SHEET_OF_LAYER[t.layer];
    if (sheet) {                                         // beam
      const id = m.id || '';
      let b = R.beams.find(x => x.sheet === sheet && x.id === id);
      const wh = (m.name || '').match(/(\d+)\/(\d+)/);
      const typical = !b?.section && wh ? R.sections.find(s => s.sheet === sheet && s.kind === 'typicalBeam' && s.title.endsWith(`${wh[1]}/${wh[2]}`)) : null;
      if (!b && !typical) return null;
      const top = (b?.bars || []).filter(x => x.position === 'top'), bot = (b?.bars || []).filter(x => x.position === 'bottom');
      const bar = (x) => `${x.count}Ø${x.dia_mm}${x.spacing_cm ? `@${x.spacing_cm}` : ''} L=${x.length_cm}`;
      if (top.length) rows.push(['ברזל עליון (ב.ע)', top.map(bar).join(' + ')]);
      if (bot.length) rows.push(['ברזל תחתון (ב.ת)', bot.map(bar).join(' + ')]);
      sec(b?.section || (typical ? typical.parsed : null));
      rows.push(['גיליון ברזל', `${sheet}${b?.section ? ` · חתך ${id}${b.section.typical ? ' (טיפוסי)' : ''}` : typical ? ` · ${typical.title.replace('חתךטיפוסי', 'חתך טיפוסי ')}` : ''}`]);
      return rows;
    }
    if (/Walls$|^basementWalls$|Columns$/.test(t.layer)) {   // wall / column
      const id = m.id;
      const s = R.sections.find(x => (x.elements || []).includes(id));
      const plan = R.plan.filter(p => p.element === id);
      if (!s && !plan.length) return null;
      for (const p of plan) rows.push([p.kind === 'mesh' ? 'רשת' : 'ברזל אנכי', fmt(p.text)]);
      if (s) { sec(s.parsed); rows.push(['גיליון ברזל', `${s.sheet} · ${s.title.replace('עמודבחתך', 'עמוד בחתך ')}`]); }
      return [...new Map(rows.map(r => [r.join('|'), r])).values()];
    }
    if (SLAB_FLOOR[t.layer]) {                              // slab
      const fl = SLAB_FLOOR[t.layer]; const S = R.slabs.find(x => x.floor === fl); if (!S) return null;
      for (const pl of S.plans) {
        const mine = pl.items.filter(it => it.slab === m.id);
        const mesh = [...new Set(pl.items.filter(it => /#/.test(it.text)).map(it => fmt(it.text)))];
        if (mesh.length) rows.push([`רשת ${pl.label}`, mesh.join(' · ')]);
        const extra = mine.filter(it => !/#/.test(it.text)).map(it => fmt(it.text));
        if (extra.length) rows.push([`תוספות ${pl.label}`, extra.join(' · ')]);
      }
      if (rows.length) rows.push(['גיליון ברזל', S.sheet]);
      return rows.length ? rows : null;
    }
    return null;
  }

  // ---- items that start at a construction step and have reinforcement data
  itemsOfStep(i) {
    const R = this.app.registry;
    const seen = new Set(); const out = [];
    for (const it of R.items) {
      if (it.meta.kind === 'ghost' || !it.meta.id || R.range(it.tags)[0] !== i) continue;
      const k = this.key(it); if (seen.has(k)) continue;
      const info = this.info(it); if (!info) continue;
      seen.add(k); out.push({ item: it, info, key: k });
    }
    return out;
  }
}

import * as THREE from 'three';
import { cylBetween, collar, sphere, box, disk, ring } from './geom.js';

// Proposals decided 07.11 by recommendation (data/plumbing/proposal.json):
//   firstFloor (PL3) – WC branches under the slab, ø50 branches in the build-up
//   unitSewer  (PB6) – separate sewage pump chamber PS-1, collectors under the basement slab, rising main, vent
//   rain       (PR1) – three alternatives for comparison (meta.rainAlt, switched in the panel)
// Every item: layer plProposal, meta.plProposal = true.
export function buildProposal2(h) {
  const { data, coords, C, mat, std, pipe, label, add, brass, steel, iron, concrete, redCap, buildChamber } = h;
  const P = data.plumbingProposal;
  const groundAt = (E, N_) => h.ground.heightAt(E, N_);
  const fmtH = (H) => coords.fmtH(H);
  const propTag = (it, extra = {}) => { it.meta.plProposal = true; Object.assign(it.meta, extra); return it; };
  const gravel = mat('gravel', () => std('#9b8f7a', 0.95, 0, { transparent: true, opacity: 0.55, depthWrite: false }));
  const sleeveM = mat('slv:gen', () => std('#8d8d8d', 0.6, 0, { transparent: true, opacity: 0.75 }));
  const superseded = [];
  const odOf = (mat_, D) => (C.pipes[mat_]?.sizes[String(D)]?.OD) || D / 1000;
  const toPts = (r, OD) => r.pts3d.map(p => coords.toLocal(p[0], p[1], p[2] != null ? p[2] : groundAt(p[0], p[1]) - (r.cover_m ?? 0.5) - OD / 2));
  const drawMat = (r) => (r.system === 'rain' ? 'PVC' : r.system === 'pumped' && r.material === 'HDPE' ? 'HDPE' : r.material);

  function run(r, tags, meta) {
    const g = new THREE.Group(); const m = drawMat(r), OD = odOf(m, r.D_mm);
    const sys = r.system === 'vent' ? 'sewage' : r.system;
    const tally = pipe(g, toPts(r, OD), OD, m, sys, 'source');
    if (r.system === 'vent') { const q = toPts(r, OD); const top = q[q.length - 1]; g.add(cylBetween(top, top.clone().add(new THREE.Vector3(0, 0.12, 0)), OD / 2 * 1.6, h.pipeMat('HDPE', 'sewage', 'source'))); }
    if (r.length_m > 2.5) { const q = toPts(r, OD); label(g, q[Math.floor(q.length / 2)].clone().add(new THREE.Vector3(0, 0.18, 0)), `ø${r.D_mm}${r.slope ? ` · ${(r.slope * 100).toFixed(0)}%` : ''}`, `sys-${sys}`); }
    const rows = [['מעמד', meta.status || 'הצעה לאישור'], ['צינור', `${r.material} ø${r.D_mm}`], ['מאיפה → לאן', `${r.from} → ${r.to}`], ['אורך', `${r.length_m.toFixed(2)} מ'`]];
    if (r.ILup != null) rows.push(['רום תחתית', `${fmtH(r.ILup)} → ${fmtH(r.ILdown)}${r.slope ? ` · שיפוע ${(r.slope * 100).toFixed(1)}%` : ''}`]);
    if (r.droppedCeiling_m) rows.push(['תקרה מונמכת בקומת הקרקע', `כ-${Math.round(r.droppedCeiling_m * 100)} ס"מ לאורך התוואי`]);
    if (r.coverToFinish_m != null) rows.push(['כיסוי עד הריצוף', `${Math.round(r.coverToFinish_m * 100)} ס"מ`]);
    rows.push(['אביזרים', Object.entries(tally).map(([k, v]) => `${v}× ${k}`).join(' · ') || '—']);
    if (r.note) rows.push(['הערה', r.note]);
    return propTag(add(g, tags, { name: `הצעה · ${r.id}`, kind: 'plPropGravity', rows, source: 'tools/plumbing/propose.py', note: 'הצעה בלבד', ...meta }), meta.extra || {});
  }
  function sleeve(s, tags, meta) {
    const g = new THREE.Group(); const dir = s.axis === 'h' ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
    g.add(collar(coords.toLocal(s.at[0], s.at[1], s.at[2]), dir, (s.sleeveD_mm || 160) / 2000, 0.26, sleeveM));
    const rows = [['מעבר', s.through], ['צינור', s.pipe], ['שרוול', s.sleeve], ['ITM / רום', `${coords.fmtEN(s.at[0], s.at[1])} · ${fmtH(s.at[2])}`]];
    return propTag(add(g, tags, { name: `הצעה · שרוול – ${s.through}`, kind: 'plPropSleeve', rows, source: 'tools/plumbing/propose.py', note: 'הצעה בלבד', ...meta }), meta.extra || {});
  }

  // ---- PL3: first floor
  const F = P.firstFloor;
  if (F) {
    const st = 'הצעה – PL3 לפי ההמלצה (אושר 07.11)';
    for (const r of F.runs) run(r, { floor: 'first', system: 'sewage', stage: 'ceiling', layer: 'plProposal' }, { plFloor: 'first', status: st });
    for (const s of F.sleeves) sleeve(s, { floor: 'first', system: 'sewage', stage: 'ceiling', layer: 'plProposal' }, { plFloor: 'first' });
    for (const d of F.drops) {
      const g = new THREE.Group(); g.add(sphere(coords.toLocal(d.E, d.N, H0of(h) + 3.70 + 0.04), 0.07, h.pipeMat('HDPE', 'sewage', 'source'), 14));
      label(g, coords.toLocal(d.E, d.N, d.bottom - 0.25), 'ירידה דרך התקרה + הסתעפות לענפי ø50', 'pt');
      propTag(add(g, { floor: 'first', system: 'sewage', stage: 'ceiling', layer: 'plProposal' }, { name: `הצעה · ירידת אסלה ${d.id}`, kind: 'plPropDrop', plFloor: 'first', rows: [['מעמד', st], ['ירידה', `${fmtH(d.top)} → ${fmtH(d.bottom)}`], ['הסתעפות', 'ענפי ø50 מצטרפים מעל התקרה (במילוי)']], source: 'tools/plumbing/propose_first.py', note: 'הצעה בלבד' }));
    }
    superseded.push(...F.superseded);
  }

  // ---- PB6: basement units sewage pump chamber
  const U = P.unitSewer;
  if (U) {
    const st = 'הצעה – PB6 לפי ההמלצה (אושר 07.11)', c = U.chamber;
    const g = new THREE.Group();
    const info = buildChamber(g, { id: c.id, kind: 'pumpChamber', E: c.E, N: c.N, D_m: c.D_m, TL: c.TL, IL: c.IL });
    for (const dx of [-0.18, 0.18]) {
      const p = coords.toLocal(c.E, c.N, c.IL + 0.05).add(new THREE.Vector3(dx, 0, 0));
      g.add(cylBetween(p, p.clone().add(new THREE.Vector3(0, 0.45, 0)), 0.09, mat('subPump', () => std('#455a64', 0.45, 0.5))));
      g.add(collar(p.clone().add(new THREE.Vector3(0, 0.5, 0)), new THREE.Vector3(0, 1, 0), 0.06, 0.08, mat('pumpTop', () => std('#1565c0', 0.5, 0.3))));
    }
    for (const z of [0.3, 0.6]) g.add(sphere(coords.toLocal(c.E, c.N, c.IL + z).add(new THREE.Vector3(0, 0, 0.25)), 0.035, mat('float', () => std('#ffb300', 0.5)), 10));
    label(g, coords.toLocal(c.E, c.N, c.TL + 0.4), `PS-1 תא שאיבה לשפכים ø100 · T.L ${c.TL.toFixed(2)} · I.L ${c.IL.toFixed(2)}`, 'chamber');
    const rows = [['מעמד', st], ['נימוק', c.why], ['משאבות', c.pumps], ['מכסה', c.cover], ['כניסות', c.inlets.map(i => `${i.run} ø${i.D_mm} @${i.IL.toFixed(2)}`).join(' · ')], ...info.rows.slice(0, 4)];
    propTag(add(g, { floor: 'unit', system: 'sewage', stage: 'groundBeams', layer: 'plProposal' }, { name: 'הצעה · PS-1 תא שאיבה לשפכי היחידות', kind: 'plPropChamber', plFloor: 'unit', rows, source: 'tools/plumbing/propose_units.py', note: 'הצעה בלבד – אישור היועץ' }));
    for (const r of U.runs) run(r, { floor: 'unit', system: 'sewage', stage: 'groundBeams', layer: 'plProposal' }, { plFloor: 'unit', status: st });
    for (const s of U.sleeves) if (s.sleeveD_mm) sleeve(s, { floor: 'unit', system: 'sewage', stage: 'groundBeams', layer: 'plProposal' }, { plFloor: 'unit' });
  }

  // ---- PR1: rain alternatives
  const R = P.rain;
  if (R) {
    for (const a of R.alternatives) {
      const meta = { plFloor: 'site', status: `הצעה – ${a.title} (להשוואה)`, extra: { rainAlt: a.id } };
      const tags = { floor: 'site', system: 'drainage', stage: 'groundBeams', layer: 'plProposal' };
      for (const r of a.runs) run(r, tags, meta);
      for (const s of a.sleeves) sleeve(s, tags, meta);
      const d = a.destination, g = new THREE.Group();
      if (d.kind === 'soakPit') {
        const RI = 0.30, ringH = 0.5, depth = 3.0;
        g.add(cylBetween(coords.toLocal(d.E, d.N, d.TL - depth), coords.toLocal(d.E, d.N, d.TL - ringH), RI, gravel, 24));
        const rg = ring(coords.toLocal(d.E, d.N, d.TL - ringH), RI, RI + 0.08, ringH - 0.03, concrete, 0.25); g.add(rg);
        g.add(disk(coords.toLocal(d.E, d.N, d.TL - 0.03), RI + 0.06, 0.03, iron));
        label(g, coords.toLocal(d.E, d.N, d.TL + 0.45), `${a.id === 1 ? 'בור החלחול של היועץ' : 'בור חלחול חדש'} · ${d.distFoundations_m.toFixed(2)} מ' מהיסודות`, 'rain');
      } else {
        buildChamber(g, { id: 'RC-1', kind: 'sewerChamber', E: d.E, N: d.N, D_m: d.D_m, TL: d.TL, IL: d.IL });
        const o = d.outlet, z = d.IL + 0.055;
        const a3 = coords.toLocal(o[0][0], o[0][1], z), b3 = coords.toLocal(o[1][0], o[1][1], z - 0.01);
        pipe(g, [a3, b3], 0.11, 'PVC', 'rain', 'source'); g.add(sphere(b3, 0.07, redCap, 12));
        label(g, b3.clone().add(new THREE.Vector3(0, 0.6, 0)), 'חיבור לניקוז העירוני – מיקום ורום לפי העירייה', 'end');
        label(g, coords.toLocal(d.E, d.N, d.TL + 0.45), `RC-1 שוחת ניקוז ø60 · T.L ${d.TL.toFixed(2)} · I.L ${d.IL.toFixed(2)}`, 'chamber');
      }
      const rows = [['מעמד', meta.status], ['יעד', d.title], ['ITM', coords.fmtEN(d.E, d.N)], ['כניסה', fmtH(d.IL)], ...a.facts.map(f => ['עובדה', f]), ['אישור נדרש', a.approval]];
      if (d.kind === 'soakPit') rows.push(['הבור', 'ø60, חצץ בשק גאוטכני (דוח הקרקע 11.6), חוליה עליונה עם מכסה; עומק 3.0 מ\' – זמני, לא כתוב בשום מקור']);
      if (a.tightCrossings.length) rows.push(['חציות לתיאום גבהים', a.tightCrossings.map(c => `${c.with} (${Math.round(c.clear_m * 100)} ס"מ)`).join(' · ')]);
      propTag(add(g, { floor: 'site', system: 'drainage', stage: 'finishes', layer: 'plProposal' }, { name: `הצעה · ${a.title}`, kind: 'plPropRainDest', plFloor: 'site', rows, source: 'tools/plumbing/propose_rain.py', note: 'להשוואה – הבחירה אחרי יועץ הקרקע והעירייה' }), { rainAlt: a.id });
    }
  }
  return { superseded };
}
const H0of = (h) => h.H0;

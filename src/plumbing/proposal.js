import * as THREE from 'three';
import { cylBetween, collar, hexNut, sphere, box } from './geom.js';

// Design proposal of the plumbing layer (data/plumbing/proposal.json, tools/plumbing/propose.py) – for approval.
// Shaft, manifolds with a ball valve per outlet, PEX in sleeves to every point, insulated hot supply + recirculation,
// moved stacks with connector pieces, and a marker at every wall / slab crossing (sleeve type, diameter, material).
// Every item: layer plProposal, meta.plProposal = true (hidden unless "with proposal" is on).
export function buildProposal(h) {
  const { data, coords, C, D, H0, mat, std, pipeMat, pipe, label, add, odOf, brass, steel, iron, rubber } = h;
  const P = data.plumbingProposal;
  const L = (p) => coords.toLocal(p[0], p[1], p[2]);
  const TAG = { cold: 'water', hot: 'water', return: 'water', sewage: 'sewage' };
  const SYSLBL = { cold: 'מים קרים', hot: 'מים חמים', return: 'מים חמים – קו סחרור (חזרה)', sewage: 'ביוב' };
  const floorTag = (f) => (f === 'roof' ? 'roof' : f === 'unit' ? 'unit' : f === 'first' ? 'first' : 'ground');
  const stageOf = (f) => (f === 'first' ? 'ceiling' : f === 'roof' ? 'finishes' : 'walls');
  const sleeveMat = (sys) => mat(`sleeve:${sys}`, () => std(sys === 'cold' ? '#3d7be0' : '#d8463a', 0.7, 0, { transparent: true, opacity: 0.38, depthWrite: false }));
  const foam = mat('foam', () => std('#26282b', 0.95));
  const white = mat('cabinet', () => std('#e9ecef', 0.5, 0.1));
  const chrome = mat('chrome', () => std('#dfe3e7', 0.15, 1.0));
  const glassM = mat('shaftGlass', () => std('#ffd54f', 0.6, 0, { transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide }));
  const propTag = (it) => { it.meta.plProposal = true; return it; };
  const fmtH = (H) => coords.fmtH(H);
  const supersededSet = P.superseded;

  // ---- runs (PEX in sleeves / insulated hot + return)
  const runsById = {};
  for (const r of P.runs) {
    runsById[r.id] = r;
    const pts = r.pts3d.map(L);
    const OD = (C.pipes.PEX.sizes[String(r.D_mm)]?.OD) || r.D_mm / 1000;
    const g = new THREE.Group();
    const sys = r.system === 'return' ? 'hot' : r.system;
    const tally = pipe(g, pts, OD, 'PEX', sys, 'source');
    const outerR = r.insulation_mm ? OD / 2 + r.insulation_mm / 1000 : (r.conduitD_mm ? r.conduitD_mm / 2000 : null);
    if (outerR) {
      const m = r.insulation_mm ? foam : sleeveMat(sys);
      for (let i = 1; i < pts.length; i++) { const c = cylBetween(pts[i - 1], pts[i], outerR, m, 14, !r.insulation_mm); if (c) { c.castShadow = false; g.add(c); } }
      for (let i = 1; i < pts.length - 1; i++) g.add(sphere(pts[i], outerR, m, 10));
    }
    if (r.length_m > 2.5 && r.system !== 'cold') label(g, pts[Math.floor(pts.length / 2)].clone().add(new THREE.Vector3(0, 0.15, 0)), `ø${r.D_mm}${r.system === 'return' ? ' חזרה' : ''}`, `sys-${sys}`);
    const rows = [['מעמד', 'הצעה לאישור – לא מתוכנית היועץ'], ['מערכת', SYSLBL[r.system]], ['צינור', `PEX ø${r.D_mm}`],
      [r.insulation_mm ? 'בידוד' : 'שרוול', r.insulation_mm ? `גומי מוקצף ${r.insulation_mm} מ"מ (עובי זמני – PD1/PL)` : `שרוול מריכף ø${r.conduitD_mm} לכל האורך (הערה 10 – לשליפה)`],
      ['אורך', `${r.length_m.toFixed(2)} מ'`], ['מאיפה → לאן', `${r.from} → ${r.to}`],
      ['מפלסים', `${fmtH(r.pts3d[0][2])} → ${fmtH(r.pts3d[r.pts3d.length - 1][2])}`],
      ['אביזרים', Object.entries(tally).map(([k, v]) => `${v}× ${k}`).join(' · ') || 'קטע רציף (PEX גמיש)']];
    if (r.note) rows.push(['הערה', r.note]);
    propTag(add(g, { floor: floorTag(r.floor), system: TAG[r.system], stage: stageOf(r.floor), layer: 'plProposal' },
      { name: `הצעה · ${r.id} · ${SYSLBL[r.system]} ø${r.D_mm}`, kind: 'plPropRun', plFloor: r.floor, rows, source: 'tools/plumbing/propose.py – הצעת תכנון', note: 'הצעה בלבד – דורשת את אישורך ואת אישור היועץ' }));
  }

  // ---- manifolds: cabinet, brass bars, ball valve per outlet, main valve at the inlet
  for (const m of P.manifolds) {
    const g = new THREE.Group();
    const ax = new THREE.Vector3(m.axis[0], 0, -m.axis[1]).normalize(), face = new THREE.Vector3(m.face[0], 0, -m.face[1]).normalize();
    const base = coords.toLocal(m.E, m.N, m.H_floor);
    const n = Math.max(m.outlets.cold.length, m.outlets.hot.length, 2);
    const len = n * 0.05 + 0.16;
    // cabinet (back panel + frame), recessed in the wall
    const cab = box(base.clone().add(new THREE.Vector3(0, (m.coldH + m.hotH) / 2, 0)).addScaledVector(face, -0.03), len + 0.12, 0.42, 0.015, white, Math.atan2(-ax.z, ax.x));
    cab.rotation.y = Math.atan2(-ax.z, ax.x); g.add(cab);
    for (const [sys, H, list] of [['cold', m.coldH, m.outlets.cold], ['hot', m.hotH, m.outlets.hot]]) {
      if (!list.length && !(sys === 'hot' && m.hotPending)) continue;
      const c0 = base.clone().add(new THREE.Vector3(0, H, 0)).addScaledVector(face, 0.05);
      const a = c0.clone().addScaledVector(ax, -len / 2), b = c0.clone().addScaledVector(ax, len / 2);
      g.add(cylBetween(a, b, 0.016, brass, 16));
      g.add(hexNut(a, ax, 0.04, 0.03, brass));      // inlet nut (main valve below)
      g.add(collar(a.clone().addScaledVector(ax, -0.05), ax, 0.02, 0.06, mat(`h:${sys}`, () => std(sys === 'cold' ? '#1e63c8' : '#c62828', 0.45))));
      g.add(hexNut(b, ax, 0.034, 0.02, brass));      // end plug / return connection
      if (sys === 'hot' && m.hotPending) { label(g, c0.clone().add(new THREE.Vector3(0, 0.12, 0)), 'חמים – ממתין להחלטה PD1', 'end'); continue; }
      list.forEach((o, i) => {
        const p = c0.clone().addScaledVector(ax, (i - (list.length - 1) / 2) * 0.05);
        g.add(cylBetween(p, p.clone().addScaledVector(face, 0.07), 0.009, brass, 10));
        g.add(sphere(p.clone().addScaledVector(face, 0.045), 0.014, brass, 10));                              // ball valve body
        const lev = box(p.clone().addScaledVector(face, 0.045).add(new THREE.Vector3(0, 0.022, 0)), 0.05, 0.006, 0.012, mat(`lev:${sys}`, () => std(sys === 'cold' ? '#1565c0' : '#c62828', 0.5)));
        lev.rotation.y = Math.atan2(-ax.z, ax.x); g.add(lev);
      });
    }
    label(g, base.clone().add(new THREE.Vector3(0, m.hotH + 0.35, 0)), m.title, 'chamber');
    const rows = [['מעמד', 'הצעה לאישור'], ['ITM', coords.fmtEN(m.E, m.N)], ['גובה', `קרים ${m.coldH.toFixed(2)} · חמים ${m.hotH.toFixed(2)} מעל הריצוף`],
      ['יציאות מים קרים', m.outlets.cold.map(o => `${o.to} ø${o.D_mm}`).join(' · ')],
      ['יציאות מים חמים', m.hotPending ? 'ממתין להחלטה PD1 (דודים ליחידות)' : m.outlets.hot.map(o => `${o.to} ø${o.D_mm}`).join(' · ')],
      ['אביזרים', 'ארון מחלקים · מחלקי פליז ø32 · ברז כדורי לכל יציאה (הערה 11) · ברז ראשי בכניסה · פקק / חיבור חזרה בקצה']];
    propTag(add(g, { floor: floorTag(m.floor), system: 'water', stage: 'finishes', layer: 'plProposal' }, { name: `הצעה · ${m.title}`, kind: 'plPropManifold', plFloor: m.floor, rows, source: 'tools/plumbing/propose.py', note: 'הצעה בלבד' }));
  }

  // ---- points: wall elbow + angle valve at the typical height
  for (const p of P.points) {
    const g = new THREE.Group();
    const dir = p.face ? new THREE.Vector3(p.face[0], 0, -p.face[1]).normalize() : new THREE.Vector3(1, 0, 0);
    const along = p.wallDir ? new THREE.Vector3(p.wallDir[0], 0, -p.wallDir[1]).normalize() : new THREE.Vector3(0, 0, 1);
    const sides = [];
    if (p.cold) sides.push(['cold', p.hot || p.hotPending ? -1 : 0]);
    if (p.hot || p.hotPending) sides.push(['hot', 1]);
    for (const [sys, sgn] of sides) {
      const c = coords.toLocal(p.E, p.N, p.H).addScaledVector(along, sgn * 0.075);
      if (sys === 'hot' && p.hotPending) { g.add(sphere(c, 0.02, h.redCap, 10)); continue; }
      g.add(box(c, 0.035, 0.035, 0.035, brass));                                         // wall-plate elbow
      g.add(cylBetween(c, c.clone().addScaledVector(dir, 0.05), 0.008, chrome, 10));      // stub
      g.add(sphere(c.clone().addScaledVector(dir, 0.055), 0.013, chrome, 10));             // angle valve body
      g.add(collar(c.clone().addScaledVector(dir, 0.055).add(new THREE.Vector3(0, 0.02, 0)), new THREE.Vector3(0, 1, 0), 0.011, 0.012, mat(`cap:${sys}`, () => std(sys === 'cold' ? '#1565c0' : '#c62828', 0.4))));
    }
    label(g, coords.toLocal(p.E, p.N, p.H + 0.22), `${p.title} · ${p.H_rel.toFixed(2)}`, 'pt');
    const rows = [['מעמד', 'הצעה לאישור'], ['קבועה', `${p.title} (${p.fixture})`], ['גובה הנקודה', `${p.H_rel.toFixed(2)} מעל הריצוף – ${fmtH(p.H)} (ערך טיפוסי, לאישור)`],
      ['צינור', `PEX ø${p.D_mm} מהמחלק, בשרוול`], ['מים', [p.cold ? 'קרים' : null, p.hot ? 'חמים' : null, p.hotPending ? 'חמים – ממתין להחלטה PD1' : null].filter(Boolean).join(' + ')],
      ['אביזרים', 'זווית קיר (פליז) + ברז זווית לכל צד'], ['מקור הקבועה', p.source]];
    propTag(add(g, { floor: floorTag(p.floor), system: 'water', stage: 'finishes', layer: 'plProposal' }, { name: `הצעה · נקודת מים – ${p.title}`, kind: 'plPropPoint', plFloor: p.floor, rows, source: 'tools/plumbing/propose.py', note: 'הצעה בלבד' }));
  }

  // ---- moved stacks (ø110 HDPE) + connector pieces
  for (const s of P.stackMoves) {
    if (!s.pts3d) continue;
    const g = new THREE.Group();
    const pts = s.pts3d.map(L), OD = 0.110;
    const tally = pipe(g, pts, OD, 'HDPE', 'sewage', 'source');
    const top = pts[pts.length - 1];
    g.add(cylBetween(top, top.clone().add(new THREE.Vector3(0, 0.12, 0)), OD / 2 * 1.6, pipeMat('HDPE', 'sewage', 'source')));
    label(g, top.clone().add(new THREE.Vector3(0, 0.4, 0)), `צ.א ${s.stack} – הוזז ${Math.round(s.displacement_m * 100)} ס"מ`, 'stack');
    for (const c of s.connectors) pipe(g, c.pts3d.map(L), c.D_mm / 1000, c.material || 'HDPE', 'sewage', 'provisional');
    const rows = [['מעמד', 'הצעה לאישור'], ['הזזה', `${(s.displacement_m * 100).toFixed(0)} ס"מ (בצירי הבית: ${s.local_dxdy_m.map(v => (v * 100).toFixed(0)).join(' / ')})`],
      ['במיקום שבתוכנית חוצה', s.clashesBefore.join(' · ') || '—'], ['במיקום המוצע', s.clashesAfter.length ? s.clashesAfter.join(' · ') : 'אין חציה של בטון'],
      ['מרחק לקו קיר אדריכלי', `${(s.distToWall_m * 100).toFixed(0)} ס"מ (להלבשה / קיר)`], ['חיבורי ענפים', s.connectors.map(c => `${c.run} ø${c.D_mm}`).join(' · ') || '—'],
      ['אביזרים', Object.entries(tally).map(([k, v]) => `${v}× ${k}`).join(' · ') || '—'], ['נימוק', s.why]];
    propTag(add(g, { floor: 'ground', system: 'sewage', stage: 'walls', layer: 'plProposal' }, { name: `הצעה · צ.א ${s.stack} – מיקום חדש`, kind: 'plPropStack', plFloor: 'ground', rows, source: 'tools/plumbing/propose.py', note: 'הצעה בלבד – תיאום אדריכל (הלבשה) וקונסטרוקטור' }));
  }

  // ---- shaft: translucent volume + slab-opening frames
  {
    const g = new THREE.Group(); const fp = P.shaft.footprintITM;
    const bot = P.shaft.bottom, top = P.shaft.top;
    const shape = new THREE.Shape(fp.map(p => { const v = coords.toLocal(p[0], p[1], 0); return new THREE.Vector2(v.x, -v.z); }));
    const geo = new THREE.ExtrudeGeometry(shape, { depth: top - bot, bevelEnabled: false }); geo.rotateX(-Math.PI / 2);
    const m = new THREE.Mesh(geo, glassM); m.position.y = bot - H0; m.renderOrder = 4; g.add(m);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: '#c49000' })); edges.position.y = bot - H0; g.add(edges);
    for (const s of P.sleeves.filter(x => x.pipe === 'SHAFT')) {
      const ring = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(fp.map(p => coords.toLocal(p[0], p[1], s.at[2]))), new THREE.LineBasicMaterial({ color: '#ff6f00' }));
      g.add(ring);
    }
    label(g, coords.toLocal(fp[0][0], fp[0][1], top + 0.3), 'פיר אינסטלציה (הצעה)', 'chamber');
    const rows = [['מעמד', 'הצעה – החלטה D2 (חלופה א\')'], ['מידות נטו', `${(P.shaft.local[2] * 100).toFixed(0)}×${(P.shaft.local[3] * 100).toFixed(0)} ס"מ`],
      ['גובה', `${fmtH(P.shaft.bottom)} → ${fmtH(P.shaft.top)}`], ['מיקום', 'צמוד לפאה הצפונית של הממ"ד, מחוץ לו; בקרקע – בחדר הרחצה של ההורים; בקומה א\' – בחדר שמצפון לחדרי הרחצה; במרתף – ביחידה 2'],
      ['בפיר', 'מים קרים (ראשי + עולה לקומה א\'), ירידה למוני היחידות, אספקה חמה + חזרה (מבודדים)'], ['בדיקת שלד', P.shaft.clashes.length ? P.shaft.clashes.join(', ') : 'לא חוצה קירות, עמודים או קורות במודל (תקרת הגג K-41 – טרם במודל)'],
      ['פתחים בתקרות', P.sleeves.filter(x => x.pipe === 'SHAFT').map(x => x.through).join(' · ')]];
    propTag(add(g, { floor: 'ground', system: 'water', stage: 'walls', layer: 'plProposal' }, { name: 'הצעה · פיר אינסטלציה מצפון לממ"ד', kind: 'plPropShaft', plFloor: 'ground', rows, source: 'tools/plumbing/propose.py', note: 'הצעה בלבד – דורש אישור אדריכל, קונסטרוקטור ויועץ' }));
  }

  // ---- sleeves at wall crossings (collar along the pipe) and the entry sleeve
  for (const s of P.sleeves) {
    if (s.pipe === 'SHAFT') continue;
    const r = runsById[s.pipe]; if (!r) continue;
    let best = null;
    for (let i = 1; i < r.pts3d.length; i++) {
      const a = r.pts3d[i - 1], b = r.pts3d[i];
      const t = Math.max(0, Math.min(1, ((s.at[0] - a[0]) * (b[0] - a[0]) + (s.at[1] - a[1]) * (b[1] - a[1])) / (((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) || 1)));
      const d = Math.hypot(a[0] + t * (b[0] - a[0]) - s.at[0], a[1] + t * (b[1] - a[1]) - s.at[1]);
      if (!best || d < best.d) best = { d, dir: new THREE.Vector3(b[0] - a[0], b[2] - a[2], -(b[1] - a[1])).normalize() };
    }
    const g = new THREE.Group();
    const R = (s.sleeveD_mm || 40) / 2000;
    g.add(collar(L(s.at), best.dir, R, Math.max(0.12, s.length_m || 0.2), mat(`slv:${s.through}`, () => std(s.through.includes('בטון') || s.through.includes('חוץ') ? '#8d8d8d' : '#f39c12', 0.6, 0, { transparent: true, opacity: 0.75 }))));
    if (s.through.includes('חוץ')) g.add(collar(L(s.at), best.dir, R + 0.05, 0.012, iron));    // puddle flange
    const rows = [['מעבר', s.through], ['צינור', s.pipe], ['שרוול', s.sleeve], ['קוטר / חומר', `${s.sleeveD_mm ? 'ø' + s.sleeveD_mm : '—'} · ${s.material}`], ['ITM / רום', `${coords.fmtEN(s.at[0], s.at[1])} · ${fmtH(s.at[2])}`]];
    propTag(add(g, { floor: floorTag(s.floor), system: 'water', stage: stageOf(s.floor), layer: 'plProposal' }, { name: `הצעה · שרוול – ${s.through}`, kind: 'plPropSleeve', plFloor: s.floor, rows, source: 'tools/plumbing/propose.py', note: 'הצעה בלבד' }));
  }

  // ---- main valve, sub-meters, recirculation pump
  for (const [o, kind] of [[P.mainValve, 'valve'], [P.submeters, 'meters'], [P.recircPump, 'pump']]) {
    const g = new THREE.Group(); const c = coords.toLocal(o.E, o.N, o.H);
    if (kind === 'valve') { g.add(sphere(c, 0.025, brass, 12)); g.add(box(c.clone().add(new THREE.Vector3(0, 0.035, 0)), 0.09, 0.008, 0.016, mat('lev:main', () => std('#d32f2f', 0.5)))); }
    if (kind === 'meters') for (const dx of [-0.08, 0.08]) { const q = c.clone().add(new THREE.Vector3(dx, 0, 0)); g.add(box(q, 0.11, 0.08, 0.08, mat('meter', () => std('#2c5aa0', 0.4, 0.2)))); g.add(sphere(q.clone().add(new THREE.Vector3(0, 0.07, 0)), 0.015, brass, 10)); }
    if (kind === 'pump') { g.add(cylBetween(c.clone().add(new THREE.Vector3(-0.06, 0, 0)), c.clone().add(new THREE.Vector3(0.06, 0, 0)), 0.035, mat('pumpBody', () => std('#b71c1c', 0.4, 0.3)))); g.add(box(c.clone().add(new THREE.Vector3(0, 0.07, 0)), 0.08, 0.06, 0.06, mat('pumpMotor', () => std('#37474f', 0.5, 0.3)))); }
    label(g, c.clone().add(new THREE.Vector3(0, 0.25, 0)), o.title, 'pt');
    propTag(add(g, { floor: kind === 'pump' ? 'roof' : kind === 'meters' ? 'unit' : 'ground', system: 'water', stage: 'finishes', layer: 'plProposal' },
      { name: `הצעה · ${o.title}`, kind: 'plPropDevice', plFloor: kind === 'pump' ? 'roof' : kind === 'meters' ? 'unit' : 'ground', rows: [['מעמד', 'הצעה לאישור'], ['רכיב', o.title], ['רום', fmtH(o.H)]], source: 'tools/plumbing/propose.py', note: 'הצעה בלבד' }));
  }
  return { superseded: supersededSet, summary: P.summary };
}

import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { cylBetween, collar, hexNut, seal, bend, sphere, box, ring, disk } from './geom.js';
import { buildPanel } from './panel.js';
import { buildProposal } from './proposal.js';
import { buildProposal2 } from './proposal2.js';

// Plumbing layer (separate module): the plumbing consultant's design as drawn – sewer, pumped line, rain water,
// cold/hot water – with real fittings, precast chambers, and the engineering findings.
// Data: data/plumbing/network.json (tools/plumbing/build.py), catalog.json (market components), display.json.
// The module adds its own layer group in memory (data/config/layers.json is not edited) and hides the older,
// simpler sewer display of stage 2b by default (its layers stay available in the layers panel).

export const LAYERS = [
  ['plSewage', 'ביוב: צנרת, אביזרים וקולטנים (צ.א)', 'sewage'],
  ['plChambers', 'שוחות ותאי ביקורת: חוליות, מכסים, אטמים', 'sewage'],
  ['plPumped', 'קו סניקה מתא השאיבה (מרתף)', 'sewage'],
  ['plRain', 'מי גשם: נקזים, צמ"ג, בור חלחול', 'drainage'],
  ['plCold', 'מים קרים: מערכת מדידה, קווים, ברזים', 'water'],
  ['plHot', 'מים חמים: דוד ומחלק בגג', 'water'],
  ['plFindings', 'ממצאי בדיקה הנדסית (סמנים)', 'plumbing'],
  ['plProposal', 'הצעת תכנון (לאישור): פיר, מחלקים, צנרת לנקודות, הזזת קולטנים', 'plumbing'],
];
const SYS_LAYER = { sewage: 'plSewage', pumped: 'plPumped', rain: 'plRain', cold: 'plCold', hot: 'plHot' };
const SYS_TAG = { sewage: 'sewage', pumped: 'sewage', rain: 'drainage', cold: 'water', hot: 'water' };
const FLOOR_REL = { site: 0, unit: -2.6, ground: 0, first: 3.85, roof: 6.85 };
const OLD_LAYERS = ['sewagePipes', 'sewageManholes', 'drainChambers'];

export function buildPlumbing(ctx) {
  const { data, coords, registry, scene, ground } = ctx;
  const N = data.plumbing, C = data.plumbingCatalog, D = data.plumbingDisplay;
  if (!N) return null;
  const link = document.createElement('link');
  link.rel = 'stylesheet'; link.href = new URL('./plumbing.css', import.meta.url).href;
  document.head.append(link);

  // ---- layers group (in memory) + older sewer layers off by default
  const g = data.layers.groups.find(x => x.id === 'plumbing');
  Object.assign(g, { label: 'אינסטלציה – תוכנית היועץ', implemented: true, system: 'plumbing', layers: LAYERS.map(([id, label]) => ({ id, label })) });
  for (const grp of data.layers.groups) for (const l of grp.layers) if (OLD_LAYERS.includes(l.id)) { l.visible = false; l.label += ' (תצוגה קודמת)'; }

  const H0 = coords.H0;
  const byId = Object.fromEntries(N.nodes.map(n => [n.id, n]));
  const runsAt = {};
  for (const r of N.runs) for (const e of [r.from, r.to]) (runsAt[e] ||= []).push(r);
  const findingsOf = {};
  for (const f of N.findings) for (const e of f.elements) (findingsOf[e] ||= []).push(f.id);

  // ---- materials
  const M = new Map();
  const mat = (key, make) => { if (!M.has(key)) M.set(key, make()); return M.get(key); };
  const std = (color, rough = 0.5, metal = 0, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal, ...extra });
  const pipeMat = (material, sys, status) => mat(`p:${material}:${sys}:${status}`, () => {
    const spec = C.pipes[material] || C.pipes.HDPE;
    const col = typeof spec.color === 'string' ? spec.color : (spec.color[sys] || spec.color.cold);
    const m = std(col, spec.roughness, 0);
    if (status === 'provisional') { m.emissive = new THREE.Color(D.provisionalTint); m.emissiveIntensity = 0.12; }
    if (status === 'missing') { m.emissive = new THREE.Color(D.openEndColor); m.emissiveIntensity = 0.25; }
    return m;
  });
  const rubber = mat('rubber', () => std('#121212', 0.9));
  const brass = mat('brass', () => std('#b68a3c', 0.32, 0.85));
  const iron = mat('iron', () => std('#2a2b2d', 0.55, 0.55));
  const steel = mat('steel', () => std('#c3c7cb', 0.28, 0.9));
  const concrete = ctx.materials.get('concrete');
  const channelMat = mat('channel', () => std('#5d5a55', 0.8));
  const redCap = mat('redcap', () => std(D.openEndColor, 0.5, 0, { emissive: new THREE.Color(D.openEndColor), emissiveIntensity: 0.35 }));

  const items = [];
  const label = (parent, pos, text, cls = '') => {
    const d = document.createElement('div'); d.className = `lbl pl ${cls}`; d.textContent = text;
    const o = new CSS2DObject(d); o.position.copy(pos); o.userData.annotation = true; parent.add(o); return o;
  };
  const add = (grp, tags, meta) => { scene.add(grp); const it = registry.add(grp, tags, meta); it.meta.plumbing = true; items.push(it); return it; };
  const stageOf = (floor, sys) => floor === 'site' || floor === 'roof' ? 'finishes' : floor === 'first' ? 'ceiling' : sys === 'stack' ? 'walls' : 'groundBeams';
  const statusTxt = (s) => D.status[s] || s || '—';
  const fmtH = (H) => H == null ? '—' : coords.fmtH(H);
  const title = (id) => byId[id] ? `${byId[id].title} (${id})` : id;
  const odOf = (r) => {
    const spec = C.pipes[r.material] || C.pipes.HDPE;
    const s = spec.sizes[String(r.D_mm)];
    return s ? s.OD : (r.D_mm || C.unknownDiameterDisplay_mm) / 1000;
  };
  const nodeH = {};    // pipe centre level of each node (from the runs that reach it)

  // ---- run -> 3D centre line
  const groundAt = (E, N_) => ground.heightAt(E, N_);
  function runPoints(r, OD) {
    const P = r.pts;
    if (r.ILup != null && r.ILdown != null) {
      let L = 0; for (let i = 1; i < P.length; i++) L += Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]);
      let s = 0;
      return P.map((p, i) => { if (i) s += Math.hypot(p[0] - P[i - 1][0], p[1] - P[i - 1][1]); return coords.toLocal(p[0], p[1], r.ILup - (r.ILup - r.ILdown) * (L ? s / L : 0) + OD / 2); });
    }
    if (r.coverDepth_m != null) {
      const out = [];
      for (let i = 0; i < P.length; i++) {
        out.push(P[i]);
        if (i < P.length - 1) {   // follow the finished grade: a point every ~1.5 m
          const L = Math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1]), n = Math.floor(L / 1.5);
          for (let k = 1; k < n; k++) out.push([P[i][0] + (P[i + 1][0] - P[i][0]) * k / n, P[i][1] + (P[i + 1][1] - P[i][1]) * k / n]);
        }
      }
      return out.map(p => coords.toLocal(p[0], p[1], groundAt(p[0], p[1]) - r.coverDepth_m - OD / 2));
    }
    const H = H0 + (FLOOR_REL[r.drawnOn || r.floor] ?? 0) - 0.3;
    return P.map(p => coords.toLocal(p[0], p[1], H));
  }

  // ---- generic pipe with fittings (bends, sockets, seals, couplers); returns fitting tallies
  function pipe(grp, P, OD, material, sys, status) {
    const spec = C.pipes[material] || C.pipes.HDPE, r = OD / 2;
    const m = pipeMat(material, sys, status), body = pipeMat(material, sys, 'source');
    const sockR = r * spec.socketOD_ratio, sockL = Math.max(0.012, OD * spec.socketLen_D);
    const Rb = OD * (C.bends.bendRadius_D[sys] ?? 1), bodyR = r * C.bends.bodyOD_ratio;
    const tally = {};
    const joint = (p, dir) => {
      if (spec.joint === 'compression') grp.add(hexNut(p, dir, OD * spec.socketOD_ratio, sockL * 0.6, brass));
      else { grp.add(collar(p, dir, sockR, sockL, body, D.radialSegments)); if (spec.joint === 'socket') grp.add(seal(p.clone().addScaledVector(dir, -sockL / 2), dir, r * 1.02, r * 0.07, rubber)); }
    };
    const straight = (a, b) => {
      const c = cylBetween(a, b, r, m, D.radialSegments); if (!c) return;
      grp.add(c);
      const d = b.clone().sub(a), L = d.length(); d.normalize();
      for (let s = spec.stdLength_m; s < L - 0.3; s += spec.stdLength_m) joint(a.clone().addScaledVector(d, s), d);   // pipe joints along the run
    };
    let start = P[0].clone();
    for (let i = 1; i < P.length; i++) {
      const v = P[i];
      if (i === P.length - 1) { straight(start, v); break; }
      const d1 = v.clone().sub(P[i - 1]).normalize(), d2 = P[i + 1].clone().sub(v).normalize();
      const ang = d1.angleTo(d2), deg = ang * 180 / Math.PI;
      if (deg < 8) continue;                       // follows the grade – flexible pipe, no fitting
      const lim = Math.min(v.distanceTo(P[i - 1]), P[i + 1].distanceTo(v)) * 0.45;
      if ((sys === 'sewage' || sys === 'rain') && deg > 60) {
        // consultant note 4: a 90° change in soil/waste lines = two 45° bends, ≥ 2D between their centres
        const dm = d1.clone().add(d2).normalize(), a = Math.min(lim, Math.max(OD * 1.2, Rb * 0.6));
        const q1 = v.clone().addScaledVector(d1, -a), q2 = v.clone().addScaledVector(d2, a);
        const t1 = Math.min(Rb * Math.tan(d1.angleTo(dm) / 2), a * 0.45);
        const b1 = bend(q1, d1, dm, t1, bodyR, body, D.bendSegments), b2 = bend(q2, dm, d2, t1, bodyR, body, D.bendSegments);
        straight(start, b1.a); grp.add(b1.mesh, b2.mesh); straight(b1.b, b2.a);
        for (const [p, d] of [[b1.a, d1], [b1.b, dm], [b2.a, dm], [b2.b, d2]]) joint(p, d);
        start = b2.b; tally['2×קשת 45°'] = (tally['2×קשת 45°'] || 0) + 1;
      } else {
        const t = Math.min(Rb * Math.tan(ang / 2), lim);
        const b = bend(v, d1, d2, t, bodyR, body, D.bendSegments);
        straight(start, b.a); grp.add(b.mesh); joint(b.a, d1); joint(b.b, d2); start = b.b;
        const std_ = sys === 'sewage' || sys === 'rain' ? C.bends.sewerAngles_deg.reduce((x, y) => Math.abs(y - deg) < Math.abs(x - deg) ? y : x) : Math.round(deg);
        const key = sys === 'cold' || sys === 'hot' || sys === 'pumped' ? `זווית ${std_}° (מחבר לחיצה)` : `קשת ${std_}°`;
        tally[key] = (tally[key] || 0) + 1;
      }
    }
    return tally;
  }

  // ---- runs
  let totalLen = 0;
  const CH = new Set(['sewerChamber', 'municipalManhole', 'pumpChamber']);
  const trimAtChamber = (P, id, atStart) => {   // a pipe ends at the inner face of the chamber wall, not at its centre
    const n = byId[id]; if (!n || !CH.has(n.kind) || P.length < 2) return;
    const [a, b] = atStart ? [P[0], P[1]] : [P[P.length - 1], P[P.length - 2]];
    const d = b.clone().sub(a); const hd = Math.hypot(d.x, d.z); if (hd <= n.D_m / 2 + 0.05) return;
    a.addScaledVector(d, (n.D_m / 2 - 0.02) / hd);
  };
  for (const r of N.runs) {
    const OD = odOf(r);
    const P = runPoints(r, OD);
    trimAtChamber(P, r.from, true); trimAtChamber(P, r.to, false);
    nodeH[r.from] ??= P[0].y + H0; nodeH[r.to] ??= P[P.length - 1].y + H0;
    const grp = new THREE.Group();
    const st = r.levelStatus === 'missing' ? 'missing' : r.levelStatus === 'provisional' ? 'provisional' : 'source';
    const tally = pipe(grp, P, OD, r.material || 'HDPE', r.system, st);
    totalLen += r.length_m;
    if (r.length_m > D.labelMinLength_m && r.D_mm) {
      let tot = 0; for (let i = 1; i < P.length; i++) tot += P[i].distanceTo(P[i - 1]);
      let acc = 0, mid = P[0].clone();
      for (let i = 1; i < P.length; i++) { const d = P[i].distanceTo(P[i - 1]); if (acc + d >= tot / 2) { mid = P[i - 1].clone().lerp(P[i], (tot / 2 - acc) / d); break; } acc += d; }
      mid.y += 0.18;
      label(grp, mid, `ø${r.D_mm}${r.slope ? ` · ${(r.slope * 100).toFixed(r.slope < 0.1 ? 1 : 0)}%` : ''}${st !== 'source' ? ' *' : ''}`, `sys-${r.system}`);
    }
    const sysLbl = D.systems[r.system]?.label || r.system;
    const rows = [
      ['מערכת', sysLbl + (r.role === 'pumped' ? ' – קו לחץ' : '')],
      ['קוטר וחומר', r.D_mm ? `ø${r.D_mm} מ"מ · ${r.material}` : 'לא כתוב בתוכנית'],
      ['קביעת הקוטר', r.diameterRule || '—'],
      ['אורך', `${r.length_m.toFixed(2)} מ'`],
      ['מאיפה', title(r.from)], ['לאן', title(r.to)],
      ['רום תחתית: התחלה → סוף', r.ILup != null ? `${fmtH(r.ILup)} → ${fmtH(r.ILdown)}` : r.coverDepth_m != null ? `עומק כיסוי ${r.coverDepth_m.toFixed(2)} מ' מתחת לפני הפיתוח` : '—'],
      ['שיפוע', r.slope != null ? `${(r.slope * 100).toFixed(2)}%` : '—'],
      ['מעמד המפלס', `${statusTxt(r.levelStatus)} – ${r.levelRule || ''}`],
      ['אביזרים בקטע', Object.entries(tally).map(([k, v]) => `${v}× ${k}`).join(' · ') || 'קטע ישר'],
    ];
    if (r.dropAtDownstream_m) rows.push(['מפל בכניסה לשוחה', `${r.dropAtDownstream_m.toFixed(2)} מ'`]);
    if (findingsOf[r.id]) rows.push(['ממצאים', findingsOf[r.id].join(', ')]);
    add(grp, { floor: r.floor, system: SYS_TAG[r.system], stage: stageOf(r.floor, r.system), layer: SYS_LAYER[r.system] },
      { name: `${r.id} · ${sysLbl}${r.D_mm ? ` ø${r.D_mm}` : ''}`, kind: 'plRun', netId: r.id, plFloor: r.drawnOn || r.floor, rows, source: r.source,
        note: st !== 'source' ? `מפלס ${statusTxt(r.levelStatus)}` : null, status: st === 'source' ? 'source' : 'provisional' });
  }

  // ---- 3D lines: stacks, downpipes, pump riser
  for (const l of N.lines3d) {
    const OD = odOf(l);
    const pts = l.pts3d.map(p => coords.toLocal(p[0], p[1], p[2] != null ? p[2] : groundAt(p[0], p[1]) - 0.5 - OD / 2));
    const grp = new THREE.Group();
    const sys = l.system;
    const tally = pipe(grp, pts, OD, l.material, sys, l.levelStatus === 'provisional' ? 'provisional' : 'source');
    if (l.kind === 'stack') {     // vent cowl above the roof
      const top = pts[pts.length - 1];
      const cow = C.fixtures.ventCowl;
      grp.add(disk(top.clone().add(new THREE.Vector3(0, 0.02, 0)), OD / 2 * cow.D_ratio, 0.025, pipeMat(l.material, sys, 'source')));
      grp.add(cylBetween(top.clone().add(new THREE.Vector3(0, 0.045, 0)), top.clone().add(new THREE.Vector3(0, cow.h_m, 0)), OD / 2 * cow.D_ratio * 0.95, pipeMat(l.material, sys, 'source')));
      label(grp, top.clone().add(new THREE.Vector3(0, 0.35, 0)), `צ.א ${l.stack}`, 'stack');
    }
    if (l.kind === 'downpipe') {  // shoe at the bottom
      const b = pts[pts.length - 1], dir = new THREE.Vector3(1, -0.6, 0).normalize();
      grp.add(cylBetween(b, b.clone().addScaledVector(dir, C.fixtures.downpipeShoe.len_m), OD / 2 * 1.05, pipeMat(l.material, sys, 'source')));
    }
    const floor = l.kind === 'stack' ? 'ground' : l.floor;
    const rows = [['מערכת', D.systems[sys]?.label || sys], ['קוטר וחומר', `ø${l.D_mm} · ${l.material}`],
      ['מסלול', l.pts3d.map(p => p[2] != null ? coords.fmtRel(p[2] - H0) : 'פני קרקע').join(' → ')],
      ['מעמד המפלס', `${statusTxt(l.levelStatus)} – ${l.levelRule || ''}`], ['אביזרים', Object.entries(tally).map(([k, v]) => `${v}× ${k}`).join(' · ') || '—']];
    if (l.notes?.length) rows.push(['הסטות', l.notes.join(' · ')]);
    if (l.ends) rows.push(['מאיפה → לאן', l.ends.map(title).join(' → ')]);
    if (findingsOf[l.id]) rows.push(['ממצאים', findingsOf[l.id].join(', ')]);
    add(grp, { floor, system: SYS_TAG[sys], stage: l.kind === 'stack' ? 'walls' : 'finishes', layer: SYS_LAYER[sys] },
      { name: l.title || l.id, kind: 'plLine', netId: l.id, plFloor: floor, rows, source: l.source, note: l.levelStatus === 'provisional' ? `מפלסים זמניים: ${l.levelRule}` : null });
  }

  // ---- nodes
  const fl = (n) => H0 + (FLOOR_REL[n.floor] ?? 0);
  const P3 = (n, H) => coords.toLocal(n.E, n.N, H);
  const chambersInfo = [];
  for (const n of N.nodes) {
    const grp = new THREE.Group();
    let layer = 'plSewage', sys = 'sewage', rows = [['סוג', n.title], ['ITM', coords.fmtEN(n.E, n.N)]], floor = n.floor, extraNote = null;
    const h = nodeH[n.id];
    const tail = (top, OD = 0.05, matl = pipeMat('HDPE', 'sewage', 'source')) => { if (h != null && top - h > 0.05) grp.add(cylBetween(P3(n, h), P3(n, top), OD / 2, matl)); };
    switch (n.kind) {
      case 'sewerChamber': case 'municipalManhole': case 'pumpChamber': {
        layer = 'plChambers';
        const info = buildChamber(grp, n);
        rows = rows.concat(info.rows); chambersInfo.push(info);
        floor = n.floor;
        break;
      }
      case 'floorDrain': {
        const big = n.title.includes('8/4'); const f = C.fixtures[big ? 'floorDrain8' : 'floorDrain'];
        const top = n.floor === 'unit' ? H0 - 1.5 : fl(n);
        tail(top - 0.02, big ? 0.11 : 0.05);
        grp.add(box(P3(n, top - 0.06), f.body_m, 0.1, f.body_m, pipeMat('HDPE', 'sewage', 'source')));
        grp.add(box(P3(n, top - 0.005), f.grate_m, 0.01, f.grate_m, steel));
        rows.push(['מפלס רשת', fmtH(top)]); break;
      }
      case 'inspectionBox': case 'dropInspectionBox': {
        const f = C.fixtures[n.kind]; const top = fl(n);
        tail(top - f.size_m, 0.11);
        grp.add(box(P3(n, top - f.size_m / 2 - 0.01), f.size_m, f.size_m, f.size_m, pipeMat('HDPE', 'sewage', 'source')));
        grp.add(disk(P3(n, top - 0.012), f.lid_m / 2, 0.012, steel));
        rows.push(['מכסה בגובה הרצפה', fmtH(top)]); break;
      }
      case 'drumTrap': { const f = C.fixtures.drumTrap; const top = fl(n); tail(top - f.H_m); grp.add(disk(P3(n, top - f.H_m), f.D_m / 2, f.H_m - 0.01, pipeMat('HDPE', 'sewage', 'source'))); grp.add(disk(P3(n, top - 0.012), f.D_m / 2 * 0.8, 0.012, steel)); break; }
      case 'wye45': case 'tee': case 'joint': {
        if (h != null) grp.add(sphere(P3(n, h), 0.065, pipeMat('HDPE', 'sewage', 'source'), 14));
        rows.push(['מפלס', fmtH(h)]); if (n.gap_m) rows.push(['רווח בשרטוט', `${n.gap_m} מ'`]); break;
      }
      case 'wc': { const top = fl(n); tail(top, 0.11); const f = C.fixtures.wcConnector; if (h != null) grp.add(collar(P3(n, top - f.len_m / 2), new THREE.Vector3(0, 1, 0), f.OD_m / 2, f.len_m, pipeMat('HDPE', 'sewage', 'source'))); rows.push(['חיבור', 'מחבר אסלה ø110 עד פני הרצפה']); break; }
      case 'basin': case 'sink': case 'shower': case 'washer': { const top = fl(n); tail(top); if (h != null) grp.add(collar(P3(n, top - 0.03), new THREE.Vector3(0, 1, 0), 0.032, 0.06, pipeMat('HDPE', 'sewage', 'source'))); rows.push(['חיבור', 'יציאת ø50 עד פני הרצפה (גובה היציאה בקיר לפי הקבועה – לא בתוכנית)']); break; }
      case 'stack': continue;      // drawn as a 3D line
      case 'openEnd': case 'designEnd': {
        layer = n.id.startsWith('WJ') || n.title.includes('מים') ? 'plCold' : 'plSewage'; sys = layer === 'plCold' ? 'cold' : 'sewage';
        const H = h ?? fl(n);
        grp.add(sphere(P3(n, H), 0.045, redCap, 14));
        label(grp, P3(n, H + 0.35), n.kind === 'designEnd' ? 'סוף תכנון' : 'קצה פתוח', 'end');
        extraNote = n.kind === 'designEnd' ? 'הקו נגמר כאן בתוכנית – אין המשך. לא הומצא חיבור.' : 'קצה קו בלי חיבור מוגדר';
        floor = n.floor === 'site' ? 'site' : n.floor; break;
      }
      case 'waterJoint': {
        layer = 'plCold'; sys = 'cold';
        if (h != null) { const p = P3(n, h); grp.add(collar(p, new THREE.Vector3(1, 0, 0), 0.03, 0.06, brass)); for (const d of [[1, 0, 0], [-1, 0, 0], [0, 0, 1]]) grp.add(hexNut(p.clone().addScaledVector(new THREE.Vector3(...d), 0.04), new THREE.Vector3(...d), 0.045, 0.02, brass)); }
        floor = 'site'; break;
      }
      case 'waterMeter': {      // per the consultant's detail "מע' מדידת מים": niche in the boundary wall, risers in PVC ø4" sleeves
        layer = 'plCold'; sys = 'cold'; floor = 'site';
        const f = C.fixtures.waterMeter, d = n.detail; const g0 = groundAt(n.E, n.N), H = g0 + d.axisH_m;
        const ax = new THREE.Vector3(d.axis[0], 0, -d.axis[1]).normalize(), back = new THREE.Vector3(d.back[0], 0, -d.back[1]).normalize();
        const c = P3(n, H), half = f.assemblyLen_m / 2, mpex = pipeMat('PEX', 'cold', 'source');
        const ends = [-1, 1].map(s => c.clone().addScaledVector(ax, s * half));
        grp.add(cylBetween(ends[0], ends[1], 0.017, brass, 14));
        grp.add(box(c, f.body_m[0], f.body_m[1], f.body_m[2], mat('meter', () => std('#2c5aa0', 0.4, 0.2)), Math.atan2(-ax.z, ax.x)));
        grp.add(disk(c.clone().add(new THREE.Vector3(0, f.body_m[1] / 2, 0)), 0.045, 0.012, mat('glass', () => std('#dfe8f2', 0.1, 0.1, { transparent: true, opacity: 0.7 }))));
        for (const [k, s] of [[0, -1], [1, 1]]) {
          const v = c.clone().addScaledVector(ax, s * (half - 0.09));
          grp.add(collar(v, ax, 0.024, 0.07, brass));                                                          // angle valve (ברז אלכסוני)
          grp.add(box(v.clone().add(new THREE.Vector3(0, 0.05, 0)), 0.09, 0.012, 0.015, mat('lever', () => std('#d32f2f', 0.5)), Math.atan2(-ax.z, ax.x)));
          const foot = P3(n, g0 - 0.5 - 0.016).addScaledVector(ax, s * half);                                   // to the depth of the consultant's lines
          grp.add(cylBetween(foot, ends[k], 0.016, k ? mpex : steel, 14));
          grp.add(cylBetween(P3(n, g0 - 0.30).addScaledVector(ax, s * half), P3(n, g0 + d.sleeveTop_m).addScaledVector(ax, s * half), d.sleeve_mm / 2000, mat('pvcSleeve', () => std('#9e9e9e', 0.6, 0, { transparent: true, opacity: 0.55 })), 18, true));
        }
        grp.add(collar(c.clone().addScaledVector(ax, half - 0.17), ax, 0.022, 0.06, mat('check', () => std('#5c6b73', 0.4, 0.6))));    // check valve
        const nb = P3(n, g0 + d.nicheH_m / 2).addScaledVector(back, 0.14);
        grp.add(box(nb, d.nicheW_m + 0.2, d.nicheH_m + 0.1, 0.06, concrete, Math.atan2(-ax.z, ax.x)));         // back of the niche
        rows.push(['הרכב (לפי הפרט)', 'עולה מהקו העירוני בשרוול PVC ø4" · ברז אלכסוני 1" · מד מים 3/4" של התאגיד · אל-חוזר קלפה · ברז אלכסוני 1" · מעבר פלדה ל-PEX ø32 יורד בשרוול']);
        rows.push(['גובה', `ציר המונה ${d.axisH_m.toFixed(2)} מעל הפיתוח, גומחה ${Math.round(d.nicheW_m * 100)} ס"מ (לפי מידות הפרט; הפרט לא בקנה מידה)`]);
        rows.push(['מצב', 'מיקום לפי חץ ההערה בתוכנית; "נא לוודא מיקום טרם הביצוע". הקטעים אל קצה ההכנה ואל תחילת הקו – בהצעה']);
        break;
      }
      case 'meterOutlet': case 'kitchenPoint': case 'riser': case 'gardenTap': case 'poolFill': {
        layer = 'plCold'; sys = 'cold'; floor = n.kind === 'riser' || n.kind === 'kitchenPoint' ? 'ground' : 'site';
        const mpex = pipeMat('PEX', 'cold', 'source');
        if (n.kind === 'gardenTap' || n.kind === 'poolFill') {
          const top = groundAt(n.E, n.N) + C.fixtures.gardenTap.height_m;
          tail(top, 0.025, mpex);
          const p = P3(n, top); grp.add(collar(p, new THREE.Vector3(0, 1, 0), 0.016, 0.05, brass));
          grp.add(cylBetween(p, p.clone().add(new THREE.Vector3(0.09, -0.04, 0)), 0.011, brass));
          grp.add(disk(p.clone().add(new THREE.Vector3(0, 0.03, 0)), 0.03, 0.01, mat('handle', () => std('#c62828', 0.5))));
          if (n.kind === 'poolFill') grp.add(box(P3(n, top - 0.25), 0.16, 0.12, 0.09, mat('rpz', () => std('#7b8a8f', 0.4, 0.6))));
          rows.push(['גובה הברז', `${C.fixtures.gardenTap.height_m.toFixed(2)} מ' מעל הפיתוח (טיפוסי – לא בתוכנית)`]);
        } else if (n.kind === 'riser') {
          const top = n.title.includes('דוד') ? H0 + FLOOR_REL.roof + 0.1 : H0 + FLOOR_REL.first + 0.3;
          tail(top, 0.032, mpex);
          if (!n.title.includes('דוד')) { grp.add(sphere(P3(n, top), 0.03, redCap, 12)); label(grp, P3(n, top + 0.3), 'סוף תכנון – קומה א\'', 'end'); extraNote = 'העולה מגיע לקומה א\'. אין בתוכנית קווים בקומה א\'.'; }
          rows.push(['גובה', `${fmtH(h)} → ${fmtH(top)}`]);
        } else if (n.kind === 'kitchenPoint') {
          const top = fl(n) + 0.5; tail(top, 0.02, mpex); grp.add(sphere(P3(n, top), 0.025, redCap, 12));
          label(grp, P3(n, top + 0.25), 'נקודת מים – מטבח', 'end'); extraNote = 'הקו מגיע לאזור הכיור ונגמר; גובה נקודה, ברז ניתוק וחיבור חם לא בתוכנית.';
        }
        break;
      }
      case 'heater': {
        layer = 'plHot'; sys = 'hot'; floor = 'roof';
        const f = C.fixtures.heater; const base = H0 + FLOOR_REL.roof;
        const p = P3(n, base + 0.6);
        const tank = cylBetween(p.clone().add(new THREE.Vector3(-f.L_m / 2, 0, 0)), p.clone().add(new THREE.Vector3(f.L_m / 2, 0, 0)), f.D_m / 2, mat('heater', () => std('#e8e8e8', 0.4, 0.3)));
        grp.add(tank);
        const panel = box(P3(n, base + 0.55).add(new THREE.Vector3(0, 0, 1.0)), f.collector_m[0], 0.06, f.collector_m[1], mat('collector', () => std('#1b2a44', 0.2, 0.6)));
        panel.rotation.x = -0.6; grp.add(panel);
        extraNote = 'גוף סמלי בלבד: בתוכנית רק "מיקום דוד וקולטים" – אין נפח, מספר קולטים או מידות. צנרת הנחושת בין הדוד לקולטים (הערה 14) לא משורטטת.';
        break;
      }
      case 'hotManifold': {
        layer = 'plHot'; sys = 'hot'; floor = 'roof';
        const f = C.fixtures.manifold; const p = P3(n, H0 + FLOOR_REL.roof + 0.25);
        grp.add(cylBetween(p.clone().add(new THREE.Vector3(0, 0, -f.len_m / 2)), p.clone().add(new THREE.Vector3(0, 0, f.len_m / 2)), f.D_m / 2, brass));
        for (let i = 0; i < 4; i++) grp.add(hexNut(p.clone().add(new THREE.Vector3(-0.04, 0, -f.len_m / 2 + 0.08 + i * 0.1)), new THREE.Vector3(-1, 0, 0), 0.03, 0.03, brass));
        extraNote = 'מחלק מים חמים בקצה המערבי של הגג. אין יציאות משורטטות ממנו לקומות.';
        break;
      }
      case 'roofDrain': case 'downpipe': case 'downpipeShoe': case 'soakawayPit': {
        layer = 'plRain'; sys = 'rain';
        if (n.kind === 'roofDrain') { const top = n.floor === 'roof' ? H0 + FLOOR_REL.roof : H0 + 3.83; grp.add(disk(P3(n, top - 0.01), C.fixtures.roofDrain.D_m / 2, 0.03, steel)); }
        else if (n.kind === 'soakawayPit') {
          const r_ = n.D_m / 2; grp.add(disk(P3(n, n.TL - 0.08), r_ + 0.08, 0.08, concrete)); grp.add(disk(P3(n, n.TL - 0.005), r_ * 0.85, 0.02, iron));
          label(grp, P3(n, n.TL + 0.4), 'בור חלחול', 'rain'); extraNote = 'מיקום בלבד – אין קווים אליו ואין עומק/קוטר בתוכנית.';
          floor = 'site';
        } else continue;
        break;
      }
      case 'poolOverflow': { grp.add(sphere(P3(n, h ?? fl(n)), 0.06, redCap, 12)); extraNote = 'מוצא מחדר המכונות / בור האיזון – מפלס לא נתון.'; break; }
      case 'pumpRiser': continue;
      default: if (h == null) continue; grp.add(sphere(P3(n, h), 0.04, pipeMat('HDPE', 'sewage', 'source'), 10));
    }
    if (!grp.children.length) continue;
    if (n.TL != null && !rows.some(r => r[0].startsWith('T.L'))) rows.push(['T.L', fmtH(n.TL)]);
    if (findingsOf[n.id]) rows.push(['ממצאים', findingsOf[n.id].join(', ')]);
    add(grp, { floor, system: SYS_TAG[sys] || 'sewage', stage: stageOf(floor, sys), layer },
      { name: `${n.title} (${n.id})`, kind: 'plNode', netId: n.id, plFloor: n.floor === 'site' ? 'site' : n.floor, rows, source: n.source, note: extraNote, status: n.status });
  }

  // ---- precast chamber: base, rings, cover slab, adjustment rings, frame + cover, benching, connectors, steps
  function buildChamber(grp, n) {
    const K = C.chambers, Dm = n.D_m, w = K.rings[String(Dm)]?.wall ?? 0.1, rIn = Dm / 2, rOut = rIn + w;
    const baseTop = n.IL - 0.10;
    const opening = K.opening_m[String(Dm)] ?? 0.6;
    const avail = n.TL - K.frame.height_m - K.topSlabThickness_m - baseTop;
    const rings = []; let sum = 0;
    for (const hh of K.ringHeights_m) while (sum + hh <= avail + 1e-6 && avail - (sum + hh) >= -1e-6) { rings.push(hh); sum += hh; }
    let rest = avail - sum; const adj = [];
    for (const a of [...K.adjustRings_m].sort((x, y) => y - x)) while (rest >= a - 1e-6) { adj.push(a); rest -= a; }
    // base slab + benching with the flow channel
    grp.add(disk(P3(n, baseTop - K.baseThickness_m), rOut, K.baseThickness_m, concrete));
    const out = (runsAt[n.id] || []).find(r => r.from === n.id);
    const odOut = out ? odOf(out) : 0.16;
    grp.add(disk(P3(n, baseTop), rIn, 0.10 + odOut * 0.5, concrete));
    if (out) {
      const q = out.pts[1] || out.pts[0], dir = new THREE.Vector3(q[0] - n.E, 0, -(q[1] - n.N)).normalize();
      const c = P3(n, n.IL + odOut / 2);
      grp.add(cylBetween(c.clone().addScaledVector(dir, -rIn * 0.95), c.clone().addScaledVector(dir, rIn * 0.95), odOut / 2 * 0.9, channelMat));
    }
    // rings (cut-away sector towards the default camera)
    let z = baseTop; const yaw = -Math.PI / 2;   // cut-away sector towards south-west (default camera)
    for (const hh of rings) { const m = ring(P3(n, z), rIn, rOut, hh - 0.004, concrete, 0.25); m.rotation.y = yaw; grp.add(m); z += hh; }
    const slab = ring(P3(n, z), opening / 2, rOut, K.topSlabThickness_m, concrete, 0.25); slab.rotation.y = yaw; grp.add(slab); z += K.topSlabThickness_m;
    for (const a of adj) { const m = ring(P3(n, z), opening / 2, opening / 2 + 0.1, a - 0.004, concrete, 0); grp.add(m); z += a; }
    // frame + cover at T.L
    const fr = ring(P3(n, n.TL - K.frame.height_m), opening / 2 - 0.02, opening / 2 + K.frame.flange_m, K.frame.height_m, iron, 0); grp.add(fr);
    const cov = disk(P3(n, n.TL - 0.03), opening / 2 - 0.025, 0.028, iron); grp.add(cov);
    // steps (consultant note 7: chambers deeper than 1.25 m)
    const depth = n.TL - n.IL;
    if (depth > K.stepsWhenDeeper_m) {
      for (let s = n.TL - 0.5; s > n.IL + 0.3; s -= K.stepSpacing_m) {
        const p = P3(n, s).add(new THREE.Vector3(Math.cos(yaw + 0.6) * (rIn - 0.08), 0, Math.sin(yaw + 0.6) * (rIn - 0.08)));
        grp.add(cylBetween(p.clone().add(new THREE.Vector3(-0.15, 0, 0)), p.clone().add(new THREE.Vector3(0.15, 0, 0)), 0.013, mat('step', () => std('#f2a900', 0.6))));
      }
    }
    // connectors (rubber manhole seals) for each pipe entering / leaving
    for (const r of runsAt[n.id] || []) {
      const atStart = r.from === n.id; const q = atStart ? (r.pts[1] || r.pts[0]) : (r.pts[r.pts.length - 2] || r.pts[0]);
      const dir = new THREE.Vector3(q[0] - n.E, 0, -(q[1] - n.N)).normalize();
      const OD = odOf(r);
      const H = atStart ? (r.ILup ?? n.IL) + OD / 2 : (r.ILdown ?? n.IL) + OD / 2;
      const p = P3(n, H).addScaledVector(dir, rIn + w / 2);
      grp.add(seal(p, dir, OD / 2 + K.connector.OD_extra_m / 2, K.connector.width_m / 2, rubber));
    }
    const lbl = n.kind === 'pumpChamber' ? `${n.id} תא שאיבה ø${Math.round(Dm * 100)}` : `שוחה ${n.id.slice(2)} · ø${Math.round(Dm * 100)}`;
    label(grp, P3(n, n.TL + 0.45), `${lbl} · T.L ${n.TL.toFixed(2)} · I.L ${n.IL.toFixed(2)}`, 'chamber');
    const cover = n.kind === 'municipalManhole' ? K.coverClass.street : K.coverClass.yard;
    return {
      id: n.id, rings, adj, rest,
      rows: [['קוטר פנימי / דופן', `ø${Math.round(Dm * 100)} / ${Math.round(w * 100)} ס"מ (חוליות טרומיות)`], ['T.L (מכסה)', fmtH(n.TL)], ['I.L (תחתית)', fmtH(n.IL)], ['עומק', `${depth.toFixed(2)} מ'`],
        ['הרכב (קטלוג)', `בסיס ${Math.round(K.baseThickness_m * 100)} · חוליות ${rings.map(x => Math.round(x * 100)).join('+') || '—'} · תקרה ${Math.round(K.topSlabThickness_m * 100)} · טבעות הגבהה ${adj.map(x => Math.round(x * 100)).join('+') || '—'}${rest > 0.004 ? ` · מצע טיט ${Math.round(rest * 100)} ס"מ` : ''} · מסגרת ${Math.round(K.frame.height_m * 100)}`],
        ['מכסה', `ב.י. ø${Math.round(opening * 100)} דרג ${cover}`], ['מדרכי רגל', depth > K.stepsWhenDeeper_m ? 'כן (עומק מעל 1.25 – הערה 7)' : 'לא נדרש'],
        ['כניסות / יציאות', (runsAt[n.id] || []).map(r => `${r.id} ø${r.D_mm}${r.to === n.id && r.ILdown != null ? ` @${r.ILdown.toFixed(2)}` : ''}`).join(' · ')]],
    };
  }

  // ---- findings markers
  const findingItems = [];
  for (const f of N.findings) {
    const grp = new THREE.Group(); const col = D.severity[f.severity].color;
    const p = coords.toLocal(f.at[0], f.at[1], f.at[2]);
    const mk = new THREE.Mesh(new THREE.OctahedronGeometry(D.markerRadius_m), mat(`sev:${f.severity}`, () => new THREE.MeshStandardMaterial({ color: col, emissive: new THREE.Color(col), emissiveIntensity: 0.6, roughness: 0.4 })));
    mk.position.copy(p).add(new THREE.Vector3(0, 0.25, 0)); grp.add(mk);
    const stem = new THREE.Line(new THREE.BufferGeometry().setFromPoints([p, mk.position]), new THREE.LineBasicMaterial({ color: col }));
    stem.userData.annotation = true; grp.add(stem);
    label(grp, mk.position.clone().add(new THREE.Vector3(0, 0.22, 0)), f.id, `sev-${f.severity}`);
    const floor = f.at[2] - H0 > 5 ? 'roof' : f.at[2] - H0 > 2.5 ? 'first' : f.at[2] - H0 < -1.8 ? 'unit' : 'ground';
    const it = add(grp, { floor, system: 'plumbing', stage: 'existing', layer: 'plFindings' },
      { name: `${f.id} · ${f.title}`, kind: 'plFinding', plFloor: floor, plSeverity: f.severity,
        rows: [['חומרה', D.severity[f.severity].label], ['תחום', f.category], ['ממצא', f.text], ['הצעה', f.proposal || '—'], ['רכיבים', f.elements.join(', ')], ['ITM / רום', `${coords.fmtEN(f.at[0], f.at[1])} · ${fmtH(f.at[2])}`]],
        note: f.proposal ? 'הצעה בלבד – לא שונה דבר במודל עד אישורך' : null, source: 'tools/plumbing/build.py – בדיקה מול נתוני השלד והתוכניות' });
    it.meta.finding = f; findingItems.push(it);
  }

  // ---- design proposal (data/plumbing/proposal.json) – separate items, shown with the "with proposal" switch
  const proposal = data.plumbingProposal ? buildProposal({ data, coords, scene, registry, C, D, H0, mat, std, pipeMat, pipe, label, add, odOf, brass, rubber, iron, steel, concrete, redCap, ground, buildChamber }) : null;
  const proposal2 = data.plumbingProposal ? buildProposal2({ data, coords, C, H0, mat, std, pipeMat, pipe, label, add, brass, steel, iron, concrete, redCap, ground, buildChamber }) : null;
  const superseded = new Set([...(proposal?.superseded || []), ...(proposal2?.superseded || [])]);

  const api = {
    items, findingItems, network: N, totalLen, chambersInfo, proposal,
    attach(app) {
      this.app = app;
      const ctl = buildPanel(app, this);
      this.panel = () => ctl.panel();
      this.pipeView = ctl.pipeView;
      // first open of this version: show every pipe right away (the pipes are underground / inside the structure and
      // invisible in the default view). Once per version per browser; skipped in automated tests (navigator.webdriver).
      const FLAG = 'house3d-plumbing-pipeview-v4';
      let seen = null; try { seen = localStorage.getItem(FLAG); } catch (e) { /* private mode */ }
      // no automatic pipe view any more: it hid the skeleton, and the saved view (js/tools/prefs.js) then kept it hidden
      // on every later open (Avihai 08.11: "why can't I see the model?"). The orange button shows / restores it.
      if (false && !seen && !navigator.webdriver) setTimeout(() => {
        ctl.pipeView(); try { localStorage.setItem(FLAG, '1'); } catch (e) { /* private mode */ }
        const t = document.createElement('div'); t.className = 'pl-toast';
        t.textContent = 'מוצגת כל הצנרת: קרקע שקופה, בלי שלד וסביבה. ↶ (בטל) מחזיר לתצוגה הרגילה; הכפתור הכתום מחזיר לכאן.';
        (document.getElementById('viewport') || document.body).append(t); setTimeout(() => t.remove(), 9000);
      }, 800);
      // module filters (floor, severity, x-ray) applied after the registry's own visibility rules
      const terrain = app.registry.items.filter(i => i.meta.kind === 'terrain');
      app.registry.onChange(() => {
        const s = app.store.get().plumbing || {};
        const floors = s.floors || {}, sev = s.severity || {};
        for (const it of items) {
          if (!it.object.visible) continue;
          if (floors[it.meta.plFloor] === false) it.object.visible = false;
          if (it.meta.plSeverity && sev[it.meta.plSeverity] === false) it.object.visible = false;
          if (it.meta.plProposal && !s.proposal) it.object.visible = false;
          if (s.proposal && it.meta.netId && superseded.has(it.meta.netId)) it.object.visible = false;
          if (it.meta.rainAlt && it.meta.rainAlt !== (s.rainAlt || 1)) it.object.visible = false;
        }
        const x = !!s.xray;
        for (const t of terrain) t.object.traverse(o => {
          if (!o.material) return;
          for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
            if (x) { m.userData.plX ??= { op: m.opacity, tr: m.transparent, dw: m.depthWrite }; m.opacity = Math.min(m.opacity, D.xrayTerrainOpacity); m.transparent = true; m.depthWrite = false; }
            else if (m.userData.plX) { Object.assign(m, { opacity: m.userData.plX.op, transparent: m.userData.plX.tr, depthWrite: m.userData.plX.dw }); delete m.userData.plX; }
            m.needsUpdate = true;
          }
        });
      });
    },
  };
  return api;
}

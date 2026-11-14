import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { makeInterpolator } from './tin.js';
import { regionMesh } from './terrain.js';

// Street in front of lot 5187 (רחוב משולב 960) from data/site/front-street.json (tools/extract_front_street.py):
// paving zones of the typical section, the DWG drainage channel and planting islands, the edge stone on the lot line,
// and – for comparison – the street line of the front-wall elevation with its written levels.
// Heights: the buyer's-map planned street (contours + spot levels, DWG); outside the map frame the derived
// (provisional) street levels of the environment module. No dimension is written here.
export function buildFrontStreet(ctx) {
  const { data, coords, registry, scene, display, materials, ground, lineMats } = ctx;
  const F = data.frontStreet; if (!F) return null;
  const D = display.frontStreet, T = display.terrain;
  const tags = (layer) => ({ floor: 'site', system: 'site', stage: 'existing', layer });
  const ctrl = [];
  for (const c of data.street.contours) for (const [x, y] of c.points) ctrl.push({ x, y, z: c.z });
  for (const s of data.heights.streetSpots) ctrl.push({ x: s.at[0], y: s.at[1], z: s.z });
  const interp = makeInterpolator(ctrl);
  const dCtrl = (data.envStreets?.derivedHeightControl?.points || []).map(p => ({ x: p.E, y: p.N, z: p.z })).concat(ctrl);
  const dInterp = makeInterpolator(dCtrl);
  const frame = data.envStreets.frameITM, inFrame = (E, N) => pin(E, N, frame);
  // owner decision (F.ownerLevels): + (architect line − DWG) on the lot line, fading linearly to 0 at the far lot line
  const OL = F.ownerLevels, fl0 = F.frontLine.points, sOff = F.frontLine.s2457_on_line;
  const flCum = [0]; for (let i = 1; i < fl0.length; i++) flCum.push(flCum[i - 1] + Math.hypot(fl0[i][0] - fl0[i - 1][0], fl0[i][1] - fl0[i - 1][1]));
  const project = (E, N) => {   // -> [s from 2457, distance toward the street]
    let best = null;
    for (let i = 0; i < fl0.length - 1; i++) {
      const [ax, ay] = fl0[i], [bx, by] = fl0[i + 1], dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
      const t = Math.max(0, Math.min(1, ((E - ax) * dx + (N - ay) * dy) / L2)), px = ax + dx * t, py = ay + dy * t, d2 = (E - px) ** 2 + (N - py) ** 2;
      if (!best || d2 < best.d2) { const L = Math.sqrt(L2); best = { d2, s: flCum[i] + t * L - sOff, side: ((E - ax) * dy - (N - ay) * dx) / L }; }
    }
    return [best.s, Math.max(0, best.side)];
  };
  const deltaAt = (s) => { const P = OL.points; if (s <= P[0].s) return P[0].delta; if (s >= P[P.length - 1].s) return P[P.length - 1].delta;
    let i = 1; while (P[i].s < s) i++; const f = (s - P[i - 1].s) / (P[i].s - P[i - 1].s); return P[i - 1].delta + (P[i].delta - P[i - 1].delta) * f; };
  const lift = (f) => !OL ? f : (E, N) => { const [s, d] = project(E, N); return f(E, N) + deltaAt(s) * Math.max(0, 1 - d / OL.taperWidth_m); };
  const interpO = lift(interp), dInterpO = lift(dInterp);
  const hAt = (E, N) => (inFrame(E, N) ? interpO(E, N) : dInterpO(E, N));
  const X = (E) => E - coords.E0, Z = (N) => -(N - coords.N0), Y = (H) => H - coords.H0;
  // pavers laid along the street: rotate the metre UVs by the street direction
  const ang = -F.displayAngle_deg * Math.PI / 180, ca = Math.cos(ang), sa = Math.sin(ang);
  const alongStreet = (g) => { const uv = g.attributes.uv; for (let i = 0; i < uv.count; i++) { const u = uv.getX(i), v = uv.getY(i); uv.setXY(i, u * ca - v * sa, u * sa + v * ca); } return g; };
  const top = (ring, f, lift = 0) => { const g = regionMesh(ring, f, coords, materials.get('envFsWalk'), null, T, []).children[0].geometry; g.translate(0, lift, 0); return alongStreet(g); };
  const fn = (hs) => (hs === 'derived' ? dInterpO : interpO);
  const add = (geos, mat, layer, meta, cast = false) => {
    const gs = geos.filter(Boolean); if (!gs.length) return null;
    const m = new THREE.Mesh(mergeGeometries(gs, false), mat); m.receiveShadow = true; m.castShadow = cast;
    registry.add(m, tags(layer), meta); scene.add(m); return m;
  };
  const sec = F.section, ch = sec.channel;
  const secRows = [
    ['חתך טיפוסי', `${sec.name}: ${sec.zones.map(z => `${z.label} ${z.width_m.toFixed(1)}`).join(' | ')} = ${sec.total_m.toFixed(1)} מ'`],
    ['רוחב מדוד מול 5187', `${sec.measuredWidth_m.toFixed(3)} מ' (DWG, קו מגרש ← קו מגרש)`],
    ['תעלת ניקוז', `${ch.inner_m.toFixed(2)}–${ch.outer_m.toFixed(2)} מ' מקו המגרש (מרכז ${ch.centre_m.toFixed(2)}; בחתך ${ch.sectionCentre_m.toFixed(2)})`],
    ['שיפוע רוחבי', `בחתך: ${sec.crossSlope}; במפה למשתכן (קו מגרש ← תעלה): ${Math.min(...sec.crossSlopeDWG.map(s => s.slope_pct)).toFixed(1)}–${Math.max(...sec.crossSlopeDWG.map(s => s.slope_pct)).toFixed(1)}%`],
  ];

  // ---------------- paving zones ----------------
  const byMat = {};
  for (const z of F.zones) (byMat[z.material + '|' + z.heights] ||= []).push(z);
  for (const [key, zs] of Object.entries(byMat)) {
    const [mat, hs] = key.split('|');
    const geos = zs.map(z => top(z.ring, fn(hs), D.paveLift_m));
    const labels = [...new Set(zs.map(z => z.label))];
    add(geos, materials.get(mat), 'frontStreet', {
      name: `רחוב בחזית – ${labels.join(' / ')}${hs === 'derived' ? ' (גובה משוער)' : ''}`, kind: 'street', role: 'frontStreet', provisional: hs === 'derived' || !!OL,
      rows: [...zs.map(z => [z.label, `${z.from_m.toFixed(2)}–${z.to_m.toFixed(2)} מ' מקו המגרש · ${z.area_m2.toFixed(1)} מ"ר`]),
        ['גבהים', (hs === 'derived' ? 'בסיס משוער – מחוץ למסגרת המפה למשתכן (E1)' : 'בסיס: המפה למשתכן – קווי גובה מתוכננים + "גובה מתוכנן מדרכה"') + (OL ? `; מוגבה לפי קו האדריכל בחזית (עד ${Math.round(Math.max(...OL.points.map(p => p.delta)) * 100)} ס"מ בקו המגרש, יורד ל-0 בצד הנגדי)` : '')],
        ...(OL ? [['החלטה', OL.decision]] : []),
        ['ריצוף', mat === 'envFsLane' ? 'אבן משתלבת "מלבן" שחור 20/8/10 (נספח 003 פרט 14)' : F.materials.street], ...secRows],
      note: [hs === 'derived' ? 'גובה משוער – מסומן זמני' : null, OL ? 'מפלס לפי קו האדריכל – לבדיקה מול האדריכל (FS1)' : null].filter(Boolean).join(' · ') || null, source: zs[0].source,
    });
  }
  // ---------------- drainage channel ----------------
  add(F.gutter.map(g => top(g.ring, fn(g.heights), D.gutterLift_m)), materials.get('envFsGutter'), 'frontStreet', {
    name: 'תעלת ניקוז – אבן תעלה דו-שיפועית 30/10/50', kind: 'gutter',
    rows: [['מיקום', `${ch.inner_m.toFixed(2)}–${ch.outer_m.toFixed(2)} מ' מקו המגרש, רוחב ${ch.width_m.toFixed(2)}`], ['חומר', F.materials.gutter],
      ['צורה', 'מוצגת שטוחה – עומק ה-V לא כתוב במקורות']],
    source: ch.source,
  });
  // ---------------- planting islands ----------------
  add(F.islands.map(g => top(g.ring, fn(g.heights), D.islandLift_m)), materials.get('envFsIsland'), 'frontStreet', {
    name: 'איי שתילה (מפה למשתכן)', kind: 'island',
    rows: [['שטח', `${F.islands.reduce((s, g) => s + Math.abs(area(g.ring)), 0).toFixed(1)} מ"ר (בתחום הרצועה)`], ['עצים / אבן שפה', 'לא כתובים במקורות – לא שורטטו']],
    source: `${F.section.channel.source.split(' layer')[0]} layer HW-CURB-ILND`,
  });
  // ---------------- edge stone on the lot line ----------------
  const E = F.edgeStone, eg = [];
  for (let i = 0; i < E.line.length - 1; i++) {
    const a = E.line[i], b = E.line[i + 1], dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy);
    const nx = dy / L, ny = -dx / L;                         // toward the street
    const cx = (a[0] + b[0]) / 2 + nx * E.width_m / 2, cy = (a[1] + b[1]) / 2 + ny * E.width_m / 2;
    const zt = hAt(cx, cy) + E.reveal_m + D.paveLift_m + D.edgeAbovePave_m;
    const g = new THREE.BoxGeometry(L + 0.002, E.height_m, E.width_m);
    g.rotateY(Math.atan2(dy, dx)); g.translate(X(cx), Y(zt - E.height_m / 2), Z(cy)); eg.push(g);
  }
  add(eg, materials.get('envFsEdge'), 'frontStreet', {
    name: `אבן גן בקו המגרש – ${E.product}`, kind: 'edge', provisional: E.status === 'provisional',
    rows: [['מוצר', E.product], ['מיקום', 'לאורך קו המגרש, בצד הרחוב'], ['בליטה מעל הריצוף', `${(E.reveal_m * 100).toFixed(0)} ס"מ – לא כתוב (זמני)`]],
    note: E.why, source: F.materials.source,
  }, true);
  // ---------------- skirt: the paving edge down to the ground below (strip outline) ----------------
  const sk = regionMesh(F.outline, hAt, coords, materials.get('envFsWalk'), materials.get('envFsBase'), T, []);
  sk.remove(sk.children[0]);
  registry.add(sk, tags('frontStreet'), { name: 'רחוב בחזית – שולי הריצוף', kind: 'street', pickable: false });
  scene.add(sk);
  ground.add(F.outline, hAt, 'env', 'front-street');

  // ---------------- elevation street line + written levels (comparison) ----------------
  const fl = F.frontLine.points, s0 = F.frontLine.s2457_on_line;
  const cum = [0]; for (let i = 1; i < fl.length; i++) cum.push(cum[i - 1] + Math.hypot(fl[i][0] - fl[i - 1][0], fl[i][1] - fl[i - 1][1]));
  const at = (s) => { const t = s + s0; let i = 1; while (i < fl.length - 1 && cum[i] < t) i++; const f = (t - cum[i - 1]) / (cum[i] - cum[i - 1]); return [fl[i - 1][0] + (fl[i][0] - fl[i - 1][0]) * f, fl[i - 1][1] + (fl[i][1] - fl[i - 1][1]) * f]; };
  const fat = (pts, color, width, dashed) => {
    const g = new LineGeometry(); g.setPositions(pts.flatMap(v => [v.x, v.y, v.z]));
    const m = new LineMaterial({ color, linewidth: width, dashed, dashSize: 0.35, gapSize: 0.25, transparent: true, depthTest: true });
    m.resolution.copy(ctx.viewer.resolution); lineMats.push(m);
    const l = new Line2(g, m); l.computeLineDistances(); l.renderOrder = 5; return l;
  };
  const label = (text, cls, pos, title) => { const d = document.createElement('div'); d.className = `lbl ${cls}`; d.textContent = text; d.title = title; const o = new CSS2DObject(d); o.position.copy(pos); return o; };
  const pg = new THREE.Group();
  const P = F.profile.points;
  pg.add(fat(P.map(p => { const [e, n] = at(p.s); return coords.toLocal(e, n, p.H + D.profileLift_m); }), D.profileColor, D.profileWidth_px, true));
  const dot = new THREE.SphereGeometry(display.labels.pointMarkerRadius_m * 0.8, 12, 8), dm = new THREE.MeshStandardMaterial({ color: D.profileColor, roughness: 0.5 });
  for (const m of F.elevation.levelMarks) {
    const [e, n] = at(m.s), p = coords.toLocal(e, n, m.H + D.profileLift_m);
    const s = new THREE.Mesh(dot, dm); s.position.copy(p); pg.add(s);
    const cmp = m.dwg == null ? '' : m.kind === 'lotFront' ? `\nבמקום הזה הרחוב לפי המפה למשתכן: ${m.dwg.toFixed(2)}` : `\nהמפה למשתכן באותה נקודה: ${m.dwg.toFixed(2)} (הפרש ${m.diff >= 0 ? '+' : ''}${(m.diff * 100).toFixed(0)} ס"מ)`;
    pg.add(label(`${m.label}${m.kind === 'lotFront' ? ' (חניה)' : ''}`, 'h h-front', p.clone().add(new THREE.Vector3(0, D.labelLift_m, 0)),
      `חזית החומה הקדמית: ${m.label}${m.note ? ` – ${m.note}` : ''}\nשרשרת ${m.chain.toFixed(2)} מ' (s=${m.s.toFixed(2)} מ' מ-2457)${cmp}`));
  }
  registry.add(pg, tags('frontStreetProfile'), {
    name: OL ? 'קו הרחוב לפי חזית החומה הקדמית (הרחוב בנוי לפיו)' : 'קו הרחוב לפי חזית החומה הקדמית (להשוואה)', kind: 'lines', provisional: true,
    rows: [['קנ"מ', F.elevation.scaleCheck], ['ראשית השרשרת', `${F.elevation.chainOrigin.rule}; סוף השרשרת מול 2420: ${(F.elevation.chainOrigin.endCheck.deviation_m * 100).toFixed(1)} ס"מ`],
      ['מול המפה למשתכן', `סטייה מרבית ${(F.profile.maxDiff_m * 100).toFixed(0)} ס"מ, ממוצעת ${(F.profile.meanDiff_m * 100).toFixed(0)} ס"מ (החזית גבוהה יותר באמצע) – docs/open-issues.md FS1`],
      ...F.elevation.levelMarks.map(m => [m.label, m.kind === 'lotFront' ? 'רצפת החניה / מפלס המגרש בחזית' : `המפה למשתכן ${m.dwg.toFixed(2)} (${m.diff >= 0 ? '+' : ''}${(m.diff * 100).toFixed(0)} ס"מ)`])],
    note: F.profile.note, source: F.elevation.source,
  });
  scene.add(pg);
  return { interp: hAt, area: F.outlineArea_m2 };
}

function pin(x, y, r) {
  let ins = false;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, yi] = r[i], [xj, yj] = r[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) ins = !ins;
  }
  return ins;
}
function area(r) { let a = 0; for (let i = 0; i < r.length; i++) { const [x1, y1] = r[i], [x2, y2] = r[(i + 1) % r.length]; a += x1 * y2 - x2 * y1; } return a / 2; }

import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { regionMesh } from '../../js/geometry/terrain.js';
import { ENV_TAGS } from './common.js';
import { treeGeometry, shrubGeometry } from './vegetation.js';

// Detailed neighbourhood from data/environment/details.json: houses (sheet 04 massing, minimalist facades),
// fences with stone cladding and gates, yards (lawn, paths, driveways), street trees, lamps, curbs, parking bays.
// All positions/heights come from the data file; this file only turns them into meshes.
export function buildDetails(ctx, mats, lots) {
  const { data, coords, registry, scene, display, ground } = ctx;
  const D = data.envDetails;
  if (!D) return { houseMaterials: [] };
  const X = (E) => E - coords.E0, Z = (N) => -(N - coords.N0), Y = (H) => H - coords.H0;
  const interpOf = Object.fromEntries(lots.map(x => [x.lot.parcel, x.interp]));
  const gAt = (E, N) => ground.heightAt(E, N, 'env');
  const M = (n) => mats.get(n);

  // box between two plan points a,b (ITM), from z0 to z1, thickness t, pushed out by `off` along the outward normal
  // UVs in metres (texture tile size from the material)
  function box(a, b, z0, z1, t, off = 0, out = null) {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy);
    if (L < 1e-3 || z1 - z0 < 1e-3) return null;
    const g = new THREE.BoxGeometry(L, z1 - z0, t);
    const uv = g.attributes.uv, dims = [[t, z1 - z0], [t, z1 - z0], [L, t], [L, t], [L, z1 - z0], [L, z1 - z0]];
    for (let f = 0; f < 6; f++) for (let k = 0; k < 4; k++) { const i = f * 4 + k; uv.setXY(i, uv.getX(i) * dims[f][0], uv.getY(i) * dims[f][1]); }
    const nx = out ? out[0] : dy / L, ny = out ? out[1] : -dx / L; // outward (right of a->b for CCW rings)
    const cx = (a[0] + b[0]) / 2 + nx * off, cy = (a[1] + b[1]) / 2 + ny * off;
    g.rotateY(Math.atan2(dy, dx)); // local x along a->b in scene (z = -N)
    g.translate(X(cx), Y((z0 + z1) / 2), Z(cy));
    return g;
  }
  const merged = (geos, mat, layer, meta, cast = true) => {
    const gs = geos.filter(Boolean); if (!gs.length) return null;
    const mix = gs.some(g => g.index) && gs.some(g => !g.index);
    const m = new THREE.Mesh(mergeGeometries(mix ? gs.map(g => g.index ? g.toNonIndexed() : g) : gs, false), mat); m.castShadow = cast; m.receiveShadow = true;
    registry.add(m, ENV_TAGS(layer), meta); scene.add(m); return m;
  };
  const extrude = (ring, z0, z1) => {
    const sh = new THREE.Shape(ring.map(([E, N]) => new THREE.Vector2(X(E), -Z(N))));
    const g = new THREE.ExtrudeGeometry(sh, { depth: z1 - z0, bevelEnabled: false });
    g.rotateX(-Math.PI / 2); g.translate(0, Y(z0), 0); return g;
  };
  // clean white render: keep the plaster's relief (normal/roughness/AO maps), drop its stained colour map
  const plaster = M('nbPlaster'); if (plaster.map) { plaster.map = null; plaster.needsUpdate = true; }
  const houseMats = [plaster, M('nbWood'), M('nbGlass')];

  // ---------------- houses ----------------
  const H = { walls: [], slab: [], coping: [], glass: [], frames: [], wood: [], door: [] };
  for (const h of D.houses) {
    // ground floor (full sheet-04 footprint) up to the slab + terrace parapet; upper floor (main mass) up to ±0.00+8.00
    H.walls.push(extrude(h.ring, h.base, h.slab + 0.9));
    H.walls.push(extrude(h.upper, h.slab, h.top));
    const r = h.ring.concat([h.ring[0]]), ru = h.upper.concat([h.upper[0]]);
    for (let i = 0; i < h.ring.length; i++) {
      H.slab.push(box(r[i], r[i + 1], h.slab - 0.12, h.slab + 0.12, 0.06, 0.03));
      H.coping.push(box(r[i], r[i + 1], h.slab + 0.86, h.slab + 0.94, 0.12, 0.02));
    }
    for (let i = 0; i < h.upper.length; i++) H.coping.push(box(ru[i], ru[i + 1], h.top - 0.06, h.top + 0.04, 0.14, 0.04));
    for (const w of [...h.walls, ...(h.wallsUpper || [])]) for (const win of w.windows) {
      H.frames.push(box(win.a, win.b, win.z0 - 0.05, win.z1 + 0.05, 0.08, 0.0));
      H.glass.push(box(win.a, win.b, win.z0, win.z1, 0.04, 0.03));
    }
    if (h.door) {
      const d = h.door, ax = d.b[0] - d.a[0], ay = d.b[1] - d.a[1], L = Math.hypot(ax, ay), ux = ax / L, uy = ay / L;
      H.door.push(box(d.a, d.b, d.z0, d.z1, 0.08, 0.02));
      // minimalist accent: vertical wood cladding around the entrance, ground to roof
      H.wood.push(box([d.a[0] - ux * 0.9, d.a[1] - uy * 0.9], [d.b[0] + ux * 0.9, d.b[1] + uy * 0.9], d.z0, h.roof, 0.05, 0.035));
      // entrance canopy (A_1 §8.4 allows up to 1.20 m beyond the front line)
      const nx = ay / L, ny = -ax / L;
      H.coping.push(box([d.a[0] - ux * 0.9 + nx * 0.6, d.a[1] - uy * 0.9 + ny * 0.6], [d.b[0] + ux * 0.9 + nx * 0.6, d.b[1] + uy * 0.9 + ny * 0.6], d.z1 + 0.25, d.z1 + 0.4, 1.2, 0, [nx, ny]));
    }
  }
  const hm = { name: 'בתי השכנים – המחשה (מתאר מגיליון 04, חזיתות המחשה)', kind: 'houses', note: D.houses[0]?.note, source: 'data/environment/details.json' };
  merged(H.walls, M('nbPlaster'), 'neighborHouses', { ...hm, rows: D.houses.map(h => [`מגרש ${h.lot}`, `${h.area_m2.toFixed(0)} מ"ר · ±0.00 ${h.pm0.toFixed(2)} · גג ${h.top.toFixed(2)}`]) });
  merged(H.slab, M('nbFrame'), 'neighborHouses', hm);
  merged(H.coping, M('nbCoping'), 'neighborHouses', hm);
  merged(H.frames, M('nbFrame'), 'neighborHouses', hm);
  merged(H.glass, M('nbGlass'), 'neighborHouses', hm, false);
  merged(H.wood, M('nbWood'), 'neighborHouses', hm);
  merged(H.door, M('nbDoor'), 'neighborHouses', hm);

  // ---------------- parking structures ----------------
  const P = { body: [], door: [] };
  for (const p of D.parking) {
    P.body.push(extrude(p.ring, p.base, p.top));
    // garage door on the street side: outward = away from the structure's centroid
    const c = p.ring.reduce((s, q) => [s[0] + q[0] / p.ring.length, s[1] + q[1] / p.ring.length], [0, 0]);
    const m = [(p.door.a[0] + p.door.b[0]) / 2, (p.door.a[1] + p.door.b[1]) / 2], o = [m[0] - c[0], m[1] - c[1]], ol = Math.hypot(...o);
    P.door.push(box(p.door.a, p.door.b, p.base, p.top - 0.35, 0.06, 0.04, [o[0] / ol, o[1] / ol]));
  }
  const pm = { name: 'מבני חניה – גיליון 04, 2.70 מ\'', kind: 'parking', source: D.parking[0]?.source };
  merged(P.body, M('nbPlaster'), 'neighborHouses', pm);
  merged(P.door, M('nbWood'), 'neighborHouses', pm);

  // ---------------- fences + gates ----------------
  const F = D.config.fence, Fg = { stone: [], plaster: [], coping: [], gate: [] };
  for (const f of D.fences) {
    const c = Math.min(f.claddingTo, f.top - 0.1);
    Fg.stone.push(box(f.a, f.b, f.base, c, F.thickness_m + 0.032, 0, [0, 0]));
    if (f.top - F.copingThick_m - c > 0.02) Fg.plaster.push(box(f.a, f.b, c, f.top - F.copingThick_m, F.thickness_m, 0, [0, 0]));
    Fg.coping.push(box(f.a, f.b, f.top - F.copingThick_m, f.top, F.copingWidth_m, 0, [0, 0]));
  }
  for (const g of D.gates) {
    if (g.kind !== 'ped') continue;
    const n = 9, ax = g.b[0] - g.a[0], ay = g.b[1] - g.a[1];
    for (let i = 0; i < n; i++) {
      const t0 = (i + 0.15) / n, t1 = (i + 0.75) / n;
      Fg.gate.push(box([g.a[0] + ax * t0, g.a[1] + ay * t0], [g.a[0] + ax * t1, g.a[1] + ay * t1], g.z, g.z + g.height, 0.05, 0, [0, 0]));
    }
  }
  const fm = { name: F.claddingFull ? 'חומות המגרשים – חיפוי אבן מלא, קופינג' : 'חומות המגרשים – חיפוי אבן עד 0.65, טיח, קופינג', note: F.claddingFull ? F.claddingFull_why : null, kind: 'fence', source: D.sources.fence,
    rows: [['גדר חזית', `${F.frontHeight_m.toFixed(2)} מ' מעל המדרכה (A_1 §14.2.1)`], ['בין שכנים', `${F.neighbourHeight_m.toFixed(2)} מ' מעל המגרש הגבוה (A_1 §14.5)`], ['דירוג', `כל ${F.stepLength_m} מ', בקפיצות ${F.stepRound_m.toFixed(2)}`], ['עובי / קופינג', `${F.thickness_m} / ${F.copingWidth_m}×${F.copingThick_m} (נספח 009 פרט 5.1)`]] };
  merged(Fg.stone, M('nbStone'), 'neighborFences', fm);
  merged(Fg.plaster, M('nbPlaster'), 'neighborFences', fm);
  merged(Fg.coping, M('nbCoping'), 'neighborFences', fm);
  merged(Fg.gate, M('nbMetal'), 'neighborFences', { name: 'שערי הולכי רגל', kind: 'gate', source: D.gates[0]?.source });

  // ---------------- yards ----------------
  const T = { ...display.terrain, sampleSpacing_m: 1.0 };
  const lawnG = [], paveG = [], drvG = [];
  const drapeMesh = (ring, parcel, lift, arr) => {
    const f = interpOf[parcel]; if (!f) return;
    const m = regionMesh(ring, f, coords, M('nbGrass'), null, T, []);
    const mesh = m.children[0]; mesh.geometry.translate(0, lift, 0); arr.push(mesh.geometry);
  };
  for (const y of D.yards) drapeMesh(y.ring, y.parcel, 0.02, lawnG);
  for (const p of D.paths) drapeMesh(p.ring, p.parcel, 0.04, p.kind === 'driveway' ? drvG : paveG);
  const bedG = [];
  for (const b of D.beds || []) drapeMesh(b.ring, b.parcel, 0.035, bedG);
  const ym = { name: 'חצרות השכנים – דשא, ערוגות, שבילים וחניות (המחשה)', kind: 'yard', pickable: true };
  merged(bedG, M('nbBed'), 'neighborYards', ym, false);
  merged(lawnG, M('nbGrass'), 'neighborYards', ym, false);
  merged(paveG, M('nbPaving'), 'neighborYards', ym, false);
  merged(drvG, M('nbDriveway'), 'neighborYards', ym, false);

  // ---------------- street: curbs, bays, islands, trees, lamps ----------------
  const S = { curb: [], lines: [], island: [] };
  for (const c of D.curbs) for (let i = 0; i < c.pts.length - 1; i++) {
    const a = c.pts[i], b = c.pts[i + 1], z = Math.max(gAt(...a), gAt(...b));
    S.curb.push(box(a, b, z - 0.25, z + c.height, c.width, 0, [0, 0]));
  }
  for (const b of D.bays) {
    if (b.kind === 'line') { const z = gAt(...b.pts[0]); S.lines.push(box(b.pts[0], b.pts[b.pts.length - 1], z + 0.005, z + 0.02, 0.1, 0, [0, 0])); }
    else { const zs = b.ring.map(p => gAt(...p)); S.island.push(extrude(b.ring, Math.min(...zs) - 0.2, Math.max(...zs) + 0.15)); }
  }
  for (const m of D.marks || []) {
    if (m.ring) { const z = Math.max(...m.ring.map(p => gAt(...p))); S.lines.push(extrude(m.ring, z + 0.005, z + 0.02)); }
    else { const a = m.pts[0], b = m.pts[m.pts.length - 1], z = Math.max(gAt(...a), gAt(...b)); S.lines.push(box(a, b, z + 0.005, z + 0.02, m.w, 0, [0, 0])); }
  }
  // integrated street lane (dark 'מלבן' pavers), regular-road parking bays, driveway crossings, bollards
  const curbH = D.config.street.curbHeight_m, LaneG = [], BayG = [], CrossG = [], BolG = [];
  const flat = (ring, lift, arr) => { const zs = ring.map(p => gAt(...p)); arr.push(extrude(ring, Math.min(...zs) + lift - 0.01, Math.max(...zs) + lift)); };
  for (const r of D.lane || []) { const g = regionMesh(r, (E, N) => gAt(E, N), coords, M('envLane'), null, T, []).children[0].geometry; g.translate(0, 0.012, 0); LaneG.push(g); }
  for (const b of D.bayPave || []) { const g = regionMesh(b.ring, (E, N) => gAt(E, N), coords, M('envBay'), null, T, []).children[0].geometry; g.translate(0, 0.01, 0); BayG.push(g); }
  for (const c of D.crossings || []) { const g = regionMesh(c.ring, (E, N) => gAt(E, N), coords, M('nbDriveway'), null, T, []).children[0].geometry; g.translate(0, (c.curbCut ? curbH : 0) + 0.02, 0); CrossG.push(g); }
  for (const b of D.bollards || []) { const g = new THREE.CylinderGeometry(0.07, 0.08, 0.8, 10); g.translate(X(b.at[0]), Y(b.z) + 0.4, Z(b.at[1])); BolG.push(g); }
  merged(LaneG, M('envLane'), 'streetFurniture', { name: 'רחוב משולב – נתיב נסיעה (אבן מלבן שחור 20/8/10), שיקנה', kind: 'street-lane', note: 'צורת השיקנה ואורכי האיים – המחשה לפי נספח 003 פרט 14', source: D.config.street.detail_source }, false);
  merged(BayG, M('envBay'), 'streetFurniture', { name: 'מפרצי חניה', kind: 'street-bays', source: D.config.street.detail_source }, false);
  merged(CrossG, M('nbDriveway'), 'streetFurniture', { name: 'כניסה לחניה – ריצוף מלבן גרפיט במעבר המדרכה (נספח 003 פרט 10)', kind: 'crossing', source: D.config.street.detail_source }, false);
  merged(BolG, M('nbMetal'), 'streetFurniture', { name: 'עמודונים', kind: 'bollards', note: 'המחשה (נספח 003 פרט 14)' });
  const sm = { name: 'פיתוח רחוב – אבני שפה, סימון כביש, מעברי חצייה, חניות, איי שתילה', kind: 'street-furniture', note: 'מקצב החניות והאיים – המחשה' };
  merged(S.curb, M('curb'), 'streetFurniture', sm);
  merged(S.lines, M('nbLine'), 'streetFurniture', sm, false);
  merged(S.island, M('nbGrass'), 'streetFurniture', sm);

  const fol = M('nbFoliage'); fol.vertexColors = true; fol.needsUpdate = true;
  const Tr = { wood: [], leaves: [] };
  for (const t of D.trees) {
    const g = treeGeometry(X(t.at[0]), Y(t.z), Z(t.at[1]), t.height, t.crown, t.species);
    Tr.wood.push(...g.wood); Tr.leaves.push(...g.leaves);
  }
  for (const sh of D.shrubs || []) {
    const g = shrubGeometry(X(sh.at[0]), Y(sh.z), Z(sh.at[1]), sh.r); Tr.leaves.push(...g.leaves);
  }
  const tm = { name: 'עצים ושיחים', kind: 'trees', note: 'עצי חצר: A_1 §12.2 (עץ כל 8 מ\' חזית) ו-§12.4 (עץ לכל 50 מ"ר פנויים). מיקומים, מינים ושיחים – המחשה', source: D.sources.tree };
  merged(Tr.wood, M('nbBark'), 'streetFurniture', tm);
  merged(Tr.leaves, M('nbFoliage'), 'streetFurniture', tm);

  const Lp = { pole: [], head: [] };
  for (const l of D.lamps) {
    const [E, N] = l.at, z = l.z, h = l.height;
    const p = new THREE.BoxGeometry(0.15, h, 0.15); p.translate(X(E), Y(z) + h / 2, Z(N)); Lp.pole.push(p);
    // arm points over the walkway (data: unit vector toward the lot side)
    const a = [E + l.arm[0] * 1.3, N + l.arm[1] * 1.3];
    Lp.pole.push(box([E, N], a, z + h - 0.1, z + h, 0.1, 0, [0, 0]));
    Lp.head.push(box([a[0] - l.arm[0] * 0.15, a[1] - l.arm[1] * 0.15], [a[0] + l.arm[0] * 0.45, a[1] + l.arm[1] * 0.45], z + h - 0.18, z + h - 0.06, 0.28, 0, [0, 0]));
  }
  const lm = { name: 'עמודי תאורה 15X15, 6 מ\' (גיליון 04 – מקרא)', kind: 'lamps', note: 'מיקום העמודים – המחשה', source: D.sources.lamp };
  merged(Lp.pole, M('nbMetal'), 'streetFurniture', lm);
  merged(Lp.head, M('nbLamp'), 'streetFurniture', lm);
  return { houseMaterials: houseMats };
}

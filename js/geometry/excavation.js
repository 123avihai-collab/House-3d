import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { regionMesh } from './terrain.js';
import { pointInRing, distToPolyline, nearestOnRing, densifyRing, ringArea, distToRing } from './tin.js';
import { surfaceZ } from '../../src/tiling/layout.js';

// Excavation for the dwelling unit (basement), from data/structure/excavation.json:
// floor = bottom outline + working space (floorOutlineITM) at bottomAbs.
// Open stretches: z = min(existing 2025, bottom + d / slope), d = distance outside the floor outline.
// Shored stretches (shoredRunsITM, decided in tools/extract_structure.py where the 1:2 slope would not
// reach existing ground inside the lot – soil report 4.3 / 10.2): vertical cut at the floor outline,
// drawn as a provisional shoring wall from existing ground down to the bottom.
export function buildExcavation(ctx) {
  const { data, coords, registry, scene, materials, display, ground, lineMats } = ctx;
  const ex = data.excavation;
  const D = display.excavation;
  const existing0 = ground.regions.find(r => r.id === 'lot-257-existing')?.interp;
  if (!existing0) { console.warn('no existing ground for excavation'); return null; }
  // earthworks (Avihai's note 1, excavation.json earthworks): stripping (soil report §10.6–10.7), then levelling of the whole lot
  // before the piles are set out (K-400) – cut down to the final development surface wherever the stripped ground is higher, so
  // the heaps behind the pool / in the back yard are gone from the start. Everything after works on the levelled ground.
  const EW = ex.earthworks || {};
  const strip = EW.stripping?.depth_m || 0;
  const plannedF = ground.regions.find(r => r.kind === 'final')?.interp;
  const stripped = (E, N) => existing0(E, N) - strip;
  const existing = (E, N) => (plannedF ? Math.min(stripped(E, N), plannedF(E, N)) : stripped(E, N));
  const bottom = ex.bottomOutlineITM;
  const floor = ex.floorOutlineITM;
  const runs = ex.shoredRunsITM || [];
  const zb = ex.bottomAbs;
  // a point outside the floor is behind a shoring wall when its nearest floor-outline point lies on a shored run
  const below0 = ex.bottomBuildUp.filter(b => b.thickness_m).reduce((a, b) => a + b.thickness_m, 0);
  const lowTop = Math.min(...(data.framing?.slabs || []).filter(s => s.top != null).map(s => s.top));
  const highSlabs = (data.framing?.slabs || []).filter(s => s.top != null && s.top > lowTop + 0.01 && s.outlineITM)
    .map(s => ({ ring: s.outlineITM, z: coords.H0 + s.top - s.thickness_m - below0 }));
  const pitZ = (E, N) => {
    if (pointInRing(E, N, floor)) { const hs = highSlabs.find(s => pointInRing(E, N, s.ring)); return hs ? Math.max(zb, hs.z) : zb; }
    const q = nearestOnRing(E, N, floor);
    if (runs.some(r => distToPolyline(q.x, q.y, r) <= D.shoringMatchTol_m)) return existing(E, N);
    return Math.min(existing(E, N), zb + q.dist / ex.sideSlope_HperV);
  };
  // trenches for the foundation beams outside the basement pit (stage 2b, provisional with the beams):
  // beam footprint (width from the tag) down to beam bottom − (lean concrete + void formers) from the excavation build-up
  const below = ex.bottomBuildUp.filter(b => b.thickness_m).reduce((a, b) => a + b.thickness_m, 0);
  const trenches = (data.framing?.groundBeams || []).filter(b => b.axisITM && b.layer === 'groundFloorBeams').map(b => {
    const [[E1, N1], [E2, N2]] = b.axisITM; const L = Math.hypot(E2 - E1, N2 - N1);
    return { E1, N1, ux: (E2 - E1) / L, uy: (N2 - N1) / L, L, hw: b.width_m / 2, z: coords.H0 + b.bottomRel - below, b };
  });
  const trenchZ = (E, N) => {
    let z = Infinity;
    for (const t of trenches) {
      const dx = E - t.E1, dy = N - t.N1, a = dx * t.ux + dy * t.uy, c = -dx * t.uy + dy * t.ux;
      if (a >= -t.hw && a <= t.L + t.hw && Math.abs(c) <= t.hw) z = Math.min(z, t.z);
    }
    return z;
  };
  // the same grid points are sampled by several surfaces (pit, trenches, working space, backfill…): pitZ is pure – cache it
  const pitMemo = new Map();
  const pitOnly = (E, N) => { const k = E + ',' + N; let z = pitMemo.get(k); if (z === undefined) { z = pitZ(E, N); pitMemo.set(k, z); } return z; };
  // local pits for chambers below the excavation bottom (plumbing plan: I.L. of the chamber)
  const chambers = (data.plumbingFoundations?.chambers || []).filter(c => c.kind !== 'sewerManhole' && c.IL < existing(c.E, c.N));
  const chamberZ = (E, N) => { let z = Infinity; for (const c of chambers) if (Math.hypot(E - c.E, N - c.N) <= c.diameter_m / 2) z = Math.min(z, c.IL); return z; };
  // pool + machine room / balance tank: cast with the basement -> dug in the same general excavation
  // (vertical sides; bottom = slab underside: pool – pile heads west/east interpolated along the pool's long axis; tank – floor − slab)
  const PL = data.pool;
  const poolZ = (E, N) => {
    if (!PL) return Infinity;
    if (pointInRing(E, N, PL.tank.pitITM || PL.tank.outerITM)) return PL.tank.slabUnderside;   // incl. the strip under the gutter (walls on both sides)
    if (PL.channel && pointInRing(E, N, PL.channel.outerITM)) return PL.channel.bottom;
    if (pointInRing(E, N, PL.pool.outerITM)) {
      const r = PL.pool.outerITM, xs = r.map(p => p[0]); const t = (E - Math.min(...xs)) / (Math.max(...xs) - Math.min(...xs));
      const zs = PL.pool.slabUndersideWest + (PL.pool.slabUndersideEast - PL.pool.slabUndersideWest) * Math.min(1, Math.max(0, t));
      // the pool walls go down below the slab (pool.json wallBottom): their strip along the outline is dug deeper
      return PL.pool.wallBottom != null && distToRing(E, N, r) <= D.poolWallStrip_m ? Math.min(zs, PL.pool.wallBottom) : zs;
    }
    if (PL.gutter && pointInRing(E, N, PL.gutter.ringOuterITM)) return PL.gutter.bottom;      // overflow gutter around the pool
    return Infinity;
  };
  const pitA = (E, N) => Math.min(pitOnly(E, N), chamberZ(E, N), poolZ(E, N));          // pit + chamber pits (until the basement walls)
  const pitZ2 = (E, N) => Math.min(pitA(E, N), trenchZ(E, N));               // + trenches of the ground-floor beams (dug before that pour)
  pitZ2.kind = 'excavation';
  const lot = data.plot.ring;
  const T = { ...display.terrain, sampleSpacing_m: D.sampleSpacing_m, boundaryDensify_m: D.sampleSpacing_m };
  const ctrl = densifyRing(floor, D.sampleSpacing_m).filter(([x, y]) => pointInRing(x, y, lot)).map(([x, y]) => ({ x, y, z: zb }));
  if (PL) for (const r of [PL.pool.outerITM, PL.tank.pitITM || PL.tank.outerITM, PL.channel?.outerITM, PL.gutter?.ringOuterITM].filter(Boolean)) for (const [x, y] of densifyRing(r, D.sampleSpacing_m / 2)) {
    // crisp vertical walls of the pool / tank pit
    const cx = r.reduce((a, p) => a + p[0] / r.length, 0), cy = r.reduce((a, p) => a + p[1] / r.length, 0);
    for (const k of [0.995, 1.005]) ctrl.push({ x: cx + (x - cx) * k, y: cy + (y - cy) * k, z: 0 });
  }
  for (const s of highSlabs) for (const [x, y] of densifyRing(s.ring, D.sampleSpacing_m / 2)) {
    const cx = s.ring.reduce((a, p) => a + p[0] / s.ring.length, 0), cy = s.ring.reduce((a, p) => a + p[1] / s.ring.length, 0);
    for (const k of [0.995, 1.005]) ctrl.push({ x: cx + (x - cx) * k, y: cy + (y - cy) * k, z: 0 });
  }
  if (PL?.pool?.wallBottom != null) { const r = PL.pool.outerITM; const cx = r.reduce((a, p) => a + p[0] / r.length, 0), cy = r.reduce((a, p) => a + p[1] / r.length, 0);
    for (const [x, y] of densifyRing(r, D.sampleSpacing_m / 2)) { const L = Math.hypot(x - cx, y - cy) || 1; const k = 1 - (D.poolWallStrip_m + 0.02) / L; ctrl.push({ x: cx + (x - cx) * k, y: cy + (y - cy) * k, z: 0 }); } }
  for (const c of chambers) for (const k of [0.98, 1.02]) for (let i = 0; i < 16; i++) {
    const a = i / 16 * 2 * Math.PI; ctrl.push({ x: c.E + Math.cos(a) * c.diameter_m / 2 * k, y: c.N + Math.sin(a) * c.diameter_m / 2 * k, z: 0 });
  }
  // crisp trench walls: control points just inside / outside every trench edge
  for (const t of trenches) for (const off of [-1, 1]) for (const k of [0.999, 1.001]) {
    const n = Math.max(2, Math.ceil(t.L / D.sampleSpacing_m));
    for (let i = 0; i <= n; i++) { const a = -t.hw + (t.L + 2 * t.hw) * i / n, c = off * t.hw * k;
      ctrl.push({ x: t.E1 + a * t.ux - c * t.uy, y: t.N1 + a * t.uy + c * t.ux, z: 0 }); }
  }
  // crisp vertical cut at shored stretches: control points just inside / outside the floor outline
  const off = D.shoringCtrlOffset_m;
  for (const r of runs) for (let i = 1; i < r.length; i++) {
    const [x1, y1] = r[i - 1], [x2, y2] = r[i]; const L = Math.hypot(x2 - x1, y2 - y1) || 1;
    const nx = (y2 - y1) / L, ny = -(x2 - x1) / L; // one of the two normals; the inside one is chosen by test
    const inside = pointInRing(x1 + nx * off, y1 + ny * off, floor) ? 1 : -1;
    for (const s of [inside, -inside]) ctrl.push({ x: x1 + nx * off * s, y: y1 + ny * off * s, z: 0 });
  }
  const meshA = regionMesh(lot, pitA, coords, materials.get('soilPit'), materials.get('soilCut'), T, ctrl);

  // backfill after the basement walls (construction order): the soil around the basement and the pool is filled and levelled
  //  - under every ground-floor slab (house, outdoor slabs, mamad): formation = slab underside − build-up below it
  //    (lean concrete + void formers, the same build-up as under the beams: excavation.json bottomBuildUp)
  //  - garden / strips without a slab: the planned lot surface (topoPlanned, מפה למשתכן)
  //  - basement, English courtyards, stairs down, pool / tank: stay open (pit level – the structure fills them)
  //  - trenches of the K-21 beams are dug into the backfill before the ground-floor pour
  const FG = data.floorGround;
  const planned = ground.regions.find(r => r.kind === 'final')?.interp;
  const bsmRing = data.basement?.outlineITM;
  const slabs = (FG?.slab || []).map(s => ({ ring: s.footprintITM, holes: s.holesITM || [], z: coords.H0 + s.bottomRel - below }));
  const openRings = (FG?.openZones || []).filter(o => o.zone !== 'garden').map(o => o.footprintITM);
  const inPoly = (E, N, s) => pointInRing(E, N, s.ring) && !s.holes.some(h => pointInRing(E, N, h));
  // working level (Avihai ק8): after the basement the contractor fills and levels the whole lot to the formation of the ground
  // floor – under each ground slab its underside − build-up; between the slabs / in the garden the formation of the nearest slab
  // (note 1: the levelling of the whole lot moved to the start – step "siteLevel". Here only the formation under the slabs; the
  // garden and the strips stay on the levelled ground and get their fill to the final surface in "development")
  const workAt = (E, N) => {
    const sl = slabs.find(s => inPoly(E, N, s)); if (sl) return sl.z;
    return existing(E, N);
  };
  const openAt = (E, N) => (bsmRing && pointInRing(E, N, bsmRing)) || openRings.some(r => pointInRing(E, N, r)) || poolZ(E, N) < Infinity;
  // inside the basement / courtyards the structure is the surface: the soil stays at the pit bottom, below every basement slab
  // (Avihai ק18: soil showed in the English courtyard over the floor lowered by OC-1 to -2.75); the pool keeps its own pit
  const openZ = (E, N) => poolZ(E, N) < Infinity || !pointInRing(E, N, floor) ? pitA(E, N) : Math.min(zb, chamberZ(E, N));
  const working = (E, N) => openAt(E, N) ? openZ(E, N) : workAt(E, N);
  working.kind = 'backfill';
  const backfill = (E, N) => openAt(E, N) ? openZ(E, N) : Math.min(workAt(E, N), trenchZ(E, N));     // + trenches of the K-21 beams
  backfill.kind = 'backfill';
  // final surface (development): garden / strips = planned lot surface; under the slabs and in the openings it stays below the structure
  const finalZ = (E, N) => {
    if (openAt(E, N)) return openZ(E, N);
    const sl = slabs.find(s => inPoly(E, N, s)); if (sl) return sl.z;
    return planned ? planned(E, N) : workAt(E, N);
  };
  finalZ.kind = 'final';
  // crisp steps at the slab / opening outlines: control points just inside and outside every ring
  const ctrlB = ctrl.slice();
  const edgePts = (r) => { const out = []; const pts = densifyRing(r, D.sampleSpacing_m / 2);
    for (let i = 0; i < pts.length; i++) { const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % pts.length]; const L = Math.hypot(x2 - x1, y2 - y1) || 1;
      const nx = (y2 - y1) / L, ny = -(x2 - x1) / L; for (const s of [-1, 1]) out.push({ x: x1 + nx * off * s, y: y1 + ny * off * s, z: 0 }); }
    return out; };
  for (const s of slabs) ctrlB.push(...edgePts(s.ring));
  for (const r of openRings) ctrlB.push(...edgePts(r));
  if (bsmRing) ctrlB.push(...edgePts(bsmRing));
  // owner changes on the final surface (OC-7 garden level, OC-8 slab behind the pool): their zones are cut out of the
  // development surface and drawn twice – as in the plans / with the change (data/changes/owner-changes-geometry.json)
  const OCG = data.ownerChangesGeometry?.changes || {};
  const garden = (FG?.openZones || []).find(o => o.zone === 'garden')?.footprintITM;
  // zone = one ring with its versions (variant conditions + surface); a ring touched by a terrain change (OC-7) and a
  // slab change (OC-8) gets 3 versions: plans / OC-7 soil level / OC-8 slab (soil under it)
  const ocZones = []; const zoneOf = new Map();
  const zone = (key, ring) => { if (!zoneOf.has(key)) { const z = { key, ring, terrain: null, slab: null }; zoneOf.set(key, z); ocZones.push(z); } return zoneOf.get(key); };
  for (const [id, g] of Object.entries(OCG)) if (g.slab?.ringITM) { const z = zone(id, g.slab.ringITM); z.slab = { id, g, s: g.slab, fn: () => coords.H0 + g.slab.topRel - g.slab.thickness_m }; }
  for (const [id, g] of Object.entries(OCG)) for (const k of g.terrain?.zones || []) {
    // a zone: 'garden', another change's slab ring (e.g. 'OC-8'), or { key, ringITM, surfaceRel } given in the data
    const ring = typeof k === 'object' ? k.ringITM : k === 'garden' ? garden : OCG[k]?.slab?.ringITM; if (!ring) continue;
    const rel = typeof k === 'object' && k.surfaceRel != null ? k.surfaceRel : g.terrain.surfaceRel;
    // followPaving (OC-17): the surface follows the finished paving of an outdoor zone (exterior.json, its sloped surface) + offset
    const FP = (typeof k === 'object' && k.followPaving) || g.terrain.followPaving, PR = FP && (data.tilingExterior?.rooms || []).find(r => r.slab === FP.slab);
    const pz = PR ? surfaceZ(PR.surface) : null;
    if (FP && !pz) console.warn(`${id}: no paving surface for ${FP.slab}`);
    const fn = pz ? (E, N) => coords.H0 + pz(E, N) + FP.offset_m : () => coords.H0 + rel;
    zone(typeof k === 'object' ? `${id}-${k.key}` : k, ring).terrain = { id, g, fn, layers: g.terrain.layers, FP, label: typeof k === 'object' ? k.label : g.terrain.zoneLabels?.[k] || null, zoneSource: typeof k === 'object' ? k.source : null };
  }
  for (const z of ocZones) {
    const S = z.slab, V = (id, show) => ({ change: id, show });
    // a terrain change applied by Avihai's decision (terrain.applied) is the plans surface itself – no button
    const Ta = z.terrain?.g.terrain.applied ? z.terrain : null; const T = Ta ? null : z.terrain;
    const plansFn = Ta ? Ta.fn : finalZ;
    z.versions = [];
    if (!T && !S) { z.versions.push({ variant: null, fn: plansFn, plans: true, applied: Ta, ids: [Ta.id] }); continue; }
    if (S?.s.applied) {   // slab applied by Avihai's decision: always cast; the soil stays under it (or at the applied level, if lower)
      z.versions.push({ variant: null, fn: Ta ? (E, N) => Math.min(Ta.fn(E, N), S.fn(E, N)) : S.fn, applied: S, plans: true, ids: [S.id] }); continue;
    }
    const plansVar = T && S ? { all: [V(S.id, 'original'), V(T.id, 'original')] } : V((T || S).id, 'original');
    z.versions.push({ variant: plansVar, fn: plansFn, plans: true, applied: Ta, ids: [T?.id, S?.id].filter(Boolean) });
    if (T) z.versions.push({ variant: S ? { all: [V(S.id, 'original'), V(T.id, 'changed')] } : V(T.id, 'changed'), fn: T.fn, oc: T });
    if (S) z.versions.push({ variant: V(S.id, 'changed'), fn: S.fn, oc: S });
  }
  for (const z of ocZones) ctrlB.push(...edgePts(z.ring));
  const ctrlL = ctrlB.filter(p => pointInRing(p.x, p.y, lot));
  const meshC = regionMesh(lot, backfill, coords, materials.get('soilPit'), materials.get('soilCut'), T, ctrlL);
  const meshW = regionMesh(lot, working, coords, materials.get('soilPit'), materials.get('soilCut'), T, ctrlL);
  const meshF = regionMesh(lot, finalZ, coords, materials.get('soilPlot'), materials.get('soilCut'), T, ctrlL, ocZones.map(z => z.ring));
  const meshS = regionMesh(lot, stripped, coords, materials.get('soilPit'), materials.get('soilCut'), T, []);
  const meshL = regionMesh(lot, existing, coords, materials.get('soilPit'), materials.get('soilCut'), T, []);
  // volumes of each earthworks layer on the volume grid (Avihai's note 1: every layer its own m³)
  const gv = D.volumeGrid_m; const EV = { strip: 0, level: 0, fillWalls: 0, fillSlabs: 0, cutFormation: 0, fillMaxDepth: 0 };
  { const xs0 = lot.map(p => p[0]), ys0 = lot.map(p => p[1]);
    for (let x = Math.min(...xs0) + gv / 2; x < Math.max(...xs0); x += gv) for (let y = Math.min(...ys0) + gv / 2; y < Math.max(...ys0); y += gv) {
      if (!pointInRing(x, y, lot)) continue;
      const a = gv * gv, lv = existing(x, y);
      EV.strip += strip * a; EV.level += Math.max(0, stripped(x, y) - lv) * a;
      if (openAt(x, y)) continue;
      const w = working(x, y), base = pitA(x, y), dug = base < lv - 0.01;
      if (w > base) { if (dug) EV.fillWalls += (w - base) * a; else EV.fillSlabs += (w - base) * a; EV.fillMaxDepth = Math.max(EV.fillMaxDepth, w - base); }
      else if (!dug) EV.cutFormation += (base - w) * a;
    } }

  // volume (cut below existing ground 2025) on a regular grid
  const g = D.volumeGrid_m;
  let vol = 0, maxDepth = 0;
  const xs = lot.map(p => p[0]), ys = lot.map(p => p[1]);
  for (let x = Math.min(...xs) + g / 2; x < Math.max(...xs); x += g) {
    for (let y = Math.min(...ys) + g / 2; y < Math.max(...ys); y += g) {
      if (!pointInRing(x, y, lot)) continue;
      const dz = existing(x, y) - pitZ(x, y);
      if (dz > 0) { vol += dz * g * g; maxDepth = Math.max(maxDepth, dz); }
    }
  }
  let trenchVol = 0;
  for (const t of trenches) {
    const n = Math.max(2, Math.ceil(t.L / g)); let acc = 0;
    for (let i = 0; i < n; i++) { const a = (i + 0.5) / n * t.L, E = t.E1 + a * t.ux, N = t.N1 + a * t.uy;
      acc += Math.max(0, Math.min(existing(E, N), pitOnly(E, N)) - t.z); }
    trenchVol += acc / n * t.L * 2 * t.hw;
  }
  const group = new THREE.Group();

  // bottom outline line
  const fat = (pts, color, width, dashed = false) => {
    const lg = new LineGeometry(); lg.setPositions(pts.flatMap(v => [v.x, v.y, v.z]));
    const m = new LineMaterial({ color, linewidth: width, dashed, dashSize: 0.5, gapSize: 0.3 });
    m.resolution.copy(ctx.viewer.resolution); lineMats.push(m);
    const l = new Line2(lg, m); l.computeLineDistances(); l.renderOrder = 6; l.userData.annotation = true; return l;
  };
  group.add(fat(bottom.concat([bottom[0]]).map(([x, y]) => coords.toLocal(x, y, zb + 0.02)), D.bottomLineColor, 2, true));

  // shoring wall (provisional): vertical panel along each shored run, existing ground -> bottom
  let shoringLen = 0, shoringMaxH = 0, shoringArea = 0;
  const shoringMeshes = [];
  for (const r of runs) {
    const pos = [], uv = [], idx = []; let s0 = 0;
    // panel pulled a few cm into the pit so it is drawn in front of the terrain's vertical cut
    const inner = r.map(([x, y], i) => {
      const [ax, ay] = r[Math.max(0, i - 1)], [bx, by] = r[Math.min(r.length - 1, i + 1)];
      const L = Math.hypot(bx - ax, by - ay) || 1; let nx = (by - ay) / L, ny = -(bx - ax) / L;
      if (!pointInRing(x + nx * 0.5, y + ny * 0.5, floor)) { nx = -nx; ny = -ny; }
      return [x + nx * D.shoringPanelInset_m, y + ny * D.shoringPanelInset_m];
    });
    r.forEach(([x0, y0], i) => {
      const [x, y] = inner[i];
      if (i) { const ds = Math.hypot(x0 - r[i - 1][0], y0 - r[i - 1][1]); s0 += ds;
        const h = ((existing(x0, y0) - zb) + (existing(r[i - 1][0], r[i - 1][1]) - zb)) / 2; shoringArea += Math.max(0, h) * ds; }
      shoringMaxH = Math.max(shoringMaxH, existing(x0, y0) - zb);
      const top = existing(x, y);
      const a = coords.toLocal(x, y, top), b2 = coords.toLocal(x, y, zb);
      pos.push(a.x, a.y, a.z, b2.x, b2.y, b2.z); uv.push(s0, top - coords.H0, s0, zb - coords.H0);
      if (i) { const k = i * 2; idx.push(k - 2, k - 1, k, k - 1, k + 1, k); }
    });
    shoringLen += s0;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    geo.setIndex(idx); geo.computeVertexNormals();
    const m = materials.get('shoring').clone(); m.side = THREE.DoubleSide;
    const wall = new THREE.Mesh(geo, m); wall.castShadow = wall.receiveShadow = true;
    shoringMeshes.push(wall);
    group.add(fat(r.map(([x, y]) => coords.toLocal(x, y, existing(x, y) + 0.03)), D.shoringColor, 4));
  }
  if (runs.length) {
    const longest = runs.reduce((p, q) => (q.length > p.length ? q : p));
    const m = longest[Math.floor(longest.length / 2)];
    const div = document.createElement('div'); div.className = 'lbl shoring';
    div.textContent = `דיפון (זמני) · ${shoringLen.toFixed(1)} מ' · עד ${shoringMaxH.toFixed(2)} מ'`;
    div.title = ex.shoringNote;
    const o = new CSS2DObject(div); o.position.copy(coords.toLocal(m[0], m[1], existing(m[0], m[1]) + 1)); group.add(o);
  }
  const lbl = document.createElement('div'); lbl.className = 'lbl h h-zero';
  lbl.textContent = `תחתית חפירה ${coords.fmtH(zb)}`;
  const c = bottom.reduce((a, p) => [a[0] + p[0] / bottom.length, a[1] + p[1] / bottom.length], [0, 0]);
  const lo = new CSS2DObject(lbl); lo.position.copy(coords.toLocal(c[0], c[1], zb + 0.4)); group.add(lo);

  const chamberVol = chambers.reduce((a, c) => a + Math.PI * (c.diameter_m / 2) ** 2 * Math.max(0, Math.min(existing(c.E, c.N), pitOnly(c.E, c.N)) - c.IL), 0);
  const stats = { earthworks: EV, chamberPitVolume_m3: chamberVol, volume_m3: vol + trenchVol + chamberVol, pitVolume_m3: vol, trenchVolume_m3: trenchVol, trenchCount: trenches.length, maxDepth_m: maxDepth, bottomArea_m2: Math.abs(ringArea(floor)), shoringLength_m: shoringLen, shoringMaxHeight_m: shoringMaxH, shoringArea_m2: shoringArea };
const exMeta = {
    name: 'חפירה ליחידת הדיור (מרתף)', kind: 'terrain', role: 'excavation', ring: lot,
    hMin: zb, hMax: meshA.userData.hMax, area: stats.bottomArea_m2,
    rows: [
      ['מפלס תחתית חפירה', coords.fmtH(zb)],
      ['שיפוע דפנות', `1:${ex.sideSlope_HperV} (אנכי:אופקי)`],
      ['מרווח עבודה בתחתית', `${ex.workingSpace_m.toFixed(2)} מ' מהקיר החיצוני`],
      ['נפח חפירה (מתחת למגרש המיושר)', `${vol.toFixed(1)} מ"ק`],
      ['עומק חפירה מקסימלי', `${maxDepth.toFixed(2)} מ'`],
      ['שטח תחתית', `${stats.bottomArea_m2.toFixed(1)} מ"ר`],
      ['שטח תחתית קורות/מרתף', `${Math.abs(ringArea(bottom)).toFixed(1)} מ"ר`],
      ['דיפון (זמני)', `${shoringLen.toFixed(1)} מ' · גובה חתך עד ${shoringMaxH.toFixed(2)} מ' · ${shoringArea.toFixed(1)} מ"ר`],
    ],
    note: `מרווח עבודה ${ex.workingSpace_m} מ'${ex.workingSpaceStatus === 'provisional' ? ' – זמני, לאישור' : ''}. ${ex.shoringNote}`, status: ex.shoringStatus,
    source: ex.source,
  };
  registry.add(group, { floor: 'unit', system: 'site', stage: 'excavation', stepTo: 'waterproofing', layer: 'excavation' }, { ...exMeta, kind: 'marks', pickable: false });
  const gA = new THREE.Group(); gA.add(meshA); scene.add(gA);
  registry.add(gA, { floor: 'unit', system: 'site', stage: 'excavation', stepTo: 'waterproofing', layer: 'excavation' }, exMeta);
  const FL = EW.fill || {};
  const layersN = (v) => Math.max(1, Math.ceil(v / (FL.layer_m || 0.2)));
  const ew = { floor: 'site', system: 'site', stage: 'excavation', layer: 'earthworks' };
  const gS = new THREE.Group(); gS.add(meshS); scene.add(gS);
  registry.add(gS, { ...ew, step: 'stripTopsoil', stepTo: 'stripTopsoil' }, { name: `חישוף ${Math.round(strip * 100)} ס"מ`, kind: 'terrain', role: 'earthworks', ring: lot,
    status: EW.stripping?.status || 'source', rows: [['עומק', `${Math.round(strip * 100)} ס"מ (מינימום)`], ['נפח', `${EV.strip.toFixed(1)} מ"ק`], ['שטח', `${Math.abs(ringArea(lot)).toFixed(1)} מ"ר`]],
    note: 'סילוק צמחייה, מילוי ישן ופסולת – לפני כל עבודות המילוי.', source: EW.stripping?.source || '' });
  const gL = new THREE.Group(); gL.add(meshL); scene.add(gL);
  registry.add(gL, { ...ew, step: 'siteLevel', stepTo: 'pilesOutside' }, { name: 'יישור המגרש (חיתוך עד פני הפיתוח)', kind: 'terrain', role: 'earthworks', ring: lot,
    status: EW.siteLevel?.status || 'source', rows: [['כלל', EW.siteLevel?.rule || ''], ['נפח חיתוך', `${EV.level.toFixed(1)} מ"ק`]],
    note: 'חיתוך כל המגרש (צד הבריכה, החצר האחורית) עד פני הפיתוח הסופיים, רק היכן שהקרקע גבוהה מהם – לפני סימון הכלונסאות (K-400). ערימות העפר נעלמות מהשלב הזה.', source: EW.siteLevel?.source || '' });
  // external waterproofing of the basement walls – provisional (no detail in the sources), framing.json waterproofing
  const WP = data.framing?.waterproofing;
  if (WP) {
    const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
    const sh = new THREE.Shape(WP.ringITM.map(toV)); for (const hh of WP.holesITM || []) sh.holes.push(new THREE.Path(hh.map(toV)));
    const geo = new THREE.ExtrudeGeometry(sh, { depth: WP.topRel - WP.bottomRel, bevelEnabled: false }); geo.rotateX(-Math.PI / 2); geo.translate(0, WP.bottomRel, 0);
    const wm = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: display.earthworks.waterproofingColor, roughness: 0.6 })); wm.castShadow = wm.receiveShadow = true;
    const gw = new THREE.Group(); gw.add(wm); gw.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: display.framing.provisionalEdgeColor })));
    registry.add(gw, { floor: 'unit', system: 'structure', stage: 'walls', layer: 'waterproofing', step: 'waterproofing' }, {
      name: 'איטום חיצוני לקירות המרתף (זמני)', status: 'provisional',
      rows: [['שכבות', WP.layers.join(' · ')], ['שטח', `${WP.area_m2.toFixed(1)} מ"ר (${WP.perimeter_m.toFixed(1)} מ' × גובה הקיר)`], ['גובה', `${coords.fmtH(coords.H0 + WP.bottomRel)} – ${coords.fmtH(coords.H0 + WP.topRel)}`]],
      note: 'אין פרט איטום במקורות – מבנה זמני עד פרט מהאדריכל / יועץ איטום. העובי בתצוגה – להמחשה.', source: WP.source });
    scene.add(gw);
  }
  const fillMeta = { ...exMeta, role: 'backfill', status: 'source', source: `${FL.source || ex.source}; data/structure/floor-ground.json (רצפות הקרקע)` };
  const gW = new THREE.Group(); gW.add(meshW); scene.add(gW);
  registry.add(gW, { floor: 'site', system: 'site', stage: 'excavation', step: 'backfill', stepTo: 'backfill', layer: 'backfill' }, { ...fillMeta,
    name: "מילוי חוזר ומצעים – מצע ג' בשכבות", hMax: meshW.userData.hMax,
    rows: [['חומר', FL.material || '—'], ['שכבות / הידוק', `${Math.round((FL.layer_m || 0.2) * 100)} ס"מ · ${FL.compaction || '—'}`],
      ['מילוי בגב קירות המרתף', `${EV.fillWalls.toFixed(1)} מ"ק`], ['מצע מתחת לרצפות (מחוץ לבור)', `${EV.fillSlabs.toFixed(1)} מ"ק · עד ${layersN(EV.fillMaxDepth)} שכבות`],
      ['חיתוך עד גובה העבודה', `${EV.cutFormation.toFixed(1)} מ"ק`],
      ['גובה העבודה מתחת לרצפות', `תחתית הרצפה − ${below.toFixed(2)} מ' (בטון רזה + ארגזי פוליביד)`], ['פתוח', 'מרתף, חצרות אנגליות, מדרגות למרתף, בריכה'],
      ...(EW.wallDrain ? [['ניקוז בגב הקיר', EW.wallDrain.item]] : [])],
    note: ['אחרי האיטום. ' + (FL.conflicts || []).join(' · '), 'ויברציה מופסקת 0.5 מ\' מגב הקיר (§10.9).'].join(' '), status: (FL.conflicts || []).length ? 'approx' : 'source' });
  const gC = new THREE.Group(); gC.add(meshC); scene.add(gC);
  registry.add(gC, { floor: 'site', system: 'site', stage: 'excavation', step: 'underSlab', stepTo: 'outdoorSlabs', layer: 'backfill' }, { ...fillMeta,
    name: 'משטח העבודה ותעלות לקורות K-21', hMax: meshC.userData.hMax,
    rows: [['תעלות', `תחתית הקורה − ${below.toFixed(2)} מ'`], ['מתחת לרצפות הקרקע', `תחתית הרצפה − ${below.toFixed(2)} מ'`]],
    note: 'תעלות הקורות של קומת הקרקע נחפרות במילוי לפני היציקה; תעלות קורות החוץ נשארות פתוחות עד יציקת קורות החוץ.' });
  const gF = new THREE.Group(); gF.add(meshF); scene.add(gF);
  registry.add(gF, { floor: 'site', system: 'site', stage: 'finishes', step: 'development', layer: 'topoPlanned' }, { ...fillMeta,
    name: 'מגרש 5187 – פני קרקע מתוכננים (פיתוח)', role: 'plot', hMax: meshF.userData.hMax,
    rows: [['גינה / רצועות', 'פני הקרקע המתוכננים (מפה למשתכן)'], ['מתחת לרצפות', 'נשאר מתחת למבנה']],
    ocZones: ocZones.map(z => z.key),
    note: 'פני הקרקע הסופיים בגינה וברצועות – לפי גבהי הפיתוח בתוכנית קומת הקרקע של ההיתר (הערת אביחי 09.11.2026); בתוך הבית, הרצפות, הבריכה והחצרות – המבנה.', source: 'data/site/development-heights.json; data/structure/floor-ground.json' });
  // an applied terrain change with layers (OC-17, garden): local soil fill from the levelled ground up to the base, then the
  // compacted base course; each layer its own mesh / layer / volume (data/changes/owner-changes-geometry.json terrain.layers)
  const buildLayers = (z, v, zCtrl) => {
    const A = v.applied, Ls = A.layers, base = Ls.find(l => l.key === 'base'), fillL = Ls.find(l => l.key === 'fill'), turf = Ls.find(l => l.key === 'turf');
    const zl = A.label || 'גינה', FP = A.FP;
    const t = base?.thickness_m || 0, topF = v.fn, botF = (E, N) => topF(E, N) - t;
    const area = Math.abs(ringArea(z.ring)), c = ocById[A.id] || { title: A.id, description: '' };
    // fill volume on the volume grid: base underside − levelled ground (working surface)
    let fv = 0, cv = 0, fMin = Infinity, fMax = 0, tMin = Infinity, tMax = -Infinity;
    const xs = z.ring.map(p => p[0]), ys = z.ring.map(p => p[1]);
    for (let x = Math.min(...xs) + gv / 2; x < Math.max(...xs); x += gv) for (let y = Math.min(...ys) + gv / 2; y < Math.max(...ys); y += gv) {
      if (!pointInRing(x, y, z.ring)) continue;
      const dd = botF(x, y) - working(x, y), d = Math.max(0, dd); fv += d * gv * gv; cv += Math.max(0, -dd) * gv * gv; fMin = Math.min(fMin, d); fMax = Math.max(fMax, d);
      tMin = Math.min(tMin, topF(x, y)); tMax = Math.max(tMax, topF(x, y));
    }
    for (const [E, N] of z.ring) { tMin = Math.min(tMin, topF(E, N)); tMax = Math.max(tMax, topF(E, N)); }
    const meta = { ...fillMeta, role: 'plot', area, status: 'owner-change', note: c.description, source: [A.zoneSource, A.g.terrain.source].filter(Boolean).join(' · '), ocId: A.id };
    const add = (fn, mat, L, name, rows) => {
      const m = regionMesh(z.ring, fn, coords, materials.get(mat), null, T, zCtrl);
      const gz = new THREE.Group(); gz.add(m);
      const pts = z.ring.concat([z.ring[0]]).map(([E, N]) => coords.toLocal(E, N, fn(E, N) + 0.02));
      gz.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: ocColor })));
      registry.add(gz, { floor: 'site', system: 'site', stage: 'finishes', step: 'development', layer: L.layer }, { ...meta, name, rows, hMax: m.userData.hMax, hMin: m.userData.hMin });
      scene.add(gz);
    };
    const f3 = (h) => `${h.toFixed(3)} (${(h - coords.H0 < 0 ? '−' : '+') + Math.abs(h - coords.H0).toFixed(3)})`;
    const rng = (a, b) => (Math.abs(b - a) < 0.0005 ? f3(a) : `${f3(a)} – ${f3(b)}`);
    if (fillL) add(botF, 'soilFillLocal', fillL, `${zl} – ${fillL.label} (${A.id}, החלטת אביחי)`, [
      ['חומר', fillL.material], ['מ-', 'פני הקרקע אחרי היישור (חישוף + יישור המגרש)'], ['עד', `תחתית המצע ${rng(tMin - t, tMax - t)}`],
      ['עובי', `${Math.round(fMin * 100)}–${Math.round(fMax * 100)} ס"מ`], ['נפח מילוי', `${fv.toFixed(1)} מ"ק`],
      ...(cv > 0.05 ? [['חיתוך (קרקע מעל תחתית המצע)', `${cv.toFixed(1)} מ"ק`]] : []), ['שטח', `${area.toFixed(1)} מ"ר`]]);
    if (base) add(topF, 'gardenBase', base, `${zl} – ${base.label} ${Math.round(t * 100)} ס"מ (${A.id}, החלטת אביחי)`, [
      ['ראש המצע', `${rng(tMin, tMax)} = פני הריצוף ${FP?.slab || ''} − ${Math.round(Math.abs(FP?.offset_m || 0) * 100)} ס"מ`],
      ['תחתית', rng(tMin - t, tMax - t)], ['עובי', `${Math.round(t * 100)} ס"מ`], ['חומר / הידוק', `${base.material} · ${base.compaction}`],
      ['נפח', `${(area * t).toFixed(2)} מ"ק`], ['שטח', `${area.toFixed(1)} מ"ר`]]);
    if (turf) { const tt = turf.thickness_m, tF = (E, N) => topF(E, N) + tt, above = tt + (FP?.offset_m || 0);
      add(tF, 'gardenTurf', turf, `${zl} – ${turf.label} ${Math.round(tt * 100)} ס"מ (${A.id}, החלטת אביחי)`, [
        ['פני הדשא', `${rng(tMin + tt, tMax + tt)} = פני הריצוף ${FP?.slab || ''} ${above >= 0 ? '+' : '−'} ${Math.round(Math.abs(above) * 100)} ס"מ`],
        ['עובי', `${Math.round(tt * 100)} ס"מ (על המצע)`], ['חומר', turf.material], ['שטח', `${area.toFixed(1)} מ"ר`]]); }
    (stats.gardens ||= []).push({ id: A.id, zone: zl, area_m2: area, top: [tMin, tMax], base_m3: area * t, fill_m3: fv, cut_m3: cv, fillThk: [fMin, fMax] });
  };
  // the two versions of every owner-change zone of the final surface
  const ocById = Object.fromEntries((data.ownerChanges?.changes || []).map(c => [c.id, c]));
  const ocColor = display.framing.ownerChangeColor;
  for (const z of ocZones) {
    const zCtrl = ctrlL.filter(p => pointInRing(p.x, p.y, z.ring));
    for (const v of z.versions) {
      if (v.applied?.layers) { buildLayers(z, v, zCtrl); continue; }
      const c = v.oc ? (ocById[v.oc.id] || { title: v.oc.id, description: '' }) : null;
      const m = regionMesh(z.ring, v.fn, coords, materials.get('soilPlot'), null, T, v.plans ? zCtrl : []);
      const gz = new THREE.Group(); gz.add(m);
      if (!v.plans || v.applied) {
        const pts = z.ring.concat([z.ring[0]]).map(([E, N]) => coords.toLocal(E, N, v.fn(E, N) + 0.02));
        gz.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: ocColor })));
      }
      registry.add(gz, { floor: 'site', system: 'site', stage: 'finishes', step: 'development', layer: 'topoPlanned' }, { ...fillMeta,
        name: v.applied ? `מגרש 5187 – פני קרקע ${coords.fmtH(v.fn(z.ring[0][0], z.ring[0][1]))} (${v.applied.id}, החלטת אביחי)${z.slab && v.applied !== z.slab && !z.slab.s.applied ? ` · ${z.slab.id}: לפי התוכניות` : v.applied === z.slab ? ' – מתחת לרצפה' : ''}` : v.plans ? `מגרש 5187 – פני קרקע מתוכננים (${v.ids.join(' / ')}: לפי התוכניות)` : `${v.oc.id} – ${c.title}${v.oc === z.slab ? ' (הקרקע מתחת לרצפה)' : ''}`,
        role: 'plot', hMax: m.userData.hMax, hMin: m.userData.hMin, area: Math.abs(ringArea(z.ring)),
        status: v.applied ? 'owner-change' : v.plans ? 'source' : 'owner-change', ...(v.variant ? { variant: v.variant } : {}),
        note: v.applied ? (ocById[v.applied.id]?.description || '') : v.plans ? 'לפי גבהי הפיתוח בהיתר (data/site/development-heights.json).' : c.description,
        source: v.applied ? (v.applied.g.terrain || v.applied.g.slab).source : v.plans ? fillMeta.source : (v.oc.g.terrain || v.oc.g.slab).source });
      scene.add(gz);
    }
    if (!z.slab) continue;
    const c = ocById[z.slab.id] || { title: z.slab.id, description: '' };
    z.id = z.slab.id; z.slab = z.slab.s;
    if (z.slab) {   // the concrete slab of OC-8 (with the change only)
      const toV = ([E, N]) => { const [x, zz] = coords.xz(E, N); return new THREE.Vector2(x, -zz); };
      const geo = new THREE.ExtrudeGeometry(new THREE.Shape(z.ring.map(toV)), { depth: z.slab.thickness_m, bevelEnabled: false });
      geo.rotateX(-Math.PI / 2); geo.translate(0, z.slab.topRel - z.slab.thickness_m, 0);
      const sm = new THREE.Mesh(geo, materials.get('concreteProvisional')); sm.castShadow = sm.receiveShadow = true;
      const gs = new THREE.Group(); gs.add(sm, new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({ color: ocColor })));
      const d = document.createElement('div'); d.className = 'lbl oc-tag'; d.textContent = `${z.id} · רצפה עד החומה`;
      const cen = z.ring.reduce((a, p) => [a[0] + p[0] / z.ring.length, a[1] + p[1] / z.ring.length], [0, 0]);
      const lo = new CSS2DObject(d); lo.position.copy(coords.toLocal(cen[0], cen[1], coords.H0 + z.slab.topRel + 0.3)); gs.add(lo);
      registry.add(gs, { floor: 'ground', system: 'structure', stage: 'slab', step: 'outdoorSlabs', layer: 'groundOutdoorSlabs' }, {
        name: `${z.slab.id} – ${c.title}`, kind: 'slab', status: 'owner-change', ...(z.slab.applied ? {} : { variant: { change: z.id, show: 'changed' } }),
        rows: [['ראש', `${coords.fmtH(coords.H0 + z.slab.topRel)}`], ['עובי', `${z.slab.thickness_m} מ' (זמני)`], ['שטח', `${z.slab.area_m2.toFixed(2)} מ"ר`], ['נפח בטון', `${(z.slab.area_m2 * z.slab.thickness_m).toFixed(2)} מ"ק`]],
        note: c.description, source: z.slab.source });
      scene.add(gs);
    }
  }
  scene.add(group);
  for (const w of shoringMeshes) {
    registry.add(w, { floor: 'unit', system: 'structure', stage: 'excavation', stepTo: 'waterproofing', layer: 'shoring' }, {
      name: 'קיר דיפון (זמני – חסר תכנון)', status: 'provisional',
      rows: [['אורך כולל', `${shoringLen.toFixed(1)} מ'`], ['גובה חתך מקסימלי', `${shoringMaxH.toFixed(2)} מ'`], ['שטח דופן', `${shoringArea.toFixed(1)} מ"ר`],
        ['כלונסאות דיפון', 'ø50 לפחות (דוח קרקע 5.6); מרווח/עומק/עוגנים – חסר']],
      note: ex.shoringNote, source: ex.shoringRule,
    });
    scene.add(w);
  }
  // height lookups (labels, walk, inspect) follow the applied owner decisions (OC-7) as well
  const applied = ocZones.filter(z => z.terrain?.g.terrain.applied);
  const finalA = (E, N) => { const z = applied.find(q => pointInRing(E, N, q.ring)); return z ? z.terrain.fn(E, N) : finalZ(E, N); };
  finalA.kind = 'final';
  for (const z of applied) ground.regions.unshift({ ring: z.ring, interp: z.terrain.fn, kind: 'final', id: `${z.terrain.id}-${z.key}` });   // found before the permit surface
  ground.add(lot, finalA, 'excavation', 'lot-257-excavation');
  return stats;
}

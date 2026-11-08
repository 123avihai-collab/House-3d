import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { regionMesh } from './terrain.js';
import { pointInRing, distToPolyline, nearestOnRing, densifyRing, ringArea, distToRing } from './tin.js';

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
  const ctrlL = ctrlB.filter(p => pointInRing(p.x, p.y, lot));
  const meshC = regionMesh(lot, backfill, coords, materials.get('soilPit'), materials.get('soilCut'), T, ctrlL);
  const meshW = regionMesh(lot, working, coords, materials.get('soilPit'), materials.get('soilCut'), T, ctrlL);
  const meshF = regionMesh(lot, finalZ, coords, materials.get('soilPlot'), materials.get('soilCut'), T, ctrlL);
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
    note: 'פני הקרקע הסופיים בגינה וברצועות – לפי הגבהים המתוכננים במפה למשתכן; בתוך הבית, הרצפות, הבריכה והחצרות – המבנה.', source: 'data/site/planned-heights.json; data/structure/floor-ground.json' });
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
  ground.add(lot, finalZ, 'excavation', 'lot-257-excavation');
  return stats;
}

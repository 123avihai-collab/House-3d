import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { regionMesh } from './terrain.js';
import { pointInRing, distToPolyline, nearestOnRing, densifyRing, ringArea } from './tin.js';

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
  const existing = ground.regions.find(r => r.id === 'lot-257-existing')?.interp;
  if (!existing) { console.warn('no existing ground for excavation'); return null; }
  const bottom = ex.bottomOutlineITM;
  const floor = ex.floorOutlineITM;
  const runs = ex.shoredRunsITM || [];
  const zb = ex.bottomAbs;
  // a point outside the floor is behind a shoring wall when its nearest floor-outline point lies on a shored run
  const pitZ = (E, N) => {
    if (pointInRing(E, N, floor)) return zb;
    const q = nearestOnRing(E, N, floor);
    if (runs.some(r => distToPolyline(q.x, q.y, r) <= D.shoringMatchTol_m)) return existing(E, N);
    return Math.min(existing(E, N), zb + q.dist / ex.sideSlope_HperV);
  };
  // trenches for the foundation beams outside the basement pit (stage 2b, provisional with the beams):
  // beam footprint (width from the tag) down to beam bottom − (lean concrete + void formers) from the excavation build-up
  const below = ex.bottomBuildUp.filter(b => b.thickness_m).reduce((a, b) => a + b.thickness_m, 0);
  const trenches = (data.framing?.groundBeams || []).filter(b => b.axisITM && b.stage === 'groundBeams' && b.sheet === 'K-21').map(b => {
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
  const pitOnly = pitZ;
  // local pits for chambers below the excavation bottom (plumbing plan: I.L. of the chamber)
  const chambers = (data.plumbingFoundations?.chambers || []).filter(c => c.IL < zb);
  const chamberZ = (E, N) => { let z = Infinity; for (const c of chambers) if (Math.hypot(E - c.E, N - c.N) <= c.diameter_m / 2) z = Math.min(z, c.IL); return z; };
  const pitZ2 = (E, N) => Math.min(pitOnly(E, N), trenchZ(E, N), chamberZ(E, N));
  pitZ2.kind = 'excavation';
  const lot = data.plot.ring;
  const T = { ...display.terrain, sampleSpacing_m: D.sampleSpacing_m, boundaryDensify_m: D.sampleSpacing_m };
  const ctrl = densifyRing(floor, D.sampleSpacing_m).filter(([x, y]) => pointInRing(x, y, lot)).map(([x, y]) => ({ x, y, z: zb }));
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
  const mesh = regionMesh(lot, pitZ2, coords, materials.get('soilPit'), materials.get('soilCut'), T, ctrl);

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
  group.add(mesh);

  // bottom outline line
  const fat = (pts, color, width, dashed = false) => {
    const lg = new LineGeometry(); lg.setPositions(pts.flatMap(v => [v.x, v.y, v.z]));
    const m = new LineMaterial({ color, linewidth: width, dashed, dashSize: 0.5, gapSize: 0.3 });
    m.resolution.copy(ctx.viewer.resolution); lineMats.push(m);
    const l = new Line2(lg, m); l.computeLineDistances(); l.renderOrder = 6; return l;
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

  const chamberVol = chambers.reduce((a, c) => a + Math.PI * (c.diameter_m / 2) ** 2 * Math.max(0, zb - c.IL), 0);
  const stats = { chamberPitVolume_m3: chamberVol, volume_m3: vol + trenchVol + chamberVol, pitVolume_m3: vol, trenchVolume_m3: trenchVol, trenchCount: trenches.length, maxDepth_m: maxDepth, bottomArea_m2: Math.abs(ringArea(floor)), shoringLength_m: shoringLen, shoringMaxHeight_m: shoringMaxH, shoringArea_m2: shoringArea };
  registry.add(group, { floor: 'unit', system: 'site', stage: 'excavation', stageTo: 'ceiling', layer: 'excavation' }, {
    name: 'חפירה ליחידת הדיור (מרתף)', kind: 'terrain', role: 'excavation', ring: lot,
    hMin: zb, hMax: mesh.userData.hMax, area: stats.bottomArea_m2,
    rows: [
      ['מפלס תחתית חפירה', coords.fmtH(zb)],
      ['שיפוע דפנות', `1:${ex.sideSlope_HperV} (אנכי:אופקי)`],
      ['מרווח עבודה בתחתית', `${ex.workingSpace_m.toFixed(2)} מ' מהקיר החיצוני`],
      ['נפח חפירה (מול קרקע 2025)', `${vol.toFixed(1)} מ"ק`],
      ['עומק חפירה מקסימלי', `${maxDepth.toFixed(2)} מ'`],
      ['שטח תחתית', `${stats.bottomArea_m2.toFixed(1)} מ"ר`],
      ['שטח תחתית קורות/מרתף', `${Math.abs(ringArea(bottom)).toFixed(1)} מ"ר`],
      ['דיפון (זמני)', `${shoringLen.toFixed(1)} מ' · גובה חתך עד ${shoringMaxH.toFixed(2)} מ' · ${shoringArea.toFixed(1)} מ"ר`],
    ],
    note: `מרווח עבודה ${ex.workingSpace_m} מ'${ex.workingSpaceStatus === 'provisional' ? ' – זמני, לאישור' : ''}. ${ex.shoringNote}`, status: ex.shoringStatus,
    source: ex.source,
  });
  scene.add(group);
  for (const w of shoringMeshes) {
    registry.add(w, { floor: 'unit', system: 'structure', stage: 'excavation', stageTo: 'ceiling', layer: 'shoring' }, {
      name: 'קיר דיפון (זמני – חסר תכנון)', status: 'provisional',
      rows: [['אורך כולל', `${shoringLen.toFixed(1)} מ'`], ['גובה חתך מקסימלי', `${shoringMaxH.toFixed(2)} מ'`], ['שטח דופן', `${shoringArea.toFixed(1)} מ"ר`],
        ['כלונסאות דיפון', 'ø50 לפחות (דוח קרקע 5.6); מרווח/עומק/עוגנים – חסר']],
      note: ex.shoringNote, source: ex.shoringRule,
    });
    scene.add(w);
  }
  ground.add(lot, pitZ2, 'excavation', 'lot-257-excavation');
  return stats;
}

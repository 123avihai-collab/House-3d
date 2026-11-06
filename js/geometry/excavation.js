import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { regionMesh } from './terrain.js';
import { pointInRing, distToRing, densifyRing, ringArea } from './tin.js';

// Excavation for the dwelling unit (basement), from data/structure/excavation.json:
// pit surface z(x) = min( existing ground 2025 , bottom + max(0, d - workingSpace) / slope ),
// d = horizontal distance outside the bottom outline. Clipped to lot 5187; where the pit is below the
// existing ground on the lot line, shoring is required (soil report §10.2) and the line is flagged.
export function buildExcavation(ctx) {
  const { data, coords, registry, scene, materials, display, ground, lineMats } = ctx;
  const ex = data.excavation;
  const D = display.excavation;
  const existing = ground.regions.find(r => r.id === 'lot-257-existing')?.interp;
  if (!existing) { console.warn('no existing ground for excavation'); return null; }
  const bottom = ex.bottomOutlineITM;
  const zb = ex.bottomAbs;
  const pitZ = (E, N) => {
    const d = pointInRing(E, N, bottom) ? 0 : distToRing(E, N, bottom);
    return Math.min(existing(E, N), zb + Math.max(0, d - ex.workingSpace_m) / ex.sideSlope_HperV);
  };
  pitZ.kind = 'excavation';
  const lot = data.plot.ring;
  const T = { ...display.terrain, sampleSpacing_m: D.sampleSpacing_m, boundaryDensify_m: D.sampleSpacing_m };
  const ctrl = densifyRing(bottom, D.sampleSpacing_m).filter(([x, y]) => pointInRing(x, y, lot)).map(([x, y]) => ({ x, y, z: zb }));
  const mesh = regionMesh(lot, pitZ, coords, materials.get('soilPit'), materials.get('soilCut'), T, ctrl);

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

  // shoring: lot-line stretches where the pit surface is below existing ground
  const edge = densifyRing(lot, 0.2);
  const runs = []; let cur = null;
  for (const [x, y] of edge.concat([edge[0]])) {
    const cut = existing(x, y) - pitZ(x, y);
    if (cut > D.shoringMinCut_m) { (cur ||= []).push([x, y, cut]); } else if (cur) { runs.push(cur); cur = null; }
  }
  if (cur) runs.push(cur);
  let shoringLen = 0, shoringMaxH = 0;
  for (const r of runs) {
    if (r.length < 2) continue;
    group.add(fat(r.map(([x, y]) => coords.toLocal(x, y, existing(x, y) + 0.05)), D.shoringColor, 4));
    for (let i = 1; i < r.length; i++) shoringLen += Math.hypot(r[i][0] - r[i - 1][0], r[i][1] - r[i - 1][1]);
    shoringMaxH = Math.max(shoringMaxH, ...r.map(p => p[2]));
  }
  if (runs.length) {
    const longest = runs.reduce((a, b) => (b.length > a.length ? b : a));
    const m = longest[Math.floor(longest.length / 2)];
    const div = document.createElement('div'); div.className = 'lbl shoring';
    div.textContent = `נדרש דיפון · ${shoringLen.toFixed(1)} מ' · עד ${shoringMaxH.toFixed(2)} מ'`;
    div.title = ex.shoringRule;
    const o = new CSS2DObject(div); o.position.copy(coords.toLocal(m[0], m[1], existing(m[0], m[1]) + 1)); group.add(o);
  }
  const lbl = document.createElement('div'); lbl.className = 'lbl h h-zero';
  lbl.textContent = `תחתית חפירה ${coords.fmtH(zb)}`;
  const c = bottom.reduce((a, p) => [a[0] + p[0] / bottom.length, a[1] + p[1] / bottom.length], [0, 0]);
  const lo = new CSS2DObject(lbl); lo.position.copy(coords.toLocal(c[0], c[1], zb + 0.4)); group.add(lo);

  const stats = { volume_m3: vol, maxDepth_m: maxDepth, bottomArea_m2: Math.abs(ringArea(bottom)), shoringLength_m: shoringLen, shoringMaxHeight_m: shoringMaxH };
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
      ['דיפון נדרש לאורך גבול המגרש', `${shoringLen.toFixed(1)} מ' (גובה חתך עד ${shoringMaxH.toFixed(2)} מ')`],
    ],
    note: `מרווח עבודה ${ex.workingSpace_m} מ'${ex.workingSpaceStatus === 'provisional' ? ' – זמני, לאישור' : ''}. ${ex.shoringRule}`,
    source: ex.source,
  });
  scene.add(group);
  ground.add(lot, pitZ, 'excavation', 'lot-257-excavation');
  return stats;
}

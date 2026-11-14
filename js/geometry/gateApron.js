import * as THREE from 'three';
import { makeInterpolator } from './tin.js';
import { regionMesh } from './terrain.js';

// Parking entrance inside the lot (data/site/gate-apron.json, tools/derive_gate_apron.py): interlocking pavers "מלבן" 15/30/7
// (development details 003, detail 10) between the parking slab GS3 and the lot line. Finish = a TIN through the control
// points of the data (the parking finish along the slab edge, the buyer's-map lot-corner level on the lot line, the permit spot).
// No dimension is written here.
export function buildGateApron(ctx) {
  const { data, coords, registry, scene, display, materials } = ctx;
  const G = data.gateApron; if (!G) return null;
  const D = display.gateApron || {}, T = display.terrain;
  const f = makeInterpolator(G.control.map(c => ({ x: c.E, y: c.N, z: c.H })));
  const mat = materials.get(G.material);
  const g = regionMesh(G.ringITM, f, coords, mat, null, T, []).children[0].geometry;
  g.translate(0, D.lift_m ?? 0, 0);
  // pavers laid along the lot line (its direction from the ring's longest edge)
  let best = 0, ang = 0; const R = G.ringITM;
  for (let i = 0; i < R.length; i++) { const a = R[i], b = R[(i + 1) % R.length], L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L > best) { best = L; ang = Math.atan2(b[1] - a[1], b[0] - a[0]); } }
  const ca = Math.cos(ang), sa = Math.sin(ang), uv = g.attributes.uv;
  for (let i = 0; i < uv.count; i++) { const u = uv.getX(i), v = uv.getY(i); uv.setXY(i, u * ca + v * sa, -u * sa + v * ca); }
  const m = new THREE.Mesh(g, mat); m.receiveShadow = true;
  const prov = G.layers.filter(l => l.status === 'provisional').map(l => l.label).join(', ');
  registry.add(m, { floor: 'site', system: 'site', stage: 'finishes', layer: 'gateApron' }, {
    name: 'כניסת החניה – אבן משתלבת (בתוך המגרש)', kind: 'paving', id: 'gateApron', provisional: true,
    rows: [['שטח', `${G.area_m2.toFixed(2)} מ"ר`], ['אבן', G.paver.name], ['פני ריצוף', `${G.finishMin.toFixed(2)}–${G.finishMax.toFixed(2)} (קו המגרש ${G.lotLineH.toFixed(2)})`],
      ['מתחת לאבן', `${prov} – אין פרט (זמני)`], ['מקור האבן', G.paver.source]],
    note: 'שכבות המצע זמניות; ההפרש לרחוב בקו המגרש – באבן הגן (docs/open-issues.md)', source: G.source,
  });
  scene.add(m);
  return { area: G.area_m2 };
}

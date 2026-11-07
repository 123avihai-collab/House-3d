import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Perimeter walls (data/structure/perimeter.json, tools/extract_perimeter.py): footing strip on the piles 100–118 + the wall stem.
// No dimensions here – all from the data. Built in the construction step "חומות" (perimeter).
export function buildPerimeter(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const PM = data.perimeter; if (!PM) return null;
  const D = display.framing; const conc = materials.get('concrete');
  const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
  const prism = (ring, z0, z1) => {   // relative levels
    const g = new THREE.ExtrudeGeometry(new THREE.Shape(ring.map(toV)), { depth: z1 - z0, bevelEnabled: false });
    g.rotateX(-Math.PI / 2); g.translate(0, z0, 0);
    const p = g.attributes.position, uv = g.attributes.uv; for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) + p.getZ(i), p.getY(i) + p.getZ(i));
    const m = new THREE.Mesh(g, conc); m.castShadow = m.receiveShadow = true; return m;
  };
  const edges = (m) => new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 30), new THREE.LineBasicMaterial({ color: D.provisionalEdgeColor }));
  const flagged = (st) => st === 'provisional' || st === 'approx';
  const area = (ring) => Math.abs(ring.reduce((a, p, i) => { const q = ring[(i + 1) % ring.length]; return a + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2;
  const SIDE = { W: 'מערבית', NW: 'צפונית (מערב)', NE: 'צפונית (מזרח)', E: 'מזרחית', S: 'דרומית (רחוב)', SW: 'פינה דרום-מערבית' };
  const stats = { footings_m3: 0, walls_m3: 0 };
  // a wall footing that carries a beam the house needs (floor-ground.json outdoorBeamsCheck.earlyFootings – B-58 / B-59 on PF5,
  // Avihai's note 3) is cast before the ground-floor pour, the rest with the perimeter walls
  const early = new Set(data.floorGround?.outdoorBeamsCheck?.earlyFootings || []);
  for (const f of PM.footings) {
    const m = prism(f.ringITM, f.bottomRel, f.topRel); const g = new THREE.Group(); g.add(m); if (flagged(f.status)) g.add(edges(m));
    stats.footings_m3 += f.area_m2 * f.thickness_m;
    registry.add(g, { floor: 'site', system: 'structure', stage: 'groundBeams', layer: 'perimeterFootings', step: early.has(f.id) ? 'underSlab' : 'perimeterFootings' }, {
      id: f.id, name: `יסוד חומה ${SIDE[f.side] || f.side} (${f.id})`, status: f.status,
      rows: [['רוחב / עובי', `${f.width_m.toFixed(2)} / ${f.thickness_m.toFixed(2)} מ'`], ['תחתית / ראש', `${coords.fmtH(coords.H0 + f.bottomRel)} / ${coords.fmtH(coords.H0 + f.topRel)}`],
        ['כלונסאות', f.piles.join(', ') || '—'], ['נפח בטון', `${(f.area_m2 * f.thickness_m).toFixed(2)} מ"ק`]],
      note: [f.note, early.has(f.id) ? 'נוצק לפני רצפת הקרקע: נושא קורה שהבית נשען עליה (B-58 / B-59).' : ''].filter(Boolean).join(' '), source: f.source,
    });
    scene.add(g);
  }
  for (const w of PM.walls) {
    const m = prism(w.ringITM, w.bottomRel, w.topRel); const g = new THREE.Group(); g.add(m); if (flagged(w.status)) g.add(edges(m));
    const v = area(w.ringITM) * (w.topRel - w.bottomRel); stats.walls_m3 += v;
    if (!w.post) {
      const c = w.ringITM.reduce((a, p) => [a[0] + p[0] / w.ringITM.length, a[1] + p[1] / w.ringITM.length], [0, 0]);
      const d = document.createElement('div'); d.className = 'lbl beam'; d.textContent = `חומה ${SIDE[w.side]} · ראש ${w.topAbs.toFixed(2)}`;
      const o = new CSS2DObject(d); o.position.copy(coords.toLocal(c[0], c[1], coords.H0 + w.topRel + D.labelLift_m)); g.add(o);
    }
    registry.add(g, { floor: 'site', system: 'structure', stage: 'walls', layer: 'perimeterWalls', step: 'perimeterWalls' }, {
      id: w.id, name: w.post ? `עמוד שער (${w.id})` : `חומה ${SIDE[w.side]} (${w.id})`, status: w.status,
      rows: [['עובי / אורך', `${w.thickness_m.toFixed(2)} / ${w.length_m.toFixed(2)} מ'`], ['תחתית (ראש היסוד) / ראש', `${coords.fmtH(coords.H0 + w.bottomRel)} / ${coords.fmtH(coords.H0 + w.topRel)}`],
        ['יושב על', w.standsOn || '— (אין יסוד ב-K-400)'], ['נפח בטון', `${v.toFixed(2)} מ"ק`]],
      note: w.topSource, source: w.source,
    });
    scene.add(g);
  }
  return stats;
}

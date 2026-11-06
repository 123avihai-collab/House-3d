import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Stairs + the utilities pillar (data/structure/stairs.json, tools/extract_stairs.py). No dimensions here – all from the data.
//  ST1 concrete stair basement -> ground (flights = side profile extruded across the flight width; landings = slabs)
//  ST2 light stair ground -> first floor (treads), ST3 outside concrete stair down to the unit
//  PIL1 garbage room + electric cabinet niche (walls), and the cabinet itself.
export function buildStairs(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const S = data.stairs; if (!S) return null;
  const D = display.framing; const DS = display.stairs;
  const conc = materials.get('concrete');
  const light = materials.get('stairLight'); const steel = materials.get('cabinetSteel');
  const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
  const prism = (ring, holes, z0, z1, mat) => {   // z0/z1 relative to ±0.00
    const sh = new THREE.Shape(ring.map(toV)); for (const h of holes || []) sh.holes.push(new THREE.Path(h.map(toV)));
    const g = new THREE.ExtrudeGeometry(sh, { depth: z1 - z0, bevelEnabled: false });
    g.rotateX(-Math.PI / 2); g.translate(0, z0, 0);
    const p = g.attributes.position, uv = g.attributes.uv; for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) + p.getY(i), p.getZ(i) + p.getY(i));
    const m = new THREE.Mesh(g, mat); m.castShadow = m.receiveShadow = true; return m;
  };
  const edges = (mesh, color) => new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 30), new THREE.LineBasicMaterial({ color }));
  const label = (text, E, N, rel, cls = 'lbl beam') => {
    const d = document.createElement('div'); d.className = cls; d.textContent = text;
    const o = new CSS2DObject(d); o.position.copy(coords.toLocal(E, N, coords.H0 + rel)); return o;
  };
  const centroid = (ring) => ring.reduce((a, p) => [a[0] + p[0] / ring.length, a[1] + p[1] / ring.length], [0, 0]);
  // a straight flight: side profile (s along the climb, z level) extruded to the right of the climb by the flight width
  const flightMesh = (f, mat) => {
    const sh = new THREE.Shape(f.profile.map(([s, z]) => new THREE.Vector2(s, z)));
    const g = new THREE.ExtrudeGeometry(sh, { depth: f.width_m, bevelEnabled: false });
    const [x0, z0] = coords.xz(...f.originITM);
    const dir = (v) => { const [a, b] = coords.xz(f.originITM[0] + v[0], f.originITM[1] + v[1]); return new THREE.Vector3(a - x0, 0, b - z0).normalize(); };
    const run = dir(f.runDirITM), right = dir(f.rightDirITM), up = new THREE.Vector3(0, 1, 0);
    const M = new THREE.Matrix4().makeBasis(run, up, right); M.setPosition(x0, 0, z0);
    g.applyMatrix4(M);
    const p = g.attributes.position, uv = g.attributes.uv; for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) + p.getZ(i), p.getY(i));
    const m = new THREE.Mesh(g, mat); m.castShadow = m.receiveShadow = true; return m;
  };
  const stats = { concrete_m3: 0 };
  const flagged = (st) => st === 'provisional' || st === 'approx';
  const vol = (g) => { // volume of a closed mesh (signed tetrahedra)
    const p = g.attributes.position, idx = g.index; let v = 0; const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    const n = idx ? idx.count : p.count;
    for (let i = 0; i < n; i += 3) {
      const [i0, i1, i2] = idx ? [idx.getX(i), idx.getX(i + 1), idx.getX(i + 2)] : [i, i + 1, i + 2];
      a.fromBufferAttribute(p, i0); b.fromBufferAttribute(p, i1); c.fromBufferAttribute(p, i2); v += a.dot(b.cross(c)) / 6;
    }
    return Math.abs(v);
  };

  for (const st of S.stairs) {
    const g = new THREE.Group(); let m3 = 0;
    if (st.kind === 'concrete') {
      for (const f of st.flights) {
        const m = flightMesh(f, conc); g.add(m); if (flagged(st.status)) g.add(edges(m, D.provisionalEdgeColor)); m3 += vol(m.geometry);
      }
      for (const L of st.landings) {
        const m = prism(L.ringITM, null, L.topRel - L.thickness_m, L.topRel, conc); g.add(m); if (flagged(st.status)) g.add(edges(m, D.provisionalEdgeColor));
        m3 += vol(m.geometry);
      }
      stats.concrete_m3 += m3;
    } else {
      for (const t of st.treads) {
        const m = prism(t.ringITM, null, t.topRel - st.treadThickness_m, t.topRel, light); g.add(m);
        if (flagged(st.status)) g.add(edges(m, D.provisionalEdgeColor));
      }
    }
    const f0 = st.flights ? st.flights[0] : null;
    const at = f0 ? f0.originITM : centroid(st.treads[0].ringITM);
    const top = st.flights ? Math.max(...st.flights.flatMap((f) => f.treadLevels)) : Math.max(...st.treads.map((t) => t.topRel));
    g.add(label(`${st.name} · ${st.risers} רומים × ${Math.round(st.rise_m * 1000) / 10} ס"מ`, at[0], at[1], top + DS.labelLift_m));
    const tags = st.kind === 'concrete'
      ? { floor: st.floor, system: 'structure', stage: 'slab', layer: 'stairs', step: st.step }
      : { floor: st.floor, system: 'finishes', stage: 'finishes', layer: 'stairsLight' };
    const rows = [['רומים', `${st.risers} × ${(st.rise_m * 100).toFixed(1)} ס"מ`]];
    if (st.flights) rows.push(['שלחים', st.flights.map((f) => `${f.numbers}: רוחב ${f.width_m.toFixed(2)} · שלח ${f.going_m.toFixed(3)}`).join(' | ')],
      ['עובי שיפוע (ניצב)', `${Math.round(st.waist_m * 100)} ס"מ`]);
    if (st.landings?.length) rows.push(['פודסטים', st.landings.map((L) => `${L.label} ${coords.fmtH(coords.H0 + L.topRel)} (D=${Math.round(L.thickness_m * 100)})`).join(' · ')]);
    if (st.treads) rows.push(['מדרכים', `${st.treads.length} (כולל 27–28 פנייה), עובי ${Math.round(st.treadThickness_m * 100)} ס"מ`]);
    if (m3) rows.push(['נפח בטון', `${m3.toFixed(2)} מ"ק`]);
    registry.add(g, tags, { name: st.name, status: st.status, rows, note: st.note, source: st.source });
    scene.add(g);
  }

  // utilities pillar: garbage room + electric-cabinet niche (cast with the perimeter walls), and the cabinet
  const P = S.pillar;
  if (P) {
    const g = new THREE.Group();
    P.wallsITM.forEach((w, i) => { const m = prism(w, P.wallHolesITM?.[i], P.bottomRel, P.topRel, conc); g.add(m, edges(m, D.provisionalEdgeColor)); });
    const c0 = centroid(P.wallsITM[0]);
    g.add(label(`${P.name} · ראש ${coords.fmtH(coords.H0 + P.topRel)}`, c0[0], c0[1], P.topRel + DS.labelLift_m));
    registry.add(g, { floor: 'site', system: 'site', stage: 'walls', layer: 'pillar', step: P.step }, {
      name: P.name, status: P.status,
      rows: [['תחתית / ראש', `${coords.fmtH(coords.H0 + P.bottomRel)} / ${coords.fmtH(coords.H0 + P.topRel)}`], ['עובי קיר', P.wallThickness_m.map((t) => `${Math.round(t * 100)} ס"מ`).join(', ')],
        ['שטח פנים', `${P.innerAreas_m2.map((a) => a.toFixed(2)).join(' / ')} מ"ר (חדר אשפה / נישת הארון)`]],
      note: P.note, source: P.source,
    });
    scene.add(g);
    const C = P.cabinet;
    if (C) {
      const cg = new THREE.Group(); const m = prism(C.ringITM, null, C.bottomRel, C.topRel, steel); cg.add(m, edges(m, D.provisionalEdgeColor));
      const cc = centroid(C.ringITM); cg.add(label(C.name, cc[0], cc[1], C.topRel + DS.labelLift_m));
      registry.add(cg, { floor: 'site', system: 'electrical', stage: 'finishes', layer: 'electricCabinet' }, {
        name: C.name, status: C.status, rows: [['גובה', `${coords.fmtH(coords.H0 + C.bottomRel)} – ${coords.fmtH(coords.H0 + C.topRel)}`]], note: C.note, source: P.source,
      });
      scene.add(cg);
    }
  }
  return stats;
}

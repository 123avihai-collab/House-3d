import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Stage 4a – block walls (data/architecture/blocks.json, tools/extract_blocks.py): every run laid course by course in the
// owner's block (blocks.json block: Ytong 60×25), half-block bond on every other course, blocks cut at the openings and at
// the run ends; the roller-shutter boxes sit inside the top of their openings (box height from the family in the permit
// sheet). Step "blockWalls" (after the skeleton). No dimensions here – block size, run geometry and levels come from the data.
export function buildBlocks(ctx) {
  const { data, coords, registry, scene, display } = ctx;
  const B = data.blocks; if (!B) return null;
  const DB = display.blocks, DF = display.framing;
  const BL = B.block.length_m, BH = B.block.height_m;
  const fullM = new THREE.MeshStandardMaterial({ color: DB.blockColor, roughness: 0.9 });
  const cutM = new THREE.MeshStandardMaterial({ color: DB.cutBlockColor, roughness: 0.9 });
  const boxM = new THREE.MeshStandardMaterial({ color: DB.shutterBoxColor, roughness: 0.6 });
  const unit = new THREE.BoxGeometry(1, 1, 1);
  const FLOOR = { unit: 'יחידת דיור', ground: 'קומת קרקע', first: "קומה א'" };
  const stats = { full: 0, cut: 0, area_m2: 0, byThickness: {}, boxes: 0 };
  for (const w of B.walls) {
    const [[E0, N0], [E1, N1]] = w.axisITM, L = w.length_m, t = w.thickness_m;
    const p0 = coords.toLocal(E0, N0, coords.H0), p1 = coords.toLocal(E1, N1, coords.H0);
    const dir = new THREE.Vector3().subVectors(p1, p0).normalize(), q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1, 0, 0), dir);
    const full = [], cut = [];
    let k = 0, z = w.bottomRel;
    while (z < w.topRel - 0.005) {   // same coursing as tools/extract_blocks.py
      const h = Math.min(BH, w.topRel - z), off = (BL / 2) * (k % 2);
      let segs = [[0, L]];
      for (const o of w.openings) if (o.z0 < z + h - 0.005 && o.z1 > z + 0.005)
        segs = segs.flatMap(([a, b]) => [[a, Math.min(b, o.s0)], [Math.max(a, o.s1), b]]).filter(([a, b]) => b - a > 0.005);
      for (const [a, b] of segs) for (let x = -off; x < b - 0.005; x += BL) {
        const xa = Math.max(x, a), xb = Math.min(x + BL, b); if (xb - xa <= 0.005) continue;
        (xb - xa >= BL - 0.005 && h >= BH - 0.005 ? full : cut).push([xa, xb, z, h]);
      }
      k++; z += h;
    }
    const g = new THREE.Group();
    for (const [list, mat] of [[full, fullM], [cut, cutM]]) {
      if (!list.length) continue;
      const im = new THREE.InstancedMesh(unit, mat, list.length), M = new THREE.Matrix4(), S = new THREE.Vector3();
      list.forEach(([xa, xb, zz, h], i) => {
        const c = p0.clone().addScaledVector(dir, (xa + xb) / 2); c.y = zz + h / 2;
        S.set((xb - xa) - DB.joint_m, h - DB.joint_m, t); M.compose(c, q, S); im.setMatrixAt(i, M);
      });
      im.castShadow = im.receiveShadow = true; g.add(im);
    }
    if (w.status !== 'source') g.add(new THREE.BoxHelper(g, DF.provisionalEdgeColor));
    const tc = Math.round(t * 100);
    stats.full += full.length; stats.cut += cut.length; stats.area_m2 += w.area_m2;
    const bt = (stats.byThickness[tc] ||= { full: 0, cut: 0, area_m2: 0 }); bt.full += full.length; bt.cut += cut.length; bt.area_m2 += w.area_m2;
    registry.add(g, { floor: w.floor, system: 'walls', stage: 'walls', layer: 'blockWalls', step: 'blockWalls' }, {
      id: w.id, name: `קיר בלוקים ${tc} ס"מ – ${FLOOR[w.floor] || w.floor}`, status: w.status,
      rows: [['בלוק', `${B.block.type} ${Math.round(BL * 100)}×${Math.round(BH * 100)}, עובי ${tc}`], ['אורך × גובה', `${L.toFixed(2)} × ${(w.topRel - w.bottomRel).toFixed(2)} מ'`],
        ['נדבכים', `${w.courses}`], ['בלוקים', `${full.length} שלמים + ${cut.length} חתוכים`], ['שטח נטו', `${w.area_m2.toFixed(2)} מ"ר`],
        ['פתחים', w.openings.map(o => o.id + (o.shutter ? ' (תריס)' : '')).join(', ') || '—'], ['תחתית / ראש', `${coords.fmtH(coords.H0 + w.bottomRel)} / ${coords.fmtH(coords.H0 + w.topRel)}`]],
      note: [w.note, 'פריסת הנדבכים: חצי בלוק בדילוג בכל נדבך שני; נדבך עליון חתוך לגובה התקרה / הקורה.'].filter(Boolean).join(' '), source: w.source,
    });
    scene.add(g);
  }
  // roller-shutter boxes: inside the top of the opening; depth = the host wall (blocks.json depth_m – built-in box, Avihai 08.11)
  for (const b of B.shutterBoxes) {
    const o = data.openings?.openings?.find(x => x.id === b.opening); if (!o || b.box_m == null) continue;
    const w = B.walls.find(x => x.openings.some(y => y.id === b.opening)); const t = b.depth_m ?? (w ? w.thickness_m : display.openings.defaultWallDepth_m);
    const [E, N] = o.centerITM, c = coords.toLocal(E, N, coords.H0 + b.headRel - b.box_m / 2);
    const [x1, z1] = coords.xz(E + o.axisITM[0], N + o.axisITM[1]), dir = new THREE.Vector3(x1 - c.x, 0, z1 - c.z).normalize();
    const m = new THREE.Mesh(unit, boxM); m.scale.set(o.width_m, b.box_m, t); m.position.copy(c); m.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), dir);
    m.castShadow = true; const g = new THREE.Group(); g.add(m); g.add(new THREE.BoxHelper(m, DF.provisionalEdgeColor));
    const d = document.createElement('div'); d.className = 'lbl beam'; d.textContent = `ארגז תריס ${b.opening} · ${Math.round(b.box_m * 100)}`;
    const lo = new CSS2DObject(d); lo.position.copy(c).add(new THREE.Vector3(0, b.box_m / 2 + DB.labelLift_m, 0)); g.add(lo);
    registry.add(g, { floor: b.floor, system: 'finishes', stage: 'walls', layer: 'shutterBoxes', step: 'blockWalls' }, {
      id: `SB-${b.opening}`, name: `ארגז תריס גלילה – ${b.opening}`, status: b.status,
      rows: [['רוחב', `${Math.round(o.width_m * 100)} ס"מ`], ['גובה הארגז', `${Math.round(b.box_m * 100)} ס"מ (בתוך גובה הפתח, מתחת ל-O.K)`], ['עומק', `${Math.round(t * 100)} ס"מ – ארגז מובנה בעובי הקיר ${b.hostWall ?? ''}`]],
      note: `גובה: ${b.status === 'source' ? 'מהתוכניות / הגרמושקה' : 'משוער'}. עומק: ${b.depthSource ?? 'עובי הקיר'}. רוחב: רוחב הפתח.`, source: b.source,
    });
    scene.add(g); stats.boxes++;
  }
  return stats;
}

import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { cylBetween, collar, sphere } from '../plumbing/geom.js';

// Electrical layer (separate module). Stage ח1: main supply – meter cabinet (pillar) -> feeder conduits -> main panel.
// Data: data/electrical/supply.json (tools/electrical/propose_supply.py), display constants: data/electrical/display.json.
// Everything here is a design proposal (status provisional) – marked in the item rows and tinted.
export function buildElectrical(ctx) {
  const { data, coords, registry, scene } = ctx;
  const S = data.electricalSupply, D = data.electricalDisplay;
  if (!S) return null;
  const H0 = coords.H0, fmtH = (H) => coords.fmtH(H);
  const std = (color, rough = 0.5, metal = 0, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal, ...extra });
  const tint = (m) => { m.emissive = new THREE.Color(D.provisionalTint); m.emissiveIntensity = 0.12; return m; };
  const items = [];
  const label = (parent, pos, text) => {
    const d = document.createElement('div'); d.className = 'lbl el'; d.textContent = text;
    const o = new CSS2DObject(d); o.position.copy(pos); o.userData.annotation = true; parent.add(o); return o;
  };
  const add = (grp, tags, meta) => { scene.add(grp); const it = registry.add(grp, tags, meta); it.meta.electrical = true; items.push(it); return it; };
  const st = (s) => D.statusLabel[s] || s;
  const L = (p) => coords.toLocal(p[0], p[1], p[2]);

  // ---- feeder: parallel conduits along the route (offset sideways; on the risers – along the wall / cabinet back)
  const F = S.feeder, P = S.mainPanel;
  {
    const g = new THREE.Group(); const n = F.conduits.length;
    const pts = F.pts3d.map(L);
    const up = new THREE.Vector3(0, 1, 0);
    const wallAlong = new THREE.Vector3(P.alongITM[0], 0, -P.alongITM[1]).normalize();
    const side = (i) => {   // sideways direction at vertex i (horizontal, perpendicular to the adjacent horizontal run)
      const seg = (a, b) => pts[b].clone().sub(pts[a]);
      let d = null;
      for (const [a, b] of [[i - 1, i], [i, i + 1]]) { if (a < 0 || b >= pts.length) continue; const v = seg(a, b); v.y = 0; if (v.length() > 0.05) { d = d ? d.add(v.normalize()) : v.normalize(); } }
      if (!d || d.length() < 1e-3) return wallAlong.clone();
      return new THREE.Vector3().crossVectors(up, d.normalize()).normalize();
    };
    F.conduits.forEach((c, k) => {
      const off = (k - (n - 1) / 2) * F.conduitSpacing_m, r = c.D_mm / 2000;
      const m = tint(std(k === 0 ? D.conduitColor : D.spareConduitColor, 0.6));
      const q = pts.map((p, i) => p.clone().addScaledVector(i >= pts.length - 2 ? wallAlong : side(i), off));
      for (let i = 0; i < q.length - 1; i++) { const s = cylBetween(q[i], q[i + 1], r, m, D.radialSegments); if (s) g.add(s); }
      for (let i = 1; i < q.length - 1; i++) g.add(sphere(q[i], r, m, 12));
    });
    const mid = pts[3].clone().lerp(pts[4], 0.5);
    label(g, mid.clone().add(new THREE.Vector3(0, D.labelOffset_m, 0)), `קו הזנה ${S.connection.size} · ${n}×ø${F.conduits[0].D_mm} · ${F.length_m.toFixed(1)} מ'`);
    const fails = S.checks.filter(c => !c.ok);
    add(g, { floor: 'site', system: 'electrical', stage: 'groundBeams', layer: 'elSupply' }, {
      name: F.name, kind: 'elFeeder', id: F.id,
      rows: [['מעמד', st(F.status)], ['גודל חיבור', `${S.connection.size} (${S.connection.kVA} kVA) – ${S.connection.note}`], ['כבל', `${F.cable.type} – ${F.cable.note}`],
        ['צנרת', F.conduits.map(c => `${c.role}: ø${c.D_mm} ${c.material}`).join(' · ')], ['אורך תוואי', `${F.length_m.toFixed(2)} מ'`], ['אורך כבל משוער', `${F.cableLength_m.toFixed(1)} מ' (${F.cableLengthNote})`],
        ['רום ציר הצינור', `${fmtH(H0 + F.centreRel)} – ${F.levelRule}`], ['עובר דרך רצפה', F.throughSlab || '—'],
        ['בדיקות מרווח', `${S.checks.length} בדיקות, ${fails.length} נכשלו${fails.length ? ': ' + fails.map(c => c.ref).join(', ') : ''}`],
        ['קצה הפילר', F.pillarEnd.note]],
      source: F.source, note: 'הצעה בלבד – ממתין לאישור' });
  }

  // ---- main panel (surface mounted inside the joinery cabinet)
  {
    const g = new THREE.Group();
    const geo = new THREE.BoxGeometry(P.width_m, P.height_m, P.depth_m);
    const box = new THREE.Mesh(geo, tint(std(D.panelColor, 0.45, 0.3))); box.castShadow = true;
    const c = [P.faceITM[0] + P.normalITM[0] * P.depth_m / 2, P.faceITM[1] + P.normalITM[1] * P.depth_m / 2, H0 + P.bottomRel + P.height_m / 2];
    box.position.copy(L(c));
    const nx = new THREE.Vector3(P.normalITM[0], 0, -P.normalITM[1]).normalize();
    box.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), nx);
    g.add(box);
    const door = new THREE.Mesh(new THREE.BoxGeometry(P.width_m * 0.9, P.height_m * 0.92, 0.012), std(D.panelDoorColor, 0.35, 0.2));
    door.position.copy(box.position).addScaledVector(nx, P.depth_m / 2 + 0.006); door.quaternion.copy(box.quaternion); g.add(door);
    label(g, box.position.clone().add(new THREE.Vector3(0, P.height_m / 2 + D.labelOffset_m, 0)), `לוח ראשי (${st(P.status)})`);
    add(g, { floor: 'ground', system: 'electrical', stage: 'finishes', layer: 'elSupply' }, {
      name: P.name, kind: 'elPanel', id: P.id,
      rows: [['מעמד', st(P.status)], ['החלטה', P.decision], ['קיר', `${P.hostWall} · בלוקים ${Math.round(P.wallThickness_m * 100)} ס"מ · אורך ${P.wallClearLength_m.toFixed(2)} מ'`],
        ['מידות (ר×ג×ע)', `${P.width_m} × ${P.height_m} × ${P.depth_m} מ'`], ['מפלס תחתית / ראש', `${fmtH(H0 + P.bottomRel)} / ${fmtH(H0 + P.topRel)}`], ['הערה', P.note]],
      source: P.source, note: 'הצעה בלבד – ממתין לאישור' });
  }

  // ---- sleeves
  const sleeveM = std(D.sleeveColor, 0.6, 0, { transparent: true, opacity: 0.75 });
  for (const s of S.sleeves) {
    const g = new THREE.Group(); const dir = s.axis === 'v' ? new THREE.Vector3(0, 1, 0) : (() => { const a = L(F.pts3d[0]), b = L(F.pts3d[1]); return b.sub(a).normalize(); })();
    g.add(collar(L(s.at), dir, s.sleeveD_mm / 2000 * (1 + (s.count - 1) * 0.9), D.sleeveLength_m, sleeveM));
    add(g, { floor: s.id === 'ES-1' ? 'ground' : 'site', system: 'electrical', stage: s.id === 'ES-1' ? 'slab' : 'finishes', layer: 'elSupply' }, {
      name: `שרוול ${s.id} – ${s.through}`, kind: 'elSleeve', id: s.id,
      rows: [['מעמד', st(s.status)], ['מעבר', s.through], ['שרוולים', `${s.count} × ø${s.sleeveD_mm}`], ['ITM / רום', `${coords.fmtEN(s.at[0], s.at[1])} · ${fmtH(s.at[2])}`], ['הערה', s.note]],
      source: S.source, note: 'הצעה בלבד – ממתין לאישור' });
  }
  return { items, supply: S };
}

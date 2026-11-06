import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Stage 2b – basement walls, basement floor slabs and foundation beams from data/structure/framing.json.
// All sizes and levels come from the data (tools/extract_framing.py). Concrete is grey; provisional records get an orange edge.
export function buildFoundations(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const F = data.framing; const D = display.framing;
  if (!F) return null;
  const H = (rel) => coords.H0 + rel;
  const shape = (ring, holes = []) => {
    const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
    const s = new THREE.Shape(ring.map(toV));
    for (const h of holes) s.holes.push(new THREE.Path(h.map(toV)));
    return s;
  };
  // extrude a plan polygon between two absolute heights
  const prism = (ring, holes, zBot, zTop, mat) => {
    const g = new THREE.ExtrudeGeometry(shape(ring, holes), { depth: zTop - zBot, bevelEnabled: false });
    g.rotateX(-Math.PI / 2); g.translate(0, zBot - coords.H0, 0);
    // world-metre UVs on all faces (box projection)
    const p = g.attributes.position, n = g.attributes.normal, uv = g.attributes.uv;
    for (let i = 0; i < p.count; i++) {
      const ax = Math.abs(n.getX(i)), ay = Math.abs(n.getY(i));
      if (ay > 0.5) uv.setXY(i, p.getX(i), p.getZ(i)); else if (ax > 0.5) uv.setXY(i, p.getZ(i), p.getY(i)); else uv.setXY(i, p.getX(i), p.getY(i));
    }
    const m = new THREE.Mesh(g, mat); m.castShadow = m.receiveShadow = true; return m;
  };
  const edges = (mesh, color) => new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 30), new THREE.LineBasicMaterial({ color }));
  const label = (text, E, N, Habs, cls = 'lbl beam') => {
    const d = document.createElement('div'); d.className = cls; d.textContent = text;
    const o = new CSS2DObject(d); o.position.copy(coords.toLocal(E, N, Habs)); return o;
  };
  const conc = materials.get('concrete');
  const stats = { walls_m3: 0, slabs_m3: 0, beams_m3: 0, beamsCount: 0, beamsMissing: [] };

  // basement walls
  for (const w of F.basementWalls) {
    const m = prism(w.footprintITM, w.holesITM, H(w.bottomRel), H(w.topRel), conc);
    const g = new THREE.Group(); g.add(m); if (w.status === 'provisional') g.add(edges(m, D.provisionalEdgeColor));
    stats.walls_m3 += w.area_m2 * (w.topRel - w.bottomRel);
    registry.add(g, { floor: 'unit', system: 'structure', stage: 'walls', layer: 'basementWalls' }, {
      name: `קירות מרתף (${w.id})`, status: w.status,
      rows: [['תחתית / ראש', `${coords.fmtH(H(w.bottomRel))} / ${coords.fmtH(H(w.topRel))}`], ['שטח חתך אופקי', `${w.area_m2.toFixed(2)} מ"ר`],
        ['נפח בטון', `${(w.area_m2 * (w.topRel - w.bottomRel)).toFixed(2)} מ"ק`]],
      note: w.note, source: w.source,
    });
    scene.add(g);
  }
  // slabs
  // owner changes (data/changes/owner-changes.json): a slab may be replaced by another level/outline
  const changes = (data.ownerChanges?.changes || []).filter(c => c.replaceSlab);
  const byId = Object.fromEntries(F.slabs.map(s => [s.id, s]));
  const slabs = F.slabs.map(s => {
    const c = changes.find(c => c.replaceSlab.remove === s.id);
    if (!c) return s;
    const from = byId[c.replaceSlab.levelFrom], out = byId[c.replaceSlab.outlineFrom];
    return { ...out, id: `${s.id}→${c.id}`, top: from.top, thickness_m: from.thickness_m, status: 'owner-change', change: c, replaced: s,
      source: `${c.source}; קו: ${out.source}; מפלס ועובי כמו ${from.id}: ${from.source}` };
  });
  for (const s of slabs) {
    if (s.top == null) { stats.beamsMissing.push(s.id); continue; }
    const m = prism(s.outlineITM, s.holesITM || [], H(s.top - s.thickness_m), H(s.top), conc);
    const g = new THREE.Group(); g.add(m);
    const c = s.outlineITM.reduce((a, p) => [a[0] + p[0] / s.outlineITM.length, a[1] + p[1] / s.outlineITM.length], [0, 0]);
    if (s.change) {
      g.add(edges(m, D.ownerChangeColor));
      g.add(label(`${s.change.id} · שינוי אביחי: רצפה O.K=${s.top.toFixed(2)} D=${Math.round(s.thickness_m * 100)} (במקום ${s.replaced.top.toFixed(2)})`, c[0], c[1], H(s.top) + D.labelLift_m, 'lbl change'));
    } else g.add(label(`רצפה O.K=${s.top.toFixed(2)} D=${Math.round(s.thickness_m * 100)}`, c[0], c[1], H(s.top) + D.labelLift_m, 'lbl beam'));
    stats.slabs_m3 += s.area_m2 * s.thickness_m;
    registry.add(g, { floor: 'unit', system: 'structure', stage: 'slab', layer: 'slabs' }, {
      name: s.change ? `רצפת מרתף – ${s.change.id}: ${s.change.title}` : `רצפת מרתף ${s.id} (תלויה)`, status: s.status,
      rows: [['מפלס עליון (O.K)', coords.fmtH(H(s.top))], ['עובי', `${Math.round(s.thickness_m * 100)} ס"מ`], ['שטח', `${s.area_m2.toFixed(2)} מ"ר`],
        ['נפח בטון', `${(s.area_m2 * s.thickness_m).toFixed(2)} מ"ק`]],
      note: s.change ? `${s.change.description} ממתין לאישור: ${s.change.approvals.map(a => a.who).join(', ')}.` : (s.note || 'רצפה תלויה על ארגזי פוליביד 25 ס"מ (דוח קרקע 9.1)'), source: s.source,
    });
    scene.add(g);
  }
  // beams (provisional geometry from the K-400 stipple, section/level from the tags)
  for (const b of F.groundBeams) {
    if (!b.axisITM) { stats.beamsMissing.push(b.id); continue; }
    const [[E1, N1], [E2, N2]] = b.axisITM;
    const L = Math.hypot(E2 - E1, N2 - N1), ux = (E2 - E1) / L, uy = (N2 - N1) / L, hw = b.width_m / 2;
    const ring = [[E1 - uy * hw, N1 + ux * hw], [E2 - uy * hw, N2 + ux * hw], [E2 + uy * hw, N2 - ux * hw], [E1 + uy * hw, N1 - ux * hw]];
    const m = prism(ring, [], H(b.bottomRel), H(b.topRel), conc);
    const g = new THREE.Group(); g.add(m); g.add(edges(m, D.provisionalEdgeColor));
    g.add(label(`${b.id} ${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)}`, (E1 + E2) / 2, (N1 + N2) / 2, H(b.topRel) + D.labelLift_m));
    stats.beams_m3 += L * b.width_m * b.depth_m; stats.beamsCount++;
    registry.add(g, { floor: b.sheet === 'K-11' ? 'unit' : 'ground', system: 'structure', stage: b.stage, layer: 'groundBeams' }, {
      name: `קורה ${b.id} · ${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)}`, status: b.status,
      rows: [['חתך (רוחב/גובה)', `${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)} ס"מ`], ['מפלס עליון (O.K)', coords.fmtH(H(b.topRel))],
        ['מפלס תחתון', coords.fmtH(H(b.bottomRel))], ['אורך (בקירוב)', `${L.toFixed(2)} מ'`], ['גיליון', b.sheet]],
      note: 'מיקום ואורך בקירוב – לפי פס הבטון בתכנית K-400 (PDF). חתך ומפלס – מתווית הקורה. יוחלף ב-IFC.', source: `${b.source}; ${b.geometrySource}`,
    });
    scene.add(g);
  }
  return stats;
}

// Plumbing items that belong to the foundations stage (data/systems/plumbing-foundations.json): chambers.
export function buildPlumbingFoundations(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const P = data.plumbingFoundations; if (!P) return null;
  const D = display.plumbing;
  for (const c of P.chambers) {
    const r = c.diameter_m / 2, h = c.TL - c.IL;
    const geo = new THREE.CylinderGeometry(r, r, h, D.radialSegments, 1, true);
    const mat = new THREE.MeshStandardMaterial({ color: D.chamberColor, roughness: 0.6, side: THREE.DoubleSide });
    const m = new THREE.Mesh(geo, mat); m.position.copy(coords.toLocal(c.E, c.N, (c.TL + c.IL) / 2)); m.castShadow = true;
    const g = new THREE.Group(); g.add(m);
    const d = document.createElement('div'); d.className = 'lbl ' + (c.affectedBy ? 'change' : 'beam');
    d.textContent = `${c.id} תא שאיבה ø${Math.round(c.diameter_m * 100)} · I.L. ${c.IL.toFixed(2)}${c.affectedBy ? ' · מושפע מ-' + c.affectedBy : ''}`;
    const o = new CSS2DObject(d); o.position.copy(coords.toLocal(c.E, c.N, c.TL + 0.4)); g.add(o);
    registry.add(g, { floor: 'unit', system: 'drainage', stage: 'excavation', layer: 'drainChambers' }, {
      name: `${c.id} – ${c.title}`, status: c.affectedBy ? 'owner-change' : c.status,
      rows: [['קוטר', `${Math.round(c.diameter_m * 100)} ס"מ`], ['T.L. (מכסה)', coords.fmtH(c.TL)], ['I.L. (תחתית)', coords.fmtH(c.IL)], ['עומק', `${c.H_m.toFixed(2)} מ'`],
        ['ITM', `${c.E.toFixed(3)} / ${c.N.toFixed(3)}`]],
      note: c.note || null, source: c.source,
    });
    scene.add(g);
  }
  return { chambers: P.chambers.length };
}

// Owner-change zones (data/changes/owner-changes.json → zone): a translucent purple box over the changed area.
export function buildOwnerChangeZones(ctx) {
  const { data, coords, registry, scene, display } = ctx;
  const D = display.framing;
  for (const c of (data.ownerChanges?.changes || [])) {
    if (!c.zone) continue;
    const s = data.framing.slabs.find(x => x.id === c.zone.outlineFrom); if (!s) continue;
    const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
    const g0 = new THREE.ExtrudeGeometry(new THREE.Shape(s.outlineITM.map(toV)), { depth: c.zone.toRel - c.zone.fromRel, bevelEnabled: false });
    g0.rotateX(-Math.PI / 2); g0.translate(0, c.zone.fromRel, 0);
    const mat = new THREE.MeshBasicMaterial({ color: D.ownerChangeColor, transparent: true, opacity: D.ownerChangeZoneOpacity, depthWrite: false });
    const m = new THREE.Mesh(g0, mat); m.renderOrder = 4;
    const g = new THREE.Group(); g.add(m);
    g.add(new THREE.LineSegments(new THREE.EdgesGeometry(g0), new THREE.LineBasicMaterial({ color: D.ownerChangeColor })));
    const d = document.createElement('div'); d.className = 'lbl change'; d.textContent = `${c.id} · אזור משתנה (שינוי אביחי)`;
    const cen = s.outlineITM.reduce((a, p) => [a[0] + p[0] / s.outlineITM.length, a[1] + p[1] / s.outlineITM.length], [0, 0]);
    const o = new CSS2DObject(d); o.position.copy(coords.toLocal(cen[0], cen[1], coords.H0 + c.zone.toRel + 0.3)); g.add(o);
    registry.add(g, { floor: 'unit', system: 'structure', stage: 'excavation', layer: 'ownerChanges' }, {
      name: `${c.id} – ${c.title}`, status: 'owner-change', note: `${c.description} ${c.zone.note}`, source: c.source,
    });
    scene.add(g);
  }
}

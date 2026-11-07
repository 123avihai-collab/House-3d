import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Stage 3 – floor skeleton (data/structure/floor-<floor>.json, tools/extract_floor.py): the floor slab, the walls and columns
// that rise from it, and its ceiling (slab + beams of the sheet above). No dimensions here – all come from the data.
// Tags: slab = {floor, stage 'slab'}; walls/columns = {floor, stage 'walls'}; ceiling slab/beams = {floor, stage 'ceiling'}.
export function buildFloorSkeleton(ctx, F) {
  const { data, coords, registry, scene, materials, display } = ctx;
  if (!F) return null;
  const D = display.framing; const floor = F.floor;
  const H = (rel) => coords.H0 + rel;
  const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
  const prism = (ring, holes, zBot, zTop, mat) => {
    const s = new THREE.Shape(ring.map(toV)); for (const h of holes || []) s.holes.push(new THREE.Path(h.map(toV)));
    const g = new THREE.ExtrudeGeometry(s, { depth: zTop - zBot, bevelEnabled: false });
    g.rotateX(-Math.PI / 2); g.translate(0, zBot - coords.H0, 0);
    const p = g.attributes.position, n = g.attributes.normal, uv = g.attributes.uv;
    for (let i = 0; i < p.count; i++) {
      const ax = Math.abs(n.getX(i)), ay = Math.abs(n.getY(i));
      if (ay > 0.5) uv.setXY(i, p.getX(i), p.getZ(i)); else if (ax > 0.5) uv.setXY(i, p.getZ(i), p.getY(i)); else uv.setXY(i, p.getX(i), p.getY(i));
    }
    const m = new THREE.Mesh(g, mat); m.castShadow = m.receiveShadow = true; return m;
  };
  const edges = (mesh, color) => new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry, 30), new THREE.LineBasicMaterial({ color }));
  const centroid = (ring) => ring.reduce((a, p) => [a[0] + p[0] / ring.length, a[1] + p[1] / ring.length], [0, 0]);
  const label = (text, ring, Habs, cls = 'lbl beam') => {
    const c = centroid(ring); const d = document.createElement('div'); d.className = cls; d.textContent = text;
    const o = new CSS2DObject(d); o.position.copy(coords.toLocal(c[0], c[1], Habs)); return o;
  };
  const conc = materials.get('concrete');
  const flagged = (st) => st === 'provisional' || st === 'approx';
  const stats = { slab_m3: 0, walls_m3: 0, columns_m3: 0, ceiling_m3: 0, beams_m3: 0, beamsMissing: [] };
  const L = (k) => `${floor}${k}`;   // layer ids: groundSlab, groundWalls, groundColumns, groundCeiling, groundCeilingBeams

  // floor slab – one panel per drawn face of K-21, each in its zone (house / entry / mamad / terraces / yards / parking)
  const OUTDOOR = new Set(ctx.data.tags.outdoorZones || []);   // cast after the house shell (step outdoorSlabs)
  for (const s of F.slab) {
    const mamad = s.zone === 'mamad';   // concrete like the house slab; purple edge = per the (missing) shelter plan
    const m = prism(s.footprintITM, s.holesITM, H(s.bottomRel), H(s.topRel), conc);
    const g = new THREE.Group(); g.add(m); if (flagged(s.status)) g.add(edges(m, mamad ? D.ownerChangeColor : D.provisionalEdgeColor));
    const ghost = false;
    g.add(label(`${s.zoneLabel} · O.K=${s.topRel.toFixed(2)} D=${Math.round(s.thickness_m * 100)}`, s.footprintITM, H(s.topRel) + D.labelLift_m));
    if (!ghost) stats.slab_m3 += s.area_m2 * s.thickness_m;
    const layer = s.zone === 'mamad' ? L('Mamad') : OUTDOOR.has(s.zone) ? L('OutdoorSlabs') : L('Slab');
    registry.add(g, { floor, system: 'structure', stage: 'slab', layer, ...(OUTDOOR.has(s.zone) ? { step: 'outdoorSlabs' } : {}) }, {
      id: s.id, name: `${s.zoneLabel} – רצפה ${s.id}`, status: s.status,
      rows: [['אזור', s.zoneLabel], ['מפלס עליון (O.K)', coords.fmtH(H(s.topRel))], ['עובי', `${Math.round(s.thickness_m * 100)} ס"מ`], ['שטח', `${s.area_m2.toFixed(2)} מ"ר`],
        ['נפח בטון', `${(s.area_m2 * s.thickness_m).toFixed(2)} מ"ק`]],
      note: s.note || '', source: s.source,
    });
    scene.add(g);
  }
  // zones without a slab: English courtyards (open down to the basement), stairs down, garden – dashed outline + label
  for (const o of F.openZones || []) {
    const ring = o.footprintITM.concat([o.footprintITM[0]]);
    const pts = ring.map(([E, N]) => coords.toLocal(E, N, H(F.slab[0]?.topRel ?? 0)));
    const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color: D.ownerChangeRemovedColor, dashSize: 0.2, gapSize: 0.12 }));
    ln.computeLineDistances(); ln.userData.annotation = true;
    const g = new THREE.Group(); g.add(ln); g.add(label(`${o.label} – בלי רצפה`, o.footprintITM, H(F.slab[0]?.topRel ?? 0) + D.labelLift_m, 'lbl removed'));
    registry.add(g, { floor, system: 'structure', stage: 'slab', layer: L('OpenZones') }, { name: `${o.label} (${o.area_m2.toFixed(1)} מ"ר)`, pickable: false, note: o.note, source: o.source });
    scene.add(g);
  }
  // tops of the basement / light-well walls that stop at the ground level (grey fill in K-21): cast with the basement walls
  for (const c of F.basementWallCaps || []) {
    const m = prism(c.footprintITM, c.holesITM, H(c.bottomRel), H(c.topRel), conc);
    const g = new THREE.Group(); g.add(m); g.add(edges(m, D.provisionalEdgeColor));
    registry.add(g, { floor: 'ground', system: 'structure', stage: 'slab', layer: 'groundSlab' }, {   // cast with the ground slab (ק9/ק10)
      name: `ראש קיר מרתף (${c.wall}) עד מפלס הקרקע`, status: c.status,
      rows: [['תחתית / ראש', `${coords.fmtH(H(c.bottomRel))} / ${coords.fmtH(H(c.topRel))}`]], note: c.note, source: c.source,
    });
    scene.add(g);
  }
  // walls rising from the floor
  const wg = new THREE.Group(); const wNotes = new Set();
  for (const w of F.walls) {
    // a wall with windows / doors (tools/extract_openings.py): its pieces around the openings + concrete sill / lintel in them
    const g = new THREE.Group();
    const pieces = w.partsITM ? w.partsITM.map((p) => [p.ringITM, p.holesITM, w.bottomRel, w.topRel]) : [[w.footprintITM, w.holesITM, w.bottomRel, w.topRel]];
    for (const f of w.infill || []) pieces.push([f.ringITM, [], f.bottomRel, f.topRel]);
    for (const [r, h, b, t] of pieces) { const m = prism(r, h, H(b), H(t), conc); g.add(m); if (flagged(w.status)) g.add(edges(m, D.provisionalEdgeColor)); }
    if (w.tag) g.add(label(w.tag, w.footprintITM, H(w.topRel) + D.labelLift_m));
    stats.walls_m3 += w.area_m2 * (w.topRel - w.bottomRel);
    registry.add(g, { floor, system: 'structure', stage: 'walls', layer: L('Walls'), ...(floor === 'roof' && w.bottomRel < (data.tags.floors.find(f => f.id === 'roof')?.level ?? 99) - 0.5 ? { step: 'firstWalls' } : {}) }, {
      id: w.id, name: `קיר ${w.tag || w.id} (${w.id}) – ${({ ground: 'קומת קרקע', first: "קומה א'", roof: 'מעל הגג' })[floor] || floor}`, status: w.status,
      rows: [['תחתית / ראש', `${coords.fmtH(H(w.bottomRel))} / ${coords.fmtH(H(w.topRel))}`], ['יושב על', w.standsOn || '— (חסר במקורות)'], ['עובי (מהשרטוט)', `${Math.round(w.thickness_m * 100)} ס"מ`],
        ...(w.openings?.length ? [['פתחים', `${w.openings.join(', ')} (אדן / משקוף בטון)`]] : []),
        ['נפח בטון', `${(w.area_m2 * (w.topRel - w.bottomRel)).toFixed(2)} מ"ק`]],
      note: w.note || 'תחתית = ראש האלמנט שמתחתיו (רצפה / קורה); ראש = תחתית תקרת K-31.', source: w.source,
    });
    if (w.note) wNotes.add(w.note);
    scene.add(g);
  }
  for (const c of F.columns) {
    const m = prism(c.footprintITM, [], H(c.bottomRel), H(c.topRel), conc);
    const g = new THREE.Group(); g.add(m); if (flagged(c.status)) g.add(edges(m, D.provisionalEdgeColor));
    g.add(label(`${c.id} ${c.size_cm[0]}/${c.size_cm[1]}`, c.footprintITM, H(c.topRel) + D.labelLift_m));
    stats.columns_m3 += new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3()).y * c.size_cm[0] * c.size_cm[1] / 1e4;
    registry.add(g, { floor, system: 'structure', stage: 'walls', layer: L('Columns') }, {
      id: c.id, name: `עמוד ${c.id} ${c.size_cm[0]}/${c.size_cm[1]}${floor === 'first' ? " – קומה א'" : ''}`, status: c.status,
      rows: [['חתך', `${c.size_cm[0]}/${c.size_cm[1]} ס"מ (תווית: ${c.tagSize_cm.join('/') || '—'})`], ['תחתית / ראש', `${coords.fmtH(H(c.bottomRel))} / ${coords.fmtH(H(c.topRel))}`], ['יושב על', c.standsOn || '— (חסר במקורות)']],
      note: c.note || '', source: c.source,
    });
    scene.add(g);
  }
  // ceiling = slab + beams of the sheet above
  const C = F.ceiling;
  if (C) {
    for (const s of C.slab) {
      const m = prism(s.footprintITM, s.holesITM, H(s.bottomRel), H(s.topRel), conc);
      const g = new THREE.Group(); g.add(m); if (flagged(s.status)) g.add(edges(m, D.provisionalEdgeColor));
      if (s.area_m2 > 2) g.add(label(`${F.ceilingLabel || 'תקרה'} O.K=${s.topRel.toFixed(2)} D=${Math.round(s.thickness_m * 100)}`, s.footprintITM, H(s.topRel) + D.labelLift_m));
      stats.ceiling_m3 += s.area_m2 * s.thickness_m;
      registry.add(g, { floor, system: 'structure', stage: 'ceiling', layer: L('Ceiling') }, {
        id: s.id, name: `${F.ceilingLabel || 'תקרת קומת הקרקע'} ${s.id}`, status: s.status,
        rows: [['מפלס עליון (O.K)', coords.fmtH(H(s.topRel))], ['עובי', `${Math.round(s.thickness_m * 100)} ס"מ`], ['שטח', `${s.area_m2.toFixed(2)} מ"ר`]],
        note: (C.mamad?.length ? `כולל תקרת הממ"ד (${C.mamad.map(o => o.area_m2.toFixed(1)).join(', ')} מ"ר) – עובי ומפלס לפי תוכנית הג"א (חסרה). ` : '') + 'האזור המזרחי בלי תקרה ב-+3.70 – חלל כפול (סימון אלכסונים ב-K-31).', source: s.source,
      });
      scene.add(g);
    }
    for (const b of C.beams) {
      if (!b.axisITM) { stats.beamsMissing.push(b.id); continue; }
      const [[E1, N1], [E2, N2]] = b.axisITM;
      const len = Math.hypot(E2 - E1, N2 - N1), ux = (E2 - E1) / len, uy = (N2 - N1) / len, hw = b.width_m / 2;
      const ring = [[E1 - uy * hw, N1 + ux * hw], [E2 - uy * hw, N2 + ux * hw], [E2 + uy * hw, N2 - ux * hw], [E1 + uy * hw, N1 - ux * hw]];
      const m = prism(ring, [], H(b.bottomRel), H(b.topRel), conc);
      const g = new THREE.Group(); g.add(m);
      g.add(label(`${b.pergola ? 'פרגולה · ' : ''}${b.id} ${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)}`, ring, H(b.topRel) + D.labelLift_m));
      // volume below / above the slab only (the part inside the slab is counted with the slab)
      const sl = C.slab[0]; const ov = sl && !b.pergola ? Math.max(0, Math.min(b.topRel, sl.topRel) - Math.max(b.bottomRel, sl.bottomRel)) : 0;
      stats.beams_m3 += len * b.width_m * (b.depth_m - ov);
      registry.add(g, { floor, system: 'structure', stage: 'ceiling', layer: L('CeilingBeams') }, {
        ceilTopRel: C.slab.length ? Math.max(...C.slab.map(x => x.topRel)) : b.topRel,
        id: b.id, name: `${b.pergola ? 'קורת פרגולה' : 'קורה'} ${b.id} · ${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)} – ${F.ceilingLabel || 'תקרת הקרקע'}`, status: b.status,
        rows: [['חתך (רוחב/גובה)', `${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)} ס"מ`], ['מפלס עליון (O.K)', coords.fmtH(H(b.topRel))],
          ['מפלס תחתון', coords.fmtH(H(b.bottomRel))], ['אורך', `${len.toFixed(2)} מ'`]],
        note: [b.pergola ? 'פרגולה: אין תקרה משני צידי הקורה – מסגרת פתוחה.' : '', C.slab.length && b.topRel > C.slab[0].topRel + 0.01 ? 'קורה הפוכה – בולטת מעל פני התקרה.' : '', b.note || ''].filter(Boolean).join(' '), source: b.source,
      });
      scene.add(g);
    }
  }
  return stats;
}

import * as THREE from 'three';

// Windows and doors (data/architecture/openings.json, tools/extract_openings.py): the architect's Revit families placed on
// their walls. Position, width, sill / head from the data; the frame / leaf profiles are display constants (display.openings)
// until the window schedule / design document gives them. Built in the "finishes" step.
export function buildOpenings(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const OP = data.openings?.openings; if (!OP) return null;
  const D = display.openings; const DF = display.framing;
  const frameM = materials.get('windowFrame'), glassM = materials.get('glass'), leafM = materials.get('doorLeaf');
  const FLOOR = { unit: 'יחידת דיור', ground: 'קומת קרקע', first: "קומה א'" };
  const KIND = { window: 'חלון', vitrine: 'ויטרינה', sliding: 'חלון הזזה', door: 'דלת' };
  const leaves = (name) => (/תלת/.test(name) ? 3 : /דו/.test(name) ? 2 : 1);
  const boxAt = (g, mat, w, h, d, x, y, z) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); m.castShadow = m.receiveShadow = true; g.add(m); return m;
  };
  let n = 0;
  for (const o of OP) {
    const W = o.width_m, Hh = o.headRel - o.sillRel; if (!(W > 0 && Hh > 0)) continue;
    const depth = o.hostThickness_m || D.defaultWallDepth_m;
    const g = new THREE.Group();   // local: x along the wall, y up from the sill, z across the wall
    const f = D.frame_m, fd = Math.min(D.frameDepth_m, depth);
    if (o.kind === 'door') {
      boxAt(g, frameM, f, Hh, fd, -W / 2 + f / 2, Hh / 2, 0); boxAt(g, frameM, f, Hh, fd, W / 2 - f / 2, Hh / 2, 0); boxAt(g, frameM, W, f, fd, 0, Hh - f / 2, 0);
      boxAt(g, leafM, W - 2 * f, Hh - f, D.doorLeaf_m, 0, (Hh - f) / 2, 0);
    } else {
      boxAt(g, frameM, f, Hh, fd, -W / 2 + f / 2, Hh / 2, 0); boxAt(g, frameM, f, Hh, fd, W / 2 - f / 2, Hh / 2, 0);
      boxAt(g, frameM, W, f, fd, 0, f / 2, 0); boxAt(g, frameM, W, f, fd, 0, Hh - f / 2, 0);
      const k = leaves(o.name);
      for (let i = 1; i < k; i++) boxAt(g, frameM, D.mullion_m, Hh - 2 * f, fd, -W / 2 + (W * i) / k, Hh / 2, 0);
      boxAt(g, glassM, W - 2 * f, Hh - 2 * f, D.glass_m, 0, Hh / 2, 0);
    }
    // place: origin at the opening centre on the sill, x = wall axis, z = its normal (right-handed with y up)
    const [x0, z0] = coords.xz(...o.centerITM);
    const [x1, z1] = coords.xz(o.centerITM[0] + o.axisITM[0], o.centerITM[1] + o.axisITM[1]);
    const ax = new THREE.Vector3(x1 - x0, 0, z1 - z0).normalize(), up = new THREE.Vector3(0, 1, 0);
    const nz = new THREE.Vector3().crossVectors(ax, up);
    const M = new THREE.Matrix4().makeBasis(ax, up, nz); M.setPosition(x0, o.sillRel, z0);
    g.applyMatrix4(M);
    if (o.status !== 'source') g.add(new THREE.BoxHelper(g, DF.provisionalEdgeColor));
    const abs = (rel) => coords.fmtH(coords.H0 + rel);
    registry.add(g, { floor: o.floor, system: 'finishes', stage: 'finishes', layer: o.kind === 'door' ? 'doors' : 'windows' }, {
      name: `${KIND[o.kind] || o.kind} ${o.id} – ${o.name}`, status: o.status,
      rows: [['קומה', FLOOR[o.floor] || o.floor], ['רוחב × גובה', `${Math.round(W * 100)} × ${Math.round(Hh * 100)} ס"מ`],
        ['U.K / O.K (מהרצפה הגמורה)', `${o.UK_cm} / ${o.OK_cm} ס"מ`], ['אדן / משקוף (מוחלט)', `${abs(o.sillRel)} / ${abs(o.headRel)}`],
        ['קיר', o.host ? `${o.host} (בטון, ${Math.round(o.hostThickness_m * 100)} ס"מ) – אדן ומשקוף בטון` : 'קיר בלוקים / אחר (שלב 4)'], ['מזהה Revit', o.revitId]],
      note: [o.note, 'פרופיל המסגרת / הכנף – קבוע תצוגה עד שיגיע מפרט החלונות.'].filter(Boolean).join(' '), source: o.source,
    });
    scene.add(g); n++;
  }
  return { count: n };
}

// Steel frames of the mamad window / door (Avihai's edit-mode note ק15): set in the formwork and cast with the walls, so they
// are part of the skeleton (step of the walls). The opening = the gap between the walls of the structural sheet
// (openings.json castFrame, tools/extract_openings.py); the frame profile is a display constant (display.openings.frame_m)
// until the approved shelter plan gives it. The leaves stay with the windows / doors (finishes – on hold).
export function buildMamadFrames(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const OP = (data.openings?.openings || []).filter(o => o.castFrame); if (!OP.length) return null;
  const f = display.openings.frame_m, steel = materials.get('steelFrame'), DF = display.framing;
  const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
  const prism = (ring, zBot, zTop) => {
    const g = new THREE.ExtrudeGeometry(new THREE.Shape(ring.map(toV)), { depth: zTop - zBot, bevelEnabled: false });
    g.rotateX(-Math.PI / 2); g.translate(0, zBot, 0);
    const m = new THREE.Mesh(g, steel); m.castShadow = m.receiveShadow = true; return m;
  };
  const lerp = (p, q, k) => [p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k];
  for (const o of OP) {
    const C = o.castFrame, [P0, P1, P2, P3] = C.ringITM, W = Math.hypot(P1[0] - P0[0], P1[1] - P0[1]), k = f / W;
    const g = new THREE.Group();
    g.add(prism([P0, lerp(P0, P1, k), lerp(P3, P2, k), P3], C.bottomRel, C.topRel));                 // jambs
    g.add(prism([lerp(P0, P1, 1 - k), P1, P2, lerp(P3, P2, 1 - k)], C.bottomRel, C.topRel));
    g.add(prism(C.ringITM, C.topRel - f, C.topRel));                                                  // head
    if (o.kind !== 'door') g.add(prism(C.ringITM, C.bottomRel, C.bottomRel + f));                    // sill
    if (C.pocketITM) g.add(prism(C.pocketITM, C.bottomRel, C.topRel));                               // shutter pocket (steel box)
    g.add(new THREE.BoxHelper(g, DF.provisionalEdgeColor));
    const abs = (rel) => coords.fmtH(coords.H0 + rel);
    registry.add(g, { floor: o.floor, system: 'structure', stage: 'walls', layer: 'mamadFrames' }, {
      id: o.id, name: `משקוף ${o.kind === 'door' ? 'דלת' : 'חלון'} ממ"ד ${o.id} (נוצק בקיר ${o.host})`, status: 'approx',
      rows: [['פתח בבטון (K-21)', `${Math.round(C.width_m * 100)} ס"מ`], ...(C.pocketWidth_m ? [['מזה כיס תריס ההדף', `${Math.round(C.pocketWidth_m * 100)} ס"מ`]] : []),
        ['תחתית / ראש', `${abs(C.bottomRel)} / ${abs(C.topRel)}`], ['משפחת Revit', `${o.name} – ${Math.round(o.width_m * 100)} ס"מ`], ['קיר', `${o.host} (${Math.round(o.hostThickness_m * 100)} ס"מ)`]],
      note: C.note, source: o.source,
    });
    scene.add(g);
  }
  return { count: OP.length };
}

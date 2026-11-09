import * as THREE from 'three';

// Mamad (shelter) per the architect's plan – data/architecture/mamad.json (tools/extract_mamad.py):
//   window  : two steel blast leaves that slide into their niches inside the walls + the inner glass wing
//   door    : sliding blast leaf on the wall face, outside the room
//   sleeves : pipes cast in the walls for the systems (ventilation 4", filter 8"), with their flanges
// A click on the window / the door (inspect tool) opens and closes it. Every size and position comes from the data, in the
// local frame of the Revit family (u along the wall, v across it); speed / colours are display constants (display.openings).
export function buildMamad(ctx) {
  const { data, coords, registry, scene, materials, display, viewer } = ctx;
  const M = data.mamad; if (!M) return null;
  const D = display.openings, DF = display.framing;
  const steel = materials.get('steelFrame'), leafM = materials.get('blastLeaf'), glassM = materials.get('glass'), frameM = materials.get('windowFrame');
  const abs = (rel) => coords.fmtH(coords.H0 + rel);
  const cmS = (m) => `${+(m * 100).toFixed(1)} ס"מ`;

  // local frame of a family -> scene
  const frame = (e) => {
    const [ox, oz] = coords.xz(...e.originITM);
    const [ux, uz] = coords.xz(e.originITM[0] + e.uITM[0], e.originITM[1] + e.uITM[1]), [vx, vz] = coords.xz(e.originITM[0] + e.vITM[0], e.originITM[1] + e.vITM[1]);
    const U = new THREE.Vector3(ux - ox, 0, uz - oz), V = new THREE.Vector3(vx - ox, 0, vz - oz);
    return { at: (u, v, y) => new THREE.Vector3(ox, y, oz).addScaledVector(U, u).addScaledVector(V, v), rotY: Math.atan2(-U.z, U.x), U, V };
  };
  // box given by its u / v / level ranges; keep = not merged by the compactor (it moves)
  const box = (f, u, v, z, mat, keep) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(u[1] - u[0], z[1] - z[0], v[1] - v[0]), mat);
    m.position.copy(f.at((u[0] + u[1]) / 2, (v[0] + v[1]) / 2, (z[0] + z[1]) / 2)); m.rotation.y = f.rotY; m.castShadow = m.receiveShadow = true;
    if (keep) m.userData.keep = true;
    return m;
  };

  // ---- sliding: every moving part goes from its closed to its open position along u ----
  const movers = [];
  const slider = (parts) => {     // parts: [{ object, shift: Vector3 (closed -> open) }]
    const s = { t: 0, target: 0, parts: parts.map(p => ({ ...p, home: p.object.position.clone() })) };
    s.toggle = () => { s.target = s.target ? 0 : 1; viewer.invalidate(); return s.target; };
    movers.push(s); return s;
  };
  viewer.updaters.push((dt) => {
    let active = false;
    for (const s of movers) {
      if (s.t === s.target) continue;
      const d = dt / D.slideSeconds; s.t = s.target > s.t ? Math.min(s.target, s.t + d) : Math.max(s.target, s.t - d);
      const k = s.t * s.t * (3 - 2 * s.t);   // ease in / out
      for (const p of s.parts) p.object.position.copy(p.home).addScaledVector(p.shift, k);
      active = true;
    }
    return active;
  });
  const hook = (id, s, items) => {     // the cast frame (js/geometry/openings.js) toggles it too
    for (const it of registry.items) if (it.meta.id === id && it.tags.layer === 'mamadFrames') items.push(it);
    for (const it of items) { it.meta.onClick = s.toggle; it.meta.toggleState = () => s.target; it.meta.toggleSettled = () => s.t === s.target; }
  };
  const HINT = 'לחיצה (בכלי "מידע") – פתיחה / סגירה.';
  let count = 0;

  // ---------------- window ----------------
  if (M.window) {
    const W = M.window, f = frame(W), g = new THREE.Group(), parts = [];
    for (const l of W.leaves) {
      const m = box(f, l.closedU, l.v, l.zRel, leafM, true); g.add(m);
      parts.push({ object: m, shift: f.U.clone().multiplyScalar(l.openU[0] - l.closedU[0]) });
    }
    const G = W.glass, st = G.stile_m;   // inner glass wing: stiles, rails, pane (closed)
    g.add(box(f, [G.u[0], G.u[0] + st], G.v, G.zRel, frameM), box(f, [G.u[1] - st, G.u[1]], G.v, G.zRel, frameM));
    g.add(box(f, [G.u[0] + st, G.u[1] - st], G.v, [G.zRel[0], G.zRel[0] + st], frameM), box(f, [G.u[0] + st, G.u[1] - st], G.v, [G.zRel[1] - st, G.zRel[1]], frameM));
    const pane = box(f, [G.u[0] + st, G.u[1] - st], G.paneV, [G.zRel[0] + st, G.zRel[1] - st], glassM); pane.castShadow = false; g.add(pane);
    // the niches: inside the concrete – outlined (seen in a section / with a transparent floor)
    const nm = new THREE.LineBasicMaterial({ color: D.nicheColor, transparent: true, opacity: 0.85 });
    for (const n of W.niches) {
      const b = box(f, n.u, n.v, n.zRel, steel), e = new THREE.LineSegments(new THREE.EdgesGeometry(b.geometry), nm);
      e.position.copy(b.position); e.rotation.copy(b.rotation); e.renderOrder = 6; e.userData.annotation = true; g.add(e);
    }
    const s = slider(parts), L = W.leaves[0], N = W.niches[0];
    const it = registry.add(g, { floor: 'ground', system: 'finishes', stage: 'finishes', layer: 'mamadLeaves' }, {
      id: 'G09-leaves', name: `חלון ממ"ד ${W.id} – שתי כנפי פלדה נגררות לגומחות + כנף זכוכית`, status: 'approx',
      rows: [['משקוף (רוחב × גובה)', `${cmS(W.frame.u[1] - W.frame.u[0])} × ${cmS(W.headRel - W.sillRel)}`], ['פתח נקי', cmS(W.frame.clearU[1] - W.frame.clearU[0])],
        ['אדן / משקוף עליון', `${abs(W.sillRel)} / ${abs(W.headRel)}`], ['כנף פלדה (×2)', `${cmS(L.width_m)} × ${cmS(L.zRel[1] - L.zRel[0])}, עובי ${cmS(L.thickness_m)}`],
        ['מהלך כל כנף', cmS(L.travel_m)], ['גומחה בקיר (×2)', `${cmS(N.length_m)} × ${cmS(N.width_m)} – בקירות ${W.niches.map(n => n.inWall || '?').join(', ')}`],
        ['משפחת Revit', W.name]],
      note: `${HINT} ${L.note} ${G.note}`, source: W.source,
    });
    hook(W.id, s, [it]); scene.add(g); count++;
  }

  // ---------------- sliding door ----------------
  if (M.door) {
    const Dr = M.door, f = frame(Dr), L = Dr.leaf, g = new THREE.Group();
    const leaf = new THREE.Group(); leaf.userData.keep = true;
    const m = box(f, L.closedU, L.v, L.zRel, leafM, true); leaf.add(m);
    if (L.handle) {     // drawn on the leading edge of the leaf; its level is a display constant
      const hu = L.handle.u.map(u => u + L.closedU[1] - L.openU[1]);
      leaf.add(box(f, hu, L.handle.v, [L.zRel[0] + D.handleRel - D.handleHeight_m / 2, L.zRel[0] + D.handleRel + D.handleHeight_m / 2], steel, true));
    }
    g.add(leaf);
    if (L.zStatus === 'provisional') { const h = new THREE.BoxHelper(m, DF.provisionalEdgeColor); h.userData.keep = true; leaf.add(h); }
    const s = slider([{ object: leaf, shift: f.U.clone().multiplyScalar(L.openU[0] - L.closedU[0]) }]);
    const it = registry.add(g, { floor: 'ground', system: 'finishes', stage: 'finishes', layer: 'mamadLeaves' }, {
      id: 'G21-leaf', name: `דלת ממ"ד ${Dr.id} – כנף נגררת (הזזה)`, status: L.zStatus === 'provisional' ? 'provisional' : 'approx',
      rows: [['פתח נקי', cmS(Dr.clearU[1] - Dr.clearU[0])], ['כנף (רוחב × גובה)', `${cmS(L.width_m)} × ${cmS(L.zRel[1] - L.zRel[0])}${L.zStatus === 'provisional' ? ' (גובה זמני)' : ''}`],
        ['עובי הכנף', cmS(L.thickness_m)], ['מהלך', cmS(L.travel_m)], ['חונה על קיר', L.parkWall || '—'], ['משפחת Revit', Dr.name]],
      note: `${HINT} ${L.note}`, source: Dr.source,
    });
    hook(Dr.id, s, [it]); scene.add(g); count++;
  }

  // ---------------- sleeves cast in the walls ----------------
  const bore = new THREE.MeshBasicMaterial({ color: D.sleeveBoreColor });
  const Y = new THREE.Vector3(0, 1, 0);
  for (const sv of M.sleeves || []) {
    const z = sv.zRel ?? D.sleeveDefaultRel, [x0, z0] = coords.xz(...sv.centerITM), [x1, z1] = coords.xz(sv.centerITM[0] + sv.axisITM[0], sv.centerITM[1] + sv.axisITM[1]);
    const A = new THREE.Vector3(x1 - x0, 0, z1 - z0).normalize(), C = new THREE.Vector3(x0, z, z0), q = new THREE.Quaternion().setFromUnitVectors(Y, A);
    const cyl = (dia, v, mat, seg = 28) => {
      const m = new THREE.Mesh(new THREE.CylinderGeometry(dia / 2, dia / 2, v[1] - v[0], seg), mat);
      m.quaternion.copy(q); m.position.copy(C).addScaledVector(A, (v[0] + v[1]) / 2); m.castShadow = m.receiveShadow = true; return m;
    };
    const g = new THREE.Group(), pipe = cyl(sv.dia_m, sv.pipeV, steel); g.add(pipe);
    for (const fl of sv.flanges) g.add(cyl(fl.dia_m, fl.v, steel));
    const ends = [Math.min(sv.pipeV[0], ...sv.flanges.map(fl => fl.v[0])), Math.max(sv.pipeV[1], ...sv.flanges.map(fl => fl.v[1]))];
    for (const [e, sgn] of [[ends[0], -1], [ends[1], 1]]) {     // the open bore at both ends
      const c = new THREE.Mesh(new THREE.CircleGeometry(sv.dia_m / 2 * D.sleeveBoreRatio, 24), bore);
      c.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), A.clone().multiplyScalar(sgn)); c.position.copy(C).addScaledVector(A, e + sgn * 0.002); g.add(c);
    }
    if (sv.status !== 'source') g.add(new THREE.BoxHelper(pipe, DF.provisionalEdgeColor));
    const hostW = data.floorGround?.walls?.find(w => w.id === sv.host), inch = Math.round(sv.dia_m / 0.0254);
    registry.add(g, { floor: sv.floor, system: 'structure', stage: 'walls', layer: 'mamadSleeves', ...(hostW?.mamad ? { step: 'groundCeiling' } : {}) }, {
      id: sv.id, name: `שרוול ${inch}" ביציקה ${inch >= 8 ? '(מערכת סינון)' : '(אוורור)'} – קיר ${sv.host}`, status: sv.status,
      rows: [['קוטר הצינור', `${Math.round(sv.dia_m * 1000)} מ"מ (${inch}")`], ['גובה מרכז', sv.zRel != null ? abs(sv.zRel) : `לא ידוע – מוצג זמני ב-${abs(z)}`],
        ['אורך כולל אוגנים', cmS(ends[1] - ends[0])], ['אוגנים', sv.flanges.map(fl => `ø${Math.round(fl.dia_m * 100)} × ${cmS(fl.v[1] - fl.v[0])}`).join(' · ')],
        ['קיר', `${sv.host} (${Math.round(sv.hostThickness_m * 100)} ס"מ)`], ['משפחת Revit', sv.name]],
      note: `${sv.note}. צינור שמוצב בתבנית ונוצק בקיר – פרט היצרן המאושר של פיקוד העורף חסר.`, source: sv.source,
    });
    scene.add(g); count++;
  }
  return { count };
}

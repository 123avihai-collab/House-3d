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
      if (st.sidePlaster?.length) buildSidePlaster(st);
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
      [st.soffit === 'stepped' ? 'עובי הלוח' : 'עובי שיפוע (ניצב)', `${Math.round(st.waist_m * 100)} ס"מ`]);
    if (st.firstRiser_m) rows.push(['רום ראשון / אחרון (מהריצוף)', `${(st.firstRiser_m * 100).toFixed(1)} / ${(st.lastRiser_m * 100).toFixed(1)} ס"מ`],
      ['חיפוי', st.cladding || 'אין – הבטון הוא המדרך הגמור'], ['תחתית', st.soffit === 'stepped' ? 'מדורגת (גרם מקופל)' : 'משופעת']);
    if (st.sidePlaster?.length) rows.push(['טיח צדדים', st.sidePlaster.map(p => `${p.flight} ${p.area_m2.toFixed(2)} מ"ר`).join(' · ')]);
    if (st.landings?.length) rows.push(['פודסטים', st.landings.map((L) => `${L.label} ${coords.fmtH(coords.H0 + L.topRel)} (D=${Math.round(L.thickness_m * 100)})`).join(' · ')]);
    if (st.treads) rows.push(['מדרכים', `${st.treads.length} (כולל 27–28 פנייה), עובי ${Math.round(st.treadThickness_m * 100)} ס"מ`]);
    if (m3) rows.push(['נפח בטון', `${m3.toFixed(2)} מ"ק`]);
    const CP = st.concreteProposal;
    registry.add(g, tags, { id: st.id, name: st.name, status: st.status, rows, note: st.note, source: st.source,
      ...(CP ? { variant: { change: CP.change, show: 'original' } } : {}) });
    scene.add(g);
    if (CP) buildStairProposal(st, CP);
  }

  // interior plaster on the exposed side of a flight (data: st.sidePlaster – the side not cast against a wall): the side profile
  // (stepped soffit) as a surface just outside the flight's side, in the plaster layer of its type
  function buildSidePlaster(st) {
    const T = data.plasterTypes?.types || [];
    for (const sp of st.sidePlaster) {
      const f = st.flights.find(x => x.id === sp.flight); const ty = T.find(t => t.id === sp.type) || {};
      const g = new THREE.ShapeGeometry(new THREE.Shape(f.profile.map(([a, z]) => new THREE.Vector2(a, z))));
      const [x0, z0] = coords.xz(...f.originITM);
      const dir = (v) => { const [a, b] = coords.xz(f.originITM[0] + v[0], f.originITM[1] + v[1]); return new THREE.Vector3(a - x0, 0, b - z0).normalize(); };
      const run = dir(f.runDirITM), right = dir(f.rightDirITM);
      const off = sp.side === 'right' ? f.width_m + DS.plasterOffset_m : -DS.plasterOffset_m;
      const M = new THREE.Matrix4().makeBasis(run, new THREE.Vector3(0, 1, 0), right); M.setPosition(x0 + right.x * off, 0, z0 + right.z * off);
      g.applyMatrix4(M);
      const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: ty.color || DS.plasterColor, roughness: DS.plasterRoughness, side: THREE.DoubleSide,
        polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
      m.receiveShadow = true;
      registry.add(m, { floor: st.floor, system: 'finishes', stage: 'finishes', layer: `plaster_${sp.type}`, step: 'plaster' }, {
        id: `${f.id}-plaster-${sp.side}`, name: `${ty.label || 'טיח'} – צד השלח ${f.numbers} (${st.name})`, status: st.status,
        rows: [['שטח', `${sp.area_m2.toFixed(2)} מ"ר`], ['צד', 'הצד החשוף (לא צמוד לקיר)']], source: st.source,
      });
      scene.add(m);
    }
  }

  // OC-3 (Avihai's note 14): the light / floating stair of the plans vs a concrete stair on the same path.
  //  original: anchor points in the concrete wall the treads cantilever from (the wall's own step) – a tread with no
  //            concrete wall in K-21 gets a red "?" (architecture vs structure mismatch)
  //  changed : concrete stair (each tread down to rise + waist under it, concrete levels = finished − finish) in its own
  //            step, starter bars waiting in the ground slab and the ground ceiling (display.starters, illustration)
  function buildStairProposal(st, CP) {
    const PM = new THREE.LineBasicMaterial({ color: D.ownerChangeColor });
    const anchorM = new THREE.MeshStandardMaterial({ color: DS.anchorColor, metalness: 0.6, roughness: 0.4 });
    const missM = new THREE.MeshBasicMaterial({ color: D.ownerChangeRemovedColor });
    // original variant – anchors
    const ag = new THREE.Group(); const missing = [];
    for (const a of st.anchors || []) {
      const t = st.treads.find(x => x.n === a.n); const c = centroid(t.ringITM);
      if (!a.wall) { missing.push(a.n); const q = new THREE.Mesh(new THREE.SphereGeometry(DS.anchorMarker_m, 12, 8), missM); q.position.copy(coords.toLocal(c[0], c[1], coords.H0 + t.topRel)); ag.add(q); continue; }
      const m = new THREE.Mesh(new THREE.BoxGeometry(DS.anchorMarker_m * 2, DS.anchorMarker_m * 2, DS.anchorMarker_m * 2), anchorM);
      m.position.copy(coords.toLocal(a.atITM[0], a.atITM[1], coords.H0 + a.zRel)); ag.add(m);
    }
    const walls = [...new Set((st.anchors || []).filter(a => a.wall).map(a => a.wall))];
    if (missing.length) { const t = st.treads.find(x => x.n === missing[0]), c = centroid(t.ringITM); ag.add(label(`? מדרכים ${missing[0]}–${missing[missing.length - 1]}: אין קיר בטון לעיגון ב-K-21`, c[0], c[1], t.topRel + DS.labelLift_m, 'lbl removed-q')); }
    registry.add(ag, { floor: 'ground', system: 'structure', stage: 'walls', layer: 'stairsLight', step: 'groundWalls' }, {
      id: `${st.id}-anchors`, name: `נקודות עיגון המדרגות המרחפות – קירות ${walls.join(', ')}`, status: 'provisional', variant: { change: CP.change, show: 'original' },
      rows: [['מעוגנים בקיר בטון', `${(st.anchors || []).filter(a => a.wall).map(a => `${a.n}→${a.wall}`).join(' · ')}`], ['בלי קיר בטון ב-K-21', missing.length ? missing.join(', ') : '—']],
      note: 'לפי התוכנית: מדרכים מרחפים מעוגנים ב"קיר בטון לעיגון מדרגות מרחפות" (גיליון 13 – לא בתיקיית המקורות). הקיר נבחר לפי מגע בין המדרך לקיר בטון של K-21.', source: st.source,
    });
    scene.add(ag);
    // changed variant – the concrete stair
    // no cladding: concrete tread = finished tread. Folded plate: flights = side profile with a stepped soffit extruded across
    // the width; the turn (26–28) = each tread a plate of the same thickness under its own top
    const cg = new THREE.Group(); let m3 = 0;
    const addC = (m) => { cg.add(m); cg.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 30), PM)); m3 += vol(m.geometry); };
    for (const f of CP.flights) addC(flightMesh(f, conc));
    for (const n of CP.turn.treads) { const t = st.treads.find(x => x.n === n); const zt = t.topRel - CP.finish_m; addC(prism(t.ringITM, null, zt - CP.turn.thickness_m, zt, conc)); }
    const c0 = centroid(st.treads[Math.floor(st.treads.length / 2)].ringITM);
    cg.add(label(`הצעה – ממתין לתוכנית (${CP.change}): גרם בטון ${st.risers} × ${Math.round(st.rise_m * 1000) / 10}`, c0[0], c0[1], CP.topRel + DS.labelLift_m, 'lbl change'));
    registry.add(cg, { floor: 'ground', system: 'structure', stage: 'slab', layer: 'stairsProposal', step: CP.step }, {
      id: `${st.id}-concrete`, name: `גרם מדרגות בטון – הצעה (${CP.change})`, status: 'provisional', variant: { change: CP.change, show: 'changed' },
      rows: [['רומים', `${st.risers} × ${(st.rise_m * 100).toFixed(1)} ס"מ – כמו בתוכנית`],
        ['רום ראשון / אחרון (מהריצוף)', `${(CP.firstRiser_m * 100).toFixed(1)} / ${(CP.lastRiser_m * 100).toFixed(1)} ס"מ`],
        ['חיפוי', CP.cladding || 'אין – הבטון הוא המדרך הגמור'],
        ['שלחים', CP.flights.map((f) => `${f.numbers}: רוחב ${f.width_m.toFixed(2)} · שלח ${f.going_m.toFixed(3)} · שיפוע ${f.pitch_deg}°`).join(' | ')],
        ['2R+G', `${((2 * st.rise_m + CP.flights[0].going_m) * 100).toFixed(1)} ס"מ`],
        ['תחתית / הגעה (בטון)', `${coords.fmtH(coords.H0 + CP.bottomRel)} רצפת הקרקע / ${coords.fmtH(coords.H0 + CP.topRel)} שפת התקרה`],
        ['תחתית', CP.soffit === 'stepped' ? 'מדורגת במקביל למדרכים (גרם מקופל), כולל הפנייה 26–28' : 'משופעת'],
        ['עובי הלוח (זמני)', `${Math.round(CP.thickness_m * 100)} ס"מ`], ['נפח בטון (הערכה)', `${m3.toFixed(2)} מ"ק`]],
      note: CP.note, source: CP.source,
    });
    scene.add(cg);
    // starter bars waiting for the stair: first riser in the ground slab, arrival edge in the ground ceiling
    const SD = display.starters, proj = data.rebar?.starters?.wallProjection_m;
    const bars = (pts, z) => {
      const geo = new THREE.CylinderGeometry(SD.schematicDia_mm / 2000 * SD.barScale, SD.schematicDia_mm / 2000 * SD.barScale, proj, 6); geo.translate(0, proj / 2, 0);
      const im = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ color: SD.schematicBarColor }), pts.length), M = new THREE.Matrix4();
      pts.forEach(([E, N], i) => { const v = coords.toLocal(E, N, coords.H0 + z); M.makeTranslation(v.x, v.y, v.z); im.setMatrixAt(i, M); }); return im;
    };
    const along = ([a, b]) => { const L = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(2, Math.round(L / SD.schematicSpacing_m)); return [...Array(n)].map((_, i) => [a[0] + (b[0] - a[0]) * (i + 0.5) / n, a[1] + (b[1] - a[1]) * (i + 0.5) / n]); };
    const first = st.treads.find(x => x.n === Math.min(...st.treads.map(t => t.n))).ringITM;
    for (const [line, z, step, where] of [[[first[0], first[1]], CP.bottomRel, 'groundSlab', 'ברצפת הקרקע'], [st.arrivalRiserITM, CP.topRel, 'groundCeiling', 'בתקרת הקרקע']]) {
      const sg = new THREE.Group(); sg.add(bars(along(line), z));
      registry.add(sg, { floor: 'ground', system: 'structure', stage: 'slab', layer: 'starters', step, stepTo: 'groundCeiling' }, {
        id: `${st.id}-starters-${step}`, name: `קוצי המתנה לגרם הבטון ${where} (הצעה ${CP.change})`, status: 'provisional', variant: { change: CP.change, show: 'changed' },
        rows: [['קוצים', `סכמטי Ø${SD.schematicDia_mm}@${Math.round(SD.schematicSpacing_m * 100)} – המחשה`]], note: 'אין תוכנית לגרם – קוצים להמחשה בלבד.', source: CP.source,
      });
      scene.add(sg);
    }
  }

  // utilities pillar: garbage room + electric-cabinet niche (cast with the perimeter walls), and the cabinet
  const P = S.pillar;
  if (P) {
    const g = new THREE.Group();
    P.wallsITM.forEach((w, i) => { const m = prism(w, P.wallHolesITM?.[i], P.bottomRel, P.topRel, conc); g.add(m, edges(m, D.provisionalEdgeColor)); });
    const c0 = centroid(P.wallsITM[0]);
    g.add(label(`${P.name} · ראש ${coords.fmtH(coords.H0 + P.topRel)}`, c0[0], c0[1], P.topRel + DS.labelLift_m));
    registry.add(g, { floor: 'site', system: 'site', stage: 'walls', layer: 'pillar', step: P.step }, {
      id: P.id, name: P.name, status: P.status,
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

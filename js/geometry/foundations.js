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

  // basement walls (+ owner-change variants: a wall with an opening is replaced by its pieces while the change is on)
  const OCG = data.ownerChangesGeometry?.changes || {};
  const OC = data.ownerChanges?.changes || [];
  const wallList = [];
  for (const w of F.basementWalls) {
    const ch = OC.find(c => (OCG[c.id]?.wallsChanged || []).some(x => x.replaces === w.id));
    if (!ch) { wallList.push(w); continue; }
    wallList.push({ ...w, variant: { change: ch.id, show: 'original' } });
    const wc = OCG[ch.id].wallsChanged.find(x => x.replaces === w.id);
    wc.pieces.forEach((p, i) => wallList.push({ ...w, id: `${w.id}·${ch.id}-${i + 1}`, footprintITM: p.footprintITM, holesITM: p.holesITM,
      area_m2: null, variant: { change: ch.id, show: 'changed' }, note: `${w.note} | ${ch.id}: בלי קיר ${ch.openWall.piece} (פתח מעבר)` }));
  }
  for (const w of wallList) {
    const m = prism(w.footprintITM, w.holesITM, H(w.bottomRel), H(w.topRel), conc);
    const g = new THREE.Group(); g.add(m); if (w.status === 'provisional') g.add(edges(m, D.provisionalEdgeColor));
    if (w.area_m2 != null && w.variant?.show !== 'changed') stats.walls_m3 += w.area_m2 * (w.topRel - w.bottomRel);
    registry.add(g, { floor: 'unit', system: 'structure', stage: 'walls', layer: 'basementWalls' }, {
      name: `קירות מרתף (${w.id})${w.variant?.show === 'original' ? ' – לפי התוכניות' : ''}`, status: w.status, variant: w.variant,
      rows: [['תחתית / ראש', `${coords.fmtH(H(w.bottomRel))} / ${coords.fmtH(H(w.topRel))}`]].concat(w.area_m2 != null ? [['שטח חתך אופקי', `${w.area_m2.toFixed(2)} מ"ר`],
        ['נפח בטון', `${(w.area_m2 * (w.topRel - w.bottomRel)).toFixed(2)} מ"ק`]] : []),
      note: w.note, source: w.source,
    });
    scene.add(g);
  }
  // owner-change wall marks: opening (red ghost, dashed) and new door (purple frame) – only with the change on
  for (const ch of OC) {
    const G = OCG[ch.id]; if (!G) continue;
    const w0 = F.basementWalls[0];
    const mark = (key, kind) => {
      const piece = G.wallPieces[key]; if (!piece) return;
      const g = new THREE.Group();
      for (const o of piece.outlinesITM) {
        const mat = kind === 'open' ? new THREE.MeshBasicMaterial({ color: D.ownerChangeRemovedColor, transparent: true, opacity: D.ownerChangeRemovedOpacity, depthWrite: false })
          : new THREE.MeshBasicMaterial({ color: D.ownerChangeColor, transparent: true, opacity: D.ownerChangeZoneOpacity * 2, depthWrite: false });
        const m = prism(o, [], H(w0.bottomRel), H(w0.topRel) + (kind === 'door' ? 0.01 : 0), mat); m.castShadow = false; m.renderOrder = 5; g.add(m);
        const lm = kind === 'open' ? new THREE.LineDashedMaterial({ color: D.ownerChangeRemovedColor, dashSize: 0.15, gapSize: 0.1 }) : new THREE.LineBasicMaterial({ color: D.ownerChangeColor });
        const ls = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 30), lm); ls.computeLineDistances(); g.add(ls);
      }
      const c = piece.outlinesITM.flat().reduce((a, p, _, arr) => [a[0] + p[0] / arr.length, a[1] + p[1] / arr.length], [0, 0]);
      const note = kind === 'open' ? ch.openWall.note : ch.doorWall.note;
      g.add(label(`${ch.id} · קיר ${key}: ${note}`, c[0], c[1], H(w0.topRel) + 0.3, kind === 'open' ? 'lbl removed' : 'lbl change'));
      registry.add(g, { floor: 'unit', system: 'structure', stage: 'walls', layer: 'ownerChanges' }, {
        name: `${ch.id} – קיר ${key}: ${note}`, status: 'owner-change', variant: { change: ch.id, show: 'changed' },
        note: ch.description, source: piece.source,
      });
      scene.add(g);
    };
    if (ch.openWall) mark(ch.openWall.piece, 'open');
    if (ch.doorWall) mark(ch.doorWall.piece, 'door');
  }
  // slabs
  // owner changes (data/changes/owner-changes.json): a slab may be replaced by another level/outline
  // both variants are built; the registry shows one of them by state.ownerChanges[id] (meta.variant)
  const slabs = [];
  for (const s0 of F.slabs) {
    const c = OC.find(c => c.slab?.split === s0.id && OCG[c.id]?.slabSplit);
    if (!c) { slabs.push(s0); continue; }
    const sp = OCG[c.id].slabSplit, keep = sp.lowered === 'south' ? 'north' : 'south';
    slabs.push({ ...s0, variant: { change: c.id, show: 'original' } });
    slabs.push({ ...s0, id: `${s0.id}-${keep}`, outlineITM: sp[keep].outlineITM, holesITM: [], area_m2: sp[keep].area_m2, variant: { change: c.id, show: 'changed' } });
    const low = sp[sp.lowered];
    slabs.push({ ...s0, id: `${s0.id}-${sp.lowered}→${c.id}`, outlineITM: low.outlineITM, holesITM: [], area_m2: low.area_m2, top: sp.newTop, thickness_m: sp.newThickness_m,
      status: 'owner-change', change: c, replaced: s0, variant: { change: c.id, show: 'changed' }, source: sp.newSource });
    slabs.push({ ...s0, id: `${s0.id}-${sp.lowered} (מבוטל)`, outlineITM: low.outlineITM, holesITM: [], area_m2: low.area_m2, removedBy: c, variant: { change: c.id, show: 'changed' } });
  }
  for (const s of slabs) {
    if (s.top == null) { stats.beamsMissing.push(s.id); continue; }
    const c = s.outlineITM.reduce((a, p) => [a[0] + p[0] / s.outlineITM.length, a[1] + p[1] / s.outlineITM.length], [0, 0]);
    if (s.removedBy) {
      // what the change cancels: the original slab as a red translucent ghost with a dashed outline
      const ghost = new THREE.MeshBasicMaterial({ color: D.ownerChangeRemovedColor, transparent: true, opacity: D.ownerChangeRemovedOpacity, depthWrite: false });
      const m = prism(s.outlineITM, s.holesITM || [], H(s.top - s.thickness_m), H(s.top), ghost); m.castShadow = false; m.renderOrder = 4;
      const g = new THREE.Group(); g.add(m);
      const ls = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 30), new THREE.LineDashedMaterial({ color: D.ownerChangeRemovedColor, dashSize: 0.15, gapSize: 0.1 }));
      ls.computeLineDistances(); g.add(ls);
      g.add(label(`${s.removedBy.id} · מבוטל: רצפה ${s.top.toFixed(2)} D=${Math.round(s.thickness_m * 100)}`, c[0], c[1], H(s.top) + D.labelLift_m, 'lbl removed'));
      registry.add(g, { floor: 'unit', system: 'structure', stage: 'slab', layer: 'ownerChanges' }, {
        name: `${s.removedBy.id} – מבוטל: רצפה ${s.top.toFixed(2)} D=${Math.round(s.thickness_m * 100)} (${s.id})`, status: 'owner-change', variant: s.variant, pickable: false,
        note: s.removedBy.description, source: s.source,
      });
      scene.add(g); continue;
    }
    const m = prism(s.outlineITM, s.holesITM || [], H(s.top - s.thickness_m), H(s.top), conc);
    const g = new THREE.Group(); g.add(m);
    if (s.change) {
      g.add(edges(m, D.ownerChangeColor));
      g.add(label(`${s.change.id} · שינוי אביחי: רצפה O.K=${s.top.toFixed(2)} D=${Math.round(s.thickness_m * 100)} (במקום ${s.replaced.top.toFixed(2)})`, c[0], c[1], H(s.top) + D.labelLift_m, 'lbl change'));
    } else g.add(label(`רצפה O.K=${s.top.toFixed(2)} D=${Math.round(s.thickness_m * 100)}`, c[0], c[1], H(s.top) + D.labelLift_m, 'lbl beam'));
    if (s.variant?.show !== 'original') stats.slabs_m3 += s.area_m2 * s.thickness_m;
    registry.add(g, { floor: 'unit', system: 'structure', stage: 'slab', layer: 'slabs' }, {
      name: s.change ? `רצפת מרתף – ${s.change.id}: ${s.change.title}` : `רצפת מרתף ${s.id} (תלויה)${s.variant ? ' – לפי התוכניות' : ''}`, status: s.status, variant: s.variant,
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
    registry.add(g, { floor: b.sheet === 'K-11' ? 'unit' : 'ground', system: 'structure', stage: b.stage, layer: b.layer || 'groundBeams' }, {
      name: `קורה ${b.id} · ${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)}`, status: b.status,
      rows: [['חתך (רוחב/גובה)', `${Math.round(b.width_m * 100)}/${Math.round(b.depth_m * 100)} ס"מ`], ['מפלס עליון (O.K)', coords.fmtH(H(b.topRel))],
        ['מפלס תחתון', coords.fmtH(H(b.bottomRel))], ['אורך (בקירוב)', `${L.toFixed(2)} מ'`], ['גיליון', b.sheet]],
      note: (b.layer === 'ceilingBeams' ? 'קורה של תקרת הקרקע מעל המרתף – יושבת על קיר המרתף. ' : b.layer === 'groundFloorBeams' ? 'קורת קומת הקרקע על כלונסאות – נוצקת אחרי קירות המרתף והמילוי, יחד עם רצפת הקרקע. ' : '') + 'חתך ומפלס – מדויקים, מתווית הקורה. מיקום ואורך – בקירוב, לפי פס הבטון בתכנית K-400 (PDF). יוחלף ב-IFC.', source: `${b.source}; ${b.geometrySource}`,
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
  // "x-ray" copy drawn on top of the soil (chambers and pipes are underground) – same tags, not pickable
  const ghost = (g0, geos, pos, color, tags, quat) => {
    const gg = new THREE.Group();
    for (const geo of geos) {
      const gm = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: D.ghostOpacity, depthTest: false, depthWrite: false }));
      gm.position.copy(pos); if (quat) gm.quaternion.copy(quat); gm.renderOrder = 6; gm.raycast = () => {}; gg.add(gm);
    }
    scene.add(gg); registry.add(gg, { ...tags, stageTo: 'ceiling' }, { name: 'שיקוף', kind: 'ghost', pickable: false });
  };
  for (const c of P.chambers) {
    const r = c.diameter_m / 2, h = c.TL - c.IL;
    const sewer = c.kind === 'sewerManhole';
    // concrete chamber: closed cylinder of the drawn diameter from I.L to T.L, with a cover disk at T.L
    const geo = new THREE.CylinderGeometry(r, r, h, D.radialSegments, 1, false);
    const uv = geo.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * 2 * Math.PI * r, uv.getY(i) * h);
    const m = new THREE.Mesh(geo, materials.get('concrete')); m.position.copy(coords.toLocal(c.E, c.N, (c.TL + c.IL) / 2)); m.castShadow = m.receiveShadow = true;
    const cover = new THREE.Mesh(new THREE.CylinderGeometry(r * D.coverRatio, r * D.coverRatio, D.coverThickness_m, D.radialSegments),
      new THREE.MeshStandardMaterial({ color: sewer ? D.sewerColor : D.chamberColor, roughness: 0.5, metalness: 0.3 }));
    cover.position.copy(coords.toLocal(c.E, c.N, c.TL + D.coverThickness_m / 2));
    const g = new THREE.Group(); g.add(m, cover);
    ghost(g, [m.geometry], m.position, sewer ? D.sewerColor : D.chamberColor, sewer ? { floor: 'site', system: 'sewage', stage: 'walls', layer: 'sewageManholes' } : { floor: 'unit', system: 'drainage', stage: 'excavation', layer: 'drainChambers' });
    const d = document.createElement('div'); d.className = 'lbl beam';
    d.textContent = sewer ? `שוחה ${c.number} · ø${Math.round(c.diameter_m * 100)} · T.L ${c.TL.toFixed(2)} · I.L ${c.IL.toFixed(2)}` : `${c.id} תא שאיבה ø${Math.round(c.diameter_m * 100)} · I.L. ${c.IL.toFixed(2)}`;
    const o = new CSS2DObject(d); o.position.copy(coords.toLocal(c.E, c.N, c.TL + 0.4)); g.add(o);
    if (c.affectedBy) {
      const ga = new THREE.Group(); const da = document.createElement('div'); da.className = 'lbl change'; da.textContent = `מושפע מ-${c.affectedBy}`;
      const oa = new CSS2DObject(da); oa.position.copy(coords.toLocal(c.E, c.N, c.TL + 0.9)); ga.add(oa); scene.add(ga);
      registry.add(ga, { floor: 'unit', system: 'drainage', stage: 'excavation', layer: 'drainChambers' }, { name: `${c.id} – מושפע מ-${c.affectedBy}`, variant: { change: c.affectedBy, show: 'changed' }, note: c.note });
    }
    registry.add(g, sewer ? { floor: 'site', system: 'sewage', stage: 'walls', layer: 'sewageManholes' } : { floor: 'unit', system: 'drainage', stage: 'excavation', layer: 'drainChambers' }, {
      name: `${c.id} – ${c.title}`, status: c.status,
      rows: [['קוטר', `${Math.round(c.diameter_m * 100)} ס"מ`], ['T.L. (מכסה)', coords.fmtH(c.TL)], ['I.L. (תחתית)', coords.fmtH(c.IL)], ['עומק', `${c.H_m.toFixed(2)} מ'`],
        ['ITM', `${c.E.toFixed(3)} / ${c.N.toFixed(3)}`]],
      note: c.note || null, source: c.source,
    });
    scene.add(g);
  }
  // sewer pipes (centre line from the plumbing PDF; levels from the chambers / slope labels – see each record's status)
  const sevC = new THREE.Color(D.sewerColor);
  let pipeLen = 0;
  for (const q of P.pipes || []) {
    const r = (q.diameter_m || D.unknownDiameter_m) / 2;
    const z1 = q.ILfrom != null ? q.ILfrom + r : coords.H0 + q.displayLevelRel - r;
    const z2 = q.ILto != null ? q.ILto + r : z1;
    const a = coords.toLocal(q.fromITM[0], q.fromITM[1], z1), b = coords.toLocal(q.toITM[0], q.toITM[1], z2);
    const dir = b.clone().sub(a), L = dir.length();
    const geo = new THREE.CylinderGeometry(r, r, L, 16, 1); geo.translate(0, L / 2, 0); geo.rotateX(Math.PI / 2);
    const col = q.status === 'missing' ? D.unknownLevelColor : q.status === 'provisional' ? D.provisionalPipeColor : D.sewerColor;
    const m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: col, roughness: 0.5 }));
    m.position.copy(a); m.lookAt(b); m.castShadow = true;
    const g = new THREE.Group(); g.add(m);
    ghost(g, [geo], a, col, { floor: 'site', system: 'sewage', stage: 'walls', layer: 'sewagePipes' }, m.quaternion);
    if (q.ILfrom != null) {   // flow arrow at mid-length, pointing downstream
      const cone = new THREE.Mesh(new THREE.ConeGeometry(r * 1.8, r * 4, 12), new THREE.MeshBasicMaterial({ color: D.flowArrowColor }));
      cone.position.copy(a.clone().lerp(b, 0.5)); cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize()); g.add(cone);
    }
    if (q.lengthM > D.labelMinLength_m && q.diameter_m) {
      const dl = document.createElement('div'); dl.className = 'lbl pipe';
      dl.textContent = `ø${Math.round(q.diameter_m * 1000)} · ${(q.slope * 100).toFixed(q.slope < 0.1 ? 2 : 1)}%${q.status !== 'source' ? ' *' : ''}`;
      const o = new CSS2DObject(dl); o.position.copy(a.clone().lerp(b, 0.5)); o.position.y += 0.25; g.add(o);
    }
    pipeLen += q.lengthM;
    const st = { source: 'מפלסים מהשוחות/תוויות', derived: 'מפלס נגזר (שיפוע כתוב)', provisional: 'מפלס זמני (שיפוע הונח 2%)', missing: 'מפלס לא ידוע – מיקום בלבד' }[q.status];
    registry.add(g, { floor: 'site', system: 'sewage', stage: 'walls', layer: 'sewagePipes' }, {
      name: `צינור ביוב ${q.id}${q.diameter_m ? ` · ø${Math.round(q.diameter_m * 1000)} ${q.material || ''}` : ''}`, status: q.status === 'source' ? 'source' : 'provisional',
      rows: [['אורך', `${q.lengthM.toFixed(2)} מ'`], ['שיפוע', q.slope ? `${(q.slope * 100).toFixed(2)}%` : '—'],
        ['I.L התחלה → סוף', q.ILfrom != null ? `${coords.fmtH(q.ILfrom)} → ${coords.fmtH(q.ILto)}` : '—'], ['כיוון זרימה', q.between?.[1] ? `אל ${q.between[1]}` : '—'], ['מעמד', st]]
        .concat(q.dropAtEnd_m ? [['מפל בכניסה לשוחה', `${q.dropAtEnd_m.toFixed(2)} מ'`]] : []),
      note: q.note || null, source: q.source,
    });
    scene.add(g);
  }
  // crossings: pipe through a basement wall / foundation beam -> sleeve
  for (const x of P.pipeCrossings || []) {
    if (!x.pipe) continue;
    const q = (P.pipes || []).find(p => p.id === x.pipe); if (!q) continue;
    const r = (q.diameter_m || D.unknownDiameter_m) / 2;
    const t = Math.hypot(x.E - q.fromITM[0], x.N - q.fromITM[1]) / q.lengthM;
    const z = q.ILfrom != null ? q.ILfrom + (q.ILto - q.ILfrom) * t + r : coords.H0 + q.displayLevelRel - r;
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r * 1.6, r * 0.35, 8, 24), new THREE.MeshBasicMaterial({ color: D.sleeveColor }));
    ring.position.copy(coords.toLocal(x.E, x.N, z)); ring.lookAt(coords.toLocal(q.toITM[0], q.toITM[1], z));
    const g = new THREE.Group(); g.add(ring);
    const dl = document.createElement('div'); dl.className = 'lbl removed'; dl.style.textDecoration = 'none'; dl.textContent = `שרוול · ${x.pipe} ↔ ${x.element}`;
    const o = new CSS2DObject(dl); o.position.copy(ring.position); o.position.y += 0.35; g.add(o);
    registry.add(g, { floor: 'site', system: 'sewage', stage: 'walls', layer: 'sewagePipes' }, {
      name: `מעבר צנרת ${x.pipe} דרך ${x.kind === 'beam' ? 'קורה' : 'קיר מרתף'} ${x.element} – שרוול נדרש`, status: 'provisional',
      rows: [['ITM', `${x.E.toFixed(3)} / ${x.N.toFixed(3)}`], ['אורך מעבר', `${x.length_m.toFixed(2)} מ'`]],
      note: x.note || 'לתאם עם הקונסטרוקטור: שרוול/פתח באלמנט הבטון לפני היציקה.', source: q.source,
    });
    scene.add(g);
  }
  return { chambers: P.chambers.length, pipes: (P.pipes || []).length, pipeLength_m: pipeLen, sleeves: (P.pipeCrossings || []).filter(x => x.pipe).length };
}

// Owner-change zones (data/changes/owner-changes.json → zone): a translucent purple box over the changed area.
export function buildOwnerChangeZones(ctx) {
  const { data, coords, registry, scene, display } = ctx;
  const D = display.framing;
  for (const c of (data.ownerChanges?.changes || [])) {
    if (!c.zone) continue;
    const sp = data.ownerChangesGeometry?.changes?.[c.id]?.slabSplit; if (!sp) continue;
    const s = sp[c.zone.slabPart];
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
      name: `${c.id} – ${c.title}`, status: 'owner-change', variant: { change: c.id, show: 'changed' }, note: `${c.description} ${c.zone.note}`, source: c.source,
    });
    scene.add(g);
  }
}

// Pool + machine room / balance tank (data/structure/pool.json): cast with the basement (slab / walls stages). PROVISIONAL.
export function buildPool(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const PL = data.pool; if (!PL) return null;
  const D = display.framing; const conc = materials.get('concrete');
  const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
  const prism = (ring, z0, z1) => {
    const g = new THREE.ExtrudeGeometry(new THREE.Shape(ring.map(toV)), { depth: z1 - z0, bevelEnabled: false });
    g.rotateX(-Math.PI / 2); g.translate(0, z0 - coords.H0, 0);
    const p = g.attributes.position, uv = g.attributes.uv; for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) + p.getY(i), p.getZ(i) + p.getY(i));
    const m = new THREE.Mesh(g, conc); m.castShadow = m.receiveShadow = true;
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(g, 30), new THREE.LineBasicMaterial({ color: D.provisionalEdgeColor }));
    const grp = new THREE.Group(); grp.add(m, e); return grp;
  };
  const lbl = (text, ring, z) => { const c = ring.reduce((a, p) => [a[0] + p[0] / ring.length, a[1] + p[1] / ring.length], [0, 0]);
    const d = document.createElement('div'); d.className = 'lbl beam'; d.textContent = text; const o = new CSS2DObject(d); o.position.copy(coords.toLocal(c[0], c[1], z)); return o; };
  const P = PL.pool, T = PL.tank;
  const poolBottom = Math.min(P.slabUndersideWest, P.slabUndersideEast);
  // slabs
  const ps = prism(P.outerITM, poolBottom, P.floorFinish); ps.add(lbl(`בריכה · רצפה ${P.floorFinish.toFixed(2)} · תחתית ${P.slabUndersideWest.toFixed(2)}/${P.slabUndersideEast.toFixed(2)}`, P.outerITM, P.floorFinish + 0.4));
  registry.add(ps, { floor: 'unit', system: 'structure', stage: 'slab', layer: 'pool' }, { name: 'רצפת הבריכה (זמני)', status: 'provisional',
    rows: [['מפלס רצפה (גמר)', coords.fmtH(P.floorFinish)], ['תחתית (ראשי כלונסאות)', `${coords.fmtH(P.slabUndersideWest)} מערב · ${coords.fmtH(P.slabUndersideEast)} מזרח`],
      ['מפלס סיפון', coords.fmtH(P.deck)], ['שטח חוץ', `${P.area_m2.toFixed(2)} מ"ר`]], note: P.note, source: P.source });
  scene.add(ps);
  const ts = prism(T.outerITM, T.slabUnderside, T.floorFinish); ts.add(lbl(`חדר מכונות / בור איזון · רצפה ${T.floorFinish.toFixed(2)}`, T.outerITM, T.floorFinish + 0.4));
  registry.add(ts, { floor: 'unit', system: 'structure', stage: 'slab', layer: 'pool' }, { name: 'רצפת חדר מכונות / בור איזון (זמני)', status: 'provisional',
    rows: [['רצפה (גמר)', coords.fmtH(T.floorFinish)], ['עובי רצפה', `${Math.round(T.slabThickness_m * 100)} ס"מ`], ['ראש כלונס 32', coords.fmtH(T.pile32Head)]], note: T.note, source: T.source });
  scene.add(ts);
  // walls (from the slab underside up to the deck)
  const wg = new THREE.Group();
  for (const w of P.wallsITM) wg.add(prism(w, poolBottom, P.deck));
  for (const w of T.wallsITM) wg.add(prism(w, T.slabUnderside, T.top));
  if (PL.channel) {
    for (const w of PL.channel.wallsITM) wg.add(prism(w, PL.channel.bottom, PL.channel.top));
    wg.add(lbl('תעלת כיסוי הבריכה', PL.channel.outerITM, PL.channel.top + 0.4));
  }
  registry.add(wg, { floor: 'unit', system: 'structure', stage: 'walls', layer: 'pool' }, { name: 'קירות הבריכה, תעלת הכיסוי וחדר המכונות (זמני)', status: 'provisional',
    rows: [['ראש קיר (סיפון)', coords.fmtH(P.deck)], ['תעלת כיסוי – תחתית (הונח)', PL.channel ? coords.fmtH(PL.channel.bottom) : '—']],
    note: `${P.note} ${T.note} ${PL.channel?.note || ''}`, source: `${P.source}; ${T.source}` });
  scene.add(wg);
  return { poolArea_m2: P.area_m2, tankArea_m2: T.area_m2 };
}

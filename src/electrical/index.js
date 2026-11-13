import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { cylBetween, collar, sphere } from '../plumbing/geom.js';

// Electrical layer (separate module). Stage ח1: main supply – meter cabinet (pillar) -> pull pit -> feeder conduits -> main panel.
// Data: data/electrical/supply.json (tools/electrical/propose_supply.py), display constants: data/electrical/display.json.
// Each part carries the construction step it is built in (supply.steps), so the slider shows the connection being built.
// Everything here is a design proposal (status provisional) – marked in the rows and tinted.
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
  const stepOf = Object.fromEntries(S.steps.map(s => [s.step, s]));
  const stepRow = (id) => ['שלב ביצוע', stepOf[id] ? `${stepOf[id].n}. ${stepOf[id].title}` : id];
  const add = (grp, tags, meta) => {
    scene.add(grp); const it = registry.add(grp, tags, { ...meta, rows: [...(meta.rows || []), stepRow(tags.step)] }); it.meta.electrical = true; items.push(it); return it;
  };
  const st = (s) => (S.approval ? `אושר ${S.approval.date.split('-').reverse().join('.')} · ` : '') + (D.statusLabel[s] || s);
  const L = (p) => coords.toLocal(p[0], p[1], p[2]);
  const dirOf = (a, b) => new THREE.Vector3(b[0] - a[0], 0, -(b[1] - a[1])).normalize();
  const F = S.feeder, P = S.mainPanel, T = S.trench, PP = S.pullPit;
  const base = { floor: 'site', system: 'electrical', layer: 'elSupply' };

  // a horizontal box along a plan segment a->b (ITM), between levels z0..z1 (absolute)
  const slabAlong = (a, b, w, z0, z1, m) => {
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(len + w, z1 - z0, w), m);
    mesh.position.copy(L([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (z0 + z1) / 2]));
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), dirOf(a, b));
    return mesh;
  };

  // ---- step 1: trench (open only while it is dug)
  {
    const g = new THREE.Group();
    const m = std(D.trenchColor, 0.95, 0, { transparent: true, opacity: D.trenchOpacity, depthWrite: false });
    for (const s of T.segments) g.add(slabAlong(s.from, s.to, T.width_m, T.bottomAbs, s.topAbs, m));
    add(g, { ...base, stage: 'excavation', step: 'underSlab', stepTo: 'underSlab' }, {
      name: 'תעלה לקו ההזנה', kind: 'elTrench',
      rows: [['מעמד', st(T.status)], ['רוחב', `${Math.round(T.width_m * 100)} ס"מ`], ['תחתית', fmtH(T.bottomAbs)],
        ['עומק לפי קטע', T.segments.map(s => `${s.depth_m.toFixed(2)} מ' (${s.topRule})`).join(' · ')], ['הערה', T.note]],
      source: S.source, note: 'הצעה בלבד – ממתין לאישור' });
  }

  // ---- step 2: sand bed around the conduits (until the slab is poured over it)
  {
    const g = new THREE.Group();
    const m = std(D.sandColor, 0.95, 0, { transparent: true, opacity: D.sandOpacity, depthWrite: false });
    for (const s of T.segments) g.add(slabAlong(s.from, s.to, T.width_m, T.bottomAbs, T.sandTopAbs, m));
    add(g, { ...base, stage: 'groundBeams', step: 'underSlabPlumbing', stepTo: 'underSlabPlumbing' }, {
      name: 'מצע ועטיפת חול לצנרת', kind: 'elSand',
      rows: [['מעמד', st(T.status)], ['חול', `${fmtH(T.bottomAbs)} → ${fmtH(T.sandTopAbs)}`], ['סרט סימון', `${fmtH(T.warningTapeAbs)} – בחצר הפתוחה בלבד`]],
      source: S.source, note: 'הצעה בלבד – ממתין לאישור' });
  }

  // ---- step 2: conduits (main + spare), parallel along the route
  const pts = F.pts3d.map(L);
  const up = new THREE.Vector3(0, 1, 0);
  const wallAlong = new THREE.Vector3(P.alongITM[0], 0, -P.alongITM[1]).normalize();
  const side = (i) => {
    let d = null;
    for (const [a, b] of [[i - 1, i], [i, i + 1]]) { if (a < 0 || b >= pts.length) continue; const v = pts[b].clone().sub(pts[a]); v.y = 0; if (v.length() > 0.05) d = d ? d.add(v.normalize()) : v.normalize(); }
    if (!d || d.length() < 1e-3) return wallAlong.clone();
    return new THREE.Vector3().crossVectors(up, d.normalize()).normalize();
  };
  const n = F.conduits.length;
  const lanes = F.conduits.map((c, k) => { const off = (k - (n - 1) / 2) * F.conduitSpacing_m; return pts.map((p, i) => p.clone().addScaledVector(i >= pts.length - 2 ? wallAlong : side(i), off)); });
  {
    const g = new THREE.Group();
    F.conduits.forEach((c, k) => {
      const r = c.D_mm / 2000, m = tint(std(k === 0 ? D.conduitColor : D.spareConduitColor, 0.6)), q = lanes[k];
      for (let i = 0; i < q.length - 1; i++) { const s = cylBetween(q[i], q[i + 1], r, m, D.radialSegments); if (s) g.add(s); }
      for (let i = 1; i < q.length - 1; i++) g.add(sphere(q[i], r, m, 12));
    });
    const mid = pts[F.pitIndex + 1].clone().lerp(pts[F.pitIndex + 2], 0.5);
    label(g, mid.clone().add(new THREE.Vector3(0, D.labelOffset_m, 0)), `קו הזנה ${S.connection.size} · ${n}×ø${F.conduits[0].D_mm} · ${F.length_m.toFixed(1)} מ'`);
    const fails = S.checks.filter(c => !c.ok);
    add(g, { ...base, stage: 'groundBeams', step: 'underSlabPlumbing' }, {
      name: F.name, kind: 'elFeeder', id: F.id,
      rows: [['מעמד', st(F.status)], ['גודל חיבור', `${S.connection.size} (${S.connection.kVA} kVA) – ${S.connection.note}`],
        ['צנרת', F.conduits.map(c => `${c.role}: ø${c.D_mm} ${c.material}`).join(' · ')], ['חוט משיכה', F.pullWire], ['אורך תוואי', `${F.length_m.toFixed(2)} מ'`],
        ['קטעי משיכה', F.pulls.map(p => `${p.name}: ${p.length_m.toFixed(1)} מ', ${p.bends_deg}°`).join(' · ')],
        ['רום ציר הצינור', `${fmtH(H0 + F.centreRel)} – ${F.levelRule}`], ['עובר דרך רצפה', F.throughSlab || '—'],
        ['בדיקות', `${S.checks.length} בדיקות, ${fails.length} נכשלו${fails.length ? ': ' + fails.map(c => c.ref).join(', ') : ''}`], ['קצה הפילר', F.pillarEnd.note]],
      source: F.source, note: 'הצעה בלבד – ממתין לאישור' });
  }

  // ---- step 2 / 5: pull pit (precast chamber; cover with the development)
  {
    const g = new THREE.Group(), gc = new THREE.Group();
    const c = PP.centreITM, a = PP.alongITM, w = D.pitWall_m, o = PP.outer_m, h = PP.topAbs - PP.bottomAbs;
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1, 0, 0), new THREE.Vector3(a[0], 0, -a[1]).normalize());
    const wm = tint(std(D.pitColor, 0.85));
    for (const [dx, dz, sx, sz] of [[0, (o - w) / 2, o, w], [0, -(o - w) / 2, o, w], [(o - w) / 2, 0, w, o - 2 * w], [-(o - w) / 2, 0, w, o - 2 * w]]) {
      const m = new THREE.Mesh(new THREE.BoxGeometry(sx, h, sz), wm);
      m.position.copy(L([c[0], c[1], PP.bottomAbs + h / 2])).add(new THREE.Vector3(dx, 0, dz).applyQuaternion(q)); m.quaternion.copy(q); m.castShadow = true; g.add(m);
    }
    label(g, L([c[0], c[1], PP.topAbs + D.labelOffset_m]), `${PP.id} תא משיכה ${Math.round(PP.inner_m * 100)}×${Math.round(PP.inner_m * 100)} · עומק ${PP.depth_m.toFixed(2)}`);
    const rows = [['מעמד', st(PP.status)], ['מיקום', PP.location], ['מידות', `פנים ${PP.inner_m}×${PP.inner_m} מ', חוץ ${PP.outer_m}×${PP.outer_m} מ'`], ['ראש / תחתית', `${fmtH(PP.topAbs)} / ${fmtH(PP.bottomAbs)} (עומק ${PP.depth_m.toFixed(2)} מ')`],
      ['ראש – מקור', PP.topSource], ['חומר', PP.material], ['מכסה', PP.coverClass], ['למה', PP.note]];
    add(g, { ...base, stage: 'groundBeams', step: 'underSlabPlumbing' }, { name: PP.name, kind: 'elPit', id: PP.id, rows, source: S.source, note: 'הצעה בלבד – ממתין לאישור' });
    const cover = new THREE.Mesh(new THREE.BoxGeometry(o, D.pitCover_m, o), std(D.pitCoverColor, 0.6, 0.6));
    cover.position.copy(L([c[0], c[1], PP.topAbs - D.pitCover_m / 2])); cover.quaternion.copy(q); gc.add(cover);
    add(gc, { ...base, stage: 'finishes', step: 'development' }, { name: `מכסה ${PP.id} (${PP.coverClass})`, kind: 'elPitCover', id: PP.id + '-C', rows, source: S.source, note: 'הצעה בלבד – ממתין לאישור' });
  }

  // ---- step 4 / 3: sleeves
  const sleeveM = std(D.sleeveColor, 0.6, 0, { transparent: true, opacity: 0.75 });
  for (const s of S.sleeves) {
    const g = new THREE.Group(); const dir = s.axis === 'v' ? new THREE.Vector3(0, 1, 0) : pts[1].clone().sub(pts[0]).normalize();
    g.add(collar(L(s.at), dir, s.sleeveD_mm / 2000 * (1 + (s.count - 1) * 0.9), D.sleeveLength_m, sleeveM));
    add(g, { floor: s.id === 'ES-1' ? 'ground' : 'site', system: 'electrical', stage: s.id === 'ES-1' ? 'slab' : 'walls', layer: 'elSupply', step: s.step }, {
      name: `שרוול ${s.id} – ${s.through}`, kind: 'elSleeve', id: s.id,
      rows: [['מעמד', st(s.status)], ['מעבר', s.through], ['שרוולים', `${s.count} × ø${s.sleeveD_mm}`], ['ITM / רום', `${coords.fmtEN(s.at[0], s.at[1])} · ${fmtH(s.at[2])}`], ['הערה', s.note]],
      source: S.source, note: 'הצעה בלבד – ממתין לאישור' });
  }

  // ---- step 6: main panel (surface mounted in the niche) + the cable pulled through the main conduit
  {
    const g = new THREE.Group();
    const box = new THREE.Mesh(new THREE.BoxGeometry(P.width_m, P.height_m, P.depth_m), tint(std(D.panelColor, 0.45, 0.3))); box.castShadow = true;
    box.position.copy(L([P.faceITM[0] + P.normalITM[0] * P.depth_m / 2, P.faceITM[1] + P.normalITM[1] * P.depth_m / 2, H0 + P.bottomRel + P.height_m / 2]));
    const nx = new THREE.Vector3(P.normalITM[0], 0, -P.normalITM[1]).normalize();
    box.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), nx); g.add(box);
    const door = new THREE.Mesh(new THREE.BoxGeometry(P.width_m * 0.9, P.height_m * 0.92, 0.012), std(D.panelDoorColor, 0.35, 0.2));
    door.position.copy(box.position).addScaledVector(nx, P.depth_m / 2 + 0.006); door.quaternion.copy(box.quaternion); g.add(door);
    label(g, box.position.clone().add(new THREE.Vector3(0, P.height_m / 2 + D.labelOffset_m, 0)), `לוח ראשי (${st(P.status)})`);
    add(g, { floor: 'ground', system: 'electrical', stage: 'finishes', layer: 'elSupply', step: 'finishes' }, {
      name: P.name, kind: 'elPanel', id: P.id,
      rows: [['מעמד', st(P.status)], ['החלטה', P.decision], ['קיר', `${P.hostWall} · בלוקים ${Math.round(P.wallThickness_m * 100)} ס"מ · אורך ${P.wallClearLength_m.toFixed(2)} מ'`],
        ['מידות (ר×ג×ע)', `${P.width_m} × ${P.height_m} × ${P.depth_m} מ'`], ['מפלס תחתית / ראש', `${fmtH(H0 + P.bottomRel)} / ${fmtH(H0 + P.topRel)}`], ['הערה', P.note],
        ...(data.electricalUnits ? [['מוני משנה', data.electricalUnits.units.map(u => `${u.meter.id} (${u.name}) – ${u.feeder.protection}`).join(' · ') + ` · ${data.electricalUnits.subMeter.type}`]] : [])],
      source: P.source, note: 'הצעה בלבד – ממתין לאישור' });
    const gk = new THREE.Group(), km = std(D.cableColor, 0.5), q = lanes[0];
    for (let i = 0; i < q.length - 1; i++) { const s = cylBetween(q[i], q[i + 1], D.cableD_m / 2, km, 10); if (s) gk.add(s); }
    add(gk, { ...base, stage: 'finishes', step: 'finishes' }, {
      name: `כבל הזנה ${F.cable.type}`, kind: 'elCable',
      rows: [['מעמד', st(F.status)], ['כבל', `${F.cable.type} – ${F.cable.note}`], ['אורך משוער', `${F.cableLength_m.toFixed(1)} מ' (${F.cableLengthNote})`],
        ['משיכה', F.pulls.map(p => `${p.name}: ${p.length_m.toFixed(1)} מ', ${p.bends_deg}°`).join(' · ')]],
      source: F.source, note: 'הצעה בלבד – ממתין לאישור' });
  }
  // ---- ח1ב: unit panels (one per basement unit), feeders from the main panel (cast in the ground slab), sub-meters in the main panel
  const UN = data.electricalUnits;
  if (UN) {
    const stU = (s) => D.statusLabel[s] || s;
    const ustep = Object.fromEntries(UN.steps.map(s => [s.step, s]));
    const urow = (id) => ['שלב ביצוע', ustep[id] ? `${ustep[id].n}. ${ustep[id].title}` : id];
    const addU = (grp, tags, meta) => { scene.add(grp); const it = registry.add(grp, tags, { ...meta, rows: [...(meta.rows || []), urow(tags.step)] }); it.meta.electrical = true; items.push(it); return it; };
    for (const u of UN.units) {
      const p = u.panel, f = u.feeder, r = f.conduitD_mm / 2000;
      // panel
      const g = new THREE.Group();
      const box = new THREE.Mesh(new THREE.BoxGeometry(p.width_m, p.height_m, p.depth_m), tint(std(D.unitPanelColor, 0.45, 0.3))); box.castShadow = true;
      box.position.copy(L([p.faceITM[0] + p.normalITM[0] * p.depth_m / 2, p.faceITM[1] + p.normalITM[1] * p.depth_m / 2, p.bottomAbs + p.height_m / 2]));
      box.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), new THREE.Vector3(p.normalITM[0], 0, -p.normalITM[1]).normalize()); g.add(box);
      label(g, box.position.clone().add(new THREE.Vector3(0, p.height_m / 2 + D.labelOffset_m, 0)), `${p.id} · ${u.name}`);
      const rows = [['מעמד', stU(p.status)], ['החלטה', UN.decision], ['כניסה', `${u.door} – ${u.doorName} (${u.doorKind === 'door' ? 'דלת' : 'הזזה'}, אדן ${u.doorSill_rel >= -2.6 + 1e-3 ? (u.doorSill_rel + 2.6).toFixed(2) + ' מעל הרצפה' : 'ברצפה'})`],
        ['מיקום', `${p.fromDoor_m.toFixed(2)} מ' ממרכז הפתח, על פני קיר המרתף`], ['מידות', `${p.width_m}×${p.height_m}×${p.depth_m} מ' · ${p.modules} מודולים`], ['תחתית / ראש', `${fmtH(p.bottomAbs)} / ${fmtH(p.topAbs)}`],
        ['הזנה', `${f.protection} · ${f.cable} · ${f.conduit}`], ['מונה משנה', `${u.meter.id} – ${u.meter.type}, ${u.meter.where}`], ['הערה', p.note]];
      if (u.warning) rows.push(['⚠ לבדיקה', u.warning]);
      addU(g, { floor: 'unit', system: 'electrical', stage: 'finishes', layer: 'elSupply', step: 'finishes' }, { name: p.name, kind: 'elUnitPanel', id: p.id, rows, source: p.source, note: 'הצעה בלבד – ממתין לאישור' });
      // feeder: the part cast in the slab (and the riser in the niche wall) vs the surface part in the unit
      const pts = f.pts3d.map(L), cast = new THREE.Group(), surf = new THREE.Group();
      const zs = UN.levels.slabSoffitAbs;
      const mc = tint(std(D.unitConduitColor, 0.6)), ms = std(D.surfaceConduitColor, 0.5, 0.2);
      for (let i = 0; i < pts.length - 1; i++) {
        const inSlab = f.pts3d[i][2] >= zs - 1e-3 && f.pts3d[i + 1][2] >= zs - 1e-3;
        const seg = cylBetween(pts[i], pts[i + 1], r, inSlab ? mc : ms, D.radialSegments); if (seg) (inSlab ? cast : surf).add(seg);
        if (i > 0) (inSlab ? cast : surf).add(sphere(pts[i], r, inSlab ? mc : ms, 10));
      }
      label(cast, pts[2].clone().lerp(pts[3], 0.5).add(new THREE.Vector3(0, D.labelOffset_m, 0)), `${f.id} · ø${f.conduitD_mm} ביציקה · ${f.slabLength_m.toFixed(1)} מ'`);
      const frows = [['מעמד', stU(f.status)], ['מ → אל', `לוח ראשי (MDB) → ${p.id}`], ['הגנה / כבל', `${f.protection} · ${f.cable}`], ['צנרת', f.conduit],
        ['ביציקה (רצפת הקרקע)', `${f.slabLength_m.toFixed(2)} מ' ב-${fmtH(UN.levels.conduitInSlabAbs)} – ${UN.slabRoute.note}`], ['גלוי ביחידה', `${f.soffitRun_m.toFixed(2)} מ' בתקרה + ירידה ללוח – ${UN.drop.how}`],
        ['אורך כבל משוער', `${f.cableLength_m.toFixed(1)} מ'`]];
      if (f.dropInMamadZone) frows.push(['⚠ ממ"ד', 'מעל הלוח רצפת הממ"ד (GS7): אין צנרת ביציקה שם. הצינור יוצא מהתקרה מחוץ לממ"ד ורץ גלוי בפינת התקרה-קיר עד הלוח (E17)']);
      addU(cast, { floor: 'ground', system: 'electrical', stage: 'slab', layer: 'elSupply', step: 'groundSlab' }, { name: `${f.id} – צנרת ביציקה ל-${p.id}`, kind: 'elUnitFeeder', id: f.id, rows: frows, source: f.source, note: 'הצעה בלבד – ממתין לאישור' });
      if (surf.children.length) addU(surf, { floor: 'unit', system: 'electrical', stage: 'finishes', layer: 'elSupply', step: 'finishes' }, { name: `${f.id} – צנרת גלויה ביחידה`, kind: 'elUnitSurface', id: f.id + '-S', rows: frows, source: f.source, note: 'הצעה בלבד – ממתין לאישור' });
    }
  }
  // ---- ח1ג: first-floor circuits from the main panel – riser above the panel, trunk in the plenum, one branch per room
  const FR = data.electricalFirstRiser;
  if (FR) {
    const fstep = Object.fromEntries(FR.steps.map(s => [s.step, s]));
    const frow = (id) => ['שלב ביצוע', fstep[id] ? `${fstep[id].n}. ${fstep[id].title}` : id];
    const addF = (grp, tags, meta) => { scene.add(grp); const it = registry.add(grp, tags, { ...meta, rows: [...(meta.rows || []), frow(tags.step)] }); it.meta.electrical = true; items.push(it); return it; };
    const Lv = FR.levels, B = FR.bundle, z = Lv.routeAbs;
    const trayM = tint(std(D.trayColor, 0.55, 0.2)), brM = tint(std(D.branchColor, 0.55, 0.1));
    const tray = (g, a, b, w, hgt, m) => g.add(slabAlong(a, b, w, z - hgt / 2, z + hgt / 2, m));
    const provRows = [['מעמד', 'הצעה – זמני'], ['החלטה', FR.decision], ['הנמכה (זמני)', `${fmtH(Lv.droppedCeilingAbs)} – ${Lv.droppedCeiling.note}`],
      ['רצפה גמורה קומה א\'', `${fmtH(Lv.firstFloorFinishAbs)} – ${Lv.firstFloorFinishSource}`], ['תקרת הגג (תחתית)', fmtH(Lv.roofSoffitAbs)], ['גובה התוואי', `${fmtH(z)} (חלל טכני ${Math.round(Lv.plenum_m * 100)} ס"מ)`], ['צנרת', `${B.conduits} – ${B.note}`]];
    // riser: in front of the niche wall, from the panel top to the plenum (inside the joinery cabinet, through FS2, closed trunking above)
    {
      const g = new THREE.Group(); const r = FR.riser;
      const m = new THREE.Mesh(new THREE.BoxGeometry(B.riserWidth_m, r.toAbs - r.fromAbs, B.trayHeight_m), trayM);
      m.position.copy(L([r.planITM[0], r.planITM[1], (r.fromAbs + r.toAbs) / 2]));
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), new THREE.Vector3(r.normalITM[0], 0, -r.normalITM[1]).normalize()); m.castShadow = true; g.add(m);
      g.add(collar(L([r.planITM[0], r.planITM[1], (Lv.fs2TopAbs + Lv.fs2BottomAbs) / 2]), new THREE.Vector3(0, 1, 0), B.riserWidth_m / 2 + 0.03, Lv.fs2TopAbs - Lv.fs2BottomAbs + 0.06, sleeveM));
      label(g, L([r.planITM[0], r.planITM[1], r.toAbs + D.labelOffset_m]), `עלייה לקומה א' · ${r.height_m.toFixed(1)} מ'`);
      addF(g, { floor: 'ground', system: 'electrical', stage: 'ceiling', layer: 'elSupply', step: 'finishes' }, { name: 'עלייה לקומה א\' מעל הלוח הראשי', kind: 'elFirstRiser', id: 'FR-RISER',
        rows: [...provRows, ['עלייה', `${fmtH(r.fromAbs)} → ${fmtH(r.toAbs)} (${r.height_m.toFixed(2)} מ')`], ['קורה B-25', `הצרור עולה לפניה – ${r.beamB25Gap_m.toFixed(2)} מ' מפני הקורה; לא חודר לקורה`], ['רצפה', `שרוולים ב-${r.throughSlab}`], ['הערה', r.note]],
        source: FR.source, note: 'הצעה בלבד – ממתין לאישור' });
    }
    // trunk in the plenum + gypsum box over the void
    {
      const g = new THREE.Group(), t = FR.trunk.planITM;
      for (let i = 0; i < t.length - 1; i++) tray(g, t[i], t[i + 1], B.trayWidth_m, B.trayHeight_m, trayM);
      const dp = FR.distribution.planITM;
      const bx = new THREE.Mesh(new THREE.BoxGeometry(D.boxSize_m, D.boxSize_m * 0.5, D.boxSize_m), std('#263238', 0.5, 0.3)); bx.position.copy(L([dp[0], dp[1], z])); g.add(bx);
      label(g, L([dp[0], dp[1], z + D.labelOffset_m]), 'תיבת חלוקה – קומה א\'');
      addF(g, { floor: 'first', system: 'electrical', stage: 'finishes', layer: 'elSupply', step: 'finishes' }, { name: 'צרור מעגלי קומה א\' בחלל הטכני', kind: 'elFirstTrunk', id: 'FR-TRUNK',
        rows: [...provRows, ['אורך', `${FR.trunk.length_m.toFixed(2)} מ', מתוכם ${FR.trunk.overVoid_m.toFixed(2)} מ' מעל חלל (סינר גבס)`], ['פתחים בקירות בלוקים', FR.trunk.blockWalls.join(', ') || '—'], ['תיבת חלוקה', FR.distribution.name], ['הערה', FR.trunk.note]],
        source: FR.source, note: 'הצעה בלבד – ממתין לאישור' });
    }
    // one branch per room (to just inside the room door)
    for (const br of FR.branches) {
      const g = new THREE.Group(), q = br.planITM;
      for (let i = 0; i < q.length - 1; i++) tray(g, q[i], q[i + 1], D.branchWidth_m, D.branchHeight_m, brM);
      addF(g, { floor: 'first', system: 'electrical', stage: 'finishes', layer: 'elSupply', step: 'finishes' }, { name: `הסתעפות לחדר – דלת ${br.door}`, kind: 'elFirstBranch', id: `FR-${br.door}`,
        rows: [...provRows, ['לחדר', `${br.door} – ${br.doorName}`], ['אורך', `${br.length_m.toFixed(2)} מ'`], ['פתחים בקירות', br.blockWalls.join(', ') || '—'], ['הערה', 'הסתעפות סכמטית עד פנים החדר; הפיזור לנקודות – בשלב הנקודות (ח4)']],
        source: FR.source, note: 'הצעה בלבד – ממתין לאישור' });
    }
  }
  return { items, supply: S, units: UN, firstRiser: FR };
}

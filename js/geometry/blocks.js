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
  // owner changes (OC-n, data/changes): the changed element is red in both variants – as drawn: red outline; with the
  // change: red, half transparent, with a red OC-n tag
  const ocM = new THREE.MeshStandardMaterial({ color: DF.ownerChangeColor, roughness: 0.7, transparent: true, opacity: 0.55, depthWrite: false });
  const clashM = new THREE.MeshStandardMaterial({ color: DF.ownerChangeColor, roughness: 0.6 });
  const ocTag = (text, pos) => { const d = document.createElement('div'); d.className = 'lbl oc-tag'; d.textContent = text; const o = new CSS2DObject(d); o.position.copy(pos); return o; };
  const vmeta = (x) => (x.variant ? { variant: x.variant } : {});
  const lintM = new THREE.MeshStandardMaterial({ color: DB.lintelColor, roughness: 0.85 });
  const LT = data.blocksCfg?.lintel; const SIDE = { L: 'שמאל', R: 'ימין' };
  const unit = new THREE.BoxGeometry(1, 1, 1);
  const FLOOR = { unit: 'יחידת דיור', ground: 'קומת קרקע', first: "קומה א'" };
  const stats = { full: 0, cut: 0, area_m2: 0, byThickness: {}, boxes: 0 };
  // owner changes that cancel a block wall (owner-changes-geometry.json blocks.removeWalls, e.g. OC-10): the wall is the
  // "as drawn" variant – shown with a red outline while the change is off, gone with it on
  const removedBy = {};
  for (const [id, g] of Object.entries(data.ownerChangesGeometry?.changes || {})) for (const wid of g.blocks?.removeWalls || []) removedBy[wid] = id;
  for (const w0 of B.walls) {
    const w = removedBy[w0.id] && !w0.variant ? { ...w0, ownerChange: removedBy[w0.id], variant: { change: removedBy[w0.id], show: 'original' } } : w0;
    const [[E0, N0], [E1, N1]] = w.axisITM, L = w.length_m, t = w.thickness_m;
    const p0 = coords.toLocal(E0, N0, coords.H0), p1 = coords.toLocal(E1, N1, coords.H0);
    const dir = new THREE.Vector3().subVectors(p1, p0).normalize(), q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(1, 0, 0), dir);
    const full = [], cut = [];
    let k = 0, z = w.bottomRel;
    const D = w.courseDatum, bond = w.bond, mod = (a, m) => ((a % m) + m) % m;
    while (z < w.topRel - 0.005) {   // same coursing as tools/extract_blocks.py: one course line per floor, one block grid per wall line
      const kk = D != null ? Math.round((z - D) / BH) : k;
      let nxt = D != null ? D + (kk + 1) * BH : z + BH; if (nxt - z < 0.005) nxt += BH;
      const h = Math.min(nxt - z, w.topRel - z), off = (BL / 2) * (mod(kk, 2));
      const x0 = bond ? mod(bond.sign * (off - bond.p0), BL) - BL : -off;
      const holes = [...w.openings, ...(w.lintels || [])];
      // an opening / lintel edge inside the course splits it into bands – blocks cut at the head / lintel underside
      const cuts = [...new Set([z, z + h, ...holes.flatMap(o => [o.z0, o.z1]).filter(c => c > z + 0.005 && c < z + h - 0.005)])].sort((a, b) => a - b);
      for (let i = 0; i < cuts.length - 1; i++) {
        const zb = cuts[i], zt = cuts[i + 1], hb = zt - zb;
        let segs = [[0, L]];
        for (const o of holes) if (o.z0 < zt - 0.005 && o.z1 > zb + 0.005)
          segs = segs.flatMap(([a, b]) => [[a, Math.min(b, o.s0)], [Math.max(a, o.s1), b]]).filter(([a, b]) => b - a > 0.005);
        for (const [a, b] of segs) for (let x = x0; x < b - 0.005; x += BL) {
          const xa = Math.max(x, a), xb = Math.min(x + BL, b); if (xb - xa <= 0.005) continue;
          (xb - xa >= BL - 0.005 && hb >= BH - 0.005 ? full : cut).push([xa, xb, zb, hb]);
        }
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
    // with the change: the new / changed opening is filled red, half transparent (as the removed beam of OC-2) – Avihai 09.11
    if (w.ownerChange && w.variant?.show === 'changed') for (const o of w.openings) {
      const c = p0.clone().addScaledVector(dir, (o.s0 + o.s1) / 2); c.y = (o.z0 + o.z1) / 2;
      const m = new THREE.Mesh(unit, ocM); m.position.copy(c); m.quaternion.copy(q); m.scale.set(o.s1 - o.s0, o.z1 - o.z0, t * 1.02); m.renderOrder = 3; g.add(m);
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(unit), new THREE.LineBasicMaterial({ color: DF.ownerChangeColor })); e.position.copy(c); e.quaternion.copy(q); e.scale.copy(m.scale); g.add(e);
    }
    if (w.ownerChange) {
      g.add(new THREE.BoxHelper(g, DF.ownerChangeColor));
      if (w.variant?.show === 'changed') { const bb = new THREE.Box3().setFromObject(g); g.add(ocTag(w.ownerChange, new THREE.Vector3((bb.min.x + bb.max.x) / 2, bb.max.y + DB.labelLift_m, (bb.min.z + bb.max.z) / 2))); }
    } else if (w.status !== 'source') g.add(new THREE.BoxHelper(g, DF.provisionalEdgeColor));
    const asDrawn = w.variant?.show !== 'changed';
    const tc = Math.round(t * 100);
    if (asDrawn) { stats.full += full.length; stats.cut += cut.length; stats.area_m2 += w.area_m2; }
    if (asDrawn) { const bt = (stats.byThickness[tc] ||= { full: 0, cut: 0, area_m2: 0 }); bt.full += full.length; bt.cut += cut.length; bt.area_m2 += w.area_m2; }
    registry.add(g, { floor: w.floor, system: 'walls', stage: 'walls', layer: 'blockWalls', step: 'blockWalls' }, {
      id: w.id, name: `קיר בלוקים ${tc} ס"מ – ${FLOOR[w.floor] || w.floor}${w.ownerChange ? ` · ${w.ownerChange} ${w.variant?.show === 'changed' ? '(עם השינוי)' : '(לפי התוכניות)'}` : ''}`, status: w.status, ...vmeta(w),
      rows: [['בלוק', `${B.block.type} ${Math.round(BL * 100)}×${Math.round(BH * 100)}, עובי ${tc}`], ['אורך × גובה', `${L.toFixed(2)} × ${(w.topRel - w.bottomRel).toFixed(2)} מ'`],
        ['נדבכים', `${w.courses}`], ['בלוקים', `${full.length} שלמים + ${cut.length} חתוכים`], ['שטח נטו', `${w.area_m2.toFixed(2)} מ"ר`],
        ['פתחים', w.openings.map(o => o.id + (o.shutter ? ' (תריס)' : '')).join(', ') || '—'], ['תחתית / ראש', `${coords.fmtH(coords.H0 + w.bottomRel)} / ${coords.fmtH(coords.H0 + w.topRel)}`]],
      note: [w.note, 'פריסת הנדבכים: חצי בלוק בדילוג בכל נדבך שני; נדבך עליון חתוך לגובה התקרה / הקורה.'].filter(Boolean).join(' '), source: w.source,
    });
    scene.add(g);
    // lintels (doors and windows): lintel block, one course on the head, bearing into the blocks (tools/extract_blocks.py)
    for (const lt of w.lintels || []) {
      const c = p0.clone().addScaledVector(dir, (lt.s0 + lt.s1) / 2); c.y = (lt.z0 + lt.z1) / 2;
      const m = new THREE.Mesh(unit, lintM); m.scale.set(lt.s1 - lt.s0 - DB.joint_m, lt.z1 - lt.z0 - DB.joint_m, t); m.position.copy(c); m.quaternion.copy(q);
      m.castShadow = m.receiveShadow = true;
      const lg = new THREE.Group(); lg.add(m); lg.add(new THREE.BoxHelper(m, DF.provisionalEdgeColor));
      const net = lt.length_m - lt.bearL_m - lt.bearR_m;
      const bear = [...lt.onConcrete.map(x => `${SIDE[x]} – על הבטון`), ...(lt.continues || []).map(x => `${SIDE[x]} – המשך בקטע הסמוך`), ...(lt.intoCrossWall || []).map(x => `${SIDE[x]} – נכנס לקיר הבלוקים הניצב`), ...(lt.pier || []).map(x => `${SIDE[x]} – עד אמצע הפילר בין שני פתחים`), ...(lt.shortBearing || []).map(x => `${SIDE[x]} – בלי הישענות, לבדיקה`)];
      registry.add(lg, { floor: w.floor, system: 'walls', stage: 'walls', layer: 'lintels', step: 'blockWalls' }, {
        ...vmeta(w), id: lt.id, name: `משקוף ${lt.opening} – ${t >= (LT?.thinBelow_m ?? 0) ? LT?.type : LT?.typeThin}`, status: lt.status,
        rows: [['אורך משקוף', `${Math.round(lt.length_m * 100)} ס"מ (פתח ${Math.round(net * 100)} + הישענות ${Math.round(lt.bearL_m * 100)} / ${Math.round(lt.bearR_m * 100)})`],
          ['חתך', `${Math.round(t * 100)} × ${Math.round((lt.z1 - lt.z0) * 100)} ס"מ (עובי הקיר × נדבך)`], ['תחתית', coords.fmtH(coords.H0 + lt.z0)], ['קיר', w.id],
          ['הישענות', bear.join('; ') || `${Math.round((LT?.bearing_m?.value ?? 0) * 100)} ס"מ בכל צד`]],
        note: `בחירת אביחי: בלוק משקוף כמקובל. הישענות ${Math.round((LT?.bearing_m?.value ?? 0) * 100)} ס"מ – ${LT?.bearing_m?.source || ''}. זיון ויציקה לפי פרט יצרן / מהנדס.`, source: w.source,
      });
      scene.add(lg); if (asDrawn) { stats.lintels = (stats.lintels || 0) + 1; stats.lintel_m = (stats.lintel_m || 0) + lt.length_m; }
    }
  }
  // roller-shutter boxes: inside the top of the opening; depth = the host wall (blocks.json depth_m – built-in box, Avihai 08.11)
  for (const b of B.shutterBoxes) {
    const o = data.openings?.openings?.find(x => x.id === b.opening); if (!o || b.box_m == null) continue;
    const w = B.walls.find(x => x.openings.some(y => y.id === b.opening)); const t = b.depth_m ?? (w ? w.thickness_m : display.openings.defaultWallDepth_m);
    const [E, N] = o.centerITM, c = coords.toLocal(E, N, coords.H0 + b.headRel - b.box_m / 2);
    const [x1, z1] = coords.xz(E + o.axisITM[0], N + o.axisITM[1]), dir = new THREE.Vector3(x1 - c.x, 0, z1 - c.z).normalize();
    const m = new THREE.Mesh(unit, b.clash ? clashM : b.variant?.show === 'changed' ? ocM : boxM); m.scale.set(o.width_m, b.box_m, t); m.position.copy(c); m.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), dir);
    m.castShadow = true; const g = new THREE.Group(); g.add(m); g.add(new THREE.BoxHelper(m, b.ownerChange ? DF.ownerChangeColor : DF.provisionalEdgeColor));
    const d = document.createElement('div'); d.className = 'lbl ' + (b.ownerChange ? 'oc-tag' : 'beam'); d.textContent = b.clash ? `התנגשות: ארגז ${b.opening} חודר ${Math.round(b.clash.into_m * 100)} ס"מ ל-B-27 · ${b.ownerChange}` : `ארגז תריס ${b.opening} · ${Math.round(b.box_m * 100)}${b.variant?.show === 'changed' ? ' · ' + b.ownerChange : ''}`;
    const lo = new CSS2DObject(d); lo.position.copy(c).add(new THREE.Vector3(0, b.box_m / 2 + DB.labelLift_m, 0)); g.add(lo);
    registry.add(g, { floor: b.floor, system: 'finishes', stage: 'walls', layer: 'shutterBoxes', step: 'blockWalls' }, {
      id: `SB-${b.opening}${b.variant?.show === 'changed' ? '~' + b.ownerChange : ''}`, name: `ארגז תריס גלילה – ${b.opening}${b.ownerChange ? ` · ${b.ownerChange} ${b.variant?.show === 'changed' ? '(עם השינוי)' : '(לפי התוכניות)'}` : ''}`, status: b.status, ...vmeta(b),
      rows: [['רוחב', `${Math.round(o.width_m * 100)} ס"מ`], ['גובה הארגז', `${Math.round(b.box_m * 100)} ס"מ (בתוך גובה הפתח, מתחת ל-O.K)`], ['עומק', `${Math.round(t * 100)} ס"מ – ארגז מובנה בעובי הקיר ${b.hostWall ?? ''}`]],
      note: [b.clash?.note, `גובה: ${b.status === 'source' ? 'מהתוכניות / הגרמושקה' : 'משוער'}. עומק: ${b.depthSource ?? 'עובי הקיר'}. רוחב: רוחב הפתח.`].filter(Boolean).join(' '), source: b.source,
    });
    scene.add(g); if (b.variant?.show !== 'changed') stats.boxes++;
  }
  // owner-change additions (blocks.json ownerAdditions – e.g. the OC-5 inner step): red, half transparent, 'changed' variant
  for (const a of B.ownerAdditions || []) {
    const shape = new THREE.Shape(a.ringITM.map(([E, N]) => { const p = coords.toLocal(E, N, coords.H0); return new THREE.Vector2(p.x, -p.z); }));
    const geo = new THREE.ExtrudeGeometry(shape, { depth: a.topRel - a.bottomRel, bevelEnabled: false }); geo.rotateX(-Math.PI / 2); geo.translate(0, a.bottomRel, 0);
    const m = new THREE.Mesh(geo, ocM); const g = new THREE.Group(); g.add(m); g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: DF.ownerChangeColor })));
    const bb = new THREE.Box3().setFromObject(m); g.add(ocTag(`${a.change} · מדרגה`, new THREE.Vector3((bb.min.x + bb.max.x) / 2, bb.max.y + DB.labelLift_m, (bb.min.z + bb.max.z) / 2)));
    registry.add(g, { floor: a.floor, system: 'finishes', stage: 'walls', layer: 'blockWalls', step: 'blockWalls' }, {
      id: a.id, name: `${a.kind === 'step' ? 'מדרגה פנימית' : 'תוספת'} – ${a.change} (עם השינוי)`, status: 'provisional', variant: { change: a.change, show: 'changed' },
      rows: [['רוחב', `${a.width_m?.toFixed(2)} מ'`], ['מפלסים', `${coords.fmtH(coords.H0 + a.bottomRel)} → ${coords.fmtH(coords.H0 + a.topRel)}`]], note: a.note, source: a.source,
    });
    scene.add(g);
  }
  return stats;
}

import * as THREE from 'three';
import { makeInterpolator, ringArea } from '../../js/geometry/tin.js';
import { regionMesh } from '../../js/geometry/terrain.js';
import { ENV_TAGS, fatLine, drape } from './common.js';

// Streets around lot 5187 from data/environment/streets.json.
// Inside the buyer-map frame the surface follows the planned street contours (DWG). Outside it the
// sources have no street levels: the area is drawn flat on the neutral reference plane, outlined in
// orange and marked "no height data" (docs/open-issues.md) – no level is invented.
export function buildStreets(ctx, mats) {
  const { data, coords, registry, scene, display, ground } = ctx;
  const S = data.envStreets, D = data.envDisplay;
  const ctrl = S.heightControl.points.map(p => ({ x: p.E, y: p.N, z: p.z }));
  const interp = makeInterpolator(ctrl);
  // outside the buyer-map frame: lot-front levels (heights plan) + the DWG street levels, flagged provisional
  const dCtrl = (S.derivedHeightControl?.points || []).map(p => ({ x: p.E, y: p.N, z: p.z })).concat(ctrl);
  const dInterp = dCtrl.length >= 3 ? makeInterpolator(dCtrl) : null;
  const sec = S.integratedStreet.typicalSection;
  const sectionRows = [
    ['חתך טיפוסי', `${sec.name}: ${sec.zones.map(z => `${z.label} ${z.width_m.toFixed(1)}`).join(' | ')} = ${sec.total_m.toFixed(1)} מ'`],
    ['רוחב מדוד מול 5187', `${S.integratedStreet.widthCheck.measured_m.toFixed(3)} מ' (סטייה ${S.integratedStreet.widthCheck.deviation_m.toFixed(3)})`],
    ['שיפוע רוחבי', sec.crossSlope],
    ['ריצוף', S.integratedStreet.materials.paving],
  ];
  const curbH = data.envDetails?.config?.street?.curbHeight_m ?? 0; // sidewalks sit above the road by the curb height
  const ZMAT = { integrated: 'envStreet', sidewalk: 'envSidewalk', parkingStrip: 'envPlantingStrip', carriageway: 'envAsphalt', street: 'envStreet' };
  const secOf = Object.fromEntries((S.sections || []).map(x => [x.id, x]));
  S.surfaces.forEach((s, i) => {
    const integ = s.zone === 'integrated';
    const sec2 = s.section ? secOf[s.section] : null;
    const nm = `${s.zoneLabel || 'רחוב'} – חלקה ${s.parcel}`;
    const zoneRows = sec2 && !integ ? [['חתך', sec2.name], ['מקור החתך', sec2.source]] : [];
    if (s.heights === 'source' && interp) {
      const mesh = regionMesh(s.ring, interp, coords, mats.get(ZMAT[s.zone] || 'envStreet'), mats.get('envSide'), display.terrain, ctrl);
      if (s.zone === 'sidewalk') mesh.position.y += curbH;
      registry.add(mesh, ENV_TAGS('street'), {
        name: `${nm} (גבהים מהמפה למשתכן)`, kind: 'terrain', role: 'street', parcel: s.parcel, ring: s.ring,
        rows: [['שטח', `${s.area_m2.toFixed(2)} מ"ר`], ['גובה מינ׳/מקס׳', `${coords.fmtH(mesh.userData.hMin)} / ${coords.fmtH(mesh.userData.hMax)}`], ...(integ ? sectionRows : zoneRows)],
        controlCount: interp.count, interp: interp.kind,
        source: `${s.source}; גבהים: ${s.heightSource}`,
      });
      scene.add(mesh);
      ground.add(s.ring, interp, 'env', `env-street-${i}`);
    } else if (s.heights === 'derived' && dInterp) {
      const mesh = regionMesh(s.ring, dInterp, coords, mats.get(ZMAT[s.zone] || 'envStreet'), mats.get('envSide'), display.terrain, dCtrl);
      if (s.zone === 'sidewalk') mesh.position.y += curbH;
      const hAt2 = (E, N) => dInterp(E, N);
      const outline = new THREE.Group();
      outline.add(fatLine(ctx, drape(coords, s.ring.concat([s.ring[0]]), hAt2, 0.03, 0.6), D.missingOutlineColor, 1.4, { dashed: true }));
      registry.add(outline, ENV_TAGS('streetHeightOutline'), { name: `${nm} – גבול אזור עם גובה משוער`, kind: 'lines', pickable: false });
      scene.add(outline);
      const chk = S.derivedHeightControl.check;
      registry.add(mesh, ENV_TAGS('street'), {
        name: `${nm} – גובה משוער`, kind: 'terrain', role: 'street', parcel: s.parcel, ring: s.ring, provisional: true,
        rows: [['שטח', `${s.area_m2.toFixed(2)} מ"ר`], ['גובה מינ׳/מקס׳', `${coords.fmtH(mesh.userData.hMin)} / ${coords.fmtH(mesh.userData.hMax)}`],
          ['שיטת הגובה', 'אינטרפולציה בין גבהי קצות המגרשים משני צידי הרחוב'],
          ['בדיקה מול המפה למשתכן', `ממוצע ${chk.mean_m >= 0 ? '+' : ''}${chk.mean_m.toFixed(2)} מ', ממוצע מוחלט ${chk.meanAbs_m.toFixed(2)} מ' (${chk.points} נק')`],
          ...(integ ? sectionRows : zoneRows)],
        controlCount: dInterp.count, interp: dInterp.kind,
        note: s.note, source: `${s.source}; גבהים: ${s.heightSource}`,
      });
      scene.add(mesh);
      ground.add(s.ring, dInterp, 'env', `env-street-${i}`);
    }
  });

  // (the buyer's-map gutter / islands are built as real elements in details.js – no draped lines here)
  return { interp };
}

import * as THREE from 'three';
import { makeInterpolator, ringArea } from '../../js/geometry/tin.js';
import { regionMesh } from '../../js/geometry/terrain.js';
import { ENV_TAGS, fatLine, label, drape, centroid } from './common.js';

// Neighbouring lots: final ground surface from the lot-corner levels of the heights plan,
// lot outline, building lines (setbacks) and labels. All values from data/environment/lots.json.
export function buildLots(ctx, mats) {
  const { data, coords, registry, scene, display, ground } = ctx;
  const D = data.envDisplay;
  const out = [];
  for (const lot of data.envLots.lots) {
    const ctrl = lot.cornerLevels.map(c => ({ x: c.at[0], y: c.at[1], z: c.z }));
    const interp = makeInterpolator(ctrl);
    if (!interp) { console.warn('lot without levels', lot.parcel); continue; }
    const mesh = regionMesh(lot.ring, interp, coords, mats.get('envLot'), mats.get('envSide'), display.terrain, ctrl);
    const name = `מגרש ${lot.lot} (חלקה ${lot.parcel})`;
    registry.add(mesh, ENV_TAGS('neighborLots'), {
      name: `${name} – פני קרקע סופיים`, kind: 'terrain', role: 'neighbor', parcel: lot.parcel, ring: lot.ring,
      rows: [
        ['שטח מגרש', `${lot.area_m2.toFixed(2)} מ"ר`],
        ['±0.00 (מפלס כניסה קובעת)', lot.pm0.z != null ? coords.fmtH(lot.pm0.z) + (lot.pm0.status === 'suspect' ? ' ⚠ חשוד' : '') : 'חסר'],
        ['גבהי פינות (תוכנית גבהים)', lot.cornerLevels.map(c => c.z.toFixed(2)).join(' · ')],
        ['גובה מינ׳/מקס׳', `${coords.fmtH(mesh.userData.hMin)} / ${coords.fmtH(mesh.userData.hMax)}`],
      ],
      area: Math.abs(ringArea(lot.ring)), hMax: mesh.userData.hMax, interp: interp.kind, controlCount: interp.count,
      note: lot.cornersWithLevel < lot.cornerCount ? `גבהים ל-${lot.cornersWithLevel} מתוך ${lot.cornerCount} פינות; בשאר הפינות אין ערך בתוכנית הגבהים (אינטרפולציה)` : null,
      source: `${lot.ringSource}; גבהים: ${lot.cornerLevels[0]?.source}`,
    });
    scene.add(mesh);
    const gid = `env-lot-${lot.parcel}`;
    ground.add(lot.ring, interp, 'env', gid);
    const hAt = (E, N) => interp(E, N);

    // outline + label
    const g = new THREE.Group();
    g.add(fatLine(ctx, drape(coords, lot.ring.concat([lot.ring[0]]), hAt, D.lineLift_m, 0.4), D.lotOutlineColor, D.lotOutlineWidth_px));
    registry.add(g, ENV_TAGS('neighborLots'), { name: `${name} – גבול`, kind: 'lines', source: lot.ringSource });
    scene.add(g);

    // building lines (envelope footprint draped on the lot)
    const bl = new THREE.Group();
    const er = lot.envelope.ring;
    bl.add(fatLine(ctx, drape(coords, er.concat([er[0]]), hAt, D.lineLift_m, 0.4), D.buildingLineColor, D.buildingLineWidth_px, { dashed: true }));
    registry.add(bl, ENV_TAGS('neighborBuildingLines'), {
      name: `${name} – קווי בניין`, kind: 'lines',
      rows: lot.edges.map(e => [`${e.kind === 'rear' ? 'אחורי' : e.kind === 'side' ? 'צדדי' : 'קדמי'} (מול ${e.across})`, `${e.setback_m.toFixed(2)} מ'`]),
      note: lot.frontStatus === 'assumption' ? `מגרש פינתי – הנחה: ${lot.frontRule}` : null,
      source: lot.envelope.source,
    });
    scene.add(bl);

    // labels: lot number, ±0.00, corner levels
    const lg = new THREE.Group();
    const c = centroid(lot.ring);
    const pm0 = lot.pm0.z != null ? `±0.00=${lot.pm0.z.toFixed(2)}` : '±0.00 חסר';
    lg.add(label(`מגרש ${lot.lot} (ח' ${lot.parcel}) · ${pm0}`, 'lot' + (lot.pm0.status !== 'source' ? ' warn' : ''),
      coords.toLocal(c[0], c[1], hAt(c[0], c[1]) + D.labelLift_m), `${lot.pm0.source}${lot.pm0.note ? '\n' + lot.pm0.note : ''}`));
    for (const cl of lot.cornerLevels) {
      lg.add(label(cl.z.toFixed(2), 'corner', coords.toLocal(cl.at[0], cl.at[1], cl.z + D.labelLift_m * 0.5), cl.source));
    }
    registry.add(lg, ENV_TAGS('neighborLabels'), { name: `${name} – תוויות`, kind: 'labels', pickable: false });
    scene.add(lg);
    out.push({ lot, interp, hMin: mesh.userData.hMin, hMax: mesh.userData.hMax });
  }
  return out;
}

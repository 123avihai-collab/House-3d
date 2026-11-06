import * as THREE from 'three';
import { makeInterpolator, ringArea } from '../../js/geometry/tin.js';
import { regionMesh } from '../../js/geometry/terrain.js';
import { ENV_TAGS, fatLine, label, drape, flatPolygon, centroid } from './common.js';

// Streets around lot 5187 from data/environment/streets.json.
// Inside the buyer-map frame the surface follows the planned street contours (DWG). Outside it the
// sources have no street levels: the area is drawn flat on the neutral reference plane, outlined in
// orange and marked "no height data" (docs/open-issues.md) – no level is invented.
export function buildStreets(ctx, mats) {
  const { data, coords, registry, scene, display, ground } = ctx;
  const S = data.envStreets, D = data.envDisplay;
  const ctrl = S.heightControl.points.map(p => ({ x: p.E, y: p.N, z: p.z }));
  const interp = makeInterpolator(ctrl);
  const sec = S.integratedStreet.typicalSection;
  const isIntegrated = (p) => S.integratedStreet.parcels.includes(p);
  const sectionRows = [
    ['חתך טיפוסי', `${sec.name}: ${sec.zones.map(z => `${z.label} ${z.width_m.toFixed(1)}`).join(' | ')} = ${sec.total_m.toFixed(1)} מ'`],
    ['רוחב מדוד מול 5187', `${S.integratedStreet.widthCheck.measured_m.toFixed(3)} מ' (סטייה ${S.integratedStreet.widthCheck.deviation_m.toFixed(3)})`],
    ['שיפוע רוחבי', sec.crossSlope],
    ['ריצוף', S.integratedStreet.materials.paving],
  ];
  S.surfaces.forEach((s, i) => {
    const integ = isIntegrated(s.parcel);
    const nm = `${integ ? 'רחוב משולב' : 'רחוב'} – חלקה ${s.parcel}`;
    if (s.heights === 'source' && interp) {
      const mesh = regionMesh(s.ring, interp, coords, mats.get('envStreet'), mats.get('envSide'), display.terrain, ctrl);
      registry.add(mesh, ENV_TAGS('street'), {
        name: `${nm} (גבהים מהמפה למשתכן)`, kind: 'terrain', role: 'street', parcel: s.parcel, ring: s.ring,
        rows: [['שטח', `${s.area_m2.toFixed(2)} מ"ר`], ['גובה מינ׳/מקס׳', `${coords.fmtH(mesh.userData.hMin)} / ${coords.fmtH(mesh.userData.hMax)}`], ...(integ ? sectionRows : [])],
        controlCount: interp.count, interp: interp.kind,
        source: `${s.source}; גבהים: ${s.heightSource}`,
      });
      scene.add(mesh);
      ground.add(s.ring, interp, 'env', `env-street-${i}`);
    } else {
      const z = ground.contextZ + D.noDataLift_m;
      const g = new THREE.Group();
      g.add(flatPolygon(coords, s.ring, z, mats.get('envStreetNoData')));
      g.add(fatLine(ctx, s.ring.concat([s.ring[0]]).map(([E, N]) => coords.toLocal(E, N, z + 0.01)), D.missingOutlineColor, 1.6, { dashed: true }));
      if (s.area_m2 > 50) {
        const c = centroid(s.ring);
        g.add(label(`${integ ? 'רחוב משולב' : 'רחוב'} (חלקה ${s.parcel}) · אין גבהים במקור`, 'nodata', coords.toLocal(c[0], c[1], z + 0.4), s.note));
      }
      registry.add(g, ENV_TAGS('street'), {
        name: `${nm} – ללא נתוני גובה`, kind: 'street-nodata', parcel: s.parcel, ring: s.ring,
        rows: [['שטח', `${s.area_m2.toFixed(2)} מ"ר`], ['גובה', `אין במקורות – מוצג על משטח הייחוס (${z.toFixed(2)})`], ...(integ ? sectionRows : [])],
        note: s.note, source: s.source,
      });
      scene.add(g);
    }
  });

  // integrated-street linework from the buyer's map: central gutter, edge stones at the lot lines, planting islands
  const hAt = (E, N) => ground.heightAt(E, N, 'env');
  const lw = new THREE.Group();
  for (const c of S.integratedStreet.gutter) lw.add(fatLine(ctx, drape(coords, c.points, hAt, 0.03), D.gutterColor, 2.4));
  for (const c of S.integratedStreet.edgeStones) lw.add(fatLine(ctx, drape(coords, c.points, hAt, 0.03), D.streetEdgeColor, 1.6));
  for (const c of S.integratedStreet.islands) lw.add(fatLine(ctx, drape(coords, c.points, hAt, 0.03, 0.3), D.islandColor, 2));
  registry.add(lw, ENV_TAGS('street'), {
    name: 'רחוב משולב – תעלת ניקוז מרכזית, אבני גן ואיי שתילה', kind: 'lines',
    rows: [['תעלה', S.integratedStreet.materials.gutter], ['אבן גן בקו המגרש', S.integratedStreet.materials.edgeAtLot]],
    source: `${S.integratedStreet.linesSource}; חומרים: ${S.integratedStreet.materials.source}`,
  });
  scene.add(lw);
  return { interp };
}

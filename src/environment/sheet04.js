import * as THREE from 'three';
import { ENV_TAGS, flatPolygon } from './common.js';

// Neighbours as drawn in the building plan sheet 04 (data/environment/sheet04.json): building, parking
// structure ("מבנה חניה") and main entrance. Building height = the same rule as the envelopes
// (±0.00 + permitted height); parking structure = A_1 §7 maximum internal height (provisional).
export function buildSheet04(ctx, mats, lots) {
  const { data, coords, registry, scene, ground } = ctx;
  const S = data.envSheet04, D = data.envDisplay;
  const P = data.envLots.parking;
  const byParcel = Object.fromEntries(lots.map(x => [x.lot.parcel, x.lot]));
  const items = [];
  const gAt = (E, N) => ground.heightAt(E, N, 'env');
  const minGround = (ring) => Math.min(...ring.map(([E, N]) => gAt(E, N)));
  const prism = (ring, bottom, top, mat) => {
    const shape = new THREE.Shape(ring.map(([E, N]) => new THREE.Vector2(E - coords.E0, N - coords.N0)));
    const geo = new THREE.ExtrudeGeometry(shape, { depth: top - bottom, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2);
    const m = new THREE.Mesh(geo, mat);
    m.position.y = bottom - coords.H0;
    m.castShadow = true; m.receiveShadow = true;
    const g = new THREE.Group(); g.add(m);
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 20), new THREE.LineBasicMaterial({ color: D.envelopeEdgeColor }));
    e.position.copy(m.position); g.add(e);
    return { g, m };
  };
  const georefNote = `גיליון 04 סרוק; גאורפרנס לסמלי ±0.00 – שארית חציונית ${S.georeference.medianResidual_m.toFixed(2)} מ', מקס' ${S.georeference.maxResidual_m.toFixed(2)} מ'`;
  for (const r of S.lots) {
    const lot = byParcel[r.parcel];
    if (!lot) continue; // 5187 itself is not drawn from this sheet
    const name = `מגרש ${lot.lot} (חלקה ${lot.parcel})`;
    const z0 = lot.pm0.z;
    for (const ring of r.building) {
      if (z0 == null) continue;
      const top = z0 + lot.envelope.height_m;
      const mat = mats.get('envBuilding').clone(); mat.depthWrite = false;
      const { g } = prism(ring, Math.min(minGround(ring), z0), top, mat);
      registry.add(g, ENV_TAGS('neighborSheet04'), {
        name: `${name} – בית לפי גיליון 04`, kind: 'building', parcel: lot.parcel, footprint: ring, base: z0, top,
        rows: [
          ['תכסית (מהגיליון)', `${r.buildingArea_m2.toFixed(1)} מ"ר`],
          ['±0.00', coords.fmtH(z0)],
          ['גובה', `${lot.envelope.height_m.toFixed(2)} מ' מעל ±0.00 → ${top.toFixed(2)} (אותו כלל כמו המעטפת)`],
          ['כניסה ראשית מ', r.entranceFrom ? r.entranceFrom.across : '—'],
          ...(r.buildingTo5187_m != null ? [['מרחק מגבול 5187', `${r.buildingTo5187_m.toFixed(2)} מ'`]] : []),
        ],
        note: georefNote, source: `${S.source} (לבן – מבנה); ${lot.envelope.source}`,
      });
      scene.add(g);
      items.push({ group: g, material: mat });
    }
    for (const ring of r.parking) {
      const base = minGround(ring);
      const mat = mats.get('envParking').clone(); mat.depthWrite = false;
      const { g } = prism(ring, base, base + P.height_m, mat);
      registry.add(g, ENV_TAGS('neighborParking'), {
        name: `${name} – מבנה חניה (גיליון 04)`, kind: 'parking', parcel: lot.parcel, footprint: ring, base, height: P.height_m, provisional: true,
        rows: [['שטח', `${r.parkingArea_m2.toFixed(1)} מ"ר (תמל/1016: עד 30 מ"ר)`], ['גובה', `${P.height_m.toFixed(2)} מ' – גובה פנימי מרבי (A_1 §7)`]],
        note: `זמני: ${P.why}. ${georefNote}`, source: `${S.source} (סגול – "מבנה חניה"); ${P.source}`,
      });
      scene.add(g);
      items.push({ group: g, material: mat });
    }
    for (const ring of r.entrance) {
      const h = Math.max(...ring.map(([E, N]) => gAt(E, N))) + D.lineLift_m;
      const g = new THREE.Group(); g.add(flatPolygon(coords, ring, h, mats.get('envEntrance')));
      registry.add(g, ENV_TAGS('neighborEntrances'), {
        name: `${name} – כניסה ראשית (גיליון 04)`, kind: 'entrance', parcel: lot.parcel, footprint: ring,
        note: georefNote, source: `${S.source} (כתום משובץ – "כניסה ראשית")`,
      });
      scene.add(g);
    }
  }
  return items;
}

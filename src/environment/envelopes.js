import * as THREE from 'three';
import { ENV_TAGS } from './common.js';

// Maximum building envelope of every neighbouring lot (TAMAL/1016): footprint = lot minus setbacks,
// from the lot ground up to ±0.00 + permitted height. Plain neutral volume (not a house design).
export function buildEnvelopes(ctx, mats, lots) {
  const { data, coords, registry, scene } = ctx;
  const D = data.envDisplay;
  const items = [];
  for (const { lot, hMin } of lots) {
    const e = lot.envelope;
    if (!e.build) continue;
    const top = e.base + e.height_m;
    const bottom = Math.min(hMin, e.base);
    const shape = new THREE.Shape(e.ring.map(([E, N]) => new THREE.Vector2(E - coords.E0, N - coords.N0)));
    const geo = new THREE.ExtrudeGeometry(shape, { depth: top - bottom, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2); // shape (E, N) -> scene (x, z = -N); extrusion -> +y
    const mat = mats.get('envEnvelope').clone();
    mat.depthWrite = false;
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.y = bottom - coords.H0;
    mesh.castShadow = true; mesh.receiveShadow = true;
    mesh.renderOrder = 3;
    const g = new THREE.Group(); g.add(mesh);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 20), new THREE.LineBasicMaterial({ color: D.envelopeEdgeColor }));
    edges.position.copy(mesh.position);
    g.add(edges);
    // ±0.00 line around the envelope
    const zl = e.ring.concat([e.ring[0]]).map(([E, N]) => coords.toLocal(E, N, e.base));
    g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(zl), new THREE.LineBasicMaterial({ color: D.envelopeZeroLineColor })));
    registry.add(g, ENV_TAGS('neighborEnvelopes'), {
      name: `מעטפת מקסימלית – מגרש ${lot.lot} (חלקה ${lot.parcel})`, kind: 'envelope', parcel: lot.parcel,
      footprint: e.ring, area: e.area_m2, height: e.height_m, base: e.base, top,
      rows: [
        ['תכסית מעטפת', `${e.area_m2.toFixed(2)} מ"ר (מגרש ${lot.area_m2.toFixed(2)} מ"ר)`],
        ['±0.00 (מפלס כניסה קובעת)', coords.fmtH(e.base)],
        ['גובה מותר', `${e.height_m.toFixed(2)} מ' מעל ±0.00 → ${top.toFixed(2)} · ${e.floors} קומות`],
        ['קווי בניין', lot.edges.map(x => `${x.kind === 'rear' ? 'אחורי' : x.kind === 'side' ? 'צדדי' : 'קדמי'} ${x.setback_m} מול ${x.across}`).join(' · ')],
      ],
      note: lot.frontStatus === 'assumption' ? `מגרש פינתי – הנחה: ${lot.frontRule}` : null,
      source: e.source,
    });
    scene.add(g);
    items.push({ group: g, material: mat });
  }
  return items;
}

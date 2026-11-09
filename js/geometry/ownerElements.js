import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Elements Avihai asked to build from the architectural plans although the structural sheets do not show them
// (owner-changes-geometry.json changes[id].elements – e.g. OC-12 laundry-screen fins, OC-13 walkway balcony): red, half
// transparent, with an "OC-n · לבדיקה" tag; variant 'original' = shown while the switch is "לפי התוכניות", hidden "עם השינוי".
// No dimensions here – rings and levels come from the data.
export function buildOwnerElements(ctx) {
  const { data, coords, registry, scene, display } = ctx;
  const D = display.framing;
  const mat = new THREE.MeshStandardMaterial({ color: D.ownerChangeColor, roughness: 0.6, transparent: true, opacity: 0.7, depthWrite: false });
  const byId = Object.fromEntries((data.ownerChanges?.changes || []).map(c => [c.id, c]));
  for (const [id, g] of Object.entries(data.ownerChangesGeometry?.changes || {})) for (const e of g.elements || []) {
    const shape = new THREE.Shape(e.ringITM.map(([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); }));
    const geo = new THREE.ExtrudeGeometry(shape, { depth: e.topRel - e.bottomRel, bevelEnabled: false }); geo.rotateX(-Math.PI / 2); geo.translate(0, e.bottomRel, 0);
    const m = new THREE.Mesh(geo, mat); m.castShadow = true; m.renderOrder = 3;
    const grp = new THREE.Group(); grp.add(m, new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: D.ownerChangeColor })));
    const c = e.ringITM.reduce((a, p) => [a[0] + p[0] / e.ringITM.length, a[1] + p[1] / e.ringITM.length], [0, 0]);
    const d = document.createElement('div'); d.className = 'lbl oc-tag'; d.textContent = `${id} · ${e.label} · לבדיקה`;
    const lo = new CSS2DObject(d); lo.position.copy(coords.toLocal(c[0], c[1], coords.H0 + e.topRel + 0.25)); grp.add(lo);
    const oc = byId[id] || {};
    registry.add(grp, { floor: 'ground', system: 'structure', stage: 'slab', step: oc.showStep || 'groundSlab', layer: 'ownerChanges' }, {
      id: e.id, name: `${e.label} – ${id} (לבדיקה של אביחי)`, kind: 'ownerElement', status: 'owner-change', variant: { change: id, show: g.show || 'original' },
      rows: [['מפלסים', `${coords.fmtH(coords.H0 + e.bottomRel)} – ${coords.fmtH(coords.H0 + e.topRel)}`], ['עובי / חתך', `${e.thickness_m ?? '—'} מ'`], ...(e.area_m2 ? [['שטח', `${e.area_m2} מ"ר`]] : [])],
      note: oc.description, source: e.source,
    });
    scene.add(grp);
  }
}

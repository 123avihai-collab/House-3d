import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { centroid } from './site.js';

// Neighbour maximum envelopes (TAMAL/1016) extruded from data/site/neighbors.json.
// Height and entrance level are provisional (flagged in data and drawn with an orange edge).
export function buildNeighbors(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const nd = display.neighbors;
  for (const lot of data.neighbors.lots) {
    if (!lot.footprint?.length || lot.entranceLevel == null) continue;
    const shape = new THREE.Shape(lot.footprint.map(([E, N]) => new THREE.Vector2(E - coords.E0, N - coords.N0)));
    const geo = new THREE.ExtrudeGeometry(shape, { depth: lot.height_m, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2); // shape XY (E,N) -> scene XZ with z = -N, extrusion -> +Y
    const mat = materials.get('envelope').clone();
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.y = lot.entranceLevel - coords.H0;
    mesh.castShadow = true; mesh.receiveShadow = true;
    const g = new THREE.Group(); g.add(mesh);
    const provisional = lot.heightStatus === 'provisional' || lot.entranceLevelStatus === 'provisional';
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 20),
      new THREE.LineBasicMaterial({ color: provisional ? nd.provisionalEdgeColor : '#5d4037' }));
    edges.position.copy(mesh.position);
    g.add(edges);
    // floor division line (2 floors): drawn only as a visual hint at mid-height
    const c = centroid(lot.footprint);
    const div = document.createElement('div');
    div.className = 'lbl envelope' + (provisional ? ' provisional' : '');
    div.textContent = `מעטפת מקס' · חלקה ${lot.parcel} · ${lot.floors} קומות`;
    div.title = `תכסית ${lot.footprintArea_m2} מ"ר · גובה ${lot.height_m} מ' (${lot.heightStatus}) · מפלס כניסה ${lot.entranceLevel} (${lot.entranceLevelStatus})`;
    const lbl = new CSS2DObject(div);
    lbl.position.copy(coords.toLocal(c[0], c[1], lot.entranceLevel + lot.height_m + 0.6));
    g.add(lbl);
    registry.add(g, { floor: 'site', system: 'environment', stage: 'existing', layer: 'neighborEnvelopes' }, {
      name: `מעטפת מקסימלית – חלקה ${lot.parcel}`, kind: 'envelope', parcel: lot.parcel,
      footprint: lot.footprint, area: lot.footprintArea_m2, height: lot.height_m, base: lot.entranceLevel,
      edgeKinds: lot.edgeKinds, provisional,
      note: provisional ? 'גובה המעטפת ומפלס הכניסה זמניים – ממתינים לאישור (docs/open-issues.md)' : null,
      source: data.neighbors.rules.source,
    });
    scene.add(g);
  }
}

import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// Lighter scene, same picture (Avihai 08.11: "lower the model's weight without lowering the quality"): inside every
// registry item the small meshes / edge lines that share a material are merged into ONE mesh / line object (the
// geometry is baked into the item's frame first). Visibility, variants, picking and the info panel work per item, so
// nothing changes for the viewer – but the scene drops from ~18 000 objects / ~4 800 draw calls to a few hundred.
// Instanced meshes, labels, multi-material meshes and objects marked userData.keep are left alone.
// materials that look the same (many modules make one material per part): same key -> mergeable, first one is kept
const keys = new WeakMap();
function matKey(m) {
  if (keys.has(m)) return keys.get(m);
  const c = (x) => (x?.isColor ? x.getHexString() : '');
  const k = [m.type, c(m.color), c(m.emissive), m.emissiveIntensity, m.roughness, m.metalness, m.opacity, m.transparent, m.side, m.depthWrite, m.depthTest,
    m.vertexColors, m.wireframe, m.linewidth, m.dashSize, m.gapSize, m.map?.uuid, m.normalMap?.uuid, m.roughnessMap?.uuid, m.aoMap?.uuid, m.metalnessMap?.uuid,
    m.envMapIntensity, m.polygonOffset, m.polygonOffsetFactor, m.polygonOffsetUnits, m.name, m.clippingPlanes ? 'clip' : '', Object.keys(m.userData || {}).length ? m.uuid : ''].join(',');
  keys.set(m, k); return k;
}

export function compactRegistry(registry, scene) {
  scene.updateMatrixWorld(true);
  const inv = new THREE.Matrix4(), rel = new THREE.Matrix4();
  let before = 0, after = 0;
  for (const it of registry.items) {
    const root = it.object;
    const groups = new Map();
    root.traverse((o) => {
      if (o === root || o.userData.keep) return;
      const kind = o.isInstancedMesh || o.isSkinnedMesh ? null : o.isMesh ? 'mesh' : o.isLineSegments ? 'lines' : null;
      if (!kind || Array.isArray(o.material) || !o.geometry?.attributes?.position) return;
      // (draw groups of a single-material geometry – e.g. a cylinder's side + caps – don't matter: merged as one)
      if (o.geometry.morphAttributes && Object.keys(o.geometry.morphAttributes).length) return;
      // only parts whose whole chain up to the item root is visible (a part hidden on purpose stays separate)
      for (let p = o; p && p !== root; p = p.parent) if (!p.visible) return;
      const g = o.geometry;
      const sig = [kind, matKey(o.material), o.castShadow, o.receiveShadow, o.renderOrder, o.frustumCulled, !!g.index, Object.keys(g.attributes).sort().join(',')].join('|');
      (groups.get(sig) || groups.set(sig, []).get(sig)).push(o);
    });
    inv.copy(root.matrixWorld).invert();
    for (const list of groups.values()) {
      before += list.length;
      if (list.length < 2) { after += 1; continue; }
      const geos = list.map((o) => { const g = o.geometry.clone(); g.clearGroups(); rel.multiplyMatrices(inv, o.matrixWorld); g.applyMatrix4(rel); return g; });
      const merged = mergeGeometries(geos, false);
      geos.forEach((g) => g.dispose());
      if (!merged) { after += list.length; continue; }
      const f = list[0];
      const m = f.isMesh ? new THREE.Mesh(merged, f.material) : new THREE.LineSegments(merged, f.material);
      m.castShadow = f.castShadow; m.receiveShadow = f.receiveShadow; m.renderOrder = f.renderOrder; m.frustumCulled = f.frustumCulled;
      m.userData = { ...f.userData, component: it, merged: list.length };
      for (const o of list) { o.parent.remove(o); o.geometry.dispose(); }
      root.add(m); after += 1;
    }
  }
  // empty groups left behind after their meshes moved
  for (const it of registry.items) {
    const dead = []; it.object.traverse((o) => { if (o !== it.object && o.isGroup && !o.children.length) dead.push(o); });
    dead.forEach((o) => o.parent?.remove(o));
  }
  scene.updateMatrixWorld(true);
  return { before, after };
}

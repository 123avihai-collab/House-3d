// Low-poly but natural-looking trees and shrubs (illustration). Pure geometry: no dimensions here –
// height/crown come from data/environment/details.json. Deterministic per position (no Math.random).
// Returns { wood: BufferGeometry[], leaves: BufferGeometry[] } with vertex colours on the leaves.
import * as THREE from 'three';

const SPECIES = {
  broad: { leaf: ['#4f7a35', '#6b8f3e', '#3f6a2c'], clusters: 9, trunkFrac: 0.45, spread: 1.0, flat: 0.72, branches: 4 },
  olive: { leaf: ['#7d8a62', '#94a07a', '#68764f'], clusters: 8, trunkFrac: 0.38, spread: 1.15, flat: 0.62, branches: 3 },
  cypress: { leaf: ['#2f4f2a', '#3c5f32', '#284325'], clusters: 7, trunkFrac: 0.12, spread: 0.32, flat: 2.6, branches: 0 },
  shrub: { leaf: ['#4d6e34', '#5f7f3a', '#6e8a45'], clusters: 3, trunkFrac: 0, spread: 1.0, flat: 0.75, branches: 0 },
};

function rng(seed) { let s = Math.abs(Math.sin(seed) * 43758.5453) % 1; return () => (s = (s * 9301 + 0.49297) % 1); }

function blob(r, detail, R, col) {
  const g = new THREE.IcosahedronGeometry(r, detail);
  const p = g.attributes.position, c = [];
  const base = new THREE.Color(col[0]), alt = [new THREE.Color(col[1]), new THREE.Color(col[2])];
  for (let i = 0; i < p.count; i++) {
    const v = new THREE.Vector3().fromBufferAttribute(p, i);
    const n = 0.78 + 0.32 * R(); v.multiplyScalar(n); p.setXYZ(i, v.x, v.y, v.z);
    const k = base.clone().lerp(alt[i % 2], R() * 0.8).multiplyScalar(0.85 + 0.25 * Math.max(0, v.y / r));
    c.push(k.r, k.g, k.b);
  }
  g.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
  g.computeVertexNormals();
  return g;
}

export function treeGeometry(x, y, z, height, crown, species = 'broad') {
  const S = SPECIES[species] || SPECIES.broad, R = rng(x * 12.9898 + z * 78.233);
  const wood = [], leaves = [];
  const r = crown / 2, th = height * S.trunkFrac, lean = (R() - 0.5) * 0.15;
  if (S.trunkFrac > 0) {
    const tr = new THREE.CylinderGeometry(0.08 + height * 0.012, 0.12 + height * 0.02, th, 7);
    tr.rotateZ(lean); tr.translate(x + Math.sin(lean) * th / 2, y + th / 2, z); wood.push(tr);
  }
  const top = new THREE.Vector3(x + Math.sin(lean) * th, y + th, z);
  for (let b = 0; b < S.branches; b++) { // a few branches into the crown
    const a = (b / S.branches) * Math.PI * 2 + R(), L = r * (0.6 + 0.3 * R());
    const br = new THREE.CylinderGeometry(0.03 + height * 0.004, 0.06 + height * 0.007, L, 5);
    br.translate(0, L / 2, 0); br.rotateZ(-0.75); br.rotateY(a); br.translate(top.x, top.y - 0.1, top.z); wood.push(br);
  }
  const cy = y + th + (height - th) * (species === 'cypress' ? 0.45 : 0.42);
  for (let k = 0; k < S.clusters; k++) {
    const a = R() * Math.PI * 2, d = r * S.spread * (k === 0 ? 0 : 0.35 + 0.35 * R());
    const rr = r * (k === 0 ? 0.62 : 0.38 + 0.18 * R());
    const g = blob(rr, 1, R, S.leaf);
    g.scale(1, S.flat, 1);
    const h = species === 'cypress' ? (k / S.clusters - 0.4) * (height - th) * 0.9 : (R() - 0.3) * r * 0.5;
    g.translate(x + Math.cos(a) * d, cy + h, z + Math.sin(a) * d);
    leaves.push(g);
  }
  return { wood, leaves };
}

export function shrubGeometry(x, y, z, r) {
  const R = rng(x * 3.17 + z * 7.31), S = SPECIES.shrub, leaves = [];
  for (let k = 0; k < S.clusters; k++) {
    const a = R() * Math.PI * 2, d = r * 0.4 * R();
    const g = blob(r * (0.6 + 0.3 * R()), 1, R, S.leaf); g.scale(1, S.flat, 1);
    g.translate(x + Math.cos(a) * d, y + r * 0.55, z + Math.sin(a) * d); leaves.push(g);
  }
  return { wood: [], leaves };
}

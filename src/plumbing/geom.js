import * as THREE from 'three';

// Low-level solids for the plumbing layer: straight pipe, moulded bend/fitting body, socket + seal, rings.
// Every size comes from data/plumbing/catalog.json (pipes, fittings) or from the network (positions, levels).
const UP = new THREE.Vector3(0, 1, 0);

export function cylBetween(a, b, r, mat, seg = 18, open = false) {
  const d = b.clone().sub(a), L = d.length();
  if (L < 1e-4) return null;
  const g = new THREE.CylinderGeometry(r, r, L, seg, 1, open);
  const m = new THREE.Mesh(g, mat);
  m.position.copy(a).addScaledVector(d, 0.5);
  m.quaternion.setFromUnitVectors(UP, d.normalize());
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

// pipe ring (socket collar, electrofusion sleeve, compression nut …) centred on p, axis dir
export function collar(p, dir, r, len, mat, seg = 18) {
  const g = new THREE.CylinderGeometry(r, r, len, seg);
  const m = new THREE.Mesh(g, mat);
  m.position.copy(p); m.quaternion.setFromUnitVectors(UP, dir.clone().normalize());
  m.castShadow = true;
  return m;
}

export function hexNut(p, dir, acrossFlats, len, mat) {
  const r = acrossFlats / Math.sqrt(3);
  const g = new THREE.CylinderGeometry(r, r, len, 6);
  const m = new THREE.Mesh(g, mat);
  m.position.copy(p); m.quaternion.setFromUnitVectors(UP, dir.clone().normalize());
  m.castShadow = true;
  return m;
}

// rubber seal: thin torus at a socket mouth / chamber connector
export function seal(p, dir, rMajor, rTube, mat) {
  const g = new THREE.TorusGeometry(rMajor, rTube, 8, 28);
  const m = new THREE.Mesh(g, mat);
  m.position.copy(p);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), dir.clone().normalize());
  return m;
}

// moulded bend between two straight legs meeting at vertex v (d1 incoming, d2 outgoing, unit vectors)
export function bend(v, d1, d2, t, r, mat, segs = 10) {
  const a = v.clone().addScaledVector(d1, -t), b = v.clone().addScaledVector(d2, t);
  const curve = new THREE.QuadraticBezierCurve3(a, v.clone(), b);
  const g = new THREE.TubeGeometry(curve, segs, r, 18, false);
  const m = new THREE.Mesh(g, mat); m.castShadow = true;
  return { mesh: m, a, b };
}

export function sphere(p, r, mat, seg = 16) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, seg, Math.max(8, seg / 2)), mat);
  m.position.copy(p); m.castShadow = true;
  return m;
}

export function box(p, sx, sy, sz, mat, yaw = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), mat);
  m.position.copy(p); m.rotation.y = yaw; m.castShadow = true; m.receiveShadow = true;
  return m;
}

// open ring (precast chamber ring / adjustment ring) with a cut-away sector so the inside is visible
export function ring(center, rIn, rOut, h, mat, cut = 0.25, seg = 40) {
  const theta = Math.PI * 2 * (1 - cut);
  const shape = new THREE.Shape();
  shape.absarc(0, 0, rOut, 0, theta, false);
  shape.absarc(0, 0, rIn, theta, 0, true);
  const g = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false, curveSegments: seg });
  g.rotateX(-Math.PI / 2);
  const uv = g.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i), uv.getY(i));
  const m = new THREE.Mesh(g, mat); m.position.copy(center); m.castShadow = true; m.receiveShadow = true;
  return m;
}

export function disk(center, r, h, mat, seg = 32, rIn = 0) {
  if (rIn > 0) return ring(center, rIn, r, h, mat, 0, seg);
  const g = new THREE.CylinderGeometry(r, r, h, seg); g.translate(0, h / 2, 0);
  const m = new THREE.Mesh(g, mat); m.position.copy(center); m.castShadow = true; m.receiveShadow = true;
  return m;
}

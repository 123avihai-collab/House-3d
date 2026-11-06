import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Shared helpers for the environment builders. No dimensions here.
export const ENV_TAGS = (layer) => ({ floor: 'site', system: 'environment', stage: 'existing', layer });

export function fatLine(ctx, pts, color, width, opts = {}) {
  const g = new LineGeometry();
  g.setPositions(pts.flatMap(v => [v.x, v.y, v.z]));
  const m = new LineMaterial({ color, linewidth: width, dashed: !!opts.dashed, dashSize: opts.dashSize ?? 0.6, gapSize: opts.gapSize ?? 0.35, transparent: true, opacity: opts.opacity ?? 1 });
  m.resolution.copy(ctx.viewer.resolution);
  ctx.lineMats.push(m);
  const l = new Line2(g, m);
  l.computeLineDistances();
  l.renderOrder = 5;
  return l;
}

export function label(text, cls, pos, title) {
  const div = document.createElement('div');
  div.className = `lbl env ${cls}`;
  div.textContent = text;
  if (title) div.title = title;
  const o = new CSS2DObject(div);
  o.position.copy(pos);
  return o;
}

// Points along a polyline [[E,N],...] every `step` metres, lifted to heights from hFn(E, N).
export function drape(coords, pts, hFn, lift, step = 0.5) {
  const out = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
    const n = Math.max(1, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / step));
    for (let k = 0; k < n; k++) {
      const x = x1 + (x2 - x1) * k / n, y = y1 + (y2 - y1) * k / n;
      out.push(coords.toLocal(x, y, hFn(x, y) + lift));
    }
  }
  const [x, y] = pts[pts.length - 1];
  out.push(coords.toLocal(x, y, hFn(x, y) + lift));
  return out;
}

export function centroid(ring) {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length];
    const f = x1 * y2 - x2 * y1; a += f; cx += (x1 + x2) * f; cy += (y1 + y2) * f;
  }
  a /= 2; return [cx / (6 * a), cy / (6 * a)];
}

// Flat polygon at absolute height H (ITM ring -> scene), UVs in metres.
export function flatPolygon(coords, ring, H, material) {
  const shape = new THREE.Shape(ring.map(([E, N]) => new THREE.Vector2(E - coords.E0, N - coords.N0)));
  const g = new THREE.ShapeGeometry(shape);
  g.rotateX(-Math.PI / 2); // (E, N) -> scene (x, z = -N)
  const uv = g.attributes.uv, ps = g.attributes.position;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, ps.getX(i), -ps.getZ(i));
  const m = new THREE.Mesh(g, material);
  m.position.y = H - coords.H0;
  m.receiveShadow = true;
  return m;
}

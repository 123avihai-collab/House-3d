import Delaunator from '../../vendor/delaunator/index.js';

// Height interpolator over control points {x, y, z} (x=E, y=N, z=H).
// >=3 non-collinear points: linear TIN inside the convex hull; outside the hull the value is taken
// from the nearest hull edge (linear along that edge) so the surface stays continuous.
// 2 points: linear along the line through them (clamped); 1 point: constant.
export function makeInterpolator(points) {
  const pts = dedupe(points);
  if (pts.length === 0) return null;
  if (pts.length === 1) return Object.assign(() => pts[0].z, { kind: 'constant', count: 1 });
  if (pts.length === 2 || collinear(pts)) {
    const a = pts[0], b = pts[pts.length - 1];
    return Object.assign((x, y) => segValue(a, b, x, y), { kind: 'linear', count: pts.length });
  }
  const d = Delaunator.from(pts, p => p.x, p => p.y);
  const T = d.triangles;
  const hull = d.hull;
  const f = (x, y) => {
    for (let i = 0; i < T.length; i += 3) {
      const a = pts[T[i]], b = pts[T[i + 1]], c = pts[T[i + 2]];
      const w = bary(a, b, c, x, y);
      if (w && w[0] >= -1e-9 && w[1] >= -1e-9 && w[2] >= -1e-9) return w[0] * a.z + w[1] * b.z + w[2] * c.z;
    }
    let best = Infinity, val = pts[0].z;
    for (let i = 0; i < hull.length; i++) {
      const a = pts[hull[i]], b = pts[hull[(i + 1) % hull.length]];
      const { t, dist } = projSeg(a, b, x, y);
      if (dist < best) { best = dist; val = a.z + (b.z - a.z) * t; }
    }
    return val;
  };
  return Object.assign(f, { kind: 'tin', count: pts.length });
}

function dedupe(points) {
  const seen = new Map();
  for (const p of points) {
    const k = `${p.x.toFixed(3)},${p.y.toFixed(3)}`;
    if (!seen.has(k)) seen.set(k, p);
  }
  return [...seen.values()];
}
function collinear(pts) {
  const a = pts[0];
  let b = null;
  for (const p of pts) if (Math.hypot(p.x - a.x, p.y - a.y) > 1e-6) { b = p; break; }
  if (!b) return true;
  return pts.every(p => Math.abs((b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)) < 1e-6 * Math.hypot(b.x - a.x, b.y - a.y) * 10);
}
function bary(a, b, c, x, y) {
  const det = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y);
  if (Math.abs(det) < 1e-12) return null;
  const l1 = ((b.y - c.y) * (x - c.x) + (c.x - b.x) * (y - c.y)) / det;
  const l2 = ((c.y - a.y) * (x - c.x) + (a.x - c.x) * (y - c.y)) / det;
  return [l1, l2, 1 - l1 - l2];
}
function projSeg(a, b, x, y) {
  const dx = b.x - a.x, dy = b.y - a.y, L2 = dx * dx + dy * dy || 1e-12;
  const t = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / L2));
  return { t, dist: Math.hypot(a.x + t * dx - x, a.y + t * dy - y) };
}
function segValue(a, b, x, y) { const { t } = projSeg(a, b, x, y); return a.z + (b.z - a.z) * t; }

// ---------- polygon helpers (ITM rings [[E,N],...]) ----------
export function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
export function ringArea(ring) {
  let a = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length];
    a += x1 * y2 - x2 * y1;
  }
  return a / 2;
}
export function distToRing(x, y, ring) {
  let best = Infinity;
  for (let i = 0; i < ring.length; i++) {
    const a = { x: ring[i][0], y: ring[i][1] }, b = { x: ring[(i + 1) % ring.length][0], y: ring[(i + 1) % ring.length][1] };
    best = Math.min(best, projSeg(a, b, x, y).dist);
  }
  return best;
}
export function nearestOnRing(x, y, ring) {
  let best = { dist: Infinity, x, y };
  for (let i = 0; i < ring.length; i++) {
    const [ax, ay] = ring[i], [bx, by] = ring[(i + 1) % ring.length];
    const r = nearestOnSegment(ax, ay, bx, by, x, y);
    if (r.dist < best.dist) best = r;
  }
  return best;
}
export function distToPolyline(x, y, line) {
  let best = Infinity;
  for (let i = 1; i < line.length; i++) {
    const a = { x: line[i - 1][0], y: line[i - 1][1] }, b = { x: line[i][0], y: line[i][1] };
    best = Math.min(best, projSeg(a, b, x, y).dist);
  }
  return best;
}
export function densifyRing(ring, step) {
  const out = [];
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length];
    const n = Math.max(1, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / step));
    for (let k = 0; k < n; k++) out.push([x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n]);
  }
  return out;
}
export function nearestOnSegment(ax, ay, bx, by, x, y) {
  const r = projSeg({ x: ax, y: ay }, { x: bx, y: by }, x, y);
  return { x: ax + (bx - ax) * r.t, y: ay + (by - ay) * r.t, dist: r.dist, t: r.t };
}
export { Delaunator };

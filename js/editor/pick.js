// Snap (grid / structure vertices & edges / pipe vertices / points) and hit-testing of pipes and points.

function nearestOnSeg(px, py, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
  const t = L2 ? Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / L2)) : 0;
  return [a[0] + t * dx, a[1] + t * dy];
}

// all in local metres; r = search radius in metres
export function snapPoint(x, y, r, opt, F, items, nodes, on) {
  // score = distance + penalty: edges and the DXF background lose to model points (structure JSON, pipes, nodes) nearby
  let best = null; const take = (kind, q, ref, pen = 0) => { const d = Math.hypot(q[0] - x, q[1] - y); if (d > r) return; const sc = d + pen + (kind === 'edge' ? r * 0.3 : 0); if (!best || sc < best.sc) best = { kind, x: q[0], y: q[1], d, sc, ref }; };
  for (const n of nodes) take('node', n.xy, n);
  for (const it of items) for (const q of it.p.pts) take('vertex', q, it.p);
  for (const [k, list] of Object.entries(F.structure)) {
    if (!on('st.' + k)) continue;
    for (const e of list) { const P = e.poly; for (let i = 0; i < P.length; i++) { take('vertex', P[i], e); const b = P[(i + 1) % P.length]; if (e.line && i === P.length - 1) break; take('edge', nearestOnSeg(x, y, P[i], b), e); } }
  }
  const bgPen = r * 0.5;
  if (on('bg.walls')) for (const P of F.background.walls) for (let i = 0; i < P.length; i++) { take('vertex', P[i], null, bgPen); if (i + 1 < P.length) take('edge', nearestOnSeg(x, y, P[i], P[i + 1]), null, bgPen); }
  if (best) return best;
  if (opt.step) return { kind: 'grid', x: Math.round(x / opt.step) * opt.step, y: Math.round(y / opt.step) * opt.step, d: 0 };
  return { kind: 'free', x, y, d: 0 };
}

export function hitTest(x, y, r, items, nodes, locked) {
  let best = null;
  for (const n of nodes) { if (locked('nodes')) break; const d = Math.hypot(n.xy[0] - x, n.xy[1] - y); if (d <= r * 1.2 && (!best || d < best.d)) best = { d, obj: n, type: 'node' }; }
  if (best) return best;
  for (const it of items) {
    const p = it.p; if (locked(p.layer + '.' + p.system)) continue;
    const bias = p.layer === 'cons' ? r * 0.35 : 0;   // proposal wins over the consultant line under it
    if (it.mode === 'plan') for (let i = 0; i + 1 < p.pts.length; i++) { const q = nearestOnSeg(x, y, p.pts[i], p.pts[i + 1]); const d = Math.hypot(q[0] - x, q[1] - y) + bias; if (d <= r + bias && (!best || d < best.d)) best = { d, obj: p, type: 'pipe' }; }
    for (const v of p.verticals) { const d = Math.hypot(v.xy[0] - x, v.xy[1] - y) + bias; if (d <= r + bias && (!best || d < best.d)) best = { d, obj: p, type: 'pipe' }; }
  }
  return best;
}

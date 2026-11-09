// Route editing operations (pure: take a run, return a new run). A run's plan is a list of STATIONS – consecutive
// vertices at the same plan position (a vertical piece) form one station, so moving a station moves the whole riser.
// Geometry is worked in the house frame (local x / y, metres); H of each vertex is kept unless an op sets it.
const r3 = (v) => Math.round(v * 1000) / 1000;

export function stations(run, fr, tol) {
  const S = [];
  run.vertices.forEach((v, i) => {
    const xy = fr.toLocal(v[0], v[1]), last = S[S.length - 1];
    if (last && Math.hypot(xy[0] - last.x, xy[1] - last.y) < tol) last.H.push(v[2]);
    else S.push({ x: xy[0], y: xy[1], H: [v[2]] });
  });
  return S;
}

export function fromStations(run, S, fr) {
  const vertices = [];
  for (const s of S) { const [E, N] = fr.toITM(s.x, s.y); for (const h of s.H) vertices.push([r3(E), r3(N), h == null ? null : r3(h)]); }
  return { ...run, vertices };
}

const axisOf = (a, b, epsDeg) => {   // 'x' | 'y' | null (not axis aligned)
  const dx = b.x - a.x, dy = b.y - a.y, L = Math.hypot(dx, dy); if (L < 1e-9) return null;
  const ang = Math.atan2(Math.abs(dy), Math.abs(dx)) * 180 / Math.PI;
  return ang <= epsDeg ? 'x' : ang >= 90 - epsDeg ? 'y' : null;
};
const lerpH = (a, b, t) => (a == null || b == null) ? (a ?? b) : a + (b - a) * t;

// drag segment s→s+1 by (dx, dy): it moves parallel to itself (only the component normal to it); neighbours stretch.
// An end of the run never leaves its point: a short connector is inserted there instead.
export function dragSegment(S, s, dx, dy, opt) {
  const a = S[s], b = S[s + 1]; let nx = -(b.y - a.y), ny = b.x - a.x; const L = Math.hypot(nx, ny); if (L < 1e-9) return S;
  const ax = opt.ortho ? axisOf(a, b, opt.axisEps_deg) : null;
  if (ax === 'x') { nx = 0; ny = 1; } else if (ax === 'y') { nx = 1; ny = 0; } else { nx /= L; ny /= L; }
  const d = dx * nx + dy * ny, mx = d * nx, my = d * ny;
  const T = S.map(q => ({ ...q, H: [...q.H] }));
  const moved = (q) => ({ ...q, x: q.x + mx, y: q.y + my });
  const out = T.slice(0, s);
  if (s === 0) { const a0 = T[0]; out.push(a0, { ...moved(a0), H: [a0.H[a0.H.length - 1]] }); }   // fixed start + connector
  else out.push(moved(T[s]));
  if (s + 1 === T.length - 1) { const e = T[s + 1]; out.push({ ...moved(e), H: [e.H[0]] }, e); }  // connector + fixed end
  else out.push(moved(T[s + 1]));
  return out.concat(T.slice(s + 2));
}

// drag station s to (x, y). Ortho: an axis-aligned neighbour segment stays aligned – an interior neighbour slides along,
// a run end gets a corner inserted.
export function dragStation(S, s, x, y, opt) {
  const T = S.map(q => ({ ...q, H: [...q.H] })); const old = { ...T[s] };
  T[s] = { ...T[s], x, y };
  if (!opt.ortho) return T;
  const fix = (n, dir) => {  // n = neighbour index, dir = -1 (before) / +1 (after)
    if (n < 0 || n >= T.length) return;
    const ax = axisOf(S[n], old, opt.axisEps_deg); if (!ax) return;
    const isEnd = n === 0 || n === T.length - 1;
    if (!isEnd) { if (ax === 'x') T[n] = { ...T[n], y }; else T[n] = { ...T[n], x }; return; }
    const c = ax === 'x' ? { x, y: T[n].y } : { x: T[n].x, y };        // keep the end, turn the corner here
    if (Math.hypot(c.x - x, c.y - y) < 1e-6) return;
    const h = T[s].H[dir < 0 ? 0 : T[s].H.length - 1];
    T.splice(dir < 0 ? s : s + 1, 0, { x: c.x, y: c.y, H: [h], inserted: true });
  };
  const len0 = T.length; fix(s + 1, +1); const shift = T.length - len0; fix(s - 1, -1);
  void shift; return T.map(({ inserted, ...q }) => q);
}

export function insertStation(S, s, x, y) {   // on segment s→s+1, H interpolated
  const a = S[s], b = S[s + 1], L = Math.hypot(b.x - a.x, b.y - a.y), t = L ? Math.hypot(x - a.x, y - a.y) / L : 0;
  const h = lerpH(a.H[a.H.length - 1], b.H[0], Math.max(0, Math.min(1, t)));
  return [...S.slice(0, s + 1), { x, y, H: [h] }, ...S.slice(s + 1)];
}

export function deleteStation(S, s) {
  if (S.length <= 2) return { S, why: 'קו חייב לפחות שתי נקודות' };
  if (S[s].H.length > 1) return { S, why: 'בנקודה יש קטע אנכי (עולה / יורד) – לא נמחקת' };
  return { S: S.filter((_, i) => i !== s) };
}

// straighten to the house axes: simplify the plan (Douglas–Peucker, risers and ends kept), then replace every
// non-aligned segment by an L (longer leg first), H interpolated along the plan length
export function orthogonalize(S, opt) {
  const keep = new Set([0, S.length - 1]); S.forEach((q, i) => { if (q.H.length > 1) keep.add(i); });
  const dist = (p, a, b) => { const dx = b.x - a.x, dy = b.y - a.y, L2 = dx * dx + dy * dy; const t = L2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L2)) : 0; return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy); };
  const dp = (i, j) => { let best = -1, k = -1; for (let m = i + 1; m < j; m++) { const d = keep.has(m) ? Infinity : dist(S[m], S[i], S[j]); if (d > best) { best = d; k = m; } } if (k >= 0 && best > opt.orthoSimplify_m) { keep.add(k); dp(i, k); dp(k, j); } };
  const anchors = [...keep].sort((a, b) => a - b); for (let i = 0; i + 1 < anchors.length; i++) dp(anchors[i], anchors[i + 1]);
  const K = [...keep].sort((a, b) => a - b).map(i => ({ ...S[i], H: [...S[i].H] }));
  const out = [K[0]];
  for (let i = 1; i < K.length; i++) {
    const a = out[out.length - 1], b = K[i];
    if (!axisOf(a, b, opt.axisEps_deg) && Math.hypot(b.x - a.x, b.y - a.y) > 1e-6) {
      const dx = Math.abs(b.x - a.x), dy = Math.abs(b.y - a.y), c = dx >= dy ? { x: b.x, y: a.y } : { x: a.x, y: b.y };
      const l1 = Math.hypot(c.x - a.x, c.y - a.y), t = l1 / (l1 + Math.hypot(b.x - c.x, b.y - c.y));
      out.push({ x: c.x, y: c.y, H: [lerpH(a.H[a.H.length - 1], b.H[0], t)] });
    }
    out.push(b);
  }
  return mergeCollinear(out, opt);
}

export function mergeCollinear(S, opt) {
  const out = [S[0]];
  for (let i = 1; i < S.length; i++) {
    const q = S[i], p = out[out.length - 1];
    if (Math.hypot(q.x - p.x, q.y - p.y) < opt.minSeg_m && q.H.length === 1 && p.H.length === 1 && i < S.length - 1) continue;   // tiny piece
    if (out.length >= 2 && i < S.length - 1 && p.H.length === 1) {
      const o = out[out.length - 2], a1 = axisOf(o, p, opt.axisEps_deg), a2 = axisOf(p, q, opt.axisEps_deg);
      if (a1 && a1 === a2) { out[out.length - 1] = q; continue; }
    }
    out.push(q);
  }
  return out;
}

// gravity line: H along the run from its first vertex down at `slope` per plan metre; vertical pieces keep their drop
export function applySlope(run, slope) {
  const V = run.vertices.map(v => [...v]); if (V[0][2] == null) return { run, why: 'אין מפלס בקצה העליון' };
  const orig = run.vertices;
  for (let i = 1; i < V.length; i++) {
    const plan = Math.hypot(orig[i][0] - orig[i - 1][0], orig[i][1] - orig[i - 1][1]);
    const dz = plan < 0.02 && orig[i][2] != null && orig[i - 1][2] != null ? orig[i][2] - orig[i - 1][2] : -slope * plan;
    V[i][2] = r3(V[i - 1][2] + dz);
  }
  return { run: { ...run, vertices: V, slope } };
}

export function shiftH(run, dh) { return { ...run, vertices: run.vertices.map(v => [v[0], v[1], v[2] == null ? null : r3(v[2] + dh)]) }; }
export function isAxisAligned(a, b, eps) { return !!axisOf(a, b, eps); }

// Move a point (manifold, fixture, chamber …) with everything connected to it, as one system.
// Connected runs: from/to names the point, or their end lies within connectTol of it. Of each such run, the stations
// within `zone` of the point (the manifold's outlet stubs; for a plain point only the end itself) move with it; the
// first station outside stays and is reached by a connector (in ortho an L, so every piece stays on the house axes).
// Returns { node, runs: {id: newRun} } – one undo step for the caller.
export function moveNodeSystem(node, runs, dx, dy, ctx) {
  const { fr, opt, zone, connectTol, stationTol } = ctx, P = fr.toLocal(node.E, node.N);
  const [E, N] = fr.toITM(P[0] + dx, P[1] + dy);
  const dE = E - node.E, dN = N - node.N;
  const { xy, outletsXY, ...plain } = node;   // drop display-only fields
  const outlets = plain.outlets ? Object.fromEntries(Object.entries(plain.outlets).map(([k, l]) => [k, l.map(o => ({ ...o, E: r3(o.E + dE), N: r3(o.N + dN) }))])) : undefined;
  const out = { node: { ...plain, E: r3(E), N: r3(N), ...(outlets ? { outlets } : {}) }, runs: {} };
  const near = (q, R) => Math.hypot(q.x - P[0], q.y - P[1]) <= R;
  for (const run of runs) {
    let S = stations(run, fr, stationTol); if (S.length < 2) continue;
    const atStart = run.from === node.id || near(S[0], connectTol), atEnd = run.to === node.id || near(S[S.length - 1], connectTol);
    if (!atStart && !atEnd) continue;
    const moveEnd = (T) => {   // T starts at the point; move its leading stations in the zone, connect to the rest
      let k = 0; while (k < T.length && (k === 0 || near(T[k], zone))) k++;
      const moved = T.slice(0, k).map(q => ({ ...q, x: q.x + dx, y: q.y + dy, H: [...q.H] }));
      if (k >= T.length) return moved;
      const p = moved[k - 1], q = T[k], o = T[k - 1], ax = axisOf(o, q, opt.axisEps_deg);
      if (ax) {   // straight on the house axes: keep it there with an L
        const mid = [];
        if (ax === 'x' && Math.abs(q.y - p.y) > 1e-6) mid.push({ x: p.x, y: q.y, H: [p.H[p.H.length - 1]] });
        else if (ax === 'y' && Math.abs(q.x - p.x) > 1e-6) mid.push({ x: q.x, y: p.y, H: [p.H[p.H.length - 1]] });
        return [...moved, ...mid, ...T.slice(k)];
      }
      // curved / diagonal route: the shift fades out along the next `zone` metres of the route (no zigzag)
      const rest = T.slice(k).map(q2 => ({ ...q2, H: [...q2.H] })); let acc = 0, prev = T[k - 1];
      for (const q2 of rest) { acc += Math.hypot(q2.x - prev.x, q2.y - prev.y); prev = { x: q2.x, y: q2.y }; const f = Math.max(0, 1 - acc / zone); if (f <= 0) break; q2.x += dx * f; q2.y += dy * f; }
      return [...moved, ...rest];
    };
    if (atStart) S = moveEnd(S);
    if (atEnd) S = moveEnd([...S].reverse().map(q => ({ ...q, H: [...q.H].reverse() }))).reverse().map(q => ({ ...q, H: [...q.H].reverse() }));
    out.runs[run.id] = fromStations(run, S, fr);   // no merging: the far end must stay exactly where it was
  }
  return out;
}

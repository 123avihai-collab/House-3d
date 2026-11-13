// Tile layout engine (pure – no THREE, no DOM; used by the workshop and by tests/tiling.mjs).
// A zone = a room floor polygon (ITM, from data/finishes/tiling/surfaces.json). The layout works in a local frame (u, v):
// u along the tile's long side, rotated to the zone's dominant wall direction (+ the chosen direction / pattern rotation),
// origin at the centre of the zone's bounding box in that frame. Every tile rectangle is clipped by the zone polygon
// (Sutherland–Hodgman, the rectangle is the convex clipper) – the pieces give the counts, the cut sizes and the 3D mesh.
// All sizes come from the arguments (catalog / Avihai's choice); nothing is written here.

const EPS = 1e-6;

export const area = (p) => { let a = 0; for (let i = 0, n = p.length; i < n; i++) { const [x1, y1] = p[i], [x2, y2] = p[(i + 1) % n]; a += x1 * y2 - x2 * y1; } return a / 2; };

// dominant wall direction of a polygon (rad, in [0, π/2)): length-weighted vote of the edge angles mod 90°
export function dominantAngle(ring) {
  const bins = new Float64Array(180);   // 0.5° bins
  const edges = [];
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length], L = Math.hypot(x2 - x1, y2 - y1);
    if (L < 0.05) continue;
    let a = Math.atan2(y2 - y1, x2 - x1) % (Math.PI / 2); if (a < 0) a += Math.PI / 2;
    edges.push([a, L]); bins[Math.min(179, Math.floor(a / (Math.PI / 2) * 180))] += L;
  }
  if (!edges.length) return 0;
  let best = 0, bw = -1;
  for (let i = 0; i < 180; i++) { const w = bins[i] + 0.5 * (bins[(i + 1) % 180] + bins[(i + 179) % 180]); if (w > bw) { bw = w; best = i; } }
  const c = (best + 0.5) / 180 * Math.PI / 2;
  // refine: circular mean (period 90°) of the edges within 1.5° of the winner
  let sx = 0, sy = 0;
  for (const [a, L] of edges) { let d = a - c; d -= Math.round(d / (Math.PI / 2)) * Math.PI / 2; if (Math.abs(d) <= 1.5 * Math.PI / 180) { sx += L * Math.cos(4 * a); sy += L * Math.sin(4 * a); } }
  let r = sx || sy ? Math.atan2(sy, sx) / 4 : c; if (r < 0) r += Math.PI / 2;
  return r;
}

// clip a polygon (any, may be concave) by an axis-aligned rectangle (convex clipper)
export function clipRect(poly, x0, y0, x1, y1) {
  let out = poly;
  const edge = (inside, cut) => {
    const inp = out; out = [];
    if (!inp.length) return;
    let S = inp[inp.length - 1];
    for (const E of inp) {
      const ei = inside(E), si = inside(S);
      if (ei) { if (!si) out.push(cut(S, E)); out.push(E); } else if (si) out.push(cut(S, E));
      S = E;
    }
  };
  const ix = (X) => (S, E) => [X, S[1] + (E[1] - S[1]) * (X - S[0]) / (E[0] - S[0])];
  const iy = (Y) => (S, E) => [S[0] + (E[0] - S[0]) * (Y - S[1]) / (E[1] - S[1]), Y];
  edge(p => p[0] >= x0, ix(x0)); edge(p => p[0] <= x1, ix(x1));
  edge(p => p[1] >= y0, iy(y0)); edge(p => p[1] <= y1, iy(y1));
  return out;
}

// the local frame of a zone for a given choice
export function frameOf(rings, opt, pattern, direction) {
  const outer = rings[0];
  const base = opt.angle_deg != null ? opt.angle_deg * Math.PI / 180 : dominantAngle(outer);
  const a = base + ((direction?.rotate_deg || 0) + (pattern?.rotate_deg || 0)) * Math.PI / 180;
  const c = Math.cos(a), s = Math.sin(a);
  // bbox centre in the rotated frame (around the first vertex, for float precision with ITM coordinates)
  const [ox, oy] = outer[0];
  let u0 = Infinity, u1 = -Infinity, v0 = Infinity, v1 = -Infinity;
  for (const r of rings) for (const [x, y] of r) { const dx = x - ox, dy = y - oy, u = dx * c + dy * s, v = -dx * s + dy * c; u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v); }
  const um = (u0 + u1) / 2, vm = (v0 + v1) / 2;
  const cx = ox + um * c - vm * s, cy = oy + um * s + vm * c;
  return { a, base, c, s, cx, cy, size: [u1 - u0, v1 - v0],
    toLocal: ([x, y]) => { const dx = x - cx, dy = y - cy; return [dx * c + dy * s, -dx * s + dy * c]; },
    toWorld: ([u, v]) => [cx + u * c - v * s, cy + u * s + v * c] };
}

// lay out one zone. rings: [outer, ...holes] in ITM; tile: { l_m, w_m }; opt: { joint_mm, origin, du_cm, dv_cm };
// pattern: { rowShift }; cuts: { hardMin_m, softMinFrac }.  Returns pieces (local coords) + counts.
export function layoutZone(rings, tile, opt, pattern, direction, cuts, frame = null) {
  const F = frame || frameOf(rings, opt, pattern, direction);
  const loc = rings.map(r => r.map(F.toLocal));
  return layoutLocal(loc, F, tile, opt, pattern, cuts);
}

export function layoutLocal(loc, F, tile, opt, pattern, cuts) {
  const L = tile.l_m, W = tile.w_m, j = (opt.joint_mm ?? 2) / 1000, mu = L + j, mv = W + j;
  const outer = loc[0], holes = loc.slice(1);
  let u0 = Infinity, u1 = -Infinity, v0 = Infinity, v1 = -Infinity;
  for (const [u, v] of outer) { u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v); }
  // start of tile (0, 0): its lower-left corner
  let su, sv;
  if (opt.origin === 'corner') { su = u0; sv = v0; }
  else if (opt.origin === 'jointCenter') { su = j / 2; sv = j / 2; }
  else { su = -L / 2; sv = -W / 2; }
  su += (opt.du_cm || 0) / 100; sv += (opt.dv_cm || 0) / 100;
  const shift = pattern?.rowShift || 0;
  const pieces = [];
  const jMin = Math.floor((v0 - sv) / mv) - 1, jMax = Math.ceil((v1 - sv) / mv) + 1;
  const tileA = L * W, hard = cuts?.hardMin_m ?? 0.05, frac = cuts?.softMinFrac ?? 1 / 3;
  for (let jj = jMin; jj <= jMax; jj++) {
    const y0 = sv + jj * mv, y1 = y0 + W;
    if (y1 < v0 - EPS || y0 > v1 + EPS) continue;
    let rs = (((jj * shift) % 1) + 1) % 1; const ru = su + rs * mu;
    const iMin = Math.floor((u0 - ru) / mu) - 1, iMax = Math.ceil((u1 - ru) / mu) + 1;
    for (let ii = iMin; ii <= iMax; ii++) {
      const x0 = ru + ii * mu, x1 = x0 + L;
      if (x1 < u0 - EPS || x0 > u1 + EPS) continue;
      const p = clipRect(outer, x0, y0, x1, y1);
      if (p.length < 3) continue;
      let A = Math.abs(area(p));
      const hs = [];
      for (const hl of holes) { const q = clipRect(hl, x0, y0, x1, y1); if (q.length >= 3) { const qa = Math.abs(area(q)); if (qa > EPS) { A -= qa; hs.push(q); } } }
      if (A < 1e-5) continue;
      let bx0 = Infinity, bx1 = -Infinity, by0 = Infinity, by1 = -Infinity;
      for (const [x, y] of p) { bx0 = Math.min(bx0, x); bx1 = Math.max(bx1, x); by0 = Math.min(by0, y); by1 = Math.max(by1, y); }
      const bw = bx1 - bx0, bh = by1 - by0;
      const full = A >= tileA - 1e-4 && !hs.length;
      let cut = null, sev = 0;
      if (!full) {
        const cu = bw < L - 1e-4 ? bw : null, cv = bh < W - 1e-4 ? bh : null;
        cut = Math.min(cu ?? Infinity, cv ?? Infinity); if (cut === Infinity) cut = null;   // notch only (a corner of the wall inside the tile)
        if ((cu != null && cu < hard) || (cv != null && cv < hard)) sev = 2;
        else if ((cu != null && cu < L * frac) || (cv != null && cv < W * frac)) sev = 1;
      }
      pieces.push({ i: ii, j: jj, x0, y0, poly: p, holes: hs, area: A, full, cut, sev, bw, bh });
    }
  }
  const cutsArr = pieces.filter(p => !p.full);
  const stats = {
    pieces: pieces.length, full: pieces.length - cutsArr.length, cut: cutsArr.length,
    slivers: cutsArr.filter(p => p.sev === 2).length, narrow: cutsArr.filter(p => p.sev === 1).length,
    minCut_m: cutsArr.reduce((m, p) => p.cut != null ? Math.min(m, p.cut) : m, Infinity),
    tileArea_m2: pieces.reduce((a, p) => a + p.area, 0), zoneArea_m2: Math.abs(area(outer)) - holes.reduce((a, hh) => a + Math.abs(area(hh)), 0),
  };
  if (stats.minCut_m === Infinity) stats.minCut_m = null;
  stats.score = score(pieces);
  return { frame: F, pieces, stats, tile: { L, W, j }, start: [su, sv] };
}

// lower = better: slivers dominate, then narrow cuts, then the number of cut pieces (fewer cuts = less work and waste)
export function score(pieces) {
  let s = 0;
  for (const p of pieces) if (!p.full) s += p.sev === 2 ? 40 + (p.cut != null ? (0.05 - p.cut) * 200 : 0) : p.sev === 1 ? 4 : 0.25;
  return s;
}

// "פריסה מושלמת": search the start offsets (du, dv) over one tile module; coarse grid, then a fine pass around the best.
// Ties are broken toward the symmetric layout (smallest offset from the chosen origin).
export function optimize(rings, tile, opt, pattern, direction, cuts) {
  const F = frameOf(rings, opt, pattern, direction);
  const loc = rings.map(r => r.map(F.toLocal));
  const j = (opt.joint_mm ?? 2) / 1000, mu = tile.l_m + j, mv = tile.w_m + j;
  const run = (du, dv) => layoutLocal(loc, F, tile, { ...opt, du_cm: du, dv_cm: dv }, pattern, cuts).stats.score;
  const n = 24;
  let best = { du: 0, dv: 0, s: run(0, 0) }; const base = best.s;
  const sym = (du, dv) => Math.min(Math.abs(du), mu * 100 - Math.abs(du)) + Math.min(Math.abs(dv), mv * 100 - Math.abs(dv));
  const consider = (du, dv) => { const s = run(du, dv); if (s < best.s - 1e-9 || (Math.abs(s - best.s) < 1e-9 && sym(du, dv) < sym(best.du, best.dv))) best = { du, dv, s }; };
  for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) consider(+(a / n * mu * 100 - (a / n > 0.5 ? mu * 100 : 0)).toFixed(1), +(b / n * mv * 100 - (b / n > 0.5 ? mv * 100 : 0)).toFixed(1));
  const st = mu * 100 / n, sv = mv * 100 / n;
  const c = { ...best };
  for (let a = -4; a <= 4; a++) for (let b = -4; b <= 4; b++) consider(+(c.du + a * st / 4).toFixed(1), +(c.dv + b * sv / 4).toFixed(1));
  return { du_cm: best.du, dv_cm: best.dv, score: best.s, before: base };
}

// quantities of one laid-out zone (catalog consumption rates – provisional)
export function quantities(lay, size, opt, cons, skirting_m) {
  const { L, W, j } = lay.tile, st = lay.stats;
  const spare = (opt.spare_pct ?? 5) / 100;
  const hSk = cons.skirtingHeight_m, strips = Math.max(1, Math.floor((W + 1e-9) / hSk));
  const skTiles = skirting_m > 0 ? Math.ceil(skirting_m / (L * strips)) : 0;
  const layTiles = st.full + st.cut;
  const order = Math.ceil((layTiles + skTiles) * (1 + spare));
  const perBox = size.perBox || 1, boxes = Math.ceil(order / perBox);
  const adh = (cons.adhesive.find(r => Math.max(L, W) <= r.maxLong_m + 1e-9) || cons.adhesive.at(-1)).kg_m2;
  const A = st.zoneArea_m2;
  const tmm = (size.thick_m || 0.01) * 1000, Lmm = L * 1000, Wmm = W * 1000, jmm = j * 1000;
  const grout = (Lmm + Wmm) / (Lmm * Wmm) * tmm * jmm * cons.groutDensity;   // kg/m²
  return {
    area_m2: A, tileArea_m2: st.tileArea_m2, full: st.full, cut: st.cut, slivers: st.slivers, narrow: st.narrow, minCut_m: st.minCut_m,
    layTiles, skirtingTiles: skTiles, order, boxes, perBox, order_m2: order * L * W, waste_pct: layTiles ? (layTiles * L * W - st.tileArea_m2) / (layTiles * L * W) * 100 : 0,
    adhesive_kg: A * adh, adhesiveBags: Math.ceil(A * adh / cons.adhesiveBag_kg), grout_kg: A * grout, groutBags: Math.ceil(A * grout / cons.groutBag_kg),
  };
}

// exterior paving: the finish surface of a zone (data/finishes/tiling/exterior.json → surface, tools/finishes/derive_exterior.py):
// best-fit plane + inverse-distance correction of the residuals at the permit spots – passes exactly through every spot.
// Returns z(E, N) (relative to ±0.00); null surface → null.
export function surfaceZ(S) {
  if (!S) return null;
  const res = S.res || [], k = S.power ?? 2;
  const pz = (E, N) => S.z + S.gE * (E - S.E) + S.gN * (N - S.N);
  return (E, N) => {
    let sw = 0, sr = 0;
    for (const [e, n, r] of res) {
      const d2 = (E - e) ** 2 + (N - n) ** 2;
      if (d2 < 1e-12) return pz(E, N) + r;
      const w = d2 ** (-k / 2); sw += w; sr += w * r;
    }
    return pz(E, N) + (sw ? sr / sw : 0);
  };
}

// a polygon (+ holes) cut into grid cells (step m, ITM) – so a curved / sloped surface can be drawn through it
export function gridPieces(ring, holes, step) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of ring) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const out = [];
  for (let x = x0; x < x1 - EPS; x += step) for (let y = y0; y < y1 - EPS; y += step) {
    const o = clipRect(ring, x, y, Math.min(x + step, x1), Math.min(y + step, y1));
    if (o.length < 3 || Math.abs(area(o)) < 1e-8) continue;
    const hs = (holes || []).map(h => clipRect(h, x, y, Math.min(x + step, x1), Math.min(y + step, y1))).filter(h => h.length >= 3 && Math.abs(area(h)) > 1e-8);
    out.push([o, hs]);
  }
  return out;
}

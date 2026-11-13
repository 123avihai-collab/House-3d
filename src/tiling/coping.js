// Pool coping layout engine (pure – no THREE, no DOM; used by src/tiling/pool.js and tests/coping.mjs).
//
// The coping sits on the pool wall tops: across a side, from the overhang line in the water (t = −oh) to the outer face
// of the wall (t = wt); t is measured from the water face of the wall, + away from the water. Along a side, s runs from
// the side's first inner corner (s = 0) to its second (s = L). Every piece is bounded by two end lines s = c + k·t:
//   k = 0  a square end (a joint between pieces, or a butt corner),
//   k = −1 a 45° mitre at the start corner (through the outer corner s = −wt, t = wt and the overhang corner s = oh, t = −oh),
//   k = +1 a 45° mitre at the end corner.
// Lengths are measured on the outer (long) edge, t = wt; the water edge of a mitre piece is shorter by the width W = wt + oh.
//
// Layout rules (accepted practice – no spec in the sources; all values come from the arguments):
//   1. corners: 45° mitre (default) – or butt: the long sides run through the corners, the short sides fit between them
//   2. symmetric about the middle of each side ("center"): a joint or a whole piece on the centre line, whole pieces outward,
//      the cut falls in the two end (corner) pieces – both ends equal. Of the two options, the one with the bigger end pieces
//   3. an end piece not shorter than minEndFrac of the stock length on its long edge, and its short (water) edge not shorter
//      than minInnerFrac of the stock and minEdge_m – otherwise equal pieces along the side ("equal", every piece cut alike)
//   4. no piece longer than the stock; equal joints; a movement joint at every corner and at least every movementMax_m
//   5. the stock is ripped to the width W when it is wider (one cut along every piece)
//   6. square edge only: two mitre pieces nest in one stock length when their long edges fit (e1 + e2 ≤ P + W − kerf·√2)

const R2 = Math.SQRT2;

// one side: { L, wt, oh } + options → end lines of the run, then the pieces
function runEnds(side, o) {
  const { L, wt, oh } = side, j = o.joint_m;
  if (o.corner === 'miter') return { A: { c: j / R2, k: -1 }, B: { c: L - j / R2, k: 1 } };
  if (side.long) return { A: { c: -wt, k: 0 }, B: { c: L + wt, k: 0 } };
  return { A: { c: oh + j, k: 0 }, B: { c: L - oh - j, k: 0 } };   // butt: between the long sides' water edges (joint each side)
}

// piece lengths along the outer edge – symmetric about the middle ([e, P × m, e]), or equal pieces
function divide(Lo, o, kA, kB, W) {
  const P = o.length_m, j = o.joint_m, half = Lo / 2;
  const inner = (e, k) => e - Math.abs(k) * W;
  const ok = (e) => e >= o.minEndFrac * P - 1e-9 && e <= P + 1e-9 && Math.min(inner(e, kA), inner(e, kB)) >= Math.max(o.minEdge_m, (o.minInnerFrac || 0) * P) - 1e-9;
  const equal = (fallback = false) => { const n = Math.max(1, Math.ceil((Lo + j) / (P + j) - 1e-9)), pl = (Lo - (n - 1) * j) / n; return { mode: 'equal', lengths: Array(n).fill(pl), end: pl, fallback }; };
  if (Lo <= P + 1e-9) return { mode: 'single', lengths: [Lo], end: Lo };
  if (o.layout === 'equal') return equal();
  const opts = [];
  // a joint on the centre line: half = j/2 + n(P + j) + e  →  [e, P × 2n, e]
  { const n = Math.max(0, Math.ceil((half - j / 2 - P) / (P + j) - 1e-9)); opts.push({ mode: 'center-joint', e: half - j / 2 - n * (P + j), m: 2 * n }); }
  // a whole piece on the centre line: half = P/2 + j + n(P + j) + e  →  [e, P × (2n + 1), e]
  if (half - P / 2 - j > 0) { const n = Math.max(0, Math.ceil((half - P / 2 - j - P) / (P + j) - 1e-9)); opts.push({ mode: 'center-piece', e: half - P / 2 - j - n * (P + j), m: 2 * n + 1 }); }
  const good = opts.filter(x => ok(x.e)).sort((a, b) => b.e - a.e);
  if (!good.length) return equal(true);
  const g = good[0];
  return { mode: g.mode, lengths: [g.e, ...Array(g.m).fill(P), g.e], end: g.e };
}

export function layoutCoping({ ring, wt, oh, stockW, opt }) {
  const o = { ...opt, joint_m: opt.joint_mm / 1000, kerf_m: (opt.kerf_mm ?? 3) / 1000 };
  const W = wt + oh, rip = stockW > W + 1e-6;
  const n = ring.length, ctr = ring.reduce((s, p) => [s[0] + p[0] / n, s[1] + p[1] / n], [0, 0]);
  const sides = ring.map((a, i) => { const b = ring[(i + 1) % n], L = Math.hypot(b[0] - a[0], b[1] - a[1]); return { i, a, b, L }; });
  const longest = Math.max(...sides.map(s => s.L));
  const runs = [];
  for (const sd of sides) {
    const { a, b, L } = sd, d = [(b[0] - a[0]) / L, (b[1] - a[1]) / L];
    let nrm = [d[1], -d[0]]; const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    if ((mid[0] - ctr[0]) * nrm[0] + (mid[1] - ctr[1]) * nrm[1] < 0) nrm = [-nrm[0], -nrm[1]];
    const side = { L, wt, oh, long: L > longest - 0.01 };
    const { A, B } = runEnds(side, o);
    const S0 = A.c + A.k * wt, S1 = B.c + B.k * wt;
    const dv = divide(S1 - S0, o, A.k, B.k, W);
    const bounds = []; let x = S0;
    dv.lengths.forEach((len, q) => { if (q) x += o.joint_m; bounds.push(x, x + len); x += len; });
    bounds[bounds.length - 1] = S1;   // float: the last edge exactly on the run end
    const pieces = [];
    for (let q = 0; q + 1 < bounds.length; q += 2) {
      const s0 = bounds[q], s1 = bounds[q + 1], first = q === 0, last = q + 2 >= bounds.length;
      const ea = first ? A : { c: s0, k: 0 }, eb = last ? B : { c: s1, k: 0 };
      const outer = (eb.c + eb.k * wt) - (ea.c + ea.k * wt), inner = (eb.c - eb.k * oh) - (ea.c - ea.k * oh);
      const miters = (ea.k ? 1 : 0) + (eb.k ? 1 : 0);
      const full = !miters && Math.abs(outer - o.length_m) < 5e-4;
      const cuts = [];
      if (miters) cuts.push(miters === 2 ? '2 × 45°' : '45°');
      if (!miters && !full) cuts.push(`קיצור ישר ל-${Math.round(outer * 1000) / 10}`);
      if (rip) cuts.push(`חיתוך לאורך לרוחב ${Math.round(W * 1000) / 10}`);
      pieces.push({ side: sd.i, q, A: ea, B: eb, outer_m: outer, inner_m: inner, s0: ea.c + ea.k * wt, s1: eb.c + eb.k * wt,
        type: miters === 2 ? 'miter2' : miters ? (ea.k ? 'miterStart' : 'miterEnd') : full ? 'full' : 'cut', cuts });
    }
    // joints between pieces (square), with movement joints every ≤ movementMax_m (the joint nearest to each target)
    const joints = pieces.slice(1).map((p, i) => ({ s: (pieces[i].s1 + p.s0) / 2, movement: false }));
    const Lo = S1 - S0, nm = o.movementMax_m > 0 ? Math.ceil(Lo / o.movementMax_m) - 1 : 0;
    for (let m = 1; m <= nm && joints.length; m++) {
      const target = S0 + Lo * m / (nm + 1);
      const jn = joints.reduce((best, x) => Math.abs(x.s - target) < Math.abs(best.s - target) ? x : best, joints[0]);
      jn.movement = true;
    }
    runs.push({ side: sd.i, a, d, n: nrm, L, long: side.long, A, B, S0, S1, outer_m: S1 - S0, mode: dv.mode, fallback: !!dv.fallback, end_m: dv.end, pieces, joints });
  }
  // corner joints (mitre or butt): one per corner, always a movement joint (rule 4)
  const corners = sides.map(s => ({ corner: s.i, length_m: o.corner === 'miter' ? W * R2 : W, movement: true }));
  return { W, rip, runs, corners, pieces: runs.flatMap(r => r.pieces), opt: o, stock: stockOf(runs.flatMap(r => r.pieces), o, W) };
}

// stock units: whole pieces one each; square cuts packed first-fit-decreasing into stock lengths (kerf between);
// mitre pieces one per stock – or two nested in one (square edge: the offcut turned 180° is the opposite mitre)
function stockOf(pieces, o, W) {
  const P = o.length_m, kerf = o.kerf_m;
  const full = pieces.filter(p => p.type === 'full').length;
  const rects = pieces.filter(p => p.type === 'cut').map(p => p.outer_m).sort((a, b) => b - a);
  const bins = [];
  for (const x of rects) { const b = bins.find(b => b.left >= x - 1e-9); if (b) { b.left -= x + kerf; b.items.push(x); } else bins.push({ left: P - x - kerf, items: [x] }); }
  const ms = pieces.filter(p => p.type === 'miterStart').map(p => p.outer_m).sort((a, b) => b - a);
  const me = pieces.filter(p => p.type === 'miterEnd').map(p => p.outer_m).sort((a, b) => a - b);
  let pairs = 0, single = 0;
  if (o.edge === 'square') {
    // start + end mitres (mirror images); with a square edge a start piece turned 180° is also an end piece – pool them
    const all = [...ms, ...me].sort((a, b) => b - a), used = new Array(all.length).fill(false);
    for (let i = 0; i < all.length; i++) { if (used[i]) continue; used[i] = true;
      let k = -1; for (let m = all.length - 1; m > i; m--) if (!used[m] && all[i] + all[m] + kerf * R2 <= P + W + 1e-9) { k = m; break; }
      if (k >= 0) { used[k] = true; pairs++; } else single++; }
  } else single = ms.length + me.length;
  const both = pieces.filter(p => p.type === 'miter2').length;
  return { full, cutBins: bins.length, miterStocks: pairs + single, miterPairs: pairs, both, units: full + bins.length + pairs + single + both, bins };
}

// the cut list: identical pieces grouped (type, long edge, short edge – to the millimetre)
export function cutList(lay) {
  const g = new Map();
  for (const p of lay.pieces) {
    const k = [p.type, p.outer_m.toFixed(3), p.inner_m.toFixed(3)].join('|');
    const x = g.get(k) || { type: p.type, outer_m: p.outer_m, inner_m: p.inner_m, cuts: p.cuts, qty: 0, where: [] };
    x.qty++; x.where.push(`${p.side + 1}.${p.q + 1}`); g.set(k, x);
  }
  const order = { full: 0, cut: 1, miterStart: 2, miterEnd: 3, miter2: 4 };
  return [...g.values()].sort((a, b) => order[a.type] - order[b.type] || b.outer_m - a.outer_m);
}

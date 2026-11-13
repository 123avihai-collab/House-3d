// Pool coping layout engine (src/tiling/coping.js) – pure, no browser. For every option (corner, layout, stock length,
// overhang): the pieces + joints fill each side exactly; no piece longer than the stock; the symmetric layout is a palindrome
// with end pieces inside the rules; a mitre end is shorter on the water edge by the width; movement joints at most
// movementMax apart; the cut list counts every piece once. Run: node tests/coping.mjs
import fs from 'fs';
import path from 'path';
import { layoutCoping, cutList } from '../src/tiling/coping.js';
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const S = JSON.parse(fs.readFileSync(path.join(root, 'data/finishes/pool/surfaces.json')));
const C = JSON.parse(fs.readFileSync(path.join(root, 'data/finishes/pool/catalog.json'))).coping;
let failed = 0, cases = 0;
const fail = (...a) => { failed++; console.error(...a); };
for (const corner of C.corners.map(x => x.id)) for (const layout of C.layouts.map(x => x.id)) for (const P of C.lengths_m) for (const oh of C.overhangs_m) for (const jm of C.joint_mm) for (const edge of C.edges.map(e => e.id)) {
  cases++;
  const opt = { ...C.rules, corner, layout, length_m: P, joint_mm: jm, edge };
  const L = layoutCoping({ ring: S.innerRingITM, wt: S.wallThickness_m, oh, stockW: 0.25, opt });
  const tag = `${corner}/${layout}/${P}/${oh}/${jm}/${edge}`, j = jm / 1000, W = S.wallThickness_m + oh;
  for (const r of L.runs) {
    const sum = r.pieces.reduce((a, p) => a + p.outer_m, 0) + (r.pieces.length - 1) * j;
    if (Math.abs(sum - r.outer_m) > 1e-6) fail(tag, 'side', r.side, 'pieces + joints ≠ side', sum, r.outer_m);
    for (const p of r.pieces) {
      if (p.outer_m > P + 1e-6) fail(tag, 'piece longer than the stock', p.outer_m);
      const m = (p.A.k ? 1 : 0) + (p.B.k ? 1 : 0);
      if (Math.abs(p.outer_m - p.inner_m - m * W) > 1e-6) fail(tag, 'mitre edge', p);
      if (p.inner_m < 0.05) fail(tag, 'sliver on the water edge', p.inner_m);
    }
    const ol = r.pieces.map(p => p.outer_m.toFixed(4));
    if (layout === 'center' && ol.join() !== [...ol].reverse().join()) fail(tag, 'not symmetric', ol);
    if (r.mode.startsWith('center')) {
      const e = r.pieces[0];
      if (e.outer_m < opt.minEndFrac * P - 1e-6 || e.inner_m < Math.max(opt.minEdge_m, opt.minInnerFrac * P) - 1e-6) fail(tag, 'end piece breaks the rules', e.outer_m, e.inner_m);
    }
    const mj = [r.S0, ...r.joints.filter(x => x.movement).map(x => x.s), r.S1];
    for (let i = 1; i < mj.length; i++) if (mj[i] - mj[i - 1] > opt.movementMax_m + P + 1e-6) fail(tag, 'movement joints too far apart', mj);
  }
  if (corner === 'miter') {   // mitre: the four sides close – outer lengths = inner sides + 2 × wall thickness (minus the corner joints)
    for (const r of L.runs) if (Math.abs(r.outer_m - (r.L + 2 * S.wallThickness_m - j * Math.SQRT2)) > 1e-6) fail(tag, 'mitre side length', r.outer_m, r.L);
  }
  if (cutList(L).reduce((a, x) => a + x.qty, 0) !== L.pieces.length) fail(tag, 'cut list count');
  if (L.stock.units > L.pieces.length) fail(tag, 'more stock than pieces');
}
if (failed) { console.error(`coping: FAILED (${failed} in ${cases} cases)`); process.exit(1); }
console.log(`coping: OK (${cases} cases)`);

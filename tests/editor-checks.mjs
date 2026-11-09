// Headless test of the editor checks (stage 3) on synthetic runs placed against real structure from the JSON:
// column clash, beam clash at / off its level, wall crossing square vs skewed, reverse / low slope, open end,
// consumption point without water, live check while dragging.
import { createRequire } from 'module';
import { execSync } from 'child_process';
import http from 'http'; import fs from 'fs'; import path from 'path';
const require = createRequire(import.meta.url);
let pw; try { pw = require('playwright'); } catch { pw = require(execSync('npm root -g').toString().trim() + '/playwright'); }
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const server = http.createServer((req, res) => { const f = path.join(root, decodeURIComponent(req.url.split('?')[0])); fs.readFile(f, (e, b) => { if (e) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); res.end(b); }); }).listen(0);
const browser = await pw.chromium.launch(); const page = await (await browser.newContext()).newPage(); const errors = [];
page.on('pageerror', e => errors.push(String(e))); page.on('console', m => m.type() === 'error' && errors.push(m.text()));
await page.goto(`http://127.0.0.1:${server.address().port}/editor.html?floor=ground`);
await page.waitForFunction(() => window.__editorReady || window.__editorErrors.length, null, { timeout: 60000 });
const res = await page.evaluate(() => {
  const E = window.__editor, CH = E.CH, fr = CH.fr, H0 = CH.H0, out = {};
  const run = (id, sys, ptsLocal, Hrel, extra = {}) => ({ id, kind: 'run', system: sys, floor: 'ground', D_mm: 20, material: 'PEX', vertices: ptsLocal.map(([x, y], i) => { const [e, n] = fr.toITM(x, y); return [e, n, H0 + (Array.isArray(Hrel) ? Hrel[i] : Hrel)]; }), ...extra });
  const types = (r) => E.checkRun(r, CH).map(i => i.sev + ':' + i.type);
  const cx = (P) => [P.reduce((s, p) => s + p[0], 0) / P.length, P.reduce((s, p) => s + p[1], 0) / P.length];
  // column: straight through its centre at mid-height → clashColumn; above its top → nothing
  const col = CH.obstacles.find(o => o.cat === 'column' && o.hi - o.lo > 1), c = cx(col.poly), zc = (col.lo + col.hi) / 2;
  out.column = types(run('T-col', 'cold', [[c[0] - 1, c[1]], [c[0] + 1, c[1]]], zc)).includes('error:clashColumn');
  out.columnAbove = !types(run('T-col2', 'cold', [[c[0] - 1, c[1]], [c[0] + 1, c[1]]], col.hi + 0.2)).includes('error:clashColumn');
  // beam: across it inside its depth → clashBeam; under it → nothing
  const bm = CH.obstacles.find(o => o.cat === 'beam' && o.lo > 2), b = cx(bm.poly);
  const ext = [Math.max(...bm.poly.map(p => p[0])) - Math.min(...bm.poly.map(p => p[0])), Math.max(...bm.poly.map(p => p[1])) - Math.min(...bm.poly.map(p => p[1]))];
  const across = ext[0] > ext[1] ? [[b[0], b[1] - 1], [b[0], b[1] + 1]] : [[b[0] - 1, b[1]], [b[0] + 1, b[1]]];
  out.beam = types(run('T-bm', 'cold', across, (bm.lo + bm.hi) / 2)).includes('error:clashBeam');
  out.beamBelow = !types(run('T-bm2', 'cold', across, bm.lo - 0.1)).some(t => t.includes('clash'));
  // concrete wall on the ground floor, long and axis aligned: square crossing → no angle warning; 30° off → warning
  const w = CH.obstacles.filter(o => o.cat === 'wall' && o.lo < 1 && o.hi > 1).map(o => ({ o, ex: [Math.max(...o.poly.map(p => p[0])) - Math.min(...o.poly.map(p => p[0])), Math.max(...o.poly.map(p => p[1])) - Math.min(...o.poly.map(p => p[1]))] })).sort((a, b) => Math.max(...b.ex) - Math.max(...a.ex))[0];
  const wc = cx(w.o.poly), alongX = w.ex[0] > w.ex[1], d = 0.8, t30 = Math.tan(30 * Math.PI / 180) * d;
  const sq = alongX ? [[wc[0], wc[1] - d], [wc[0], wc[1] + d]] : [[wc[0] - d, wc[1]], [wc[0] + d, wc[1]]];
  const sk = alongX ? [[wc[0] - t30, wc[1] - d], [wc[0] + t30, wc[1] + d]] : [[wc[0] - d, wc[1] - t30], [wc[0] + d, wc[1] + t30]];
  out.wallSquare = !types(run('T-w1', 'cold', sq, 1)).includes('warn:wallAngle');
  out.wallSkew = types(run('T-w2', 'cold', sk, 1)).includes('warn:wallAngle');
  // drainage: falls 2% ok, rises → reverse, falls 0.5% with design 2% → lowSlope
  const far = [[c[0] + 3, c[1] + 3], [c[0] + 6, c[1] + 3]];
  out.slopeOk = !types(run('T-s1', 'sewage', far, [1.0, 0.94], { slope: 0.02 })).some(t => /reverse|lowSlope/.test(t));
  out.reverse = types(run('T-s2', 'sewage', far, [0.94, 1.0], { slope: 0.02 })).includes('error:reverse');
  out.lowSlope = types(run('T-s3', 'sewage', far, [1.0, 0.985], { slope: 0.02 })).includes('warn:lowSlope');
  // open end + consumption point without water: add a free run, delete the cold run of a fixture
  E.store.apply({ 'T-open': run('T-open', 'cold', [[c[0] + 20, c[1] + 20], [c[0] + 21, c[1] + 20]], 0.3) }, 'test');
  out.openEnd = E.issues().conn.some(i => i.run === 'T-open' && i.type === 'openEnd');
  const fx = E.M.nodes.find(n => n.cold && n.floor === 'ground'), cr = E.store.runs().find(r => r.system === 'cold' && r.to === fx.id);
  out.connectedBefore = !E.issues().conn.some(i => i.node === fx.id);
  E.store.apply({ [cr.id]: null }, 'test');
  out.unconnected = E.issues().conn.some(i => i.node === fx.id && i.type === 'unconnected');
  E.store.undo(); E.store.undo();
  out.restored = !E.issues().conn.some(i => i.node === fx.id || i.run === 'T-open');
  // the panel lists the floor's findings
  out.panel = document.querySelectorAll('#ed-issues li').length === E.floorIssues().length || document.querySelectorAll('#ed-issues li').length === 200;
  return out;
});
// live during a drag: drag a column-free segment onto the column → red while dragging (preview run in error)
const c0 = await page.evaluate(() => {
  const E = window.__editor, CH = E.CH, fr = CH.fr, H0 = CH.H0;
  const col = CH.obstacles.find(o => o.cat === 'column' && o.hi - o.lo > 1), c = [col.poly.reduce((s, p) => s + p[0], 0) / col.poly.length, col.poly.reduce((s, p) => s + p[1], 0) / col.poly.length];
  const z = H0 + (col.lo + col.hi) / 2, mk = (x, y) => { const [e, n] = fr.toITM(x, y); return [e, n, z]; };
  const r = { id: 'T-live', kind: 'run', system: 'cold', floor: 'ground', D_mm: 20, material: 'PEX', vertices: [mk(c[0] - 1.5, c[1] - 1), mk(c[0] - 1.5, c[1] + 1), mk(c[0] + 1.5, c[1] + 1), mk(c[0] + 1.5, c[1] - 1)] };
  E.store.apply({ 'T-live': r }, 'test');
  const p = E.current().items.find(i => i.p.id === 'T-live').p; E.S.sel = { type: 'pipe', obj: p, vtx: null, seg: null }; E.S.snapOn = false;
  return c;
});
await page.waitForTimeout(250);   // layout settles (toolbar text) before screen coordinates are taken
const live = await page.evaluate((c) => {
  const E = window.__editor;
  E.v.resize(); E.v.cx = c[0]; E.v.cy = c[1]; E.v.k = 80; E.setFloor('ground', false); E.S.sel = { type: 'pipe', obj: E.current().items.find(i => i.p.id === 'T-live').p, vtx: null, seg: null };
  const rc = document.getElementById('ed-canvas').getBoundingClientRect(), [sx, sy] = E.toScreen(c[0], c[1] + 1);
  return { x: sx + rc.left, y: sy + rc.top };
}, c0);
await page.mouse.move(live.x, live.y); await page.mouse.down();
for (let t = 1; t <= 8; t++) await page.mouse.move(live.x, live.y + 10 * t);
await page.waitForTimeout(80);
const during = await page.evaluate(() => { const E = window.__editor; return E.S.preview ? E.checkRun(E.S.preview.run, E.CH).some(i => i.type === 'clashColumn') : null; });
await page.mouse.up(); await page.waitForTimeout(100);
const afterDrop = await page.evaluate(() => window.__editor.issues().runs['T-live']?.some(i => i.type === 'clashColumn'));
res.liveDuringDrag = during === true; res.liveAfterDrop = afterDrop === true;
res.console = !errors.length;
console.log(JSON.stringify(res));
await browser.close(); server.close();
const bad = Object.entries(res).filter(([, v]) => v !== true);
if (bad.length) { console.error('FAIL', bad.map(b => b[0]).join(', ')); process.exit(1); }
console.log('editor checks OK');

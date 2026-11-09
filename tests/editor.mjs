// Headless test of the 2D pipe editor (editor.html): desktop + phone, every floor, no console errors; pipe counts per
// floor = routes.json; pick → info card; hide / lock a layer; snap to a column corner within 1 mm.
// Usage: node tests/editor.mjs [--shots dir]
import { createRequire } from 'module';
import { execSync } from 'child_process';
import http from 'http';
import fs from 'fs';
import path from 'path';
const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch { pw = require(execSync('npm root -g').toString().trim() + '/playwright'); }
const { chromium, devices } = pw;

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const shotsDir = process.argv.includes('--shots') ? process.argv[process.argv.indexOf('--shots') + 1] : null;
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  const f = path.join(root, decodeURIComponent(req.url.split('?')[0].split('#')[0]));
  fs.readFile(f, (err, buf) => { if (err) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); res.end(buf); });
}).listen(0);
const url = `http://127.0.0.1:${server.address().port}/editor.html`;
const browser = await chromium.launch();
let failed = false;
const fail = (m) => { failed = true; console.error('FAIL', m); };

for (const [name, opts] of [['desktop', { viewport: { width: 1400, height: 860 } }], ['phone', devices['Pixel 7']]]) {
  const ctx = await browser.newContext(opts); const page = await ctx.newPage(); const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  page.on('requestfailed', r => errors.push('request failed: ' + r.url()));
  await page.goto(url);
  await page.waitForFunction(() => window.__editorReady || (window.__editorErrors && window.__editorErrors.length), null, { timeout: 60000 });
  const res = { floors: {} };
  for (const fid of await page.evaluate(() => window.__editor.cfg.floors.map(f => f.id))) {
    const r = await page.evaluate((fid) => {
      const E = window.__editor; E.setFloor(fid);
      const F = E.M.floors[fid], also = F.cfg.alsoRuns || [];
      const expected = E.D.routes.runs.filter(r => r.floor === fid || also.includes(r.floor)).length;
      const drawn = E.current().items.filter(it => it.p.layer === 'prop' && it.mode === 'plan').length;
      return { expected, drawn, walls: F.structure.concreteWalls.length, bg: F.background.walls.length };
    }, fid);
    res.floors[fid] = r;
    if (r.expected !== r.drawn) fail(`${name} ${fid}: proposal runs drawn ${r.drawn} != routes.json ${r.expected}`);
    if (shotsDir) { await page.waitForTimeout(300); await page.screenshot({ path: path.join(shotsDir, `editor-${name}-${fid}.png`) }); }
  }
  // pick: click the middle of the longest plan segment of a proposal cold run on the ground floor → info card names it
  const pick = await page.evaluate(() => {
    const E = window.__editor; E.setFloor('ground'); E.L.set('nodes', false);
    let best = null;
    for (const it of E.current().items) { const p = it.p; if (p.layer !== 'prop' || it.mode !== 'plan') continue;
      for (let i = 0; i + 1 < p.pts.length; i++) { const L = Math.hypot(p.pts[i + 1][0] - p.pts[i][0], p.pts[i + 1][1] - p.pts[i][1]); if (!best || L > best.L) best = { L, id: p.id, m: [(p.pts[i][0] + p.pts[i + 1][0]) / 2, (p.pts[i][1] + p.pts[i + 1][1]) / 2] }; } }
    const c = document.getElementById('ed-canvas').getBoundingClientRect(); const [x, y] = E.toScreen(...best.m);
    return { id: best.id, x: x + c.left, y: y + c.top };
  });
  await page.mouse.click(pick.x, pick.y); await page.waitForTimeout(200);
  const info = await page.evaluate(() => ({ shown: !document.getElementById('ed-info').classList.contains('hidden'), title: document.querySelector('#ed-info h3')?.textContent || '', sel: window.__editor.S.sel?.obj?.id }));
  res.pick = { want: pick.id, got: info.sel };
  if (!info.shown || !info.title.includes(pick.id.split('@')[0])) fail(`${name}: pick ${pick.id} → info "${info.title}" (sel ${info.sel})`);
  // hide, then lock: a locked layer stays visible but a click on it selects nothing of it
  const sysid = await page.evaluate((id) => window.__editor.D.routes.runs.find(r => r.id === id).system, pick.id);
  const hidden = await page.evaluate((k) => { const E = window.__editor; E.L.set(k, false); const h = !E.visibleItems().some(it => it.p.layer + '.' + it.p.system === k); E.L.set(k, true); return h; }, 'prop.' + sysid);
  await page.evaluate((k) => { const E = window.__editor; E.L.setLock(k, true); E.S.sel = null; }, 'prop.' + sysid);
  await page.mouse.click(pick.x, pick.y); await page.waitForTimeout(150);
  const lockedSel = await page.evaluate((k) => { const E = window.__editor, s = E.S.sel?.obj; E.L.setLock(k, false); E.L.set('nodes', true); return s ? s.layer + '.' + s.system : null; }, 'prop.' + sysid);
  res.hideLock = { hidden, lockedSel };
  if (!hidden || lockedSel === 'prop.' + sysid) fail(`${name}: hide/lock ${JSON.stringify(res.hideLock)}`);
  // snap: hover 4 px off a ground-floor column corner → snap = that corner (≤ 1 mm)
  const t = await page.evaluate(() => {
    const E = window.__editor; E.setFloor('ground'); const col = E.M.floors.ground.structure.columns[0]; const q = col.poly[2];
    E.v.cx = q[0]; E.v.cy = q[1]; E.v.k = 300; E.setFloor('ground', false);   // closes the info card, zoom on the corner
    const c = document.getElementById('ed-canvas').getBoundingClientRect(); const [x, y] = E.toScreen(q[0], q[1]);
    return { q, x: x + c.left, y: y + c.top, id: col.id };
  });
  await page.mouse.move(t.x + 4, t.y - 3); await page.waitForTimeout(100); await page.mouse.move(t.x + 3, t.y - 3); await page.waitForTimeout(150);
  const s = await page.evaluate(() => window.__editor.S.snap);
  const d = s ? Math.hypot(s.x - t.q[0], s.y - t.q[1]) : null;
  res.snap = { col: t.id, kind: s?.kind, d_mm: d != null ? +(d * 1000).toFixed(2) : null };
  if (!s || s.kind !== 'vertex' || d > 0.001) fail(`${name}: snap ${JSON.stringify(res.snap)}`);
  res.errors = [...errors, ...(await page.evaluate(() => window.__editorErrors))];
  if (res.errors.length) fail(`${name}: console errors ${JSON.stringify(res.errors)}`);
  console.log(name, JSON.stringify(res));
  await ctx.close();
}
await browser.close(); server.close();
if (failed) process.exit(1);
console.log('editor OK');

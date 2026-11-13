// Headless test of the interactive structural plans (plans.html): desktop + phone, no console errors;
// every pile / beam of data/plans/k400.json is drawn; the K-400 pile-table row matches the pile record;
// click → card with sketches + rebar table; search; measuring 1 pile-pair distance = ITM distance (±1 mm).
// Usage: node tests/plans.mjs [--shots dir]
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
let failed = false;
const fail = (m) => { failed = true; console.error('FAIL', m); };

// ---- data checks ----
const D = JSON.parse(fs.readFileSync(path.join(root, 'data/plans/k400.json'), 'utf8'));
for (const p of D.piles) {
  const t = p.table;
  if (!t) { fail(`pile ${p.id}: no K-400 table row`); continue; }
  if (+t.load !== p.designLoad_t) fail(`pile ${p.id}: table load ${t.load} ≠ ${p.designLoad_t}`);
  if (Math.abs(parseFloat(t.top) - p.headRel) > 1e-6) fail(`pile ${p.id}: table top ${t.top} ≠ ${p.headRel}`);
  if (+t.dia !== Math.round(p.diameter_m * 100)) fail(`pile ${p.id}: table Ø ${t.dia}`);
  if (+t.minEmbed !== Math.round(p.length_m * 100)) fail(`pile ${p.id}: table L ${t.minEmbed}`);
  if (Math.abs(parseFloat(t.volume) - p.volume_m3) > 0.01) fail(`pile ${p.id}: table volume ${t.volume} ≠ ${p.volume_m3}`);
  if (!p.source) fail(`pile ${p.id}: no source`);
  if (!p.rebar.length || p.rebar.some((r) => r.kg != null && !(r.kg > 0))) fail(`pile ${p.id}: rebar rows`);
}
for (const b of D.beams) if (!b.source || !(b.length_m > 0)) fail(`beam ${b.id}: source / length`);

// ---- browser ----
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg' };
const server = http.createServer((req, res) => {
  const f = path.join(root, decodeURIComponent(req.url.split('?')[0].split('#')[0]));
  fs.readFile(f, (err, buf) => { if (err) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); res.end(buf); });
}).listen(0);
const url = `http://127.0.0.1:${server.address().port}/plans.html`;
const browser = await chromium.launch();
for (const [name, opts] of [['desktop', { viewport: { width: 1400, height: 860 } }], ['phone', devices['Pixel 7']]]) {
  const ctx = await browser.newContext(opts); const page = await ctx.newPage(); const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('requestfailed', (r) => { if (!/fonts\.(googleapis|gstatic)/.test(r.url())) errors.push('request failed: ' + r.url()); });
  await page.goto(url);
  await page.waitForFunction(() => window.__plansReady, null, { timeout: 30000 });
  const n = await page.evaluate(() => ({ piles: document.querySelectorAll('[data-key^="pile:"]').length, beams: document.querySelectorAll('[data-key^="beam:"]').length }));
  if (n.piles !== D.piles.length) fail(`${name}: drawn piles ${n.piles} ≠ ${D.piles.length}`);
  if (n.beams !== D.beams.length) fail(`${name}: drawn beams ${n.beams} ≠ ${D.beams.length}`);
  // click a pile on the plan
  // the first pile that is not covered by an overlay (legend, zoom buttons)
  const pick = await page.evaluate(() => {
    for (const c of document.querySelectorAll('[data-key^="pile:"] .shape')) {
      const r = c.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2;
      if (document.elementFromPoint(x, y)?.closest('.el') === c.parentNode) return { id: c.parentNode.dataset.key.slice(5), x, y };
    }
  });
  const p = D.piles.find((q) => q.id === pick.id);
  await page.mouse.click(pick.x, pick.y);
  await page.waitForTimeout(200);
  const card = await page.evaluate(() => ({ h: document.querySelector('#pl-card h2')?.textContent, sk: document.querySelectorAll('#pl-card .sk svg').length, rows: document.querySelectorAll('#pl-card table.rb tbody tr').length, hash: location.hash }));
  if (card.h !== 'כלונס ' + p.id) fail(`${name}: click pile ${p.id} → card "${card.h}"`);
  if (card.sk !== 2) fail(`${name}: pile sketches ${card.sk}`);
  if (card.rows !== p.rebar.length + 1) fail(`${name}: rebar rows ${card.rows}`);
  if (card.hash !== '#pile-' + p.id) fail(`${name}: hash ${card.hash}`);
  if (shotsDir) await page.screenshot({ path: path.join(shotsDir, `plans-${name}-pile.png`) });
  // search a beam
  await page.fill('#pl-q', 'B-39'); await page.press('#pl-q', 'Enter'); await page.waitForTimeout(200);
  if ((await page.textContent('#pl-card h2')) !== 'קורה B-39') fail(`${name}: search B-39`);
  // measure between pile 1 and pile 2 centres
  const d12 = await page.evaluate(() => {
    const ps = Object.fromEntries([...document.querySelectorAll('[data-key^="pile:"] .shape')].map((c) => [c.parentNode.dataset.key, c]));
    return ['pile:1', 'pile:2'].map((k) => { const r = ps[k].getBoundingClientRect(); return [r.x + r.width / 2, r.y + r.height / 2]; });
  });
  await page.click('#pl-measure');
  for (const [x, y] of d12) await page.mouse.click(x, y);
  const txt = await page.textContent('#pl-measure-out');
  const a = D.piles.find((q) => q.id === '1'), b = D.piles.find((q) => q.id === '2');
  const itm = Math.hypot(a.E - b.E, a.N - b.N), got = parseFloat(txt.replace(/[^\d.]/g, ''));
  const tol = name === 'phone' ? 0.03 : 0.015;   // screen-pixel rounding of the click
  if (!(Math.abs(got - itm) < tol)) fail(`${name}: measure 1–2 ${got} vs ITM ${itm.toFixed(3)}`);
  if (name === 'phone') {
    // real touch pinch (CDP): the sheet point under the fingers' midpoint must stay there, zoom follows the finger distance
    await page.click('#pl-measure');   // measuring off
    const cdp = await ctx.newCDPSession(page);
    const r = await page.locator('#pl-svg').boundingBox();
    const mx = r.x + r.width / 2, my = r.y + r.height / 2;
    const vb = () => page.evaluate(() => document.querySelector('#pl-svg').getAttribute('viewBox').split(' ').map(Number));
    const worldAt = (v) => [v[0] + (mx - r.x) / r.width * v[2], v[1] + (my - r.y) / r.width * v[2]];
    const v0 = await vb(); const w0 = worldAt(v0);
    const tp = (d) => [{ x: mx - d, y: my, id: 1 }, { x: mx + d, y: my, id: 2 }];
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: tp(40) });
    let prev = v0[2], monotonic = true;
    for (let d = 44; d <= 120; d += 4) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: tp(d) });
      await page.waitForTimeout(20);
      const w = (await vb())[2]; if (w > prev + 1e-6) monotonic = false; prev = w;
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForTimeout(100);
    const v1 = await vb(); const w1 = worldAt(v1);
    const ratio = v0[2] / v1[2], drift = Math.hypot(w1[0] - w0[0], w1[1] - w0[1]) / v1[2] * r.width;
    if (!(ratio > 2.7 && ratio < 3.3)) fail(`phone pinch: zoom ×${ratio.toFixed(2)} (expected ≈3)`);
    if (!monotonic) fail('phone pinch: zoom not monotonic (jumps)');
    if (drift > 3) fail(`phone pinch: anchor drift ${drift.toFixed(1)} px`);
    console.log(`phone pinch: ×${ratio.toFixed(2)}, anchor drift ${drift.toFixed(2)} px, monotonic ${monotonic}`);
  }
  const hs = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  if (hs > 0) fail(`${name}: horizontal scroll ${hs}px`);
  if (errors.length) fail(`${name}: console errors:\n  ` + errors.join('\n  '));
  console.log(`${name}: ${n.piles} piles, ${n.beams} beams, card ok, measure 1–2 = ${got} (ITM ${itm.toFixed(3)})`);
  await ctx.close();
}
await browser.close(); server.close();
if (failed) process.exit(1);
console.log('plans: OK');

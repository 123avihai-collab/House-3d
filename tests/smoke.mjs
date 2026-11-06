// Headless smoke test: serves the site, loads it (desktop + phone), fails on any console error.
// Usage: node tests/smoke.mjs [--shots dir]
import { createRequire } from 'module';
import { execSync } from 'child_process';
const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch { pw = require(execSync('npm root -g').toString().trim() + '/playwright'); }
const { chromium, devices } = pw;
import http from 'http';
import fs from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const shotsDir = process.argv.includes('--shots') ? process.argv[process.argv.indexOf('--shots') + 1] : null;
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg', '.png': 'image/png', '.hdr': 'application/octet-stream' };
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0].split('#')[0]));
  const f = p.endsWith('/') ? path.join(p, 'index.html') : p;
  fs.readFile(f, (err, buf) => { if (err) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); res.end(buf); });
}).listen(0);
const port = server.address().port;
const url = `http://127.0.0.1:${port}/index.html`;

const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
let failed = false;
const results = {};
for (const [name, opts] of [['desktop', { viewport: { width: 1500, height: 900 } }], ['phone', devices['Pixel 7']]]) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); if (m.type() === 'warning' && !/GPU stall|ReadPixels|swiftshader|Automatic fallback/i.test(m.text())) console.log(`[${name} warn]`, m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  page.on('requestfailed', r => errors.push('request failed: ' + r.url()));
  await page.goto(url);
  await page.waitForFunction(() => window.__ready === true || (window.__errors && window.__errors.length), null, { timeout: 120000 });
  await page.waitForTimeout(2500);
  const info = await page.evaluate(() => {
    const a = window.__app;
    return {
      errors: window.__errors,
      components: a.registry.items.length,
      visible: a.registry.items.filter(i => i.object.visible).length,
      layers: Object.keys(a.store.get().layers).length,
      sun: a.sun.last && { az: +a.sun.last.azimuth.toFixed(2), el: +a.sun.last.elevation.toFixed(2) },
      untagged: a.registry.items.filter(i => !i.tags.floor || !i.tags.system || !i.tags.stage).length,
    };
  });
  if (name === 'desktop') {
    // interactions: inspect, measure, note, section, undo/redo, walk
    const box = await page.locator('#viewport > canvas:not(#minimap)').boundingBox();
    const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
    await page.mouse.click(cx, cy); await page.waitForTimeout(300);
    info.inspectShown = await page.evaluate(() => !document.getElementById('info').classList.contains('hidden'));
    await page.evaluate(() => window.__app.setTool('measure'));
    await page.mouse.click(cx - 80, cy); await page.mouse.click(cx + 80, cy + 30); await page.waitForTimeout(300);
    info.measures = await page.evaluate(() => window.__app.tools.measure.items.map(i => +i.d3.toFixed(3)));
    await page.evaluate(() => window.__app.setTool('note'));
    await page.mouse.click(cx, cy + 20);
    await page.fill('.modal textarea', 'בדיקה אוטומטית'); await page.click('.modal .primary');
    info.notes = await page.evaluate(() => window.__app.store.get().notes.length);
    await page.evaluate(() => { const a = window.__app; a.store.set({ section: { ...a.store.get().section, hOn: true, hLevel: 0.2 } }); });
    info.clipPlanes = await page.evaluate(() => window.__app.viewer.renderer.clippingPlanes.length);
    await page.evaluate(() => { window.__app.store.undo(); window.__app.store.undo(); });
    info.afterUndo = await page.evaluate(() => ({ notes: window.__app.store.get().notes.length, clip: window.__app.viewer.renderer.clippingPlanes.length }));
    await page.evaluate(() => window.__app.store.redo());
    info.afterRedo = await page.evaluate(() => window.__app.store.get().notes.length);
    await page.evaluate(() => window.__app.nav.startWalk()); await page.keyboard.down('KeyW'); await page.waitForTimeout(700); await page.keyboard.up('KeyW');
    info.walkEyeAboveGround = await page.evaluate(() => { const a = window.__app; const c = a.viewer.camera.position; const g = a.nav.groundAt(c.x, c.z, c.y + 5); a.nav.stopWalk(); return g == null ? null : +(c.y - g).toFixed(3); });
    for (const t of ['layers', 'floors', 'sun', 'section', 'tools', 'nav', 'notes', 'electric', 'settings']) await page.evaluate((t) => window.__app.ui.openTab(t), t);
    info.exportOk = await page.evaluate(() => JSON.parse(window.__app.store.exportJson()).app === 'house3d-5187');
    await page.evaluate(() => { localStorage.clear(); });
    const errs2 = await page.evaluate(() => window.__errors);
    errors.push(...errs2.filter(e => !(info.errors || []).includes(e)));
  }
  errors.push(...(info.errors || []));
  results[name] = { ...info, errors };
  if (shotsDir) { fs.mkdirSync(shotsDir, { recursive: true }); await page.screenshot({ path: path.join(shotsDir, `${name}.png`) }); }
  if (errors.length) failed = true;
  await ctx.close();
}
await browser.close();
server.close();
console.log(JSON.stringify(results, null, 1));
process.exit(failed ? 1 : 0);

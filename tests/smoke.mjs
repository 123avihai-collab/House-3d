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
    // owner-change toggle: "changed" items visible with the change on, "original" with it off
    info.ownerChange = await page.evaluate(() => {
      const a = window.__app; const ids = Object.keys(a.store.get().ownerChanges || {}); if (!ids.length) return 'none';
      const vis = (show) => a.registry.items.filter(i => i.meta.variant?.show === show && i.object.visible).length;
      a.store.set({ stageIndex: a.data.tags.sequence.length - 1, ownerChanges: Object.fromEntries(ids.map(k => [k, true])) });
      const on = { changed: vis('changed'), original: vis('original') };
      a.store.set({ ownerChanges: Object.fromEntries(ids.map(k => [k, false])) });
      const off = { changed: vis('changed'), original: vis('original') };
      a.store.undo();
      return on.changed > 0 && on.original === 0 && off.changed === 0 && off.original > 0 ? 'ok' : JSON.stringify({ on, off });
    });
    if (info.ownerChange !== 'ok' && info.ownerChange !== 'none') errors.push('owner-change toggle: ' + info.ownerChange);
    // per-layer label switch: piles stay visible, their labels hide
    info.labelsOff = await page.evaluate(() => {
      const a = window.__app; a.store.set({ stageIndex: a.data.tags.sequence.findIndex(s => s.id === 'pilesBasement'), labelsOff: { piles: true } });
      const it = a.registry.items.filter(i => i.tags.layer === 'piles' && i.meta.kind === 'pile');
      let lab = 0; it.forEach(i => i.object.traverse(o => { if (o.isCSS2DObject && o.visible) lab++; }));
      const vis = it.filter(i => i.object.visible).length; a.store.undo();
      return vis > 0 && lab === 0 ? 'ok' : JSON.stringify({ vis, lab });
    });
    if (info.labelsOff !== 'ok') errors.push('labels switch: ' + info.labelsOff);
    // construction steps: ground-floor walls appear only after the ground-floor slab, the ceiling after the walls
    info.sequence = await page.evaluate(() => {
      const a = window.__app, seq = a.data.tags.sequence, idx = id => seq.findIndex(s => s.id === id);
      const vis = (layer) => a.registry.items.filter(i => i.tags.layer === layer && i.object.visible).length;
      const at = (id) => { a.store.set({ stageIndex: idx(id) }); return { slab: vis('groundSlab'), walls: vis('groundWalls'), ceil: vis('groundCeiling') }; };
      const r = { slab: at('groundSlab'), walls: at('groundWalls'), ceil: at('groundCeiling') }; a.store.undo(); a.store.undo(); a.store.undo();
      return r.slab.slab > 0 && r.slab.walls === 0 && r.walls.walls > 0 && r.walls.ceil === 0 && r.ceil.ceil > 0 ? 'ok' : JSON.stringify(r);
    });
    if (info.sequence !== 'ok') errors.push('construction sequence: ' + info.sequence);
    // load path: nothing appears before what it stands on (walls / columns -> the beam, wall or column under them; the
    // K-21 beams no later than the ground slab; every component on some step)
    info.loadPath = await page.evaluate(() => {
      const a = window.__app, R = a.registry, bad = [];
      const byId = {}; for (const it of R.items) if (it.meta.id && it.meta.kind !== 'ghost') (byId[it.meta.id] ||= []).push(it);
      const step = (it) => R.range(it.tags)[0];
      for (const it of R.items) {
        const [from, to] = R.range(it.tags);
        if (from < 0 || to < from) { if (it.meta.kind !== 'ghost' || from < 0) bad.push(`${it.meta.id || it.meta.name}: no step (${from}..${to})`); continue; }
        const on = (it.meta.rows || []).find(r => r[0] === 'יושב על')?.[1] || '';
        const m = on.match(/^(?:קורה|עמוד|קיר) ([A-Z]+-?\d+[A-Z]?)/);
        if (m && byId[m[1]]) { const s = Math.min(...byId[m[1]].map(step)); if (s > from) bad.push(`${it.meta.id} (שלב ${from}) על ${m[1]} (שלב ${s})`); }
      }
      const gs = (byId.GS1 || []).map(step)[0];
      for (const it of R.items) if (['groundFloorBeams', 'ceilingBeams'].includes(it.tags.layer) && it.meta.kind !== 'ghost' && step(it) > gs && !it.tags.step) bad.push(`${it.meta.id} after GS1`);
      return bad.length ? bad.slice(0, 12).join(' | ') : 'ok';
    });
    if (info.loadPath !== 'ok') errors.push('load path: ' + info.loadPath);
    // walk mode stands on the ground-floor slab (not in the basement below it)
    info.walk = await page.evaluate(() => {
      const a = window.__app, v = a.viewer, C = a.display.camera;
      a.store.set({ stageIndex: a.data.tags.sequence.length - 1 });
      const gs = a.data.floorGround.slab.find(s => s.id === 'GS1');
      const r = gs.footprintITM; const c = r.reduce((s, p) => [s[0] + p[0] / r.length, s[1] + p[1] / r.length], [0, 0]);
      // a point of GS1 away from walls: the centroid if it is inside, else the first vertex pulled inward
      const t = a.coords.toLocal(c[0], c[1], a.coords.H0 + gs.topRel);
      v.camera.position.set(t.x, t.y + 1.5, t.z + 0.01); v.camera.lookAt(t); v.camera.updateMatrixWorld();
      a.nav.startWalk(); const eye = v.camera.position.y - (a.coords.H0 - a.coords.H0); a.nav.stopWalk();
      const feetRel = eye - C.eyeHeight_m - (a.coords.toLocal(c[0], c[1], a.coords.H0).y);
      a.store.undo();
      return Math.abs(feetRel - gs.topRel) < 0.06 || feetRel > gs.topRel ? 'ok' : `feet ${feetRel.toFixed(2)} vs GS1 ${gs.topRel}`;
    });
    if (info.walk !== 'ok') errors.push('walk on slab: ' + info.walk);
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

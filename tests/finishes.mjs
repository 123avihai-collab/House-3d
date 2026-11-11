// Headless test of the finishes layer (src/finishes): plaster by type, waterproofing, tiling prep, room names.
// Checks: no console errors; the layer totals equal the derived data; a type override moves the area between types;
// the Excel export produces a real xlsx file. Optional screenshots: node tests/finishes.mjs --shots <dir>
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium, devices } = require('playwright');
import http from 'http';
import fs from 'fs';
import path from 'path';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const shotsDir = process.argv.includes('--shots') ? process.argv[process.argv.indexOf('--shots') + 1] : null;
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' };
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0].split('#')[0]));
  const f = p.endsWith('/') ? path.join(p, 'index.html') : p;
  fs.readFile(f, (err, buf) => { if (err) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); res.end(buf); });
}).listen(0);
const url = `http://127.0.0.1:${server.address().port}/index.html`;
const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
let failed = false;
const data = JSON.parse(fs.readFileSync(path.join(root, 'data/finishes/plaster/surfaces.json'), 'utf8'));
const want = {};
for (const s of [...data.walls, ...data.ceilings]) want[s.type] = (want[s.type] || 0) + s.net;
for (const s of [...data.tops, ...data.reveals, ...data.beams]) want[s.type] = (want[s.type] || 0) + s.area;

for (const [name, opts] of [['desktop', { viewport: { width: 1500, height: 900 }, acceptDownloads: true }], ['phone', { ...devices['Pixel 7'], acceptDownloads: true }]]) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  page.on('requestfailed', r => errors.push('request failed: ' + r.url()));
  await page.goto(url);
  await page.waitForFunction(() => window.__ready === true || (window.__errors && window.__errors.length), null, { timeout: 120000 });
  await page.waitForTimeout(1500);
  const info = await page.evaluate(() => {
    const a = window.__app, F = a.modules.finishes;
    const all = a.data.layers.groups.find(g => g.id === 'finishes').layers.map(l => l.id);
    const before = a.registry.items.length;
    a.store.set({ layers: { ...a.store.get().layers, ...Object.fromEntries(all.map(l => [l, true])) }, stageIndex: a.data.tags.sequence.length - 1 });
    const items = a.registry.items.filter(i => i.meta.kind === 'plaster');
    const shown = items.filter(i => i.object.visible).length;
    const T = F.totals();
    return { before, after: a.registry.items.length, plasterItems: items.length, shown, byType: T.byType, extras: T.extras, tiling: T.tiling,
      waterproof: a.registry.items.filter(i => i.meta.kind === 'waterproofing').length, floorLayers: a.registry.items.filter(i => i.meta.kind === 'floorLayer').length, cladding: a.registry.items.filter(i => i.meta.kind === 'cladding').length,
      offByDefault: a.data.layers.groups.filter(g => ['finishes', 'cladding'].includes(g.id)).flatMap(g => g.layers).every(l => l.visible === false),
      lastGroup: a.data.layers.groups.at(-1).id, undrawnPlaster: items.filter(i => ['plaster_membrane', 'plaster_none', 'plaster_cladding'].includes(i.tags.layer)).length,
      labels: a.registry.items.filter(i => i.meta.kind === 'room').length };
  });
  const diff = Object.entries(want).map(([k, v]) => Math.abs((info.byType[k] || 0) - v)).reduce((a, b) => Math.max(a, b), 0);
  info.maxDiff_m2 = +diff.toFixed(4);
  if (diff > 0.01) { failed = true; console.error(name, 'totals differ from data', diff); }
  // override: an interior wall face -> scratch coat, area moves between types
  const ov = await page.evaluate(async () => {
    const a = window.__app, F = a.modules.finishes;
    const s = F.surf.find(x => x.cat === 'wall' && x.type === 'interior' && x.net > 2);
    const b = F.totals().byType;
    await F.setType(s, 'exterior');
    const c = F.totals().byType;
    // pick through the triangle map
    const it = a.registry.items.find(i => i.meta.kind === 'plaster' && i.tags.layer === 'plaster_exterior' && i.tags.floor === s.floor);
    const fi = it.object.userData.faceMap.indexOf(s.key);
    it.meta.onClick({ object: it.object, faceIndex: fi, point: it.object.position });
    const shown = document.querySelector('#info h3')?.textContent || '';
    await F.setType(s, s.defaultType);
    const d = F.totals().byType;
    return { key: s.key, net: s.net, moved: +(c.exterior - (b.exterior || 0)).toFixed(3), back: +((d.interior || 0) - (b.interior || 0)).toFixed(3), info: shown };
  });
  info.override = ov;
  if (Math.abs(ov.moved - ov.net) > 0.001 || Math.abs(ov.back) > 0.001 || !ov.info.includes('טיח')) { failed = true; console.error(name, 'override failed', ov); }
  if (!info.offByDefault || info.lastGroup !== 'cladding' || info.undrawnPlaster || info.floorLayers < 4) { failed = true; console.error(name, 'layers check failed', info); }
  // panel + export
  await page.evaluate(() => window.__app.ui.openTab('finishes'));
  await page.waitForTimeout(300);
  info.panelRows = await page.evaluate(() => document.querySelectorAll('.finishes table.qty tr').length);
  if (name === 'desktop') {
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 20000 }), page.evaluate(() => window.__app.modules.finishes.exportXlsx())]);
    const fp = await dl.path(); const buf = fs.readFileSync(fp);
    info.xlsx = { name: dl.suggestedFilename(), bytes: buf.length, zip: buf.slice(0, 2).toString() === 'PK' };
    if (!info.xlsx.zip) { failed = true; console.error('xlsx export failed'); }
  }
  if (shotsDir) {
    fs.mkdirSync(shotsDir, { recursive: true });
    await page.evaluate(() => { const a = window.__app; a.ui.setPanel(false); a.ui.showInfo(null); a.modules.finishes.highlight(null); });
    const views = [['out', [-22, 16, 26], [1, 2, 3]], ['in-ground', [6, 9, 13], [-4, 0.5, 2]], ['floors', [2, 7, 9], [-5, -0.5, 3]]];
    for (const [v, pos, tgt] of views) {
      await page.evaluate(([v, pos, tgt]) => {
        const a = window.__app, fl = ['floorFill', 'floorScreed', 'floorAdhesive', 'floorTile'];
        const L = { ...a.store.get().layers }; for (const k of fl) L[k] = v === 'floors'; for (const k of Object.keys(L)) if (k.startsWith('plaster_')) L[k] = v !== 'floors';
        L.wetProofing = true; a.store.set({ layers: L });
        if (v !== 'out') { const floors = Object.fromEntries(Object.entries(a.store.get().floors).map(([k, x]) => [k, { ...x, visible: k === 'ground' }])); a.store.set({ floors, section: { ...a.store.get().section, hOn: true, hideBeams: true, hLevel: 1.3 } }); }
        a.viewer.camera.position.set(...pos); a.viewer.controls.target.set(...tgt); a.viewer.controls.update(); a.viewer.invalidate();
      }, [v, pos, tgt]);
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(shotsDir, `finishes-${name}-${v}.png`) });
    }
  }
  info.errors = errors;
  if (errors.length) failed = true;
  console.log(name, JSON.stringify(info));
  await ctx.close();
}
await browser.close(); server.close();
if (failed) { console.error('finishes test FAILED'); process.exit(1); }
console.log('finishes OK');

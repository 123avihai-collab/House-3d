// Headless test of the tiling workshop (src/tiling): mode "ריצוף", a tile per zone, layout, optimisation, quantities, export.
// Checks: no console errors; the laid tile area + the joints = the zone area; every zone of the workshop is a floor of the
// derived data; "פריסה מושלמת" never makes a zone worse; a change is drawn in 3D (tile items) and the placeholder of that
// zone goes; the Excel export is a real xlsx file. Optional screenshots: node tests/tiling.mjs --shots <dir>
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
const fail = (...a) => { failed = true; console.error(...a); };

for (const [name, opts] of [['desktop', { viewport: { width: 1500, height: 900 }, acceptDownloads: true }], ['phone', { ...devices['Pixel 7'], acceptDownloads: true }]]) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  page.on('requestfailed', r => errors.push('request failed: ' + r.url()));
  await page.goto(url);
  await page.waitForFunction(() => window.__ready === true || (window.__errors && window.__errors.length), null, { timeout: 120000 });
  await page.waitForTimeout(1000);
  const info = await page.evaluate(async () => {
    const a = window.__app, W = a.modules.finishes.tiling;
    try { localStorage.removeItem('house3d.tiling'); } catch {}
    for (const z of W.zones) if (W.choice[z.key]) await W.setChoice(z.key, null, { rebuild: false });
    a.store.set({ mode: 'tiling' }, { label: 'mode' });
    const r = { zones: W.zones.length, tab: a.ui.tab, tileOn: a.store.get().layers.floorTile, placeholder0: a.registry.items.filter(i => i.meta.kind === 'floorLayer' && i.tags.layer === 'floorTile').length };
    // every zone: 60×60, then the best layout; area check
    const out = [];
    for (const z of W.zones) {
      await W.setChoice(z.key, { size: '60x60', finish: 'lightGrey' }, { rebuild: false });
      const L0 = W.layout(z.key);
      const o = W.optimizeZone(z.key);
      await W.setChoice(z.key, { du_cm: o.du_cm, dv_cm: o.dv_cm }, { rebuild: false });
      const L1 = W.layout(z.key);
      const j = L1.tile.j;
      out.push({ key: z.key, area: z.r.area, laid: L1.stats.zoneArea_m2, tiles: L1.stats.tileArea_m2, before: L0.stats.score, after: L1.stats.score, slivers0: L0.q.slivers, slivers1: L1.q.slivers, order: L1.q.order, layTiles: L1.q.layTiles, j });
    }
    W.rebuild(); W.refresh();
    r.out = out;
    // followers (OC-13 walkway – the floor of the room it opens from): own tile item, shown only with the proposal (plan mode – hidden),
    // laid on the leader's frame from the leader's start – the joints continue (start difference = whole tile modules)
    r.followers = W.followers.map(f => { const L = W.followLayout(f), M = W.layout(f.follow); if (!L || !M) return { key: f.key, none: true };
      const mu = M.tile.L + M.tile.j, mv = M.tile.W + M.tile.j, du = (L.start[0] - M.start[0]) / mu, dv = (L.start[1] - M.start[1]) / mv;
      return { key: f.key, sameFrame: L.frame === M.frame, grid: Math.abs(du - Math.round(du)) < 1e-6 && Math.abs(dv - Math.round(dv)) < 1e-6, pieces: L.pieces.length,
        item: a.registry.items.some(i => i.meta.kind === 'tiles' && i.meta.variant?.change && i.meta.name.includes(f.name)) }; });
    const nf = r.followers.filter(f => !f.none).length;
    r.tileItems = a.registry.items.filter(i => i.meta.kind === 'tiles').length - nf;
    r.visibleTiles = a.registry.items.filter(i => i.meta.kind === 'tiles' && i.object.visible).length;
    r.placeholder1 = a.registry.items.filter(i => i.meta.kind === 'floorLayer' && i.tags.layer === 'floorTile').length;
    r.panelRows = document.querySelectorAll('#panel .tiling tr.zone-row').length;
    r.plan = !!document.querySelector('#panel .tiling svg.tile-plan polygon');
    const T = W.totals(); r.order = T.order.map(o => [o.size, o.order, o.boxes]); r.totalArea = +T.area.toFixed(3);
    // a pattern / size change: the counts change, the area stays
    const k = W.zones.find(z => z.r.area > 50).key;
    await W.setChoice(k, { size: '60x120', pattern: 'half' });
    r.big = { area: +W.layout(k).stats.zoneArea_m2.toFixed(3), tiles: W.layout(k).q.layTiles };
    // a real product (catalog.products): size, thickness, tiles per box and finish together
    const P = W.products[0];
    if (P) {
      const k2 = W.zones.find(z => z.key !== k).key;
      await W.setChoice(k2, { product: P.id, size: P.id, finish: P.id });
      const L = W.layout(k2);
      r.product = { size: L.size.label, l: L.size.l_m, w: L.size.w_m, t: L.size.thick_m, perBox: L.q.perBox, boxM2: +(L.q.perBox * L.size.l_m * L.size.w_m).toFixed(3), want: P.box_m2, fin: !!W.finBy[P.id] };
      if (L.size.l_m !== P.l_m || L.size.w_m !== P.w_m || L.size.thick_m !== P.thick_m || Math.abs(r.product.boxM2 - P.box_m2) > 1e-6 || !r.product.fin) r.productFail = true;
      await W.setChoice(k2, { size: '60x60', finish: 'lightGrey', product: '' });
    }
    // exterior paving (data/finishes/tiling/exterior.json): the tile top passes through every permit spot (±1 mm),
    // the stack under it = the build-up, the tiles of an outdoor zone sit on the extTile layer
    const H0 = a.modules.finishes.ctx.coords.H0, EXR = a.modules.finishes.EX?.rooms || [];
    r.ext = { zones: W.zones.filter(z => z.r.outdoor).length, want: EXR.length, bad: [] };
    // tiled hatches (src/tiling/hatches.js): built, a click opens the lid to the product's angle (tiles attached), again – closed
    const HZ = a.modules.finishes.hatches;
    if (HZ) { a.store.set({ layers: { ...a.store.get().layers, poolHatches: true } }, { label: 'layers' });
      const ids = Object.keys(HZ.lids), L = HZ.lids[ids[0]]; L.t = 1; HZ.pose(ids[0]);
      const ang = 2 * Math.acos(Math.min(1, Math.abs(L.lid.quaternion.w))) * 180 / Math.PI;
      r.hatch = { n: ids.length, items: a.registry.items.filter(i => i.meta.kind === 'hatch').length, ang: +ang.toFixed(2), want: HZ.P.openAngle_deg, attached: L.objs.size };
      L.t = 0; HZ.pose(ids[0]); r.hatch.closed = +(2 * Math.acos(Math.min(1, Math.abs(L.lid.quaternion.w))) * 180 / Math.PI).toFixed(3);
      // the panel buttons (a tap in the model on the lid's tiles does the same): open – the animation – closed again
      W.refresh(); const b = document.querySelector('#panel .tiling [data-act="hatch-' + ids[0] + '"]'); r.hatch.button = !!b;
      if (b) { b.click(); await new Promise(res => setTimeout(res, (HZ.D.openMs ?? 1400) + 300)); r.hatch.byButton = +L.t.toFixed(3); HZ.toggle(ids[0]); await new Promise(res => setTimeout(res, (HZ.D.openMs ?? 1400) + 300)); r.hatch.closedAgain = +L.t.toFixed(3); } }
    for (const z of W.zones.filter(z => z.r.outdoor && !z.r.hatch && !z.r.stairLanding)) {
      for (const sp of z.r.spots) { const d = z.zTop(sp.E, sp.N) - (sp.z - H0); const rs = (z.r.raisedSpots || []).find(x => x.handle === sp.handle);
        // a spot inside a raised piece (concrete too high for the permit level – listed in raisedSpots): the finish = the raised level
        if (rs ? Math.abs(z.zTop(sp.E, sp.N) - (rs.raisedTo - H0)) > 0.001 : Math.abs(d) > 0.001) r.ext.bad.push([z.key, sp.handle, +d.toFixed(4)]); }
      const tl = z.r.layers.find(l => l.id === 'extTile'), st = z.r.layers.reduce((a2, l) => a2 + (l.dz0 != null ? l.thickness_m : 0), 0);
      if (Math.abs(tl.dz1) > 1e-6 || Math.abs(st + z.r.layers.find(l => l.id === 'extFill').dz1) > 1e-6) r.ext.bad.push([z.key, 'stack']);
    }
    r.ext.tileLayer = a.registry.items.filter(i => i.meta.kind === 'tiles' && i.tags.layer === 'extTile').length;
    // tiled outdoor stairs (exterior.json stairs): one item per stair, a piece on every tread and riser, the finish on the source levels
    const ST = a.modules.finishes.EX?.stairs || [];
    r.stairs = ST.map(S => ({ id: S.id, item: a.registry.items.some(i => i.meta.kind === 'stairTiles' && i.meta.id === 'stairTiles-' + S.id), n: S.pieces.length, want: S.treads + S.risers,
      top: Math.max(...S.pieces.map(p => p.z1)), srcTop: Math.max(...S.finishProfile.map(p => p[1])) }));
    // shared joint grid (catalog.gridGroups.ext): all the outdoor zones + balconies in one grid – one start point in plan
    // (continuous joints), a change in one member applies to all, the joint optimisation never makes the group worse
    const gk = W.zones.filter(z => z.r.outdoor || z.r.roomType === 'balcony').map(z => z.key);
    for (const k of gk) await W.setChoice(k, { grid: 'ext' }, { rebuild: false });
    await W.setChoice(gk[0], { size: '60x120', direction: 'across' }, { rebuild: false });
    const st = () => new Set(gk.map(k => { const L = W.layout(k); return L.frame.toWorld(L.start).map(v => v.toFixed(4)).join(','); }));
    const sc = () => gk.reduce((s2, k) => s2 + W.layout(k).stats.score, 0);
    const s0 = sc(), o = W.optimizeZone(gk[0]); await W.setChoice(gk[0], { du_cm: o.du_cm, dv_cm: o.dv_cm }, { rebuild: false });
    r.grid2 = { members: gk.length, starts: st().size, same: gk.every(k => W.choice[k].size === '60x120' && W.choice[k].du_cm === o.du_cm), better: sc() <= s0 + 1e-9 };
    for (const k of gk) await W.setChoice(k, { grid: '' }, { rebuild: false });
    r.ext.changeMarks = a.registry.items.filter(i => i.meta.kind === 'changeMark').length; r.ext.changeWant = EXR.filter(x => x.change).length;
    for (const x of EXR) if (x.surface?.minZ != null && x.check.fillMin_m < x.check.minFill_m - 1e-6) r.ext.bad.push([x.room, 'below K-21 minimum']);
    W.select(k);
    // "הצג חלוקה": the button in the panel, one shared uniform (no rebuild), back off
    const items0 = a.registry.items.filter(i => i.meta.kind === 'tiles').length;
    document.querySelector('#panel .tiling [data-act="grid"]')?.click();
    r.grid = { on: W.gridU.value, items: a.registry.items.filter(i => i.meta.kind === 'tiles').length === items0, label: document.querySelector('#panel .tiling [data-act="grid"]')?.textContent || '' };
    W.setGrid(false); r.grid.off = W.gridU.value;
    return r;
  });
  for (const z of info.out) {
    const d = Math.abs(z.laid - z.area);
    if (d > Math.max(0.02, z.area * 5e-4)) fail(name, 'zone area differs from the data', z.key, z.laid, z.area);
    if (z.tiles > z.laid + 1e-6 || z.tiles < z.laid * 0.97) fail(name, 'tile area out of range', z);
    if (z.after > z.before + 1e-9) fail(name, 'optimise made it worse', z);
    if (z.order < z.layTiles) fail(name, 'order below the layout', z);
  }
  if (info.tab !== 'tiling' || !info.tileOn || info.tileItems !== info.zones || info.visibleTiles !== info.zones || info.placeholder1 >= info.placeholder0 && info.placeholder0 > 0 && info.zones > 0 && info.placeholder1 !== 0 || !info.plan || info.panelRows !== info.zones)
    fail(name, 'workshop check failed', { ...info, out: undefined });
  if (info.followers.some(f => !f.none && (!f.sameFrame || !f.grid || !f.pieces || !f.item))) fail(name, 'follower (OC-13 walkway) tiles not on the leader grid', info.followers);
  if (!info.grid || info.grid.on !== 1 || info.grid.off !== 0 || !info.grid.items || !info.grid.label.includes('חלוקה')) fail(name, 'grid toggle failed', info.grid);
  if (info.productFail) fail(name, 'product does not match the catalog', info.product);
  if (!info.ext || info.ext.zones !== info.ext.want || info.ext.want < 1 || info.ext.bad.length || info.ext.tileLayer !== info.ext.zones || info.ext.changeMarks !== info.ext.changeWant || !info.grid2 || info.grid2.starts !== 1 || !info.grid2.same || !info.grid2.better || info.grid2.members < 8 || !info.stairs?.length || info.stairs.some(s => !s.item || s.n !== s.want || Math.abs(s.top - s.srcTop) > 1e-6) || !info.hatch || info.hatch.n !== 2 || info.hatch.items !== 2 || Math.abs(info.hatch.ang - info.hatch.want) > 0.01 || info.hatch.closed > 0.001 || !info.hatch.button || info.hatch.byButton !== 1 || info.hatch.closedAgain !== 0) fail(name, 'exterior paving check failed', info.ext);
  // pool tiling + coping (src/tiling/pool.js): drawn, quantities = the derived areas, a change rebuilds, coping covers the walls
  const pool = await page.evaluate(async () => {
    const a = window.__app, P = a.modules.finishes.pool; if (!P) return { missing: true };
    try { localStorage.removeItem('house3d.poolTiling'); } catch {}
    await P.set(null);
    a.store.set({ layers: { ...a.store.get().layers, poolTile: true, poolCoping: true } }, { label: 'layers' });
    const kinds = () => a.registry.items.filter(i => ['poolTiles', 'poolCoping'].includes(i.meta.kind));
    const r = { items0: kinds().length, visible0: kinds().filter(i => i.object.visible).length, panel: !!document.querySelector('#panel .pool-ed') };
    const S = P.S, q = P.quantities();
    r.q = { floor: q.floor, walls: q.walls, steps: q.steps, total: q.total, wallH: q.wallH };
    r.wallExpect = S.areas.perimeterInner_m * (S.copingTop - P.c.coping.thick_m - S.floor) - S.areas.wallCoveredByBlocks_m2;
    // coping: the runs cover the perimeter of the wall tops (long sides over the corners)
    const cp = P.copingPieces(), wt = S.wallThickness_m, oh = P.c.coping.overhang_m;
    // mitre corners (default): each side's outer edge = inner side + 2 × wall (− the corner joints); centre-line length of the coping
    r.copLen = cp.runs.reduce((s, x) => s + x.len, 0);
    r.copExpect = S.innerSides_m.reduce((s, L) => s + L + 2 * wt - P.c.coping.joint_mm / 1000 * Math.SQRT2, 0);
    r.centre = P.quantities().coping.len_m; r.centreExpect = S.innerSides_m.reduce((s, L) => s + L, 0) + 4 * (wt - oh);
    r.planSvg = !!document.querySelector('#panel .coping-plan polygon') && document.querySelectorAll('#panel .coping-strip').length === 4;
    r.cutRows = document.querySelectorAll('#panel .coping-ed table')[1]?.querySelectorAll('tr').length || 0;
    r.pieces = cp.pieces.length; r.maxPiece = Math.max(...cp.runs.map(x => x.piece_m));
    await P.set({ tile: 'porc3060', color: 'white', coping: { material: 'basalt', length_m: 1.0, edge: 'square' } });
    r.items1 = kinds().length; r.pieces1 = P.copingPieces().pieces.length; r.tile1 = P.c.tile;
    await P.set(null);
    return r;
  });
  if (pool.missing || pool.items0 !== 5 || pool.visible0 !== 5 || !pool.panel || pool.items1 !== 5 || pool.tile1 !== 'porc3060' || pool.pieces1 >= pool.pieces
    || Math.abs(pool.q.walls - pool.wallExpect) > 1e-6 || Math.abs(pool.q.total - pool.q.floor - pool.q.walls - pool.q.steps) > 1e-6 || Math.abs(pool.copLen - pool.copExpect) > 2e-3 || pool.maxPiece > 0.6 + 1e-9 || Math.abs(pool.centre - pool.centreExpect) > 0.02 || !pool.planSvg || pool.cutRows < 3)
    fail(name, 'pool tiling check failed', pool);
  // export
  const dl = page.waitForEvent('download', { timeout: 20000 }).catch(() => null);
  await page.evaluate(() => window.__app.modules.finishes.tiling.exportXlsx());
  const d = await dl;
  let xlsx = 0;
  if (d) { const p = await d.path(); const buf = fs.readFileSync(p); xlsx = buf.length; if (buf[0] !== 0x50 || buf[1] !== 0x4b) fail(name, 'export is not an xlsx'); } else fail(name, 'no export download');
  if (shotsDir) {
    fs.mkdirSync(shotsDir, { recursive: true });
    await page.evaluate(() => { const W = window.__app.modules.finishes.tiling; W.showZone(W.sel); });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(shotsDir, `tiling-${name}.png`) });
    await page.evaluate(() => { const a = window.__app; a.ui.setPanel(false); a.viewer.invalidate(); });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(shotsDir, `tiling-${name}-3d.png`) });
  }
  const sl0 = info.out.reduce((a, z) => a + z.slivers0, 0), sl1 = info.out.reduce((a, z) => a + z.slivers1, 0);
  console.log(name, JSON.stringify({ zones: info.zones, tileItems: info.tileItems, followers: info.followers, placeholder: [info.placeholder0, info.placeholder1], slivers: [sl0, sl1], area: info.totalArea, order: info.order, big: info.big, product: info.product, ext: info.ext, grid2: info.grid2, hatch: info.hatch, stairs: info.stairs, xlsx, pool: { items: pool.items0, total: pool.q?.total, pieces: pool.pieces } }));
  const errs = errors.filter(e => !/favicon/.test(e));
  if (errs.length) fail(name, 'console errors', errs.slice(0, 5));
  await ctx.close();
}
await browser.close();
server.close();
if (failed) { console.error('tiling: FAILED'); process.exit(1); }
console.log('tiling: OK');

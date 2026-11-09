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
    // measure snap: the longest straight edge of a roof parapet (K-41), clicked 6 px beside its corners, must snap to both
    // corners and give the source length (data/structure/floor-roof.json footprintITM) within 1 mm
    info.measureSnap = await (async () => {
      const t = await page.evaluate(() => {
        const a = window.__app, C = a.coords; let best = null;
        for (const w of a.data.floorRoof.walls) { const r = w.footprintITM; for (let i = 0; i < r.length; i++) { const P = r[i], Q = r[(i + 1) % r.length]; const L = Math.hypot(Q[0] - P[0], Q[1] - P[1]); if (!best || L > best.L) best = { L, P, Q, top: w.topRel }; } }
        const pa = C.toLocal(best.P[0], best.P[1], C.H0 + best.top), pb = C.toLocal(best.Q[0], best.Q[1], C.H0 + best.top), c = pa.clone().lerp(pb, 0.5);
        a.store.set({ stageIndex: a.data.tags.sequence.length - 1 }, { record: false });
        a.viewer.controls.target.copy(c); a.viewer.camera.position.set(c.x + 6, c.y + 14, c.z + 9); a.viewer.controls.update(); a.viewer.camera.updateMatrixWorld(); a.viewer.invalidate();
        a.setTool('measure'); const m = a.tools.measure; m.clearAll(); m.setOpt('snap', true); m.setOpt('ortho', false);
        const el = a.viewer.renderer.domElement.getBoundingClientRect();
        const sc = (v) => { const s = m.snapper.toScreen(v); return [s.x + el.left, s.y + el.top]; };
        return { L: best.L, pts: [sc(pa), sc(pb)] };
      });
      await page.waitForTimeout(600);
      for (const [x, y] of t.pts) { await page.mouse.move(x + 6, y - 6); await page.waitForTimeout(80); await page.mouse.click(x + 6, y - 6); await page.waitForTimeout(150); }
      const r = await page.evaluate(() => { const it = window.__app.tools.measure.items[0]; return it && { d3: it.d3, k: it.ka + '/' + it.kb, dy: it.dy }; });
      await page.evaluate(() => { window.__app.tools.measure.clearAll(); window.__app.setTool('inspect'); });
      return r && Math.abs(r.d3 - t.L) < 0.001 && r.k === 'vertex/vertex' ? 'ok' : JSON.stringify({ src: t.L, r });
    })();
    if (info.measureSnap !== 'ok') errors.push('measure snap: ' + info.measureSnap);
    // smart measure (Avihai 09.11): a wall off the house axes (PW3, 4.9°) – corner to corner in "element" axes = its length
    // along itself (named "אורך", width ~0), and 📦 element box = length × thickness × height of the source
    info.measureElement = await (async () => {
      const t = await page.evaluate(() => {
        const a = window.__app, C = a.coords; const w = a.data.perimeter.walls.find(x => x.id === 'PW3'); const r = w.ringITM;
        let b = null; for (let i = 0; i < r.length; i++) { const P = r[i], Q = r[(i + 1) % r.length]; const L = Math.hypot(Q[0] - P[0], Q[1] - P[1]); if (!b || L > b.L) b = { L, P, Q }; }
        const pa = C.toLocal(b.P[0], b.P[1], C.H0 + w.topRel), pb = C.toLocal(b.Q[0], b.Q[1], C.H0 + w.topRel), c = pa.clone().lerp(pb, 0.5);
        a.store.set({ stageIndex: a.data.tags.sequence.length - 1 }, { record: false });
        a.viewer.controls.target.copy(c); a.viewer.camera.position.set(c.x - 9, c.y + 12, c.z + 8); a.viewer.controls.update(); a.viewer.camera.updateMatrixWorld(); a.viewer.invalidate();
        a.setTool('measure'); const m = a.tools.measure; m.clearAll(); m.setOpt('snap', true); m.setOpt('ortho', false); m.setOpt('axes', 'element');
        const el = a.viewer.renderer.domElement.getBoundingClientRect(); const sc = (v) => { const s = m.snapper.toScreen(v); return [s.x + el.left, s.y + el.top]; };
        const item = a.registry.items.find(i => i.meta.id === 'PW3' || /PW3/.test(i.meta.name || ''));
        return { L: b.L, pts: [sc(pa), sc(pb)], th: w.thickness_m, h: w.topRel - w.bottomRel, hasItem: !!item };
      });
      await page.waitForTimeout(600);
      // 5 px from each corner towards the other one (along the wall top)
      const [[x0, y0], [x1, y1]] = t.pts; const L = Math.hypot(x1 - x0, y1 - y0) || 1; const ux = (x1 - x0) / L * 5, uy = (y1 - y0) / L * 5;
      for (const [x, y] of [[x0 + ux, y0 + uy], [x1 - ux, y1 - uy]]) { await page.mouse.move(x, y); await page.waitForTimeout(80); await page.mouse.click(x, y); await page.waitForTimeout(150); }
      const r = await page.evaluate(() => { const m = window.__app.tools.measure; const it = m.items[0]; return it && { what: it.what, first: m.items[0]?.A, dx: Math.abs(it.dx), dy: Math.abs(it.dy), d3: it.d3, k: it.ka + '/' + it.kb }; });
      const bx = await page.evaluate(() => { const a = window.__app, m = a.tools.measure; const item = a.registry.items.find(i => i.meta.id === 'PW3' || /PW3/.test(i.meta.name || ''));
        let mesh = null; item.object.traverse(o => { if (!mesh && o.isMesh) mesh = o; }); m.measureElement({ object: mesh }); const it = m.items[m.items.length - 1];
        const res = it?.box && { l: it.box.l, w: it.box.w, h: it.box.h }; m.clearAll(); m.setOpt('axes', 'element'); a.setTool('inspect'); return res; });
      const ok = r && r.what === 'אורך' && Math.abs(r.dx - t.L) < 0.001 && r.dy < 0.001 && bx && Math.abs(bx.l - t.L) < 0.005 && Math.abs(bx.w - t.th) < 0.005;
      return ok ? 'ok' : JSON.stringify({ src: { L: t.L, th: t.th, h: t.h }, r, bx });
    })();
    if (info.measureElement !== 'ok') errors.push('measure element: ' + info.measureElement);
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
    // mamad (data/architecture/mamad.json): a real click on the window opens it – each steel leaf slides its full travel into
    // its niche inside the wall; the sliding door leaf moves its travel along the wall; a second click closes both
    info.mamad = await (async () => {
      const prep = await page.evaluate(() => {
        const a = window.__app, M = a.data.mamad, W = M.window; a.setTool('inspect');
        const P = (u, v) => a.coords.xz(W.originITM[0] + W.uITM[0] * u + W.vITM[0] * v, W.originITM[1] + W.uITM[1] * u + W.vITM[1] * v);
        const [x, z] = P(0.25, 0.03), [cx, cz] = P(0.45, 2.5);
        a.viewer.controls.target.set(x, 1.6, z); a.viewer.camera.position.set(cx, 1.7, cz); a.viewer.controls.update(); a.viewer.camera.updateMatrixWorld();
        const v = new a.viewer.camera.position.constructor(x, 1.6, z).project(a.viewer.camera), r = a.viewer.renderer.domElement.getBoundingClientRect();
        return { px: [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height], sleeves: a.registry.items.filter(i => i.tags.layer === 'mamadSleeves').length, want: M.sleeves.length };
      });
      if (prep.sleeves !== prep.want || !prep.want) return `sleeves ${prep.sleeves} / ${prep.want}`;
      const pos = () => page.evaluate(() => { const a = window.__app, f = (id) => a.registry.items.find(i => i.meta.id === id);
        const w = f('G09-leaves').object.children.filter(o => o.userData.keep).map(o => o.position.toArray()), d = f('G21-leaf').object.children[0].position.toArray();
        return { w, d, st: [f('G09-leaves').meta.toggleState(), f('G21-leaf').meta.toggleState()] }; });
      const p0 = await pos();
      await page.waitForTimeout(600); await page.mouse.click(prep.px[0], prep.px[1]);
      await page.evaluate(() => window.__app.registry.items.find(i => i.meta.id === 'G21' && i.tags.layer === 'mamadFrames').meta.onClick());   // via the cast frame
      await page.waitForFunction(() => { const a = window.__app; return a.registry.items.filter(i => i.tags.layer === 'mamadLeaves').every(i => i.meta.toggleState() === 1 && i.meta.toggleSettled()); }, null, { timeout: 90000 }).catch(() => {});
      const p1 = await pos(), T = await page.evaluate(() => ({ w: window.__app.data.mamad.window.leaves.map(l => l.travel_m), d: window.__app.data.mamad.door.leaf.travel_m }));
      const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
      if (p1.st.join() !== '1,1') return 'not opened by the click: ' + p1.st.join();
      for (let i = 0; i < 2; i++) if (Math.abs(dist(p0.w[i], p1.w[i]) - T.w[i]) > 0.001) return `window leaf ${i} moved ${dist(p0.w[i], p1.w[i]).toFixed(3)} / ${T.w[i]}`;
      if (Math.abs(dist(p0.d, p1.d) - T.d) > 0.001) return `door leaf moved ${dist(p0.d, p1.d).toFixed(3)} / ${T.d}`;
      await page.evaluate(() => window.__app.registry.items.filter(i => i.tags.layer === 'mamadLeaves').forEach(i => i.meta.onClick()));
      await page.waitForFunction(() => window.__app.registry.items.filter(i => i.tags.layer === 'mamadLeaves').every(i => i.meta.toggleSettled()), null, { timeout: 90000 }).catch(() => {});
      const p2 = await pos();
      if (dist(p0.w[0], p2.w[0]) > 0.001 || dist(p0.d, p2.d) > 0.001) return 'did not close back';
      await page.evaluate(() => document.getElementById('info').classList.add('hidden'));
      return 'ok';
    })();
    if (info.mamad !== 'ok') errors.push('mamad open / close: ' + info.mamad);
    // house map: a plan per floor, a click on the ground slab starts walk mode there; a click while walking opens the inspect card
    info.mapWalk = await (async () => {
      const r = await page.evaluate(() => {
        const a = window.__app, mm = a.minimap; if (!mm || mm.mode !== 'house' || mm.plans.length < 3) return { err: 'plans ' + (mm?.plans.length) };
        const gs = a.data.floorGround.slab.find(s => s.id === 'GS1').footprintITM; const c = gs.reduce((s, q) => [s[0] + q[0] / gs.length, s[1] + q[1] / gs.length], [0, 0]);
        const [x, z] = a.coords.xz(c[0], c[1]); const [px, py] = mm.toPx(x, z); const back = mm.toWorld(px, py);
        if (Math.hypot(back[0] - x, back[1] - z) > 1e-6) return { err: 'map px <-> world' };
        document.getElementById('info').classList.add('hidden'); a.setTool('inspect');
        return { ok: a.nav.walkAt(x, z, 0), walking: a.nav.walking };
      });
      if (!r.ok || !r.walking) return JSON.stringify(r);
      await page.waitForTimeout(300);
      const box = await page.locator('#viewport > canvas:not(#minimap)').boundingBox();
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2 + 40); await page.waitForTimeout(300);
      const shown = await page.evaluate(() => { const v = !document.getElementById('info').classList.contains('hidden'); window.__app.nav.stopWalk(); return v; });
      return shown ? 'ok' : 'no inspect card while walking';
    })();
    if (info.mapWalk !== 'ok') errors.push('map walk: ' + info.mapWalk);
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

// Headless test of editing in the 2D pipe editor (stage 2): straighten → drag segment (parallel, ends fixed) → drag
// corner (ortho kept) → undo / redo → add / delete corner → property → slope → new pipe → reload keeps the edits.
// Outside claude.ai the edits live in localStorage, so a reload in the same context must restore them.
import { createRequire } from 'module';
import { execSync } from 'child_process';
import http from 'http';
import fs from 'fs';
import path from 'path';
const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch { pw = require(execSync('npm root -g').toString().trim() + '/playwright'); }
const { chromium } = pw;
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  const f = path.join(root, decodeURIComponent(req.url.split('?')[0]));
  fs.readFile(f, (err, buf) => { if (err) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); res.end(buf); });
}).listen(0);
const url = `http://127.0.0.1:${server.address().port}/editor.html?floor=ground`;
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 860 } });
const page = await ctx.newPage(); const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
let failed = false; const res = {};
const check = (name, ok, info) => { res[name] = ok ? 'ok' : info; if (!ok) { failed = true; console.error('FAIL', name, JSON.stringify(info)); } };
const ready = async () => { await page.waitForFunction(() => window.__editorReady || (window.__editorErrors || []).length, null, { timeout: 60000 }); };
await page.goto(url); await ready();

// pick the ground-floor cold run with most stations, select it, zoom on it
const RID = await page.evaluate(() => {
  const E = window.__editor; let best = null;
  for (const it of E.current().items) if (it.p.layer === 'prop' && it.p.system === 'cold' && it.mode === 'plan') { const n = E.stOf(it.p).length; if (!best || n > best.n) best = { n, p: it.p }; }
  E.S.sel = { type: 'pipe', obj: best.p, vtx: null, seg: null }; E.showInfo(E.S.sel); return best.p.id;
});
const orig = await page.evaluate((id) => window.__editor.store.get(id).vertices, RID);
const axisOK = (V, fr) => page.evaluate(([id]) => { const E = window.__editor, st = E.stOf(E.current().items.find(i => i.p.id === id && i.p.layer === 'prop').p); return st.slice(1).every((q, i) => E.OP.isAxisAligned(st[i], q, E.cfg.edit.axisEps_deg)); }, [V]);

// 1. straighten (button) – every segment on the house axes, both ends unchanged
await page.click('#pf-ortho'); await page.waitForTimeout(100);
const v1 = await page.evaluate((id) => window.__editor.store.get(id).vertices, RID);
check('ortho', (await axisOK(RID)) && JSON.stringify(v1[0]) === JSON.stringify(orig[0]) && JSON.stringify(v1.at(-1)) === JSON.stringify(orig.at(-1)), { n: v1.length });

// 2. drag the longest interior segment 40 px across: it moves parallel by 40/k m, run ends stay
const seg = await page.evaluate((id) => {
  const E = window.__editor, p = E.current().items.find(i => i.p.id === id && i.p.layer === 'prop').p, st = E.stOf(p);
  let b = null; for (let i = 1; i + 2 < st.length; i++) { const L = Math.hypot(st[i + 1].x - st[i].x, st[i + 1].y - st[i].y); if (!b || L > b.L) b = { i, L }; }
  if (!b) for (let i = 0; i + 1 < st.length; i++) { const L = Math.hypot(st[i + 1].x - st[i].x, st[i + 1].y - st[i].y); if (!b || L > b.L) b = { i, L }; }
  const a = st[b.i], c = st[b.i + 1], m = [(a.x + c.x) / 2, (a.y + c.y) / 2];
  E.v.cx = m[0]; E.v.cy = m[1]; E.v.k = 120; E.setFloor('ground', false); E.S.sel = { type: 'pipe', obj: p, vtx: null, seg: null }; E.showInfo(E.S.sel);
  const rc = document.getElementById('ed-canvas').getBoundingClientRect(), [sx, sy] = E.toScreen(...m);
  const horiz = Math.abs(c.y - a.y) < Math.abs(c.x - a.x);
  E.S.snapOn = false;
  return { i: b.i, x: sx + rc.left, y: sy + rc.top, horiz, a, c, k: E.v.k, n: st.length };
}, RID);
await page.mouse.move(seg.x, seg.y); await page.mouse.down();
for (let t = 1; t <= 8; t++) await page.mouse.move(seg.x + (seg.horiz ? 0 : 5 * t), seg.y + (seg.horiz ? -5 * t : 0));
await page.mouse.up(); await page.waitForTimeout(150);
const after2 = await page.evaluate(([id, i]) => { const E = window.__editor, p = E.current().items.find(x => x.p.id === id && x.p.layer === 'prop').p, st = E.stOf(p); return { st: st.map(q => [q.x, q.y]), V: E.store.get(id).vertices }; }, [RID, seg.i]);
const want = 40 / seg.k;
const movedIdx = after2.st.findIndex(q => Math.abs((seg.horiz ? q[1] - seg.a.y : q[0] - seg.a.x) - want) < 0.002 && Math.abs((seg.horiz ? q[0] - seg.a.x : q[1] - seg.a.y)) < 0.002);
check('dragSegment', movedIdx >= 0 && JSON.stringify(after2.V[0]) === JSON.stringify(v1[0]) && JSON.stringify(after2.V.at(-1)) === JSON.stringify(v1.at(-1)) && (await axisOK(RID)), { movedIdx, want });

// 3. undo ×2 → original, redo ×2 → back to the dragged route
await page.keyboard.press('Control+z'); await page.keyboard.press('Control+z'); await page.waitForTimeout(100);
const u = await page.evaluate((id) => window.__editor.store.get(id).vertices, RID);
await page.keyboard.press('Control+y'); await page.keyboard.press('Control+y'); await page.waitForTimeout(100);
const r = await page.evaluate((id) => window.__editor.store.get(id).vertices, RID);
check('undoRedo', JSON.stringify(u) === JSON.stringify(orig) && JSON.stringify(r) === JSON.stringify(after2.V), {});

// 4. drag an interior corner (ortho): neighbours stay on the axes
const cor = await page.evaluate((id) => {
  const E = window.__editor, p = E.current().items.find(i => i.p.id === id && i.p.layer === 'prop').p, st = E.stOf(p);
  const i = Math.max(1, Math.floor(st.length / 2)); const q = st[i]; E.v.cx = q.x; E.v.cy = q.y; E.setFloor('ground', false);
  E.S.sel = { type: 'pipe', obj: p, vtx: null, seg: null }; E.showInfo(E.S.sel);
  const rc = document.getElementById('ed-canvas').getBoundingClientRect(), [sx, sy] = E.toScreen(q.x, q.y); return { i, x: sx + rc.left, y: sy + rc.top };
}, RID);
await page.mouse.move(cor.x, cor.y); await page.mouse.down();
for (let t = 1; t <= 6; t++) await page.mouse.move(cor.x + 4 * t, cor.y + 3 * t);
await page.mouse.up(); await page.waitForTimeout(150);
const v4 = await page.evaluate((id) => window.__editor.store.get(id).vertices, RID);
check('dragCorner', (await axisOK(RID)) && JSON.stringify(v4[0]) === JSON.stringify(v1[0]) && JSON.stringify(v4.at(-1)) === JSON.stringify(v1.at(-1)) && JSON.stringify(v4) !== JSON.stringify(r), {});

// 5. double-click on a segment adds a corner; Delete removes it
const ins = await page.evaluate((id) => {
  const E = window.__editor, p = E.current().items.find(i => i.p.id === id && i.p.layer === 'prop').p, st = E.stOf(p);
  let b = 0, bl = 0; for (let i = 0; i + 1 < st.length; i++) { const L = Math.hypot(st[i + 1].x - st[i].x, st[i + 1].y - st[i].y); if (L > bl) { bl = L; b = i; } }
  const m = [(st[b].x + st[b + 1].x) / 2 + (st[b + 1].x - st[b].x) * 0.15, (st[b].y + st[b + 1].y) / 2 + (st[b + 1].y - st[b].y) * 0.15];
  E.v.cx = m[0]; E.v.cy = m[1]; E.setFloor('ground', false); E.S.sel = { type: 'pipe', obj: p, vtx: null, seg: null }; E.showInfo(E.S.sel);
  const rc = document.getElementById('ed-canvas').getBoundingClientRect(), [sx, sy] = E.toScreen(...m); return { n: st.length, x: sx + rc.left, y: sy + rc.top };
}, RID);
await page.mouse.dblclick(ins.x, ins.y); await page.waitForTimeout(150);
const n5 = await page.evaluate((id) => { const E = window.__editor; return { n: E.stOf(E.current().items.find(i => i.p.id === id && i.p.layer === 'prop').p).length, vtx: E.S.sel?.vtx }; }, RID);
await page.mouse.move(ins.x + 300, ins.y + 200); await page.keyboard.press('Delete'); await page.waitForTimeout(150);
const n5b = await page.evaluate((id) => { const E = window.__editor; return E.stOf(E.current().items.find(i => i.p.id === id && i.p.layer === 'prop').p).length; }, RID);
check('insertDelete', n5.n === ins.n + 1 && n5b === ins.n, { before: ins.n, afterIns: n5, afterDel: n5b });

// 6. property: diameter select → store
await page.evaluate((id) => { const E = window.__editor; const p = E.current().items.find(i => i.p.id === id && i.p.layer === 'prop').p; E.S.sel = { type: 'pipe', obj: p, vtx: null, seg: null }; E.showInfo(E.S.sel); }, RID);
const dOld = await page.evaluate((id) => window.__editor.store.get(id).D_mm, RID);
const dNew = await page.evaluate(() => [...document.querySelector('[data-f="D_mm"]').options].map(o => +o.value).find(x => x && x !== +document.querySelector('[data-f="D_mm"]').value));
await page.selectOption('[data-f="D_mm"]', String(dNew)); await page.waitForTimeout(100);
check('property', await page.evaluate(([id, d]) => window.__editor.store.get(id).D_mm === d && window.__editor.store.get(id).status === 'manual', [RID, dNew]), { dOld, dNew });

// 7. slope on a sewage run: every horizontal step drops slope × plan length
const sl = await page.evaluate(() => {
  const E = window.__editor; E.setFloor('first'); const it = E.current().items.find(i => i.p.layer === 'prop' && i.p.system === 'sewage' && i.mode === 'plan' && i.p.ref.vertices[0][2] != null && i.p.ref.vertices.length >= 3);
  E.S.sel = { type: 'pipe', obj: it.p, vtx: null, seg: null }; E.showInfo(E.S.sel); document.getElementById('pf-slope').value = '2'; document.getElementById('pf-slope-go').click();
  const V = E.store.get(it.p.id).vertices; let ok = true;
  for (let i = 1; i < V.length; i++) { const pl = Math.hypot(V[i][0] - V[i - 1][0], V[i][1] - V[i - 1][1]); if (pl >= 0.02 && Math.abs((V[i - 1][2] - V[i][2]) - 0.02 * pl) > 0.0011) ok = false; }
  return { id: it.p.id, ok, slope: E.store.get(it.p.id).slope };
});
check('slope', sl.ok && sl.slope === 0.02, sl);

// 8. new pipe: 3 clicks (ortho), Enter
const np = await page.evaluate(() => {
  const E = window.__editor; E.setFloor('ground'); E.setMode('draw'); document.getElementById('dw-h').value = '0.30'; document.getElementById('dw-h').dispatchEvent(new Event('change'));
  E.S.snapOn = false; const rc = document.getElementById('ed-canvas').getBoundingClientRect(); return { x: rc.left + rc.width * 0.3, y: rc.top + rc.height * 0.3 };
});
await page.mouse.click(np.x, np.y); await page.mouse.click(np.x + 120, np.y + 7); await page.mouse.click(np.x + 125, np.y + 90); await page.keyboard.press('Enter'); await page.waitForTimeout(150);
const nr = await page.evaluate(() => { const E = window.__editor, runs = E.store.runs().filter(r => r.id.startsWith(E.cfg.edit.newIdPrefix + '-')); const r = runs[runs.length - 1]; if (!r) return null; const st = E.OP.stations(r, E.M.frame, 0.02); return { id: r.id, n: r.vertices.length, H: r.vertices.map(v => +(v[2] - E.M.H0).toFixed(3)), axis: st.slice(1).every((q, i) => E.OP.isAxisAligned(st[i], q, 0.5)) }; });
check('newPipe', nr && nr.n === 3 && nr.axis && nr.H.every(h => h === 0.3), nr);

// 8b. manifold as one system: drag MAN-ground 50 px along x → the node and the start of every connected run move by the
// same vector, the far ends stay, one undo step restores all
const man = await page.evaluate(() => {
  const E = window.__editor; E.setMode('select'); E.setFloor('ground'); const n = E.M.nodes.find(x => x.id === 'MAN-ground');
  E.v.cx = n.xy[0]; E.v.cy = n.xy[1]; E.v.k = 100; E.S.snapOn = false; E.setFloor('ground', false);
  E.S.sel = { type: 'node', obj: E.current().nodes.find(x => x.id === 'MAN-ground'), vtx: null, seg: null }; E.showInfo(E.S.sel);
  const runs = E.nodeRuns(E.S.sel.obj).map(r => ({ id: r.id, first: r.vertices[0], last: r.vertices[r.vertices.length - 1], from: r.from }));
  const rc = document.getElementById('ed-canvas').getBoundingClientRect(), [sx, sy] = E.toScreen(...n.xy);
  return { x: sx + rc.left, y: sy + rc.top, k: E.v.k, E: n.E, N: n.N, runs, undo: E.store.undoS.length };
});
await page.mouse.move(man.x, man.y); await page.mouse.down();
for (let t = 1; t <= 10; t++) await page.mouse.move(man.x + 5 * t, man.y);
await page.mouse.up(); await page.waitForTimeout(150);
const manAfter = await page.evaluate((ids) => { const E = window.__editor, n = E.store.nodes().find(x => x.id === 'MAN-ground'); return { E: n.E, N: n.N, runs: ids.map(id => { const r = E.store.get(id); return { id, first: r.vertices[0], last: r.vertices[r.vertices.length - 1] }; }), undo: E.store.undoS.length }; }, man.runs.map(r => r.id));
const dM = 50 / man.k, ux = await page.evaluate(() => window.__editor.D.routes.frame.ux);
const wantM = [man.E + dM * ux[0], man.N + dM * ux[1]], near = (a, b, t = 0.0015) => Math.hypot(a[0] - b[0], a[1] - b[1]) <= t;
const okNode = near([manAfter.E, manAfter.N], wantM);
const okRuns = man.runs.filter(r => r.from === 'MAN-ground').every(r => { const a = manAfter.runs.find(x => x.id === r.id); return near(a.first, [r.first[0] + dM * ux[0], r.first[1] + dM * ux[1]]) && Math.abs(a.first[2] - r.first[2]) < 1e-6 && near(a.last, r.last, 1e-6); });
check('manifoldSystem', okNode && okRuns && man.runs.length >= 10 && manAfter.undo === man.undo + 1, { okNode, okRuns, n: man.runs.length });
await page.keyboard.press('Control+z'); await page.waitForTimeout(100);
const manUndo = await page.evaluate((ids) => { const E = window.__editor, n = E.store.nodes().find(x => x.id === 'MAN-ground'); return { E: n.E, N: n.N, first: ids.map(id => E.store.get(id).vertices[0]) }; }, man.runs.map(r => r.id));
check('manifoldUndo', manUndo.E === man.E && manUndo.N === man.N && manUndo.first.every((f, i) => JSON.stringify(f) === JSON.stringify(man.runs[i].first)), {});

// 8c. delete a pipe: 🗑 → in-page dialog (window.confirm is blocked in the artifact frame) → מחק
const delId = await page.evaluate(() => { const E = window.__editor; const it = E.current().items.find(i => i.p.layer === 'prop' && i.mode === 'plan' && i.p.system === 'hot'); E.S.sel = { type: 'pipe', obj: it.p, vtx: null, seg: null }; E.showInfo(E.S.sel); return it.p.id; });
await page.evaluate(() => { window.confirm = () => { throw new Error('window.confirm used'); }; });
await page.click('#pf-del'); await page.waitForSelector('.dlg button.ok'); await page.click('.dlg button.ok'); await page.waitForTimeout(100);
check('deleteDialog', await page.evaluate((id) => !window.__editor.store.get(id), delId), { delId });
await page.keyboard.press('Control+z'); await page.waitForTimeout(80);

// 9. reload: the edits come back from storage
const before = await page.evaluate(() => window.__editor.store.exportJson());
await page.reload(); await ready(); await page.waitForTimeout(200);
const after = await page.evaluate(() => window.__editor.store.exportJson());
const strip = (s) => { const o = JSON.parse(s); delete o.exportedAt; return JSON.stringify(o); };
check('persist', strip(before) === strip(after), {});
check('console', !errors.length && !(await page.evaluate(() => window.__editorErrors.length)), errors);
console.log(JSON.stringify(res));
await browser.close(); server.close();
if (failed) process.exit(1);
console.log('editor edit OK');

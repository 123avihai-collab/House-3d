// Loads the model headless and writes the geometry-computed quantities (app.quantities) to
// docs/quantities/boq/model-quantities.json – the cross-check for tools/boq/build_boq.py.
// Usage: node tools/boq/export_model_quantities.mjs
import { createRequire } from 'module';
import { execSync } from 'child_process';
import http from 'http'; import fs from 'fs'; import path from 'path';
const require = createRequire(import.meta.url);
let pw; try { pw = require('playwright'); } catch { pw = require(execSync('npm root -g').toString().trim() + '/playwright'); }
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../..');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg', '.png': 'image/png' };
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0])); const f = p.endsWith('/') ? path.join(p, 'index.html') : p;
  fs.readFile(f, (e, b) => { if (e) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); res.end(b); });
}).listen(0);
const browser = await pw.chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await (await browser.newContext({ viewport: { width: 1200, height: 800 } })).newPage();
await page.goto(`http://127.0.0.1:${server.address().port}/index.html`);
await page.waitForFunction(() => window.__ready === true, null, { timeout: 180000 });
const q = await page.evaluate(() => JSON.parse(JSON.stringify(window.__app.quantities, (k, v) => (v && typeof v === 'object' && v.isObject3D) ? undefined : v)));
const out = path.join(root, 'docs/quantities/boq/model-quantities.json');
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify({ _doc: 'נוצר ע"י tools/boq/export_model_quantities.mjs – כמויות שהמודל מחשב מהגיאומטריה (app.quantities). משמש לבקרה של כתב הכמויות.', quantities: q }, null, 1));
console.log(JSON.stringify(q, null, 1).slice(0, 4000));
await browser.close(); server.close();

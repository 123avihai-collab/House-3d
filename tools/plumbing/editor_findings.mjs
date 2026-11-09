// Runs the editor's checks (js/editor/checks.js) headless on routes.json (no saved edits) and writes the findings list
// -> docs/verification/editor-stage-3-findings.md.   Usage: node tools/plumbing/editor_findings.mjs
import { createRequire } from 'module';
import { execSync } from 'child_process';
import http from 'http'; import fs from 'fs'; import path from 'path';
const require = createRequire(import.meta.url);
let pw; try { pw = require('playwright'); } catch { pw = require(execSync('npm root -g').toString().trim() + '/playwright'); }
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const server = http.createServer((req, res) => { const f = path.join(root, decodeURIComponent(req.url.split('?')[0])); fs.readFile(f, (e, b) => { if (e) { res.writeHead(404); res.end(); return; } res.writeHead(200, { 'Content-Type': types[path.extname(f)] || 'application/octet-stream' }); res.end(b); }); }).listen(0);
const browser = await pw.chromium.launch(); const page = await (await browser.newContext()).newPage();
await page.goto(`http://127.0.0.1:${server.address().port}/editor.html`);
await page.waitForFunction(() => window.__editorReady, null, { timeout: 60000 });
const all = await page.evaluate(() => { const E = window.__editor, I = E.issues(), runs = Object.fromEntries(E.store.runs().map(r => [r.id, r]));
  return [...Object.values(I.runs).flat(), ...I.conn].map(i => ({ ...i, floor: i.run ? runs[i.run]?.floor : E.M.nodes.find(n => n.id === i.node)?.floor, system: i.run ? runs[i.run]?.system : null })); });
await browser.close(); server.close();
const T = { clashColumn: 'חוצה עמוד', clashBeam: 'חוצה קורה', inConcrete: 'בתוך בטון', courtyard: 'עובר בחצר האנגלית', wallAngle: 'מעבר בקיר לא בניצב', reverse: 'שיפוע נגדי', rise: 'עלייה בכיוון הזרימה', lowSlope: 'שיפוע נמוך', openEnd: 'קצה לא מחובר', unconnected: 'נקודה בלי מים', noSlope: 'אין שיפוע תכנון' };
const F = ['unit', 'ground', 'site', 'first', 'roof'], sev = { error: '⛔', warn: '⚠', info: 'ℹ' };
const L = ['# ממצאי הבדיקות – הצעת האינסטלציה (routes.json, לפני עריכה)', '', `נוצר ע"י \`node tools/plumbing/editor_findings.mjs\` – אותן בדיקות שרצות בעורך. סה"כ ${all.length} ממצאים.`, '',
  '| סוג | ' + F.join(' | ') + ' | סה"כ |', '|---|' + F.map(() => '---|').join('') + '---|'];
for (const [t, lbl] of Object.entries(T)) { const r = all.filter(i => i.type === t); if (!r.length) continue; L.push(`| ${sev[r[0].sev]} ${lbl} | ${F.map(f => r.filter(i => i.floor === f).length || '').join(' | ')} | ${r.length} |`); }
L.push('', '## שגיאות (⛔) – כל הרשימה', '', '| קומה | קו | מערכת | ממצא | אלמנט (מקור) |', '|---|---|---|---|---|');
for (const i of all.filter(i => i.sev === 'error').sort((a, b) => F.indexOf(a.floor) - F.indexOf(b.floor) || a.run.localeCompare(b.run))) L.push(`| ${i.floor} | ${i.run} | ${i.system} | ${i.text} | ${i.el || ''}${i.elSource ? ` (${i.elSource})` : ''} |`);
L.push('', '## אזהרות (⚠)', '', '| קומה | קו / נקודה | ממצא |', '|---|---|---|');
for (const i of all.filter(i => i.sev === 'warn').sort((a, b) => F.indexOf(a.floor) - F.indexOf(b.floor))) L.push(`| ${i.floor} | ${i.run || i.node} | ${i.text} |`);
fs.writeFileSync(path.join(root, 'docs/verification/editor-stage-3-findings.md'), L.join('\n') + '\n');
console.log(L.slice(0, 16).join('\n'));

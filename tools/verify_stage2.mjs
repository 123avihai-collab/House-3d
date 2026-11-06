// Stage-2 verification: excavation for the dwelling unit + piles (K-400).
// Model values are computed from the same data files and geometry helpers the viewer uses.
// Writes docs/verification/stage-2.md.   Run: node tools/verify_stage2.mjs
import fs from 'fs';
import path from 'path';
import { makeInterpolator, pointInRing, distToRing, distToPolyline, nearestOnRing, ringArea } from '../js/geometry/tin.js';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const J = (p) => JSON.parse(fs.readFileSync(path.join(root, p), 'utf8'));
const P = J('data/structure/piles.json');
const B = J('data/structure/basement.json');
const X = J('data/structure/excavation.json');
const plot = J('data/site/plot-5187.json');
const survey = J('data/site/survey-existing.json');
const origin = J('data/site/origin.json');
const xlsx = J('tools/pile-table-xlsx.json');
const display = J('data/config/display.json');

const H0 = origin.H0 ?? origin.h0 ?? origin.zero?.H;
const f = (v, d = 3) => (v == null ? '—' : Number(v).toFixed(d));
const sgn = (v, d = 3) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d);
const out = [];
const summary = [];

out.push('# טבלת אימות – שלב 2 (חפירה ליחידת הדיור + כלונסאות)', '',
  `נוצר אוטומטית ע"י \`node tools/verify_stage2.mjs\` · ${new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC`, '',
  'ערכי "מודל" מחושבים מקובצי הנתונים (`data/structure/*.json`) ומאותן פונקציות גיאומטריה שהמודל משתמש בהן (`js/geometry/tin.js`).', '');

// 1. georeference of K-400
const g = P.georeference;
out.push('## 1. גאורפרנס תכנית K-400 (PDF) ל-ITM', '',
  '| בדיקה | ערך | הערה |', '|---|---|---|',
  `| שיטה | ${g.method} | |`,
  `| סיבוב תכנית מול רשת ITM | ${f(g.rotationDeg, 5)}° | |`,
  `| היסט פס קיר היקפי מקו המגרש | ${f(g.bandOffsetFromPlotLine_m)} מ' | נפתר בהתאמה |`,
  `| שארית מקסימלית מקווי המגרש | ${(g.maxLineResidual_m * 1000).toFixed(2)} מ"מ | ${g.equations} משוואות / ${g.unknowns} נעלמים |`, '');
out.push('### בדיקת קנה מידה 1:50 מול מידות כתובות (שרשרת מידות בין כלונסאות)', '',
  '| מ- | אל | כתוב (ס"מ) | נמדד (ס"מ) | סטייה (ס"מ) |', '|---|---|---|---|---|');
let maxScale = 0;
for (const s of P.scaleCheck) {
  const d = s.measured_cm - s.written_cm; maxScale = Math.max(maxScale, Math.abs(d));
  out.push(`| ${s.from} | ${s.to} | ${s.written_cm} | ${f(s.measured_cm, 1)} | ${sgn(d, 1)} |`);
}
out.push('', `סטייה מקסימלית: ${maxScale.toFixed(1)} ס"מ (דיוק קריאת PDF וקוטר עיגול). כשיגיע DXF של K-400 – הוא גובר.`, '');
summary.push(['קנה מידה K-400 מול מידות כתובות', `סטייה מקס' ${maxScale.toFixed(1)} ס"מ`]);
summary.push(['שארית גאורפרנס K-400', `${(g.maxLineResidual_m * 1000).toFixed(2)} מ"מ`]);

// 2. piles vs xlsx
const ids = Object.keys(xlsx.piles);
const modelIds = P.piles.map(p => p.id);
const missingInModel = ids.filter(i => !modelIds.includes(i));
const extraInModel = modelIds.filter(i => !ids.includes(i));
let mism = 0;
out.push('## 2. כלונסאות – K-400 מול טבלת הכלונסאות (xlsx)', '',
  '| כלונס | ø מודל (ס"מ) | ø טבלה | L מודל | L טבלה | ראש מודל | ראש טבלה | N מודל (ט\') | N טבלה | מותר | E | N (ITM) | תחתית מוחלטת | התאמה |',
  '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|');
const byNum = (a, b) => parseInt(a.id) - parseInt(b.id) || a.id.localeCompare(b.id);
for (const p of [...P.piles].sort(byNum)) {
  const t = xlsx.piles[p.id];
  const ok = t && Math.round(p.diameter_m * 100) === t[0] && p.length_m === t[1] && Math.abs(p.headRel - t[2]) < 1e-6 && p.designLoad_t === t[3];
  if (!ok) mism++;
  const flag = ok ? (p.overAllowed ? '✓ · מעל המותר' : '✓') : '✗';
  out.push(`| ${p.id} | ${Math.round(p.diameter_m * 100)} | ${t?.[0] ?? '—'} | ${p.length_m} | ${t?.[1] ?? '—'} | ${f(p.headRel, 2)} | ${t ? f(t[2], 2) : '—'} | ${p.designLoad_t} | ${t?.[3] ?? '—'} | ${t?.[4] ?? '—'} | ${f(p.E)} | ${f(p.N)} | ${f(H0 + p.tipRel)} | ${flag} |`);
}
const drill = P.piles.reduce((s, p) => s + p.length_m, 0);
const conc = P.piles.reduce((s, p) => s + Math.PI * (p.diameter_m / 2) ** 2 * p.length_m, 0);
out.push('', '| סיכום | מודל | טבלה | סטייה |', '|---|---|---|---|',
  `| מספר כלונסאות | ${P.piles.length} | ${xlsx.totals.count} | ${P.piles.length - xlsx.totals.count} |`,
  `| מטר קידוח | ${f(drill, 1)} | ${xlsx.totals.drillMetres} | ${sgn(drill - xlsx.totals.drillMetres, 1)} |`,
  `| נפח בטון תיאורטי (מ"ק) | ${f(conc, 2)} | ${xlsx.totals.concrete_m3} | ${sgn(conc - xlsx.totals.concrete_m3, 2)} |`,
  `| חסרים במודל / עודפים במודל | ${missingInModel.join(', ') || '—'} / ${extraInModel.join(', ') || '—'} | | |`,
  `| אי-התאמות בנתוני כלונס | ${mism} | | |`, '');
summary.push(['כלונסאות: מספר / קידוח / בטון מול xlsx', `${P.piles.length}/${xlsx.totals.count} · ${f(drill, 0)}/${xlsx.totals.drillMetres} מ' · ${f(conc, 2)}/${xlsx.totals.concrete_m3} מ"ק · ${mism} אי-התאמות`]);

// 3. perimeter piles vs lot line
const lot = plot.ring;
const near = P.piles.map(p => ({ id: p.id, d: distToRing(p.E, p.N, lot), r: p.diameter_m / 2, inside: pointInRing(p.E, p.N, lot) })).filter(q => q.d < 1.0);
out.push('## 3. כלונסאות היקפיים מול גבול המגרש (בדיקה עצמאית למיקום)', '',
  '| כלונס | מרחק מרכז מקו המגרש (מ\') | רדיוס | מרווח שפה–גבול (מ\') | בתוך המגרש |', '|---|---|---|---|---|');
for (const q of near.sort((a, b) => a.d - b.d)) out.push(`| ${q.id} | ${f(q.d)} | ${f(q.r, 2)} | ${f(q.d - q.r)} | ${q.inside ? '✓' : '✗'} |`);
const dmin = Math.min(...near.map(q => q.d)), dmax = Math.max(...near.map(q => q.d));
out.push('', `${near.length} כלונסאות היקפיים, מרכזים ${f(dmin, 2)}–${f(dmax, 2)} מ' מקו המגרש, כולם בתוך המגרש.`, '');
summary.push(['כלונסאות היקפיים מול קו המגרש', `${f(dmin, 2)}–${f(dmax, 2)} מ' פנימה, ${near.every(q => q.inside) ? 'כולם בתוך המגרש' : 'יש חריגה!'}`]);

// 4. basement outline
const cc = B.crossCheckPermitWalls, k = B.k11ToK400;
out.push('## 4. קו מרתף (K-11 DXF) – מיקום', '',
  '| בדיקה | ערך |', '|---|---|',
  `| התאמת K-11 ל-K-400 (ICP) – חציון שארית | ${f(k.medianResidual_mm, 2)} מ"מ (בקנה מידה PDF), ${Math.round(k.inlierFraction * 100)}% נקודות תואמות |`,
  `| קודקודי קו המרתף מול קירות הגרמושקה (גאורפרנס נפרד) – חציון | ${f(cc.median_m)} מ' |`,
  `| – מקסימום | ${f(cc.max_m)} מ' (${cc.note}) |`,
  `| שטח חוץ מרתף | ${f(B.area_m2, 2)} מ"ר |`, '');
summary.push(['קו מרתף מול גרמושקה (גאורפרנס עצמאי)', `חציון ${(cc.median_m * 100).toFixed(1)} ס"מ`]);

// 5. excavation levels and quantities (same formula as js/geometry/excavation.js)
const pts = survey.survey2025.points.map(p => ({ x: p.E, y: p.N, z: p.z }));
const existing = makeInterpolator(pts);
const bottom = X.bottomOutlineITM, floor = X.floorOutlineITM, runs = X.shoredRunsITM, zb = X.bottomAbs;
const pitZ = (E, N) => {
  if (pointInRing(E, N, floor)) return zb;
  const q = nearestOnRing(E, N, floor);
  if (runs.some(r => distToPolyline(q.x, q.y, r) <= display.excavation.shoringMatchTol_m)) return existing(E, N);
  return Math.min(existing(E, N), zb + q.dist / X.sideSlope_HperV);
};
const gs = display.excavation.volumeGrid_m;
let vol = 0, maxD = 0;
const xs = lot.map(p => p[0]), ys = lot.map(p => p[1]);
for (let x = Math.min(...xs) + gs / 2; x < Math.max(...xs); x += gs) for (let y = Math.min(...ys) + gs / 2; y < Math.max(...ys); y += gs) {
  if (!pointInRing(x, y, lot)) continue;
  const dz = existing(x, y) - pitZ(x, y); if (dz > 0) { vol += dz * gs * gs; maxD = Math.max(maxD, dz); }
}
let shL = 0, shH = 0, shA = 0;
for (const r of runs) for (let i = 1; i < r.length; i++) {
  const ds = Math.hypot(r[i][0] - r[i - 1][0], r[i][1] - r[i - 1][1]);
  const h1 = existing(...r[i]) - zb, h0 = existing(...r[i - 1]) - zb;
  shL += ds; shA += Math.max(0, (h0 + h1) / 2) * ds; shH = Math.max(shH, h0, h1);
}
// open slopes must stay inside the lot: largest distance of an open-slope top point outside the lot
let maxOut = 0;
for (const [x, y] of lot) { const z = pitZ(x, y), e = existing(x, y); if (e - z > 0.05) maxOut = Math.max(maxOut, e - z); }
const bu = X.bottomBuildUp;
const beam = bu.find(b => b.rel != null)?.rel;
const below = bu.filter(b => b.thickness_m).reduce((s, b) => s + b.thickness_m, 0);
out.push('## 5. חפירה – מפלסים וכמויות', '',
  '| רכיב | ערך | מקור |', '|---|---|---|');
for (const b of bu) out.push(`| ${b.item} | ${b.rel != null ? f(b.rel, 2) : f(b.thickness_m, 2) + " מ'"}${b.status ? ' (זמני)' : ''} | ${b.source} |`);
out.push(`| **תחתית חפירה** | **${f(X.bottomRel, 2)} (${f(zb, 2)} מוחלט)** | ${f(beam, 2)} − ${f(below, 2)} = ${f(beam - below, 2)} ${Math.abs(beam - below - X.bottomRel) < 1e-6 ? '✓' : '✗'} |`,
  `| שיפוע דפנות | 1:${X.sideSlope_HperV} (אנכי:אופקי) | ${X.sideSlopeSource} |`,
  `| מרווח עבודה בתחתית | ${X.workingSpace_m} מ' (${X.workingSpaceStatus === 'approved' ? 'אושר' : 'זמני'}) | ${X.workingSpaceNote} |`, '',
  '| כמות | מודל (חישוב חוזר) | הערה |', '|---|---|---|',
  `| נפח חפירה מול קרקע 2025 | ${f(vol, 1)} מ"ק | רשת ${gs} מ', חפירה בתוך מגרש 5187 בלבד |`,
  `| שטח תחתית חפירה (כולל מרווח עבודה) | ${f(Math.abs(ringArea(floor)), 1)} מ"ר | קו מרתף ∪ דיסקיות כלונסאות המרתף, + ${X.workingSpace_m} מ' |`,
  `| עומק מקסימלי | ${f(maxD, 2)} מ' | |`,
  `| דיפון (זמני – קו מחושב) | ${f(shL, 1)} מ', חתך עד ${f(shH, 2)} מ', שטח דופן ${f(shA, 1)} מ"ר | ${X.shoringRule} |`,
  `| חפירה פתוחה בפינות המגרש (בדיקה שהשיפוע לא חורג מהמגרש) | ${maxOut > 0.05 ? 'חריגה ' + f(maxOut, 2) + " מ'" : 'אין חתך בפינות ✓'} | |`, '', X.shoringNote, '');
summary.push(['תחתית חפירה', `${f(X.bottomRel, 2)} (${f(zb, 2)}) = ${f(beam, 2)} − ${f(below, 2)}`]);
summary.push(['נפח חפירה / דיפון (זמני)', `${f(vol, 1)} מ"ק · ${f(shL, 1)} מ' עד ${f(shH, 2)} מ' · ${f(shA, 1)} מ"ר`]);

// 6. overloaded piles
const over = P.piles.filter(p => p.overAllowed);
out.push('## 6. הערות תכנון שעלו מהבדיקה', '',
  ...over.map(p => `- כלונס ${p.id}: עומס תכנון ${p.designLoad_t} ט' מעל המותר בטבלה (${p.xlsxCheck.allowed} ט') – לבירור מול הקונסטרוקטור (open-issues).`),
  `- מפלס תחתית כלונס = מפלס ראש פחות L, לבקרה בלבד (${P.piles[0].tipNote}).`, '');

out.splice(4, 0, '## סיכום', '', '| בדיקה | תוצאה |', '|---|---|', ...summary.map(([a, b]) => `| ${a} | ${b} |`), '');
fs.mkdirSync(path.join(root, 'docs/verification'), { recursive: true });
fs.writeFileSync(path.join(root, 'docs/verification/stage-2.md'), out.join('\n') + '\n');
console.log(summary.map(r => r.join(': ')).join('\n'));
if (mism || missingInModel.length || extraInModel.length) process.exitCode = 1;

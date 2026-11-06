// Stage-1 verification: model values (computed with the same geometry code the viewer uses)
// vs the values written in the source documents. Writes docs/verification/stage-1.md.
// Run: node tools/verify_stage1.mjs
import fs from 'fs';
import path from 'path';
import { makeInterpolator, ringArea } from '../js/geometry/tin.js';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const J = (p) => JSON.parse(fs.readFileSync(path.join(root, p), 'utf8'));
const plot = J('data/site/plot-5187.json');
const heights = J('data/site/planned-heights.json');
const street = J('data/site/street.json');
const survey = J('data/site/survey-existing.json');
const origin = J('data/site/origin.json');
const neighbors = J('data/site/neighbors.json');
const src = J('tools/verification-sources.json');

const f3 = (v) => (v == null ? '—' : Number(v).toFixed(3));
const f2 = (v) => (v == null ? '—' : Number(v).toFixed(2));
const dev = (a, b, d = 3) => (a == null || b == null ? '—' : (a - b >= 0 ? '+' : '−') + Math.abs(a - b).toFixed(d));
const rows = [];
const out = [];
let maxCoordDev = 0;

out.push('# טבלת אימות – שלב 1 (מגרש וסביבה)', '',
  `נוצר אוטומטית ע"י \`node tools/verify_stage1.mjs\` · ${new Date().toISOString().slice(0, 16).replace('T', ' ')} UTC`, '',
  'ערכי "מודל" מחושבים מאותם קובצי נתונים ואותו קוד גיאומטריה שהמודל משתמש בהם (‏js/geometry/tin.js). ערכי "מקור" הם המספרים הכתובים במסמכי המקור.', '');

// 1. corner coordinates
out.push('## 1. קואורדינטות פינות המגרש (ITM)', '',
  '| נקודה | E מודל | E מדידה | סטייה | N מודל | N מדידה | סטייה |', '|---|---|---|---|---|---|---|');
for (const name of plot.order) {
  const m = plot.points[name]; const s = src.surveyTable.points[name];
  // the model ring vertex nearest the point (geometry actually drawn)
  const v = plot.ring.reduce((b, q) => (Math.hypot(q[0] - m.E, q[1] - m.N) < Math.hypot(b[0] - m.E, b[1] - m.N) ? q : b));
  maxCoordDev = Math.max(maxCoordDev, Math.abs(v[0] - s.E), Math.abs(v[1] - s.N));
  out.push(`| ${name} | ${f3(v[0])} | ${f3(s.E)} | ${dev(v[0], s.E)} | ${f3(v[1])} | ${f3(s.N)} | ${dev(v[1], s.N)} |`);
}
out.push('', `מקור: ${src.surveyTable.source}. אותן קואורדינטות מופיעות גם במפת השיווק (${src.marketingMap.source}). סטייה מקסימלית: ${maxCoordDev.toFixed(3)} מ'.`, '');

// 2. area + edge lengths
const pts = plot.points;
const arcEdge = plot.edges.find(e => e.type === 'arc');
const a = pts[arcEdge.from], b = pts[arcEdge.to];
const chord = Math.hypot(b.E - a.E, b.N - a.N);
const R = arcEdge.radius;
const th = 2 * Math.asin(chord / (2 * R));
const segArea = R * R / 2 * (th - Math.sin(th));
const polyArea = Math.abs(ringArea(plot.order.map(n => [pts[n].E, pts[n].N])));
const exactArea = polyArea + segArea; // arc bulges outwards (towards the street)
const modelArea = Math.abs(ringArea(plot.ring));
out.push('## 2. שטח ואורכי צלעות', '',
  '| גודל | מודל | מקור | סטייה | הערה |', '|---|---|---|---|---|',
  `| שטח מגרש (מ"ר) | ${modelArea.toFixed(2)} | ${src.surveyTable.area_m2} | ${dev(modelArea, src.surveyTable.area_m2, 2)} | שטח רשום. חישוב אנליטי עם הקשת: ${exactArea.toFixed(3)} · שטח מחושב במפה למשתכן (cellno): ${plot.area_m2_cellno_attr} |`);
for (const e of plot.edges) {
  const p = pts[e.from], q = pts[e.to];
  const c = Math.hypot(q.E - p.E, q.N - p.N);
  const L = e.type === 'arc' ? 2 * e.radius * Math.asin(c / (2 * e.radius)) : c;
  const w = src.surveyTable.edges[`${e.from}-${e.to}`];
  out.push(`| צלע ${e.from}–${e.to}${e.type === 'arc' ? ` (קשת R=${e.radius})` : ''} | ${L.toFixed(3)} | ${w} | ${dev(L, w)} | מידה כתובה בשרטוט (2 ספרות) |`);
}
out.push('');

// 3. heights
const H0 = origin.H0;
const lotCtrl = heights.lotCorners.filter(h => h.parcel === '257').map(h => ({ x: h.at[0], y: h.at[1], z: h.z }));
const lotI = makeInterpolator(lotCtrl);
const stCtrl = [];
for (const c of street.contours) for (const [x, y] of c.points) stCtrl.push({ x, y, z: c.z });
const contourOnly = makeInterpolator(stCtrl);
for (const s of heights.streetSpots) stCtrl.push({ x: s.at[0], y: s.at[1], z: s.z });
const stI = makeInterpolator(stCtrl);
const s25 = survey.survey2025.points.map(p => ({ x: p.E, y: p.N, z: p.z }));
const exI = makeInterpolator(s25);
const rel = (z) => `${z - H0 >= 0 ? '+' : '−'}${Math.abs(z - H0).toFixed(2)}`;

out.push('## 3. גבהים מרכזיים (מוחלט / יחסי ל-±0.00)', '',
  '| נקודה | מודל | מקור | סטייה | מקור הנתון |', '|---|---|---|---|---|',
  `| ±0.00 של הבית | ${f2(H0)} | ${f2(heights.houseZero.z)} / ${f2(src.permitZero)} | ${dev(H0, src.permitZero, 2)} | מפה למשתכן (בלוק aumiflas, LEVEL1) / גרמושקה (G-ANNO-DIMS) |`);
for (const h of heights.lotCorners.filter(x => x.parcel === '257')) {
  const z = lotI(h.at[0], h.at[1]);
  out.push(`| גובה מתוכנן מגרש 5187 ב-E ${h.at[0].toFixed(2)} N ${h.at[1].toFixed(2)} (קרוב ל-${nearestName(h.at)}) | ${f2(z)} (${rel(z)}) | ${f2(h.z)} | ${dev(z, h.z, 3)} | מפה למשתכן, שכבה L-00-ktse migrash |`);
}
for (const p of src.permitLotHeights) {
  const z = lotI(p.E, p.N);
  out.push(`| גרמושקה "${p.label}" (${p.where}) | ${f2(z)} | ${f2(p.z)} | ${dev(z, p.z, 3)} | ${p.source} |`);
}
for (const s of heights.streetSpots) {
  const z = stI(s.at[0], s.at[1]); const zc = contourOnly(s.at[0], s.at[1]);
  out.push(`| מדרכה ${s.parcel ? `(חלקה ${s.parcel})` : ''} ב-${f3(s.at[0])}/${f3(s.at[1])} | ${f2(z)} (${rel(z)}) | ${f2(s.z)} | ${dev(z, s.z, 3)} | בדיקה צולבת – מקווי הגובה בלבד: ${f2(zc)} (${dev(zc, s.z, 2)}) |`);
}
out.push('', '**פני המגרש המתוכננים בפינות** (אינטרפולציה TIN של גבהי המגרש המתוכננים, ללא ערך כתוב בפינה עצמה):', '',
  '| פינה | גובה מתוכנן במודל | קרקע קיימת 2025 במודל | הפרש (חפירה− / מילוי+) |', '|---|---|---|---|');
for (const n of plot.order) {
  const zp = lotI(pts[n].E, pts[n].N), ze = exI(pts[n].E, pts[n].N);
  out.push(`| ${n} | ${f2(zp)} (${rel(zp)}) | ${f2(ze)} (${rel(ze)}) | ${dev(zp, ze, 2)} |`);
}
out.push('');

// existing heights: 2023 vs 2025 surveys
out.push('**קרקע קיימת: מפה למשתכן 2023 מול מדידה 2025** (נקודות 2023 בתוך תחום מדידת 2025):', '',
  '| נקודה 2023 | גובה 2023 | משטח 2025 במודל באותו מיקום | הפרש |', '|---|---|---|---|');
for (const p of survey.survey2023) {
  const near = s25.some(q => Math.hypot(q.x - p.E, q.y - p.N) < 6);
  if (!near) continue;
  const z = exI(p.E, p.N);
  out.push(`| ${p.name} | ${f2(p.z)} | ${f2(z)} | ${dev(z, p.z, 2)} |`);
}
out.push('');

// 4. georeference & self checks
const g = origin.georeference.inset;
out.push('## 4. גאורפרנס ובדיקות עצמיות', '',
  '| בדיקה | תוצאה |', '|---|---|',
  `| מפה למשתכן (DWG) – קואורדינטות ITM מקוריות | הנקודות זהות לטבלת המדידה (סטייה מקס' ${maxCoordDev.toFixed(3)} מ') |`,
  `| תרשים 1:5000 (גבולות שכנים) מול נקודות הגבול | קנ"מ ${g.scale.toFixed(9)}, סיבוב ${g.rotationDeg.toExponential(1)}°, שארית מקס' ${g.maxResidual_m.toExponential(1)} מ' |`,
  `| מעטפת בנייה מחושבת למגרש 5187 (3/3/5 מ') מול קו הבניין המשורטט | סטייה מקס' ${neighbors.selfCheck.maxDeviationFromDrawnEnvelope_m.toFixed(3)} מ' |`,
  `| מדידה סרוקה 2025 – התאמה אפינית לפי 5 נקודות גבול | שאריות ${Object.values(src.scanGeoref.residuals_m).map(v => v.toFixed(2)).join(' / ')} מ' (לכן משמשת רק לגבהים קיימים, לא לגבולות) |`,
  `| צפון אמיתי מול צפון רשת ITM | ${origin.trueNorthGridAzimuth_deg}° |`,
  `| מיקום גיאוגרפי למערכת השמש | ${origin.lotCentroid.lat}°N, ${origin.lotCentroid.lon}°E (EPSG:2039→4326, pyproj) |`, '');
fs.mkdirSync(path.join(root, 'docs/verification'), { recursive: true });
fs.writeFileSync(path.join(root, 'docs/verification/stage-1.md'), out.join('\n') + '\n');
console.log(out.join('\n'));

function nearestName(v) {
  let best = null, bd = Infinity;
  for (const [n, p] of Object.entries(pts)) { const d = Math.hypot(p.E - v[0], p.N - v[1]); if (d < bd) { bd = d; best = n; } }
  return best;
}

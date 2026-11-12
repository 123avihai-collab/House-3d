#!/usr/bin/env python3
"""Plaster coverage check, round 4 (chat prompt docs/chat-prompts/2026-11-11-בדיקה-היקפית-טיח-ואיטום.md).

The exposed skin of the skeleton (tools/finishes/skin.py – every face of every wall / column / block segment / beam /
slab / courtyard wall that looks at air: not the soil, not a floor, not another element, not an opening) is sampled on a
2 cm grid; every sample must have a finish surface in front of it (plaster of any type, membrane, cladding, the 'none'
neighbour side, reveal, patch) within the plaster thickness + 2 cm.
Also: the steps between elements on one wall surface – plan jogs and ledges. Up to 2 cm: the plaster covers them (no
report). Over 2 cm (up to 8 cm – beyond that it is a designed projection, not a deviation): listed for a joint decision
-> docs/verification/plaster-deviations.xlsx.
Outputs: docs/verification/finishes-coverage.md, docs/verification/plaster-deviations.xlsx
  python3 tools/finishes/verify_coverage.py            report
  python3 tools/finishes/verify_coverage.py --check    + exit 1 when a sample is not covered (npm test)
"""
import json, math, os, runpy, sys
from collections import defaultdict
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CHECK = '--check' in sys.argv
try:
    import numpy, shapely  # noqa: F401
except ImportError:
    print('verify_coverage: SKIPPED – needs python packages shapely + numpy (pip install shapely numpy)'); sys.exit(0)
os.environ['FINISHES_NO_XLSX'] = '1'
G = runpy.run_path(os.path.join(ROOT, 'tools', 'finishes', 'derive_finishes.py'), run_name='coverage')
sys.path.insert(0, os.path.join(ROOT, 'tools', 'finishes'))
import skin
S, res = skin.analyse(G, patches=G['PATCHES'], grid=G['CFG'].get('skinGrid_m', 0.02))
n_bad = int(sum(r['U'].sum() for r in res)); a_bad = sum(r['area'] for r in res)
n_all_v = sum(len(skin.Skin.samples_vertical(S, f)[0]) * len(skin.Skin.samples_vertical(S, f)[1]) for f in S.vertical)
area_v = sum(f['L'] * (f['z1'] - f['z0']) for f in S.vertical); area_h = sum(h['poly'].area for h in S.horizontal)
STEP_MAX = G['CFG'].get('stepTolerance_m', 0.02)
ST = skin.steps(S, maxstep=G['CFG'].get('stepReportMax_m', 0.08))
FLOOR_HE = G['FLOOR_HE']; ROOMS = G['ROOMS']
from shapely.geometry import Polygon
for r_ in ROOMS: r_.setdefault('poly', Polygon(r_['ringITM']))   # dropped before the json dump


def floor_name(z, o):
    if o and o.get('floor') == 'site': return FLOOR_HE['site']
    return FLOOR_HE[G['floor_of_z'](z + 0.2)]   # a ledge at a slab top belongs to the floor above it


def room_name(xy, z):
    best = None
    for d in (0.1, 0.25, 0.5):
        for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
            r = G['room_at']((xy[0] + dx, xy[1] + dy), z)
            if r: return r['name'] or r['key']
    return 'חוץ'


def origin(o):
    k = o['kind']
    if k == 'block': return 'אדריכל (קירות בלוקים – blocks.json)'
    if k in ('perimeter', 'footing'): return 'קונסטרוקציה (חומות K-400)'
    return 'קונסטרוקציה (' + ('K-11' if o.get('floor') == 'unit' else 'K-21/K-31/K-41') + ')'


KIND_HE = {'concrete': 'קיר בטון', 'column': 'עמוד', 'block': 'קיר בלוקים', 'beam': 'קורה', 'slab': 'רצפה / תקרה', 'infill': 'בטון מעל / מתחת לפתח',
           'perimeter': 'חומה', 'footing': 'יסוד חומה'}
for s_ in ST: s_['step_m'] = round(s_['step_m'], 3)   # to the mm (CLAUDE.md §2)
small = [s for s in ST if s['step_m'] <= STEP_MAX]
big = sorted([s for s in ST if s['step_m'] > STEP_MAX], key=lambda s: -s['step_m'])
dev = []
for i, s in enumerate(big, 1):
    a, b = s['a'], s['b']; z = (s['z0'] + s['z1']) / 2
    cm = round(s['step_m'] * 100, 1)
    if s['kind'] == 'jog':
        kinds = {a['kind'], b['kind']}
        fix = ('ליישר את קו הבלוקים לפני הבטון בביצוע, או טיח עבה מקומית + רשת' if 'block' in kinds else 'טיח עבה מקומית + רשת, או החלטה להשאיר מדרגה (פינה)')
        where = 'מדרגה בתוכנית (לאורך הקיר)'
    else:
        fix = 'יישור בטיח עבה (עד 4 ס"מ) עם רשת, או החלטה להשאיר את המדרגה (פס / אף)' if s['step_m'] <= 0.04 else 'להשאיר כמדרגה מתוכננת, או לבדוק מול הקונסטרוקטור'
        where = 'מדרגה אנכית (מפלס ' + f"{z:+.2f}" + ')'
    dev.append([i, floor_name(z, a), room_name(s['xy'], z + 0.05), f"E {s['xy'][0]:.2f} / N {s['xy'][1]:.2f}", where,
                f"{a['id']} ({KIND_HE.get(a['kind'], a['kind'])})", origin(a), f"{b['id']} ({KIND_HE.get(b['kind'], b['kind'])})", origin(b),
                cm, round(s['length_m'] or 0, 2), f"{s['z0']:+.2f}…{s['z1']:+.2f}" if s['kind'] == 'jog' else f"{z:+.2f}", fix])
# ---- Excel
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
wb = Workbook(); ws = wb.active; ws.title = 'סטיות מעל 2 סמ'; ws.sheet_view.rightToLeft = True
head = ['מס\'', 'קומה', 'חדר / אזור', 'מיקום (ITM)', 'סוג', 'אלמנט א\'', 'מקור א\'', 'אלמנט ב\'', 'מקור ב\'', 'סטייה (ס"מ)', 'אורך / גובה המדרגה (מ\')', 'מפלס (יחסי)', 'הצעת תיקון']
ws.append(head)
for c in ws[1]: c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='2F5496'); c.alignment = Alignment(horizontal='center', wrap_text=True)
for r in dev: ws.append(r)
for i, w in enumerate([6, 12, 26, 24, 22, 22, 26, 22, 26, 10, 12, 14, 46]): ws.column_dimensions[chr(65 + i)].width = w
ws.freeze_panes = 'A2'
ws2 = wb.create_sheet('הסבר'); ws2.sheet_view.rightToLeft = True
for t in ['רשימת מדרגות בין פני אלמנטים סמוכים באותו משטח קיר, מעל 2 ס"מ (עד 8 ס"מ – מעבר לזה זו בליטה מתוכננת, לא סטייה).',
          'עד 2 ס"מ – הטיח מכסה (לא ברשימה). מעל 2 ס"מ – לא מוסתר; להחלטה משותפת. השלד לא שונה.',
          'מדרגה בתוכנית: קפיצה בקו פני הקיר לאורכו (למשל קיר בלוקים מול קיר בטון). מדרגה אנכית: פס אופקי בין אלמנט תחתון לעליון (קיר מתחת לקורה).',
          'נוצר ב-python3 tools/finishes/verify_coverage.py מגיאומטריית המודל.']: ws2.append([t])
ws2.column_dimensions['A'].width = 120
xlsx = os.path.join(ROOT, 'docs/verification/plaster-deviations.xlsx'); wb.save(xlsx)
# ---- markdown
byk = defaultdict(float)
for r in res:
    f = r['face']
    if r['kind'] == 'v':
        m = ((f['a'][0] + f['b'][0]) / 2, (f['a'][1] + f['b'][1]) / 2); o = S.owner(m[0] - f['n'][0] * 0.005, m[1] - f['n'][1] * 0.005, float(r['z'][r['U'].any(1)].mean()))
    else:
        c = f['poly'].representative_point(); o = S.owner(c.x, c.y, f['z'])
    byk[(o or {}).get('id', '?')] += r['area']
pk = defaultdict(float); pn = defaultdict(int)
for p in G['PATCHES']: pk[p['part']] += p['area']; pn[p['part']] += 1
PART_HE = {'side': 'פנים אנכיים (קצוות קירות, שפות רצפה במדרגה, גומחות, צדי פתחים)', 'sill': 'אדנים', 'top': 'ראשים / מדפים (פונים למעלה)', 'soffit': 'תחתיות (פונות למטה – משקופים, תקרות מבחוץ, קורות)'}
L = ['# בדיקת כיסוי טיח – סבב 4 (רשת 2 ס"מ)', '',
     'נוצר ב-`python3 tools/finishes/verify_coverage.py` (רץ ב-`npm test` עם `--check`). עור השלד – כל פן של קיר / עמוד / קטע בלוקים / קורה / רצפה / חומה שפונה לאוויר (לא לקרקע, לא רצפה, לא אלמנט אחר, לא פתח) – נדגם ברשת של 2 ס"מ; מול כל נקודה צריך להיות משטח גמר (טיח מכל סוג, איטום, חיפוי, צד שכן, גליף, השלמה) במרחק עובי הטיח + 2 ס"מ.', '',
     f'**נקודות לא מכוסות: {n_bad} ({a_bad:.4f} מ"ר).** עור השלד שנבדק: {area_v:.1f} מ"ר אנכי, {area_h:.1f} מ"ר אופקי (כולל רצפות, שלא מקבלות טיח).', '',
     '## השלמות שנוספו (patches)', '', '| סוג | מספר | מ"ר |', '|---|---|---|']
for k in ('side', 'sill', 'top', 'soffit'): L.append(f'| {PART_HE[k]} | {pn[k]} | {pk[k]:.2f} |')
L += [f'| **סה"כ** | **{len(G["PATCHES"])}** | **{sum(pk.values()):.2f}** |', '',
      '## מדרגות בין אלמנטים באותו משטח', '',
      f'- עד {STEP_MAX * 100:.0f} ס"מ: {len(small)} מקומות. הטיח מכסה (השלמה על המדרגה), בלי דיווח.',
      f'- מעל {STEP_MAX * 100:.0f} ס"מ (עד 8): {len(big)} מקומות. הם ב-[plaster-deviations.xlsx](plaster-deviations.xlsx), להחלטה משותפת. השלד לא שונה.', '']
if byk: L += ['## לא מכוסה לפי אלמנט', '', '| אלמנט | מ"ר |', '|---|---|'] + [f'| {k} | {v:.4f} |' for k, v in sorted(byk.items(), key=lambda x: -x[1])]
open(os.path.join(ROOT, 'docs/verification/finishes-coverage.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print(f'coverage: {n_bad} uncovered samples ({a_bad:.4f} m2) · patches {len(G["PATCHES"])} ({sum(pk.values()):.2f} m2) · steps ≤2cm {len(small)}, >2cm {len(big)}')

# ---- one plane per wall surface (12.11.2026, tools/finishes/flatten.py): the drawn plaster in front of the skeleton everywhere,
# no slit between the pieces -> docs/verification/plaster-flatten.md
import flatten as FLAT
DF = G['J']('data/config/display.json')['finishes']; TOL = G['CFG'].get('flattenMax_m', 0.08)
front, _ = FLAT.front_check(G, DF['offset_m'], DF.get('seamOverlap_m', 0), TOL, extra=G['FILLERS'])
rest = FLAT.remaining_steps(G, DF['offset_m'], TOL)
corners = FLAT.corner_check(G, DF['offset_m'], DF.get('seamOverlap_m', 0)); corners_bad = [c for c in corners if c['gap'] > DF['offset_m']]
R_ = G['FLAT_RES']; rep = sorted(R_['report'], key=lambda x: -x['max_shift'])
sh = [x.get('shift', 0) for x in G['FACES']] + [x.get('shift', 0) for b in G['BEAMSURF'] for x in b['sides']] + [p.get('shift', 0) for p in G['PATCHES'] if p['vertical']]
def band(lo, hi): return sum(1 for v in sh if lo < v <= hi)
FL = ['# טיח במישור אחד – בדיקה (12.11.2026)', '',
      'נוצר ב-`python3 tools/finishes/verify_coverage.py` (רץ ב-`npm test` עם `--check`). הכלל: `tools/finishes/flatten.py`, הסף: `data/finishes/config.json → flattenMax_m` = '
      f'{TOL * 100:.0f} ס"מ.', '',
      '## התוצאה', '',
      f'**נקודות שלד שבולטות מהטיח או נראות בסדק בין שני משטחים (רשת 2 ס"מ, כל הפנים האנכיים): {len(front)}.** (חייב 0.)', '',
      f'**פינות חוץ שהטיח לא נסגר בהן (סדק מעל {DF["offset_m"] * 1000:.0f} מ"מ): {len(corners_bad)}.** (חייב 0. סדקים קטנים יותר: {len(corners) - len(corners_bad)}, עד {max([c["gap"] for c in corners] or [0]) * 1000:.0f} מ"מ.)', '',
      '| מה | מספר |', '|---|---|',
      f'| משטחי קיר (קבוצות פנים מקבילים וסמוכים) | {R_["clusters"]} |',
      f'| משטחים שהוזזו למישור אחד | {R_["moved"]} |',
      f'| פנים שהטיח שלהם הוקדם | {R_["shifted"]} |',
      f'| פני מדרגה שנבלעו בטיח (בכמויות, לא מצוירים) | {R_["hidden"]} |',
      f'| קודקודים של גליפים / ראשי קירות / אדנים שעברו עם הפנים | {R_["vertices"]} |',
      f'| פינות חוץ שנסגרו | {R_["joins"]} |',
      f'| סדקים קטנים לאורך משטח שגושרו (עד 5 ס"מ) | {R_["bridged"]} |',
      f'| מילוי תצוגה (סדקי מ"מ שנשארו, לא בכמויות) | {len(G["FILLERS"])} |', '',
      '## עובי הטיח שנוסף (פנים)', '', '| תוספת | פנים |', '|---|---|',
      f'| עד 1 ס"מ | {band(0.0005, 0.01)} |', f'| 1–2 ס"מ | {band(0.01, 0.02)} |', f'| 2–4 ס"מ (רשת) | {band(0.02, 0.04)} |', f'| 4–8 ס"מ (טיח עבה + רשת, או יישור הבלוקים בביצוע) | {band(0.04, 0.081)} |', '',
      '## משטחים עם תוספת מעל 2 ס"מ', '', '| # | קומה | מיקום (ITM) | מפלסים (יחסי) | אלמנטים | תוספת מרבית (ס"מ) |', '|---|---|---|---|---|---|']
for i, x in enumerate([x for x in rep if x['max_shift'] > 0.02], 1):
    FL.append(f"| {i} | {FLOOR_HE.get(x['floor'], '—') if x['floor'] else '—'} | E {x['at'][0]:.2f} / N {x['at'][1]:.2f} | {x['z0']:+.2f}…{x['z1']:+.2f} | {', '.join(m for m in x['members'] if m != '?')} | {x['max_shift'] * 100:.1f} |")
big_rest = sorted([r for r in rest if r['step'] > 0.01], key=lambda r: -r['step'])
FL += ['', '## מדרגות שנשארו (מעל 1 ס"מ)', '',
       'מדרגה שנשארת = שני חלקים של אותו קיר שלא אוחדו: האיחוד היה מעבה את הטיח מעבר לסף (בדרך כלל קורה / שפת תקרה שבולטת ~8–10 ס"מ מקיר הבלוקים שמתחתיה – חגורה מתוכננת).', '',
       '| # | מיקום (ITM) | מפלס | מדרגה (ס"מ) | משטח |', '|---|---|---|---|---|']
seen_ = set()
for r in big_rest:
    k_ = (round(r['at'][0], 1), round(r['at'][1], 1), round(r['z'][0], 1))
    if k_ in seen_: continue
    seen_.add(k_)
    FL.append(f"| {len(seen_)} | E {r['at'][0]:.2f} / N {r['at'][1]:.2f} | {r['z'][0]:+.2f}…{r['z'][1]:+.2f} | {r['step'] * 100:.1f} | {r['a'] or '—'} |")
FL += ['', '## תצוגה', '',
       '- הטיח מצויר כמשטח דק לפני השלד (`display.json → finishes.offset_m`). כל משטח מוקדם ב-`shift` למישור המשטח שלו ומוארך ב-`ext` לפינה; חפיפה של `seamOverlap_m` בכל קצה סוגרת את התפר בין משטחים שכנים.',
       '- שכבת ה-AO (ambient occlusion) מציירת עכשיו את שני צדי המשטחים הדקים: קודם היא "ראתה" דרך הטיח את הבלוקים והקורות שמאחוריו, וזה נראה כקווים כהים על הקיר.',
       '- הטיח מטיל צל: הוא סוגר בצל את הסדקים של מ"מ בין חלקי השלד.']
open(os.path.join(ROOT, 'docs/verification/plaster-flatten.md'), 'w', encoding='utf-8').write('\n'.join(FL) + '\n')
print(f'one plane: {len(front)} samples in front of / between the drawn sheets · {len(corners_bad)} open corners · {R_["moved"]} surfaces moved · {len(G["FILLERS"])} fillers · {len(big_rest)} steps >1cm left')
if CHECK and n_bad: print('coverage FAILED'); sys.exit(1)
if CHECK and front: print('one-plane check FAILED (skeleton in front of / between the plaster sheets)'); sys.exit(1)
if CHECK and corners_bad: print('one-plane check FAILED (open outer corners)', corners_bad[:5]); sys.exit(1)

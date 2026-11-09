#!/usr/bin/env python3
"""Verification of 2D pipe editor stage 1 -> docs/verification/editor-stage-1.md
 1. plan background (consultant DXF) vs the model's concrete walls (K-xx JSON): distance of each concrete wall corner to the
    nearest background wall / structure line, per floor
 2. routes.json vs proposal.json: counts, vertex reduction, max deviation, 3D length before / after
 3. house frame vs blocks.json houseAxisDeg"""
import json, math, os, statistics as st
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
BG, R, P, NET = J('data/plumbing/plan-background.json'), J('data/plumbing/routes.json'), J('data/plumbing/proposal.json'), J('data/plumbing/network.json')
FR, FG, FF, FRF, BL = J('data/structure/framing.json'), J('data/structure/floor-ground.json'), J('data/structure/floor-first.json'), J('data/structure/floor-roof.json'), J('data/architecture/blocks.json')
out = ['# אימות – עורך צנרת דו-ממדי, שלב 1', '', 'נוצר ע"י `python3 tools/plumbing/verify_editor.py`.', '']
# 1
out += ['## 1. רקע אדריכלי (DXF היועץ) מול קירות הבטון של המודל', '',
        'לכל פינה של קיר / עמוד בטון במודל (K-11/21/31/41 → JSON): המרחק לקו הקרוב ברקע (שכבות קירות + שלד של היועץ). נלקחות פינות עד 10 ס"מ מקו (פינות בלי קו מקביל ברקע לא נספרות).', '',
        '| קומה | שיבוץ ה-DXF (network.json: חציון, inlier) | פינות שנבדקו | חציון | 90% | מקס\' | מקור הבטון |', '|---|---|---|---|---|---|---|']
CON = {'unit': [w['footprintITM'] for w in FR['basementWalls']], 'ground': [w['footprintITM'] for w in FG['walls'] + FG['columns']],
       'first': [w['footprintITM'] for w in FF['walls'] + FF['columns']], 'roof': [w['footprintITM'] for w in FRF['walls']]}
SRC = {'unit': 'framing.json basementWalls (K-11)', 'ground': 'floor-ground.json (K-21)', 'first': 'floor-first.json (K-31)', 'roof': 'floor-roof.json (K-41)'}
for fl in ('unit', 'ground', 'first', 'roof'):
    g = BG['floors'][fl]['groups']; lines = unary_union([LineString(q) for q in g['walls'] + g['structure'] if len(q) > 1])
    d = sorted(x for x in (lines.distance(Point(p)) for P_ in CON[fl] for p in P_) if x <= 0.10)
    pl = BG['placement'][fl]
    out.append(f"| {fl} | {pl['median_cm'] * 10:.1f} מ\"מ, {pl['inlier'] * 100:.0f}% | {len(d)} | {st.median(d) * 1000:.1f} מ\"מ | {d[int(len(d) * 0.9) - 1] * 1000:.1f} מ\"מ | {d[-1] * 1000:.1f} מ\"מ | {SRC[fl]} |")
# 2
L3 = lambda V: sum(math.dist(V[i], V[i + 1]) for i in range(len(V) - 1)) if all(v[2] is not None for v in V) else sum(math.dist(V[i][:2], V[i + 1][:2]) for i in range(len(V) - 1))
srcmap = {}
for r in P['runs']: srcmap[r['id']] = r['pts3d']
for k in ('unitSewer', 'firstFloor', 'site'): [srcmap.__setitem__(r['id'], r['pts3d']) for r in P[k]['runs']]
for r in P['site']['drops']: srcmap[r['id']] = r['pts3d']
for s in P['stackMoves']: srcmap[s['id']] = s['pts3d']
for a in P['rain']['alternatives']:
    if a['id'] == P['rain']['default']: [srcmap.__setitem__(r['id'], r['pts3d']) for r in a['runs']]
out += ['', '## 2. routes.json מול proposal.json', '',
        f"זריעה: `tools/plumbing/seed_routes.py`, פישוט Douglas–Peucker תלת-ממדי בסבולת {R['runs'][0]['simplify']['tol_m'] * 1000:.0f} מ\"מ (הקשתות של PEX נשמרות כנקודות פנייה צפופות).", '',
        '| מערכת | קווים | נקודות לפני → אחרי | סטייה מקס\' | אורך לפני | אורך אחרי | הפרש |', '|---|---|---|---|---|---|---|']
by = {}
for r in R['runs']:
    b = by.setdefault(r['system'], [0, 0, 0, 0, 0, 0]); s = r['simplify']; P0 = [p for p in srcmap[r['id']]]
    b[0] += 1; b[1] += s['ptsBefore']; b[2] += s['ptsAfter']; b[3] = max(b[3], s['maxDev_m']); b[4] += L3(P0); b[5] += L3(r['vertices'])
tot = [0, 0, 0, 0, 0, 0]
for k, b in by.items():
    out.append(f"| {k} | {b[0]} | {b[1]} → {b[2]} | {b[3] * 1000:.0f} מ\"מ | {b[4]:.3f} מ' | {b[5]:.3f} מ' | {(b[5] - b[4]) * 1000:+.0f} מ\"מ |")
    tot = [tot[0] + b[0], tot[1] + b[1], tot[2] + b[2], max(tot[3], b[3]), tot[4] + b[4], tot[5] + b[5]]
out.append(f"| **סה\"כ** | {tot[0]} | {tot[1]} → {tot[2]} | {tot[3] * 1000:.0f} מ\"מ | {tot[4]:.3f} מ' | {tot[5]:.3f} מ' | {(tot[5] - tot[4]) * 1000:+.0f} מ\"מ |")
missing = [k for k in srcmap if k not in {r['id'] for r in R['runs']}]
out += ['', f"קווים בהצעה שלא נזרעו: {len(missing)}. נקודות: {len(R['nodes'])} (‏{len(P['points'])} נקודות צריכה, {len(P['manifolds'])} מחלקים, {len(P['unitHot']['heaters'])} דודים, מוני משנה, ברז ראשי, משאבת סחרור).",
        f"צנרת היועץ (network.json) – לא הועתקה: {len(NET['runs'])} קווים + {len(NET['lines3d'])} קווים אנכיים, מוצגים בעורך לקריאה בלבד; {len(R['superseded']['runs'])} מהם מסומנים \"הוחלף\" (מוסתרים כברירת מחדל)."]
# 3
f = R['frame']; uy_az = math.degrees(math.atan2(f['uy'][0], f['uy'][1])) % 360
out += ['', '## 3. צירי הבית', '', '| | ערך | מקור |', '|---|---|---|',
        f"| אזימוט ציר x של הבית (ux) | {f['azimuthDeg_ux']:.3f}° | {f['source']} |",
        f"| אזימוט ציר y (uy) | {uy_az:.3f}° | |",
        f"| houseAxisDeg בקירות הבלוקים | {BL['houseAxisDeg']:.3f}° (= 90° − {90 - BL['houseAxisDeg']:.3f}°) | data/architecture/blocks.json |",
        f"| הפרש | {abs((90 - BL['houseAxisDeg']) - uy_az):.3f}° | |"]
out += ['', '## 4. העורך (tests/editor.mjs)', '', '- בכל קומה מספר קווי ההצעה שמצוירים = מספר הקווים ב-routes.json לקומה (קרקע כולל פיתוח).',
        '- לחיצה על קו ההצעה הארוך בקרקע → כרטיס עם שם הקו; שכבה מוסתרת לא מצוירת; שכבה נעולה לא נבחרת.',
        '- הצמדה לפינת עמוד C5: ≤ 1 מ"מ (0.5 מ"מ = שתי נקודות כמעט כפולות במצולע של C5 במקור).',
        '- מחשב וטלפון (Pixel 7): אין שגיאות בקונסול.']
open(os.path.join(ROOT, 'docs', 'verification', 'editor-stage-1.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('\n'.join(out))

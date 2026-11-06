#!/usr/bin/env python3
"""Stage 3a verification (ground-floor skeleton) -> docs/verification/stage-3.md (run: python3 tools/verify_stage3.py)."""
import json, math, os, datetime
from shapely.geometry import Polygon, LineString
from shapely.ops import unary_union
from shapely import affinity

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
G = J('data/structure/floor-ground.json'); P = J('data/structure/piles.json'); H0 = J('data/site/origin.json')['H0']
theta = P['georeference']['sheetToItm']['theta_rad']
out = ['# טבלת אימות – שלב 3א (שלד קומת הקרקע ותקרתה)', '',
       f'נוצר ע"י `python3 tools/verify_stage3.py` · {datetime.datetime.now(datetime.UTC):%Y-%m-%d %H:%M} UTC', '',
       '> מקורות: k-21.dxf (קירות, עמודים, רצפת הקרקע), k-31.dxf (תקרה +3.70), K-31 PDF (קורות, פתח המדרגות). '
       'יוחלפו בקובץ IFC מהקונסטרוקטור כשיגיע (open-issues #24).', '']

pl = G['placement']
out += ['## 1. מיקום', '', '| בדיקה | תוצאה |', '|---|---|',
        f"| k-31.dxf מול k-21.dxf – עמודים 4 ו-5 המשותפים | {pl['k31_vs_k21_columns_m']} מ' (אותה מערכת קואורדינטות) |",
        f"| K-31 PDF על גיליון K-400 (ICP מול k-31.dxf) | הזזה {pl['K31pdf']['translation_pt']} pt, התאמה {pl['K31pdf']['inlierFraction']}, שארית חציונית {pl['K31pdf']['medianResidual_pt']} pt ({pl['K31pdf']['medianResidual_pt'] / 56.69 * 1000:.1f} מ\"מ) |", '']

out += ['## 2. עמודי קומת הקרקע – חתך מהשרטוט (HATCH) מול התווית', '', '| עמוד | חתך בשרטוט (ס"מ) | תווית | סטייה | תחתית | ראש | מעמד |', '|---|---|---|---|---|---|---|']
for c in G['columns']:
    t = c['tagSize_cm']; ok = sorted(t) == sorted(c['size_cm']) if len(t) == 2 else None
    out.append(f"| {c['id']} | {c['size_cm'][0]}/{c['size_cm'][1]} | {'/'.join(map(str, t)) or '—'} | {'0 ✓' if ok else ('תווית חלקית' if ok is None else '✗')} | "
               f"{c['bottomRel']:+.2f} | {c['topRel']:+.2f} | {c['status']} |")
out += ['', 'גובה עמוד = מפני רצפת הקרקע עד תחתית תקרת K-31 (O.K +3.70 − D).', '']

out += ['## 3. קירות קומת הקרקע (קווי "Beton Ole" – בטון עולה ב-k-21)', '', '| קיר | תווית | עובי (ס"מ) | תחתית | ראש | גובה | מעמד |', '|---|---|---|---|---|---|---|']
for w in G['walls']:
    out.append(f"| {w['id']} | {w['tag'] or '—'} | {round(w['thickness_m'] * 100)} | {w['bottomRel']:+.2f} | {w['topRel']:+.2f} | {w['topRel'] - w['bottomRel']:.2f} | {w['status']} |")
prov = [w['id'] for w in G['walls'] if w['status'] == 'provisional']
out += ['', f"קירות זמניים (בלי תקרה +3.70 מעליהם – בחלל הכפול / בחוץ): {', '.join(prov) or '—'}. "
        f"קירות 'מפסיקים' (מילוי אפור – ראשי קירות המרתף/החצרות): {G['stoppingWalls']['count']} – לא שורטטו כאן. חומות היקפיות: {G['perimeterWallsPending']['count']} חלקים – בצעד 'חומות'.", '']

out += ['## 4. רצפת הקרקע (K-21) – לפי אזורים', '', '| רצפה | אזור | O.K | D | שטח | מעמד |', '|---|---|---|---|---|---|']
for s in G['slab']:
    out.append(f"| {s['id']} | {s['zoneLabel']} | {s['topRel']:+.2f} | {round(s['thickness_m'] * 100)} | {s['area_m2']:.1f} מ\"ר | {s['status']} |")
out += ['', 'כל פאנל = פאה שמשורטטת ב-k-21 (קווי רצפה + קירות + עמודים), בלי איחוד בין אזורים. המפלס מתגית הרצפה שבתוך הפאנל. '
        'זיהוי האזור (בית, כניסה, מרפסת, חצרות, חניה, חצר אנגלית, מדרגות, גינה) – מתוכנית האדריכלות "קומה קרקע – פיתוח היקפי" (זיהוי בלבד, `tools/ground-zones.json`).', '',
        '**אזורים בלי רצפה:**', '', '| אזור | שטח |', '|---|---|']
for o in G['openZones']:
    out.append(f"| {o['label']} | {o['area_m2']:.1f} מ\"ר |")
from shapely.geometry import Polygon as _P
opn = [_P(o['footprintITM']) for o in G['openZones']]
hit = [(s['id'], o_['label']) for s in G['slab'] for o_, og in zip(G['openZones'], opn) if _P(s['footprintITM']).intersection(og).area > 0.01]
out += ['', f"**בדיקה:** רצפה שחותכת חצר אנגלית / מדרגות / גינה: {hit or 'אין ✓'}. פאות לא מסווגות: {len(G['unclassifiedFaces'])}.", '']
out += ['## 4ב. חיבור: על מה עומד כל עמוד וקיר', '', '| אלמנט | תחתית | יושב על |', '|---|---|---|']
for e in G['columns'] + G['walls']:
    out.append(f"| {e['id']}{' ' + e['tag'] if e.get('tag') else ''} | {e['bottomRel']:+.2f} | {e.get('standsOn') or '**— אין אלמנט נושא במקורות**'} |")
out += ['', f"ללא אלמנט נושא: {G.get('unsupportedCount', 0)} (מסומנים זמניים – חסרה קורה ב-K-21 / IFC). "
        f"ראשי קירות מרתף עד מפלס הקרקע (מילוי אפור ב-K-21): {len(G.get('basementWallCaps', []))}.", '',
        'סדר הביצוע במודל: קירות מרתף עד תחתית הרצפה (‎-0.40) → קורות K-21 + רצפת הבית מעליהם (‎-0.40…‎-0.15) → עמודים וקירות מראש הקורה / הרצפה שמתחתם '
        '(על קורה הפוכה B-45, O.K +0.20 – מראש הקורה) → תקרה +3.70 → חומות → רצפות חוץ (משטח צפוני, חצרות, חניה) וקורותיהן.', '']
C = G['ceiling']
out += ['## 5. תקרת קומת הקרקע (K-31, +3.70)', '', '| תקרה | O.K | D | שטח |', '|---|---|---|---|']
for s in C['slab']:
    out.append(f"| {s['id']} | {s['topRel']:+.2f} | {round(s['thickness_m'] * 100)} | {s['area_m2']:.1f} מ\"ר |")
areas = ', '.join(f"{o['area_m2']:.2f}" for o in C.get('mamad', []))
out += ['', f'ממ"ד (ריבוע עם אלכסון, "ראה תכנית הג\"א מאושרת"): {areas} מ"ר – לא פתח; התקרה נשמרת, עובי/מפלס לפי תוכנית הג"א (חסרה).', '']
out += ['| קורה | חתך | O.K | תחתית | אורך | מעמד |', '|---|---|---|---|---|---|']
for b in C['beams']:
    out.append(f"| {b['id']} | {round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)} | {b['topRel']:+.2f} | {b['bottomRel']:+.2f} | "
               f"{(str(b['length_m']) + ' מ') if b.get('length_m') else '—'} | {b['status']} |")
# independent check: overall size of the K-31 frame (slab + beams) on the building axes vs the written overall dimensions
rects = []
for b in C['beams']:
    if not b.get('axisITM'): continue
    rects.append(LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2))
frame = unary_union([Polygon(s['footprintITM']) for s in C['slab']] + rects)
rot = affinity.rotate(frame, -theta, origin=(0, 0), use_radians=True)
x0, y0, x1, y1 = rot.bounds
out += ['', '**בדיקה בלתי תלויה – מידות כוללות של תקרת K-31 (רצפה + קורות) מול המידות הכתובות בגיליון:**', '',
        '| מידה | מודל | כתוב ב-K-31 | סטייה |', '|---|---|---|---|',
        f"| אורך כולל (ציר הבניין) | {x1 - x0:.3f} מ' | 17.02 (\"1702\") | {abs(x1 - x0 - 17.02) * 100:.1f} ס\"מ |",
        f"| רוחב כולל | {y1 - y0:.3f} מ' | 14.65 (\"1465\") | {abs(y1 - y0 - 14.65) * 100:.1f} ס\"מ |", '']
missing = [b['id'] for b in C['beams'] if b['status'] == 'missing']
out += [f"קורות בלי גיאומטריה (לא שורטטו): {', '.join(missing) or '—'}.", '']
os.makedirs(os.path.join(ROOT, 'docs/verification'), exist_ok=True)
open(os.path.join(ROOT, 'docs/verification/stage-3.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('overall', round(x1 - x0, 3), round(y1 - y0, 3), 'missing beams', missing)

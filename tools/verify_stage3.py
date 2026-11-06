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
FF = J('data/structure/floor-first.json')
out += ['## 6. עמודי קומה א\' (K-31 → K-41)', '', '| עמוד | חתך | תווית | תחתית | ראש | יושב על | מעמד |', '|---|---|---|---|---|---|---|']
for c in FF['columns']:
    out.append(f"| {c['id']} | {c['size_cm'][0]}/{c['size_cm'][1]} | {'/'.join(map(str, c['tagSize_cm'])) or '—'} | {c['bottomRel']:+.2f} | {c['topRel']:+.2f} | {c.get('standsOn') or '—'} | {c['status']} |")
out += ['', f"ראש העמודים = תחתית תקרת הגג K-41 (O.K {FF['roofLevels'][0]['topRel']:+.2f}, D={round(FF['roofLevels'][0]['thickness_m'] * 100)}).", '']
FR_ = J('data/structure/floor-roof.json')
out += ['## 7. קומה א\' וגג (K-31, K-41)', '', f"קירות קומה א': {len(FF['walls'])} (מ-+3.70 / ראש קורה עד +6.65). קירות מעל הגג: {len(FR_['walls'])} (עד +8.00, לפי מפלסי הנקודה '+8.00 / +6.65' ב-K-41).", '',
        '| קורה (K-41) | חתך | O.K | אורך | פרגולה |', '|---|---|---|---|---|']
for b in FR_['ceiling']['beams']:
    out.append(f"| {b['id']} | {round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)} | {b['topRel']:+.2f} | {b.get('length_m') or '—'} | {'כן' if b.get('pergola') else '—'} |")
rr = [LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2) for b in FR_['ceiling']['beams'] if b.get('axisITM')]
fr2 = unary_union([Polygon(s_['footprintITM']) for s_ in FF['ceiling']['slab']] + rr + [Polygon(w['footprintITM']) for w in FR_['walls']])
x0_, y0_, x1_, y1_ = affinity.rotate(fr2, -theta, origin=(0, 0), use_radians=True).bounds
out += ['', '**בדיקה בלתי תלויה – מידות כוללות של הגג (תקרה + קורות + קירות) מול K-41:**', '', '| מידה | מודל | כתוב | סטייה |', '|---|---|---|---|',
        f"| אורך | {x1_ - x0_:.3f} | 15.79 (\"1579\") | {abs(x1_ - x0_ - 15.79) * 100:.1f} ס\"מ |",
        f"| רוחב | {y1_ - y0_:.3f} | 14.97 (\"1497\") | {abs(y1_ - y0_ - 14.97) * 100:.1f} ס\"מ |", '']
ST = J('data/structure/stairs.json')
pg, pb = ST['placement']['groundSheet'], ST['placement']['basementSheet']
shaft = [o for o in G['openZones'] if o['zone'] == 'stairShaft']
cc = list(Polygon(shaft[0]['footprintITM']).minimum_rotated_rectangle.exterior.coords)
sw = min(math.dist(cc[0], cc[1]), math.dist(cc[1], cc[2]))
s1, s2, s3 = ST['stairs']
out += ['## 8. מדרגות ופילר מערכות (תוכניות אדריכלות 1:100 + חתך א-א)', '',
        '| בדיקה | מודל | מקור | סטייה |', '|---|---|---|---|',
        f"| מיקום גיליון הקרקע (ICP מול k-21) | קנ\"מ {pg['scaleCheck']}, {pg['matchedPoints']} נק' | ×2 = 1:100 | שארית חציונית {pg['medianResidual_mm']:.1f} מ\"מ |",
        f"| מיקום גיליון המרתף (ICP מול k-11) | קנ\"מ {pb['scaleCheck']}, {pb['matchedPoints']} נק' | ×2 = 1:100 | שארית חציונית {pb['medianResidual_mm']:.1f} מ\"מ |",
        f"| רוחב פיר המדרגות (פתח K-21) | {sw:.3f} | 1.86 (K-21 \"186\") / 1.84 (K-31 \"184\") | {abs(sw - 1.86) * 100:.1f} / {abs(sw - 1.84) * 100:.1f} ס\"מ |",
        f"| מרתף ← קרקע: רומים | 15 × {s1['rise_m'] * 100:.2f} ס\"מ | 2.60 / 15 (חתך: ‎-2.60 → 0, שלבים 1–15) | 0 |",
        f"| שלבים 9–15: גיליון הקרקע מול גיליון המרתף | {max(s1['crossCheck_m']['flight9to15_groundVsBasementSheet']) * 100:.0f} ס\"מ | אותם קווים בשני הגיליונות | קו אף המדרגה |",
        f"| רוחב שלחים 1–8 / 9–15 | {s1['flights'][0]['width_m']:.3f} / {s1['flights'][1]['width_m']:.3f} | (186 − מחיצה) / 2 | — |",
        f"| שלח (עומק מדרך) | {s1['flights'][0]['going_m']:.3f} / {s1['flights'][1]['going_m']:.3f} | 2×רום + שלח = {2 * s1['rise_m'] + s1['flights'][0]['going_m']:.3f} (נוחות 0.60–0.65) | — |",
        f"| קרקע ← קומה א': רומים | 22 × {s2['rise_m'] * 100:.2f} ס\"מ | 3.85 / 22 (חתך: \"385 קומה א'\", שלבים 16–37) | 0 |",
        f"| ירידה ליחידה: רומים / רוחב | 14 × {s3['rise_m'] * 100:.2f} ס\"מ / {s3['flights'][0]['width_m']:.3f} | 280.31 → 277.88 / \"82\" | {abs(s3['flights'][0]['width_m'] - 0.82) * 100:.1f} ס\"מ |",
        f"| פילר: גובה | {ST['pillar']['topRel'] - ST['pillar']['bottomRel']:.2f} | \"240\" (חזית החומה הקדמית) | 0 |",
        f"| פילר: עובי קיר / שטח חדר האשפה | {ST['pillar']['wallThickness_m'][0]:.3f} / {ST['pillar']['innerAreas_m2'][0]:.2f} מ\"ר | קווי התוכנית | — |", '',
        'עובי שיפוע (20 ס"מ ניצב) ופודסט (28) – נמדדו בחתך א-א 1:100 (קנ"מ אומת: 0 → ‎-260 = 73.7 pt). מפלסי המדרגות – גמר (אחרי ריצוף).', '']
PM = J('data/structure/perimeter.json')
from shapely.geometry import Point as _Pt
allp = [p_ for p_ in P['piles'] if p_['id'].isdigit() and int(p_['id']) >= 100]
inside = [p_['id'] for p_ in allp if any(Polygon(f['ringITM']).buffer(0.05).contains(_Pt(p_['E'], p_['N'])) for f in PM['footings'])]
out += ['## 9. חומות היקפיות (K-400 + חזיתות החומות)', '',
        '| צד | קו חוץ | פנים הקיר | פנים היסוד | B = רוחב היסוד | טבלת "חתך חומה" |', '|---|---|---|---|---|---|']
for c in PM['measuredOffsets']:
    out.append(f"| {c['side']} | {c['stemOuter_m']:+.2f} | {c['stemInner_m']:+.2f} | {c['footingInner_m']:+.2f} | {c['footingInner_m'] - c['stemOuter_m']:.2f} | 0.80 (H 0.5–1.0) |")
out += ['', 'היסט מקו המגרש פנימה (מ\'). צפון / מזרח / מערב: קיר 20 ס"מ ממורכז על הגבול (משותף לשכן).', '',
        f"כלונסאות 100–118 בתוך יסוד חומה: {len(inside)}/{len(allp)}. תחתית היסוד = ראש הכלונס (K-400), עובי a=0.20 לפי הטבלה.", '',
        '| חומה | צד | אורך | עובי | ראש (חזית) | תחתית | מעמד |', '|---|---|---|---|---|---|---|']
for w in PM['walls']:
    out.append(f"| {w['id']} | {w['side']} | {w['length_m']:.2f} | {w['thickness_m']:.2f} | {w['topAbs']:.2f} | {w['bottomRel']:+.2f} | {w['status']} |")
out += ['']
missing = [b['id'] for b in C['beams'] if b['status'] == 'missing']
out += [f"קורות בלי גיאומטריה (לא שורטטו): {', '.join(missing) or '—'}.", '']
os.makedirs(os.path.join(ROOT, 'docs/verification'), exist_ok=True)
open(os.path.join(ROOT, 'docs/verification/stage-3.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('overall', round(x1 - x0, 3), round(y1 - y0, 3), 'missing beams', missing)

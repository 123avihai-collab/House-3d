#!/usr/bin/env python3
"""Stage 2b verification -> docs/verification/stage-2b.md (run: python3 tools/verify_stage2b.py)."""
import json, math, os, datetime
from shapely.geometry import Polygon, Point, LineString

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
F = J('data/structure/framing.json'); P = J('data/structure/piles.json')['piles']; X = J('data/structure/excavation.json')
H0 = J('data/site/origin.json')['H0']
out = ['# טבלת אימות – שלב 2ב (קורות יסוד, רצפת מרתף, קירות מרתף)', '',
       f'נוצר ע"י `python3 tools/verify_stage2b.py` · {datetime.datetime.now(datetime.UTC):%Y-%m-%d %H:%M} UTC', '',
       '> **מעמד:** קורות היסוד חולצו מ-PDF (מיקום בקירוב). הנתונים יוחלפו בקובץ IFC מהקונסטרוקטור (open-issues #24).', '']

pl = F['placement']
out += ['## 1. מיקום הגיליונות על K-400 (שגוארפרנס בשלב 2)', '', '| גיליון | הזזה (pt) | שיעור התאמה | שארית חציונית |', '|---|---|---|---|']
for k, v in pl.items():
    out.append(f"| {k} | {v['translation_pt']} | {v.get('inlierFraction', '—')} | {v.get('medianResidual_pt', '—')} pt |")
d = abs(pl['k21dxf']['translation_pt'][0] - pl['k11dxf']['translation_pt'][0]) + abs(pl['k21dxf']['translation_pt'][1] - pl['k11dxf']['translation_pt'][1])
out += ['', f'בדיקה: k-11.dxf ו-k-21.dxf יוצאים מאותו מודל Revit – ההזזות שלהם שונות ב-{d:.3f} pt ({d / 56.69 * 1000:.1f} מ"מ).', '']

# beams vs pile heads: every pile under a beam must have head = beam bottom
out += ['## 2. קורות יסוד מול ראשי הכלונסאות (בדיקה בלתי תלויה: תחתית קורה מתווית K-21/K-11 מול O.K של הכלונס מ-K-400)', '',
        '| קורה | חתך | O.K | תחתית קורה | כלונסאות מתחת | ראש כלונס | סטייה |', '|---|---|---|---|---|---|---|']
ok = bad = 0
for b in F['groundBeams']:
    if not b.get('axisITM'): continue
    ax = LineString(b['axisITM'])
    under = [p for p in P if ax.distance(Point(p['E'], p['N'])) <= b['width_m'] / 2 + p['diameter_m'] / 2]
    for p in under:
        dv = p['headRel'] - b['bottomRel']
        if p['headRel'] < b['bottomRel'] - 0.5:
            out.append(f"| {b['id']} | {round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)} | {b['topRel']:+.2f} | {b['bottomRel']:+.2f} | {p['id']} | {p['headRel']:+.2f} | ראש הכלונס נמוך בהרבה – הקורה עוברת מעל קיר/אלמנט אחר, לא נשענת עליו |")
            continue
        good = abs(dv) <= 0.051
        ok += good; bad += not good
        out.append(f"| {b['id']} | {round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)} | {b['topRel']:+.2f} | {b['bottomRel']:+.2f} | {p['id']} | {p['headRel']:+.2f} | {dv:+.2f} {'✓' if good else '✗'} |")
    if not under:
        out.append(f"| {b['id']} | {round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)} | {b['topRel']:+.2f} | {b['bottomRel']:+.2f} | — | — | אין כלונס מתחת |")
out += ['', f'התאמה (עד 5 ס"מ): {ok}, אי-התאמה: {bad}. אי-התאמה = קורה ששויכה לפס הלא נכון, או כלונס שעובר ליד הקורה ולא מתחתיה.', '']
missing = [b['id'] for b in F['groundBeams'] if not b.get('axisITM')]
out += [f"קורות עם תווית ללא מיקום (לא שורטטו): {', '.join(missing) or '—'}. פסי נקודות ב-K-400 ללא תווית: {F['unmatchedStipple']['count']}.", '']

# walls
out += ['## 3. קירות מרתף', '', '| קיר | שטח חתך | תחתית | ראש | מקור |', '|---|---|---|---|---|']
for w in F['basementWalls']:
    out.append(f"| {w['id']} | {w['area_m2']:.2f} מ\"ר | {w['bottomRel']:+.2f} ({H0 + w['bottomRel']:.2f}) | {w['topRel']:+.2f} ({H0 + w['topRel']:.2f}) | {w['source']} |")
heads = sorted({p['headRel'] for p in P if p['zone'] == 'basement'})
out += ['', f'תחתית הקיר = ראש כלונסאות המרתף ({heads}). ראש הקיר = תחתית תקרת הקרקע (O.K−D). שניהם זמניים עד IFC.', '']
# slabs
out += ['## 4. רצפות מרתף (תלויות)', '', '| רצפה | שטח | O.K | D | תחתית | מקור |', '|---|---|---|---|---|---|']
for s in F['slabs']:
    if s['top'] is None:
        out.append(f"| {s['id']} | {s['area_m2']:.2f} | — | — | — | {s.get('note')} |"); continue
    out.append(f"| {s['id']} | {s['area_m2']:.2f} מ\"ר | {s['top']:+.2f} | {round(s['thickness_m'] * 100)} | {s['top'] - s['thickness_m']:+.2f} | {s['source']} |")
main = max((s for s in F['slabs'] if s['top'] is not None), key=lambda s: s['area_m2'])
below = sum(b['thickness_m'] for b in X['bottomBuildUp'] if b.get('thickness_m'))
out += ['', f"בדיקת עקביות: תחתית רצפה ראשית {main['top'] - main['thickness_m']:+.2f} = ראש כלונסאות {heads[0]:+.2f} "
        f"{'✓' if abs(main['top'] - main['thickness_m'] - heads[0]) < 0.005 else '✗'}; תחתית חפירה {X['bottomRel']:+.2f} = {heads[0]:+.2f} − {below:.2f} "
        f"{'✓' if abs(heads[0] - below - X['bottomRel']) < 0.005 else '✗'}.", '']
PL = J('data/systems/plumbing-foundations.json'); ck = PL.get('checks', {})
out += ['## 5. אינסטלציה (ביוב) – מיקום ובדיקות בלתי תלויות', '', '| בדיקה | תוצאה |', '|---|---|',
        f"| התאמת תוכנית האינסטלציה (קרקע) ל-k-21 – שארית חציונית | {PL['placement']['ground']['medianResidual_cm']} ס\"מ |",
        f"| התאמת תוכנית האינסטלציה (מרתף) ל-k-11 – שארית חציונית | {PL['placement']['medianResidual_cm']} ס\"מ |",
        f"| שוחה 0 מול השוחה העירונית במפה למשתכן | {ck.get('municipalManhole_vs_MIG_m')} מ' |",
        f"| I.L שוחה 1 מול נפל המגרש במפה למשתכן (278.20) | סטייה {ck.get('connectionIL_vs_MIG_nipple_m')} מ' |",
        f"| התאמת ה-PDF (קווי הצנרת) ל-6 השוחות | שארית מקסימלית {ck.get('pdfFitMaxResidual_m')} מ' |", '',
        '| צינור | בין | קוטר | שיפוע | I.L התחלה → סוף | מעמד |', '|---|---|---|---|---|---|']
for q in PL['pipes']:
    if q.get('ILfrom') is None: continue
    out.append(f"| {q['id']} | {q['between'][0] or 'בית'} → {q['between'][1]} | {q.get('diameter_m') or '—'} | {q['slope'] * 100:.2f}% | {q['ILfrom']:.3f} → {q['ILto']:.3f} | {q['status']} |")
out.append('')
os.makedirs(os.path.join(ROOT, 'docs/verification'), exist_ok=True)
open(os.path.join(ROOT, 'docs/verification/stage-2b.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print(f'beams vs piles: ok {ok}, bad {bad}; missing beams {missing}')

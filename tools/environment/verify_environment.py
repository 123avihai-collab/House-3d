#!/usr/bin/env python3
"""Verification table for the environment (neighbouring lots, streets, envelopes) -> docs/verification/environment.md"""
import json, math, os, datetime
from shapely.geometry import Polygon, LineString, Point
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda *p: json.load(open(os.path.join(ROOT, *p), encoding='utf-8'))
L, S = J('data', 'environment', 'lots.json'), J('data', 'environment', 'streets.json')
parcels = {p['parcel']: p for p in J('data', 'site', 'parcels.json')['parcels']}
mig = J('data', 'site', 'planned-heights.json')['lotCorners']
f = lambda v, n=3: f'{v:+.{n}f}'.replace('-', '−')
out = []
w = out.append
w('# טבלת אימות – סביבה: מגרשים שכנים, רחובות ומעטפות')
w('')
w(f'נוצר אוטומטית ע"י `python3 tools/environment/verify_environment.py` · {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC')
w('')
w('## 1. גאורפרנס של המקורות')
w('')
w('| מקור | שיטה | נקודות | קנ"מ (מ\'/pt) | שארית |')
w('|---|---|---|---|---|')
g = L['georeference']
w(f"| מפה אורכי מגרשים (וקטורי 1:500) | דמיון מול 8 נקודות גבול מה-DWG ({', '.join(g['lengthsMap']['points'])}) | 8 | {g['lengthsMap']['scale_m_per_pt']} (1:500 = 0.176389) | מקס' {g['lengthsMap']['maxResidual_m']:.3f} · RMS {g['lengthsMap']['rms_m']:.3f} |")
w(f"| מפה אורכי מגרשים – בדיקה עצמאית | כל נקודות הגבול שבחלון מול קודקודי החלקות ב-DWG | {g['boundaryPointCheck']['points']} | — | מקס' {g['boundaryPointCheck']['maxDist_m']:.3f} · חציון {g['boundaryPointCheck']['median_m']:.3f} |")
w(f"| תוכנית גבהים בגוש (וקטורי) | ICP של קצוות קווי המגרשים מול פינות ה-DWG | {g['heightsPlan']['pairs']} | {g['heightsPlan']['scale_m_per_pt']} | חציון {g['heightsPlan']['medianResidual_m']:.3f} · 95% {g['heightsPlan']['p95Residual_m']:.3f} |")
w('')
w('מתוכנית הגבהים נלקחים **רק מספרים** (גבהים). הגאורפרנס משמש לשיוך כל תווית למגרש ולפינה. הגבולות עצמם לקוחים מה-DWG.')
w('')
w('## 2. גבולות מגרשים ושטחים')
w('')
w('| חלקה | מגרש | שטח מודל (מ"ר) | שטח רשום (דונם→מ"ר) | סטייה | מקור הגבול |')
w('|---|---|---|---|---|---|')
for l in L['lots']:
    leg = parcels.get(l['parcel'], {}).get('legalArea_dunam')
    src = 'DWG' + (' + קו חלוקה ממפת האורכים' if 'dividing line' in l['ringSource'] else '')
    w(f"| {l['parcel']} | {l['lot']} | {l['area_m2']:.2f} | {leg * 1000:.0f}" + f" | {f(l['area_m2'] - leg * 1000, 2)} | {src} |" if leg else
      f"| {l['parcel']} | {l['lot']} | {l['area_m2']:.2f} | — | — | {src} |")
sp = L['splits'][0]
w('')
w(f"קו החלוקה {sp['merged']}: נקודות {sp['line'][0]} ו-{sp['line'][1]} ממפת האורכים יושבות על המתאר הממוזג שב-DWG במרחק {sp['offOutline_m'][0]:.3f} / {sp['offOutline_m'][1]:.3f} מ'.")
w('')
w('## 3. מפלס ±0.00 (מפלס כניסה קובעת) – תוכנית גבהים מול גיליון 04 הסרוק')
w('')
w('| מגרש | חלקה | תוכנית גבהים (וקטורי) | גיליון 04 (סרוק, נקרא בעין) | סטייה | מצב |')
w('|---|---|---|---|---|---|')
for l in L['lots']:
    pm = l['pm0']; ch = pm.get('check')
    w(f"| {l['lot']} | {l['parcel']} | {pm['z']:.2f} | {ch['sheet04Scan']:.2f} | {f(pm['z'] - ch['sheet04Scan'], 2)} | {pm['status']} |" if ch else
      f"| {l['lot']} | {l['parcel']} | {pm['z']:.2f} | — | — | {pm['status']}{' ⚠' if pm['status'] != 'source' else ''} |")
c57 = L['lot5187Check']
w(f"| 5187 (בדיקה) | 257 | {c57['pm0'][0]['z']:.2f} | 280.50 (וגם ‏H0 במפה למשתכן ובהיתר) | {f(c57['pm0'][0]['z'] - 280.5, 2)} | — |")
w('')
w('## 4. גבהי פינות – תוכנית גבהים מול המפה למשתכן (DWG) בפינות המשותפות')
w('')
w('| חלקה | פינה (ITM) | תוכנית גבהים | מפה למשתכן | סטייה |')
w('|---|---|---|---|---|')
rows = 0
for l in L['lots'] + [{'parcel': '257', 'cornerLevels': c57['corners']}]:
    for c in l['cornerLevels']:
        m = [x for x in mig if x['parcel'] == l['parcel'] and math.dist(x['at'], c['at']) < 2.0]
        if m:
            x = min(m, key=lambda q: math.dist(q['at'], c['at']))
            w(f"| {l['parcel']} | {c['at'][0]:.2f} / {c['at'][1]:.2f} | {c['z']:.2f} | {x['z']:.2f} | {f(c['z'] - x['z'], 2)} |"); rows += 1
w('')
w(f'{rows} פינות משותפות. בשאר הפינות יש מקור אחד בלבד (תוכנית הגבהים).')
w('')
w('## 5. מעטפות – קווי בניין (תמל/1016 §4.1.2: קדמי 3, צדדי 3, אחורי 5) ובדיקה עצמית')
w('')
sc = L['envelopeSelfCheck']
w(f"**בדיקה עצמית:** אותה שגרה הופעלה על 5187 והושוותה לקו הבניין המשורטט במפה למשתכן (`0-BOUNDARY-BUILDING`): סטייה מקסימלית {sc['maxDeviation_m']:.3f} מ' ב-{sc['drawnVertices']} קודקודים, שטח {sc['areaComputed_m2']:.2f} מ\"ר.")
w('')
w('| מגרש | קדמי | צדדי | אחורי | מרחק מינ\' מעטפת–גבול (בדיקה) | תכסית מעטפת (מ"ר) | ±0.00 | גג מעטפת | הערה |')
w('|---|---|---|---|---|---|---|---|---|')
for l in L['lots']:
    env = Polygon(l['envelope']['ring'])
    worst = min(LineString(e['pts']).distance(env) - e['setback_m'] for e in l['edges'])
    k = lambda kind: ', '.join(sorted({e['across'].replace('רחוב (חלקה ', 'רחוב ').replace('רחוב (מחוץ לתרשים החלקות', 'רחוב').rstrip(')') for e in l['edges'] if e['kind'] in kind})) or '—'
    e = l['envelope']
    top = f"{e['base'] + e['height_m']:.2f}" if e['build'] else '— (לא נבנתה)'
    note = 'פינתי – הנחה' if l['frontStatus'] == 'assumption' else ''
    w(f"| {l['lot']} | {k(('front', 'front2'))} | {k(('side',))} | {k(('rear',))} | עודף {f(worst)} מ' | {e['area_m2']:.1f} | {l['pm0']['z']:.2f} | {top} | {note} |")
w('')
w('## 6. רחובות')
w('')
wc = S['integratedStreet']['widthCheck']
sec = S['integratedStreet']['typicalSection']
w('| גודל | מודל | מקור | סטייה |')
w('|---|---|---|---|')
w(f"| רוחב הרחוב המשולב מול 5187 (קו מגרש–קו מגרש, ל-222/223) | {wc['measured_m']:.3f} | {wc['section_m']:.1f} (חתך טיפוסי, תוכנית נוף) | {f(wc['deviation_m'])} |")
gut = [LineString(c['points']) for c in S['integratedStreet']['gutter']]
lot257 = Polygon(J('data', 'site', 'plot-5187.json')['ring'])
dg = sorted(round(gl.distance(lot257), 3) for gl in gut)
w(f"| תעלת ניקוז מרכזית – מרחק מקו המגרש של 5187 | {dg[0]:.2f}–{dg[-1]:.2f} | מרכז הרחוב 6.50 ({sec['total_m']:.1f}/2) | — |")
hs = [s for s in S['surfaces'] if s['heights'] == 'source']
hm = [s for s in S['surfaces'] if s['heights'] == 'missing']
w(f"| שטח רחוב עם גבהים (בתוך מסגרת המפה למשתכן) | {sum(s['area_m2'] for s in hs):.0f} מ\"ר | DWG – קווי גובה מתוכננים | — |")
w(f"| שטח רחוב **ללא** גבהים במקורות | {sum(s['area_m2'] for s in hm):.0f} מ\"ר | — | מוצג שטוח על משטח הייחוס, מסומן בכתום |")
w('')
S4p = os.path.join(ROOT, 'data', 'environment', 'sheet04.json')
if os.path.exists(S4p):
    S4 = json.load(open(S4p, encoding='utf-8')); g4 = S4['georeference']
    w('## 7. גיליון 04 (סרוק): בית, מבנה חניה וכניסה ראשית')
    w('')
    w(f"גאורפרנס: אפיני, {g4['pairs']} סמלי ±0.00 בסריקה מול אותם סמלים בתוכנית הגבהים הווקטורית. שארית חציונית {g4['medianResidual_m']:.3f} מ', מקסימלית {g4['maxResidual_m']:.3f} מ'. "
      f"הפרש קנ\"מ בין הצירים {g4['scaleDifference_pct']}% (עיוות הסריקה – נבלע באפיני).")
    w('')
    w('בדיקה: מרחק הבית שבגיליון מכל גבול, מול קו הבניין בתב"ע. ערך שלילי = הבית בגיליון חורג מקו הבניין (צפוי לכ-0.3 מ\' בגלל דיוק הסריקה והחילוץ).')
    w('')
    w('| מגרש | תכסית בית (מ"ר) | מבנה חניה (מ"ר) | כניסה מ | מרחק מינ\' בית–גבול מול קו בניין | מרחק מגבול 5187 |')
    w('|---|---|---|---|---|---|')
    for r in S4['lots']:
        if r['parcel'] == '257': continue
        be = r.get('buildingToEdges', [])
        worst = min(be, key=lambda e: e['drawn_m'] - e['setback_m']) if be else None
        ws = f"{worst['drawn_m']:.2f} מול {worst['setback_m']:.0f} ({worst['across'].replace('רחוב (חלקה ', 'רחוב ').rstrip(')')})" if worst else '—'
        ef = r.get('entranceFrom', {}).get('across', '—').replace('רחוב (חלקה ', 'רחוב ').rstrip(')')
        d57 = f"{r['buildingTo5187_m']:.2f}" if r.get('buildingTo5187_m') is not None else '—'
        w(f"| {r['lot']} | {r['buildingArea_m2']:.1f} | {r['parkingArea_m2']:.1f} | {ef} | {ws} | {d57} |")
    w('')
open(os.path.join(ROOT, 'docs', 'verification', 'environment.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('\n'.join(out))

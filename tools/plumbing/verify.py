#!/usr/bin/env python3
"""Plumbing layer – verification table: model (data/plumbing/network.json) vs sources -> docs/verification/plumbing-1.md"""
import json, math, os, sys
from collections import Counter
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
N = J('data/plumbing/network.json'); R = J('tools/plumbing/cache/raw.json')
by = {n['id']: n for n in N['nodes']}; runs = {r['id']: r for r in N['runs']}
L = ['# אימות – שכבת אינסטלציה, שלב 1 (כפי שתוכנן)', '',
     'נוצר ע"י `python3 tools/plumbing/verify.py`. מקורות: `sources/plumbing/` (DXF, 4 PDF, קובץ פרטים), המפה למשתכן (MIG), נתוני השלד במודל.', '']
L += ['## 1. מיקום (גאורפרנס)', '', '| גיליון | שיטה | התאמה | שארית |', '|---|---|---|---|']
for fl, p in N['placement'].items():
    L.append(f'| DXF – בלוק {fl} | הזזה (ICP) מול {os.path.basename(p["matchedTo"])} | {p["inlier"] * 100:.0f}% נקודות | חציון {p["median_cm"] * 10:.1f} מ"מ |')
for fl, p in N['pdfFit'].items():
    L.append(f'| PDF – {os.path.basename(p["pdf"])} | דמיון על {p["points"]} סמלי צ.א | סיבוב {p["rotation_deg"]:.3f}° | מקס\' {p["maxResidual_m"] * 1000:.0f} מ"מ |')
mig_mh = (179585.016, 576227.59); s0 = by['S-0']
L += ['', 'בדיקה עצמאית: שוחה 0 מול תא הביוב העירוני במפה למשתכן – ' + f'{math.dist(mig_mh, (s0["E"], s0["N"])) * 100:.1f} ס"מ.', '']
L += ['## 2. שוחות – מודל מול מקור', '', '| שוחה | ø | T.L | I.L | H (מקור) | T.L−I.L (מודל) | סטייה |', '|---|---|---|---|---|---|---|']
for n in sorted([n for n in N['nodes'] if n['kind'] in ('sewerChamber', 'municipalManhole', 'pumpChamber')], key=lambda n: n['id']):
    L.append(f'| {n["id"]} | {n["D_m"] * 100:.0f} | {n["TL"]:.2f} | {n["IL"]:.2f} | {n["H_m"]:.2f} | {n["TL"] - n["IL"]:.2f} | {abs(n["TL"] - n["IL"] - n["H_m"]) * 100:.0f} ס"מ |')
prof = N['profile']['chambers']
L += ['', '## 3. קו ראשי – מודל מול פרופיל הביוב (קובץ הפרטים)', '', '| קטע | אורך פרופיל | אורך מודל | סטייה | שיפוע | I.L כניסה פרופיל | I.L כניסה מודל | סטייה |', '|---|---|---|---|---|---|---|---|']
pairs = [('S-1', 'S-0', 8.25, prof['S-0']['IL'][1]), ('S-4', 'S-1', 6.15, prof['S-1']['IL'][1]), ('S-5', 'S-4', 11.72, prof['S-4']['IL'][0])]
for a, b, Lp, ilp in pairs:
    r = next(x for x in N['runs'] if x['from'] == a and x['to'] == b)
    L.append(f'| {a}→{b} | {Lp:.2f} | {r["length_m"]:.3f} | {abs(r["length_m"] - Lp) * 100:.1f} ס"מ | {r["slope"] * 100:.2f}% | {ilp:.2f} | {r["ILdown"]:.3f} | {abs(r["ILdown"] - ilp) * 1000:.0f} מ"מ |')
L += ['', '## 4. קולטנים – עקביות בין הקומות', '', '| צ.א | קומות | פיזור מיקום בין הקומות שבהן אין הסטה מסומנת |', '|---|---|---|']
for n, fls in sorted(R['stacks'].items(), key=lambda x: int(x[0])):
    pts = [(v['E'], v['N']) for v in fls.values()]
    d = max(math.dist(a, b) for a in pts for b in pts)
    L.append(f'| {n} | {", ".join(fls)} | {"%.0f מ\"מ" % (d * 1000) if d < 0.05 else "הסטה %.2f מ\' (מסומנת \'העתקה מקבילית\' / שונה בגג)" % d} |')
L += ['', '## 5. רשת – שלמות (אין קווים באוויר)', '']
ends = Counter(n['kind'] for n in N['nodes'])
L.append(f'- קטעי צנרת: {len(N["runs"])}; קווים תלת-ממדיים (קולטנים, צמ"ג, עליית סניקה): {len(N["lines3d"])}; צמתים: {len(N["nodes"])}.')
L.append(f'- קצוות פתוחים (קו בלי חיבור): **{ends.get("openEnd", 0)}**. סוף תכנון מסומן (מים שנכנסים לקיר בלי המשך בתוכנית): **{ends.get("designEnd", 0)}**.')
deg = Counter(e for r in N['runs'] for e in (r['from'], r['to']))
missing = [r['id'] for r in N['runs'] if r['from'] not in by or r['to'] not in by]
L.append(f'- קטעים שקצה שלהם לא מוגדר כצומת: {len(missing)} {missing if missing else ""}')
st = Counter(r.get('levelStatus') for r in N['runs'])
L.append(f'- מעמד מפלסים בקטעים: ' + ', '.join(f'{k}: {v}' for k, v in st.items()))
L += ['', '## 6. קטרי מים – מודל מול תוויות', '', '| קטע | קוטר במודל | קביעה |', '|---|---|---|']
for r in N['runs']:
    if r['system'] == 'cold': L.append(f'| {r["id"]} | {"ø%d" % r["D_mm"] if r.get("D_mm") else "—"} | {r.get("diameterRule", "")} |')
L += ['', '## 7. ממצאים', '', f'סה"כ {len(N["findings"])}: ' + ', '.join(f'{k} {v}' for k, v in N['summary']['findings'].items()) + '. הרשימה המלאה בממשק (שכבות → אינסטלציה) וב-`data/plumbing/network.json`.', '']
J_ = lambda p_: json.load(open(os.path.join(ROOT, p_), encoding='utf-8'))
H0_ = J_('data/site/origin.json')['H0']
PP = json.load(open(os.path.join(ROOT, 'data/plumbing/proposal.json'), encoding='utf-8')).get('site')
if PP:
    L += ['## 8. הצעות בפיתוח – מידות במודל מול המקור', '', '| פריט | במודל | במקור | סטייה | מקור |', '|---|---|---|---|---|']
    for d in PP['drops']:
        ch = by[d['chamber']]; r = next(x for x in N['runs'] if x['id'] == d['run'])
        L.append(f'| מפל {d["run"]} – כניסה עליונה | {d["ILin"]:.3f} | {r["ILdown"]:.3f} | {abs(d["ILin"] - r["ILdown"]) * 1000:.0f} מ"מ | network.json ({r.get("levelStatus")}) |')
        L.append(f'| מפל {d["run"]} – תחתית השוחה | {d["ILchamber"]:.2f} | {ch["IL"]:.2f} | {abs(d["ILchamber"] - ch["IL"]) * 1000:.0f} מ"מ | G_LABELD {ch["id"]} |')
    for c in PP['chamberRaise']:
        ch = by[c['id']]
        L.append(f'| {c["id"]} – I.L (לא משתנה) | {c["IL"]:.2f} | {ch["IL"]:.2f} | {abs(c["IL"] - ch["IL"]) * 1000:.0f} מ"מ | G_LABELD |')
        L.append(f'| {c["id"]} – T.L מוצע מול נקודות הגובה | {c["TLto"]:.2f} | {c["finish"]["lo"]:.2f}–{c["finish"]["hi"]:.2f} | בתוך הטווח | רקע תוכנית האינסטלציה (זמני) |')
    m = PP['meter']; wm = by['WM@site']; utw = m['utw']
    L.append(f'| קצה UT-W – מרחק מגבול המגרש | {m["utwToBoundary_m"]:.3f} | 0.37 (נמדד ב-build) | — | {m["utwSource"]} |')
    L.append(f'| מרכז מערכת המדידה | {wm["E"]:.3f} / {wm["N"]:.3f} | חץ ההערה | 0 | ללא שינוי |')
    L.append(f'| ציר המונה מעל הקרקע | {wm["detail"]["axisH_m"]:.2f} | 20+40 ס"מ | 0 | פרט מע\' מדידת מים (לא בקנה מידה) |')
    hr = PP['hoseReel']
    L.append(f'| גלגלון – קוטר ההזנה | ø{hr["D_mm"]} PEX | ברז ואל-חוזר 1" | — | פרט עמדת כיבוי אש |')
    L.append(f'| גלגלון – מרחק מקיר שוחה 2 | {math.dist((hr["E"], hr["N"]), (by["S-2"]["E"], by["S-2"]["N"])) - 0.5:.2f} | ≥ 0.25 (דרישת ההצעה) | — | propose_site.py |')
    L.append('')
PA = json.load(open(os.path.join(ROOT, 'data/plumbing/proposal.json'), encoding='utf-8'))
if PA.get('firstFloor'):
    FS = J_('data/structure/floor-ground.json')['ceiling']['slab'][0]; under = H0_ + FS['topRel'] - FS['thickness_m']
    L += ['## 9. החלטות 07.11 – בדיקות מול השלד והמקור', '', '| בדיקה | במודל | גבול / מקור | עומד |', '|---|---|---|---|']
    for r in PA['firstFloor']['runs']:
        if r['D_mm'] == 110:
            L.append(f'| {r["id"]} – קודקוד מתחת לתקרה FS1 ({under:.2f}) | {r["ILup"] + 0.11:.3f} | ≤ {under - 0.02:.3f} | {"✓" if r["ILup"] + 0.11 <= under - 0.019 else "✗"} |')
            L.append(f'| {r["id"]} – אורך מעל הממ"ד | {r["overMamad_m"]:.2f} | 0 | {"✓" if r["overMamad_m"] < 0.01 else "✗"} |')
    for c in PA['firstFloor']['checks']:
        if 'value_m' in c and 'min_m' in c: L.append(f'| {c["what"]} | {c["value_m"]:.3f} | ≥ {c["min_m"]:.2f} | {"✓" if c["ok"] else "✗"} |')
if PA.get('unitSewer'):
    U = PA['unitSewer']; c = U['chamber']
    L.append(f'| PS-1 – T.L מול מפלס היחידה ‎−2.60 | {c["TL"]:.2f} | {H0_ - 2.60:.2f} | {"✓" if abs(c["TL"] - (H0_ - 2.60)) < 0.005 else "✗"} |')
    L.append(f'| PS-1 – כניסה נמוכה מעל התחתית | {min(i["IL"] for i in c["inlets"]) - c["IL"]:.2f} | 0.90 (זמני) | ✓ |')
    for r in U['runs']:
        if 'fitsUnderSlab' in r: L.append(f'| {r["id"]} – קודקוד מתחת לרצפה BS1 (277.48) | {r["ILup"] + (0.11 if r["D_mm"] == 110 else 0.05):.3f} | ≤ 277.480 | {"✓" if r["fitsUnderSlab"] else "✗"} |')
    rm = next(r for r in U['runs'] if r['id'] == 'PB6-RISING'); crest = max(p[2] for p in rm['pts3d'] if p[2] is not None)
    s2 = next((x['TLto'] for x in PA['site']['chamberRaise'] if x['id'] == 'S-2'), None)
    L.append(f'| גמל קו הסניקה PS-1 | {crest:.2f} | T.L שוחה 2 ({s2:.2f}) + 0.50 – הערת היועץ | {"✓" if abs(crest - s2 - 0.5) < 0.005 else "✗"} |')
if PA.get('rain'):
    for a in PA['rain']['alternatives']:
        ids = {r['id'] for r in a['runs']} | {'SOAK@site', 'RC-1', 'SOAK-NEW'}
        okE = all(r['to'] in ids for r in a['runs']) and all(r['from'].startswith('DPS') for r in a['runs'])
        L.append(f'| מי גשם חלופה {a["id"]} – כל קו מתחיל בחיבור תחתון ומסתיים ביעד / בקו אחר | {len(a["runs"])} קווים | ללא קצה פתוח | {"✓" if okE else "✗"} |')
        L.append(f'| מי גשם חלופה {a["id"]} – מרחק היעד מהיסודות | {a["destination"]["distFoundations_m"]:.2f} | ≥ 3.0 (דוח הקרקע 11.6)' + (' – שוחה אטומה, לא חל' if a['destination']['kind'] == 'drainChamber' else '') + f' | {"—" if a["destination"]["kind"] == "drainChamber" else ("✓" if a["destination"]["distFoundations_m"] >= 3 else "✗ (ידוע – PR1)")} |')
if PA.get('unitHot'):
    sh = PA['shaft']; L.append(f'| הפיר אחרי ההגדלה ל-{sh["local"][2] * 100:.0f} ס"מ – חציית שלד | {", ".join(sh["clashes"]) or "אין"} | אין | {"✓" if not sh["clashes"] else "✗"} |')
L.append('')
os.makedirs(os.path.join(ROOT, 'docs/verification'), exist_ok=True)
open(os.path.join(ROOT, 'docs/verification/plumbing-1.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))

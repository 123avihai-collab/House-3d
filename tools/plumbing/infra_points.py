#!/usr/bin/env python3
"""Infrastructure / connection points of the plumbing (consultant network.json + proposal routes.json):
name, type, purpose, place, levels and what each one connects to -> docs/plumbing/infrastructure-points.md
Usage: python3 tools/plumbing/infra_points.py"""
import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
N, R, C, H0 = J('data/plumbing/network.json'), J('data/plumbing/routes.json'), J('data/config/plan-editor.json')['points'], J('data/site/origin.json')['H0']
SUP = set(R['superseded']['runs'])
GROUPS = ['utility', 'sewage', 'pump', 'rain', 'pool', 'water', 'hot']
SYS = {'sewage': 'ביוב', 'cold': 'מים קרים', 'hot': 'מים חמים', 'rain': 'מי גשם', 'pumped': 'סניקה', 'return': 'סחרור', 'vent': 'אוורור'}
FL = {'site': 'חצר', 'ground': 'קרקע', 'unit': 'מרתף', 'first': "א'", 'roof': 'גג'}
pts = [dict(n, layer='יועץ') for n in N['nodes']] + [dict(n, layer='הצעה') for n in R['nodes']]
def links(n):
    out = []
    for r, lay in [(r, 'יועץ') for r in N['runs']] + [(r, 'הצעה') for r in R['runs']]:
        if n['id'] not in (r.get('from'), r.get('to')): continue
        if lay == 'יועץ' and r['id'] in SUP: continue
        other = r['to'] if r.get('from') == n['id'] else r.get('from')
        out.append(f"{'→' if r.get('from') == n['id'] else '←'} {(other or '?').split('@')[0]} ({SYS.get(r['system'], r['system'])}{' ø' + str(r['D_mm']) if r.get('D_mm') else ''}, {r['id'].split('@')[0]}, {lay})")
    return out
L = ['# נקודות חיבור ותשתיות – אינסטלציה', '', 'נוצר ע"י `python3 tools/plumbing/infra_points.py` מ-`data/plumbing/network.json` (תוכנית היועץ) ו-`data/plumbing/routes.json` (ההצעה). '
     'הייעוד = הכיתוב בתוכנית. גבהים מוחלטים, ובסוגריים יחסית ל-±0.00 (280.50). → = הקו יוצא מהנקודה, ← = נכנס אליה. קווים של היועץ שההצעה מחליפה – לא מופיעים.', '']
for g in GROUPS:
    rows = [n for n in pts if (C['kinds'].get(n['kind']) or ['water'])[0] == g and n['kind'] != 'waterJoint']
    if not rows: continue
    L += [f"## {C['groups'][g]['label']}", '', '| נקודה | סוג | ייעוד | קומה | T.L | I.L | עומק | ø | מתחבר אל | שכבה / סטטוס |', '|---|---|---|---|---|---|---|---|---|---|']
    for n in sorted(rows, key=lambda n: n['id']):
        tl, il = n.get('TL'), n.get('IL')
        f = lambda h: f"{h:.2f} ({h - H0:+.2f})" if h is not None else ''
        L.append(f"| **{n['id'].split('@')[0]}** | {C['kinds'].get(n['kind'], [None, n['kind']])[1]} | {n.get('title') or ''} | {FL.get(n['floor'], n['floor'])} | {f(tl)} | {f(il)} | {f'{tl - il:.2f}' if tl is not None and il is not None else ''} | "
                 f"{f'{n['D_m'] * 100:.0f} ס\"מ' if n.get('D_m') else ''} | {'<br>'.join(links(n)) or '—'} | {n['layer']} · {n.get('status', '')} |")
    L.append('')
L += ['## הערות', '', '- **S-0** – שוחת התאגיד (קיימת, עם הכנת התחברות). כל הביוב של המגרש מתנקז אליה דרך S-1.',
      '- **UT-W** – קצה הכנת המים של התאגיד (מהמפה למשתכן); **WM** – מערכת המדידה (שעון התאגיד) בגומחה. מכאן הקו הראשי לבית.',
      '- **SOAK** – בור החלחול של היועץ: מיקום בלבד, בלי עומק (ראו PR1 – 3 חלופות למי הגשם).',
      '- **PS-1** – תא השאיבה החדש של ההצעה לשפכי יחידות המרתף; **PC-1** – תא השאיבה של היועץ לניקוז החצרות האנגליות.']
open(os.path.join(ROOT, 'docs/plumbing/infrastructure-points.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L[:30]))

#!/usr/bin/env python3
"""Dropped ceiling vs pipes: which proposal pipes (data/plumbing/routes.json) run horizontally in the ceiling space of a
floor with a dropped ceiling (data/finishes/dropped-ceiling.json, provisional), and which hang below it.

For every floor in dropped-ceiling.json: ceiling bottom = the floor's ceilings in data/finishes/plaster/surfaces.json
(under the slab above, not the double-height void). A pipe segment counts when it is horizontal (|dH| < 25% of its plan
length) and its centre is between the floor finish + 2.00 m and the ceiling bottom; its bottom = centre - D/2 (the outer
diameter of the run, mm). bottom >= drop height -> "בתוך ההנמכה" (shares the space with the AC unit / ducts),
bottom < drop height -> "נמוך מההנמכה" (crosses the gypsum: clash).

Writes docs/verification/dropped-ceiling-pipes.md. Run from the repo root: python3 tools/finishes/check_dropped_ceiling.py
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
DC = J('data/finishes/dropped-ceiling.json')
R = J('data/plumbing/routes.json')
P = J('data/finishes/plaster/surfaces.json')
T = J('data/config/tags.json')
H0 = J('data/site/origin.json')
H0 = H0.get('H0') or H0.get('h0') or R['H0']
SYS = {'sewage': 'ביוב', 'cold': 'מים קרים', 'hot': 'מים חמים', 'return': 'חוזר חמים', 'rain': 'מי גשם', 'pumped': 'שאיבה', 'vent': 'אוורור'}
levels = {f['id']: f['level'] for f in T['floors'] if f.get('level') is not None}


def run():
    out = ['# הנמכת תקרה מול הצנרת (זמני)', '',
           'נוצר ע"י `tools/finishes/check_dropped_ceiling.py`. צנרת: הצעת האינסטלציה (`data/plumbing/routes.json`, מקור האמת של העורך). הנמכה: `data/finishes/dropped-ceiling.json` (**זמני**).',
           'סגמנט נספר כשהוא אופקי ומרכזו בין 2.00 מ\' מעל הריצוף לתחתית התקרה; תחתית הצינור = מרכז − קוטר/2.', '']
    for fl, cfg in DC['floors'].items():
        drop = cfg['height_rel']; lv = levels[fl]
        above = min([v for v in levels.values() if v > lv], default=math.inf)
        ceil = min(c['z'] for c in P['ceilings'] if c['floor'] == fl and c['z'] < above)
        out += [f'## {fl}: הנמכה ‎+{drop:.2f}, תחתית תקרה ‎+{ceil:.2f} – מקום {round((ceil - drop) * 100)} ס"מ', '',
                '| צינור | מערכת | קוטר (מ"מ) | גובה מרכז | תחתית | אורך אופקי (מ\') | מצב |', '|---|---|---|---|---|---|---|']
        rows = []
        for r in R['runs']:
            v = r.get('vertices') or []
            D = (r.get('D_mm') or 0) / 1000
            for a, b in zip(v, v[1:]):
                if a[2] is None or b[2] is None: continue   # no level in the proposal (open plumbing issue)
                L = math.hypot(b[0] - a[0], b[1] - a[1]); dz = abs(b[2] - a[2])
                if L < 0.05 or dz > 0.25 * L: continue
                zc = (a[2] + b[2]) / 2 - H0
                if not (lv + 2.0 <= zc < ceil + 0.05): continue
                bot = zc - D / 2
                rows.append((r['id'], SYS.get(r.get('system'), r.get('system')), r.get('D_mm'), zc, bot, L, 'בתוך ההנמכה' if bot >= drop else '⚠ נמוך מההנמכה'))
        agg = {}
        for x in rows:
            k = (x[0], x[6]); a = agg.get(k)
            agg[k] = [x[0], x[1], x[2], min(x[3], a[3]) if a else x[3], min(x[4], a[4]) if a else x[4], (a[5] if a else 0) + x[5], x[6]]
        for x in sorted(agg.values(), key=lambda x: (x[6] != '⚠ נמוך מההנמכה', x[4])):
            out.append(f'| {x[0]} | {x[1]} | {x[2]} | ‎+{x[3]:.2f} | ‎+{x[4]:.2f} | {x[5]:.2f} | {x[6]} |')
        if not agg: out.append('| — | | | | | | אין צנרת אופקית בתחום |')
        clash = sum(1 for x in agg.values() if x[6].startswith('⚠'))
        out += ['', f'סה"כ {len(agg)} צינורות בתחום התקרה, מתוכם **{clash} נמוכים מההנמכה**.', '']
    p = os.path.join(ROOT, 'docs', 'verification', 'dropped-ceiling-pipes.md')
    open(p, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('\n'.join(out))


run()

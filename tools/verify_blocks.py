#!/usr/bin/env python3
"""Self-check of the block-wall layer (data/architecture/blocks.json) against the concrete it meets – Avihai 09.11:
"no gaps between a block and a beam, a window, a door or a shutter box".
For every run, sampled every 5 cm along its axis (and on both faces):
  1. top    – the slab / beam over it: no support = open top; support bottom above the block top = gap; below = clash
  2. bottom – the slab / beam under it: same, the blocks must sit on concrete over the whole length
  3. ends   – each run end must meet another run, concrete or an opening (gap 5 mm … 40 cm = hole in the wall)
  4. openings – blocks over the head need a lintel; the opening must lie inside the run; the shutter box inside the head
Output: docs/verification/blocks-check.json + docs/verification/blocks-check.md"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import Point, LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree
import extract_blocks as XB

ROOT = XB.ROOT
J = XB.J
r3 = XB.r3
STEP, TOL = 0.05, 0.01


def levels_at(items, tree, p, pick):
    hits = [items[i][1] for i in tree.query(p) if items[i][0].covers(p)]
    return pick(hits) if hits else None


def main():
    C = XB.context(); B = J('data/architecture/blocks.json'); L_ = J('data/architecture/blocks.json')['walls']
    trees = {fl: {k: STRtree([g for g, _ in C[k][fl]]) for k in ('under', 'over')} for fl in C['over']}
    runs_by_fl = {}
    for w in B['walls']: runs_by_fl.setdefault(w['floor'], []).append(w)
    poly = lambda w: LineString(w['axisITM']).buffer(w['thickness_m'] / 2, cap_style=2)
    out = []
    for w in B['walls']:
        fl = w['floor']; (x0, y0), (x1, y1) = w['axisITM']; L = w['length_m']; ux, uy = (x1 - x0) / L, (y1 - y0) / L; nx, ny = -uy, ux
        n = max(2, int(L / STEP))
        top = {'open': 0.0, 'gap': [], 'clash': []}; bot = {'open': 0.0, 'gap': [], 'clash': []}
        for i in range(n + 1):
            s = L * i / n
            # an opening that reaches the ceiling / floor is not a block top / bottom there
            op_top = any(o['s0'] - 0.01 <= s <= o['s1'] + 0.01 and o['z1'] >= w['topRel'] - 0.01 for o in w['openings'])
            op_bot = any(o['s0'] - 0.01 <= s <= o['s1'] + 0.01 and o['z0'] <= w['bottomRel'] + 0.01 for o in w['openings'])
            for off in (0.0, -w['thickness_m'] / 2 + 0.02, w['thickness_m'] / 2 - 0.02):
                p = Point(x0 + ux * s + nx * off, y0 + uy * s + ny * off)
                face = off != 0.0      # a face past the edge of a narrower beam / slab: info only (plaster line), not a hole
                if not op_top:
                    z = levels_at(C['over'][fl], trees[fl]['over'], p, min)
                    if z is None: top['open'] += 0 if face else STEP
                    elif z > w['topRel'] + (0.051 if face else TOL): top['gap'].append((round(s, 2), round(z - w['topRel'], 3)))
                    elif z < w['topRel'] - TOL: top['clash'].append((round(s, 2), round(w['topRel'] - z, 3)))
                if not op_bot:
                    z = levels_at(C['under'][fl], trees[fl]['under'], p, max)
                    if z is None: bot['open'] += 0 if face else STEP
                    elif z < w['bottomRel'] - (0.051 if face else TOL): bot['gap'].append((round(s, 2), round(w['bottomRel'] - z, 3)))
                    elif z > w['bottomRel'] + TOL: bot['clash'].append((round(s, 2), round(z - w['bottomRel'], 3)))
        # run ends: what does each end meet?
        others = [poly(o) for o in runs_by_fl[fl] if o is not w] + C['conc'][fl]
        ends = []
        for (ex, ey), sg in (((x0, y0), -1), ((x1, y1), 1)):
            e = Point(ex, ey)
            face = LineString([(ex + nx * w['thickness_m'] / 2, ey + ny * w['thickness_m'] / 2), (ex - nx * w['thickness_m'] / 2, ey - ny * w['thickness_m'] / 2)])
            d = min((g.distance(face) for g in others), default=9)
            if 0.005 < d < 0.40: ends.append({'end': 'start' if sg < 0 else 'end', 'gap_m': r3(d)})
        ops = []
        for o in w['openings']:
            o_ = {'id': o['id']}
            if o['s0'] < -0.01 or o['s1'] > L + 0.01: o_['outsideRun'] = True
            if o['z1'] < w['topRel'] - 0.02 and o['s1'] - o['s0'] < L - 0.02:
                o_['blocksOverHead_m'] = r3(w['topRel'] - o['z1'])
                hasL = any(o['id'] in l['opening'].split('+') and abs(l['z0'] - o['z1']) < 0.005 and l['s0'] <= o['s0'] + 0.005 and l['s1'] >= o['s1'] - 0.005 for l in w.get('lintels', []))
                if not hasL: o_['lintelMissing'] = True
            box = next((b for b in B['shutterBoxes'] if b['opening'] == o['id']), None)
            if box and box.get('box_m'):
                if box['box_m'] > o['z1'] - o['z0'] - 0.3: o_['boxTooTall'] = True                 # the box leaves < 30 cm of glass
                if abs(box['headRel'] - o['z1']) > 0.005: o_['boxNotAtHead_m'] = r3(box['headRel'] - o['z1'])
                if box.get('depth_m') and abs(box['depth_m'] - w['thickness_m']) > 0.005: o_['boxDepthNotWall'] = True
            ops.append(o_)
        sum_ = lambda lst: r3(len(lst) * STEP / 3)
        rec = {'id': w['id'], 'floor': fl, 'length_m': L, 'bottomRel': w['bottomRel'], 'topRel': w['topRel'],
               'topOpen_m': r3(top['open']), 'topGap_m': sum_(top['gap']), 'topGapMax_m': max((g for _, g in top['gap']), default=0),
               'topClash_m': sum_(top['clash']), 'bottomOpen_m': r3(bot['open']), 'bottomGap_m': sum_(bot['gap']),
               'bottomGapMax_m': max((g for _, g in bot['gap']), default=0), 'bottomClash_m': sum_(bot['clash']), 'endGaps': ends, 'openings': ops}
        rec['ok'] = not (rec['topOpen_m'] > 0.05 or rec['topGap_m'] > 0.05 or rec['bottomOpen_m'] > 0.05 or rec['bottomGap_m'] > 0.05
                         or ends or any(o.get('lintelMissing') or o.get('outsideRun') or o.get('boxNotAtHead_m') or o.get('boxDepthNotWall') or o.get('boxTooTall') for o in ops))
        out.append(rec)
    bad = [r for r in out if not r['ok']]
    json.dump({'_doc': 'נוצר ע"י tools/verify_blocks.py – בדיקת מגע של קירות הבלוקים עם הבטון, הפתחים והקירות הסמוכים.', 'runs': out,
               'summary': {'runs': len(out), 'withIssues': len(bad)}}, open(os.path.join(ROOT, 'docs/verification/blocks-check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    lines = ['# בדיקת שכבת הבלוקים – מגע עם בטון, פתחים וקירות סמוכים', '', 'נוצר ע"י `python3 tools/verify_blocks.py`. דגימה כל 5 ס"מ לאורך הציר ובשתי הפאות.', '',
             f'ריצות: {len(out)} · עם ממצא: {len(bad)}', '', '| ריצה | קומה | ראש פתוח (מ\') | רווח בראש (מ\', מקס\') | תחתית פתוחה | רווח בתחתית (מקס\') | קצוות עם רווח | פתחים בלי משקוף |', '|---|---|---|---|---|---|---|---|']
    for r in bad:
        lines.append(f"| {r['id']} | {r['floor']} | {r['topOpen_m'] or ''} | {(str(r['topGap_m']) + ' (' + str(r['topGapMax_m']) + ')') if r['topGap_m'] else ''} | {r['bottomOpen_m'] or ''} | "
                     f"{(str(r['bottomGap_m']) + ' (' + str(r['bottomGapMax_m']) + ')') if r['bottomGap_m'] else ''} | {', '.join(str(e['gap_m']) for e in r['endGaps'])} | "
                     f"{', '.join(o['id'] + ' (' + str(o['blocksOverHead_m']) + ')' for o in r['openings'] if o.get('lintelMissing'))} |")
    open(os.path.join(ROOT, 'docs/verification/blocks-check.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(f'runs {len(out)}, with issues {len(bad)}')
    for r in bad: print(r['id'], {k: r[k] for k in ('topOpen_m', 'topGap_m', 'topGapMax_m', 'bottomOpen_m', 'bottomGap_m', 'bottomGapMax_m')}, r['endGaps'], [o for o in r['openings'] if len(o) > 1])


if __name__ == '__main__':
    main()

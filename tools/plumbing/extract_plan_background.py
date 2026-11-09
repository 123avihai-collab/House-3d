#!/usr/bin/env python3
"""Plan-view background for the 2D pipe editor (editor.html).

Source: the architect background inside the consultant's DXF (sources/plumbing/אינסטלציה חתכים הכל.dxf), one block per
floor (pituah=ground, martef=unit, alef=first, gag=roof). Placement in ITM = the SAME chain the plumbing layer already
uses (data/plumbing/network.json placement.t_cm + basement.json k11ToK400 -> K-400 sheet -> ITM, tools/plumbing/georef.py);
nothing is re-fitted here.

Output: data/plumbing/plan-background.json – per floor, per group (walls / structure / details / openings / fixtures)
a list of polylines [[E, N], ...] (mm), plus room/annotation texts. Re-runnable: python3 tools/plumbing/extract_plan_background.py
"""
import json, math, os, re, sys
import ezdxf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import georef as G

ROOT = G.ROOT
OUT = os.path.join(ROOT, 'data', 'plumbing', 'plan-background.json')
GROUPS = {
    'walls': ('A-WALL', 'I-WALL'),
    'structure': ('S-STRS', 'S-STRS-MBND', 'S-COLS', 'S-BEAM'),
    'details': ('A-DETL', 'A-DETL-THIN', 'A-DETL-MBND', 'A-FLOR', 'A-FLOR-HRAL', 'A-GENM'),
    'openings': ('A-DOOR', 'A-GLAZ', 'A-GLAZ-CWMG'),
    'fixtures': ('P-SANR-FIXT', 'I-FURN'),
}
LAYER2GROUP = {l: g for g, ls in GROUPS.items() for l in ls}
TEXT_LAYERS = ('G-ANNO-TEXT', 'A-GLAZ-IDEN', 'A-DOOR-IDEN')
ARC_STEP_DEG = 15
r3 = lambda v: round(float(v), 3)


def explode(ents, depth=0):
    for v in ents:
        if v.dxftype() == 'INSERT' and depth < 4:
            try: sub = list(v.virtual_entities())
            except Exception: continue
            for s in sub:
                if s.dxf.layer == '0': s.dxf.layer = v.dxf.layer       # block contents on layer 0 take the INSERT's layer
            yield from explode(sub, depth + 1)
        else:
            yield v


def polyline_of(v):
    t = v.dxftype()
    if t == 'LINE': return [(v.dxf.start.x, v.dxf.start.y), (v.dxf.end.x, v.dxf.end.y)]
    if t == 'LWPOLYLINE':
        p = [tuple(q) for q in v.get_points('xy')]
        return p + [p[0]] if v.closed and p else p
    if t in ('ARC', 'CIRCLE'):
        c, r = v.dxf.center, v.dxf.radius
        a0, a1 = (v.dxf.start_angle, v.dxf.end_angle) if t == 'ARC' else (0, 360)
        if a1 < a0: a1 += 360
        n = max(2, math.ceil((a1 - a0) / ARC_STEP_DEG))
        return [(c.x + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), c.y + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    return None


def main():
    net = json.load(open(os.path.join(ROOT, 'data', 'plumbing', 'network.json'), encoding='utf-8'))
    bas = json.load(open(os.path.join(ROOT, 'data', 'structure', 'basement.json'), encoding='utf-8'))
    to_itm = G.make_to_itm(net['placement'], bas['k11ToK400']['translation_pt'])
    msp = ezdxf.readfile(os.path.join(ROOT, G.DXF)).modelspace()
    floors, counts = {}, {}
    for fl, blk in G.BLOCK.items():
        f = to_itm(fl)
        ins = next(e for e in msp.query('INSERT') if e.dxf.name == blk)
        out = {g: [] for g in GROUPS}; texts = []
        for v in explode(list(ins.virtual_entities())):
            lay = v.dxf.layer
            if lay in TEXT_LAYERS and v.dxftype() in ('MTEXT', 'TEXT'):
                s = (v.plain_text() if v.dxftype() == 'MTEXT' else v.dxf.text)
                s = re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), s).strip()   # DXF \U+XXXX escapes
                if len(s) >= 2 and re.search(r'[\w\u0590-\u05FF]', s):   # the DXF splits some words into 1-char MTEXTs – those are dropped
                    E, N = f(v.dxf.insert.x, v.dxf.insert.y)
                    texts.append({'t': s, 'E': r3(E), 'N': r3(N), 'layer': lay})
                continue
            g = LAYER2GROUP.get(lay)
            if not g: continue
            pl = polyline_of(v)
            if not pl or len(pl) < 2: continue
            q = [[r3(c) for c in f(x, y)] for x, y in pl]
            if sum(math.dist(q[i], q[i + 1]) for i in range(len(q) - 1)) < 0.005: continue
            out[g].append(q)
        floors[fl] = {'groups': out, 'texts': texts}
        counts[fl] = {g: len(v) for g, v in out.items()} | {'texts': len(texts)}
    doc = {
        '_doc': 'רקע אדריכלי לעורך הצנרת הדו-ממדי (editor.html). נוצר ע"י tools/plumbing/extract_plan_background.py – לא לערוך ידנית. '
                'קווים = [[E, N], ...] ב-ITM (מ\'). מיקום: אותה שרשרת של שכבת האינסטלציה (network.json placement + basement.json k11ToK400).',
        'source': G.DXF + ' – בלוקים ' + ', '.join(f'{b} ({k})' for k, b in G.BLOCK.items()),
        'placement': {fl: net['placement'][fl] for fl in G.BLOCK},
        'groups': {g: list(ls) for g, ls in GROUPS.items()},
        'floors': floors,
        'counts': counts,
        'status': 'source',
    }
    json.dump(doc, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('wrote', os.path.relpath(OUT, ROOT), f'{os.path.getsize(OUT) / 1024:.0f} KB'); [print(' ', k, v) for k, v in counts.items()]


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Perimeter walls (retaining / boundary walls) -> data/structure/perimeter.json

Plan  : sources/structure/K-400 (foundation plan 1:50, georeferenced in stage 2). Along each lot side the sheet draws the wall
        stem (hatched band) and its footing (grey band). The offsets of those lines from the lot line are measured here:
        north / east / west: stem −0.10…+0.10 (shared wall, centred on the boundary), footing −0.10…+0.70 (B = 0.80);
        south (street): footing 0…0.80 with the stem on the street side.
Section: K-400 "חתך חומה 1:25" + table: B = 0.80, b = 0.60 -> row H = 0.50–1.00: a (footing thickness) = 0.20, h = 0.60.
        Footing bottom = head of the piles 100–118 under it (K-400 "O.K= -0.80"; same convention as the ground beams).
Tops  : architectural wall elevations (sources/architecture/חומה מזרחית + מערבית …, חומה קדמית+ חומה אחורית …).
Run   : python3 tools/extract_perimeter.py
"""
import json, math, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union, substring
from shapely import affinity
import extract_framing as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K400 = 'sources/structure/K-400-תכנית יסודות.pdf'
EW = 'sources/architecture/חומה מזרחית + מערבית - מבט על קנמ 1-10.pdf'
FB = 'sources/architecture/חומה קדמית+ חומה אחורית - מבט על קנמ 1-10.pdf'
SIDE = 1
H0 = json.load(open(os.path.join(ROOT, 'data/site/origin.json'), encoding='utf-8'))['H0']
r3 = lambda v: round(float(v), 3)
RING = json.load(open(os.path.join(ROOT, 'data/site/plot-5187.json'), encoding='utf-8'))['ring']
LOT = Polygon(RING)
PILES = [p for p in json.load(open(os.path.join(ROOT, 'data/structure/piles.json'), encoding='utf-8'))['piles'] if p['id'].isdigit() and int(p['id']) >= 100]


def k400_segments():
    p = pymupdf.open(os.path.join(ROOT, K400))[0]; out = []
    for d in p.get_drawings():
        r = d['rect']
        if not (3000 < r.x0 < 4500 and 20 < r.y0 < 1500) or d.get('color') is None or d.get('dashes') not in (None, '[] 0'): continue
        w = round(d.get('width') or 0, 2)
        if w < 0.5: continue
        for it in d['items']:
            if it[0] == 'l':
                a, b = F.sheet2itm(it[1].x, it[1].y), F.sheet2itm(it[2].x, it[2].y)
                if math.dist(a, b) > 0.3: out.append((a, b, w))
    return out


def offsets_along(path, segs, max_off=1.5):
    """lines parallel to a boundary path: {(offset inward [m], line width): [(s0, s1), …]} (s = distance along the path)"""
    acc = defaultdict(list)
    for a, b, w in segs:
        m = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if m.distance(path) > max_off: continue
        s = path.project(m)
        if s < 0.02 or s > path.length - 0.02: continue
        q0, q1 = path.interpolate(max(s - 0.05, 0)), path.interpolate(min(s + 0.05, path.length))
        tx, ty = q1.x - q0.x, q1.y - q0.y; tl = math.hypot(tx, ty); vx, vy = b[0] - a[0], b[1] - a[1]; vl = math.hypot(vx, vy)
        if abs(vx / vl * ty / tl - vy / vl * tx / tl) > 0.03: continue
        off = (1 if LOT.contains(m) else -1) * m.distance(path)
        s0, s1 = sorted((path.project(Point(a)), path.project(Point(b))))
        acc[(round(off, 2), w)].append((round(s0, 2), round(s1, 2)))
    return acc


def band(path, s0, s1, o0, o1):
    """region between inward offsets o0 < o1 of the boundary path, from s0 to s1 (mitred corners)"""
    sub = substring(path, s0, s1)
    inner = lambda o: sub.offset_curve(SIDE * o, join_style=2) if o else sub   # SIDE: +1 = inward is left of the path (CCW ring)
    a, b = inner(o0), inner(o1)
    ring = list(a.coords) + list(b.coords)[::-1]
    return Polygon(ring).buffer(0)


def main():
    segs = k400_segments()
    # paths (lot ring order: r0 north kink -> r1 NW -> r2 SW -> arc -> r14 SE -> r15 NE -> r0)
    P = {'NW': LineString([RING[0], RING[1]]), 'W': LineString([RING[1], RING[2]]), 'S': LineString(RING[2:15]),
         'E': LineString([RING[14], RING[15]]), 'NE': LineString([RING[15], RING[0]])}
    # inward side: the left of the path for a counter-clockwise ring
    global SIDE
    SIDE = 1 if Polygon(RING).exterior.is_ccw else -1
    for k, path in P.items():
        t = path.offset_curve(SIDE * 0.5).interpolate(0.5, normalized=True)
        assert LOT.contains(t), f'{k}: inward offset is not inside the lot'
    meas = {k: offsets_along(path, segs) for k, path in P.items()}
    def pick(k, lo, hi, w=None):
        c = [(o, ww, sum(b - a for a, b in v)) for (o, ww), v in meas[k].items() if lo <= o <= hi and (w is None or ww == w)]
        return max(c, key=lambda x: x[2]) if c else None
    walls, footings, checks = [], [], []
    TOP = {   # wall tops (absolute) from the architectural elevations; s ranges as fractions of the written dimension chains
        'W': [(0.0, 1.0, 281.90, f'{EW}: "גובה חומה מתוכננת 281.90" (חומה מערבית)')],
        'NW': [(0.0, 1.0, 282.85, f'{FB}: "חומה מתוכננת 282.85" (חומה אחורית). בתוכנית הקרקע: 282.45 – סתירה (#41)')],
        'NE': [(0.0, 1.0, 284.00, f'{FB}: "חומה מתוכננת 284.00" (מעל טרסת הבריכה); {EW}: "284.00"')],
        'E': [(0.0, (0.20 + 15.36) / 23.69, 282.74, f'{EW}: "חומה מתוכננת 282.74", שרשרת "20 | 1536"'),
              ((0.20 + 15.36) / 23.69, (23.69 - 0.61) / 23.69, 282.53, f'{EW}: "חומה מתוכננת 282.53" (חניה), שרשרת "177 | 502 | 73"'),
              ((23.69 - 0.61) / 23.69, 1.0, 281.00, f'{EW}: "פילר 281.00" בפינה הדרום-מזרחית, "61"')],
    }
    # east chain runs north -> south on the elevation; the path E runs south -> north
    TOP['E'] = [(1 - b, 1 - a, t, s) for a, b, t, s in TOP['E']]
    n = 0
    for k in ('W', 'NW', 'NE', 'E'):
        path = P[k]
        o_out = pick(k, -0.2, 0.0, 0.71); o_in = pick(k, 0.0, 0.3, 0.51); o_f = pick(k, 0.4, 1.3, 0.71)
        assert o_out and o_in and o_f, (k, dict(meas[k]))
        checks.append({'side': k, 'stemOuter_m': o_out[0], 'stemInner_m': o_in[0], 'footingInner_m': o_f[0], 'length_m': r3(path.length)})
        for a, b, top, src in TOP[k]:
            n += 1
            g = band(path, a * path.length, b * path.length, o_out[0], o_in[0])
            walls.append({'id': f'PW{n}', 'side': k, 'ringITM': [[r3(x), r3(y)] for x, y in g.exterior.coords[:-1]], 'thickness_m': r3(o_in[0] - o_out[0]),
                          'length_m': r3((b - a) * path.length), 'topRel': r3(top - H0), 'topAbs': top,
                          'status': 'provisional' if k == 'NW' else 'source', 'topSource': src})
        fg = band(path, 0, path.length, o_out[0], o_f[0])
        footings.append({'side': k, 'poly': fg, 'width_m': r3(o_f[0] - o_out[0])})
    # south (street): footing 0 … 0.80 (two lines of 0.71), stem on the street side up to the 0.51 line
    S = P['S']; fo = pick('S', -0.05, 0.05, 0.71); fi = pick('S', 0.6, 1.0, 0.71); si = pick('S', 0.1, 0.3, 0.51)
    assert fo and fi and si, dict(meas['S'])
    fr = meas['S'][(fi[0], 0.71)]; s_f0, s_f1 = min(a for a, b in fr), max(b for a, b in fr)
    sr = meas['S'][(si[0], 0.51)]; s_s1 = max(b for a, b in sr)
    checks.append({'side': 'S', 'stemOuter_m': fo[0], 'stemInner_m': si[0], 'footingInner_m': fi[0], 'footing_s': [s_f0, s_f1], 'stem_s_end': s_s1, 'length_m': r3(S.length)})
    n += 1
    g = band(S, s_f0, s_s1, fo[0], si[0])
    walls.append({'id': f'PW{n}', 'side': 'S', 'ringITM': [[r3(x), r3(y)] for x, y in g.exterior.coords[:-1]], 'thickness_m': r3(si[0] - fo[0]),
                  'length_m': r3(s_s1 - s_f0), 'topRel': r3(281.19 - H0), 'topAbs': 281.19, 'status': 'source',
                  'topSource': f'{FB}: "גובה חומה מתוכננת 281.19 / חומה בנויה" (מעליה גדר קלה עד 281.75 – לא שורטטה)'})
    footings.append({'side': 'S', 'poly': band(S, s_f0, s_f1, fo[0], fi[0]), 'width_m': r3(fi[0] - fo[0])})
    # SW corner: footing link under the utilities pillar (K-400: grey band from pile 115, no stem) – the first metres of the arc
    footings.append({'side': 'SW', 'poly': band(S, 0.0, s_f0, fo[0], fi[0]).union(band(P['W'], P['W'].length - 1.0, P['W'].length, fo[0], fi[0])).buffer(0),
                     'width_m': r3(fi[0] - fo[0]), 'approx': True})
    # pile cap under the gate (pile 111): K-400 box 0 … 1.00 from the boundary, east of the south footing
    cap = pick('S', 0.9, 1.05, 0.71)
    if cap:
        c0, c1 = min(a for a, b in meas['S'][(cap[0], 0.71)]), max(b for a, b in meas['S'][(cap[0], 0.71)])
        footings.append({'side': 'S', 'poly': band(S, c0, c1, fo[0], cap[0]), 'width_m': r3(cap[0] - fo[0]), 'cap': True})
    # gate posts east of the south wall (short hatched pieces at the boundary, 0 … 0.20)
    gp = [(o, w, v) for (o, w), v in meas['S'].items() if abs(o - 0.2) < 0.03 and w == 0.51]
    posts = []
    for a, b in sorted({(a, b) for o, w, v in gp for a, b in v if a > s_s1}):   # merge touching pieces
        if posts and a <= posts[-1][1] + 0.05: posts[-1] = (posts[-1][0], max(posts[-1][1], b))
        else: posts.append((a, b))
    for a, b in posts:
        n += 1
        g = band(S, a, b, 0.0, 0.2)
        walls.append({'id': f'PW{n}', 'side': 'S', 'ringITM': [[r3(x), r3(y)] for x, y in g.exterior.coords[:-1]], 'thickness_m': 0.2, 'length_m': r3(b - a),
                      'topRel': r3(281.75 - H0), 'topAbs': 281.75, 'status': 'provisional', 'post': True,
                      'topSource': f'{FB}: עמודי שער הכניסה ("שער כניסה למגרש", 281.75)'})
    # footing levels: bottom = head of the piles under it (K-400), thickness a = 0.20 (table row B = 0.80)
    A = 0.20
    fo_out = []
    for i, f in enumerate(footings):
        under = [p for p in PILES if f['poly'].buffer(0.05).contains(Point(p['E'], p['N']))]
        heads = sorted({p['headRel'] for p in under})
        bot = min(heads) if heads else -0.80
        fo_out.append({'id': f'PF{i + 1}', 'side': f['side'], 'ringITM': [[r3(x), r3(y)] for x, y in f['poly'].exterior.coords[:-1]],
                       'width_m': f['width_m'], 'bottomRel': r3(bot), 'topRel': r3(bot + A), 'thickness_m': A, 'piles': [p['id'] for p in under],
                       'pileHeads': heads, 'area_m2': r3(f['poly'].area), 'status': 'approx' if f.get('approx') or len(heads) > 1 else 'source',
                       'note': ('ראש כלונס מתחת לשער הכניסה (תיבה ב-K-400). ' if f.get('cap') else '') + ('ראשי כלונסאות שונים מתחת לאותו יסוד: ' + ', '.join(f'{h:+.2f}' for h in heads) + ' – התחתית לפי הנמוך.' if len(heads) > 1 else '')
                               + (' חיבור היסודות בפינה הדרום-מערבית (מתחת לפילר) – בקירוב לפי הצורה ב-K-400.' if f.get('approx') else ''),
                       'source': f'{K400}: רצועה אפורה לאורך הגבול (קווים {f["width_m"]:.2f} מ\' מהגבול), ראשי כלונסאות; עובי a=0.20 לפי טבלת "חתך חומה" (B=0.80)'})
    for w in walls:
        g = Polygon(w['ringITM'])
        f = max(fo_out, key=lambda f: Polygon(f['ringITM']).intersection(g).area)
        on = Polygon(f['ringITM']).intersection(g).area > 0.5 * g.area
        w['bottomRel'] = f['topRel'] if on else r3(-0.60)
        w['standsOn'] = f['id'] if on else None
        if not on: w['status'] = 'provisional'
        w['source'] = f'{K400}: רצועת הקיר (מקווקו) {w["thickness_m"]:.2f} מ\'; ראש: {w["topSource"]}'
    # owner corrections (edit-mode notes): drop elements, keep walls out of the utilities pillar
    FX = json.load(open(os.path.join(ROOT, 'tools/perimeter-fixes.json'), encoding='utf-8'))
    removed = [{'id': w['id'], 'reason': FX['drop'][w['id']]} for w in walls if w['id'] in FX['drop']]
    walls = [w for w in walls if w['id'] not in FX['drop']]
    pil = json.load(open(os.path.join(ROOT, 'data/structure/stairs.json'), encoding='utf-8'))['pillar']
    pil_u = unary_union([Polygon(r) for r in pil['wallsITM']]).buffer(0)
    for w in walls:
        if w['id'] not in FX['clipToPillar']: continue
        g = Polygon(w['ringITM']); cut = g.difference(pil_u)
        if g.area - cut.area < 1e-6: continue
        cut = max(getattr(cut, 'geoms', [cut]), key=lambda x: x.area)
        w['ringITM'] = [[r3(x), r3(y)] for x, y in cut.exterior.coords[:-1]]
        w['clippedByPillar_m2'] = r3(g.area - cut.area)
        w['length_m'] = r3(w['length_m'] - (g.area - cut.area) / w['thickness_m'])
        w['topSource'] += '; ' + FX['clipToPillar'][w['id']]
    out = {'_doc': 'Perimeter walls + footings. Generated by tools/extract_perimeter.py – do not edit by hand.',
           'removedByOwner': removed,
           'measuredOffsets': checks,
           'section': {'B_m': 0.80, 'b_m': 0.60, 'a_m': A, 'h_m': 0.60, 'tableRow': 'H = 0.50–1.00', 'source': f'{K400}: "חתך חומה 1:25" + טבלה'},
           'walls': walls, 'footings': fo_out}
    json.dump(out, open(os.path.join(ROOT, 'data/structure/perimeter.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for c in checks: print(c)
    print('walls', [(w['id'], w['side'], w['length_m'], w['thickness_m'], w['topAbs'], w['bottomRel'], w['status']) for w in walls])
    print('footings', [(f['id'], f['side'], f['area_m2'], f['width_m'], f['bottomRel'], f['piles']) for f in fo_out])


if __name__ == '__main__':
    main()

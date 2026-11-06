#!/usr/bin/env python3
"""Swimming pool + machine room / balance tank -> data/structure/pool.json (stage 2b: cast with the basement).

Plan outline: the pool / tank walls of k-21.dxf (IfcWall hatches, placed on K-400 like the rest of the structure).
Levels: the architectural pool sections (sources/structure/pool-walls/בריכה חתך א+ב.pdf, absolute levels written on the
sheet) and the pile heads under the pool in K-400. The structural pool drawing ("ראה תכנית בריכה") is still missing, so
slab underside / thickness are PROVISIONAL (see docs/open-issues.md).
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_framing as F
from shapely.geometry import Polygon, MultiPoint, box
from shapely.ops import unary_union

ROOT = F.ROOT; r3 = F.r3
SEC = 'sources/structure/pool-walls/בריכה חתך א+ב.pdf'
# levels written on the section sheet (absolute, m)
DECK, FLOOR, STEPS, TANK_FLOOR, TANK_SLAB = 280.48, 279.30, 279.97, 278.33, 0.20
# measured on the sections at the verified 1:50 scale (level-marker tips: 280.48→279.30 = 67 pt = 1.18 m = written "118"):
TANK_WALL = 0.20          # K-400: 530.8→542.2 pt = 0.20 m
POOL_FINISH_LAYER = 0.27  # "27": floor finish 279.30 -> structural slab top 279.03 (section A)
POOL_SLAB_TOP, POOL_SLAB_BOT_E, POOL_SLAB_BOT_W = 279.03, 278.83, 279.03   # 20 cm slab; sloped 4.9% (section B) -> ~0.20 m higher at the shallow end
POOL_WALL_BOTTOM = 278.13 # section A draws both pool walls down to 278.13 – conflicts with K-400 pile heads 279.30/279.00 (open-issues); model: south wall (shared with the machine room) only
DECK_SLAB_TOP = 280.33    # deck slab top (finish 280.48)
GUTTER_W, LIP_W, GUTTER_FLOOR, GUTTER_BOT = 0.25, 0.20, 280.13, 280.05   # overflow gutter (תעלת גלישה): width K-400 (0.247) / section A (0.24-0.25); levels section A
CHANNEL_FLOOR, CHANNEL_BOTTOM = 280.05, 279.90               # cover-shutter pit (section B), slab 15 cm
ring = lambda g: [[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]]


def hatches():
    m21 = F.read_dxf(F.K21)
    t = json.load(open(os.path.join(ROOT, 'data/structure/framing.json'), encoding='utf-8'))['placement']['k21dxf']['translation_pt']
    to = lambda x, y: F.sheet2itm(x * F.S_CM + t[0], -y * F.S_CM + t[1])
    out = []
    for h in m21.query('HATCH[layer=="IfcWall"]'):
        for path in h.paths:
            vs = [(v[0], v[1]) for v in path.vertices] if hasattr(path, 'vertices') else [(e.start[0], e.start[1]) for e in path.edges if e.EDGE_TYPE == 'LineEdge']
            if len(vs) >= 3:
                g = Polygon([to(x, y) for x, y in vs]).buffer(0)
                out += [q for q in getattr(g, 'geoms', [g]) if q.geom_type == 'Polygon' and q.area > 0.05]
    return out


def main():
    P = {p['id']: p for p in json.load(open(os.path.join(ROOT, 'data/structure/piles.json'), encoding='utf-8'))['piles']}
    H0 = json.load(open(os.path.join(ROOT, 'data/site/origin.json'), encoding='utf-8'))['H0']
    hs = hatches()
    sel = json.load(open(os.path.join(ROOT, 'tools/pool-pieces.json'), encoding='utf-8'))
    from shapely.geometry import Point as _P
    pick = lambda pts: [next(q for q in hs if q.buffer(0.02).contains(_P(x, y))) for x, y in pts]
    pool_walls, ch_walls, tank_walls = pick(sel['pool']), pick(sel['channel']), pick(sel['tank'])
    pool_outer = unary_union(pool_walls).minimum_rotated_rectangle
    ch_outer = unary_union(ch_walls).minimum_rotated_rectangle.difference(pool_outer).buffer(0)
    ch_outer = max(getattr(ch_outer, 'geoms', [ch_outer]), key=lambda g: g.area)
    # pool-local frame on the pool side that faces the machine room: u along the side, v outward (m)
    import numpy as np
    from shapely.geometry import LineString
    C = np.array(pool_outer.exterior.coords[:4]); tc = unary_union(tank_walls).centroid
    i = min(range(4), key=lambda k: LineString([C[k], C[(k + 1) % 4]]).distance(tc))
    a, b = C[i], C[(i + 1) % 4]; u = (b - a) / np.linalg.norm(b - a); n = np.array([u[1], -u[0]])
    if np.dot(np.array(pool_outer.centroid.coords[0]) - a, n) > 0: n = -n
    loc = lambda g: [(float(np.dot(np.array(q) - a, u)), float(np.dot(np.array(q) - a, n))) for q in g.exterior.coords]
    rect = lambda u0, u1, v0, v1: Polygon([tuple(a + s_ * u + t_ * n) for s_, t_ in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))])
    lb = lambda g: (min(p[0] for p in loc(g)), max(p[0] for p in loc(g)), min(p[1] for p in loc(g)), max(p[1] for p in loc(g)))
    # overflow gutter ring: K-400 – gutter 14.0 pt = 0.25 m + outer lip wall 11.4 pt = 0.20 m (outer ring 25.5 pt = 0.45 m from the pool, all sides)
    gut_in = pool_outer.buffer(GUTTER_W, join_style=2); gut = pool_outer.buffer(GUTTER_W + LIP_W, join_style=2)
    gutter_floor = gut.difference(pool_outer).buffer(0); lip = gut.difference(gut_in).buffer(0)
    # machine room (K-400): box from the gutter lip to its south wall; the k-21 walls start at the lip's outer face (0.45 m),
    # the lip itself is its north wall, and its side walls run through under the gutter to the pool wall.
    u0, u1, v0, v1 = lb(unary_union(tank_walls).minimum_rotated_rectangle)
    tank_outer = rect(u0, u1, GUTTER_W, v1)
    extra = [rect(u0, u1, GUTTER_W, GUTTER_W + LIP_W),   # north wall = gutter lip
             rect(u0, u1, v1 - TANK_WALL, v1)]             # south wall continuous in K-400 (k-21 shows it cut by an opening above the floor)
    tank_pit = rect(u0, u1, 0.0, v1)                       # walls on both sides of the strip under the gutter reach the machine-room bottom
    under_gutter = []   # side walls continued under the gutter: they stop at the gutter's underside so the gutter stays open
    for w in tank_walls:
        wu0, wu1, wv0, wv1 = lb(w)
        if wv0 - v0 < 0.05 and wu1 - wu0 < 0.4: under_gutter.append(rect(wu0, wu1, 0.0, GUTTER_W))
    tank_walls = tank_walls + extra
    tank_check = {'k21_offsetFromPool_m': r3(v0), 'expected_m': GUTTER_W + LIP_W, 'eastEnd_vs_poolEnd_m': r3(min(abs(u0), abs(u1 - 8.40), abs(u1), abs(u0 - 8.40)))}
    west = [P[k]['headRel'] + H0 for k in ('28', '30')]; east = [P[k]['headRel'] + H0 for k in ('29', '31')]
    out = {
        'pool': {'outerITM': ring(pool_outer), 'area_m2': r3(pool_outer.area), 'wallsITM': [ring(q) for q in pool_walls],
                 'deck': DECK, 'floorFinish': FLOOR, 'stepsLevel': STEPS,
                 'finishLayer_m': POOL_FINISH_LAYER, 'slabTop': POOL_SLAB_TOP, 'slabUndersideWest': POOL_SLAB_BOT_W, 'slabUndersideEast': POOL_SLAB_BOT_E,
                 'wallBottom': POOL_WALL_BOTTOM, 'deckSlabTop': DECK_SLAB_TOP,
                 'pileHeads': {'west_28_30': r3(min(west)), 'east_29_31': r3(min(east))},
                 'status': 'provisional',
                 'note': 'מחתכי הבריכה (קנ"מ 1:50 אומת): סיפון 280.48 (משטח בטון 280.33), רצפה 279.30 בעומק 1.20 ("118"), שכבת גמר 27 ס"מ, רצפת בטון 279.03–278.83 (20 ס"מ, משופעת 4.9% – בצד הרדוד גבוהה בכ-20 ס"מ), קירות 20 ס"מ יורדים עד 278.13. תעלת גלישה ברוחב 24 ס"מ מסביב (רצפה 280.13). ראשי כלונסאות 28–31 (279.30/279.00) נכנסים לקירות. מצע מתחת לרצפה – לא כתוב.',
                 'source': f'{F.K21} (קירות הבריכה, IfcWall); {SEC} (מפלסים); {F.K400} (ראשי כלונסאות 28–31)'},
        'gutter': {'ringOuterITM': ring(gut), 'ringInnerITM': ring(gut_in), 'width_m': GUTTER_W, 'lipWidth_m': LIP_W,
                   'floor': GUTTER_FLOOR, 'bottom': GUTTER_BOT, 'lipTop': DECK_SLAB_TOP, 'status': 'source',
                   'note': 'תעלת גלישה סביב הבריכה: רוחב 25 ס"מ + שפה חיצונית 20 ס"מ (K-400: טבעת 45 ס"מ סביב הבריכה; חתך א). רצפת התעלה 280.13–280.05, ראש השפה 280.33. במזרח השפה היא הקיר המערבי של תעלת הכיסוי; בדרום – הקיר הצפוני של חדר המכונות.',
                   'source': f'{F.K400}; {SEC}'},
        'channel': {'outerITM': ring(ch_outer), 'area_m2': r3(ch_outer.area), 'wallsITM': [ring(q) for q in ch_walls], 'top': DECK,
                    'floor': CHANNEL_FLOOR, 'bottom': CHANNEL_BOTTOM, 'status': 'source',
                    'note': 'תעלת תריס כיסוי הבריכה (בצד המזרחי, מעבר לתעלת הגלישה; K-400/K-21). רוחב פנים 45 ס"מ, רצפה 280.05, תחתית 279.90 – נמדדו בחתך ב (קנ"מ 1:50 מאומת).',
                    'source': f'{F.K21} (IfcWall); tools/pool-pieces.json; {F.K400}'},
        'tank': {'outerITM': ring(tank_outer), 'pitITM': ring(tank_pit), 'underGutterWallsITM': [ring(q) for q in under_gutter], 'underGutterWallsTop': GUTTER_BOT, 'area_m2': r3(tank_outer.area), 'wallsITM': [ring(q) for q in tank_walls],
                 'top': DECK_SLAB_TOP, 'floorFinish': TANK_FLOOR, 'slabThickness_m': TANK_SLAB, 'slabUnderside': r3(TANK_FLOOR - TANK_SLAB),
                 'joinedToPool': 'צמוד לבריכה (K-400, חתך א): הקיר הצפוני = שפת תעלת הגלישה (0.25–0.45 מ מהבריכה), קירות הצד ממשיכים מתחת לתעלה עד קיר הבריכה',
                 'check': tank_check, 'wallBottom': r3(TANK_FLOOR - TANK_SLAB),
                 'pile32Head': r3(P['32']['headRel'] + H0), 'status': 'source',
                 'note': 'חדר מכונות (רצפה 278.33, עומק 2.17, גובה פנים "180", רצפה "20" ס"מ – מחתך א, קנ"מ 1:50 מאומת); פתח בור האיזון מעליו. ראש כלונס 32 (278.25) נכנס לרצפה (תחתית 278.13).',
                 'source': f'{F.K21} (קירות, IfcWall); {SEC} (מפלסים); {F.K400} (כלונס 32)'},
        'castWith': 'basement', 'stages': {'excavation': 'excavation', 'slab': 'slab', 'walls': 'walls'},
    }
    json.dump(out, open(os.path.join(ROOT, 'data/structure/pool.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('pool walls', len(pool_walls), 'area', r3(pool_outer.area), [r3(v) for v in pool_outer.bounds], 'west', west, 'east', east)
    print('tank walls', len(tank_walls), 'area', r3(tank_outer.area)); print('channel', len(ch_walls), 'area', r3(ch_outer.area))


if __name__ == '__main__':
    main()

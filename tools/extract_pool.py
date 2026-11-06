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
POOL_SLAB = 0.27          # dimension "27" under the pool floor (section A); section scale verified 1:50 (280.48→279.30 = 67 pt = 1.18 m = written "118")
CHANNEL_BOTTOM = 279.75   # cover-shutter pit (section B, right): bottom of its slab measured at the verified 1:50 scale from the 280.48 level line
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
    tank_outer = unary_union(tank_walls).minimum_rotated_rectangle.difference(pool_outer).buffer(0)
    tank_outer = max(getattr(tank_outer, 'geoms', [tank_outer]), key=lambda g: g.area)
    west = [P[k]['headRel'] + H0 for k in ('28', '30')]; east = [P[k]['headRel'] + H0 for k in ('29', '31')]
    out = {
        'pool': {'outerITM': ring(pool_outer), 'area_m2': r3(pool_outer.area), 'wallsITM': [ring(q) for q in pool_walls],
                 'deck': DECK, 'floorFinish': FLOOR, 'stepsLevel': STEPS,
                 'slabThickness_m': POOL_SLAB, 'slabUndersideWest': r3(min(west)), 'slabUndersideEast': r3(FLOOR - POOL_SLAB),
                 'checkDeepEnd': {'fromSection': r3(FLOOR - POOL_SLAB), 'pileHeads29_31': r3(min(east))},
                 'status': 'provisional',
                 'note': 'מחתכי הבריכה (קנ"מ 1:50 אומת מול המפלסים הכתובים): סיפון 280.48, רצפה 279.30 בעומק 1.20 ("118"), עובי רצפה 27 ס"מ → תחתית 279.03 בצד העמוק (מול ראשי כלונסאות 29/31: 279.00 – הפרש 3 ס"מ). מדרגות 279.97, שיפוע 4.9%. בצד הרדוד – תחתית לפי ראשי כלונסאות 28/30 (279.30). מצע מתחת לרצפה – לא כתוב.',
                 'source': f'{F.K21} (קירות הבריכה, IfcWall); {SEC} (מפלסים); {F.K400} (ראשי כלונסאות 28–31)'},
        'channel': {'outerITM': ring(ch_outer), 'area_m2': r3(ch_outer.area), 'wallsITM': [ring(q) for q in ch_walls], 'top': DECK,
                    'bottom': CHANNEL_BOTTOM, 'status': 'source',
                    'note': 'תעלת תריס כיסוי הבריכה (הקופסה הצרה בצד המזרחי, K-400/K-21). תחתית 279.75 – נמדדה בחתך ב (קנ"מ 1:50 מאומת) מקו הסיפון 280.48.',
                    'source': f'{F.K21} (IfcWall); tools/pool-pieces.json; {F.K400}'},
        'tank': {'outerITM': ring(tank_outer), 'area_m2': r3(tank_outer.area), 'wallsITM': [ring(q) for q in tank_walls],
                 'top': DECK, 'floorFinish': TANK_FLOOR, 'slabThickness_m': TANK_SLAB, 'slabUnderside': r3(TANK_FLOOR - TANK_SLAB),
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

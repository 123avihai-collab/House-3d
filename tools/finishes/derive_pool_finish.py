#!/usr/bin/env python3
"""Pool tiling + coping surfaces, derived from data/structure/pool.json (no dimension is typed here).

Input:  data/structure/pool.json  (k-21 pool walls, pool sections / plan 1:50: floor 279.30, deck 280.48, steps, platform)
Output: data/finishes/pool/surfaces.json  (derived – do not edit by hand)

  innerRingITM  the water face of the pool walls = the outer ring of the walls offset in by the wall thickness
                (each side: the k-21 wall band; 0.200 m all round)
  floor         the pool floor finish (279.30) = the inner ring
  blocks        the entry steps and the lounge platform (top + ring) – tiled on top and on every exposed side
  faces         vertical faces of the blocks: for every edge, the height of what is next to it (pool floor or the
                next block) up to the block top; edges on the pool wall are covered by the wall tiles (skipped)
  wall          the four wall faces (inner ring edges) from the floor up to the coping underside (the coping
                thickness is chosen in the workshop: data/finishes/pool/catalog.json)
  coping        the wall top: outer edge = outer face of the pool walls, inner edge = water face (+ overhang, chosen),
                top = the deck finish level 280.48 ("משטח מרוצף נוגד החלקה", sections A/B)
"""
import json, math, os
from shapely.geometry import Polygon, Point

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = 'data/structure/pool.json'
OUT = 'data/finishes/pool/surfaces.json'
r3 = lambda v: round(v, 3)


def wall_thickness(P):
    """per side of the outer ring: the farthest wall vertex inside that side's band (k-21 walls)."""
    O = P['outerITM']; pts = [p for w in P['wallsITM'] for p in w]; out = []
    for i in range(len(O)):
        a, b = O[i], O[(i + 1) % len(O)]; dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L
        ds = [abs((p[0] - a[0]) * nx + (p[1] - a[1]) * ny) for p in pts
              if -0.01 <= ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L <= L + 0.01 and abs((p[0] - a[0]) * nx + (p[1] - a[1]) * ny) < 0.35]
        out.append(max(ds))
    return out


def main():
    D = json.load(open(os.path.join(ROOT, SRC)))
    P = D['pool']
    O = P['outerITM']
    th = wall_thickness(P)
    t = round(sum(th) / len(th), 3)
    assert max(th) - min(th) < 0.003, th
    outer = Polygon(O)
    inner = outer.buffer(-t, join_style=2)
    ring = [[r3(x), r3(y)] for x, y in list(inner.exterior.coords)[:-1]]
    if Polygon(ring).exterior.is_ccw != Polygon(O).exterior.is_ccw: ring.reverse()
    # start the inner ring at the corner nearest to O[0] (same winding / side order as the outer ring)
    k = min(range(len(ring)), key=lambda i: math.dist(ring[i], O[0])); ring = ring[k:] + ring[:k]
    sides = [math.dist(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]
    long_i = max(range(len(sides)), key=lambda i: sides[i])
    a, b = ring[long_i], ring[(long_i + 1) % len(ring)]
    axis = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))

    blocks = [{'id': f'step{i + 1}', 'label': f'מדרגה {i + 1}', 'kind': 'step', 'ringITM': s['ringITM'], 'top': s['top']} for i, s in enumerate(P.get('steps', []))]
    if P.get('platform'): blocks.append({'id': 'platform', 'label': 'משטח רביצה', 'kind': 'platform', 'ringITM': P['platform']['ringITM'], 'top': P['platform']['top']})
    floor = P['floorFinish']
    inner_poly = Polygon(ring)
    faces = []; covered = 0.0
    for bl in blocks:
        R = bl['ringITM']; poly = Polygon(R)
        sgn = 1 if poly.exterior.is_ccw else -1
        for i in range(len(R)):
            p, q = R[i], R[(i + 1) % len(R)]; dx, dy = q[0] - p[0], q[1] - p[1]; L = math.hypot(dx, dy)
            if L < 0.005: continue
            nx, ny = dy / L * sgn, -dx / L * sgn   # outward normal
            m = Point((p[0] + q[0]) / 2 + nx * 0.03, (p[1] + q[1]) / 2 + ny * 0.03)
            if not inner_poly.contains(m): covered += L * (bl['top'] - floor); continue   # against the pool wall – hides that part of the wall tiles
            nb = [o['top'] for o in blocks if o is not bl and Polygon(o['ringITM']).contains(m)]
            z0 = max(nb) if nb else floor
            if z0 >= bl['top'] - 0.001: continue
            faces.append({'block': bl['id'], 'a': p, 'b': q, 'z0': r3(z0), 'z1': bl['top'], 'normal': [r3(nx), r3(ny)], 'riser': bl['kind'] == 'step' and abs(dx * math.cos(math.radians(axis)) + dy * math.sin(math.radians(axis))) / L < 0.2})
    foot = sum(Polygon(b['ringITM']).area for b in blocks)
    out = {
        '_doc': 'נגזר מ-data/structure/pool.json ע"י tools/finishes/derive_pool_finish.py – לא לערוך ידנית. משטחי הריצוף של הבריכה (רצפה, קירות, מדרגות, משטח רביצה) והקופינג על ראש קירות הבריכה. הבחירה (אריח, קופינג) – סדנת הריצוף, data/finishes/pool/catalog.json / layout.json.',
        'source': f"{SRC} ← {P['source']}; {P.get('stepsSource', '')}",
        'status': 'provisional',
        'wallThickness_m': t,
        'outerRingITM': O,
        'innerRingITM': ring,
        'innerSides_m': [r3(s) for s in sides],
        'axis_deg': round(axis, 3),
        'floor': floor,
        'copingTop': P['deck'],
        '_copingTop': 'ראש הקופינג = מפלס המשטח המרוצף סביב הבריכה 280.48 (חתכים א/ב: "משטח מרוצף נוגד החלקה"; קיר הבריכה מגיע עד הקו הזה). עובי הקופינג – לבחירה (זמני). ראש בטון הקיר מתחת לקופינג – לא כתוב (open-issues).',
        'gutter': {'width_m': D['gutter']['width_m'], 'floor': D['gutter']['floor'], 'lipTop': D['gutter']['lipTop']},
        'blocks': blocks,
        'blockFaces': faces,
        'areas': {'floorInner_m2': r3(inner_poly.area), 'blocksFootprint_m2': r3(foot), 'floorNet_m2': r3(inner_poly.area - foot),
                  'blockTops_m2': r3(foot), 'blockSides_m2': r3(sum(math.dist(f['a'], f['b']) * (f['z1'] - f['z0']) for f in faces)),
                  'perimeterInner_m': r3(sum(sides)), 'wallCoveredByBlocks_m2': r3(covered)},
    }
    json.dump(out, open(os.path.join(ROOT, OUT), 'w'), ensure_ascii=False, indent=1)
    print(OUT, 'wall', t, 'inner', [r3(s) for s in sides], 'axis', round(axis, 2), 'faces', len(faces), out['areas'])


if __name__ == '__main__':
    main()

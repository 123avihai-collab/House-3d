#!/usr/bin/env python3
"""Plaster coverage sweep (Avihai 11.11: "go over all the walls and beams – what is not plastered"): every vertical face of
every wall / column / beam / slab edge is sampled (0.25 m along, 0.2 m up). A sample that faces air (not soil, not another
element, not an opening) must lie on a finish surface (plaster of any type, membrane, cladding, 'none' side of a
neighbour wall, reveal). Uncovered samples are reported per element -> docs/verification/finishes-coverage.md"""
import json, math, os, runpy, sys
from collections import defaultdict
from shapely.geometry import Point, LineString, Polygon
from shapely.prepared import prep
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
os.environ['FINISHES_NO_XLSX'] = '1'
G = runpy.run_path(os.path.join(ROOT, 'tools', 'finishes', 'derive_finishes.py'), run_name='coverage')
SOL, SLABS, BEAMS, FACES, REVS, BEAMSURF, OP, CFG = (G[k] for k in ('SOL', 'SLABS', 'BEAM_LIST', 'FACES', 'REVS', 'BEAMSURF', 'OP', 'CFG'))
INFILL, COURTS, STAIR, ROOMS = G['INFILL'], G['COURTS'], G['STAIR'], G['ROOMS']
unit_normal = G['unit_normal']
OCC = [(prep(s['poly']), s['bottom'], s['top']) for s in SOL + INFILL] + [(prep(s['poly']), s['bottom'], s['top']) for s in SLABS] + \
      [(b['P'], b['bottomRel'], b['topRel']) for b in BEAMS]
OPEN = []
for o in OP:
    if o['id'].startswith('OC-'): continue
    c, (ax, ay), w = o['centerITM'], o['axisITM'], o['width_m']
    OPEN.append((prep(LineString([(c[0] - ax * w / 2, c[1] - ay * w / 2), (c[0] + ax * w / 2, c[1] + ay * w / 2)]).buffer(0.4, cap_style=2)), o['sillRel'] - 0.2, o['headRel']))
for c in G['GAPCL'] + G['CLOSERS']: OPEN.append((prep(c['poly'].buffer(0.05)), c['bottom'] if c['bottom'] > -90 else -9, c['top'] if c['top'] < 90 else 99))
# finish surfaces as vertical patches: (line, z0, z1, holes)
PATCH = []
for f in FACES: PATCH.append((LineString([f['a'], f['b']]), f['z0'], f['z1']))
for b in BEAMSURF:
    for x in b['sides']: PATCH.append((LineString([x['a'], x['b']]), x['z0'], x['z1']))
for r in REVS:
    for q in r['quads']:
        if q['part'] == 'jamb': PATCH.append((LineString([q['q'][0][:2], q['q'][1][:2]]), q['q'][0][2], q['q'][2][2]))
for x in json.load(open(os.path.join(ROOT, 'data/finishes/cladding/surfaces.json')))['items']: PATCH.append((LineString([x['a'], x['b']]), x['z0'], x['z1']))
GRID = defaultdict(list)
for k, (ln, z0, z1) in enumerate(PATCH):
    x0, y0, x1, y1 = ln.bounds
    for i in range(int(x0 // 2) - 1, int(x1 // 2) + 2):
        for j in range(int(y0 // 2) - 1, int(y1 // 2) + 2): GRID[(i, j)].append(k)


def covered(p, z):
    for k in GRID[(int(p[0] // 2), int(p[1] // 2))]:
        ln, z0, z1 = PATCH[k]
        if z0 - 0.03 <= z <= z1 + 0.03 and ln.distance(Point(p)) < 0.045: return True
    return False


def air(q, z):
    P = Point(q)
    for pp, b, t in OCC:
        if b - 0.005 <= z <= t + 0.005 and pp.contains(P): return False
    for pp, b, t in OPEN:
        if b <= z <= t and pp.contains(P): return False
    # soil: outside the house, below the slab / ground there (no outdoor slab and below ±0.00 = planned ground ≈ house floor)
    # soil: below ±0.00-ish with no slab under the point at any level (outside the house, under the courts' slabs)
    if z < -0.15 and G['floor_at'](q, z, reach=(0.02,)) is None: return False
    return True


def sweep(name, poly, z0, z1, kind):
    bad = 0.0; pts = []
    for g in getattr(poly, 'geoms', [poly]):
        for ring in [g.exterior] + list(g.interiors):
            cs = list(ring.coords)
            for A, B in zip(cs, cs[1:]):
                L = math.dist(A, B)
                if L < 0.05: continue
                ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
                nx, ny = unit_normal(A, B, True)
                if g.contains(Point((A[0] + B[0]) / 2 + nx * 0.02, (A[1] + B[1]) / 2 + ny * 0.02)): nx, ny = -nx, -ny
                n = max(1, int(L / 0.25)); ds = L / n
                for i in range(n):
                    s_ = (i + 0.5) * ds; p = (A[0] + ux * s_, A[1] + uy * s_); q = (p[0] + nx * 0.03, p[1] + ny * 0.03)
                    m = max(1, int((z1 - z0) / 0.2)); dz = (z1 - z0) / m
                    for j in range(m):
                        z = z0 + (j + 0.5) * dz
                        if air(q, z) and not covered(p, z): bad += ds * dz; pts.append((round(p[0], 2), round(p[1], 2), round(z, 2)))
    return bad, pts


rows = []
for s in SOL:
    a, pts = sweep(s['id'], s['poly'], s['bottom'], s['top'], s['kind'])
    if a > 0.05: rows.append((s['kind'], s['id'], s['floor'], a, pts[:3]))
for b in BEAMS:
    a, pts = sweep(b['id'], b['R'], b['bottomRel'], b['topRel'], 'beam')
    if a > 0.05: rows.append(('beam', b['id'], b.get('floorOf'), a, pts[:3]))
for sl in SLABS:
    if sl['id'][:2] not in ('FS', 'RS'): continue
    a, pts = sweep(sl['id'], sl['poly'], sl['bottom'], sl['top'], 'slab')
    if a > 0.05: rows.append(('slab', sl['id'], '', a, pts[:3]))
rows.sort(key=lambda r: -r[3])
L = ['# בדיקת כיסוי טיח – כל פני הקירות, העמודים, הקורות ושפות התקרות', '',
     'נוצר ב-`python3 tools/finishes/verify_coverage.py`. דגימה כל 25 ס"מ לאורך וכל 20 ס"מ לגובה; דגימה שפונה לאוויר (לא לקרקע, לא לאלמנט אחר, לא לפתח) חייבת להיות על משטח גמר (טיח מכל סוג, איטום, חיפוי, צד שכן, גליף).', '',
     f'**סה"כ לא מכוסה: {sum(r[3] for r in rows):.2f} מ"ר ב-{len(rows)} אלמנטים.**', '',
     '| סוג | אלמנט | קומה | לא מכוסה מ"ר | דוגמה (E, N, z) |', '|---|---|---|---|---|']
for k, i, fl, a, pts in rows: L.append(f'| {k} | {i} | {fl or ""} | {a:.2f} | {pts[0] if pts else ""} |')
open(os.path.join(ROOT, 'docs/verification/finishes-coverage.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L[4:40]))

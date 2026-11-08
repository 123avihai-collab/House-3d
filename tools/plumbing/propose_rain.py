#!/usr/bin/env python3
"""PR1 – rain water, three alternatives for comparison (Avihai 07.11: build all three; the choice follows the soil
consultant and the municipality). Common: the three downpipe shoes (architect background) sit on suspended slabs ->
each pipe drops through the slab, hangs under it (consultant's detail "עטיפת בטון"), crosses ground beams in cast
sleeves, avoids piles, the basement and the pool, and continues buried in the yard. PVC SN-8 ø110, slope 1%.
  1  the consultant's soak pit (as drawn)                     – contradicts soil report 11.6 / 11.7
  2  drainage chamber at the street front + connection to the municipal drainage (location / level: municipality)
  3  new soak pit at the point of the lot farthest from all foundations (still < 3.0 m – soil consultant)
Called from propose.py (needs its Grid class).
"""
import math, os, sys
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union, nearest_points
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_common import J, H0, FG, FR, BAS, beam_poly
import georef as G

r3 = lambda v: round(float(v), 3)


def build(make_grid):
    N = J('data/plumbing/network.json'); C = J('data/plumbing/catalog.json'); R = J('tools/plumbing/cache/raw.json')
    RI = J('tools/plumbing/proposal-inputs.json')['rain']
    by = {n['id']: n for n in N['nodes']}
    lot = Polygon(J('data/site/plot-5187.json')['ring']); POOL = J('data/structure/pool.json'); PI = J('data/structure/piles.json')['piles']
    OD = C['pipes']['PVC SN-8']['sizes'][str(RI['D_mm'])]['OD']; s = RI['slope']
    slabs = [(x['id'], Polygon(x['footprintITM']).buffer(0), H0 + x['topRel'] - x['thickness_m']) for x in FG['slab']]
    under_at = lambda p: min((u for _, P, u in slabs if P.contains(Point(p))), default=None)
    bas = Polygon(BAS['outlineITM']); pool = unary_union([Polygon(POOL['gutter']['ringOuterITM']), Polygon(POOL['channel']['outerITM']), Polygon(POOL['tank']['outerITM'])])
    piles = [Point(p['E'], p['N']).buffer(p['diameter_m'] / 2 + RI['pileClear_m']) for p in PI]
    beams = [(b['id'], beam_poly(b), H0 + b['bottomRel'], H0 + b['topRel']) for b in FR['groundBeams'] if b.get('axisITM')]
    wall_t = C['chambers']['rings']
    chambers = [Point(n['E'], n['N']).buffer(n['D_m'] / 2 + wall_t[str(n['D_m'])]['wall'] + 0.2) for n in N['nodes'] if n['kind'] in ('sewerChamber', 'pumpChamber', 'municipalManhole')]
    fin = lambda p: (G.finish_level(R['spots'], lot, p[0], p[1], near=2.0, far=6.0) or {'H': H0 - 0.05})['H']
    forb = [bas.buffer(0.3), pool.buffer(RI['poolClear_m'])]
    region = lot.buffer(-0.3)
    g0 = make_grid(region, [P for _, P, _, _ in beams], [], forb, piles + chambers, RI['cell_m'])
    slabU = unary_union([P for _, P, _ in slabs])
    X, Y = g0.centers_world()
    m = np.isfinite(g0.base) & (g0.base == 1.0) & shapely.contains_xy(slabU, X, Y); g0.base[m] = RI['underSlabCost']
    shoes = [by[k] for k in ('DPS1@ground', 'DPS2@ground', 'DPS3@ground')]
    sewer = [r for r in N['runs'] if r['system'] in ('sewage', 'pumped') and r['drawnOn'] in ('ground', 'site') and r.get('ILup') is not None]
    water = [r for r in N['runs'] if r['system'] == 'cold' and r['drawnOn'] in ('ground', 'site')]
    found = unary_union([bas] + [Point(p['E'], p['N']).buffer(p['diameter_m'] / 2) for p in PI] + [P for _, P, _, _ in beams] + [pool])

    # ---- destinations
    soak = by['SOAK@site']
    # alt 3: farthest point from the foundations, outside the slabs, clear of utilities
    utl = unary_union([LineString(r['pts']) for r in sewer + water]).buffer(RI['utilClear_m']) if (sewer or water) else Polygon()
    best3 = None
    for x in np.arange(lot.bounds[0], lot.bounds[2], 0.1):
        for y in np.arange(lot.bounds[1], lot.bounds[3], 0.1):
            P = Point(x, y)
            if not lot.buffer(-RI['boundaryClear_m']).contains(P) or slabU.buffer(0.3).contains(P) or utl.contains(P) or any(c.contains(P) for c in chambers): continue
            d = found.distance(P)
            if best3 is None or d > best3[0]: best3 = (d, (x, y))
    # alt 2: front drainage chamber – candidates along the street edge (arc 2420 -> 2457), 0.8 m inside
    PL = J('data/site/plot-5187.json'); pts = PL['points']; ring = PL['ring']
    i0 = next(i for i, p in enumerate(ring) if math.dist(p, (pts['2420']['E'], pts['2420']['N'])) < 0.01)
    i1 = next(i for i, p in enumerate(ring) if math.dist(p, (pts['2457']['E'], pts['2457']['N'])) < 0.01)
    arc = LineString(ring[i0:i1 + 1] if i0 < i1 else ring[i1:i0 + 1])
    cands = []
    for t in np.arange(0.5, arc.length - 0.5, 0.25):
        q = arc.interpolate(t); n_ = nearest_points(lot.buffer(-RI['frontInset_m']).exterior, q)[0]
        P = Point(n_.x, n_.y)
        if slabU.buffer(0.3).contains(P) or any(c.contains(P) for c in chambers) or utl.contains(P) or not region.contains(P): continue
        cands.append(((P.x, P.y), q))
    dests = {1: {'kind': 'soakPit', 'E': soak['E'], 'N': soak['N'], 'TL': soak['TL'], 'D_m': 0.60, 'title': 'בור החלחול של היועץ (במיקום שבתוכנית)'},
             3: {'kind': 'soakPit', 'E': r3(best3[1][0]), 'N': r3(best3[1][1]), 'TL': r3(fin(best3[1])), 'D_m': 0.60, 'title': 'בור חלחול חדש – הנקודה הרחוקה ביותר מהיסודות',
                 'distFoundations_m': r3(best3[0])}}
    best2 = None
    for (c, q) in cands[::4]:
        tot = 0.0
        for sh in shoes:
            p = g0.route((sh['E'], sh['N']), c); g0.used[:] = 0
            if p is None: tot = None; break
            tot += sum(math.dist(p[i], p[i + 1]) for i in range(len(p) - 1))
        if tot is not None and (best2 is None or tot < best2[0]): best2 = (tot, c, q)
    dests[2] = {'kind': 'drainChamber', 'E': r3(best2[1][0]), 'N': r3(best2[1][1]), 'TL': r3(fin(best2[1])), 'D_m': 0.60, 'title': 'שוחת ניקוז בחזית – חיבור לניקוז העירוני',
                'outlet': [[r3(best2[1][0]), r3(best2[1][1])], [r3(best2[2].x), r3(best2[2].y)]]}
    for k, d in dests.items():
        d['distFoundations_m'] = r3(found.distance(Point(d['E'], d['N'])))
        d['distBoundary_m'] = r3(lot.exterior.distance(Point(d['E'], d['N'])))

    alts = []
    for k in (1, 2, 3):
        D = dests[k]; g0.used[:] = 0
        tgt = (D['E'], D['N']); runs, sleeves, crosses = [], [], []
        order = sorted(shoes, key=lambda sh: -math.dist((sh['E'], sh['N']), tgt))
        paths = {}
        for sh in order:
            a = (sh['E'], sh['N'])
            # join an existing line if one passes closer than the destination
            join = None
            for pid, pp in paths.items():
                q = nearest_points(LineString(pp), Point(a))[0]
                if math.dist(a, (q.x, q.y)) < min(RI['joinIfCloser_m'], math.dist(a, tgt)): join = (pid, (q.x, q.y))
            end = join[1] if join else (tgt[0] + (a[0] - tgt[0]) * 0, tgt[1])
            p = g0.route(a, join[1] if join else tgt)
            if p is None: raise SystemExit(f'PR1 alt {k}: no route from {sh["id"]}')
            paths[sh['id']] = p; runs.append({'shoe': sh['id'], 'path': p, 'join': join})
        # levels: walk the tree from the destination; every point must stay under its slab (or under the cover in soil)
        def limit(p):
            u = under_at(p)
            return (u - RI['hangerGap_m'] - OD) if u is not None else (fin(p) - RI['coverMin_m'] - OD)
        def pathlen(p): return [0.0] + list(np.cumsum([math.dist(p[i], p[i + 1]) for i in range(len(p) - 1)]))
        level_end = {}
        # main lines first (no join), then branches
        for rr in [x for x in runs if not x['join']] + [x for x in runs if x['join']]:
            p = rr['path']; L = pathlen(p); tot = L[-1]
            dense = []
            for i in range(len(p) - 1):
                n_ = max(1, int(math.dist(p[i], p[i + 1]) / 0.25))
                for j in range(n_): dense.append(((p[i][0] + (p[i + 1][0] - p[i][0]) * j / n_, p[i][1] + (p[i + 1][1] - p[i][1]) * j / n_), L[i] + math.dist(p[i], p[i + 1]) * j / n_))
            dense.append((p[-1], tot))
            il_up = min(limit(q) + s * dl for q, dl in dense)
            if rr['join']:
                host = next(x for x in runs if x['shoe'] == rr['join'][0])
                il_host = host['ILup'] - s * LineString(host['path']).project(Point(rr['join'][1]))
                il_up = min(il_up, il_host + s * tot)
            rr['ILup'] = r3(il_up); rr['ILdown'] = r3(il_up - s * tot); rr['length'] = tot
            sh = by[rr['shoe']]; zs = fin((sh['E'], sh['N']))
            rr['pts3d'] = [[r3(p[0][0]), r3(p[0][1]), r3(max(zs, il_up + OD))], [r3(p[0][0]), r3(p[0][1]), r3(il_up + OD / 2)]] + \
                          [[r3(q[0]), r3(q[1]), r3(il_up - s * dl + OD / 2)] for q, dl in zip(p[1:], L[1:])]
            # slab drop sleeve, beam sleeves, crossings with sewer / water
            if under_at(p[0]) is not None:
                sleeves.append({'pipe': f'PR1-{k}-{rr["shoe"]}', 'at': [r3(p[0][0]), r3(p[0][1]), r3(under_at(p[0]) + 0.12)], 'through': 'תקרה תלויה (קרקע)', 'axis': 'v',
                                'sleeve': 'שרוול PVC ø160 יצוק / קידוח בתקרה', 'sleeveD_mm': 160, 'material': 'PVC'})
            Ls = LineString(p)
            for bid, P, bot, top in beams:
                x = Ls.intersection(P)
                if x.is_empty or x.length < 0.02: continue
                dl = Ls.project(x.centroid); z = il_up - s * dl + OD / 2
                if z - OD / 2 < top and z + OD / 2 > bot:
                    sleeves.append({'pipe': f'PR1-{k}-{rr["shoe"]}', 'at': [r3(x.centroid.x), r3(x.centroid.y), r3(z)], 'through': f'קורת יסוד {bid}', 'axis': 'h',
                                    'sleeve': 'שרוול PVC ø160 יצוק בקורה (תיאום קונסטרוקטור)', 'sleeveD_mm': 160, 'material': 'PVC'})
            for o in sewer + water:
                Lo = LineString(o['pts']); x = Ls.intersection(Lo)
                if x.is_empty: continue
                for pt in getattr(x, 'geoms', [x]):
                    z = il_up - s * Ls.project(pt)
                    if o['system'] == 'cold':
                        zo = fin((pt.x, pt.y)) - 0.5 - 0.016; clear = (z) - (zo + 0.016) if z > zo else zo - 0.016 - (z + OD)
                    else:
                        t = Lo.project(pt) / max(Lo.length, 1e-6); zo = o['ILup'] + (o['ILdown'] - o['ILup']) * t; Do = (o.get('D_mm') or 110) / 1000
                        clear = z - (zo + Do) if z > zo else zo - (z + OD)
                    crosses.append({'with': o['id'], 'at': [r3(pt.x), r3(pt.y)], 'clear_m': r3(clear), 'above': bool(z > zo)})
        tot_len = sum(x['length'] for x in runs)
        bad = [c for c in crosses if c['clear_m'] < RI['minCrossClear_m']]
        D['IL'] = r3(min(x['ILdown'] for x in runs if not x['join']))
        alts.append({'id': k, 'title': {1: 'חלופה 1 – לבור החלחול של היועץ', 2: 'חלופה 2 – שוחת ניקוז בחזית וחיבור לעירייה', 3: 'חלופה 3 – בור חלחול חדש, רחוק ככל האפשר מהיסודות'}[k],
                     'destination': D, 'length_m': r3(tot_len), 'beamSleeves': sum(1 for x in sleeves if x['through'].startswith('קורת')), 'slabDrops': sum(1 for x in sleeves if x['axis'] == 'v'),
                     'crossings': crosses, 'tightCrossings': bad, 'sleeves': sleeves,
                     'runs': [{'id': f'PR1-{k}-{x["shoe"]}', 'system': 'rain', 'D_mm': RI['D_mm'], 'material': 'PVC SN-8', 'pts3d': x['pts3d'], 'from': x['shoe'],
                               'to': (f'PR1-{k}-{x["join"][0]}' if x['join'] else {1: 'SOAK@site', 2: 'RC-1', 3: 'SOAK-NEW'}[k]), 'ILup': x['ILup'], 'ILdown': x['ILdown'],
                               'slope': s, 'length_m': r3(x['length']), 'status': 'proposal'} for x in runs]})
    # pros / cons (facts from the computation; the decision is Avihai's with the soil consultant and the municipality)
    for a in alts:
        d = a['destination']
        a['facts'] = [f'אורך צנרת {a["length_m"]:.1f} מ\'', f'{a["slabDrops"]} ירידות דרך תקרה, {a["beamSleeves"]} שרוולים בקורות יסוד',
                      f'מרחק היעד מהיסודות {d["distFoundations_m"]:.2f} מ\' (דוח הקרקע 11.6: ≥3.0)', f'מרחק מגבול המגרש {d["distBoundary_m"]:.2f} מ\'',
                      f'חציות של קווים קיימים: {len(a["crossings"])}' + (f', מהן {len(a["tightCrossings"])} במרווח קטן מ-{RI["minCrossClear_m"] * 100:.0f} ס"מ' if a['tightCrossings'] else '')]
        a['approval'] = {1: 'יועץ הקרקע (סטייה מ-11.6, 11.7) + היועץ', 2: 'העירייה (מיקום ורום החיבור, היתר ניקוז) + היועץ', 3: 'יועץ הקרקע (עדיין פחות מ-3.0 מ\') + היועץ'}[a['id']]
    return {'alternatives': alts, 'default': 1, 'common': 'PVC SN-8 ø110, שיפוע 1% (זמני), תלוי מתחת לתקרות לפי פרט "עטיפת בטון" של היועץ, ובקרקע בכיסוי ≥0.30'}

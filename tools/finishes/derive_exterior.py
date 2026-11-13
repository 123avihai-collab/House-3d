#!/usr/bin/env python3
"""Exterior paving ("ריצוף חוץ") – zones, finish planes and the layer build-up.

Inputs (all from data/, re-runnable):
  data/structure/floor-ground.json        exterior concrete slabs (K-21): footprint, top of concrete
  data/site/development-heights.json      finish levels of the permit development plan (spots)
  data/finishes/floors/exterior-buildup.json   layer order / thicknesses (provisional) + fit rules
Output:
  data/finishes/tiling/exterior.json      one zone per slab, in the format of tiling/surfaces.json rooms, plus the
                                          finish plane (z = z0 + gE·(E−E) + gN·(N−N)), the spots used / dropped, checks

Finish plane: least squares over the spots inside the slab (≤ spotMaxDist); the worst spot off by more than outlier_m is
dropped, one at a time (usually a garden level at the edge). 2 spots → slope along the line between them; 1 spot → flat.
"""
import json, math, os
import numpy as np
from shapely.geometry import Polygon, Point

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
r3 = lambda v: round(float(v), 3)

GF = J('data/structure/floor-ground.json')
DH = J('data/site/development-heights.json')
BU = J('data/finishes/floors/exterior-buildup.json')
HT = J('data/finishes/exterior/hatches.json')   # tiled hatches over the pool machine room (tools/finishes/derive_hatches.py)
H0 = J('data/site/origin.json')['H0']
FIT = BU['fit']
STACK = sum(l['thickness_m'] for l in BU['layers'] if l['thickness_m'] is not None)   # everything above the slope fill

spots = [s for s in DH['spots'] if not s.get('reason')]   # 'reason' = excluded (±0.00, wall tops, outside the lot)


def plane(pts):
    """least squares z = z0 + gE·(E−E0) + gN·(N−N0); 2 spots → along the line between them; 1 → flat"""
    E0 = sum(p[0] for p in pts) / len(pts); N0 = sum(p[1] for p in pts) / len(pts)
    if len(pts) >= 3:
        A = np.array([[1, p[0] - E0, p[1] - N0] for p in pts]); b = np.array([p[2] for p in pts])
        if np.linalg.matrix_rank(A, tol=0.3) == 3:
            z0, gE, gN = np.linalg.lstsq(A, b, rcond=None)[0]; return E0, N0, float(z0), float(gE), float(gN)
    if len(pts) >= 2:
        (e1, n1, z1), (e2, n2, z2) = max(((a[:3], b[:3]) for a in pts for b in pts), key=lambda ab: (ab[0][0] - ab[1][0]) ** 2 + (ab[0][1] - ab[1][1]) ** 2)
        L2 = (e2 - e1) ** 2 + (n2 - n1) ** 2; g = (z2 - z1) / L2
        return E0, N0, sum(p[2] for p in pts) / len(pts), g * (e2 - e1), g * (n2 - n1)
    return E0, N0, pts[0][2], 0.0, 0.0


def surface(pts):
    """pts: [(E, N, z, handle, inside)] -> (surface dict, f(E, N), used, dropped)"""
    used, dropped = list(pts), []
    while True:
        E0, N0, z0, gE, gN = plane(used)
        pz = lambda E, N: z0 + gE * (E - E0) + gN * (N - N0)
        out = [(abs(pz(p[0], p[1]) - p[2]), p) for p in used if not p[4]]
        if out and len(used) > 1:
            w = max(out, key=lambda x: x[0])
            if w[0] > FIT['outlier_m']: used.remove(w[1]); dropped.append(w[1]); continue
        break
    res = [(p[0], p[1], p[2] - pz(p[0], p[1])) for p in used]
    k = FIT['idwPower']
    def f(E, N):
        sw = sr = 0.0
        for e, n, r in res:
            d2 = (E - e) ** 2 + (N - n) ** 2
            if d2 < 1e-12: return pz(E, N) + r
            w = d2 ** (-k / 2); sw += w; sr += w * r
        return pz(E, N) + (sr / sw if sw else 0.0)
    S = dict(type='planeIdw', E=r3(E0), N=r3(N0), z=r3(z0), gE=round(gE, 6), gN=round(gN, 6), power=k,
             res=[[r3(e), r3(n), round(r, 4)] for e, n, r in res])
    return S, pz, f, used, dropped


def pool_deck():
    """the paved deck around the pool that is in no K-21 slab: the lot inside the boundary walls, less every ground slab,
    open zone, house wall and the pool openings (pool + overflow gutter, cover channel, balance pit) – the pieces touching the pool"""
    from shapely.ops import unary_union
    lot = Polygon(J('data/site/plot-5187.json')['ring'])
    walls = unary_union([Polygon(w['ringITM']) for w in J('data/structure/perimeter.json')['walls']])
    slabs = unary_union([Polygon(s['footprintITM'], s.get('holesITM') or []) for s in GF['slab']])
    oz = unary_union([Polygon(z['footprintITM']) for z in GF['openZones']])
    hw = unary_union([Polygon(w['footprintITM'], w.get('holesITM') or []) for w in GF['walls']])
    PO = J('data/structure/pool.json'); g, ch, tk = PO['gutter'], PO['channel'], PO['tank']
    # the machine-room roof is paved too (Avihai 13.11 – tiled hatches): only its hatch openings stay out of the deck
    openings = unary_union([Polygon(g['ringOuterITM']), Polygon(ch['outerITM'])] + [Polygon(h['openingITM']) for h in HT['hatches']])
    rest = lot.difference(walls).difference(slabs).difference(oz).difference(hw).difference(openings).buffer(-0.01, join_style=2).buffer(0.01, join_style=2)
    near = unary_union([openings, Polygon(tk['outerITM'])]).buffer(0.05)
    return [p for p in getattr(rest, 'geoms', [rest]) if p.intersects(near) and p.area > 0.5], PO['pool']['deckSlabTop'] - H0


def main():
    zones, checks = [], []
    for sl in GF['slab']:
        if sl['id'] not in BU['slabs']: continue
        P = Polygon(sl['footprintITM'], sl.get('holesITM') or [])
        ZO0 = BU.get('zones', {}).get(sl['id'], {})
        slabParts = []
        if ZO0.get('extendPoolDeck'):   # the pool deck joins this slab's zone – one surface (Avihai 13.11)
            from shapely.ops import unary_union
            deck, deckTop = pool_deck()
            U = unary_union([P] + deck).buffer(0.002, join_style=2).buffer(-0.002, join_style=2)
            if U.geom_type != 'Polygon': raise SystemExit(f"{sl['id']}: the pool deck does not join the slab")
            for dp in deck: slabParts.append(dict(ringITM=[[r3(x), r3(y)] for x, y in list(dp.exterior.coords)[:-1]], slabTop=r3(deckTop), area=r3(dp.area),
                                                 source='data/structure/pool.json pool.deckSlabTop (חתכי הבריכה: "משטח בטון 280.33"); השטח – tools/finishes/derive_exterior.py pool_deck()'))
            P = U
        inc = FIT.get('include', {}).get(sl['id'], {}).get('handles', [])
        near = []
        for sp in spots + [x for x in DH['spots'] if x['handle'] in inc and x.get('reason')]:
            d = P.distance(Point(sp['E'], sp['N']))
            if d <= FIT['spotMaxDist_m'] or sp['handle'] in inc: near.append((sp['E'], sp['N'], sp['z'] - H0, sp['handle'], d == 0 or sp['handle'] in inc))
        if not near: raise SystemExit(f"{sl['id']}: no development height in the zone")
        top = sl['topRel']
        ZO = BU.get('zones', {}).get(sl['id'], {})
        floorZ = top + STACK + BU['minFill_m'] if ZO.get('clampToSlab') else None
        raised = []
        if floorZ is not None:   # K-21 state (OC-16): a permit level below the slab + layers + minimum fill is raised to it
            for k_, p_ in enumerate(near):
                if p_[2] < floorZ: raised.append(dict(handle=p_[3], z=r3(p_[2] + H0), raisedTo=r3(floorZ + H0))); near[k_] = (p_[0], p_[1], floorZ, p_[3], p_[4])
        S, pz, f0, used, dropped = surface(near)
        f = f0 if floorZ is None else (lambda E, N: max(f0(E, N), floorZ))
        if floorZ is not None: S['minZ'] = r3(floorZ)
        # sample the surface on a grid inside the slab: finish range, fill thickness range, mean, volume, steepest fall
        g = FIT['sampleGrid_m']; x0, y0, x1, y1 = P.bounds
        samp = []
        for i in range(int((x1 - x0) / g) + 1):
            for j in range(int((y1 - y0) / g) + 1):
                E, N = x0 + (i + 0.5) * g, y0 + (j + 0.5) * g
                if P.contains(Point(E, N)): samp.append((E, N, f(E, N)))
        for E, N in list(P.exterior.coords)[:-1]: samp.append((E, N, f(E, N)))
        fz = [s_[2] for s_ in samp]
        inner = [s_[2] for s_ in samp[:len(samp) - (len(P.exterior.coords) - 1)]] or fz
        slabAt = lambda E, N: next((sp_['slabTop'] for sp_ in slabParts if Polygon(sp_['ringITM']).buffer(0.005).contains(Point(E, N))), top)
        fill = [v - STACK - slabAt(E, N) for E, N, v in samp]
        inn = samp[:len(samp) - (len(P.exterior.coords) - 1)] or samp
        fmean = sum(v - STACK - slabAt(E, N) for E, N, v in inn) / len(inn)
        slope = math.hypot(S['gE'], S['gN']) * 100
        layers, off = [], -STACK
        for l in BU['layers']:
            t = l['thickness_m']
            if t is None:
                layers.append(dict(id=l['id'], dz0=None, dz1=r3(off), z0=r3(top), z1=r3(top + fmean), thickness_m=r3(fmean), min_m=r3(min(fill)), max_m=r3(max(fill)), status=l['status']))
            else:
                layers.append(dict(id=l['id'], dz0=r3(off), dz1=r3(off + t), z0=r3(top + fmean + off + STACK), z1=r3(top + fmean + off + STACK + t), thickness_m=t, status=l['status']))
                off += t
        bad = min(fill) < BU['minFill_m']
        c = P.centroid
        sp = lambda p: dict(handle=p[3], E=r3(p[0]), N=r3(p[1]), z=r3(p[2] + H0), plane=r3(pz(p[0], p[1]) + H0), d=r3(pz(p[0], p[1]) - p[2]), inside=bool(p[4]))
        fall = (math.degrees(math.atan2(-S['gE'], -S['gN'])) % 360) if slope > 0.05 else None
        z = dict(room='ext:' + sl['id'], floor='ground', outdoor=True, roomName=sl['zoneLabel'], roomType='paving', slab=sl['id'],
                 area=r3(P.area), void_m2=0.0, slabTop=top, finishRel=r3(sum(inner) / len(inner)), finishMin=r3(min(fz)), finishMax=r3(max(fz)),
                 buildUp_m=r3(sum(inner) / len(inner) - top), skirting_m=0, wallTiling=None,
                 parts=[dict(ringITM=[[r3(x), r3(y)] for x, y in list(P.exterior.coords)[:-1]], holesITM=[[[r3(x), r3(y)] for x, y in list(hh.coords)[:-1]] for hh in P.interiors])],
                 slabParts=slabParts, slabArea_m2=r3(sl['area_m2']),
                 surface=S, planeSlope_pct=round(slope, 2), planeFallAzimuth_deg=None if fall is None else round(fall, 1),
                 spots=[sp(p) for p in used], dropped=[sp(p) for p in dropped],
                 layers=layers, fillVolume_m3=r3(P.area * fmean), tileType=None,
                 status='conflict' if bad else 'change' if ZO.get('change') else 'provisional', slabStatus=sl['status'],
                 change=ZO.get('change'), changeReason=ZO.get('reason'), raised=raised,
                 check=dict(minFill_m=BU['minFill_m'], ok=not bad, fillMin_m=r3(min(fill)), fillMax_m=r3(max(fill))),
                 source=f"פני ריצוף: data/site/development-heights.json (sources/permit/permit-sheet1-gramushka.dwg, ישויות {', '.join(p[3] for p in used)}); פני בטון ופוליגון: data/structure/floor-ground.json {sl['id']} ({sl['source'].split(';')[0]}); שכבות: data/finishes/floors/exterior-buildup.json")
        zones.append(z)
        checks.append((sl['id'], z['area'], top, z['finishMin'], z['finishMax'], slope, min(fill), max(fill), len(used), len(dropped)))
    # the hatch lids: own zones in the shared grid (the tiles continue the paving around), on the surface of the zone they sit in
    PR = HT['product']
    for h in HT['hatches']:
        lid = Polygon(h['openingITM']).buffer(-PR['frameTop_m'], join_style=2)
        host = next(z for z in zones if Polygon(z['parts'][0]['ringITM']).buffer(0.05).contains(Polygon(h['openingITM']).centroid))
        tl = next(l for l in host['layers'] if l['id'] == 'extTile')
        zones.append(dict(room='ext:' + h['id'], floor='ground', outdoor=True, hatch=h['id'], roomName=h['label'], roomType='paving', slab=host['slab'],
                          area=r3(lid.area), void_m2=0.0, slabTop=host['slabTop'], finishRel=host['finishRel'], finishMin=host['finishMin'], finishMax=host['finishMax'],
                          buildUp_m=None, skirting_m=0, wallTiling=None, parts=[dict(ringITM=[[r3(x), r3(y)] for x, y in list(lid.exterior.coords)[:-1]], holesITM=[])],
                          surface=host['surface'], planeSlope_pct=host['planeSlope_pct'], planeFallAzimuth_deg=host['planeFallAzimuth_deg'], spots=[], dropped=[],
                          layers=[dict(tl)], fillVolume_m3=0.0, tileType=None, status='provisional', slabStatus='provisional',
                          check=dict(minFill_m=BU['minFill_m'], ok=True, fillMin_m=0.0, fillMax_m=0.0),
                          source=f"מכסה מרוצף {h['id']} – data/finishes/exterior/hatches.json ({h['source']}); פני הריצוף – כמו האזור {host['room']}"))
    # the stairs down to the unit (ST3): tiles on the treads and the risers; the landing at their foot (open until now)
    stairs = []
    STJ = J('data/structure/stairs.json'); FR = J('data/structure/framing.json'); IBU = J('data/finishes/floors/buildup.json')
    for sid, SC in BU.get('stairs', {}).items():
        st = next(x for x in STJ['stairs'] if x['id'] == sid); t = SC['tile_m'] + SC['adhesive_m']
        for f in st['flights']:
            pr = f['profile']; top = pr[:-2]   # the stepped outline (the last two points = the soffit)
            # the concrete inside the finish: treads down, risers back by t; the top riser is the flight's end against the path slab –
            # it stays, its tile goes on the stair side (the finish face 1 tile + adhesive toward the stair)
            conc = [[r3(top[0][0] + t), top[0][1]]] + [[r3(x + t), r3(z - t)] for x, z in top[1:-2]] + [[top[-2][0], r3(top[-2][1] - t)], [top[-1][0], r3(top[-1][1] - t)]] + [list(q) for q in pr[-2:]]
            o, rd, rr, W = f['originITM'], f['runDirITM'], f['rightDirITM'], f['width_m']
            at = lambda s_, w_: [r3(o[0] + rd[0] * s_ + rr[0] * w_), r3(o[1] + rd[1] * s_ + rr[1] * w_)]
            rect = lambda s0, s1: [at(s0, 0), at(s1, 0), at(s1, W), at(s0, W)]
            # risers: vertical segments of the outline; treads: horizontal ones
            rs = [(top[i][0], top[i][1], top[i + 1][1]) for i in range(len(top) - 1) if abs(top[i][0] - top[i + 1][0]) < 1e-6]
            ts = [(top[i][0], top[i + 1][0], top[i][1]) for i in range(len(top) - 1) if abs(top[i][1] - top[i + 1][1]) < 1e-6]
            pieces = []
            for k, (s0, s1, z) in enumerate(ts):
                end = s1 + t if k < len(ts) - 1 else s1 - t   # under the next riser tile; the last – up to the top riser's tile
                pieces.append(dict(kind='tread', ringITM=rect(s0, end), z0=r3(z - t), z1=r3(z), depth_m=r3(end - s0), width_m=W))
            for k, (s0, za, zb) in enumerate(rs):
                last = k == len(rs) - 1
                a0, a1, zt = (s0 - t, s0, zb) if last else (s0, s0 + t, zb - t)
                pieces.append(dict(kind='riser', ringITM=rect(a0, a1), z0=r3(za), z1=r3(zt), height_m=r3(zt - za), width_m=W))
            stairs.append(dict(id=sid, flight=f['id'], floor=st['floor'], tile_m=SC['tile_m'], adhesive_m=SC['adhesive_m'], finishProfile=pr, concreteProfile=conc, pieces=pieces,
                               treads=len(ts), risers=len(rs), treadArea_m2=r3(sum(p_['depth_m'] * W for p_ in pieces if p_['kind'] == 'tread')),
                               riserArea_m2=r3(sum(p_['height_m'] * W for p_ in pieces if p_['kind'] == 'riser')), status='provisional',
                               source=f"data/structure/stairs.json {sid} ({st['source']}); עוביים – data/finishes/floors/exterior-buildup.json (זמני)"))
        L = SC.get('landing')
        if L:
            from shapely.ops import unary_union
            pit = Polygon(next(z_['footprintITM'] for z_ in GF['openZones'] if z_['zone'] == 'basementStairs'))
            fl = unary_union([Polygon([[f['originITM'][0] + f['runDirITM'][0] * s_ + f['rightDirITM'][0] * w_, f['originITM'][1] + f['runDirITM'][1] * s_ + f['rightDirITM'][1] * w_]
                                       for s_, w_ in ((0, 0), (f['profile'][-3][0], 0), (f['profile'][-3][0], f['width_m']), (0, f['width_m']))]) for f in st['flights']])
            land = pit.difference(fl).buffer(-0.002, join_style=2).buffer(0.002, join_style=2)
            land = max(getattr(land, 'geoms', [land]), key=lambda g: g.area)
            bs = next(s_ for s_ in FR['slabs'] if s_.get('id') == 'BS1'); slab = bs['top']
            fin = STJ['levels']['outBottom']['rel']
            fixed = sum(l['thickness_m'] for l in IBU['layers'] if l['thickness_m'] is not None)
            lay, zc = [], slab
            for l in IBU['layers']:
                th = l['thickness_m'] if l['thickness_m'] is not None else fin - slab - fixed
                lay.append(dict(id=l['id'], z0=r3(zc), z1=r3(zc + th), thickness_m=r3(th), status=l['status'])); zc += th
            zones.append(dict(room='ext:' + sid + 'L', floor=L['floor'], outdoor=True, stairLanding=sid, roomName=L['label'], roomType='paving', slab='BS1',
                              area=r3(land.area), void_m2=0.0, slabTop=slab, finishRel=fin, finishMin=fin, finishMax=fin, buildUp_m=r3(fin - slab), skirting_m=0, wallTiling=None,
                              parts=[dict(ringITM=[[r3(x), r3(y)] for x, y in list(land.exterior.coords)[:-1]], holesITM=[])], surface=None, planeSlope_pct=0, planeFallAzimuth_deg=None,
                              spots=[], dropped=[], layers=lay, fillVolume_m3=r3(land.area * lay[0]['thickness_m']), tileType=None, status='provisional', slabStatus=bs.get('status', 'source'),
                              check=dict(minFill_m=BU['minFill_m'], ok=lay[0]['thickness_m'] >= 0, fillMin_m=lay[0]['thickness_m'], fillMax_m=lay[0]['thickness_m']),
                              source=f"{L['_doc']} שכבות – data/finishes/floors/buildup.json"))
    out = dict(_doc='ריצוף חוץ – אזור לכל רצפת בטון חיצונית בקומת הקרקע: פני ריצוף במישור בשיפוע (מגבהי הפיתוח), שכבות: בטון שיפועים (משתנה) → איטום → דבק → אריח. נוצר ע"י tools/finishes/derive_exterior.py – לא לערוך ידנית.',
               source='data/structure/floor-ground.json; data/site/development-heights.json; data/finishes/floors/exterior-buildup.json',
               status='provisional', buildUp=BU, rooms=zones, stairs=stairs)
    json.dump(out, open(os.path.join(ROOT, 'data/finishes/tiling/exterior.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('slab  area   concrete  finish(min..max)  plane%  fill min..max  spots/dropped')
    for c in checks: print(f'{c[0]:5} {c[1]:6.2f} {c[2]:+.3f}  {c[3]:+.3f}..{c[4]:+.3f}  {c[5]:5.2f}  {c[6]:.3f}..{c[7]:.3f}  {c[8]}/{c[9]}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Detailed neighbourhood (illustration) derived from the environment data -> data/environment/details.json

Inputs: data/environment/lots.json, sheet04.json, streets.json, config.json ("details").
Each element carries a status:
  rule         – dimension from a written rule (A_1 גרסה 18 / נספח פרטי פיתוח 009 / תמל/1016 / חתך טיפוסי)
  sheet04      – position/shape from the scanned building plan (sheet 04)
  illustrative – visual detail with no dimension in the sources (window layout, tree/lamp spacing). Shown, never measured.
Run: python3 tools/environment/derive_details.py   (after extract_environment.py and extract_sheet04.py)
"""
import json, math, os
import numpy as np, cv2
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from shapely.geometry import Polygon, LineString, Point, MultiLineString, box
from shapely.ops import unary_union, linemerge, nearest_points
from shapely import affinity

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda *p: json.load(open(os.path.join(ROOT, *p), encoding='utf-8'))
L, S4, ST = J('data', 'environment', 'lots.json'), J('data', 'environment', 'sheet04.json'), J('data', 'environment', 'streets.json')
C = J('data', 'environment', 'config.json')['details']
plot = J('data', 'site', 'plot-5187.json')
r3 = lambda v: round(float(v), 3)
pts = lambda g: [[r3(x), r3(y)] for x, y in g]


def ring(g):
    g = g if g.geom_type == 'Polygon' else max(g.geoms, key=lambda q: q.area)
    c = list(g.exterior.coords)[:-1]
    if not Polygon(c).exterior.is_ccw:
        c = c[::-1]
    return pts(c)


def interp(cp):
    xy = np.array([(c[0], c[1]) for c in cp]); z = np.array([c[2] for c in cp])
    lin = LinearNDInterpolator(xy, z) if len(cp) >= 3 else None
    nn = NearestNDInterpolator(xy, z)
    def f(x, y):
        v = lin(x, y) if lin is not None else np.nan
        return float(nn(x, y)) if np.isnan(v) else float(v)
    return f


lots = {l['parcel']: l for l in L['lots']}
s4 = {r['parcel']: r for r in S4['lots']}
gz = {k: interp([(c['at'][0], c['at'][1], c['z']) for c in l['cornerLevels']]) for k, l in lots.items()}
street_f = interp([(p['E'], p['N'], p['z']) for p in ST['heightControl']['points']] +
                  [(p['E'], p['N'], p['z']) for p in ST['derivedHeightControl']['points']])
lot257 = Polygon(plot['ring'])
src = {
    'fence': 'sources/neighborhood/development-B1/A_1 - גרסה 18.pdf §14 (גדר חזית: 1.80–2.40 מ\' ממפלס המדרכה; בין שכנים: עד 1.60 מ\' מעל המגרש הגבוה; דירוג כל 4 מ\' לפחות); '
             'נספח פרטי פיתוח 009 פרט 5.1 (קיר 25, קופינג 30/4.5, חיפוי אבן עד 65 ס"מ, מעליו טיח)',
    'parking': J('data', 'environment', 'config.json')['parking']['source'],
    'tree': 'A_1 §12.2–12.3: עץ כל 8 מ\' חזית במרווח הקדמי, לפחות 0.5 מ\' מגבול המגרש',
    'lamp': 'גיליון 04 – מקרא: עמוד תאורה 15X15, גובה 6/8/5 מ\', גוף לד (מיקומים: המחשה)',
}


# ---------------------------------------------------------------- houses
def lot_frame(l):
    fr = next(e for e in l['edges'] if e['kind'] == 'front')
    a, b = np.array(fr['pts'][0]), np.array(fr['pts'][-1])
    u = (b - a) / np.linalg.norm(b - a)
    v = np.array([-u[1], u[0]])  # CCW ring: left of the edge direction = inside
    if not Polygon(l['ring']).contains(Point(*(a + (b - a) / 2 + v * 1.0))):
        v = -v
    return a, u, v, fr


def _max_rect(m):
    """Largest all-true axis-aligned rectangle in a boolean grid (histogram method). Returns (r0, c0, r1, c1) inclusive-exclusive."""
    H, W = m.shape; hgt = np.zeros(W, int); best = (0, None)
    for r in range(H):
        hgt = np.where(m[r], hgt + 1, 0)
        st = []
        for c in range(W + 1):
            h = hgt[c] if c < W else 0
            start = c
            while st and st[-1][1] >= h:
                s0, sh = st.pop()
                if sh * (c - s0) > best[0]:
                    best = (sh * (c - s0), (r - sh + 1, s0, r + 1, c))
                start = s0
            st.append((start, h))
    return best[1]


def rectilinear(poly, origin, u, v, cell, smooth, max_rects=3, min_share=0.07, want_upper=False, upper_setback=0):
    """House massing: the footprint in the lot frame approximated by its largest 1–2 axis-aligned rectangles
    (clean orthogonal walls instead of the jagged scan outline)."""
    loc = [((np.array(p) - origin) @ u, (np.array(p) - origin) @ v) for p in poly.exterior.coords]
    xs, ys = [p[0] for p in loc], [p[1] for p in loc]
    x0, y0 = min(xs) - 1, min(ys) - 1
    W, H = int((max(xs) - x0 + 1) / cell) + 1, int((max(ys) - y0 + 1) / cell) + 1
    img = np.zeros((H, W), np.uint8)
    cv2.fillPoly(img, [np.round([((x - x0) / cell, (y - y0) / cell) for x, y in loc]).astype(np.int32)], 1)
    m = img.astype(bool); total = m.sum(); rects = []
    for _ in range(max_rects):
        rr = _max_rect(m)
        if rr is None:
            break
        r0, c0, r1, c1 = rr
        if (r1 - r0) * (c1 - c0) < min_share * total or min(r1 - r0, c1 - c0) * cell < smooth:
            break
        rects.append(rr); m[r0:r1, c0:c1] = False
    if not rects:
        return None
    to_w = lambda x, y: tuple(origin + u * (x * cell + x0) + v * (y * cell + y0))
    rp = [Polygon([to_w(c0, r0), to_w(c1, r0), to_w(c1, r1), to_w(c0, r1)]) for r0, c0, r1, c1 in rects]
    g = unary_union(rp)
    g = g.buffer(0.01, join_style='mitre').buffer(-0.01, join_style='mitre').simplify(0.05)
    if g.area <= 4:
        return None
    if want_upper:
        if len(rp) > 1:
            up = rp[0]
        else:  # single box: upper floor set back from the street side (terrace over the entrance)
            r0, c0, r1, c1 = rects[0]
            sb = int(round(upper_setback / cell))
            up = Polygon([to_w(c0, r0 + sb), to_w(c1, r0 + sb), to_w(c1, r1), to_w(c0, r1)]) if r1 - r0 - sb > 4 / cell else rp[0]
        return g, up
    return g


def facade_items(fp, door_pt, z0, levels):
    """Windows on every wall ≥ minWall; a door on the wall closest to the entrance (illustrative layout)."""
    D = C['house']
    cs = list(fp.exterior.coords)[:-1]
    if not Polygon(cs).exterior.is_ccw:
        cs = cs[::-1]
    walls, door = [], None
    if door_pt is not None:
        ok = [i for i in range(len(cs)) if math.dist(cs[i], cs[(i + 1) % len(cs)]) >= D['minWall_m'] + 1]
        door_wall = min(ok, key=lambda i: LineString([cs[i], cs[(i + 1) % len(cs)]]).distance(Point(door_pt))) if ok else -1
    else:
        door_wall = -1
    for i in range(len(cs)):
        a, b = np.array(cs[i]), np.array(cs[(i + 1) % len(cs)])
        Lw = np.linalg.norm(b - a)
        if Lw < D['minWall_m']:
            continue
        t = (b - a) / Lw
        items = []
        if i == door_wall:
            s = np.clip((np.array(door_pt) - a) @ t, D['doorWidth_m'] / 2 + 0.4, Lw - D['doorWidth_m'] / 2 - 0.4)
            door = {'a': pts([a + t * (s - D['doorWidth_m'] / 2)])[0], 'b': pts([a + t * (s + D['doorWidth_m'] / 2)])[0],
                    'z0': r3(z0), 'z1': r3(z0 + D['doorHeight_m'])}
        for f, (zl, zh) in enumerate(zip(levels[:-1], levels[1:])):
            n = int((Lw - 2 * D['windowEdge_m']) // D['windowPitch_m'])
            if n < 1:
                continue
            wide = (i == door_wall and f == 0)
            for k in range(n):
                s = Lw / 2 + (k - (n - 1) / 2) * D['windowPitch_m']
                w = D['windowWidth_m'] * (1.6 if wide and k % 2 == 1 else 1.0)
                if door and i == door_wall and f == 0 and abs(s - ((np.array(door['a']) + np.array(door['b'])) / 2 - a) @ t) < w / 2 + D['doorWidth_m'] / 2 + 0.3:
                    continue
                sill = zl + (0.0 if wide else D['sill_m'])
                items.append({'a': pts([a + t * (s - w / 2)])[0], 'b': pts([a + t * (s + w / 2)])[0],
                              'z0': r3(sill), 'z1': r3(zl + D['head_m'])})
        walls.append({'a': pts([a])[0], 'b': pts([b])[0], 'windows': items})
    return walls, door


houses, parking, fences, gates, yards, paths, trees = [], [], [], [], [], [], []
fence_done = set()
for k, l in lots.items():
    r = s4.get(k)
    if not r or not r['building'] or l['pm0']['z'] is None:
        continue
    z0 = l['pm0']['z']
    origin, u, v, front = lot_frame(l)
    lp = Polygon(l['ring'])
    bpoly = unary_union([Polygon(b) for b in r['building']])
    env = Polygon(l['envelope']['ring'])
    bi = bpoly.intersection(env)
    bi = max(bi.geoms, key=lambda g: g.area) if bi.geom_type != 'Polygon' else bi
    bi = bi.buffer(-C['house']['cell_m'] * 0.75, join_style='mitre')  # raster rectangles may grow by up to one cell
    if bi.is_empty:
        continue
    bi = max(bi.geoms, key=lambda g: g.area) if bi.geom_type != 'Polygon' else bi
    res = rectilinear(bi, origin, u, v, C['house']['cell_m'], C['house']['smooth_m'], want_upper=True, upper_setback=C['house']['upperSetback_m'])
    if res is None:
        continue
    fp, up = res
    big = lambda g: max(g.geoms, key=lambda q: q.area) if g.geom_type != 'Polygon' else g
    fp = big(fp.intersection(env).simplify(0.02))   # exact building lines (raster edges may stick out by < 0.25 m)
    up = big(up.intersection(fp).simplify(0.02))
    ent = unary_union([Polygon(e) for e in r['entrance']]) if r['entrance'] else None
    door_pt = nearest_points(fp.exterior, ent)[0].coords[0] if ent is not None else None
    H = C['house']
    levels = [z0, z0 + H['floor_m'], z0 + 2 * H['floor_m']]
    walls, door = facade_items(fp, door_pt, z0, levels[0:2])
    walls_up, _ = facade_items(up, None, z0, levels[1:3])
    gmin = min(gz[k](x, y) for x, y in fp.exterior.coords)
    houses.append({'parcel': k, 'lot': l['lot'], 'ring': ring(fp), 'upper': ring(up), 'wallsUpper': walls_up, 'base': r3(min(gmin, z0) - 0.3), 'pm0': z0,
                   'slab': r3(z0 + H['floor_m']), 'top': r3(z0 + l['envelope']['height_m']), 'roof': r3(z0 + 2 * H['floor_m']),
                   'walls': walls, 'door': door, 'area_m2': r3(fp.area),
                   'status': 'sheet04+illustrative',
                   'note': 'מתאר מגיליון 04 (מיושר לניצב), נחתך לקווי הבניין; גובה ±0.00+8.00 (מעקה גג); קומות 3.50; חלונות ודלת – המחשה בלבד'})
    # parking structures (sheet 04 position, 2.70 m) with a garage door on the side facing the street
    pk_all = []
    for pr in r['parking']:
        pg = rectilinear(Polygon(pr), origin, u, v, C['house']['cell_m'], 1.5, max_rects=1) or Polygon(pr)
        pg = pg.intersection(lp)
        pg = max(pg.geoms, key=lambda g: g.area) if pg.geom_type != 'Polygon' else pg
        base = min(gz[k](x, y) for x, y in pg.exterior.coords)
        cs = list(pg.exterior.coords)[:-1]
        st_edges = [e for e in l['edges'] if e['across'].startswith('רחוב')]
        sl = unary_union([LineString(e['pts']) for e in st_edges])
        di = [LineString([cs[i], cs[(i + 1) % len(cs)]]).distance(sl) for i in range(len(cs))]
        i = int(np.argmin(di))
        parking.append({'parcel': k, 'ring': ring(pg), 'base': r3(base), 'top': r3(base + J('data', 'environment', 'config.json')['parking']['height_m']),
                        'door': {'a': pts([cs[i]])[0], 'b': pts([cs[(i + 1) % len(cs)]])[0]}, 'status': 'sheet04', 'source': src['parking']})
        pk_all.append((pg, LineString([cs[i], cs[(i + 1) % len(cs)]])))

    # ------------------------------------------------ fence + gates
    F = C['fence']
    openings = []
    street_edges = [e for e in l['edges'] if e['across'].startswith('רחוב')]
    for pg, door_line in pk_all:  # car opening = the parking door projected on the nearest street edge
        e = min(street_edges, key=lambda e: LineString(e['pts']).distance(door_line))
        el = LineString(e['pts'])
        if el.distance(door_line) > F['carGateMaxDist_m']:
            continue
        s0, s1 = sorted([el.project(Point(p)) for p in door_line.coords])
        openings.append(('car', el, s0 - 0.1, s1 + 0.1))
    if ent is not None:
        e = min(street_edges, key=lambda e: LineString(e['pts']).distance(ent))
        el = LineString(e['pts'])
        if el.distance(ent) < F['pedGateMaxDist_m']:
            c = el.project(ent.centroid)
            openings.append(('ped', el, c - F['pedGateWidth_m'] / 2, c + F['pedGateWidth_m'] / 2))
    for e in l['edges']:
        street = e['across'].startswith('רחוב')
        key = tuple(sorted([k, e['across']]))
        if not street:
            if key in fence_done:
                continue
            fence_done.add(key)
        el = LineString(e['pts'])
        cuts = sorted([(s0, s1, kind) for kind, line, s0, s1 in openings if line.equals(el)])
        pieces, s = [], 0.0
        for s0, s1, kind in cuts:
            if s0 > s:
                pieces.append((s, s0))
            g = LineString([el.interpolate(s0).coords[0], el.interpolate(s1).coords[0]])
            gates.append({'parcel': k, 'kind': kind, 'a': pts([g.coords[0]])[0], 'b': pts([g.coords[-1]])[0],
                          'z': r3(gz[k](*g.interpolate(0.5, normalized=True).coords[0])),
                          'height': F['frontHeight_m'], 'status': 'sheet04' if kind == 'car' else 'sheet04',
                          'source': 'גיליון 04 (מיקום הכניסה/החניה); A_1 §7 (שער בנסיגה – הוצג בקו הגדר)'})
            s = s1
        if s < el.length:
            pieces.append((s, el.length))
        other = e['across'] if e['across'] in gz else None
        for p0, p1 in pieces:
            n = max(1, math.ceil((p1 - p0) / F['stepLength_m']))
            for q in range(n):
                a, b = p0 + (p1 - p0) * q / n, p0 + (p1 - p0) * (q + 1) / n
                seg = LineString([el.interpolate(a).coords[0], el.interpolate(b).coords[0]])
                xy = [seg.interpolate(t, normalized=True).coords[0] for t in (0, 0.5, 1)]
                g_in = [gz[k](*p) for p in xy]
                if street:
                    g_out = [street_f(*p) for p in xy]
                    top = max(g_out) + F['frontHeight_m']
                    top = max(top, max(g_in) + F['minAboveYard_m'])
                    kind = 'front'
                else:
                    g_out = [gz[other](*p) for p in xy] if other else ([gz[k](*p) for p in xy] if e['across'] != '257' else
                                                                       [gz[k](*p) for p in xy])
                    if e['across'] == '257':
                        g_out = [interp([(c['at'][0], c['at'][1], c['z']) for c in L['lot5187Check']['corners']])(*p) for p in xy]
                    top = max(g_in + g_out) + F['neighbourHeight_m']
                    kind = 'neighbour'
                top = math.ceil(top / F['stepRound_m']) * F['stepRound_m']
                fences.append({'parcel': k, 'kind': kind, 'a': pts([seg.coords[0]])[0], 'b': pts([seg.coords[-1]])[0],
                               'base': r3(min(g_in + g_out) - F['footing_m']), 'top': r3(top), 'claddingTo': r3(min(g_in + g_out) + F['claddingHeight_m'])})

    # ------------------------------------------------ yard: paths, driveway, lawn, trees
    Y = C['yard']
    hard = []
    if door and ent is not None:
        gp = next((g for g in gates if g['parcel'] == k and g['kind'] == 'ped'), None)
        start = ((np.array(gp['a']) + np.array(gp['b'])) / 2) if gp else np.array(ent.centroid.coords[0])
        dmid = (np.array(door['a']) + np.array(door['b'])) / 2
        pth = LineString([start, dmid]).buffer(Y['pathWidth_m'] / 2, cap_style='flat').union(ent)
        hard.append(('path', pth))
    for (pg, dl), gt in zip(pk_all, [g for g in gates if g['parcel'] == k and g['kind'] == 'car'] or [None] * len(pk_all)):
        if gt:
            drv = Polygon(list(dl.coords) + [tuple(gt['b']), tuple(gt['a'])]).convex_hull
            hard.append(('driveway', drv))
    inner = lp.buffer(-F['thickness_m'] / 2)
    hard_u = unary_union([h for _, h in hard] + [fp.buffer(Y['houseApron_m'], join_style='mitre')] + [pg for pg, _ in pk_all]) if hard or pk_all else fp.buffer(Y['houseApron_m'], join_style='mitre')
    for kind, h in hard:
        h = h.intersection(inner).difference(fp)
        if not h.is_empty and h.area > 0.5:
            paths.append({'parcel': k, 'kind': kind, 'ring': ring(h), 'status': 'illustrative' if kind == 'path' else 'sheet04'})
    apron = fp.buffer(Y['houseApron_m'], join_style='mitre').difference(fp).intersection(inner)
    if not apron.is_empty:
        paths.append({'parcel': k, 'kind': 'apron', 'ring': ring(apron), 'status': 'illustrative'})
    lawn = inner.difference(hard_u)
    for g in (lawn.geoms if lawn.geom_type == 'MultiPolygon' else [lawn]):
        if g.area > 2:
            yards.append({'parcel': k, 'ring': ring(g), 'holes': [pts(list(h.coords)[:-1]) for h in g.interiors]})
    # trees in the front setback: one per 8 m of frontage, ≥0.5 m from the lot line, clear of paths/driveway
    for e in street_edges:
        el = LineString(e['pts'])
        n = int(el.length // Y['treeEvery_m'])
        for q in range(n):
            s = (q + 0.5) * el.length / n
            p = np.array(el.interpolate(s).coords[0])
            nrm = np.array(Polygon(l['ring']).centroid.coords[0]) - p
            t = np.array(el.interpolate(min(el.length, s + 0.5)).coords[0]) - np.array(el.interpolate(max(0, s - 0.5)).coords[0])
            t = t / (np.linalg.norm(t) or 1); vin = np.array([-t[1], t[0]])
            if vin @ nrm < 0:
                vin = -vin
            c = p + vin * Y['treeInset_m']
            if Point(c).distance(hard_u) < Y['treeClear_m'] or not inner.contains(Point(c)):
                continue
            trees.append({'at': pts([c])[0], 'z': r3(gz[k](*c)), 'height': Y['treeHeight_m'], 'crown': Y['treeCrown_m'], 'kind': 'yard',
                          'status': 'rule', 'source': src['tree']})

# ---------------------------------------------------------------- streets: curbs, parking bays, trees, lamps
SC = C['street']
surf = ST['surfaces']
zone_u = {z: unary_union([Polygon(s['ring']).buffer(0) for s in surf if s['zone'] == z]) for z in {s['zone'] for s in surf}}
road = unary_union([zone_u.get('carriageway', Polygon()), zone_u.get('parkingStrip', Polygon())])
curbs = []
if 'sidewalk' in zone_u and not road.is_empty:
    cl = zone_u['sidewalk'].boundary.intersection(road.buffer(0.05))
    cl = linemerge(cl) if cl.geom_type == 'MultiLineString' else cl
    for g in (cl.geoms if hasattr(cl, 'geoms') else [cl]):
        if g.geom_type == 'LineString' and g.length > 1:
            curbs.append({'pts': pts(g.coords), 'height': SC['curbHeight_m'], 'width': SC['curbWidth_m']})
bays, lamps = [], []
# parking strip (910 / 870): bays of 6 m with a 2 m planting island + tree after every second bay (illustrative rhythm)
for s in surf:
    if s['zone'] != 'parkingStrip':
        continue
    g = Polygon(s['ring']).buffer(0)
    mrr = g.minimum_rotated_rectangle
    c = list(mrr.exterior.coords)[:4]
    e1, e2 = LineString([c[0], c[1]]), LineString([c[1], c[2]])
    axis, wid = (e1, e2) if e1.length > e2.length else (e2, e1)
    if axis.length < 5:
        continue
    a, b = np.array(axis.coords[0]), np.array(axis.coords[1]); t = (b - a) / np.linalg.norm(b - a)
    off = np.array(wid.coords[1]) - np.array(wid.coords[0])
    if axis.coords[1] != wid.coords[0]:
        off = np.array(wid.coords[1]) - np.array(wid.coords[0])
    pos, k_ = 0.0, 0
    while pos + 2 < axis.length:
        if k_ % 3 == 2:
            cpt = a + t * (pos + 1.0) + off / 2
            if g.buffer(0.2).contains(Point(*cpt)):
                trees.append({'at': pts([cpt])[0], 'z': r3(street_f(*cpt)), 'height': SC['treeHeight_m'], 'crown': SC['treeCrown_m'], 'kind': 'street', 'status': 'illustrative'})
                isl = Polygon([a + t * pos, a + t * (pos + 2.0), a + t * (pos + 2.0) + off, a + t * pos + off]).intersection(g)
                if not isl.is_empty and isl.area > 0.5:
                    bays.append({'kind': 'island', 'ring': ring(isl)})
            pos += 2.0
        else:
            ln = LineString([a + t * pos, a + t * pos + off]).intersection(g.buffer(0.05))
            if not ln.is_empty and ln.geom_type == 'LineString':
                bays.append({'kind': 'line', 'pts': pts(ln.coords)})
            pos += SC['bayLength_m']
        k_ += 1
# integrated street: planting islands + trees in the 5.0 m band (south side, as at 5187 in the buyer's map),
# alternating with parking; outside the buyer-map frame only (inside it the drawn islands exist)
frame = Polygon(ST['frameITM'])
sec = ST['integratedStreet']['typicalSection']
south_lots = ['222', '223', '218', '217', '262']
south = unary_union([Polygon(lots[q]['ring']) for q in south_lots if q in lots] +
                    [Polygon(p['ring']) for p in J('data', 'site', 'parcels.json')['parcels'] if p['parcel'] in ('216', '219', '220', '221', '263', '264')])
integ = zone_u.get('integrated', Polygon())
band0, band1 = sec['zones'][-1]['width_m'], sec['zones'][-1]['width_m'] + sec['zones'][-2]['width_m']
band = integ.intersection(south.buffer(band1).difference(south.buffer(band0)))
band_out = band.difference(frame.buffer(1))
for g in (band_out.geoms if band_out.geom_type == 'MultiPolygon' else [band_out]):
    if g.is_empty or g.area < 10:
        continue
    sk = g.buffer(-0.1)
    line = LineString(list(g.minimum_rotated_rectangle.exterior.coords)[:2])
    if line.length < 5:
        line = LineString(list(g.minimum_rotated_rectangle.exterior.coords)[1:3])
    n = int(line.length // SC['islandEvery_m'])
    for q in range(n):
        c = line.interpolate((q + 0.5) / n, normalized=True)
        cpt = nearest_points(g.centroid if False else g, c)[0] if not g.contains(c) else c
        p = Point(cpt.x, cpt.y)
        # project to the middle of the band
        isl = p.buffer(SC['islandRadius_m']).intersection(g)
        if isl.area < 1:
            continue
        bays.append({'kind': 'island', 'ring': ring(isl)})
        cc = isl.centroid
        trees.append({'at': pts([cc.coords[0]])[0], 'z': r3(street_f(cc.x, cc.y)), 'height': SC['treeHeight_m'], 'crown': SC['treeCrown_m'], 'kind': 'street', 'status': 'illustrative'})
# MIG islands near 5187 get a tree too
for isl in ST['integratedStreet']['islands']:
    lsx = LineString(isl['points'])
    if lsx.length > 4:
        c = Polygon(isl['points']).centroid if len(isl['points']) > 3 else lsx.centroid
        trees.append({'at': pts([c.coords[0]])[0], 'z': r3(street_f(c.x, c.y)), 'height': SC['treeHeight_m'], 'crown': SC['treeCrown_m'], 'kind': 'street', 'status': 'illustrative'})
# street lamps: along each lot frontage, every lampEvery_m, at lampInset_m from the lot line (illustrative)
done = []
for l in L['lots']:
    for e in l['edges']:
        if not e['across'].startswith('רחוב'):
            continue
        el = LineString(e['pts'])
        n = max(1, round(el.length / SC['lampEvery_m']))
        for q in range(n):
            s = (q + 0.5) * el.length / n
            p = np.array(el.interpolate(s).coords[0])
            t = np.array(el.interpolate(min(el.length, s + 0.5)).coords[0]) - np.array(el.interpolate(max(0, s - 0.5)).coords[0])
            t = t / (np.linalg.norm(t) or 1); vo = np.array([t[1], -t[0]])
            if Polygon(l['ring']).contains(Point(*(p + vo * 0.5))):
                vo = -vo
            c = p + vo * SC['lampInset_m']
            if any(math.dist(c, d) < SC['lampMinGap_m'] for d in done) or lot257.distance(Point(*c)) < 0.5:
                continue
            done.append(c)
            lamps.append({'at': pts([c])[0], 'z': r3(street_f(*c)), 'height': SC['lampHeight_m'], 'arm': pts([vo])[0], 'status': 'illustrative', 'source': src['lamp']})

out = {'_doc': 'Detailed neighbourhood for display. Generated by tools/environment/derive_details.py – do not edit. '
               'status: rule / sheet04 / illustrative (illustrative = no dimension in the sources, shown only).',
       'sources': src, 'houses': houses, 'parking': parking, 'fences': fences, 'gates': gates, 'yards': yards, 'paths': paths,
       'trees': trees, 'lamps': lamps, 'curbs': curbs, 'bays': bays, 'config': C}
json.dump(out, open(os.path.join(ROOT, 'data', 'environment', 'details.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print({k: len(v) for k, v in out.items() if isinstance(v, list)})

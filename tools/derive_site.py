#!/usr/bin/env python3
"""
Stage-1 derivation (pure geometry on extracted data, no new measurements):
  data/site/*.json + data/config/neighbors-rules.json  ->  data/site/terrain-regions.json, data/site/neighbors.json

* terrain regions: lot 5187, neighbouring lots, sidewalk (street area north of the curb/gutter line),
  road (street area south of it). Street areas are clipped to the buyer's-map frame (the extent with height data).
* neighbour envelopes: lot polygon inset by front/side/rear setbacks (TAMAL/1016 §4.1.2), edges classified by
  the parcel across each edge. The same routine is run on lot 5187 and compared with the envelope drawn in the
  buyer's map (layer 0-BOUNDARY-BUILDING) as a self-check.
Run: python3 tools/derive_site.py
"""
import json, math, os
from shapely.geometry import Polygon, LineString, Point, MultiPolygon, box
from shapely.ops import split, unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = lambda n: os.path.join(ROOT, 'data', 'site', n)
r3 = lambda v: round(float(v), 3)


def load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def ring_of(geom):
    if isinstance(geom, MultiPolygon):
        geom = max(geom.geoms, key=lambda g: g.area)
    g = geom.buffer(0)
    pts = list(g.exterior.coords)[:-1]
    return [[r3(x), r3(y)] for x, y in pts]


def inset_polygon(poly, edge_dists):
    """Intersect inner half-planes: edge i shifted inwards by edge_dists[i]."""
    pts = list(poly.exterior.coords)[:-1]
    if Polygon(pts).exterior.is_ccw is False:
        pts = pts[::-1]
        edge_dists = edge_dists[::-1]
        # after reversing points, edge i now runs between pts[i] and pts[i+1]; re-align
        edge_dists = edge_dists[1:] + edge_dists[:1]
    big = 1000.0
    result = poly
    n = len(pts)
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux  # inward normal for CCW ring
        d = edge_dists[i]
        ax, ay = x1 + nx * d - ux * big, y1 + ny * d - uy * big
        bx, by = x1 + nx * d + ux * big, y1 + ny * d + uy * big
        half = Polygon([(ax, ay), (bx, by), (bx + nx * big, by + ny * big), (ax + nx * big, ay + ny * big)])
        result = result.intersection(half)
        if result.is_empty:
            break
    return result


def classify_edges(pid, poly, parcels, rules):
    """front = edge across a public parcel; the longest front group defines the primary street;
    rear = edges facing away from the primary front (dot < -0.5); all others side."""
    pts = list(poly.exterior.coords)[:-1]
    ccw = Polygon(pts).exterior.is_ccw
    others = [(p['parcel'], p['use'], Polygon(p['ring'])) for p in parcels if p['parcel'] != pid]
    kinds = []
    n = len(pts)
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1
        ox, oy = (dy / L, -dx / L) if ccw else (-dy / L, dx / L)  # outward normal
        probe = Point((x1 + x2) / 2 + ox * 0.6, (y1 + y2) / 2 + oy * 0.6)
        across = next(((q, u) for q, u, g in others if g.contains(probe)), (None, 'unknown'))
        kinds.append({'across': across[0], 'acrossUse': across[1], 'normal': (ox, oy), 'len': L,
                      'seg': ((x1, y1), (x2, y2))})
    groups = {}
    for k in kinds:
        if k['acrossUse'] == 'public':
            g = groups.setdefault(k['across'], [0.0, 0.0, 0.0])
            g[0] += k['normal'][0] * k['len']; g[1] += k['normal'][1] * k['len']; g[2] += k['len']
    fx = fy = None
    if groups:
        gx, gy, _ = max(groups.values(), key=lambda g: g[2])
        fl = math.hypot(gx, gy) or 1; fx, fy = gx / fl, gy / fl
    for k in kinds:
        if k['acrossUse'] == 'public':
            k['kind'] = 'front'
        elif fx is not None and (k['normal'][0] * fx + k['normal'][1] * fy) < -0.5:
            k['kind'] = 'rear'
        else:
            k['kind'] = 'side'
        k['dist'] = rules['setbacks_m'][k['kind']]
    return kinds, ccw


def setback_envelope(poly, kinds):
    """Envelope = lot minus every point closer than the edge's setback to that edge segment."""
    strips = [LineString(k['seg']).buffer(k['dist'], quad_segs=16) for k in kinds]
    return poly.difference(unary_union(strips))


def main():
    origin = load(S('origin.json'))
    parcels = load(S('parcels.json'))['parcels']
    heights = load(S('planned-heights.json'))
    street = load(S('street.json'))
    bl = load(S('building-lines.json'))
    rules = load(os.path.join(ROOT, 'data', 'config', 'neighbors-rules.json'))
    P = {p['parcel']: p for p in parcels}
    frame = Polygon(origin['mapFrameITM'])

    # ---------- terrain regions ----------
    regions = []
    def lot_region(pid, material, role):
        ctrl = [h for h in heights['lotCorners'] if h['parcel'] == pid]
        regions.append({'id': f'lot-{pid}', 'role': role, 'parcel': pid, 'material': material,
                        'ring': P[pid]['ring'], 'control': {'lotCorners': [i for i, h in enumerate(heights['lotCorners']) if h['parcel'] == pid]},
                        'controlCount': len(ctrl), 'layer': 'topoPlanned' if role == 'plot' else 'neighborLots',
                        'note': None if len(ctrl) >= 3 else 'פחות מ-3 גבהים מתוכננים במקור – משטח מפושט (ראו docs/open-issues.md)',
                        'source': 'parcel ring: data/site/parcels.json; heights: data/site/planned-heights.json lotCorners'})
    lot_region('257', 'soilPlot', 'plot')
    # lot 5187: the development spot heights of the permit ground plan (tools/extract_dev_heights.py) – Avihai 09.11.2026
    dev = load(S('development-heights.json'))
    regions[-1].update({'control': {'developmentSpots': True}, 'controlCount': len(dev['spots']),
                        'source': 'parcel ring: data/site/parcels.json; heights: data/site/development-heights.json spots (' + dev['source'] + ', תצוגה "' + dev['view'] + '")'})
    for pid in rules['lots']:
        lot_region(pid, 'soilLot', 'neighbor')

    street_area = unary_union([Polygon(P[p]['ring']) for p in P if P[p]['use'] == 'public']).intersection(frame)
    # curb line = the HW-CURB-GUTR polyline closest to the lots (longest one); extend to cross the street area
    gutr = [c for c in street['curbs'] if c['layer'] == 'HW-CURB-GUTR']
    lot_front = Polygon(P['257']['ring'])
    curb = min(gutr, key=lambda c: LineString(c['points']).distance(lot_front))
    cl = LineString(curb['points'])
    (x1, y1), (x2, y2) = cl.coords[0], cl.coords[-1]
    ext = 30.0
    ux, uy = (x2 - x1) / cl.length, (y2 - y1) / cl.length
    cut = LineString([(x1 - ux * ext, y1 - uy * ext)] + list(cl.coords) + [(x2 + ux * ext, y2 + uy * ext)])
    parts = split(street_area, cut)
    side, road = [], []
    for g in parts.geoms:
        (side if g.distance(lot_front) < 0.5 else road).append(g)
    street_ctrl = {'contours': 'all', 'streetSpots': 'all'}
    for i, g in enumerate(side):
        regions.append({'id': f'sidewalk-{i}', 'role': 'sidewalk', 'material': 'pavers', 'ring': ring_of(g),
                        'control': street_ctrl, 'layer': 'street',
                        'source': 'street parcels (9, 20/28) ∩ buyer-map frame, split by curb line HW-CURB-GUTR; heights: planned contours + Road Elevations'})
    for i, g in enumerate(road):
        regions.append({'id': f'road-{i}', 'role': 'road', 'material': 'asphalt', 'ring': ring_of(g),
                        'control': street_ctrl, 'layer': 'street',
                        'source': 'street parcels (9, 20/28) ∩ buyer-map frame, south of curb line; heights: planned contours'})

    # ---------- envelopes ----------
    def envelope(pid):
        poly = Polygon(P[pid]['ring'])
        kinds, ccw = classify_edges(pid, poly, parcels, rules)
        env = setback_envelope(poly, kinds)
        summary = {}
        for k in kinds:
            summary.setdefault(k['kind'], []).append(k['across'])
        return env, summary

    # self-check against the envelope drawn for lot 5187 (0-BOUNDARY-BUILDING, open polyline of 4 sides)
    env257, sum257 = envelope('257')
    drawn = LineString(bl['lot5187Envelope'][0]['points'])
    dev = max(Point(c).distance(env257.exterior) for c in drawn.coords)
    selfcheck = {'lot': '5187', 'maxDeviationFromDrawnEnvelope_m': r3(dev), 'edgeKinds': {k: sorted(set(map(str, v))) for k, v in sum257.items()},
                 'drawnSource': 'sources/survey/INDEX_F02628-36-MIG-5187.dwg layer 0-BOUNDARY-BUILDING'}
    print('self-check envelope 5187: max deviation', dev)

    lots = []
    for pid in rules['lots']:
        env, summ = envelope(pid)
        el = rules['entranceLevel'].get('byParcel', {}).get(pid)
        if el:
            base, base_status = el['pm0'], rules['entranceLevel']['status']
        else:
            ctrl = [h['z'] for h in heights['lotCorners'] if h['parcel'] == pid]
            base, base_status = (sum(ctrl) / len(ctrl) if ctrl else None), 'provisional'
        lots.append({'parcel': pid, 'footprint': ring_of(env), 'footprintArea_m2': r3(env.area),
                     'edgeKinds': {k: sorted(set(map(str, v))) for k, v in summ.items()},
                     'entranceLevel': r3(base) if base is not None else None,
                     'entranceLevelStatus': base_status, 'lot': (el or {}).get('lot'),
                     'height_m': rules['maxHeightAboveEntrance_m']['value'],
                     'heightStatus': rules['maxHeightAboveEntrance_m']['status'],
                     'floors': rules['floorsAboveEntrance']})
    out = {'rules': rules, 'selfCheck': selfcheck, 'lots': lots,
           'plot5187EnvelopeComputed': ring_of(env257)}
    with open(S('neighbors.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(S('terrain-regions.json'), 'w', encoding='utf-8') as f:
        json.dump({'regions': regions, 'curbLine': curb['points'],
                   'note': 'אזורי משטח. הגיאומטריה נוצרת בדפדפן (js/geometry/terrain.js) מהטבעות ומנקודות הבקרה.'}, f, ensure_ascii=False, indent=1)
    print('regions', [r['id'] for r in regions])


if __name__ == '__main__':
    main()

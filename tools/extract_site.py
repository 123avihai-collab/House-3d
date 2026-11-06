#!/usr/bin/env python3
"""
Stage-1 extraction: survey / buyer's map / permit DWG  ->  data/site/*.json

Inputs  (converted by tools/dwg2json/convert.mjs into tools/cache/):
  tools/cache/mig-5187.json       <- sources/survey/INDEX_F02628-36-MIG-5187.dwg   (buyer's map, native ITM)
  tools/cache/permit-sheet1.json  <- sources/permit/permit-sheet1-gramushka.dwg     (permit sheet, local cm)
Manual reading table:
  tools/contour-levels.json      (Z of planned contour polylines, see _doc there)
  tools/survey-2025-points.json  (spot heights transcribed from the scanned survey, see _doc there)

Run:  python3 tools/extract_site.py
Every output record carries a "source" field.
"""
import json, math, os, sys
from collections import defaultdict

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from pyproj import CRS, Transformer, Proj

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, 'tools', 'cache')
OUT = os.path.join(ROOT, 'data', 'site')
SRC_MIG = 'sources/survey/INDEX_F02628-36-MIG-5187.dwg'
SRC_PERMIT = 'sources/permit/permit-sheet1-gramushka.dwg'
SRC_SURVEY_SCAN = 'sources/survey/survey-5187-tzachi-abitan.pdf'
CONTEXT = (179530.0, 576170.0, 179680.0, 576310.0)  # E0,N0,E1,N1 of the context window (display extent, not a dimension)
ARC_CHORD_TOL = 0.001  # m, max sagitta when discretising arcs (mm precision)

r3 = lambda v: round(float(v), 3)


def load(name):
    with open(os.path.join(CACHE, name), encoding='utf-8') as f:
        return json.load(f)


def attribs(e):
    return {a['tag']: a['text']['text'] for a in (e.get('attribs') or [])}


def arc_points(p, q, bulge):
    """Points from p to q along a DXF bulge arc (p and q included)."""
    if abs(bulge) < 1e-12:
        return [p, q]
    th = 4 * math.atan(bulge)
    dx, dy = q[0] - p[0], q[1] - p[1]
    c = math.hypot(dx, dy)
    R = c / (2 * math.sin(th / 2))
    mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
    h = R * math.cos(th / 2)
    nx, ny = -dy / c, dx / c
    cx, cy = mx + nx * h, my + ny * h
    r = abs(R)
    a0 = math.atan2(p[1] - cy, p[0] - cx)
    # segments so that sagitta <= tol
    seg_angle = 2 * math.acos(max(-1.0, min(1.0, 1 - ARC_CHORD_TOL / r))) if r > ARC_CHORD_TOL else abs(th)
    n = max(1, int(math.ceil(abs(th) / max(seg_angle, 1e-6))))
    pts = [(cx + r * math.cos(a0 + th * i / n), cy + r * math.sin(a0 + th * i / n)) for i in range(n + 1)]
    pts[0], pts[-1] = p, q
    return pts


def lw_points(e, tf=lambda x, y: (x, y)):
    v = e['vertices']
    closed = bool(e.get('flag', 0) & 1)
    n = len(v)
    out = []
    for i in range(n - 1 + (1 if closed else 0)):
        a, b = v[i], v[(i + 1) % n]
        pa, pb = tf(a['x'], a['y']), tf(b['x'], b['y'])
        seg = arc_points(pa, pb, a.get('bulge', 0) or 0)
        out += seg if not out else seg[1:]
    if n == 1:
        out = [tf(v[0]['x'], v[0]['y'])]
    return out


def arc_entity_points(e, tf=lambda x, y: (x, y)):
    c, R = e['center'], e['radius']
    a0, a1 = e['startAngle'], e['endAngle']
    if a1 < a0:
        a1 += 2 * math.pi
    p = (c['x'] + R * math.cos(a0), c['y'] + R * math.sin(a0))
    q = (c['x'] + R * math.cos(a1), c['y'] + R * math.sin(a1))
    bulge = math.tan((a1 - a0) / 4)
    return [tf(*pt) for pt in arc_points(p, q, bulge)]


def ring_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return a / 2


def main():
    mig = load('mig-5187.json')
    E = mig['entities']
    in_itm = lambda x: x > 170000  # main map is native ITM; inset/sheet furniture are local

    # ---------------- control points (C1610 = boundary points) ----------------
    pts = {}
    for e in E:
        if e['type'] == 'INSERT' and e['name'] == 'C1610' and in_itm(e['insertionPoint']['x']):
            a = attribs(e)
            pts[a['POINT_NAME']] = (e['insertionPoint']['x'], e['insertionPoint']['y'])

    # ---------------- inset (1:5000) georeference: exact scaled copy ----------------
    inset_verts = []
    for e in E:
        if e['layer'] == '1602' and e['type'] == 'LWPOLYLINE' and 99000 < e['vertices'][0]['x'] < 101000:
            inset_verts += [(v['x'], v['y']) for v in e['vertices']]
    # coarse transform from the inset grid ticks (179500 @ x=100110.419, 576250 @ y=99684.979, 1:5)
    coarse = lambda x, y: (179500 + (x - 100110.419) * 5, 576250 + (y - 99684.979) * 5)
    A, B = [], []
    for name, p in pts.items():
        q = min(inset_verts, key=lambda q: math.dist(coarse(*q), p))
        A.append(q); B.append(p)
    A, B = np.array(A), np.array(B)
    ma, mb = A.mean(0), B.mean(0)
    za = (A - ma) @ np.array([1, 1j]); zb = (B - mb) @ np.array([1, 1j])
    s = (np.conj(za) @ zb) / (np.conj(za) @ za)
    inset_res = float(np.abs(zb - s * za).max())
    def inset_tf(x, y):
        z = complex(mb[0], mb[1]) + s * (complex(x, y) - complex(ma[0], ma[1]))
        return (z.real, z.imag)
    georef = {
        'inset': {'scale': float(abs(s)), 'rotationDeg': float(math.degrees(np.angle(s))),
                  'maxResidual_m': inset_res, 'pointsUsed': sorted(pts)},
    }

    # ---------------- parcels from inset layer 1602 ----------------
    lines = []
    for e in E:
        if e['layer'] != '1602':
            continue
        if e['type'] == 'LWPOLYLINE' and 99000 < e['vertices'][0]['x'] < 101000:
            p = lw_points(e, inset_tf)
            if len(p) >= 2:
                lines.append(LineString(p))
    win = box(*CONTEXT)
    merged = unary_union(lines)
    polys = [pg for pg in polygonize(merged) if pg.area > 20 and pg.intersects(win)]
    labels = []
    for e in E:
        if e['type'] == 'INSERT' and e['layer'] == '1603':
            a = attribs(e)
            ip = e['insertionPoint']
            if 99000 < ip['x'] < 101000:
                labels.append((a.get('PARCEL_NUM'), Point(*inset_tf(ip['x'], ip['y']))))
    legal = {}
    for e in E:
        if e['type'] == 'INSERT' and e['layer'] == 'C1603_0':
            a = attribs(e)
            legal[a['PARCEL_NAME']] = {'legalArea_dunam': float(a['LEGAL_AREA']), 'source': a.get('PARCEL_SOURCE')}
    parcels = []
    used = set()
    for pg in polys:
        used.update(n for n, p in labels if pg.contains(p))
    for pg in polys:
        inside = sorted({n for n, p in labels if pg.contains(p)}, key=lambda n: int(n) if n.isdigit() else 0)
        pid = '/'.join(inside) if inside else None
        merged_parcels = len(inside) > 1
        labelRule = 'label inside polygon' if len(inside) == 1 else (
            'several labels inside one polygon: dividing line missing in source' if inside else '')
        if pid is None:
            # label falls outside its (clipped / irregular) polygon: nearest unused label within 15 m
            cands = sorted(((pg.distance(p), n) for n, p in labels if n not in used), key=lambda t: t[0])
            if cands and cands[0][0] < 15:
                pid = cands[0][1]; used.add(pid); labelRule = f'nearest label ({cands[0][0]:.1f} m outside polygon)'
        ring = [(r3(x), r3(y)) for x, y in list(pg.exterior.coords)[:-1]]
        if ring_area(ring) < 0:
            ring = ring[::-1]
        nums = [int(n) for n in (pid or '').split('/') if n.isdigit()]
        if nums and all(100 <= n < 1000 for n in nums):
            use = 'residential'
        elif nums and all(n < 100 for n in nums):
            use = 'public'
        else:
            use = 'unknown'
        rec = {'parcel': pid, 'labelRule': labelRule, 'merged': merged_parcels, 'use': use, 'gush': '38762',
               'area_m2': r3(pg.area), 'ring': ring,
               'clippedByContext': not win.contains(pg),
               'source': f'{SRC_MIG} layer 1602 (inset 1:5000, exact scaled copy, residual {inset_res:.1e} m); label layer 1603'}
        if pid in legal:
            rec['legalArea_dunam'] = legal[pid]['legalArea_dunam']
        parcels.append(rec)
    parcels.sort(key=lambda r: (r['parcel'] is None, int(r['parcel'].split('/')[0]) if r['parcel'] else 0))

    # ---------------- lot 5187 (parcel 257) ----------------
    lot = next(p for p in parcels if p['parcel'] == '257')
    cell = next((attribs(e) for e in E if e['type'] == 'INSERT' and e['name'] == 'cellno'), {})
    lot_poly = Polygon(lot['ring'])
    # boundary definition: the 5 survey points + arc 2420->2457 (R=502.50, from layer C1609 RADIUS attr)
    seg_attr = []
    for e in E:
        if e['type'] == 'INSERT' and e['name'] == 'C1609' and in_itm(e['insertionPoint']['x']):
            a = attribs(e)
            seg_attr.append({'at': [r3(e['insertionPoint']['x']), r3(e['insertionPoint']['y'])],
                             'length': a.get('CALC_LENGTH'), 'radius': a.get('RADIUS') or None})
    plot = {
        'lot': '5187', 'parcel': '257', 'gush': '38762', 'use': "מגורים א'",
        'points': {k: {'E': r3(v[0]), 'N': r3(v[1])} for k, v in pts.items() if k in ('2403', '2420', '2424', '2447', '2457')},
        'order': ['2403', '2420', '2457', '2447', '2424'],
        'edges': [
            {'from': '2403', 'to': '2420', 'type': 'line'},
            {'from': '2420', 'to': '2457', 'type': 'arc', 'radius': 502.5, 'bulgesTowards': 'street (south-west)'},
            {'from': '2457', 'to': '2447', 'type': 'line'},
            {'from': '2447', 'to': '2424', 'type': 'line'},
            {'from': '2424', 'to': '2403', 'type': 'line'},
        ],
        'ring': lot['ring'],
        'area_m2_computed': lot['area_m2'],
        'area_m2_registered': 498.0,
        'area_m2_cellno_attr': float(cell.get('AREA', 'nan')),
        'segmentLabels': seg_attr,
        'source': f'{SRC_MIG}: points layer C1610, parcel ring layer 1602, segment labels C1609, cellno AREA; '
                  f'registered area 0.498 dunam from {SRC_SURVEY_SCAN} and sources/survey/INDEX_F02628-25-SHIVUK-MIG-5187.pdf',
    }

    # ---------------- planned heights ----------------
    texts = []
    for e in E:
        if e['type'] == 'TEXT' and in_itm(e['startPoint']['x']):
            # text box centre: left/baseline anchored (halign 0) -> centre = start + R(rot)*(w/2, h/2);
            # centred texts (halign 1) -> midpoint of start/end alignment points
            h, rot = e.get('textHeight', 0.5), e.get('rotation', 0)
            if e.get('halign', 0) == 0:
                w = len(e['text']) * 0.9 * h * 0.5  # approximate glyph advance (only used to locate the label centre)
                cx = e['startPoint']['x'] + math.cos(rot) * w / 2 - math.sin(rot) * h / 2
                cy = e['startPoint']['y'] + math.sin(rot) * w / 2 + math.cos(rot) * h / 2
            else:
                ep = e.get('endPoint') or e['startPoint']
                cx, cy = (e['startPoint']['x'] + ep['x']) / 2, (e['startPoint']['y'] + ep['y']) / 2
            texts.append((e['layer'], cx, cy, e['text'], e['handle']))
    parcel_polys = [(p['parcel'], Polygon(p['ring'])) for p in parcels]
    def parcel_at(x, y):
        pt = Point(x, y)
        for pid, pg in parcel_polys:
            if pg.contains(pt):
                return pid
        return None
    lot_heights = []
    for layer, x, y, t, h in texts:
        if layer == 'L-00-ktse migrash':
            pid = parcel_at(x, y)
            par = next((p for p in parcels if p['parcel'] == pid), None)
            if par is None or par['use'] != 'residential':
                # lot-height label whose centre lies on a street strip: belongs to the nearest residential lot
                pid = min((p for p in parcels if p['use'] == 'residential'),
                          key=lambda p: Polygon(p['ring']).distance(Point(x, y)))['parcel']
                par = next(p for p in parcels if p['parcel'] == pid)
            ring_ls = LineString(par['ring'] + [par['ring'][0]])
            proj = ring_ls.interpolate(ring_ls.project(Point(x, y)))
            nearest_v = min(par['ring'], key=lambda q: math.dist(q, (proj.x, proj.y)))
            lot_heights.append({
                'z': float(t), 'parcel': pid, 'labelCentre': [r3(x), r3(y)],
                'at': [r3(proj.x), r3(proj.y)],
                'atRule': 'label centre projected onto the lot boundary',
                'nearestCorner': list(nearest_v), 'distToNearestCorner_m': r3(math.dist(nearest_v, (proj.x, proj.y))),
                'source': f'{SRC_MIG} TEXT handle {h} layer "L-00-ktse migrash" (legend: גובה מתוכנן מגרש)'})
    street_spots = []
    for layer, x, y, t, h in texts:
        if layer == 'Road Elevations':
            street_spots.append({'z': float(t), 'at': [r3(x), r3(y)], 'parcel': parcel_at(x, y),
                                 'source': f'{SRC_MIG} TEXT handle {h} layer "Road Elevations" (legend: גובה מתוכנן מדרכה)'})
    zero = None
    for e in E:
        if e['type'] == 'INSERT' and e['name'] == 'aumiflas11_10':
            a = attribs(e)
            zero = {'z': float(a['LEVEL1']), 'at': [r3(e['insertionPoint']['x']), r3(e['insertionPoint']['y'])],
                    'source': f'{SRC_MIG} block aumiflas11_10 attr LEVEL1 (legend: גובה 0.0 מתוכנן מבנה)'}

    # cross-check ±0.00 in the permit sheet (DIMS text "280.50" next to "± 0.00")
    permit = load('permit-sheet1.json')
    permit_zero = [e['text'] for e in permit['entities'] if e['type'] == 'MTEXT' and e.get('layer') == 'G-ANNO-DIMS'
                   and e['text'].strip() == '280.50']

    # ---------------- planned contours ----------------
    levels = json.load(open(os.path.join(ROOT, 'tools', 'contour-levels.json'), encoding='utf-8'))['levels']
    contours = []
    for e in E:
        if e['layer'].startswith('HW-CONT') and e['type'] == 'LWPOLYLINE' and in_itm(e['vertices'][0]['x']):
            lv = levels.get(e['handle'])
            if lv is None:
                print('WARNING: contour without level', e['handle'], file=sys.stderr)
                continue
            contours.append({'z': lv['z'], 'points': [[r3(x), r3(y)] for x, y in lw_points(e)],
                             'handle': e['handle'], 'basis': lv['basis'],
                             'source': f'{SRC_MIG} layer {e["layer"]} handle {e["handle"]}; Z per tools/contour-levels.json'})

    # ---------------- street linework (main map, native ITM) ----------------
    def collect(layer_names):
        out = []
        for e in E:
            if e['layer'] not in layer_names:
                continue
            if e['type'] == 'LWPOLYLINE' and in_itm(e['vertices'][0]['x']):
                out.append({'layer': e['layer'], 'closed': bool(e.get('flag', 0) & 1),
                            'points': [[r3(x), r3(y)] for x, y in lw_points(e)]})
            elif e['type'] == 'ARC' and in_itm(e['center']['x']):
                out.append({'layer': e['layer'], 'closed': False,
                            'points': [[r3(x), r3(y)] for x, y in arc_entity_points(e)]})
            elif e['type'] == 'LINE' and in_itm(e['startPoint']['x']):
                out.append({'layer': e['layer'], 'closed': False,
                            'points': [[r3(e['startPoint']['x']), r3(e['startPoint']['y'])],
                                       [r3(e['endPoint']['x']), r3(e['endPoint']['y'])]]})
        return out
    street = {
        'curbs': collect({'HW-CURB-BRDR', 'HW-CURB-GUTR', 'HW-CURB-IN', 'HW-CURB-SHLD', 'HW-CURB-LOW', 'HW-CURB-SDWK'}),
        'islands': collect({'HW-CURB-ILND'}),
        'pavedEntries': collect({'HW-WALK-250'}),
        'plannedFences': collect({'0-GDR'}),
        'source': f'{SRC_MIG} (main map, native ITM), layers HW-CURB-*, HW-WALK-250, 0-GDR',
        'note': 'קווי שפה/תעלה של המדרכה והכביש בתחום מסגרת המפה למשתכן בלבד',
    }
    building_lines = {
        'lot5187Envelope': collect({'0-BOUNDARY-BUILDING'}),
        'buildLines': collect({'0-Buildline'}),
        'source': f'{SRC_MIG} layers 0-BOUNDARY-BUILDING, 0-Buildline',
    }
    # main-map frame = block FRAMEM_BORDER (unit square) inserted with scale/rotation in ITM
    frame = None
    for e in E:
        if e['type'] == 'INSERT' and e['name'] == 'FRAMEM_BORDER' and in_itm(e['insertionPoint']['x']):
            ox, oy = e['insertionPoint']['x'], e['insertionPoint']['y']
            sx, sy, rot = e['xScale'], e['yScale'], e['rotation']
            c, sn = math.cos(rot), math.sin(rot)
            frame = [[r3(ox + u * sx * c - v * sy * sn), r3(oy + u * sx * sn + v * sy * c)]
                     for u, v in ((0, 0), (1, 0), (1, 1), (0, 1))]

    # ---------------- existing survey points ----------------
    survey_2023 = []
    for e in E:
        if e['type'] == 'INSERT' and e['name'] == 'M1502' and in_itm(e['insertionPoint']['x']):
            a = attribs(e)
            survey_2023.append({'name': a.get('NAME'), 'E': r3(e['insertionPoint']['x']), 'N': r3(e['insertionPoint']['y']),
                                'z': float(a['HEIGHT']), 'source': f'{SRC_MIG} block M1502 (גבהים קיימים, מפה למשתכן 08-05-2023)'})
    scan_pts_file = os.path.join(ROOT, 'tools', 'survey-2025-points.json')
    survey_2025 = json.load(open(scan_pts_file, encoding='utf-8')) if os.path.exists(scan_pts_file) else None

    # ---------------- origin, true north, lat/lon ----------------
    cen = lot_poly.centroid
    E0, N0 = round(cen.x), round(cen.y)
    tr = Transformer.from_crs(CRS.from_epsg(2039), CRS.from_epsg(4326), always_xy=True)
    lon, lat = tr.transform(cen.x, cen.y)
    pj = Proj(CRS.from_epsg(2039))
    fac = pj.get_factors(lon, lat)
    fwd = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(2039), always_xy=True)
    e1, n1 = fwd.transform(lon, lat); e2, n2 = fwd.transform(lon, lat + 0.001)
    true_north_grid_az = math.degrees(math.atan2(e2 - e1, n2 - n1))
    origin = {
        'crs': 'EPSG:2039 (Israeli TM Grid, ITM)',
        'E0': E0, 'N0': N0, 'H0': zero['z'],
        'H0_meaning': '±0.00 של הבית = גובה 0.0 מתוכנן מבנה',
        'H0_source': zero['source'] + (f'; cross-checked in {SRC_PERMIT} G-ANNO-DIMS "280.50"' if permit_zero else ''),
        'axes': 'x = E - E0 (east), y = H - H0 (up), z = -(N - N0) (south)',
        'lotCentroid': {'E': r3(cen.x), 'N': r3(cen.y), 'lat': round(lat, 7), 'lon': round(lon, 7)},
        'meridianConvergence_deg': round(fac.meridian_convergence, 5),
        'trueNorthGridAzimuth_deg': round(true_north_grid_az, 5),
        'trueNorth_note': 'כיוון הצפון האמיתי ברשת ITM: אזימוט רשת = trueNorthGridAzimuth_deg (נבדק בהמרה מספרית של נקודה 0.001° צפונה). אזימוט שמש ברשת = אזימוט אמיתי + trueNorthGridAzimuth_deg.',
        'timezone': 'Asia/Jerusalem',
        'georeference': georef,
        'mapFrameITM': frame,
        'contextWindowITM': list(CONTEXT),
    }

    # ---------------- write ----------------
    os.makedirs(OUT, exist_ok=True)
    def dump(name, obj):
        with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        print('wrote', name)
    dump('origin.json', origin)
    dump('control-points.json', {'points': [{'name': k, 'E': r3(v[0]), 'N': r3(v[1])} for k, v in sorted(pts.items())],
                                 'source': f'{SRC_MIG} block C1610 (נקודות גבול), identical to coordinate table in {SRC_SURVEY_SCAN}'})
    dump('plot-5187.json', plot)
    dump('parcels.json', {'parcels': parcels, 'note': 'גבולות חלקות מהתרשים 1:5000 שבמפה למשתכן (העתק מוקטן מדויק). ייעוד החלקות הציבוריות (9, 20, 21) – ראו docs/open-issues.md'})
    dump('planned-heights.json', {'houseZero': zero, 'lotCorners': lot_heights, 'streetSpots': street_spots,
                                  'note': 'גבהים סופיים לפי המפה למשתכן (תוכנית פיתוח). תוויות גובה המגרש משויכות לחלקה לפי מיקום התווית, ומוצמדות לקודקוד הקרוב של החלקה.'})
    dump('street.json', {**street, 'contours': contours})
    dump('building-lines.json', building_lines)
    dump('survey-existing.json', {'survey2023': survey_2023, 'survey2025': survey_2025})


if __name__ == '__main__':
    main()

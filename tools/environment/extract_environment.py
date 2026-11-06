#!/usr/bin/env python3
"""
Environment extraction: neighbouring lots, streets and maximum neighbour envelopes around lot 5187.
  -> data/environment/lots.json, data/environment/streets.json

Sources (priority per CLAUDE.md §1):
  1. DWG  sources/survey/INDEX_F02628-36-MIG-5187.dwg   (already extracted to data/site/parcels.json, street.json,
          planned-heights.json, building-lines.json by tools/extract_site.py)  -> lot/street boundaries, street heights
  2. PDF  sources/neighborhood/מפה אורכי מגרשים רקפות.pdf  (vector, 1:500, georeferenced here to 8 DWG boundary points)
          -> lot numbers (מגרש) per parcel, dividing line 226/227 (missing in the DWG inset), boundary-point check
     PDF  sources/development/תוכנית גבהים בגוש שלי.pdf     (vector, sheet 04 B1, 04.12.2022, georeferenced here by
          ICP to the DWG lot corners) -> final lot-corner levels and ±0.00 (מפלס כניסה קובעת) of every lot
  3. Zoning text (TAMAL/1016 §4.1.2, table 5) via data/config/neighbors-rules.json -> setbacks, floors, height rule
     Typical street sections: sources/development/תוכנית נוף.pdf (scanned; values typed in
     data/environment/manual-readings.json with the location on the sheet)
Run: python3 tools/environment/extract_environment.py   (needs pymupdf, shapely, numpy, scipy)
"""
import json, math, os, re
import numpy as np
import pymupdf as fitz
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, LineString, Point, MultiPolygon, box
from shapely.ops import unary_union, split, nearest_points

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = lambda *a: os.path.join(ROOT, *a)
OUT = P('data', 'environment')
r3 = lambda v: round(float(v), 3)

SRC_MIG = 'sources/survey/INDEX_F02628-36-MIG-5187.dwg'
SRC_LEN = 'sources/neighborhood/מפה אורכי מגרשים רקפות.pdf'
SRC_HGT = 'sources/development/תוכנית גבהים בגוש שלי.pdf'
SRC_NOF = 'sources/development/תוכנית נוף.pdf'


def jload(*p):
    with open(P(*p), encoding='utf-8') as f:
        return json.load(f)


def jdump(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    print('wrote', os.path.relpath(os.path.join(OUT, name), ROOT))


def ring_of(g):
    if isinstance(g, MultiPolygon):
        g = max(g.geoms, key=lambda q: q.area)
    g = g.buffer(0)
    if not g.exterior.is_ccw:
        g = Polygon(list(g.exterior.coords)[::-1])
    return [[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]]


def fit_similarity(A, B, reflect):
    """Least-squares similarity A(pdf) -> B(ITM). reflect=True for y-down PDF space. Returns f, residuals."""
    za = np.array([complex(*a) for a in A]); za = np.conj(za) if reflect else za
    zb = np.array([complex(*b) for b in B])
    M = np.vstack([za, np.ones_like(za)]).T
    s, *_ = np.linalg.lstsq(M, zb, rcond=None)
    res = np.abs(M @ s - zb)
    def f(q):
        z = complex(*q); z = z.conjugate() if reflect else z
        w = s[0] * z + s[1]
        return (w.real, w.imag)
    f.scale = abs(s[0]); f.rot = math.degrees(np.angle(s[0]))
    return f, res


cfg = jload('data', 'environment', 'config.json')
manual = jload('data', 'environment', 'manual-readings.json')
rules = jload('data', 'config', 'neighbors-rules.json')
parcels = {p['parcel']: p for p in jload('data', 'site', 'parcels.json')['parcels']}
ctrl = {q['name']: (q['E'], q['N']) for q in jload('data', 'site', 'control-points.json')['points']}
street_dwg = jload('data', 'site', 'street.json')
heights_dwg = jload('data', 'site', 'planned-heights.json')
origin = jload('data', 'site', 'origin.json')
bl_dwg = jload('data', 'site', 'building-lines.json')

# =====================================================================================================
# 1. Lot-lengths map (vector PDF 1:500): boundary points + lot numbers, georeferenced to the DWG points
# =====================================================================================================
doc = fitz.open(P(SRC_LEN)); pg = doc[0]
win = fitz.Rect(*cfg['lengthsMap']['pdfWindow'])
markers, annots = [], []
for dr in pg.get_drawings():
    r = dr['rect']
    if not r.intersects(win):
        continue
    if dr['items'] and all(i[0] == 'c' for i in dr['items']) and abs(r.width - cfg['lengthsMap']['markerSize_pt']) < 0.3:
        markers.append(((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
for a in pg.annots():
    if a.rect.intersects(win):
        annots.append((((a.rect.x0 + a.rect.x1) / 2, (a.rect.y0 + a.rect.y1) / 2), (a.info.get('content') or '').strip(),
                       a.rect.width, a.rect.height))
ptnum = [a for a in annots if re.fullmatch(r'\d{4}', a[1]) and a[3] < cfg['lengthsMap']['pointLabelMaxHeight_pt']]
bpts_pdf = {}
for (x, y) in markers:
    best = min(ptnum, key=lambda a: (a[0][0] - x) ** 2 + (a[0][1] - y) ** 2)
    if math.dist(best[0], (x, y)) < cfg['lengthsMap']['labelMarkerMaxDist_pt']:
        bpts_pdf.setdefault(best[1], (x, y))
common = [k for k in ctrl if k in bpts_pdf]
Tlen, res_len = fit_similarity([bpts_pdf[k] for k in common], [ctrl[k] for k in common], reflect=True)
bpts = {k: Tlen(v) for k, v in bpts_pdf.items()}
georef_len = {'method': 'similarity (with reflection: PDF y-down) fitted to DWG boundary points', 'points': common,
              'scale_m_per_pt': r3(Tlen.scale * 1000) / 1000, 'rotation_deg': round(Tlen.rot, 4),
              'maxResidual_m': r3(res_len.max()), 'rms_m': r3(np.sqrt((res_len ** 2).mean()))}
print('lengths map georef', georef_len)

# lot numbers (large 4-digit labels inside the lot) -> parcel
lotlabels = [a for a in annots if re.fullmatch(r'\d{4}', a[1]) and a[3] >= cfg['lengthsMap']['lotLabelMinHeight_pt']]

# =====================================================================================================
# 2. Lots: DWG parcels; 226/227 split along the lengths-map line between its two boundary points
# =====================================================================================================
polys = {k: Polygon(v['ring']) for k, v in parcels.items()}
for sp in cfg['splits']:
    merged = polys[sp['merged']]
    a, b = bpts[sp['line'][0]], bpts[sp['line'][1]]
    da, db = merged.exterior.distance(Point(a)), merged.exterior.distance(Point(b))
    ux, uy = (b[0] - a[0]), (b[1] - a[1]); L = math.hypot(ux, uy); ux, uy = ux / L, uy / L
    cut = LineString([(a[0] - ux * 2, a[1] - uy * 2), (b[0] + ux * 2, b[1] + uy * 2)])
    parts = list(split(merged, cut).geoms)
    assert len(parts) == 2, 'split failed'
    for part in parts:
        inside = [l for l in lotlabels if part.contains(Point(Tlen(l[0])))]
        # parcel number labels (1–3 digits, black) from the lengths map
        pn = [a2[1] for a2 in annots if re.fullmatch(r'\d{1,3}', a2[1]) and part.contains(Point(Tlen(a2[0])))]
        pid = next(p for p in pn if p in sp['parts'])
        part = Polygon(ring_of(part))
        polys[pid] = part
        parcels[pid] = {**parcels[sp['merged']], 'parcel': pid, 'merged': False, 'ring': ring_of(part),
                        'area_m2': r3(part.area),
                        'source': f"{parcels[sp['merged']]['source']}; dividing line {sp['line'][0]}–{sp['line'][1]} from {SRC_LEN} "
                                  f"(boundary points off the DWG outline by {da:.3f} / {db:.3f} m)"}
    sp['offOutline_m'] = [r3(da), r3(db)]
    del polys[sp['merged']]

def parcel_of(E, N):
    for k, pg2 in polys.items():
        if pg2.contains(Point(E, N)):
            return k
    return None

lot_no = {}
for (xy, txt, w, h) in lotlabels:
    k = parcel_of(*Tlen(xy))
    if k:
        lot_no.setdefault(k, txt)

# check: every lengths-map boundary point near the lot set lies on a DWG parcel vertex
allv = np.array([v for k, p in polys.items() for v in p.exterior.coords])
tree = cKDTree(allv)
sel_union = unary_union([polys[k] for k in cfg['lots'] + ['257']]).buffer(1.0)
chk = [(k, tree.query(v)[0]) for k, v in bpts.items() if sel_union.contains(Point(v))]
bp_check = {'points': len(chk), 'maxDist_m': r3(max(d for _, d in chk)), 'median_m': r3(np.median([d for _, d in chk]))}
print('lengths-map boundary points vs DWG vertices', bp_check)

# =====================================================================================================
# 3. Heights plan (vector PDF): georeference by ICP on lot corners, read ±0.00 and lot-corner levels
# =====================================================================================================
CACHE = P('tools', 'cache', 'heights-plan-window-v3.json')
HSYM = cfg['heightsPlan']['zeroSymbolSize_pt']
if os.path.exists(CACHE) and json.load(open(CACHE)).get('window') == cfg['heightsPlan']['pdfWindowRotated']:
    _c = json.load(open(CACHE)); ends = [[tuple(q) for q in e] for e in _c['ends']]; hann = [(tuple(a[0]), a[1]) for a in _c['annots']]
    syms = [tuple(q) for q in _c['symbols']]
else:
    hd = fitz.open(P(SRC_HGT)); hp = hd[0]; RM = hp.rotation_matrix
    hwin = fitz.Rect(*cfg['heightsPlan']['pdfWindowRotated'])
    blue = tuple(cfg['heightsPlan']['lotLineColor'])
    ends, hann, syms = [], [], []
    for dr in hp.get_drawings():
        rr = dr['rect'] * RM
        # ±0.00 symbol ("מפלס כניסה קובעת"): small black circle drawn with curves
        if rr.intersects(hwin) and dr.get('color') == (0.0, 0.0, 0.0) and dr['items'] and all(i[0] == 'c' for i in dr['items']) \
                and HSYM[0] < rr.width < HSYM[1] and HSYM[0] < rr.height < HSYM[1]:
            syms.append(((rr.x0 + rr.x1) / 2, (rr.y0 + rr.y1) / 2))
        if (dr['rect'] * RM).intersects(hwin) and dr.get('color') and all(abs(a - b) < 1e-3 for a, b in zip(dr['color'], blue)):
            for it in dr['items']:
                if it[0] == 'l':
                    ends.append([tuple(it[1] * RM), tuple(it[2] * RM)])
                elif it[0] == 'c':
                    ends.append([tuple(it[1] * RM), tuple(it[4] * RM)])
    for a in hp.annots():
        r = a.rect * RM
        if r.intersects(hwin):
            hann.append((((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2), (a.info.get('content') or '').strip()))
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump({'window': cfg['heightsPlan']['pdfWindowRotated'], 'ends': ends, 'annots': hann, 'symbols': syms}, open(CACHE, 'w'))
def junctions(k):
    """Ring vertices of lot k where the parcel on the other side changes (true lot corners incl. arc ends)."""
    ring = list(polys[k].exterior.coords)[:-1]
    others = [(q, polys[q]) for q in polys if q != k and polys[q].distance(polys[k]) < 0.05]
    def nb(p):
        return frozenset(q for q, g in others if g.distance(Point(p)) < 0.02)
    out = []
    n = len(ring)
    for i in range(n):
        s_prev, s_here, s_next = nb(ring[i - 1]), nb(ring[i]), nb(ring[(i + 1) % n])
        if len(s_here) >= 2 or s_prev != s_next and s_here and (s_here != s_prev or s_here != s_next):
            out.append(ring[i])
    # merge near-duplicates
    merged = []
    for p in out:
        if all(math.dist(p, m) > 0.5 for m in merged):
            merged.append(p)
    return merged

# initial transform: lot-number labels -> parcel centroids (lot numbers from the lengths map)
seed = [(xy, polys[k].centroid.coords[0]) for xy, t in hann for k, n in lot_no.items() if t == n and k in polys]
Th, _ = fit_similarity([s[0] for s in seed], [s[1] for s in seed], reflect=True)
# keep lot lines only: drop short strokes (digits, flow arrows) and the blue lot-number boxes
HB = cfg['heightsPlan']
boxes = [xy for xy, t in hann if re.fullmatch(r'\d{2,4}', t)]
def in_box(q):
    return any(abs(q[0] - b[0]) < HB['lotLabelBoxHalf_pt'][0] and abs(q[1] - b[1]) < HB['lotLabelBoxHalf_pt'][1] for b in boxes)
ends = np.array([q for a, b in ends if math.dist(a, b) > HB['minSegment_pt'] for q in (a, b) if not in_box(q)])
near = unary_union([polys[q] for q in cfg['lots'] + ['257']])
verts = np.array([v for k in polys if polys[k].distance(near) < 20 and parcels[k]['use'] == 'residential' for v in junctions(k)])
vt = cKDTree(verts)
for tol in cfg['heightsPlan']['icpTolerances_m']:
    E = np.array([Th(q) for q in ends]); d, i = vt.query(E); ok = d < tol
    Th, res_h = fit_similarity(ends[ok], verts[i[ok]], reflect=True)
georef_h = {'method': 'similarity (reflection, rotated page) by ICP of lot-line end points to DWG lot vertices',
            'pairs': int(ok.sum()), 'scale_m_per_pt': round(float(Th.scale), 6), 'rotation_deg': round(Th.rot, 4),
            'medianResidual_m': r3(np.median(res_h)), 'p95Residual_m': r3(np.percentile(res_h, 95)), 'maxResidual_m': r3(res_h.max()),
            'note': 'used only to attach the height labels to lots and corners; no geometry is taken from this sheet'}
print('heights plan georef', georef_h)
# ±0.00 symbol centres in ITM (merge the curve pieces of each symbol), with the ±0.00 value written next to it
_sy = []
for q in (Th(q) for q in syms):
    if all(math.dist(q, m) > 0.6 for m in _sy):
        _sy.append(q)
_lab = [(Th(xy), float(t)) for xy, t in hann if re.fullmatch(r'\d{3}\.\d{1,2}', t)]
pm0_symbols = []
for q in _sy:
    near_l = sorted(((math.dist(q, l[0]), l[1]) for l in _lab))
    pm0_symbols.append({'E': r3(q[0]), 'N': r3(q[1]), 'z': near_l[0][1] if near_l and near_l[0][0] < 7.0 else None})
print('±0.00 symbols', len(pm0_symbols))


nums = [(Th(xy), float(t)) for xy, t in hann if re.fullmatch(r'\d{3}\.\d{1,2}', t)]
lots_heights = {}
_near_win = unary_union([polys[q] for q in cfg['lots'] + ['257']]).buffer(cfg['streets']['windowMargin_m'] + 25)
_all_res = [k for k in polys if parcels[k]['use'] == 'residential' and polys[k].intersects(_near_win)]
for k in sorted(set(cfg['lots'] + ['257'] + _all_res)):
    pg2 = polys[k]
    zero, corners = [], []
    J = junctions(k)
    for (E, N), z in nums:
        if not pg2.contains(Point(E, N)):
            continue
        db = pg2.exterior.distance(Point(E, N))
        if db >= cfg['heightsPlan']['zeroLabelMinDistFromBoundary_m']:
            zero.append({'z': z, 'labelAt': [r3(E), r3(N)]})
        elif db <= cfg['heightsPlan']['cornerLabelMaxDistFromBoundary_m']:
            j = min(J, key=lambda q: math.dist(q, (E, N)))
            corners.append({'z': z, 'at': [r3(j[0]), r3(j[1])], 'labelAt': [r3(E), r3(N)], 'labelToCorner_m': r3(math.dist(j, (E, N)))})
    lots_heights[k] = (zero, corners, J)

# =====================================================================================================
# 4. Setbacks + maximum envelope (TAMAL/1016 §4.1.2)
# =====================================================================================================
SB = rules['setbacks_m']
public = {k for k, p in parcels.items() if p['use'] == 'public'}


def edge_pieces(k):
    """Split the lot boundary into pieces: one per residential neighbour; street frontage (any public parcel or no
    parcel) is one 'street' piece, split again where its direction turns by more than the corner-split angle
    (the two frontages of a corner lot)."""
    ring = list(polys[k].exterior.coords)[:-1]
    if not polys[k].exterior.is_ccw:
        ring = ring[::-1]
    n = len(ring)
    def across(i):
        a, b = ring[i], ring[(i + 1) % n]
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy) or 1
        q = parcel_of(m[0] + dy / L * 0.3, m[1] - dx / L * 0.3)  # right-hand side of a CCW ring = outside
        return 'street' if (q is None or q in public) else q
    labels = [across(i) for i in range(n)]
    start = next((i for i in range(n) if labels[i] != labels[i - 1]), 0)
    pieces, cur = [], None
    lim = math.radians(cfg['envelope']['cornerSplitTurn_deg'])
    for j in range(n):
        i = (start + j) % n
        a, b = ring[i], ring[(i + 1) % n]
        hd = math.atan2(b[1] - a[1], b[0] - a[0])
        turn = cur is not None and labels[i] == 'street' and cur['across'] == 'street' and \
            abs((hd - cur['h0'] + math.pi) % (2 * math.pi) - math.pi) > lim
        if cur is None or labels[i] != cur['across'] or turn:
            cur = {'across': labels[i], 'pts': [a], 'h0': hd}
            pieces.append(cur)
        cur['pts'].append(b)
    for p in pieces:
        a, b = p['pts'][0], p['pts'][-1]
        p['length'] = LineString(p['pts']).length
        dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy) or 1
        p['outward'] = (dy / L, -dx / L)
        q = [parcel_of(x + p['outward'][0] * 0.3, y + p['outward'][1] * 0.3) for x, y in p['pts'][len(p['pts']) // 2:len(p['pts']) // 2 + 1]]
        p['parcelAcross'] = q[0]
    return pieces


def corner_lot(pcs):
    return len([p for p in pcs if p['across'] == 'street']) > 1


def dotp(p, q):
    return p['outward'][0] * q['outward'][0] + p['outward'][1] * q['outward'][1]


S04 = P('data', 'environment', 'sheet04.json')
sheet04 = {l['parcel']: l for l in json.load(open(S04, encoding='utf-8'))['lots']} if os.path.exists(S04) else {}
lots_out, env_check = [], None
for k in cfg['lots'] + ['257']:
    ov = cfg.get('frontOverrides', {}).get(k)
    s4 = sheet04.get(k, {}).get('entranceFrom') if cfg.get('frontFromSheet04', {}).get('use') else None
    pcs = edge_pieces(k)
    pub = [p for p in pcs if p['across'] == 'street']
    res = [p for p in pcs if p not in pub]
    if not pub:
        print('no street frontage', k); raise SystemExit(1)
    # primary front: the street piece facing a residential piece (the rear) – the longest such piece
    cand = [p for p in pub if any(dotp(p, q) < -0.8 for q in res)] or pub
    if ov:
        rear = max((q for q in res if q['across'] == ov['rear']), key=lambda q: q['length'])
        front = min(pub, key=lambda p: dotp(p, rear))
    elif s4 and len(pub) > 1 and pcs[s4['edgeIndex']] in pub:
        front = pcs[s4['edgeIndex']]
    else:
        front = max(cand, key=lambda p: p['length'])
    for p in pcs:
        if p is front:
            p['kind'] = 'front'
        elif p in pub:
            p['kind'] = 'front2'  # second street frontage of a corner lot: front-type line (3 m)
        else:
            p['kind'] = 'rear' if dotp(front, p) < -0.8 else 'side'
    dist = {'front': SB['front'], 'front2': SB['front'], 'side': SB['side'], 'rear': SB['rear']}
    cutters = [LineString(p['pts']).buffer(dist[p['kind']], cap_style='round', join_style='round', quad_segs=32) for p in pcs]
    env = polys[k].difference(unary_union(cutters))
    env = max(env.geoms, key=lambda g: g.area) if isinstance(env, MultiPolygon) else env
    corner = len([p for p in pcs if p['kind'] == 'front2']) > 0
    if k == '257':
        drawn_pts = [tuple(q) for e in bl_dwg['lot5187Envelope'] for q in e['points']]
        devs = [env.exterior.distance(Point(q)) for q in drawn_pts]
        env_check = {'lot': '5187', 'maxDeviation_m': r3(max(devs)), 'drawnVertices': len(drawn_pts), 'areaComputed_m2': r3(env.area),
                     'edges': {p['kind']: [q['across'] for q in pcs if q['kind'] == p['kind']] for p in pcs},
                     'drawn': f'{SRC_MIG} layer 0-BOUNDARY-BUILDING (open polylines; distance of every drawn vertex to the computed envelope)',
                     'note': 'same routine as the neighbours; validates the setback logic'}
        print('self-check 5187 envelope', env_check)
        continue
    zero, corners, J = lots_heights[k]
    zrule = rules['entranceLevel']['byParcel'].get(k)
    z0 = zero[0]['z'] if len(zero) == 1 else None
    z0_check = None
    if zrule:
        z0_check = {'sheet04Scan': zrule['pm0'], 'match': z0 is not None and abs(zrule['pm0'] - z0) < 0.005}
    sus = cfg.get('suspectValues', {}).get(k)
    dec = cfg.get('ownerDecisions', {}).get(k)
    pm0 = {'z': z0, 'status': 'suspect' if sus else ('source' if z0 is not None else 'missing'),
           'source': f'{SRC_HGT} symbol "מפלס כניסה קובעת" (annotation text)', 'check': z0_check, **({'note': sus['note']} if sus else {})}
    if dec and 'pm0' in dec:
        pm0 = {'z': dec['pm0'], 'status': 'owner', 'source': dec['why'], 'sourceValue': z0, 'check': z0_check}
        z0, sus = dec['pm0'], None
    front_rule = ov['why'] if ov else (cfg['frontFromSheet04']['why'] + ' (sheet 04)' if s4 and corner_lot(pcs) else
                 'front = street frontage opposite a residential neighbour (rear); other street frontage of a corner lot = 3 m')
    front_status = ov.get('status', 'assumption') if ov else ('sheet04' if s4 and corner_lot(pcs) else ('assumption' if corner_lot(pcs) else 'rule'))
    rec = {
        'parcel': k, 'lot': lot_no.get(k), 'gush': parcels[k].get('gush'), 'use': parcels[k]['use'],
        'ring': ring_of(polys[k]), 'area_m2': r3(polys[k].area),
        'ringSource': parcels[k]['source'],
        'lotNumberSource': f'{SRC_LEN} (label inside the lot, georeferenced map)',
        'pm0': pm0,
        'cornerLevels': [{**c, 'source': f'{SRC_HGT} lot-corner label (annotation text) – assigned to the nearest lot corner'} for c in corners],
        'cornerCount': len(J), 'cornersWithLevel': len(corners),
        'edges': [{'across': p['across'] if p['across'] != 'street' else (f"רחוב (חלקה {p['parcelAcross']})" if p['parcelAcross'] else 'רחוב (מחוץ לתרשים החלקות)'), 'kind': p['kind'], 'setback_m': dist[p['kind']], 'length_m': r3(p['length']),
                   'pts': [[r3(x), r3(y)] for x, y in p['pts']]} for p in pcs],
        'cornerLot': corner,
        'frontRule': front_rule,
        'frontStatus': front_status,
        'envelope': {
            'ring': ring_of(env), 'area_m2': r3(env.area),
            'base': z0, 'height_m': rules['maxHeightAboveEntrance_m']['value'],
            'heightStatus': rules['maxHeightAboveEntrance_m']['status'],
            'floors': rules['floorsAboveEntrance'],
            'build': z0 is not None and not sus,
            'source': f"{rules['source']}; setbacks front {SB['front']} / side {SB['side']} / rear {SB['rear']} m; "
                      f"height {rules['maxHeightAboveEntrance_m']['value']} m above ±0.00 ({rules['maxHeightAboveEntrance_m']['source']})",
        },
        'type': cfg.get('lotTypes', {}).get(k),
    }
    lots_out.append(rec)

jdump('lots.json', {
    '_doc': 'Neighbouring lots of 5187: boundary (DWG), lot number (lengths map), final levels (heights plan), '
            'setbacks and maximum envelope (TAMAL/1016). Generated by tools/environment/extract_environment.py – do not edit.',
    'georeference': {'lengthsMap': georef_len, 'heightsPlan': georef_h, 'boundaryPointCheck': bp_check},
    'splits': cfg['splits'],
    'pm0Symbols': pm0_symbols,
    'parking': cfg['parking'],
    'envelopeSelfCheck': env_check,
    'rules': {'setbacks_m': SB, 'source': rules['source'], 'height': rules['maxHeightAboveEntrance_m'],
              'floorsAboveEntrance': rules['floorsAboveEntrance'], 'floorsBelowEntrance': rules['floorsBelowEntrance']},
    'lot5187Check': {'pm0': lots_heights['257'][0], 'corners': lots_heights['257'][1]},
    'lots': lots_out,
})

# =====================================================================================================
# 5. Streets: parcels clipped to the modelled window; integrated street (13.0 m) + MIG linework/heights
# =====================================================================================================
sel = unary_union([polys[k] for k in cfg['lots'] + ['257']])
minx, miny, maxx, maxy = sel.bounds
m = cfg['streets']['windowMargin_m']
window = box(minx - m, miny - m, maxx + m, maxy + m)
frame = Polygon(origin['mapFrameITM'])
streets = []
street_parcels = cfg['streets']['parcels']
if street_parcels == 'auto':
    street_parcels = sorted(k for k in public if polys[k].distance(sel) < 0.1)
for k in street_parcels:
    g = polys[k].intersection(window)
    if g.is_empty:
        continue
    geoms = g.geoms if hasattr(g, 'geoms') else [g]
    for gi in geoms:
        if gi.area < 1:
            continue
        with_h = gi.intersection(frame)
        without = gi.difference(frame)
        def parts(x):
            return [q for q in (x.geoms if hasattr(x, 'geoms') else [x]) if not q.is_empty and q.area > 0.5]
        for q in parts(with_h):
            streets.append({'parcel': k, 'ring': ring_of(q), 'area_m2': r3(q.area), 'heights': 'source',
                            'heightSource': f'{SRC_MIG}: planned contours HW-CONT-10/20 + "Road Elevations" (data/site/street.json, planned-heights.json streetSpots)',
                            'source': f"{parcels[k]['source']} ∩ buyer-map frame"})
        for q in parts(without):
            streets.append({'parcel': k, 'ring': ring_of(q), 'area_m2': r3(q.area), 'heights': 'missing',
                            'heightSource': None, 'note': 'אין גבהי רחוב במקורות מחוץ למסגרת המפה למשתכן (docs/open-issues.md)',
                            'source': f"{parcels[k]['source']} (outside the buyer-map frame)"})

# ---------- street zones by measured width (lot line to the lot opposite) ----------
# 13 m = integrated street (960), 15 m = traffic-calming section (910, owner decision E5), other widths: no section
SEC = cfg['streets']['sectionsByWidth']
resid = {k: g for k, g in polys.items() if parcels[k]['use'] == 'residential' and g.distance(window) < 1}
res_union = unary_union(list(resid.values()))
street_area = unary_union([Polygon(s['ring']) for s in streets])
zone_geoms = {}
piece_widths = []
others_cache = {}
for k, g in resid.items():
    if g.distance(street_area) > 0.1:
        continue
    others = unary_union([q for kk, q in resid.items() if kk != k and q.distance(g) > 0.05])
    for pc in edge_pieces(k):
        if pc['across'] != 'street' or pc['length'] < 1:
            continue
        line = LineString(pc['pts'])
        n = max(1, int(line.length / cfg['streets']['sampleStep_m']))
        for i in range(n):
            a_ = line.interpolate(i / n, normalized=True); b_ = line.interpolate((i + 1) / n, normalized=True)
            dx, dy = b_.x - a_.x, b_.y - a_.y; Ln = math.hypot(dx, dy) or 1
            nx, ny = dy / Ln, -dx / Ln  # outward for a CCW ring
            mx, my = (a_.x + b_.x) / 2, (a_.y + b_.y) / 2
            hit = LineString([(mx + nx * 0.05, my + ny * 0.05), (mx + nx * 25, my + ny * 25)]).intersection(others)
            if hit.is_empty:
                continue
            w = Point(mx, my).distance(hit)
            sec_k = next((x for x in SEC if abs(w - x['width_m']) <= x['tol_m']), None)
            piece_widths.append({'lot': k, 'at': [r3(mx), r3(my)], 'width_m': r3(w), 'section': sec_k['id'] if sec_k else None})
            if not sec_k:
                continue
            seg = LineString([(a_.x, a_.y), (b_.x, b_.y)])
            for band in sec_k['bands']:
                zone_geoms.setdefault(band['zone'], []).append(seg.buffer(band['to_m'], cap_style='flat').buffer(0.02))
            zone_geoms.setdefault('region-' + sec_k['id'], []).append(seg.buffer(w / 2 + 0.05, cap_style='flat').buffer(0.05))
zones = {z: unary_union(g) for z, g in zone_geoms.items()}
# bands are cumulative distances from the lot line: subtract the inner bands
for sec_k in SEC:
    prev = None
    for band in sec_k['bands']:
        z = band['zone']
        if prev is not None:
            zones[z] = zones[z].difference(zones[prev + '#acc'])
        zones[z + '#acc'] = unary_union([zones[z]] + ([zones[prev + '#acc']] if prev else []))
        prev = z
zoned = []
for s_ in streets:
    q0 = Polygon(s_['ring'])
    rest = q0
    for sec_k in SEC:
        reg = zones.get('region-' + sec_k['id'])
        if reg is None:
            continue
        for band in sec_k['bands']:
            part = rest.intersection(zones[band['zone']]).intersection(reg)
            for g in (part.geoms if hasattr(part, 'geoms') else [part]):
                if g.geom_type == 'Polygon' and g.area > 0.3:
                    zoned.append({**s_, 'ring': ring_of(g), 'area_m2': r3(g.area), 'zone': band['zone'], 'zoneLabel': band['label'], 'section': sec_k['id']})
            rest = rest.difference(part)
        part = rest.intersection(reg)
        for g in (part.geoms if hasattr(part, 'geoms') else [part]):
            if g.geom_type == 'Polygon' and g.area > 0.3:
                zoned.append({**s_, 'ring': ring_of(g), 'area_m2': r3(g.area), 'zone': sec_k['restZone'], 'zoneLabel': sec_k['restLabel'], 'section': sec_k['id']})
        rest = rest.difference(part)
    for g in (rest.geoms if hasattr(rest, 'geoms') else [rest]):
        if g.geom_type == 'Polygon' and g.area > 0.3:
            zoned.append({**s_, 'ring': ring_of(g), 'area_m2': r3(g.area), 'zone': 'street', 'zoneLabel': 'רחוב – ללא חתך', 'section': None})
streets = zoned
print('street zones', {z: round(sum(x['area_m2'] for x in streets if x['zone'] == z)) for z in set(x['zone'] for x in streets)})

# measured street width (lot line to lot line) in front of 5187 vs the typical section
front257 = next(e for e in edge_pieces('257') if e['across'] == 'street')
width_meas = min(polys[q].distance(LineString(front257['pts'])) for q in cfg['streets']['oppositeLots'])
sec = manual['integratedStreetSection']
ctrl_pts = [{'E': x, 'N': y, 'z': c['z']} for c in street_dwg['contours'] for x, y in c['points']] + \
           [{'E': s['at'][0], 'N': s['at'][1], 'z': s['z']} for s in heights_dwg['streetSpots']]

# ---------- street levels outside the buyer-map frame: derived from the lot-front levels ----------
# The sources have no street levels there (no road plan/profiles – owner 06.11.2026: "use what exists").
# Control points = final lot-corner levels (heights plan) on the street frontages of all lots in the window.
from scipy.interpolate import LinearNDInterpolator
street_union = unary_union([Polygon(x['ring']).buffer(0) for x in streets]).buffer(0.05)
front_pts = []
for k, (zero, corners, J) in lots_heights.items():
    for c in corners:
        if street_union.contains(Point(c['at'])) or street_union.distance(Point(c['at'])) < 0.05:
            front_pts.append({'E': c['at'][0], 'N': c['at'][1], 'z': c['z'], 'lot': k})
# dedupe identical corners (two lots share a corner): mean of the two labels
_dd = {}
for q in front_pts:
    _dd.setdefault((round(q['E'], 1), round(q['N'], 1)), []).append(q)
front_pts = [{'E': v[0]['E'], 'N': v[0]['N'], 'z': r3(sum(x['z'] for x in v) / len(v)), 'lots': sorted({x['lot'] for x in v})} for v in _dd.values()]
# check: interpolate the lot-front levels at the DWG street contour points (inside the frame)
fi = LinearNDInterpolator([(q['E'], q['N']) for q in front_pts], [q['z'] for q in front_pts])
dev = [fi(p['E'], p['N']) - p['z'] for p in ctrl_pts]
dev = [float(d) for d in dev if not np.isnan(d)]
derived_check = {'points': len(dev), 'mean_m': r3(np.mean(dev)) if dev else None, 'meanAbs_m': r3(np.mean(np.abs(dev))) if dev else None,
                 'max_m': r3(max(dev, key=abs)) if dev else None,
                 'note': 'lot-front interpolation minus the DWG planned street levels, inside the buyer-map frame'}
# the street is systematically lower than the lot edges (curb/edge stone, drainage): calibrate by the mean offset
bias = float(np.mean(dev)) if dev else 0.0
res_after = [d - bias for d in dev]
derived_check.update({'biasApplied_m': r3(-bias), 'afterBias_meanAbs_m': r3(np.mean(np.abs(res_after))) if dev else None,
                      'afterBias_max_m': r3(max(res_after, key=abs)) if dev else None})
for q in front_pts:
    q['zLotEdge'] = q['z']; q['z'] = r3(q['z'] - bias)
print('derived street levels check', derived_check)
for x in streets:
    if x['heights'] == 'missing':
        x['heights'] = 'derived'
        x['heightStatus'] = 'provisional'
        x['heightSource'] = f'{SRC_HGT}: final lot-corner levels on the street frontages, interpolated across the street (no street levels in the sources)'
        x['note'] = 'גובה רחוב משוער: אינטרפולציה בין גבהי קצות המגרשים שמשני הצדדים (תוכנית הגבהים). אין במקורות גבהי רחוב לאזור זה (docs/open-issues.md E1)'
jdump('streets.json', {
    '_doc': 'Streets around lot 5187. Generated by tools/environment/extract_environment.py – do not edit.',
    'window': [r3(v) for v in window.bounds],
    'parcels': street_parcels,
    'frameITM': origin['mapFrameITM'],
    'surfaces': streets,
    'sections': SEC,
    'frontageWidths': piece_widths,
    'derivedHeightControl': {'points': front_pts, 'check': derived_check, 'status': 'provisional',
                             'source': f'{SRC_HGT} lot-corner levels on street frontages'},
    'heightControl': {'points': [{'E': r3(p['E']), 'N': r3(p['N']), 'z': p['z']} for p in ctrl_pts],
                      'source': f'{SRC_MIG} (planned street contours + Road Elevations, inside the map frame only)'},
    'integratedStreet': {
        'name': sec['name'], 'parcels': cfg['streets']['integratedParcels'],
        'typicalSection': sec,
        'widthCheck': {'section_m': sec['total_m'], 'measured_m': r3(width_meas), 'deviation_m': r3(width_meas - sec['total_m'])},
        'gutter': [c for c in street_dwg['curbs'] if c['layer'] == 'HW-CURB-GUTR'],
        'edgeStones': [c for c in street_dwg['curbs'] if c['layer'] in ('HW-CURB-BRDR', 'HW-CURB-IN')],
        'islands': street_dwg['islands'],
        'linesSource': street_dwg['source'],
        'materials': manual['streetMaterials'],
    },
    'otherSections': manual['otherSections'],
})

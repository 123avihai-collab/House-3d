#!/usr/bin/env python3
"""
Sheet 04 of the B1 building plan (scanned): planned building, parking structure and main entrance of every
neighbouring lot -> data/environment/sheet04.json

Georeference: the "מפלס כניסה קובעת" (±0.00) symbols are found in the scan by template matching and paired with
the same symbols in the vector heights plan (the CAD version of the same sheet, RAKAFOT00_1B_BINUY_04), whose ITM
positions come from tools/environment/extract_environment.py (data/environment/lots.json -> pm0Symbols).
An affine transform (scan pixels -> ITM) is fitted to the pairs; residuals are reported.
Then, inside each lot, the legend colours are segmented: white = building, purple = "מבנה חניה",
orange grid = "כניסה ראשית". Contours -> polygons in ITM.
Run after extract_environment.py:  python3 tools/environment/extract_sheet04.py   (needs pymupdf, opencv, shapely)
"""
import json, math, os
import numpy as np, cv2
import pymupdf as fitz
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = lambda *a: os.path.join(ROOT, *a)
SRC = 'sources/neighborhood/development-B1/תכנית בינוי גיליון 04 מתחם B1.pdf'
r3 = lambda v: round(float(v), 3)
cfg = json.load(open(P('data', 'environment', 'config.json'), encoding='utf-8'))['sheet04']
L = json.load(open(P('data', 'environment', 'lots.json'), encoding='utf-8'))
plot = json.load(open(P('data', 'site', 'plot-5187.json'), encoding='utf-8'))

# ---------- render the scan window ----------
Z = cfg['zoom']
x0, y0, x1, y1 = cfg['pdfClip']
page = fitz.open(P(SRC))[0]
pix = page.get_pixmap(clip=fitz.Rect(x0, y0, x1, y1), matrix=fitz.Matrix(Z, Z))
img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

# ---------- ±0.00 symbols in the scan ----------
tcx, tcy = (cfg['templateCentre_pt'][0] - x0) * Z, (cfg['templateCentre_pt'][1] - y0) * Z
R = cfg['templateHalf_px']
tb = (gray[int(tcy) - R:int(tcy) + R, int(tcx) - R:int(tcx) + R] < cfg['darkThreshold']).astype(np.float32)
res = cv2.matchTemplate((gray < cfg['darkThreshold']).astype(np.float32), tb, cv2.TM_CCOEFF_NORMED)
scan_sym = []
while True:
    _, mv, _, ml = cv2.minMaxLoc(res)
    if mv < cfg['matchMin']:
        break
    scan_sym.append((ml[0] + R, ml[1] + R)); cv2.circle(res, ml, 2 * R, -1, -1)
scan_sym = np.array(scan_sym, float)
itm_sym = np.array([(s['E'], s['N']) for s in L['pm0Symbols']])

# ---------- pairing: coarse search (rotation in 90° steps, reflection, scale) anchored on lot 5187 ----------
anchor_px = np.array([tcx, tcy])
a_itm = min(itm_sym, key=lambda q: math.dist(q, cfg['anchorITM']))
best = None
for refl in (1, -1):
    for rot in range(0, 360, 90):
        for sc in np.arange(*cfg['scaleSearch_m_per_px']):
            c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            d = (scan_sym - anchor_px) * [1, refl]
            pred = a_itm + sc * np.c_[c * d[:, 0] - s * d[:, 1], s * d[:, 0] + c * d[:, 1]]
            dist = np.min(np.linalg.norm(pred[:, None, :] - itm_sym[None, :, :], axis=2), axis=1)
            n = int((dist < 1.5).sum())
            if best is None or n > best[0]:
                best = (n, pred)
pred = best[1]


def affine_fit(A, B):
    M = np.c_[A, np.ones(len(A))]
    X, *_ = np.linalg.lstsq(M, B, rcond=None)
    return X, np.linalg.norm(M @ X - B, axis=1)


for tol in cfg['icpTolerances_m']:
    dist = np.linalg.norm(pred[:, None, :] - itm_sym[None, :, :], axis=2)
    j = dist.argmin(1); ok = dist[np.arange(len(j)), j] < tol
    X, res_a = affine_fit(scan_sym[ok], itm_sym[j[ok]])
    pred = np.c_[scan_sym, np.ones(len(scan_sym))] @ X
to_itm = lambda pts: np.c_[pts, np.ones(len(pts))] @ X
Xinv = np.linalg.inv(np.r_[X.T, [[0, 0, 1]]])
to_px = lambda pts: (np.c_[pts, np.ones(len(pts))] @ Xinv.T)[:, :2]
sx = math.hypot(X[0, 0], X[0, 1]); sy = math.hypot(X[1, 0], X[1, 1])
georef = {'method': 'affine (scan px -> ITM) fitted to ±0.00 symbols matched against the vector heights plan',
          'pairs': int(ok.sum()), 'symbolsInScan': len(scan_sym),
          'scale_m_per_px': [round(sx, 5), round(sy, 5)], 'scaleDifference_pct': round(abs(sx - sy) / sx * 100, 2),
          'medianResidual_m': r3(np.median(res_a)), 'maxResidual_m': r3(res_a.max()),
          'note': 'scanned paper print: positions from this sheet carry the residual above + ~1 px (≈0.05 m) of the scan'}
print('sheet 04 georef', georef)

# ---------- colour classes (legend of sheet 04) ----------
blur = cv2.blur(img, (cfg['blur_px'], cfg['blur_px'])).astype(int)
Rc, Gc, Bc = blur[:, :, 0], blur[:, :, 1], blur[:, :, 2]
C = cfg['colours']
# the private yard is a dotted texture ("שטח חצר פרטית"); the building is the dot-free area of the lot
dark = (img.min(2) < C['dotDarkMax']).astype(np.uint8)
_n, _lab, _st, _ = cv2.connectedComponentsWithStats(dark, 8)
_a, _side = _st[:, 4], np.maximum(_st[:, 2], _st[:, 3])
_isdot = (_a >= C['dotArea_px'][0]) & (_a <= C['dotArea_px'][1]) & (_side <= C['dotMaxSide_px']); _isdot[0] = False
dots = cv2.blur(_isdot[_lab].astype(np.float32), (C['dotWindow_px'], C['dotWindow_px']))  # density of yard dots only (not lines/text)
parking = (Bc - Gc > C['purpleBminusG']) & (Rc - Gc > C['purpleRminusG'])
entrance = (Rc > C['orangeRmin']) & (Rc - Bc > C['orangeRminusB']) & (Gc - Bc > C['orangeGminusB'])
masks = {'building': (dots < C['dotDensityMax']) & ~parking & ~entrance, 'parking': parking, 'entrance': entrance}
px_per_m = 1 / ((sx + sy) / 2)


def polys_of(mask, lotpoly_px, min_m2, close_m, open_m):
    m = np.zeros(mask.shape, np.uint8)
    cv2.fillPoly(m, [np.round(lotpoly_px).astype(np.int32)], 1)
    mm = (mask & (m > 0)).astype(np.uint8) * 255
    kc = max(3, int(round(close_m * px_per_m)) | 1); ko = max(3, int(round(open_m * px_per_m)) | 1)
    mm = cv2.morphologyEx(mm, cv2.MORPH_CLOSE, np.ones((kc, kc), np.uint8))
    mm = cv2.morphologyEx(mm, cv2.MORPH_OPEN, np.ones((ko, ko), np.uint8))
    cnts, _ = cv2.findContours(mm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        c = cv2.approxPolyDP(c, cfg['simplify_m'] * px_per_m, True)[:, 0, :]
        if len(c) < 3:
            continue
        pg = Polygon(to_itm(c.astype(float))).buffer(0)
        if pg.area >= min_m2:
            out.append(pg)
    return out


def ring(pg):
    pg = pg if pg.geom_type == 'Polygon' else max(pg.geoms, key=lambda g: g.area)
    return [[r3(x), r3(y)] for x, y in list(pg.exterior.coords)[:-1]]


lots_out = []
targets = [(l['parcel'], l['lot'], l['ring'], l['edges'], l['envelope']['ring']) for l in L['lots']] + [('257', '5187', plot['ring'], None, None)]
for parcel, lot, lr, edges, env_ring in targets:
    lp = Polygon(lr)
    lpx = {k: to_px(np.array(lp.buffer(-d).exterior.coords)) for k, d in cfg['lotInset_m'].items()}
    M = cfg['morph_m']
    b = polys_of(masks['building'], lpx['building'], cfg['minArea_m2']['building'], *M['building'])
    pk = polys_of(masks['parking'], lpx['parking'], cfg['minArea_m2']['parking'], *M['parking'])
    en = polys_of(masks['entrance'], lpx['entrance'], cfg['minArea_m2']['entrance'], *M['entrance'])
    bu = unary_union(b).buffer(cfg['mergeGap_m'], join_style='mitre').buffer(-cfg['mergeGap_m'], join_style='mitre') if b else None
    if bu is not None and (pk or en):  # the building never overlaps its parking structure / entrance
        bu = bu.difference(unary_union(pk + en).buffer(cfg['separation_m']))
        bu = bu.buffer(-cfg['minWidth_m'] / 2, join_style='mitre').buffer(cfg['minWidth_m'] / 2, join_style='mitre')
        bu = None if bu.is_empty else bu
    clipped = None
    if bu is not None and env_ring and cfg.get('clipToBuildingLines', {}).get('use'):
        before = bu
        bu = bu.intersection(Polygon(env_ring))
        bu = None if bu.is_empty else (max(bu.geoms, key=lambda g: g.area) if bu.geom_type != 'Polygon' else bu)
        clipped = {'removed_m2': r3(before.area - (bu.area if bu else 0)), 'maxBeyondLine_m': r3(max(Polygon(env_ring).exterior.distance(Point(c)) for c in before.exterior.coords if not Polygon(env_ring).contains(Point(c))) if not Polygon(env_ring).contains(before) else 0)}
    rec = {'parcel': parcel, 'lot': lot, 'clippedToBuildingLines': clipped,
           'building': [ring(g) for g in (bu.geoms if bu is not None and bu.geom_type == 'MultiPolygon' else [bu] if bu else [])],
           'parking': [ring(g) for g in pk], 'entrance': [ring(g) for g in en]}
    rec['buildingArea_m2'] = r3(bu.area) if bu else 0
    rec['parkingArea_m2'] = r3(sum(g.area for g in pk))
    # front = the street piece of the lot closest to the entrance (or the parking if no entrance was found)
    ref = unary_union(en or pk)
    if edges and not ref.is_empty:
        st = [(i, e) for i, e in enumerate(edges) if e['across'].startswith('רחוב')]
        i, f = min(st, key=lambda ie: LineString(ie[1]['pts']).distance(ref))
        rec['entranceFrom'] = {'edgeIndex': i, 'across': f['across'], 'by': 'entrance' if en else 'parking',
                               'distance_m': r3(LineString(f['pts']).distance(ref))}
    # distances of the drawn building from each lot edge (vs the setbacks of TAMAL/1016)
    if edges and bu:
        rec['buildingToEdgesBeforeClip'] = [{'across': e['across'], 'setback_m': e['setback_m'], 'drawn_m': r3(LineString(e['pts']).distance(before if clipped else bu))} for e in edges] if clipped else None
        rec['buildingToEdges'] = [{'across': e['across'], 'setback_m': e['setback_m'], 'drawn_m': r3(LineString(e['pts']).distance(bu))} for e in edges]
    if parcel != '257' and bu:
        rec['buildingTo5187_m'] = r3(bu.distance(Polygon(plot['ring'])))
    lots_out.append(rec)
    print(lot, parcel, 'building', rec['buildingArea_m2'], 'parking', rec['parkingArea_m2'], 'entr', len(en), rec.get('entranceFrom', {}).get('across'))

# debug overlay
vis = img[:, :, ::-1].copy()
for r in lots_out:
    for k, col in (('building', (0, 0, 255)), ('parking', (255, 0, 160)), ('entrance', (0, 160, 255))):
        for g in r[k]:
            cv2.polylines(vis, [np.round(to_px(np.array(g))).astype(np.int32)], True, col, 3)
for q in itm_sym:
    cv2.circle(vis, tuple(np.round(to_px(np.array([q]))[0]).astype(int)), 10, (0, 200, 0), 3)
os.makedirs(P('tools', 'cache'), exist_ok=True)
cv2.imwrite(P('tools', 'cache', 'sheet04-overlay.jpg'), vis, [cv2.IMWRITE_JPEG_QUALITY, 80])

json.dump({'_doc': 'Planned building / parking structure / main entrance per lot, from the scanned building plan sheet 04 (B1, 25.10.2022). '
                   'Generated by tools/environment/extract_sheet04.py – do not edit.',
           'source': SRC, 'georeference': georef,
           'legend': {'building': 'לבן – מבנה', 'parking': 'סגול – "מבנה חניה"', 'entrance': 'כתום משובץ – "כניסה ראשית"'},
           'lots': lots_out},
          open(P('data', 'environment', 'sheet04.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('wrote data/environment/sheet04.json')

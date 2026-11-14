#!/usr/bin/env python3
"""Street in front of lot 5187 (רחוב משולב 960) – the strip between the lot front and the far side of the street,
along the frontage drawn in the front-wall elevation.

Sources (CLAUDE.md §1 – DWG first, scaled PDF second):
  * sources/survey/INDEX_F02628-36-MIG-5187.dwg (via data/site/street.json, planned-heights.json, parcels.json):
    edge line on the lot front (HW-CURB-BRDR), drainage channel (HW-CURB-GUTR, 3 lines), planting islands
    (HW-CURB-ILND, closed rings from data/environment/details.json), planned street contours + spot levels.
  * sources/architecture/חומה קדמית+ חומה אחורית - מבט על קנמ 1-10.pdf, upper view (front wall, seen from the street):
    dimension chain 1361 | 120 | 101 | 600 | 139, level marks "מפלס הרחוב ע"פ המשתכן" and the street ground line.
    Scale 1:100 verified against the chain (each segment), level scale against the 5 written levels.
  * sources/development/תוכנית נוף.pdf (data/environment/manual-readings.json): typical section 2.0 | 4.5 | 5.0 | 1.5,
    cross slope 1.5 %.
  * נספח פרטי פיתוח 003 פרט 14 / פרט 10 (data/environment/manual-readings.json): materials only.

Output: data/site/front-street.json. Re-runnable: python3 tools/extract_front_street.py
"""
import json, math, os
import numpy as np
import pymupdf
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.ops import unary_union, linemerge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
r3 = lambda v: round(float(v), 3)
ELEV_PDF = 'sources/architecture/חומה קדמית+ חומה אחורית - מבט על קנמ 1-10.pdf'
DWG = 'sources/survey/INDEX_F02628-36-MIG-5187.dwg'

street = J('data/site/street.json')
heights = J('data/site/planned-heights.json')
plot = J('data/site/plot-5187.json')
parcels = {p['parcel']: p for p in J('data/site/parcels.json')['parcels']}
pillar = J('data/structure/stairs.json')['pillar']
env = J('data/environment/streets.json')
details = J('data/environment/details.json')
readings = J('data/environment/manual-readings.json')

P2457 = (plot['points']['2457']['E'], plot['points']['2457']['N'])
P2420 = (plot['points']['2420']['E'], plot['points']['2420']['N'])

# ---------------------------------------------------------------- front line (DWG edge line on the lot fronts)
brdr = [c for c in street['curbs'] if c['layer'] == 'HW-CURB-BRDR']
front = linemerge([LineString(c['points']) for c in brdr if c['points'][0] in ([179575.354, 576240.657], [179610.59, 576224.606])])
assert front.geom_type == 'LineString', front.geom_type
if front.coords[0][0] > front.coords[-1][0]: front = LineString(front.coords[::-1])   # west -> east
s2457 = front.project(Point(P2457))
chk_2457 = front.distance(Point(P2457)); chk_2420 = front.distance(Point(P2420))
arc = front.project(Point(P2420)) - s2457
S = lambda s: front.interpolate(s2457 + s)                     # point on the front line, s = metres from 2457 (east +)

def normal(s):                                               # unit normal toward the street (south-west)
    a, b = S(s - 0.25), S(s + 0.25); tx, ty = b.x - a.x, b.y - a.y; L = math.hypot(tx, ty)
    return (ty / L, -tx / L)                                 # right of west->east = street side

# ---------------------------------------------------------------- elevation (PDF)
doc = pymupdf.open(os.path.join(ROOT, ELEV_PDF)); pg = doc[0]
drw = pg.get_drawings()
# dimension chain: vertical tick lines y 150..161 in the upper view
ticks = sorted({round(d['rect'].x0, 2) for d in drw if d['rect'].width < 0.01 and 150 <= d['rect'].y0 <= 151
                and 160 <= d['rect'].y1 <= 162 and 230 < d['rect'].x0 < 1000})
chain_cm = [1361, 120, 101, 600, 139]
assert len(ticks) == 6, ticks
seg_scale = [(ticks[i + 1] - ticks[i]) / (chain_cm[i] / 100) for i in range(5)]
PT_M = 72 / 25.4 * 1000 / 100                                 # 1:100 -> 28.3465 pt per metre
X0 = ticks[0]
# level marks: filled triangles (apex = the level), with the written value next to them
words = pg.get_text('words')
tri = []
for d in drw:
    r = d['rect']
    if d.get('fill') is None or not (4 < r.width < 20 and 3 < r.height < 15 and 180 <= r.y0 <= 300): continue
    pts = [it[1] for it in d['items'] if it[0] == 'l']
    if len(pts) != 3: continue
    ys = sorted(p.y for p in pts)
    down = abs(ys[0] - ys[1]) < 0.05                          # two points on top -> apex below
    apex = max(pts, key=lambda p: p.y) if down else min(pts, key=lambda p: p.y)
    tri.append((apex.x, apex.y, r))
def label_of(t):
    x, y, r = t; best = None
    for w in words:
        try: v = float(w[4])
        except ValueError: continue
        if not (270 < v < 290): continue
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        dd = math.hypot(cx - x, cy - (r.y0 + r.y1) / 2)
        if dd < 22 and (best is None or dd < best[0]): best = (dd, v)
    return best[1] if best else None
marks = [(x, y, label_of((x, y, r))) for x, y, r in tri]
STREET_LEVELS = (279.35, 279.39, 279.79, 280.00, 280.01)       # "מפלס הרחוב ע"פ המשתכן" + the gate-front mark (outside ground line)
street_marks = sorted([m for m in marks if m[2] in STREET_LEVELS], key=lambda m: m[0])
assert [m[2] for m in street_marks] == list(STREET_LEVELS), street_marks
A = np.array([[m[1], 1.0] for m in street_marks]); bv = np.array([m[2] for m in street_marks])
(ky, k0), *_ = np.linalg.lstsq(A, bv, rcond=None)
H_of_y = lambda y: ky * y + k0
v_scale = -1 / ky
# street ground line: thin (0.12) connected polyline in the upper view, x 235..962
segs = []
for d in drw:
    if abs((d.get('width') or 0) - 0.12) > 0.01: continue
    for it in d['items']:
        if it[0] != 'l': continue
        a, b = it[1], it[2]
        if a.x > b.x: a, b = b, a
        if 258 <= min(a.y, b.y) <= 285 and 230 < a.x < 965 and b.x - a.x > 2 and abs(b.y - a.y) < 0.2 * (b.x - a.x):
            segs.append((a.x, a.y, b.x, b.y))
segs = sorted(set(segs))
def follow(x, y):
    pts = [(x, y)]
    while True:
        nx = [s for s in segs if abs(s[0] - x) < 0.05 and abs(s[1] - y) < 0.05]
        if not nx: return pts
        s = max(nx, key=lambda s: s[2]); x, y = s[2], s[3]; pts.append((x, y))
west = [s for s in segs if abs(s[1] - 283.88) < 0.02 and s[0] < 240]          # flat part in front of the pillar (279.35)
main = follow(327.32, 283.4)                                                    # rising part, from the wall to the parking / east pillar
assert west and len(main) > 50, (west, len(main))
prof_pts = [(west[0][0], west[0][1]), (west[0][2], west[0][3])] + main
# chain origin on the plan: the west face of the systems pillar (chain 1361 starts at it, see the elevation)
pil_s = []
for w in pillar['wallsITM']:
    for p in w:
        P = Point(p); s = front.project(P) - s2457
        if front.project(P) <= 1e-9:                       # west of the line start: along the tangent
            a, b = S(0), S(0.5); tx, ty = (b.x - a.x) / 0.5, (b.y - a.y) / 0.5
            s = (p[0] - a.x) * tx + (p[1] - a.y) * ty
        pil_s.append(s)
C0 = min(pil_s)                                             # s of the chain origin
chain_end_s = C0 + sum(chain_cm) / 100
s_of_x = lambda x: C0 + (x - X0) / PT_M

# ---------------------------------------------------------------- DWG heights along the front line (linear TIN, as the model)
ctrl = [(x, y, c['z']) for c in street['contours'] for x, y in c['points']] + [(h['at'][0], h['at'][1], h['z']) for h in heights['streetSpots']]
from scipy.interpolate import LinearNDInterpolator
tin = LinearNDInterpolator(np.array([(x, y) for x, y, _ in ctrl]), np.array([z for *_, z in ctrl]))
def dwgH(s, d=0.0):
    p = S(s); n = normal(s); v = tin(p.x + n[0] * d, p.y + n[1] * d)
    return None if np.isnan(v) else float(v)
# contour crossings of the front line (exact DWG values on the line)
crossings = []
for c in street['contours']:
    L = LineString(c['points'])
    if L.distance(front) < 0.01:
        for end in (Point(c['points'][0]), Point(c['points'][-1])):
            if end.distance(front) < 0.01: crossings.append({'z': c['z'], 's': r3(front.project(end) - s2457)})

profile = [{'s': r3(s_of_x(x)), 'chain': r3((x - X0) / PT_M), 'H': r3(H_of_y(y))} for x, y in prof_pts]
for p in profile:
    z = dwgH(p['s']); p['dwg'] = r3(z) if z is not None else None
    p['diff'] = r3(p['H'] - z) if z is not None else None
level_marks = []
for x, y, v in street_marks:
    s = s_of_x(x); z = dwgH(s)
    lot = v == 280.00   # marker points up from below the parking floor line (thick, 280.00 = "(280.00) לפי המשתכן" – lot level at the front)
    level_marks.append({'label': f'{v:.2f}', 'H': v, 's': r3(s), 'chain': r3((x - X0) / PT_M), 'kind': 'lotFront' if lot else 'street',
                        'dwg': r3(z) if z is not None else None, 'diff': None if lot else (r3(v - z) if z is not None else None),
                        **({'note': 'מפלס רצפת החניה / המגרש בחזית (בתוכנית: "(280.00) לפי המשתכן") – לא מפלס הרחוב'} if lot else {})})
inner_marks = [{'label': f'{v:.2f}', 'H': v, 's': r3(s_of_x(x)), 'chain': r3((x - X0) / PT_M)} for x, y, v in marks if v in (280.24, 280.16)]

# ---------------------------------------------------------------- strip of street in front of the lot
s0, s1 = r3(profile[0]['s']), r3(profile[-1]['s'])          # extent of the elevation's street line
FAR = 20.0
def cut(s):
    p = S(s); n = normal(s); return [(p.x - n[0] * 0.5, p.y - n[1] * 0.5), (p.x + n[0] * FAR, p.y + n[1] * FAR)]
ns = np.linspace(s0, s1, 60)
line_pts = [(S(s).x, S(s).y) for s in ns]
far_pts = [(S(s).x + normal(s)[0] * FAR, S(s).y + normal(s)[1] * FAR) for s in ns]
band_all = Polygon(line_pts + far_pts[::-1])
public = unary_union([Polygon(parcels[k]['ring']).buffer(0) for k in ('9', '20/28', '11', '21') if k in parcels])
strip = band_all.intersection(public)
if strip.geom_type == 'MultiPolygon': strip = max(strip.geoms, key=lambda g: g.area)
frame = Polygon(street['frameITM'] if 'frameITM' in street else env['frameITM'])

def offset_band(d0, d1):
    """part of the strip between distances d0..d1 from the front line (along the normals)"""
    a = [(S(s).x + normal(s)[0] * d0, S(s).y + normal(s)[1] * d0) for s in ns]
    b = [(S(s).x + normal(s)[0] * d1, S(s).y + normal(s)[1] * d1) for s in ns]
    return Polygon(a + b[::-1]).buffer(0).intersection(strip)

# street width across (lot line -> far parcel edge), measured along the normal at a few stations
def width_at(s):
    p = S(s); n = normal(s); L = LineString([(p.x, p.y), (p.x + n[0] * FAR, p.y + n[1] * FAR)])
    X = L.intersection(strip.exterior)
    pts = [X] if X.geom_type == 'Point' else [g for g in getattr(X, 'geoms', []) if g.geom_type == 'Point']
    return max(Point(p.x, p.y).distance(q) for q in pts) if pts else None
widths = [r3(width_at(s)) for s in np.linspace(s0 + 0.5, s1 - 0.5, 7)]
W = float(np.median(widths))
# drainage channel: the 3 DWG lines (two edges + centre), offsets from the front line
gut = [LineString(c['points']) for c in street['curbs'] if c['layer'] == 'HW-CURB-GUTR']
def dist_along_normal(L, s):
    p = S(s); n = normal(s); R = LineString([(p.x, p.y), (p.x + n[0] * FAR, p.y + n[1] * FAR)]); X = R.intersection(L)
    return Point(p.x, p.y).distance(X) if X.geom_type == 'Point' else None
g_off = sorted([[dist_along_normal(L, s) for s in np.linspace(s0 + 0.5, min(s1, 20.0), 7)] for L in gut], key=lambda v: v[0] or 0)
g_med = [float(np.median([v for v in g if v is not None])) for g in g_off]
g_in, g_mid, g_out = g_med[0], g_med[1], g_med[2]
# channel polygon between the two edge lines (inner / outer by offset from the front line)
med_off = lambda L: float(np.median([v for v in [dist_along_normal(L, s) for s in np.linspace(s0 + 0.5, min(s1, 20.0), 7)] if v is not None]))
gs = sorted(gut, key=med_off)
ein, eout = gs[0], gs[2]
ec = list(ein.coords); oc = list(eout.coords)
if math.dist(ec[0], oc[0]) > math.dist(ec[0], oc[-1]): oc = oc[::-1]
gutter_poly = Polygon(ec + oc[::-1]).buffer(0).intersection(strip)

sec = readings['integratedStreetSection']
zones_def = [  # lot side -> far side; widths from the typical section, the channel from the DWG
    ('walkNear', 'שביל (צד המגרש)', 0.0, sec['zones'][0]['width_m'], 'envFsWalk'),
    ('lane', 'מיסעה / הולכי רגל – נתיב נסיעה', sec['zones'][0]['width_m'], g_in, 'envFsLane'),
    ('zoneFar', 'חניה / אזור שתילה / מיתון', g_out, sec['zones'][0]['width_m'] + sec['zones'][1]['width_m'] + sec['zones'][2]['width_m'], 'envFsWalk'),
    ('walkFar', 'שביל (צד נגדי)', sec['zones'][0]['width_m'] + sec['zones'][1]['width_m'] + sec['zones'][2]['width_m'], W + 0.5, 'envFsWalk'),
]
islands = []
for b in details['bays']:
    if b.get('kind') != 'island' or 'HW-CURB-ILND' not in (b.get('source') or ''): continue
    g = Polygon(b['ring']).buffer(0)
    if g.intersection(strip).area > 0.5:
        islands.append(g.intersection(strip))
isl_u = unary_union(islands) if islands else Polygon()

def rings(g):
    gs = [g] if g.geom_type == 'Polygon' else [x for x in getattr(g, 'geoms', []) if x.geom_type == 'Polygon']
    return [[[r3(x), r3(y)] for x, y in list(p.exterior.coords)[:-1]] for p in gs if p.area > 0.02]
def split(g):
    """parts inside the buyer-map frame (DWG heights) and outside it (derived, provisional)"""
    return [('source', rings(g.intersection(frame))), ('derived', rings(g.difference(frame)))]

zones = []
for zid, label, d0, d1, mat in zones_def:
    g = offset_band(d0, d1).difference(gutter_poly).difference(isl_u)
    for hs, rr in split(g):
        for r in rr:
            zones.append({'id': f'{zid}-{len(zones)}', 'zone': zid, 'label': label, 'from_m': r3(d0), 'to_m': r3(min(d1, W)), 'material': mat,
                          'ring': r, 'area_m2': r3(Polygon(r).area), 'heights': hs,
                          **({'heightStatus': 'provisional'} if hs == 'derived' else {}),
                          'source': f'{DWG} (רצועה בין קו המגרש לקו המגרש שממול – parcels.json; תעלה HW-CURB-GUTR; איים HW-CURB-ILND); רוחבי האזורים: {sec["source"]}'})
gutter = [{'ring': r, 'heights': hs, **({'heightStatus': 'provisional'} if hs == 'derived' else {})} for hs, rr in split(gutter_poly) for r in rr]
isl_out = [{'ring': r, 'heights': hs, **({'heightStatus': 'provisional'} if hs == 'derived' else {})} for hs, rr in split(isl_u) for r in rr]

# edge stone 'רמות' on the lot line (street side), along the strip
EDGE_W = 0.125
edge = [[r3(S(s).x), r3(S(s).y)] for s in np.linspace(s0, s1, 40)]

# cross slope from the DWG: lot line -> channel centre, at the stations of the width check
slopes = []
for s in np.linspace(s0 + 1.0, s1 - 1.0, 6):
    z0, z1 = dwgH(s, 0.05), dwgH(s, g_mid)
    if z0 is not None and z1 is not None: slopes.append({'s': r3(s), 'zLot': r3(z0), 'zChannel': r3(z1), 'slope_pct': r3((z0 - z1) / g_mid * 100)})
far_slopes = []
for s in np.linspace(s0 + 1.0, s1 - 1.0, 6):
    z0, z1 = dwgH(s, 12.0), dwgH(s, g_mid)
    if z0 is not None and z1 is not None: far_slopes.append({'s': r3(s), 'zFar': r3(z0), 'zChannel': r3(z1), 'd_m': 12.0, 'slope_pct': r3((z0 - z1) / (12.0 - g_mid) * 100)})

diffs = [p['diff'] for p in profile if p['diff'] is not None]
out = {
    '_doc': 'Street in front of lot 5187 (רחוב משולב 960), along the frontage of the front-wall elevation. Generated by tools/extract_front_street.py – do not edit.',
    'source': f'{DWG} (data/site/street.json, planned-heights.json, parcels.json); {ELEV_PDF} (חזית עליונה – חומה קדמית, מבט מהרחוב); {sec["source"]}',
    'frontLine': {'points': [[r3(x), r3(y)] for x, y in front.coords], 'origin': '2457', 's2457_on_line': r3(s2457),
                  'check': {'dist2457_m': r3(chk_2457), 'dist2420_m': r3(chk_2420), 'arc2457_2420_m': r3(arc)},
                  'source': f'{DWG} layer HW-CURB-BRDR (קו אבן הגן על חזיתות המגרשים, west→east)'},
    'extent': {'s0': s0, 's1': s1, 'why': 'קצות קו הרחוב בחזית (מעט מערבית לפילר עד מעט מזרחית לפינה 2420)'},
    'elevation': {
        'source': ELEV_PDF, 'view': 'חזית עליונה – החומה הקדמית, מבט מהרחוב, משמאל מערב',
        'chainTicks_pt': ticks, 'chain_cm': chain_cm, 'segmentScale_pt_per_m': [r3(v) for v in seg_scale], 'nominal_pt_per_m': r3(PT_M),
        'scaleCheck': f'1:100 – כל 5 מקטעי השרשרת: {min(seg_scale):.2f}–{max(seg_scale):.2f} נק\'/מ\' (נומינלי {PT_M:.2f}, סטייה עד {max(abs(v / PT_M - 1) for v in seg_scale) * 100:.2f}%)',
        'levelScale_pt_per_m': r3(v_scale), 'levelFitResidual_m': max(r3(abs(H_of_y(m[1]) - m[2])) for m in street_marks),
        'chainOrigin': {'s': r3(C0), 'rule': 'השרשרת 1361 מתחילה בדופן המערבית של פילר המערכות (data/structure/stairs.json PIL1)',
                        'endCheck': {'chainEnd_s': r3(chain_end_s), 'corner2420_s': r3(arc), 'deviation_m': r3(chain_end_s - arc)}},
        'chain': [{'cm': c, 's0': r3(C0 + sum(chain_cm[:i]) / 100), 's1': r3(C0 + sum(chain_cm[:i + 1]) / 100),
                   'label': ['חומה בנויה + גדר קלה', 'שער כניסה', '', 'חניה', ''][i]} for i, c in enumerate(chain_cm)],
        'levelMarks': level_marks, 'innerMarks': inner_marks,
    },
    'profile': {'points': profile, 'status': 'reference',
                'note': 'קו פני הרחוב כפי שצויר בחזית. המודל בונה את הרחוב לפי המפה למשתכן (DWG, עדיפות 1); הקו מוצג להשוואה',
                'maxDiff_m': r3(max(diffs, key=abs)), 'meanDiff_m': r3(np.mean(diffs))},
    'dwgOnFrontLine': {'contourCrossings': sorted(crossings, key=lambda c: c['s']),
                       'spots': [{'z': h['z'], 's': r3(front.project(Point(h['at'])) - s2457), 'offset_m': r3(front.distance(Point(h['at'])))} for h in heights['streetSpots']],
                       'source': f'{DWG} קווי גובה מתוכננים + "גובה מתוכנן מדרכה"'},
    'section': {'name': sec['name'], 'zones': sec['zones'], 'total_m': sec['total_m'], 'crossSlope': sec['crossSlope'], 'source': sec['source'],
                'measuredWidth_m': r3(W), 'widths_m': widths,
                'channel': {'inner_m': r3(g_in), 'centre_m': r3(g_mid), 'outer_m': r3(g_out), 'width_m': r3(g_out - g_in),
                            'sectionCentre_m': sec['zones'][0]['width_m'] + sec['zones'][1]['width_m'],
                            'source': f'{DWG} layer HW-CURB-GUTR (3 קווים: שתי שפות + מרכז)'},
                'crossSlopeDWG': slopes, 'crossSlopeDWGFar': far_slopes},
    'outline': rings(strip)[0],
    'outlineArea_m2': r3(strip.area),
    # owner decision (Avihai 14.11.2026): the street follows the architect's line (front-wall elevation) on the lot line;
    # the correction (elevation − DWG) fades linearly to 0 at the far lot line, so the opposite side stays on the DWG levels
    'ownerLevels': {'status': 'owner', 'decision': 'החלטת אביחי 14.11.2026: הרחוב לפי קו הרחוב בחזית החומה הקדמית (אדריכל). לבדיקה מול האדריכל – open-issues FS1',
                    'taper': 'התיקון (חזית − DWG) מלא בקו המגרש ויורד ליניארית ל-0 בקו המגרשים שממול',
                    'taperWidth_m': r3(W),
                    'points': [{'s': p['s'], 'delta': p['diff']} for p in profile if p['diff'] is not None]},
    'zones': zones,
    'gutter': gutter,
    'islands': isl_out,
    'edgeStone': {'line': edge, 'width_m': EDGE_W, 'height_m': 0.1875, 'reveal_m': 0.0, 'side': 'street',
                  'status': 'provisional', 'product': 'אבן גן "רמות" אפור 12.5/18.75/50',
                  'why': 'נספח 003 פרט 14 / פרט 10: "אבן גן מפרידה בין המדרכה למגרש – רמות 12.5/18.75/50". הבליטה מעל הריצוף והצד ביחס לקו המגרש לא כתובים – שורטט בצד הרחוב, במפלס הריצוף (open-issues FS2)'},
    'displayAngle_deg': r3(math.degrees(math.atan2(S(s1).y - S(s0).y, S(s1).x - S(s0).x))),
    'materials': {'street': readings['streetMaterials']['paving'], 'edge': readings['streetMaterials']['edgeAtLot'], 'gutter': readings['streetMaterials']['gutter'],
                  'source': readings['streetMaterials']['source']},
}
json.dump(out, open(os.path.join(ROOT, 'data/site/front-street.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"front line: 2457 {chk_2457:.4f} / 2420 {chk_2420:.4f} m off; arc {arc:.3f}")
print('scale', [round(v, 2) for v in seg_scale], 'levels', round(v_scale, 2), 'chain end dev', round(chain_end_s - arc, 3))
print('width', W, widths, 'channel', round(g_in, 3), round(g_mid, 3), round(g_out, 3))
print('profile vs DWG: max', out['profile']['maxDiff_m'], 'mean', out['profile']['meanDiff_m'])
for m in level_marks: print(' mark', m)
print('crossings', out['dwgOnFrontLine']['contourCrossings'])
print('slopes', [s['slope_pct'] for s in slopes], 'far', [s['slope_pct'] for s in far_slopes])
print('zones', len(zones), [(z['zone'], z['heights'], z['area_m2']) for z in zones], 'gutter', len(gutter), 'islands', len(isl_out))

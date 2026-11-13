#!/usr/bin/env python3
"""Stairs + the utilities pillar (garbage room / electric cabinet) -> data/structure/stairs.json

Sources (no stair is drawn in the structural sheets – K-21 / K-31 only show the shaft as an opening):
  * sources/architecture/קומה מרתף - מבט על …pdf        basement plan 1:100: the concrete stair basement -> ground (risers 1-15)
                                                         and the outside stair down to the unit (1-14)
  * sources/architecture/קומה קרקע- פיתוח היקפי …pdf    ground plan 1:100: the light stair ground -> first floor (16-37),
                                                         the lower flight 9-15 (cut, solid) as a cross-check, the utilities pillar
  * sources/architecture/חתך א-א …pdf                   section: levels (−2.60 / 0 / +3.85), riser numbering, concrete vs light,
                                                         waist / landing thickness of the concrete stair
  * sources/architecture/חומה קדמית+ חומה אחורית …pdf   front-wall elevation: pillar height 240 from the street 279.35
Placement: each architectural sheet is placed on the K-400 sheet by ICP (translation only, scale ×2 = 1:100 -> 1:50, checked)
against the k-21 / k-11 wall line work, then the stage-2 chain K-400 -> ITM.
Run: python3 tools/extract_stairs.py
"""
import json, math, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pymupdf
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union, polygonize
import extract_framing as F
import extract_floor as X

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GA = 'sources/architecture/קומה קרקע- פיתוח היקפי - מבט על קנמ 1-10.pdf'
BA = 'sources/architecture/קומה מרתף - מבט על קנמ 1-10.pdf'
SEC = "sources/architecture/חתך א-א - חזית מערב - מטבח+קומה א' מזדרון - מבט על קנמ 1-10.pdf"
FRONT = 'sources/architecture/חומה קדמית+ חומה אחורית - מבט על קנמ 1-10.pdf'
H0 = json.load(open(os.path.join(ROOT, 'data/site/origin.json'), encoding='utf-8'))['H0']
r3 = lambda v: round(float(v), 3)
PT_M = 72 / 2.54   # 1:100 -> 28.346 pt per metre on the architectural sheets

# ---- levels (finished, absolute -> relative to ±0.00 = H0) ----
LV = {
    'basement': (277.90, f'{BA}: "2.60- / 277.90" (מרתף שירות); {SEC}: "-260 מרתף"'),
    'ground': (H0, f'{SEC}: "0 קומת קרקע" = 280.50'),
    'first': (H0 + 3.85, f'{SEC}: "385 קומה א\'"'),
    'outBottom': (277.88, f'{BA}: "2.62- / 277.88" (משטח הכניסה ליחידה)'),
    'outTop': (280.31, f'{GA}: "280.31" (שביל דרומי בראש המדרגות)'),
    'pillarBase': (279.35, f'{FRONT}: "279.35 מפלס הרחוב"'),
    'pillarTop': (279.35 + 2.40, f'{FRONT}: "240" מעל 279.35 (= 281.75, כמו "גדר קלה 281.75")'),
}
rel = {k: r3(v[0] - H0) for k, v in LV.items()}


def place(pdf, dxf, clip):
    """ICP of the architectural sheet (×2) on the K-400 sheet against the structural DXF wall lines; scale re-fitted as a check"""
    t, sheet, to = X.placement()
    m = F.read_dxf(dxf)
    B = np.unique(np.round(np.array([sheet(e.dxf.start.x, e.dxf.start.y) for e in m.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcColumn')] +
                                    [sheet(e.dxf.end.x, e.dxf.end.y) for e in m.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcColumn')]), 2), axis=0)
    A = F.pdf_endpoints(pdf, clip) * 2
    score, tr, med = F.icp(A, B)
    d, i = cKDTree(B).query(A + tr); mm = d < 0.6
    P, Q = A[mm] - A[mm].mean(0), B[i[mm]] - B[i[mm]].mean(0)
    scale = float((P * Q).sum() / (P * P).sum())
    f = lambda x, y: F.sheet2itm(x * 2 + tr[0], y * 2 + tr[1])
    return f, {'translation_pt': [r3(v) for v in tr], 'matchedPoints': int(mm.sum()), 'scaleCheck': round(scale, 5),
               'medianResidual_mm': r3(med / F.PT * 1000)}


def hlines(pdf, x0, x1, y0, y1, mode, keep_near=False):
    """y of the horizontal lines across a flight window. mode 'solid' = one segment over ≥90 % of the width,
    'dashed' = ≥3 dashes over ≥65 %. Long reference lines (> 2.2 × width) are skipped. Double lines (nosing) -> first."""
    p = pymupdf.open(os.path.join(ROOT, pdf))[0]; rows = defaultdict(list)
    for d in p.get_drawings():
        if (d.get('width') or 0) > 0.2: continue          # tread lines are thin (0.12); edges / walls are heavier
        for it in d['items']:
            if it[0] != 'l': continue
            a, b = it[1], it[2]
            if abs(a.y - b.y) > 0.05 or not (y0 <= a.y <= y1) or abs(a.x - b.x) > 2.2 * (x1 - x0): continue
            lo, hi = max(min(a.x, b.x), x0), min(max(a.x, b.x), x1)
            if hi - lo > 0.3: rows[round(a.y, 2)].append((lo, hi))
    kind = {}
    for y, segs in sorted(rows.items()):
        segs = sorted(set(segs)); cov, cur = 0.0, None
        for lo, hi in segs:
            if cur is None or lo > cur[1]:
                cov += (cur[1] - cur[0]) if cur else 0; cur = [lo, hi]
            else: cur[1] = max(cur[1], hi)
        cov = (cov + cur[1] - cur[0]) / (x1 - x0); longest = max(hi - lo for lo, hi in segs) / (x1 - x0)
        kind[y] = 'solid' if longest >= 0.9 else ('dashed' if len(segs) >= 3 and cov >= 0.65 else None)
    solid = [y for y, k in kind.items() if k == 'solid']
    ys = []
    for y in sorted(kind):
        if kind[y] != mode: continue
        if mode == 'dashed' and not keep_near and any(abs(y - s) < 0.8 for s in solid): continue    # nosing double of a solid (cut) tread
        if not (ys and y - ys[-1] < 1.0): ys.append(y)
    return ys


def flight(f, x0, x1, ys, z0, rise, start, waist, sense):
    """a straight flight. ys = riser lines on the sheet (in climbing order), x0/x1 = its sides; z0 = level before the first riser.
    Profile in the vertical plane (s along the climb, z): treads + risers on top, soffit = line through the riser roots lowered by
    the waist (perpendicular). start: 'floor' (stands on a floor at z0) or 'landing' (springs from a landing slab)."""
    P0 = np.array(f(x0, ys[0])); P1 = np.array(f(x1, ys[0])); Pe = np.array(f(x0, ys[-1]))
    run = (Pe - P0) / np.linalg.norm(Pe - P0)
    right = np.array([run[1], -run[0]])        # to the right of the climb (right-handed run / up / right basis in the viewer)
    side = (P1 - P0) / np.linalg.norm(P1 - P0)
    origin, width = (P0, np.linalg.norm(P1 - P0)) if side @ right > 0 else (P1, np.linalg.norm(P1 - P0))
    s = [float((np.array(f(x0, y)) - P0) @ run) for y in ys]
    n = len(ys); z = [z0 + (k + 1) * rise for k in range(n)]
    going = (s[-1] - s[0]) / (n - 1) if n > 1 else 0.28
    m = rise / going; th = math.atan(m); off = waist / math.cos(th)
    soff = lambda x: z0 + m * (x - s[0]) - off
    prof = []
    for k in range(n):
        prof += [(s[k], z0 if k == 0 else z[k - 1]), (s[k], z[k])]
    prof += [(s[-1], soff(s[-1]))]
    prof += [(s[0] + off / m, z0)] if start == 'floor' else [(s[0], soff(s[0]))]
    return {'originITM': [r3(v) for v in origin], 'runDirITM': [round(float(v), 6) for v in run], 'rightDirITM': [round(float(v), 6) for v in right],
            'width_m': r3(width), 'going_m': r3(going), 'risers': n, 'profile': [[r3(a), r3(b)] for a, b in prof],
            'treadLevels': [r3(v) for v in z], 'riserS_m': [r3(v) for v in s], 'sense': sense}


def ring(f, pts):
    return [[r3(v) for v in f(x, y)] for x, y in pts]


def main():
    fg, plG = place(GA, X.K21, (300, 200, 900, 760))
    fb, plB = place(BA, 'sources/structure/k-11.dxf', (300, 200, 900, 760))
    print('placement ground', plG, 'basement', plB)

    # ---------- ST1: concrete stair basement -> ground (section: "מדרגות בטון ירידה למרתף"), 15 risers ----------
    # the concrete stair is built to the CONCRETE levels of the slabs it joins (Avihai's note 6): K-11 basement slab O.K -2.75,
    # K-21 ground slab O.K -0.15 – the architect's levels (-2.60 / ±0.00) are the finished floors, 15 cm higher at both ends,
    # so the rise stays 2.60 / 15
    FRm = json.load(open(os.path.join(ROOT, 'data/structure/framing.json'), encoding='utf-8'))
    FGm = json.load(open(os.path.join(ROOT, 'data/structure/floor-ground.json'), encoding='utf-8'))
    bs = next(x for x in FRm['slabs'] if x['id'] == 'BS1'); gs = next(x for x in FGm['slab'] if x['id'] == 'GS1')
    relc = {'basement': bs['top'], 'ground': gs['topRel']}
    fin1 = {'basement': rel['basement'] - relc['basement'], 'ground': rel['ground'] - relc['ground']}
    assert abs(fin1['basement'] - fin1['ground']) < 0.005, fin1
    rise1 = (relc['ground'] - relc['basement']) / 15
    WAIST, LAND = 0.20, 0.28    # measured on section A-A (1:100): waist ⟂ ≈ 5.7 pt, landing ≈ 7.9 pt -> approx
    yA = hlines(BA, 640.9, 665.9, 545, 640, 'solid')                  # right flight 1-7 + riser 8 onto the landing
    yA = [y for y in yA if 555 < y < 620]
    assert len(yA) == 8, yA
    yB = hlines(GA, 593.1, 617.9, 575, 640, 'solid')                  # left flight 9-15 (cut -> solid on the ground plan)
    assert len(yB) == 7, yB
    gb = lambda x, y: fg(x, y)                                        # B flight measured on the ground sheet
    yBb = [y + 26.14 for y in hlines(BA, 640.9, 665.9, 562, 612, 'dashed', keep_near=True)]   # same risers, dashed on the basement sheet (check)
    chkB = [r3(abs(a - b) / PT_M) for a, b in zip(sorted(yB)[1:], sorted(yBb))] if len(yBb) == 6 else []   # 10..9 (riser 15 is solid on both)
    xA0, xA1 = 640.88, 665.96   # flight A sides on the basement sheet (stringer line / shaft wall face)
    A = flight(fb, xA0, xA1, yA, relc['basement'], rise1, 'floor', WAIST, 'south')
    xB0, xB1 = 593.0, 617.96    # flight B sides on the ground sheet (shaft wall face / divider)
    B = flight(gb, xB0, xB1, sorted(yB, reverse=True), relc['basement'] + 8 * rise1, rise1, 'landing', WAIST, 'north')
    # shaft = the stair opening of K-21 (stairShaft zone in floor-ground.json)
    FG = json.load(open(os.path.join(ROOT, 'data/structure/floor-ground.json'), encoding='utf-8'))
    shaft = [o for o in FG['openZones'] if o.get('zone') == 'stairShaft']
    assert shaft, 'stairShaft zone missing in floor-ground.json (tools/ground-zones.json)'
    shaftP = Polygon(shaft[0]['footprintITM'])
    # half-planes on the ground sheet: landing 8 = south of riser 8 (right) / riser 9 (left); landing 15 = north of riser 15 / riser 1
    gsh = lambda x0, y0, x1, y1: Polygon(ring(fg, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))
    y8g, y9g = yA[-1] + 26.14, max(yB)        # basement -> ground sheet: +(-20.31, +26.14) pt (from the two ICPs)
    land8 = unary_union([shaftP.intersection(gsh(580, y8g, 680, 700)), shaftP.intersection(gsh(580, y9g, 618.9, 700))]).buffer(0)
    land15 = shaftP.intersection(gsh(580, 500, 680, min(yB))).buffer(0)
    st1 = {'id': 'ST1', 'name': 'מדרגות בטון: מרתף ← קרקע', 'kind': 'concrete', 'floor': 'unit', 'step': 'groundSlab',
           'rise_m': r3(rise1), 'risers': 15, 'waist_m': WAIST, 'flights': [dict(A, id='ST1-A', numbers='1–8'), dict(B, id='ST1-B', numbers='9–15')],
           'landings': [{'id': 'ST1-L8', 'label': 'פודסט ביניים (8)', 'ringITM': [[r3(a), r3(b)] for a, b in land8.exterior.coords[:-1]],
                         'topRel': r3(relc['basement'] + 8 * rise1), 'thickness_m': LAND},
                        {'id': 'ST1-L15', 'label': 'פודסט קומת הקרקע (15)', 'ringITM': [[r3(a), r3(b)] for a, b in land15.exterior.coords[:-1]],
                         'topRel': relc['ground'], 'thickness_m': LAND}],
           'concreteLevels': {'basement': relc['basement'], 'ground': relc['ground'], 'finish_m': r3(fin1['ground']),
                              'source': f"K-11 BS1 O.K={relc['basement']:+.2f}; K-21 GS1 O.K={relc['ground']:+.2f}; ריצוף {round(fin1['ground'] * 100)} ס\"מ מעל הבטון בשני הקצוות"},
           'crossCheck_m': {'flight9to15_groundVsBasementSheet': chkB},
           'status': 'approx',
           'note': 'אין תוכנית קונסטרוקציה למדרגות: מיקום ומספר שלבים מהתוכניות האדריכליות, עובי שיפוע/פודסט נמדדו בחתך א-א 1:100. מפלסי בטון (הערת אביחי 6): הפודסט העליון בפני הבטון של רצפת הקרקע ‎-0.15 (280.35), התחתון ברצפת המרתף ‎-2.75; הריצוף 15 ס"מ מעל. עובי הריצוף על המדרכים לא ידוע – הגרם כולו הונמך ב-15 ס"מ (זמני).',
           'source': f'{BA} (שלבים 1–8); {GA} (שלבים 9–15, מוצגים בחיתוך); {SEC} (מפלסים, "מדרגות בטון ירידה למרתף", עוביים); K-21 (פתח הפיר)'}

    # ---------- ST2: light stair ground -> first floor (section: "מדרגות קלות עלייה קומה א'"), risers 16-37 ----------
    rise2 = (rel['first'] - rel['ground']) / 22
    TREAD = 0.05   # light treads – thickness as drawn on the section (≈ 1.4 pt) – approx
    yR = hlines(GA, 620.1, 645.0, 550, 626, 'solid') + hlines(GA, 620.1, 645.0, 626, 640, 'dashed')   # 16..24 solid, 25-26 dashed
    yL = hlines(GA, 593.1, 617.9, 565, 640, 'dashed')                 # 29..37 (above the cut -> dashed)
    yL = [y for y in yL if y not in (yB)]
    assert len(yR) == 11 and len(yL) == 9, (yR, yL)
    xs, xd, xe, ys_ = 593.0, 618.92, 645.08, 661.64    # shaft west face / flight divider / east face / south face (ground sheet)
    treads = []
    for k in range(11):        # 16..26 (26 = quarter landing to the south wall)
        y1 = yR[k + 1] if k < 10 else ys_
        treads.append({'n': 16 + k, 'ringITM': ring(fg, [(xd, yR[k]), (xe, yR[k]), (xe, y1), (xd, y1)]), 'topRel': r3((k + 1) * rise2)})
    yLs = sorted(yL, reverse=True)       # 29 at the south ... 37 at the north
    treads.append({'n': 27, 'ringITM': ring(fg, [(xd, yLs[0]), (xd, ys_), (xs, ys_)]), 'topRel': r3(12 * rise2), 'winder': True})
    treads.append({'n': 28, 'ringITM': ring(fg, [(xs, ys_), (xs, yLs[0]), (xd, yLs[0])]), 'topRel': r3(13 * rise2), 'winder': True})
    for k in range(8):         # 29..36 ; riser 37 (yLs[8]) arrives at the first floor
        treads.append({'n': 29 + k, 'ringITM': ring(fg, [(xs, yLs[k + 1]), (xd, yLs[k + 1]), (xd, yLs[k]), (xs, yLs[k])]), 'topRel': r3((14 + k) * rise2)})
    st2 = {'id': 'ST2', 'name': "מדרגות קלות: קרקע ← קומה א'", 'kind': 'light', 'floor': 'ground', 'rise_m': r3(rise2), 'risers': 22,
           'treadThickness_m': TREAD, 'treads': treads, 'arrivalRiserITM': ring(fg, [(xs, yLs[8]), (xd, yLs[8])]),
           'status': 'approx',
           'note': 'מדרגות קלות (לפי החתך) – החומר והקונסטרוקציה לפי מסמך העיצוב / יצרן (חסר). עובי המדרך כפי שמשורטט בחתך. 27–28 שלבי פנייה (מחולקים באלכסון כמו בתוכנית).',
           'source': f'{GA} (שלבים 16–37, קו האלכסון של 27–28); {SEC} ("מדרגות קלות עלייה קומה א\'", קומה א\' +3.85)'}

    # ---------- ST2 alternative (Avihai's note 14 – OC-3): concrete stair on the same path instead of the floating one ----------
    # the architect's plan = floating treads anchored in a concrete wall ("קיר בטון לעיגון מדרגות מרחפות", sheet 13 – not in
    # sources/). The owner prefers a concrete stair: a proposal on the same treads / risers, built to the concrete levels
    # (ground slab -0.15, ground ceiling +3.70 – the finished floors ±0.00 / +3.85 are 15 cm higher at both ends)
    fc = next(x for x in FGm['ceiling']['slab'] if x['id'] == 'FS1')
    fin2 = {'ground': rel['ground'] - relc['ground'], 'first': rel['first'] - fc['topRel']}
    assert abs(fin2['ground'] - fin2['first']) < 0.005, fin2
    # anchoring wall of the floating variant: the K-21 concrete wall each tread touches (longest shared edge)
    walls = [(w['id'], w.get('tag'), Polygon(w['footprintITM']).buffer(0)) for w in FGm['walls']]
    anchors = []
    for t in treads:
        T = Polygon(t['ringITM']).buffer(0)
        best = max(((wid, tag, W.buffer(0.03).intersection(T.exterior)) for wid, tag, W in walls), key=lambda x: x[2].length)
        if best[2].length < 0.15: anchors.append({'n': t['n'], 'wall': None}); continue
        c = best[2].interpolate(0.5, normalized=True)
        anchors.append({'n': t['n'], 'wall': best[0], 'wallTag': best[1], 'contact_m': r3(best[2].length), 'atITM': [r3(c.x), r3(c.y)], 'zRel': r3(t['topRel'] - TREAD / 2)})
    # Avihai 13.11.2026: the concrete stair has NO cladding – the concrete treads ARE the finished treads (tread n at n × rise
    # above ±0.00), so the first riser off the finished ground floor and the last riser onto the finished first floor are 17.5
    # like all the others. The flight stands on the ground slab (-0.15) – the 15 cm floor build-up abuts riser 16 – and
    # bears on the ground ceiling edge (FS1 +3.70) at riser 37.
    # Design (proposal): two straight flights with a soffit parallel to the pitch line (waist ⟂ = WAIST), the turn (26–28)
    # a slab whose soffit continues flush with flight A's soffit, 27–28 cast on it.
    TT = {t['n']: t for t in treads}
    def run_flight(ns, z_floor, first_on_floor):
        rs = [np.array(TT[n]['ringITM']) for n in ns]
        c0, c1 = rs[0].mean(0), rs[-1].mean(0)
        run = (c1 - c0) / np.linalg.norm(c1 - c0)
        right = np.array([run[1], -run[0]])
        proj = lambda P: float((P - rs[0][0]) @ run)
        s0 = min(proj(P) for P in rs[0]); front = [P for P in rs[0] if abs(proj(P) - s0) < 1e-3]
        assert len(front) == 2, front
        origin = front[0] if (front[1] - front[0]) @ right > 0 else front[1]
        width = float(np.linalg.norm(front[1] - front[0]))
        o = lambda P: float((P - origin) @ run)
        sb = [(min(o(P) for P in r), max(o(P) for P in r)) for r in rs]
        tops = [TT[n]['topRel'] for n in ns]
        going = (sb[-1][1] - sb[0][0]) / len(ns)
        m = rise2 / going; off = WAIST / math.cos(math.atan(m))
        soff = lambda x: tops[0] + m * x - off      # nosing line (front edges) lowered by the waist ⟂
        z0 = z_floor if first_on_floor else soff(0)
        prof = [(0.0, z0)]
        for (a, b), z in zip(sb, tops): prof += [(a, z), (b, z)]
        prof[1] = (0.0, tops[0])
        prof += [(sb[-1][1], soff(sb[-1][1]))]
        if first_on_floor and soff(0) > z_floor: prof += [(0.0, soff(0))]
        elif first_on_floor: x = (z_floor - tops[0] + off) / m; prof += [(x, z_floor)]
        return {'treads': ns, 'originITM': [r3(v) for v in origin], 'runDirITM': [round(float(v), 6) for v in run], 'rightDirITM': [round(float(v), 6) for v in right],
                'width_m': r3(width), 'going_m': r3(going), 'profile': [[r3(a), r3(b)] for a, b in prof], 'soffitEnd': r3(soff(sb[-1][1])),
                'soffitStart': r3(soff(0)), 'pitch_deg': round(math.degrees(math.atan(m)), 1)}
    FA = run_flight(list(range(16, 26)), relc['ground'], True)
    FB = run_flight(list(range(29, 37)), None, False)
    turnBottom = FA['soffitEnd']
    st2['concreteProposal'] = {
        'change': 'OC-3', 'step': 'stairsPour', 'cladding': None, 'finish_m': 0.0, 'floorBuildUp_m': r3(fin2['ground']),
        'waist_m': WAIST, 'bottomRel': relc['ground'], 'topRel': fc['topRel'], 'ceilingThickness_m': fc.get('thickness_m'),
        'flights': [dict(FA, id='ST2-A', numbers='16–25'), dict(FB, id='ST2-B', numbers='29–36')],
        'turn': {'treads': [26, 27, 28], 'bottomRel': turnBottom},
        'firstRiser_m': r3(TT[16]['topRel'] - rel['ground']), 'lastRiser_m': r3(rel['first'] - TT[36]['topRel']),
        'note': 'הצעת בעלים (OC-3): גרם בטון באותו תוואי ובאותם רום ושלח (22 × 17.5 ס"מ), **בלי חיפוי** – הבטון הוא המדרך הגמור. '
                'רום ראשון מהריצוף ±0.00 = רום אחרון אל הריצוף +3.85 = 17.5 ס"מ. הגרם עומד על רצפת הקרקע ‎-0.15 (מילוי וריצוף 15 ס"מ צמודים לרום 16) '
                'ונשען על שפת תקרת הקרקע +3.70 (FS1). שני שלחים עם תחתית משופעת (עובי ⟂ 20 ס"מ, זמני) ופודסט פנייה 26–28 בהמשך התחתית. '
                'ממתין לתוכנית אדריכל + קונסטרוקטור.',
        'source': f"{GA} (תוואי, שלבים 16–37); {SEC} (רום, ±0.00 / +3.85); K-21 GS1 / K-31 FS1 (מפלסי בטון)"}
    print('ST2 OC-3 flights', [(f['id'], f['going_m'], f['pitch_deg'], f['profile'][:3], f['profile'][-3:]) for f in st2['concreteProposal']['flights']], 'turn', turnBottom)
    st2['anchors'] = anchors
    print('ST2 anchors', [(a['n'], a['wall'], a.get('contact_m')) for a in anchors])

    # ---------- ST3: outside stair down to the unit (west light well), 14 risers 280.31 -> 277.88 ----------
    rise3 = (rel['outTop'] - rel['outBottom']) / 14
    yW = hlines(BA, 358.1, 381.4, 530, 650, 'solid')
    yW = [y for y in yW if y not in (551.96, 614.12)]                # two long reference lines (ground-floor outline)
    if len(yW) != 14:
        yW = sorted(set(hlines(BA, 358.1, 381.4, 530, 650, 'dashed') + yW))
        yW = [y for i, y in enumerate(yW) if not (i and y - yW[i - 1] < 1.0)]
    assert len(yW) == 14, yW
    W = flight(fb, 358.04, 381.44, yW, rel['outBottom'], rise3, 'floor', WAIST, 'south')
    st3 = {'id': 'ST3', 'name': 'מדרגות חוץ: ירידה ליחידת הדיור', 'kind': 'concrete', 'floor': 'unit', 'step': 'outdoorSlabs',
           'rise_m': r3(rise3), 'risers': 14, 'waist_m': WAIST, 'flights': [dict(W, id='ST3-A', numbers='1–14')], 'landings': [],
           'status': 'approx',
           'note': 'במרווח המערבי (חצר המדרגות, בין קירות המרתף). למטה: משטח הכניסה ‎-2.62 על רצפת המרתף; למעלה: השביל הדרומי 280.31. עובי השיפוע כמו במדרגות הפנים (לא כתוב).',
           'source': f'{BA} (שלבים 1–14, רוחב "82"); {GA} (280.31 בראש המדרגות)'}

    # ---------- utilities pillar: garbage room (360 l) + electric cabinet niche, SW corner (standard B1 detail) ----------
    p = pymupdf.open(os.path.join(ROOT, GA))[0]; segs, cab = [], []
    for d in p.get_drawings():
        col, wd = tuple(round(c, 2) for c in (d.get('color') or ())), round(d.get('width') or 0, 2)
        for it in d['items']:
            if it[0] != 'l': continue
            a, b = it[1], it[2]
            if not (255 < a.x < 365 and 680 < a.y < 775): continue
            if col == (0.67, 1.0, 0.67) and wd == 0.36: segs.append(((round(a.x, 1), round(a.y, 1)), (round(b.x, 1), round(b.y, 1))))
            if col == (1.0, 0.67, 0.75) and wd == 0.96 and all(270 < q.x < 306 and 735 < q.y < 756 for q in (a, b)): cab += [(a.x, a.y), (b.x, b.y)]
    def ext(l, e=0.8):   # extend each segment a little to close the 0.1–0.8 pt joints of the drawing
        (x0, y0), (x1, y1) = l.coords; d = math.dist((x0, y0), (x1, y1)); ux, uy = (x1 - x0) / d, (y1 - y0) / d
        return LineString([(x0 - ux * e, y0 - uy * e), (x1 + ux * e, y1 + uy * e)])
    faces = list(polygonize(unary_union([ext(LineString(sg)) for sg in set(segs) if sg[0] != sg[1]])))
    thin = lambda g: 2 * g.area / g.length < 4.5        # wall bands (≈ 10 cm) vs the room / niche (≥ 0.6 m)
    walls_sheet = unary_union([g for g in faces if thin(g) and g.area > 1.0]).buffer(0.05).buffer(-0.05)
    rooms = [g for g in faces if not thin(g)]
    to_itm = lambda g: [[r3(v) for v in fg(x, y)] for x, y in g.exterior.coords[:-1]]
    wall_parts = [g for g in getattr(walls_sheet, 'geoms', [walls_sheet]) if g.area > 1.0]
    cabR = Polygon([tuple(v) for v in np.array(cab)]).convex_hull
    thick = [r3(2 * g.area / g.length / PT_M) for g in wall_parts]
    room_m2 = [r3(g.area / PT_M ** 2) for g in sorted(rooms, key=lambda g: -g.area)]
    pillar = {'id': 'PIL1', 'name': 'פילר מערכות + חדר אשפה (360 ל\')', 'floor': 'site', 'step': 'perimeterWalls',
              'wallsITM': [to_itm(g) for g in wall_parts], 'wallHolesITM': [[[[r3(v) for v in fg(x, y)] for x, y in i.coords[:-1]] for i in g.interiors] for g in wall_parts],
              'wallThickness_m': thick, 'innerAreas_m2': room_m2,
              'bottomRel': rel['pillarBase'], 'topRel': rel['pillarTop'],
              'cabinet': {'name': 'ארון חשמל (לפי המפה למשתכן)', 'ringITM': to_itm(cabR), 'bottomRel': rel['pillarBase'], 'topRel': rel['pillarTop'],
                          'status': 'approx', 'note': 'מידות הארון מהסימון בתוכנית; בחזית: ארון בגובה הפילר (240).'},
              'status': 'approx',
              'note': 'קירות הפילר וחדר האשפה (פתח 82 ס"מ לדרום, לרחוב) מקווי התוכנית; גובה 240 מעל מפלס הרחוב 279.35 לפי חזית החומה הקדמית. '
                      'יסוד ותחתית הקירות לא כתובים – תחתית זמנית במפלס הרחוב. פרט שכונתי: "תכנית פילרים במגרש פרטי" (נספח 009).',
              'source': f'{GA} (קווי הפילר, "אשפה 360 ליטר", "ארון חשמל לפי מפה למשתכן", "פילר מערכות במגרש"); {FRONT} (240, 279.35); '
                        'sources/neighborhood/development-B1/פרט חזית פילרים.PNG'}

    out = {'_doc': 'Stairs and the utilities pillar. Generated by tools/extract_stairs.py – do not edit by hand.',
           'placement': {'groundSheet': plG, 'basementSheet': plB, 'note': 'ICP (הזזה בלבד, ×2 = 1:100→1:50) מול קווי k-21 / k-11; בדיקת קנ"מ = יחס התאמה חופשי'},
           'levels': {k: {'abs': r3(v[0]), 'rel': rel[k], 'source': v[1]} for k, v in LV.items()},
           'stairs': [st1, st2, st3], 'pillar': pillar}
    json.dump(out, open(os.path.join(ROOT, 'data/structure/stairs.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('ST1 rise', r3(rise1), 'A', A['riserS_m'], 'B', B['riserS_m'], 'going', A['going_m'], B['going_m'], 'width', A['width_m'], B['width_m'],
          'land8', r3(land8.area), 'land15', r3(land15.area), 'check9-15', chkB)
    print('ST2 rise', r3(rise2), 'treads', len(treads), 'ST3 rise', r3(rise3), 'going', W['going_m'], 'width', W['width_m'])
    print('pillar walls', len(wall_parts), 'thick', thick, 'rooms', room_m2, 'cabinet m2', r3(cabR.area / PT_M ** 2))


if __name__ == '__main__':
    main()

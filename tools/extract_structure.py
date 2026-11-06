#!/usr/bin/env python3
"""
Stage-2 extraction: foundations plan K-400 (PDF, vector) + basement geometry K-11 (DXF) + soil report
-> data/structure/piles.json, data/structure/basement.json, data/structure/excavation.json

Georeference chain (no measurement taken from a raster):
  K-400 sheet (pt, 1:50, scale verified on the pile dimension chain)  --similarity-->  ITM
      fitted to the plot lines 2447-2424, 2424-2403, 2403-2420, 2457-2447 (perimeter wall band, uniform offset solved)
  K-11 DXF (cm, Revit)  --translation at 1:50-->  K-400 sheet  (ICP on wall line end-points)
Run: python3 tools/extract_structure.py
"""
import io, json, math, os, re, statistics
from collections import Counter, defaultdict

import ezdxf
import numpy as np
import pymupdf as fitz
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K400 = 'sources/structure/K-400-תכנית יסודות.pdf'
K11 = 'sources/structure/k-11.dxf'
SOIL = 'sources/geotech/דוח קרקע וביסוס - רקפות מגרש 5187.pdf'
OUT = os.path.join(ROOT, 'data', 'structure')
PT_PER_M = 72 / 25.4 * 1000 / 50          # 1:50 sheet -> 56.6929 pt per metre
PLAN_BOX = (3000, 0, 4500, 1500)          # pile-plan area on the K-400 sheet (pt)
R_PT = {'50': 0.25 * PT_PER_M, '60': 0.30 * PT_PER_M}
r3 = lambda v: round(float(v), 3)


def jload(p):
    with open(os.path.join(ROOT, p), encoding='utf-8') as f:
        return json.load(f)


def in_plan(x, y):
    return PLAN_BOX[0] < x < PLAN_BOX[2] and PLAN_BOX[1] < y < PLAN_BOX[3]


def main():
    page = fitz.open(os.path.join(ROOT, K400))[0]
    drawings = page.get_drawings()
    words = [w for w in page.get_text('words') if in_plan(w[0], w[1])]

    # ---------- pile circles: centre voting with the known radius ----------
    segs = []
    for d in drawings:
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                L = math.dist((a.x, a.y), (b.x, b.y))
                if in_plan(a.x, a.y) and 0.3 < L < 5:
                    segs.append((a.x, a.y, b.x, b.y, L))
    S = np.array(segs)
    mx, my = (S[:, 0] + S[:, 2]) / 2, (S[:, 1] + S[:, 3]) / 2
    nx, ny = -(S[:, 3] - S[:, 1]) / S[:, 4], (S[:, 2] - S[:, 0]) / S[:, 4]
    circles = {}
    for dia, r in R_PT.items():
        votes = Counter()
        for sgn in (1, -1):
            for x, y, L in zip(mx + sgn * nx * r, my + sgn * ny * r, S[:, 4]):
                votes[(round(x * 2) / 2, round(y * 2) / 2)] += L
        thr = 0.9 * 2 * math.pi * r   # at least ~one full circle of arc length
        keep = []
        for k, v in sorted(votes.items(), key=lambda kv: -kv[1]):
            if v < thr:
                break
            if all(math.dist(k, q) > 3 for q, _ in keep):
                keep.append((k, v))
        circles[dia] = [k for k, _ in keep]

    # ---------- labels: number / Pileøxx / O.K / L / N ----------
    labels = []
    for w in words:
        m = re.match(r'Pileø(\d\d)$', w[4])
        if not m:
            continue
        cx, y = (w[0] + w[2]) / 2, w[1]
        num = [v for v in words if re.fullmatch(r'\d{1,3}A?', v[4]) and 0 < y - v[1] < 18 and abs((v[0] + v[2]) / 2 - cx) < 25]
        num = min(num, key=lambda v: abs((v[0] + v[2]) / 2 - cx) + abs(y - v[1]))[4]
        below = [v for v in words if 0 < v[1] - y < 50 and abs(v[0] - w[0]) < 25]
        def grab(prefix):
            c = [v for v in below if v[4].startswith(prefix)]
            if not c:
                return None
            v = min(c, key=lambda v: v[1])
            return ' '.join(u[4] for u in sorted([u for u in words if abs(u[1] - v[1]) < 1 and v[0] - 1 <= u[0] < v[0] + 60], key=lambda u: u[0]))
        ok, Ls, N = grab('O.K'), grab('L='), grab('N=')
        labels.append({'id': num, 'dia': m.group(1), 'lx': cx, 'ly': y,
                       'head': float(re.search(r'-?\d+\.\d+', ok.replace(' ', '')).group()),
                       'L': float(re.search(r'L=(\d+(?:\.\d+)?)m', Ls).group(1)),
                       'N': float(re.search(r'N=\s*(\d+)', N).group(1)), 'labelText': f'{ok} {Ls} {N}'})
    # Revit tags sit at a fixed offset (up-right) from their pile: estimate it, then assign globally by distance
    def assign(offset):
        pairs = []
        for i, l in enumerate(labels):
            ex = (l['lx'] + offset[0], l['ly'] + offset[1])
            for j, c in enumerate(circles[l['dia']]):
                pairs.append((math.dist(ex, c), i, j, l['dia']))
        pairs.sort(); ui, uc, res = set(), set(), {}
        for d, i, j, dia in pairs:
            if i in ui or (dia, j) in uc:
                continue
            ui.add(i); uc.add((dia, j)); res[i] = (circles[dia][j], d)
        return res
    first = assign((0, 0))
    good = [(first[i][0][0] - l['lx'], first[i][0][1] - l['ly']) for i, l in enumerate(labels) if 76 < math.dist(first[i][0], (l['lx'], l['ly'])) < 82]
    offset = (statistics.median(g[0] for g in good), statistics.median(g[1] for g in good))
    final = assign(offset)
    for i, l in enumerate(labels):
        l['sheetXY'] = list(final[i][0]); l['tagOffsetError_pt'] = round(final[i][1], 1)

    # ---------- georeference K-400 -> ITM (plot lines, uniform band offset) ----------
    pts = {p['name']: (p['E'], p['N']) for p in jload('data/site/control-points.json')['points']}
    band = [d for d in drawings if d.get('fill') and abs(d['fill'][0] - 0.898) < 0.01 and in_plan(d['rect'].x0, d['rect'].y0)
            and (d['rect'].width > 300 or d['rect'].height > 300) and len(d['items']) <= 25]
    vtx = np.array([(it[1].x, it[1].y) for d in band for it in d['items'] if it[0] == 'l'])
    def corner(target):  # band vertex nearest a target (rough) sheet position
        return tuple(vtx[np.argmin(np.hypot(vtx[:, 0] - target[0], vtx[:, 1] - target[1]))])
    c2447, c2424, c2403 = corner((3100, 110)), corner((3805, 152)), corner((4316, 108))
    c_r, c_l = corner((4428, 1412)), corner((3130, 1394))
    edges = {('2447', '2424'): [c2447, c2424], ('2424', '2403'): [c2424, c2403],
             ('2403', '2420'): [c2403, c_r], ('2457', '2447'): [c_l, c2447]}
    cen = np.mean([pts[k] for k in ('2403', '2420', '2457', '2447', '2424')], axis=0)
    def sheet2itm(par, x, y):
        th, tx, ty = par[:3]; X, Y = x / PT_PER_M, -y / PT_PER_M
        return (tx + X * math.cos(th) - Y * math.sin(th), ty + X * math.sin(th) + Y * math.cos(th))
    def resid(par):
        r = []
        for (a, b), ends in edges.items():
            A, B = np.array(pts[a]), np.array(pts[b]); d = (B - A) / np.linalg.norm(B - A); n = np.array([d[1], -d[0]])
            if np.dot(cen - A, n) > 0: n = -n
            for x, y in ends:
                r.append(np.dot(np.array(sheet2itm(par, x, y)) - A, n) - par[3])
        return r
    X0, Y0 = c2447[0] / PT_PER_M, -c2447[1] / PT_PER_M
    sol = least_squares(resid, [0, pts['2447'][0] - X0, pts['2447'][1] - Y0, 0.05])
    G = sol.x
    georef = {'method': 'similarity at verified 1:50, fitted to 4 plot lines (perimeter wall band, uniform offset solved)',
              'rotationDeg': round(math.degrees(G[0]), 5), 'bandOffsetFromPlotLine_m': r3(G[3]),
              'maxLineResidual_m': float(np.abs(sol.fun).max()), 'equations': len(sol.fun), 'unknowns': 4}
    to_itm = lambda x, y: sheet2itm(G, x, y)

    # scale check on the written dimension chain between piles 100-101-102-104-105 (horizontal dims, cm)
    byid = {l['id']: l for l in labels}
    chain = [('100', '101', 492), ('101', '102', 478), ('102', '104', 513), ('104', '105', 484)]
    scale_check = [{'from': a, 'to': b, 'written_cm': w,
                    'measured_cm': round(abs(byid[b]['sheetXY'][0] - byid[a]['sheetXY'][0]) / PT_PER_M * 100, 1)} for a, b, w in chain]

    # ---------- piles ----------
    xl = jload('tools/pile-table-xlsx.json')['piles']
    piles = []
    for l in sorted(labels, key=lambda l: (int(re.match(r'\d+', l['id']).group()), l['id'])):
        E, N = to_itm(*l['sheetXY'])
        x = xl.get(l['id'])
        piles.append({
            'id': l['id'], 'diameter_m': int(l['dia']) / 100, 'E': r3(E), 'N': r3(N),
            'headRel': l['head'], 'length_m': l['L'], 'tipRel': r3(l['head'] - l['L']), 'designLoad_t': l['N'],
            'zone': 'basement' if l['head'] <= -2.99 else 'ground',
            'tipNote': 'מפלס תחתית = מפלס ראש פחות L. לפי דוח הקרקע (6.5) L הוא האורך בקרקע טבעית – לבקרה',
            'xlsxCheck': None if not x else {'diameter_cm': x[0], 'L': x[1], 'head': x[2], 'N': x[3], 'allowed': x[4],
                                             'match': x[0] == int(l['dia']) and x[1] == l['L'] and abs(x[2] - l['head']) < 1e-6 and x[3] == l['N']},
            'overAllowed': bool(x and x[3] > x[4]),
            'source': f'{K400} – pile circle (centre voting r={l["dia"]}cm) + tag "{l["labelText"]}"',
        })

    # ---------- basement outline (K-11 DXF walls) -> K-400 sheet -> ITM ----------
    txt = open(os.path.join(ROOT, K11), 'rb').read().decode('cp1255', errors='replace').replace('\r\n', '\n')
    msp = ezdxf.read(io.StringIO(txt)).modelspace()
    s = PT_PER_M / 100  # pt per cm
    A = []
    for e in msp.query('LINE[layer=="IfcWall"]'):
        A += [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    A = np.unique(np.round(np.array(A), 2), axis=0); Ap = np.c_[A[:, 0] * s, -A[:, 1] * s]
    B = []
    for d in drawings:
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                if in_plan(a.x, a.y) and math.dist((a.x, a.y), (b.x, b.y)) > 8:
                    B += [(a.x, a.y), (b.x, b.y)]
    B = np.unique(np.round(np.array(B), 2), axis=0); T = cKDTree(B)
    votes = Counter((round(q[0] - p[0]), round(q[1] - p[1])) for p in Ap for q in B)
    best = None
    for (tx, ty), _ in votes.most_common(60):
        t = np.array([tx, ty], float)
        for _ in range(20):
            dd, ii = T.query(Ap + t); m = dd < 2
            if m.sum() < 10: break
            t += (B[ii[m]] - (Ap[m] + t)).mean(0)
        dd, _ = T.query(Ap + t); score = (dd < 0.3).mean()
        if best is None or score > best[0]: best = (score, t.copy(), float(np.median(dd)))
    k11_t = best[1]
    k11_to_itm = lambda x, y: to_itm(x * s + k11_t[0], -y * s + k11_t[1])
    hatch = []
    for h in msp.query('HATCH[layer=="IfcWall"]'):
        for path in h.paths:
            vs = [(v[0], v[1]) for v in path.vertices] if hasattr(path, 'vertices') else \
                 [(e.start[0], e.start[1]) for e in path.edges if e.EDGE_TYPE == 'LineEdge']
            if len(vs) >= 3: hatch.append(Polygon(vs).buffer(0))
    walls = unary_union([p.buffer(0.5) for p in hatch]).buffer(-0.5)
    main_walls = max(walls.geoms, key=lambda g: g.area) if walls.geom_type == 'MultiPolygon' else walls
    outline_cm = Polygon(main_walls.exterior).simplify(0.5)
    outline = [[r3(c) for c in k11_to_itm(x, y)] for x, y in list(outline_cm.exterior.coords)[:-1]]
    slabs = []
    for e in msp.query('MTEXT[layer=="Floor Tags"]'):
        t = e.plain_text()
        if t.startswith('O.K'):
            v = [u for u in msp.query('MTEXT[layer=="Floor Tags"]') if abs(u.dxf.insert.y - e.dxf.insert.y) < 1 and u.dxf.insert.x > e.dxf.insert.x]
            if v:
                ok = -float(min(v, key=lambda u: u.dxf.insert.x).plain_text())
                d = [u for u in msp.query('MTEXT[layer=="Floor Tags"]') if abs(u.dxf.insert.y - (e.dxf.insert.y - 28.8)) < 2 and u.plain_text().strip().isdigit()]
                slabs.append({'topRel': ok, 'thickness_cm': int(d[0].plain_text()) if d else None,
                              'tagAt': [r3(c) for c in k11_to_itm(e.dxf.insert.x, e.dxf.insert.y)]})
    basement = {
        'outlineITM': outline, 'area_m2': r3(Polygon(outline).area),
        'wallFootprint_m2': r3(main_walls.area / 1e4),
        'slabTags': slabs,
        'k11ToK400': {'translation_pt': [r3(k11_t[0]), r3(k11_t[1])], 'scale_pt_per_cm': s,
                      'inlierFraction': round(best[0], 3), 'medianResidual_mm': round(best[2] / s * 10, 2)},
        'source': f'{K11} layer IfcWall (HATCH union, outer face) + Floor Tags; placed via K-400',
    }

    # independent cross-check: basement outline vs the architect's walls in the permit sheet (separate georeference)
    try:
        import sys; sys.path.insert(0, os.path.join(ROOT, 'tools'))
        from permit_georef import permit_to_itm
        from shapely.geometry import LineString
        pj = json.load(open(os.path.join(ROOT, 'tools', 'cache', 'permit-sheet1.json'), encoding='utf-8'))
        wl = [LineString([permit_to_itm(e['startPoint']['x'], e['startPoint']['y']), permit_to_itm(e['endPoint']['x'], e['endPoint']['y'])])
              for e in pj['entities'] if e['type'] == 'LINE' and e['layer'] in ('A-WALL', 'S-STRS', 'I-WALL')
              and 39500 < e['startPoint']['x'] < 43200 and -4000 < e['startPoint']['y'] < -600]
        Wu = unary_union(wl); ds = sorted(Wu.distance(Point(p)) for p in outline)
        basement['crossCheckPermitWalls'] = {'vertices': len(ds), 'median_m': r3(statistics.median(ds)), 'max_m': r3(ds[-1]),
            'note': 'מרחק קודקודי קו המרתף (K-11 דרך K-400) מקירות הגרמושקה (גאורפרנס נפרד). קודקודים רחוקים = מקומות שקיר המרתף שונה מקיר הקרקע.'}
    except FileNotFoundError:
        basement['crossCheckPermitWalls'] = None

    # ---------- excavation for the dwelling unit (basement) ----------
    H0 = jload('data/site/origin.json')['H0']
    basement_piles = [p for p in piles if p['zone'] == 'basement']
    pile_disks = [Point(p['E'], p['N']).buffer(p['diameter_m'] / 2, 32) for p in basement_piles]
    bottom_poly = unary_union([Polygon(outline)] + pile_disks)
    bottom_poly = Polygon(bottom_poly.exterior) if bottom_poly.geom_type == 'Polygon' else Polygon(max(bottom_poly.geoms, key=lambda g: g.area).exterior)
    excavation = {
        'bottomOutlineITM': [[r3(x), r3(y)] for x, y in list(bottom_poly.exterior.coords)[:-1]],
        'bottomRel': -3.30, 'bottomAbs': r3(H0 - 3.30),
        'bottomBuildUp': [
            {'item': 'תחתית קורות יסוד / רצפה תלויה = מפלס ראש כלונסאות המרתף', 'rel': -3.00, 'source': f'{K400} (טבלה: O.K=-3.00), {K11} (O.K=-2.75, D=25)'},
            {'item': 'בטון רזה 3÷5 ס"מ + יריעות דיקט', 'thickness_m': 0.05, 'status': 'approved', 'approved': 'אביחי 06.11.2026 – הערך העליון בטווח',
             'source': f'{K400} פרט כלונס טיפוסי מתחת לקורת יסוד: "בטון רזה בעובי 3÷5 ס\"מ" (טווח 3 עד 5)'},
            {'item': 'ארגזי הפרדה (פוליביד) 25 ס"מ', 'thickness_m': 0.25, 'source': f'{SOIL} סעיף 9.1; {K400} פרט רצפה תלויה'},
        ],
        'sideSlope_HperV': 2.0, 'sideSlopeSource': f'{SOIL} סעיף 10.1: חפירה זמנית בשיפוע 1V:2H',
        'workingSpace_m': 1.0, 'workingSpaceStatus': 'approved',
        'workingSpaceNote': 'לא מופיע במקורות. הנחיית אביחי 06.11.2026: המקובל 0.80–1.00 מ\' בתחתית, מהפנים החיצוניים של הקיר עד דופן החפירה (טפסות, איטום ביריעות ביטומניות, לוח הגנה, צינור ניקוז, מילוי והידוק); מינימום 0.60. נלקח 1.00 (הערך העליון).',
        'shoringRule': f'{SOIL} סעיף 10.2: חפירה החודרת למגרש שכן/פיתוח מחייבת כלונסאות דיפון',
        'clipToPlot': True,
        'source': f'{K11} + {K400} + {SOIL}',
    }

    os.makedirs(OUT, exist_ok=True)
    def dump(name, obj):
        with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        print('wrote', name)
    dump('piles.json', {'georeference': georef, 'scaleCheck': scale_check, 'tagOffset_pt': [round(offset[0], 2), round(offset[1], 2)],
                        'count': len(piles), 'piles': piles,
                        'requirements': 'K-400: ניסיון קידוח בשיטה יבשה, בדיקות סוניות בכל הכלונסאות לאחר 7 ימים, בטון ב-30, לפי דוח קרקע 214140/5187'})
    dump('basement.json', basement)
    dump('excavation.json', excavation)


if __name__ == '__main__':
    main()

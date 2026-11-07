#!/usr/bin/env python3
"""Stage 2b – foundations below the ground floor, from the structural drawings (Yarin Engineering, Revit exports).

Sources and placement (all onto the K-400 sheet, which is georeferenced in tools/extract_structure.py → piles.json):
  k-11.dxf (basement, cm)     -> K-400 sheet: translation found by ICP (stored in basement.json k11ToK400)
  k-21.dxf (ground floor, cm) -> K-400 sheet: translation found by ICP on the wall lines (same method)
  K-21 / K-11 PDF (1:50)      -> K-400 sheet: translation found by ICP on line end points (beam tags)
  K-400 PDF                   : ground beams drawn with concrete stipple (black dots, 0.51 pt)

Output: data/structure/framing.json
  basementWalls  – wall footprints (K-11 IfcWall hatches) with bottom/top levels
  slabs          – floor slab panels with top (O.K) and thickness (D) from the floor tags
  groundBeams    – beams under the ground floor (K-400 stipple strips + K-21/K-11 beam tags) – PROVISIONAL geometry
Nothing here is guessed: every level comes from a tag in the drawings; where the drawings do not decide something the
record carries status "provisional" and a note, and docs/open-issues.md lists it. The Revit/IFC model has been
requested from the structural engineer and will replace this extraction.
"""
import io, json, math, os, re
from collections import Counter
import ezdxf
import numpy as np
import pymupdf
from scipy.spatial import cKDTree
from scipy.signal import find_peaks
from shapely.geometry import Polygon, Point, LineString, MultiPolygon
from shapely.ops import unary_union, polygonize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
r3 = lambda v: round(float(v), 3)
K400 = 'sources/structure/K-400-תכנית יסודות.pdf'
K11 = 'sources/structure/k-11.dxf'
K21 = 'sources/structure/k-21.dxf'
K11P = 'sources/structure/K-11-‏תוכנית קומה מרתף- גיאומטריה.pdf'
K21P = 'sources/structure/K-21-תוכנית קרקע- גיאומטריה.pdf'
PLAN = (3000, 0, 4500, 1500)            # plan window on the K-400 sheet (pt)
SD_REBAR = {'K-12': 'sources/structure/K-12-קומת מרתף - פריסת ברזל קורות.pdf', 'K-22': 'sources/structure/K-22-קומה קרקע - פריסת ברזל קורות.pdf'}

piles = J('data/structure/piles.json'); basement = J('data/structure/basement.json')
G = piles['georeference']['sheetToItm']; PT = G['ptPerM']; S_CM = PT / 100


def sheet2itm(x, y):
    X, Y = x / PT, -y / PT
    th = G['theta_rad']
    return (G['tx'] + X * math.cos(th) - Y * math.sin(th), G['ty'] + X * math.sin(th) + Y * math.cos(th))


def read_dxf(path):
    raw = open(os.path.join(ROOT, path), 'rb').read().decode('cp1255', errors='replace').replace('\r\n', '\n')
    return ezdxf.read(io.StringIO(raw)).modelspace()


def k400_lines():
    p = pymupdf.open(os.path.join(ROOT, K400))[0]
    B, dots = [], []
    for d in p.get_drawings():
        R = d['rect']
        if not (PLAN[0] < R.x0 < PLAN[2] and PLAN[1] < R.y0 < PLAN[3]): continue
        col = d.get('color') or (1, 1, 1)
        if d['type'] == 's' and col[0] < 0.01 and col[1] < 0.01 and round(d.get('width') or 0, 2) == 0.51 and max(R.width, R.height) < 1.5:
            dots.append(((R.x0 + R.x1) / 2, (R.y0 + R.y1) / 2))
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                if math.dist((a.x, a.y), (b.x, b.y)) > 8: B += [(a.x, a.y), (b.x, b.y)]
    return np.unique(np.round(np.array(B), 2), axis=0), np.array(dots)


def icp(A, B, tries=60):
    T = cKDTree(B)
    votes = Counter((round(q[0] - p[0]), round(q[1] - p[1])) for p in A[::2] for q in B[::2])
    best = None
    for (tx, ty), _ in votes.most_common(tries):
        t = np.array([tx, ty], float)
        for _ in range(20):
            dd, ii = T.query(A + t); m = dd < 2
            if m.sum() < 10: break
            t += (B[ii[m]] - (A[m] + t)).mean(0)
        dd, _ = T.query(A + t); score = (dd < 0.3).mean()
        if best is None or score > best[0]: best = (score, t.copy(), float(np.median(dd[dd < 2])) if (dd < 2).any() else 99)
    return best


def dxf_wall_endpoints(msp):
    A = []
    for e in msp.query('LINE[layer=="IfcWall"]'):
        A += [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    A = np.unique(np.round(np.array(A), 2), axis=0)
    return np.c_[A[:, 0] * S_CM, -A[:, 1] * S_CM]


def pdf_endpoints(path, clip):
    p = pymupdf.open(os.path.join(ROOT, path))[0]; B = []
    for d in p.get_drawings():
        for it in d['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                if clip[0] < a.x < clip[2] and clip[1] < a.y < clip[3] and math.dist((a.x, a.y), (b.x, b.y)) > 8:
                    B += [(a.x, a.y), (b.x, b.y)]
    return np.unique(np.round(np.array(B), 2), axis=0)


def floor_tags(msp, to_sheet):
    """Floor tags = TAGFLOOR inserts; the values are separate MTEXT fragments ('O.K=-' + '2.75', 'D=' + '25')."""
    frag = [(e.dxf.insert.x, e.dxf.insert.y, e.plain_text().strip()) for e in msp.query('MTEXT[layer=="Floor Tags"]')]
    out = []
    for e in msp.query('INSERT[layer=="Floor Tags"]'):
        x, y = e.dxf.insert.x, e.dxf.insert.y
        near = sorted(frag, key=lambda f: math.dist((f[0], f[1]), (x, y)))[:6]
        ok = next(f for f in near if f[2].startswith('O.K='))
        sign = -1 if ok[2].endswith('-') else 1
        okv = min((f for f in near if re.match(r'^\d+\.\d+$', f[2])), key=lambda f: abs(f[1] - ok[1]) * 10 + abs(f[0] - ok[0]))
        dd = next(f for f in near if f[2].startswith('D='))
        dv = min((f for f in near if re.match(r'^\d+$', f[2])), key=lambda f: abs(f[1] - dd[1]) * 10 + abs(f[0] - dd[0]))
        sx, sy = to_sheet(x, y)
        out.append({'top': sign * float(okv[2]), 'thickness_m': int(dv[2]) / 100, 'sheetXY': (sx, sy), 'itm': sheet2itm(sx, sy)})
    return out


def wall_polys(msp, to_itm):
    polys = []
    for h in msp.query('HATCH[layer=="IfcWall"]'):
        for path in h.paths:
            vs = [(v[0], v[1]) for v in path.vertices] if hasattr(path, 'vertices') else \
                 [(e.start[0], e.start[1]) for e in path.edges if e.EDGE_TYPE == 'LineEdge']
            if len(vs) >= 3: polys.append(Polygon([to_itm(x, y) for x, y in vs]).buffer(0))
    return unary_union([p.buffer(0.003) for p in polys]).buffer(-0.003)


def strips(P, axis):
    """Straight stipple strips (axis=1: horizontal on the sheet, 0: vertical)."""
    c, a = P[:, axis], P[:, 1 - axis]
    h, e = np.histogram(c, bins=np.arange(c.min() - 5, c.max() + 5, 1.0))
    hs = np.convolve(h, np.ones(9) / 9, 'same')
    pk, _ = find_peaks(hs, height=2.0, distance=12)
    out = []
    for k in pk:
        y0 = (e[k] + e[k + 1]) / 2
        m = np.abs(c - y0) < 12
        xs = np.sort(a[m])
        if len(xs) < 8: continue
        gaps = np.where(np.diff(xs) > 30)[0]
        for s, t in zip(np.r_[0, gaps + 1], np.r_[gaps, len(xs) - 1]):
            sel = m & (a >= xs[s] - 0.1) & (a <= xs[t] + 0.1)
            if sel.sum() < 8 or xs[t] - xs[s] < 25: continue
            out.append({'axis': 'h' if axis == 1 else 'v', 'center': float(np.median(c[sel])), 'from': float(xs[s]), 'to': float(xs[t]), 'n': int(sel.sum())})
    return out


def pdf_beam_tags(path, t):
    p = pymupdf.open(os.path.join(ROOT, path))[0]; L = []
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            L.append((''.join(s['text'] for s in l['spans']).strip(), l['bbox'], l['dir']))
    out = []
    for txt, bb, dr in L:
        if not re.match(r'^B-\d+$', txt): continue
        sec = min((x for x in L if re.match(r'^\d+/\d+; O\.K=', x[0])),
                  key=lambda x: (x[1][0] + x[1][2] - bb[0] - bb[2]) ** 2 + (x[1][1] + x[1][3] - bb[1] - bb[3]) ** 2)
        m = re.match(r'^(\d+)/(\d+); O\.K=([+-]\d\.\d+)', sec[0])
        cx = (bb[0] + bb[2] + sec[1][0] + sec[1][2]) / 4 + t[0]; cy = (bb[1] + bb[3] + sec[1][1] + sec[1][3]) / 4 + t[1]
        out.append({'id': txt, 'w_cm': int(m[1]), 'h_cm': int(m[2]), 'top': float(m[3]), 'tagSheetXY': (cx, cy), 'axis': 'h' if abs(dr[0]) > 0.5 else 'v'})
    return out


def close_beam_corners(beams, tol=0.06):
    """L-corner of two perpendicular beams (each ends at the other): the drawn outlines stop at each other's axis /
    inner face, leaving the corner square open. The beam is run on to the outer face of the other one (the corner is cast
    with both). Returns the ids changed."""
    done = []
    ax = [b for b in beams if b.get('axisITM')]
    for a in ax:
        for b in ax:
            if a is b: continue
            (p0, p1), (q0, q1) = a['axisITM'], b['axisITM']
            ua = np.subtract(p1, p0); la = np.linalg.norm(ua); ua = ua / la
            ub = np.subtract(q1, q0); lb = np.linalg.norm(ub); ub = ub / lb
            if abs(float(np.dot(ua, ub))) > 0.05: continue          # perpendicular only
            for k in (0, 1):
                P = np.array(a['axisITM'][k]); out_dir = -ua if k == 0 else ua
                # the beam goes on in line (another beam continues from this end): not a corner
                # (at the same level: B-53 / B-47 at -0.17 meet where the parking beams B-54 / B-52 at -0.47 go on in line –
                # the house corner is still an L corner, Avihai's note 17)
                if any(c is not a and abs(abs(float(np.dot(ua, np.subtract(*c['axisITM'][::-1]) / math.dist(*c['axisITM'])))) - 1) < 0.01
                       and abs(c.get('topRel', 0) - a.get('topRel', 0)) < 0.05
                       and min(math.dist(P, c['axisITM'][0]), math.dist(P, c['axisITM'][1])) < 0.2 for c in ax): continue
                # b's axis line near this end of a, and one end of b near a's axis line (corner, not a T)
                t = float(np.dot(P - q0, ub)); foot = np.array(q0) + ub * t
                dist = float(np.linalg.norm(P - foot))
                if dist > b['width_m'] / 2 + tol or not (-a['width_m'] / 2 - tol <= t <= lb + a['width_m'] / 2 + tol): continue
                near_end = min(abs(t), abs(t - lb))
                if near_end > a['width_m'] / 2 + tol: continue           # T-junction: b runs on past a – nothing to close
                # the far face of b, seen from a
                side = float(np.dot(foot - P, out_dir))
                target = float(np.dot(foot - P, out_dir)) + b['width_m'] / 2
                if target > 0.005 and target < b['width_m'] + tol and (side > -tol):
                    newP = P + out_dir * target
                    a['axisITM'][k] = [r3(newP[0]), r3(newP[1])]
                    if 'length_m' in a: a['length_m'] = r3(math.dist(*a['axisITM']))
                    done.append(f"{a['id']}+{target:.2f}")
    return done


def main():
    lines400, dots = k400_lines()
    # ---- placements ----
    k11 = basement['k11ToK400']; t11 = k11['translation_pt']
    k11_sheet = lambda x, y: (x * S_CM + t11[0], -y * S_CM + t11[1])
    m21 = read_dxf(K21)
    sc21, t21, med21 = icp(dxf_wall_endpoints(m21), lines400)
    k21_sheet = lambda x, y: (x * S_CM + t21[0], -y * S_CM + t21[1])
    p21 = icp(pdf_endpoints(K21P, (1650, 150, 3100, 1700)), lines400)
    p11 = icp(pdf_endpoints(K11P, (350, 150, 1150, 1150)), lines400)
    placement = {
        'k11dxf': {'translation_pt': t11, 'source': 'basement.json k11ToK400'},
        'k21dxf': {'translation_pt': [r3(v) for v in t21], 'inlierFraction': r3(sc21), 'medianResidual_pt': r3(med21)},
        'K21pdf': {'translation_pt': [r3(v) for v in p21[1]], 'inlierFraction': r3(p21[0]), 'medianResidual_pt': r3(p21[2])},
        'K11pdf': {'translation_pt': [r3(v) for v in p11[1]], 'inlierFraction': r3(p11[0]), 'medianResidual_pt': r3(p11[2])},
    }
    m11 = read_dxf(K11)
    to_itm11 = lambda x, y: sheet2itm(*k11_sheet(x, y))
    to_itm21 = lambda x, y: sheet2itm(*k21_sheet(x, y))

    # ---- basement walls (K-11) ----
    W = wall_polys(m11, to_itm11)
    Wl = list(W.geoms) if W.geom_type == 'MultiPolygon' else [W]
    tags11 = floor_tags(m11, k11_sheet)
    tags21 = floor_tags(m21, k21_sheet)
    bsm = Polygon(basement['outlineITM'])
    # the ground-floor slab over the basement carries one tag (outside the basement footprint): take the nearest one
    over_bsm = sorted(tags21, key=lambda t: bsm.centroid.distance(Point(t['itm'])))[:1]
    pile_head_bsm = sorted({p['headRel'] for p in piles['piles'] if p['zone'] == 'basement'})
    wall_top = over_bsm[0]['top'] - over_bsm[0]['thickness_m']
    walls = [{'id': f'BW{i + 1}', 'footprintITM': [[r3(x), r3(y)] for x, y in list(w.exterior.coords)[:-1]],
              'holesITM': [[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in w.interiors],
              'area_m2': r3(w.area), 'bottomRel': pile_head_bsm[0], 'topRel': r3(wall_top),
              'status': 'provisional',
              'note': 'תחתית = מפלס ראש כלונסאות המרתף (K-400 O.K=-3.00); ראש = תחתית תקרת הקרקע מעל המרתף (K-21: O.K ועובי D). '
                      'אין חתך קיר במקורות – לאישור מול ה-IFC.',
              'source': f'{K11} HATCH IfcWall; {K400}; {K21} Floor Tags'}
             for i, w in enumerate(sorted(Wl, key=lambda g: -g.area)) if w.area > 0.02]

    # ---- slab panels: rooms of the basement (outline minus walls) and of the ground floor outside the basement ----
    # slab panels of the basement level = faces of the IfcSlab lines (k-11), each with the floor tag it contains
    L = [LineString([to_itm11(e.dxf.start.x, e.dxf.start.y), to_itm11(e.dxf.end.x, e.dxf.end.y)]) for e in m11.query('LINE[layer=="IfcSlab"]')]
    slabs = []
    for i, face in enumerate(sorted(polygonize(unary_union(L)), key=lambda g: -g.area)):
        tg = [t for t in tags11 if face.contains(Point(t['itm']))]
        rec = {'id': f'BS{i + 1}', 'level': 'basement', 'outlineITM': [[r3(x), r3(y)] for x, y in list(face.exterior.coords)[:-1]],
               'holesITM': [[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in face.interiors], 'area_m2': r3(face.area)}
        vals = {(t['top'], t['thickness_m']) for t in tg}
        if len(vals) == 1:
            top, d = vals.pop()
            rec.update(top=top, thickness_m=d, status='source', source=f'{K11} IfcSlab (קווי רצפה) + Floor Tag O.K={top:+.2f} D={round(d * 100)}')
        else:
            rec.update(top=None, thickness_m=None, status='missing', note=f'{len(tg)} תגיות – מפלס הרצפה לא נקבע מהשרטוט', source=f'{K11} IfcSlab')
        slabs.append(rec)

    # ---- ground beams: K-400 stipple strips matched to beam tags (K-21 ground floor, K-11 basement) ----
    S = strips(dots, 1) + strips(dots, 0)
    tags = [dict(t, sheet='K-21') for t in pdf_beam_tags(K21P, p21[1])] + [dict(t, sheet='K-11') for t in pdf_beam_tags(K11P, p11[1])]
    beams = []
    used = Counter()
    # 1) nearest strip for every tag
    match = []
    for t in tags:
        x, y = t['tagSheetXY']; best = None
        for k, s_ in enumerate(S):
            if s_['axis'] != t['axis']: continue
            along, perp = (x, y) if s_['axis'] == 'h' else (y, x)
            d = abs(perp - s_['center']) + max(0, s_['from'] - along, along - s_['to'])
            if best is None or d < best[0]: best = (d, k)
        match.append(best if best and best[0] <= 10 else None)
    # 2) a strip carrying several tags is split between them, at the crossing strip nearest the midpoint
    seg = {}
    for k in {m[1] for m in match if m}:
        idx = [i for i, m in enumerate(match) if m and m[1] == k]
        s_ = S[k]; al = lambda i: tags[i]['tagSheetXY'][0 if s_['axis'] == 'h' else 1]
        idx.sort(key=al); cuts = [s_['from']]
        for i, j in zip(idx, idx[1:]):
            mid = (al(i) + al(j)) / 2
            cross = [c['center'] for c in S if c['axis'] != s_['axis'] and c['from'] - 5 <= s_['center'] <= c['to'] + 5 and al(i) < c['center'] < al(j)]
            cuts.append(min(cross, key=lambda c: abs(c - mid)) if cross else mid)
        cuts.append(s_['to'])
        for n, i in enumerate(idx): seg[i] = (k, cuts[n], cuts[n + 1], len(idx) > 1)
    for i, t in enumerate(tags):
        rec = {'id': t['id'], 'sheet': t['sheet'], 'width_m': t['w_cm'] / 100, 'depth_m': t['h_cm'] / 100, 'topRel': t['top'],
               'bottomRel': r3(t['top'] - t['h_cm'] / 100), 'tagITM': [r3(v) for v in sheet2itm(*t['tagSheetXY'])],
               'source': f"{K21P if t['sheet'] == 'K-21' else K11P} תווית {t['id']} ({t['w_cm']}/{t['h_cm']}; O.K={t['top']:+.2f})"}
        if i in seg:
            k, f0, f1, split = seg[i]; s_ = S[k]; used[k] += 1
            a = (f0, s_['center']) if s_['axis'] == 'h' else (s_['center'], f0)
            b = (f1, s_['center']) if s_['axis'] == 'h' else (s_['center'], f1)
            rec.update(axisITM=[[r3(v) for v in sheet2itm(*a)], [r3(v) for v in sheet2itm(*b)]], matchDistance_pt=r3(match[i][0]),
                       geometrySource=f'{K400} פס נקודות בטון (stipple) – ציר ואורך' + (' (פס משותף לכמה קורות – חולק בין התוויות)' if split else ''),
                       status='provisional')
        else:
            rec.update(axisITM=None, status='missing', note='לא נמצא פס קורה תואם ב-K-400 (קורה מעל המרתף / לא קורת יסוד)')
        if rec.get('axisITM'):
            ax = LineString(rec['axisITM'])
            over = bsm.buffer(0.15).intersection(ax).length / max(ax.length, 1e-6)
            rec['overBasement'] = over > 0.6
            # a ground-floor (K-21) beam above the basement is part of the slab over the basement, not a foundation beam
            # construction order: basement-level beams (K-11) first; ground-floor beams (K-21) are cast after the basement
            # walls and backfill, in one pour with the ground slab / the slab over the basement -> stage "ceiling"
            if t['sheet'] == 'K-21':
                rec['stage'] = 'slab'           # cast with the ground slab (step "רצפת קרקע")
                rec['layer'] = 'ceilingBeams' if rec['overBasement'] else 'groundFloorBeams'
            else:
                rec['stage'] = 'groundBeams'; rec['layer'] = 'groundBeams'
        beams.append(rec)
    # de-duplicate identical tags (same beam tagged twice)
    seen = set(); beams = [b for b in beams if not ((b['id'], tuple(map(tuple, b['axisITM'] or []))) in seen or seen.add((b['id'], tuple(map(tuple, b['axisITM'] or [])))))]
    unmatched = [k for k in range(len(S)) if not used[k]]

    # ---- beam outlines from the rebar plans K-12 / K-22 (tools/extract_rebar.py -> rebar.json): they show every beam with
    # both edge lines and its ends, so they replace the K-400 stipple strips (which are shared between beams / cut short) ----
    RB = J('data/structure/rebar.json') if os.path.exists(os.path.join(ROOT, 'data/structure/rebar.json')) else {'beams': []}
    rmap = {'K-12': 'K-11', 'K-22': 'K-21'}
    rebar_note = []
    for rb in RB['beams']:
        if rb['sheet'] not in rmap or not rb.get('axisITM'): continue
        sheet = rmap[rb['sheet']]
        same = [b for b in beams if b['id'] == rb['id'] and b['sheet'] == sheet]
        if same:
            b = same[0]
            for extra in same[1:]: beams.remove(extra)            # the same beam picked from two stipple strips
            if len(same) > 1: rebar_note.append(f"{rb['id']}: {len(same)} רשומות אוחדו")
        else:
            b = {'id': rb['id'], 'sheet': sheet, 'width_m': rb['width_m'], 'depth_m': rb['depth_m'], 'topRel': rb['topRel'],
                 'bottomRel': r3(rb['topRel'] - rb['depth_m']),
                 'source': f"{SD_REBAR[rb['sheet']]} " + (f"{rb.get('label')}" if rb.get('label') else f"תווית {rb['id']} ({round(rb['width_m'] * 100)}/{round(rb['depth_m'] * 100)}; O.K={rb['topRel']:+.2f})")}
            if rb.get('label'): b.update(numbered=False, label=rb['label'])
            beams.append(b)
        old_len = math.dist(*b['axisITM']) if b.get('axisITM') else None
        b['axisITM'] = rb['axisITM']
        b['geometrySource'] = f"{SD_REBAR[rb['sheet']]} – שני קווי השפה של הקורה וקצותיה (מתאר אפור)" + (f"; {rb['note']}" if rb.get('note') else '')
        b['status'] = rb['status']
        b.pop('note', None); b.pop('matchDistance_pt', None)
        if old_len is not None and abs(old_len - rb['length_m']) > 0.1:
            rebar_note.append(f"{rb['id']}: {old_len:.2f} ← {rb['length_m']:.2f} מ'")
        elif old_len is None:
            rebar_note.append(f"{rb['id']}: חדש / בלי ציר קודם – {rb['length_m']:.2f} מ'")
        ax = LineString(b['axisITM'])
        b['overBasement'] = bsm.buffer(0.15).intersection(ax).length / max(ax.length, 1e-6) > 0.6
        if sheet == 'K-21':
            b['stage'] = 'slab'
            b['layer'] = 'ceilingBeams' if b['overBasement'] else 'groundFloorBeams'
        else:
            b['stage'] = 'groundBeams'; b['layer'] = 'groundBeams'
    # a K-11 "slab" face that is really a beam band (B-32 = BS4 0.22 wide): drop it
    rb_polys = [LineString(b['axisITM']).buffer(b['width_m'] / 2 + 0.03, cap_style=2) for b in beams if b.get('axisITM') and b['sheet'] == 'K-11']
    dropped = [s_['id'] for s_ in slabs if s_['status'] == 'missing' and any(Polygon(s_['outlineITM']).intersection(g).area > 0.7 * Polygon(s_['outlineITM']).area for g in rb_polys)]
    slabs = [s_ for s_ in slabs if s_['id'] not in dropped]
    if dropped: rebar_note.append(f"הוסר {', '.join(dropped)} – רצועת קורה, לא רצפה")
    print('rebar outlines:', rebar_note)
    cc = close_beam_corners([b for b in beams if b['sheet'] == 'K-21'])
    if cc: rebar_note.append('פינות L נסגרו: ' + ', '.join(cc))
    print('closed corners K-21', cc)

    # ---- double pile caps (K-400: rectangle under the tag "80/60; O.K=-0.15" around two piles, detail "ראש כלונס כפול") ----
    pg = pymupdf.open(os.path.join(ROOT, K400))[0]
    rect_lines = []
    for d in pg.get_drawings():
        col = d.get('color')
        if not col or max(col) > 0.05 or round(d.get('width') or 0, 2) != 0.51: continue
        for it in d['items']:
            if it[0] == 'l': rect_lines.append((it[1].x, it[1].y, it[2].x, it[2].y))
    caps = []
    for blk in pg.get_text('dict')['blocks']:
        for l in blk.get('lines', []):
            txt = ''.join(sp['text'] for sp in l['spans']).strip()
            m = re.match(r'^(\d+)/(\d+); O\.K=([+-]\d\.\d+)$', txt)
            if not m: continue
            bb = l['bbox']; cx = (bb[0] + bb[2]) / 2
            # top edge of the cap: a horizontal line just under the tag, spanning its centre
            tops = [q for q in rect_lines if abs(q[1] - q[3]) < 0.2 and 0 < q[1] - bb[3] < 12 and min(q[0], q[2]) < cx < max(q[0], q[2])]
            if not tops: continue
            tl = min(tops, key=lambda q: q[1] - bb[3]); y0 = tl[1]; x0, x1 = sorted((tl[0], tl[2]))
            sides = [q for q in rect_lines if abs(q[0] - q[2]) < 0.2 and min(q[1], q[3]) - 0.5 <= y0 and abs(q[0] - x0) < 0.5]
            if not sides: continue
            y1 = max(max(q[1], q[3]) for q in sides)
            ring = [sheet2itm(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            poly = Polygon(ring)
            inside = [p_ for p_ in piles['piles'] if poly.contains(Point(p_['E'], p_['N']))]
            if len(inside) < 2: continue
            top = float(m[3]); depth = int(m[2]) / 100
            heads = sorted({p_['headRel'] for p_ in inside})
            ok = all(abs(h - (top - depth)) < 0.01 for h in heads)
            caps.append({'id': 'PC' + '-'.join(p_['id'] for p_ in inside), 'piles': [p_['id'] for p_ in inside], 'ringITM': [[r3(x), r3(y)] for x, y in ring],
                         'width_m': int(m[1]) / 100, 'depth_m': depth, 'topRel': top, 'bottomRel': r3(top - depth),
                         'size_m': [r3((x1 - x0) / PT), r3((y1 - y0) / PT)], 'pileHeads': heads, 'status': 'source' if ok else 'provisional',
                         'note': 'ראש כלונס כפול – ראשי הכלונסאות בתחתית הראש (-0.75) כמו בטבלה' if ok else
                                 f"התווית {txt} לא מתאימה לראשי הכלונסאות שבתוך המלבן ({', '.join(f'{h:+.2f}' for h in heads)}) – לשאלה לקונסטרוקטור",
                         'source': f'{K400} מלבן מתחת לתווית "{txt}" (pt {round(cx)},{round(bb[1])}) + "פרט ראש כלונס כפול קוטר60"'})
    print('pile caps', [(c['id'], c['size_m'], c['topRel'], c['bottomRel'], c['status']) for c in caps])

    # external waterproofing of the basement walls (Avihai's note 2): no detail in the sources – a provisional band on the
    # outer face of the basement outline, from the wall bottom to the wall top (tools/earthworks.json waterproofing)
    EW = json.load(open(os.path.join(ROOT, 'tools/earthworks.json'), encoding='utf-8'))['waterproofing']
    bo = Polygon(basement['outlineITM']).buffer(0)
    band = bo.buffer(EW['displayThickness_m'], join_style=2).difference(bo)
    bwall = [w for w in walls if w.get('bottomRel') is not None]
    wp = {'ringITM': [[r3(a), r3(b)] for a, b in band.exterior.coords[:-1]], 'holesITM': [[[r3(a), r3(b)] for a, b in i.coords[:-1]] for i in band.interiors],
          'bottomRel': min(w['bottomRel'] for w in bwall), 'topRel': max(w['topRel'] for w in bwall), 'area_m2': r3(bo.length * (max(w['topRel'] for w in bwall) - min(w['bottomRel'] for w in bwall))),
          'perimeter_m': r3(bo.length), 'layers': EW['layers'], 'status': 'provisional', 'source': EW['source']}
    out = {'placement': placement, 'basementWalls': walls, 'waterproofing': wp, 'slabs': slabs, 'groundBeams': beams, 'pileCaps': caps, 'rebarChanges': rebar_note,
           'unmatchedStipple': {'count': len(unmatched), 'note': 'פסי נקודות ב-K-400 שלא שויכו לתווית קורה (בעיקר בתוך ראשי כלונס רחבים) – לא שורטטו'},
           'floorTags': {'k11': [{'top': t['top'], 'D': t['thickness_m'], 'itm': [r3(v) for v in t['itm']]} for t in tags11],
                         'k21': [{'top': t['top'], 'D': t['thickness_m'], 'itm': [r3(v) for v in t['itm']]} for t in tags21]},
           'status': 'provisional',
           'note': 'חילוץ מ-PDF/DXF עד קבלת קובץ IFC מהקונסטרוקטור (open-issues). מיקום קורות לפי פסי הבטון ב-K-400 – בקירוב.'}
    with open(os.path.join(ROOT, 'data/structure/framing.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('placement', json.dumps(placement))
    print('walls', len(walls), 'wall top', wall_top, 'slabs', [(s['id'], s['area_m2'], s['top'], s['thickness_m']) for s in slabs])
    print('beams', [(b['id'], b.get('topRel'), b.get('depth_m'), b['status'], b.get('matchDistance_pt'), b.get('stage')) for b in beams]); print('unmatched strips', len(unmatched))


if __name__ == '__main__':
    main()

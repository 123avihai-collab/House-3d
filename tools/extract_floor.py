#!/usr/bin/env python3
"""Stage 3 – floor skeleton -> data/structure/floor-ground.json (run: python3 tools/extract_floor.py).

Ground floor = what rises from the ground-floor slab (k-21.dxf: IfcWall / IfcColumn hatches = elements cut above the level)
plus the ground-floor slab itself (k-21 IfcSlab faces + Floor Tags), and the ground-floor ceiling = the first-floor slab
(k-31.dxf IfcSlab faces + Floor Tags) with its beams (K-31 PDF: beam tags "B-xx" + "w/h; O.K=…" and the two edge lines of
each beam). All Revit sheets share one coordinate system: k-21 placement from data/structure/framing.json is reused for
k-31 (checked: columns 4 and 5 coincide to 0.1 mm); the K-31 PDF is placed on the K-400 sheet by ICP against the k-31 DXF.
"""
import json, math, os, re, sys
from collections import Counter
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_framing as F
import pymupdf
from shapely.geometry import Polygon, LineString, Point, box, MultiPoint
from shapely.ops import unary_union, voronoi_diagram

ROOT = F.ROOT; r3 = F.r3
K21, K31 = F.K21, 'sources/structure/k-31.dxf'
K31P = "sources/structure/K-31-תוכנית קומה א' - גיאומטריה.pdf"
K31P_CLIP = (650, 100, 1850, 1200)
PLOT = 'data/site/plot-5187.json'
ring = lambda g: [[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]]
holes = lambda g: [[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in g.interiors]
polys = lambda g: [q for q in getattr(g, 'geoms', [g]) if q.geom_type == 'Polygon' and not q.is_empty]


def placement():
    t = json.load(open(os.path.join(ROOT, 'data/structure/framing.json'), encoding='utf-8'))['placement']['k21dxf']['translation_pt']
    sheet = lambda x, y: (x * F.S_CM + t[0], -y * F.S_CM + t[1])
    return t, sheet, (lambda x, y: F.sheet2itm(*sheet(x, y)))


def hatches(m, layer, to):
    out = []
    for h in m.query(f'HATCH[layer=="{layer}"]'):
        for p in h.paths:
            vs = [(v[0], v[1]) for v in p.vertices] if hasattr(p, 'vertices') else [(e.start[0], e.start[1]) for e in p.edges if e.EDGE_TYPE == 'LineEdge']
            if len(vs) >= 3: out.append(Polygon([to(*v) for v in vs]).buffer(0))
    return polys(unary_union([q.buffer(0.002) for q in out]).buffer(-0.002))


def hatches_of(h, to):
    out = []
    for p in h.paths:
        vs = [(v[0], v[1]) for v in p.vertices] if hasattr(p, 'vertices') else [(e.start[0], e.start[1]) for e in p.edges if e.EDGE_TYPE == 'LineEdge']
        if len(vs) >= 3: out += polys(Polygon([to(*v) for v in vs]).buffer(0))
    return out


def tag_texts(m, layer, to):
    return [(to(e.dxf.insert.x, e.dxf.insert.y), e.plain_text().strip()) for e in m.query(f'MTEXT[layer=="{layer}"]')]


def slab_faces(m, to, bridge=0.3):
    """Slab panels: IfcSlab edges are broken where walls / columns sit on them, so the wall and column outlines are added
    as edges; remaining dangling ends closer than `bridge` are joined. Faces = holes of the buffered line work."""
    segs = []
    for L in ('IfcSlab', 'IfcWall', 'IfcColumn'):
        segs += [(to(e.dxf.start.x, e.dxf.start.y), to(e.dxf.end.x, e.dxf.end.y)) for e in m.query(f'LINE[layer=="{L}"]')]
    for e in m.query('ARC[layer=="IfcSlab"]'):
        P = [to(p.x, p.y) for p in e.flattening(0.5)]; segs += list(zip(P[:-1], P[1:]))
    k = lambda p: (round(p[0], 3), round(p[1], 3))
    deg = Counter()
    for a, b in segs: deg[k(a)] += 1; deg[k(b)] += 1
    dang = [p for p, n in deg.items() if n == 1]
    used, add = set(), []
    for d, i, j in sorted((math.dist(a, b), i, j) for i, a in enumerate(dang) for j, b in enumerate(dang) if i < j):
        if d > bridge or i in used or j in used: continue
        used |= {i, j}; add.append((dang[i], dang[j]))
    U = unary_union([LineString(s).buffer(0.015, cap_style=2) for s in segs] + [LineString(s).buffer(0.015) for s in add])
    H = [Polygon(r) for g in polys(U) for r in g.interiors]
    out = []
    # a face may contain islands (e.g. the pool inside the deck): remove the line work and the faces nested in it
    for i, f in enumerate(H):
        inner = [h for j, h in enumerate(H) if j != i and h.area < f.area and f.contains(h.representative_point())]
        g = f.difference(U).difference(unary_union(inner)) if inner else f
        out += [q.buffer(0.015, join_style=2) for q in polys(g) if q.area > 0.01]
    return out


def tagged_panels(faces, tags, min_area=0.5):
    """faces carrying floor tags; a face with several different tags is split between them (Voronoi of the tag points)."""
    out = []
    for f in faces:
        tg = [t for t in tags if f.contains(Point(t['itm']))]
        if not tg or f.area < min_area: continue
        vals = {(t['top'], t['thickness_m']) for t in tg}
        if len(vals) == 1:
            top, d = vals.pop(); out.append({'poly': f, 'top': top, 'D': d, 'split': False}); continue
        vor = voronoi_diagram(MultiPoint([t['itm'] for t in tg]), envelope=f.buffer(5))
        for cell in vor.geoms:
            t = next(t for t in tg if cell.contains(Point(t['itm'])))
            for q in polys(cell.intersection(f)):
                out.append({'poly': q, 'top': t['top'], 'D': t['thickness_m'], 'split': True})
    # merge neighbouring panels with the same level
    merged = []
    for key in {(p['top'], p['D']) for p in out}:
        grp = [p for p in out if (p['top'], p['D']) == key]
        for q in polys(unary_union([p['poly'].buffer(0.02, join_style=2) for p in grp]).buffer(-0.02, join_style=2)):
            merged.append({'poly': q, 'top': key[0], 'D': key[1], 'split': any(p['split'] and p['poly'].intersects(q) for p in grp)})
    return merged


def num_near(c, texts, pat=r'^\d+$', k=4):
    near = sorted(texts, key=lambda t: math.dist(t[0], (c.x, c.y)))[:k]
    return [t[1] for t in near if re.match(pat, t[1])]


def pdf_lines(path, clip, t):
    p = pymupdf.open(os.path.join(ROOT, path))[0]; H, V = [], []
    for d in p.get_drawings():
        for it in d['items']:
            if it[0] != 'l': continue
            a, b = it[1], it[2]
            if not (clip[0] < a.x < clip[2] and clip[1] < a.y < clip[3]): continue
            if abs(a.y - b.y) < 0.05 and abs(a.x - b.x) > 3: H.append((a.y + t[1], min(a.x, b.x) + t[0], max(a.x, b.x) + t[0]))
            elif abs(a.x - b.x) < 0.05 and abs(a.y - b.y) > 3: V.append((a.x + t[0], min(a.y, b.y) + t[1], max(a.y, b.y) + t[1]))
    return H, V


def merge_collinear(L, gap=2.0):
    out = []
    for c in sorted({round(l[0], 1) for l in L}):
        iv = sorted((l[1], l[2]) for l in L if abs(l[0] - c) < 0.06)
        cur = list(iv[0])
        for a, b in iv[1:]:
            if a <= cur[1] + gap: cur[1] = max(cur[1], b)
            else: out.append((c, *cur)); cur = [a, b]
        out.append((c, *cur))
    return out


def beam_geometry(tag, H, V, S_CM):
    """the two parallel edge lines of the beam nearest its tag: spacing = beam width, overlap containing the tag"""
    w = tag['w_cm'] * S_CM; x, y = tag['tagSheetXY']
    L, (al, pe) = (H, (x, y)) if tag['axis'] == 'h' else (V, (y, x))
    best = None
    for i, a in enumerate(L):
        if abs(a[0] - pe) > 40: continue
        for b in L:
            if not (abs((b[0] - a[0]) - w) < 0.7): continue
            lo, hi = max(a[1], b[1]), min(a[2], b[2])
            if hi - lo < 10 or not (lo - 15 <= al <= hi + 15): continue
            d = abs((a[0] + b[0]) / 2 - pe)
            if best is None or d < best[0]: best = (d, (a[0] + b[0]) / 2, lo, hi)
    return best


def main():
    t, sheet, to = placement()
    m21, m31 = F.read_dxf(K21), F.read_dxf(K31)
    lot = Polygon(json.load(open(os.path.join(ROOT, PLOT), encoding='utf-8'))['ring'])
    pool_sel = json.load(open(os.path.join(ROOT, 'tools/pool-pieces.json'), encoding='utf-8'))
    pool_pts = [Point(*p) for k in ('pool', 'channel', 'tank') for p in pool_sel[k]]
    pool = json.load(open(os.path.join(ROOT, 'data/structure/pool.json'), encoding='utf-8'))
    pool_zone = unary_union([Polygon(pool['gutter']['ringOuterITM']), Polygon(pool['channel']['outerITM']), Polygon(pool['tank']['pitITM'])]).buffer(0.05)

    # ---- check: k-31 shares the k-21 coordinates (identical columns) ----
    c21, c31 = hatches(m21, 'IfcColumn', to), hatches(m31, 'IfcColumn', to)
    shared = [min(a.centroid.distance(b.centroid) for b in c21) for a in c31]
    same_coords = sorted(shared)[:2]

    # ---- ground-floor slab (k-21) ----
    tags21 = F.floor_tags(m21, sheet)
    faces21 = slab_faces(m21, to)
    panels21 = tagged_panels(faces21, tags21)
    # the slab over the basement (= basement ceiling) carries no floor tag of its own in K-21 (DXF and PDF alike):
    # it takes the tag nearest the basement – the same assumption as the basement wall tops in framing.json (stage 2b)
    bsm = Polygon(json.load(open(os.path.join(ROOT, 'data/structure/basement.json'), encoding='utf-8'))['outlineITM'])
    near_b = min(tags21, key=lambda tg: bsm.centroid.distance(Point(tg['itm'])))
    for f in faces21:
        if f.area > 1 and not any(f.contains(Point(tg['itm'])) for tg in tags21) and bsm.buffer(0.3).contains(f.representative_point()) \
                and f.intersection(bsm).area > 0.6 * f.area:
            panels21.append({'poly': f, 'top': near_b['top'], 'D': near_b['thickness_m'], 'split': False, 'untagged': True})
    # the slab runs on over the walls below (thin strips between panels of the same level): close gaps up to 0.30 m
    def close(panels, gap=0.15):
        out = []
        for key in {(p['top'], p['D']) for p in panels}:
            grp = [p for p in panels if (p['top'], p['D']) == key]
            for q in polys(unary_union([p['poly'].buffer(gap, join_style=2) for p in grp]).buffer(-gap, join_style=2)):
                src = [p for p in grp if p['poly'].intersects(q)]
                out.append({'poly': q, 'top': key[0], 'D': key[1], 'split': any(p['split'] for p in src),
                            'untagged': any(p.get('untagged') for p in src)})
        return out
    panels21 = close(panels21)
    # walls standing on a slab cut thin holes in its faces: the slab runs on under them -> fill wall-shaped holes
    def fill_thin(panels):
        for p in panels:
            q = p['poly']
            keep = [r for r in q.interiors if 2 * Polygon(r).area / Polygon(r).length > 0.35 or Polygon(r).area > 6]
            p['poly'] = Polygon(q.exterior, keep)
        return panels
    panels21 = fill_thin(panels21)
    # ---- first-floor slab = ground-floor ceiling (k-31) ----
    tags31 = F.floor_tags(m31, sheet)
    faces31 = slab_faces(m31, to)
    panels31 = fill_thin(close(tagged_panels(faces31, tags31)))
    # stair opening: K-31 PDF draws it as a rectangle crossed by one diagonal (symbol); the face of the DXF line work
    # stays open toward the landing, so the opening is taken from that diagonal (rectangle on the building axes)
    tp = F.icp(F.pdf_endpoints(K31P, K31P_CLIP), np.unique(np.round(np.array(
        [sheet(e.dxf.start.x, e.dxf.start.y) for e in m31.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcSlab', 'IfcColumn')] +
        [sheet(e.dxf.end.x, e.dxf.end.y) for e in m31.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcSlab', 'IfcColumn')]), 2), axis=0))
    t31p = tp[1]
    page = pymupdf.open(os.path.join(ROOT, K31P))[0]
    diag = []
    for d in page.get_drawings():
        for it in d['items']:
            if it[0] != 'l': continue
            a, b = it[1], it[2]
            if not (K31P_CLIP[0] < a.x < K31P_CLIP[2] and K31P_CLIP[1] < a.y < K31P_CLIP[3]): continue
            dx, dy = abs(a.x - b.x), abs(a.y - b.y)
            if dx > 40 and dy > 40 and 0.6 < dx / dy < 1.6: diag.append(((a.x + t31p[0], a.y + t31p[1]), (b.x + t31p[0], b.y + t31p[1])))
    openings = []
    for (a, b) in diag:
        rect = box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        g = Polygon([F.sheet2itm(x, y) for x, y in list(rect.exterior.coords)[:-1]])
        hit = [p for p in panels31 if p['poly'].buffer(-0.05).contains(g.centroid)]
        if hit and g.area < 30: openings.append(g)
    cut = []
    for p in panels31:
        g_ = p['poly']
        for g in openings:
            if g_.contains(g.centroid): g_ = g_.difference(g)
        cut += [dict(p, poly=q) for q in polys(g_) if q.area > 0.3]
    panels31 = cut

    def level_at(panels, q, default=None):
        # walls / columns sit on the panel edges (the faces exclude their footprints): take the panel that overlaps most
        # with the element grown by 0.5 m
        g = q.buffer(0.5, join_style=2)
        hit = max(panels, key=lambda p: p['poly'].intersection(g).area)
        return (hit['top'], hit['D']) if hit['poly'].intersection(g).area > 0.02 else default

    # ---- walls rising from the ground floor ----
    # k-21 hatches are incomplete (e.g. W3, W7, W8 have no hatch), so the walls are the thin faces of the IfcWall line
    # work. Legend of the sheet: diagonal hatch = wall/column that continues up ("צומח"); grey fill (SOLID hatch) = wall that
    # stops at this level ("מפסיק" – the tops of the basement / light-well walls) -> not a ground-floor wall.
    # line type "Beton Ole" (בטון עולה = rising concrete) marks the outlines of the walls that continue up; walls below the
    # slab / stopping walls are drawn with other line types and are not taken
    RISE = 'Beton Ole'
    WL = [LineString([to(e.dxf.start.x, e.dxf.start.y), to(e.dxf.end.x, e.dxf.end.y)]) for e in m21.query('LINE[layer=="IfcWall"]') if e.dxf.linetype == RISE]
    for e in m21.query('ARC[layer=="IfcWall"]'):
        if e.dxf.linetype == RISE: WL.append(LineString([to(q.x, q.y) for q in e.flattening(0.5)]))
    from shapely.ops import polygonize
    thin = [f for f in polygonize(unary_union(WL)) if f.area > 0.02 and 0.08 <= 2 * f.area / f.length <= 0.35]
    grey = unary_union([q for h in m21.query('HATCH[layer=="IfcWall"]') if h.dxf.pattern_name == 'SOLID'
                        for q in hatches_of(h, to)]) if True else None
    # one piece per face of the line work; faces split along their length by an inner line (two halves of one wall)
    # are merged: shared edge longer than a third of the piece's perimeter
    par = list(range(len(thin)))
    def find(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    for i in range(len(thin)):
        for j in range(i + 1, len(thin)):
            if thin[i].distance(thin[j]) > 0.005: continue
            sh = thin[i].buffer(0.005).intersection(thin[j].buffer(0.005)).length / 2
            if sh > min(thin[i].length, thin[j].length) / 3: par[find(i)] = find(j)
    grp = {}
    for i in range(len(thin)): grp.setdefault(find(i), []).append(thin[i])
    W = [q for g in grp.values() for q in polys(unary_union([x.buffer(0.003, join_style=2) for x in g]).buffer(-0.003, join_style=2))]
    wtags = tag_texts(m21, 'Wall Tags', to)
    walls, perimeter, stopping = [], [], []
    for q in W:
        if any(q.buffer(0.03).contains(p) for p in pool_pts) or pool_zone.contains(q.representative_point()): continue
        near_lot = q.intersection(lot.exterior.buffer(0.6)).area / q.area
        if near_lot > 0.7: perimeter.append(q); continue
        if q.intersection(grey).area > 0.5 * q.area: stopping.append(q); continue
        walls.append(q)
    cols = hatches(m21, 'IfcColumn', to)
    ctags = tag_texts(m21, 'Structural Column Tags', to)

    def vertical(q, kind):
        c = q.centroid
        bot = level_at(panels21, q)
        top = level_at(panels31, q)
        rec = {'bottomRel': bot[0] if bot else None, 'topRel': r3(top[0] - top[1]) if top else None}
        st, notes = 'source', []
        if bot is None:
            near = min(tags21, key=lambda tg: c.distance(Point(tg['itm'])))
            rec['bottomRel'] = near['top']; st = 'provisional'; notes.append(f'תחתית: לא על רצפת הקרקע – לפי תגית הרצפה הקרובה ({near["top"]:+.2f})')
        if top is None:
            main = max(panels31, key=lambda p: p['poly'].area)
            rec['topRel'] = r3(main['top'] - main['D']); st = 'provisional'
            notes.append('ראש: אין תקרת K-31 מעל (חלל כפול / חוץ) – זמנית בתחתית תקרת +3.70; הגובה האמיתי לפי K-41 (שלב 3ג)')
        rec.update(status=st)
        if notes: rec['note'] = '; '.join(notes)
        return rec

    walls = sorted(walls, key=lambda g: -g.area)
    wtag_of = {}
    for (xy, txt) in wtags:
        if not re.match(r'^\d+$', txt): continue
        k = min(range(len(walls)), key=lambda i: walls[i].distance(Point(xy)))
        if walls[k].distance(Point(xy)) < 2.0 and (k not in wtag_of or walls[k].distance(Point(xy)) < wtag_of[k][1]):
            wtag_of[k] = (f'W{txt}', walls[k].distance(Point(xy)))
    wall_out = []
    for i, q in enumerate(walls):
        mr = q.minimum_rotated_rectangle; xy = list(mr.exterior.coords)
        th = min(math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2]))
        if th > 0.45: th = 2 * q.area / q.length   # L / T shaped piece: mean width
        tag = wtag_of.get(i, (None,))[0]
        rec = {'id': f'GW{i + 1}', 'tag': tag, 'footprintITM': ring(q), 'holesITM': holes(q), 'area_m2': r3(q.area), 'thickness_m': r3(th)}
        rec.update(vertical(q, 'wall'))
        rec['source'] = f'{K21} HATCH IfcWall' + (f' (תווית {tag})' if tag else '') + f'; מפלסים: {K21}/{K31} Floor Tags'
        wall_out.append(rec)
    col_out = []
    for q in cols:
        mr = q.minimum_rotated_rectangle; xy = list(mr.exterior.coords)
        a_, b_ = sorted([math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2])])
        near = sorted(ctags, key=lambda tt: math.dist(tt[0], (q.centroid.x, q.centroid.y)))[:4]
        nums = [x[1] for x in near if re.match(r'^\d+$', x[1])]
        # tag = "<no>" + "<w>" "/" "<h>": the two size numbers are the ones matching the hatch, the remaining one is the column no.
        size = (round(a_ * 100), round(b_ * 100))
        no = next((n for n in nums if int(n) not in size), None)
        rec = {'id': f'C{no}' if no else f'C?{len(col_out) + 1}', 'footprintITM': ring(q), 'size_cm': list(size),
               'tagSize_cm': sorted(int(n) for n in nums if int(n) in size)[:2]}
        rec.update(vertical(q, 'column'))
        rec['source'] = f'{K21} HATCH IfcColumn + Structural Column Tags; מפלסים: {K21}/{K31} Floor Tags'
        col_out.append(rec)

    # ---- K-31 beams: tags + edge lines in the K-31 PDF ----
    H, V = pdf_lines(K31P, K31P_CLIP, t31p)
    H, V = merge_collinear(H), merge_collinear(V)
    btags = F.pdf_beam_tags(K31P, t31p)
    beams = []
    for bt in btags:
        g = beam_geometry(bt, H, V, F.S_CM)
        rec = {'id': bt['id'], 'width_m': bt['w_cm'] / 100, 'depth_m': bt['h_cm'] / 100, 'topRel': bt['top'],
               'bottomRel': r3(bt['top'] - bt['h_cm'] / 100), 'tagITM': [r3(v) for v in F.sheet2itm(*bt['tagSheetXY'])],
               'source': f"{K31P} תווית {bt['id']} ({bt['w_cm']}/{bt['h_cm']}; O.K={bt['top']:+.2f}) + שני קווי השפה של הקורה"}
        if g:
            d, c, lo, hi = g
            a, b = ((lo, c), (hi, c)) if bt['axis'] == 'h' else ((c, lo), (c, hi))
            rec.update(axisITM=[[r3(v) for v in F.sheet2itm(*a)], [r3(v) for v in F.sheet2itm(*b)]], length_m=r3((hi - lo) / F.PT),
                       tagDistance_pt=r3(d), status='source')
        else:
            rec.update(axisITM=None, status='missing', note='לא נמצאו שני קווי שפה ברוחב הקורה ליד התווית – לא שורטטה')
        beams.append(rec)
    seen = set(); beams = [b for b in beams if not (b['id'] in seen or seen.add(b['id']))]

    out = {
        'floor': 'ground',
        'placement': {'k31dxf': 'k21dxf translation (same Revit coordinates)', 'k31_vs_k21_columns_m': [r3(v) for v in same_coords],
                      'K31pdf': {'translation_pt': [r3(v) for v in t31p], 'inlierFraction': r3(tp[0]), 'medianResidual_pt': r3(tp[2])}},
        'slab': [{'id': f'GS{i + 1}', 'footprintITM': ring(p['poly']), 'holesITM': holes(p['poly']), 'area_m2': r3(p['poly'].area),
                  'topRel': p['top'], 'thickness_m': p['D'], 'bottomRel': r3(p['top'] - p['D']),
                  'status': 'provisional' if p.get('untagged') else 'approx' if p['split'] else 'source',
                  'note': ' '.join(x for x in [
                      'גבול בין מפלסים לא שורטט בקווי הרצפה – חולק בין התגיות (בקירוב).' if p['split'] else '',
                      'החלק שמעל המרתף (תקרת המרתף) בלי תגית רצפה ב-K-21 – לפי התגית הקרובה (כמו ראש קירות המרתף בשלב 2ב).' if p.get('untagged') else ''] if x),
                  'source': f"{K21} IfcSlab + קווי קירות/עמודים; Floor Tag O.K={p['top']:+.2f} D={round(p['D'] * 100)}"}
                 for i, p in enumerate(sorted(panels21, key=lambda p: -p['poly'].area))],
        'walls': wall_out, 'columns': col_out,
        'stoppingWalls': {'count': len(stopping), 'note': 'קירות "מפסיקים" במפלס הקרקע (מילוי אפור ב-K-21: ראשי קירות המרתף / החצרות האנגליות) – שייכים למרתף, לא שורטטו כאן.'},
        'perimeterWallsPending': {'count': len(perimeter), 'note': 'חומות היקפיות (חלקי IfcWall לאורך גבול המגרש ב-k-21) – ייבנו בצעד "חומות" אחרי אישור שלד הקרקע.'},
        'ceiling': {
            'slab': [{'id': f'FS{i + 1}', 'footprintITM': ring(p['poly']), 'holesITM': holes(p['poly']), 'area_m2': r3(p['poly'].area),
                      'topRel': p['top'], 'thickness_m': p['D'], 'bottomRel': r3(p['top'] - p['D']),
                      'status': 'approx' if p['split'] else 'source',
                      'source': f"{K31} IfcSlab + קווי קירות/עמודים; Floor Tag O.K={p['top']:+.2f} D={round(p['D'] * 100)}"}
                     for i, p in enumerate(sorted(panels31, key=lambda p: -p['poly'].area))],
            'openings': [{'footprintITM': ring(g), 'area_m2': r3(g.area), 'kind': 'stair', 'source': f'{K31P} – מלבן עם אלכסון (סימון פתח)'} for g in openings],
            'beams': beams,
        },
        'source': f'{K21}; {K31}; {K31P}',
    }
    json.dump(out, open(os.path.join(ROOT, 'data/structure/floor-ground.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('k31 vs k21 columns', [r3(v) for v in same_coords], 'K31pdf', [r3(v) for v in t31p], r3(tp[0]), r3(tp[2]))
    print('ground slab', [(s['id'], s['topRel'], s['area_m2'], s['status']) for s in out['slab']])
    print('walls', [(w['id'], w['tag'], w['thickness_m'], w['bottomRel'], w['topRel'], w['status']) for w in wall_out])
    print('columns', [(c['id'], c['size_cm'], c['tagSize_cm'], c['bottomRel'], c['topRel'], c['status']) for c in col_out])
    print('perimeter pieces', len(perimeter))
    print('ceiling slab', [(s['id'], s['topRel'], s['thickness_m'], s['area_m2']) for s in out['ceiling']['slab']], 'openings', [o['area_m2'] for o in out['ceiling']['openings']])
    print('beams', [(b['id'], b['width_m'], b['depth_m'], b['topRel'], b.get('length_m'), b['status']) for b in beams])


if __name__ == '__main__':
    main()

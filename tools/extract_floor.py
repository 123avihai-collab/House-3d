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
from shapely.ops import unary_union, voronoi_diagram, split

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


def slab_faces(m, to, bridge=0.3, extend=0.0, snap=1.2):
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
    # a slab edge that stops short of the next line (T-junction hidden under a wall / tag): extend it along its own
    # direction to the first line it meets, up to `extend` m
    if extend:
        allL = unary_union([LineString(s) for s in segs])
        for a, b in [s for s in segs if k(s[0]) in set(dang) - {k(p) for i in used for p in [dang[i]]} or k(s[1]) in set(dang) - {k(p) for i in used for p in [dang[i]]}]:
            for p, q in ((a, b), (b, a)):
                if deg[k(p)] != 1 or any(k(p) == k(dang[i]) for i in used): continue
                L = math.dist(p, q)
                if L < 1e-6: continue
                u = ((p[0] - q[0]) / L, (p[1] - q[1]) / L)
                ray = LineString([(p[0] + u[0] * 1e-3, p[1] + u[1] * 1e-3), (p[0] + u[0] * extend, p[1] + u[1] * extend)])
                hit = ray.intersection(allL)
                if not hit.is_empty:
                    pts = [g for g in getattr(hit, 'geoms', [hit])]
                    d = min(Point(p).distance(g) for g in pts)
                    add.append((p, (p[0] + u[0] * (d + 0.005), p[1] + u[1] * (d + 0.005)))); continue
                # no line ahead: join the nearest corner of another edge (open slab end next to a corner)
                cand = [v for v in deg if math.dist(v, p) < snap and k(v) != k(q) and k(v) != k(p)]
                if cand: add.append((p, min(cand, key=lambda v: math.dist(v, p))))
    U = unary_union([LineString(s).buffer(0.015) for s in segs + add])   # round caps: no hairline gaps at corners
    # faces = every region enclosed by the line work (complement of the buffered lines, minus the outside region);
    # islands (e.g. the pool inside the deck) are cut out automatically
    bb = box(*U.bounds).buffer(1.0)
    regions = polys(bb.difference(U))
    return [q.buffer(0.015, join_style=2) for q in regions if q.area > 0.01 and not q.intersects(bb.exterior.buffer(0.5))]


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


def close(panels, gap=0.15):
    """merge same-level panels separated by thin strips (walls standing on one continuous slab)"""
    out = []
    for key in {(p['top'], p['D']) for p in panels}:
        grp = [p for p in panels if (p['top'], p['D']) == key]
        for q in polys(unary_union([p['poly'].buffer(gap, join_style=2) for p in grp]).buffer(-gap, join_style=2)):
            out.append({'poly': q, 'top': key[0], 'D': key[1], 'split': any(p['split'] for p in grp if p['poly'].intersects(q))})
    return out


def fill_thin(panels):
    """walls standing on a slab cut thin holes in its faces: the slab runs on under them"""
    for p in panels:
        q = p['poly']
        p['poly'] = Polygon(q.exterior, [r for r in q.interiors if 2 * Polygon(r).area / Polygon(r).length > 0.35 or Polygon(r).area > 6])
    return panels


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

    # ---- ground-floor slab (k-21): panels = faces of the drawn line work, one level each, sorted into zones ----
    # (no merging across drawn lines, no guessed boundaries: house, terraces, yards, parking, courtyards stay apart)
    tags21 = F.floor_tags(m21, sheet)
    faces21 = [f for f in slab_faces(m21, to) if f.area > 0.3]
    ZN = json.load(open(os.path.join(ROOT, 'tools/ground-zones.json'), encoding='utf-8'))
    FR = json.load(open(os.path.join(ROOT, 'data/structure/framing.json'), encoding='utf-8'))
    beams21 = [b for b in FR['groundBeams'] if b['sheet'] == 'K-21' and b.get('axisITM')]
    lvl = lambda f: {(t['top'], t['thickness_m']) for t in tags21 if f.contains(Point(t['itm']))}

    def split_levels(f):
        """a face holding two levels: the step between them is not drawn – it runs along a K-21 beam (framing.json);
        split along the beam axis (extended across the face); untagged pieces go back to their longest neighbour"""
        if len(lvl(f)) <= 1: return [(f, None)]
        for b in beams21:
            (x1, y1), (x2, y2) = b['axisITM']; L = math.dist((x1, y1), (x2, y2)); ux, uy = (x2 - x1) / L, (y2 - y1) / L
            ext = LineString([(x1 - ux * 30, y1 - uy * 30), (x2 + ux * 30, y2 + uy * 30)])
            pieces = polys(split(f, ext))
            if len(pieces) < 2: continue
            tagged = [q for q in pieces if lvl(q)]
            if any(len(lvl(q)) > 1 for q in tagged) or len({frozenset(lvl(q)) for q in tagged}) < 2: continue
            for q in [q for q in pieces if not lvl(q)]:
                nb = max(tagged, key=lambda r: r.buffer(0.01).intersection(q.buffer(0.01)).area)
                tagged[tagged.index(nb)] = nb.union(q.buffer(0.005)).buffer(-0.005)
            return [(q, b['id']) for q in tagged]
        return [(f, 'unsplit')]

    pieces = [x for f in faces21 for x in split_levels(f)]
    zone_of = lambda q: next((z for z, Z in ZN['zones'].items() if any(q.contains(Point(*pt)) for pt in Z['points'])), None)
    # mamad (shelter): K-21 / K-31 draw it as a square crossed by one diagonal + "ראה תכנית הג\"א מאושרת"
    K21P_T = FR['placement']['K21pdf']['translation_pt']
    def diag_rects(pdf, clip, tt):
        page = pymupdf.open(os.path.join(ROOT, pdf))[0]; out = []
        for d in page.get_drawings():
            for it in d['items']:
                if it[0] != 'l': continue
                a, b = it[1], it[2]
                if not (clip[0] < a.x < clip[2] and clip[1] < a.y < clip[3]): continue
                dx, dy = abs(a.x - b.x), abs(a.y - b.y)
                if dx > 40 and dy > 40 and 0.6 < dx / dy < 1.6:
                    r = box(min(a.x, b.x) + tt[0], min(a.y, b.y) + tt[1], max(a.x, b.x) + tt[0], max(a.y, b.y) + tt[1])
                    g = Polygon([F.sheet2itm(x, y) for x, y in list(r.exterior.coords)[:-1]])
                    if 4 < g.area < 30: out.append(g)
        return out
    mamad21 = [g for g in diag_rects(F.K21P, (1650, 150, 3100, 1700), K21P_T)
               if any(zone_of(q) == 'house' and q.intersection(g).area > 0.5 * g.area for q, _ in pieces)]
    bsm = Polygon(json.load(open(os.path.join(ROOT, 'data/structure/basement.json'), encoding='utf-8'))['outlineITM'])
    near_b = min(tags21, key=lambda tg: bsm.centroid.distance(Point(tg['itm'])))
    panels21, open21, unclassified = [], [], []
    for q, how in pieces:
        z = zone_of(q)
        if z is None:
            if q.area > 1 and not pool_zone.contains(q.representative_point()) and 2 * q.area / q.length > 0.35:
                unclassified.append(q)
            continue
        Z = ZN['zones'][z]
        if not Z['slab']: open21.append({'poly': q, 'zone': z}); continue
        lv = lvl(q)
        if len(lv) == 1:
            top, D = lv.pop(); st = 'source'; note = ''
        else:
            top, D = near_b['top'], near_b['thickness_m']; st = 'provisional'
            note = 'חלק מהרצפה בלי תגית מפלס ב-K-21 (DXF ו-PDF) – לפי התגית הקרובה למרתף (‎-0.15, כמו ראש קירות המרתף בשלב 2ב).'
        if how not in (None, 'unsplit'):
            note += f' הגבול בין המפלסים לא שורטט – לאורך ציר הקורה {how} (מיקום הקורה מ-K-400, בקירוב).'; st = 'approx' if st == 'source' else st
        panels21.append({'poly': q, 'top': top, 'D': D, 'zone': z, 'status': st, 'note': note.strip()})
    # house: the panels of the rooms meet at the walls standing on the slab – the slab runs on under them
    house = [p for p in panels21 if p['zone'] == 'house']
    rest = [p for p in panels21 if p['zone'] != 'house']
    merged = []
    for key in {(p['top'], p['D']) for p in house}:
        grp = [p for p in house if (p['top'], p['D']) == key]
        for q in polys(unary_union([p['poly'].buffer(0.15, join_style=2) for p in grp]).buffer(-0.15, join_style=2)):
            src = [p for p in grp if p['poly'].intersects(q)]
            q = Polygon(q.exterior, [r for r in q.interiors if 2 * Polygon(r).area / Polygon(r).length > 0.35 and Polygon(r).area > 0.3])
            worst = 'provisional' if any(p['status'] == 'provisional' for p in src) else 'approx' if any(p['status'] == 'approx' for p in src) else 'source'
            merged.append({'poly': q, 'top': key[0], 'D': key[1], 'zone': 'house', 'status': worst,
                           'note': ' '.join(sorted({p['note'] for p in src if p['note']}))})
    # mamad: its floor is per the approved shelter plan (missing) – cut out of the house slab, kept as its own panel
    for g in mamad21:
        for p in merged:
            if p['poly'].intersects(g):
                inside = p['poly'].intersection(g)
                p['poly'] = polys(p['poly'].difference(g))[0] if len(polys(p['poly'].difference(g))) == 1 else max(polys(p['poly'].difference(g)), key=lambda x: x.area)
                for q in polys(inside):
                    if q.area > 1: rest.append({'poly': q, 'top': p['top'], 'D': p['D'], 'zone': 'mamad', 'status': 'provisional',
                                                'note': 'ממ"ד – "ראה תכנית הג\"א מאושרת" (K-21). מפלס ועובי לפי תוכנית הג"א, שלא הועלתה – זמני כמו רצפת הבית.'})
    panels21 = merged + rest
    # ---- first-floor slab = ground-floor ceiling (k-31) ----
    tags31 = F.floor_tags(m31, sheet)
    faces31 = slab_faces(m31, to)
    panels31 = fill_thin(close(tagged_panels(faces31, tags31)))
    # the square crossed by a diagonal with "ראה תכנית הג\"א מאושרת" is the mamad (shelter), not an opening: its ceiling
    # (and floor) follow the approved shelter plan, which is missing – the slab is kept and the mamad is marked
    tp = F.icp(F.pdf_endpoints(K31P, K31P_CLIP), np.unique(np.round(np.array(
        [sheet(e.dxf.start.x, e.dxf.start.y) for e in m31.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcSlab', 'IfcColumn')] +
        [sheet(e.dxf.end.x, e.dxf.end.y) for e in m31.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcSlab', 'IfcColumn')]), 2), axis=0))
    t31p = tp[1]
    mamad31 = [g for g in diag_rects(K31P, K31P_CLIP, t31p) if any(p['poly'].buffer(0.1).contains(g.centroid) for p in panels31)]
    # the mamad square is open toward the landing in the DXF line work: fill it into the slab it sits in
    for g in mamad31:
        for p in panels31:
            if p['poly'].buffer(0.1).contains(g.centroid): p['poly'] = polys(p['poly'].union(g).buffer(0.01, join_style=2).buffer(-0.01, join_style=2))[0]

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
        'slab': [{'id': f'GS{i + 1}', 'zone': p['zone'], 'zoneLabel': 'ממ"ד' if p['zone'] == 'mamad' else ZN['zones'][p['zone']]['label'],
                  'footprintITM': ring(p['poly']), 'holesITM': holes(p['poly']), 'area_m2': r3(p['poly'].area),
                  'topRel': p['top'], 'thickness_m': p['D'], 'bottomRel': r3(p['top'] - p['D']), 'status': p['status'], 'note': p['note'],
                  'source': f"{K21} IfcSlab + קווי קירות/עמודים (פאה משורטטת); Floor Tag O.K={p['top']:+.2f} D={round(p['D'] * 100)}; אזור: {ZN['source']}"}
                 for i, p in enumerate(sorted(panels21, key=lambda p: -p['poly'].area))],
        'openZones': [{'zone': o['zone'], 'label': ZN['zones'][o['zone']]['label'], 'note': ZN['zones'][o['zone']]['note'],
                       'footprintITM': ring(o['poly']), 'area_m2': r3(o['poly'].area), 'source': f"{K21} (קווים); {ZN['source']}"} for o in open21],
        'unclassifiedFaces': [{'footprintITM': ring(q), 'area_m2': r3(q.area)} for q in unclassified],
        'walls': wall_out, 'columns': col_out,
        'stoppingWalls': {'count': len(stopping), 'note': 'קירות "מפסיקים" במפלס הקרקע (מילוי אפור ב-K-21: ראשי קירות המרתף / החצרות האנגליות) – שייכים למרתף, לא שורטטו כאן.'},
        'perimeterWallsPending': {'count': len(perimeter), 'note': 'חומות היקפיות (חלקי IfcWall לאורך גבול המגרש ב-k-21) – ייבנו בצעד "חומות" אחרי אישור שלד הקרקע.'},
        'ceiling': {
            'slab': [{'id': f'FS{i + 1}', 'footprintITM': ring(p['poly']), 'holesITM': holes(p['poly']), 'area_m2': r3(p['poly'].area),
                      'topRel': p['top'], 'thickness_m': p['D'], 'bottomRel': r3(p['top'] - p['D']),
                      'status': 'approx' if p['split'] else 'source',
                      'source': f"{K31} IfcSlab + קווי קירות/עמודים; Floor Tag O.K={p['top']:+.2f} D={round(p['D'] * 100)}"}
                     for i, p in enumerate(sorted(panels31, key=lambda p: -p['poly'].area))],
            'openings': [],
            'mamad': [{'footprintITM': ring(g), 'area_m2': r3(g.area), 'status': 'missing',
                       'note': 'ממ"ד – "ראה תכנית הג\"א מאושרת": עובי ומפלס התקרה לפי תוכנית הג"א (לא הועלתה). התקרה מוצגת כמו התקרה הסמוכה.',
                       'source': f'{K31P} – ריבוע עם אלכסון + "ראה תכנית הג\"א מאושרת"'} for g in mamad31],
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
    print('ceiling slab', [(s['id'], s['topRel'], s['thickness_m'], s['area_m2']) for s in out['ceiling']['slab']], 'mamad', [o['area_m2'] for o in out['ceiling']['mamad']])
    print('zones', [(x['id'], x['zone'], x['topRel'], x['area_m2'], x['status']) for x in out['slab']])
    print('open', [(o['zone'], o['area_m2']) for o in out['openZones']], 'unclassified', [u['area_m2'] for u in out['unclassifiedFaces']])
    print('beams', [(b['id'], b['width_m'], b['depth_m'], b['topRel'], b.get('length_m'), b['status']) for b in beams])


if __name__ == '__main__':
    main()

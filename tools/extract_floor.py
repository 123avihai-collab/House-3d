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
K21, K31, K11, K41 = F.K21, 'sources/structure/k-31.dxf', F.K11, 'sources/structure/k-41.dxf'
K41P = 'sources/structure/K-41-תוכנית קומה גג - גיאומטריה.pdf'
K41P_CLIP = (200, 150, 1350, 1200)
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


def clip_to_beams(panels, beams):
    """A floor slab never runs past its edge beams: clip to the frame of the beams (building axes). Drops faces closed by
    leader / section-cut lines outside the plan, and the part of an absorbed column that stands out of the slab edge."""
    from shapely import affinity
    th = F.G['theta_rad']
    rects = [LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2) for b in beams if b.get('axisITM')]
    fr = affinity.rotate(box(*affinity.rotate(unary_union(rects), -th, origin=(0, 0), use_radians=True).bounds), th, origin=(0, 0), use_radians=True)
    for p in panels: p['poly'] = p['poly'].intersection(fr).buffer(0)
    return [p for p in panels if p['poly'].area > 0.05]


def pdf_grey(path, t, shades=(0.74, 0.81)):
    """grey solid fill of a structural sheet ("קיר מפסיק" – wall that stops at this level = the wall below) -> ITM"""
    p = pymupdf.open(os.path.join(ROOT, path))[0]; out = []
    for d in p.get_drawings():
        f = d.get('fill')
        if f is None or not all(shades[0] <= c <= shades[1] for c in f) or max(f) - min(f) > 0.01: continue   # neutral grey only
        rings, cur = [], []
        for it in d['items']:          # one path may hold several sub-shapes: a new one starts where the pen jumps
            if it[0] == 'l':
                a, b = (it[1].x, it[1].y), (it[2].x, it[2].y)
                if cur and math.dist(cur[-1], a) > 0.05: rings.append(cur); cur = []
                if not cur: cur.append(a)
                cur.append(b)
            elif it[0] == 're':
                R = it[1]; rings.append([(R.x0, R.y0), (R.x1, R.y0), (R.x1, R.y1), (R.x0, R.y1)])
        if cur: rings.append(cur)
        for rg in rings:
            if len(rg) >= 3:
                g = Polygon([F.sheet2itm(x + t[0], y + t[1]) for x, y in rg]).buffer(0)
                if g.area > 0.01: out.append(g)
    return unary_union(out)


def arch_band(floor):
    """the architect's walls of a floor (Revit plan in the plumbing DXF, placed by tools/extract_openings.place), ±13 cm"""
    import ezdxf, extract_openings as O
    blk, dxf, _, _ = O.FLOORS[floor]
    ents, to_itm, _ = O.place(ezdxf.readfile(os.path.join(ROOT, O.SRC)).modelspace(), blk, dxf)
    return unary_union([LineString([to_itm(v.dxf.start.x, v.dxf.start.y), to_itm(v.dxf.end.x, v.dxf.end.y)]) for v in ents
                        if v.dxftype() == 'LINE' and v.dxf.layer in ('A-WALL', 'I-WALL', 'S-STRS', 'S-STRS-MBND')]).buffer(0.13)


def below_slab(path, t):
    """walls under the slab of a structural sheet: grey fill (stops at the slab) ∪ light hatch fill (continues up)"""
    return pdf_grey(path, t).union(pdf_grey(path, t, shades=(0.93, 0.97)))


def keep_in(pieces, region):
    """a floor's concrete walls = the wall pieces the sheet of the slab ABOVE draws under it (grey / hatched); outlines
    only on the sheet of the floor itself (block walls drawn for reference) are dropped"""
    kept, dropped = [], []
    for q in pieces:
        r = q.intersection(region.buffer(0.05))
        parts = [x for x in polys(r) if x.area > 0.03 and 2 * x.area / x.length > 0.06]
        if q.area - sum(x.area for x in parts) > 0.02: dropped.append({'areaRemoved_m2': r3(q.area - sum(x.area for x in parts)), 'centroidITM': [r3(v) for v in q.centroid.coords[0]]})
        kept += parts
    return kept, dropped


def drop_below(pieces, grey, arch):
    """remove from the wall pieces of a floor what the sheet fills grey (wall below, stopping at the level) and the architect
    does not have on that floor; returns (kept pieces, removed areas)"""
    cut = grey.difference(arch)
    kept, removed = [], []
    for q in pieces:
        r = q.difference(cut.buffer(0.02))
        lost = q.area - r.area
        parts = [x for x in polys(r) if x.area > 0.05 and 2 * x.area / x.length > 0.06]
        if lost > 0.02: removed.append({'areaRemoved_m2': r3(lost), 'centroidITM': [r3(v) for v in q.centroid.coords[0]]})
        kept += parts
    return kept, removed


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


def rising_wall_pieces(m, to):
    """walls that continue up from a level: thin faces of the IfcWall lines drawn with line type "Beton Ole" (בטון עולה);
    faces split along their length by an inner line are merged. Returns (pieces, grey) – grey = SOLID hatches (walls that
    stop at this level, "מפסיק")."""
    from shapely.ops import polygonize
    RISE = 'Beton Ole'
    WL = [LineString([to(e.dxf.start.x, e.dxf.start.y), to(e.dxf.end.x, e.dxf.end.y)]) for e in m.query('LINE[layer=="IfcWall"]') if e.dxf.linetype == RISE]
    for e in m.query('ARC[layer=="IfcWall"]'):
        if e.dxf.linetype == RISE: WL.append(LineString([to(q.x, q.y) for q in e.flattening(0.5)]))
    thin = [f for f in polygonize(unary_union(WL)) if f.area > 0.02 and 0.08 <= 2 * f.area / f.length <= 0.35] if WL else []
    grey = unary_union([q for h in m.query('HATCH[layer=="IfcWall"]') if h.dxf.pattern_name == 'SOLID' for q in hatches_of(h, to)])
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
    return [q for g in grp.values() for q in polys(unary_union([x.buffer(0.003, join_style=2) for x in g]).buffer(-0.003, join_style=2))], grey


def mark_pergola(beams, panels):
    """a beam with no slab on either side carries no floor: a pergola beam (open frame, e.g. over a terrace).
    An edge beam has the slab on one side."""
    slab = unary_union([p['poly'] for p in panels])
    for b in beams:
        if not b.get('axisITM'): continue
        L = LineString(b['axisITM'])
        sides = [L.buffer(sgn * (b['width_m'] / 2 + 0.4), single_sided=True, cap_style=2) for sgn in (1, -1)]
        cov = [slab.intersection(sd).area / max(sd.area, 1e-6) for sd in sides]
        b['pergola'] = max(cov) < 0.3


def col_tag(q, ctags):
    """column tag = "<no>" over "<w>" "/" "<h>" as separate texts: the nearest number below 15 is the column no.; the
    section = the two numbers from 15 up nearest to that number text (the tag is a compact group around it)"""
    c = (q.centroid.x, q.centroid.y)
    num = [(x[0], int(x[1])) for x in ctags if re.match(r'^\d+$', x[1])]
    nos = sorted((math.dist(p, c), p, n) for p, n in num if n < 15)
    if not nos: return None, []
    _, p0, no = nos[0]
    sz = [n for d, n in sorted((math.dist(p, p0), n) for p, n in num if n >= 15)[:2]]
    return no, sorted(sz)


def beam_tags_all(path, t):
    """every beam section tag "w/h; O.K=±x.xx" of the sheet, with the beam number next to it when there is one
    (some beams of K-31 – around the mamad and the stair hall – carry a section tag without a number)"""
    p = pymupdf.open(os.path.join(ROOT, path))[0]; L = []
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            L.append((''.join(sp['text'] for sp in l['spans']).strip(), l['bbox']))
    ids = [(txt, bb) for txt, bb in L if re.match(r'^B-\d+$', txt)]
    out, used = [], set()
    for txt, bb in L:
        m = re.match(r'^(\d+)/(\d+); O\.K=([+-]\d\.\d+)', txt)
        if not m: continue
        vert = (bb[3] - bb[1]) > (bb[2] - bb[0])
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        near = sorted((math.dist(((i[1][0] + i[1][2]) / 2, (i[1][1] + i[1][3]) / 2), (cx, cy)), k) for k, i in enumerate(ids) if k not in used)
        if near and near[0][0] < 45:
            k = near[0][1]; used.add(k); name = ids[k][0]; ib = ids[k][1]
            cx, cy = (cx + (ib[0] + ib[2]) / 2) / 2, (cy + (ib[1] + ib[3]) / 2) / 2
        else:
            name = f"B-?{m[1]}/{m[2]}@{round(cx)},{round(cy)}"
        out.append({'id': name, 'w_cm': int(m[1]), 'h_cm': int(m[2]), 'top': float(m[3]), 'tagSheetXY': (cx + t[0], cy + t[1]),
                    'axis': 'v' if vert else 'h', 'numbered': not name.startswith('B-?')})
    return out


def beam_geometry(tag, H, V, S_CM):
    """the two parallel edge lines of the beam nearest its tag: spacing = beam width, overlap containing the tag"""
    w = tag['w_cm'] * S_CM; x, y = tag['tagSheetXY']
    L, (al, pe) = (H, (x, y)) if tag['axis'] == 'h' else (V, (y, x))
    best = None
    for i, a in enumerate(L):
        if abs(a[0] - pe) > 50: continue
        for b in L:
            if not (abs((b[0] - a[0]) - w) < 0.7): continue
            lo, hi = max(a[1], b[1]), min(a[2], b[2])
            if hi - lo < 10 or not (lo - 25 <= al <= hi + 25): continue
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
    W, grey = rising_wall_pieces(m21, to)
    wtags = tag_texts(m21, 'Wall Tags', to)
    walls, perimeter, stopping = [], [], []
    for q in W:
        if any(q.buffer(0.03).contains(p) for p in pool_pts) or pool_zone.contains(q.representative_point()): continue
        near_lot = q.intersection(lot.exterior.buffer(0.6)).area / q.area
        if near_lot > 0.7: perimeter.append(q); continue
        if q.intersection(grey).area > 0.5 * q.area: stopping.append(q); continue
        walls.append(q)
    # walls the sheet fills grey (stopping = basement walls below) and the architect's ground plan does not have
    walls, removed21 = drop_below(walls, pdf_grey(F.K21P, K21P_T), arch_band('ground'))
    walls, notUnder31 = keep_in(walls, below_slab(K31P, t31p))      # not drawn under the +3.70 slab in K-31 -> not a concrete wall
    removed21 += notUnder31
    print('ground: not under K-31', notUnder31)
    print('ground: removed below-walls', removed21)
    cols = hatches(m21, 'IfcColumn', to)
    ctags = tag_texts(m21, 'Structural Column Tags', to)

    # what a wall / column stands on (construction order: basement walls up to the slab underside -> ground beams + slab
    # poured over them -> walls and columns from the top of the beam / slab under them)
    beam_polys = [(LineString(x['axisITM']).buffer(x['width_m'] / 2, cap_style=2), x) for x in FR['groundBeams']
                  if x['sheet'] == 'K-21' and x.get('axisITM')]
    bw_polys = [(Polygon(w['footprintITM'], w['holesITM']).buffer(0), w) for w in FR['basementWalls']]
    bands = []          # slab strips under walls standing over a basement wall (the slab runs on over the wall top)
    unsupported = []

    def vertical(q, kind):
        q = q.buffer(0); c = q.centroid
        frac = lambda P: q.intersection(P).area / q.area
        slab_u = unary_union([p['poly'] for p in panels21] + [x['poly'] for x in bands])
        unc = q.difference(slab_u)
        sup, notes, st = [], [], 'source'
        # over a basement wall but outside the drawn slab faces: the slab continues over the wall (same level as the
        # house slab next to it) – add that strip to the slab
        if unc.area > 0.25 * q.area:
            bw = [w for P, w in bw_polys if unc.intersection(P).area > 0.5 * unc.area]
            near = [p for p in panels21 if p['zone'] in ('house', 'mamad', 'entry') and p['poly'].distance(q) < 0.6]
            if bw and near:
                p0 = min(near, key=lambda p: p['poly'].distance(q))
                bands.append({'poly': unc, 'top': p0['top'], 'D': p0['D'], 'zone': p0['zone'], 'over': bw[0]['id']})
                notes.append(f"עומד מעל קיר המרתף {bw[0]['id']} – רצפת הקרקע ממשיכה מעליו (רצועה בעובי הרצפה נוספה)")
        for p in panels21 + bands:
            if frac(p['poly']) > 0.25: sup.append((p['top'], f"רצפה {p['zone']}"))
        for P, x in beam_polys:
            if frac(P) > 0.25: sup.append((x['topRel'], f"קורה {x['id']} ({round(x['width_m'] * 100)}/{round(x['depth_m'] * 100)}, O.K {x['topRel']:+.2f})"))
        top = level_at(panels31, q)
        rec = {'topRel': r3(top[0] - top[1]) if top else None}
        if sup:
            b0 = max(sup, key=lambda t: t[0])
            rec['bottomRel'] = b0[0]; rec['standsOn'] = b0[1]
            if b0[1].startswith('קורה') and b0[0] > max([t[0] for t in sup if t[1].startswith('רצפה')] or [-9]) + 0.01:
                notes.append(f'יושב על קורה הפוכה {b0[1]} – מתחיל מראש הקורה')
        else:
            near = min(tags21, key=lambda tg: c.distance(Point(tg['itm'])))
            rec['bottomRel'] = near['top']; rec['standsOn'] = None; st = 'provisional'; unsupported.append(c)
            notes.append(f'אין במקורות אלמנט נושא מתחתיו (קורה / קיר מרתף / רצפה) – תחתית לפי תגית הרצפה הקרובה ({near["top"]:+.2f}); חסרה כנראה קורה ב-K-21 (IFC)')
        if top is None:
            main = max(panels31, key=lambda p: p['poly'].area)
            rec['topRel'] = r3(main['top'] - main['D']); st = 'provisional'
            notes.append('ראש: אין תקרת K-31 מעל (חלל כפול / חוץ) – זמנית בתחתית תקרת +3.70; הגובה האמיתי לפי K-41 (שלב 3ד)')
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
        size = (round(a_ * 100), round(b_ * 100))
        no, tsz = col_tag(q, ctags)
        rec = {'id': f'C{no}' if no else f'C?{len(col_out) + 1}', 'footprintITM': ring(q), 'size_cm': list(size), 'tagSize_cm': tsz}
        rec.update(vertical(q, 'column'))
        rec['source'] = f'{K21} HATCH IfcColumn + Structural Column Tags; מפלסים: {K21}/{K31} Floor Tags'
        col_out.append(rec)

    # the strips over the basement walls join the house slab next to them (one pour)
    for bd in bands:
        tgt = min([p for p in panels21 if p['zone'] == bd['zone'] and (p['top'], p['D']) == (bd['top'], bd['D'])],
                  key=lambda p: p['poly'].distance(bd['poly']))
        g = unary_union([tgt['poly'].buffer(0.01, join_style=2), bd['poly'].buffer(0.01, join_style=2)]).buffer(-0.01, join_style=2)
        tgt['poly'] = max(polys(g), key=lambda x: x.area) if polys(g) else tgt['poly']
        tgt['bands'] = tgt.get('bands', 0) + 1
    for p in panels21:
        if p.get('bands'): p['note'] = (p['note'] + f" כולל {p['bands']} רצועות מעל קירות המרתף שמתחת לקירות הקרקע.").strip()
    # strips left between the house panels (over the basement walls below, where no ground wall stands): the slab is one
    # pour over the whole house – close gaps up to 0.6 m, never into courtyards / stairs down / outdoor slabs / the mamad
    keep_out = unary_union([o['poly'] for o in open21] + [p['poly'] for p in panels21 if p['zone'] != 'house'] + [pool_zone])
    for p in [p for p in panels21 if p['zone'] == 'house']:
        mam = unary_union([x['poly'] for x in panels21 if x['zone'] == 'mamad'])
        g = unary_union([p['poly'], mam]).buffer(0.3, join_style=2).buffer(-0.3, join_style=2).difference(keep_out)
        g = max(polys(g), key=lambda x: x.area)
        added = g.area - p['poly'].area
        p['poly'] = Polygon(g.exterior, [r for r in g.interiors if 2 * Polygon(r).area / Polygon(r).length > 0.3])
        if added > 0.05: p['note'] = (p['note'] + f' רצועות בין חלקי הרצפה (מעל קירות המרתף) מולאו – {added:.1f} מ"ר.').strip()
    # walls that stop at the ground level (grey fill in K-21 = tops of the basement / light-well walls): the basement wall
    # rises to the level of the ground slab next to it
    caps = []
    for g in polys(grey):
        if g.area < 0.05 or pool_zone.contains(g.representative_point()): continue
        bw = [w for P, w in bw_polys if g.intersection(P).area > 0.3 * g.area]
        adj = [p for p in panels21 if p['poly'].distance(g) < 0.3]
        if not bw or not adj: continue
        topc = max(p['top'] for p in adj)
        if topc <= bw[0]['topRel'] + 0.005: continue
        caps.append({'footprintITM': ring(g), 'holesITM': holes(g), 'area_m2': r3(g.area), 'bottomRel': bw[0]['topRel'], 'topRel': topc,
                     'wall': bw[0]['id'], 'status': 'provisional',
                     'note': f"קיר מרתף שמסתיים במפלס הקרקע (מילוי אפור ב-K-21 = 'מפסיק'): ממשיך מראש {bw[0]['id']} ({bw[0]['topRel']:+.2f}) עד מפלס הרצפה הצמודה ({topc:+.2f}). גובה מדויק – IFC.",
                     'source': f'{K21} HATCH IfcWall SOLID (קיר מפסיק); {K11} (קיר המרתף)'})

    # ---- K-31 beams: tags + edge lines in the K-31 PDF ----
    H, V = pdf_lines(K31P, K31P_CLIP, t31p)
    H, V = merge_collinear(H), merge_collinear(V)
    btags = beam_tags_all(K31P, t31p)
    Hd, Vd = merge_collinear(pdf_lines(K31P, K31P_CLIP, t31p)[0], gap=8.0), merge_collinear(pdf_lines(K31P, K31P_CLIP, t31p)[1], gap=8.0)
    beams = []
    for bt in btags:
        # flush / hidden beams are drawn dashed: retry with dashes joined
        g = beam_geometry(bt, H, V, F.S_CM) or beam_geometry(bt, Hd, Vd, F.S_CM)
        rec = {'id': bt['id'] if bt['numbered'] else f"קורה ללא מספר {bt['w_cm']}/{bt['h_cm']}", 'numbered': bt['numbered'], 'width_m': bt['w_cm'] / 100, 'depth_m': bt['h_cm'] / 100, 'topRel': bt['top'],
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
    mark_pergola(beams, panels31)

    # the slab runs on under the walls and columns that stand on it, and the ceiling runs on over the ones that carry it:
    # the drawn faces stop at their outlines, which leaves notches / holes at every column and wall -> absorb them
    def absorb(panels, elems, zones=None):
        n = 0
        for g in elems:
            g = g.buffer(0)
            cand = [p for p in panels if (zones is None or p.get('zone') in zones) and p['poly'].distance(g) < 0.05]
            if not cand: continue
            tgt = max(cand, key=lambda p: p['poly'].buffer(0.05, join_style=2).intersection(g).area)
            u = unary_union([tgt['poly'].buffer(0.005, join_style=2), g.buffer(0.005, join_style=2)]).buffer(-0.005, join_style=2)
            tgt['poly'] = max(polys(u), key=lambda x: x.area); n += 1
        return n
    elems21 = [Polygon(c['footprintITM']) for c in col_out] + [Polygon(w['footprintITM'], w['holesITM']) for w in wall_out]
    n21 = absorb(panels21, elems21)
    # thin strips of the K-21 line work between slab panels (the faces of the beams the slab edges stop at): the slab /
    # beam concrete is continuous there -> into the neighbouring panel (the house first)
    openU = unary_union([o['poly'] for o in open21] + [pool_zone])
    strips = [f for f in faces21 if 2 * f.area / f.length <= 0.35 and f.area > 0.05 and not f.intersects(openU.buffer(-0.02))
              and sum(1 for p in panels21 if p['poly'].distance(f) < 0.05) >= 2
              and f.intersection(lot.exterior.buffer(0.6)).area < 0.3 * f.area]   # not the perimeter walls (later step)
    for f in strips:
        cand = [p for p in panels21 if p['poly'].distance(f) < 0.05]
        house = [p for p in cand if p['zone'] in ('house', 'mamad', 'entry')]
        tgt = max(house or cand, key=lambda p: p['poly'].buffer(0.05, join_style=2).intersection(f).area)
        u = unary_union([tgt['poly'].buffer(0.005, join_style=2), f.buffer(0.005, join_style=2)]).buffer(-0.005, join_style=2)
        tgt['poly'] = max(polys(u), key=lambda x: x.area)
    print('beam strips filled', len(strips))
    for p in panels21:   # holes the columns / walls left inside a panel
        q = p['poly']; p['poly'] = Polygon(q.exterior, [r for r in q.interiors if not any(Polygon(r).buffer(0.02).intersects(e) for e in elems21)])
    elems31 = elems21 + hatches(m31, 'IfcColumn', to)
    n31 = absorb(panels31, elems31)
    panels31 = clip_to_beams(fill_thin(close(panels31, gap=0.35)), beams)   # K-31 overall 1702 x 1465 (column 9 stands 35 cm out)
    print('absorbed into slabs: ground', n21, 'ceiling', n31)
    # owner corrections to the zone slabs (tools/ground-zones.json "slabCuts")
    for cut in ZN.get('slabCuts', []):
        cp = Polygon(cut['ringITM']).buffer(0)
        for p in panels21:
            if p['zone'] == cut['zone'] and p['poly'].intersection(cp).area > 0.01:
                p['poly'] = max(polys(p['poly'].difference(cp)), key=lambda g: g.area); p['note'] = (p.get('note', '') + ' ' + cut['note']).strip()

    out = {
        'floor': 'ground',
        'wallsRemovedAsBelow': {'items': removed21, 'note': 'חלקי קירות שב-K-21 ממולאים אפור ("מפסיק" = קיר המרתף שמתחת) ואין להם קיר בתוכנית האדריכל של הקרקע – הוסרו.'},
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
        'basementWallCaps': caps,
        # K-21 beam -> zone of the slab it carries (most of its length under that zone): beams of the outdoor slabs are cast
        # with them (construction step "outdoorSlabs"), not with the house slab
        # a beam that carries a house wall / column is cast with the house, whatever slab is next to it
        'beamZones': {x['id']: ('house' if any((e.get('standsOn') or '').startswith(f"קורה {x['id']} ") for e in wall_out + col_out)
                                else max(panels21, key=lambda p: p['poly'].intersection(P.buffer(0.3)).area)['zone'])
                      for P, x in beam_polys if max(p['poly'].intersection(P.buffer(0.3)).area for p in panels21) > 0.05},
        'unsupportedCount': len(unsupported),
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

    # ---- first floor: columns rising from the K-31 slab (hatched in k-31 = cut above the level) up to the K-41 roof slab ----
    m41 = F.read_dxf(K41)
    t41 = F.icp(F.pdf_endpoints(K41P, K41P_CLIP), np.unique(np.round(np.array(
        [sheet(e.dxf.start.x, e.dxf.start.y) for e in m41.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcSlab', 'IfcColumn')] +
        [sheet(e.dxf.end.x, e.dxf.end.y) for e in m41.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcSlab', 'IfcColumn')]), 2), axis=0))
    tags41 = F.floor_tags(m41, sheet)
    panels41 = fill_thin(close(tagged_panels(slab_faces(m41, to), tags41)))
    cols31 = hatches(m31, 'IfcColumn', to); ctags31 = tag_texts(m31, 'Structural Column Tags', to)
    beam31 = [(LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2), b) for b in beams if b.get('axisITM')]
    first_cols = []
    for q in cols31:
        mr = q.minimum_rotated_rectangle; xy = list(mr.exterior.coords)
        size = tuple(round(v * 100) for v in sorted([math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2])]))
        no, tag_size = col_tag(q, ctags31)
        sup = [(p['top'], f"תקרת הקרקע +{p['top']:.2f}") for p in panels31 if q.intersection(p['poly']).area > 0.25 * q.area]
        # a column standing on a ground-floor column runs on through the slab: continuous from the column below
        sup += [(c['topRel'], f"עמוד {c['id']} של קומת הקרקע (רציף)") for c in col_out if q.intersection(Polygon(c['footprintITM'])).area > 0.25 * q.area]
        sup += [(b['topRel'], f"קורה {b['id']} ({round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)}, O.K {b['topRel']:+.2f})")
                for P, b in beam31 if q.intersection(P).area > 0.25 * q.area]
        top = level_at(panels41, q)
        notes, st = [], 'source'
        if sup: bot, on = max(sup, key=lambda x: x[0])
        else:
            bot, on, st = max(panels31, key=lambda p: p['poly'].area)['top'], None, 'provisional'
            notes.append('אין במקורות אלמנט נושא מתחתיו – תחתית במפלס תקרת הקרקע')
        if top is None:
            main = max(panels41, key=lambda p: p['poly'].area); top = (main['top'], main['D']); st = 'provisional'
            notes.append('אין תקרת K-41 מעליו – ראש זמני בתחתית תקרת הגג הראשית')
        fp = q
        if tag_size and sorted(tag_size) != sorted(size):
            below = [c for c in col_out if q.intersection(Polygon(c['footprintITM'])).area > 0.25 * q.area and sorted(c['size_cm']) == sorted(tag_size)]
            if below:
                fp = Polygon(below[0]['footprintITM']); st = 'approx' if st == 'source' else st
                notes.append(f"משורטט {size[0]}/{size[1]} (חלקו מוסתר בקיר) מול תווית {'/'.join(map(str, tag_size))} – לפי התווית, רציף עם {below[0]['id']} שמתחתיו")
                size = tuple(sorted(tag_size))
            else: notes.append(f'חתך משורטט {size[0]}/{size[1]} מול תווית {"/".join(map(str, tag_size))} – לפי השרטוט')
        first_cols.append({'id': f'C{no}' if no else f'C?{len(first_cols) + 1}', 'footprintITM': ring(fp), 'size_cm': list(size), 'tagSize_cm': tag_size,
                           'bottomRel': bot, 'topRel': r3(top[0] - top[1]), 'standsOn': on, 'status': st, **({'note': '; '.join(notes)} if notes else {}),
                           'source': f'{K31} HATCH IfcColumn + Structural Column Tags; מפלסים: {K31}/{K41} Floor Tags'})
    # ---- first-floor walls (k-31 "Beton Ole" faces) ----
    W31, grey31 = rising_wall_pieces(m31, to)
    wtags31 = tag_texts(m31, 'Wall Tags', to)
    W31 = [q for q in W31 if q.intersection(grey31).area < 0.5 * q.area]
    # K-31 also draws the ground-floor walls under the +3.70 slab (grey fill = "מפסיק"): keep only what rises – walls the
    # sheet fills grey and the architect's first-floor plan does not have are removed
    W31, removed31 = drop_below(W31, pdf_grey(K31P, t31p), arch_band('first'))
    W31, notUnder41 = keep_in(W31, below_slab(K41P, t41[1]))     # not drawn under the roof slab in K-41 -> not a concrete wall
    removed31 += notUnder41
    print('first: not under K-41', notUnder41)
    print('first: removed below-walls', removed31)
    W31 = sorted(W31, key=lambda g: -g.area)
    wtag31 = {}
    for (xy, txt) in wtags31:
        if not re.match(r'^\d+$', txt) or not W31: continue
        k = min(range(len(W31)), key=lambda i: W31[i].distance(Point(xy)))
        if W31[k].distance(Point(xy)) < 2.0 and (k not in wtag31 or W31[k].distance(Point(xy)) < wtag31[k][1]): wtag31[k] = (f'W{txt}', W31[k].distance(Point(xy)))
    first_walls = []
    for i, q in enumerate(W31):
        mr = q.minimum_rotated_rectangle; xy = list(mr.exterior.coords)
        th = min(math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2]))
        if th > 0.45: th = 2 * q.area / q.length
        sup = [(p['top'], f"תקרת הקרקע +{p['top']:.2f}") for p in panels31 if q.intersection(p['poly'].buffer(0.05)).area > 0.25 * q.area]
        sup += [(b['topRel'], f"קורה {b['id']} ({round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)}, O.K {b['topRel']:+.2f})")
                for P, b in beam31 if q.intersection(P).area > 0.25 * q.area]
        sup += [(w['topRel'], f"קיר {w.get('tag') or w['id']} של קומת הקרקע (רציף)") for w in wall_out if q.intersection(Polygon(w['footprintITM'])).area > 0.5 * q.area]
        top = level_at(panels41, q); notes, st = [], 'source'
        if sup: bot, on = max(sup, key=lambda x: x[0])
        else:
            bot, on, st = max(panels31, key=lambda p: p['poly'].area)['top'], None, 'provisional'
            notes.append('אין במקורות אלמנט נושא מתחתיו – תחתית במפלס תקרת הקרקע')
        if top is None:
            main = max(panels41, key=lambda p: p['poly'].area); top = (main['top'], main['D']); st = 'provisional'
            notes.append('אין תקרת גג (K-41) מעליו – ראש זמני בתחתית תקרת הגג')
        tag = wtag31.get(i, (None,))[0]
        first_walls.append({'id': f'FW{i + 1}', 'tag': tag, 'footprintITM': ring(q), 'holesITM': holes(q), 'area_m2': r3(q.area), 'thickness_m': r3(th),
                            'bottomRel': bot, 'topRel': r3(top[0] - top[1]), 'standsOn': on, 'status': st, **({'note': '; '.join(notes)} if notes else {}),
                            'source': f'{K31} IfcWall "Beton Ole"' + (f' (תווית {tag})' if tag else '') + f'; מפלסים: {K31}/{K41} Floor Tags'})
    # ---- roof (K-41): slab + beams (K-41 PDF tags + edge lines; parapet / pergola beams up to +8.00) ----
    H4, V4 = pdf_lines(K41P, K41P_CLIP, t41[1]); H4, V4 = merge_collinear(H4), merge_collinear(V4)
    H4d, V4d = merge_collinear(pdf_lines(K41P, K41P_CLIP, t41[1])[0], gap=8.0), merge_collinear(pdf_lines(K41P, K41P_CLIP, t41[1])[1], gap=8.0)
    roof_beams = []
    for bt in beam_tags_all(K41P, t41[1]):
        g = beam_geometry(bt, H4, V4, F.S_CM) or beam_geometry(bt, H4d, V4d, F.S_CM)
        rec = {'id': bt['id'] if bt['numbered'] else f"קורה ללא מספר {bt['w_cm']}/{bt['h_cm']}", 'numbered': bt['numbered'], 'width_m': bt['w_cm'] / 100,
               'depth_m': bt['h_cm'] / 100, 'topRel': bt['top'], 'bottomRel': r3(bt['top'] - bt['h_cm'] / 100),
               'tagITM': [r3(v) for v in F.sheet2itm(*bt['tagSheetXY'])],
               'source': f"{K41P} תווית {bt['id']} ({bt['w_cm']}/{bt['h_cm']}; O.K={bt['top']:+.2f}) + שני קווי השפה של הקורה"}
        if g:
            d, c, lo, hi = g; a_, b_ = ((lo, c), (hi, c)) if bt['axis'] == 'h' else ((c, lo), (c, hi))
            rec.update(axisITM=[[r3(v) for v in F.sheet2itm(*a_)], [r3(v) for v in F.sheet2itm(*b_)]], length_m=r3((hi - lo) / F.PT), tagDistance_pt=r3(d), status='source')
        else: rec.update(axisITM=None, status='missing', note='לא נמצאו שני קווי שפה ברוחב הקורה ליד התווית – לא שורטטה')
        roof_beams.append(rec)
    seen = set(); roof_beams = [b for b in roof_beams if not (b['id'] in seen or seen.add(b['id']))]
    # roof slab runs on over the first-floor walls and columns that carry it
    absorb(panels41, [Polygon(w['footprintITM'], w['holesITM']) for w in first_walls] + [Polygon(c['footprintITM']) for c in first_cols])
    panels41 = fill_thin(close(panels41, gap=0.35))
    panels41 = clip_to_beams(panels41, roof_beams)   # K-41 overall 1579 x 1497 (stray faces of the B-8 section / tag leader lines)
    mark_pergola(roof_beams, panels41)
    # ground-floor walls / columns in the double height (no +3.70 ceiling above): up to the roof slab
    fixed = 0
    for e in out['walls'] + out['columns']:
        if 'אין תקרת K-31 מעל' not in (e.get('note') or ''): continue
        lv41 = level_at(panels41, Polygon(e['footprintITM']).buffer(0))
        if lv41 is None: continue
        e['topRel'] = r3(lv41[0] - lv41[1]); fixed += 1
        e['note'] = e['note'].replace('ראש: אין תקרת K-31 מעל (חלל כפול / חוץ) – זמנית בתחתית תקרת +3.70; הגובה האמיתי לפי K-41 (שלב 3ד)',
                                      'ראש: בחלל הכפול – עד תחתית תקרת הגג K-41 (+6.65)')
        if 'זמני' not in e['note'] and 'אין במקורות' not in e['note']: e['status'] = 'source'
    if fixed: json.dump(out, open(os.path.join(ROOT, 'data/structure/floor-ground.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('double-height walls up to the roof', fixed)
    roof = {'slab': [{'id': f'RS{i + 1}', 'footprintITM': ring(p['poly']), 'holesITM': holes(p['poly']), 'area_m2': r3(p['poly'].area),
                      'topRel': p['top'], 'thickness_m': p['D'], 'bottomRel': r3(p['top'] - p['D']), 'status': 'source',
                      'source': f"{K41} IfcSlab + קווי קירות/עמודים; Floor Tag O.K={p['top']:+.2f} D={round(p['D'] * 100)}"}
                     for i, p in enumerate(sorted(panels41, key=lambda p: -p['poly'].area))],
            'openings': [], 'mamad': [], 'beams': roof_beams,
            'placement': {'K41pdf': {'translation_pt': [r3(v) for v in t41[1]], 'inlierFraction': r3(t41[0]), 'medianResidual_pt': r3(t41[2])}}}
    # first-floor columns under a roof / pergola beam reach the beam bottom
    beam41 = [(LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2), b) for b in roof_beams if b.get('axisITM')]
    for c in first_cols:
        q = Polygon(c['footprintITM'])
        over = [b for P, b in beam41 if q.intersection(P).area > 0.25 * q.area]
        if over:
            b = max(over, key=lambda b: b['bottomRel'])
            if b['bottomRel'] > c['topRel']:
                c['topRel'] = b['bottomRel']; c['carries'] = b['id']
                c['note'] = (c.get('note', '') + f"; נושא את קורה {b['id']} – ראש העמוד בתחתית הקורה ({b['bottomRel']:+.2f})").strip('; ')
                c['note'] = c['note'].replace('אין תקרת K-41 מעליו – ראש זמני בתחתית תקרת הגג הראשית', '').strip('; ')
                if 'אין במקורות' not in c['note']: c['status'] = 'source'
    # ---- roof: walls above the roof slab (k-41 "Beton Ole": parapets, pergola supports) up to +8.00 – the spot levels
    #      "+8.00 / +6.65" written next to them in K-41 – and the K-41 beams on top of them (parapet / pergola beams) ----
    pg41 = pymupdf.open(os.path.join(ROOT, K41P))[0]
    spots = [Point(F.sheet2itm((w[0] + w[2]) / 2 + t41[1][0], (w[1] + w[3]) / 2 + t41[1][1])) for w in pg41.get_text('words') if w[4] == '+8.00']
    W41, grey41 = rising_wall_pieces(m41, to)
    roof_walls = []
    for i, q in enumerate(sorted([q for q in W41 if q.intersection(grey41).area < 0.5 * q.area], key=lambda g: -g.area)):
        mr = q.minimum_rotated_rectangle; xy = list(mr.exterior.coords)
        th = min(math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2]))
        if th > 0.45: th = 2 * q.area / q.length
        sup = [(p['top'], f"תקרת הגג +{p['top']:.2f}") for p in panels41 if q.intersection(p['poly'].buffer(0.05)).area > 0.25 * q.area]
        sup += [(w['topRel'], f"קיר {w.get('tag') or w['id']} של קומה א' (רציף)") for w in first_walls if q.intersection(Polygon(w['footprintITM'])).area > 0.25 * q.area]
        sup += [(c['topRel'], f"עמוד {c['id']} של קומה א' (רציף)") for c in first_cols if q.intersection(Polygon(c['footprintITM'])).area > 0.25 * q.area]
        notes, st = [], 'source'
        if not sup:
            # outside the roof slab (façade band / pergola edge): K-41 writes "+8.00 / +6.65" next to its walls – the band
            # between the roof-slab underside (+6.65) and the parapet top (+8.00). Below it: the first-floor walls / windows
            # (a full-height wall from +3.70 covered the first-floor vitrines – corrected)
            if any(w_[4] == '+6.65' for w_ in pg41.get_text('words')):
                sup = [(6.65, 'רצועה ‎+6.65…+8.00 (מפלסי הנקודה "+8.00 / +6.65" ב-K-41) – מתחתיה קירות / חלונות קומה א\'')]
        if sup: bot, on = max(sup, key=lambda x: x[0])
        else: bot, on, st = max(panels41, key=lambda p: p['poly'].area)['top'], None, 'provisional'; notes.append('אין במקורות אלמנט נושא מתחתיו')
        near = min((sp.distance(q) for sp in spots), default=99)
        top = 8.0 if spots else None
        if near > 3.0: st = 'provisional'; notes.append('ראש +8.00 לפי מפלסי הנקודה שב-K-41 (לא ליד הקיר הזה)')
        if top is None or top <= bot: continue
        roof_walls.append({'id': f'RW{i + 1}', 'tag': None, 'footprintITM': ring(q), 'holesITM': holes(q), 'area_m2': r3(q.area), 'thickness_m': r3(th),
                           'bottomRel': bot, 'topRel': top, 'standsOn': on, 'status': st, **({'note': '; '.join(notes)} if notes else {}),
                           'source': f'{K41} IfcWall "Beton Ole"; ראש: מפלס נקודה "+8.00 / +6.65" ב-{K41P}'})
    # thick hatched walls of K-41 (60 cm pergola pier, NE corner – K-31: "ליציקת הקיר!") are outside the thin-face filter:
    # hatched (light fill) regions of the K-41 sheet ≥ 45 cm thick not yet in the model -> wall from the K-31 beam / slab under it to +8.00
    H41 = pdf_grey(K41P, t41[1], shades=(0.93, 0.97))
    have = unary_union([Polygon(w['footprintITM']).buffer(0) for w in roof_walls + first_walls] + [Polygon(c['footprintITM']) for c in first_cols])
    for q in polys(H41.difference(have.buffer(0.03))):
        if q.area < 0.5 or 2 * q.area / q.length < 0.45: continue
        sup = [(b['topRel'], f"קורה {b['id']} (O.K {b['topRel']:+.2f})") for P, b in beam31 if q.intersection(P.buffer(0.1)).area > 0.02]
        sup += [(p['top'], f"תקרת הקרקע +{p['top']:.2f}") for p in panels31 if q.intersection(p['poly']).area > 0.25 * q.area]
        bot, on = max(sup, key=lambda x: x[0]) if sup else (6.65, None)
        mr = q.minimum_rotated_rectangle; xy = list(mr.exterior.coords)
        roof_walls.append({'id': f'RW{len(roof_walls) + 1}', 'tag': None, 'footprintITM': ring(q), 'holesITM': holes(q), 'area_m2': r3(q.area),
                           'thickness_m': r3(min(math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2]))), 'bottomRel': bot, 'topRel': 8.0, 'standsOn': on,
                           'status': 'approx', 'note': 'עמוד-קיר עבה בפינת הפרגולה: מילוי מוקווקו ב-K-41, ב-K-31 הערה "ליציקת הקיר!" – מראש הקורה שמתחתיו עד +8.00.',
                           'source': f'{K41P} מילוי מוקווקו (קיר); {K31P} "ליציקת הקיר!"'})
        print('thick roof wall', roof_walls[-1]['id'], r3(q.area), bot, on)
    roof_floor = {'floor': 'roof', 'slab': [], 'walls': roof_walls, 'columns': [],
                  'ceiling': {'slab': [], 'openings': [], 'mamad': [], 'beams': roof_beams}, 'ceilingLabel': 'קורות הגג והפרגולות',
                  'note': 'מעל תקרת הגג (+6.90): מעקות / קירות עד +8.00 וקורות K-41 (O.K +8.00) עליהם – קורות בלי תקרה משני הצדדים = פרגולה.',
                  'source': f'{K41}; {K41P}'}
    json.dump(roof_floor, open(os.path.join(ROOT, 'data/structure/floor-roof.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('roof walls', [(w['id'], w['thickness_m'], w['bottomRel'], w['topRel'], w['standsOn'], w['status']) for w in roof_walls])
    roof = dict(roof, beams=[])   # the K-41 beams sit on the roof walls -> drawn with the roof (floor "roof")
    first = {'floor': 'first', 'slab': [], 'walls': first_walls, 'columns': first_cols, 'ceiling': roof, 'ceilingLabel': 'תקרת הגג',
             'roofLevels': [{'topRel': t_['top'], 'thickness_m': t_['thickness_m']} for t_ in tags41],
             'wallsRemovedAsBelow': {'items': removed31, 'note': 'חלקי קירות שב-K-31 ממולאים אפור ("מפסיק" = קיר קומת הקרקע שמתחת לתקרה +3.70) ואין להם קיר בתוכנית האדריכל של קומה א\' – הוסרו (היו קירות קרקע שהועתקו בטעות לקומה א\').'},
             'note': 'קומה א\': קירות ועמודים מ-K-31 (רק מה שעולה מהתקרה +3.70), תקרת הגג K-41.',
             'source': f'{K31}; {K41}'}
    json.dump(first, open(os.path.join(ROOT, 'data/structure/floor-first.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('first-floor walls', [(w['id'], w['tag'], w['thickness_m'], w['bottomRel'], w['topRel'], w['status']) for w in first_walls])
    print('roof slab', [(x['id'], x['topRel'], x['area_m2']) for x in roof['slab']], 'K41pdf', roof['placement'])
    print('roof beams', [(b['id'], b['width_m'], b['depth_m'], b['topRel'], b.get('length_m'), b['status'], b.get('pergola')) for b in roof_beams])
    print('ground-ceiling pergola beams', [b['id'] for b in beams if b.get('pergola')])
    print('first-floor columns', [(c['id'], c['size_cm'], c['tagSize_cm'], c['bottomRel'], c['topRel'], c['standsOn'], c['status']) for c in first_cols])
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

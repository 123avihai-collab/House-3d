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


TITLE_LEVEL = -0.15      # K-21 title block "מפלס פני בטון: -0.15" (pt 3166,1840)
REBAR = json.load(open(os.path.join(F.ROOT, 'data/structure/rebar.json'), encoding='utf-8')) if os.path.exists(os.path.join(F.ROOT, 'data/structure/rebar.json')) else {'sections': [], 'beams': []}


def wall_section_lengths(sheets):
    """wall sections W1… on the rebar sheets: the longest written dimension = the wall length (m)"""
    out = {}
    for s in REBAR['sections']:
        if s['kind'] != 'wall' or s['sheet'] not in sheets: continue
        d = [v for v in s['parsed']['dims'] if v > 40]
        if d: out[s['title']] = max(d) / 100
    return out


def assign_wall_tags(walls, wtags, sec_len):
    """Wall Tags -> wall pieces: nearest piece, corrected by the wall length of the tag's rebar section (a tag that sits
    between two walls goes to the one whose length matches its section)"""
    out = {}
    for (xy, txt) in wtags:
        if not re.match(r'^\d+$', txt) or not walls: continue
        tag = f'W{txt}'; P = Point(xy)
        def score(i):
            d = walls[i].distance(P)
            if tag in sec_len:
                mr = walls[i].minimum_rotated_rectangle; xy_ = list(mr.exterior.coords)
                L = max(math.dist(xy_[0], xy_[1]), math.dist(xy_[1], xy_[2]))
                d += 2 * abs(L - sec_len[tag])
            return d
        cand = [i for i in range(len(walls)) if walls[i].distance(P) < 2.0]
        if not cand: continue
        k = min(cand, key=score); sc = score(k)
        if k not in out or sc < out[k][1]: out[k] = (tag, sc)
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


def bear_beam_ends(beams, verts, slabs, bar_len=None, reach=1.2, tol=0.03):
    """a beam end with nothing under it and nothing it frames into (Avihai's edit-mode note ק12 – B-26 "באוויר"): the plan
    outline of the beam stops at the face of the wall below it, but the beam runs on over the wall (K-32: the grey outline
    and the bars continue over W7 to the far face of B-27). Looks ahead along the axis (up to `reach`):
      - a beam crossing the axis at the same level  -> run on to its far face (T joint, cast together)
      - else a wall / column in line under the beam -> run on to its far face (bearing on it)
    verts: [(polygon, bottomRel, topRel, id)], slabs: [(polygon, topRel, D)]. Returns [(beam id, end, metres, onto)]."""
    ax = [b for b in beams if b.get('axisITM')]
    bpoly = lambda b: LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2)
    same_level = lambda lo, hi, b: lo < b['topRel'] - 0.005 and hi > b['bottomRel'] + 0.005
    done = []
    for b in ax:
        for k in (0, 1):
            p0, p1 = np.array(b['axisITM'][0], float), np.array(b['axisITM'][1], float)
            u = (p1 - p0) / np.linalg.norm(p1 - p0); P = p0 if k == 0 else p1; d = -u if k == 0 else u
            hw = b['width_m'] / 2
            patch = LineString([P - d * 0.2, P]).buffer(hw, cap_style=2)
            under = sum(patch.intersection(g).area for g, lo, hi, _ in verts if lo < b['bottomRel'] - 0.005 and hi >= b['bottomRel'] - 0.06) / patch.area
            # framed: touches a wall / column standing at the beam's level (rising through it, or the first-floor wall
            # on the slab next to an upstand beam – B-13 at W9 in K-32), another beam or a slab at its level
            framed = (any(patch.distance(g) < tol for g, lo, hi, _ in verts if min(hi, b['topRel']) - max(lo, b['bottomRel']) > 0.1)
                      or any(patch.distance(bpoly(o)) < tol for o in ax if o is not b and same_level(o['bottomRel'], o['topRel'], b))
                      or any(patch.distance(s) < tol for s, top, D in slabs if same_level(top - D, top, b)))
            # framed into a beam / slab / wall at its level: done – unless the end already stands partly on a wall it
            # stops on (B-22 on GW3: K-32 bars to the far face of the wall)
            if under > 0.3 or (framed and under < 0.05): continue
            target, onto = None, None
            for o in ax:          # a beam crossing the axis ahead
                if o is b or not same_level(o['bottomRel'], o['topRel'], b): continue
                q0, q1 = np.array(o['axisITM'][0], float), np.array(o['axisITM'][1], float)
                v = (q1 - q0) / np.linalg.norm(q1 - q0)
                if abs(float(np.dot(u, v))) > 0.05: continue
                t = float(np.dot(q0 - P, d)) if abs(float(np.dot(v, d))) < 0.05 else None
                if t is None: continue
                s = float(np.dot(P + d * t - q0, v))
                if not (-hw <= s <= np.linalg.norm(q1 - q0) + hw): continue
                far = t + o['width_m'] / 2
                if t - o['width_m'] / 2 > -tol and far <= reach and (target is None or far < target): target, onto = far, f"קורה {o['id']}"
            if target is None:    # a wall / column in line under the beam: to its far face
                step = 0.02; s = 0.0; hit = None
                while s < reach:
                    sl = LineString([P + d * s, P + d * (s + step)]).buffer(hw, cap_style=2)
                    cov = [(gid, sl.intersection(g).area / sl.area) for g, lo, hi, gid in verts if lo < b['bottomRel'] - 0.005 and hi >= b['bottomRel'] - 0.06]
                    best = max(cov, key=lambda c: c[1], default=(None, 0))
                    if best[1] > 0.5: hit = best[0]; target = s + step
                    elif hit: break
                    elif s > 0.1: break
                    s += step
                if hit and s >= reach:   # the wall runs on along the beam line: no end to run to – left as drawn
                    done.append((b['id'], k, None, f'{hit} (ממשיך מעבר ל-{reach} מ\' – לא שונה)')); continue
                onto = hit and f"{hit}"
            if target is None or target < 0.01: continue
            newP = P + d * target
            # the bars of the beam in the rebar sheet (K-32 / K-42, length incl. anchorage) must reach the new end
            Lb = (bar_len or {}).get(b['id'])
            if Lb and Lb < math.dist(newP, b['axisITM'][1 - k]) - 0.10:
                done.append((b['id'], k, None, f'{onto}: המוטות L={Lb * 100:.0f} קצרים מ-{math.dist(newP, b["axisITM"][1 - k]):.2f} – לא שונה')); continue
            if not Lb and framed: continue
            b['axisITM'][k] = [r3(newP[0]), r3(newP[1])]
            if 'length_m' in b: b['length_m'] = r3(math.dist(*b['axisITM']))
            b['note'] = (b.get('note', '') + f" הקצה הוארך ב-{target:.2f} מ' עד הפאה הרחוקה של {onto}: בתוכנית הקורה נעצרת בפאת הקיר שמתחתיה, "
                         "אבל היא ממשיכה מעליו (בגיליון הברזל המתאר והמוטות ממשיכים) – הערת אביחי ק12.").strip()
            done.append((b['id'], k, round(target, 3), onto))
    return done


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


def roof_notes(roof_walls, roof_beams, first_walls, first_cols, beams31, m41, to):
    """Avihai's notes 2.1–2.9 on the roof / pergola (07.11.2026), all from K-41 / K-42 / K-31:
    2.4 / 2.5  the roof perimeter is ONE ring cast in one pour: K-41 3D view (parapets and the K-41 beams, tops +8.00, one
               closed ring) and K-42 "חתך טיפוסי 38/55" (parapet 22 + beam 38 in one section). Every K-41 beam is cast with
               the parapets (castWith roofWalls). Where a beam fills the parapet line over the parapet's full height (B-8
               22/135, +6.65…+8.00) the parapet piece takes the beam's section: the overlap is cut from the wall piece.
    2.3        a K-31 beam ending at the face of a thick wall that stands on the same beams (B-30 at the 60 cm pergola wall)
               runs on to the wall's far face – its bars run into the wall (K-32 B-30 L=810).
    2.7        names: K-41 tags (W2 … W12) sit on the grey "מפסיק" pieces – the first-floor walls under the roof slab; they
               are checked against the K-31 tags. The parapets have no tag in K-41 / K-42 (no invented name). K-41 column
               numbers (1, 3, 4, 5) are recorded next to the K-31 ones (C9 = "3")."""
    out = {'trimmed': [], 'beamsIntoWall': [], 'names': []}
    # ---- 2.4 / 2.5 ----
    for b in roof_beams:
        if not b.get('axisITM'): continue
        b['castWith'] = 'roofWalls'; b['perimeter'] = True
        b['note'] = (b.get('note', '') + ' קורה בהיקף הגג (O.K +8.00 = ראש המעקה) – נוצקת יחד עם המעקות כטבעת רציפה אחת (K-41 תלת-ממד; '
                     'K-42 חתך טיפוסי 38/55: מעקה וקורה בחתך אחד). בקטע שבו היא בקו המעקה – החתך והברזל של הקורה (K-42).').strip()
        BP = LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2)
        for w in list(roof_walls):
            W = Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0)
            if W.intersection(BP).area < 0.02 or b['bottomRel'] > w['bottomRel'] + 0.01: continue
            rest = [g for g in polys(W.difference(BP.buffer(0.01, cap_style=2, join_style=2))) if g.area > 0.03 and 2 * g.area / g.length > 0.05]
            out['trimmed'].append((w['id'], b['id'], r3(W.area - sum(g.area for g in rest))))
            note = f"החלק שבקו הקורה {b['id']} ({round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)}, {b['bottomRel']:+.2f}…{b['topRel']:+.2f}) הוא הקורה עצמה – נחתך מהמעקה (הערת אביחי 2.5)"
            if not rest:
                w['replacedBy'] = b['id']; w['note'] = (w.get('note', '') + '; ' + note).strip('; '); continue
            rest.sort(key=lambda g: -g.area)
            w.update(footprintITM=ring(rest[0]), holesITM=holes(rest[0]), area_m2=r3(rest[0].area), trimmedBy=b['id'], note=(w.get('note', '') + '; ' + note).strip('; '))
            for k, g in enumerate(rest[1:]):
                roof_walls.append(dict(w, id=f"{w['id']}{'bcdef'[k]}", footprintITM=ring(g), holesITM=holes(g), area_m2=r3(g.area)))
    roof_walls[:] = [w for w in roof_walls if not w.get('replacedBy')] + []
    # ---- 2.3 ----
    for w in [w for w in roof_walls if w.get('thick')]:
        q = Polygon(w['footprintITM']).buffer(0)
        for bb in beams31:
            if not bb.get('axisITM') or bb['topRel'] < w['bottomRel'] - 0.005: continue
            for k in (0, 1):
                P, Q = np.array(bb['axisITM'][k], float), np.array(bb['axisITM'][1 - k], float)
                if q.distance(Point(P)) > 0.05: continue
                u = (P - Q) / np.linalg.norm(P - Q)
                hit = LineString([P - u * 0.01, P + u * 1.5]).intersection(q)
                if hit.is_empty: continue
                far = max(float(np.dot(np.array(c) - P, u)) for g in getattr(hit, 'geoms', [hit]) for c in g.coords)
                if far < 0.05 or far > w['thickness_m'] + 0.05: continue   # frames into the side of the wall – not along it
                bb['axisITM'][k] = [r3(P[0] + u[0] * far), r3(P[1] + u[1] * far)]
                bb['length_m'] = r3(math.dist(*bb['axisITM']))
                bb['note'] = (bb.get('note', '') + f" הקצה נמשך {far:.2f} מ' לתוך הקיר העבה בפינת הפרגולה עד הפאה הרחוקה – הקורה מתחברת לקיר "
                              f"(ברזל {bb['id']} ב-K-32 נכנס לתוך הקיר; הערת אביחי 2.3).").strip()
                out['beamsIntoWall'].append((bb['id'], w['id'], r3(far)))
                w.setdefault('framedBy', []).append({'id': bb['id'], 'topRel': bb['topRel'], 'bottomRel': bb['bottomRel'], 'width_m': bb['width_m'], 'depth_m': bb['depth_m']})
        # K-41 beams whose end rests on the wall (B-4 at the pergola corner)
        for rb in roof_beams:
            if not rb.get('axisITM'): continue
            for E in rb['axisITM']:
                if q.distance(Point(E)) < 0.1: w.setdefault('carriesRoof', []).append({'id': rb['id'], 'endITM': E, 'topRel': rb['topRel'], 'bottomRel': rb['bottomRel']})
        # owner changes that cancel this wall (data/changes/owner-changes.json "cancelsWall")
        for oc in json.load(open(os.path.join(ROOT, 'data/changes/owner-changes.json'), encoding='utf-8'))['changes']:
            cw = oc.get('cancelsWall')
            if cw and cw.get('floor') == 'roof' and q.buffer(0.05).contains(Point(cw['pointITM'])): w['cancelledBy'] = oc['id']
    # ---- 2.7 ----
    wt41 = [(p, t) for p, t in tag_texts(m41, 'Wall Tags', to) if re.match(r'^\d+$', t)]
    for p, t in wt41:
        cand = sorted((Polygon(fw['footprintITM']).buffer(0).distance(Point(p)), fw['id']) for fw in first_walls)
        if not cand or cand[0][0] > 0.6: out['names'].append((f'W{t}', None, 'no first-floor wall near')); continue
        fw = next(x for x in first_walls if x['id'] == cand[0][1]); fw['tagK41'] = f'W{t}'
        if fw.get('tag') and fw['tag'] != f'W{t}':
            fw['note'] = (fw.get('note', '') + f"; שם ב-K-31: {fw['tag']}, ב-K-41: W{t} – לבדיקה").strip('; ')
        elif not fw.get('tag'):
            fw['tag'] = f'W{t}'; fw['note'] = (fw.get('note', '') + f'; שם W{t} מ-K-41 (אין תווית ב-K-31)').strip('; ')
        out['names'].append((f'W{t}', fw['id'], fw.get('tag')))
    for w in roof_walls:
        if w.get('displayName'): continue
        W = Polygon(w['footprintITM']).buffer(0)
        under = [fw.get('tag') for fw in first_walls if fw.get('tag') and Polygon(fw['footprintITM']).buffer(0).intersection(W).area > 0.25 * W.area]
        w['displayName'] = 'מעקה גג (ללא שם בתוכנית' + (f' – מעל {under[0]})' if under else ')')
    ct41 = tag_texts(m41, 'Structural Column Tags', to)
    for c in first_cols:
        no, sz = col_tag(Polygon(c['footprintITM']), ct41)
        if no is None or Polygon(c['footprintITM']).centroid.distance(Point(next(p for p, t in ct41 if t == str(no)))) > 1.5: continue
        c['tagK41'] = str(no)
        if f'C{no}' != c['id']:
            c['note'] = (c.get('note', '') + f'; ב-K-41 העמוד מסומן "{no}" ({"/".join(map(str, sz))})').strip('; ')
        out['names'].append((c['id'], f'K-41 "{no}"'))
    # 2.9: a column under the end of a K-41 beam that is deeper than the beam is wide – the strip outside the beam stops at the
    # beam bottom (K-41 DXF: that strip is filled grey "מפסיק"); recorded, not changed
    for c in first_cols:
        if not c.get('carries'): continue
        b = next((x for x in roof_beams if x['id'] == c['carries'] and x.get('axisITM')), None)
        if not b: continue
        q = Polygon(c['footprintITM']); BP = LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2)
        ledge = q.difference(BP.buffer(0.005)).area
        if ledge > 0.01:
            c['ledge'] = {'beam': b['id'], 'area_m2': r3(ledge), 'width_m': r3(ledge / max(math.dist(*list(q.minimum_rotated_rectangle.exterior.coords)[:2]), math.dist(*list(q.minimum_rotated_rectangle.exterior.coords)[1:3]))),
                          'stepHeight_m': r3(b['topRel'] - b['bottomRel'])}
            c['note'] = (c.get('note', '') + f"; מדרגה מול {b['id']}: העמוד ({c['size_cm'][0]}/{c['size_cm'][1]}) עמוק מרוחב הקורה ({round(b['width_m'] * 100)}) – "
                         f"רצועה של כ-{round(c['ledge']['width_m'] * 100)} ס\"מ בצד הפנימי נעצרת בתחתית הקורה ({b['bottomRel']:+.2f}), "
                         f"{round(c['ledge']['stepHeight_m'] * 100)} ס\"מ מתחת לראשה; הפאה החיצונית מיושרת. כך ב-K-41 DXF (חלק העמוד מחוץ לקורה ממולא אפור "
                         '"מפסיק") – לאישור הקונסטרוקטור / האדריכל (הערת אביחי 2.9)').strip('; ')
    print('roof notes 2.x', out)
    return out


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
            top, D = near_b['top'], near_b['thickness_m']
            if abs(top - TITLE_LEVEL) < 0.005 and abs(D - 0.25) < 0.005:
                st = 'source'
                note = ('חלק מהרצפה בלי תגית מפלס ב-K-21 – לפי "מפלס פני בטון: ‎-0.15" בכותרת K-21 ובחתכי הקורות ב-K-22 '
                        '(B-43/B-44/B-45/B-46: רצפה ‎-0.15, עובי 25).')
            else:
                st = 'provisional'
                note = 'חלק מהרצפה בלי תגית מפלס ב-K-21 (DXF ו-PDF) – לפי התגית הקרובה למרתף.'
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
            slab_sup = [t for t in sup if t[1].startswith('רצפה')]
            if b0[1].startswith('קורה') and b0[0] > max([t[0] for t in slab_sup] or [-9]) + 0.01:
                bp = next(P for P, x in beam_polys if b0[1].startswith(f"קורה {x['id']} "))
                if slab_sup and frac(bp) < 0.9:
                    # the upstand beam is under part of the column only: the column is cast from the slab top
                    # (Avihai's edit-mode note 07.11.2026, ק3 – C9)
                    s0 = max(slab_sup, key=lambda t: t[0])
                    rec['bottomRel'] = s0[0]; rec['standsOn'] = s0[1]
                    notes.append(f'{b0[1]} מתחת ל-{round(frac(bp) * 100)}% מהעמוד בלבד – העמוד יוצק מראש הרצפה (הערת אביחי 07.11.2026)')
                else:
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
    wtag_of = assign_wall_tags(walls, wtags, wall_section_lengths({'K-22'}))
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
    # rising wall hatch (diagonal, k-21 IfcWall HATCH) with no "Beton Ole" outline: the pieces are added to the wall they
    # touch (e.g. the east wall of the stair shaft above GW19 – Avihai's edit-mode note ק11) – after the ids are given,
    # so the ids of the other walls do not move
    hatch = F.wall_polys(m21, to)
    taken = unary_union([Polygon(w['footprintITM']).buffer(0.01) for w in wall_out] + [c.buffer(0.01) for c in cols])
    rec_pieces = []
    for q in polys(hatch.difference(taken)):
        if q.area < 0.08 or 2 * q.area / q.length < 0.12: continue
        if pool_zone.intersects(q.representative_point()) or q.intersection(lot.exterior.buffer(0.6)).area > 0.5 * q.area: continue
        if q.intersection(grey).area > 0.5 * q.area: continue                      # grey = stops here (basement wall top)
        kept_, _ = keep_in([q], below_slab(K31P, t31p))
        rec_pieces += kept_
    recovered = []
    for q in rec_pieces:
        touch = [w for w in wall_out if Polygon(w['footprintITM']).buffer(0.03).intersects(q)]
        if touch:
            w = max(touch, key=lambda w: Polygon(w['footprintITM']).buffer(0.03).intersection(q).area)
            g = unary_union([Polygon(w['footprintITM']).buffer(0.005), q.buffer(0.005)]).buffer(-0.005)
            g = max(polys(g), key=lambda x: x.area)
            w['footprintITM'] = ring(g); w['holesITM'] = holes(g); w['area_m2'] = r3(g.area)
            w['note'] = (w.get('note', '') + f' הוסף קטע קיר מקווקו (HATCH IfcWall ב-k-21, {q.area:.2f} מ"ר) שאין לו קווי "Beton Ole" – הקיר ממשיך לאורך הפיר.').strip()
            w['status'] = 'approx' if w['status'] == 'source' else w['status']
            recovered.append(f"{w['id']}+{q.area:.2f}")
        else:
            rec = {'id': f'GW{len(wall_out) + 1}', 'tag': None, 'footprintITM': ring(q), 'holesITM': holes(q), 'area_m2': r3(q.area),
                   'thickness_m': r3(2 * q.area / q.length)}
            rec.update(vertical(q, 'wall')); rec['status'] = 'approx'
            rec['note'] = (rec.get('note', '') + ' מ-HATCH IfcWall ב-k-21 (אין קווי "Beton Ole").').strip()
            rec['source'] = f'{K21} HATCH IfcWall; מפלסים: {K21}/{K31} Floor Tags'
            wall_out.append(rec); recovered.append(f"{rec['id']} חדש {q.area:.2f}")
    # a wall drawn hatched in the K-21 PDF with neither "Beton Ole" lines nor an IfcWall hatch in the DXF, that connects
    # walls of the model (the south wall of the mamad between GW10 and GW16 / GW20 – Avihai's edit-mode note ק15: "למה
    # הקיר הזה לא סגור?") -> a wall of its own (new id after the others)
    hatchP = pdf_grey(F.K21P, K21P_T, shades=(0.93, 0.97))
    have = unary_union([Polygon(w['footprintITM'], w['holesITM']).buffer(0) for w in wall_out] + [c.buffer(0) for c in cols])
    for q in polys(hatchP.difference(have.buffer(0.02))):
        if q.area < 0.08 or 2 * q.area / q.length < 0.12 or q.intersection(lot.exterior.buffer(0.6)).area > 0.3 * q.area: continue
        if q.intersection(grey).area > 0.5 * q.area or pool_zone.intersects(q.representative_point()): continue
        touch = [w for w in wall_out if Polygon(w['footprintITM'], w['holesITM']).buffer(0).distance(q) < 0.05]
        if len(touch) < 2: continue
        q = unary_union([q, have.buffer(0.025).intersection(q.buffer(0.03))]).difference(have).buffer(0)   # up to the faces of the walls it joins
        q = max(polys(q), key=lambda x: x.area)
        rec = {'id': f'GW{len(wall_out) + 1}', 'tag': None, 'footprintITM': ring(q), 'holesITM': holes(q), 'area_m2': r3(q.area), 'thickness_m': r3(2 * q.area / q.length)}
        rec.update(vertical(q, 'wall')); rec['status'] = 'approx'
        rec['note'] = (rec.get('note', '') + f" קיר מקווקו ב-K-21 (PDF) בין {', '.join(w['id'] for w in touch)}, בלי קווי \"Beton Ole\" ובלי HATCH ב-DXF – נוסף (הערת אביחי ק15).").strip()
        rec['source'] = f"{F.K21P} מילוי קיר מקווקו; מפלסים: {K21}/{K31} Floor Tags"
        wall_out.append(rec); recovered.append(f"{rec['id']} חדש מה-PDF {q.area:.2f} ({', '.join(w['id'] for w in touch)})")
    print('recovered hatched wall pieces', recovered)
    # notches / slits left in the wall outlines (a sleeve island in the k-21 hatch, a corner not closed – the mamad corner
    # GW7 / GW4, Avihai's edit-mode note ק16): where the K-21 PDF fills the wall hatch, the wall is continuous
    WU =unary_union([Polygon(w['footprintITM'], w['holesITM']).buffer(0) for w in wall_out] + [c.buffer(0) for c in cols])
    slits = []
    # + shallow dips on a straight wall face (< 3 cm deep – a hatch seam, Avihai ק46: GW1 is one pour) even where the PDF hatch misses
    closing = WU.buffer(0.08, join_style=2).buffer(-0.08, join_style=2).difference(WU)
    shallow = [q for q in polys(closing) if q.area >= 0.001 and q.area / max(q.length / 2, 1e-6) < 0.03]
    for q in polys(unary_union(list(polys(closing.intersection(hatchP.buffer(0.01)))) + shallow)):
        if q.area < 0.001: continue
        touch = [w for w in wall_out if Polygon(w['footprintITM'], w['holesITM']).buffer(0).distance(q) < 0.005]
        if not touch: continue
        w = max(touch, key=lambda w: Polygon(w['footprintITM'], w['holesITM']).buffer(0).buffer(0.005).intersection(q).area)
        g = max(polys(unary_union([Polygon(w['footprintITM'], w['holesITM']).buffer(0), q]).buffer(0.002, join_style=2).buffer(-0.002, join_style=2)), key=lambda x: x.area)
        w['footprintITM'] = ring(g); w['holesITM'] = holes(g); w['area_m2'] = r3(g.area)
        w['note'] = (w.get('note', '') + f' שקע / חריץ של {q.area * 1e4:.0f} סמ"ר בקו הקיר נסגר – ב-K-21 הקיר מקווקו ורציף שם (הערת אביחי ק16).').strip()
        slits.append(f"{w['id']}+{q.area:.4f}")
    print('wall notches / slits closed', slits)
    # a straight wall whose outline dips by < 3 cm along one face (two hatch pieces of one pour, Avihai ק46 – GW1): the wall
    # is its minimum rectangle (only when the rectangle adds < 3 % and every added sliver is < 3 cm thick)
    squared = []
    for w in wall_out:
        if w.get('holesITM'): continue
        g = Polygon(w['footprintITM']).buffer(0); r = g.minimum_rotated_rectangle
        if g.is_empty or r.area <= 0: continue
        c = list(r.exterior.coords); e1, e2 = math.dist(c[0], c[1]), math.dist(c[1], c[2]); th = min(e1, e2)
        if th > 0.45 or g.area / r.area < 0.97: continue
        add = [q for q in polys(r.difference(g)) if q.area > 1e-5]
        if not add or any(q.area / max(q.length / 2, 1e-6) > 0.03 for q in add) or sum(q.area for q in add) < 0.002: continue
        if any(Polygon(o['footprintITM']).buffer(0).intersection(r).area > 0.002 for o in wall_out if o is not w): continue
        w['footprintITM'] = ring(r); w['area_m2'] = r3(r.area)
        w['note'] = (w.get('note', '') + f' קיר ישר אחד ביציקה אחת – שקע של עד 3 ס"מ בפאה (תפר בין שני קטעי מילוי בשרטוט) נסגר ({sum(q.area for q in add) * 1e4:.0f} סמ"ר, הערת אביחי ק46).').strip()
        squared.append(w['id'])
    print('straight walls squared (face dips < 3 cm)', squared)
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
    cc31 = F.close_beam_corners(beams)
    print('closed corners K-31', cc31)
    for b in beams:
        if any(c.startswith(b['id'] + '+') for c in cc31):
            b['note'] = (b.get('note', '') + ' הקצה הוארך עד הפאה החיצונית של הקורה הניצבת בפינה (פינת L סגורה – הערת אביחי ק5).').strip()
    mark_pergola(beams, panels31)
    # wall hatch of the K-21 PDF that was dropped as "not under the K-31 slab" but stands under a K-31 beam (the mamad NW
    # corner GW4 / GW7 under the 30/70 beam – Avihai's note 10: "יש מגרעת"): a wall under a beam is a wall – into the wall
    # it touches
    b31U = unary_union([LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2) for b in beams if b.get('axisITM')])
    haveW = unary_union([Polygon(w['footprintITM'], w['holesITM']).buffer(0) for w in wall_out] + [c.buffer(0) for c in cols])
    underB = []
    hp_all = pdf_grey(F.K21P, K21P_T, shades=(0.93, 0.97))
    for q in polys(hp_all.difference(haveW.buffer(0.01))):
        if q.area < 0.05 or q.intersection(b31U).area < 0.5 * q.area or q.intersection(grey).area > 0.5 * q.area: continue
        if q.intersection(lot.exterior.buffer(0.6)).area > 0.3 * q.area or pool_zone.intersects(q.representative_point()): continue
        touch = [w for w in wall_out if Polygon(w['footprintITM'], w['holesITM']).buffer(0).distance(q) < 0.08]
        if not touch: continue
        w = min(touch, key=lambda w: Polygon(w['footprintITM'], w['holesITM']).buffer(0).distance(q))
        wg = Polygon(w['footprintITM'], w['holesITM']).buffer(0)
        g = max(polys(unary_union([wg, q.buffer(0.012), wg.buffer(0.09, join_style=2).intersection(q.buffer(0.09, join_style=2)).intersection(hp_all.buffer(0.012))]).buffer(-0.002, join_style=2)), key=lambda x: x.area)
        w['footprintITM'] = ring(g); w['holesITM'] = holes(g); w['area_m2'] = r3(g.area)
        w['note'] = (w.get('note', '') + f' הוסף קטע קיר מקווקו ב-K-21 ({q.area:.2f} מ"ר) מתחת לקורת K-31 – הפינה רציפה כמו בתוכנית (הערת אביחי, סעיף 10).').strip()
        underB.append(f"{w['id']}+{q.area:.3f}")
    print('K-21 wall hatch under K-31 beams added', underB)

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
        zs = cut.get('zones') or [cut['zone']]
        for p in panels21:
            if p['zone'] in zs and p['poly'].intersection(cp).area > 0.01:
                p['poly'] = max(polys(p['poly'].difference(cp)), key=lambda g: g.area); p['note'] = (p.get('note', '') + ' ' + cut['note']).strip()
        if cut.get('openZone'): open21.append({'poly': cp, 'zone': cut['openZone']['zone'], 'override': cut['openZone']})
    # the ground slab is cast over the top of the basement wall at the stair shaft (bears on it): K-21 leaves the wall top
    # between the shaft and the house / entry slabs without a face – fill it into the house slab (Avihai's edit-mode note
    # 07.11.2026, ק4). Rims of the English courtyards / outside stairs down are left as drawn (open question).
    bwU = unary_union([P for P, w in bw_polys])
    # the same at the rims of the English courtyards and the stairs down (Avihai's edit-mode note ק18: "אמרנו שיהיה שם המשך
    # יציקת רצפה" – the answer to open issue #82); the grey caps of K-21 (walls that stop at the level) stay as they are
    capU = unary_union([Polygon(c['footprintITM'], c['holesITM']).buffer(0) for c in caps]) if caps else Polygon()
    gapU = bwU.difference(unary_union([p['poly'] for p in panels21] + [o['poly'] for o in open21] + [capU]))
    shaft = [o['poly'] for o in open21 if o['zone'] in ('stairShaft', 'courtyard', 'basementStairs')]
    other_open = [o['poly'] for o in open21 if o['zone'] not in ('stairShaft', 'courtyard', 'basementStairs')]
    ZL = {'stairShaft': 'פיר המדרגות', 'courtyard': 'החצר האנגלית', 'basementStairs': 'מדרגות הירידה למרתף'}
    zname = lambda q: ZL[min((o for o in open21 if o['zone'] in ZL), key=lambda o: o['poly'].distance(q))['zone']]
    for q in polys(gapU):
        if q.area < 0.05 or not any(o.distance(q) < 0.02 for o in shaft) or any(o.distance(q) < 0.02 for o in other_open): continue
        house = [p for p in panels21 if p['zone'] in ('house', 'entry') and p['poly'].distance(q) < 0.02]
        if not house: continue
        tgt = max(house, key=lambda p: p['poly'].area)
        g = unary_union([tgt['poly'].buffer(0.01, join_style=2), q.buffer(0.01, join_style=2)]).buffer(-0.01, join_style=2)
        tgt['poly'] = max(polys(g), key=lambda x: x.area)
        tgt['note'] = (tgt.get('note', '') + f' רצועה מעל ראש קיר המרתף בשפת {zname(q)} ({q.area:.2f} מ"ר) – הרצפה יצוקה על הקיר, לפי הערות אביחי ק4 / ק18 (07.11.2026).').strip()
        print('slab over basement wall at the rim of', zname(q), round(q.area, 3))
    # a column / wall that stood on the slab, but the slab under it was cut away afterwards (the south English courtyard –
    # slabCuts): it is the joint of the K-21 beams that frame into it – cast with them from their underside (Avihai's
    # edit-mode note ק13: C10 20/80 between B-46 and B-45 over the light well; K-21: dashed outline = goes on below the slab)
    slabU = unary_union([p['poly'] for p in panels21])
    rejoined = []
    for e in col_out + wall_out:
        q = Polygon(e['footprintITM']).buffer(0)
        if not (e.get('standsOn') or '').startswith('רצפה') or q.intersection(slabU).area > 0.5 * q.area: continue
        near = [(x, P) for P, x in beam_polys if P.distance(q) < 0.03]
        if not near: continue
        frac = {x['id']: q.intersection(P).area / q.area for x, P in near}
        near.sort(key=lambda t: -frac[t[0]['id']])
        bot = min(x['bottomRel'] for x, _ in near)
        on = ' + '.join(f"{x['id']} ({round(x['width_m'] * 100)}/{round(x['depth_m'] * 100)}, O.K {x['topRel']:+.2f}" +
                        (f", {round(frac[x['id']] * 100)}% מתחתיו)" if frac[x['id']] > 0.01 else ', נכנסת לצד העמוד)') for x, _ in near)
        e['bottomRel'] = r3(bot); e['standsOn'] = f"קורה {on}"
        e['note'] = (re.sub(r'קורה B-\d+ \([^)]*\) מתחת ל-\d+% מהעמוד בלבד – העמוד יוצק מראש הרצפה \(הערת אביחי 07\.11\.2026\);?\s*', '', e.get('note', '')) +
                     f" הרצפה שמתחתיו הוצאה (החצר האנגלית) – {round(q.intersection(slabU).area / q.area * 100)}% על רצפה. העמוד הוא הצומת של הקורות "
                     f"שנכנסות אליו, ויוצק איתן מתחתיתן ({bot:+.2f}); ב-K-21 קו המתאר שלו מקווקו (ממשיך מתחת לרצפה). הערת אביחי ק13.").strip()
        rejoined.append(f"{e['id']} → {bot:+.2f} ({', '.join(x['id'] for x, _ in near)})")
    print('elements re-seated on the beams after the slab cuts', rejoined)

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
        'openZones': [{'zone': o['zone'], 'label': (o.get('override') or ZN['zones'][o['zone']])['label'], 'note': (o.get('override') or ZN['zones'][o['zone']])['note'],
                       'footprintITM': ring(o['poly']), 'area_m2': r3(o['poly'].area),
                       'source': o['override']['source'] if o.get('override') else f"{K21} (קווים); {ZN['source']}"} for o in open21],
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
        drawn_has_section = any(sec['kind'] == 'column' and sec['sheet'] in ('K-32', 'K-42') and
                                sorted(int(v) for v in sec['title'].replace('עמודבחתך', '').split('/')) == sorted(size) for sec in REBAR['sections'])
        if tag_size and sorted(tag_size) != sorted(size) and drawn_has_section:
            notes.append(f"תווית {'/'.join(map(str, tag_size))} מול ההאצ' ב-k-31.dxf {size[0]}/{size[1]}: לפי ה-DXF וחתך \"עמוד בחתך {size[1]}/{size[0]}\" "
                         "בגיליונות הברזל K-32/K-42 (ב-K-41 מסומן \"3\")")
        elif tag_size and sorted(tag_size) != sorted(size):
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
    wtag31 = assign_wall_tags(W31, wtags31, wall_section_lengths({'K-32', 'K-42'}))
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
    # K-31 beam ends with nothing under them (ק12) – after the first-floor walls, which frame the upstand beams next to them
    verts31 = [(Polygon(e['footprintITM'], e.get('holesITM') or []).buffer(0), e['bottomRel'], e['topRel'], e['id'])
               for e in wall_out + col_out + first_walls + first_cols]
    bars_of = lambda sh: {rb['id']: max([x['length_cm'] / 100 for x in rb['bars'] if x.get('length_cm') and x['position'] in ('top', 'bottom')] or [0]) or None
                          for rb in REBAR['beams'] if rb['sheet'] == sh}
    be31 = bear_beam_ends(beams, verts31, [(p['poly'], p['top'], p['D']) for p in panels31], bars_of('K-32'))
    print('beam ends run on to their support K-31', be31)
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
    # rebar-sheet corrections (tools/rebar-beams.json): B-3 stops at B-2 (K-41 dimension "337")
    for rb in REBAR['beams']:
        if rb['sheet'] != 'K-42' or 'trimTo_m' not in rb: continue
        b = next((x for x in roof_beams if x['id'] == rb['id'] and x.get('axisITM')), None)
        if not b: continue
        others = [LineString(x['axisITM']).buffer(x['width_m'] / 2) for x in roof_beams if x is not b and x.get('axisITM')]
        P, Q = b['axisITM']; inQ = any(o.contains(Point(Q)) for o in others)
        keep, move = (P, Q) if inQ or not any(o.contains(Point(P)) for o in others) else (Q, P)
        u = np.subtract(move, keep) / math.dist(keep, move)
        new = [r3(keep[0] + u[0] * rb['trimTo_m']), r3(keep[1] + u[1] * rb['trimTo_m'])]
        b['axisITM'] = [keep, new] if keep is P else [new, keep]; b['length_m'] = rb['trimTo_m']
        b['note'] = (b.get('note', '') + ' ' + rb['note']).strip()
    ccr = F.close_beam_corners(roof_beams)
    print('closed corners K-41', ccr)
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
    print('double-height walls up to the roof', fixed)
    # a double-height ground wall with a first-floor wall drawn on top of it (K-31): the ground wall stops at the bottom of
    # the first-floor wall, which stands on it (one continuous wall, not two overlapping ones)
    stacked = []
    for e in out['walls']:
        if e['topRel'] < 6.0: continue
        g = Polygon(e['footprintITM']).buffer(0)
        over = [fw for fw in first_walls if Polygon(fw['footprintITM']).buffer(0).intersection(g).area > 0.3 * min(g.area, Polygon(fw['footprintITM']).area)]
        if not over: continue
        fw = max(over, key=lambda fw: Polygon(fw['footprintITM']).buffer(0).intersection(g).area)
        e['topRel'] = fw['bottomRel']
        e['note'] = (re.sub(r'ראש: בחלל הכפול – עד תחתית תקרת הגג K-41 \(\+6\.65\);?\s*', '', e.get('note', '')) +
                     f" ראש: תחתית קיר קומה א' {fw['id']} ({fw['bottomRel']:+.2f}) שממשיך מעליו.").strip()
        if not fw.get('standsOn'):
            fw['standsOn'] = f"קיר {e.get('tag') or e['id']} של קומת הקרקע (רציף)"; fw['bottomRel'] = e['topRel']
            fw['note'] = re.sub(r'אין במקורות אלמנט נושא מתחתיו – תחתית במפלס תקרת הקרקע;?\s*', '', fw.get('note', '')).strip()
            if 'זמני' not in fw['note']: fw['status'] = 'approx'
        stacked.append(f"{e['id']}→{fw['id']}")
    print('double-height ground walls under a first-floor wall', stacked)
    # a ground wall / column under a K-31 beam is cast up to the beam soffit (the beam is cast with the slab above it):
    # double-height walls under B-23 / B-27 / B-28 (+3.45), mamad walls under the +3.65 beams (+3.05)
    under = []
    for e in out['walls'] + out['columns']:
        g = Polygon(e['footprintITM']).buffer(0)
        hits = [(b['bottomRel'], b) for b in beams if b.get('axisITM') and LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2).intersection(g).area > 0.5 * g.area]
        if not hits: continue
        bot, b = min(hits, key=lambda h: h[0])
        if bot < e['topRel'] - 0.005:
            under.append(f"{e['id']} {e['topRel']:+.2f}→{bot:+.2f}")
            # the part of a wall with no beam over it still rises to the ceiling slab (Avihai's edit-mode note ק17 – GW5 at
            # the mamad's NE corner stopped 40 cm under the slab)
            old = e['topRel']
            if 'thickness_m' in e and old <= max(p['top'] - p['D'] for p in panels31) + 0.01:     # a wall under the ceiling slab
                bU = unary_union([LineString(x['axisITM']).buffer(x['width_m'] / 2, cap_style=2) for x in beams if x.get('axisITM') and x['bottomRel'] < old - 0.005]).buffer(0.005)
                rest = [p for p in polys(g.difference(bU)) if p.area > 0.005]
                if rest:
                    e['raisedITM'] = [{'ringITM': ring(p), 'holesITM': holes(p), 'bottomRel': r3(bot), 'topRel': r3(old)} for p in rest]
                    e['note'] = (e.get('note', '') + f" החלק שאין מעליו קורה ({sum(p.area for p in rest):.2f} מ\"ר) ממשיך עד תחתית התקרה ({old:+.2f}) – הערת אביחי ק17.").strip()
            e['topRel'] = r3(bot)
            e['note'] = (re.sub(r'ראש: בחלל הכפול – עד תחתית תקרת הגג K-41 \(\+6\.65\);?\s*', '', e.get('note', '')) +
                         f" ראש: תחתית הקורה {b['id']} ({round(b['width_m'] * 100)}/{round(b['depth_m'] * 100)}, O.K {b['topRel']:+.2f}) שמעליו.").strip()
    print('ground walls / columns up to the K-31 beam soffit', under)
    out['wallsUnderBeams'] = under
    # mamad: walls and ceiling are cast as one body (Avihai's note 10) – its walls are cast with the ground ceiling
    mam = unary_union([Polygon(s_['footprintITM'], s_['holesITM']).buffer(0) for s_ in out['slab'] if s_['zone'] == 'mamad'])
    for w in out['walls']:
        g = Polygon(w['footprintITM'], w['holesITM']).buffer(0)
        if not mam.is_empty and g.distance(mam) < 0.03 and g.intersection(mam.buffer(0.35, join_style=2)).area > 0.5 * g.area:
            w['mamad'] = True
    print('mamad walls (cast with the ceiling)', [w['id'] for w in out['walls'] if w.get('mamad')])
    # ---- outdoor K-21 beams: critical for the house? (Avihai's note 3) – a house beam whose end has no pile, basement wall,
    #      wall footing or house beam under it rests on the outdoor beam it meets: that beam (and the beams that carry it on in
    #      line down to a support) is cast with the house, and the wall footing it rests on before it ----
    OUTZ = set(json.load(open(os.path.join(ROOT, 'data/config/tags.json'), encoding='utf-8'))['outdoorZones'])
    PL = json.load(open(os.path.join(ROOT, 'data/structure/piles.json'), encoding='utf-8'))['piles']
    PF = json.load(open(os.path.join(ROOT, 'data/structure/perimeter.json'), encoding='utf-8'))['footings']
    pileC = {p['id']: Point(p['E'], p['N']).buffer(p['diameter_m'] / 2) for p in PL}
    pfP = {f['id']: Polygon(f['ringITM']).buffer(0) for f in PF}
    bwU2 = unary_union([P for P, w in bw_polys])
    K21B = {x['id']: (LineString(x['axisITM']).buffer(x['width_m'] / 2, cap_style=2), x) for x in FR['groundBeams'] if x['sheet'] == 'K-21' and x.get('axisITM')}
    zone = out['beamZones']
    isHouse = lambda k: zone.get(k, 'house') not in OUTZ
    def end_patch(x, k, d=0.25):
        (a, b) = np.array(x['axisITM'][0], float), np.array(x['axisITM'][1], float); u = (b - a) / np.linalg.norm(b - a)
        P0 = a if k == 0 else b; inward = u if k == 0 else -u
        return LineString([P0, P0 + inward * d]).buffer(x['width_m'] / 2 + 0.02, cap_style=2)
    def supports(patch, own, house_only=True):
        r = [f"כלונס {i}" for i, c in pileC.items() if patch.intersects(c)]
        r += [f"יסוד {i}" for i, g in pfP.items() if patch.intersects(g)]
        if patch.intersection(bwU2).area > 0.01: r.append('קיר מרתף')
        r += [f"קורה {o}" for o, (P, y) in K21B.items() if o != own and patch.intersects(P) and (isHouse(o) or not house_only)]
        return r
    critical, why = set(), {}
    changed = True
    while changed:
        changed = False
        for k, (P, x) in K21B.items():
            if not (isHouse(k) or k in critical): continue
            for e in (0, 1):
                pt = end_patch(x, e)
                if supports(pt, k): continue
                carriers = [o for o, (Q, y) in K21B.items() if o != k and not isHouse(o) and o not in critical and pt.intersects(Q)]
                for o in carriers:
                    critical.add(o); why[o] = f"קצה {k} נשען רק עליה"; changed = True
    early_footings = sorted({f for o in critical for f, g in pfP.items() if K21B[o][0].intersects(g)})
    for o in critical: zone[o] = 'house'
    rows = []
    for k, (P, x) in sorted(K21B.items()):
        z0 = zone.get(k)
        if k not in critical and z0 not in OUTZ: continue
        rests = sorted(set(supports(end_patch(x, 0), k, False) + supports(end_patch(x, 1), k, False)))
        carries = sorted({w['id'] for w in wall_out + col_out if (w.get('standsOn') or '').startswith(f"קורה {k} ")} |
                         {s_['zone'] for s_ in [{'zone': p_['zone']} for p_ in panels21 if p_['poly'].intersection(P.buffer(0.15)).area > 0.1]})
        rows.append({'beam': k, 'size': f"{round(x['width_m'] * 100)}/{round(x['depth_m'] * 100)}", 'topRel': x['topRel'], 'length_m': r3(math.dist(*x['axisITM'])),
                     'restsOn': rests, 'carries': carries, 'class': 'critical' if k in critical else 'outdoor',
                     'reason': why.get(k, 'נושאת רק רצפות חוץ; לא נושאת קיר / עמוד / קצה קורה של הבית')})
    out['outdoorBeamsCheck'] = {'rows': rows, 'earlyFootings': early_footings,
                                'note': 'קורה שקצה קורת בית נשען רק עליה – נוצקת עם רצפת הקרקע; יסוד החומה שהיא נשענת עליו – לפני כן. השאר – בשלב קורות החוץ.'}
    print('outdoor beams: critical', sorted(critical), 'early footings', early_footings)
    # ---- under the ground slabs and K-21 beams outside the basement: lean concrete + void formers (Avihai's ק14 – "על מה
    #      זה יושב?": the suspended slab is cast on them; they were only a gap above the working level) ----
    EXC = json.load(open(os.path.join(ROOT, 'data/structure/excavation.json'), encoding='utf-8'))
    build = [{'item': b['item'], 'thickness_m': b['thickness_m'], 'source': b['source'], **({'status': b['status']} if b.get('status') else {})}
             for b in EXC['bottomBuildUp'] if b.get('thickness_m')]
    no_soil = unary_union([bsm.buffer(0), pool_zone] + [Polygon(o['footprintITM']).buffer(0) for o in out['openZones']])
    gb = [(LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2), b) for b in FR['groundBeams'] if b.get('axisITM') and b.get('layer') == 'groundFloorBeams']
    beamU = unary_union([P for P, _ in gb])
    pieces_u = []
    for s in out['slab']:
        for q in polys(Polygon(s['footprintITM'], s['holesITM']).buffer(0).difference(no_soil).difference(beamU)):
            if q.area >= 0.05: pieces_u.append({'on': s['id'], 'kind': 'slab', 'zone': s['zone'], 'footprintITM': ring(q), 'holesITM': holes(q), 'area_m2': r3(q.area), 'topRel': s['bottomRel']})
    for P, b in gb:
        for q in polys(P.difference(no_soil)):
            if q.area >= 0.02: pieces_u.append({'on': b['id'], 'kind': 'beam', 'zone': out['beamZones'].get(b['id'], 'house'), 'footprintITM': ring(q), 'holesITM': holes(q),
                                                'area_m2': r3(q.area), 'topRel': b['bottomRel']})
    out['underSlab'] = {'buildUp': build, 'pieces': pieces_u,
                        'note': 'מתחת לרצפות הקרקע ולקורות K-21 שמחוץ למרתף (רצפה תלויה): בטון רזה ומעליו ארגזי הפרדה (פוליביד). הרצפה נוצקת עליהם ונישאת על הקורות, הקירות והכלונסאות – לא על הקרקע.',
                        'source': 'data/structure/excavation.json bottomBuildUp'}
    print('under-slab build-up pieces', len(pieces_u), round(sum(p['area_m2'] for p in pieces_u), 1), 'm2')
    json.dump(out, open(os.path.join(ROOT, 'data/structure/floor-ground.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
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
        # a parapet over the outer wall line, mostly outside the slab outline (the k-41 slab face stops at the wall): the band
        # +6.65…+6.90 under it is the slab edge, cast with it – the parapet starts at the slab underside ("+8.00 / +6.65" in
        # K-41), over the first-floor block wall (Avihai 09.11, ק25 / ק32: no void over the outer block walls)
        pin = [p_ for p_ in panels41 if q.intersection(p_['poly']).area > 0.02 * q.area]
        if pin and on and on.startswith('תקרת הגג') and sum(q.intersection(p_['poly']).area for p_ in pin) < 0.5 * q.area:
            sl = max(pin, key=lambda p_: q.intersection(p_['poly']).area)
            if sl.get('D'): bot = r3(sl['top'] - sl['D'] / 100 if sl['D'] > 2 else sl['top'] - sl['D']); on = f"שפת תקרת הגג (יצוקה עם המעקה) ‎+{bot:.2f}"
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
        # close the hairline left by the 3 cm clearance above against the walls it meets (PDF fill tolerance – the K-41 hatch
        # runs on to the corner): only the sliver between the two is added, the free faces keep the drawn thickness
        nb = [Polygon(w['footprintITM']).buffer(0) for w in roof_walls] + [Polygon(w['footprintITM']).buffer(0) for w in first_walls]
        for g in nb:
            if 0 < q.distance(g) < 0.05:
                gap = q.buffer(0.05, join_style=2).intersection(g.buffer(0.05, join_style=2)).intersection(unary_union([q, g]).convex_hull).difference(g)
                if gap.area < 0.1:
                    u = unary_union([q, gap]).buffer(0.002, join_style=2).buffer(-0.002, join_style=2)
                    q = max(polys(u), key=lambda x: x.area)
        sup = [(b['topRel'], f"קורה {b['id']} (O.K {b['topRel']:+.2f})") for P, b in beam31 if q.intersection(P.buffer(0.1)).area > 0.02]
        sup += [(p['top'], f"תקרת הקרקע +{p['top']:.2f}") for p in panels31 if q.intersection(p['poly']).area > 0.25 * q.area]
        # bottom = the LOWEST support top: the wall bears on every beam under it (B-27 / B-28 corner +4.05) and the higher
        # one (B-30 +4.15) frames into it – with the highest the wall floated 10 cm over the corner (Avihai's note 2.3)
        bot = min(x[0] for x in sup) if sup else 6.65
        on = ', '.join(x[1] for x in sorted(set(sup))) if sup else None
        mr = q.minimum_rotated_rectangle; xy = list(mr.exterior.coords)
        roof_walls.append({'id': f'RW{len(roof_walls) + 1}', 'tag': None, 'footprintITM': ring(q), 'holesITM': holes(q), 'area_m2': r3(q.area),
                           'thickness_m': r3(min(math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2]))), 'bottomRel': bot, 'topRel': 8.0, 'standsOn': on,
                           'status': 'approx', 'thick': True, 'displayName': 'קיר 60 בפינת הפרגולה (ללא שם בתוכנית)',
                           'noRebar': True, 'noRebarNote': 'אין פרט זיון לקיר הזה בגיליונות K-32 / K-42 / K-43 – לא נבנה זיון במודל עד פרט מהקונסטרוקטור (הערת אביחי 2.1): פרט זיון מלא, עיגון לפינה, אישור שמדובר בזיז, K-41 בגרסת P1.',
                           'note': 'עמוד-קיר עבה בפינת הפרגולה: מילוי מוקווקו ב-K-41, ב-K-31 הערה "ליציקת הקיר!" – מראש הקורות שמתחתיו (פינת B-27 / B-28 +4.05) עד +8.00; '
                                   'אין מתחתיו קיר או עמוד בקומת הקרקע (K-21) – נושא את קצה B-30 ואת קצה B-4 בגג כזיז מהפינה (לאישור הקונסטרוקטור).',
                           'source': f'{K41P} מילוי מוקווקו (קיר); {K31P} "ליציקת הקיר!"'})
        print('thick roof wall', roof_walls[-1]['id'], r3(q.area), bot, on)
    roof_notes(roof_walls, roof_beams, first_walls, first_cols, beams, m41, to)
    json.dump(out, open(os.path.join(ROOT, 'data/structure/floor-ground.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)   # B-30 into the corner wall
    verts41 = [(Polygon(e['footprintITM'], e.get('holesITM') or []).buffer(0), e['bottomRel'], e['topRel'], e['id']) for e in first_walls + first_cols + roof_walls]
    print('beam ends run on to their support K-41', bear_beam_ends(roof_beams, verts41, [(p['poly'], p['top'], p['D']) for p in panels41], bars_of('K-42')))
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

#!/usr/bin/env python3
"""Stage 4a – block walls (Ytong 60×25) -> data/architecture/blocks.json  (run after extract_floor / extract_openings).

Source of the walls: the architect's Revit floor plans (blocks martef / pituah / alef in the plumbing DXF, placed on the
structural sheets by tools/extract_openings.place): cut walls = A-WALL-PATT hatch, partitions = thin faces of the I-WALL /
A-WALL line pairs. Block wall = that minus the concrete already in the model (walls, columns, basement walls, perimeter
walls) and minus whatever lies outside the building.
  - each wall piece is split into straight runs (rectangles in the house axes); thickness = drawn thickness
  - bottom = top of the concrete under it (slab / beam), top = underside of the slab / beam over it
  - openings = the architect's windows / doors with no concrete host (openings.json, host None); their head (O.K) already
    includes the roller-shutter box – the box height per family is read from the family's elevation in the permit sheet
    (gramushka): the band between the frame top and the family top
  - courses: block size from data/config/blocks.json (owner's choice: Ytong 60×25), half-block bond
Quantities per floor / thickness: full + cut blocks, wall area, volume, shutter boxes, lintels."""
import json, math, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezdxf
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union, polygonize
from shapely import affinity
import extract_openings as O

ROOT = O.ROOT if hasattr(O, 'ROOT') else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
r3 = lambda v: round(float(v), 3)
polys = lambda g: [q for q in getattr(g, 'geoms', [g]) if q.geom_type == 'Polygon' and not q.is_empty]
P = lambda r, h=None: Polygon(r, h or []).buffer(0)


def house_axis(FG):
    """main direction of the house (longest edge of the biggest ground slab)"""
    s = max(FG['slab'], key=lambda s: s['area_m2'])['footprintITM']
    e = max(((s[i], s[(i + 1) % len(s)]) for i in range(len(s))), key=lambda e: math.dist(*e))
    return math.degrees(math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0]))


def rect_runs(g, ang, min_area=0.02):
    """split a wall piece into straight rectangular runs: rotate into the house axes, cut along the lines through the
    reflex vertices until every part fills ≥ 85 % of its bounding box"""
    c = g.centroid; q = affinity.rotate(g, -ang, origin=c)
    out, todo = [], [q]
    while todo:
        p = todo.pop()
        if p.area < min_area: continue
        x0, y0, x1, y1 = p.bounds
        if p.area >= 0.85 * (x1 - x0) * (y1 - y0) or len(out) > 400:
            out.append(p); continue
        xs = sorted({round(x, 3) for x, _ in p.exterior.coords if x0 + 0.01 < x < x1 - 0.01})
        ys = sorted({round(y, 3) for _, y in p.exterior.coords if y0 + 0.01 < y < y1 - 0.01})
        cut = None
        if xs and (x1 - x0) >= (y1 - y0) or not ys: cut = box(x0 - 1, y0 - 1, xs[len(xs) // 2], y1 + 1) if xs else None
        else: cut = box(x0 - 1, y0 - 1, x1 + 1, ys[len(ys) // 2])
        if cut is None: out.append(p); continue
        parts = polys(p.intersection(cut)) + polys(p.difference(cut))
        if len(parts) < 2: out.append(p); continue
        todo += parts
    res = []
    for p in out:
        x0, y0, x1, y1 = p.bounds; w, h = x1 - x0, y1 - y0
        if min(w, h) < 0.05: continue
        along_x = w >= h
        fill = p.area / (w * h)
        if fill < 0.85:   # could not be cut into a clean rectangle (a stub on its side): mean thickness, centred on the bulk
            L = max(w, h); t = p.area / L
            if along_x: yc = p.centroid.y; y0, y1 = yc - t / 2, yc + t / 2
            else: xc = p.centroid.x; x0, x1 = xc - t / 2, xc + t / 2
            w, h = x1 - x0, y1 - y0
        a = ((x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)) if along_x else (((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1))
        A = [affinity.rotate(Point(*pt), ang, origin=c) for pt in a]
        res.append({'axisITM': [[r3(A[0].x), r3(A[0].y)], [r3(A[1].x), r3(A[1].y)]], 'length_m': r3(max(w, h)), 'thickness_m': r3(min(w, h)),
                    'poly': affinity.rotate(box(x0, y0, x1, y1), ang, origin=c)})
    return res


def shutter_boxes():
    """roller-shutter box height of each window family, from its section / elevation blocks in the permit sheet: the box is
    the band between the first two full-width horizontals (from the top) that are 20–60 cm apart; the family top = the
    opening head (O.K), so the box sits inside the opening"""
    d = J(O.PERMIT)
    out = {}
    for b in d['blocks']:
        n = b.get('name') or ''
        if not ('גלילה' in n or 'תריס' in n) or not ('חזית' in n or 'חתך' in n): continue
        m = O.NAME.match(n); rid = m.group(2) if m else None
        if not rid or rid in out: continue
        segs = [((e['startPoint']['x'], e['startPoint']['y']), (e['endPoint']['x'], e['endPoint']['y'])) for e in b['entities'] if e['type'] == 'LINE']
        for e in b['entities']:
            if e['type'] == 'HATCH':
                for bp in e.get('boundaryPaths') or []:
                    segs += [((g['start']['x'], g['start']['y']), (g['end']['x'], g['end']['y'])) for g in bp.get('edges') or [] if g.get('type') == 1]
        if not segs: continue
        xs = [p[0] for sg in segs for p in sg]; W = max(xs) - min(xs)
        if W < 50: continue                                   # side view of the family
        hy = sorted({round(a[1], 1) for a, c in segs if abs(a[1] - c[1]) < 0.01 and abs(a[0] - c[0]) > 0.8 * W}, reverse=True)
        top = max(p[1] for sg in segs for p in sg); bot = min(p[1] for sg in segs for p in sg)
        for y1, y0 in zip(hy, hy[1:]):
            if 20 <= y1 - y0 <= 60:
                out[rid] = {'box_cm': round(y1 - y0, 1), 'familyTopOverBox_cm': round(top - y1, 1), 'familyHeight_cm': round(top - bot, 1), 'block': n}
                break
    return out


def count_blocks(L, zb, zt, wo, BL, BH, bond=None, datum=None):
    """courses (bond: half a block on every other course), blocks clipped by the openings -> full, cut, courses, net area.
    bond = {'p0', 'sign'}: the run's start on the wall line's own axis – every run of one straight wall shares one block
    grid (head joints line up across runs, Avihai 09.11); datum = the floor's course line – every course boundary sits
    on datum + k x BH (the first course is cut to fit). js/geometry/blocks.js lays the same grid."""
    nfull = ncut = 0; area = L * (zt - zb); z = zb; k = 0
    while z < zt - 0.005:
        kk = round((z - datum) / BH) if datum is not None else k            # course number on the floor grid
        nxt = datum + (kk + 1) * BH if datum is not None else z + BH
        if nxt - z < 0.005: nxt += BH
        h = min(nxt - z, zt - z); off = (BL / 2) * (kk % 2)
        x0 = ((bond['sign'] * (off - bond['p0'])) % BL) - BL if bond else -off
        # an opening / lintel edge inside the course splits it into bands: the blocks are cut at the head / lintel
        # underside, not dropped (Avihai 09.11 – a gap under the lintels beside the windows)
        cuts = sorted({z, z + h} | {c for o in wo for c in (o['z0'], o['z1']) if z + 0.005 < c < z + h - 0.005})
        for zb_, zt_ in zip(cuts, cuts[1:]):
            segs = [(0.0, L)]
            for o in wo:
                if o['z0'] < zt_ - 0.005 and o['z1'] > zb_ + 0.005:
                    segs = [p for a, b in segs for p in ((a, min(b, o['s0'])), (max(a, o['s1']), b)) if p[1] - p[0] > 0.005]
            hb = zt_ - zb_
            for a, b in segs:
                x = x0
                while x < b - 0.005:
                    xa, xb = max(x, a), min(x + BL, b)
                    if xb - xa > 0.005:
                        if xb - xa >= BL - 0.005 and hb >= BH - 0.005: nfull += 1
                        else: ncut += 1
                    x += BL
        k += 1; z += h
    for o in wo: area -= (o['s1'] - o['s0']) * (o['z1'] - o['z0'])
    return nfull, ncut, k, area


def split_by_levels(run, under_fl, over_fl, step=0.05, min_len=0.15):
    """a run that stands on (or carries) concrete at different levels along its length – part on the slab, part on an
    upturned beam (ק27) – is split where the level changes, so each part gets its own bottom / top (no gap under / over the
    blocks). Levels sampled on the axis every 5 cm; parts shorter than 15 cm join their neighbour."""
    (x0, y0), (x1, y1) = run['axisITM']; L = run['length_m']
    if L < 2 * min_len: return [run]
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    def lev(lst, pt, pick):
        z = [zz for g, zz in lst if g.covers(pt)]
        return round(pick(z), 2) if z else None
    n = int(L / step); keys = []
    for i in range(n + 1):
        sp = min(L, (i + 0.5) * step) if i < n else L - 0.01
        pt = Point(x0 + ux * sp, y0 + uy * sp)
        keys.append((lev(under_fl, pt, max), lev(over_fl, pt, min)))
    groups = []
    for i, k in enumerate(keys):
        s0 = i * step
        if groups and groups[-1][2] == k: groups[-1][1] = min(L, s0 + step)
        else: groups.append([s0, min(L, s0 + step), k])
    groups[-1][1] = L
    while len(groups) > 1:                                    # absorb short parts into the longer neighbour
        i = min(range(len(groups)), key=lambda j: groups[j][1] - groups[j][0])
        if groups[i][1] - groups[i][0] >= min_len: break
        j = i - 1 if i == len(groups) - 1 or (i > 0 and groups[i - 1][1] - groups[i - 1][0] >= groups[i + 1][1] - groups[i + 1][0]) else i + 1
        a, b = sorted((i, j)); groups[a] = [groups[a][0], groups[b][1], groups[j][2]]; del groups[b]
        k2 = []                                               # re-merge equal neighbours
        for gg in groups:
            if k2 and k2[-1][2] == gg[2]: k2[-1][1] = gg[1]
            else: k2.append(gg)
        groups = k2
    if len(groups) == 1: return [run]
    out = []
    for a, b, _ in groups:
        ax = [[r3(x0 + ux * a), r3(y0 + uy * a)], [r3(x0 + ux * b), r3(y0 + uy * b)]]
        out.append({**run, 'axisITM': ax, 'length_m': r3(b - a), 'poly': LineString(ax).buffer(run['thickness_m'] / 2, cap_style=2), 'splitByLevel': True})
    return out


def context():
    """concrete per floor, the surfaces under / over each floor (polygon, level rel. ±0.00) and the building outline –
    shared with tools/verify_blocks.py"""
    FR, FG, FF, FRF = J('data/structure/framing.json'), J('data/structure/floor-ground.json'), J('data/structure/floor-first.json'), J('data/structure/floor-roof.json')
    PER, OPN = J('data/structure/perimeter.json'), J('data/architecture/openings.json')
    ang = house_axis(FG)
    bpoly = lambda b: LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2)
    # concrete per floor, the surfaces under / over each floor, and the building outline
    conc = {
        'unit': [P(p['ringITM'], p.get('holesITM')) for w in FR['basementWalls'] for p in (w.get('partsITM') or [{'ringITM': w['footprintITM'], 'holesITM': w.get('holesITM')}])],
        'ground': [P(w['footprintITM'], w.get('holesITM')) for w in FG['walls']] + [P(c['footprintITM']) for c in FG['columns']] + [P(w['ringITM']) for w in PER['walls']],
        'first': [P(w['footprintITM'], w.get('holesITM')) for w in FF['walls']] + [P(c['footprintITM']) for c in FF['columns']] + [P(w['footprintITM']) for w in FRF['walls'] if w['bottomRel'] < 6],
    }
    under = {
        'unit': [(P(s.get('outlineITM') or s['footprintITM'], s.get('holesITM')), s['top']) for s in FR['slabs'] if s.get('level') == 'basement'],
        'ground': [(P(s['footprintITM'], s.get('holesITM')), s['topRel']) for s in FG['slab']]
                  + [(bpoly(b), b['topRel']) for b in FR['groundBeams'] if b.get('axisITM') and b.get('sheet') == 'K-21']   # upturned ground beams (B-45 +0.20)
                  + [(P(c['footprintITM'], c.get('holesITM')), c['topRel']) for c in FG.get('basementWallCaps', [])],
        'first': [(P(s['footprintITM'], s.get('holesITM')), s['topRel']) for s in FG['ceiling']['slab']] + [(bpoly(b), b['topRel']) for b in FG['ceiling']['beams'] if b.get('axisITM')],
    }
    over = {
        'unit': [(P(s['footprintITM'], s.get('holesITM')), s['bottomRel'] if 'bottomRel' in s else s['topRel'] - s['thickness_m']) for s in FG['slab']]
                + [(bpoly(b), b['bottomRel']) for b in FR['groundBeams'] if b.get('axisITM') and b.get('sheet') == 'K-21'],
        'ground': [(P(s['footprintITM'], s.get('holesITM')), s['bottomRel']) for s in FG['ceiling']['slab']] + [(bpoly(b), b['bottomRel']) for b in FG['ceiling']['beams'] if b.get('axisITM')]
                  + [(P(s['footprintITM'], s.get('holesITM')), s['bottomRel']) for s in FF['ceiling']['slab']],
        'first': [(P(s['footprintITM'], s.get('holesITM')), s['bottomRel']) for s in FF['ceiling']['slab']] + [(bpoly(b), b['bottomRel']) for b in FRF['ceiling']['beams'] if b.get('axisITM')]
                 + [(P(w['footprintITM'], w.get('holesITM')), w['bottomRel']) for w in FRF['walls'] if 6 <= w['bottomRel'] < 7],   # roof slab edge / parapets
    }
    inside = {fl: unary_union([g for g, _ in over[fl]] + [g for g, _ in under[fl]]).buffer(0.35) for fl in over}
    return dict(FR=FR, FG=FG, FF=FF, FRF=FRF, PER=PER, OPN=OPN, ang=ang, conc=conc, under=under, over=over, inside=inside, bpoly=bpoly)


def main():
    CFG = J('data/config/blocks.json')
    BL, BH = CFG['block']['length_m'], CFG['block']['height_m']
    C = context()
    FR, FG, FF, FRF, PER, OPN, ang = (C[k] for k in ('FR', 'FG', 'FF', 'FRF', 'PER', 'OPN', 'ang'))
    conc, under, over, inside, bpoly = (C[k] for k in ('conc', 'under', 'over', 'inside', 'bpoly'))
    boxes = shutter_boxes()
    msp = ezdxf.readfile(os.path.join(ROOT, O.SRC)).modelspace()
    walls, Q = [], defaultdict(lambda: defaultdict(float))
    boxes_out, lintels, outside = [], [], []
    for fl, (blk, dxf, ffl, _) in O.FLOORS.items():
        ents, to, _ = O.place(msp, blk, dxf)
        H = []
        for v in ents:
            if v.dxftype() == 'HATCH' and v.dxf.layer == 'A-WALL-PATT':
                for p in v.paths:
                    vs = [(q[0], q[1]) for q in p.vertices] if hasattr(p, 'vertices') else [(e.start[0], e.start[1]) for e in p.edges if e.EDGE_TYPE == 'LineEdge']
                    if len(vs) >= 3: H.append(Polygon([to(*q) for q in vs]).buffer(0))
        WL = [LineString([to(v.dxf.start.x, v.dxf.start.y), to(v.dxf.end.x, v.dxf.end.y)]) for v in ents if v.dxftype() == 'LINE' and v.dxf.layer in ('A-WALL', 'I-WALL')]
        thin = [f for f in polygonize(unary_union(WL)) if f.area > 0.02 and 2 * f.area / f.length < 0.30]
        R = unary_union(H + thin).buffer(0.002).buffer(-0.002)
        ops = [o for o in OPN['openings'] if o['floor'] == fl and not o.get('host') and not o.get('castFrame')]
        # the cut-wall hatch stops at the windows / doors: the wall under the sill and over the head is closed again, as
        # thick as the wall on both sides of the opening (sill / head levels come from the openings, below)
        fills = []
        for o in ops:
            (E, N), (ax, ay) = o['centerITM'], o['axisITM']; n_ = math.hypot(ax, ay); ux, uy = ax / n_, ay / n_
            rect = lambda w, d: Polygon([(E - ux * w / 2 - uy * d / 2, N - uy * w / 2 + ux * d / 2), (E + ux * w / 2 - uy * d / 2, N + uy * w / 2 + ux * d / 2),
                                         (E + ux * w / 2 + uy * d / 2, N + uy * w / 2 - ux * d / 2), (E - ux * w / 2 + uy * d / 2, N - uy * w / 2 - ux * d / 2)])
            fl_ = R.intersection(rect(o['width_m'] + 0.4, 0.8))
            if fl_.is_empty: continue
            # the wall the opening sits in = the pieces just beside the jambs, along the opening axis (a wall meeting the
            # jamb at right angles, or a parallel wall nearby, spans the whole probe depth and is ignored)
            # cross-section of the wall a few cm past each jamb (a wall meeting the jamb would widen a whole-piece measure)
            ext = []
            for sd in (-1, 1):
                for dt in (0.04, 0.08, 0.12):
                    tt = sd * (o['width_m'] / 2 + dt)
                    line = LineString([(E + ux * tt - uy * 0.4, N + uy * tt + ux * 0.4), (E + ux * tt + uy * 0.4, N + uy * tt - ux * 0.4)])
                    for seg in [g for g in getattr(R.intersection(line), 'geoms', [R.intersection(line)]) if g.geom_type == 'LineString' and g.length > 0.04]:
                        nn = [(x - E) * (-uy) + (y - N) * ux for x, y in seg.coords]
                        if max(nn) - min(nn) <= 0.45: ext.append((abs((min(nn) + max(nn)) / 2), min(nn), max(nn)))
            if not ext: continue
            _, a, b = min(ext); mid = (a + b) / 2          # the section nearest the opening's centre line
            f = rect(o['width_m'] + 0.02, b - a); fills.append(affinity.translate(f, -uy * mid, ux * mid))
        R = unary_union([R] + fills)
        C = unary_union(conc[fl]).buffer(0.0005)   # the blocks run up to the concrete face (was 1 cm – a gap at every joint, ק26 / ק33)
        # morphological opening: drawing slivers < 4 cm (line ends, hatch seams) are not wall – they made a 10 cm partition at a
        # door look 45 cm thick
        pieces = [q for g in polys(R.difference(C).intersection(inside[fl])) for q in polys(g.buffer(-0.02, join_style=2).buffer(0.02, join_style=2))
                  if q.area > 0.03 and 2 * q.area / q.length > 0.05]
        for g in pieces:
            for run in [r_ for r0 in rect_runs(g, ang) for r_ in split_by_levels(r0, under[fl], over[fl])]:
                rp = run['poly']
                if run['thickness_m'] < 0.06 or run['length_m'] < 0.10: continue
                bot = [z for s, z in under[fl] if s.intersection(rp).area > 0.3 * rp.area]
                top = [z for s, z in over[fl] if s.intersection(rp).area > 0.3 * rp.area]
                st = 'source'; note = None
                # an exterior wall carries the slab / beam whose edge runs along its inner face (the slab outline stops at
                # the wall – K-41 RS1 over the first floor): a slab / beam touching the run along ≥ half its length counts
                # as over / under it (permit plans: these walls are block, red, 22 / 30 cm)
                touch = lambda lst: [z for s, z in lst if s.buffer(0.03).intersection(rp).area >= 0.5 * run['length_m'] * 0.02]
                if not top:
                    top = touch(over[fl])
                    if top: note = 'רום עליון: תחתית התקרה / הקורה הצמודה לפאה הפנימית של הקיר (שפת התקרה נגמרת בקיר)'
                if not bot and top: bot = touch(under[fl])
                if not top: outside.append({'floor': fl, 'axisITM': run['axisITM'], 'length_m': run['length_m'], 'thickness_m': run['thickness_m']}); continue   # no ceiling over it: garden / fence wall (development)
                if not bot: bot = [max(z for _, z in under[fl])]; st = 'approx'
                zb, zt = max(bot), min(top)
                if zt - zb < 0.3: continue
                (x0, y0), (x1, y1) = run['axisITM']; L = run['length_m']; ux, uy = (x1 - x0) / L, (y1 - y0) / L
                wo = []
                for o in ops:
                    c = Point(o['centerITM'])
                    if rp.buffer(0.05).contains(c) and abs(o['axisITM'][0] * uy - o['axisITM'][1] * ux) / (math.hypot(*o['axisITM']) or 1) < 0.3:
                        s = (c.x - x0) * ux + (c.y - y0) * uy
                        # a door at floor level (sill = finished floor): the rough opening in the blocks goes down to the concrete
                        # the wall stands on – the floor build-up fills it (Avihai ק37, 09.11: no block strip in the door line)
                        atFloor = o['kind'] in ('door', 'sliding') and o.get('floorFinishRel') is not None and o['sillRel'] <= o['floorFinishRel'] + 0.01
                        wo.append({'id': o['id'], 'kind': o['kind'], 's0': r3(max(0, s - o['width_m'] / 2)), 's1': r3(min(L, s + o['width_m'] / 2)), 'z0': r3(zb) if atFloor else o['sillRel'], 'z1': o['headRel'],
                                   'clip': [sd for sd, c in (('L', s - o['width_m'] / 2 < -0.005), ('R', s + o['width_m'] / 2 > L + 0.005)) if c],
                                   'shutter': ('גלילה' in o['name'] or 'תריס' in o['name'])})
                nfull, ncut, k, area = count_blocks(L, zb, zt, wo, BL, BH)
                tcm = round(run['thickness_m'] * 100)
                Q[fl][f't{tcm}_full'] += nfull; Q[fl][f't{tcm}_cut'] += ncut; Q[fl][f't{tcm}_m2'] += area
                walls.append({'id': f'BK-{fl[0].upper()}{len(walls) + 1}', 'floor': fl, 'axisITM': run['axisITM'], 'length_m': L, 'thickness_m': run['thickness_m'],
                              'bottomRel': r3(zb), 'topRel': r3(zt), 'openings': wo, 'courses': k, 'blocksFull': nfull, 'blocksCut': ncut, 'area_m2': r3(area),
                              'status': st, 'source': f'{O.SRC} (תוכנית Revit {blk}: A-WALL-PATT / I-WALL) פחות הבטון במודל; מפלסים: הבטון שמתחת / מעל',
                              **({'levelNote': note} if note else {})})
        for o in ops:
            if not ('גלילה' in o['name'] or 'תריס' in o['name']): continue
            b = boxes.get(str(o['revitId']))
            boxes_out.append({'opening': o['id'], 'floor': fl, 'width_m': o['width_m'], 'headRel': o['headRel'],
                              'box_m': r3(b['box_cm'] / 100) if b else None, 'frameTop_m': r3(b['familyTopOverBox_cm'] / 100) if b else None,
                              'status': 'source' if b else 'missing', 'source': f"{O.PERMIT_SRC}: {b['block']}" if b else 'אין חזית למשפחה בגרמושקה'})
    # a wall drawn as two parallel hatch strips (seam line, e.g. 30 = 20 + 10): the strip with no slab of its own lies beside
    # a block run on the same floor along ≥ half its length -> one run, as thick as both (levels / blocks from the run)
    def strip(a, t, L):
        (x0, y0), (x1, y1) = a; return LineString(a).buffer(t / 2, cap_style=2), ((x1 - x0) / L, (y1 - y0) / L)
    # two runs of one straight wall left a few cm apart (hatch seam at a jamb / door frame, ק26 / ק33): extend both to meet
    for i, w in enumerate(walls):
        for v in walls[i + 1:]:
            if v['floor'] != w['floor'] or abs(v['thickness_m'] - w['thickness_m']) > 0.015 or (w['bottomRel'], w['topRel']) != (v['bottomRel'], v['topRel']): continue
            (a0, a1), (b0, b1) = w['axisITM'], v['axisITM']; ux, uy = (a1[0] - a0[0]) / w['length_m'], (a1[1] - a0[1]) / w['length_m']
            vx, vy = (b1[0] - b0[0]) / v['length_m'], (b1[1] - b0[1]) / v['length_m']
            if abs(ux * vy - uy * vx) > 0.02: continue
            best = min(((math.dist(p, q), pi, qi) for pi, p in enumerate((a0, a1)) for qi, q in enumerate((b0, b1))), key=lambda t: t[0])
            d, pi, qi = best
            p, q = (a0, a1)[pi], (b0, b1)[qi]
            lat = abs((q[0] - p[0]) * -uy + (q[1] - p[1]) * ux)
            if not (0.005 < d < 0.08) or lat > 0.01: continue
            m = [r3((p[0] + q[0]) / 2), r3((p[1] + q[1]) / 2)]
            for r_, idx, old in ((w, pi, p), (v, qi, q)):
                ax = [list(r_['axisITM'][0]), list(r_['axisITM'][1])]; ax[idx] = m
                Ln = r3(math.dist(*ax)); grow = Ln - r_['length_m']
                if idx == 0:                                         # the run grew at its start: openings shift along
                    for o in r_['openings']: o['s0'] = r3(o['s0'] + grow); o['s1'] = r3(o['s1'] + grow)
                r_['axisITM'] = ax; r_['length_m'] = Ln
                r_['blocksFull'], r_['blocksCut'], r_['courses'], ar = count_blocks(Ln, r_['bottomRel'], r_['topRel'], r_['openings'], BL, BH); r_['area_m2'] = r3(ar)
                r_['joinedGap_m'] = r3(d)
    # lintels (owner's choice 08.11: lintel block, "as is customary"; 09.11 ק23/ק28–ק30: over the windows too): every opening of
    # data/config/blocks.json lintel.kinds with blocks over its head gets one course on the head, bearing into the blocks on both
    # sides (lintel.bearing_m – common practice, provisional). A side with less block than that rests on the concrete when the run
    # ends there, continues in the next run when the opening is split over two runs, else is flagged (shortBearing).
    LT = CFG['lintel']; BEAR = LT['bearing_m']['value']; KINDS = set(LT.get('kinds') or [])
    concU = {fl: unary_union(conc[fl]) for fl in conc}
    def near_conc(w, sd):
        (x0, y0), (x1, y1) = w['axisITM']; p = Point(x0, y0) if sd == 'L' else Point(x1, y1)
        return concU[w['floor']].distance(p) < w['thickness_m'] / 2 + 0.03
    # course line of each floor (most common bottom = the slab): the lintel top lands on it, so the course over the lintel
    # is a full course (lintel = one block course + the bed to the line, ≥ 20 cm)
    fdat = {}
    for fl in {w['floor'] for w in walls}:
        cnt = defaultdict(float)
        for w in walls:
            if w['floor'] == fl: cnt[w['bottomRel']] += w['length_m']
        fdat[fl] = max(cnt, key=cnt.get)
    for w in walls:
        w['lintels'] = []
        for o in sorted(w['openings'], key=lambda o: o['s0']):
            gap = w['topRel'] - o['z1']
            if o.get('kind') not in KINDS or gap < LT.get('minHeadGap_m', 0.05) or o['s1'] - o['s0'] >= w['length_m'] - 0.02 and not o.get('clip'): continue
            bl, br = min(BEAR, o['s0']), min(BEAR, w['length_m'] - o['s1'])
            w['lintels'].append({'id': f"LT-{o['id']}", 'opening': o['id'], 's0': r3(o['s0'] - bl), 's1': r3(o['s1'] + br), 'z0': o['z1'], 'z1': r3(min(w['topRel'], fdat[w['floor']] + math.ceil((o['z1'] + LT.get('minHeight_m', 0.2) - fdat[w['floor']]) / BH - 1e-6) * BH)),
                                 'bearL_m': r3(bl), 'bearR_m': r3(br), 'length_m': r3(o['s1'] - o['s0'] + bl + br), 'status': LT['bearing_m']['status'],
                                 'onConcrete': [sd for sd, bb in (('L', bl), ('R', br)) if bb < BEAR - 0.005 and near_conc(w, sd)],
                                 'continues': [sd for sd in o.get('clip', []) if not near_conc(w, sd)]})
        # lintels of neighbouring openings with different heads (door 2.10 / window 2.30) must not overlap: each bearing
        # stops at the middle of the pier between them (Avihai 09.11 – the lintels crossed each other)
        ls = sorted(w['lintels'], key=lambda l: l['s0'])
        for a_, b_ in zip(ls, ls[1:]):
            if b_['s0'] < a_['s1'] and abs(a_['z0'] - b_['z0']) >= 0.01:
                oa = next(o for o in w['openings'] if o['id'] == a_['opening']); ob = next(o for o in w['openings'] if o['id'] == b_['opening'])
                mid = r3((oa['s1'] + ob['s0']) / 2)
                a_['s1'] = mid; a_['bearR_m'] = r3(mid - oa['s1']); b_['s0'] = mid; b_['bearL_m'] = r3(ob['s0'] - mid)
                for l_ in (a_, b_): l_['length_m'] = r3(l_['s1'] - l_['s0']); l_['sharedPier'] = True
        # two lintels of one wall at the same head that would overlap (openings < 2 x bearing apart): one lintel over both
        merged = []
        for lt in w['lintels']:
            if merged and lt['s0'] < merged[-1]['s1'] and abs(lt['z0'] - merged[-1]['z0']) < 0.01:
                m = merged[-1]; m['s1'] = lt['s1']; m['bearR_m'] = lt['bearR_m']; m['opening'] += '+' + lt['opening']; m['id'] += '+' + lt['opening']
                m['length_m'] = r3(m['s1'] - m['s0']); m['onConcrete'] = sorted(set(m['onConcrete']) | {x for x in lt['onConcrete'] if x == 'R'})
            else: merged.append(lt)
        w['lintels'] = merged
        if w['lintels']:
            w['blocksFull'], w['blocksCut'], w['courses'], ar = count_blocks(w['length_m'], w['bottomRel'], w['topRel'], w['openings'] + w['lintels'], BL, BH)
            w['area_m2'] = r3(ar)
    for w in walls:
        for lt in w['lintels']:
            n = sum(1 for w_ in walls for x in w_['lintels'] if x['opening'] == lt['opening'])
            if n > 1: lt['id'] = f"{lt['id']}-{w['id'].split('-')[-1]}"
            lt['continues'] = [sd for sd in lt['continues'] if n > 1]
            atEnd = lambda sd: lt['s0'] < 0.005 if sd == 'L' else lt['s1'] > w['length_m'] - 0.005
            sb = [sd for sd, bb in (('L', lt['bearL_m']), ('R', lt['bearR_m'])) if bb < BEAR - 0.005 and sd not in lt['onConcrete'] and sd not in lt['continues']]
            lt['pier'] = [sd for sd in sb if not atEnd(sd)]           # bearing cut at the middle of a pier between two openings
            short = [sd for sd in sb if atEnd(sd)]
            # the run ends against a crossing block wall: the lintel bears into it (built with it, same courses)
            (x0, y0), (x1, y1) = w['axisITM']
            cross = lambda sd: any(LineString(v['axisITM']).buffer(v['thickness_m'] / 2 + 0.03, cap_style=2).contains(Point((x0, y0) if sd == 'L' else (x1, y1)))
                                   for v in walls if v is not w and v['floor'] == w['floor'])
            lt['intoCrossWall'] = [sd for sd in short if cross(sd)]
            lt['shortBearing'] = [sd for sd in short if sd not in lt['intoCrossWall']]
    # a short side that ends against the next run of the same straight wall (split by level / seam): the lintel carries
    # on into that run for the rest of its bearing (Avihai 09.11 – the lintel stopped at the run end)
    for w in walls:
        (x0, y0), (x1, y1) = w['axisITM']; L = w['length_m']; ux, uy = (x1 - x0) / L, (y1 - y0) / L
        for lt in list(w['lintels']):
            if lt.get('stubOf'): continue
            for sd in [x for x in lt['shortBearing'] + lt['intoCrossWall']]:
                end = (x0, y0) if sd == 'L' else (x1, y1); need = r3(BEAR - (lt['bearL_m'] if sd == 'L' else lt['bearR_m']))
                for v in walls:
                    if v is w or v['floor'] != w['floor']: continue
                    (a0, b0), (a1, b1) = v['axisITM']; Lv = v['length_m']; vx, vy = (a1 - a0) / Lv, (b1 - b0) / Lv
                    if abs(ux * vy - uy * vx) > 0.02: continue
                    if math.dist(end, (a0, b0)) < 0.02: s0, s1 = 0.0, min(need, Lv)
                    elif math.dist(end, (a1, b1)) < 0.02: s0, s1 = max(0.0, Lv - need), Lv
                    else: continue
                    if any(o['s0'] < s1 and o['s1'] > s0 and o['z1'] > lt['z0'] and o['z0'] < lt['z1'] for o in v['openings']) or lt['z1'] > v['topRel'] + 0.005: continue
                    v.setdefault('lintels', []).append({**{k: lt[k] for k in ('opening', 'z0', 'z1', 'status')}, 'id': f"{lt['id']}-{sd}", 's0': r3(s0), 's1': r3(s1),
                                                        'bearL_m': 0.0, 'bearR_m': 0.0, 'length_m': r3(s1 - s0), 'stubOf': lt['id'],
                                                        'onConcrete': [], 'continues': [], 'intoCrossWall': [], 'shortBearing': []})
                    for key in ('shortBearing', 'intoCrossWall'):
                        if sd in lt[key]: lt[key].remove(sd)
                    lt['continues'] = sorted(set(lt['continues']) | {sd}); lt['continuedIn'] = v['id']
                    break
    for o in list(outside):
        po, (ox, oy) = strip(o['axisITM'], o['thickness_m'], o['length_m'])
        for w in walls:
            if w['floor'] != o['floor']: continue
            pw, (wx, wy) = strip(w['axisITM'], w['thickness_m'], w['length_m'])
            if abs(ox * wy - oy * wx) > 0.05 or po.distance(pw) > 0.01: continue
            if po.buffer(0.01).intersection(pw).area < 0.5 * min(o['length_m'], w['length_m']) * 0.01: continue
            m = unary_union([pw, po.buffer(0.005, join_style=2)]).minimum_rotated_rectangle
            (x0, y0), (x1, y1) = w['axisITM']; nx, ny = -wy, wx
            off = [(px - x0) * nx + (py - y0) * ny for px, py in m.exterior.coords]
            lo, hi = min(off), max(off); mid = (lo + hi) / 2
            w['axisITM'] = [[r3(x0 + nx * mid), r3(y0 + ny * mid)], [r3(x1 + nx * mid), r3(y1 + ny * mid)]]
            w['thickness_m'] = r3(hi - lo - 0.01)
            w['mergedStrip_m'] = o['thickness_m']; outside.remove(o); break
    # drawn thickness -> the dominant wall thicknesses of the plans (≥ 5 m of wall each), ±2 cm (joint slivers / hatch
    # tolerance); quantities are recomputed per snapped thickness
    tl = defaultdict(float)
    for w in walls: tl[round(w['thickness_m'] * 100)] += w['length_m']
    dom = sorted(t for t, L in tl.items() if L >= 5)
    Q.clear()
    for w in walls:
        t = round(w['thickness_m'] * 100); near = min(dom, key=lambda d: abs(d - t)) if dom else t
        w['drawnThickness_m'] = w['thickness_m']
        if abs(near - t) <= 2: w['thickness_m'] = near / 100
        else: w['status'] = 'approx'; w['note'] = f'עובי {t} ס"מ לא תואם לעוביי הקירות בתוכנית ({dom}) – לבדיקה'
        tc = round(w['thickness_m'] * 100)
        Q[w['floor']][f't{tc}_full'] += w['blocksFull']; Q[w['floor']][f't{tc}_cut'] += w['blocksCut']; Q[w['floor']][f't{tc}_m2'] += w['area_m2']
    # the box height written in the permit plans' dimension chains ("220 +35") wins over the family elevation measure
    PL = J('tools/shutter-box-plans.json')
    for r in PL['readings']:
        for b in boxes_out:
            if b['opening'] in r['openings']:
                if b['box_m'] is not None and abs(b['box_m'] * 100 - r['box_cm']) > 0.5: b['elevationBox_m'] = b['box_m']
                b.update(box_m=r['box_cm'] / 100, status='source', source=f"{PL['source_folder']} / {r['sheet']}: \"{r['text']}\" ({r['where']})")
    # a family with no section / elevation band in the permit sheet: the box of the same family type (approx)
    fam = lambda o: re.sub(r'\s*-\s*[^-]*$', '', o).strip()
    for b in boxes_out:
        if b['box_m'] is not None: continue
        o = next(x for x in OPN['openings'] if x['id'] == b['opening'])
        same = [x for x in boxes_out if x['box_m'] is not None and fam(next(y for y in OPN['openings'] if y['id'] == x['opening'])['name']) == fam(o['name'])]
        if same: b.update(box_m=same[0]['box_m'], status='approx', source=f"כמו {same[0]['opening']} (אותו סוג משפחה) – אין חתך / חזית למשפחה בגרמושקה")
    # manual checks of the odd-thickness runs against the permit plans (tools/blocks-plan-checks.json)
    for c in J('tools/blocks-plan-checks.json')['checks']:
        for w in walls:
            (x0, y0), (x1, y1) = w['axisITM']
            if w['floor'] != c['floor'] or math.dist(((x0 + x1) / 2, (y0 + y1) / 2), c['centerITM']) > 0.10: continue
            if c['thickness_m']:
                if c.get('insidePointITM'):   # the extra drawn depth is outside (cladding): keep the inner face
                    L = w['length_m']; nx, ny = -(y1 - y0) / L, (x1 - x0) / L; ix, iy = c['insidePointITM']
                    if (ix - x0) * nx + (iy - y0) * ny < 0: nx, ny = -nx, -ny
                    d = (w['thickness_m'] - c['thickness_m']) / 2
                    w['axisITM'] = [[r3(x0 + nx * d), r3(y0 + ny * d)], [r3(x1 + nx * d), r3(y1 + ny * d)]]
                w['thickness_m'] = c['thickness_m']
            w['status'] = c['status']; w['note'] = 'בדיקה מול תוכנית ההיתר (08.11): ' + c['finding']
    # one bond for the whole house: block grid along each wall line (house axes) and one course line per floor (the most
    # common bottom = the floor slab) – the head joints of neighbouring runs line up, no half-course steps (Avihai 09.11)
    hx, hy = math.cos(math.radians(ang)), math.sin(math.radians(ang)); OE, ON = FG['slab'][0]['footprintITM'][0]
    datum = {}
    for fl in {w['floor'] for w in walls}:
        cnt = defaultdict(float)
        for w in walls:
            if w['floor'] == fl: cnt[w['bottomRel']] += w['length_m']
        datum[fl] = max(cnt, key=cnt.get)
    for w in walls:
        (x0, y0), (x1, y1) = w['axisITM']; L = w['length_m']; dx, dy = (x1 - x0) / L, (y1 - y0) / L
        cu = (hx, hy) if abs(dx * hx + dy * hy) >= abs(-dx * hy + dy * hx) else (-hy, hx)       # the house axis the run follows
        sg = 1 if dx * cu[0] + dy * cu[1] >= 0 else -1
        w['bond'] = {'p0': r3((x0 - OE) * cu[0] + (y0 - ON) * cu[1]), 'sign': sg}; w['courseDatum'] = datum[w['floor']]
        w['blocksFull'], w['blocksCut'], w['courses'], ar = count_blocks(L, w['bottomRel'], w['topRel'], w['openings'] + w.get('lintels', []), BL, BH, w['bond'], datum[w['floor']])
        w['area_m2'] = r3(ar)
    Q.clear()
    for w in walls:
        tc = round(w['thickness_m'] * 100)
        Q[w['floor']][f't{tc}_full'] += w['blocksFull']; Q[w['floor']][f't{tc}_cut'] += w['blocksCut']; Q[w['floor']][f't{tc}_m2'] += w['area_m2']
    # box depth = the thickness of the block wall the opening sits in (Avihai 08.11: a built-in box as deep as the wall –
    # such boxes are on the market); width = the opening, height = above
    for b in boxes_out:
        w = next((w for w in walls if any(o['id'] == b['opening'] for o in w['openings'])), None)
        b['depth_m'] = w['thickness_m'] if w else None; b['hostWall'] = w['id'] if w else None
        b['depthSource'] = 'החלטת אביחי 08.11.2026: ארגז מובנה בעובי הקיר' + (' (עובי הקיר approx)' if w and w['status'] != 'source' else '')
    # ---- owner changes (data/changes/owner-changes-geometry.json): both variants, button "לפי התוכניות / עם השינוי" ----
    # the walls / boxes as drawn get variant 'original'; a copy with the change ('changed', id "<run>~OC-n") is added. The
    # quantities (Q) stay as drawn. Nothing of an owner change is applied silently (Avihai 09.11).
    import copy
    OCG = J('data/changes/owner-changes-geometry.json')['changes']; additions = []
    cen = unary_union([P(sl['footprintITM'], sl.get('holesITM')) for sl in FG['slab']]).centroid
    def relay_(v):
        v['blocksFull'], v['blocksCut'], v['courses'], ar = count_blocks(v['length_m'], v['bottomRel'], v['topRel'], v['openings'] + v['lintels'], BL, BH, v['bond'], v['courseDatum'])
        v['area_m2'] = r3(ar)
    for oc, g in OCG.items():
        for oid, ch in (g.get('openings') or {}).items():
            for w in [w for w in walls if any(o['id'] == oid for o in w['openings']) and not w.get('variant')]:
                v = copy.deepcopy(w); v['id'] = f"{w['id']}~{oc}"; v['variant'] = {'change': oc, 'show': 'changed'}
                w['variant'] = {'change': oc, 'show': 'original'}; w['ownerChange'] = v['ownerChange'] = oc
                for o in v['openings']:
                    if o['id'] == oid: o['z1'] = ch['headRel']
                v['lintels'] = [l for l in v['lintels'] if oid not in l['opening'].split('+')]
                relay_(v); walls.append(v)
            for b in [b for b in boxes_out if b['opening'] == oid and not b.get('variant')]:
                wtop = next((w['topRel'] for w in walls if w['id'] == b.get('hostWall')), None)
                c2 = copy.deepcopy(b); c2.update(box_m=ch['box_m'], headRel=ch['headRel'], variant={'change': oc, 'show': 'changed'}, ownerChange=oc,
                                                source=f"{oc} – {ch.get('shutter', '')}; {g.get('source', '')}")
                b['variant'] = {'change': oc, 'show': 'original'}; b['ownerChange'] = oc
                if wtop is not None and b['headRel'] > wtop + 0.005:
                    b['clash'] = {'into_m': r3(b['headRel'] - wtop), 'note': f"ארגז התריס חודר {round((b['headRel'] - wtop) * 100)} ס\"מ מעל תחתית הבטון שמעליו (‎+{wtop:.2f})"}
                boxes_out.append(c2)
        dr = g.get('door')
        if dr:
            hosts = [min((w for w in walls if w['floor'] == 'first' and not w.get('variant')), key=lambda w: LineString(w['axisITM']).distance(Point(pt))) for pt in dr['runsNearITM']]
            span = []
            for w in hosts:
                v = copy.deepcopy(w); v['id'] = f"{w['id']}~{oc}"; v['variant'] = {'change': oc, 'show': 'changed'}
                w['variant'] = {'change': oc, 'show': 'original'}; w['ownerChange'] = v['ownerChange'] = oc
                L = v['length_m']
                v['openings'] = [{'id': f'{oc}-door', 'kind': 'door', 's0': 0.0, 's1': L, 'z0': max(v['bottomRel'], dr['sillRel']), 'z1': dr['headRel'], 'clip': ['L', 'R'], 'shutter': False}]
                v['lintels'] = [{'id': f'LT-{oc}-{w["id"]}', 'opening': f'{oc}-door', 's0': 0.0, 's1': L, 'z0': dr['headRel'], 'z1': dr['lintelTopRel'], 'bearL_m': 0.0, 'bearR_m': 0.0,
                                 'length_m': L, 'status': 'provisional', 'onConcrete': [], 'continues': ['L', 'R'], 'intoCrossWall': [], 'shortBearing': [], 'pier': []}]
                relay_(v); walls.append(v); span += w['axisITM']
            st = g.get('step')
            if st:
                a_, b_ = max(((p, q) for p in span for q in span), key=lambda pq: math.dist(*pq))
                Lsp = math.dist(a_, b_); ux, uy = (b_[0] - a_[0]) / Lsp, (b_[1] - a_[1]) / Lsp; nx, ny = -uy, ux
                tw = max(w['thickness_m'] for w in hosts) / 2
                if (cen.x - a_[0]) * nx + (cen.y - a_[1]) * ny < 0: nx, ny = -nx, -ny
                d0, d1 = tw, tw + st['depth_m']
                ring = [[r3(a_[0] + nx * d0), r3(a_[1] + ny * d0)], [r3(b_[0] + nx * d0), r3(b_[1] + ny * d0)], [r3(b_[0] + nx * d1), r3(b_[1] + ny * d1)], [r3(a_[0] + nx * d1), r3(a_[1] + ny * d1)]]
                additions.append({'id': f'{oc}-step', 'change': oc, 'floor': 'first', 'kind': 'step', 'ringITM': ring, 'bottomRel': st['bottomRel'], 'topRel': st['topRel'],
                                  'width_m': r3(Lsp), 'note': st['note'], 'source': g.get('source', '')})
    out = {'_doc': 'נוצר ע"י tools/extract_blocks.py – קירות בלוקים (איטונג 60×25 לפי בחירת אביחי), ארגזי תריס וכמויות. לא לערוך ידנית.',
           'block': CFG['block'], 'houseAxisDeg': r3(ang), 'walls': walls, 'shutterBoxes': boxes_out,
           'outsideWalls': {'items': outside, 'note': 'קירות בתוכנית האדריכל בלי תקרה מעליהם (גינה / גדרות) – לשלב הפיתוח, לא נספרו'},
           'dominantThickness_cm': dom, 'ownerAdditions': additions,
           'quantities': {fl: {k: (round(v, 2) if k.endswith('m2') else int(v)) for k, v in sorted(q.items())} for fl, q in Q.items()}}
    json.dump(out, open(os.path.join(ROOT, 'data/architecture/blocks.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('walls', len(walls), {fl: sum(1 for w in walls if w['floor'] == fl) for fl in O.FLOORS})
    print('quantities', json.dumps(out['quantities'], ensure_ascii=False))
    print('boxes', [(b['opening'], b['box_m'], b['status']) for b in boxes_out])


if __name__ == '__main__':
    main()


def export_xlsx(path=os.path.join(ROOT, 'docs/quantities/blocks-quantities.xlsx')):
    """quantities workbook: summary per floor / thickness (+ waste), every wall run, the roller-shutter boxes"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    D = J('data/architecture/blocks.json'); CFG = J('data/config/blocks.json'); W = CFG['waste_pct']['value']
    D['walls'] = [w for w in D['walls'] if (w.get('variant') or {}).get('show') != 'changed']   # quantities as drawn (owner-change copies apart)
    D['shutterBoxes'] = [b for b in D['shutterBoxes'] if (b.get('variant') or {}).get('show') != 'changed']
    FL = {'unit': 'יחידת דיור', 'ground': 'קומת קרקע', 'first': "קומה א'"}
    wb = Workbook(); hdr = Font(bold=True, color='FFFFFF'); fill = PatternFill('solid', fgColor='2F5496')
    def sheet(ws, head, rows, widths):
        ws.sheet_view.rightToLeft = True; ws.append(head)
        for c in ws[1]: c.font, c.fill, c.alignment = hdr, fill, Alignment(horizontal='center')
        for r in rows: ws.append(r)
        for i, w_ in enumerate(widths): ws.column_dimensions[chr(65 + i)].width = w_
        ws.freeze_panes = 'A2'
    agg = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for w in D['walls']:
        k = (w['floor'], round(w['thickness_m'] * 100)); a = agg[k]
        a[0] += w['blocksFull']; a[1] += w['blocksCut']; a[2] += w['area_m2']; a[3] += w['area_m2'] * w['thickness_m']
    rows = []
    for (fl, t), (f, c, m2, m3) in sorted(agg.items(), key=lambda x: (list(FL).index(x[0][0]), x[0][1])):
        face = CFG['block']['length_m'] * CFG['block']['height_m']
        rows.append([FL[fl], t, f, c, f + c, round(m2, 2), round(m2 / face), round(m2 / face * (1 + W / 100)), round(m3, 3)])
    n = len(rows) + 1
    rows.append(['סה"כ', ''] + [f'=SUM({col}2:{col}{n})' for col in 'CDEFGHI'])
    ws = wb.active; ws.title = 'סיכום'
    sheet(ws, ['קומה', 'עובי (ס"מ)', 'בלוקים שלמים', 'חלקי בלוק חתוכים', 'סה"כ יחידות בקיר', 'שטח קיר נטו (מ"ר)', 'שווה ערך בלוקים (לפי שטח)', f'להזמנה (+{W}% פחת)', 'נפח (מ"ק)'], rows, [14, 11, 14, 16, 16, 17, 22, 18, 11])
    for c in ws[ws.max_row]: c.font = Font(bold=True)
    ws.append([]); ws.append([f"בלוק: {CFG['block']['type']} {round(CFG['block']['length_m'] * 100)}×{round(CFG['block']['height_m'] * 100)} – {CFG['block']['source']}. פחת {W}% – זמני, לאישור."])
    sheet(wb.create_sheet('קירות'), ['מזהה', 'קומה', 'עובי (ס"מ)', 'אורך (מ\')', 'תחתית', 'ראש', 'נדבכים', 'שלמים', 'חתוכים', 'שטח נטו (מ"ר)', 'פתחים', 'סטטוס'],
          [[w['id'], FL[w['floor']], round(w['thickness_m'] * 100), w['length_m'], w['bottomRel'], w['topRel'], w['courses'], w['blocksFull'], w['blocksCut'], w['area_m2'],
            ', '.join(o['id'] for o in w['openings']), w['status']] for w in D['walls']], [9, 12, 10, 10, 9, 9, 9, 9, 9, 14, 18, 10])
    OPN = {o['id']: o for o in J('data/architecture/openings.json')['openings']}
    sheet(wb.create_sheet('ארגזי תריס'), ['פתח', 'קומה', 'משפחה', 'רוחב (ס"מ)', 'גובה ארגז (ס"מ)', 'עומק ארגז (ס"מ)', 'קיר', 'סטטוס', 'מקור הגובה', 'מקור העומק'],
          [[b['opening'], FL[b['floor']], OPN[b['opening']]['name'], round(b['width_m'] * 100), round(b['box_m'] * 100) if b['box_m'] else '',
            round(b['depth_m'] * 100) if b.get('depth_m') else '', b.get('hostWall') or '', b['status'], b['source'], b.get('depthSource', '')] for b in D['shutterBoxes']],
          [8, 12, 44, 11, 15, 15, 10, 10, 60, 40])
    LT = CFG['lintel']; byO = {}; SD = {'L': 'שמאל', 'R': 'ימין'}
    bear_note = lambda lt: '; '.join([f"{SD[x]}: על הבטון" for x in lt['onConcrete']] + [f"{SD[x]}: המשך בקטע הקיר הסמוך" for x in lt.get('continues', [])]
                                     + [f"{SD[x]}: נכנס לקיר הבלוקים הניצב" for x in lt.get('intoCrossWall', [])]
                                     + [f"{SD[x]}: עד אמצע הפילר בין שני פתחים" for x in lt.get('pier', [])]
                                     + [f"{SD[x]}: בלי הישענות – לבדיקה" for x in lt.get('shortBearing', [])]) or '—'
    for w in D['walls']:
        for lt in w.get('lintels', []):
            if not lt.get('stubOf'): byO[lt['id']] = (w, dict(lt))
    for w in D['walls']:
        for lt in w.get('lintels', []):
            if lt.get('stubOf') and lt['stubOf'] in byO: p_ = byO[lt['stubOf']][1]; p_['length_m'] = round(p_['length_m'] + lt['length_m'], 3)
    lrows = [[lt['id'], lt['opening'], FL[w['floor']], w['id'], round(w['thickness_m'] * 100), LT['type'] if w['thickness_m'] >= LT['thinBelow_m'] else LT['typeThin'],
              round((lt['length_m'] - lt['bearL_m'] - lt['bearR_m']) * 100), round(lt['bearL_m'] * 100), round(lt['bearR_m'] * 100), round(lt['length_m'] * 100),
              round((lt['z1'] - lt['z0']) * 100), bear_note(lt), lt['status']] for w, lt in byO.values()]
    n = len(lrows) + 1
    lrows.append(['סה"כ', f'=COUNTA(A2:A{n})', '', '', '', '', '', '', '', f'=SUM(J2:J{n})'])
    sheet(wb.create_sheet('משקופים'), ['מזהה', 'פתח', 'קומה', 'קיר', 'עובי (ס"מ)', 'סוג', 'פתח נטו (ס"מ)', 'הישענות שמאל', 'הישענות ימין', 'אורך משקוף (ס"מ)', 'גובה (ס"מ)', 'הישענות – הערה', 'סטטוס'],
          lrows, [10, 7, 12, 8, 9, 40, 12, 12, 12, 15, 9, 34, 11])
    ws = wb['משקופים']; ws.append([]); ws.append([f"הישענות {round(LT['bearing_m']['value'] * 100)} ס\"מ בכל צד – {LT['bearing_m']['source']}. גובה = נדבך אחד."])
    os.makedirs(os.path.dirname(path), exist_ok=True); wb.save(path); print('xlsx', path)


if __name__ == '__main__' and '--xlsx' in sys.argv:
    export_xlsx()

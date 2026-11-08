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


def main():
    CFG = J('data/config/blocks.json')
    BL, BH = CFG['block']['length_m'], CFG['block']['height_m']
    FR, FG, FF, FRF = J('data/structure/framing.json'), J('data/structure/floor-ground.json'), J('data/structure/floor-first.json'), J('data/structure/floor-roof.json')
    PER, OPN = J('data/structure/perimeter.json'), J('data/architecture/openings.json')
    ang = house_axis(FG)
    boxes = shutter_boxes()
    msp = ezdxf.readfile(os.path.join(ROOT, O.SRC)).modelspace()
    bpoly = lambda b: LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2)
    # concrete per floor, the surfaces under / over each floor, and the building outline
    conc = {
        'unit': [P(p['ringITM'], p.get('holesITM')) for w in FR['basementWalls'] for p in (w.get('partsITM') or [{'ringITM': w['footprintITM'], 'holesITM': w.get('holesITM')}])],
        'ground': [P(w['footprintITM'], w.get('holesITM')) for w in FG['walls']] + [P(c['footprintITM']) for c in FG['columns']] + [P(w['ringITM']) for w in PER['walls']],
        'first': [P(w['footprintITM'], w.get('holesITM')) for w in FF['walls']] + [P(c['footprintITM']) for c in FF['columns']] + [P(w['footprintITM']) for w in FRF['walls'] if w['bottomRel'] < 6],
    }
    under = {
        'unit': [(P(s.get('outlineITM') or s['footprintITM'], s.get('holesITM')), s['top']) for s in FR['slabs'] if s.get('level') == 'basement'],
        'ground': [(P(s['footprintITM'], s.get('holesITM')), s['topRel']) for s in FG['slab']],
        'first': [(P(s['footprintITM'], s.get('holesITM')), s['topRel']) for s in FG['ceiling']['slab']] + [(bpoly(b), b['topRel']) for b in FG['ceiling']['beams'] if b.get('axisITM')],
    }
    over = {
        'unit': [(P(s['footprintITM'], s.get('holesITM')), s['bottomRel'] if 'bottomRel' in s else s['topRel'] - s['thickness_m']) for s in FG['slab']]
                + [(bpoly(b), b['bottomRel']) for b in FR['groundBeams'] if b.get('axisITM') and b.get('sheet') == 'K-21'],
        'ground': [(P(s['footprintITM'], s.get('holesITM')), s['bottomRel']) for s in FG['ceiling']['slab']] + [(bpoly(b), b['bottomRel']) for b in FG['ceiling']['beams'] if b.get('axisITM')]
                  + [(P(s['footprintITM'], s.get('holesITM')), s['bottomRel']) for s in FF['ceiling']['slab']],
        'first': [(P(s['footprintITM'], s.get('holesITM')), s['bottomRel']) for s in FF['ceiling']['slab']] + [(bpoly(b), b['bottomRel']) for b in FRF['ceiling']['beams'] if b.get('axisITM')],
    }
    inside = {fl: unary_union([g for g, _ in over[fl]] + [g for g, _ in under[fl]]).buffer(0.35) for fl in over}
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
        C = unary_union(conc[fl]).buffer(0.01)
        # morphological opening: drawing slivers < 4 cm (line ends, hatch seams) are not wall – they made a 10 cm partition at a
        # door look 45 cm thick
        pieces = [q for g in polys(R.difference(C).intersection(inside[fl])) for q in polys(g.buffer(-0.02, join_style=2).buffer(0.02, join_style=2))
                  if q.area > 0.03 and 2 * q.area / q.length > 0.05]
        for g in pieces:
            for run in rect_runs(g, ang):
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
                        wo.append({'id': o['id'], 's0': r3(max(0, s - o['width_m'] / 2)), 's1': r3(min(L, s + o['width_m'] / 2)), 'z0': o['sillRel'], 'z1': o['headRel'],
                                   'shutter': ('גלילה' in o['name'] or 'תריס' in o['name'])})
                # courses (bond: half a block on every other course), blocks clipped by openings
                nfull = ncut = 0; area = L * (zt - zb)
                k = 0; z = zb
                while z < zt - 0.005:
                    h = min(BH, zt - z); off = (BL / 2) * (k % 2)
                    segs = [(0.0, L)]
                    for o in wo:
                        if o['z0'] < z + h - 0.005 and o['z1'] > z + 0.005:
                            segs = [p for a, b in segs for p in ((a, min(b, o['s0'])), (max(a, o['s1']), b)) if p[1] - p[0] > 0.005]
                    for a, b in segs:
                        x = -off
                        while x < b - 0.005:
                            xa, xb = max(x, a), min(x + BL, b)
                            if xb - xa > 0.005:
                                if xb - xa >= BL - 0.005 and h >= BH - 0.005: nfull += 1
                                else: ncut += 1
                            x += BL
                    k += 1; z += h
                for o in wo: area -= (o['s1'] - o['s0']) * (o['z1'] - o['z0'])
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
    out = {'_doc': 'נוצר ע"י tools/extract_blocks.py – קירות בלוקים (איטונג 60×25 לפי בחירת אביחי), ארגזי תריס וכמויות. לא לערוך ידנית.',
           'block': CFG['block'], 'houseAxisDeg': r3(ang), 'walls': walls, 'shutterBoxes': boxes_out,
           'outsideWalls': {'items': outside, 'note': 'קירות בתוכנית האדריכל בלי תקרה מעליהם (גינה / גדרות) – לשלב הפיתוח, לא נספרו'},
           'dominantThickness_cm': dom,
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
    os.makedirs(os.path.dirname(path), exist_ok=True); wb.save(path); print('xlsx', path)


if __name__ == '__main__' and '--xlsx' in sys.argv:
    export_xlsx()

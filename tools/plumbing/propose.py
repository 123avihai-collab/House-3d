#!/usr/bin/env python3
"""Plumbing layer – DESIGN PROPOSAL (for Avihai's approval, then the consultant's). Nothing here is from the drawings
unless stated; every record carries status 'proposal' and the reason.

Inputs : data/plumbing/network.json (the consultant's design as drawn), tools/plumbing/proposal-inputs.json (decisions,
         typical values), structure (floor-ground.json, framing.json, basement.json), architect walls (plumbing DXF
         background blocks), the basement sketch (sources/basement, provisional).
Output : data/plumbing/proposal.json
  stackMoves  – each stack צ.א moved by the smallest displacement that clears all concrete (walls, columns, beams) along
                its height, the ממ"ד and the shaft; connector pieces from the drawn branches to the new position
  shaft       – plumbing shaft north of the ממ"ד (decision D2) with its slab openings
  manifolds   – cold/hot manifolds per floor / unit (decisions D1, D4), ball valve per outlet
  runs        – PEX lines in sleeves, routed in the floor build-up around walls (A* on a 5 cm grid; concrete avoided,
                the ממ"ד forbidden on the ground floor), risers in the walls to each point at a typical height
  sleeves     – every crossing of a wall / slab, with sleeve type, diameter and material
  superseded  – consultant items replaced by the proposal (hidden when the proposal is shown)
"""
import heapq, json, math, os, sys
import numpy as np
import shapely
from shapely.geometry import Polygon, Point, LineString, MultiLineString
from shapely.ops import unary_union, nearest_points
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_common import *
import georef as G
from georef_basement_sketch import fit as sketch_fit, SKETCH
import propose_site

r3 = lambda v: round(float(v), 3)
I = J('tools/plumbing/proposal-inputs.json')
N = J('data/plumbing/network.json')
NODES = {n['id']: n for n in N['nodes']}
CON = concrete()
CORN = list(MAMAD.exterior.coords)[:4]
O = CORN[1]
LOC = [local(c, O) for c in CORN]
YMAX = max(q[1] for q in LOC); XMIN = min(q[0] for q in LOC)
FL = I['floors']
SLEEVE_SERIES = [25, 32, 40, 50, 63, 75, 90, 110, 125, 160, 200]


def next_sleeve(d_mm, gap=10):
    return next(s for s in SLEEVE_SERIES if s >= d_mm + gap)


# ------------------------------------------------------------------ shaft
def shaft():
    S = I['shaft']; x0 = XMIN + S['x0']; y0 = YMAX + S['gap']
    poly = rect(O, x0, y0, x0 + S['len'], y0 + S['depth'])
    inner = {k: world((x0 + v[0], y0 + v[1]), O) for k, v in S['inner'].items()}
    hits = [f'{k} {eid}' for k, eid, P, b, t, st in CON if P.intersects(poly)]
    return {'footprintITM': [[r3(x), r3(y)] for x, y in poly.exterior.coords][:4], 'local': [x0, y0, S['len'], S['depth']], 'inner': inner, 'poly': poly,
            'bottom': r3(H0 + FL['unit']['finish']), 'top': r3(H0 + FL['roof']['finish'] + 0.15), 'clashes': hits}


# ------------------------------------------------------------------ stacks
def move_stacks(SH):
    P = I['stacks']; out = []
    walls_g = unary_union(arch_walls(GG, 'ground')); walls_f = unary_union(arch_walls(GG, 'first'))
    taken = [Point(p[0], p[1]) for l in N['lines3d'] if l.get('kind') == 'downpipe' for p in l['pts3d']]
    stacks = [l for l in N['lines3d'] if l.get('kind') == 'stack']
    moved_pos = []
    for l in stacks:
        pts = l['pts3d']
        verts = [(a, b) for a, b in zip(pts[:-1], pts[1:]) if abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) < 0.01]
        def clear(dx, dy):
            for a, b in verts:
                q = world(tuple(np.add(local(a, O), (dx, dy))), O)
                c = Point(q).buffer(0.055 + P['clearance_m'])
                lo, hi = min(a[2], b[2]) - H0, max(a[2], b[2]) - H0
                for k, eid, poly, bot, top, st in CON:
                    if min(hi, top) - max(lo, bot) > 0.02 and c.intersects(poly): return False
                if c.intersects(MAMAD) or c.intersects(SH['poly'].buffer(0.02)): return False
                if any(Point(q).distance(t) < P['minBetween_m'] for t in taken + moved_pos): return False
            return True
        def hits(dx, dy):
            out_ = []
            for a, b in verts:
                q = world(tuple(np.add(local(a, O), (dx, dy))), O); c = Point(q).buffer(0.055)
                lo, hi = min(a[2], b[2]) - H0, max(a[2], b[2]) - H0
                out_ += [f'{k} {eid}' for k, eid, poly, bot, top, st in CON if min(hi, top) - max(lo, bot) > 0.02 and c.intersects(poly)]
            return sorted(set(out_))
        before = hits(0, 0)
        if not before and clear(0, 0):
            moved_pos += [Point(p[0], p[1]) for p in pts]; continue
        best = None; R = P['search_m']; st = P['step_m']
        g0 = Point(pts[0][0], pts[0][1])
        for i in range(-int(R / st), int(R / st) + 1):
            for j in range(-int(R / st), int(R / st) + 1):
                dx, dy = i * st, j * st; d = math.hypot(dx, dy)
                if d > R or (best and d > best[0] + 0.3): continue
                if not clear(dx, dy): continue
                q = world(tuple(np.add(local(pts[0], O), (dx, dy))), O)
                wd = min(walls_g.distance(Point(q)), walls_f.distance(Point(q)))
                cost = d + 0.5 * max(0, wd - P['wallPenaltyFrom_m'])
                if best is None or cost < best[1]: best = (d, cost, dx, dy, wd)
        if not best:
            out.append({'stack': l['stack'], 'status': 'unresolved', 'clashesBefore': before}); continue
        d, cost, dx, dy, wd = best
        new = [[*world(tuple(np.add(local(p, O), (dx, dy))), O), p[2]] for p in pts]
        moved_pos += [Point(p[0], p[1]) for p in new]
        dvec = (new[0][0] - pts[0][0], new[0][1] - pts[0][1])
        # connectors: every drawn sewer run that ends at this stack, extended horizontally to the new position
        conns = []
        for r in N['runs']:
            if r['system'] != 'sewage': continue
            for end, key, IL in ((r['from'], 0, r.get('ILup')), (r['to'], -1, r.get('ILdown'))):
                if end.startswith(f'ST{l["stack"]}@') and IL is not None:
                    p0 = r['pts'][key]; OD = (r.get('D_mm') or 110) / 1000
                    conns.append({'run': r['id'], 'D_mm': r.get('D_mm') or 110, 'material': r.get('material', 'HDPE'),
                                  'pts3d': [[r3(p0[0]), r3(p0[1]), r3(IL + OD / 2)], [r3(p0[0] + dvec[0]), r3(p0[1] + dvec[1]), r3(IL + OD / 2)]]})
        out.append({'stack': l['stack'], 'id': f'PSTACK{l["stack"]}', 'replaces': l['id'], 'status': 'proposal', 'displacement_m': r3(d),
                    'local_dxdy_m': [r3(dx), r3(dy)], 'distToWall_m': r3(wd), 'clashesBefore': before, 'clashesAfter': hits(dx, dy),
                    'pts3d': [[r3(a), r3(b), r3(c)] for a, b, c in new], 'connectors': conns,
                    'why': f'במיקום שבתוכנית הקולטן עובר בתוך: {", ".join(before)}. הוזז {d * 100:.0f} ס"מ למקום הפנוי הקרוב (מרווח {P["clearance_m"] * 100:.0f} ס"מ מכל אלמנט בטון לכל גובהו, מחוץ לממ"ד ולפיר).'})
    return out


# ------------------------------------------------------------------ routing grid
class Grid:
    def __init__(self, region, walls, concrete_polys, forbidden, keepouts):
        R = I['routing']; self.c = R['cell_m']
        x0, y0, x1, y1 = region.bounds; self.x0, self.y0 = x0 - 0.2, y0 - 0.2
        self.nx, self.ny = int((x1 - x0 + 0.4) / self.c) + 1, int((y1 - y0 + 0.4) / self.c) + 1
        xs = self.x0 + (np.arange(self.nx) + 0.5) * self.c; ys = self.y0 + (np.arange(self.ny) + 0.5) * self.c
        X, Y = np.meshgrid(xs, ys, indexing='ij')
        cost = np.full(X.shape, np.inf)
        cost[shapely.contains_xy(region, X, Y)] = 1.0
        self.wallpoly = unary_union([w.buffer(R['wallBuffer_m']) for w in walls]) if walls else Polygon()
        if not self.wallpoly.is_empty: cost[np.isfinite(cost) & shapely.contains_xy(self.wallpoly, X, Y)] = R['wallCost']
        self.conpoly = unary_union(concrete_polys) if concrete_polys else Polygon()
        if not self.conpoly.is_empty: cost[np.isfinite(cost) & shapely.contains_xy(self.conpoly, X, Y)] = R['concreteCost'] if R['concreteCost'] else np.inf
        for f in forbidden:
            cost[shapely.contains_xy(f, X, Y)] = np.inf
        for k in keepouts:
            cost[shapely.contains_xy(k, X, Y)] = np.inf
        self.base = cost; self.used = np.zeros_like(cost)

    def ij(self, p): return (min(self.nx - 1, max(0, int((p[0] - self.x0) / self.c))), min(self.ny - 1, max(0, int((p[1] - self.y0) / self.c))))
    def xy(self, ij): return (self.x0 + (ij[0] + 0.5) * self.c, self.y0 + (ij[1] + 0.5) * self.c)

    def route(self, a, b):
        R = I['routing']; s, t = self.ij(a), self.ij(b)
        cost = self.base + self.used * R['usedCost']
        free = lambda ij: ij in (s, t) or np.isfinite(cost[ij])
        D = {s: 0.0}; prev = {}; Q = [(0.0, s)]
        nb = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1), (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
        h = lambda ij: math.hypot(ij[0] - t[0], ij[1] - t[1])
        Q = [(h(s), 0.0, s)]
        while Q:
            f, g, u = heapq.heappop(Q)
            if u == t: break
            if g > D.get(u, 1e18): continue
            for di, dj, w in nb:
                v = (u[0] + di, u[1] + dj)
                if not (0 <= v[0] < self.nx and 0 <= v[1] < self.ny) or not free(v): continue
                cv = 1.0 if v in (s, t) else cost[v]
                ng = g + w * cv
                if ng < D.get(v, 1e18): D[v] = ng; prev[v] = u; heapq.heappush(Q, (ng + h(v), ng, v))
        if t not in D: return None
        path = [t]
        while path[-1] != s: path.append(prev[path[-1]])
        path = path[::-1]
        for ij in path:
            i, j = ij; self.used[max(0, i - 1):i + 2, max(0, j - 1):j + 2] = 1
        return self.smooth(path, a, b)

    def los(self, p, q):
        n = max(2, int(math.dist(p, q) / (self.c / 2)))
        for k in range(n + 1):
            x = p[0] + (q[0] - p[0]) * k / n; y = p[1] + (q[1] - p[1]) * k / n
            ij = self.ij((x, y))
            if self.base[ij] != 1.0: return False
        return True

    def smooth(self, path, a, b):
        pts = [self.xy(ij) for ij in path]; pts[0] = a; pts[-1] = b
        free = [self.base[ij] == 1.0 for ij in path]
        out = [pts[0]]; i = 0
        while i < len(pts) - 1:
            j = len(pts) - 1
            while j > i + 1:
                if all(free[i + 1:j]) and self.los(pts[i], pts[j]): break
                j -= 1
            out.append(pts[j]); i = j
        # merge collinear
        res = [out[0]]
        for k in range(1, len(out) - 1):
            a_, b_, c_ = res[-1], out[k], out[k + 1]
            cr = (b_[0] - a_[0]) * (c_[1] - a_[1]) - (b_[1] - a_[1]) * (c_[0] - a_[0])
            if abs(cr) > 1e-4: res.append(b_)
        res.append(out[-1])
        return res


# ------------------------------------------------------------------ helpers
def snap_to_wall(p, walls, maxd=0.9, into=0.05):
    best = None
    for w in walls:
        q = nearest_points(w, Point(p))[0]
        d = q.distance(Point(p))
        if d < maxd and (best is None or d < best[0]): best = (d, q, w)
    if not best: return p, None
    d, q, w = best
    v = (p[0] - q.x, p[1] - q.y); L = math.hypot(*v) or 1
    # wall direction
    cs = list(w.coords); seg = min(zip(cs[:-1], cs[1:]), key=lambda s: LineString(s).distance(q))
    t = (seg[1][0] - seg[0][0], seg[1][1] - seg[0][1]); tl = math.hypot(*t) or 1
    return (q.x + v[0] / L * into, q.y + v[1] / L * into), ((t[0] / tl, t[1] / tl), (v[0] / L, v[1] / L))


def sketch_walls():
    import pymupdf
    T, _ = sketch_fit(); p = pymupdf.open(os.path.join(ROOT, SKETCH))[0]; out = []
    for d in p.get_drawings():
        if tuple(round(v, 2) for v in (d.get('color') or ())) != (0.0, 0.0, 0.0) or round(d.get('width') or 0, 2) < 0.7: continue
        for it in d['items']:
            if it[0] == 'l':
                a, b = T(it[1].x, it[1].y), T(it[2].x, it[2].y)
                if math.dist(a, b) > 0.25: out.append(LineString([a, b]))
    return out


def crossings(pts2, grid, pipe_id, D, z, floor):
    L = LineString(pts2); out = []
    ends = [Point(pts2[0]), Point(pts2[-1])]
    for geom, kind in ((grid.conpoly, 'concrete'), (grid.wallpoly, 'wall')):
        if geom.is_empty: continue
        x = L.intersection(geom)
        for part in getattr(x, 'geoms', [x]):
            if part.is_empty or part.length < 0.02: continue
            c = part.centroid
            if kind == 'wall' and not grid.conpoly.is_empty and grid.conpoly.buffer(0.02).contains(c): continue
            if kind == 'concrete' and min(e.distance(part) for e in ends) < 0.12: continue   # point on a concrete wall: riser in the plaster / cladding, no sleeve
            conduit = next_sleeve(D, 8)
            out.append({'pipe': pipe_id, 'floor': floor, 'at': [r3(c.x), r3(c.y), r3(z)], 'length_m': r3(part.length),
                        'through': 'קיר בטון' if kind == 'concrete' else 'קיר / מחיצה',
                        'sleeve': (f'שרוול PVC ø{next_sleeve(conduit, 15)} יצוק (תיאום קונסטרוקטור)' if kind == 'concrete'
                                   else f'מעבר בקיר בתוך שרוול מריכף ø{conduit} (המשך שרוול הצינור), סגירה בטיט'),
                        'sleeveD_mm': next_sleeve(conduit, 15) if kind == 'concrete' else conduit, 'material': 'PVC' if kind == 'concrete' else 'פוליאתילן מריכף'})
    return out


# ------------------------------------------------------------------ main
def main():
    global GG
    GG = G.load()
    SH = shaft()
    print('shaft clashes:', SH['clashes'])
    SM = move_stacks(SH)
    for s in SM: print('stack', s['stack'], s.get('displacement_m'), s.get('clashesBefore'), '->', s.get('clashesAfter'))
    new_stack_pts = [Point(p[0], p[1]) for s in SM if s.get('pts3d') for p in s['pts3d']]
    kept = [Point(p[0], p[1]) for l in N['lines3d'] if l.get('kind') == 'stack' and not any(s.get('replaces') == l['id'] for s in SM) for p in l['pts3d']]
    dp = [Point(p[0], p[1]) for l in N['lines3d'] if l.get('kind') == 'downpipe' for p in l['pts3d']]
    keepouts = [p.buffer(I['routing']['keepout_m']) for p in new_stack_pts + kept + dp] + [SH['poly'].buffer(0.01)]

    # regions + walls per floor
    gs = unary_union([Polygon(s['footprintITM']).buffer(0) for s in FG['slab']])
    fs = unary_union([Polygon(s['footprintITM']).buffer(0) for s in FG['ceiling']['slab']] + [MAMAD.buffer(0.01)])
    bs = Polygon(BAS['outlineITM']).buffer(-0.02)
    walls = {'ground': arch_walls(GG, 'ground'), 'first': arch_walls(GG, 'first'), 'unit': sketch_walls()}
    conc = {'ground': [P for k, e, P, b, t, s in CON if k in ('קיר בטון', 'עמוד')],
            'first': [], 'unit': [P for k, e, P, b, t, s in CON if k == 'קיר מרתף']}
    grids = {'ground': Grid(gs, walls['ground'], conc['ground'], [MAMAD.buffer(0.02)], keepouts),
             'first': Grid(fs, walls['first'], conc['first'], [], keepouts),
             'unit': Grid(bs, walls['unit'], conc['unit'], [], keepouts)}

    # fixtures -> supply points
    PT = I['points']; points = []
    fix = [n for n in N['nodes'] if n['floor'] in ('ground', 'first') and n['kind'] in ('wc', 'basin', 'shower', 'sink', 'washer')]
    for n in fix: points.append((n['floor'], n['kind'], (n['E'], n['N']), n['id'], n.get('title', '')))
    for k, (E, N_) in enumerate(I['balconyTaps']): points.append(('first', 'balconyTap', (E, N_), f'BT{k + 1}@first', 'ברז גן במרפסת (הערת היועץ)'))
    for u in ('unit2', 'unit1'):
        for kind, E, N_ in I['unitFixtures'][u]: points.append(('unit', kind, (E, N_), f'{u.upper()}-{kind}', f'{u} – לפי הסקיצה (provisional)'))

    # manifolds
    MF = I['manifolds']; manifolds = {}
    def man_at_shaft(key, fl):
        m = MF[key]; x0, y0, ln, dp_ = SH['local']
        c = world((x0 + ln + m['offset'] / 2 + 0.05, y0 + 0.08), O)
        return {'id': f'MAN-{key}', 'floor': fl, 'E': c[0], 'N': c[1], 'axis': UX, 'face': UY, 'title': m['title'], 'coldH': m['coldH'], 'hotH': m['hotH']}
    def man_near(key, fl):
        m = MF[key]; p, fr = snap_to_wall(tuple(m['near']), walls[fl], 1.2, 0.08)
        return {'id': f'MAN-{key}', 'floor': fl, 'E': p[0], 'N': p[1], 'axis': fr[0] if fr else UX, 'face': fr[1] if fr else UY, 'title': m['title'], 'coldH': m['coldH'], 'hotH': m['hotH']}
    manifolds['ground'] = man_near('ground', 'ground'); manifolds['first'] = man_at_shaft('first', 'first')
    manifolds['unit2'] = man_at_shaft('unit2', 'unit'); manifolds['unit1'] = man_near('unit1', 'unit')
    floor_of_man = {'ground': 'ground', 'first': 'first', 'unit2': 'unit', 'unit1': 'unit'}

    runs, sleeves = [], []
    def add_run(rid, system, floor, D, pts3d, frm, to, note='', insul=False, material='PEX'):
        conduit = None if insul else next_sleeve(D, 8)
        runs.append({'id': rid, 'system': system, 'floor': floor, 'D_mm': D, 'material': material, 'pts3d': [[r3(a), r3(b), r3(c)] for a, b, c in pts3d],
                     'from': frm, 'to': to, 'conduitD_mm': conduit, 'insulation_mm': I['feeds']['insulation_mm'] if insul else None,
                     'length_m': r3(sum(math.dist(pts3d[i], pts3d[i + 1]) for i in range(len(pts3d) - 1))), 'status': 'proposal', 'note': note})

    # distribution: each point -> manifold of its floor/unit
    assign = []
    for fl, kind, p, fid, title in points:
        mk = fl if fl in ('ground', 'first') else ('unit2' if fid.startswith('UNIT2') else 'unit1')
        sp, fr = snap_to_wall(p, walls[fl], 0.9, 0.05)
        moved = None
        if not fr and Point(sp).distance(SH['poly']) < 0.30:   # no wall found (sketch) and on the shaft: slide east along the building axis
            for k in range(1, 30):
                q = (sp[0] + UX[0] * 0.05 * k, sp[1] + UX[1] * 0.05 * k)
                if Point(q).distance(SH['poly']) >= 0.30: moved = math.dist(q, sp); sp = q; break
        if fr and Point(sp).distance(SH['poly']) < 0.30:   # point falls on the shaft: slide it along the wall, away from the shaft
            c0 = SH['poly'].centroid; t = fr[0]; sgn = 1 if (sp[0] - c0.x) * t[0] + (sp[1] - c0.y) * t[1] >= 0 else -1
            for k in range(1, 20):
                q = (sp[0] + sgn * t[0] * 0.05 * k, sp[1] + sgn * t[1] * 0.05 * k)
                if Point(q).distance(SH['poly']) >= 0.30: moved = math.dist(q, sp); sp = q; break
        assign.append((mk, fl, kind, sp, fr, fid, title + (f' · הנקודה הוזזה {moved * 100:.0f} ס"מ לאורך הקיר בגלל הפיר' if moved else '')))
    pt_out = []
    for mk, m in manifolds.items():
        fl = floor_of_man[mk]; z = H0 + FL[fl]['pipe']; zf = H0 + FL[fl]['finish']
        mine = [a for a in assign if a[0] == mk]
        # outlet order along the manifold axis by projection of the target point
        mine.sort(key=lambda a: (a[3][0] - m['E']) * m['axis'][0] + (a[3][1] - m['N']) * m['axis'][1])
        n_c = sum(1 for a in mine if PT[a[2]]['cold']); n_h = sum(1 for a in mine if PT[a[2]]['hot'])
        m['outlets'] = {'cold': [], 'hot': []}
        ci = hi = 0
        for a in mine:
            _, fl_, kind, sp, fr, fid, title = a; spec = PT[kind]
            pt_out.append({'id': fid, 'floor': fl_, 'kind': kind, 'title': spec['title'], 'fixture': fid, 'E': r3(sp[0]), 'N': r3(sp[1]),
                           'H': r3(zf + spec['H']), 'H_rel': spec['H'], 'D_mm': spec['D'], 'cold': spec['cold'],
                           'hot': spec['hot'] and not (mk.startswith('unit')), 'hotPending': spec['hot'] and mk.startswith('unit'),
                           'wallDir': fr[0] if fr else None, 'face': fr[1] if fr else None, 'status': 'proposal', 'source': title})
            for sysn, on, idx, n_tot, H in (('cold', spec['cold'], ci, n_c, m['coldH']), ('hot', spec['hot'] and not mk.startswith('unit'), hi, n_h, m['hotH'])):
                if not on: continue
                off = (idx - (n_tot - 1) / 2) * MF['outletPitch_m']
                ox, oy = m['E'] + m['axis'][0] * off, m['N'] + m['axis'][1] * off
                start = (ox + m['face'][0] * 0.12, oy + m['face'][1] * 0.12)
                hs = I['hotSpacing_m'] / 2 * (1 if sysn == 'hot' else -1)
                tgt = (sp[0] + (fr[0][0] * hs if fr else 0), sp[1] + (fr[0][1] * hs if fr else 0)) if spec['hot'] or sysn == 'hot' else sp
                path = grids[fl].route(start, tgt)
                if path is None: print('NO ROUTE', mk, fid, sysn); continue
                rid = f'{"C" if sysn == "cold" else "H"}-{fid}'
                pts3d = [(ox, oy, zf + H), (start[0], start[1], zf + H), (start[0], start[1], z)] + [(x, y, z) for x, y in path[1:-1]] + [(tgt[0], tgt[1], z), (tgt[0], tgt[1], zf + spec['H'])]
                add_run(rid, sysn, fl, spec['D'], pts3d, m['id'], fid, f'{spec["title"]} – PEX ø{spec["D"]} בשרוול, ברז ניתוק במחלק')
                sleeves.extend(crossings(path, grids[fl], rid, spec['D'], z, fl))
                m['outlets'][sysn].append({'E': r3(ox), 'N': r3(oy), 'to': fid, 'D_mm': spec['D']})
                if sysn == 'cold': ci += 1
                else: hi += 1

    # supply chain: main entry -> shaft -> manifolds; hot from the roof heater -> shaft -> manifolds, return
    F = I['feeds']; inner = SH['inner']; ent = NODES[I['mainEntry']['from']]
    zE = H0 - 0.55
    zg, zfirst, zu = H0 + FL['ground']['finish'], H0 + FL['first']['finish'], H0 + FL['unit']['finish']
    c = inner['cold']; bcold = inner['basementCold']; hs, hr = inner['hotSupply'], inner['hotReturn']
    add_run('MAIN-ENTRY', 'cold', 'ground', 32, [(ent['E'], ent['N'], zE), (c[0], c[1], zE), (c[0], c[1], zg + I['mainEntry']['valveH'])],
            ent['id'], 'SHAFT', 'המשך הקו הראשי של היועץ (CW16) אל הפיר; ברז ראשי בפיר בגובה +0.30', material='PEX')
    sleeves.append({'pipe': 'MAIN-ENTRY', 'floor': 'ground', 'at': [r3((ent['E'] + c[0]) / 2), r3((ent['N'] + c[1]) / 2), r3(zE)], 'through': 'קיר חוץ / קיר מרתף מתחת לפני הקרקע',
                    'sleeve': 'שרוול PVC ø63 עם אוגן אטימה (puddle flange) + אטם בין הצינור לשרוול', 'sleeveD_mm': 63, 'material': 'PVC'})
    # first floor riser + ground feed + basement riser
    mf, mg, m2, m1 = manifolds['first'], manifolds['ground'], manifolds['unit2'], manifolds['unit1']
    def inlet(m, h): return (m['E'] - m['axis'][0] * 0.35, m['N'] - m['axis'][1] * 0.35, h)
    add_run('RISER-FIRST', 'cold', 'first', F['firstRiser_D'], [(c[0], c[1], zg + 0.40), (c[0], c[1], zfirst + mf['coldH']), inlet(mf, zfirst + mf['coldH'])], 'SHAFT', mf['id'], 'עולה מים קרים לקומה א\' בפיר (במקום WJ23 שבתוך העמוד C8)')
    gstart = (c[0] + UY[0] * 0.20, c[1] + UY[1] * 0.20)
    gp = grids['ground'].route(gstart, inlet(mg, 0)[:2])
    add_run('FEED-GROUND', 'cold', 'ground', F['groundManifold_D'], [(c[0], c[1], zg + 0.40), (gstart[0], gstart[1], zg + 0.40), (gstart[0], gstart[1], zg + FL['ground']['pipe'])]
            + [(x, y, zg + FL['ground']['pipe']) for x, y in gp[1:]] + [(*inlet(mg, 0)[:2], zg + mg['coldH'])], 'SHAFT', mg['id'], 'הזנת מחלק הקרקע מהפיר')
    sleeves.extend(crossings(gp, grids['ground'], 'FEED-GROUND', F['groundManifold_D'], zg + FL['ground']['pipe'], 'ground'))
    add_run('RISER-UNITS', 'cold', 'unit', F['basementRiser_D'], [(c[0], c[1], zg + 0.40), (bcold[0], bcold[1], zg + 0.40), (bcold[0], bcold[1], zu + 0.60)], 'SHAFT', 'SUBMETERS', 'ירידה למרתף בפיר – למונים של היחידות')
    add_run('FEED-UNIT2', 'cold', 'unit', F['unitFeed_D'], [(bcold[0], bcold[1], zu + 0.60), inlet(m2, zu + m2['coldH'])], 'SUBMETERS', m2['id'], 'מונה משנה יחידה 2 → מחלק יחידה 2')
    ustart = (bcold[0] + UY[0] * 0.20, bcold[1] + UY[1] * 0.20)
    up = grids['unit'].route(ustart, inlet(m1, 0)[:2])
    add_run('FEED-UNIT1', 'cold', 'unit', F['unitFeed_D'], [(bcold[0], bcold[1], zu + 0.60), (ustart[0], ustart[1], zu + 0.60), (ustart[0], ustart[1], zu + FL['unit']['pipe'])]
            + [(x, y, zu + FL['unit']['pipe']) for x, y in up[1:]] + [(*inlet(m1, 0)[:2], zu + m1['coldH'])], 'SUBMETERS', m1['id'], 'מונה משנה יחידה 1 → מחלק יחידה 1')
    sleeves.extend(crossings(up, grids['unit'], 'FEED-UNIT1', F['unitFeed_D'], zu + FL['unit']['pipe'], 'unit'))
    # hot: heater (roof) -> shaft top -> first manifold -> ground manifold; return
    htr = NODES['HTR@roof']; zr = H0 + FL['roof']['finish']; zrp = H0 + FL['roof']['pipe']
    add_run('HOT-ROOF', 'hot', 'roof', F['hotSupply_D'], [(htr['E'], htr['N'], zr + 0.60), (htr['E'], htr['N'], zrp), (hs[0], hs[1], zrp), (hs[0], hs[1], zfirst + mf['hotH']), inlet(mf, zfirst + mf['hotH'])],
            'HTR@roof', mf['id'], 'אספקת מים חמים מהדוד: על הגג ובפיר, מבודד', insul=True)
    gh = grids['ground'].route((hs[0] + UY[0] * 0.20, hs[1] + UY[1] * 0.20), inlet(mg, 0)[:2])
    add_run('HOT-GROUND', 'hot', 'ground', F['hotSupply_D'], [(hs[0], hs[1], zfirst + mf['hotH']), (hs[0], hs[1], zg + FL['ground']['pipe'])]
            + [(x, y, zg + FL['ground']['pipe']) for x, y in gh] + [(*inlet(mg, 0)[:2], zg + mg['hotH'])], 'HOT-ROOF', mg['id'], 'המשך האספקה החמה למחלק הקרקע', insul=True)
    sleeves.extend(crossings(gh, grids['ground'], 'HOT-GROUND', F['hotSupply_D'], zg + FL['ground']['pipe'], 'ground'))
    gr = grids['ground'].route(inlet(mg, 0)[:2], (hr[0] + UY[0] * 0.20, hr[1] + UY[1] * 0.20))
    outl = lambda m, h: (m['E'] + m['axis'][0] * 0.35, m['N'] + m['axis'][1] * 0.35, h)
    add_run('RET-GROUND', 'return', 'ground', F['hotReturn_D'], [outl(mg, zg + mg['hotH']), (*outl(mg, 0)[:2], zg + FL['ground']['pipe'])] + [(x, y, zg + FL['ground']['pipe']) for x, y in gr[1:]]
            + [(hr[0], hr[1], zg + FL['ground']['pipe']), (hr[0], hr[1], zfirst + mf['hotH'] + 0.10)], mg['id'], 'RET-RISER', 'קו סחרור (חזרה) מקצה מחלק הקרקע (הערה 12)', insul=True)
    sleeves.extend(crossings(gr, grids['ground'], 'RET-GROUND', F['hotReturn_D'], zg + FL['ground']['pipe'], 'ground'))
    add_run('RET-FIRST', 'return', 'first', F['hotReturn_D'], [outl(mf, zfirst + mf['hotH']), (hr[0], hr[1], zfirst + mf['hotH'] + 0.10)], mf['id'], 'RET-RISER', 'חזרה מקצה מחלק קומה א\'', insul=True)
    add_run('RET-RISER', 'return', 'roof', F['hotReturn_D'], [(hr[0], hr[1], zfirst + mf['hotH'] + 0.10), (hr[0], hr[1], zrp + 0.06), (htr['E'] + 0.25, htr['N'], zrp + 0.06), (htr['E'] + 0.25, htr['N'], zr + 0.25)],
            'RET-GROUND', 'HTR@roof', 'קו סחרור עולה לגג אל כניסת הדוד; משאבת סחרור + אל-חוזר ליד הדוד, טיימר / רגש לחץ', insul=True)
    # shaft slab openings
    for lvl, name in ((H0 - 0.15, 'תקרת המרתף / רצפת הקרקע (‎-0.15)'), (H0 + 3.70, 'תקרת הקרקע (+3.70)'), (H0 + FL['roof']['finish'], 'תקרת הגג (+6.85)')):
        sleeves.append({'pipe': 'SHAFT', 'floor': 'shaft', 'at': [r3(SH['poly'].centroid.x), r3(SH['poly'].centroid.y), r3(lvl)], 'through': name,
                        'sleeve': f'פתח פיר {SH["local"][2] * 100:.0f}×{SH["local"][3] * 100:.0f} ס"מ ביציקה (תיאום קונסטרוקטור); שרוול PVC לכל צינור ואיטום אש בין הקומות',
                        'sleeveD_mm': None, 'material': 'פתח ביציקה'})
    # superseded consultant items
    sup = set()
    for s in SM:
        if s.get('replaces'): sup.add(s['replaces'])
    for rid in ('CWR22@roof', 'HWR23@roof'):
        pass
    for r in N['runs']:
        if r['system'] == 'hot': sup.add(r['id'])
    for n in N['nodes']:
        if n['kind'] in ('designEnd', 'kitchenPoint') or (n['kind'] == 'riser' and "קומה א'" in n.get('title', '')): sup.add(n['id'])
        if n['kind'] == 'hotManifold': sup.add(n['id'])
    sup.discard(I['mainEntry']['from'])
    deg = {}
    for r in N['runs']:
        if r['system'] == 'cold':
            for e in (r['from'], r['to']): deg[e] = deg.get(e, 0) + 1
    changed = True
    while changed:
        changed = False
        for r in N['runs']:
            if r['system'] != 'cold' or r['id'] in sup or I['mainEntry']['from'] in (r['from'], r['to']): continue
            a, b = r['from'], r['to']
            if a in sup or b in sup:
                sup.add(r['id']); changed = True
                for e in (a, b):
                    if e not in sup and deg.get(e) == 2 and NODES[e]['kind'] == 'waterJoint': sup.add(e)
    sup = sorted(sup)
    mans = [{**{k: v for k, v in m.items()}, 'E': r3(m['E']), 'N': r3(m['N']), 'axis': [r3(v) for v in m['axis']], 'face': [r3(v) for v in m['face']],
             'H_floor': r3(H0 + FL[floor_of_man[k]]['finish']), 'hotPending': k.startswith('unit'), 'status': 'proposal'} for k, m in manifolds.items()]
    out = {'_doc': 'הצעת תכנון לשכבת האינסטלציה – לאישור אביחי ואחר כך היועץ. נוצר ע"י tools/plumbing/propose.py; לא לערוך ידנית.',
           'status': 'proposal', 'decisions': I['decisions'], 'pending': I['pending'],
           'shaft': {k: v for k, v in SH.items() if k not in ('poly',)}, 'stackMoves': SM, 'manifolds': mans, 'points': pt_out, 'runs': runs,
           'sleeves': sleeves, 'superseded': sup,
           'submeters': {'E': r3(bcold[0]), 'N': r3(bcold[1]), 'H': r3(zu + 0.60), 'title': 'מוני משנה ליחידות 1 ו-2 + ברזי ניתוק (בבסיס הפיר)'},
           'mainValve': {'E': r3(c[0]), 'N': r3(c[1]), 'H': r3(zg + I['mainEntry']['valveH']), 'title': 'ברז ראשי + מז"ח/אל-חוזר לבית (בפיר, קומת קרקע)'},
           'recircPump': {'E': r3(htr['E'] + 0.25), 'N': r3(htr['N']), 'H': r3(zr + 0.25), 'title': 'משאבת סחרור + אל-חוזר + ברז ניתוק (פרט הסחרור של היועץ)'},
           'summary': {'runs': len(runs), 'pex_m': r3(sum(r['length_m'] for r in runs)), 'points': len(pt_out), 'sleeves': len(sleeves),
                       'stacksMoved': sum(1 for s in SM if s.get('status') == 'proposal')}}
    out['site'] = propose_site.build()
    out['summary']['site'] = {'chambers': len(out['site']['chamberRaise']), 'drops': len(out['site']['drops']), 'hoseReel': 1, 'meterConn': 2}
    json.dump(out, open(os.path.join(ROOT, 'data/plumbing/proposal.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out['summary'], ensure_ascii=False)); print('superseded', sup)
    for m in mans: print(m['id'], m['E'], m['N'], len(m['outlets']['cold']), len(m['outlets']['hot']))


if __name__ == '__main__':
    main()

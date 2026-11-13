"""The exposed skin of the skeleton, and how much of it the finish surfaces cover (plaster round 4, chat prompt
docs/chat-prompts/2026-11-11-בדיקה-היקפית-טיח-ואיטום.md).

Every element of the skeleton is a vertical prism (a plan polygon between a bottom and a top level): concrete walls and
columns, block walls (each segment – the openings are the gaps between them), the infill over / under the basement-wall
openings, slabs, ceiling and ground beams, the courtyard walls. The union of the prisms is cut into height bands at every
bottom / top level; inside a band the cross-section does not change, so:
  - vertical skin  = the boundary of the band's union, from the band's bottom to its top (merged over the bands while the
                     same edge goes on)
  - horizontal skin = at every level, the union below minus the union above (faces looking up: wall tops, sills, ledges)
                     and the union above minus the union below (faces looking down: soffits, heads, beam bottoms)
Not finish surfaces: floors (an up face at the level of a slab next to it), faces against the soil, faces against the
blockers (stairs, pool – not plastered, but they hide what they touch).
Sampling: a 2 cm grid on every skin face (config skin.grid_m). A sample is covered when a finish surface (plaster of any
type, membrane, cladding, the 'none' neighbour side, reveals, sills, patches) faces the same way within reach_m of it.
"""
import math
from collections import defaultdict

import numpy as np
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, Point, box
from shapely.ops import unary_union

EPS = 0.0005


def polys(g):
    if g is None or g.is_empty: return []
    if g.geom_type == 'Polygon': return [g]
    return [q for q in getattr(g, 'geoms', []) if q.geom_type == 'Polygon' and not q.is_empty]


class Skin:
    def __init__(self, prisms, blockers, soil_fn, floor_fn, grid=0.02):
        """prisms: [{id, kind, poly, bottom, top, floor}] (plastered material); blockers: same shape (hide, not plastered);
        soil_fn(x, y, z) -> bool; floor_fn(x, y, z) -> bool (an up face here is a floor)"""
        self.P = [p for p in prisms if p['top'] - p['bottom'] > 0.004 and not p['poly'].is_empty]
        self.B = [p for p in blockers if p['top'] - p['bottom'] > 0.004 and not p['poly'].is_empty]
        self.soil, self.isfloor, self.grid = soil_fn, floor_fn, grid
        zs = sorted({round(v, 3) for p in self.P for v in (p['bottom'], p['top'])})
        lv = []
        for z in zs:
            if not lv or z - lv[-1] > 0.002: lv.append(z)
        self.levels = lv
        self.bands = []   # (z0, z1, union, members)
        for z0, z1 in zip(lv, lv[1:]):
            zm = (z0 + z1) / 2
            mem = [p for p in self.P if p['bottom'] < zm < p['top']]
            U = unary_union([p['poly'] for p in mem]).buffer(0.0015, join_style=2).buffer(-0.0015, join_style=2) if mem else Polygon()
            self.bands.append((z0, z1, U, mem))
        self.BU = {}   # blockers per band
        for i, (z0, z1, _, _) in enumerate(self.bands):
            zm = (z0 + z1) / 2
            bl = [b['poly'] for b in self.B if b['bottom'] < zm < b['top']]
            self.BU[i] = unary_union(bl) if bl else Polygon()
        self.vertical = self._vertical()
        self.horizontal = self._horizontal()

    # ------------------------------------------------------------ owners
    def owner(self, x, y, z, members=None):
        pt = Point(x, y); best = None; bd = 9
        for p in (members if members is not None else self.P):
            if p['bottom'] - 0.003 <= z <= p['top'] + 0.003:
                d = p['poly'].exterior.distance(pt) if p['poly'].geom_type == 'Polygon' else p['poly'].boundary.distance(pt)
                if p['poly'].contains(pt): d = min(d, 0.0)
                if d < bd: bd, best = d, p
        return best if bd < 0.02 else None

    # ------------------------------------------------------------ vertical skin: edges × z, merged over the bands
    def _vertical(self):
        out = []; open_ = {}
        for i, (z0, z1, U, mem) in enumerate(self.bands):
            cur = {}
            for g in polys(U):
                for ring, hole in [(g.exterior, False)] + [(r, True) for r in g.interiors]:
                    cs = list(ring.coords)
                    ccw = ring.is_ccw
                    for A, B in zip(cs, cs[1:]):
                        L = math.dist(A, B)
                        if L < 0.004: continue
                        # outward normal: for a CCW exterior the material is on the left -> normal to the right
                        dx, dy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
                        nx, ny = (dy, -dx) if ccw else (-dy, dx)
                        k = (round(A[0], 3), round(A[1], 3), round(B[0], 3), round(B[1], 3))
                        cur[k] = (A, B, (nx, ny), L)
            nxt = {}
            for k, (A, B, n, L) in cur.items():
                if k in open_ and abs(open_[k]['z1'] - z0) < 1e-6: f = open_[k]; f['z1'] = z1; f['bands'].append(i)
                else: f = dict(a=A, b=B, n=n, L=L, z0=z0, z1=z1, bands=[i]); out.append(f)
                nxt[k] = f
            open_ = nxt
        return out

    # ------------------------------------------------------------ horizontal skin
    def _horizontal(self):
        out = []
        idx = {round(b[0], 3): i for i, b in enumerate(self.bands)}
        for j, z in enumerate(self.levels):
            below = self.bands[j - 1][2] if j - 1 >= 0 and j - 1 < len(self.bands) and abs(self.bands[j - 1][1] - z) < 1e-6 else Polygon()
            above = self.bands[j][2] if j < len(self.bands) and abs(self.bands[j][0] - z) < 1e-6 else Polygon()
            for g, up in ((below.difference(above), True), (above.difference(below), False)):
                for q in polys(g.buffer(-0.001, join_style=2).buffer(0.001, join_style=2)):
                    if q.area < 2e-4: continue
                    out.append(dict(poly=q, z=z, up=up))
        return out

    # ------------------------------------------------------------ sampling
    def samples_vertical(self, f):
        """grid samples of a vertical skin face: s (along), z, and the probe point in front (3 cm)"""
        g = self.grid; L = f['L']; H = f['z1'] - f['z0']
        ns, nz = max(1, int(math.ceil(L / g - 1e-9))), max(1, int(math.ceil(H / g - 1e-9)))
        s = (np.arange(ns) + 0.5) * (L / ns); z = f['z0'] + (np.arange(nz) + 0.5) * (H / nz)
        return s, z, L / ns, H / nz

    def samples_horizontal(self, h):
        g = self.grid; x0, y0, x1, y1 = h['poly'].bounds
        xs = np.arange(x0 + g / 2, x1, g); ys = np.arange(y0 + g / 2, y1, g)
        if not len(xs) or not len(ys):
            c = h['poly'].representative_point(); return np.array([c.x]), np.array([c.y])
        X, Y = np.meshgrid(xs, ys); X = X.ravel(); Y = Y.ravel()
        m = shapely.contains_xy(h['poly'], X, Y)
        if not m.any():
            c = h['poly'].representative_point(); return np.array([c.x]), np.array([c.y])
        return X[m], Y[m]


# ---------------------------------------------------------------- finish surfaces as coverage targets
class Cover:
    """vertical targets: (line a-b, outward normal, z0, z1); horizontal: (polygon, z, up)"""
    def __init__(self, reach=0.045):
        self.V = []; self.H = []; self.reach = reach; self.grid = defaultdict(list); self.hz = defaultdict(list)

    def add_v(self, a, b, n, z0, z1, holes=(), tag=None):
        if math.dist(a, b) < 1e-4 or z1 - z0 < 1e-4: return
        k = len(self.V); self.V.append((a, b, n, z0, z1, list(holes), tag))
        for gx in range(int(min(a[0], b[0]) // 1) - 1, int(max(a[0], b[0]) // 1) + 2):
            for gy in range(int(min(a[1], b[1]) // 1) - 1, int(max(a[1], b[1]) // 1) + 2): self.grid[(gx, gy)].append(k)

    def add_h(self, poly, z, up=None, tag=None):
        for q in polys(poly):
            if q.area < 1e-6: continue
            k = len(self.H); self.H.append((q, z, up, tag)); self.hz[round(z, 1)].append(k)

    def cand_v(self, f):
        A, B = f['a'], f['b']; nx, ny = f['n']
        ks = set()
        for gx in range(int(min(A[0], B[0]) // 1) - 1, int(max(A[0], B[0]) // 1) + 2):
            for gy in range(int(min(A[1], B[1]) // 1) - 1, int(max(A[1], B[1]) // 1) + 2): ks.update(self.grid.get((gx, gy), ()))
        seg = LineString([A, B]); out = []
        for k in ks:
            a, b, n, z0, z1, holes, tag = self.V[k]
            if z1 <= f['z0'] or z0 >= f['z1']: continue
            if abs(n[0] * nx + n[1] * ny) < 0.85: continue     # parallel faces only (either side – a face drawn the other way still covers)
            if LineString([a, b]).distance(seg) > self.reach: continue
            out.append(self.V[k])
        return out

    def covered_v(self, f, s, z):
        """bool matrix [len(z), len(s)]: covered samples of skin face f"""
        A, B = f['a'], f['b']; L = f['L']; ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L; nx, ny = f['n']
        C = np.zeros((len(z), len(s)), dtype=bool)
        px = A[0] + ux * s; py = A[1] + uy * s
        for a, b, n, z0, z1, holes, tag in self.cand_v(f):
            la = math.dist(a, b); vx, vy = (b[0] - a[0]) / la, (b[1] - a[1]) / la
            t = (px - a[0]) * vx + (py - a[1]) * vy                       # along the target
            d = np.abs((px - a[0]) * -vy + (py - a[1]) * vx)              # off the target line
            okS = (t >= -0.012) & (t <= la + 0.012) & (d <= self.reach)
            if not okS.any(): continue
            okZ = (z >= z0 - 0.012) & (z <= z1 + 0.012)
            M = np.outer(okZ, okS)
            for (hs0, hs1, hz0, hz1) in holes:   # openings in the target (s along the target)
                hS = (t > hs0 + 0.012) & (t < hs1 - 0.012); hZ = (z > hz0 + 0.012) & (z < hz1 - 0.012)
                M &= ~np.outer(hZ, hS)
            C |= M
        return C

    def covered_h(self, h, X, Y):
        z = h['z']; C = np.zeros(len(X), dtype=bool)
        for zk in (round(z - 0.1, 1), round(z, 1), round(z + 0.1, 1)):
            for k in self.hz.get(zk, ()):
                q, qz, up, tag = self.H[k]
                if abs(qz - z) > self.reach: continue
                if up is not None and up != h['up']: continue
                C |= shapely.contains_xy(q.buffer(0.012, join_style=2), X, Y)
        return C


# ---------------------------------------------------------------- the model -> skin + targets (G = derive_finishes globals)
def model_prisms(G):
    P = []
    # block walls: rebuilt from blocks.json with the openings cut out (sill below, lintel / shutter box above, jambs at the sides)
    for w in G['BL']['walls']:   # incl. the walls an owner change would cancel – plan mode shows them (OC-10: BK-F83 / BK-F84)
        (x0, y0), (x1, y1) = w['axisITM']; L = math.hypot(x1 - x0, y1 - y0); ux, uy = (x1 - x0) / L, (y1 - y0) / L
        segs = w.get('segments') or [{'s0': 0, 's1': L, 'bottomRel': w['bottomRel'], 'topRel': w['topRel']}]
        ops = [o for o in w.get('openings') or [] if o['s1'] - o['s0'] > 0.005 and o['z1'] - o['z0'] > 0.005]
        for sg in segs:
            zb, zt = sg['bottomRel'], sg['topRel']
            zs = sorted({zb, zt, *[min(max(v, zb), zt) for o in ops for v in (o['z0'], o['z1'])]})
            for za, zc in zip(zs, zs[1:]):
                if zc - za < 0.002: continue
                zm = (za + zc) / 2
                iv = [(sg['s0'], sg['s1'])]
                for o in ops:
                    if not (o['z0'] < zm < o['z1']): continue
                    nv = []
                    for lo, hi in iv:
                        if o['s0'] > lo: nv.append((lo, min(hi, o['s0'])))
                        if o['s1'] < hi: nv.append((max(lo, o['s1']), hi))
                    iv = [v for v in nv if v[1] - v[0] > 0.002]
                for lo, hi in iv:
                    pa = (x0 + ux * lo, y0 + uy * lo); pb = (x0 + ux * hi, y0 + uy * hi)
                    P.append(dict(id=w['id'], kind='block', poly=G['block_rect'](pa, pb, w['thickness_m'])[0], bottom=za, top=zc, floor=w['floor'], src=w['source']))
    # concrete walls exactly as the model draws them (js/geometry/floors.js): the pieces around the openings, the concrete
    # sill / lintel in them, the part raised to the slab where no beam is above (ק17); the heads of the basement walls up to
    # the ground level (basementWallCaps, cast with the ground slab)
    poly_ = G['poly']
    for fl, D in (('ground', G['GF']), ('first', G['FF']), ('roof', G['RF'])):
        for w in D['walls']:
            pcs = [(p_['ringITM'], p_.get('holesITM', []), w['bottomRel'], w['topRel']) for p_ in w['partsITM']] if w.get('partsITM') else [(w['footprintITM'], w.get('holesITM', []), w['bottomRel'], w['topRel'])]
            pcs += [(f_['ringITM'], [], f_['bottomRel'], f_['topRel']) for f_ in w.get('infill') or []]
            pcs += [(f_['ringITM'], f_.get('holesITM', []), f_['bottomRel'], f_['topRel']) for f_ in w.get('raisedITM') or []]
            for r_, h_, b_, t_ in pcs: P.append(dict(id=w['id'], kind='concrete', poly=poly_(r_, h_), bottom=b_, top=t_, floor=fl, src=w['source']))
        for c in D['columns']: P.append(dict(id=c['id'], kind='column', poly=poly_(c['footprintITM']), bottom=c['bottomRel'], top=c['topRel'], floor=fl, src=c['source']))
        for c in D.get('basementWallCaps') or []: P.append(dict(id=c['wall'], kind='concrete', poly=poly_(c['footprintITM'], c.get('holesITM', [])), bottom=c['bottomRel'], top=c['topRel'], floor='unit', src=c['source']))
    for w in G['FR']['basementWalls']:
        pcs = [(p_['ringITM'], p_.get('holesITM', [])) for p_ in w['partsITM']] if w.get('partsITM') else [(w['footprintITM'], w.get('holesITM', []))]
        for r_, h_ in pcs: P.append(dict(id=w['id'], kind='concrete', poly=poly_(r_, h_), bottom=w['bottomRel'], top=w['topRel'], floor='unit', src=w['source']))
    # the systems pillar + bin room (stairs.json pillar): concrete walls, plastered
    pl = G['J']('data/structure/stairs.json').get('pillar')
    if pl: P.append(dict(id=pl['id'], kind='concrete', poly=unary_union([poly_(r_, (pl.get('wallHolesITM') or [])[i_] if i_ < len(pl.get('wallHolesITM') or []) else []) for i_, r_ in enumerate(pl['wallsITM'])]), bottom=pl['bottomRel'], top=pl['topRel'], floor='site', src=pl['source']))
    for s in G['INFILL']: P.append(dict(id=s['id'], kind=s['kind'], poly=s['poly'], bottom=s['bottom'], top=s['top'], floor=s.get('floor'), src=s.get('src')))
    for s in G['SLABS']: P.append(dict(id=s['id'], kind='slab', poly=s['poly'], bottom=s['bottom'], top=s['top'], floor=None, src=s.get('src')))
    for b in G['BEAM_LIST']: P.append(dict(id=b['id'], kind='beam', poly=b['R'], bottom=b['bottomRel'], top=b['topRel'], floor=b.get('floorOf'), src=b.get('src')))
    PER = G['PER']
    for w in PER['walls']: P.append(dict(id=w['id'], kind='perimeter', poly=G['poly'](w['ringITM']), bottom=w['bottomRel'], top=w['topRel'], floor='site', src=w['source']))
    for f in PER['footings']: P.append(dict(id=f['id'], kind='footing', poly=G['poly'](f['ringITM']), bottom=f['bottomRel'], top=f['topRel'], floor='site', src=f['source']))
    for p in P:
        if not p['poly'].is_valid: p['poly'] = p['poly'].buffer(0)
    return P


def soil_and_floor(G):
    SL = G['SLABS']; tree = shapely.STRtree([s['poly'] for s in SL]); tops = np.array([s['top'] for s in SL])
    DEV = G['DEV']; H0 = G['H0']
    dxy = np.array([(s['E'], s['N']) for s in DEV]); dz = np.array([s['z'] - H0 for s in DEV])
    house = unary_union([s['poly'] for s in SL if s['id'][:2] == 'GS']).buffer(0.05)

    def thr(X, Y):
        """soil below this level at (X, Y): the lowest slab top within 5 mm (a slab under the point); with no slab: the planned ground (development
        heights within 4 m, else ±0.00 - 0.15)"""
        X = np.atleast_1d(X); Y = np.atleast_1d(Y); n = len(X)
        T = np.full(n, np.inf)
        pts = shapely.points(X, Y)
        pi, si = tree.query(pts, predicate='dwithin', distance=0.005)
        if len(pi): np.minimum.at(T, pi, tops[si])
        base = np.full(n, -0.15)
        outside = ~shapely.contains_xy(house, X, Y)
        if outside.any():
            ii = np.where(outside)[0]
            d = np.hypot(dxy[None, :, 0] - X[ii, None], dxy[None, :, 1] - Y[ii, None]); j = d.argmin(1)
            g = np.where(d[np.arange(len(ii)), j] < 4, dz[j], -0.15); base[ii] = g
        out = np.minimum(base, T)
        # in front of an exterior paving zone: the paving finish surface (ק69–ק75) – what is below it is inside the paving build-up
        PV = G.get('PAVE')
        if PV is not None:
            pv = PV.at(X, Y); m = ~np.isnan(pv)
            if m.any(): out[m] = pv[m]
        return out

    def isfloor(poly, z):
        c = poly.representative_point()
        for s in SL:
            if abs(s['top'] - z) < 0.06 and s['poly'].distance(poly) < 0.05: return True
        return False
    return thr, isfloor


def model_cover(G, patches=()):
    C = Cover()
    for f in G['FACES']:
        L = math.dist(f['a'], f['b']); ux, uy = (f['b'][0] - f['a'][0]) / L, (f['b'][1] - f['a'][1]) / L
        C.add_v(f['a'], f['b'], f['normal'], f['z0'], f['z1'], [(o['s0'], o['s1'], o['z0'], o['z1']) for o in f['openings']], tag=('wall', f['key']))
    for b in G['BEAMSURF']:
        for x in b['sides']: C.add_v(x['a'], x['b'], x['normal'], x['z0'], x['z1'], tag=('beam', b['key']))
        for x in b['flats']: C.add_h(Polygon(x['ringITM']), x['z'], x['part'] == 'top', tag=('beam', b['key']))
    for r in G['REVS']:
        for q in r['quads']:
            Q = q['q']
            if q['part'] == 'jamb':
                a, b = Q[0][:2], Q[1][:2]; L = math.dist(a, b)
                if L < 1e-4: continue
                C.add_v(a, b, (-(b[1] - a[1]) / L, (b[0] - a[0]) / L), Q[0][2], Q[2][2], tag=('reveal', r['key']))
            else: C.add_h(Polygon([p[:2] for p in Q]).buffer(0), Q[0][2], None, tag=('reveal', r['key']))
    for c in G['CEILS']: C.add_h(Polygon(c['ringITM'], c['holesITM']).buffer(0), c['z'], False, tag=('ceiling', c['key']))
    for t in G['TOPS']: C.add_h(Polygon(t['ringITM'], t.get('holesITM', [])).buffer(0), t['z'], True, tag=('top', t['key']))
    for x in G['CLAD']: C.add_v(x['a'], x['b'], x['normal'], x['z0'], x['z1'], tag=('cladding', x['owner']))
    for p in patches:
        if p['vertical']: C.add_v(p['a'], p['b'], p['normal'], p['z0'], p['z1'], tag=('patch', p.get('key')))
        else: C.add_h(Polygon(p['ringITM'], p.get('holesITM', [])).buffer(0), p['z'], p['up'], tag=('patch', p.get('key')))
    return C


def analyse(G, patches=(), grid=0.02):
    """-> (skin, list of uncovered pieces): vertical {face, s, z, ds, dz, U (bool [z, s])}; horizontal {face, X, Y, U}"""
    prisms = model_prisms(G)
    thr, isfloor = soil_and_floor(G)
    S = Skin(prisms, [], None, None, grid)
    C = model_cover(G, patches); S.cover = C
    res = []
    for f in S.vertical:
        s, z, ds, dz = S.samples_vertical(f)
        A, B = f['a'], f['b']; ux, uy = (B[0] - A[0]) / f['L'], (B[1] - A[1]) / f['L']; nx, ny = f['n']
        qx = A[0] + ux * s + nx * 0.03; qy = A[1] + uy * s + ny * 0.03
        T = thr(qx, qy)
        need = z[:, None] >= T[None, :] - 1e-6                           # not against the soil
        cov = C.covered_v(f, s, z)
        U = need & ~cov
        if U.any(): res.append(dict(kind='v', face=f, s=s, z=z, ds=ds, dz=dz, U=U, area=float(U.sum() * ds * dz)))
        # basement walls against the soil / backfill with no finish at all (e.g. the courtyard side under the court floor):
        # waterproofing + protection sheet (type membrane – not plaster), so the quantities and the check see them
        Us = ~need & ~cov
        if Us.any() and f['z0'] < -0.5:
            m = ((A[0] + B[0]) / 2 - nx * 0.005, (A[1] + B[1]) / 2 - ny * 0.005)
            o = S.owner(m[0], m[1], float(z[Us.any(1)].mean()))
            if o and o.get('floor') == 'unit': res.append(dict(kind='v', face=f, s=s, z=z, ds=ds, dz=dz, U=Us, area=float(Us.sum() * ds * dz), soil=True))
    for h in S.horizontal:
        if h['up'] and isfloor(h['poly'], h['z']): continue
        X, Y = S.samples_horizontal(h)
        T = thr(X, Y)
        z = h['z'] + (0.03 if h['up'] else -0.03)
        need = z >= T - 1e-6
        if not need.any(): continue
        cov = C.covered_h(h, X, Y)
        U = need & ~cov
        if U.any(): res.append(dict(kind='h', face=h, X=X, Y=Y, U=U, area=float(U.sum() * grid * grid)))
    return S, res


# ---------------------------------------------------------------- patches: plaster where the skin is exposed and nothing covers it
def _runs(col):
    out = []; i = 0; n = len(col)
    while i < n:
        if col[i]:
            j = i
            while j + 1 < n and col[j + 1]: j += 1
            out.append((i, j)); i = j + 1
        else: i += 1
    return out


def make_patches(S, res, G):
    """vertical pieces -> rectangles (columns with the same uncovered z runs merged); horizontal -> union of grid cells.
    Type by the space in front: wet room – smoothed cement, ממ"ד soffit – skim, other room – interior, outside – exterior."""
    r3 = G['r3']; room_at = G['room_at']; floor_of_z = G['floor_of_z']; g = S.grid
    out = []

    PLOT = G.get('PLOT'); PARCELS = G.get('PARCELS') or []; PV = G.get('PAVE')

    def outside_plot(o, px, py):
        """a face of a courtyard wall that looks out of the lot: the neighbour side (no plaster) or the street (cladding) –
        ק73–ק75: the patches at the foot / the end of the walls on the neighbour side had got exterior plaster"""
        if not o or o.get('kind') != 'perimeter' or PLOT is None or PLOT.contains(Point(px, py)): return None
        use = next((u for pg, u in PARCELS if pg.contains(Point(px, py))), None)
        return ('cladding', 'השלמה – חומה לרחוב, צד הרחוב: חיפוי אבן, בלי טיח') if use == 'public' else \
               ('none', 'השלמה – חומה עם השכן, צד השכן: בלי טיח (ק73–ק75)')

    def riser(o, px, py):
        """the edge of a ground slab outside, above the paving in front of it: the riser of a step – finished with the paving /
        stone of the step, no plaster (ק69, ק72)"""
        if not o or o.get('kind') != 'slab' or not str(o.get('id', '')).startswith('GS') or PV is None: return None
        if np.isnan(PV.at(px, py))[0]: return None
        return ('none', 'השלמה – רום מדרגה בחוץ (שפת רצפה מעל הריצוף): בלי טיח – חיפוי המדרגה עם הריצוף (ק69, ק72)')

    def typ(px, py, z, down=False):
        rm = room_at((px, py), z)
        if not rm: return 'exterior', None, 'השלמה – פן חשוף מבחוץ'
        if rm['type'] == 'wet': return 'wet', rm, 'השלמה – חדר רטוב'
        if rm['type'] == 'mamad' and down: return 'skim', rm, 'השלמה – תקרת ממ"ד (שפכטל)'
        if rm['type'] in ('court', 'outdoor'): return 'exterior', rm, 'השלמה – חצר / גג'
        return 'interior', rm, 'השלמה – פן חשוף בחדר'
    for r in res:
        f = r['face']
        if r['kind'] == 'v':
            A, B = f['a'], f['b']; L = f['L']; ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L; nx, ny = f['n']
            U = r['U']; ds, dz = r['ds'], r['dz']; z = r['z']
            cols = [tuple(_runs(U[:, j])) for j in range(U.shape[1])]
            j = 0
            while j < len(cols):
                if not cols[j]: j += 1; continue
                k = j
                while k + 1 < len(cols) and cols[k + 1] == cols[j]: k += 1
                s0, s1 = j * ds, (k + 1) * ds
                for i0, i1 in cols[j]:
                    z0 = max(f['z0'], z[i0] - dz / 2); z1 = min(f['z1'], z[i1] + dz / 2)
                    sm = (s0 + s1) / 2; px, py = A[0] + ux * sm, A[1] + uy * sm; zm = (z0 + z1) / 2
                    o = S.owner(px - nx * 0.005, py - ny * 0.005, zm)
                    ty, rm, why = typ(px + nx * 0.1, py + ny * 0.1, zm)
                    if r.get('soil'): ty, rm, why = 'membrane', None, 'השלמה – קיר מרתף במגע עם הקרקע / המילוי: איטום + יריעת הגנה, בלי טיח'
                    elif not rm:
                        alt = outside_plot(o, px + nx * 0.1, py + ny * 0.1) or riser(o, px + nx * 0.1, py + ny * 0.1)
                        if alt: ty, why = alt
                    a = [r3(A[0] + ux * s0), r3(A[1] + uy * s0)]; b = [r3(A[0] + ux * s1), r3(A[1] + uy * s1)]
                    out.append(dict(kind='patch', vertical=True, part='side', a=a, b=b, normal=[r3(nx), r3(ny)], z0=r3(z0), z1=r3(z1),
                                    length=r3(s1 - s0), area=round((s1 - s0) * (z1 - z0), 6), net=round((s1 - s0) * (z1 - z0), 6),
                                    owner=o['id'] if o else None, ownerKind=o['kind'] if o else None,
                                    floor=(o or {}).get('floor') or floor_of_z(zm) if (o or {}).get('floor') != 'site' else 'site',
                                    room=rm['key'] if rm else None, roomType=rm['type'] if rm else 'outdoor', defaultType=ty, typeReason=why,
                                    scaffold=False, scaffoldArea=0, source=(o or {}).get('src') or 'נגזר מעור השלד (tools/finishes/skin.py)'))
                j = k + 1
        else:
            X, Y = r['X'][r['U']], r['Y'][r['U']]
            # exact: the skin face minus what already covers it (no saw-tooth of grid cells along slanted edges); grid cells
            # only for the samples a sliver clean-up would leave out
            C = S.cover; z = f['z']
            cov = [q.buffer(0.012, join_style=2) for (q, qz, up, tag) in C.H if abs(qz - z) <= C.reach and (up is None or up == f['up']) and q.intersects(f['poly'])]
            exact = f['poly'].difference(unary_union(cov)) if cov else f['poly']
            # only where samples are uncovered (not against the soil): the cells of those samples, grown half a cell
            need = unary_union([box(x - g, y - g, x + g, y + g) for x, y in zip(X, Y)])
            exact = exact.intersection(need)
            exact = exact.buffer(-0.002, join_style=2).buffer(0.002, join_style=2).intersection(f['poly'])
            left = ~shapely.contains_xy(exact.buffer(0.0005), X, Y) if not exact.is_empty else np.ones(len(X), dtype=bool)
            extra = [box(x - g / 2, y - g / 2, x + g / 2, y + g / 2) for x, y in zip(X[left], Y[left])]
            cells = unary_union([exact] + extra).intersection(f['poly'].buffer(0.0005)) if extra else exact
            for q in polys(cells.buffer(0.0002, join_style=2).buffer(-0.0002, join_style=2)):
                if q.area < 1e-7: continue
                if q.geom_type != 'Polygon' or q.is_empty: continue
                c = q.representative_point(); z = f['z']
                o = S.owner(c.x, c.y, z + (-0.005 if f['up'] else 0.005))
                ty, rm, why = typ(c.x, c.y, z + (0.3 if f['up'] else -0.3), down=not f['up'])
                part = 'soffit' if not f['up'] else ('sill' if (o and o['kind'] == 'block' and any(abs(op['sillRel'] - z) < 0.03 and Point(op['centerITM']).distance(q) < 0.4 for op in G['OP'])) else 'top')
                out.append(dict(kind='patch', vertical=False, part=part, up=bool(f['up']), z=r3(z),
                                ringITM=[[r3(x), r3(y)] for x, y in list(q.exterior.coords)[:-1]],
                                holesITM=[[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in q.interiors],
                                area=round(q.area, 6), net=round(q.area, 6), owner=o['id'] if o else None, ownerKind=o['kind'] if o else None,
                                floor=('site' if (o or {}).get('floor') == 'site' else floor_of_z(z)), room=rm['key'] if rm else None,
                                roomType=rm['type'] if rm else 'outdoor', defaultType=ty, typeReason=why + (' – אדן' if part == 'sill' else ''),
                                scaffold=False, scaffoldArea=0, source=(o or {}).get('src') or 'נגזר מעור השלד (tools/finishes/skin.py)'))
    return [p for p in out if p['area'] > 1e-6]


# ---------------------------------------------------------------- steps between elements on one wall surface
def steps(S, maxstep=0.08, minrun=0.1):
    """plan jogs (a short edge between two parallel faces of different elements) and ledges (a thin horizontal strip
    between a face below and a face above). -> [{kind, step_m, length_m, z0, z1, xy, n, a, b}]; a / b = prisms"""
    out = {}
    for i, (z0, z1, U, mem) in enumerate(S.bands):
        if z1 - z0 < 0.01: continue
        zm = (z0 + z1) / 2
        for g in polys(U):
            for ring in [g.exterior] + list(g.interiors):
                cs = list(ring.coords)[:-1]; n = len(cs)
                if n < 4: continue
                E = [(cs[k], cs[(k + 1) % n]) for k in range(n)]
                for k in range(n):
                    (A, B) = E[k]; L = math.dist(A, B)
                    if L > maxstep or L < 0.003: continue
                    (P0, P1), (Q0, Q1) = E[k - 1], E[(k + 1) % n]
                    Lp, Lq = math.dist(P0, P1), math.dist(Q0, Q1)
                    if Lp < minrun or Lq < minrun: continue
                    up = ((P1[0] - P0[0]) / Lp, (P1[1] - P0[1]) / Lp); uq = ((Q1[0] - Q0[0]) / Lq, (Q1[1] - Q0[1]) / Lq)
                    if up[0] * uq[0] + up[1] * uq[1] < 0.995: continue           # the two faces run on in the same direction
                    off = abs((Q0[0] - P1[0]) * -up[1] + (Q0[1] - P1[1]) * up[0])  # offset between the two face lines
                    if off < 0.003: continue
                    # the material behind each face (probe 5 mm inside, 5 cm from the jog)
                    ccw = ring.is_ccw if ring is g.exterior else ring.is_ccw
                    def inside(Pa, Pb, back):
                        u = ((Pb[0] - Pa[0]), (Pb[1] - Pa[1])); l = math.hypot(*u); u = (u[0] / l, u[1] / l)
                        nn = (u[1], -u[0]) if ccw else (-u[1], u[0])             # outward
                        base = Pb if back else Pa; d = -0.05 if back else 0.05
                        return (base[0] + u[0] * d - nn[0] * 0.005, base[1] + u[1] * d - nn[1] * 0.005), nn
                    pa, nn = inside(P0, P1, True); pb, _ = inside(Q0, Q1, False)
                    oa, ob = S.owner(pa[0], pa[1], zm, mem), S.owner(pb[0], pb[1], zm, mem)
                    if not oa or not ob or oa['id'] == ob['id']: continue
                    key = ('jog', round(A[0], 2), round(A[1], 2), oa['id'], ob['id'])
                    r = out.get(key)
                    if r and abs(r['z1'] - z0) < 0.003: r['z1'] = z1; continue
                    out[key] = dict(kind='jog', step_m=off, length_m=None, z0=z0, z1=z1, xy=((A[0] + B[0]) / 2, (A[1] + B[1]) / 2), n=nn, a=oa, b=ob)
    res = [dict(r, length_m=r['z1'] - r['z0']) for r in out.values()]
    for h in S.horizontal:
        q = h['poly']; per = q.length
        if per <= 0: continue
        w = 2 * q.area / per * 1.0
        mr = q.minimum_rotated_rectangle; ps = list(mr.exterior.coords)[:4]
        e1, e2 = math.dist(ps[0], ps[1]), math.dist(ps[1], ps[2]); width, length = min(e1, e2), max(e1, e2)
        if width > maxstep or length < minrun or q.area < 0.9 * width * length: continue   # a straight strip only
        c = q.representative_point(); z = h['z']
        lo, hi = (z - 0.005, z + 0.005)
        below = S.owner(c.x, c.y, lo) if h['up'] else None; above = S.owner(c.x, c.y, hi) if not h['up'] else None
        # the other element: the one on the other side of the level, touching the strip
        other = None; bd = 9
        for p in S.P:
            zz = hi if h['up'] else lo
            if not (p['bottom'] - 0.003 <= zz <= p['top'] + 0.003): continue
            d = p['poly'].distance(q)
            if d < 0.01 and d < bd: bd, other = d, p
        a, b = (below, other) if h['up'] else (other, above)
        if not a or not b or a['id'] == b['id']: continue
        res.append(dict(kind='ledge', step_m=width, length_m=length, z0=z, z1=z, xy=(c.x, c.y), n=None, a=a, b=b, up=h['up']))
    return res

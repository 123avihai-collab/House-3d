"""Plaster in one plane (12.11.2026, Avihai: "the walls are not in one line – many lines and bumps").

The plaster faces are derived per element (wall, column, block segment, beam side, patch), each on its own skeleton
face. Where neighbouring elements of one wall surface are not flush (a block wall 2–8 cm behind a column, a beam a few cm
proud of the wall under it) every piece was drawn on its own plane: steps, slivers and dark slits at the joints.
Here, after the derivation, the vertical plaster faces of one wall surface are brought to ONE plane – the most proud skin
of that surface – with a varying plaster thickness, the way it is built (thick plaster + mesh over the recessed part):

1. plane of each face = its own line, or the skeleton skin in front of it (a face never lies behind the skeleton);
2. faces that look the same way, lie within `flattenMax_m` (data/finishes/config.json) of each other and touch along the
   wall or in height form one surface; its plane = the most proud one; each face gets `shift` (m, along its normal);
3. the small faces of the steps themselves (the return of a jog, the ledge under a proud beam) are inside the thickened
   plaster: kept in the quantities, `hidden` in the model;
4. reveals, wall heads, sills and the other horizontal pieces whose edge is on a shifted face follow it (their vertices move);
5. outer corners: the drawn faces (plane + the display offset of the plaster sheet, data/config/display.json) are extended
   to meet each other (`ext` = [at a, at b], m) – no slit at the corner.
Nothing of the skeleton changes. The thickness added (`shift`) is listed: docs/verification/plaster-flatten.md.
"""
import math
from collections import defaultdict

PAR = 0.9998     # parallel faces (about 1.1°)
SPAN = 0.08      # (set by flatten(): the largest added thickness on one surface)


def _unit(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L), L


class _Face:
    __slots__ = ('i', 'ref', 'kind', 'a', 'b', 'n', 'u', 'L', 'z0', 'z1', 'c', 'plane', 'k', 'shift', 'seed', 'off')

    def __init__(self, ref, kind, a, b, n, z0, z1, seed, off):
        self.ref, self.kind, self.a, self.b, self.z0, self.z1, self.seed, self.off = ref, kind, a, b, z0, z1, seed, off
        (self.u), self.L = _unit(a, b)
        nn = math.hypot(*n); self.n = (n[0] / nn, n[1] / nn)
        self.c = self.n[0] * a[0] + self.n[1] * a[1]
        self.plane = self.c; self.k = None; self.shift = 0.0


def _along(f, p):
    return (p[0] - f.a[0]) * f.u[0] + (p[1] - f.a[1]) * f.u[1]


def _dist(f, p):
    """signed distance of p in front of the plane of f (along its normal), from its own line"""
    return f.n[0] * p[0] + f.n[1] * p[1] - f.c


def flatten(G, tol, off, eps=0.03, span=None):
    global SPAN
    SPAN = span if span is not None else tol
    FACES, BEAMS, PATCHES, REVS, TOPS, WP = G['FACES'], G['BEAMSURF'], G['PATCHES'], G['REVS'], G['TOPS'], G['WPROOF']
    SV = G['SKIN_S'].vertical
    V = []
    for f in FACES:
        f.pop('proud', None)
        if math.dist(f['a'], f['b']) > 1e-4: V.append(_Face(f, 'wall', f['a'], f['b'], f['normal'], f['z0'], f['z1'], True, off))
    for b in BEAMS:
        for x in b['sides']:
            if math.dist(x['a'], x['b']) > 1e-4: V.append(_Face(x, 'beam', x['a'], x['b'], x['normal'], x['z0'], x['z1'], True, off))
    for p in PATCHES:
        if p['vertical'] and math.dist(p['a'], p['b']) > 1e-4: V.append(_Face(p, 'patch', p['a'], p['b'], p['normal'], p['z0'], p['z1'], True, off))
    for i, f in enumerate(V): f.i = i   # stable order (never id(): the clusters must come out the same on every run)
    seeds = [f for f in V if f.seed]
    # grid on the plan (1 m cells) for the neighbour searches
    grid = defaultdict(list)
    for i, f in enumerate(V):
        for gx in range(int(min(f.a[0], f.b[0]) // 1) - 1, int(max(f.a[0], f.b[0]) // 1) + 2):
            for gy in range(int(min(f.a[1], f.b[1]) // 1) - 1, int(max(f.a[1], f.b[1]) // 1) + 2): grid[(gx, gy)].append(i)

    def near(f, pool=None):
        ks = set()
        for gx in range(int(min(f.a[0], f.b[0]) // 1) - 1, int(max(f.a[0], f.b[0]) // 1) + 2):
            for gy in range(int(min(f.a[1], f.b[1]) // 1) - 1, int(max(f.a[1], f.b[1]) // 1) + 2): ks.update(grid.get((gx, gy), ()))
        return [V[k] for k in sorted(ks)]

    def rng(f, g):   # g's extent along f
        t0, t1 = _along(f, g.a), _along(f, g.b)
        return min(t0, t1), max(t0, t1)

    # 1. plane = own line, or the skin in front of it
    sgrid = defaultdict(list)
    for j, s in enumerate(SV):
        for gx in range(int(min(s['a'][0], s['b'][0]) // 1) - 1, int(max(s['a'][0], s['b'][0]) // 1) + 2):
            for gy in range(int(min(s['a'][1], s['b'][1]) // 1) - 1, int(max(s['a'][1], s['b'][1]) // 1) + 2): sgrid[(gx, gy)].append(j)
    for f in seeds:
        ks = set()
        for gx in range(int(min(f.a[0], f.b[0]) // 1), int(max(f.a[0], f.b[0]) // 1) + 1):
            for gy in range(int(min(f.a[1], f.b[1]) // 1), int(max(f.a[1], f.b[1]) // 1) + 1): ks.update(sgrid.get((gx, gy), ()))
        for j in ks:
            s = SV[j]
            if s['n'][0] * f.n[0] + s['n'][1] * f.n[1] < PAR: continue
            if s['z1'] <= f.z0 + 0.005 or s['z0'] >= f.z1 - 0.005: continue
            t0, t1 = sorted((_along(f, s['a']), _along(f, s['b'])))
            if t1 <= 0.005 or t0 >= f.L - 0.005: continue
            d = max(_dist(f, s['a']), _dist(f, s['b']))
            if 0 < d <= tol: f.plane = max(f.plane, f.c + d)
    # 2. one surface = touching parallel faces within tol of each other (union-find, the span kept within tol)
    up = {f.i: f.i for f in seeds}

    def find(x):
        while up[x] != x: up[x] = up[up[x]]; x = up[x]
        return x
    span = {f.i: [f.plane, f.plane, f] for f in seeds}   # in the frame of the root's normal: [min, max, reference face]
    pairs = []
    for f in seeds:
        for g in near(f):
            if not g.seed or g is f or g.i < f.i: continue
            if f.n[0] * g.n[0] + f.n[1] * g.n[1] < PAR: continue
            gp = g.plane - g.c + f.n[0] * g.a[0] + f.n[1] * g.a[1]    # g's plane in f's frame
            if abs(gp - f.plane) > tol: continue
            t0, t1 = rng(f, g)
            ov_s = min(t1, f.L) - max(t0, 0.0); ov_z = min(f.z1, g.z1) - max(f.z0, g.z0)
            if not ((ov_s > 0.01 and ov_z > -eps) or (ov_z > 0.01 and ov_s > -eps)): continue
            pairs.append((abs(gp - f.plane), f, g))
    pairs.sort(key=lambda x: (round(x[0], 6), x[1].i, x[2].i))
    for _, f, g in pairs:
        rf, rg = find(f.i), find(g.i)
        if rf == rg: continue
        A, B = span[rf], span[rg]; ref = A[2]
        # B's extremes in A's frame (the reference faces are parallel within PAR – the offset is taken at the faces)
        bmin = B[0] - (B[2].n[0] * B[2].a[0] + B[2].n[1] * B[2].a[1]) + (ref.n[0] * B[2].a[0] + ref.n[1] * B[2].a[1])
        bmax = B[1] - B[0] + bmin
        lo, hi = min(A[0], bmin), max(A[1], bmax)
        if hi - lo > SPAN + 1e-6: continue
        up[rg] = rf; span[rf] = [lo, hi, ref]
    groups = defaultdict(list)
    for f in seeds: groups[find(f.i)].append(f)
    clusters = []
    for r, mem in groups.items():
        lo, hi, ref = span[r]
        K = dict(ref=ref, n=ref.n, top=hi, low=lo, mem=mem)
        for f in mem:
            f.k = K
            # the common plane at the face (its own frame): the root plane moved by the face's offset in the root frame
            cf_in_ref = ref.n[0] * ((f.a[0] + f.b[0]) / 2) + ref.n[1] * ((f.a[1] + f.b[1]) / 2)
            f.shift = max(0.0, hi - cf_in_ref)
        clusters.append(K)
    # cluster extents in the root frame (along u of ref, z)
    for K in clusters:
        ref = K['ref']; ss = []
        for f in K['mem']: ss += [_along(ref, f.a), _along(ref, f.b)]
        K['s0'], K['s1'] = min(ss), max(ss)
        K['z0'], K['z1'] = min(f.z0 for f in K['mem']), max(f.z1 for f in K['mem'])
        K['moved'] = any(f.shift > 0.001 for f in K['mem'])
    moved = [K for K in clusters if K['moved']]

    def in_zone(K, p, z=None, e=0.005):
        ref = K['ref']; s = _along(ref, p); d = ref.n[0] * p[0] + ref.n[1] * p[1]
        ok = K['s0'] - e <= s <= K['s1'] + e and K['low'] - e <= d <= K['top'] + e
        if z is not None: ok = ok and K['z0'] - e <= z <= K['z1'] + e
        return ok

    def both_sides(K, f, e=0.012):
        """a jog face is inside the plaster only when the surface goes on at both sides of it (at its height)"""
        ref = K['ref']; sm = _along(ref, ((f.a[0] + f.b[0]) / 2, (f.a[1] + f.b[1]) / 2))
        def has(s_):
            for g in K['mem']:
                if min(g.z1, f.z1) - max(g.z0, f.z0) < min(0.01, f.z1 - f.z0 - 0.001): continue
                lo, hi = sorted((_along(ref, g.a), _along(ref, g.b)))
                if lo - 0.002 <= s_ <= hi + 0.002: return True
            return False
        return has(sm - e) and has(sm + e)

    def above_below(K, p, e=0.012):
        """a ledge is inside the plaster only when the surface goes on above and below it (along its length)"""
        ref = K['ref']; ss = [_along(ref, q) for q in p['ringITM']]; sm = (min(ss) + max(ss)) / 2; z = p['z']
        up_ = dn = False
        for g in K['mem']:
            lo, hi = sorted((_along(ref, g.a), _along(ref, g.b)))
            if not (lo - 0.002 <= sm <= hi + 0.002): continue
            if g.z0 - 0.002 <= z + e <= g.z1 + 0.002: up_ = True
            if g.z0 - 0.002 <= z - e <= g.z1 + 0.002: dn = True
        return up_ and dn

    # 3. patches: parallel ones inside a surface -> onto its plane; the step faces inside the thickened plaster -> hidden
    hidden = 0
    for f in V:
        for K in moved:
            if f.seed and f.k is K: continue
            ref = K['ref']; dot = f.n[0] * ref.n[0] + f.n[1] * ref.n[1]
            if f.z0 < K['z0'] - 0.005 or f.z1 > K['z1'] + 0.005: continue
            if dot > PAR or (dot > 0.98 and f.L * math.sqrt(max(0.0, 1 - dot * dot)) <= 0.003):   # a sliver a hair off parallel counts
                if f.k is not None and f.k['moved']: continue   # on its own surface already
                if in_zone(K, f.a) and in_zone(K, f.b):
                    f.shift = max(f.shift, K['top'] - (ref.n[0] * (f.a[0] + f.b[0]) / 2 + ref.n[1] * (f.a[1] + f.b[1]) / 2)); f.k = K
            elif abs(dot) < 0.05 and in_zone(K, f.a) and in_zone(K, f.b) and both_sides(K, f):
                f.ref['hidden'] = True; hidden += 1; break
    for p in PATCHES:
        if p['vertical'] or p.get('hidden'): continue
        for K in moved:
            if not (K['z0'] - 0.005 <= p['z'] <= K['z1'] + 0.005): continue
            if all(in_zone(K, q) for q in p['ringITM']) and above_below(K, p): p['hidden'] = True; hidden += 1; break

    # 4. horizontal pieces whose edge is on a shifted face follow it
    sh = [f for f in V if f.shift > 0.001 and not f.ref.get('hidden')]

    def move(pt, z):
        dx = dy = 0.0; seen = set()
        for f in sh:
            if id(f.k) in seen: continue
            if not (f.z0 - 0.01 <= z <= f.z1 + 0.01): continue
            if abs(_dist(f, pt)) > 0.006: continue
            s = _along(f, pt)
            if s < -0.01 or s > f.L + 0.01: continue
            dx += f.n[0] * f.shift; dy += f.n[1] * f.shift; seen.add(id(f.k))
        return dx, dy
    nmov = 0
    for r in REVS:
        for q in r['quads']:
            for v in q['q']:
                dx, dy = move(v, v[2])
                if dx or dy: v[0] = round(v[0] + dx, 3); v[1] = round(v[1] + dy, 3); nmov += 1
    # wall heads, sills, ledges, beam soffits / tops: the strip between an edge on a shifted face and the face's new plane is
    # drawn with the piece (`grow`: extra rings at the same level – the piece itself and its quantity stay as they are)
    def grow(t):
        nonlocal nmov
        ring = t['ringITM']; z = t['z']; adds = []
        for i in range(len(ring)):
            p1, p2 = ring[i], ring[(i + 1) % len(ring)]
            for f in sh:
                if not (f.z0 - 0.01 <= z <= f.z1 + 0.01): continue
                if abs(_dist(f, p1)) > 0.006 or abs(_dist(f, p2)) > 0.006: continue
                s1, s2 = _along(f, p1), _along(f, p2)
                if min(s1, s2) < -0.01 or max(s1, s2) > f.L + 0.01: continue
                o = f.shift
                adds.append([[round(p1[0], 4), round(p1[1], 4)], [round(p2[0], 4), round(p2[1], 4)],
                             [round(p2[0] + f.n[0] * o, 4), round(p2[1] + f.n[1] * o, 4)], [round(p1[0] + f.n[0] * o, 4), round(p1[1] + f.n[1] * o, 4)]])
                break
        if adds: t['grow'] = adds; nmov += len(adds)
    for t in TOPS + [p for p in PATCHES if not p['vertical'] and not p.get('hidden')]: grow(t)
    for b in BEAMS:
        for x in b['flats']: grow(x)

    # 5. outer corners: extend the drawn faces (plane + display offset) to meet
    D = [f for f in V if not f.ref.get('hidden')]
    ext = {id(f): [0.0, 0.0] for f in D}

    def drawn(f, end):
        p = f.a if end == 0 else f.b; o = f.shift + f.off
        return (p[0] + f.n[0] * o, p[1] + f.n[1] * o)
    R = tol + off + 0.04
    joins = 0
    for f in D:
        for end in (0, 1):
            E = drawn(f, end); best = None
            for g in near(f):
                if g is f or g.ref.get('hidden') or id(g) not in ext: continue
                if abs(f.u[0] * g.u[0] + f.u[1] * g.u[1]) > 0.87: continue
                if min(f.z1, g.z1) - max(f.z0, g.z0) < 0.01: continue
                for ge in (0, 1):
                    F = drawn(g, ge)
                    if math.dist(E, F) > R: continue
                    # a corner of the skin: the two faces end at the same point (else it is not this corner)
                    if math.dist(f.a if end == 0 else f.b, g.a if ge == 0 else g.b) > 0.01: continue
                    # intersection of the two drawn lines
                    den = f.u[0] * g.u[1] - f.u[1] * g.u[0]
                    if abs(den) < 1e-9: continue
                    t = ((F[0] - E[0]) * g.u[1] - (F[1] - E[1]) * g.u[0]) / den           # along f from E
                    w = ((F[0] - E[0]) * f.u[1] - (F[1] - E[1]) * f.u[0]) / den           # along g from F
                    ef = t if end == 1 else -t; eg = w if ge == 1 else -w                   # + = beyond the face end
                    if not (0.0005 < ef <= R and -1e-6 <= eg <= R): continue
                    # the real partner: the face that shares most of the corner's height (not a sliver patch next to it)
                    w_ = (min(f.z1, g.z1) - max(f.z0, g.z0)) * min(g.L, 0.5)
                    if best is None or w_ > best[4] + 1e-9: best = (ef, g, ge, eg, w_)
            if best:
                ef, g, ge, eg, _ = best
                ext[id(f)][end] = max(ext[id(f)][end], ef)
                ext[id(g)][ge] = max(ext[id(g)][ge], eg); joins += 1
    # 6. small gaps along one surface (slivers between the pieces, up to `gap`): the pieces are extended over them
    gap = 0.05; bridged = 0
    byK = defaultdict(list)
    for f in D:
        if f.k is not None: byK[id(f.k)].append(f)
    for mem in byK.values():
        ref = mem[0].k['ref']
        iv = []
        for f in mem:
            sa, sb = _along(ref, f.a), _along(ref, f.b)
            iv.append((min(sa, sb), max(sa, sb), f, 1 if sb > sa else 0))   # end index of f at the high side
        for lo1, hi1, f, hi_end in iv:
            nxt = None
            for lo2, hi2, g, _ in iv:
                if g is f or min(f.z1, g.z1) - max(f.z0, g.z0) < 0.01: continue
                if lo2 <= hi1 + 1e-4: continue
                d = lo2 - hi1
                if d <= gap and (nxt is None or d < nxt): nxt = d
            if nxt is None: continue
            # nothing of this surface already covers the gap at this height
            if any(lo2 <= hi1 + 1e-4 and hi2 >= hi1 + nxt - 1e-4 and g is not f and min(f.z1, g.z1) - max(f.z0, g.z0) >= f.z1 - f.z0 - 0.01 for lo2, hi2, g, _ in iv): continue
            ext[id(f)][hi_end] = max(ext[id(f)][hi_end], nxt); bridged += 1
    for f in D:
        e = ext[id(f)]
        if e[0] > 0.0005 or e[1] > 0.0005: f.ref['ext'] = [round(e[0], 3), round(e[1], 3)]
        if f.shift > 0.0005: f.ref['shift'] = round(f.shift, 3)
    # waterproofing strips on the wet room walls: with the wall face they lie on
    for w in WP:
        if w['kind'] != 'wall': continue
        best = None
        for f in seeds:
            if f.kind != 'wall' or f.shift <= 0.0005: continue
            if f.n[0] * w['normal'][0] + f.n[1] * w['normal'][1] < PAR: continue
            if abs(_dist(f, w['a'])) > 0.004 or abs(_dist(f, w['b'])) > 0.004: continue
            s0, s1 = sorted((_along(f, w['a']), _along(f, w['b'])))
            if s0 < -0.01 or s1 > f.L + 0.01 or w['z0'] > f.z1 or w['z1'] < f.z0: continue
            best = max(best or 0, f.shift)
        if best: w['shift'] = round(best, 3)
    rep = []
    for K in moved:
        mx = max(f.shift for f in K['mem'])
        rep.append(dict(members=sorted({(f.ref.get('owner') or f.ref.get('beam') or '?') for f in K['mem']}), max_shift=round(mx, 3),
                        z0=K['z0'], z1=K['z1'], at=[round((K['ref'].a[0] + K['ref'].b[0]) / 2, 2), round((K['ref'].a[1] + K['ref'].b[1]) / 2, 2)],
                        floor=K['ref'].ref.get('floor')))
    return dict(clusters=len(clusters), moved=len(moved), shifted=sum(1 for f in V if f.shift > 0.0005), hidden=hidden, vertices=nmov, joins=joins, bridged=bridged, report=rep)


# ---------------------------------------------------------------- check: the drawn plaster is IN FRONT of the skeleton everywhere it covers it
def front_check(G, off, ov, tol, grid=0.02, extra=()):
    """Every exposed vertical skin sample that a drawn plaster type covers (the coverage of tools/finishes/verify_coverage.py)
    must lie behind or on a drawn sheet: its final plane (shift + display offset), its final extent (ext + the seam overlap),
    not hidden. A sample in front of the sheet (the skeleton pokes through) or between two sheets (a slit) is a failure.
    -> list of {xy, z, owner?} (empty = the model shows one closed plaster skin)."""
    import numpy as np
    import skin as SKIN
    T = {t['id']: t for t in G['TYPES']['types']}
    drawn_t = lambda s: T.get(s.get('type'), {}).get('drawn', True) is not False
    S = G['SKIN_S']; thr, _ = SKIN.soil_and_floor(G)
    sheets = []   # (a, u, n, L, e0, e1, z0, z1, holes, plane offset from a)
    def add(s, holes=(), fill=False):
        if s.get('hidden'): return   # a step face inside the thickened plaster (both sides of it go on in one plane)
        hid = False
        a, b = s['a'], s['b']; L = math.dist(a, b)
        if L < 1e-4: return
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L); n = s['normal']; nn = math.hypot(*n); n = (n[0] / nn, n[1] / nn)
        e = s.get('ext') or [0, 0]
        sheets.append((a, u, n, L, max(e[0], ov), max(e[1], ov), s['z0'] - ov, s['z1'] + ov, list(holes), (s.get('shift') or 0) + off, s, fill, hid))
    for f in G['FACES']:
        if drawn_t(f): add(f, [(o['s0'], o['s1'], o['z0'], o['z1']) for o in f['openings']])
    for b in G['BEAMSURF']:
        if drawn_t(b):
            for x in b['sides']: add(dict(x, type=b['type'], floor=b['floor'], room=b.get('room'), roomType=b.get('roomType')))
    for p in G['PATCHES']:
        if p['vertical'] and drawn_t(p): add(p)
    for p in extra: add(p, fill=True)   # fillers close a gap; they do not make the skin around them 'needed'
    grid_ = defaultdict(list)
    for k, sh in enumerate(sheets):
        a, u, n, L = sh[:4]; b = (a[0] + u[0] * L, a[1] + u[1] * L)
        for gx in range(int(min(a[0], b[0]) // 1) - 1, int(max(a[0], b[0]) // 1) + 2):
            for gy in range(int(min(a[1], b[1]) // 1) - 1, int(max(a[1], b[1]) // 1) + 2): grid_[(gx, gy)].append(k)
    bad = []; pieces = []
    for f in S.vertical:
        s, z, ds, dz = S.samples_vertical(f)
        A, B = f['a'], f['b']; ux, uy = (B[0] - A[0]) / f['L'], (B[1] - A[1]) / f['L']; nx, ny = f['n']
        px = A[0] + ux * s; py = A[1] + uy * s
        need = z[:, None] >= thr(px + nx * 0.03, py + ny * 0.03)[None, :] - 1e-6
        if not need.any(): continue
        ok = np.zeros_like(need); cov0 = np.zeros_like(need)
        ks = set()
        for gx in range(int(min(A[0], B[0]) // 1) - 1, int(max(A[0], B[0]) // 1) + 2):
            for gy in range(int(min(A[1], B[1]) // 1) - 1, int(max(A[1], B[1]) // 1) + 2): ks.update(grid_.get((gx, gy), ()))
        for k in ks:
            a, u, n, L, e0, e1, z0, z1, holes, po, _, fill, hid = sheets[k]
            dot = n[0] * nx + n[1] * ny
            t = (px - a[0]) * u[0] + (py - a[1]) * u[1]
            d = (px - a[0]) * n[0] + (py - a[1]) * n[1] - po          # <= 0: the sample is behind the sheet
            if dot < 0.85:
                if hid: continue
                # an inner corner: a sliver of skin in the space of a crossing sheet, behind it – hidden by it
                if dot > -0.5:
                    m_ = (t >= -e0 - 1e-4) & (t <= L + e1 + 1e-4) & (d + po > 0.0005) & (d <= 0.001)
                    if m_.any(): ok |= np.outer((z >= z0 - 1e-4) & (z <= z1 + 1e-4), m_)
                continue
            # the sheet's own face covers the sample (as in the coverage check, same direction): then it has to be drawn in front of it
            c0 = (t >= -0.012) & (t <= L + 0.012) & (np.abs(d + po) <= 0.045)
            if c0.any() and not fill:
                M0 = np.outer((z >= z0 + ov - 0.012) & (z <= z1 - ov + 0.012), c0)
                for hs0, hs1, hz0, hz1 in holes:
                    M0 &= ~np.outer((z > hz0 + 0.012) & (z < hz1 - 0.012), (t > hs0 + 0.012) & (t < hs1 - 0.012))
                cov0 |= M0
            if hid: continue
            okS = (t >= -e0 - 1e-4) & (t <= L + e1 + 1e-4) & (d <= 0.001) & (d >= -(tol + off + 0.03))
            if not okS.any(): continue
            M = np.outer((z >= z0 - 1e-4) & (z <= z1 + 1e-4), okS)
            for hs0, hs1, hz0, hz1 in holes:
                M &= ~np.outer((z > hz0 + 0.012) & (z < hz1 - 0.012), (t > hs0 + 0.012) & (t < hs1 - 0.012))
            ok |= M
        U = need & cov0 & ~ok
        if U.any():
            iz, is_ = np.nonzero(U)
            for j in range(len(iz)):
                bad.append(dict(xy=(float(px[is_[j]]), float(py[is_[j]])), z=float(z[iz[j]]), n=(nx, ny), area=ds * dz))
            # the uncovered samples as rectangles (s0, s1, z0, z1) on this skin face – for the fillers
            cols = {}
            for j_ in range(U.shape[1]):
                col = U[:, j_]
                if not col.any(): continue
                runs = []; i_ = 0
                while i_ < len(col):
                    if col[i_]:
                        k_ = i_
                        while k_ + 1 < len(col) and col[k_ + 1]: k_ += 1
                        runs.append((float(z[i_] - dz / 2), float(z[k_] + dz / 2))); i_ = k_ + 1
                    else: i_ += 1
                cols[j_] = runs
            done = set()
            for j_ in sorted(cols):
                for r_ in cols[j_]:
                    if (j_, r_) in done: continue
                    k_ = j_
                    while k_ + 1 in cols and r_ in cols[k_ + 1]: k_ += 1; done.add((k_, r_))
                    s0_, s1_ = float(s[j_] - ds / 2), float(s[k_] + ds / 2)
                    pieces.append(dict(a=(A[0] + ux * s0_, A[1] + uy * s0_), b=(A[0] + ux * s1_, A[1] + uy * s1_), n=(nx, ny), z0=r_[0], z1=r_[1],
                                       near=[sheets[k][10] for k in ks if sheets[k][2][0] * nx + sheets[k][2][1] * ny > -0.5]))
    return bad, pieces


def fillers(G, off, ov, tol):
    """display-only sheets over what the front check still finds (corner slivers a few mm wide between pieces that do not meet,
    a skeleton face a hair in front of its sheet): drawn on the skin face + the display offset, with the type of the nearest
    sheet. Not in the quantities (area ~0). After them the check must be empty."""
    _, pcs = front_check(G, off, ov, tol)
    out = []
    for p in pcs:
        a, b = p['a'], p['b']; L = math.dist(a, b)
        if L < 1e-4: continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        def dseg(s):
            A, B = s['a'], s['b']; LL = math.dist(A, B); u = ((B[0] - A[0]) / LL, (B[1] - A[1]) / LL)
            t = max(0.0, min(LL, (m[0] - A[0]) * u[0] + (m[1] - A[1]) * u[1])); return math.dist(m, (A[0] + u[0] * t, A[1] + u[1] * t))
        nb = min(p['near'], key=dseg) if p['near'] else None
        out.append(dict(kind='filler', vertical=True, a=[round(a[0], 4), round(a[1], 4)], b=[round(b[0], 4), round(b[1], 4)], normal=[round(p['n'][0], 4), round(p['n'][1], 4)],
                        z0=round(p['z0'], 3), z1=round(p['z1'], 3), length=round(L, 3), area=0, net=0,
                        floor=(nb or {}).get('floor') or 'ground', room=(nb or {}).get('room'), roomType=(nb or {}).get('roomType'),
                        type=(nb or {}).get('type') or 'exterior', defaultType=(nb or {}).get('type') or 'exterior', overridden=False,
                        typeReason='מילוי תצוגה – סדק של מ"מ בין שני משטחים (לא בכמויות)', source='tools/finishes/flatten.py fillers()'))
    for i, f in enumerate(out): f['key'] = f"{f['floor']}|fill#{i + 1}"
    return out


def remaining_steps(G, off, tol, minstep=0.003):
    """pairs of touching parallel drawn sheets (along the wall or one above the other) whose final planes still differ by
    minstep..tol – the steps the one-plane rule did not take (span limit, different surfaces)"""
    T = {t['id']: t for t in G['TYPES']['types']}
    drawn_t = lambda s: T.get(s.get('type'), {}).get('drawn', True) is not False
    V = []
    def add(s, t=None):
        if s.get('hidden') or not drawn_t(t or s): return
        if math.dist(s['a'], s['b']) < 0.02: return
        V.append(_Face(s, 'x', s['a'], s['b'], s['normal'], s['z0'], s['z1'], True, off)); V[-1].shift = s.get('shift') or 0
    for f in G['FACES']: add(f)
    for b in G['BEAMSURF']:
        for x in b['sides']: add(x, b)
    for p in G['PATCHES']:
        if p['vertical']: add(p)
    out = []
    for i, f in enumerate(V):
        for g in V[i + 1:]:
            if f.n[0] * g.n[0] + f.n[1] * g.n[1] < PAR: continue
            if max(abs(_dist(f, g.a)), abs(_dist(f, g.b))) > tol + 0.02: continue
            t0, t1 = sorted((_along(f, g.a), _along(f, g.b)))
            ov_s = min(t1, f.L) - max(t0, 0.0); ov_z = min(f.z1, g.z1) - max(f.z0, g.z0)
            if not ((ov_s > 0.01 and -0.01 < ov_z < 0.01) or (ov_z > 0.05 and -0.02 < ov_s < 0.01)): continue
            pf = f.shift; pg = g.shift + _dist(f, ((g.a[0] + g.b[0]) / 2, (g.a[1] + g.b[1]) / 2))
            d = abs(pf - pg)
            if minstep <= d <= tol:
                out.append(dict(a=f.ref.get('key') or f.ref.get('owner'), b=g.ref.get('key') or g.ref.get('owner'), step=round(d, 3),
                                at=[round(x, 2) for x in (f.b if abs(_along(f, g.a)) > abs(_along(f, g.a) - f.L) else f.a)], z=[max(f.z0, g.z0), min(f.z1, g.z1)]))
    return out


def corner_check(G, off, ov):
    """outer corners: two drawn sheets that end at the same skeleton corner must meet in front of it (their drawn ends, with
    ext + the seam overlap, reach the other sheet's plane) – else the corner of the skeleton shows in a slit. -> list"""
    T = {t['id']: t for t in G['TYPES']['types']}
    drawn_t = lambda s: T.get(s.get('type'), {}).get('drawn', True) is not False
    V = []
    def add(s, t=None):
        if s.get('hidden') or not drawn_t(t or s) or math.dist(s['a'], s['b']) < 1e-4: return
        f = _Face(s, 'x', s['a'], s['b'], s['normal'], s['z0'], s['z1'], True, off); f.shift = s.get('shift') or 0; V.append(f)
    for f in G['FACES']: add(f)
    for b in G['BEAMSURF']:
        for x in b['sides']: add(x, b)
    for p in G['PATCHES']:
        if p['vertical']: add(p)
    ends = defaultdict(list)
    for f in V:
        for e, p in ((0, f.a), (1, f.b)): ends[(round(p[0], 2), round(p[1], 2))].append((f, e))
    bad = []
    for k, lst in ends.items():
        for i, (f, ef_) in enumerate(lst):
            for g, eg_ in lst[i + 1:]:
                if abs(f.u[0] * g.u[0] + f.u[1] * g.u[1]) > 0.87: continue
                if min(f.z1, g.z1) - max(f.z0, g.z0) < 0.05: continue
                pf = f.a if ef_ == 0 else f.b; pg = g.a if eg_ == 0 else g.b
                if math.dist(pf, pg) > 0.002: continue
                # outer corner: each face's normal points away from the other face
                mg = ((g.a[0] + g.b[0]) / 2, (g.a[1] + g.b[1]) / 2); mf = ((f.a[0] + f.b[0]) / 2, (f.a[1] + f.b[1]) / 2)
                if _dist(f, mg) > -1e-4 or _dist(g, mf) > -1e-4: continue
                # the end of f's drawn sheet (with ext / overlap) must reach g's drawn plane, and the other way round
                e_f = max((f.ref.get('ext') or [0, 0])[ef_], ov); e_g = max((g.ref.get('ext') or [0, 0])[eg_], ov)
                need_f = g.shift + off; need_g = f.shift + off
                if e_f < need_f - 0.002 or e_g < need_g - 0.002:
                    bad.append(dict(at=[round(pf[0], 3), round(pf[1], 3)], z=[max(f.z0, g.z0), min(f.z1, g.z1)], a=f.ref.get('key'), b=g.ref.get('key'),
                                    gap=round(max(need_f - e_f, need_g - e_g), 3)))
    return bad

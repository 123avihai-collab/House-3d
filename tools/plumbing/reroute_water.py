#!/usr/bin/env python3
"""Re-route the hot / cold water of the proposal from every manifold (Avihai 09.11.2026), in data/plumbing/routes.json:

  - remove the cancelled fixtures (BS1 ground + first) and their pipes
  - manifold: one slot per fixture along its axis (slot spacing as in the proposal); the cold outlet (coldH) and the hot
    outlet (hotH) of a fixture in the same slot, slots ordered by direction so the pairs do not cross; every outlet named
    with its destination and room
  - each fixture: the SHORTEST path (diagonal allowed) in the floor fill from the manifold to the point, inside the floor
    area of that storey (no mamad, no English courtyard – not even under the concrete), around columns, concrete walls and
    beams that reach the fill level; block walls are crossed in the fill
  - hot and cold of a fixture run together, 5 cm apart (±2.5 cm off the pair's centre line), up to the point
  - pairs are routed one after another, each keeping a lane (lanePitch) beside the ones already laid; if no such path
    exists, the pair may cross them (reported)

Keeps: run ids, diameters, materials, insulation, feeds / returns / risers. Writes routes.json (+ a report to stdout).
Inputs: tools/plumbing/reroute-inputs.json.   Usage: python3 tools/plumbing/seed_routes.py --force && python3 tools/plumbing/reroute_water.py
"""
import heapq, json, math, os, sys
from shapely.geometry import Polygon, Point, LineString, MultiPolygon
from shapely.ops import unary_union, nearest_points
from shapely.prepared import prep

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
IN = {k: (v['value'] if isinstance(v, dict) and 'value' in v else v) for k, v in J('tools/plumbing/reroute-inputs.json').items() if not k.startswith('_')}
RP = os.path.join(ROOT, 'data/plumbing/routes.json')
R = json.load(open(RP, encoding='utf-8'))
H0 = J('data/site/origin.json')['H0']
FG, FF, FR, BL = J('data/structure/floor-ground.json'), J('data/structure/floor-first.json'), J('data/structure/framing.json'), J('data/architecture/blocks.json')
BG = J('data/plumbing/plan-background.json')
r3 = lambda v: round(float(v), 3)
HALF, CLR, PITCH = IN['pairSpacing_m'] / 2, IN['clearance_m'], IN['lanePitch_m']


def beam_poly(axis, w):
    (e1, n1), (e2, n2) = axis; L = math.dist((e1, n1), (e2, n2)); ux, uy = (e2 - e1) / L, (n2 - n1) / L; h = w / 2
    return Polygon([(e1 - uy * h, n1 + ux * h), (e2 - uy * h, n2 + ux * h), (e2 + uy * h, n2 - ux * h), (e1 + uy * h, n1 - ux * h)])


def region(fl):
    if fl == 'ground':   # house floor, without the tops of the basement wall around the English courtyards (concrete, no fill)
        caps = unary_union([Polygon(c['footprintITM']).buffer(0) for c in FG.get('basementWallCaps') or []])
        return unary_union([Polygon(s['footprintITM']).buffer(0) for s in FG['slab'] if s['zone'] == 'house']).difference(caps.buffer(0.005)).buffer(0)
    if fl == 'first': return unary_union([Polygon(s['footprintITM']).buffer(0) for s in FG['ceiling']['slab']])
    if fl == 'unit': return unary_union([Polygon(s['outlineITM'], s.get('holesITM') or []).buffer(0) for s in FR['slabs'] if s['id'] == 'BS1'])


def obstacles(fl, z):
    """structure that reaches the fill level z (rel): columns, concrete walls, beams; + English courtyards (any level)"""
    E = []
    def add(poly, lo, hi):
        if lo is not None and hi is not None and lo < z + 0.03 and hi > z - 0.03: E.append(poly.buffer(0))
    for F in (FG, FF):
        for w in F['walls'] + F['columns']: add(Polygon(w['footprintITM'], w.get('holesITM') or []), w['bottomRel'], w['topRel'])
        for b in F['ceiling'].get('beams') or []:
            if b.get('axisITM'): add(beam_poly(b['axisITM'], b['width_m']), b['bottomRel'], b['topRel'])
    for w in FR['basementWalls']: add(Polygon(w['footprintITM'], w.get('holesITM') or []), w['bottomRel'], w['topRel'])
    for b in FR['groundBeams']:
        if b.get('axisITM'): add(beam_poly(b['axisITM'], b['width_m']), b['bottomRel'], b['topRel'])
    for zn in FG.get('openZones') or []:
        if zn['zone'] == 'courtyard': E.append(Polygon(zn['footprintITM']).buffer(0))
    return unary_union(E)


def free_space(fl, z, extra=None, half=None):
    half = HALF if half is None else half
    reg = region(fl).buffer(-(CLR + half - HALF), join_style=2)
    obs = obstacles(fl, z).buffer(half + CLR, join_style=2)
    if extra is not None and not extra.is_empty: obs = obs.union(extra)
    return reg.difference(obs).buffer(0)


def graph_nodes(free):
    pts = []
    geoms = free.geoms if isinstance(free, MultiPolygon) else [free]
    for g in geoms:
        g = g.simplify(0.005)
        for ring in [g.exterior, *g.interiors]: pts += list(ring.coords)[:-1]
    return pts


def shortest(free, a, b):
    """visibility-graph shortest path inside `free` from a to b (both must be inside); None if none"""
    F = prep(free.buffer(1e-6)); N = [a, b] + graph_nodes(free)
    vis = lambda p, q: F.covers(LineString([p, q]))
    if vis(a, b): return [a, b]
    dist = {0: 0.0}; prev = {}; pq = [(0.0, 0)]; done = set()
    while pq:
        d, i = heapq.heappop(pq)
        if i in done: continue
        done.add(i)
        if i == 1: break
        for j in range(1, len(N)):
            if j in done or j == i: continue
            w = math.dist(N[i], N[j])
            if d + w >= dist.get(j, 1e18): continue
            if not vis(N[i], N[j]): continue
            dist[j] = d + w; prev[j] = i; heapq.heappush(pq, (d + w, j))
    if 1 not in prev: return None
    path, k = [N[1]], 1
    while k != 0: k = prev[k]; path.append(N[k])
    return path[::-1]


def into_free(free, p, maxd):
    P = Point(p)
    if free.covers(P): return p, 0.0
    q = nearest_points(free, P)[0]; d = q.distance(P)
    if d > maxd: return None, d
    # step a hair inside
    v = ((q.x - p[0]) / d, (q.y - p[1]) / d) if d else (0, 0)
    return (q.x + v[0] * 1e-4, q.y + v[1] * 1e-4), d


def offset_line(pts, off):
    if abs(off) < 1e-9 or len(pts) < 2: return list(pts)
    g = LineString(pts).offset_curve(off, join_style=2, mitre_limit=3.0)
    c = list(g.coords) if g.geom_type == 'LineString' else max(g.geoms, key=lambda x: x.length).coords
    return [tuple(x) for x in c]


def room_of(fl, E, N):
    names = set(IN['roomNames'])
    T = [t for t in BG['floors'][fl if fl != 'site' else 'ground']['texts'] if t['layer'] == 'G-ANNO-TEXT' and t['t'].replace('\n', ' ').strip() in names]
    t = min(T, key=lambda t: math.dist((t['E'], t['N']), (E, N)), default=None)
    return t['t'].replace('\n', ' ').strip() if t and math.dist((t['E'], t['N']), (E, N)) < 5 else None


def clean(V):
    return [V[0]] + [v for i, v in enumerate(V[1:], 1) if math.dist(v, V[i - 1]) > 1e-4]


def len3(V): return sum(math.dist(V[i], V[i + 1]) for i in range(len(V) - 1))


SRC = 'tools/plumbing/reroute_water.py – ניתוב מחדש לפי החלטות אביחי 09.11.2026 (tools/plumbing/reroute-inputs.json)'


def main():
    if R.get('rerouted') and '--again' not in sys.argv:
        sys.exit('routes.json was already rerouted – run tools/plumbing/seed_routes.py --force first (the routing starts from the seed)')
    report = []
    # 1. cancelled fixtures
    gone = set(IN['removeFixtures'])
    removed_runs = [r['id'] for r in R['runs'] if r.get('to') in gone or r.get('from') in gone]
    R['runs'] = [r for r in R['runs'] if r['id'] not in removed_runs]; R['nodes'] = [n for n in R['nodes'] if n['id'] not in gone]
    R.setdefault('removed', []).extend([{'id': i, 'why': 'בוטל (אביחי 09.11.2026)'} for i in sorted(gone | set(removed_runs)) if i not in {x['id'] for x in R.get('removed', [])}])
    report.append(f'removed fixtures {sorted(gone)} + runs {removed_runs}')
    # the consultant's branches of a cancelled fixture (drain) are superseded too (hidden as "replaced by the proposal")
    NET = J('data/plumbing/network.json')
    cons = [r['id'] for r in NET['runs'] if r.get('from') in gone or r.get('to') in gone]
    R['superseded']['runs'] = sorted(set(R['superseded']['runs']) | set(cons)); report.append(f'consultant runs superseded: {cons}')
    SHAFT = J('data/plumbing/proposal.json')['shaft']['inner']
    inlet = lambda m: (m['E'] - m['axis'][0] * 0.35, m['N'] - m['axis'][1] * 0.35)     # feed end of a manifold (as in propose.py)
    outlet = lambda m: (m['E'] + m['axis'][0] * 0.35, m['N'] + m['axis'][1] * 0.35)    # far end (recirculation)
    # 2. secondary manifolds: a new manifold at the shaft takes fixtures from another one + its own short feeds
    for sm in IN.get('subManifolds') or []:
        ref = next(n for n in R['nodes'] if n['id'] == sm['placementLike']); src = next(n for n in R['nodes'] if n['id'] == sm['takesFrom'])
        m = {'id': sm['id'], 'kind': 'manifold', 'floor': sm['floor'], 'E': ref['E'], 'N': ref['N'], 'H': src['H'], 'title': sm['title'], 'axis': ref['axis'], 'face': ref['face'],
             'coldH': ref['coldH'], 'hotH': ref['hotH'], 'hotPending': False, 'outlets': {'cold': [], 'hot': []}, 'status': 'proposal',
             'source': f"tools/plumbing/reroute-inputs.json subManifolds – מיקום בתוכנית כמו {ref['id']} (ליד הפיר), מפלס הרצפה כמו {src['id']}"}
        R['nodes'].insert(next(j for j, x in enumerate(R['nodes']) if x['id'] == src['id']), m)
        for r in R['runs']:
            if r.get('from') == src['id'] and r.get('to') in sm['fixtures']: r['from'] = m['id']
        c, hs, hr = SHAFT['cold'], SHAFT['hotSupply'], SHAFT['hotReturn']; zf = m['H']; i_, o_ = inlet(m), outlet(m); tag = sm['id'].split('-', 1)[1].upper()
        def add(rid, system, D, V, frm, to, note, insul=None):
            V = clean(V); rec = {'id': rid, 'kind': 'run', 'system': system, 'floor': sm['floor'], 'D_mm': D, 'material': 'PEX', 'from': frm, 'to': to,
                                 'vertices': [[r3(a), r3(b), r3(h)] for a, b, h in V], 'length_m': r3(len3(V)), 'note': note, 'status': 'proposal', 'source': SRC}
            if insul: rec['insulation_mm'] = insul
            R['runs'].append(rec)
        add(f'FEED-{tag}', 'cold', sm['feed_D'], [(c[0], c[1], zf + 0.40), (c[0], c[1], zf + m['coldH']), (*i_, zf + m['coldH'])], 'SHAFT', m['id'], 'הזנת המחלק מעולה המים הקרים בפיר (אחרי הברז הראשי)')
        add(f'HOT-{tag}', 'hot', sm['hot_D'], [(hs[0], hs[1], zf + m['hotH']), (*i_, zf + m['hotH'])], 'HOT-GROUND', m['id'], 'הסתעפות מהאספקה החמה בפיר', sm.get('insulation_mm'))
        add(f'RET-{tag}', 'return', sm['ret_D'], [(*o_, zf + m['hotH']), (hr[0], hr[1], zf + m['hotH'] + 0.10)], m['id'], 'RET-RISER', 'חזרה מקצה המחלק לעולה הסחרור בפיר', sm.get('insulation_mm'))
        report.append(f"sub-manifold {m['id']} at {ref['id']} position, takes {sm['fixtures']} from {src['id']}")
    nodes = {n['id']: n for n in R['nodes']}
    fixt_kinds = {'wc', 'basin', 'shower', 'sink', 'washer', 'balconyTap'}
    TR = IN.get('trunk') or {}
    GAP = PITCH - 2 * HALF                      # clear distance kept between neighbouring pipe centre lines of different bundles
    for mid in IN['manifolds']:
        m = next(n for n in R['nodes'] if n['id'] == mid); fl = m['floor']; z = IN['routeLevelRel'][fl]; zabs = H0 + z
        ax, face = m['axis'], m['face']
        centre = (m['E'], m['N'])
        laid = []   # (centre line, half width) of the bundles already laid on this floor from this manifold
        # 3. trunk: the feed of this manifold from the shaft (cold + hot + return) as one bundle, laid first (it hugs the walls)
        if TR.get('manifold') == mid:
            sp = TR['spacing_m']; ids = TR['runs']; rc, rh, rr = (next(r for r in R['runs'] if r['id'] == ids[k]) for k in ('cold', 'hot', 'return'))
            r0 = rr['vertices'][-1]                                                        # top of the return riser in the shaft (as in the proposal)
            w = TR['wallOffset_m']; mp = next(n for n in R['nodes'] if n['id'] == TR['fromManifold'])   # pass-through manifold the trunk continues from
            e_ = outlet(mp); ef = (e_[0] + mp['face'][0] * w, e_[1] + mp['face'][1] * w)   # its far end; the drops are w in front of the wall plane
            hr = SHAFT['hotReturn']; zr = mp['H'] + mp['hotH'] + 0.10
            fr_ = free_space(fl, z, None, half=sp + HALF)
            i_, o_ = inlet(m), outlet(m)
            a, _ = into_free(fr_, ef, 1.0); b, _ = into_free(fr_, (i_[0] + face[0] * IN['exitDist_m'], i_[1] + face[1] * IN['exitDist_m']), 1.0)
            path = shortest(fr_, a, b) if a and b else None
            if not path: report.append(f'  !! trunk to {mid}: no path')
            else:
                laid.append((LineString(path), sp + HALF))
                Lc, Lh, Lr = offset_line(path, sp), list(path), offset_line(path, -sp)
                ib = (i_[0] - face[0] * w, i_[1] - face[1] * w); ob = (o_[0] - face[0] * w, o_[1] - face[1] * w)
                Vc = [(*e_, mp['H'] + mp['coldH']), (*ef, mp['H'] + mp['coldH']), (*ef, zabs)] + [(x, y, zabs) for x, y in Lc] + [(*i_, zabs), (*i_, m['H'] + m['coldH'])]
                Vh = [(*e_, mp['H'] + mp['hotH']), (*ef, mp['H'] + mp['hotH']), (*ef, zabs)] + [(x, y, zabs) for x, y in Lh] + [(*i_, zabs), (*i_, m['H'] + m['hotH'])]
                Vr = [(*o_, m['H'] + m['hotH']), (*ob, m['H'] + m['hotH']), (*ib, m['H'] + m['hotH']), (*ib, zabs)] + [(x, y, zabs) for x, y in Lr[::-1]] \
                     + [(*ef, zabs), (*ef, zr), (hr[0], hr[1], zr), tuple(r0)]   # up at the manifold end, along the service wall to the return riser
                rc['from'] = rh['from'] = mp['id']
                for r, V, what in ((rc, Vc, 'קר'), (rh, Vh, 'חם'), (rr, Vr, 'סחרור')):
                    V = clean(V); j = next(k for k, x in enumerate(R['runs']) if x['id'] == r['id'])
                    R['runs'][j] = {**{k2: r[k2] for k2 in r if k2 not in ('vertices', 'simplify', 'source', 'status', 'length_m', 'edited')}, 'vertices': [[r3(p), r3(q), r3(h)] for p, q, h in V],
                                    'length_m': r3(len3(V)), 'status': 'proposal', 'bundle': 'trunk-' + mid,
                                    'note': (r.get('note') or '') + f' · צרור ההזנה ({what}) במילוי ({z:+.2f}), {sp * 100:.0f} ס"מ בין צירים, מסביב לממ"ד – לא בחצר האנגלית; ממשיך מקצה {mp["id"]}', 'source': SRC}
                report.append(f'  trunk shaft -> {mid}: {LineString(path).length:.2f} m (plan)')
        mine = [r for r in R['runs'] if r.get('from') == mid and r['system'] in ('cold', 'hot') and r.get('to') in nodes and nodes[r['to']]['kind'] in fixt_kinds]
        fx = {}
        for r in mine: fx.setdefault(r['to'], {})[r['system']] = r
        free0 = free_space(fl, z)
        # first pass: free path from the manifold front to each fixture -> direction -> slot order
        exitp = (centre[0] + face[0] * IN['exitDist_m'], centre[1] + face[1] * IN['exitDist_m'])
        # the drops come down inside the wall, so a pair may leave on either side of it – the side its point is reached shorter from
        prelim = {}; fsgn = {}
        for fid in fx:
            n = nodes[fid]; b, _ = into_free(free0, (n['E'], n['N']), IN['approach_m']); best_ = None
            for sg in (1, -1):
                a, da = into_free(free0, (centre[0] + face[0] * sg * IN['exitDist_m'], centre[1] + face[1] * sg * IN['exitDist_m']), IN['approach_m'])
                pth = shortest(free0, a, b) if a and b else None
                if pth and (best_ is None or LineString(pth).length + da < best_[0] - 0.05): best_ = (LineString(pth).length + da, pth, sg)
            prelim[fid] = best_[1] if best_ else None; fsgn[fid] = best_[2] if best_ else 1
        def side(fid):
            """angular position of the pair around the manifold (from the face direction, + toward the axis), read where
            its free path leaves circles of growing radius – pairs that share the first metres are told apart further out"""
            sg = fsgn[fid]; ex = (centre[0] + face[0] * sg * IN['exitDist_m'], centre[1] + face[1] * sg * IN['exitDist_m'])
            p = prelim[fid]; L = LineString([ex] + list(p)) if p else LineString([ex, (nodes[fid]['E'], nodes[fid]['N'])])
            key = []
            for rad in (0.4, 0.8, 1.6, 3.2, 6.4, 12.8):
                hit = L.intersection(Point(ex).buffer(rad).exterior)
                q = (list(hit.geoms)[0] if hasattr(hit, 'geoms') and len(hit.geoms) else hit) if not hit.is_empty else Point(L.coords[-1])
                q = q if q.geom_type == 'Point' else Point(L.coords[-1])
                dx, dy = q.x - ex[0], q.y - ex[1]
                key.append(round(math.degrees(math.atan2(dx * ax[0] + dy * ax[1], (dx * face[0] + dy * face[1]) * sg)) / 2))   # 2° steps
            return tuple(key)
        order = sorted(fx, key=side)
        # a point on the manifold's own wall, close by: piped inside the (service) wall at outlet height – nearest one per side
        IW = IN['inWall']; inwall = {}
        for sgn in (-1, 1):
            cand = []
            for fid in fx:
                n = nodes[fid]; dx, dy = n['E'] - centre[0], n['N'] - centre[1]; off = dx * face[0] + dy * face[1]; al = dx * ax[0] + dy * ax[1]
                if abs(off) <= IW['maxOff_m'] and 0 < sgn * al <= IW['maxLen_m']: cand.append((abs(al), fid))
            if cand: inwall[min(cand)[1]] = sgn
        floor0 = [f for f in order if f not in inwall]; base_laid = list(laid)
        def lay(floor_ids):
            laid = list(base_laid); rep_ = []; floor_done = []
            order = [f for f in inwall if inwall[f] < 0] + floor_ids + [f for f in inwall if inwall[f] > 0]   # in-wall ones take the end slots
            k = len(order); s = IN['slotSpacing_m']
            slot = {fid: (centre[0] + ax[0] * (i - (k - 1) / 2) * s, centre[1] + ax[1] * (i - (k - 1) / 2) * s) for i, fid in enumerate(order)}
            # staggered exits (a comb): a pair that turns toward one end of the manifold leaves further out than the slots it passes
            exitd = {}
            for sg in (1, -1):                       # a comb on each side of the wall
                grp = [f for f in floor_ids if fsgn[f] == sg]; kf = len(grp)
                for i, fid in enumerate(grp):
                    turn = side(fid)[0]
                    exitd[fid] = IN['exitDist_m'] + PITCH * ((kf - 1 - i) if turn > 0 else i if turn < 0 else min(i, kf - 1 - i))
            kf = len(floor_ids)
            out_runs = {}
            for fid, sgn in inwall.items():
                n = nodes[fid]; st = slot[fid]
                for sysn, r in fx[fid].items():
                    hOut = m['H'] + (m['coldH'] if sysn == 'cold' else m['hotH'])
                    V = clean([(st[0], st[1], hOut), (n['E'], n['N'], hOut), (n['E'], n['N'], n['H'])])
                    out_runs[r['id']] = {**{k2: r[k2] for k2 in r if k2 not in ('vertices', 'simplify', 'source', 'status', 'length_m', 'note', 'edited')},
                                         'vertices': [[r3(a), r3(b), r3(c)] for a, b, c in V], 'length_m': r3(len3(V)), 'status': 'proposal', 'inWall': True,
                                         'pair': fid if len(fx[fid]) == 2 else None, 'note': f"בתוך הקיר / קיר השירות בגובה היציאה ({hOut - m['H']:+.2f} מעל הרצפה) – הנקודה על הקיר של המחלק", 'source': SRC}
                rep_.append(f'  {mid} -> {fid}: in the wall, {math.dist(st, (n["E"], n["N"])):.2f} m')
            # second pass: route in lanes – outer slots first (they hug the wall), toward the middle
            mid_i = (kf - 1) / 2
            for fid in sorted(floor_ids, key=lambda f: -abs(floor_ids.index(f) - mid_i)):
                n = nodes[fid]; T = (n['E'], n['N']); st = slot[fid]
                start = (st[0] + face[0] * fsgn[fid] * exitd[fid], st[1] + face[1] * fsgn[fid] * exitd[fid])
                lanes = unary_union([ln.buffer(hw + GAP + HALF - 1e-3, join_style=2) for ln, hw in laid]) if laid else None   # keep GAP between bundles
                # no lanes at the two ends of the pair themselves
                if lanes is not None: lanes = lanes.difference(Point(start).buffer(PITCH * 0.9)).difference(Point(T).buffer(IN['approach_m']))
                crossed = False; path = None
                for extra in ([lanes, None] if lanes is not None else [None]):
                    fr_ = free_space(fl, z, extra)
                    a, _ = into_free(fr_, start, IN['approach_m']); b, db = into_free(fr_, T, IN['approach_m'])
                    if a and b: path = shortest(fr_, a, b)
                    if path: crossed = False; break
                if not path: rep_.append(f'  !! {mid} -> {fid}: no path'); continue
                path = [start] + [p for p in path if math.dist(p, start) > 0.03 and math.dist(p, T) > 0.03] + [T]   # nudged ends back to the real ones (no stubs < 3 cm)
                laid.append((LineString([st] + path), HALF)); floor_done.append(fid)
                both = set(fx[fid]) == {'cold', 'hot'}
                for sysn, r in fx[fid].items():
                    off = (-HALF if sysn == 'cold' else HALF) if both else 0.0
                    line = offset_line(path, off)
                    hOut = m['H'] + (m['coldH'] if sysn == 'cold' else m['hotH'])
                    V = clean([(st[0], st[1], hOut), (st[0], st[1], zabs)] + [(x, y, zabs) for x, y in line] + [(line[-1][0], line[-1][1], n['H'])])
                    out_runs[r['id']] = {**{k2: r[k2] for k2 in r if k2 not in ('vertices', 'simplify', 'source', 'status', 'length_m', 'note', 'edited')},
                                         'vertices': [[r3(a), r3(b), r3(c)] for a, b, c in V], 'length_m': r3(len3(V)), 'status': 'proposal',
                                         'pair': fid if both else None, 'note': f"{'צמד חם/קר, 5 ס\"מ' if both else 'קר בלבד'} · הקו הקצר ביותר במילוי ({z:+.2f})" + (' · חוצה צנרת אחרת' if crossed else ''),
                                         'source': SRC}
                rep_.append(f'  {mid} -> {fid}: {LineString(path).length:.2f} m{" (crosses)" if crossed else ""}')
            mine_l = laid[len(base_laid):]
            X = [(floor_done[i], floor_done[j]) for i in range(len(mine_l)) for j in range(i + 1, len(mine_l)) if mine_l[i][0].crosses(mine_l[j][0])]
            X += [(floor_done[i], None) for i in range(len(mine_l)) for ln, _ in base_laid if mine_l[i][0].crosses(ln)]
            return out_runs, order, slot, X, rep_
        # slot order: start from the angular order, then swap the slots of pairs that cross and lay again, while it helps
        best = lay(floor0); cur = list(floor0); tried = {tuple(cur)}
        for _ in range(40):
            if not best[3]: break
            improved = False
            movers = [x for pr in best[3] for x in pr if x]
            cands = []
            for a_, b_ in best[3]:
                if b_: c_ = list(cur); ia, ib2 = c_.index(a_), c_.index(b_); c_[ia], c_[ib2] = c_[ib2], c_[ia]; cands.append(c_)
            for x in dict.fromkeys(movers):            # or move one of them to any other slot
                rest = [f for f in cur if f != x]; cands += [rest[:i] + [x] + rest[i:] for i in range(len(rest) + 1)]
            for cand in cands:
                if tuple(cand) in tried: continue
                tried.add(tuple(cand)); res = lay(cand)
                if len(res[3]) < len(best[3]): best, cur, improved = res, cand, True; break
            if not improved: break
        out_runs, order, slot, X, rep_ = best; report += rep_
        if X: report.append(f'  ! {mid}: {len(X)} crossing(s) left: {X}')
        fx_note = {a_ for a_, b_ in X} | {b_ for a_, b_ in X if b_}
        for r_ in out_runs.values():
            if r_.get('to') in fx_note and 'חוצה' not in r_['note']: r_['note'] += ' · חוצה צנרת אחרת'
        for rid, nr in out_runs.items():
            i = next(j for j, x in enumerate(R['runs']) if x['id'] == rid); R['runs'][i] = nr
        # manifold outlets: one slot per fixture, cold + hot in the same slot, named with destination + room
        mi = next(j for j, x in enumerate(R['nodes']) if x['id'] == mid)
        outl = {'cold': [], 'hot': []}
        for fid in order:
            n = nodes[fid]; room = room_of(fl, n['E'], n['N'])
            for sysn in ('cold', 'hot'):
                if sysn in fx[fid]: outl[sysn].append({'E': r3(slot[fid][0]), 'N': r3(slot[fid][1]), 'to': fid, 'D_mm': fx[fid][sysn].get('D_mm'), 'room': room, 'run': fx[fid][sysn]['id']})
        R['nodes'][mi] = {**R['nodes'][mi], 'outlets': outl, 'layout': 'slot per fixture: cold (coldH) + hot (hotH) in the same slot, ordered by direction',
                          'source': R['nodes'][mi]['source'] + ' · יציאות: tools/plumbing/reroute_water.py'}
    R['rerouted'] = {'by': 'tools/plumbing/reroute_water.py', 'inputs': 'tools/plumbing/reroute-inputs.json', 'date': '2026-11-09'}
    json.dump(R, open(RP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n'.join(report))


if __name__ == '__main__':
    main()

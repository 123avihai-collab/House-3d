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
    if fl == 'ground': return unary_union([Polygon(s['footprintITM']).buffer(0) for s in FG['slab'] if s['zone'] == 'house'])
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


def free_space(fl, z, extra=None):
    reg = region(fl).buffer(-CLR, join_style=2)
    obs = obstacles(fl, z).buffer(HALF + CLR, join_style=2)
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


def main():
    if R.get('rerouted') and '--again' not in sys.argv:
        sys.exit('routes.json was already rerouted – run tools/plumbing/seed_routes.py --force first (the routing starts from the seed)')
    runs = {r['id']: r for r in R['runs']}; nodes = {n['id']: n for n in R['nodes']}
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
    runs = {r['id']: r for r in R['runs']}
    fixt_kinds = {'wc', 'basin', 'shower', 'sink', 'washer', 'balconyTap'}
    for mid in IN['manifolds']:
        m = next(n for n in R['nodes'] if n['id'] == mid); fl = m['floor']; z = IN['routeLevelRel'][fl]; zabs = H0 + z
        ax, face = m['axis'], m['face']
        mine = [r for r in R['runs'] if r.get('from') == mid and r['system'] in ('cold', 'hot') and r.get('to') in nodes and nodes[r['to']]['kind'] in fixt_kinds]
        fx = {}
        for r in mine: fx.setdefault(r['to'], {})[r['system']] = r
        free0 = free_space(fl, z)
        centre = (m['E'], m['N'])
        # first pass: free path from the manifold front to each fixture -> direction -> slot order
        exitp = (centre[0] + face[0] * IN['exitDist_m'], centre[1] + face[1] * IN['exitDist_m'])
        prelim = {}
        for fid in fx:
            n = nodes[fid]; a, _ = into_free(free0, exitp, IN['approach_m'] + 0.5); b, _ = into_free(free0, (n['E'], n['N']), IN['approach_m'])
            p = shortest(free0, a, b) if a and b else None
            prelim[fid] = p
        def side(fid):   # where along the manifold axis the pair heads off (by its first metre)
            p = prelim[fid]; q = LineString(p).interpolate(min(1.0, LineString(p).length)) if p else Point(nodes[fid]['E'], nodes[fid]['N'])
            return (q.x - centre[0]) * ax[0] + (q.y - centre[1]) * ax[1]
        order = sorted(fx, key=side)
        k = len(order); s = IN['slotSpacing_m']
        slot = {fid: (centre[0] + ax[0] * (i - (k - 1) / 2) * s, centre[1] + ax[1] * (i - (k - 1) / 2) * s) for i, fid in enumerate(order)}
        # second pass: route in lanes, shortest first
        laid = []; out_runs = {}
        for fid in sorted(order, key=lambda f: LineString(prelim[f]).length if prelim[f] else 1e9):
            n = nodes[fid]; T = (n['E'], n['N']); st = slot[fid]
            start = (st[0] + face[0] * IN['exitDist_m'], st[1] + face[1] * IN['exitDist_m'])
            lanes = unary_union(laid).buffer(PITCH - 1e-3, join_style=2) if laid else None   # a new centre line keeps ≥ PITCH from the laid ones
            # all pairs leave through the front of the manifold – no lanes there (nor at the point itself)
            if lanes is not None: lanes = lanes.difference(Point(centre).buffer(IN['manifoldZone_m'] + (k - 1) / 2 * s)).difference(Point(T).buffer(IN['approach_m']))
            crossed = False
            path = None
            for extra in ([lanes, None] if lanes is not None else [None]):
                fr_ = free_space(fl, z, extra)
                a, _ = into_free(fr_, start, IN['approach_m']); b, db = into_free(fr_, T, IN['approach_m'])
                if a and b: path = shortest(fr_, a, b)
                if path: crossed = extra is None and lanes is not None; break
            if not path: report.append(f'  !! {mid} -> {fid}: no path'); continue
            path = [start] + [p for p in path if math.dist(p, start) > 0.03 and math.dist(p, T) > 0.03] + [T]   # nudged ends back to the real ones (no stubs < 3 cm)
            laid.append(LineString(path))
            both = set(fx[fid]) == {'cold', 'hot'}
            for sysn, r in fx[fid].items():
                off = (-HALF if sysn == 'cold' else HALF) if both else 0.0
                line = offset_line(path, off)
                hOut = m['H'] + (m['coldH'] if sysn == 'cold' else m['hotH'])
                V = [(st[0], st[1], hOut), (st[0], st[1], zabs)] + [(x, y, zabs) for x, y in line] + [(line[-1][0], line[-1][1], n['H'])]
                V = [V[0]] + [v for i, v in enumerate(V[1:], 1) if math.dist(v, V[i - 1]) > 1e-4]
                L3 = sum(math.dist(V[i], V[i + 1]) for i in range(len(V) - 1))
                out_runs[r['id']] = {**{k2: r[k2] for k2 in r if k2 not in ('vertices', 'simplify', 'source', 'status', 'length_m', 'note', 'edited')},
                                     'vertices': [[r3(a), r3(b), r3(c)] for a, b, c in V], 'length_m': r3(L3), 'status': 'proposal',
                                     'pair': fid if both else None, 'note': f"{'צמד חם/קר, 5 ס\"מ' if both else 'קר בלבד'} · הקו הקצר ביותר במילוי ({z:+.2f})" + (' · חוצה צנרת אחרת' if crossed else ''),
                                     'source': 'tools/plumbing/reroute_water.py – ניתוב מחדש לפי החלטות אביחי 09.11.2026 (tools/plumbing/reroute-inputs.json)'}
            report.append(f'  {mid} -> {fid}: {LineString(path).length:.2f} m{" (crosses)" if crossed else ""}')
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

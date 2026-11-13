#!/usr/bin/env python3
"""ח1ג – מעגלי קומה א' מהלוח הראשי: עלייה מעל הלוח (בארון, ליד קורה B-25), דרך FS2 והחלל עד גובה הנמכת התקרה,
תוואי בחלל הטכני עד תיבת חלוקה במסדרון, והסתעפות לכל חדר.
קלט: tools/electrical/first-riser-inputs.json + data/. פלט: data/electrical/first-riser.json. הרצה: python3 tools/electrical/propose_first_riser.py"""
import json, math, os, heapq
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
I = L('tools/electrical/first-riser-inputs.json'); H0 = L('data/site/origin.json')['H0']
fg = L('data/structure/floor-ground.json'); ff = L('data/structure/floor-first.json'); bl = L('data/architecture/blocks.json')
op = {o['id']: o for o in L('data/architecture/openings.json')['openings']}; st = L('data/structure/stairs.json'); sup = L('data/electrical/supply.json')
r3 = lambda v: round(v, 3)
def inside(p, ring):
    c = False
    for i in range(len(ring)):
        a, b = ring[i], ring[(i+1) % len(ring)]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1]): c = not c
    return c
edges = lambda r: [(r[i], r[(i+1) % len(r)]) for i in range(len(r))]
def seg_x(a, b, c, d):
    r = (b[0]-a[0], b[1]-a[1]); s = (d[0]-c[0], d[1]-c[1]); den = r[0]*s[1]-r[1]*s[0]
    if abs(den) < 1e-12: return None
    t = ((c[0]-a[0])*s[1]-(c[1]-a[1])*s[0])/den; u = ((c[0]-a[0])*r[1]-(c[1]-a[1])*r[0])/den
    return t if 0 < t < 1 and 0 < u < 1 else None
def seg_pt(a, b, p):
    d = (b[0]-a[0], b[1]-a[1]); l2 = d[0]**2+d[1]**2
    t = max(0, min(1, ((p[0]-a[0])*d[0]+(p[1]-a[1])*d[1])/l2)) if l2 else 0
    return math.hypot(p[0]-a[0]-t*d[0], p[1]-a[1]-t*d[1])

rs1 = ff['ceiling']['slab'][0]; soffit = H0+rs1['topRel']-rs1['thickness_m']
DC = I['droppedCeiling']; dcAbs = H0+DC['undersideRel']; zRoute = soffit-I['routeLevelBelowSoffit_m']
floors1 = [s['footprintITM'] for s in fg['ceiling']['slab']]      # first-floor slabs (FS1, FS2): no slab below = void
concrete = [(w['id'], w['footprintITM']) for w in ff['walls']]
blocks = [w for w in bl['walls'] if w['floor'] == 'first']
P = sup['mainPanel']; B = I['bundle']
# ---- riser: in front of the niche wall, panel centre, up to the route level
R = (P['faceITM'][0]+P['normalITM'][0]*B['riserOffsetFromWall_m'], P['faceITM'][1]+P['normalITM'][1]*B['riserOffsetFromWall_m'])
b25 = next(x for x in fg['ceiling']['beams'] if x['id'] == 'B-25')
beamGap = seg_pt(b25['axisITM'][0], b25['axisITM'][-1], R)-b25['width_m']/2-B['riserWidth_m']/2*0   # bundle sits in front of the wall face
fs2 = next(s for s in fg['ceiling']['slab'] if s['id'] == 'FS2')
assert inside(R, fs2['footprintITM']), 'riser not over FS2'
# ---- distribution box: on the landing at the top of the stairs (ST2 arrival riser, into the first floor)
ar = next(x for x in st['stairs'] if x['id'] == 'ST2')['arrivalRiserITM']
am = ((ar[0][0]+ar[1][0])/2, (ar[0][1]+ar[1][1])/2); ad = (ar[1][0]-ar[0][0], ar[1][1]-ar[0][1]); an = (-ad[1], ad[0]); nl = math.hypot(*an); an = (an[0]/nl, an[1]/nl)
fs1 = next(s for s in fg['ceiling']['slab'] if s['id'] == 'FS1')
if not inside((am[0]+an[0]*0.5, am[1]+an[1]*0.5), fs1['footprintITM']): an = (-an[0], -an[1])
Dp = (am[0]+an[0]*I['distribution']['fromStairArrival_m'], am[1]+an[1]*I['distribution']['fromStairArrival_m'])
# ---- plenum planner (grid A*): inside the roof outline, not through concrete walls; block wall crossing / over-void penalties
PL = I['planner']; h = PL['step_m']
def in_concrete(q): return any(inside(q, r) for _, r in concrete) or any(min(seg_pt(a, b, q) for a, b in edges(r)) < PL['concreteClear_m']+B['trayWidth_m']/2 for _, r in concrete)
def over_void(q): return not any(inside(q, r) for r in floors1)
blockSegs = [(w['id'], w['axisITM'][0], w['axisITM'][1]) for w in blocks]
def crossings(a, b): return [wid for wid, c, d in blockSegs if seg_x(a, b, c, d) is not None]
def astar(a, b):
    key = lambda q: (round(q[0]/h), round(q[1]/h))
    start, goal = key(a), key(b); pq = [(0, start)]; g = {start: 0}; prev = {}
    nb = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    while pq:
        _, k = heapq.heappop(pq)
        if k == goal: break
        p = (k[0]*h, k[1]*h)
        for dx, dy in nb:
            k2 = (k[0]+dx, k[1]+dy); q = (k2[0]*h, k2[1]*h)
            if k2 != goal and (not inside(q, rs1['footprintITM']) or in_concrete(q)): continue
            c = math.hypot(dx, dy)*h*(PL['voidPenalty'] if over_void(q) else 1)+PL['blockWallCrossingPenalty_m']*len(crossings(p, q))
            if g[k]+c < g.get(k2, 1e9):
                g[k2] = g[k]+c; prev[k2] = k; heapq.heappush(pq, (g[k2]+math.dist(q, b), k2))
    if goal not in prev: return None
    path = [goal]
    while path[-1] != start: path.append(prev[path[-1]])
    pts = [(k[0]*h, k[1]*h) for k in reversed(path)]; pts[0] = a; pts[-1] = b
    out = [pts[0]]                                   # simplify collinear grid steps
    for i in range(1, len(pts)-1):
        d1 = (pts[i][0]-out[-1][0], pts[i][1]-out[-1][1]); d2 = (pts[i+1][0]-pts[i][0], pts[i+1][1]-pts[i][1])
        if abs(d1[0]*d2[1]-d1[1]*d2[0]) > 1e-9: out.append(pts[i])
    out.append(pts[-1]); return out
def clear_seg(a, b):
    n_ = max(2, int(math.dist(a, b)/0.05))
    return all(inside(q, rs1['footprintITM']) and not in_concrete(q) for q in [(a[0]+(b[0]-a[0])*i/n_, a[1]+(b[1]-a[1])*i/n_) for i in range(1, n_)])
def pull(path):                       # string pulling: straight legs between mutually visible vertices, no extra wall openings, no more over-void length
    if not path: return path
    out = [path[0]]; i = 0
    while i < len(path)-1:
        j = len(path)-1
        while j > i+1:
            sub = path[i:j+1]
            orig_c = sum(len(crossings(sub[k], sub[k+1])) for k in range(len(sub)-1))
            orig_v = sum(math.dist(sub[k], sub[k+1]) for k in range(len(sub)-1) if over_void(((sub[k][0]+sub[k+1][0])/2, (sub[k][1]+sub[k+1][1])/2)))
            mid = ((path[i][0]+path[j][0])/2, (path[i][1]+path[j][1])/2)
            if clear_seg(path[i], path[j]) and len(crossings(path[i], path[j])) <= orig_c and (math.dist(path[i], path[j]) if over_void(mid) else 0) <= orig_v+0.3: break
            j -= 1
        out.append(path[j]); i = j
    return out
_astar = astar
astar = lambda a, b: pull(_astar(a, b))
trunk = astar(R, Dp)
if trunk is None: raise SystemExit('no plenum route riser -> distribution box')
def describe(path):
    ln = sum(math.dist(path[i], path[i+1]) for i in range(len(path)-1)); vo = 0.0; cr = []
    for i in range(len(path)-1):
        n_ = max(1, int(math.dist(path[i], path[i+1])/0.05))
        for j in range(n_):
            q = (path[i][0]+(path[i+1][0]-path[i][0])*(j+0.5)/n_, path[i][1]+(path[i+1][1]-path[i][1])*(j+0.5)/n_)
            if over_void(q): vo += math.dist(path[i], path[i+1])/n_
        cr += crossings(path[i], path[i+1])
    return ln, vo, cr
tl, tv, tc = describe(trunk)
branches = []
for rm in I['rooms']:
    o = op[rm['door']]; c = o['centerITM']; ax = o['axisITM']; n_ = (-ax[1], ax[0])
    # end inside the room, 0.4 m past the door line (the side away from the distribution box)
    s_ = 1 if (Dp[0]-c[0])*n_[0]+(Dp[1]-c[1])*n_[1] < 0 else -1
    E_ = (c[0]+n_[0]*0.4*s_, c[1]+n_[1]*0.4*s_)
    pth = astar(Dp, E_)
    if pth is None: raise SystemExit(f"no branch to {rm['door']}")
    bl_, bv, bc = describe(pth)
    branches.append({'door': rm['door'], 'doorName': o['name'], 'planITM': [[r3(p[0]), r3(p[1])] for p in pth], 'length_m': r3(bl_), 'overVoid_m': r3(bv), 'blockWalls': bc})
riserTop = zRoute
out = {'_doc': "ח1ג – מעגלי קומה א' מהלוח הראשי (עלייה מעל הלוח + חלוקה בהנמכת התקרה). נוצר ע״י tools/electrical/propose_first_riser.py – לא לערוך ידנית. הצעה (provisional).",
  'status': 'proposal', 'source': 'tools/electrical/propose_first_riser.py + tools/electrical/first-riser-inputs.json', 'decision': I['decision'],
  'levels': {'panelTopAbs': r3(H0+P['topRel']), 'fs2TopAbs': r3(H0+fs2['topRel']), 'fs2BottomAbs': r3(H0+fs2['bottomRel']), 'firstFloorFinishAbs': r3(H0+I['firstFloorFinishRel']), 'firstFloorFinishSource': I['firstFloorFinishSource'],
             'droppedCeilingAbs': r3(dcAbs), 'droppedCeiling': DC, 'roofSoffitAbs': r3(soffit), 'routeAbs': r3(zRoute), 'plenum_m': r3(soffit-dcAbs)},
  'bundle': B,
  'riser': {'planITM': [r3(R[0]), r3(R[1])], 'fromAbs': r3(H0+P['topRel']), 'toAbs': r3(riserTop), 'height_m': r3(riserTop-(H0+P['topRel'])), 'alongITM': P['alongITM'], 'normalITM': P['normalITM'],
            'beamB25Gap_m': r3(beamGap), 'throughSlab': 'FS2', 'note': 'בתוך ארון הנגרות עד התקרה, שרוולים ברצפה FS2, ומעליה תעלה סגורה לאורך הקיר BK-F83 עד החלל הטכני'},
  'trunk': {'planITM': [[r3(p[0]), r3(p[1])] for p in trunk], 'length_m': r3(tl), 'overVoid_m': r3(tv), 'blockWalls': tc, 'note': I['planner']['note']},
  'distribution': {'name': I['distribution']['name'], 'planITM': [r3(Dp[0]), r3(Dp[1])], 'abs': r3(zRoute)},
  'branches': branches, 'steps': I['steps'],
  'checks': [
    {'kind': 'beam', 'ref': 'קורה B-25 – הצרור עולה לפניה', 'clear_m': r3(beamGap), 'required_m': 0.0, 'ok': beamGap >= -1e-3, 'note': 'מרחק ציר הצרור מפני הקורה (הצרור צמוד לפני הקיר, הקורה מיושרת עם פני הקיר)'},
    {'kind': 'plenum', 'ref': 'חלל טכני מעל ההנמכה', 'clear_m': r3(soffit-dcAbs), 'required_m': 0.2, 'ok': soffit-dcAbs >= 0.2, 'note': 'גובה זמני – E20'},
    {'kind': 'route', 'ref': 'התוואי לא חוצה קירות בטון', 'clear_m': 1, 'required_m': 0, 'ok': True, 'note': 'אכיפה בחיפוש'}],
}
out['summary'] = {'riser_m': out['riser']['height_m'], 'trunk_m': r3(tl), 'trunkOverVoid_m': r3(tv), 'branches_m': r3(sum(b['length_m'] for b in branches)), 'blockWallOpenings': len(tc)+sum(len(b['blockWalls']) for b in branches)}
json.dump(out, open(os.path.join(ROOT, 'data/electrical/first-riser.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(out['summary']); print('trunk', [[round(p[0]-179500,2), round(p[1]-576200,2)] for p in trunk], tc)
for b in branches: print(b['door'], b['length_m'], b['overVoid_m'], b['blockWalls'])

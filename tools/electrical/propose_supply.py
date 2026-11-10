#!/usr/bin/env python3
"""ח1 – הצעת הזנה ראשית: ארון המונה בפילר -> תא משיכה -> קו הזנה תת-קרקעי -> לוח ראשי בנישה שבכניסה.
קלט: tools/electrical/supply-inputs.json (ערכי תכנון) + קובצי data/ (גיאומטריה ממקורות).
פלט: data/electrical/supply.json (כולל בדיקות מרווח וכיפופים).  הרצה: python3 tools/electrical/propose_supply.py"""
import json, math, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
I = L('tools/electrical/supply-inputs.json')
H0 = L('data/site/origin.json')['H0']
stairs = L('data/structure/stairs.json'); blocks = L('data/architecture/blocks.json')
basement = L('data/structure/basement.json'); framing = L('data/structure/framing.json')
piles = L('data/structure/piles.json')['piles']; perim = L('data/structure/perimeter.json')
floor = L('data/structure/floor-ground.json'); net = L('data/plumbing/network.json'); plot = L('data/site/plot-5187.json')
dev = L('data/site/development-heights.json'); openings = L('data/architecture/openings.json')['openings']
r3 = lambda v: round(v, 3)
def unit(a, b):
    d = (b[0]-a[0], b[1]-a[1]); n = math.hypot(*d); return (d[0]/n, d[1]/n)
def seg_pt(a, b, p):
    d = (b[0]-a[0], b[1]-a[1]); l2 = d[0]**2+d[1]**2
    t = max(0, min(1, ((p[0]-a[0])*d[0]+(p[1]-a[1])*d[1])/l2)) if l2 else 0
    return math.hypot(p[0]-a[0]-t*d[0], p[1]-a[1]-t*d[1])
def seg_x(a, b, c, d):
    r = (b[0]-a[0], b[1]-a[1]); s = (d[0]-c[0], d[1]-c[1]); den = r[0]*s[1]-r[1]*s[0]
    if abs(den) < 1e-12: return None
    t = ((c[0]-a[0])*s[1]-(c[1]-a[1])*s[0])/den; u = ((c[0]-a[0])*r[1]-(c[1]-a[1])*r[0])/den
    return (t, u) if 0 <= t <= 1 and 0 <= u <= 1 else None
def seg_seg(a, b, c, d):
    return 0.0 if seg_x(a, b, c, d) else min(seg_pt(a, b, c), seg_pt(a, b, d), seg_pt(c, d, a), seg_pt(c, d, b))
def inside(p, ring):
    c = False
    for i in range(len(ring)):
        a, b = ring[i], ring[(i+1) % len(ring)]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1]): c = not c
    return c
edges = lambda ring: [(ring[i], ring[(i+1) % len(ring)]) for i in range(len(ring))]
def ring_dist(p, ring): return min(seg_pt(a, b, p) for a, b in edges(ring))
def poly_gap(sq, ring):            # gap between a convex square and a ring (0 if they overlap)
    if any(inside(p, ring) for p in sq) or any(inside(p, sq) for p in ring): return 0.0
    return min(seg_seg(a, b, c, d) for a, b in edges(sq) for c, d in edges(ring))
def path_gap(path, ring):
    if any(inside(p, ring) for p in path): return 0.0
    return min(seg_seg(path[i], path[i+1], c, d) for i in range(len(path)-1) for c, d in edges(ring))

mc = I['minClear']; rC = max(c['D_mm'] for c in I['conduits'])/2000
halfB = rC+I['conduitSpacing_m']/2*(len(I['conduits'])-1)
zc = H0+I['feederCentreRel']; top = zc+rC
slabs = [s['footprintITM'] for s in floor['slab']]
pillarRings = stairs['pillar']['wallsITM']
def hull(points):
    pts = sorted(set((round(p[0], 4), round(p[1], 4)) for p in points)); cr_ = lambda o, a, b: (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo, up = [], []
    for q in pts:
        while len(lo) >= 2 and cr_(lo[-2], lo[-1], q) <= 0: lo.pop()
        lo.append(q)
    for q in reversed(pts):
        while len(up) >= 2 and cr_(up[-2], up[-1], q) <= 0: up.pop()
        up.append(q)
    return lo[:-1]+up[:-1]
pillarHull = hull(pillarRings[0])   # outer outline of the pillar (the wall ring traces the rooms as well)
PIT_MODE = os.environ.get('PIT_MODE', I['pullPit'].get('mode', 'outside'))
walls = [w['ringITM'] for w in perim['walls']]+[f['ringITM'] for f in perim['footings']]
beams = framing['groundBeams']
chambers = [n for n in net['nodes'] if n['kind'] in ('sewerChamber', 'pumpChamber', 'municipalManhole') and n.get('D_m')]
yardRuns = [r for r in net['runs'] if r['floor'] in ('site', 'ground')]
bo = basement['outlineITM']

# ---- main panel on the inner face of its niche wall
mp = I['mainPanel']; wall = next(w for w in blocks['walls'] if w['id'] == mp['hostWall'])
a, b = wall['axisITM']; u = unit(a, b); mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
door = next(o for o in openings if o['id'] == 'G01')['centerITM']
nrm = (-u[1], u[0])
if (door[0]-mid[0])*nrm[0]+(door[1]-mid[1])*nrm[1] < 0: nrm = (u[1], -u[0])
face = (mid[0]+nrm[0]*wall['thickness_m']/2, mid[1]+nrm[1]*wall['thickness_m']/2)
R = (face[0]+nrm[0]*I['riserOffsetFromWall_m'], face[1]+nrm[1]*I['riserOffsetFromWall_m'])

# ---- facade direction (B-45 = south facade beam)
b45 = next(g for g in beams if g['id'] == 'B-45')['axisITM']
fu = unit(b45[0], b45[-1]); fu = fu if fu[0] > 0 else (-fu[0], -fu[1])
fs = (fu[1], -fu[0]); fs = fs if fs[1] < 0 else (-fs[0], -fs[1])
sw = min(bo, key=lambda p: p[0])

# ---- meter cabinet: conduit enters through the back wall (pile 115 under the cabinet)
cab = stairs['pillar']['cabinet']; cr = cab['ringITM']; ce = I['cabinetEntry']
cc = (sum(p[0] for p in cr)/4, sum(p[1] for p in cr)/4)
long_ = max(edges(cr), key=lambda e: math.dist(*e)); lu = unit(*long_); lu = lu if lu[0] > 0 else (-lu[0], -lu[1])
wt = stairs['pillar']['wallThickness_m'][0]
back = max((e for e in edges(cr) if math.dist(*e) > 0.8*math.dist(*long_)), key=lambda e: e[0][1]+e[1][1])
bm = ((back[0][0]+back[1][0])/2, (back[0][1]+back[1][1])/2); nb = (-lu[1], lu[0]); nb = nb if nb[1] > 0 else (-nb[0], -nb[1])
cabR = (bm[0]+lu[0]*ce['alongBack_m']+nb[0]*(wt+ce['behindBackWall_m']), bm[1]+lu[1]*ce['alongBack_m']+nb[1]*(wt+ce['behindBackWall_m']))
zin = H0+cab['bottomRel']+ce['entryAboveCabinetBottom_m']

# ---- generic horizontal clearance of a conduit path (plan) – returns (min margin, list of (kind, ref, clear, need))
def path_checks(path, skipPillar=False):
    out = []
    for p in piles:
        d = min(seg_pt(path[i], path[i+1], (p['E'], p['N'])) for i in range(len(path)-1))-p['diameter_m']/2-halfB
        out.append(('pile', f"כלונס {p['id']}", d, mc['pile_m']))
    for n in chambers:
        d = min(seg_pt(path[i], path[i+1], (n['E'], n['N'])) for i in range(len(path)-1))-n['D_m']/2-halfB
        out.append(('chamber', n['id'], d, mc['chamber_m']))
    out.append(('basement', 'קירות המרתף (קו חוץ)', path_gap(path, bo)-halfB, I['approach']['basementClear_m']))
    out.append(('plot', 'גבול המגרש', (min(ring_dist(p, plot['ring']) for p in path) if all(inside(p, plot['ring']) for p in path) else -1), 0.1))
    return out
margin = lambda cs: min(c[2]-c[3] for c in cs)

# ---- 1. pull pit: search the open ground near the pillar
PP = I['pullPit']; Cl = PP['clear']; ho = PP['outer_m']/2
def square(c):
    return [(c[0]+fu[0]*x+fs[0]*y, c[1]+fu[1]*x+fs[1]*y) for x, y in ((-ho, -ho), (ho, -ho), (ho, ho), (-ho, ho))]
def pit_checks(c):
    sq = square(c); out = []
    for p in piles: out.append(('pile', f"כלונס {p['id']}", math.dist(c, (p['E'], p['N']))-p['diameter_m']/2-ho*math.sqrt(2) if math.dist(c, (p['E'], p['N'])) > 2 else poly_gap(sq, [(p['E']+p['diameter_m']/2*math.cos(t/8*math.pi), p['N']+p['diameter_m']/2*math.sin(t/8*math.pi)) for t in range(16)]), Cl['pile_m']))
    for n in chambers: out.append(('chamber', n['id'], math.dist(c, (n['E'], n['N']))-n['D_m']/2-ho*math.sqrt(2) if math.dist(c, (n['E'], n['N'])) > 2.5 else poly_gap(sq, [(n['E']+n['D_m']/2*math.cos(t/8*math.pi), n['N']+n['D_m']/2*math.sin(t/8*math.pi)) for t in range(16)]), Cl['chamber_m']))
    for r in yardRuns:
        pts = r['pts']; out.append(('pipe', r['id'], min(seg_seg(pts[i], pts[i+1], e0, e1) for i in range(len(pts)-1) for e0, e1 in edges(sq)) if not any(inside(q, sq) for q in pts) else 0.0, Cl['pipe_m']))
    for k, ring in enumerate(walls): out.append(('wall', (perim['walls']+perim['footings'])[k]['id'], poly_gap(sq, ring), Cl['wall_m']))
    for ring in pillarRings: out.append(('wall', 'קירות הפילר', poly_gap(sq, ring), Cl['wall_m']))
    if PIT_MODE == 'outside': out.append(('wall', 'הפילר (קו חוץ)', poly_gap(sq, pillarHull), Cl['wall_m']))
    elif not all(inside(q, pillarHull) for q in sq): out.append(('wall', 'חדר האשפה (התא כולו בתוך הפילר)', -1, 0))
    for s, ring in zip(floor['slab'], slabs): out.append(('slab', s['id'], poly_gap(sq, ring), 0.0))
    for g in beams:
        ax = g['axisITM']; out.append(('beam', g['id'], min(seg_seg(ax[i], ax[i+1], e0, e1) for i in range(len(ax)-1) for e0, e1 in edges(sq))-g['width_m']/2, Cl['beam_m']))
    out.append(('plot', 'גבול המגרש', min(ring_dist(q, plot['ring']) for q in sq) if all(inside(q, plot['ring']) for q in sq) else -1, Cl['plot_m']))
    return out
S = PP['search']; best = None
nE = int(round((S['E'][1]-S['E'][0])/S['step_m'])); nN = int(round((S['N'][1]-S['N'][0])/S['step_m']))
for i in range(nE+1):
    for j in range(nN+1):
        c = (S['E'][0]+i*S['step_m'], S['N'][0]+j*S['step_m'])
        if not inside(c, plot['ring']): continue
        cs = pit_checks(c)
        if any(x[0] == 'slab' and x[2] <= 0 for x in cs): continue
        cs = [x for x in cs if x[0] != 'slab']
        m = margin(cs)
        if m < 0: continue
        cs2 = path_checks([cabR, c])
        m2 = margin(cs2)
        if m2 < 0: continue
        score = min(m, m2)-0.05*math.dist(c, cabR)
        if not best or score > best[0]: best = (score, c, cs, cs2)
if not best: raise SystemExit('no feasible pull-pit location')
_, pit, pitCs, legCs = best

# ---- 2. pit -> straight leg parallel to the facade -> diagonal to the riser
A_ = I['approach']; bestA = None
def turn(a, b, c):
    v1 = (b[0]-a[0], b[1]-a[1]); v2 = (c[0]-b[0], c[1]-b[1]); n1 = math.hypot(*v1); n2 = math.hypot(*v2)
    if n1 < 1e-6 or n2 < 1e-6: return 0.0
    return math.degrees(math.acos(max(-1, min(1, (v1[0]*v2[0]+v1[1]*v2[1])/n1/n2))))
sR = (R[0]-pit[0])*fu[0]+(R[1]-pit[1])*fu[1]
for k in range(int(round((A_['search_m'][1]-A_['search_m'][0])/A_['step_m']))+1):
    ds = A_['search_m'][0]+k*A_['step_m']
    for off10 in range(int(A_['corridorOffset_m'][0]*10), int(A_['corridorOffset_m'][1]*10)+1):
        off = off10/10
        # corridor line: offset 'off' south of the basement SW corner line
        base = (sw[0]+fs[0]*off, sw[1]+fs[1]*off)
        tPit = (pit[0]-base[0])*fs[0]+(pit[1]-base[1])*fs[1]   # pit distance from corridor line
        J = (pit[0]-fs[0]*tPit, pit[1]-fs[1]*tPit)              # pit projected on the corridor
        A = (J[0]+fu[0]*(sR+ds), J[1]+fu[1]*(sR+ds))
        path = [pit, J, A, R] if math.dist(pit, J) > PP['inner_m']/2 else [pit, A, R]   # corridor through the pit: leave it straight
        cs = path_checks(path)
        m = margin(cs)
        if m < 0: continue
        bends = sum(turn(path[i-1], path[i], path[i+1]) for i in range(1, len(path)-1))+90
        cost = bends+5*sum(math.dist(path[i], path[i+1]) for i in range(len(path)-1))-20*min(m, 0.3)
        if not bestA or cost < bestA[0]: bestA = (cost, path, cs, bends)
if not bestA: raise SystemExit('no feasible approach')
_, path2, pathCs, bends2 = bestA

# ---- 3. 3D route
devZ = min(dev['spots'], key=lambda s_: math.dist((s_['E'], s_['N']), pit))
if PIT_MODE == 'trashRoom':
    pitTop = H0+stairs['pillar']['bottomRel']
    pitTopSource = f"רצפת חדר האשפה = מפלס הרחוב {pitTop:.2f} (data/structure/stairs.json pillar.bottomRel; החדר נפתח לרחוב) – זמני, פרט הפילר חסר"
else:
    pitTop = devZ['z']
    pitTopSource = f"data/site/development-heights.json – הנקודה הקרובה ({math.dist((devZ['E'], devZ['N']), pit):.2f} מ'), {devZ['z']:.2f}"
pitBottom = zc-rC-PP['sumpBelowConduit_m']
panelBottom = H0+mp['bottomRel']
pts3d = [[r3(cc[0]), r3(cc[1]), r3(zin)], [r3(cabR[0]), r3(cabR[1]), r3(zin)], [r3(cabR[0]), r3(cabR[1]), r3(zc)]] + \
        [[r3(p[0]), r3(p[1]), r3(zc)] for p in path2] + [[r3(R[0]), r3(R[1]), r3(panelBottom)]]
pitIndex = 3
def turn3(a, b, c):
    v1 = [b[i]-a[i] for i in range(3)]; v2 = [c[i]-b[i] for i in range(3)]
    n1 = math.sqrt(sum(x*x for x in v1)); n2 = math.sqrt(sum(x*x for x in v2))
    return math.degrees(math.acos(max(-1, min(1, sum(v1[i]*v2[i] for i in range(3))/n1/n2))))
pulls = []
for name, seg in (('ארון המונה ← תא המשיכה', pts3d[:pitIndex+1]), ('תא המשיכה ← לוח ראשי', pts3d[pitIndex:])):
    bd = sum(turn3(seg[i-1], seg[i], seg[i+1]) for i in range(1, len(seg)-1))
    ln = sum(math.dist(seg[i], seg[i+1]) for i in range(len(seg)-1))
    pulls.append({'name': name, 'length_m': r3(ln), 'bends_deg': round(bd, 1), 'ok': bd <= I['pullRules']['maxBendPerPull_deg']+0.5})
length = sum(math.dist(pts3d[i], pts3d[i+1]) for i in range(len(pts3d)-1))
plan = [tuple(p[:2]) for p in pts3d]; segs = [(plan[i], plan[i+1]) for i in range(len(plan)-1) if math.dist(plan[i], plan[i+1]) > 1e-6]

# ---- 4. checks (feeder)
checks = []
def chk(kind, ref, value, need, note=''):
    checks.append({'kind': kind, 'ref': ref, 'clear_m': r3(value), 'required_m': need, 'ok': value >= need-1e-6, 'note': note})
seen = set()
for kind, ref, v, need in legCs+pathCs:
    if kind in ('pile', 'chamber') and v > 1.0: continue
    key = (kind, ref)
    if key in seen:
        prev = next(c for c in checks if (c['kind'], c['ref']) == key)
        if v < prev['clear_m']: checks.remove(prev)
        else: continue
    seen.add(key)
    chk(kind, ref, v, need, {'pile': 'מרחק אופקי משפת הכלונס', 'chamber': 'מרחק אופקי מדופן השוחה', 'basement': 'מרחק אופקי מקו החוץ של קירות המרתף', 'plot': 'כל התוואי בתוך המגרש'}[kind])
for g in beams:
    ax = g['axisITM']
    if any(seg_x(s[0], s[1], ax[i], ax[i+1]) for s in segs for i in range(len(ax)-1)):
        chk('beam', g['id'], H0+g['bottomRel']-top, mc['beamVertical_m'], f"תחתית קורה {g['bottomRel']:+.2f}; ראש הצינור {top-H0:+.2f}")
for f in perim['footings']:
    ring = f['ringITM']
    if any(seg_x(s[0], s[1], c, d) for s in segs for c, d in edges(ring)) or any(inside(p, ring) for p in plan):
        chk('footing', f['id'], H0+f['bottomRel']-top, mc['beamVertical_m'], f"תחתית יסוד החומה {f['bottomRel']:+.2f}")
pb = stairs['pillar']['bottomRel']
for ring in pillarRings:
    if any(seg_x(s[0], s[1], c, d) for s in segs[1:] for c, d in edges(ring)):
        chk('footing', 'קירות הפילר', H0+pb-top, mc['beamVertical_m'], f"תחתית קירות הפילר {pb:+.2f} (זמנית – פרט הפילר חסר)")
for r in net['runs']:
    if r['system'] not in ('sewage', 'pumped', 'rain') or r.get('ILup') is None: continue
    pts = r['pts']; tot = sum(math.dist(pts[i], pts[i+1]) for i in range(len(pts)-1)); run = 0
    for i in range(len(pts)-1):
        for s in segs:
            x = seg_x(pts[i], pts[i+1], s[0], s[1])
            if x:
                il = r['ILup']+(r['ILdown']-r['ILup'])*(run+x[0]*math.dist(pts[i], pts[i+1]))/tot
                chk('pipe', r['id'], il-top, mc['pipeVertical_m'], f"ø{r['D_mm']} {r['system']}, רום תחתית בחצייה {il:.3f}; הצינור עובר מתחת")
        run += math.dist(pts[i], pts[i+1])
b49 = next(g for g in beams if g['id'] == 'B-49'); bx = b49['axisITM']
chk('beamSide', 'B-49 (מתחת לקיר הלוח)', seg_pt(bx[0], bx[-1], R)-b49['width_m']/2-rC, 0.0, 'העלייה דרך הרצפה צמודה לדופן הקורה – בלי לחדור לקורה')
for kind, ref, v, need in pitCs:
    if kind in ('pile', 'chamber', 'pipe', 'beam', 'wall') and v > 0.8: continue
    chk('pit:'+kind, ref, v, need, 'תא המשיכה – מרחק אופקי מדופן התא')
for p_ in pulls: checks.append({'kind': 'pull', 'ref': p_['name'], 'clear_m': round(I['pullRules']['maxBendPerPull_deg']-p_['bends_deg'], 1), 'required_m': 0, 'ok': p_['ok'], 'note': f"כיפופים {p_['bends_deg']}° מתוך {I['pullRules']['maxBendPerPull_deg']}° מותרים (הערך במעלות)"})

slab = next((s for s in floor['slab'] if inside(R, s['footprintITM']) and not any(inside(R, h) for h in s.get('holesITM') or [])), None)
tr = I['trench']; trBottom = zc-rC-tr['beddingBelow_m']
trSegs = []   # horizontal legs at conduit level, with the level the trench is dug from at that point (formation under a slab / pillar floor / yard)
for i in range(2, len(pts3d)-2):
    a_, b_ = pts3d[i], pts3d[i+1]
    if abs(a_[2]-zc) > 1e-3 or abs(b_[2]-zc) > 1e-3 or math.dist(a_[:2], b_[:2]) < 0.05: continue
    m_ = ((a_[0]+b_[0])/2, (a_[1]+b_[1])/2)
    sl = next((x for x in floor['slab'] if inside(m_, x['footprintITM'])), None)
    if sl: topZ, why = H0+sl['bottomRel']-0.30, f"מתחת לרצפה {sl['id']}: תחתית הרצפה {sl['bottomRel']:+.2f} פחות 0.30 (פוליביד 25 + בטון רזה 5)"
    elif inside(m_, pillarHull): topZ, why = H0+stairs['pillar']['bottomRel'], 'רצפת חדר האשפה (זמני)'
    else:
        dz = min(dev['spots'], key=lambda s_: math.dist((s_['E'], s_['N']), m_)); topZ, why = dz['z'], f"פני הפיתוח הקרובים {dz['z']:.2f}"
    trSegs.append({'from': a_[:2], 'to': b_[:2], 'topAbs': r3(topZ), 'depth_m': r3(topZ-trBottom), 'topRule': why})
out = {
  '_doc': 'ח1 – הצעת הזנה ראשית (חשמל). נוצר ע"י tools/electrical/propose_supply.py – לא לערוך ידנית. כל הערכים הצעת תכנון (provisional) עד אישור אביחי.',
  'status': 'proposal', 'source': 'tools/electrical/propose_supply.py + tools/electrical/supply-inputs.json',
  'connection': I['connection'],
  'meterCabinet': {'id': 'MC', 'name': 'ארון מונה בפילר (חברת החשמל)', 'ringITM': cr, 'bottomRel': cab['bottomRel'], 'topRel': cab['topRel'], 'status': cab['status'],
                   'note': 'מיקום הארון מתוכנית הפיתוח; מידות הארון ופרט היסוד חסרים (open-issues #64, E8)', 'source': 'data/structure/stairs.json pillar.cabinet'},
  'mainPanel': {'id': mp['id'], 'name': 'לוח ראשי', 'hostWall': mp['hostWall'], 'faceITM': [r3(face[0]), r3(face[1])], 'alongITM': [r3(u[0]), r3(u[1])], 'normalITM': [r3(nrm[0]), r3(nrm[1])],
                'width_m': mp['width_m'], 'height_m': mp['height_m'], 'depth_m': mp['depth_m'], 'bottomRel': mp['bottomRel'], 'topRel': r3(mp['bottomRel']+mp['height_m']),
                'wallClearLength_m': wall['length_m'], 'wallThickness_m': wall['thickness_m'], 'status': 'provisional', 'decision': mp['decision'], 'note': mp['note'],
                'source': f"מיקום: החלטת אביחי 10.11.2026 (אושר); קיר: data/architecture/blocks.json {mp['hostWall']}; מידות: הנחת תכנון"},
  'pullPit': {'id': 'EP-1', 'name': PP['name'], 'centreITM': [r3(pit[0]), r3(pit[1])], 'alongITM': [r3(fu[0]), r3(fu[1])], 'outer_m': PP['outer_m'], 'inner_m': PP['inner_m'],
              'topAbs': r3(pitTop), 'bottomAbs': r3(pitBottom), 'depth_m': r3(pitTop-pitBottom), 'topSource': pitTopSource,
              'coverClass': PP['coverClass'], 'mode': PIT_MODE, 'location': 'רצפת חדר האשפה בפילר' if PIT_MODE == 'trashRoom' else 'שטח פתוח ליד הפילר', 'material': PP['material'], 'status': 'provisional', 'note': PP['note']},
  'feeder': {'id': 'FD-MAIN', 'name': 'קו הזנה ראשי: ארון מונה → תא משיכה → לוח ראשי', 'cable': I['cable'], 'conduits': I['conduits'], 'conduitSpacing_m': I['conduitSpacing_m'], 'pullWire': I['pullWire'],
             'pts3d': pts3d, 'pitIndex': pitIndex, 'centreRel': I['feederCentreRel'], 'levelRule': I['feederLevelRule'], 'length_m': r3(length), 'cableLength_m': r3(length+mp['height_m']+1.5+1.0),
             'cableLengthNote': 'אורך התוואי + גובה הלוח + 1.5 מ\' קצוות בארון + 1 מ\' לולאה בתא המשיכה', 'pulls': pulls, 'throughSlab': slab and slab['id'], 'status': 'provisional',
             'pillarEnd': {'points': [0, 1, 2], 'status': 'provisional', 'note': ce['note']},
             'source': 'tools/electrical/propose_supply.py (הנחת תכנון; מכשולים מ-data/structure, data/plumbing)'},
  'trench': {'segments': trSegs, 'width_m': tr['width_m'], 'bottomAbs': r3(trBottom), 'sandTopAbs': r3(zc+rC+tr['sandAbove_m']), 'warningTapeAbs': r3(zc+rC+tr['warningTapeAbove_m']), 'note': tr['note'], 'status': 'provisional'},
  'sleeves': [
    {'id': 'ES-1', 'through': f"רצפת הקרקע {slab['id'] if slab else '?'} (תלויה) – עלייה ללוח הראשי", 'at': [r3(R[0]), r3(R[1]), r3(H0+(slab['topRel'] if slab else 0))], 'axis': 'v',
     'count': len(I['conduits']), 'sleeveD_mm': 110, 'note': 'שרוול לכל צינור, לפני יציקת הרצפה; צמוד לדופן קורה B-49 – לאישור הקונסטרוקטור. רפיון בצינור בגובה ארגזי ההפרדה', 'status': 'provisional', 'step': 'groundSlab'},
    {'id': 'ES-2', 'through': 'הקיר האחורי של ארון המונה בפילר (מחדר האשפה)', 'at': [r3((cc[0]+cabR[0])/2), r3((cc[1]+cabR[1])/2), r3(zin)], 'axis': 'h',
     'count': len(I['conduits']), 'sleeveD_mm': 110, 'note': ce['note'], 'status': 'provisional', 'step': 'perimeterWalls'}],
  'steps': I['steps'],
  'checks': checks, 'summary': {'length_m': r3(length), 'checks': len(checks), 'failed': sum(1 for c in checks if not c['ok']), 'bendsTotal_deg': round(sum(p_['bends_deg'] for p_ in pulls), 1)},
}
json.dump(out, open(os.path.join(ROOT, 'data/electrical/supply.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if __name__ == '__main__':
    print('summary', out['summary']); print('pit', out['pullPit']['centreITM'], 'depth', out['pullPit']['depth_m'], 'top', pitTop); print('pulls', pulls)
    for c in checks[:0]: print(' ', 'OK ' if c['ok'] else 'XX ', c['kind'], c['ref'], c['clear_m'], '/', c['required_m'])

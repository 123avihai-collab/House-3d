#!/usr/bin/env python3
"""ח1ב – לוח לכל יחידת דיור במרתף: מיקום הלוח ליד פתח הכניסה, צנרת הזנה ביציקת רצפת הקרקע מהלוח הראשי, ירידה ללוח.
קלט: tools/electrical/units-inputs.json + data/ (גיאומטריה) + data/electrical/supply.json (הלוח הראשי).
פלט: data/electrical/units.json.  הרצה: python3 tools/electrical/propose_units.py"""
import json, math, os, heapq
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
I = L('tools/electrical/units-inputs.json'); H0 = L('data/site/origin.json')['H0']
fg = L('data/structure/floor-ground.json'); fr = L('data/structure/framing.json'); bs = L('data/structure/basement.json')
op = {o['id']: o for o in L('data/architecture/openings.json')['openings']}
fx = L('tools/plumbing/proposal-inputs.json')['unitFixtures']; sup = L('data/electrical/supply.json')
r3 = lambda v: round(v, 3)
def inside(p, ring):
    c = False
    for i in range(len(ring)):
        a, b = ring[i], ring[(i+1) % len(ring)]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1]): c = not c
    return c
edges = lambda r: [(r[i], r[(i+1) % len(r)]) for i in range(len(r))]
def seg_pt(a, b, p):
    d = (b[0]-a[0], b[1]-a[1]); l2 = d[0]**2+d[1]**2
    t = max(0, min(1, ((p[0]-a[0])*d[0]+(p[1]-a[1])*d[1])/l2)) if l2 else 0
    return math.hypot(p[0]-a[0]-t*d[0], p[1]-a[1]-t*d[1])
def seg_x(a, b, c, d):
    r = (b[0]-a[0], b[1]-a[1]); s = (d[0]-c[0], d[1]-c[1]); den = r[0]*s[1]-r[1]*s[0]
    if abs(den) < 1e-12: return False
    t = ((c[0]-a[0])*s[1]-(c[1]-a[1])*s[0])/den; u = ((c[0]-a[0])*r[1]-(c[1]-a[1])*r[0])/den
    return 0 < t < 1 and 0 < u < 1
def offset_ring(ring, d):   # outward offset of a polygon by d (miter, convex-ish rings) – used for obstacle buffers
    n = len(ring); area = sum(ring[i][0]*ring[(i+1) % n][1]-ring[(i+1) % n][0]*ring[i][1] for i in range(n))/2
    sgn = 1 if area > 0 else -1; out = []
    for i in range(n):
        p0, p1, p2 = ring[i-1], ring[i], ring[(i+1) % n]
        def nrm(a, b):
            dx, dy = b[0]-a[0], b[1]-a[1]; l = math.hypot(dx, dy) or 1; return (sgn*dy/l, -sgn*dx/l)
        n1, n2 = nrm(p0, p1), nrm(p1, p2); m = (n1[0]+n2[0], n1[1]+n2[1]); ml = math.hypot(*m) or 1
        cos = max(0.3, (n1[0]*n2[0]+n1[1]*n2[1]+1)/2)**0.5
        out.append((p1[0]+m[0]/ml*d/cos, p1[1]+m[1]/ml*d/cos))
    return out

gs1 = next(s for s in fg['slab'] if s['id'] == I['slabRoute']['inSlab'])
soffit = H0+gs1['bottomRel']; zSlab = soffit+I['slabRoute']['coverFromSoffit_m']+I['feeder']['conduitD_mm']/2000
floorU = H0-2.60
buf = I['slabRoute']['obstacleBuffer_m']
obst = [(z['label'], z['footprintITM']) for z in fg['openZones']]+[(s['zoneLabel'], s['footprintITM']) for s in fg['slab'] if s['id'] == 'GS7']
obst += [('פתח ברצפה', h) for h in (gs1.get('holesITM') or [])]
obstB = [(n, offset_ring(r, buf)) for n, r in obst]
def free_seg(a, b):
    if not inside(((a[0]+b[0])/2, (a[1]+b[1])/2), gs1['footprintITM']): return False
    for _, r in obstB:
        if any(seg_x(a, b, c, d) for c, d in edges(r)) or inside(((a[0]+b[0])/2, (a[1]+b[1])/2), r): return False
    return True
def route(a, b):           # shortest path in the slab around the buffered obstacles (visibility graph)
    nodes = [a, b]+[p for _, r in obstB for p in r if inside(p, gs1['footprintITM']) and not any(inside(p, rr) for _, rr in obstB if rr is not r)]
    dist = {0: 0}; prev = {}; pq = [(0, 0)]
    while pq:
        d, i = heapq.heappop(pq)
        if i == 1: break
        if d > dist.get(i, 1e9): continue
        for j in range(len(nodes)):
            if j == i: continue
            if free_seg(nodes[i], nodes[j]):
                nd = d+math.dist(nodes[i], nodes[j])
                if nd < dist.get(j, 1e9): dist[j] = nd; prev[j] = i; heapq.heappush(pq, (nd, j))
    if 1 not in prev: return None
    path = [1]
    while path[-1] != 0: path.append(prev[path[-1]])
    return [nodes[i] for i in reversed(path)]

P = I['panel']; mdb = sup['mainPanel']
mdbOut = (mdb['faceITM'][0]+mdb['normalITM'][0]*0.1+mdb['alongITM'][0]*0.25, mdb['faceITM'][1]+mdb['normalITM'][1]*0.1+mdb['alongITM'][1]*0.25)
units = []; checks = []
def chk(kind, ref, v, need, note=''): checks.append({'kind': kind, 'ref': ref, 'clear_m': r3(v), 'required_m': need, 'ok': v >= need-1e-6, 'note': note})
for k, U in enumerate(I['units']):
    o = op[U['door']]; c = o['centerITM']; ax = o['axisITM']
    cen = (sum(p[1] for p in fx[U['id']])/len(fx[U['id']]), sum(p[2] for p in fx[U['id']])/len(fx[U['id']]))
    nrm = (-ax[1], ax[0])
    if (cen[0]-c[0])*nrm[0]+(cen[1]-c[1])*nrm[1] < 0: nrm = (-nrm[0], -nrm[1])
    # wall inner face: walk from the opening centre towards the unit until leaving the basement wall footprint
    walls = [w['footprintITM'] for w in fr['basementWalls']]
    holes = [w.get('holesITM') or [] for w in fr['basementWalls']]
    def in_wall(q): return any(inside(q, w) and not any(inside(q, h) for h in hs) for w, hs in zip(walls, holes))
    wallEdges = [e for w, hs in zip(walls, holes) for r in [w]+hs for e in edges(r)]
    # candidate spots: on the inner faces of the basement walls (the room outline = the holes of the wall footprint), near the door,
    # the whole panel width on one straight face, clear of every opening, on this unit's side
    other = [u_ for u_ in I['units'] if u_['id'] != U['id']][0]
    cenO = (sum(p[1] for p in fx[other['id']])/len(fx[other['id']]), sum(p[2] for p in fx[other['id']])/len(fx[other['id']]))
    unitOps = [x for x in op.values() if x['floor'] == 'unit']
    faces = [e for hs in holes for h in hs for e in edges(h)]
    best = None; hw = P['width_m']/2
    for f0, f1 in faces:
        Lf = math.dist(f0, f1)
        if Lf < P['width_m']+0.1: continue
        fu_ = ((f1[0]-f0[0])/Lf, (f1[1]-f0[1])/Lf); fn = (-fu_[1], fu_[0])
        mid_ = ((f0[0]+f1[0])/2+fn[0]*0.05, (f0[1]+f1[1])/2+fn[1]*0.05)
        if in_wall(mid_): fn = (-fn[0], -fn[1])        # normal into the room
        k_ = 0.05+hw
        while k_ <= Lf-0.05-hw:
            pc_ = (f0[0]+fu_[0]*k_, f0[1]+fu_[1]*k_)
            dd = math.dist(pc_, c)
            if 0.5 <= dd <= 2.2:
                clear = min((abs((x['centerITM'][0]-pc_[0])*fu_[0]+(x['centerITM'][1]-pc_[1])*fu_[1])-x['width_m']/2-hw
                             for x in unitOps if seg_pt(f0, f1, x['centerITM']) < 0.45), default=9)
                room = (pc_[0]+fn[0]*0.3, pc_[1]+fn[1]*0.3)
                vis = lambda q: not any(seg_x(room, q, a_, b_) for a_, b_ in wallEdges)
                dm = min((math.dist(room, (f_[1], f_[2])) for f_ in fx[U['id']] if vis((f_[1], f_[2]))), default=99)
                do = min((math.dist(room, (f_[1], f_[2])) for f_ in fx[other['id']] if vis((f_[1], f_[2]))), default=99)
                mine = dm < 99 and dm < do          # the room of this unit's fixtures (seen without crossing a concrete wall)
                if clear >= P['gapFromOpening_m'] and mine and inside(room, bs['outlineITM']) and not in_wall(room):
                    sc = dd
                    if not best or sc < best[0]: best = (sc, pc_, fu_, fn, clear)
            k_ += 0.05
    if not best: raise SystemExit(f"no wall spot for {U['panelId']}")
    _, pc, ax, nrm, clearOp = best
    sgn = 1; t = 0; okWall = okRoom = True
    chk('opening', f"{U['panelId']} – מרחק מפתח קרוב", clearOp, P['gapFromOpening_m'], f"מרחק הלוח מפתח {U['door']}: {math.dist(pc, c):.2f} מ' (מרכז למרכז)")
    chk('panelWall', f"{U['panelId']} – על קיר המרתף לכל רוחבו", 1 if okWall else -1, 0, 'הלוח כולו על קיר (לא חורג מפינה או מפתח)')
    chk('panelRoom', f"{U['panelId']} – בתוך היחידה", 1 if okRoom else -1, 0, 'צד הלוח הרחוק בתוך המרתף')
    # drop point in the slab above the panel (just off the wall face), then the slab route from the main panel
    above = (pc[0]+nrm[0]*0.08, pc[1]+nrm[1]*0.08)        # just off the wall face, over the panel
    dropP = above; soff = []                 # soffit (surface) run: list of plan points from the slab exit to above the panel
    if any(inside(dropP, r) for _, r in obstB):   # over an opening / the mamad floor: slab exit at the nearest free point by a wall,
        # then a surface run in the ceiling-wall corner along the house axes (two straight legs, hugging the walls)
        hx = ax; hy = (-ax[1], ax[0])
        def wall_d(q): return min(seg_pt(a_, b_, q) for a_, b_ in faces)
        def ok_leg(p0, p1):
            if any(seg_x(p0, p1, a_, b_) for a_, b_ in wallEdges): return False
            n_ = max(2, int(math.dist(p0, p1)/0.1))
            return all(inside(q, bs['outlineITM']) and not in_wall(q) for q in [(p0[0]+(p1[0]-p0[0])*i/n_, p0[1]+(p1[1]-p0[1])*i/n_) for i in range(n_+1)])
        bestE = None
        for i in range(-130, 131):
            for j in range(-130, 131):
                q = (above[0]+hx[0]*i*0.05+hy[0]*j*0.05, above[1]+hx[1]*i*0.05+hy[1]*j*0.05)
                if not inside(q, bs['outlineITM']) or in_wall(q) or any(inside(q, r) for _, r in obstB): continue
                if not 0.06 <= wall_d(q) <= 0.2: continue
                for corner in ((q[0]+hx[0]*((above[0]-q[0])*hx[0]+(above[1]-q[1])*hx[1]), q[1]+hx[1]*((above[0]-q[0])*hx[0]+(above[1]-q[1])*hx[1])),
                               (q[0]+hy[0]*((above[0]-q[0])*hy[0]+(above[1]-q[1])*hy[1]), q[1]+hy[1]*((above[0]-q[0])*hy[0]+(above[1]-q[1])*hy[1]))):
                    if not (ok_leg(q, corner) and ok_leg(corner, above)): continue
                    legs = [q, corner, above]
                    hug = sum(wall_d(((legs[k][0]+legs[k+1][0])/2, (legs[k][1]+legs[k+1][1])/2)) for k in range(2))
                    cost = math.dist(q, corner)+math.dist(corner, above)+4*hug
                    if not bestE or cost < bestE[0]: bestE = (cost, q, corner)
        if not bestE: raise SystemExit(f"no slab exit for {U['panelId']}")
        dropP = bestE[1]; soff = [bestE[1], bestE[2], above]
    soffitRun = sum(math.dist(soff[k], soff[k+1]) for k in range(len(soff)-1)) if soff else 0.0
    inMamad = any(inside(above, r) for n, r in obst if 'ממ' in n)
    path = route(mdbOut, dropP)
    if path is None: raise SystemExit(f"no slab route to {U['panelId']}")
    ln = sum(math.dist(path[i], path[i+1]) for i in range(len(path)-1))
    for n, r in obst:
        d = min(seg_pt(path[i], path[i+1], q) for i in range(len(path)-1) for q in r)
        dd = min(min(seg_pt(a, b, q) for a, b in edges(r)) for q in path)
        chk('slabObstacle', f"{U['panelId']} – {n}", min(d, dd), buf-0.001, 'מרחק אופקי של הצינור ביציקה מפתח / ממ"ד')
    top = floorU+P['bottomAboveFloor_m']+P['height_m']
    pts3d = [[r3(mdb['faceITM'][0]+mdb['normalITM'][0]*0.1+mdb['alongITM'][0]*0.25), r3(mdb['faceITM'][1]+mdb['normalITM'][1]*0.1+mdb['alongITM'][1]*0.25), r3(H0+mdb['bottomRel'])]]
    pts3d += [[r3(p[0]), r3(p[1]), r3(zSlab)] for p in path]
    zSoff = soffit-I['feeder']['conduitD_mm']/2000-0.02
    if soffitRun > 0.01: pts3d += [[r3(q[0]), r3(q[1]), r3(zSoff)] for q in soff if math.dist(q, soff[0]) > 1e-6 or q is soff[0]]
    pts3d += [[r3(above[0]), r3(above[1]), r3(top)]]
    tot = sum(math.dist(pts3d[i], pts3d[i+1]) for i in range(len(pts3d)-1))
    units.append({'id': U['id'], 'name': U['name'], 'door': U['door'], 'doorKind': o['kind'], 'doorName': o['name'], 'doorSill_rel': o['sillRel'], 'warning': U.get('warning'),
      'panel': {'id': U['panelId'], 'name': f"לוח {U['name']}", 'centreITM': [r3(pc[0]), r3(pc[1])], 'faceITM': [r3(pc[0]), r3(pc[1])], 'alongITM': [r3(ax[0]), r3(ax[1])], 'normalITM': [r3(nrm[0]), r3(nrm[1])],
                'width_m': P['width_m'], 'height_m': P['height_m'], 'depth_m': P['depth_m'], 'bottomAbs': r3(floorU+P['bottomAboveFloor_m']), 'topAbs': r3(top), 'modules': P['modules'],
                'fromDoor_m': r3(math.dist(pc, c)), 'status': 'provisional', 'note': P['note'], 'source': f"ליד פתח {U['door']} (data/architecture/openings.json); החלטת אביחי 10.11.2026; מידות: הנחת תכנון"},
      'feeder': {'id': f"FD-{U['id'].upper()}", 'from': 'MDB', 'to': U['panelId'], 'protection': I['feeder']['protection'], 'cable': I['feeder']['cable'], 'conduit': I['feeder']['conduit'],
                 'conduitD_mm': I['feeder']['conduitD_mm'], 'pts3d': pts3d, 'slabLength_m': r3(ln), 'soffitRun_m': r3(soffitRun), 'slabExitITM': [r3(dropP[0]), r3(dropP[1])], 'length_m': r3(tot), 'cableLength_m': r3(tot+2.0), 'dropInMamadZone': inMamad,
                 'status': 'provisional', 'source': 'tools/electrical/propose_units.py'},
      'meter': {'id': U['meterId'], 'type': I['subMeter']['type'], 'where': I['subMeter']['where'], 'modules': I['subMeter']['modules']}})
out = {'_doc': 'ח1ב – לוחות יחידות הדיור במרתף. נוצר ע"י tools/electrical/propose_units.py – לא לערוך ידנית. הצעת תכנון (provisional).',
       'status': 'proposal', 'source': 'tools/electrical/propose_units.py + tools/electrical/units-inputs.json', 'decision': I['decision'],
       'units': units, 'subMeter': I['subMeter'], 'slabRoute': I['slabRoute'], 'drop': I['drop'], 'steps': I['steps'],
       'levels': {'unitFloorAbs': r3(floorU), 'slabSoffitAbs': r3(soffit), 'conduitInSlabAbs': r3(zSlab), 'source': 'רצפת המרתף ‎-2.60; תחתית GS1 (data/structure/floor-ground.json)'},
       'checks': checks, 'summary': {'checks': len(checks), 'failed': sum(1 for c in checks if not c['ok'])}}
json.dump(out, open(os.path.join(ROOT, 'data/electrical/units.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(out['summary'])
for u in units: print(u['panel']['id'], u['panel']['centreITM'], u['panel']['fromDoor_m'], 'slab', u['feeder']['slabLength_m'], 'soffit', u['feeder']['soffitRun_m'], 'total', u['feeder']['length_m'], 'mamad', u['feeder']['dropInMamadZone'], len(u['feeder']['pts3d']))
for c in checks:
    if not c['ok'] or c['clear_m'] < 0.5: print('  ', 'OK' if c['ok'] else 'XX', c['ref'], c['clear_m'])

#!/usr/bin/env python3
"""ח4 קומה א' – נקודות חשמל לכל חדר (הצעה). חדרים: חלוקת הקירות + תוויות האדריכל; נקודות לפי טבלת tools/electrical/points-first-inputs.json.
פלט: data/electrical/points-first.json. הרצה: python3 tools/electrical/propose_points_first.py"""
import json, math, os
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union, split
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
I = L('tools/electrical/points-first-inputs.json'); H0 = L('data/site/origin.json')['H0']
bl = L('data/architecture/blocks.json'); ff = L('data/structure/floor-first.json'); fg = L('data/structure/floor-ground.json')
ops = [x for x in L('data/architecture/openings.json')['openings'] if x['floor'] == 'first']
pr = L('data/plumbing/proposal.json'); FR = L('data/electrical/first-riser.json')
r3 = lambda v: round(v, 3)
FFL = FR['levels']['firstFloorFinishAbs']; CEIL = FR['levels']['droppedCeilingAbs']; Hh = I['heights']; PL = I['place']
def ext(a, c, e):
    dx, dy = c[0]-a[0], c[1]-a[1]; l = math.hypot(dx, dy); ux, uy = dx/l, dy/l
    return [(a[0]-ux*e, a[1]-uy*e), (c[0]+ux*e, c[1]+uy*e)]
walls = [LineString(ext(*w['axisITM'], 0.12)).buffer(w['thickness_m']/2+0.015, cap_style=2) for w in bl['walls'] if w['floor'] == 'first']
walls += [Polygon(w['footprintITM']).buffer(0.03) for w in ff['walls']]
for x in ops:
    c = x['centerITM']; a = x['axisITM']; h = x['width_m']/2+0.08
    walls.append(LineString([(c[0]-a[0]*h, c[1]-a[1]*h), (c[0]+a[0]*h, c[1]+a[1]*h)]).buffer(0.14, cap_style=2))
W = unary_union(walls)
outline = Polygon(ff['ceiling']['slab'][0]['footprintITM'])
free = outline.difference(W)
regions = [g for g in (free.geoms if hasattr(free, 'geoms') else [free]) if g.area > 0.8]
fx = [(p['kind'], p['id'], Point(p['E'], p['N'])) for p in pr['points'] if p.get('floor') == 'first']
slab1 = unary_union([Polygon(s['footprintITM']) for s in fg['ceiling']['slab'] if s['id'] == 'FS1'])
rooms = {}
for lb in I['labels']:
    g = next((r for r in regions if r.contains(Point(lb['ITM']))), None)
    if g is None: continue
    if lb['room'] == 'hall': g = g.intersection(slab1.buffer(-0.05)); g = max(g.geoms, key=lambda q: q.area) if hasattr(g, 'geoms') else g
    rooms[lb['room']] = {'name': lb['name'], 'poly': g, 'source': I['labelsSource']}
# bathrooms: the region holding the fixtures, split between the two fixture groups (perpendicular bisector)
bathReg = next(r for r in regions if sum(1 for _, _, p in fx if r.buffer(0.15).contains(p)) >= 4)
g1 = [p for k, i_, p in fx if i_.endswith('1@first') and bathReg.buffer(0.15).contains(p)]
g2 = [p for k, i_, p in fx if i_.endswith('2@first') and bathReg.buffer(0.15).contains(p)]
c1 = (sum(p.x for p in g1)/len(g1), sum(p.y for p in g1)/len(g1)); c2 = (sum(p.x for p in g2)/len(g2), sum(p.y for p in g2)/len(g2))
mid = ((c1[0]+c2[0])/2, (c1[1]+c2[1])/2); d = (c2[0]-c1[0], c2[1]-c1[1]); n = (-d[1], d[0]); nl = math.hypot(*n); n = (n[0]/nl*20, n[1]/nl*20)
parts = split(bathReg, LineString([(mid[0]-n[0], mid[1]-n[1]), (mid[0]+n[0], mid[1]+n[1])]))
for gpart in parts.geoms:
    key = 'bath1' if gpart.contains(Point(c1)) else 'bath2' if gpart.contains(Point(c2)) else None
    if key: rooms[key] = {'name': 'חדר רחצה ' + key[-1], 'poly': gpart, 'source': 'קבועות האינסטלציה (data/plumbing/proposal.json) – האזור חולק בין שתי קבוצות הקבועות (מחיצה לא סגורה בנתונים)'}
roomDoor = {}
for k, r in rooms.items():
    ds = [x for x in ops if x['kind'] == 'door' and r['poly'].buffer(0.4).intersects(Point(x['centerITM']))]
    r['doors'] = [x['id'] for x in ds]; r['windows'] = [x['id'] for x in ops if x['kind'] != 'door' and r['poly'].buffer(0.4).intersects(Point(x['centerITM']))]
# bathroom door: shared with its bedroom; bedroom entrance: the door towards the hall
ent = {'room1': None, 'room2': None, 'bath1': None, 'bath2': None}
for b in ('bath1', 'bath2'): ent[b] = next(dd for dd in rooms[b]['doors'] if dd in rooms['room1']['doors']+rooms['room2']['doors'])
for rm in ('room1', 'room2'): ent[rm] = next(dd for dd in rooms[rm]['doors'] if dd in rooms['hall']['doors'])
bathOf = {('room1' if ent[b] in rooms['room1']['doors'] else 'room2'): b for b in ('bath1', 'bath2')}
opById = {x['id']: x for x in ops}
# ---- wall faces of a room with free intervals
def faces(poly):
    ring = list(poly.exterior.coords)[:-1]; out = []
    for i in range(len(ring)):
        a, b = ring[i], ring[(i+1) % len(ring)]; Lf = math.dist(a, b)
        if Lf < 0.4: continue
        u = ((b[0]-a[0])/Lf, (b[1]-a[1])/Lf); nn = (-u[1], u[0])
        if not poly.contains(Point(a[0]+u[0]*Lf/2+nn[0]*0.05, a[1]+u[1]*Lf/2+nn[1]*0.05)): nn = (u[1], -u[0])
        blocked = []
        for x in ops:
            c = x['centerITM']; t = (c[0]-a[0])*u[0]+(c[1]-a[1])*u[1]; dperp = abs((c[0]-a[0])*nn[0]+(c[1]-a[1])*nn[1])
            if dperp < 0.45 and -x['width_m'] < t < Lf+x['width_m']: blocked.append((t-x['width_m']/2-PL['openingClear_m'], t+x['width_m']/2+PL['openingClear_m'], x['id']))
        out.append({'a': a, 'b': b, 'u': u, 'n': nn, 'L': Lf, 'blocked': blocked})
    return out
def free_spots(fcs):
    spots = []
    for fi, f in enumerate(fcs):
        t = PL['cornerClear_m']
        while t <= f['L']-PL['cornerClear_m']:
            if not any(b0 <= t <= b1 for b0, b1, _ in f['blocked']):
                spots.append((fi, t, (f['a'][0]+f['u'][0]*t, f['a'][1]+f['u'][1]*t)))
            t += PL['step_m']
    return spots
def spread(spots, k, start):          # farthest-point sampling along the free wall, starting far from 'start'
    if not spots: return []
    chosen = [max(spots, key=lambda s: math.dist(s[2], start))]
    while len(chosen) < k:
        nxt = max(spots, key=lambda s: min(math.dist(s[2], c[2]) for c in chosen))
        if min(math.dist(nxt[2], c[2]) for c in chosen) < 0.6: break
        chosen.append(nxt)
    return chosen
points = []
def add(room, kind, label, xy, h, onWall=None, circuit=None, note=''):
    p = {'id': f"{room}-{kind}-{sum(1 for q in points if q['room'] == room and q['kind'] == kind)+1}", 'room': room, 'roomName': rooms[room]['name'], 'kind': kind, 'label': label,
         'ITM': [r3(xy[0]), r3(xy[1])], 'abs': r3(h), 'rel': r3(h-H0), 'aboveFloor_m': r3(h-FFL) if h < CEIL-0.01 else None, 'onCeiling': h >= CEIL-0.01, 'circuit': circuit, 'status': 'provisional', 'note': note}
    if onWall: p['normalITM'] = [r3(onWall[0]), r3(onWall[1])]
    points.append(p); return p
def at(fc, t, off=0.0): return (fc['a'][0]+fc['u'][0]*t+fc['n'][0]*off, fc['a'][1]+fc['u'][1]*t+fc['n'][1]*off)
def door_switch(room, doorId, circuitL, label='מפסק תאורה'):
    fcs = faces(rooms[room]['poly']); x = opById[doorId]; c = x['centerITM']
    best = None
    for fi, f in enumerate(fcs):
        t = (c[0]-f['a'][0])*f['u'][0]+(c[1]-f['a'][1])*f['u'][1]; dperp = abs((c[0]-f['a'][0])*f['n'][0]+(c[1]-f['a'][1])*f['n'][1])
        if dperp > 0.45: continue
        for sgn in (1, -1):
            ts = t+sgn*(x['width_m']/2+PL['doorSwitchGap_m']+0.04)
            if PL['cornerClear_m']*0.4 <= ts <= f['L']-0.1 and not any(b0 <= ts <= b1 for b0, b1, i_ in f['blocked'] if i_ != doorId):
                room_len = (f['L']-ts) if sgn > 0 else ts
                if not best or room_len > best[0]: best = (room_len, f, ts)
    if not best:   # adjacent face (door in a corner): nearest free spot
        sp = free_spots(fcs); s = min(sp, key=lambda s_: math.dist(s_[2], c)); f = fcs[s[0]]; best = (0, f, s[1])
    _, f, ts = best
    return add(room, 'switch', label, at(f, ts, 0.0), FFL+Hh['switch'], f['n'], circuitL, f'ליד דלת {doorId}, צד הידית – לאשר')
circ = {c['id']: c for c in I['circuits']}
def circ_of(room, kind):
    for c in I['circuits']:
        if c['kind'] == kind and room in c['rooms']: return c['id']
    return None
for rm in ('room1', 'room2'):
    R = rooms[rm]; poly = R['poly']; fcs = faces(poly); sp = free_spots(fcs); door = opById[ent[rm]]['centerITM']
    add(rm, 'light', 'נקודת תאורה', (poly.centroid.x, poly.centroid.y), CEIL, None, circ_of(rm, 'light'), 'במרכז החדר, בהנמכה')
    door_switch(rm, ent[rm], circ_of(rm, 'light'))
    # bath switch outside the bathroom door (in the bedroom)
    door_switch(rm, ent[bathOf[rm]], circ_of(bathOf[rm], 'light'), f"מפסק תאורה – {rooms[bathOf[rm]]['name']}")
    for s in spread([s for s in sp if math.dist(s[2], door) > 0.8], I['rooms']['bedroom']['sockets'], door):
        add(rm, 'socket', 'שקע', at(fcs[s[0]], s[1]), FFL+Hh['socket'], fcs[s[0]]['n'], circ_of(rm, 'socket'))
    soc = [p for p in points if p['room'] == rm and p['kind'] == 'socket']
    tv = max(soc, key=lambda p: math.dist(p['ITM'], door))   # data next to the farthest socket (TV / desk)
    add(rm, 'data', 'נקודת תקשורת', (tv['ITM'][0]+0.0, tv['ITM'][1]+0.0), FFL+Hh['data']+0.12, tv.get('normalITM'), circ_of(rm, 'lv'), 'ליד השקע הרחוק (טלוויזיה / שולחן)')
    for wid in R['windows']:
        w = opById[wid]
        if 'גלילה' not in w['name'] and 'תריס' not in w['name']: continue
        c = w['centerITM']; ax_ = w['axisITM']
        f = min(fcs, key=lambda f_: abs((c[0]-f_['a'][0])*f_['n'][0]+(c[1]-f_['a'][1])*f_['n'][1]))
        t = (c[0]-f['a'][0])*f['u'][0]+(c[1]-f['a'][1])*f['u'][1]
        add(rm, 'shutter', f'נקודת מנוע תריס – {wid}', at(f, t+w['width_m']/2+0.1), H0+w['headRel']+Hh['shutterAboveHead'], f['n'], 'F-SH', 'בצד הארגז, מעל הראש')
        for sgn in (1, -1):
            ts = t+sgn*(w['width_m']/2+0.25)
            if PL['cornerClear_m'] <= ts <= f['L']-PL['cornerClear_m']: break
        add(rm, 'shutterSwitch', f'מפסק תריס – {wid}', at(f, ts), FFL+Hh['shutterSwitch'], f['n'], 'F-SH')
for b in ('bath1', 'bath2'):
    R = rooms[b]; poly = R['poly']; fcs = faces(poly)
    add(b, 'light', 'תאורה בתקרה', (poly.centroid.x, poly.centroid.y), CEIL, None, circ_of(b, 'light'))
    basin = next(p for k, i_, p in fx if k == 'basin' and i_.endswith(b[-1]+'@first'))
    shower = next(p for k, i_, p in fx if k == 'shower' and i_.endswith(b[-1]+'@first'))
    f = min(fcs, key=lambda f_: LineString([f_['a'], f_['b']]).distance(basin))
    t = (basin.x-f['a'][0])*f['u'][0]+(basin.y-f['a'][1])*f['u'][1]
    add(b, 'mirrorLight', 'תאורה מעל המראה', at(f, t), FFL+Hh['mirrorLight'], f['n'], circ_of(b, 'light'))
    best = None
    for sgn in (1, -1):
        ts = t+sgn*PL['bathSocketFromBasin_m']; q = at(f, ts)
        if not (0.1 <= ts <= f['L']-0.1): continue
        dsh = math.dist(q, (shower.x, shower.y))
        if not best or dsh > best[0]: best = (dsh, q)
    dsh, q = best
    add(b, 'bathSocket', 'שקע מוגן מים (IP44) ליד הכיור', q, FFL+Hh['bathSocket'], f['n'], circ_of(b, 'socket'), f'{dsh:.2f} מ\' מנקודת המקלחת (נדרש ≥{PL["showerClear_m"]})')
    rooms[b]['showerClear'] = r3(dsh)
# hall
Rh = rooms['hall']; poly = Rh['poly']; fcs = faces(poly); sp = free_spots(fcs)
dp = FR['distribution']['planITM']; ar = L('data/structure/stairs.json')['stairs'][1]['arrivalRiserITM']; am = ((ar[0][0]+ar[1][0])/2, (ar[0][1]+ar[1][1])/2)
far = max(list(poly.exterior.coords), key=lambda q: math.dist(q, am))
for frac in (0.25, 0.7):
    q = (am[0]+(far[0]-am[0])*frac, am[1]+(far[1]-am[1])*frac)
    if not poly.contains(Point(q)): q = (poly.centroid.x, poly.centroid.y)
    add('hall', 'light', 'תאורה – מבואה', q, CEIL, None, 'F-L1')
s0 = min(sp, key=lambda s: math.dist(s[2], am)); add('hall', 'switch', 'מחליף – ראש המדרגות', at(fcs[s0[0]], s0[1]), FFL+Hh['switch'], fcs[s0[0]]['n'], 'F-L1', 'מחליף (דו-כיווני) עם המפסק בתחתית המדרגות')
s1 = max(sp, key=lambda s: math.dist(s[2], am)); add('hall', 'switch', 'מחליף – קצה המבואה', at(fcs[s1[0]], s1[1]), FFL+Hh['switch'], fcs[s1[0]]['n'], 'F-L1')
s2 = spread([s for s in sp if math.dist(s[2], s0[2]) > 1.0 and math.dist(s[2], s1[2]) > 1.0], 1, am)
for s in s2: add('hall', 'socket', 'שקע', at(fcs[s[0]], s[1]), FFL+Hh['socket'], fcs[s[0]]['n'], 'F-S3')
st_ = sorted(sp, key=lambda s: math.dist(s[2], (poly.centroid.x, poly.centroid.y)))[0]
add('hall', 'thermostat', 'תרמוסטט מיני-מרכזי', at(fcs[st_[0]], st_[1]), FFL+Hh['thermostat'], fcs[st_[0]]['n'], 'F-ACc')
add('hall', 'smoke', 'גלאי עשן', (poly.centroid.x, poly.centroid.y), CEIL, None, 'F-SD')
ac = FR.get('acReserve')
if ac: add('hall', 'acPower', 'נקודת כוח – מיני-מרכזי (בחלל הטכני)', ac['centreITM'], ac['topAbs']+0.0, None, 'F-AC', 'ליד היחידה הפנימית, מעל ההנמכה')
# ---- checks
checks = []
for p in points:
    if p['onCeiling'] or p['kind'] == 'acPower': continue
    R = rooms[p['room']]['poly']
    d = R.exterior.distance(Point(p['ITM']))
    checks.append({'ref': p['id'], 'check': 'על פני קיר החדר', 'value': r3(d), 'required': 0.02, 'ok': d <= 0.02})
for b in ('bath1', 'bath2'):
    checks.append({'ref': f'{b} שקע', 'check': 'מרחק מהמקלחת', 'value': rooms[b]['showerClear'], 'required': PL['showerClear_m'], 'ok': rooms[b]['showerClear'] >= PL['showerClear_m']})
counts = {}
for p in points: counts.setdefault(p['roomName'], {}).setdefault(p['label'].split(' –')[0], 0); counts[p['roomName']][p['label'].split(' –')[0]] += 1
out = {'_doc': 'ח4 קומה א\' – נקודות חשמל (הצעה). נוצר ע״י tools/electrical/propose_points_first.py – לא לערוך ידנית.', 'status': 'proposal',
       'source': 'tools/electrical/propose_points_first.py + tools/electrical/points-first-inputs.json', 'decision': I['decision'], 'heights': Hh,
       'levels': {'floorAbs': FFL, 'ceilingAbs': CEIL},
       'rooms': {k: {'name': v['name'], 'ringITM': [[r3(x), r3(y)] for x, y in list(v['poly'].exterior.coords)[:-1]], 'area_m2': r3(v['poly'].area), 'doors': v.get('doors'), 'windows': v.get('windows'), 'entrance': ent.get(k), 'source': v['source']} for k, v in rooms.items() if k != 'voidFS2'},
       'points': points, 'circuits': I['circuits'], 'counts': counts, 'checks': checks,
       'summary': {'points': len(points), 'circuits': len([c for c in I['circuits'] if c['kind'] not in ('lv', 'spare')]), 'conduitsUp': sum(2 if c['conduit'].startswith('2×') else 1 for c in I['circuits']),
                   'checks': len(checks), 'failed': sum(1 for c in checks if not c['ok'])}}
json.dump(out, open(os.path.join(ROOT, 'data/electrical/points-first.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(out['summary']); print(json.dumps(counts, ensure_ascii=False))
for c in checks:
    if not c['ok']: print('XX', c)

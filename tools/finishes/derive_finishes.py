#!/usr/bin/env python3
"""Rooms, plaster surfaces and tiling surfaces, derived from the model geometry (no dimension is typed here).

Inputs (geometry – the single source of truth):
  data/structure/floor-ground.json / floor-first.json / floor-roof.json  concrete walls, columns, slabs, ceilings, beams
  data/structure/framing.json        basement walls (K-11) and basement slabs
  data/architecture/blocks.json      block walls (axis + thickness, merged runs with segments)
  data/architecture/openings.json    windows / doors / vitrines (centre, axis, width, sill, head)
  data/structure/perimeter.json      courtyard walls (site)
  sources/plumbing/אינסטלציה חתכים הכל.dxf  room names (architect's Revit plans, layer G-ANNO-TEXT)
Decisions (Avihai):
  data/finishes/plaster/types.json, overrides.json, data/finishes/rooms-input.json, data/finishes/config.json
Outputs (derived – do not edit by hand):
  data/architecture/rooms.json, data/finishes/plaster/surfaces.json, data/finishes/tiling/surfaces.json,
  docs/quantities/plaster-quantities.xlsx

Method: every floor is cut horizontally (config cuts). The union of the walls / columns standing at the cut (plus the
openings of the concrete walls, closed) is the solid; its holes are the rooms, its outer rings the façade. Every ring
edge belongs to the wall it lies on – that edge is a wall face. Its height: from the floor under the face to the
ceiling over it (the slabs of the whole house at that point), clipped by the wall's own bottom / top. Openings of the
same wall line are subtracted. Ceilings: the room polygon split by the slabs above it (lowest first; a slab already
claimed by a lower room – double-height void, stair shaft – is not counted twice).
"""
import json, math, os, re, sys
from collections import defaultdict

from shapely.geometry import Polygon, MultiPolygon, LineString, Point, box
from shapely.ops import unary_union

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
r3 = lambda v: round(float(v) + 0.0, 3)
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))


def dump(p, d):
    with open(os.path.join(ROOT, p), 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
        f.write('\n')


CFG = J('data/finishes/config.json')
TYPES = J('data/finishes/plaster/types.json')
OVR = J('data/finishes/plaster/overrides.json')['overrides']
RIN = J('data/finishes/rooms-input.json')['rooms']
ORIGIN = J('data/site/origin.json')
GF, FF, RF = J('data/structure/floor-ground.json'), J('data/structure/floor-first.json'), J('data/structure/floor-roof.json')
FR = J('data/structure/framing.json')
BL = J('data/architecture/blocks.json')
OP = J('data/architecture/openings.json')['openings']
PER = J('data/structure/perimeter.json')
FLOORS = ['unit', 'ground', 'first', 'roof']
FLOOR_HE = {'unit': 'יחידת דיור (מרתף)', 'ground': 'קרקע', 'first': "קומה א'", 'roof': 'גג', 'site': 'מגרש'}


def poly(ring, holes=()):
    p = Polygon(ring, [h for h in holes if len(h) >= 3])
    return p if p.is_valid else p.buffer(0)


# ---------------------------------------------------------------- solids (walls / columns), all floors
SOL = []   # {id, kind, poly, bottom, top, thickness, src}


def add_solid(id_, kind, p, bottom, top, thickness, src, floor=None):
    if p.is_empty or p.area < 1e-4: return
    SOL.append(dict(id=id_, kind=kind, poly=p, bottom=bottom, top=top, thickness=thickness, src=src, floor=floor))


for fl, D in (('ground', GF), ('first', FF), ('roof', RF)):
    for w in D['walls']:
        add_solid(w['id'], 'concrete', poly(w['footprintITM'], w.get('holesITM', [])), w['bottomRel'], w['topRel'], w['thickness_m'], w['source'], fl)
    for c in D['columns']:
        add_solid(c['id'], 'column', poly(c['footprintITM']), c['bottomRel'], c['topRel'], min(c['size_cm']) / 100, c['source'], fl)
for w in FR['basementWalls']:
    parts = w.get('partsITM') or [w['footprintITM']]
    add_solid(w['id'], 'concrete', poly(w['footprintITM'], w.get('holesITM', [])), w['bottomRel'], w['topRel'], None, w['source'], 'unit')


def block_rect(a, b, t):
    (x0, y0), (x1, y1) = a, b
    L = math.hypot(x1 - x0, y1 - y0); ux, uy = (x1 - x0) / L, (y1 - y0) / L; nx, ny = -uy * t / 2, ux * t / 2
    return Polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]), L, (ux, uy)


BLOCKS = {}
for w in BL['walls']:
    if w.get('removedBy'): continue
    a, b = w['axisITM']; t = w['thickness_m']
    _, L, (ux, uy) = block_rect(a, b, t)
    segs = w.get('segments') or [{'id': w['id'], 's0': 0, 's1': L, 'bottomRel': w['bottomRel'], 'topRel': w['topRel']}]
    for s in segs:
        pa = (a[0] + ux * s['s0'], a[1] + uy * s['s0']); pb = (a[0] + ux * s['s1'], a[1] + uy * s['s1'])
        p, _, _ = block_rect(pa, pb, t)
        add_solid(w['id'], 'block', p, s['bottomRel'], s['topRel'], t, w['source'], w['floor'])
    BLOCKS[w['id']] = w

# openings whose host is a concrete wall are gaps in its drawn footprint: closed for the room detection only
HOST_T = {s['id']: s['thickness'] for s in SOL}
CLOSERS = []
for o in OP:
    if o['id'].startswith('OC-'): continue
    c, (ax, ay), wd = o['centerITM'], o['axisITM'], o['width_m']
    Pc = Point(c)
    inside = [x for x in SOL if x['kind'] in ('concrete', 'block') and x['poly'].contains(Pc)]
    if inside:   # the opening sits inside a drawn wall (block walls): the closer stays inside it (no jog in the room outline)
        t = min(2 * x['poly'].exterior.distance(Pc) for x in inside) - 0.004
    else:        # a gap in a concrete wall: close it at the host thickness
        near = sorted([x for x in SOL if x['kind'] in ('concrete', 'block') and x['poly'].distance(Pc) < 0.4], key=lambda x: x['poly'].distance(Pc))
        t = HOST_T.get(o['host']) or (near[0]['thickness'] if near and near[0]['thickness'] else None) or CFG['gapCloserDefault_m']
    t = max(t, 0.02)
    p, _, _ = block_rect((c[0] - ax * wd / 2, c[1] - ay * wd / 2), (c[0] + ax * wd / 2, c[1] + ay * wd / 2), t)
    CLOSERS.append(dict(id=o['id'], kind='opening', poly=p, bottom=o['sillRel'], top=o['headRel'], thickness=t, src=o['source'], floor=o['floor']))

# ---------------------------------------------------------------- slabs (floors and ceilings of the whole house)
SLABS = []   # {id, poly, top, bottom, role}
for s in FR['slabs']:
    SLABS.append(dict(id=s['id'], poly=poly(s['outlineITM'], s.get('holesITM', [])), top=s['top'], bottom=r3(s['top'] - s['thickness_m']), src=s['source']))
for s in GF['slab']:
    SLABS.append(dict(id=s['id'], poly=poly(s['footprintITM'], s.get('holesITM', [])), top=s['topRel'], bottom=s['bottomRel'], src=s['source'], zone=s['zone']))
for D in (GF, FF):
    for s in D['ceiling']['slab']:
        SLABS.append(dict(id=s['id'], poly=poly(s['footprintITM'], s.get('holesITM', [])), top=s['topRel'], bottom=s['bottomRel'], src=s['source']))
SLAB_BY = {s['id']: s for s in SLABS}
BEAMS = [dict(b, floorOf=fl) for fl, D in (('ground', GF), ('first', FF), ('roof', RF)) for b in D['ceiling']['beams'] if b.get('axisITM')]


def floor_at(pt, z):
    """top of the highest slab under (pt, z) – the floor a face at that point stands on"""
    P = Point(pt); c = [s for s in SLABS if s['top'] <= z + 1e-6 and s['poly'].buffer(0.02).contains(P)]
    return max(c, key=lambda s: s['top']) if c else None


def ceiling_at(pt, z):
    P = Point(pt); c = [s for s in SLABS if s['bottom'] >= z - 1e-6 and s['poly'].buffer(0.02).contains(P)]
    return min(c, key=lambda s: s['bottom']) if c else None


# ---------------------------------------------------------------- room names (architect's Revit plans)
def room_labels():
    cache = os.path.join(ROOT, 'tools', 'cache', 'room-labels.json')
    src = os.path.join(ROOT, 'sources', 'plumbing', 'אינסטלציה חתכים הכל.dxf')
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(src):
        return json.load(open(cache, encoding='utf-8'))
    import ezdxf
    import extract_openings as XO
    msp = ezdxf.readfile(src).modelspace()
    dec = lambda s: re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), s)
    out = {}
    for fl, (blk, dxf, *_r) in XO.FLOORS.items():
        ents, to_itm, _ = XO.place(msp, blk, dxf)
        L = []
        for e in ents:
            if e.dxftype() not in ('TEXT', 'MTEXT') or e.dxf.layer != 'G-ANNO-TEXT': continue
            t = dec(e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).strip().replace('\n', ' ')
            if not re.search('[א-ת]', t): continue
            x, y = to_itm(e.dxf.insert.x, e.dxf.insert.y)
            L.append({'text': t, 'itm': [r3(x), r3(y)]})
        out[fl] = L
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump(out, open(cache, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return out


LABELS = room_labels()
WET_WORDS = ('רחצה', 'מקלחת', 'שירותים', 'כביסה')
TYPE_HE = {'dry': 'יבש', 'wet': 'רטוב', 'kitchen': 'מטבח', 'mamad': 'ממ"ד', 'basement': 'מרתף', 'stairs': 'חדר מדרגות',
           'court': 'חצר אנגלית', 'outdoor': 'חוץ', 'unknown': 'לא מסווג'}
NET = J('data/plumbing/network.json')
FIX = [n for n in NET['nodes'] if n['kind'] in ('wc', 'shower', 'basin', 'washer', 'sink', 'kitchenPoint', 'floorDrain', 'drumTrap')]
COURTS = [poly(z['footprintITM']) for z in GF['openZones'] if z['zone'] in ('courtyard', 'basementStairs')]
STAIR = [poly(z['footprintITM']) for z in GF['openZones'] if z['zone'] == 'stairShaft']
MAMAD = [poly(s['footprintITM']) for s in GF['slab'] if s['zone'] == 'mamad']


def default_room_type(floor, names, p):
    """(type, reason) – fixtures of the plumbing plan first, then the room name in the architect's plan"""
    n = ' '.join(names)
    fx = [f for f in FIX if f['floor'] == floor and p.buffer(CFG['fixtureReach_m']).contains(Point(f['E'], f['N']))]
    kinds = {f['kind'] for f in fx}
    if floor == 'roof': return 'outdoor', 'גג פתוח'
    if any(p.intersection(c).area > 0.5 * p.area for c in COURTS): return 'court', 'אזור חצר אנגלית / מדרגות חוץ (K-21 openZones)'
    if any(p.intersection(c).area > 0.5 * p.area for c in STAIR): return 'stairs', 'פיר המדרגות (K-21 openZones)'
    if floor == 'unit': return 'basement', 'קומת המרתף – כל הקירות מבפנים טיח רטוב (החלטת אביחי)'
    if 'ממ' in n or (floor == 'ground' and any(p.intersection(m).area > 0.6 * p.area for m in MAMAD)): return 'mamad', 'רצפת ממ"ד GS7 / תווית ממ"ד'
    if kinds & {'wc', 'shower', 'washer', 'floorDrain', 'drumTrap'}:
        return 'wet', 'כלים סניטריים בתוכנית האינסטלציה: ' + ', '.join(sorted(f['id'] + ' ' + f['kind'] for f in fx))
    if any(w in n for w in WET_WORDS): return 'wet', 'שם החדר: ' + n
    if kinds & {'sink', 'kitchenPoint'} or 'מטבח' in n: return 'kitchen', 'כיור מטבח / שם החדר'
    if names: return 'dry', 'שם החדר: ' + n
    return 'unknown', 'אין שם ואין כלים סניטריים'


# ---------------------------------------------------------------- per floor: solid, rooms, faces
def solids_at(floor, z):
    S = [s for s in SOL if s['bottom'] <= z <= s['top']]
    C = [c for c in CLOSERS if c['floor'] == floor]
    return S, C


def ring_edges(ring):
    pts = list(ring.coords)[:-1]
    n = len(pts)
    return [(pts[i], pts[(i + 1) % n]) for i in range(n)]


def owner_of(a, b, S):
    """the solid whose boundary carries the edge a–b (most of it)"""
    seg = LineString([a, b]); best, bl = None, 0
    for s in S:
        ov = s['poly'].boundary.buffer(0.006).intersection(seg).length
        if ov > bl + 1e-6: best, bl = s, ov
    if not best or bl <= 0.5 * seg.length: return None
    return best.get('hostSolid') if best['kind'] == 'opening' else best   # an opening's edge is a face of its host wall


def unit_normal(a, b, inside_left):
    dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy)
    nx, ny = (-dy / L, dx / L) if inside_left else (dy / L, -dx / L)
    return nx, ny


def facade_of(nx, ny):
    """outward normal (grid) -> true azimuth -> N / E / S / W"""
    az = (math.degrees(math.atan2(nx, ny)) - ORIGIN['trueNorthGridAzimuth_deg']) % 360
    return ['N', 'E', 'S', 'W'][int(((az + 45) % 360) // 90)]


FACADE_HE = {'N': 'צפון', 'E': 'מזרח', 'S': 'דרום', 'W': 'מערב'}
ROOMS, FACES, CEILS, TILES, CLAIMED = [], [], [], [], defaultdict(list)
ISSUES = []
GAPS = []


def merge_faces(edges):
    """consecutive edges on the same owner and the same line -> one face"""
    out = []
    for e in edges:
        if out:
            p = out[-1]
            same = p['owner'] is e['owner'] or (p['owner'] and e['owner'] and p['owner']['id'] == e['owner']['id'])
            dx1, dy1 = p['b'][0] - p['a'][0], p['b'][1] - p['a'][1]; dx2, dy2 = e['b'][0] - e['a'][0], e['b'][1] - e['a'][1]
            cr = abs(dx1 * dy2 - dy1 * dx2) / (math.hypot(dx1, dy1) * math.hypot(dx2, dy2) + 1e-12)
            if same and cr < 0.02 and math.dist(p['b'], e['a']) < 1e-6:
                p['b'] = e['b']; continue
        out.append(dict(e))
    if len(out) > 1:   # wrap-around
        p, e = out[-1], out[0]
        if (p['owner'] and e['owner'] and p['owner']['id'] == e['owner']['id']) and math.dist(p['b'], e['a']) < 1e-6:
            dx1, dy1 = p['b'][0] - p['a'][0], p['b'][1] - p['a'][1]; dx2, dy2 = e['b'][0] - e['a'][0], e['b'][1] - e['a'][1]
            cr = abs(dx1 * dy2 - dy1 * dx2) / (math.hypot(dx1, dy1) * math.hypot(dx2, dy2) + 1e-12)
            if cr < 0.02: e['a'] = p['a']; out.pop()
    return out


def opening_cut(face, z0, z1):
    """openings in the face's wall line: [(id, s0, s1, zlo, zhi, kind)] in face coordinates (s from a)"""
    a, b = face['a'], face['b']; L = math.dist(a, b); ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    t = (face['owner'] or {}).get('thickness') or 0.3
    out = []
    for o in OP:
        if o['id'].startswith('OC-'): continue
        c = o['centerITM']; ax, ay = o['axisITM']
        if abs(ax * uy - ay * ux) > 0.05: continue            # not parallel
        d = abs((c[0] - a[0]) * -uy + (c[1] - a[1]) * ux)       # distance of the opening centre (wall axis) from the face line
        if d > t / 2 + 0.08: continue
        sc = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
        s0, s1 = max(0, sc - o['width_m'] / 2), min(L, sc + o['width_m'] / 2)
        zlo, zhi = max(z0, o['sillRel']), min(z1, o['headRel'])
        if s1 - s0 < 0.02 or zhi - zlo < 0.02: continue
        out.append(dict(id=o['id'], s0=r3(s0), s1=r3(s1), z0=r3(zlo), z1=r3(zhi), kind=o['kind'], width=o['width_m'],
                        sill=o['sillRel'], head=o['headRel']))
    return out


def standing_level(fl, flo, z0, side):
    """the level one stands on in front of the face: the finished floor of the floor when the face rises from its slab"""
    ff = CFG['finishFloor'].get(fl)
    if side == 'in' and flo and ff is not None and 0 <= ff - flo['top'] <= 0.3: return ff
    return flo['top'] if flo else z0


def face_record(fl, f, side, room, inside_left, z_cut):
    a, b = f['a'], f['b']; L = math.dist(a, b)
    if L < 0.03: return None
    nx, ny = unit_normal(a, b, inside_left)
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    probe = (m[0] + nx * 0.08, m[1] + ny * 0.08)       # just off the face, in the space it faces
    ow = f['owner']
    flo, cei = floor_at(probe, z_cut), ceiling_at(probe, z_cut)
    if side == 'in':
        z0 = flo['top'] if flo else ow['bottom']
        if ow['bottom'] > z0 + CFG['beamFlushMax_m']: z0 = ow['bottom']
        z1 = cei['bottom'] if cei else ow['top']
        if ow['top'] < z1 - CFG['beamFlushMax_m']: z1 = ow['top']
    else:   # façade: from the outdoor slab / ground under the face to the wall top
        z0 = max(ow['bottom'], flo['top']) if flo else ow['bottom']
        z1 = ow['top']
    if z1 - z0 < 0.05: return None
    ops = opening_cut(f, z0, z1)
    gross = L * (z1 - z0)
    oa = sum((o['s1'] - o['s0']) * (o['z1'] - o['z0']) for o in ops
             if (o['s1'] - o['s0']) * (o['z1'] - o['z0']) >= TYPES['params']['openingMinArea_m2'])
    rec = dict(kind='wall', floor=fl, side=side, room=room['key'] if room else None, roomName=room['name'] if room else None,
               roomType=room['type'] if room else ('outdoor' if side == 'out' else None),
               owner=ow['id'], ownerKind=ow['kind'], ownerFloor=ow['floor'], thickness=ow['thickness'],
               a=[r3(a[0]), r3(a[1])], b=[r3(b[0]), r3(b[1])], normal=[r3(nx), r3(ny)], length=r3(L), z0=r3(z0), z1=r3(z1),
               gross=r3(gross), openingsArea=r3(oa), net=r3(gross - oa), openings=ops,
               floorSlab=flo['id'] if flo else None, ceilingSlab=cei['id'] if cei else None,
               standing=r3(standing_level(fl, flo, z0, side)), source=ow['src'])
    lim = rec['standing'] + TYPES['params']['scaffoldAbove_m']
    rec['scaffold'] = z1 > lim + 1e-6
    # the part above the scaffold limit (its share of the net area) – summed separately
    rec['scaffoldArea'] = r3(rec['net'] * max(0.0, z1 - max(z0, lim)) / (z1 - z0)) if rec['scaffold'] else 0.0
    if side == 'out': rec['facade'] = facade_of(nx, ny)
    return rec


def process_ring(fl, ring, side, room, inside_left, S, z):
    """faces of one ring + the corner quantities: fibreglass mesh at block / concrete junctions, corner beads at
    protruding corners (seen from the space the faces look at)"""
    mf = merge_faces([dict(a=a, b=b, owner=owner_of(a, b, S)) for a, b in ring_edges(ring)])
    recs = []
    for f in mf:
        r = face_record(fl, f, side, room, inside_left, z) if f['owner'] else None
        if r: r['meshV_m'] = 0.0; r['beads_m'] = 0.0; r['meshH_m'] = 0.0
        recs.append(r)
    n = len(mf)
    for i in range(n):
        f, g = mf[i], mf[(i + 1) % n]; rf, rg = recs[i], recs[(i + 1) % n]
        if not rf or not rg: continue
        h = min(rf['z1'], rg['z1']) - max(rf['z0'], rg['z0'])
        if h <= 0: continue
        kinds = {rf['ownerKind'], rg['ownerKind']}
        if 'block' in kinds and kinds & {'concrete', 'column'}:
            rf['meshV_m'] = r3(rf['meshV_m'] + h)
        # turn at the shared vertex: the space is on the left when inside_left – a right turn is a protruding corner
        d1 = (f['b'][0] - f['a'][0], f['b'][1] - f['a'][1]); d2 = (g['b'][0] - g['a'][0], g['b'][1] - g['a'][1])
        cr = (d1[0] * d2[1] - d1[1] * d2[0]) / (math.hypot(*d1) * math.hypot(*d2) + 1e-12)
        if (cr < -0.2 and inside_left) or (cr > 0.2 and not inside_left):
            rf['beads_m'] = r3(rf['beads_m'] + h)
    for r in recs:
        if not r: continue
        # block wall under a beam / slab: horizontal junction along the face top
        if r['ownerKind'] == 'block' and r['side'] == 'in' and r['ceilingSlab']: r['meshH_m'] = r['length']
        FACES.append(r)


def build_floor(fl):
    z = CFG['cuts'][fl]
    S, C = solids_at(fl, z)
    if not S: return
    C = [dict(c) for c in C]
    for c in C:   # host wall of each opening: the named host, else the wall the opening centre lies in
        P = c['poly'].centroid
        cand = [x for x in S if x['kind'] in ('concrete', 'block')]
        hs = [x for x in cand if x['id'] == next((o['host'] for o in OP if o['id'] == c['id']), None)] or \
             sorted([x for x in cand if x['poly'].distance(P) < 0.35], key=lambda x: x['poly'].distance(P))[:1]
        c['hostSolid'] = hs[0] if hs else None
        if hs and c['thickness'] is None: pass
    U = unary_union([s['poly'] for s in S] + [c['poly'] for c in C]).buffer(0.003, join_style=2).buffer(-0.003, join_style=2)
    # narrow gaps between solids that no opening record explains (e.g. the ממ"ד window niches): bridged when – and only
    # when – the bridge closes a room (the number of holes grows). Listed in the output as 'gaps'.
    r = CFG['gapBridge_m'] / 2
    nh = lambda G: sum(len(q.interiors) for q in getattr(G, 'geoms', [G]))
    D = U.buffer(r, join_style=2).buffer(-r, join_style=2).difference(U)
    for q in sorted(getattr(D, 'geoms', [D]), key=lambda q: -q.area):
        if q.area < 0.002: continue
        V = unary_union([U, q.buffer(0.002, join_style=2)])
        if nh(V) > nh(U):
            U = V; c = q.centroid
            gp = dict(id=f"GAP-{fl}-{len(GAPS) + 1}", kind='opening', poly=q.buffer(0.002, join_style=2), bottom=-99, top=99, thickness=None,
                      src='פער בין קירות בחיתוך (אין רשומת פתח) – נסגר לזיהוי החדר', floor=fl)
            gp['hostSolid'] = min([x for x in S if x['kind'] in ('concrete', 'block')], key=lambda x: x['poly'].distance(c))
            C = C + [gp]; GAPS.append(dict(id=gp['id'], floor=fl, itm=[r3(c.x), r3(c.y)], area_m2=r3(q.area)))
    parts = list(U.geoms) if isinstance(U, MultiPolygon) else [U]
    lab = [l for l in LABELS.get(fl, []) if l['text'] not in CFG['ignoreNames'] and len(l['text']) > 1]
    rooms_here = []
    for P in parts:
        for hole in P.interiors:
            hp = Polygon(hole)
            if hp.area < CFG['minRoom_m2']: continue
            names = sorted({l['text'] for l in lab if hp.contains(Point(l['itm']))})
            c = hp.representative_point()
            key = f"{fl}@{round(c.x * 4) / 4:.2f},{round(c.y * 4) / 4:.2f}"
            rt, why = default_room_type(fl, names, hp)
            dec = RIN.get(key, {})
            clean = [n for n in names if any(w in n for w in CFG['roomWords'])]
            fx_k = {f['kind'] for f in FIX if f['floor'] == fl and hp.buffer(CFG['fixtureReach_m']).contains(Point(f['E'], f['N']))}
            auto = ('חדר רחצה (לפי כלים בתוכנית האינסטלציה)' if 'shower' in fx_k else 'שירותים (לפי כלים בתוכנית האינסטלציה)' if 'wc' in fx_k else None) if rt == 'wet' else None
            room = dict(key=key, floor=fl, name=dec.get('name') or (' / '.join(clean) if clean else auto), names=names,
                        type=dec.get('type') or rt, typeDefault=rt, typeSource='rooms-input.json (החלטת אביחי)' if dec.get('type') else why,
                        fixtures=[f['id'] + ' ' + f['kind'] for f in FIX if f['floor'] == fl and hp.buffer(CFG['fixtureReach_m']).contains(Point(f['E'], f['N']))],
                        ringITM=[[r3(x), r3(y)] for x, y in list(hole.coords)[:-1]], area_m2=r3(hp.area), perimeter_m=r3(hp.length),
                        showerFaces=dec.get('showerFaces', []), poly=hp)
            rooms_here.append(room)
            # faces of the room: the hole ring runs clockwise around the room for shapely interiors? decide by orientation
            ring = Polygon(hole).exterior
            process_ring(fl, ring, 'in', room, ring.is_ccw, S + C, z)
        # façade
        ring = P.exterior
        process_ring(fl, ring, 'out', None, not ring.is_ccw, S + C, z)
    for r in rooms_here: ROOMS.append(r)


for fl in FLOORS: build_floor(fl)

# ---------------------------------------------------------------- same wall face seen from two cuts (double height, stair shaft): keep one
def dedupe():
    keep = []
    for f in FACES:
        dup = None
        for g in keep:
            if g['owner'] != f['owner'] or g['side'] != f['side']: continue
            if math.dist(g['a'], f['a']) < 0.02 and math.dist(g['b'], f['b']) < 0.02 and abs(g['z0'] - f['z0']) < 0.02 and abs(g['z1'] - f['z1']) < 0.02:
                dup = g; break
        if not dup: keep.append(f)
    return keep


FACES[:] = dedupe()
ROOM_BY = {r['key']: r for r in ROOMS}
PRM = TYPES['params']; WP = TYPES['waterproofing']


def seg_dist(pt, a, b):
    return LineString([a, b]).distance(Point(pt))


# ---------------------------------------------------------------- default plaster type of each wall face (rules)
def default_type(f):
    rt = f['roomType']
    if f['side'] == 'in':
        if rt in ('wet', 'basement'): return 'wet', 'חדר רטוב / מרתף מבפנים'
        if rt == 'mamad': return 'skim', 'ממ"ד – אסור טיח (פיקוד העורף)'
        if rt in ('court', 'outdoor'): return 'exterior', 'חצר אנגלית / גג פתוח'
        if rt == 'kitchen':
            sinks = [x for x in FIX if x['floor'] == f['floor'] and x['kind'] in ('sink', 'kitchenPoint')]
            if sinks and min(seg_dist((x['E'], x['N']), f['a'], f['b']) for x in sinks) < CFG['sinkWall_m']:
                return 'wet', 'הקיר שמאחורי כיור המטבח'
        return 'interior', 'קיר פנים'
    if f['floor'] == 'unit': return 'bitumen', 'קיר מרתף במגע עם קרקע (מבחוץ)'
    return 'exterior', 'קיר חיצוני (החיפוי בחזיתות טרם סומן – open-issues)'


for f in FACES:
    f['defaultType'], f['typeReason'] = default_type(f)

# ---------------------------------------------------------------- waterproofing (over the wet plaster) – wet rooms
WPROOF = []
for f in FACES:
    if f['side'] != 'in' or f['roomType'] != 'wet': continue
    room = ROOM_BY[f['room']]; ff = CFG['finishFloor'].get(f['floor'], f['standing'])
    showers = [x for x in FIX if x['floor'] == f['floor'] and x['kind'] == 'shower' and room['poly'].contains(Point(x['E'], x['N']))]
    sh = f['owner'] in room['showerFaces'] or any(seg_dist((x['E'], x['N']), f['a'], f['b']) < CFG['showerWall_m'] for x in showers)
    h = WP['showerHeight_m'] if sh else WP['wetRoomHeight_m']
    z1 = min(f['z1'], ff + h)
    if z1 <= f['z0']: continue
    doors = sum(o['s1'] - o['s0'] for o in f['openings'] if o['sill'] <= f['z0'] + 0.3)
    area = (f['length'] - doors) * (z1 - f['z0'])
    WPROOF.append(dict(kind='wall', face=None, floor=f['floor'], room=f['room'], owner=f['owner'], a=f['a'], b=f['b'], normal=f['normal'],
                       z0=f['z0'], z1=r3(z1), shower=sh, area=r3(area),
                       rule=("קיר מקלחת – עד %.2f מ' מפני הריצוף" % h) if sh else ("%.2f מ' מפני הריצוף" % h),
                       status='provisional' if sh and f['owner'] not in room['showerFaces'] else 'rule'))

# ---------------------------------------------------------------- ceilings: room split by the slabs above (lowest first)
CEILS = []
for fl in FLOORS:
    for room in [r for r in ROOMS if r['floor'] == fl]:
        z = CFG['cuts'][fl]; rem = room['poly']
        for sl in sorted([s for s in SLABS if s['bottom'] >= z], key=lambda s: s['bottom']):
            free = sl['poly']
            for c in CLAIMED[sl['id']]: free = free.difference(c)
            pc = rem.intersection(free)
            if pc.area < 0.05: continue
            CLAIMED[sl['id']].append(pc); rem = rem.difference(pc)
            # exposed ceiling beams of that slab inside the piece: two sides each
            sides, bl = 0.0, []
            inner = pc.buffer(-0.05)
            for b in BEAMS:
                drop = sl['bottom'] - b['bottomRel']
                if drop < 0.05 or abs(b['topRel'] - sl['top']) > 0.6: continue
                L = LineString(b['axisITM']).intersection(inner).length
                if L > 0.05: sides += 2 * L * drop; bl.append(dict(id=b['id'], length=r3(L), drop=r3(drop)))
            st = sl['bottom'] - (floor_at(pc.representative_point().coords[0], z) or {'top': z})['top']
            rt = room['type']
            dt = ('skim', 'תקרת ממ"ד – שפכטל בלבד') if rt == 'mamad' else (('exterior', 'תקרה חיצונית') if rt in ('court', 'outdoor') else ('interior', 'תקרה – טיח פנים'))
            for g in getattr(pc, 'geoms', [pc]):
                if g.geom_type != 'Polygon' or g.area < 0.05: continue
                share = g.area / pc.area
                CEILS.append(dict(kind='ceiling', floor=fl, room=room['key'], roomName=room['name'], roomType=rt, slab=sl['id'], z=sl['bottom'],
                                  ringITM=[[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]],
                                  holesITM=[[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in g.interiors],
                                  area=r3(g.area), beamSides=r3(sides * share), beams=bl if share > 0.5 else [], net=r3(g.area + sides * share),
                                  scaffold=st > PRM['scaffoldAbove_m'] + 1e-6, scaffoldArea=r3(g.area + sides * share) if st > PRM['scaffoldAbove_m'] + 1e-6 else 0, height=r3(st), defaultType=dt[0], typeReason=dt[1], source=sl['src']))
        room['ceilingUncovered_m2'] = r3(rem.area)

# ---------------------------------------------------------------- tops of free-standing walls (parapets, courtyard walls, low walls): under the coping
TOPS = []
for sd in SOL:
    if sd['kind'] not in ('concrete', 'block') or sd['floor'] == 'unit': continue
    c = sd['poly'].representative_point().coords[0]
    over = [s for s in SLABS if abs(s['bottom'] - sd['top']) < CFG['beamFlushMax_m'] and s['poly'].buffer(0.05).contains(Point(c))]
    if over or any(abs(b['bottomRel'] - sd['top']) < 0.02 and LineString(b['axisITM']).buffer(b['width_m'] / 2 + 0.05).contains(Point(c)) for b in BEAMS): continue
    # a wall standing on another one carries it: not a free top
    if any(o is not sd and o['kind'] in ('concrete', 'block') and abs(o['bottom'] - sd['top']) < 0.3 and o['poly'].intersection(sd['poly']).area > 0.5 * sd['poly'].area for o in SOL): continue
    TOPS.append(dict(kind='top', floor=sd['floor'], owner=sd['id'], ownerKind=sd['kind'], z=sd['top'], area=r3(sd['poly'].area),
                     ringITM=[[r3(x), r3(y)] for x, y in list(getattr(sd['poly'], 'geoms', [sd['poly']])[0].exterior.coords)[:-1]],
                     defaultType='exterior', typeReason='ראש קיר / מעקה מתחת לקופינג', scaffold=False, source=sd['src']))

# ---------------------------------------------------------------- courtyard walls (site): both sides
DEV = J('data/site/development-heights.json')['spots']
H0 = ORIGIN['H0']
for w in PER['walls']:
    P = poly(w['ringITM'])
    mr = P.minimum_rotated_rectangle; pts = list(mr.exterior.coords)[:4]
    e = sorted([(pts[i], pts[(i + 1) % 4]) for i in range(4)], key=lambda e: -math.dist(*e))[:2]
    for a, b in e:
        L = math.dist(a, b); m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        cx, cy = P.centroid.x, P.centroid.y
        nx, ny = unit_normal(a, b, True)
        if (m[0] + nx - cx) ** 2 + (m[1] + ny - cy) ** 2 < (m[0] - cx) ** 2 + (m[1] - cy) ** 2: nx, ny = -nx, -ny
        probe = (m[0] + nx * 0.3, m[1] + ny * 0.3)
        sl = floor_at(probe, w['topRel'])
        if sl: z0, zs = sl['top'], 'רצפת חוץ ' + sl['id']
        else:
            sp = min(DEV, key=lambda s: math.dist((s['E'], s['N']), probe))
            dd = math.dist((sp['E'], sp['N']), probe)
            z0, zs = (r3(sp['z'] - H0), f"נקודת גובה פיתוח {sp['z']:.2f} ({dd:.1f} מ')") if dd < 4 else (w['bottomRel'], 'אין גובה קרקע – ראש היסוד')
        z0 = max(z0, w['bottomRel'])
        if w['topRel'] - z0 < 0.05: continue
        FACES.append(dict(kind='wall', floor='site', side='out', room=None, roomName=None, roomType='outdoor', owner=w['id'], ownerKind='concrete',
                          ownerFloor='site', thickness=w['thickness_m'], a=[r3(a[0]), r3(a[1])], b=[r3(b[0]), r3(b[1])], normal=[r3(nx), r3(ny)],
                          length=r3(L), z0=r3(z0), z1=w['topRel'], gross=r3(L * (w['topRel'] - z0)), openingsArea=0, net=r3(L * (w['topRel'] - z0)),
                          openings=[], floorSlab=sl['id'] if sl else None, ceilingSlab=None, standing=r3(z0), source=w['source'],
                          scaffold=w['topRel'] - z0 > PRM['scaffoldAbove_m'], scaffoldArea=r3(L * max(0, w['topRel'] - z0 - PRM['scaffoldAbove_m'])), facade=facade_of(nx, ny), meshV_m=0, beads_m=0, meshH_m=0,
                          defaultType='exterior', typeReason='קיר חצר – שני הצדדים', zSource=zs,
                          status='provisional' if 'אין' in zs or 'נקודת' in zs else 'source'))
    TOPS.append(dict(kind='top', floor='site', owner=w['id'], ownerKind='concrete', z=w['topRel'], area=r3(P.area),
                     ringITM=[[r3(x), r3(y)] for x, y in list(P.exterior.coords)[:-1]], defaultType='exterior',
                     typeReason='ראש קיר חצר מתחת לקופינג', scaffold=False, source=w['source']))

# ---------------------------------------------------------------- reveals of openings (depth = wall thickness), once per opening
REV = {}
for f in sorted(FACES, key=lambda f: f['side'] != 'in'):
    for o in f['openings']:
        if o['id'] in REV: continue
        oo = next(x for x in OP if x['id'] == o['id'])
        h = oo['headRel'] - max(oo['sillRel'], f['z0']); w = oo['width_m']
        sill = oo['kind'] in ('window', 'vitrine') and oo['sillRel'] > f['z0'] + 0.05
        per = 2 * h + w + (w if sill else 0)
        depth = f['thickness'] or 0.2
        REV[o['id']] = dict(opening=o['id'], kind=oo['kind'], floor=oo['floor'], room=f['room'], width=w, height=r3(h), depth=r3(depth),
                            perimeter=r3(per), area=r3(per * depth), type=f['defaultType'] if f['side'] == 'in' else 'exterior',
                            beads=r3((2 * h + w) * (2 if PRM['beadsAtOpenings'] else 0)), host=f['owner'])

# ---------------------------------------------------------------- keys, overrides
def keyed(items, fn):
    seen = defaultdict(int)
    for it in items:
        k = fn(it); seen[k] += 1; it['key'] = f"{k}#{seen[k]}"
        o = OVR.get(it['key'])
        it['type'] = o['type'] if o else it['defaultType']
        it['overridden'] = bool(o)


FACES.sort(key=lambda f: (FLOORS.index(f['floor']) if f['floor'] in FLOORS else 9, f['side'], f['owner'], f['a'][0], f['a'][1]))
keyed(FACES, lambda f: f"{f['floor']}|{f['owner']}|{f['side']}|{(f['room'] or f.get('facade') or '').split('@')[-1]}")
keyed(CEILS, lambda c: f"{c['floor']}|ceil|{c['slab']}|{c['room'].split('@')[-1]}")
keyed(TOPS, lambda t: f"{t['floor']}|top|{t['owner']}")

# ---------------------------------------------------------------- tiling preparation: floor area per room, skirting
TILES = []
for room in ROOMS:
    fl = room['floor']; z = CFG['cuts'][fl]
    own = [s for s in SLABS if s['top'] < z and s['top'] > z - 3.0]
    top = max([s['top'] for s in own if s['poly'].buffer(0.02).contains(room['poly'].representative_point())] or [None]) if own else None
    on = unary_union([s['poly'] for s in own if top is not None and abs(s['top'] - top) < 0.6]) if top is not None else Polygon()
    pc = room['poly'].intersection(on) if not on.is_empty else Polygon()
    faces = [f for f in FACES if f['room'] == room['key'] and f['side'] == 'in']
    doors = sum(o['s1'] - o['s0'] for f in faces for o in f['openings'] if o['sill'] <= f['z0'] + 0.3)
    skirting = sum(f['length'] for f in faces) - doors
    wet = room['type'] in ('wet',)
    TILES.append(dict(room=room['key'], floor=fl, roomName=room['name'], roomType=room['type'], area=r3(pc.area),
                      void_m2=r3(room['area_m2'] - pc.area), finishRel=CFG['finishFloor'].get(fl), skirting_m=r3(max(0, skirting)) if room['type'] not in ('wet', 'court', 'outdoor') else 0,
                      wallTiling=dict(height_m=None, note='גובה חיפוי קירות – טרם הוחלט') if wet or room['type'] == 'kitchen' else None,
                      ringITM=[[r3(x), r3(y)] for x, y in list(pc.exterior.coords)[:-1]] if pc.geom_type == 'Polygon' and not pc.is_empty else
                              ([[r3(x), r3(y)] for x, y in list(max(pc.geoms, key=lambda g: g.area).exterior.coords)[:-1]] if not pc.is_empty else []),
                      tileType=None, status='prep'))

# ---------------------------------------------------------------- summaries
def summarize():
    S = defaultdict(lambda: defaultdict(float))
    for f in FACES + CEILS + TOPS:
        S[(f['floor'], f['type'])]['net'] += f['net'] if 'net' in f else f['area']
        S[(f['floor'], f['type'])]['scaffold'] += f.get('scaffoldArea', 0)
    return {f"{k[0]}|{k[1]}": {a: r3(b) for a, b in v.items()} for k, v in S.items()}


TOT = summarize()
for r in ROOMS: r.pop('poly', None)
meta = dict(source='tools/finishes/derive_finishes.py – נגזר מגיאומטריית המודל (ראו _doc)', generated='derived')
dump('data/architecture/rooms.json', dict(_doc='חדרים – נגזרים מהחללים הסגורים בין פני הקירות בכל קומה (tools/finishes/derive_finishes.py). '
     'שמות: תוכנית האדריכל (Revit, G-ANNO-TEXT). סוג: כלים סניטריים בתוכנית האינסטלציה / שם החדר, או החלטת אביחי ב-data/finishes/rooms-input.json.',
     **meta, cuts=CFG['cuts'], gaps=GAPS, rooms=ROOMS))
dump('data/finishes/plaster/surfaces.json', dict(_doc='משטחי טיח – נגזרים (לא לערוך ידנית). type = הדריסה של אביחי (overrides.json) או defaultType לפי הכללים. '
     'kind: wall (פני קיר: a→b ב-ITM, z0..z1 יחסי, normal = הצד שאליו הפנים פונים), ceiling (תחתית תקרה + דפנות קורות חשופות), top (ראש קיר / מעקה). '
     'net = ברוטו פחות פתחים. meshV_m / meshH_m – רשת במפגש בלוק-בטון (אנכי / לאורך ראש הקיר); beads_m – פינות בולטות.',
     **meta, walls=FACES, ceilings=CEILS, tops=TOPS, reveals=list(REV.values()), waterproofing=WPROOF, totals=TOT))
dump('data/finishes/tiling/surfaces.json', dict(_doc='הכנה לריצוף – שטח רצפה לכל חדר (החלק שמעל רצפת הקומה), פני ריצוף, פאנלים (היקף פחות דלתות). '
     'סוג אריח וגובה חיפוי קירות – טרם הוחלטו (tileType null).', **meta, rooms=TILES))
print(len(ROOMS), 'rooms', len(FACES), 'walls', len(CEILS), 'ceilings', len(TOPS), 'tops', len(REV), 'reveals', len(WPROOF), 'waterproofing', len(GAPS), 'gaps')
for k, v in sorted(TOT.items()): print(k, v)


# ---------------------------------------------------------------- Excel (docs/quantities/plaster-quantities.xlsx)
def export_xlsx(path='docs/quantities/plaster-quantities.xlsx'):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); wb.remove(wb.active)
    hdr = Font(bold=True, color='FFFFFF'); fill = PatternFill('solid', fgColor='2F5496')
    TL = {t['id']: t['label'] for t in TYPES['types']}
    RN = {r['key']: r['name'] or ('ללא שם – ' + TYPE_HE.get(r['type'], r['type'])) for r in ROOMS}

    def sheet(name, head, rows, widths=None):
        ws = wb.create_sheet(name); ws.sheet_view.rightToLeft = True; ws.append(head)
        for c in ws[1]: c.font = hdr; c.fill = fill; c.alignment = Alignment(horizontal='center', wrap_text=True)
        for r in rows: ws.append(r)
        for i, w in enumerate(widths or [16] * len(head)): ws.column_dimensions[chr(65 + i) if i < 26 else 'A' + chr(65 + i - 26)].width = w
        ws.freeze_panes = 'A2'
        return ws
    allS = [dict(f, cat='wall', amount=f['net']) for f in FACES] + [dict(c, cat='ceiling', amount=c['net']) for c in CEILS] + [dict(t, cat='top', amount=t['area']) for t in TOPS]
    by = defaultdict(float); scf = defaultdict(float)
    for s in allS: by[s['type']] += s['amount']; scf[s['type']] += s.get('scaffoldArea', 0)
    rev = sum(r['area'] for r in REV.values()); mesh = sum(f.get('meshV_m', 0) + f.get('meshH_m', 0) for f in FACES)
    beads = sum(f.get('beads_m', 0) for f in FACES) + sum(r['beads'] for r in REV.values())
    wpw = sum(w['area'] for w in WPROOF); wpf = sum(t['area'] for t in TILES if t['roomType'] == 'wet')
    price = lambda k: next((t['price'] for t in TYPES['types'] if t['id'] == k), None)
    rows = [[TL[t['id']], r3(by[t['id']]), 'מ"ר', r3(scf[t['id']]), t['price'], None] for t in TYPES['types']]
    rows += [[TYPES['waterproofing']['label'], r3(wpw + wpf), 'מ"ר', None, TYPES['waterproofing']['price'], None],
             ['ספלטות וגליפים', r3(rev), 'מ"ר', None, None, None], ['רשת פיברגלס', r3(mesh), 'מ"א', None, None, None], ['פינות מגן', r3(beads), 'מ"א', None, None, None]]
    ws = sheet('סיכום', ['סוג', 'כמות', 'יחידה', 'מזה בפיגום (מעל %.1f מ\')' % PRM['scaffoldAbove_m'], 'מחיר ליחידה', 'עלות'], rows, [30, 12, 8, 18, 14, 14])
    for i in range(2, ws.max_row + 1): ws.cell(i, 6).value = f'=IF(E{i}="","",B{i}*E{i})'
    ws.append(['סה"כ', None, None, None, None, f'=SUM(F2:F{ws.max_row})'])
    for c in ws[ws.max_row]: c.font = Font(bold=True)
    ws.append([]); ws.append(['ריצוף – שטח רצפות (הכנה)', r3(sum(t['area'] for t in TILES if t['roomType'] not in ('court', 'outdoor'))), 'מ"ר'])
    ws.append(['פנלים', r3(sum(t['skirting_m'] for t in TILES)), 'מ"א'])
    ws.append([]); ws.append(['המחירים – למילוי (ברירת מחדל ריק). מקור הכמויות: tools/finishes/derive_finishes.py – נגזר מגיאומטריית המודל.'])
    fl_rows = []
    for fl in FLOORS + ['site']:
        d = defaultdict(float)
        for s in allS:
            if s['floor'] == fl: d[s['type']] += s['amount']
        fl_rows.append([FLOOR_HE[fl]] + [r3(d[t['id']]) for t in TYPES['types']])
    sheet('לפי קומה', ['קומה'] + [TL[t['id']] for t in TYPES['types']], fl_rows)
    fc = defaultdict(lambda: defaultdict(float))
    for f in FACES:
        if f['side'] == 'out': fc[f['facade']][f['type']] += f['net']
    sheet('חוץ לפי חזית', ['חזית'] + [TL[t['id']] for t in TYPES['types']], [[FACADE_HE[k]] + [r3(fc[k][t['id']]) for t in TYPES['types']] for k in 'NESW'])
    rr = []
    for r in ROOMS:
        d = defaultdict(float)
        for s in allS:
            if s.get('room') == r['key']: d[s['type']] += s['amount']
        tl = next((t for t in TILES if t['room'] == r['key']), {})
        rr.append([FLOOR_HE[r['floor']], RN[r['key']], TYPE_HE.get(r['type']), r['area_m2'], tl.get('area')] + [r3(d[t['id']]) for t in TYPES['types']])
    sheet('לפי חדר', ['קומה', 'חדר', 'סוג חדר', 'שטח חדר', 'שטח ריצוף'] + [TL[t['id']] for t in TYPES['types']], rr, [12, 30, 12, 10, 10] + [12] * 7)
    sheet('משטחים', ['מפתח', 'קומה', 'משטח', 'צד', 'חזית', 'חדר', 'רכיב', 'סוג', 'ברירת מחדל', 'סיבה', 'אורך', 'מגובה', 'עד גובה', 'ברוטו', 'פתחים', 'נטו', 'פיגום', 'שטח בפיגום', 'רשת מ"א', 'זוויתנים מ"א'],
          [[s['key'], FLOOR_HE[s['floor']], {'wall': 'קיר', 'ceiling': 'תקרה', 'top': 'ראש קיר'}[s['cat']], {'in': 'פנים', 'out': 'חוץ'}.get(s.get('side'), ''),
            FACADE_HE.get(s.get('facade'), ''), RN.get(s.get('room'), ''), s.get('owner') or s.get('slab'), TL[s['type']], TL[s['defaultType']], s['typeReason'],
            s.get('length'), s.get('z0', s.get('z')), s.get('z1'), s.get('gross', s['amount']), s.get('openingsArea', 0), s['amount'],
            'כן' if s.get('scaffold') else '', s.get('scaffoldArea', 0), r3(s.get('meshV_m', 0) + s.get('meshH_m', 0)), s.get('beads_m', 0)] for s in allS],
          [30, 10, 8, 6, 8, 24, 10, 16, 16, 30] + [9] * 10)
    sheet('גליפים', ['פתח', 'סוג', 'קומה', 'רוחב', 'גובה', 'עומק (עובי קיר)', 'היקף', 'שטח', 'זוויתנים'],
          [[r['opening'], r['kind'], FLOOR_HE[r['floor']], r['width'], r['height'], r['depth'], r['perimeter'], r['area'], r['beads']] for r in REV.values()])
    sheet('איטום', ['קומה', 'חדר', 'רכיב', 'כלל', 'מגובה', 'עד גובה', 'שטח', 'מעמד'],
          [[FLOOR_HE[w['floor']], RN.get(w['room']), w['owner'], w['rule'], w['z0'], w['z1'], w['area'], w['status']] for w in WPROOF] +
          [[FLOOR_HE[t['floor']], RN.get(t['room']), 'רצפה', 'רצפת חדר רטוב', None, None, t['area'], 'rule'] for t in TILES if t['roomType'] == 'wet'], [12, 30, 10, 30, 8, 8, 8, 10])
    sheet('ריצוף', ['קומה', 'חדר', 'סוג חדר', 'שטח מ"ר', 'חלל (בלי רצפה) מ"ר', 'פנלים מ"א', 'פני ריצוף', 'חיפוי קירות', 'סוג אריח'],
          [[FLOOR_HE[t['floor']], RN.get(t['room']), TYPE_HE.get(t['roomType']), t['area'], t['void_m2'], t['skirting_m'], t['finishRel'], 'טרם הוחלט' if t['wallTiling'] else '', 'טרם הוחלט'] for t in TILES],
          [12, 30, 12, 10, 12, 10, 10, 12, 12])
    os.makedirs(os.path.join(ROOT, os.path.dirname(path)), exist_ok=True)
    wb.save(os.path.join(ROOT, path))
    print('xlsx ->', path)


export_xlsx()

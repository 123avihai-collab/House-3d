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
INFILL = []
for w in FR['basementWalls']:
    add_solid(w['id'], 'concrete', poly(w['footprintITM'], w.get('holesITM', [])), w['bottomRel'], w['topRel'], None, w['source'], 'unit')
    for k_, f_ in enumerate(w.get('infill', [])):   # concrete over / under the openings of the basement walls (K-11)
        INFILL.append(dict(id=f"{w['id']}-{f_['kind']}-{f_.get('opening', k_)}", kind='infill', poly=poly(f_['ringITM']), bottom=f_['bottomRel'], top=f_['topRel'],
                           thickness=None, src=w['source'], floor='unit', host=w['id']))


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
    if inside:   # the opening sits inside a drawn wall: the closer = that wall's thickness (stays inside it – no jog in the room outline)
        tw = [x['thickness'] for x in inside if x['thickness']]
        t = (min(tw) if tw else min(2 * x['poly'].exterior.distance(Pc) for x in inside)) - 0.004
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


def clean(g):
    """outline ready for triangulation: no repeated / almost-collinear points (DXF outlines carry many)"""
    h = g.buffer(0).simplify(0.003, preserve_topology=True)
    return h if not h.is_empty else g


def LinearRingCCW(P):
    return P.exterior.is_ccw


def LinearRingIsCCW(ring):
    return ring.is_ccw


def floor_at(pt, z, reach=(0.02, 0.35)):
    """top of the highest slab under (pt, z) – the floor a face at that point stands on (a slab drawn a few cm short of
    the wall still counts)"""
    P = Point(pt)
    for r in reach:
        c = [s for s in SLABS if s['top'] <= z + 1e-6 and s['poly'].distance(P) <= r]
        if c: return max(c, key=lambda s: s['top'])
    return None


def ceiling_at(pt, z, reach=(0.02, 0.35)):
    P = Point(pt)
    for r in reach:
        c = [s for s in SLABS if s['bottom'] >= z - 1e-6 and s['poly'].distance(P) <= r]
        if c: return min(c, key=lambda s: s['bottom'])
    return None


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
           'court': 'חצר אנגלית', 'outdoor': 'חוץ', 'balcony': 'מרפסת', 'unknown': 'לא מסווג'}
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
    return best   # an opening / gap edge: plaster only where material stands over / under it (lintel, sill) – see face_record


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
GAPCL = []


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


def opening_cut(face, z0, z1, floor=None):
    """openings in the face's wall line: [(id, s0, s1, zlo, zhi, kind)] in face coordinates (s from a)"""
    a, b = face['a'], face['b']; L = math.dist(a, b); ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    ow = face['owner']
    t = (ow.get('thickness') if isinstance(ow, dict) else face.get('thickness')) or 0.3
    out = []
    fl_ = floor or face.get('floor')
    for o in OP:
        if o['id'].startswith('OC-'): continue
        if fl_ and o['floor'] != fl_: continue                 # an opening of another floor never cuts this face (beam / slab between)
        c = o['centerITM']; ax, ay = o['axisITM']
        if abs(ax * uy - ay * ux) > 0.05: continue            # not parallel
        d = abs((c[0] - a[0]) * -uy + (c[1] - a[1]) * ux)       # distance of the opening centre (wall axis) from the face line
        if d > t / 2 + 0.08: continue
        sc = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
        s0, s1 = max(0, sc - o['width_m'] / 2), min(L, sc + o['width_m'] / 2)
        ff = CFG['finishFloor'].get(o['floor'])
        door = o['kind'] in ('door', 'sliding', 'vitrine') and ff is not None and o['sillRel'] <= ff + 0.05
        zlo, zhi = (z0 if door else max(z0, o['sillRel'])), min(z1, o['headRel'])
        if s1 - s0 < 0.02 or zhi - zlo < 0.02: continue
        out.append(dict(id=o['id'], s0=r3(s0), s1=r3(s1), z0=r3(zlo), z1=r3(zhi), kind=o['kind'], width=o['width_m'],
                        sill=o['sillRel'], head=o['headRel']))
    return out


GBEAMS = [b for b in FR['groundBeams'] if b.get('axisITM')]


def beam_rect(b):
    (x0, y0), (x1, y1) = b['axisITM'][0], b['axisITM'][-1]
    return block_rect((x0, y0), (x1, y1), b['width_m'])[0]


STACK = [dict(kind='wall', poly=s_['poly'], bottom=s_['bottom'], top=s_['top']) for s_ in SOL + INFILL] + \
        [dict(kind='beam', poly=beam_rect(b), bottom=b['bottomRel'], top=b['topRel']) for b in BEAMS + GBEAMS] + \
        [dict(kind='slab', poly=s_['poly'], bottom=s_['bottom'], top=s_['top']) for s_ in SLABS]


from shapely import affinity as shp_affinity
STACK_N = [(0, 0)]; STACK_PROUD = [0.0]


def stack(strip, z, way, limit, slabs=True, walls=True, outer=None):
    """follow the material behind a face (the strip 2 cm inside the wall) from level z up / down: a beam, slab or wall whose
    bottom (up) / top (down) meets z and covers most of the strip carries the face on – to its other end. Stops at limit,
    or where nothing is behind (no plaster on air)."""
    for _ in range(8):
        best = None
        for c in STACK:
            if c['kind'] == 'slab' and not slabs: continue
            if c['kind'] == 'wall' and (not walls or any(c['bottom'] <= zc <= c['top'] for zc in CFG['cuts'].values())): continue
            meet = c['bottom'] if way == 'up' else c['top']
            if abs(meet - z) > 0.05: continue
            nxt = c['top'] if way == 'up' else c['bottom']
            if (way == 'up' and nxt <= z + 0.01) or (way == 'down' and nxt >= z - 0.01): continue
            if c['poly'].intersection(strip).length < 0.5 * strip.length: continue
            # flush only: material that sticks out beyond the face (a wider beam / slab) has faces of its own
            if outer is not None and c['poly'].intersection(outer).length > 0.5 * outer.length: continue
            if best is None or (nxt > best if way == 'up' else nxt < best): best = nxt; best_c = c
        if best is None: break
        z = best
        if outer is not None:   # how far the stacked element stands proud of the face (≤ 2 cm) – the plaster is drawn in front of it
            for d in (0.02, 0.015, 0.01, 0.005):
                o2 = shp_affinity.translate(strip, *(lambda v: (v[0] * (0.02 + d), v[1] * (0.02 + d)))(STACK_N[0]))
                if best_c['poly'].intersection(o2).length > 0.5 * o2.length: STACK_PROUD[0] = max(STACK_PROUD[0], d); break
        if (way == 'up' and z >= limit) or (way == 'down' and z <= limit): break
    return min(z, limit) if way == 'up' else max(z, limit)


def standing_level(fl, flo, z0, side):
    """the level one stands on in front of the face: the finished floor of the floor when the face rises from its slab"""
    ff = CFG['finishFloor'].get(fl)
    if side == 'in' and flo and ff is not None and 0 <= ff - flo['top'] <= 0.3: return ff
    return flo['top'] if flo else z0


def face_record(fl, f, side, room, inside_left, z_cut):
    a, b = f['a'], f['b']; L = math.dist(a, b)
    if L < 0.03: return None
    if f['owner']['kind'] == 'opening':   # a gap in a concrete wall: the wall material over the head / under the sill only
        o = f['owner']; nx, ny = unit_normal(a, b, inside_left)
        strip = LineString([(a[0] - nx * 0.02, a[1] - ny * 0.02), (b[0] - nx * 0.02, b[1] - ny * 0.02)])
        m = ((a[0] + b[0]) / 2 + nx * 0.08, (a[1] + b[1]) / 2 + ny * 0.08); cei = ceiling_at(m, z_cut); flo = floor_at(m, z_cut)
        host = o.get('hostSolid') or {}
        parts = []
        if o['top'] < 90:
            zt = stack(strip, o['top'], 'up', cei['bottom'] if (cei and side == 'in') else 99)
            if zt - o['top'] > 0.02: parts.append((o['top'], zt))
            if flo and o['bottom'] - flo['top'] > 0.05:
                zb = stack(strip, o['bottom'], 'down', flo['top'])
                if o['bottom'] - zb > 0.02: parts.append((zb, o['bottom']))
        if not parts: return None
        z0, z1 = parts[0]
        ow = dict(id=host.get('id', o['id']), kind=host.get('kind', 'concrete'), floor=host.get('floor', fl), thickness=o['thickness'], src=host.get('src', o['src']))
        recs = []
        for z0, z1 in parts:
            g = L * (z1 - z0)
            recs.append(dict(kind='wall', floor=fl, side=side, room=room['key'] if room else None, roomName=room['name'] if room else None,
                             roomType=room['type'] if room else ('outdoor' if side == 'out' else None), owner=ow['id'], ownerKind=ow['kind'], ownerFloor=ow['floor'],
                             thickness=ow['thickness'], a=[r3(a[0]), r3(a[1])], b=[r3(b[0]), r3(b[1])], normal=[r3(nx), r3(ny)], length=r3(L), z0=r3(z0), z1=r3(z1),
                             gross=r3(g), openingsArea=0.0, net=r3(g), openings=[], overOpening=o['id'], floorSlab=flo['id'] if flo else None,
                             ceilingSlab=cei['id'] if cei else None, standing=r3(standing_level(fl, flo, z0, side)), source=ow['src'],
                             scaffold=False, scaffoldArea=0.0, **({'facade': facade_of(nx, ny)} if side == 'out' else {})))
        return recs
    nx, ny = unit_normal(a, b, inside_left)
    m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    probe = (m[0] + nx * 0.08, m[1] + ny * 0.08)       # just off the face, in the space it faces
    ow = f['owner']
    flo, cei = floor_at(probe, z_cut), ceiling_at(probe, z_cut)
    strip = LineString([(a[0] - nx * 0.02, a[1] - ny * 0.02), (b[0] - nx * 0.02, b[1] - ny * 0.02)])   # 2 cm into the wall
    outer = LineString([(a[0] + nx * 0.02, a[1] + ny * 0.02), (b[0] + nx * 0.02, b[1] + ny * 0.02)])  # 2 cm in front of it
    # the face runs on through flush beams / curbs above and below; slab edges and wider beams get faces of their own
    STACK_N[0] = (nx, ny); STACK_PROUD[0] = 0.0
    if side == 'in':
        z0 = max(stack(strip, ow['bottom'], 'down', flo['top'] if flo else -99, slabs=False, outer=outer), flo['top'] if flo else -99)
        z1 = min(stack(strip, ow['top'], 'up', cei['bottom'] if cei else 99, slabs=False, outer=outer), cei['bottom'] if cei else 99)
    else:   # façade (overlaps between floors clipped later)
        z0 = stack(strip, ow['bottom'], 'down', flo['top'] if flo else -99, slabs=False, outer=outer)
        z0 = max(z0, flo['top']) if flo else z0
        z1 = stack(strip, ow['top'], 'up', 99, slabs=False, outer=outer)
    if z1 - z0 < 0.05: return None
    ops = opening_cut(f, z0, z1, fl)
    gross = L * (z1 - z0)
    oa = sum((o['s1'] - o['s0']) * (o['z1'] - o['z0']) for o in ops
             if (o['s1'] - o['s0']) * (o['z1'] - o['z0']) >= TYPES['params']['openingMinArea_m2'])
    rec = dict(kind='wall', floor=fl, side=side, room=room['key'] if room else None, roomName=room['name'] if room else None,
               roomType=room['type'] if room else ('outdoor' if side == 'out' else None),
               owner=ow['id'], ownerKind=ow['kind'], ownerFloor=ow['floor'], thickness=ow['thickness'],
               a=[r3(a[0]), r3(a[1])], b=[r3(b[0]), r3(b[1])], normal=[r3(nx), r3(ny)], length=r3(L), z0=r3(z0), z1=r3(z1),
               gross=r3(gross), openingsArea=r3(oa), net=r3(gross - oa), openings=ops,
               floorSlab=flo['id'] if flo else None, ceilingSlab=cei['id'] if cei else None,
               standing=r3(standing_level(fl, flo, z0, side)), source=ow['src'], proud=r3(STACK_PROUD[0]))
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
    extra = []
    for f in mf:
        r = face_record(fl, f, side, room, inside_left, z) if f['owner'] else None
        if isinstance(r, list):   # material over / under a gap opening: no corner quantities of its own
            for x in r: x['meshV_m'] = 0.0; x['beads_m'] = 0.0; x['meshH_m'] = 0.0
            extra += r; r = None
        if r: r['meshV_m'] = 0.0; r['beads_m'] = 0.0; r['meshH_m'] = 0.0
        recs.append(r)
    FACES.extend(extra)
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
            C = C + [gp]; GAPCL.append(gp); GAPS.append(dict(id=gp['id'], floor=fl, itm=[r3(c.x), r3(c.y)], area_m2=r3(q.area)))
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


def clip_facade():
    """the same façade plane seen from two floor cuts (slab edge, beams carried up / down): the upper face starts where
    the lower one ends"""
    out = [f for f in FACES if f['side'] == 'out']
    out.sort(key=lambda f: f['z0'])
    for i, lo in enumerate(out):
        A, B = lo['a'], lo['b']; L = math.dist(A, B); ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
        for up in out[i + 1:]:
            if up is lo or up['z0'] >= lo['z1'] - 0.005 or up['z1'] <= lo['z1']: continue
            if abs(up['normal'][0] * lo['normal'][0] + up['normal'][1] * lo['normal'][1]) < 0.995: continue
            d = abs((up['a'][0] - A[0]) * -uy + (up['a'][1] - A[1]) * ux)
            if d > 0.03: continue
            s0 = sorted([(up['a'][0] - A[0]) * ux + (up['a'][1] - A[1]) * uy, (up['b'][0] - A[0]) * ux + (up['b'][1] - A[1]) * uy])
            ov = min(L, s0[1]) - max(0, s0[0])
            if ov < 0.5 * min(L, up['length']): continue
            up['z0'] = lo['z1']
    for f in out:   # re-measure the clipped faces
        if f['z1'] - f['z0'] < 0.05: f['drop'] = True; continue
        f['openings'] = opening_cut(f, f['z0'], f['z1'])
        f['gross'] = r3(f['length'] * (f['z1'] - f['z0']))
        f['openingsArea'] = r3(sum((o['s1'] - o['s0']) * (o['z1'] - o['z0']) for o in f['openings']))
        f['net'] = r3(f['gross'] - f['openingsArea'])
    FACES[:] = [f for f in FACES if not f.get('drop')]


clip_facade()
ROOM_BY = {r['key']: r for r in ROOMS}
PRM = TYPES['params']; WP = TYPES['waterproofing']


def seg_dist(pt, a, b):
    return LineString([a, b]).distance(Point(pt))


# ---------------------------------------------------------------- default plaster type of each wall face (rules)
def default_type(f):
    """all wall faces, block and concrete, inside and outside: cement plaster (Avihai 11.11); wet rooms: smoothed cement
    plaster under the waterproofing; basement walls against the soil: waterproofing + protection sheet, no plaster"""
    rt = f['roomType']
    if f['side'] == 'in':
        if rt == 'wet': return 'wet', 'חדר רטוב – טיח צמנטי מוחלק (לא גבס), האיטום מעליו'
        if rt in ('court', 'outdoor'): return 'exterior', 'חצר אנגלית / גג פתוח'
        if rt == 'kitchen':
            sinks = [x for x in FIX if x['floor'] == f['floor'] and x['kind'] in ('sink', 'kitchenPoint')]
            if sinks and min(seg_dist((x['E'], x['N']), f['a'], f['b']) for x in sinks) < CFG['sinkWall_m']:
                return 'wet', 'הקיר שמאחורי כיור המטבח – טיח צמנטי מוחלק'
        return 'interior', 'קיר פנים – טיח צמנטי'
    if f['floor'] == 'unit': return 'membrane', 'קיר מרתף במגע עם הקרקע: איטום + יריעת הגנה, בלי טיח (שכבת "איטום חיצוני לקירות המרתף")'
    return 'exterior', 'קיר חיצוני – טיח צמנטי (השליכט / החיפוי – בקטגוריית חיפויי חוץ)'


for f in FACES:
    f['defaultType'], f['typeReason'] = default_type(f)

# ---------------------------------------------------------------- waterproofing (over the smoothed cement plaster) – wet rooms
# walls: up to wetRoomHeight above the finished floor; in the shower zone (the stretch of wall in front of the shower
# point, ± showerZoneHalf_m – provisional, no shower layout in the sources) up to showerHeight; floors: the whole room.
WPROOF = []
for f in FACES:
    if f['side'] != 'in' or f['roomType'] != 'wet': continue
    room = ROOM_BY[f['room']]; ff = CFG['finishFloor'].get(f['floor'], f['standing'])
    # the strip starts at the room's slab even where the face itself starts higher (an upturned beam / curb under the face): no gap
    # at the floor (round 4 – waterproofing check)
    wz0 = min(f['z0'], SLAB_BY[f['floorSlab']]['top']) if f.get('floorSlab') in SLAB_BY else f['z0']
    A, B = f['a'], f['b']; L = f['length']; ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
    showers = [x for x in FIX if x['floor'] == f['floor'] and x['kind'] == 'shower' and room['poly'].buffer(CFG['fixtureReach_m']).contains(Point(x['E'], x['N']))]
    cuts = []   # shower stretches along the face [s0, s1]
    for x in showers:
        if seg_dist((x['E'], x['N']), A, B) > CFG['showerWall_m']: continue
        sc = (x['E'] - A[0]) * ux + (x['N'] - A[1]) * uy
        lo, hi = max(0, sc - WP['showerZoneHalf_m']), min(L, sc + WP['showerZoneHalf_m'])
        if hi - lo > 0.05: cuts.append((lo, hi))
    if f['owner'] in room['showerFaces']: cuts = [(0, L)]
    marks = sorted({0, L, *[c for ab in cuts for c in ab]})
    for s0, s1 in zip(marks, marks[1:]):
        if s1 - s0 < 0.02: continue
        sh = any(lo <= (s0 + s1) / 2 <= hi for lo, hi in cuts)
        h = WP['showerHeight_m'] if sh else WP['wetRoomHeight_m']
        z1 = min(f['z1'], ff + h)
        # kept even when the face starts above the waterproofing (z1 <= z0, area 0): the heights can be raised from the panel
        doors = sum(max(0, min(o['s1'], s1) - max(o['s0'], s0)) for o in f['openings'] if o['z0'] <= f['z0'] + 0.01)
        pa = [r3(A[0] + ux * s0), r3(A[1] + uy * s0)]; pb = [r3(A[0] + ux * s1), r3(A[1] + uy * s1)]
        WPROOF.append(dict(kind='wall', floor=f['floor'], room=f['room'], owner=f['owner'], a=pa, b=pb, normal=f['normal'],
                           s0=r3(s0), s1=r3(s1), z0=r3(wz0), z1=r3(z1), height_m=h, shower=sh, finish=r3(ff), faceTop=f['z1'], area=r3(max(0, (s1 - s0 - doors) * (z1 - wz0))),
                           openings=[dict(o, s0=r3(max(o['s0'], s0) - s0), s1=r3(min(o['s1'], s1) - s0)) for o in f['openings'] if o['z0'] <= f['z0'] + 0.01 and min(o['s1'], s1) > max(o['s0'], s0)],
                           label=f"איטום {round(h * 100):.0f} ס\"מ", rule=(f"אזור מקלחת – עד {h:.2f} מ' מפני הריצוף" if sh else f"{h:.2f} מ' מפני הריצוף"),
                           status='provisional'))   # the heights are defaults (types.json waterproofing.status) – open-issues #156, #166

# ---------------------------------------------------------------- ceilings: room split by the slabs above (lowest first)
CEILS = []
for fl in FLOORS:
    for room in [r for r in ROOMS if r['floor'] == fl and r['type'] not in ('court', 'outdoor')]:   # open to the sky: no ceiling
        z = CFG['cuts'][fl]; rem = room['poly']
        for sl in sorted([s for s in SLABS if s['bottom'] >= z], key=lambda s: s['bottom']):
            free = sl['poly']
            for c in CLAIMED[sl['id']]: free = free.difference(c)
            pc = rem.intersection(free)
            if pc.area < 0.05: continue
            CLAIMED[sl['id']].append(pc); rem = rem.difference(pc)
            st = sl['bottom'] - (floor_at(pc.representative_point().coords[0], z) or {'top': z})['top']
            st = sl['bottom'] - (CFG['finishFloor'].get(fl, sl['bottom'] - st))
            rt = room['type']
            dt = ('skim', 'תקרת ממ"ד – שפכטל בלבד (אסור טיח)') if rt == 'mamad' else ('interior', 'תקרה – טיח צמנטי')
            for g in getattr(pc, 'geoms', [pc]):
                if g.geom_type != 'Polygon' or g.area < 0.05: continue
                g = clean(g)
                if g.geom_type != 'Polygon': continue
                CEILS.append(dict(kind='ceiling', floor=fl, room=room['key'], roomName=room['name'], roomType=rt, slab=sl['id'], z=sl['bottom'],
                                  ringITM=[[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]],
                                  holesITM=[[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in g.interiors],
                                  area=r3(g.area), net=r3(g.area), scaffold=st > PRM['scaffoldAbove_m'] + 1e-6,
                                  scaffoldArea=r3(g.area) if st > PRM['scaffoldAbove_m'] + 1e-6 else 0, height=r3(st),
                                  defaultType=dt[0], typeReason=dt[1], source=sl['src']))
        room['ceilingUncovered_m2'] = r3(rem.area)

# ---------------------------------------------------------------- tops of free-standing walls (parapets, low walls): under the coping
TOPS = []
for sd in SOL:
    if sd['kind'] not in ('concrete', 'block') or sd['floor'] == 'unit': continue
    c = sd['poly'].representative_point().coords[0]
    over = [s for s in SLABS if abs(s['bottom'] - sd['top']) < CFG['beamFlushMax_m'] and s['poly'].buffer(0.05).contains(Point(c))]
    if over or any(abs(b['bottomRel'] - sd['top']) < 0.02 and LineString(b['axisITM']).buffer(b['width_m'] / 2 + 0.05).contains(Point(c)) for b in BEAMS): continue
    # a wall standing on another one carries it: not a free top
    if any(o is not sd and o['kind'] in ('concrete', 'block') and abs(o['bottom'] - sd['top']) < 0.3 and o['poly'].intersection(sd['poly']).area > 0.5 * sd['poly'].area for o in SOL): continue
    # a wall top at the level of a slab next to it is part of the floor – no plaster on floors
    if any(abs(sl['top'] - sd['top']) < 0.06 and sl['poly'].distance(sd['poly']) < 0.05 for sl in SLABS): continue
    for g_ in getattr(sd['poly'], 'geoms', [sd['poly']]):   # every part of the wall
        if g_.area < 0.005: continue
        g_ = clean(g_)
        if g_.geom_type != 'Polygon': g_ = max(g_.geoms, key=lambda q: q.area)
        TOPS.append(dict(kind='top', floor=sd['floor'], owner=sd['id'], ownerKind=sd['kind'], z=sd['top'], area=r3(g_.area),
                         ringITM=[[r3(x), r3(y)] for x, y in list(g_.exterior.coords)[:-1]],
                         holesITM=[[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in g_.interiors],
                         defaultType='exterior', typeReason='ראש קיר / מעקה מתחת לקופינג', scaffold=False, source=sd['src']))

# ---------------------------------------------------------------- courtyard walls (site): the plot side plastered; street side stone cladding; neighbour side nothing
DEV = J('data/site/development-heights.json')['spots']
H0 = ORIGIN['H0']
PLOT = Polygon(J('data/site/plot-5187.json')['ring'])
PARCELS = [(Polygon(p_['ring']), p_['use']) for p_ in J('data/site/parcels.json')['parcels']]
CLAD = []
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
        if PLOT.contains(Point(probe)): side, dt = 'plot', ('exterior', 'חומה – צד המגרש: טיח צמנטי (שליכט בהמשך – חיפויי חוץ)')
        else:
            use = next((u for pg, u in PARCELS if pg.contains(Point(probe))), None)
            side, dt = ('street', ('cladding', 'חומה לרחוב – צד הרחוב: חיפוי אבן, בלי טיח (אביחי 11.11)')) if use == 'public' else \
                       ('neighbour', ('none', 'חומה עם השכן – צד השכן: בלי טיח (אביחי 11.11)'))
        sl = floor_at(probe, w['topRel'])
        if sl: z0, zs = sl['top'], 'רצפת חוץ ' + sl['id']
        else:
            sp = min(DEV, key=lambda s: math.dist((s['E'], s['N']), probe))
            dd = math.dist((sp['E'], sp['N']), probe)
            z0, zs = (r3(sp['z'] - H0), f"נקודת גובה פיתוח {sp['z']:.2f} ({dd:.1f} מ')") if dd < 4 else (w['bottomRel'], 'אין גובה קרקע – ראש היסוד')
        z0 = max(z0, w['bottomRel'])
        if w['topRel'] - z0 < 0.05: continue
        rec = dict(kind='wall', floor='site', side='out', wallSide=side, room=None, roomName=None, roomType='outdoor', owner=w['id'], ownerKind='concrete',
                   ownerFloor='site', thickness=w['thickness_m'], a=[r3(a[0]), r3(a[1])], b=[r3(b[0]), r3(b[1])], normal=[r3(nx), r3(ny)],
                   length=r3(L), z0=r3(z0), z1=w['topRel'], gross=r3(L * (w['topRel'] - z0)), openingsArea=0, net=r3(L * (w['topRel'] - z0)),
                   openings=[], floorSlab=sl['id'] if sl else None, ceilingSlab=None, standing=r3(z0), source=w['source'],
                   scaffold=w['topRel'] - z0 > PRM['scaffoldAbove_m'], scaffoldArea=r3(L * max(0, w['topRel'] - z0 - PRM['scaffoldAbove_m'])), facade=facade_of(nx, ny),
                   meshV_m=0, beads_m=0, meshH_m=0, defaultType=dt[0], typeReason=dt[1], zSource=zs,
                   status='provisional' if 'אין' in zs or 'נקודת' in zs or side == 'neighbour' else 'source')
        FACES.append(rec)
        if side == 'street':
            CLAD.append(dict(kind='claddingStone', owner=w['id'], a=rec['a'], b=rec['b'], normal=rec['normal'], z0=rec['z0'], z1=rec['z1'], area=rec['net'],
                             color=None, source='החלטת אביחי 11.11.2026 – צד הרחוב של החומה לרחוב: חיפוי אבן; גבהים – ' + zs, status='owner'))
    TOPS.append(dict(kind='top', floor='site', owner=w['id'], ownerKind='concrete', z=w['topRel'], area=r3(P.area),
                     ringITM=[[r3(x), r3(y)] for x, y in list(P.exterior.coords)[:-1]], defaultType='exterior',
                     typeReason='ראש חומה מתחת לקופינג', scaffold=False, source=w['source']))

# ---------------------------------------------------------------- reveals: jambs and head of every opening, in the wall depth (no sill)
CLOSER_T = {c['id']: c['thickness'] for c in CLOSERS}
REV = {}
for f in sorted(FACES, key=lambda f: f['side'] != 'in'):
    if f['floor'] == 'site': continue
    A, B = f['a'], f['b']; L = f['length']; ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L; nx, ny = f['normal']
    for o in f['openings']:
        if o['id'] in REV: continue
        t = f['thickness'] or CLOSER_T.get(o['id']) or 0.2
        P_ = lambda s_, d_, z_: [r3(A[0] + ux * s_ - nx * d_), r3(A[1] + uy * s_ - ny * d_), r3(z_)]
        quads = []
        if o['s0'] > 0.01: quads.append(dict(part='jamb', q=[P_(o['s0'], 0, o['z0']), P_(o['s0'], t, o['z0']), P_(o['s0'], t, o['z1']), P_(o['s0'], 0, o['z1'])]))
        if o['s1'] < L - 0.01: quads.append(dict(part='jamb', q=[P_(o['s1'], 0, o['z0']), P_(o['s1'], t, o['z0']), P_(o['s1'], t, o['z1']), P_(o['s1'], 0, o['z1'])]))
        if o['z1'] < f['z1'] - 0.01: quads.append(dict(part='head', q=[P_(o['s0'], 0, o['z1']), P_(o['s1'], 0, o['z1']), P_(o['s1'], t, o['z1']), P_(o['s0'], t, o['z1'])]))
        h = o['z1'] - o['z0']; w = o['s1'] - o['s0']
        area = sum(h * t if q['part'] == 'jamb' else w * t for q in quads)
        if not quads: continue
        REV[o['id']] = dict(kind='reveal', opening=o['id'], openingKind=o['kind'], floor=f['floor'], room=f['room'], roomType=f['roomType'], width=r3(w), height=r3(h),
                            depth=r3(t), area=r3(area), net=r3(area), quads=quads, host=f['owner'], scaffold=False, scaffoldArea=0,
                            beads=r3(sum((h if q['part'] == 'jamb' else w) * 2 for q in quads) if PRM['beadsAtOpenings'] else 0),
                            defaultType=f['defaultType'] if f['side'] == 'in' and f['defaultType'] in ('interior', 'wet', 'exterior') else 'exterior',
                            typeReason='גליף – צדי הפתח והמשקוף בעומק הקיר (בלי אדן)', source=f['source'])
# ---------------------------------------------------------------- exposed beams: sides, soffit, top (ceiling beams + ground beams that rise above the slab)
from shapely.prepared import prep
OCC = [dict(kind='wall', P=prep(s_['poly']), poly=s_['poly'], bottom=s_['bottom'], top=s_['top'], id=s_['id']) for s_ in SOL] + \
      [dict(kind='slab', P=prep(s_['poly']), poly=s_['poly'], bottom=s_['bottom'], top=s_['top'], id=s_['id']) for s_ in SLABS]
BEAM_LIST = [dict(b_, src=b_['source'], ground=False) for b_ in BEAMS] + [dict(b_, src=b_['source'], ground=True, floorOf='ground') for b_ in GBEAMS]
for b_ in BEAM_LIST: b_['R'] = beam_rect(b_); b_['P'] = prep(b_['R'])
NEXT_FINISH = {'unit': CFG['finishFloor']['ground'], 'ground': CFG['finishFloor']['first'], 'first': 6.9}


def room_at(pt, z):
    """the room a point at height z belongs to (interior) – or None (outside)"""
    for r in ROOMS:
        fl = r['floor']
        if fl == 'roof' or r['type'] in ('court', 'outdoor'): continue
        lo = CFG['finishFloor'].get(fl, -9) - 0.5; hi = NEXT_FINISH.get(fl, 99)
        if lo <= z <= hi and r['poly'].contains(Point(pt)): return r
    return None


def floor_of_z(z):
    for fl in ('unit', 'ground', 'first'):
        if z < NEXT_FINISH[fl] - 0.05: return fl
    return 'roof'


FGRID = defaultdict(list)
for f_ in FACES:
    for gx in range(int(min(f_['a'][0], f_['b'][0]) // 2) - 1, int(max(f_['a'][0], f_['b'][0]) // 2) + 2):
        for gy in range(int(min(f_['a'][1], f_['b'][1]) // 2) - 1, int(max(f_['a'][1], f_['b'][1]) // 2) + 2): FGRID[(gx, gy)].append(f_)


def face_cover(pt, n):
    """z ranges of wall faces that already plaster the spot pt (within 3 cm, facing the same way)"""
    out = []
    for f_ in FGRID[(int(pt[0] // 2), int(pt[1] // 2))]:
        if f_['normal'][0] * n[0] + f_['normal'][1] * n[1] < 0.9: continue
        if LineString([f_['a'], f_['b']]).distance(Point(pt)) < 0.03: out.append((f_['z0'], f_['z1']))
    return out


BEAMSURF = []
for k, bm in enumerate(BEAM_LIST):
    R, bz, tz = bm['R'], bm['bottomRel'], bm['topRel']
    others = [x for j, x in enumerate(BEAM_LIST) if j != k]
    if bm['ground']:   # floor beams: only what rises above the slab next to them
        c = R.centroid
        sl = [s_['top'] for s_ in SLABS if s_['top'] <= tz + 0.01 and s_['poly'].distance(R) < 0.3]
        if not sl or tz - min(sl) < 0.05: continue
        bz = max(bz, min(sl))   # below the lowest slab next to it: soil
    touch = lambda o: (o['bottom'] < tz - 0.02 and o['top'] > bz + 0.02) or abs(o['top'] - bz) < 0.05 or abs(o['bottom'] - tz) < 0.05
    # inside a wall / standing on a wall: the wall faces carry the plaster over the beam there
    inwall = [o for o in OCC if o['kind'] == 'wall' and touch(o)]
    quads = []
    pts = list(R.exterior.coords)[:4]
    for i in range(4):
        A, B = pts[i], pts[(i + 1) % 4]; L = math.dist(A, B)
        if L < 0.03: continue
        ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
        nx, ny = unit_normal(A, B, not LinearRingCCW(R))   # outward
        n = max(1, int(L / 0.1)); ds = L / n; run = None
        for j in range(n):
            sm = (j + 0.5) * ds
            pin = Point(A[0] + ux * sm - nx * 0.01, A[1] + uy * sm - ny * 0.01); pout = Point(A[0] + ux * sm + nx * 0.02, A[1] + uy * sm + ny * 0.02)
            q = (A[0] + ux * sm + nx * 0.05, A[1] + uy * sm + ny * 0.05)
            iv = []
            # exposed where it faces air; minus the part a wall face already plasters at this very spot (flush wall faces that
            # run on through the beam) – no gap, no double count
            if True:
                iv = [[bz, tz]]
                for o in OCC + [dict(P=x['P'], bottom=x['bottomRel'], top=x['topRel']) for x in others]:
                    if o['top'] <= bz or o['bottom'] >= tz or not o['P'].contains(Point(q)): continue
                    nv = []
                    for lo, hi in iv:
                        if o['bottom'] > lo: nv.append([lo, min(hi, o['bottom'])])
                        if o['top'] < hi: nv.append([max(lo, o['top']), hi])
                    iv = [v for v in nv if v[1] - v[0] > 0.02]
                pp = (A[0] + ux * sm, A[1] + uy * sm)
                for fz0, fz1 in face_cover(pp, (nx, ny)):
                    nv = []
                    for lo, hi in iv:
                        if fz0 > lo: nv.append([lo, min(hi, fz0)])
                        if fz1 < hi: nv.append([max(lo, fz1), hi])
                    iv = [v for v in nv if v[1] - v[0] > 0.02]
            key_ = tuple((r3(lo), r3(hi)) for lo, hi in iv)
            if run and run[2] == key_: run[1] = (j + 1) * ds
            else:
                if run and run[2]: quads.append((A, ux, uy, nx, ny) + tuple(run))
                run = [j * ds, (j + 1) * ds, key_]
        if run and run[2]: quads.append((A, ux, uy, nx, ny) + tuple(run))
    sides = []
    for A, ux, uy, nx, ny, s0, s1, ivs in quads:
        for lo, hi in ivs:
            pa = [r3(A[0] + ux * s0), r3(A[1] + uy * s0)]; pb = [r3(A[0] + ux * s1), r3(A[1] + uy * s1)]
            mid = ((pa[0] + pb[0]) / 2 + nx * 0.1, (pa[1] + pb[1]) / 2 + ny * 0.1)
            sides.append(dict(a=pa, b=pb, normal=[r3(nx), r3(ny)], z0=lo, z1=hi, area=r3((s1 - s0) * (hi - lo)), room=(room_at(mid, (lo + hi) / 2) or {}).get('key')))
    # soffit and top: what is not resting on / carrying something
    cov_b = [o['poly'] for o in OCC if (o['kind'] == 'wall' and touch(o)) or (o['kind'] == 'slab' and o['bottom'] - 0.05 <= bz <= o['top'] + 0.05)] + \
            [x['R'] for j, x in enumerate(BEAM_LIST) if j < k and x['bottomRel'] - 0.05 <= bz <= x['topRel'] + 0.05]
    cov_t = [o['poly'] for o in OCC if (o['kind'] == 'wall' and (touch(o) or o['bottom'] <= tz + 0.01 < o['top'])) or (o['kind'] == 'slab' and o['bottom'] - 0.05 <= tz <= o['top'] + 0.05)] + \
            [x['R'] for j, x in enumerate(BEAM_LIST) if j < k and x['bottomRel'] - 0.05 <= tz <= x['topRel'] + 0.05]
    bot = R.difference(unary_union(cov_b)) if (cov_b and not bm['ground']) else (Polygon() if bm['ground'] else R)
    top = R.difference(unary_union(cov_t)) if cov_t else R
    flats = []
    for g, z_, part in [(bot, bz, 'soffit'), (top, tz, 'top')]:
        for q in getattr(g, 'geoms', [g]):
            if q.geom_type != 'Polygon' or q.area < 0.01: continue
            q = clean(q)
            if q.geom_type != 'Polygon': continue
            flats.append(dict(part=part, z=r3(z_), ringITM=[[r3(x), r3(y)] for x, y in list(q.exterior.coords)[:-1]], area=r3(q.area),
                              room=(room_at(q.representative_point().coords[0], z_ - 0.05 if part == 'soffit' else z_ + 0.05) or {}).get('key')))
    if not sides and not flats: continue
    area = sum(x['area'] for x in sides) + sum(x['area'] for x in flats)
    zin = [x for x in sides + flats if x['room']]
    room = max(zin, key=lambda x: x['area'])['room'] if zin else None
    fl = floor_of_z((bz + tz) / 2)
    BEAMSURF.append(dict(kind='beam', beam=bm['id'], floor=fl, room=room, roomType=ROOM_BY[room]['type'] if room else 'outdoor',
                         width=bm['width_m'], bottom=r3(bz), top=r3(tz), pergola=bool(bm.get('pergola')), sides=sides, flats=flats,
                         area=r3(area), net=r3(area), scaffold=tz - CFG['finishFloor'].get(fl, bz) > PRM['scaffoldAbove_m'],
                         scaffoldArea=r3(area) if tz - CFG['finishFloor'].get(fl, bz) > PRM['scaffoldAbove_m'] else 0,
                         defaultType='interior' if room and ROOM_BY[room]['type'] != 'wet' else ('wet' if room else 'exterior'),
                         typeReason=('קורה גלויה בתוך החדר' if room else 'קורה גלויה מבחוץ / פרגולה') + ' – טיח צמנטי', source=bm['src']))


# ---------------------------------------------------------------- slab edges: the band of every ceiling slab that is not hidden by a wall / slab / beam next to it
EDGE_SLABS = [s_ for s_ in SLABS if s_['id'][:2] in ('FS', 'RS')] + [s_ for s_ in SLABS if s_['id'][:2] == 'GS']
OPENAIR = COURTS + STAIR
for sl in EDGE_SLABS:
    ground = sl['id'][:2] == 'GS'
    for ring in [r_ for g in getattr(sl['poly'], 'geoms', [sl['poly']]) for r_ in [g.exterior] + list(g.interiors)]:
        pts = list(ring.coords)
        sides = []
        for A, B in zip(pts, pts[1:]):
            L = math.dist(A, B)
            if L < 0.03: continue
            ux, uy = (B[0] - A[0]) / L, (B[1] - A[1]) / L
            nx, ny = unit_normal(A, B, True)
            if sl['poly'].contains(Point((A[0] + B[0]) / 2 + nx * 0.03, (A[1] + B[1]) / 2 + ny * 0.03)): nx, ny = -nx, -ny   # outward
            n = max(1, int(L / 0.1)); ds = L / n; run = None
            for j in range(n):
                sm = (j + 0.5) * ds; q = Point(A[0] + ux * sm + nx * 0.03, A[1] + uy * sm + ny * 0.03)
                iv = []
                if not ground or any(o.contains(q) for o in OPENAIR):
                    iv = [[sl['bottom'], sl['top']]]
                    for o in OCC + [dict(P=x['P'], bottom=x['bottomRel'], top=x['topRel']) for x in BEAM_LIST]:
                        if o.get('id') == sl['id'] or o['top'] <= sl['bottom'] or o['bottom'] >= sl['top'] or not o['P'].contains(q): continue
                        nv = []
                        for lo, hi in iv:
                            if o['bottom'] > lo: nv.append([lo, min(hi, o['bottom'])])
                            if o['top'] < hi: nv.append([max(lo, o['top']), hi])
                        iv = [v for v in nv if v[1] - v[0] > 0.02]
                key_ = tuple((r3(lo), r3(hi)) for lo, hi in iv)
                if run and run[2] == key_: run[1] = (j + 1) * ds
                else:
                    if run and run[2]: sides.append((A, ux, uy, nx, ny) + tuple(run))
                    run = [j * ds, (j + 1) * ds, key_]
            if run and run[2]: sides.append((A, ux, uy, nx, ny) + tuple(run))
        for A, ux, uy, nx, ny, s0, s1, ivs in sides:
            for lo, hi in ivs:
                pa = [r3(A[0] + ux * s0), r3(A[1] + uy * s0)]; pb = [r3(A[0] + ux * s1), r3(A[1] + uy * s1)]
                if s1 - s0 < 0.05: continue
                mid = ((pa[0] + pb[0]) / 2 + nx * 0.1, (pa[1] + pb[1]) / 2 + ny * 0.1)
                rm = room_at(mid, (lo + hi) / 2)
                area = r3((s1 - s0) * (hi - lo)); fl = floor_of_z(lo + 0.01)
                BEAMSURF.append(dict(kind='slabEdge', edge=True, beam=sl['id'], floor=fl, room=rm['key'] if rm else None, roomType=rm['type'] if rm else 'outdoor',
                                     width=None, bottom=r3(lo), top=r3(hi), pergola=False, flats=[],
                                     sides=[dict(a=pa, b=pb, normal=[r3(nx), r3(ny)], z0=lo, z1=hi, area=area, room=rm['key'] if rm else None)],
                                     area=area, net=area, scaffold=hi - CFG['finishFloor'].get(fl, lo) > PRM['scaffoldAbove_m'],
                                     scaffoldArea=area if hi - CFG['finishFloor'].get(fl, lo) > PRM['scaffoldAbove_m'] else 0,
                                     defaultType=('wet' if rm and rm['type'] == 'wet' else 'interior') if rm else 'exterior',
                                     typeReason='שפת תקרה גלויה – טיח צמנטי', source=sl['src']))

# ---------------------------------------------------------------- jambs of openings that are gaps in concrete walls (no reveal from a wall face)
for c in CLOSERS + GAPCL:
    oid = c['id']
    have = [q for q in REV[oid]['quads'] if q['part'] == 'jamb'] if oid in REV else []
    R = c['poly'] if c['poly'].geom_type == 'Polygon' else max(c['poly'].geoms, key=lambda g: g.area)
    mr = R.minimum_rotated_rectangle; pts = list(mr.exterior.coords)[:4]
    edges = sorted([(pts[i], pts[(i + 1) % 4]) for i in range(4)], key=lambda e: math.dist(*e))
    short = edges[:2]; t = math.dist(*short[0])
    if t < 0.05 or t > 0.8: continue
    cen = R.centroid; fl = c['floor']; zc = CFG['cuts'].get(fl)
    if zc is None: continue
    flo, cei = floor_at((cen.x, cen.y), zc), ceiling_at((cen.x, cen.y), zc)
    z0 = flo['top'] if flo else c['bottom']; z0 = max(z0, c['bottom']) if c['bottom'] > -90 else z0
    if c['bottom'] > -90 and c['bottom'] <= CFG['finishFloor'].get(fl, -9) + 0.05: z0 = flo['top'] if flo else c['bottom']   # doors to the slab
    z1 = min(c['top'] if c['top'] < 90 else 99, cei['bottom'] if cei else 99)
    # nothing modelled over the head (the gap runs to the wall top in the data): the jamb runs up to the wall top / ceiling
    hostTop = max([x['top'] for x in SOL if x['poly'].distance(R) < 0.05 and x['bottom'] < z1] or [z1])
    over = [x for x in STACK if x['kind'] in ('wall', 'beam') and abs(x['bottom'] - z1) < 0.05 and x['poly'].intersects(R)]
    if c['top'] < 90 and not over: z1 = min(hostTop, cei['bottom'] if cei else 99)
    if z1 > 90 or z1 - z0 < 0.1: continue
    quads = []
    for A, B in short:
        m = ((A[0] + B[0]) / 2, (A[1] + B[1]) / 2); d = (m[0] - cen.x, m[1] - cen.y); Ld = math.hypot(*d) or 1
        beyond = Point(m[0] + d[0] / Ld * 0.03, m[1] + d[1] / Ld * 0.03)
        if not any(x['poly'].contains(beyond) for x in SOL if x['bottom'] < z1 and x['top'] > z0): continue   # no wall there: no jamb
        near = [h_ for h_ in have if LineString([h_['q'][0][:2], h_['q'][1][:2]]).distance(Point(m)) < 0.12]
        spans = [(z0, z1)]
        if near:   # the wall face already gave this jamb – only what it misses (e.g. above a head that has no lintel in the data)
            lo_, hi_ = min(q['q'][0][2] for q in near), max(q['q'][2][2] for q in near)
            spans = [(a_, b_) for a_, b_ in ((z0, lo_), (hi_, z1)) if b_ - a_ > 0.02]
        for za, zb in spans:
            quads.append(dict(part='jamb', q=[[r3(A[0]), r3(A[1]), r3(za)], [r3(B[0]), r3(B[1]), r3(za)], [r3(B[0]), r3(B[1]), r3(zb)], [r3(A[0]), r3(A[1]), r3(zb)]]))
    if oid not in REV and c['top'] < 90 and cei and c['top'] < cei['bottom'] - 0.02 and quads and over:
        P4 = [[r3(x), r3(y), r3(c['top'])] for x, y in pts]
        quads.append(dict(part='head', q=P4))
    if not quads: continue
    if oid in REV:   # add the missing jamb(s) to the reveal found from the wall face
        R_ = REV[oid]; a_ = sum((q['q'][2][2] - q['q'][0][2]) * t for q in quads)
        R_['quads'] += quads; R_['area'] = r3(R_['area'] + a_); R_['net'] = R_['area']
        R_['beads'] = r3(R_['beads'] + sum((q['q'][2][2] - q['q'][0][2]) * 2 for q in quads)); continue
    h_ = z1 - z0; w_ = math.dist(*edges[2])
    area = sum(((q['q'][2][2] - q['q'][0][2]) if q['part'] == 'jamb' else w_) * t for q in quads)
    rm = room_at((cen.x, cen.y), z0 + 1.0)
    REV[oid] = dict(kind='reveal', opening=oid, openingKind=next((o['kind'] for o in OP if o['id'] == oid), 'gap'), floor=fl, room=rm['key'] if rm else None,
                    roomType=rm['type'] if rm else 'outdoor', width=r3(w_), height=r3(h_), depth=r3(t), area=r3(area), net=r3(area), quads=quads,
                    host=(c.get('hostSolid') or {}).get('id'), scaffold=False, scaffoldArea=0,
                    beads=r3(sum((h_ if q['part'] == 'jamb' else w_) * 2 for q in quads) if PRM['beadsAtOpenings'] else 0),
                    defaultType=('wet' if rm and rm['type'] == 'wet' else 'interior') if rm else 'exterior',
                    typeReason='גליף של פתח בקיר בטון – צדי הפתח (והמשקוף)', source=c['src'])


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
REVS = list(REV.values()); keyed(REVS, lambda r: f"{r['floor']}|rev|{r['opening']}")
keyed(BEAMSURF, lambda b: f"{b['floor']}|beam|{b['beam']}")

# ---------------------------------------------------------------- patches (plaster round 4): the exposed skin of the skeleton that no surface
# above covers – sills, slab edges at level steps, niches, the ends of walls, soffits outside, ledges (tools/finishes/skin.py; check:
# tools/finishes/verify_coverage.py, 2 cm grid – must be 0)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skin as SKIN
SKIN_S, SKIN_RES = SKIN.analyse(globals(), grid=CFG.get('skinGrid_m', 0.02))
PATCHES = SKIN.make_patches(SKIN_S, SKIN_RES, globals())
PATCHES.sort(key=lambda p_: (p_['floor'], p_['owner'] or '', p_['z0'] if p_['vertical'] else p_['z'], (p_['a'] if p_['vertical'] else p_['ringITM'][0])[0]))
keyed(PATCHES, lambda p_: f"{p_['floor']}|patch|{p_['owner'] or 'x'}|{p_['part']}")

# ---------------------------------------------------------------- one plane per wall surface (12.11.2026): steps between neighbouring elements up to
# flattenMax_m are taken up by the plaster thickness – the faces brought to the most proud one, the step faces hidden, corners closed (tools/finishes/flatten.py)
import flatten as FLAT
FLAT_RES = FLAT.flatten(globals(), CFG.get('flattenMax_m', 0.08), J('data/config/display.json')['finishes']['offset_m'])
print('flatten:', {k: v for k, v in FLAT_RES.items() if k != 'report'})
DISP_F = J('data/config/display.json')['finishes']
FILLERS = FLAT.fillers(globals(), DISP_F['offset_m'], DISP_F.get('seamOverlap_m', 0), CFG.get('flattenMax_m', 0.08))
print('fillers:', len(FILLERS), round(sum(f['length'] * (f['z1'] - f['z0']) for f in FILLERS), 3), 'm2 (display only)')

# ---------------------------------------------------------------- floors: area per room, skirting, the floor build-up layers (no plaster on floors)
BU = J('data/finishes/floors/buildup.json')
TZ = CFG.get('tilingZones', {})
TZ_EX = set(TZ.get('excludeSlabs', {}))
TILES = []


def wall_skirting(fl, parts, z_at):
    """skirting of a floor part by geometry: its outline along the walls standing on it, less the door / vitrine widths (a room mostly void, a balcony)"""
    S, C = solids_at(fl, z_at)
    W = unary_union([x['poly'] for x in S if x['kind'] in ('concrete', 'block', 'column')]).buffer(0.03)
    L = sum(g.exterior.intersection(W).length for g in parts)
    dw = sum(o['width_m'] for o in OP if o['floor'] == fl and o['kind'] in ('door', 'sliding', 'vitrine') and not o['id'].startswith('OC-')
             and any(g.exterior.distance(Point(o['centerITM'])) < 0.4 for g in parts))
    return max(0, L - dw)


for room in ROOMS:
    fl = room['floor']; z = CFG['cuts'][fl]
    own = [s for s in SLABS if s['top'] < z and s['top'] > z - 3.0 and s['id'] not in TZ_EX]
    # the floor slab = the one under a sample point of the room; a room that is mostly void (the first-floor gallery round the
    # double-height space – its sample point falls in the void): the slab under most of it
    top = max([s['top'] for s in own if s['poly'].buffer(0.02).contains(room['poly'].representative_point())] or [None]) if own else None
    if top is None and room['type'] not in ('court', 'outdoor'):
        cov = sorted(((s['poly'].intersection(room['poly']).area, s['top']) for s in own), reverse=True)
        top = cov[0][1] if cov and cov[0][0] > 0.5 else None
    on = unary_union([s['poly'] for s in own if top is not None and abs(s['top'] - top) < 0.6]) if top is not None else Polygon()
    pc = room['poly'].intersection(on) if not on.is_empty else Polygon()
    faces = [f for f in FACES if f['room'] == room['key'] and f['side'] == 'in']
    doors = sum(o['s1'] - o['s0'] for f in faces for o in f['openings'] if o['z0'] <= f['z0'] + 0.01)
    skirting = sum(f['length'] for f in faces) - doors
    wet = room['type'] in ('wet',)
    parts = [clean(g) for g in getattr(pc, 'geoms', [pc]) if g.geom_type == 'Polygon' and g.area > 0.05] if not pc.is_empty else []
    parts = [g for g in parts if g.geom_type == 'Polygon']
    ff = CFG['finishFloor'].get(fl)
    layers = []
    if parts and ff is not None and top is not None and room['type'] not in ('court', 'outdoor'):
        tot = ff - top; fixed = sum(l['thickness_m'] for l in BU['layers'] if l['thickness_m'])
        zc = top
        for l in BU['layers']:
            th = l['thickness_m'] if l['thickness_m'] is not None else tot - fixed
            layers.append(dict(id=l['id'], z0=r3(zc), z1=r3(zc + th), thickness_m=r3(th), status=l['status'])); zc += th
    mostlyVoid = bool(parts) and room['area_m2'] - pc.area > 0.5 * room['area_m2']
    if mostlyVoid: skirting = wall_skirting(fl, parts, z)   # the faces of such a room run round the void too – only the walls on its floor count
    TILES.append(dict(room=room['key'], floor=fl, roomName=room['name'], zoneName=TZ.get('names', {}).get(room['key']), roomType=room['type'], area=r3(pc.area),
                      void_m2=r3(room['area_m2'] - pc.area), slabTop=top, finishRel=ff, buildUp_m=r3(ff - top) if (ff is not None and top is not None) else None,
                      skirting_m=r3(max(0, skirting)) if room['type'] not in ('wet', 'court', 'outdoor') else 0,
                      **(dict(skirtingBy='geometry') if mostlyVoid else {}),
                      wallTiling=dict(height_m=None, note='גובה חיפוי קירות – טרם הוחלט') if wet or room['type'] == 'kitchen' else None,
                      parts=[dict(ringITM=[[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]], holesITM=[[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in g.interiors]) for g in parts],
                      ringITM=[[r3(x), r3(y)] for x, y in list(max(parts, key=lambda g: g.area).exterior.coords)[:-1]] if parts else [],
                      layers=layers, tileType=None, status='prep'))
# balconies (13.11.2026): the slab of the floor outside the house – the parts holding an architect's label "מרפסת" (Revit, G-ANNO-TEXT).
# Outline = the slab edge less the walls standing on it and the rooms; finish level – config tilingZones.balconies (the permit drawing)
for fl, B in TZ.get('balconies', {}).items():
    z = CFG['cuts'][fl]; ff = B['finishRel']
    own = [s for s in SLABS if s['top'] < z and s['top'] > z - 3.0 and s['id'] not in TZ_EX]
    S, C = solids_at(fl, B['wallCut'])
    W = unary_union([x['poly'] for x in S] + [c['poly'] for c in C])
    R = unary_union([r['poly'] for r in ROOMS if r['floor'] == fl]).buffer(0.001)
    out = unary_union([s['poly'] for s in own]).difference(W).difference(R)
    labs = [l for l in LABELS.get(fl, []) if B['label'] in l['text']]
    # strips narrower than sliverMax_m between the slab edge and a wall face (a few mm / cm of drawing tolerance) are not floor: an opening removes them
    sv = B.get('sliverMax_m', 0.05) / 2
    out = out.buffer(-sv, join_style=2).buffer(sv, join_style=2).intersection(out)
    regs = [clean(g) for g in getattr(out, 'geoms', [out]) if g.geom_type == 'Polygon' and g.area > 0.5 and any(g.contains(Point(l['itm'])) for l in labs)]
    for i, g in enumerate(sorted(regs, key=lambda g: -g.centroid.y)):
        top = max(s['top'] for s in own if s['poly'].intersection(g).area > 0.5 * g.area)
        key = f"{fl}@balcony-{i + 1}"   # numbered north to south (stable: the saved tile choices are keyed by it)
        side = (B.get('names') or [])[i] if i < len(B.get('names') or []) else f"{B['label']} {i + 1}"
        layers = []
        tot = ff - top; fixed = sum(l['thickness_m'] for l in BU['layers'] if l['thickness_m']); zc = top
        for l in BU['layers']:
            th = l['thickness_m'] if l['thickness_m'] is not None else tot - fixed
            layers.append(dict(id=l['id'], z0=r3(zc), z1=r3(zc + th), thickness_m=r3(th), status='provisional' if l['status'] != 'placeholder' else l['status'])); zc += th
        TILES.append(dict(room=key, floor=fl, roomName=side, zoneName=side, roomType='balcony', area=r3(g.area), void_m2=0, slabTop=top, finishRel=ff,
                          finishStatus=B['status'], finishSource=B['source'], buildUp_m=r3(ff - top), skirting_m=r3(wall_skirting(fl, [g], B['wallCut'])), skirtingBy='geometry',
                          wallTiling=None, labels=sorted({l['text'] for l in labs if g.contains(Point(l['itm']))}),
                          parts=[dict(ringITM=[[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]], holesITM=[[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in g.interiors])],
                          ringITM=[[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]], layers=layers, tileType=None, status='prep',
                          source=f"{SLAB_BY[max(own, key=lambda s: s['poly'].intersection(g).area)['id']]['src']} (פני התקרה); תווית '{B['label']}' – תוכנית האדריכל; מפלס הריצוף: {B['source']}"))
        print('balcony', key, side, r3(g.area), 'm2, skirting', TILES[-1]['skirting_m'])

# wet floors: the waterproofing on the screed, under the adhesive (provisional – no floor detail)
for t in TILES:
    if t['roomType'] != 'wet' or not t['layers']: continue
    zs = next(l['z1'] for l in t['layers'] if l['id'] == BU['wetProofingOn'])
    for pp in t['parts']:
        WPROOF.append(dict(kind='floor', floor=t['floor'], room=t['room'], ringITM=pp['ringITM'], holesITM=pp['holesITM'], z=zs,
                           area=r3(poly(pp['ringITM'], pp['holesITM']).area), rule='כל רצפת החדר הרטוב (על המדה, מתחת לדבק – זמני)', status='provisional'))


# ---------------------------------------------------------------- summaries
def summarize():
    S = defaultdict(lambda: defaultdict(float))
    for f in FACES + CEILS + TOPS + REVS + BEAMSURF + PATCHES:
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
     'kind: wall (פני קיר: a→b ב-ITM, z0..z1 יחסי, normal = הצד שאליו הפנים פונים), ceiling (תחתית תקרה), top (ראש קיר / מעקה), reveal (גליפים: צדי הפתח והמשקוף), beam (קורה גלויה: דפנות, תחתית, ראש). '
     'patch (השלמה – פן חשוף של השלד שאף משטח אחר לא מכסה: אדן, שפת רצפה במדרגה, גומחה, קצה קיר, תחתית מבחוץ; vertical: a→b + z0..z1, אחרת ringITM ב-z, up = פונה למעלה). net = ברוטו פחות פתחים. '
     'מישור אחד (tools/finishes/flatten.py): shift = הטיח מוקדם למישור המשטח (עובי משתנה, מ\'), ext = הארכה בפינה [בקצה a, בקצה b], hidden = פן מדרגה בתוך הטיח המעובה (בכמויות, לא מצויר); fillers – מילוי תצוגה של סדקי מ"מ (לא בכמויות). meshV_m / meshH_m – רשת במפגש בלוק-בטון (אנכי / לאורך ראש הקיר); beads_m – פינות בולטות.',
     **meta, walls=FACES, ceilings=CEILS, tops=TOPS, reveals=REVS, beams=BEAMSURF, patches=PATCHES, fillers=FILLERS, waterproofing=WPROOF, totals=TOT, scratchNote=TYPES['scratchNote']))
dump('data/finishes/tiling/surfaces.json', dict(_doc='רצפות – שטח לכל חדר (החלק שמעל רצפת הקומה), פני ריצוף, פנלים (היקף פחות דלתות), ושכבות הרצפה: סומסום / טיט-מדה / דבק / אריח '
     '(data/finishes/floors/buildup.json – חלוקת עובי זמנית). סוג אריח וגובה חיפוי קירות – טרם הוחלטו.', **meta, buildUp=BU, rooms=TILES))
dump('data/finishes/cladding/surfaces.json', dict(_doc='חיפויי חוץ – נגזר: משטחים ידועים (כרגע: צד הרחוב של החומה לרחוב – אבן). אזורי האדריכל – data/finishes/cladding/zones.json.',
     **meta, kinds=J('data/finishes/cladding/zones.json')['kinds'], items=CLAD))
print(len(ROOMS), 'rooms', len(FACES), 'walls', len(CEILS), 'ceilings', len(TOPS), 'tops', len(REVS), 'reveals', len(BEAMSURF), 'beams', len(PATCHES), 'patches', r3(sum(p_['area'] for p_ in PATCHES)), 'm2 patches', len(WPROOF), 'waterproofing', len(CLAD), 'cladding', len(GAPS), 'gaps')
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
    allS = [dict(f, cat='wall', amount=f['net']) for f in FACES] + [dict(c, cat='ceiling', amount=c['net']) for c in CEILS] + [dict(t, cat='top', amount=t['area']) for t in TOPS] + \
           [dict(r, cat='reveal', amount=r['area']) for r in REVS] + [dict(b, cat='beam', amount=b['area']) for b in BEAMSURF] + [dict(p_, cat='patch', amount=p_['area']) for p_ in PATCHES]
    by = defaultdict(float); scf = defaultdict(float)
    for s in allS: by[s['type']] += s['amount']; scf[s['type']] += s.get('scaffoldArea', 0)
    rev = sum(r['area'] for r in REVS); mesh = sum(f.get('meshV_m', 0) + f.get('meshH_m', 0) for f in FACES)
    beads = sum(f.get('beads_m', 0) for f in FACES) + sum(r['beads'] for r in REVS)
    wpw = sum(w['area'] for w in WPROOF); wpf = 0
    price = lambda k: next((t['price'] for t in TYPES['types'] if t['id'] == k), None)
    rows = [[TL[t['id']], r3(by[t['id']]), 'מ"ר', r3(scf[t['id']]), t['price'], None] for t in TYPES['types']]
    rows += [[TYPES['waterproofing']['label'], r3(wpw), 'מ"ר', None, TYPES['waterproofing']['price'], None],
             ['מזה גליפים (כלול בסוגים)', r3(rev), 'מ"ר', None, None, None], ['מזה קורות גלויות (כלול בסוגים)', r3(sum(b['area'] for b in BEAMSURF)), 'מ"ר', None, None, None], ['מזה השלמות – אדנים, שפות, קצוות (כלול בסוגים)', r3(sum(p_['area'] for p_ in PATCHES)), 'מ"ר', None, None, None], ['רשת פיברגלס', r3(mesh), 'מ"א', None, None, None], ['פינות מגן', r3(beads), 'מ"א', None, None, None]]
    ws = sheet('סיכום', ['סוג', 'כמות', 'יחידה', 'מזה בפיגום (מעל %.1f מ\')' % PRM['scaffoldAbove_m'], 'מחיר ליחידה', 'עלות'], rows, [30, 12, 8, 18, 14, 14])
    for i in range(2, ws.max_row + 1): ws.cell(i, 6).value = f'=IF(E{i}="","",B{i}*E{i})'
    ws.append(['סה"כ', None, None, None, None, f'=SUM(F2:F{ws.max_row})'])
    for c in ws[ws.max_row]: c.font = Font(bold=True)
    ws.append([]); ws.append(['ריצוף – שטח רצפות (הכנה)', r3(sum(t['area'] for t in TILES if t['roomType'] not in ('court', 'outdoor'))), 'מ"ר'])
    ws.append(['פנלים', r3(sum(t['skirting_m'] for t in TILES)), 'מ"א'])
    ws.append([]); ws.append([TYPES['scratchNote']])
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
          [[s['key'], FLOOR_HE[s['floor']], {'wall': 'קיר', 'ceiling': 'תקרה', 'top': 'ראש קיר', 'reveal': 'גליף', 'beam': 'קורה', 'patch': 'השלמה'}[s['cat']], {'in': 'פנים', 'out': 'חוץ'}.get(s.get('side'), ''),
            FACADE_HE.get(s.get('facade'), ''), RN.get(s.get('room'), ''), s.get('owner') or s.get('slab') or s.get('opening') or s.get('beam'), TL[s['type']], TL[s['defaultType']], s['typeReason'],
            s.get('length'), s.get('z0', s.get('z')), s.get('z1'), s.get('gross', s['amount']), s.get('openingsArea', 0), s['amount'],
            'כן' if s.get('scaffold') else '', s.get('scaffoldArea', 0), r3(s.get('meshV_m', 0) + s.get('meshH_m', 0)), s.get('beads_m', 0)] for s in allS],
          [30, 10, 8, 6, 8, 24, 10, 16, 16, 30] + [9] * 10)
    sheet('גליפים', ['פתח', 'סוג', 'קומה', 'רוחב', 'גובה', 'עומק (עובי קיר)', 'חלקים', 'שטח', 'זוויתנים'],
          [[r['opening'], r['openingKind'], FLOOR_HE[r['floor']], r['width'], r['height'], r['depth'], ' + '.join(q['part'] for q in r['quads']), r['area'], r['beads']] for r in REVS])
    sheet('קורות', ['קורה', 'קומה', 'תחתית', 'ראש', 'פרגולה', 'דפנות מ"ר', 'תחתית/ראש מ"ר', 'סה"כ', 'סוג'],
          [[b['beam'], FLOOR_HE[b['floor']], b['bottom'], b['top'], 'כן' if b['pergola'] else '', r3(sum(x['area'] for x in b['sides'])), r3(sum(x['area'] for x in b['flats'])), b['area'], TL[b['type']]] for b in BEAMSURF])
    sheet('איטום', ['קומה', 'חדר', 'רכיב', 'כלל', 'מגובה', 'עד גובה', 'שטח', 'מעמד'],
          [[FLOOR_HE[w['floor']], RN.get(w['room']), w.get('owner', 'רצפה'), w['rule'], w.get('z0', w.get('z')), w.get('z1'), w['area'], w['status']] for w in WPROOF], [12, 30, 10, 30, 8, 8, 8, 10])
    sheet('רצפות', ['קומה', 'חדר', 'סוג חדר', 'שטח מ"ר', 'חלל (בלי רצפה) מ"ר', 'פנלים מ"א', 'פני בטון', 'פני ריצוף', 'סומסום מ\'', 'טיט/מדה מ\'', 'דבק מ\'', 'אריח מ\'', 'סוג אריח'],
          [[FLOOR_HE[t['floor']], t.get('zoneName') or RN.get(t['room']), TYPE_HE.get(t['roomType']), t['area'], t['void_m2'], t['skirting_m'], t['slabTop'], t['finishRel']] +
           [next((l['thickness_m'] for l in t['layers'] if l['id'] == i), None) for i in ('floorFill', 'floorScreed', 'floorAdhesive', 'floorTile')] + ['טרם הוחלט'] for t in TILES],
          [12, 30, 12, 10, 12, 10, 9, 9, 9, 9, 9, 9, 12])
    os.makedirs(os.path.join(ROOT, os.path.dirname(path)), exist_ok=True)
    wb.save(os.path.join(ROOT, path))
    print('xlsx ->', path)


if not os.environ.get('FINISHES_NO_XLSX'): export_xlsx()

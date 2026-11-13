#!/usr/bin/env python3
"""Doorway floor strips for the tiling workshop (Avihai 13.11.2026: "where there is a door you put no tiles – those areas
belong to the floor of the big space, e.g. the corridor belongs to the central space, not to the rooms").

The room floors (data/finishes/tiling/surfaces.json) stop at the wall faces, so the floor inside the wall thickness under
every door / vitrine is in no zone. The strip is taken from the door jambs of the plaster data (data/finishes/plaster/
surfaces.json reveals, part "jamb" – both sides of the opening, through the wall thickness, from the real wall geometry):
bounding rectangle of the jambs' bottom edges at slab level (ק71: not the hull – no wedge where one jamb is shallower), minus the room floors of that storey (only the gap is left).
Each strip joins the adjacent zone with the largest floor area (the main space – Avihai's rule).

Output: data/finishes/tiling/door-strips.json
Run from the repo root:  python3 tools/finishes/door_strips.py
"""
import json
import os

from shapely.geometry import MultiPoint, Polygon
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = json.load(open(os.path.join(ROOT, 'data/finishes/plaster/surfaces.json'), encoding='utf-8'))
TL = json.load(open(os.path.join(ROOT, 'data/finishes/tiling/surfaces.json'), encoding='utf-8'))
CAT = json.load(open(os.path.join(ROOT, 'data/finishes/tiling/catalog.json'), encoding='utf-8'))
EXCL = set(CAT.get('excludeRoomTypes', []))
TOUCH = 0.05      # a zone touches the strip if it is within this distance (wall-face rounding)
MIN_AREA = 0.01   # m² – smaller leftovers are slivers of the hull, not a doorway
r3 = lambda v: round(v, 3)

rooms = [r for r in TL['rooms'] if r.get('layers') and r['area'] > 0.05 and r.get('parts') and r['roomType'] not in EXCL]
polys = {r['room']: unary_union([Polygon(p['ringITM'], p.get('holesITM') or []).buffer(0) for p in r['parts']]) for r in rooms}
# exterior paving zones (data/finishes/tiling/exterior.json – the yards / terrace / parking of the ground floor):
# Avihai 13.11.2026 – "the door area belongs to the outside": a threshold that touches an exterior zone (or a balcony) joins it
EXT = json.load(open(os.path.join(ROOT, 'data/finishes/tiling/exterior.json'), encoding='utf-8'))
for r in EXT['rooms']:
    rooms.append(r); polys[r['room']] = unary_union([Polygon(p['ringITM'], p.get('holesITM') or []).buffer(0) for p in r['parts']])
OUTSIDE = lambda r: r.get('outdoor') or r['roomType'] == 'balcony'
by_floor = {}
for r in rooms: by_floor.setdefault(r['floor'], []).append(r)

out = []
for rv in P['reveals']:
    if rv.get('openingKind') not in ('door', 'sliding', 'vitrine'): continue
    fl = rv['floor']; rs = by_floor.get(fl, [])
    if not rs: continue
    slab = min(r['slabTop'] for r in rs if not r.get('outdoor'))
    pts = []
    for q in rv['quads']:
        if q['part'] != 'jamb': continue
        zb = min(p[2] for p in q['q'])
        if zb > slab + 0.05: continue          # a window / a sill above the floor: no floor strip
        pts += [(p[0], p[1]) for p in q['q'] if abs(p[2] - zb) < 1e-3]
    if len(pts) < 3: continue
    # the bounding rectangle of the jambs, not their hull: where one jamb is shallower than the other (the pocket of the
    # ממ"ד sliding door, G21) the hull is a trapezoid and leaves a wedge between the strip and the room floor (ק71)
    hull = MultiPoint(pts).minimum_rotated_rectangle
    if hull.area < MIN_AREA: continue
    gap = hull.difference(unary_union([polys[r['room']] for r in rs]))
    parts = [g for g in getattr(gap, 'geoms', [gap]) if g.area >= MIN_AREA and g.geom_type == 'Polygon']
    if not parts: continue
    strip = unary_union(parts)
    near = [r for r in rs if polys[r['room']].distance(strip) <= TOUCH]
    if not near: continue
    # owner: the corridor (a shared floor zone – tilingZones.names in data/finishes/config.json) if it touches the strip, else the largest
    # adjacent zone; a balcony (outside, another level) never takes the threshold of a vitrine – it stays with the room inside
    out_ = [r for r in near if OUTSIDE(r)]
    inside = [r for r in near if not OUTSIDE(r)] or near
    shared = [r for r in inside if r.get('zoneName')]
    own = max(out_, key=lambda r: r['area']) if out_ else max(shared or inside, key=lambda r: r['area'])
    for g in getattr(strip, 'geoms', [strip]):
        ring = [[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]]
        out.append(dict(id=rv['opening'] + ('' if len(out) == 0 or out[-1]['id'].split('#')[0] != rv['opening'] else '#2'), opening=rv['opening'],
                        kind=rv['openingKind'], floor=fl, room=own['room'], roomName=own.get('roomName'), neighbours=[r['room'] for r in near],
                        area_m2=r3(g.area), depth_m=rv.get('depth'), ringITM=ring, status='derived',
                        source=f"data/finishes/plaster/surfaces.json reveal {rv['key']} (jamb quads – {rv['source']}); minus the room floors of {fl}; owner = the exterior zone / balcony if adjacent (Avihai 13.11: the door area belongs outside), else the corridor, else the largest adjacent zone"))

# the zone floor with its strips as one polygon (the workshop lays the tiles over it – a tile across the threshold is one tile)
merged = {}
for key in sorted({s['room'] for s in out}):
    u = unary_union([polys[key]] + [Polygon(s['ringITM']) for s in out if s['room'] == key]).buffer(0.002, join_style=2).buffer(-0.002, join_style=2)
    merged[key] = [dict(ringITM=[[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]], holesITM=[[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in g.interiors])
                   for g in getattr(u, 'geoms', [u]) if g.area >= MIN_AREA]

doc = {
    '_doc': 'רצועות הרצפה בעובי הקיר מתחת לדלתות / ויטרינות – לא היו בשום אזור ריצוף. רצועה של פתח החוצה מצטרפת לאזור החוץ / המרפסת (אביחי 13.11.2026: "אזור הדלתות שייך לבחוץ"); אחרת – לאזור הגדול הצמוד ("המסדרון שייך לחלל המרכזי, לא לחדרים"). נגזר: tools/finishes/door_strips.py.',
    'source': 'tools/finishes/door_strips.py ← data/finishes/plaster/surfaces.json (גליפי הדלתות) + data/finishes/tiling/surfaces.json',
    'status': 'derived',
    'strips': out,
    'zones': merged,
    '_zones': 'פוליגון האזור כולל הרצועות (איחוד) – לפריסת האריחים בסדנה.',
}
dst = os.path.join(ROOT, 'data/finishes/tiling/door-strips.json')
with open(dst, 'w', encoding='utf-8') as f:
    json.dump(doc, f, ensure_ascii=False, indent=1); f.write('\n')
print(f'{len(out)} door strips, {sum(s["area_m2"] for s in out):.3f} m2 -> data/finishes/tiling/door-strips.json')
for s in out: print(f"  {s['id']:6} {s['floor']:6} {s['kind']:8} {s['area_m2']:.3f} m2 -> {s['roomName'] or s['room']}  (touches {len(s['neighbours'])})")

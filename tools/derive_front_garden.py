"""הגינה בחזית (OC-17): היקף = המגרש פחות רצפות הקרקע, אזורים פתוחים, קירות, עמודים וחומות היקפיות,
הרכיב שמכיל את הכיתוב "גינון" שבחזית (תוכנית קומת קרקע, data/plumbing/plan-background.json texts).
כותב את האזור ל-data/changes/owner-changes-geometry.json (OC-17 terrain.zones, key 'front').
הרצה: python3 tools/derive_front_garden.py"""
import json, os, collections
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union
R = os.path.join(os.path.dirname(__file__), '..')
J = lambda p: json.load(open(os.path.join(R, p), encoding='utf-8'), object_pairs_hook=collections.OrderedDict)
fg = J('data/structure/floor-ground.json'); per = J('data/structure/perimeter.json'); lot = Polygon(J('data/site/plot-5187.json')['ring'])
texts = J('data/plumbing/plan-background.json')['floors']['ground']['texts']
polys = [Polygon(s['footprintITM']).buffer(0) for s in fg['slab']] + [Polygon(o['footprintITM']).buffer(0) for o in fg['openZones']]
polys += [Polygon(w['ringITM']).buffer(0) for w in per['walls'] if w.get('ringITM')]
polys += [Polygon(w['footprintITM']).buffer(0) for w in fg['walls'] + fg['columns'] if w.get('footprintITM')]
free = lot.difference(unary_union(polys))
# the "גינון" label of the front (the one that lies on no slab, south of the house)
labels = [t for t in texts if t['t'] == 'גינון' and not any(Polygon(s['footprintITM']).contains(Point(t['E'], t['N'])) for s in fg['slab'])
          and not any(Polygon(o['footprintITM']).contains(Point(t['E'], t['N'])) for o in fg['openZones'])]
P = Point(labels[0]['E'], labels[0]['N'])
g = next(q for q in getattr(free, 'geoms', [free]) if q.contains(P))
# remove slivers (gaps of a few cm between a slab and a wall): morphological opening by 5 cm, keep the part with the label
o = g.buffer(-0.05, join_style=2).buffer(0.05, join_style=2)
part = next(q for q in getattr(o, 'geoms', [o]) if q.contains(P))
ring = [[round(x, 3), round(y, 3)] for x, y in list(part.exterior.coords)[:-1]]
p = os.path.join(R, 'data/changes/owner-changes-geometry.json'); d = J('data/changes/owner-changes-geometry.json')
T = d['changes']['OC-17']['terrain']
zone = collections.OrderedDict([('key', 'front'), ('label', 'הגינה בחזית'), ('area_m2', round(part.area, 3)), ('ringITM', ring),
  ('followPaving', {'slab': 'GS4', 'offset_m': -0.02, '_doc': 'ראש המצע = פני הריצוף של החצר הדרומית GS4 הצמודה (exterior.json) − 2 ס"מ'}),
  ('status', 'derived'),
  ('source', f'מחושב: מגרש 5187 (data/site/plot-5187.json) פחות רצפות / אזורים פתוחים / קירות / עמודים (data/structure/floor-ground.json) וחומות (data/structure/perimeter.json walls), '
             f'הרכיב שמכיל את הכיתוב "גינון" (E {labels[0]["E"]} N {labels[0]["N"]}, data/plumbing/plan-background.json); פתיחה מורפולוגית 5 ס"מ – tools/derive_front_garden.py')])
T['zones'] = [z for z in T['zones'] if not (isinstance(z, dict) and z.get('key') == 'front')] + [zone]
open(p, 'w', encoding='utf-8').write(json.dumps(d, ensure_ascii=False, indent=1) + '\n')
print(f'front garden: {part.area:.3f} m², {len(ring)} vertices, label at {labels[0]["E"]}, {labels[0]["N"]}')

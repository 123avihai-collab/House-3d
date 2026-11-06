#!/usr/bin/env python3
"""Geometry for the owner's changes (data/changes/owner-changes.json) -> data/changes/owner-changes-geometry.json.

Wall pieces are the individual IfcWall hatches of k-11.dxf (before the union done in extract_framing.wall_polys),
picked by a point inside them (ITM) so that the choice survives a re-export of the DXF. The geometry produced here is
derived only from the source outlines (k-11 walls, framing.json slabs); the owner change decides which of them change.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_framing as F
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union, split

ROOT = F.ROOT; r3 = F.r3
ring = lambda g: [[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]]
holes = lambda g: [[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in g.interiors]


def wall_pieces():
    m11 = F.read_dxf(F.K11); t = F.basement['k11ToK400']['translation_pt']
    to = lambda x, y: F.sheet2itm(x * F.S_CM + t[0], -y * F.S_CM + t[1])
    out = []
    for h in m11.query('HATCH[layer=="IfcWall"]'):
        for path in h.paths:
            vs = [(v[0], v[1]) for v in path.vertices] if hasattr(path, 'vertices') else \
                 [(e.start[0], e.start[1]) for e in path.edges if e.EDGE_TYPE == 'LineEdge']
            if len(vs) >= 3:
                g = Polygon([to(x, y) for x, y in vs]).buffer(0)
                polys = [q for q in getattr(g, 'geoms', [g]) if q.geom_type == 'Polygon' and q.area > 1e-4]
                if polys: out.append(max(polys, key=lambda q: q.area))
    return out


def main():
    oc = json.load(open(os.path.join(ROOT, 'data/changes/owner-changes.json'), encoding='utf-8'))
    fr = json.load(open(os.path.join(ROOT, 'data/structure/framing.json'), encoding='utf-8'))
    pieces = wall_pieces()
    pick = lambda pt: next((p for p in pieces if p.buffer(0.01).contains(Point(pt))), None)
    out = {'_doc': 'נגזר אוטומטית ע"י tools/apply_owner_changes.py – לא לערוך ידנית.', 'changes': {}}
    for c in oc['changes']:
        g = {'wallPieces': {}}
        for key, w in (c.get('walls') or {}).items():
            parts = [pick(pt) for pt in w['pointsITM']]
            if any(p is None for p in parts): raise SystemExit(f'{c["id"]}: wall piece {key} not found')
            u = unary_union(parts)
            g['wallPieces'][key] = {'role': w['role'], 'outlinesITM': [ring(p) for p in parts], 'area_m2': r3(u.area),
                                    'source': f'{F.K11} HATCH IfcWall (חלק קיר בודד, נבחר לפי נקודה)'}
        s = c.get('slab')
        if s:
            slab = next(x for x in fr['slabs'] if x['id'] == s['split'])
            P = Polygon(slab['outlineITM'])
            a = unary_union([pick(pt) for pt in c['walls'][s['byWall']]['pointsITM']])
            # the dividing line = long axis of wall A, extended across the slab
            mr = a.minimum_rotated_rectangle; xy = list(mr.exterior.coords)[:4]
            e = sorted([(xy[i], xy[(i + 1) % 4]) for i in range(4)], key=lambda q: -LineString(q).length)[0]
            cx, cy = a.centroid.x, a.centroid.y; dx, dy = e[1][0] - e[0][0], e[1][1] - e[0][1]; L = (dx * dx + dy * dy) ** 0.5
            cut = LineString([(cx - dx / L * 20, cy - dy / L * 20), (cx + dx / L * 20, cy + dy / L * 20)])
            parts = sorted(split(P, cut).geoms, key=lambda q: q.centroid.y)   # south first (smaller N)
            if len(parts) != 2: raise SystemExit(f'{c["id"]}: slab split gave {len(parts)} parts')
            south, north = parts
            lv = next(x for x in fr['slabs'] if x['id'] == s['levelFrom'])
            g['slabSplit'] = {
                'north': {'outlineITM': ring(north), 'area_m2': r3(north.area), 'top': slab['top'], 'thickness_m': slab['thickness_m'], 'source': slab['source']},
                'south': {'outlineITM': ring(south), 'area_m2': r3(south.area), 'top': slab['top'], 'thickness_m': slab['thickness_m'], 'source': slab['source']},
                'lowered': s['lower'], 'newTop': lv['top'], 'newThickness_m': lv['thickness_m'],
                'newSource': f"{c['source']}; מפלס ועובי כמו {lv['id']}: {lv['source']}",
                'check': {'sumArea_m2': r3(north.area + south.area), 'original_m2': slab['area_m2']}}
        ow = (c.get('openWall') or {}).get('piece')
        if ow:
            cpart = unary_union([pick(pt) for pt in c['walls'][ow]['pointsITM']])
            changed = []
            for w in fr['basementWalls']:
                W = Polygon(w['footprintITM'], w.get('holesITM') or [])
                if W.intersection(cpart).area > 0.5 * cpart.area:
                    d = W.difference(cpart.buffer(0.002))
                    geoms = [q for q in getattr(d, 'geoms', [d]) if q.geom_type == 'Polygon']
                    changed.append({'replaces': w['id'], 'pieces': [{'footprintITM': ring(q), 'holesITM': holes(q)} for q in geoms if q.area > 0.005],
                                    'bottomRel': w['bottomRel'], 'topRel': w['topRel'], 'check': {'removed_m2': r3(W.area - d.area), 'piece_m2': r3(cpart.area)}})
            g['wallsChanged'] = changed
        out['changes'][c['id']] = g
    json.dump(out, open(os.path.join(ROOT, 'data/changes/owner-changes-geometry.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for k, g in out['changes'].items():
        print(k, {kk: v['area_m2'] for kk, v in g['wallPieces'].items()}, g.get('slabSplit', {}).get('check'),
              {'north': g['slabSplit']['north']['area_m2'], 'south': g['slabSplit']['south']['area_m2']} if 'slabSplit' in g else None,
              [w['check'] for w in g.get('wallsChanged', [])])


if __name__ == '__main__':
    main()

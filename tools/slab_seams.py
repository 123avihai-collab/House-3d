#!/usr/bin/env python3
"""Seams between the ground slabs (Avihai ק19, 11.11.2026): two slab outlines of the K-21 DXF that meet over a beam can leave a
strip of a few mm–2.5 cm with no slab, and the beam top shows through it (GS1 / GS3 over B-53). Such a strip – narrower than
max_m, over a K-21 beam, not inside a wall / column – joins the slab whose top is nearest the beam top under it.
Used by tools/extract_floor.py; standalone: python3 tools/slab_seams.py (fixes data/structure/floor-ground.json in place)."""
import json, math, os
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
r3 = lambda v: round(float(v), 3)


def _ring(p): return [[r3(x), r3(y)] for x, y in list(p.exterior.coords)[:-1]]


def _holes(p): return [[[r3(x), r3(y)] for x, y in list(h.coords)[:-1]] for h in p.interiors]


def _polys(g): return [g] if g.geom_type == 'Polygon' else [q for q in getattr(g, 'geoms', []) if q.geom_type == 'Polygon']


def _beam(b):
    (x0, y0), (x1, y1) = b['axisITM'][0], b['axisITM'][-1]; L = math.hypot(x1 - x0, y1 - y0); ux, uy = (x1 - x0) / L, (y1 - y0) / L; t = b['width_m'] / 2
    return Polygon([(x0 - uy * t, y0 + ux * t), (x1 - uy * t, y1 + ux * t), (x1 + uy * t, y1 - ux * t), (x0 + uy * t, y0 - ux * t)])


def close_slab_seams(gf, framing, max_m=0.025):
    SL = [(s, Polygon(s['footprintITM'], s.get('holesITM', [])).buffer(0)) for s in gf['slab']]
    U = unary_union([p for _, p in SL])
    solid = unary_union([Polygon(w['footprintITM'], w.get('holesITM', [])).buffer(0) for w in gf['walls'] + gf['columns']])
    beams = [(b, _beam(b)) for b in framing['groundBeams'] if b.get('axisITM') and b.get('sheet') == 'K-21']
    r = max_m / 2
    gaps = U.buffer(r, join_style=2).buffer(-r, join_style=2).difference(U).difference(solid)
    done = []
    for q in _polys(gaps):
        if q.area < 2e-4 or 2 * q.area / q.length > max_m: continue
        under = [(b, bp) for b, bp in beams if bp.intersection(q).area > 0.8 * q.area]
        if not under: continue
        bt = max(b['topRel'] for b, _ in under)
        touch = [(s, p) for s, p in SL if p.distance(q) < 0.002]
        if len(touch) < 2: continue
        s, p = min(touch, key=lambda sp: abs(sp[0]['topRel'] - bt))
        g = max(_polys(unary_union([p, q.buffer(0.0005, join_style=2)]).buffer(0)), key=lambda x: x.area)
        s['footprintITM'], s['holesITM'], s['area_m2'] = _ring(g), _holes(g), r3(g.area)
        msg = f"תפר של {q.area * 1e4:.0f} סמ\"ר ({q.length / 2:.2f} מ') בין {', '.join(t['id'] for t, _ in touch)} מעל {', '.join(b['id'] for b, _ in under)} – נסגר ב-{s['id']} (הערת אביחי ק19)."
        if msg not in (s.get('note') or ''): s['note'] = ((s.get('note') or '') + ' ' + msg).strip()
        SL = [(t, (g if t is s else pp)) for t, pp in SL]
        done.append(msg)
    return done


if __name__ == '__main__':
    p = os.path.join(ROOT, 'data/structure/floor-ground.json')
    gf = json.load(open(p, encoding='utf-8')); fr = json.load(open(os.path.join(ROOT, 'data/structure/framing.json'), encoding='utf-8'))
    for m in close_slab_seams(gf, fr): print(m)
    with open(p, 'w', encoding='utf-8') as f: json.dump(gf, f, ensure_ascii=False, indent=1); f.write('\n')

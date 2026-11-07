#!/usr/bin/env python3
"""Plan check of the ceilings and parapets (Avihai's note 2.8): the model against the structural sheets, independent of
the extraction path where possible.
  1. walls that rise from a slab (K-31 first floor, K-41 parapets): the sheet's hatch fill (PDF, "קיר צומח") against the
     model walls (+ the K-41 perimeter beams, which are part of the parapet ring) – plan not in model = MISSING,
     model not in plan = EXTRA (marked, never deleted).
  2. beams: every beam tag of K-31 / K-41 has a model beam and vice versa.
  3. ceiling slabs: air gaps between a ceiling slab and the walls / beams / slabs around it inside the building outline
     (a gap in the plan would be drawn as an opening – a gap in the model only is a hole).
  4. the overall K-41 dimensions (1579 × 1497) against the model's outer ring.
Output: docs/verification/plan-check.json (+ printed)."""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
import extract_floor as X
ROOT = X.ROOT
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
r3 = lambda v: round(float(v), 3)
MIN = 0.05   # m² – smaller differences are drawing / hatch tolerance


def pieces(g, min_area=MIN):
    return [q for q in getattr(g, 'geoms', [g]) if q.geom_type == 'Polygon' and q.area >= min_area and 2 * q.area / q.length > 0.04]


def near(q, named):
    return min(named, key=lambda e: e[1].distance(q))[0] if named else None


def beam_poly(b):
    return LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2)


def main():
    FG, FF, FR = J('data/structure/floor-ground.json'), J('data/structure/floor-first.json'), J('data/structure/floor-roof.json')
    t31 = FG['placement']['K31pdf']['translation_pt']; t41 = FF['ceiling']['placement']['K41pdf']['translation_pt']
    out = {'_doc': 'נוצר ע"י tools/plan_check.py – בדיקת תקרות, קירות ומעקות מול התוכניות (הערת אביחי 2.8). חסר = בתוכנית ולא במודל; עודף = במודל ולא בתוכנית (מסומן, לא נמחק).', 'checks': []}

    def compare(name, sheet, plan, model_named, tol=0.04):
        # the PDF hatch is drawn as fill only on part of the walls (the rest is line hatching), so only MISSING is reliable
        # here (hatched in the plan, absent in the model); EXTRA comes from the ring / DXF checks below
        model = unary_union([g for _, g in model_named])
        miss = [q for q in pieces(plan.difference(model.buffer(tol)))]
        rec = {'check': name, 'sheet': sheet, 'planFill_m2': r3(plan.area), 'model_m2': r3(model.area),
               'missing': [{'area_m2': r3(q.area), 'atITM': [r3(q.centroid.x), r3(q.centroid.y)], 'near': near(q, model_named)} for q in miss]}
        out['checks'].append(rec); return rec

    # 1a. K-41: parapet ring = hatched walls ("צומח") – the model's roof walls + perimeter beams
    hatch41 = X.pdf_grey(X.K41P, t41, shades=(0.93, 0.97))
    ring = [(w.get('displayName', w['id']) + f" [{w['id']}]", Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0)) for w in FR['walls']] + \
           [(b['id'], beam_poly(b)) for b in FR['ceiling']['beams'] if b.get('axisITM')]
    walls_only = [(n, g) for n, g in ring if not n.startswith('B-')]
    compare('מעקות הגג מול המילוי המוקווקו של K-41', 'K-41', hatch41, walls_only)
    # 1b. K-31: first-floor walls (rising from +3.70)
    hatch31 = X.pdf_grey(X.K31P, t31, shades=(0.93, 0.97))
    compare("קירות קומה א' מול המילוי המוקווקו של K-31", 'K-31', hatch31,
            [(f"{w.get('tag') or 'ללא שם'} [{w['id']}]", Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0)) for w in FF['walls']] +
            [(c['id'], Polygon(c['footprintITM'])) for c in FF['columns']])
    # 2. beams by tag
    for sheet, path, t, beams in (('K-31', X.K31P, t31, FG['ceiling']['beams']), ('K-41', X.K41P, t41, FR['ceiling']['beams'])):
        tags = {bt['id'] for bt in X.beam_tags_all(path, t) if bt['numbered']}
        model = {b['id'] for b in beams if b.get('axisITM')}
        out['checks'].append({'check': f'קורות {sheet}: תוויות מול המודל', 'sheet': sheet, 'tags': len(tags), 'model': len(model),
                              'missing': sorted(tags - model), 'extra': sorted(m for m in model - tags if not m.startswith('קורה ללא מספר')),
                              'unnumbered': sorted(m for m in model - tags if m.startswith('קורה ללא מספר'))})
    # 3. ceiling slabs: holes inside the outline that no element fills
    for name, slabs, verts in (('תקרת הקרקע +3.70 (K-31)', FG['ceiling']['slab'], FG['walls'] + FG['columns'] + FF['walls'] + FF['columns']),
                               ('תקרת הגג +6.90 (K-41)', FF['ceiling']['slab'], FF['walls'] + FF['columns'] + FR['walls'])):
        S = unary_union([Polygon(s['footprintITM'], s.get('holesITM') or []).buffer(0) for s in slabs])
        B = unary_union([beam_poly(b) for b in (FG['ceiling']['beams'] if 'K-31' in name else FR['ceiling']['beams']) if b.get('axisITM')])
        V = unary_union([Polygon(e['footprintITM'], e.get('holesITM') or []).buffer(0) for e in verts])
        allg = unary_union([S, B, V])
        holes_ = [Polygon(h) for g in getattr(allg, 'geoms', [allg]) for h in g.interiors]
        openings = unary_union([Polygon(o['footprintITM']).buffer(0) for o in (FG['ceiling'].get('openings') or [])]) if 'K-31' in name else Polygon()
        gaps = [h for h in holes_ if h.area >= MIN and h.difference(openings.buffer(0.05)).area >= MIN]
        out['checks'].append({'check': f'{name}: חורים בתוך המתאר', 'gaps': [{'area_m2': r3(h.area), 'atITM': [r3(h.centroid.x), r3(h.centroid.y)]} for h in gaps]})
    # 1c. the roof ring is closed: walls + perimeter beams (all cast in step roofWalls / RW21 before) enclose the roof slab,
    #     the two open boxes and the north pergola with no gap (Avihai's note 2.4 – the gap between RW1 and RW7)
    allR = unary_union([g.buffer(0.01) for _, g in ring])
    encl = sorted((Polygon(h) for g in getattr(allR, 'geoms', [allR]) for h in g.interiors if Polygon(h).area > 1), key=lambda h: -h.area)
    rs = unary_union([Polygon(s['footprintITM'], s.get('holesITM') or []).buffer(0) for s in FF['ceiling']['slab']])
    out['checks'].append({'check': 'טבעת הגג סגורה (מעקות + קורות ההיקף)', 'parts': len(getattr(allR, 'geoms', [allR])),
                          'enclosed': [{'area_m2': r3(h.area), 'atITM': [r3(h.centroid.x), r3(h.centroid.y)],
                                        'kind': 'תקרת הגג' if h.intersection(rs).area > 0.5 * h.area else 'פתוח (פרגולה / חלל)'} for h in encl],
                          'roofSlabEnclosed': any(h.intersection(rs).area > 0.9 * rs.area for h in encl)})
    # 4. K-41 overall dimensions: the outer ring in the house axes
    mrr = allR.minimum_rotated_rectangle; xy = list(mrr.exterior.coords)
    a, b = math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2])
    out['checks'].append({'check': 'מידות חוץ של טבעת הגג מול K-41 (1579 × 1497 ס"מ)', 'model_cm': sorted([round(a * 100), round(b * 100)], reverse=True), 'plan_cm': [1579, 1497]})
    json.dump(out, open(os.path.join(ROOT, 'docs/verification/plan-check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for c in out['checks']:
        print(c['check'], {k: v for k, v in c.items() if k not in ('check',)})


if __name__ == '__main__':
    main()

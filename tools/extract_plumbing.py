#!/usr/bin/env python3
"""Plumbing items that touch the foundations stage (stage 2b), from sources/plumbing/אינסטלציה חתכים הכל.dxf.

Placement: the basement background of the plumbing DXF (block 'martef', cm) is the architect's basement plan; its
walls coincide with k-11.dxf (structural basement, cm) after a pure translation found by ICP (inliers at 0.1 mm).
k-11 -> ITM is the stage-2 chain (basement.json k11ToK400 + piles.json sheetToItm).

Output data/systems/plumbing-foundations.json:
  chambers – pump chamber for the English courtyards (T.L./I.L./H/D from the G_LABELD attributes)
  pipeCrossings – plumbing lines of the basement plan that cross a basement wall (sleeve needed)
"""
import json, math, os, re
import ezdxf
import numpy as np
from shapely.geometry import LineString, Point, Polygon
import extract_framing as F

ROOT = F.ROOT
SRC = 'sources/plumbing/אינסטלציה חתכים הכל.dxf'
r3 = F.r3


def main():
    doc = ezdxf.readfile(os.path.join(ROOT, SRC)); msp = doc.modelspace()
    mar = next(e for e in msp.query('INSERT') if e.dxf.name == 'martef')
    A = []
    for v in mar.virtual_entities():
        if v.dxftype() == 'LINE' and v.dxf.layer in ('A-WALL', 'S-STRS', 'S-STRS-MBND'):
            A += [(v.dxf.start.x, v.dxf.start.y), (v.dxf.end.x, v.dxf.end.y)]
    A = np.unique(np.round(np.array(A), 1), axis=0)
    m11 = F.read_dxf(F.K11); B = []
    for e in m11.query('LINE[layer=="IfcWall"]'):
        B += [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    B = np.unique(np.round(np.array(B), 1), axis=0)
    sc, t, med = F.icp(A, B, tries=80)
    t11 = F.basement['k11ToK400']['translation_pt']
    to_itm = lambda x, y: F.sheet2itm((x + t[0]) * F.S_CM + t11[0], -(y + t[1]) * F.S_CM + t11[1])
    xs, ys = A[:, 0], A[:, 1]; box = (xs.min() - 600, xs.max() + 600, ys.min() - 600, ys.max() + 600)
    inside = lambda x, y: box[0] < x < box[1] and box[2] < y < box[3]

    chambers = []
    for lab in msp.query('INSERT[name=="G_LABELD"]'):
        if not inside(lab.dxf.insert.x, lab.dxf.insert.y): continue
        at = {a.dxf.tag: a.dxf.text for a in lab.attribs}
        # the chamber symbol (MH D1000) nearest to the label
        mh = min(msp.query('INSERT[name=="MH D1000"]'), key=lambda m: math.dist((m.dxf.insert.x, m.dxf.insert.y), (lab.dxf.insert.x, lab.dxf.insert.y)))
        circ = [c for c in mh.virtual_entities() if c.dxftype() == 'CIRCLE']
        cen = max(circ, key=lambda c: c.dxf.radius).dxf.center if circ else mh.dxf.insert
        note = next((e.plain_text() for e in msp.query('MTEXT') if math.dist((e.dxf.insert.x, e.dxf.insert.y), (lab.dxf.insert.x, lab.dxf.insert.y)) < 400 and 'שאיבה' in e.plain_text()), '')
        d_cm = int(re.sub(r'\D', '', at.get('D', '')) or 0)
        E, N = to_itm(cen.x, cen.y)
        chambers.append({'id': 'PC-1', 'kind': 'pumpChamber', 'title': note.strip() or 'תא שאיבה',
                         'E': r3(E), 'N': r3(N), 'diameter_m': d_cm / 100, 'TL': float(at['TL']), 'IL': float(at['IL']), 'H_m': float(at['H']),
                         'status': 'source', 'affectedBy': None,
                         'source': f'{SRC} – G_LABELD (TL={at["TL"]}, IL={at["IL"]}, H={at["H"]}, D={at["D"]}) + סמל MH D1000'})

    # basement walls (stage 2b data) – plumbing lines of the basement plan crossing them
    fr = json.load(open(os.path.join(ROOT, 'data/structure/framing.json'), encoding='utf-8'))
    walls = [Polygon(w['footprintITM'], w.get('holesITM') or []) for w in fr['basementWalls']]
    crossings = []
    for e in msp.query('LINE LWPOLYLINE'):
        if e.dxf.layer not in ('BIUV', 'biov 110', 'biov center', 'cold water', 'hot water', 'num of plumbing'): continue
        ps = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)] if e.dxftype() == 'LINE' else [tuple(p) for p in e.get_points('xy')]
        if len(ps) < 2 or not all(inside(*p) for p in ps): continue
        L = LineString([to_itm(*p) for p in ps])
        if L.length < 0.3: continue
        for i, w in enumerate(walls):
            x = L.intersection(w)
            if not x.is_empty and x.length > 0.05:
                c = x.centroid
                crossings.append({'wall': fr['basementWalls'][i]['id'], 'layer': e.dxf.layer, 'E': r3(c.x), 'N': r3(c.y), 'length_m': r3(x.length)})
    # owner changes: chambers near an area that the owner changed (OC-n) are flagged for re-design
    oc = json.load(open(os.path.join(ROOT, 'data/changes/owner-changes.json'), encoding='utf-8'))['changes']
    for c in chambers:
        for ch in oc:
            geo = json.load(open(os.path.join(ROOT, 'data/changes/owner-changes-geometry.json'), encoding='utf-8'))['changes'].get(ch['id'], {})
            sp = geo.get('slabSplit'); sl = sp and sp[sp['lowered']]
            if sl and Polygon(sl['outlineITM']).distance(Point(c['E'], c['N'])) < 2.0:  # the chamber drains that courtyard area
                c['affectedBy'] = ch['id']
                c['note'] = f"התא תוכנן לניקוז החצרות האנגליות (‎-1.50). {ch['id']} מוריד את החצר הדרומית – לבדוק מחדש מול יועץ האינסטלציה."
    out = {'placement': {'martefToK11_cm': [r3(v) for v in t], 'inlierFraction': r3(sc), 'medianResidual_cm': r3(med),
                         'method': 'ICP על קווי הקירות (A-WALL/S-STRS של הבלוק martef מול IfcWall של k-11.dxf)'},
           'chambers': chambers, 'pipeCrossings': crossings, 'source': SRC}
    os.makedirs(os.path.join(ROOT, 'data/systems'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'data/systems/plumbing-foundations.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out['placement']), chambers, len(crossings), crossings[:10])


if __name__ == '__main__':
    import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()

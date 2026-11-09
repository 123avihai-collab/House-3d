#!/usr/bin/env python3
"""Development spot heights of the permit ground plan ("קרקע פיתוח") -> data/site/development-heights.json

Source : sources/permit/permit-sheet1-gramushka.dwg (cache tools/cache/permit-sheet1.json), layer G-ANNO-DIMS (Revit spot elevations).
Georef : the wall lines of the permit view (A-WALL / S-STRS / S-STRS-MBND) are matched by ICP (translation, same Revit cm) to the
         architect's ground plan block 'pituah' (sources/plumbing/אינסטלציה חתכים הכל.dxf), already placed in ITM by
         tools/extract_openings.py place().
Filter : inside lot 5187 (+0.5 m: labels next to the boundary wall) and z <= the outdoor floor finish (280.48); higher values in this
         view are tops of boundary / retaining walls ("גובה חומה מתוכננת") and ±0.00 of the house (280.50).
Position = the label insertion point (the spot symbol is beside it): accuracy ±0.5 m.
Run: python3 tools/extract_dev_heights.py   (then python3 tools/derive_site.py)
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from shapely.geometry import Polygon, Point
import extract_openings as XO
import extract_framing as F

ROOT = F.ROOT; r3 = F.r3
SRC = 'sources/permit/permit-sheet1-gramushka.dwg'
VIEW = 'קרקע פיתוח'
FINISH_MAX = 280.48      # outdoor floor finish in the same view (deck / terraces, "280.48")
EDGE = 0.5               # label offset from the spot symbol
ACC = 0.5


def main():
    d = json.load(open(os.path.join(ROOT, XO.PERMIT), encoding='utf-8'))
    # the view box: the window / door instances of the view
    NAME = re.compile(r'^(.*)-([A-Z]?\d+)-(.+)$')
    ins = [e['insertionPoint'] for e in d['entities'] if e['type'] == 'INSERT' and (m := NAME.match(e['name'])) and m.group(3) == VIEW and e['insertionPoint']['y'] != 0]
    xs = [p['x'] for p in ins]; ys = [p['y'] for p in ins]
    pad = 700
    bx = (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)
    inb = lambda p: bx[0] < p['x'] < bx[1] and bx[2] < p['y'] < bx[3]
    A = []
    for e in d['entities']:
        if e['type'] == 'LINE' and e['layer'] in ('A-WALL', 'S-STRS', 'S-STRS-MBND') and inb(e['startPoint']):
            A += [(e['startPoint']['x'], e['startPoint']['y']), (e['endPoint']['x'], e['endPoint']['y'])]
    A = np.unique(np.round(np.array(A), 1), axis=0)
    ents, to_itm, _ = XO.place(F.read_dxf(XO.SRC), 'pituah', XO.FLOORS['ground'][1])
    B = []
    for v in ents:
        if v.dxftype() == 'LINE' and v.dxf.layer in ('A-WALL', 'S-STRS', 'S-STRS-MBND'): B += [(v.dxf.start.x, v.dxf.start.y), (v.dxf.end.x, v.dxf.end.y)]
    B = np.unique(np.round(np.array(B), 1), axis=0)
    sc, t, med = F.icp(A, B, tries=200)
    lot = Polygon(json.load(open(os.path.join(ROOT, 'data/site/plot-5187.json')))['ring'])
    zone = lot.buffer(EDGE)
    spots, excl = [], []
    for e in d['entities']:
        if e['type'] != 'MTEXT' or e['layer'] != 'G-ANNO-DIMS' or not re.fullmatch(r'\s*2\d\d\.\d\d\s*', e['text']) or not inb(e['insertionPoint']): continue
        p = e['insertionPoint']; E, N = to_itm(p['x'] + t[0], p['y'] + t[1]); z = float(e['text'])
        rec = {'E': r3(E), 'N': r3(N), 'z': z, 'handle': e['handle'], 'source': f'{SRC} תצוגה "{VIEW}", שכבה G-ANNO-DIMS, ישות {e["handle"]} ("{e["text"].strip()}")'}
        if not zone.contains(Point(E, N)): excl.append({**rec, 'reason': 'מחוץ למגרש'})
        elif z > FINISH_MAX: excl.append({**rec, 'reason': '±0.00 של הבית' if abs(z - 280.5) < 0.005 else 'ראש חומה / קיר תומך (מעל גמר רצפת החוץ 280.48)'})
        else: spots.append(rec)
    out = {'_doc': 'גבהי הפיתוח בתוכנית קומת הקרקע של ההיתר – פני הקרקע / הריצוף הסופיים של מגרש 5187. נוצר ע"י tools/extract_dev_heights.py. '
                   'משמשים כנקודות בקרה לפני הקרקע המתוכננים של המגרש (topoPlanned) במקום 4 פינות המגרש של המפה למשתכן (הערת אביחי 09.11.2026).',
           'source': SRC, 'view': VIEW, 'finishMax': FINISH_MAX, 'positionAccuracy_m': ACC,
           'georef': {'method': 'ICP קווי קירות התצוגה מול בלוק pituah (tools/extract_openings.py place)', 'translation_cm': [r3(v) for v in t],
                      'inlierFraction': r3(sc), 'medianResidual_cm': r3(med)},
           'spots': spots, 'excluded': excl}
    json.dump(out, open(os.path.join(ROOT, 'data/site/development-heights.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'spots {len(spots)}, excluded {len(excl)}, icp inliers {sc:.3f} median {med:.3f} cm')


if __name__ == '__main__':
    main()

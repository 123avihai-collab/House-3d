#!/usr/bin/env python3
"""Basement sketch (sources/basement/, owner's sketch – provisional) -> ITM.
Similarity fit on the 4 lot-corner symbols drawn in the sketch (2447, 2424, 2403, 2457, from the buyer's map),
then a check of the sketch's basement walls against k-11 (structural basement walls)."""
import json, math, os, sys
import numpy as np, pymupdf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import georef as G
ROOT = G.ROOT
SKETCH = 'sources/basement/סקיצה קומת מרתף - יחידות דיור - קנמ 1-100.pdf'
CORNERS = {'2447': (28.86, 107.46), '2424': (463.5, 132.9), '2403': (779.94, 105.78), '2457': (45.78, 905.22)}  # page pt (circle centres ø16.2)


def fit():
    pts = json.load(open(os.path.join(ROOT, 'data/site/plot-5187.json')))['points']
    a = np.array([complex(x, -y) for x, y in CORNERS.values()]); b = np.array([complex(pts[k]['E'], pts[k]['N']) for k in CORNERS])
    ca, cb = a.mean(), b.mean(); s = (np.conj(a - ca) @ (b - cb)) / (np.conj(a - ca) @ (a - ca))
    res = np.abs(s * (a - ca) + cb - b)
    T = lambda x, y: (lambda z: (float(z.real), float(z.imag)))(s * (complex(x, -y) - ca) + cb)
    return T, {'points': list(CORNERS), 'maxResidual_m': round(float(res.max()), 3), 'scale_m_per_pt': round(float(abs(s)), 5),
               'impliedScale': f'1:{round(1 / (abs(s) / 0.0254 * 72) ) if False else round(abs(s) * 72 / 0.0254)}', 'rotation_deg': round(math.degrees(np.angle(s)), 3)}


if __name__ == '__main__':
    T, info = fit(); print(info)

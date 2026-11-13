#!/usr/bin/env python3
"""Tiled access hatches over the pool machine room (Avihai 13.11.2026: "lids that lift, hinge opening to 95°, a hydraulic /
gas strut, a metal frame, tiled with the layout of the paving around").

Openings: the two rectangles "פתח מכונות" / "פתח בור איזון" of the architect's ground-floor plan
(sources/architecture/קומה קרקע- פיתוח היקפי - מבט על קנמ 1-10.pdf, vector rects), measured from the pool's inner east and
south faces (the pool water rectangle of the same plan). Scale checked on the plan's own dimensions (600 / 500 cm).
Placed in ITM from data/structure/pool.json (pool outer ring, wall 0.20).
The machine-room roof slab: its underside from section A ("גובה פנים 180" above the floor 278.33), top = walls top 280.33.
Product data (frame, tray, struts): data/finishes/exterior/hatches-config.json (provisional – a product type, no supplier yet).
Output: data/finishes/exterior/hatches.json.  Run from the repo root:  python3 tools/finishes/derive_hatches.py
"""
import json, math, os
import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
r3 = lambda v: round(float(v), 3)
PDF = 'sources/architecture/קומה קרקע- פיתוח היקפי - מבט על קנמ 1-10.pdf'
CFG = J('data/finishes/exterior/hatches-config.json')
PL = J('data/structure/pool.json'); P, T = PL['pool'], PL['tank']

pg = pymupdf.open(os.path.join(ROOT, PDF))[0]
D = pg.get_drawings()
# scale: the plan's dimension lines 600 (parking width, horizontal) and 500 (parking depth, vertical)
def dimline(label, horiz):
    w = next(w for w in pg.get_text('words') if w[4] == label and (w[1] > 600))
    cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
    best = None
    for dr in D:
        r = dr['rect']
        if horiz and r.height < 1.5 and r.width > 50 and abs(r.y0 - cy) < 8 and r.x0 < cx < r.x1: best = r.width
        if not horiz and r.width < 1.5 and r.height > 50 and abs(r.x0 - cx) < 8 and r.y0 < cy < r.y1: best = r.height
    return best
k600, k500 = dimline('600', True) / 6.0, dimline('500', False) / 5.0   # reported only – these two dimension lines do not match their text at 1:100

# the pool water rectangle (inner faces) and the two opening rectangles (stroked, black) south of it
rects = sorted({(round(d['rect'].x0, 2), round(d['rect'].y0, 2), round(d['rect'].x1, 2), round(d['rect'].y1, 2)) for d in D
                if d.get('color') == (0.0, 0.0, 0.0) and not d.get('fill') and 25 < d['rect'].width < 35 and 25 < d['rect'].height < 35
                and 740 < d['rect'].x0 < 860 and 255 < d['rect'].y0 < 330})
water = max((d['rect'] for d in D if 120 < d['rect'].width < 300 and 40 < d['rect'].height < 120 and 600 < d['rect'].x0 < 700 and 150 < d['rect'].y0 < 200), key=lambda r: r.width * r.height)   # the pool's inner faces
# scale: the pool's inner faces in the plan against the pool of K-21 (pool.json outer ring less the 0.20 walls) – both axes
WALL = 0.20   # pool wall (pool.json note: "קירות 20 ס\"מ")
_O = P['outerITM']; _L, _W = math.dist(_O[0], _O[1]) - 2 * WALL, math.dist(_O[1], _O[2]) - 2 * WALL
kx, ky = water.width / _L, water.height / _W
K = (kx + ky) / 2
if abs(kx - ky) / K > 0.005: raise SystemExit(f'pool scale differs between the axes: {kx:.3f} / {ky:.3f}')
if len(rects) != len(CFG['hatches']): raise SystemExit(f'expected {len(CFG["hatches"])} opening rectangles, found {len(rects)}')

# pool frame in ITM: u = along the long side toward the east end, v = from the south face away from the pool (south)
O = P['outerITM']   # [SE, SW, NW, NE] (pool.json order)
SE, SW, NW = O[0], O[1], O[2]
L = math.dist(SE, SW); u = ((SE[0] - SW[0]) / L, (SE[1] - SW[1]) / L)
wv = math.dist(SW, NW); n = ((NW[0] - SW[0]) / wv, (NW[1] - SW[1]) / wv)   # toward the pool (north)
v = (-n[0], -n[1])
innerSE = (SE[0] - u[0] * WALL + n[0] * WALL, SE[1] - u[1] * WALL + n[1] * WALL)
P2 = lambda a, b: [r3(innerSE[0] - u[0] * a + v[0] * b), r3(innerSE[1] - u[1] * a + v[1] * b)]   # a: west of the inner east face, b: south of the inner south face

hatches = []
for (x0, y0, x1, y1), H in zip(sorted(rects, key=lambda r: r[0]), CFG['hatches']):
    a0, a1 = (water.x1 - x1) / K, (water.x1 - x0) / K
    b0, b1 = (y0 - water.y1) / K, (y1 - water.y1) / K
    ring = [P2(a0, b0), P2(a1, b0), P2(a1, b1), P2(a0, b1)]
    hatches.append(dict(id=H['id'], label=H['label'], openingITM=ring, clear_m=[r3(a1 - a0), r3(b1 - b0)],
                        fromPoolInnerFaces_m=dict(west=[r3(a0), r3(a1)], south=[r3(b0), r3(b1)]), hinge=H['hinge'],
                        status='provisional', source=f"{PDF}: מלבן הפתח (וקטור, נק' {x0}–{x1} × {y0}–{y1}), קנ\"מ {K:.2f} נק'/מ' (מאומת מול הבריכה ב-K-21); מיקום – ממישורי הפנים של הבריכה (data/structure/pool.json outerITM, קיר 0.20)"))

roofBottom = T['floorFinish'] + CFG['roof']['innerHeight_m']
out = dict(_doc='מכסי ריצוף מעל חדר המכונות של הבריכה (אביחי 13.11.2026): מכסה שקוע מרוצף – מסגרת נירוסטה, מגש שממולא בריצוף באותה פריסה כמו הריצוף מסביב, ציר בצד אחד, פתיחה ל-95° בבוכנות. נוצר ע"י tools/finishes/derive_hatches.py – לא לערוך ידנית.',
           source=f'{PDF}; data/structure/pool.json; data/finishes/exterior/hatches-config.json', status='provisional',
           scale=dict(pt_per_m=r3(K), ratio=f'1:{100 * 28.3465 / K:.1f}', fromPoolLength=r3(kx), fromPoolWidth=r3(ky), check='מישורי הפנים של הבריכה בתוכנית מול הבריכה ב-K-21 (pool.json, פחות קירות 0.20) – בשני הצירים',
                      note=f'מידות החניה בתוכנית (600 / 500) לא תואמות את קווי המידה שלהן ב-1:100 ({k600:.2f} / {k500:.2f} נק\'/מ\') – לא שימשו'),
           roof=dict(ringITM=T['outerITM'], bottom=r3(roofBottom), top=T['top'], thickness_m=r3(T['top'] - roofBottom), status='provisional',
                     source=f"data/structure/pool.json tank: floorFinish {T['floorFinish']} + 'גובה פנים 180' (חתך א) = תחתית התקרה; ראש = ראש הקירות {T['top']}"),
           product=CFG['product'], hatches=hatches)
json.dump(out, open(os.path.join(ROOT, 'data/finishes/exterior/hatches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'scale {K:.3f} pt/m = 1:{100 * 28.3465 / K:.1f} (pool length {kx:.3f}, width {ky:.3f}; parking dims 600: {k600:.2f}, 500: {k500:.2f} – not used)')
for h in hatches: print(h['id'], h['label'], 'clear', h['clear_m'], 'from pool faces', h['fromPoolInnerFaces_m'])
print('roof', r3(roofBottom), '..', T['top'])

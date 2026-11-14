#!/usr/bin/env python3
"""כניסת החניה – רצועת אבן משתלבת בתוך המגרש, בין רצפת החניה GS3 לקו המגרש ברחוב (אביחי 14.11.2026:
"תעשה את זה אבנים משתלבות כמו של הרחוב").

היקף: המגרש פחות רצפות הקרקע, אזורים פתוחים, קירות, עמודים וחומות היקפיות – הרכיב שגובל גם ב-GS3 וגם בקו המגרש
שמול הרחוב (data/site/front-street.json frontLine); פתיחה מורפולוגית 5 ס"מ.
פני הריצוף – משטח (TIN) דרך:
  * פני הריצוף של GS3 לאורך השפה המשותפת (data/finishes/tiling/exterior.json – המשטח של החניה, כולל minZ של OC-16),
  * קו המגרש: הגובה המתוכנן של פינת המגרש שעל הקו במפה למשתכן (planned-heights.json lotCorners – 280.00 ליד השער); אבן הגן בקו המגרש
    לוקחת את ההפרש לרחוב (גובה הרחוב – אותו TIN של js/geometry/frontStreet.js – רק לבדיקה, acrossFall),
  * נקודות הגובה בהיתר שבתוך הרצועה (data/site/development-heights.json, למשל 18083 280.00 בשער).
חומר: "מלבן" אפור גרפיט 15/30/7 – נספח פרטי פיתוח 003, פרט 10 ("ריצוף בכניסות לחניות ... בתוך המגרש עד קו הבניין").
שכבות מתחת לאבן – אין פרט: זמני (open-issues).
פלט: data/site/gate-apron.json.  הרצה: python3 tools/derive_gate_apron.py (אחרי tools/finishes/derive_exterior.py)
"""
import json, os, math
import numpy as np
from scipy.interpolate import LinearNDInterpolator
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
J = lambda p: json.load(open(os.path.join(R, p), encoding='utf-8'))
r3 = lambda v: round(float(v), 3)
CFG = {'sample_m': 0.25, 'opening_m': 0.05, 'touch_m': 0.05}

GF = J('data/structure/floor-ground.json'); PER = J('data/structure/perimeter.json'); FS = J('data/site/front-street.json')
EX = J('data/finishes/tiling/exterior.json'); DH = J('data/site/development-heights.json'); H0 = J('data/site/origin.json')['H0']
lot = Polygon(J('data/site/plot-5187.json')['ring'])
gs3 = Polygon(next(s for s in GF['slab'] if s['id'] == 'GS3')['footprintITM'])
front = LineString(FS['frontLine']['points'])

# ---- outline
polys = [Polygon(s['footprintITM'], s.get('holesITM') or []).buffer(0) for s in GF['slab']] + [Polygon(o['footprintITM']).buffer(0) for o in GF['openZones']]
polys += [Polygon(w['ringITM']).buffer(0) for w in PER['walls'] if w.get('ringITM')]
polys += [Polygon(w['footprintITM']).buffer(0) for w in GF['walls'] + GF['columns'] if w.get('footprintITM')]
for r in EX['rooms']:   # the paving zones as derived (slab + the concrete joined to them)
    polys += [Polygon(p['ringITM'], p.get('holesITM') or []).buffer(0) for p in r['parts']]
free = lot.difference(unary_union(polys)).buffer(-CFG['opening_m'], join_style=2).buffer(CFG['opening_m'], join_style=2)
cand = [g for g in getattr(free, 'geoms', [free]) if g.geom_type == 'Polygon' and g.distance(gs3) < CFG['touch_m'] and g.distance(front) < CFG['touch_m']]
if not cand: raise SystemExit('no strip between GS3 and the front line')
P = max(cand, key=lambda g: g.area)

# ---- the parking finish (exterior.json GS3 surface – plane + IDW of the residuals, minZ)
z3 = next(r for r in EX['rooms'] if r['slab'] == 'GS3'); S = z3['surface']


def gs3_z(E, N):
    pz = S['z'] + S['gE'] * (E - S['E']) + S['gN'] * (N - S['N'])
    sw = sr = 0.0
    for e, n, rr in S['res']:
        d2 = (E - e) ** 2 + (N - n) ** 2
        if d2 < 1e-12: sw, sr = 1.0, rr; break
        w = d2 ** (-S['power'] / 2); sw += w; sr += w * rr
    v = pz + (sr / sw if sw else 0.0)
    return max(v, S['minZ']) if S.get('minZ') is not None else v


# ---- the street (buyer's map TIN – the one js/geometry/frontStreet.js builds)
ST = J('data/site/street.json'); PH = J('data/site/planned-heights.json')
pts, zz = [], []
for c in ST['contours']:
    for x, y in c['points']: pts.append((x, y)); zz.append(c['z'])
for s in PH['streetSpots']: pts.append(tuple(s['at'])); zz.append(s['z'])
street = LinearNDInterpolator(np.array(pts), np.array(zz))

ctrl = []   # (E, N, H, kind, ref)
ring = list(P.exterior.coords)[:-1]
edge_gs3 = P.exterior.intersection(gs3.buffer(CFG['touch_m']))
edge_lot = P.exterior.intersection(front.buffer(CFG['touch_m']))


def sample(line):
    out = []
    for g in getattr(line, 'geoms', [line]):
        if g.length < 1e-6: continue
        n = max(1, int(math.ceil(g.length / CFG['sample_m'])))
        out += [g.interpolate(i / n, normalized=True) for i in range(n + 1)]
    return out


for p in sample(edge_gs3): ctrl.append((p.x, p.y, gs3_z(p.x, p.y) + H0, 'gs3', 'פני הריצוף של GS3 (exterior.json)'))
# the lot side of the lot line: the buyer's map planned level of the lot corner on this line (planned-heights.json lotCorners –
# 280.00 at the corner by the gate); the edge stone on the line takes the step down to the street
corners = [c for c in PH['lotCorners'] if edge_lot.distance(Point(c['at'])) < CFG['touch_m']]
if not corners: raise SystemExit('no planned lot-corner level on the strip lot line')
lotH = sum(c['z'] for c in corners) / len(corners)
for p in sample(edge_lot): ctrl.append((p.x, p.y, lotH, 'lotLine', f"קו המגרש – גובה פינת המגרש במפה למשתכן ({', '.join(f'{c[chr(122)]:.2f}' for c in corners)})"))
spots = [s for s in DH['spots'] if not s.get('reason') and P.buffer(0.05).contains(Point(s['E'], s['N']))]
for s in spots: ctrl.append((s['E'], s['N'], s['z'], 'permit', f"נקודת גובה בהיתר {s['handle']} ({s['z']:.2f})"))
# every outline vertex gets a level (TIN over the control points; a vertex outside their hull – nearest control point)
cp = np.array([(c[0], c[1]) for c in ctrl]); cz = np.array([c[2] for c in ctrl])
tin = LinearNDInterpolator(cp, cz)


def zat(E, N):
    v = float(tin(E, N))
    if math.isnan(v): v = float(cz[np.argmin((cp[:, 0] - E) ** 2 + (cp[:, 1] - N) ** 2)])
    return v


zs = [zat(x, y) for x, y in ring]
# steepest fall across the strip (GS3 edge → lot line), for the check
fall = []
for p in sample(edge_lot):
    q = edge_gs3.interpolate(edge_gs3.project(p)) if not edge_gs3.is_empty else None
    if q is None or q.distance(p) < 0.2: continue
    h = float(street(p.x, p.y))
    if not math.isnan(h): fall.append(dict(E=r3(p.x), N=r3(p.y), street=r3(h), lotLine=r3(lotH), step_m=r3(lotH - h), parking=r3(gs3_z(q.x, q.y) + H0), d_m=r3(q.distance(p)),
                                           slope_pct=round((gs3_z(q.x, q.y) + H0 - lotH) / q.distance(p) * 100, 1)))
out = {
    '_doc': 'כניסת החניה בתוך המגרש: רצועת אבן משתלבת בין רצפת החניה GS3 לקו המגרש ברחוב (אביחי 14.11.2026). נוצר ע"י tools/derive_gate_apron.py – לא לערוך ידנית.',
    'source': 'היקף: data/site/plot-5187.json פחות floor-ground.json (רצפות, אזורים פתוחים, קירות, עמודים), perimeter.json ואזורי הריצוף (exterior.json); '
              'גבהים: exterior.json GS3, המפה למשתכן (data/site/street.json, planned-heights.json streetSpots), data/site/development-heights.json; '
              'חומר: sources/neighborhood/development-B1/נספח פרטי פיתוח מהדורה 003.pdf פרט 10',
    'ringITM': [[r3(x), r3(y)] for x, y in ring], 'ringH': [r3(z) for z in zs], 'area_m2': r3(P.area),
    'control': [dict(E=r3(c[0]), N=r3(c[1]), H=r3(c[2]), kind=c[3], ref=c[4]) for c in ctrl],
    'finishMin': r3(min(zs)), 'finishMax': r3(max(zs)), 'lotLineH': r3(lotH), 'acrossFall': fall[::4],
    'material': 'envDriveway', 'paver': {'name': 'אבן משתלבת "מלבן" אפור גרפיט 15/30/7', 'thickness_m': 0.07, 'status': 'source',
                                          'source': 'נספח פרטי פיתוח 003, פרט 10 – "ריצוף בכניסות לחניות, מגרשי בנה ביתך": בתוך המגרש "מלבן" אפור גרפיט 15/30/7; בקו המגרש אבן גן "רמות" (docs/sources-inventory/neighborhood.md ש4)'},
    'layers': [{'id': 'paver', 'label': 'אבן משתלבת 7 ס"מ', 'thickness_m': 0.07, 'status': 'source'},
               {'id': 'sand', 'label': 'מצע חול', 'thickness_m': None, 'status': 'provisional', '_doc': 'אין פרט שכבות בנספח (פרט 10 הוא תוכנית) – open-issues #217'},
               {'id': 'base', 'label': 'מצע מהודק', 'thickness_m': None, 'status': 'provisional'}],
    'status': 'provisional',
}
json.dump(out, open(os.path.join(R, 'data/site/gate-apron.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"gate apron: {P.area:.3f} m², finish {min(zs):.3f}..{max(zs):.3f}, control {len(ctrl)} ({len(spots)} permit spots)")
for f in fall[::6]: print('  across', f)

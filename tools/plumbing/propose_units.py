#!/usr/bin/env python3
"""PB6 (decided 07.11 by recommendation): a SEPARATE sewage pump chamber for the two basement units. The consultant's
PC-1 stays for the English courtyards only.
  PS-1     precast ø100 next to PC-1 at unit level, gas-tight cover, 2 submersible grinder pumps (duty / standby, the
           consultant's pump spec: 20 m³/h, 10 m head), floats + high-level alarm; slab opening in BS1
  gravity  each fixture drops through the basement slab BS1; collectors hung in the void-former layer under the slab
           (consultant's detail "עטיפת בטון"), 2%, around the pile heads, one collector per unit into PS-1
  pumped   HDPE ø75 riser beside PC-1's riser, camel 0.50 m above the cover of S-2 (consultant's note), buried line
           alongside the consultant's pumped line into S-2
  vent     ø75 from PS-1 up to 0.50 m above the roof, at the nearest position clear of concrete along its height
Called from propose.py (needs its Grid class and the architect walls).
"""
import math, os, sys
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union, nearest_points
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_common import J, H0, FG, FR, BAS, MAMAD, concrete, orthoize

r3 = lambda v: round(float(v), 3)


def build(Grid, walls_g, walls_f, shaft_poly, stack_pts, s2_TL):
    N = J('data/plumbing/network.json'); C = J('data/plumbing/catalog.json'); I = J('tools/plumbing/proposal-inputs.json')
    U = I['unitSewer']; FL = I['floors']; FX = I['unitFixtures']
    by = {n['id']: n for n in N['nodes']}
    pc1 = by['PC-1']; CON = concrete()
    bs1 = next(s for s in FR['slabs'] if s['top'] == -2.75)
    slab = Polygon(bs1['outlineITM']).buffer(0)
    top, under = H0 + bs1['top'], H0 + bs1['top'] - bs1['thickness_m']
    TL = H0 + FL['unit']['finish']
    piles = [Point(p['E'], p['N']).buffer(p['diameter_m'] / 2 + U['pileClear_m']) for p in J('data/structure/piles.json')['piles'] if p['zone'] == 'basement']
    bwalls = [P for k, e, P, b, t, st in CON if k == 'קיר מרתף']
    rO = 0.5 + C['chambers']['rings']['1.0']['wall']; rPC = pc1['D_m'] / 2 + C['chambers']['rings'][str(pc1['D_m'])]['wall']
    # ---- PS-1 position: ring of candidates around PC-1, inside BS1, clear of walls / piles / PC-1, closest to the fixtures
    fx = [(u, k, (E, N_)) for u in ('unit1', 'unit2') for k, E, N_ in FX[u]]
    best = None
    for rad in np.arange(rPC + rO + U['chamberGap_m'], 3.0, 0.1):
        for a in range(0, 360, 15):
            q = (pc1['E'] + rad * math.cos(math.radians(a)), pc1['N'] + rad * math.sin(math.radians(a)))
            c = Point(q).buffer(rO)
            if not slab.buffer(-0.05).contains(c) or any(c.intersects(w) for w in bwalls) or any(c.intersects(p) for p in piles): continue
            cost = sum(math.dist(q, f[2]) for f in fx)
            if best is None or cost < best[0]: best = (cost, q, rad)
        if best: break
    _, ps, _ = best
    # ---- gravity collectors under the slab
    region = slab.buffer(0.3)
    g = Grid(region, [], bwalls, [], piles + [Point(pc1['E'], pc1['N']).buffer(rPC + 0.05)])
    d110 = C['pipes']['HDPE']['sizes']['110']['OD']; s = U['slope']
    il_top = under - U['hangerGap_m'] - d110        # highest invert of a ø110 crown just under the slab
    runs, sleeves, inlets = [], [], []
    for u in ('unit1', 'unit2'):
        items = sorted([f for f in fx if f[0] == u], key=lambda f: -math.dist(f[2], ps))
        ent = (ps[0] + (items[0][2][0] - ps[0]) / math.dist(items[0][2], ps) * (0.5 - 0.02), ps[1] + (items[0][2][1] - ps[1]) / math.dist(items[0][2], ps) * (0.5 - 0.02))
        main = g.route(items[0][2], ent)
        if main is None: raise SystemExit(f'PB6: no route for {u}')
        Lm = sum(math.dist(main[i], main[i + 1]) for i in range(len(main) - 1))
        # lower the collector so that every branch crown stays under the slab (branch inverts crown-aligned at the wye)
        need = 0.0; brs = []
        for uu, kind, p in items[1:]:       # route the branches first, then lower the collector so every branch crown stays under the slab
            D = 110 if kind == 'wc' else 50; d = C['pipes']['HDPE']['sizes'][str(D)]['OD']
            j = nearest_points(LineString(main), Point(p))[0]
            br = g.route(p, (j.x, j.y)) or [p, (j.x, j.y)]
            Lb = sum(math.dist(br[i], br[i + 1]) for i in range(len(br) - 1))
            brs.append((kind, p, D, d, j, br, Lb))
            up = il_top - s * LineString(main).project(j) + (d110 - d) + s * Lb + d
            need = max(need, up - (under - U['hangerGap_m']))
        il_far = il_top - need; il_in = il_far - s * Lm
        def il_at(pt):
            L_ = LineString(main); return il_far - s * L_.project(Point(pt))
        acc, p3 = 0.0, [[r3(main[0][0]), r3(main[0][1]), r3(TL)], [r3(main[0][0]), r3(main[0][1]), r3(il_far + d110 / 2)]]
        for i in range(1, len(main)):
            acc += math.dist(main[i - 1], main[i]); p3.append([r3(main[i][0]), r3(main[i][1]), r3(il_far - s * acc + d110 / 2)])
        kind0 = items[0][1]
        runs.append({'id': f'PB6-{u.upper()}-MAIN', 'system': 'sewage', 'D_mm': 110, 'material': 'HDPE', 'pts3d': p3, 'from': f'{u.upper()}-{kind0}', 'to': 'PS-1',
                     'ILup': r3(il_far), 'ILdown': r3(il_in), 'slope': s, 'length_m': r3(Lm), 'floor': 'unit', 'status': 'proposal', 'loweredBy_m': r3(need),
                     'note': f'קו מאסף {"יחידה 1" if u == "unit1" else "יחידה 2"}: יורד דרך רצפת המרתף בקבועה הרחוקה ונתלה מתחת לרצפה בשכבת ארגזי ההפרדה (פרט "עטיפת בטון" של היועץ), סביב ראשי הכלונסאות, אל PS-1'})
        inlets.append({'run': f'PB6-{u.upper()}-MAIN', 'IL': r3(il_in), 'D_mm': 110, 'dir': [r3((main[-2][0] - ps[0])), r3((main[-2][1] - ps[1]))]})
        sleeves.append({'pipe': f'PB6-{u.upper()}-MAIN', 'floor': 'unit', 'at': [r3(main[0][0]), r3(main[0][1]), r3(top - bs1['thickness_m'] / 2)], 'through': 'רצפת המרתף BS1',
                        'sleeve': 'שרוול PVC ø160 יצוק ברצפה (תיאום קונסטרוקטור)', 'sleeveD_mm': 160, 'material': 'PVC', 'axis': 'v'})
        for kind, p, D, d, j, br, Lb in brs:
            il_dn = il_at((j.x, j.y)) + (d110 - d); il_up = il_dn + s * Lb
            ok = il_up + d <= under - U['hangerGap_m'] + 1e-3
            acc, q3 = 0.0, [[r3(p[0]), r3(p[1]), r3(TL)], [r3(p[0]), r3(p[1]), r3(il_up + d / 2)]]
            for i in range(1, len(br)):
                acc += math.dist(br[i - 1], br[i]); q3.append([r3(br[i][0]), r3(br[i][1]), r3(il_up - s * acc + d / 2)])
            runs.append({'id': f'PB6-{u.upper()}-{kind}', 'system': 'sewage', 'D_mm': D, 'material': 'HDPE', 'pts3d': q3, 'from': f'{u.upper()}-{kind}', 'to': f'PB6-{u.upper()}-MAIN',
                         'ILup': r3(il_up), 'ILdown': r3(il_dn), 'slope': s, 'length_m': r3(Lb), 'floor': 'unit', 'status': 'proposal', 'fitsUnderSlab': ok,
                         'note': f'ענף {kind} ø{D} מתחת לרצפה, מסתעף 45° לקו המאסף' + ('' if ok else ' – ⚠️ הקודקוד גבוה מתחתית הרצפה: להנמיך את הקו המאסף')})
            sleeves.append({'pipe': f'PB6-{u.upper()}-{kind}', 'floor': 'unit', 'at': [r3(p[0]), r3(p[1]), r3(top - bs1['thickness_m'] / 2)], 'through': 'רצפת המרתף BS1',
                            'sleeve': f'שרוול PVC ø{110 if D == 50 else 160} יצוק ברצפה (תיאום קונסטרוקטור)', 'sleeveD_mm': 110 if D == 50 else 160, 'material': 'PVC', 'axis': 'v'})
    il_in = min(x['IL'] for x in inlets); IL = il_in - U['sumpDepth_m']
    chamber = {'id': 'PS-1', 'E': r3(ps[0]), 'N': r3(ps[1]), 'D_m': 1.0, 'TL': r3(TL), 'IL': r3(IL), 'inlets': inlets, 'distToPC1_m': r3(math.dist(ps, (pc1['E'], pc1['N']))),
               'pumps': U['pumps'], 'cover': U['cover'], 'status': 'proposal',
               'why': f'PB6 לפי ההמלצה: תא נפרד לשפכי היחידות, PC-1 נשאר לניקוז החצרות. ø100 טרומי ב-{math.dist(ps, (pc1["E"], pc1["N"])):.2f} מ\' מ-PC-1, במפלס היחידה. '
                      f'כניסות ב-{il_in:.2f}, בור משאבה {U["sumpDepth_m"]:.2f} מ\' מתחתן (נפח הפעלה ומשאבה שנייה) – תחתית {IL:.2f}. דורש פתח ברצפה BS1.'}
    # ---- rising main: riser beside PC-1's riser, camel above S-2 cover + 0.50, buried along the consultant's pumped line into S-2
    pru, prg, j1, s2 = by['PRU@unit'], by['PRG@ground'], by['J1@ground'], by['S-2']
    path = LineString([(prg['E'], prg['N']), (j1['E'], j1['N']), (s2['E'], s2['N'])])
    off = path.parallel_offset(U['risingOffset_m'], 'right')
    if off.is_empty or off.length < 0.5: off = path.parallel_offset(U['risingOffset_m'], 'left')
    oc = list(off.coords)
    if math.dist(oc[0], (prg['E'], prg['N'])) > math.dist(oc[-1], (prg['E'], prg['N'])): oc = oc[::-1]
    crest = s2_TL + 0.50; Dp = U['risingD_mm']
    riser = (pru['E'] + (oc[0][0] - prg['E']), pru['N'] + (oc[0][1] - prg['N']))
    s2in = (s2['E'] + (oc[-2][0] - s2['E']) / math.dist(oc[-2], (s2['E'], s2['N'])) * 0.38, s2['N'] + (oc[-2][1] - s2['N']) / math.dist(oc[-2], (s2['E'], s2['N'])) * 0.38)
    rm = [[r3(ps[0]), r3(ps[1]), r3(IL + 0.35)], [r3(ps[0]), r3(ps[1]), r3(TL - 0.25)], [r3(riser[0]), r3(riser[1]), r3(TL - 0.25)], [r3(riser[0]), r3(riser[1]), r3(crest)],
          [r3(oc[0][0]), r3(oc[0][1]), r3(crest)], [r3(oc[0][0]), r3(oc[0][1]), None]] + [[r3(x), r3(y), None] for x, y in oc[1:-1]] + [[r3(s2in[0]), r3(s2in[1]), r3(s2_TL - 0.35)]]
    rm = [list(p) for p in orthoize([tuple(p) for p in rm])]
    runs.append({'id': 'PB6-RISING', 'system': 'pumped', 'D_mm': Dp, 'material': 'HDPE', 'pts3d': rm, 'cover_m': I['site']['hoseReel']['cover_m'], 'from': 'PS-1', 'to': 'S-2',
                 'length_m': r3(sum(math.dist(rm[i][:2], rm[i + 1][:2]) for i in range(len(rm) - 1)) + (crest - IL)), 'floor': 'unit', 'status': 'proposal',
                 'note': f'קו סניקה HDPE ø{Dp} (כמו פרט "תא איסוף עם משאבה"), אל-חוזר + ברז ניתוק לכל משאבה, עולה ליד העולה של PC-1, גמל ב-{crest:.2f} (50 ס"מ מעל מכסה שוחה 2), '
                         f'ומשם בקרקע לצד קו הסניקה של היועץ אל שוחה 2'})
    # ---- vent ø75: nearest vertical clear of concrete, near an architect wall, from PS-1 to roof + 0.5
    zr = H0 + FL['roof']['finish']; vtop = zr + 0.50
    taken = [Point(p) for p in stack_pts]
    vbest = None
    for rad in np.arange(0.0, 2.6, 0.05):
        for a in range(0, 360, 20 if rad > 0 else 360):
            q = (ps[0] + rad * math.cos(math.radians(a)), ps[1] + rad * math.sin(math.radians(a)))
            c = Point(q).buffer(0.0375 + 0.03)
            if any(c.intersects(P) for k, e, P, b, t, st in CON if t > -2.6 and b < 6.85): continue
            if c.intersects(MAMAD) or c.intersects(shaft_poly.buffer(0.03)) or any(Point(q).distance(x) < 0.16 for x in taken): continue
            wd = min(walls_g.distance(Point(q)), walls_f.distance(Point(q)))
            cost = rad + 2.0 * max(0, wd - 0.15)
            if vbest is None or cost < vbest[0]: vbest = (cost, q, wd)
    _, vq, vwd = vbest
    vpts = [[r3(ps[0]), r3(ps[1]), r3(TL - 0.20)], [r3(vq[0]), r3(vq[1]), r3(TL - 0.20)], [r3(vq[0]), r3(vq[1]), r3(vtop)]]
    runs.append({'id': 'PB6-VENT', 'system': 'vent', 'D_mm': 75, 'material': 'HDPE', 'pts3d': vpts, 'from': 'PS-1', 'to': 'אוויר מעל הגג', 'floor': 'unit',
                 'length_m': r3(math.dist(ps, vq) + vtop - TL + 0.2), 'status': 'proposal', 'distToWall_m': r3(vwd),
                 'note': f'אוורור התא ø75 עד 0.50 מעל הגג (כמו הקולטנים, PL8). מיקום העולה: הקרוב ל-PS-1 שלא חוצה בטון לכל גובהו, {vwd * 100:.0f} ס"מ מקו קיר אדריכלי – בהלבשה / בקיר, לפי האדריכל. '
                         'מאוורר גם את הקווים המאספים (פתוחים לתא); בראש כל קו מאסף – שסתום אוורור (לאישור היועץ)'})
    for lvl, nm in ((H0 - 0.15, 'תקרת המרתף / רצפת הקרקע'), (H0 + 3.70, 'תקרת הקרקע +3.70'), (zr, 'תקרת הגג +6.85')):
        sleeves.append({'pipe': 'PB6-VENT', 'floor': 'unit', 'at': [r3(vq[0]), r3(vq[1]), r3(lvl - 0.1)], 'through': nm, 'sleeve': 'שרוול PVC ø110 + צווארון אש', 'sleeveD_mm': 110, 'material': 'PVC', 'axis': 'v'})
    sleeves.append({'pipe': 'PB6-RISING', 'floor': 'unit', 'at': [r3(riser[0]), r3(riser[1]), r3(H0 - 0.25)], 'through': 'תקרת המרתף / רצפת הקרקע', 'sleeve': f'שרוול PVC ø110 יצוק (כמו עולה PC-1)', 'sleeveD_mm': 110, 'material': 'PVC', 'axis': 'v'})
    sleeves.append({'pipe': 'PS-1', 'floor': 'unit', 'at': [r3(ps[0]), r3(ps[1]), r3(top - 0.12)], 'through': 'רצפת המרתף BS1', 'sleeve': f'פתח ø{(rO + 0.05) * 200:.0f} ס"מ ברצפה לחוליות התא (תיאום קונסטרוקטור)', 'sleeveD_mm': None, 'material': 'פתח ביציקה', 'axis': 'v'})
    checks = [{'what': 'ענפים מתחת לרצפה', 'ok': all(r.get('fitsUnderSlab', True) for r in runs), 'text': ', '.join(f'{r["id"]}: {"נכנס" if r.get("fitsUnderSlab", True) else "לא נכנס"}' for r in runs if 'fitsUnderSlab' in r)}]
    return {'chamber': chamber, 'runs': runs, 'sleeves': sleeves, 'checks': checks, 'superseded': []}

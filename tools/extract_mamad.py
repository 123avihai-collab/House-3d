#!/usr/bin/env python3
"""Mamad (shelter) window, sliding door and cast-in sleeves per the architect's plan -> data/architecture/mamad.json.

Plan      : sources/plumbing/אינסטלציה חתכים הכל.dxf, block 'pituah' (the architect's ground-floor plan) – the Revit families
            "Tovna_Mamad_Window_Dubble" (two steel blast leaves that slide into two wall niches, inner glass wing),
            "דלת ממד נגררת - פלרז" (sliding blast door, drawn open beside the opening), "צינור אורור 4" / "Zinor8_Ext"
            (sleeves with flanges), and the two niches of the window drawn on A-WALL. Placed on k-21 like the openings.
Elevation : sources/architecture/חזית מזרח - צד יחידת דיור….pdf (the sheet titled "חזית מערבית", 1:100, vector):
            level tags +1.10 / +2.10 of the window, the window outline, the two ø20 flanges of the 4" sleeves.
Everything is stored in the local frame of each family: u along the wall, v across it (ITM unit vectors), metres.
Also fixes in data/architecture/openings.json + data/structure/floor-ground.json: G09 sill / head per the elevation tags,
no K-21 "pocket" inside the opening (the niches are in the walls, per the architect), and drops the sleeve that is only
the ground-floor sleeve seen from above in the first-floor view.
Run after tools/extract_openings.py:  python3 tools/extract_mamad.py
"""
import json, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezdxf
import numpy as np
import pymupdf
from shapely.geometry import Polygon, Point
import extract_openings as X

F = X.F; ROOT = F.ROOT; r3 = F.r3
ELEV = 'sources/architecture/חזית מזרח - צד יחידת דיור - מבט על קנמ 1-10.pdf'
PT_PER_M = 72 / 0.0254 / 100          # 1:100
cm = lambda v: r3(v / 100)


def lines_of(block):
    return [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y), e.dxf.layer) for e in block if e.dxftype() == 'LINE']


def rects(L, tol=0.06):
    """axis-aligned closed rectangles drawn with 4 lines: [(u0, u1, v0, v1)]"""
    H = [(min(a[0], b[0]), max(a[0], b[0]), a[1]) for a, b, _ in L if abs(a[1] - b[1]) < tol and abs(a[0] - b[0]) > tol]
    V = [(a[0], min(a[1], b[1]), max(a[1], b[1])) for a, b, _ in L if abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) > tol]
    out = set()
    for i, (x0, x1, y0) in enumerate(H):
        for (X0, X1, y1) in H[i + 1:]:
            if abs(x0 - X0) > tol or abs(x1 - X1) > tol or abs(y0 - y1) < tol: continue
            lo, hi = min(y0, y1), max(y0, y1)
            if all(any(abs(vx - x) < tol and abs(a - lo) < tol and abs(b - hi) < tol for vx, a, b in V) for x in (x0, x1)):
                out.add((round(x0, 2), round(x1, 2), round(lo, 2), round(hi, 2)))
    return sorted(out)


def frame_of(v, to_itm):
    """local frame of an INSERT: origin (ITM), u = family x, v = family y (ITM unit vectors)"""
    x, y, r = v.dxf.insert.x, v.dxf.insert.y, math.radians(v.dxf.rotation)
    L = lambda a, b: (x + a * math.cos(r) - b * math.sin(r), y + a * math.sin(r) + b * math.cos(r))
    o = np.array(to_itm(*L(0, 0))); U = np.array(to_itm(*L(100, 0))) - o; V = np.array(to_itm(*L(0, 100))) - o
    inv = lambda px, py: ((px - x) * math.cos(r) + (py - y) * math.sin(r), -(px - x) * math.sin(r) + (py - y) * math.cos(r))
    return o, U / np.linalg.norm(U), V / np.linalg.norm(V), inv


def elevation():
    """window outline, level tags and sleeve flanges of the west elevation -> levels (m, rel ±0.00)"""
    p = pymupdf.open(os.path.join(ROOT, ELEV))[0]
    D = p.get_drawings()
    blue = [d['rect'] for d in D if d.get('fill') and tuple(round(c, 2) for c in d['fill']) == (0.0, 0.0, 1.0) and 8 < d['rect'].width < 20 and 15 < d['rect'].height < 35]
    tri = [d['rect'] for d in D if d.get('fill') == (0.0, 0.0, 0.0) and len(d['items']) == 3 and 10 < d['rect'].width < 25]
    words = [(w[0], w[1], w[2], w[3], w[4]) for w in p.get_text('words') if re.fullmatch(r'\d\.\d\d\+', w[4])]
    best = None
    for b in blue:
        # the window outline: the unfilled rectangle around the glass with a level triangle right above and right below
        outl = [d['rect'] for d in D if not d.get('fill') and d['rect'].contains(b) and d['rect'].width < 40 and d['rect'].height < 40]
        up = [t for t in tri if t.y1 <= b.y0 + 0.5 and b.y0 - t.y1 < 6 and t.x0 < b.x1 and t.x1 > b.x0]
        dn = [t for t in tri if t.y0 >= b.y1 - 0.5 and t.y0 - b.y1 < 6 and t.x0 < b.x1 and t.x1 > b.x0]
        if outl and up and dn: best = (b, min(outl, key=lambda r: r.width * r.height), up[0], dn[0])
    if not best: raise SystemExit('mamad window not found in the elevation')
    b, o, up, dn = best
    tag = lambda t: float(min(words, key=lambda w: math.hypot((w[0] + w[2]) / 2 - (t.x0 + t.x1) / 2, (w[1] + w[3]) / 2 - (t.y0 + t.y1) / 2))[4][:-1])
    head, sill = tag(up), tag(dn)                         # +2.10 / +1.10: the triangle tips touch the frame
    scale = (dn.y0 - up.y1) / (head - sill)                # pt per m, checked against the nominal 1:100
    z = lambda y: sill + (dn.y0 - y) / PT_PER_M
    circ = {}
    for d in D:
        r = d['rect']
        if d.get('fill') or not all(i[0] == 'c' for i in d['items']) or len(d['items']) != 2: continue
        if abs(r.width - 2 * r.height) < 0.2 and 4 < r.width < 8 and abs(r.y0 - o.y0) < 40:    # half circles (upper / lower)
            circ.setdefault(round((r.x0 + r.x1) / 2, 1), []).append(r)
    fl = [{'x': x, 'y': max(r.y0 for r in rs) if len(rs) == 1 else sorted(r.y0 for r in rs)[-1], 'dia_m': r3(rs[0].width / PT_PER_M)} for x, rs in circ.items()]
    return {'sill': sill, 'head': head, 'scaleCheck_ptPerM': round(scale, 3), 'frameX': [o.x0, o.x1], 'frameTop': r3(z(o.y0)), 'frameBottom': r3(z(o.y1)),
            'glassX': [b.x0, b.x1], 'flanges': [{'x': f['x'], 'zRel': r3(z(f['y'])), 'dia_m': f['dia_m']} for f in fl]}


def main():
    doc = ezdxf.readfile(os.path.join(ROOT, X.SRC)); msp = doc.modelspace()
    ents, to_itm, pl = X.place(msp, 'pituah', F.K21)
    OPN = json.load(open(os.path.join(ROOT, 'data/architecture/openings.json'), encoding='utf-8'))
    FG = json.load(open(os.path.join(ROOT, 'data/structure/floor-ground.json'), encoding='utf-8'))
    walls = {w['id']: Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0) for w in FG['walls']}
    in_wall = lambda P: next((k for k, g in walls.items() if g.buffer(0.005).contains(Point(*P))), None)
    E = elevation()
    src_plan = lambda v: f'{X.SRC} בלוק pituah, משפחה "{v.dxf.name}"'
    vec = lambda a: [round(float(a[0]), 6), round(float(a[1]), 6)]
    pt = lambda a: [r3(a[0]), r3(a[1])]
    out = {'_doc': 'Mamad window / sliding door / cast-in sleeves per the architect\'s plan. Generated by tools/extract_mamad.py – do not edit by hand. '
                   'Local frame of each element: originITM + u·uITM + v·vITM (metres); levels relative to ±0.00.',
           'elevation': {'source': ELEV + ' (כותרת הגיליון: "חזית מערבית", 1:100)', **{k: E[k] for k in ('sill', 'head', 'scaleCheck_ptPerM')}, 'nominal_ptPerM': round(PT_PER_M, 3)}}

    # ---------------- window ----------------
    v = next(e for e in ents if e.dxftype() == 'INSERT' and 'Mamad_Window' in e.dxf.name)
    o, U, V, inv = frame_of(v, to_itm)
    L = lines_of(doc.blocks[v.dxf.name]); R = rects(L)
    leaves = [q for q in R if q[1] - q[0] > 40 and q[2] < 1 < q[3] and q[3] - q[2] < 6]          # the two steel leaves (55 × 3.5)
    wing = [q for q in R if q[3] <= -2.5 and q[2] >= -9.5]                                         # inner glass wing (stiles / pane)
    pane = min(wing, key=lambda q: q[3] - q[2])
    wu = (min(q[0] for q in wing), max(q[1] for q in wing)); wv = (min(q[2] for q in wing), max(q[3] for q in wing))
    fr = [a[0] for a, b, _ in L if abs(a[0] - b[0]) < 0.06 and abs(min(a[1], b[1]) - wv[1]) < 0.1 and max(a[1], b[1]) < 1]
    frame_u = (min(fr), max(fr))                                                                     # outer faces of the jambs (rise from the wing line)
    # the niches: closed A-WALL rectangles of the plan next to the frame, on the leaf line
    AW = [(inv(e.dxf.start.x, e.dxf.start.y), inv(e.dxf.end.x, e.dxf.end.y), 'A-WALL') for e in ents if e.dxftype() == 'LINE' and e.dxf.layer == 'A-WALL']
    AW = [l for l in AW if all(-80 < p[0] < 170 and -12 < p[1] < 12 for p in l[:2])]
    nu = sorted({round(p[0], 2) for l in AW for p in l[:2]}); nv = sorted({round(p[1], 2) for l in AW for p in l[:2]})
    niches = [(nu[0], max(u for u in nu if u < 45), nv[0], nv[-1]), (min(u for u in nu if u > 45), nu[-1], nv[0], nv[-1])]
    lw = leaves[0][1] - leaves[0][0]
    mid = (frame_u[0] + frame_u[1]) / 2
    zb, zt = E['frameBottom'], E['head']                    # the tip of the +2.10 tag touches the top of the frame
    # elevation x <-> u: the frame outline spans the jamb faces; the glass strip between the half-open leaves fixes the direction
    drawn_gap = (leaves[0][1], leaves[1][0])
    xu = lambda x: frame_u[1] - (x - E['frameX'][0]) / PT_PER_M * 100     # u decreases with x (seen from outside)
    gap_el = sorted(xu(x) for x in E['glassX'])
    win = {
        'id': 'G09', 'name': v.dxf.name.split('-10')[0].strip(), 'originITM': pt(o), 'uITM': vec(U), 'vITM': vec(V),
        'vNote': 'v חיובי = כלפי חוץ', 'sillRel': E['sill'], 'headRel': E['head'],
        'frame': {'u': [cm(frame_u[0]), cm(frame_u[1])], 'clearU': [cm(wu[0]), cm(wu[1])], 'zRel': [E['sill'], E['head']], 'sillProfile_m': r3(zb - E['sill'])},
        'leaves': [], 'glass': {'u': [cm(wu[0]), cm(wu[1])], 'v': [cm(wv[0]), cm(wv[1])], 'paneV': [cm(pane[2]), cm(pane[3])], 'stile_m': cm(pane[0] - wu[0]), 'zRel': [zb, zt],
                                'status': 'approx', 'note': 'כנף זכוכית פנימית – מוצגת סגורה. סוג הפתיחה (ציר / קיפ) לא מופיע בתוכנית.'},
        'niches': [], 'status': 'source',
        'check': {'drawnGapPlan_cm': [round(drawn_gap[0], 1), round(drawn_gap[1], 1)], 'drawnGapElevation_cm': [round(gap_el[0], 1), round(gap_el[1], 1)],
                  'frameWidthElevation_m': r3((E['frameX'][1] - E['frameX'][0]) / PT_PER_M), 'frameWidthPlan_m': cm(frame_u[1] - frame_u[0])},
        'source': f'{src_plan(v)} + גומחות בשכבה A-WALL; גבהים: {ELEV}',
    }
    for i, q in enumerate(sorted(leaves)):
        side = -1 if i == 0 else 1
        closed = (mid - lw, mid) if side < 0 else (mid, mid + lw)             # the leaves meet on the axis of the frame
        n = niches[0] if side < 0 else niches[1]
        opened = (n[0], n[0] + lw) if side < 0 else (n[1] - lw, n[1])          # fully inside its niche
        win['leaves'].append({'id': f'G09-L{i + 1}', 'closedU': [cm(closed[0]), cm(closed[1])], 'openU': [cm(opened[0]), cm(opened[1])], 'drawnU': [cm(q[0]), cm(q[1])],
                              'v': [cm(q[2]), cm(q[3])], 'zRel': [zb, zt], 'width_m': cm(lw), 'thickness_m': cm(q[3] - q[2]), 'travel_m': cm(abs(opened[0] - closed[0])),
                              'status': 'approx', 'note': 'מידות הכנף והגומחה – מהתוכנית. מצב סגור = שתי הכנפיים נפגשות בציר המשקוף; מצב פתוח = הכנף כולה בגומחה (בתוכנית הכנפיים משורטטות חצי פתוחות).'})
        c = o + U * ((n[0] + n[1]) / 200) + V * ((n[2] + n[3]) / 200)
        win['niches'].append({'u': [cm(n[0]), cm(n[1])], 'v': [cm(n[2]), cm(n[3])], 'zRel': [zb, zt], 'length_m': cm(n[1] - n[0]), 'width_m': cm(n[3] - n[2]), 'inWall': in_wall(c),
                              'zStatus': 'approx', 'note': 'גומחה (כוך) לכנף הפלדה, בתוך קיר הבטון – מתאר מהתוכנית (A-WALL). גובה הגומחה = גובה הכנף (אין חתך).'})
    out['window'] = win

    # ---------------- sliding door ----------------
    v = next(e for e in ents if e.dxftype() == 'INSERT' and 'דלת ממד' in e.dxf.name)
    o, U, V, inv = frame_of(v, to_itm)
    L = lines_of(doc.blocks[v.dxf.name])
    FRM = [p for a, b, ly in L if ly == 'A-DOOR-FRAM' for p in (a, b)]
    wall_v = (min(p[1] for p in FRM), max(p[1] for p in FRM))
    clear = min(abs(p[0]) for p in FRM)
    long_ = [(a, b) for a, b, ly in L if abs(a[1] - b[1]) < 0.06 and abs(a[0] - b[0]) > 60 and min(a[1], b[1]) > wall_v[1] + 1]
    lv = (min(a[1] for a, b in long_), max(a[1] for a, b in long_))
    ends = [a[0] for a, b, ly in L if abs(a[0] - b[0]) < 0.06 and abs(a[1] - b[1]) > 2 and lv[0] - 0.5 <= min(a[1], b[1]) and max(a[1], b[1]) <= lv[1] + 0.5]
    lu = (min(ends), max(ends)); lw = lu[1] - lu[0]
    hnd = [p for a, b, ly in L for p in (a, b) if min(a[0], b[0]) >= lu[1] - 0.06 and max(a[0], b[0]) > lu[1] + 0.3 and lv[0] < p[1] < lv[1]]
    g21 = next(q for q in OPN['openings'] if q['id'] == 'G21')
    park = o + U * ((lu[0] + lu[1]) / 200) + V * (wall_v[1] / 100 - 0.05)
    out['door'] = {
        'id': 'G21', 'name': v.dxf.name.split('-10')[0].strip(), 'originITM': pt(o), 'uITM': vec(U), 'vITM': vec(V), 'vNote': 'v חיובי = צד הכנף (מחוץ לממ"ד)',
        'clearU': [cm(-clear), cm(clear)], 'wallV': [cm(wall_v[0]), cm(wall_v[1])],
        'leaf': {'id': 'G21-L1', 'openU': [cm(lu[0]), cm(lu[1])], 'closedU': [cm(-lw / 2), cm(lw / 2)], 'v': [cm(lv[0]), cm(lv[1])], 'width_m': cm(lw), 'thickness_m': cm(lv[1] - lv[0]),
                 'travel_m': cm(-lw / 2 - lu[0]), 'zRel': [g21['floorFinishRel'], g21['headRel']], 'zStatus': 'provisional', 'parkWall': in_wall(park),
                 'handle': {'u': [cm(lu[1]), cm(max(p[0] for p in hnd))], 'v': [cm(min(p[1] for p in hnd)), cm(max(p[1] for p in hnd))]} if hnd else None,
                 'status': 'approx', 'note': 'כנף נגררת על פני הקיר, מחוץ לממ"ד. בתוכנית הכנף משורטטת פתוחה (חונה לצד הפתח); מצב סגור = ממורכזת על הפתח. '
                                             'גובה הכנף – זמני (גובה הפתח 2.10, אין חתך / רשימת מסגרות).'},
        'status': 'approx', 'source': src_plan(v),
    }

    # ---------------- sleeves ----------------
    OPN['sleeves'] = [s for s in OPN['sleeves'] if s['floor'] == 'ground' or
                      not any(t['floor'] == 'ground' and math.dist(t['centerITM'], s['centerITM']) < 0.05 for t in OPN['sleeves'])]
    wo, wU = np.array(win['originITM']), np.array(win['uITM'])
    sl = []
    for v in ents:
        if v.dxftype() != 'INSERT' or not re.search(r'צינור|Zinor', v.dxf.name): continue
        o, U, V, inv = frame_of(v, to_itm)
        s = next((q for q in OPN['sleeves'] if math.dist(q['centerITM'], o) < 0.05), None)
        if not s or any(math.dist(q['centerITM'], s['centerITM']) < 0.05 for q in sl): continue
        L = lines_of(doc.blocks[v.dxf.name]); r = s['dia_m'] * 50
        sym = sorted((a[1], abs(a[0])) for a, b, _ in L if abs(a[1] - b[1]) < 0.06 and abs(a[0] + b[0]) < 0.2 and abs(a[0]) > r + 1.5)
        fl = []
        for y, hw in sym:                                   # flange = a run of full-width lines across the pipe
            if fl and y - fl[-1][1] < 4.5 and abs(hw - fl[-1][2]) < 1.5: fl[-1][1] = y
            else: fl.append([y, y, hw])
        fl = [f for f in fl if f[1] - f[0] > 0.5]
        body = [p[1] for a, b, _ in L for p in (a, b) if abs(a[0] - b[0]) < 0.06 and abs(abs(a[0]) - r) < 0.6]     # the pipe walls
        pv = (min([min(body)] + [f[1] for f in fl if f[1] < 0]), max([max(body)] + [f[0] for f in fl if f[0] > 0]))
        t = s.get('hostThickness_m') or 0
        rec = {**{k: s[k] for k in ('id', 'floor', 'name', 'revitId', 'centerITM', 'dia_m', 'host', 'hostThickness_m')}, 'axisITM': vec(V),
               'pipeV': [cm(pv[0]), cm(pv[1])], 'flanges': [{'v': [cm(f[0]), cm(f[1])], 'dia_m': cm(2 * f[2])} for f in fl],
               'zRel': s['zRel'], 'status': s['status'], 'note': s['note'], 'source': s['source']}
        u_win = float((np.array(s['centerITM']) - wo) @ wU) * 100
        hit = [f for f in E['flanges'] if abs(xu(f['x']) - u_win) < 4]
        if hit:
            rec.update(zRel=hit[0]['zRel'], status='source', elevationFlangeDia_m=hit[0]['dia_m'],
                       note='גובה המרכז – נמדד בחזית המערבית (עיגול האוגן ø20); קוטר מהשם (אינץ\'); אוגנים ואורך – מהמשפחה בתוכנית',
                       source=s['source'] + f'; גובה: {ELEV}')
            s['zRel'] = hit[0]['zRel']
        elif rec['zRel'] is None:
            rec['note'] = 'אין גובה במקורות (קיר פנימי, לא נראה בחזיתות) – מוצג בגובה תצוגה זמני; אוגנים ואורך – מהמשפחה בתוכנית'
        else:
            rec['note'] += '; אוגנים ואורך – מהמשפחה בתוכנית'
        sl.append(rec)
    out['sleeves'] = sorted(sl, key=lambda q: q['id'])

    # ---------------- openings.json / floor-ground.json: G09 per the elevation, no pocket inside the opening ----------------
    g09 = next(q for q in OPN['openings'] if q['id'] == 'G09')
    ffl = g09['floorFinishRel']
    g09.update(sillRel=E['sill'], headRel=E['head'], UK_cm=round((E['sill'] - ffl) * 100), OK_cm=round((E['head'] - ffl) * 100), status='source',
               heightSource=f'{ELEV}: תגיות +{E["sill"]:.2f} / +{E["head"]:.2f} (tools/extract_mamad.py)')
    g09['source'] = g09['source'].split('; גובה:')[0] + '; גובה: ' + g09['heightSource']
    C = g09['castFrame']; C.update(bottomRel=E['sill'], topRel=E['head']); C.pop('pocketITM', None); C.pop('pocketWidth_m', None)
    C['note'] = ('משקוף פלדה של חלון הממ"ד – מוצב בתבנית ונוצק עם הקירות. הפתח בבטון (K-21) = המשקוף בתוכנית האדריכל (1.00 מ\', פתח נקי 0.90). '
                 'שתי כנפי הפלדה נגררות לגומחות בתוך הקירות משני צידי הפתח (data/architecture/mamad.json). '
                 'הקטע האפור 34 ס"מ ב-K-21 בתוך הפתח לא מופיע בתוכנית האדריכל – לא מוצג (open-issues #101).')
    for w in FG['walls']:
        for inf in w.get('infill') or []:
            if inf.get('opening') != 'G09': continue
            if inf['kind'] == 'sill': inf['topRel'] = E['sill']
            if inf['kind'] == 'lintel': inf['bottomRel'] = E['head']
    json.dump(OPN, open(os.path.join(ROOT, 'data/architecture/openings.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(FG, open(os.path.join(ROOT, 'data/structure/floor-ground.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(out, open(os.path.join(ROOT, 'data/architecture/mamad.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()

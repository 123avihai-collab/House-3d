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
    ground = ground_floor(msp, fr)
    chambers += ground['chambers']
    out = {'placement': {'martefToK11_cm': [r3(v) for v in t], 'inlierFraction': r3(sc), 'medianResidual_cm': r3(med),
                         'method': 'ICP על קווי הקירות (A-WALL/S-STRS של הבלוק martef מול IfcWall של k-11.dxf)',
                         'ground': ground['placement']},
           'chambers': chambers, 'pipes': ground['pipes'], 'pipeCrossings': crossings + ground['crossings'], 'checks': ground['checks'], 'source': SRC}
    os.makedirs(os.path.join(ROOT, 'data/systems'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'data/systems/plumbing-foundations.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(json.dumps(out['placement'], ensure_ascii=False)); print('checks', out['checks']); print('chambers', [(c['id'], c['IL']) for c in out['chambers']])
    for p in out['pipes']: print(p['id'], p['lengthM'], p.get('diameter_m'), p.get('slope'), p.get('ILfrom'), p.get('ILto'), p.get('between'), p['status'])
    print('crossings', [(c['pipe'], c['element']) for c in out['pipeCrossings']])


PDF_GROUND = 'sources/plumbing/אינסטלציה - קומת קרקע ופיתוח.pdf'
PIPE_COLOR, PIPE_WIDTH = (0.0, 1.0, 0.0), 0.72     # sewer centre lines in the ground-floor plumbing PDF (green, 0.72 pt)
MIG_MANHOLE = (179585.016, 576227.59)               # sewer manhole of the buyer's map (MIG DWG layer Sewagemanholes_500)
MIG_NIPPLE_IL = 278.20                              # IL of the lot's sewer stub (MIG DWG _HGM-block_nipel_500)


def ground_floor(msp, fr):
    """Ground-floor / development plumbing: chambers 0-5 (DXF: MH D1000 + G_LABELD) and sewer pipes (PDF centre lines).
    DXF block 'pituah' (cm) -> k-21.dxf by ICP translation -> ITM (stage-2 chain). The PDF is fitted to the 6 chambers
    (similarity, the chambers are the triple circles of the PDF)."""
    import pymupdf, itertools
    pit = next(e for e in msp.query('INSERT') if e.dxf.name == 'pituah')
    A = []
    for v in pit.virtual_entities():
        if v.dxftype() == 'LINE' and v.dxf.layer in ('A-WALL', 'S-STRS'):
            A += [(v.dxf.start.x, v.dxf.start.y), (v.dxf.end.x, v.dxf.end.y)]
    A = np.unique(np.round(np.array(A), 1), axis=0)
    m21 = F.read_dxf(F.K21); B = []
    for e in m21.query('LINE[layer=="IfcWall"]'): B += [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    B = np.unique(np.round(np.array(B), 1), axis=0)
    sc, t, med = F.icp(A, B, tries=100)
    t11 = F.basement['k11ToK400']['translation_pt']
    to_itm = lambda x, y: F.sheet2itm((x + t[0]) * F.S_CM + t11[0], -(y + t[1]) * F.S_CM + t11[1])
    x0, x1 = A[:, 0].min() - 800, A[:, 0].max() + 800; y0, y1 = A[:, 1].min() - 1200, A[:, 1].max() + 800
    labels = [l for l in msp.query('INSERT[name=="G_LABELD"]') if x0 < l.dxf.insert.x < x1 and y0 < l.dxf.insert.y < y1]
    mhs = [m for m in msp.query('INSERT[name=="MH D1000"]') if x0 < m.dxf.insert.x < x1 and y0 < m.dxf.insert.y < y1]
    def centre(m):
        circ = [c for c in m.virtual_entities() if c.dxftype() == 'CIRCLE']
        return max(circ, key=lambda c: c.dxf.radius).dxf.center if circ else m.dxf.insert
    # one label per chamber: global nearest assignment
    pairs = sorted(((math.dist((l.dxf.insert.x, l.dxf.insert.y), (centre(m).x, centre(m).y)), i, j) for i, l in enumerate(labels) for j, m in enumerate(mhs)))
    used_l, used_m, chambers = set(), set(), []
    for d, i, j in pairs:
        if i in used_l or j in used_m: continue
        used_l.add(i); used_m.add(j)
        at = {a.dxf.tag: a.dxf.text for a in labels[i].attribs}
        num = re.sub(r'\D', '', at.get('NUMBER', '')[:2]) or str(len(chambers))
        c = centre(mhs[j]); E, N = to_itm(c.x, c.y)
        chambers.append({'id': f'S-{num}', 'number': int(num), 'kind': 'sewerManhole', 'title': f'שוחת ביוב {num}',
                         'E': r3(E), 'N': r3(N), 'diameter_m': int(re.sub(r'\D', '', at.get('D', '')) or 0) / 100,
                         'TL': float(at['TL']), 'IL': float(at['IL']), 'H_m': float(at['H']), 'status': 'source', 'affectedBy': None,
                         'source': f'{SRC} – G_LABELD #{num} (TL={at["TL"]}, IL={at["IL"]}, H={at["H"]}, D={at["D"]}) + סמל MH D1000'})
    byn = {c['number']: c for c in chambers}
    checks = {'municipalManhole_vs_MIG_m': r3(math.dist((byn[0]['E'], byn[0]['N']), MIG_MANHOLE)) if 0 in byn else None,
              'connectionIL_vs_MIG_nipple_m': r3(byn[1]['IL'] - MIG_NIPPLE_IL) if 1 in byn else None}

    # ---- PDF: fit to the chambers (triple circles), then green centre lines ----
    page = pymupdf.open(os.path.join(ROOT, PDF_GROUND))[0]
    circles = {}
    for d in page.get_drawings():
        R = d['rect']
        if 9 < R.width < 12 and abs(R.width - R.height) < 0.6 and any(it[0] == 'c' for it in d['items']):
            circles[(round((R.x0 + R.x1) / 2, 1), round((R.y0 + R.y1) / 2, 1))] = 1
    P = list(circles)
    if len(P) < len(chambers): raise SystemExit('PDF chambers not found')
    b = np.array([complex(c['E'], c['N']) for c in chambers])
    best = None
    for perm in itertools.permutations(range(len(P)), len(chambers)):
        a = np.array([complex(P[k][0], -P[k][1]) for k in perm])
        ca, cb = a.mean(), b.mean(); s_ = (np.conj(a - ca) @ (b - cb)) / (np.conj(a - ca) @ (a - ca))
        res = np.abs((b - cb) - s_ * (a - ca)).max()
        if best is None or res < best[0]: best = (res, s_, ca, cb)
    res, s_, ca, cb = best
    T = lambda x, y: cb + s_ * (complex(x, -y) - ca)
    segs = []
    for d in page.get_drawings():
        col = tuple(round(v, 2) for v in (d.get('color') or ())); w = round(d.get('width') or 0, 2)
        if (col, w) != (PIPE_COLOR, PIPE_WIDTH): continue
        for it in d['items']:
            if it[0] == 'l':
                p1, p2 = T(it[1].x, it[1].y), T(it[2].x, it[2].y)
                if abs(p2 - p1) > 0.25: segs.append((p1, p2))
    # labels (diameter / slope) of the DXF, in ITM
    texts = []
    for e in msp.query('TEXT'):
        if e.dxf.layer == 'BIUV' and x0 < e.dxf.insert.x < x1 and y0 < e.dxf.insert.y < y1:
            E, N = to_itm(e.dxf.insert.x, e.dxf.insert.y); texts.append((complex(E, N), e.dxf.text.replace('ץ', '.')))
    def near_label(p1, p2, pat, maxd=1.6):
        L = LineString([(p1.real, p1.imag), (p2.real, p2.imag)])
        c = [(L.distance(Point(z.real, z.imag)), t) for z, t in texts if re.search(pat, t)]
        c = [x for x in c if x[0] <= maxd]
        return min(c)[1] if c else None
    ch_pt = {c['id']: complex(c['E'], c['N']) for c in chambers}
    at_ch = lambda z: next((k for k, q in ch_pt.items() if abs(z - q) < 0.35), None)
    pipes = []
    for i, (p1, p2) in enumerate(segs):
        c1, c2 = at_ch(p1), at_ch(p2)
        dia = near_label(p1, p2, r'%%C(110|160)')
        dmm = int(re.search(r'(110|160)', dia).group(1)) if dia else None
        slope_t = near_label(p1, p2, r'%%%')
        slope = float(re.search(r'([\d.]+)', slope_t).group(1)) / 100 if slope_t else None
        Lm = abs(p2 - p1)
        rec = {'id': f'P-{i + 1}', 'lengthM': r3(Lm), 'diameter_m': (dmm or 0) / 1000 or None,
               'material': ('PVC SN-8' if dmm == 160 else 'HDPE' if dmm == 110 else None),
               'source': f'{PDF_GROUND} (קו ירוק – קו מרכז הצינור), התאמה לשוחות: שארית {res:.3f} מ\'; קוטר/שיפוע: {SRC} טקסט BIUV'}
        if c1 and c2:   # main run between two chambers: flow to the lower IL; levels from the chambers (and the slope label)
            up, dn = (c1, c2) if byn[int(c1[2:])]['IL'] >= byn[int(c2[2:])]['IL'] else (c2, c1)
            ilu = byn[int(up[2:])]['IL']; ild = byn[int(dn[2:])]['IL']
            ild_pipe = ilu - slope * Lm if slope else ild
            drop = r3(ild_pipe - ild) if slope else 0.0
            a, bpt = (ch_pt[up], ch_pt[dn])
            rec.update(fromITM=[r3(a.real), r3(a.imag)], toITM=[r3(bpt.real), r3(bpt.imag)], ILfrom=r3(ilu), ILto=r3(ild_pipe),
                       slope=slope if slope else r3((ilu - ild) / Lm), dropAtEnd_m=drop if drop > 0.005 else 0.0,
                       levels='source' if slope else 'source (IL השוחות)', between=[up, dn], status='source')
        elif c1 or c2:  # branch from the house into a chamber: invert at the chamber = chamber IL, rising at the slope label
            ch = c1 or c2; far = p2 if c1 else p1
            il_end = byn[int(ch[2:])]['IL']
            sl = slope if slope else 0.02
            rec.update(fromITM=[r3(far.real), r3(far.imag)], toITM=[r3(ch_pt[ch].real), r3(ch_pt[ch].imag)], ILfrom=r3(il_end + sl * Lm), ILto=r3(il_end),
                       slope=sl, between=[None, ch], status='derived' if slope else 'provisional',
                       note=('מפלס בכניסה לשוחה = I.L של השוחה; עולה לפי השיפוע הכתוב.' if slope else
                             'שיפוע לא כתוב ליד הקטע – הונח 2% (השיפוע שכתוב לשאר הקווים בתוכנית). מפלס בכניסה לשוחה = I.L של השוחה.'))
        else:           # pipe piece inside the house – no level in the sources
            rec.update(fromITM=[r3(p1.real), r3(p1.imag)], toITM=[r3(p2.real), r3(p2.imag)], ILfrom=None, ILto=None, slope=slope,
                       status='missing', note='קטע צנרת בתוך הבית – מפלס לא כתוב במקורות. מוצג במפלס תחתית רצפת הקרקע (לסימון מיקום בלבד).')
        pipes.append(rec)
    # propagate levels upstream through connected pieces (house pipes): the downstream end of a piece = the upstream IL
    # of the pipe it joins; it rises at its slope label (or 2%, marked provisional)
    for _ in range(10):
        changed = False
        known = [q for q in pipes if q.get('ILfrom') is not None]
        for q in pipes:
            if q.get('ILfrom') is not None: continue
            a, b = complex(*q['fromITM']), complex(*q['toITM'])
            for k in known:
                up = complex(*k['fromITM'])
                for far, joint in ((a, b), (b, a)):
                    if abs(joint - up) < 0.2:
                        sl = q['slope'] if q.get('slope') else 0.02
                        q.update(fromITM=[r3(far.real), r3(far.imag)], toITM=[r3(joint.real), r3(joint.imag)], ILto=k['ILfrom'],
                                 ILfrom=r3(k['ILfrom'] + sl * q['lengthM']), slope=sl, between=[None, k['id']],
                                 status='derived' if q.get('slope') and q['status'] != 'missing' else 'provisional',
                                 note=f"מפלס נגזר מהצינור {k['id']} שאליו הוא מתחבר, בשיפוע {sl * 100:.1f}%" + ('' if q.get('slope') else ' (הונח – השיפוע הכתוב לשאר הקווים)'))
                        changed = True; break
                if q.get('ILfrom') is not None: break
        if not changed: break
    # pieces still without a level: drawn at the underside of the ground slab (nearest K-21 floor tag: O.K − D), location only
    tags21 = fr['floorTags']['k21']
    for q in pipes:
        if q.get('ILfrom') is None:
            m = complex(*q['fromITM']) * 0.5 + complex(*q['toITM']) * 0.5
            tg = min(tags21, key=lambda t: abs(complex(*t['itm']) - m))
            q['displayLevelRel'] = r3(tg['top'] - tg['D'])
    # crossings with basement walls / foundation beams (sleeves)
    walls = [Polygon(w['footprintITM'], w.get('holesITM') or []) for w in fr['basementWalls']]
    beams = []
    for bm in fr['groundBeams']:
        if not bm.get('axisITM'): continue
        (e1, n1), (e2, n2) = bm['axisITM']; Lb = math.dist((e1, n1), (e2, n2)); ux, uy = (e2 - e1) / Lb, (n2 - n1) / Lb; hw = bm['width_m'] / 2
        beams.append((bm['id'], Polygon([(e1 - uy * hw, n1 + ux * hw), (e2 - uy * hw, n2 + ux * hw), (e2 + uy * hw, n2 - ux * hw), (e1 + uy * hw, n1 - ux * hw)])))
    crossings = []
    for pp in pipes:
        Lp = LineString([pp['fromITM'], pp['toITM']])
        for k, Wp in enumerate(walls):
            x = Lp.intersection(Wp)
            if not x.is_empty and x.length > 0.05:
                crossings.append({'pipe': pp['id'], 'element': fr['basementWalls'][k]['id'], 'kind': 'basementWall', 'E': r3(x.centroid.x), 'N': r3(x.centroid.y), 'length_m': r3(x.length)})
        for bid, Bp in beams:
            x = Lp.intersection(Bp)
            if not x.is_empty and x.length > 0.05:
                crossings.append({'pipe': pp['id'], 'element': bid, 'kind': 'beam', 'E': r3(x.centroid.x), 'N': r3(x.centroid.y), 'length_m': r3(x.length),
                                  'note': 'מיקום הקורה בקירוב (PDF) – לבדיקה מול ה-IFC'})
    checks['pdfFitMaxResidual_m'] = r3(res)
    return {'placement': {'pituahToK21_cm': [r3(v) for v in t], 'inlierFraction': r3(sc), 'medianResidual_cm': r3(med),
                          'pdf': PDF_GROUND, 'pdfFit': 'דמיון לפי 6 השוחות', 'pdfMaxResidual_m': r3(res)},
            'chambers': chambers, 'pipes': pipes, 'crossings': crossings, 'checks': checks}


if __name__ == '__main__':
    import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()

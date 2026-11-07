#!/usr/bin/env python3
"""Plumbing layer – network extraction from the plumbing consultant's drawings (as drawn; nothing invented).

Sources (sources/plumbing/): plan DXF (symbols, labels, chambers, water lines, architect fixtures/downpipes),
4 PDF sheets (31.10.2026 – sewer centre lines, green), details DXF (sewer profile 0-1-4-5).
Placement: tools/plumbing/georef.py (same ITM chain as the main model).

Output: data/plumbing/network.json
  nodes    – chambers, stacks, fittings/symbols, fixtures, risers, meter, taps, downpipes, roof drains …
  runs     – pipe runs (polyline in ITM), each with from/to node ids, system, diameter, material, levels, slope, status
  findings – engineering findings (clashes, missing levels, dangling ends …) – filled by tools/plumbing/check.py
Every record carries `source` and `status`: source | derived | provisional | missing.
"""
import json, math, os, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import georef as G

ROOT = G.ROOT
r3 = G.r3
KB = dict(zip("qwertyuiopasdfghjkl;zxcvbnm,./'", "/'קראטוןםפשדגכעיחלךףזסבהנמצתץ.,"))
heb = lambda s: ''.join(KB.get(c, c) for c in s)
SYM = {'uky': ('inspectionBox', 'ק.ב – קופסת ביקורת'), 'yuk': ('dropInspectionBox', 'ק.ב.נ – קופסת ביקורת נופלת'),
       '3wre': ('floorDrain', 'מ.ר – מחסום רצפה'), 'uyk': ('drumTrap', 'מ.ת – מחסום תופי'),
       'TEE -45°': ('wye45', 'הסתעפות 45°')}
FIX = [('toilet_wall_hung', 'wc', 'אסלה תלויה'), ('כיור עגול', 'basin', 'כיור רחצה עגול 44×35'), ('כיור מלבני', 'sink', 'כיור מטבח 65×50'),
       ('מקלחון', 'shower', 'מקלחון'), ('צינור 4_ - צמ_ג', 'downpipe', 'צינור מי גשם (צמ"ג) 4"'),
       ('חיבור תחתון למרזב', 'downpipeShoe', 'חיבור תחתון למרזב'), ('נקז גג', 'roofDrain', 'נקז גג 2"'),
       ('brandslanghaspel', 'hoseReel', 'גלגלון כיבוי אש 3/4"')]


def P(x): return [r3(x[0]), r3(x[1])]


# ------------------------------------------------------------------ chambers
def chambers(msp, to_itm):
    out = []
    labels = [e for e in msp.query('INSERT[name=="G_LABELD"]')]
    mhs = [e for e in msp.query('INSERT[name=="MH D1000"]') if G.floor_of(e.dxf.insert.x, e.dxf.insert.y)]
    def centre(m):
        c = [v for v in m.virtual_entities() if v.dxftype() == 'CIRCLE']
        return max(c, key=lambda v: v.dxf.radius).dxf.center if c else m.dxf.insert
    pairs = sorted((math.dist((l.dxf.insert.x, l.dxf.insert.y), (centre(m).x, centre(m).y)), i, j) for i, l in enumerate(labels) for j, m in enumerate(mhs))
    ul, um = set(), set()
    for d, i, j in pairs:
        if i in ul or j in um: continue
        ul.add(i); um.add(j)
        at = {a.dxf.tag: a.dxf.text for a in labels[i].attribs}
        c = centre(mhs[j]); fl = G.floor_of(c.x, c.y); E, N = to_itm(fl)(c.x, c.y)
        num = re.sub(r'\D', '', at.get('NUMBER', '')[:2])
        D = int(re.sub(r'\D', '', at['D'])) / 100
        cid = f'S-{num}' if num else 'PC-1'
        out.append({'id': cid, 'kind': 'pumpChamber' if not num else ('municipalManhole' if num == '0' else 'sewerChamber'),
                    'title': 'תא שאיבה לניקוז חצרות אנגליים' if not num else ('שוחה עירונית עם הכנת התחברות' if num == '0' else f'שוחת ביוב (תא בקרה) {num}'),
                    'floor': 'unit' if fl == 'unit' else 'site', 'E': r3(E), 'N': r3(N), 'D_m': D, 'TL': float(at['TL']), 'IL': float(at['IL']), 'H_m': float(at['H']),
                    'status': 'source', 'source': f'{G.DXF} – G_LABELD {cid} (T.L={at["TL"]}, I.L={at["IL"]}, H={at["H"]}, D={at["D"].replace("%%C", "ø")}) + סמל MH D1000'})
    return sorted(out, key=lambda c: c['id'])


def profile(details_msp):
    """Sewer profile 0-1-4-5 in the details DXF: per chamber column T.L, outlet I.L and (where written) inlet I.L."""
    T = [(e.dxf.insert.x, e.dxf.insert.y, e.dxf.text.strip()) for e in details_msp.query('TEXT[layer=="TXT"]')]
    num = {round(x): t for x, y, t in T if -25 < y < -10 and re.fullmatch(r'\d', t)}
    cols = {}
    for x, t in num.items():
        near = [(x2, y, s) for x2, y, s in T if abs(x2 - x) < 20 and -80 < y < -40 and re.fullmatch(r'\d{3}\.\d\d', s)]
        tl = [float(s) for x2, y, s in near if -55 < y < -40]
        il = sorted(((x2, float(s)) for x2, y, s in near if -80 < y < -65), key=lambda v: v[0])
        cols[f'S-{t}'] = {'TL': tl[0] if tl else None, 'IL': [v for _, v in il]}
    segs = []
    for e in details_msp.query('TEXT[layer=="TXT"]'):
        s = e.dxf.text.strip()
        if -150 < e.dxf.insert.y < -130 and '%%%' in s: segs.append((e.dxf.insert.x, 'slope', float(s.replace('%%%', '')) / 100))
        if -150 < e.dxf.insert.y < -130 and 'PVC' in s: segs.append((e.dxf.insert.x, 'pipe', s.replace('%%C', 'ø')))
        if -125 < e.dxf.insert.y < -110 and re.fullmatch(r'\d+\.\d\d', s): segs.append((e.dxf.insert.x, 'dist', float(s)))
    return {'chambers': cols, 'labels': sorted(segs), 'source': f'{G.DETAILS} – פרופיל ביוב (שכבות TXT / Profile Legend)'}


# ------------------------------------------------------------------ symbols, fixtures, labels
def symbols(msp, to_itm):
    out = []
    for e in msp.query('INSERT'):
        fl = G.floor_of(e.dxf.insert.x, e.dxf.insert.y)
        if not fl or e.dxf.name not in SYM: continue
        kind, title = SYM[e.dxf.name]
        E, N = to_itm(fl)(e.dxf.insert.x, e.dxf.insert.y)
        out.append({'kind': kind, 'title': title, 'floor': fl, 'E': r3(E), 'N': r3(N), 'rotation_deg': r3(e.dxf.rotation),
                    'source': f'{G.DXF} – סמל {e.dxf.name} (שכבה {e.dxf.layer})'})
    # WC pan connectors (dynamic MEP fitting blocks drawn at the toilet outlets)
    for e in msp.query('INSERT'):
        fl = G.floor_of(e.dxf.insert.x, e.dxf.insert.y)
        if fl and e.dxf.name.startswith('*U'):
            lay = {v.dxf.layer for v in e.virtual_entities()}
            if 'M-DR-FITTING' in lay or 'FITTINGS' in lay:
                E, N = to_itm(fl)(e.dxf.insert.x, e.dxf.insert.y)
                out.append({'kind': 'fitting', 'title': 'אביזר (בלוק FITTINGS)', 'floor': fl, 'E': r3(E), 'N': r3(N), 'rotation_deg': r3(e.dxf.rotation),
                            'source': f'{G.DXF} – בלוק {e.dxf.name} (שכבות {", ".join(sorted(lay))})'})
    return out


def fixtures(msp, to_itm):
    out = []
    for fl, blk in G.BLOCK.items():
        ins = next(e for e in msp.query('INSERT') if e.dxf.name == blk)
        for v in ins.virtual_entities():
            if v.dxf.layer != 'P-SANR-FIXT' or v.dxftype() != 'INSERT': continue
            k = next((f for f in FIX if f[0] in v.dxf.name), None)
            if not k: continue
            E, N = to_itm(fl)(v.dxf.insert.x, v.dxf.insert.y)
            out.append({'kind': k[1], 'title': k[2], 'floor': fl, 'E': r3(E), 'N': r3(N), 'rotation_deg': r3(v.dxf.rotation),
                        'block': v.dxf.name.split(' - ')[0][:60], 'source': f'{G.DXF} – רקע אדריכלי בבלוק {blk}, שכבה P-SANR-FIXT ({v.dxf.name[:50]})'})
    return out


def labels(msp, to_itm):
    """Pipe labels: BIUV (ø / material / slope), text (water ø), stacks (צ.א + number)."""
    out = []
    for e in msp.query('TEXT'):
        fl = G.floor_of(e.dxf.insert.x, e.dxf.insert.y)
        if not fl or e.dxf.layer not in ('BIUV', 'text', 'INS'): continue
        s = e.dxf.text.strip().replace('%%C', 'ø').replace('%%%', '%')
        E, N = to_itm(fl)(e.dxf.insert.x, e.dxf.insert.y)
        out.append({'floor': fl, 'layer': e.dxf.layer, 'text': s, 'E': r3(E), 'N': r3(N), 'height_m': r3(e.dxf.height / 100), 'rot': round(e.dxf.rotation) % 360})
    return out


def stacks(msp, to_itm):
    """Stacks צ.א 1–6: numbered MULTILEADER bubbles; the arrow tip sits on the stack circle (layer hot water, colour 6)."""
    circ = G.stack_circles_itm(msp, to_itm)
    out = defaultdict(dict)
    for e in msp.query('MULTILEADER'):
        ctx = e.context
        att = [a.text for a in getattr(e, 'block_attribs', []) or []]
        if not att or not re.fullmatch(r'\d', att[0].strip()): continue
        pts = [tuple(v)[:2] for L in ctx.leaders for ln in L.lines for v in ln.vertices]
        if not pts: continue
        fl = G.floor_of(*pts[0])
        if not fl: continue
        tip = to_itm(fl)(*pts[0])
        c = min(circ[fl], key=lambda q: math.dist(q, tip))
        out[int(att[0])][fl] = {'E': r3(c[0]), 'N': r3(c[1]), 'tipToCircle_m': r3(math.dist(c, tip))}
    return dict(sorted(out.items()))


def mleader_tip(msp, to_itm, note_xy, fl, maxd=600):
    """Arrow tip of the leader whose last vertex is nearest to a note (DXF cm)."""
    best = None
    for e in msp.query('MULTILEADER'):
        pts = []
        for L in e.context.leaders:
            pts += [tuple(v)[:2] for ln in L.lines for v in ln.vertices]
            if L.last_leader_point is not None: pts.append(tuple(L.last_leader_point)[:2])
        if len(pts) < 2 or G.floor_of(*pts[0]) != fl: continue
        d = math.dist(pts[-1], note_xy)
        if d < maxd and (best is None or d < best[0]): best = (d, pts[0])
    return to_itm(fl)(*best[1]) if best else None


def spot_levels(msp, to_itm):
    """Development spot levels of the architect background in the ground block (finished levels next to chambers)."""
    ins = next(e for e in msp.query('INSERT') if e.dxf.name == 'pituah'); out = []
    for v in ins.virtual_entities():
        if v.dxftype() in ('TEXT', 'MTEXT'):
            t = (v.plain_text() if v.dxftype() == 'MTEXT' else v.dxf.text).strip()
            m = re.fullmatch(r'\(?\s*(2[78]\d\.\d\d)\s*\)?', t)
            if m:
                E, N = to_itm('ground')(v.dxf.insert.x, v.dxf.insert.y)
                out.append({'H': float(m.group(1)), 'E': r3(E), 'N': r3(N), 'layer': v.dxf.layer})
    return out


def mtext_anchor(msp, to_itm, needle, fl):
    for e in msp.query('MTEXT'):
        if needle in e.plain_text() and G.floor_of(e.dxf.insert.x, e.dxf.insert.y) == fl:
            return (e.dxf.insert.x, e.dxf.insert.y)


def pc1_centre(page, T):
    """Centre of the pump chamber PC-1 = the ø60 circle (13.6 pt) of the triple-circle symbol in the basement PDF."""
    for d in page.get_drawings():
        R_ = d['rect']
        if tuple(round(v, 2) for v in (d.get('color') or ())) == (0.33, 0.33, 0.33) and any(it[0] == 'c' for it in d['items']) and 13 < R_.width < 14.2:
            return T((R_.x0 + R_.x1) / 2, (R_.y0 + R_.y1) / 2)


# ------------------------------------------------------------------ geometry from the PDFs / DXF
def pdf_green(page, T):
    segs = []
    for d in page.get_drawings():
        if tuple(round(v, 2) for v in (d.get('color') or ())) != (0.0, 1.0, 0.0): continue
        for it in d['items']:
            if it[0] == 'l':
                a, b = T(it[1].x, it[1].y), T(it[2].x, it[2].y)
                if math.dist(a, b) > 0.02: segs.append((a, b))
    return segs


def pdf_blue_drains(page):
    """Floor drains ø8/4" of the English courtyards = blue circles 4.9 pt in the basement PDF."""
    out = {}
    for d in page.get_drawings():
        R_ = d['rect']
        if tuple(round(v, 2) for v in (d.get('color') or ())) == (0.0, 0.0, 1.0) and any(it[0] == 'c' for it in d['items']) and 4.6 < R_.width < 5.2:
            out[(round((R_.x0 + R_.x1) / 2, 2), round((R_.y0 + R_.y1) / 2, 2))] = 1
    return list(out)


def chain(segs, tol=0.02):
    """Join segments that share end points into polylines."""
    segs = [list(s) for s in segs]; lines = []
    while segs:
        cur = segs.pop(0)
        grown = True
        while grown:
            grown = False
            for i, s in enumerate(segs):
                if math.dist(cur[-1], s[0]) < tol: cur.append(s[1])
                elif math.dist(cur[-1], s[1]) < tol: cur.append(s[0])
                elif math.dist(cur[0], s[1]) < tol: cur.insert(0, s[0])
                elif math.dist(cur[0], s[0]) < tol: cur.insert(0, s[1])
                else: continue
                segs.pop(i); grown = True; break
        lines.append(cur)
    return lines


def water_lines(msp, to_itm):
    out = []
    for e in msp.query('LWPOLYLINE'):
        if e.dxf.layer not in ('cold water', 'hot water'): continue
        p0 = e.get_points('xy')[0]; fl = G.floor_of(p0[0], p0[1])
        if not fl: continue
        pts = [to_itm(fl)(x, y) for x, y in e.get_points('xy')]
        col = e.dxf.color if e.dxf.color != 256 else 150
        out.append({'floor': fl, 'pts': pts, 'hot': col == 1 or e.dxf.layer == 'hot water', 'layer': e.dxf.layer, 'color': col})
    return out


def risers(msp, to_itm):
    out = []
    for c in msp.query('CIRCLE[layer=="hot water"]'):
        fl = G.floor_of(c.dxf.center.x, c.dxf.center.y)
        if fl and c.dxf.color == 5:
            out.append({'floor': fl, 'E': r3(to_itm(fl)(c.dxf.center.x, c.dxf.center.y)[0]), 'N': r3(to_itm(fl)(c.dxf.center.x, c.dxf.center.y)[1]), 'r_m': r3(c.dxf.radius / 100)})
    return out


def taps(msp, to_itm):
    out = []
    for e in msp.query('INSERT[name=="ברז גן"]'):
        fl = G.floor_of(e.dxf.insert.x, e.dxf.insert.y)
        if fl: out.append({'floor': fl, 'E': r3(to_itm(fl)(e.dxf.insert.x, e.dxf.insert.y)[0]), 'N': r3(to_itm(fl)(e.dxf.insert.x, e.dxf.insert.y)[1]), 'src': 'INSERT ברז גן'})
    for e in msp.query('TEXT[layer=="text"]'):
        fl = G.floor_of(e.dxf.insert.x, e.dxf.insert.y)
        if fl and heb(e.dxf.text).startswith('ברז גן'):
            out.append({'floor': fl, 'E': r3(to_itm(fl)(e.dxf.insert.x, e.dxf.insert.y)[0]), 'N': r3(to_itm(fl)(e.dxf.insert.x, e.dxf.insert.y)[1]), 'src': 'TEXT ברז גן 3/4"'})
    return out


def splines(msp, to_itm):
    out = []
    for e in msp.query('SPLINE'):
        pts = [(p.x, p.y) for p in e.flattening(2)]
        fl = G.floor_of(*pts[0])
        if fl: out.append({'floor': fl, 'pts': [to_itm(fl)(x, y) for x, y in pts], 'linetype': e.dxf.get('linetype')})
    return out


if __name__ == '__main__' and not os.environ.get('PLUMB_NET'):
    g = G.load(); msp = g['msp']; to = g['to_itm']
    import ezdxf
    det = ezdxf.readfile(os.path.join(ROOT, G.DETAILS)).modelspace()
    raw = {'placement': g['placement'], 'pdfFit': g['pdfFit'], 'chambers': chambers(msp, to), 'profile': profile(det),
           'symbols': symbols(msp, to), 'fixtures': fixtures(msp, to), 'labels': labels(msp, to), 'stacks': stacks(msp, to),
           'water': water_lines(msp, to), 'risers': risers(msp, to), 'taps': taps(msp, to), 'splines': splines(msp, to),
           'green': {fl: [[P(a), P(b)] for a, b in pdf_green(pg, T)] for fl, (pg, T) in g['pages'].items()},
           'pc1Centre': P(pc1_centre(*g['pages']['unit'])), 'spots': spot_levels(msp, to),
           'unitDrains': [P(T(x, y)) for x, y in pdf_blue_drains(g['pages']['unit'][0]) for T in [g['pages']['unit'][1]]],
           'poolFill': P(mleader_tip(msp, to, mtext_anchor(msp, to, 'ברז מילוי בריכת', 'ground'), 'ground')),
           'washerLabel': P(to('ground')(26187, -1161)),
           'meter': P(mleader_tip(msp, to, (24931 + 300, -1599), 'ground')), 'hoseReel': P(mleader_tip(msp, to, (25076 + 300, -1465), 'ground'))}
    os.makedirs(os.path.join(ROOT, 'tools/plumbing/cache'), exist_ok=True)
    json.dump(raw, open(os.path.join(ROOT, 'tools/plumbing/cache/raw.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in raw.items()})
    print('profile', json.dumps(raw['profile']['chambers'], ensure_ascii=False), raw['profile']['labels'])
    print('stacks', json.dumps(raw['stacks']))
    print('meter', raw['meter'], 'hoseReel', raw['hoseReel'])


# ================================================================== network (topology + levels)
CAPTURE = {'chamber': 0.15, 'stack': 0.13, 'inspectionBox': 0.22, 'dropInspectionBox': 0.22, 'floorDrain': 0.22, 'drumTrap': 0.22,
           'wye45': 0.18, 'fitting': 0.0, 'wc': 0.42, 'basin': 0.45, 'sink': 0.42, 'shower': 0.55}
PREFIX = {'inspectionBox': 'IB', 'dropInspectionBox': 'DIB', 'floorDrain': 'FD', 'drumTrap': 'DT', 'wye45': 'WY', 'wc': 'WC', 'basin': 'BS',
          'sink': 'SK', 'shower': 'SH', 'downpipe': 'DP', 'downpipeShoe': 'DPS', 'roofDrain': 'RD'}


def build_nodes(R):
    nodes = []
    for c in R['chambers']:
        E, N = c['E'], c['N']
        if c['id'] == 'PC-1': E, N = R['pc1Centre']   # centre of the ø60 circle (the MH insert point is not the centre)
        nodes.append({**c, 'E': r3(E), 'N': r3(N), 'cls': 'chamber', 'capture': c['D_m'] / 2 + CAPTURE['chamber']})
    for n, fls in R['stacks'].items():
        for fl, p in fls.items():
            nodes.append({'id': f'ST{n}@{fl}', 'kind': 'stack', 'cls': 'stack', 'stack': int(n), 'floor': fl, 'E': p['E'], 'N': p['N'], 'capture': CAPTURE['stack'],
                          'title': f'קולטן צ.א {n} (HDPE ø110)', 'status': 'source', 'source': f'{G.DXF} – עיגול מגנטה (שכבה hot water) + תווית צ.א {n}'})
    cnt = defaultdict(int)
    for s in R['symbols']:
        if s['kind'] == 'fitting': continue
        cnt[(s['floor'], s['kind'])] += 1
        nodes.append({**s, 'id': f"{PREFIX[s['kind']]}{cnt[(s['floor'], s['kind'])]}@{s['floor']}", 'cls': 'symbol', 'capture': CAPTURE[s['kind']], 'status': 'source'})
    for f in R['fixtures']:
        if f['kind'] in ('hoseReel',): continue
        cnt[(f['floor'], f['kind'])] += 1
        nodes.append({**f, 'id': f"{PREFIX[f['kind']]}{cnt[(f['floor'], f['kind'])]}@{f['floor']}", 'cls': 'fixture', 'capture': CAPTURE.get(f['kind'], 0.3), 'status': 'source'})
    return nodes


def split_at_nodes(segs, nodes, fl):
    """Chain PDF segments into runs, never joining through a node (chamber, stack, symbol)."""
    hard = [n for n in nodes if n['floor'] in (fl, 'site') and n['cls'] in ('chamber', 'stack', 'symbol')]
    inside = lambda p: any(math.dist(p, (n['E'], n['N'])) < n['capture'] for n in hard)
    segs = [list(map(tuple, s)) for s in segs]
    runs = []
    while segs:
        cur = segs.pop(0); grown = True
        while grown:
            grown = False
            for i, s in enumerate(segs):
                for end in (0, -1):
                    q = cur[end]
                    if inside(q): continue
                    for k in (0, 1):
                        if math.dist(q, s[k]) < 0.02:
                            other = s[1 - k]
                            if end == -1: cur.append(other)
                            else: cur.insert(0, other)
                            segs.pop(i); grown = True; break
                    if grown: break
                if grown: break
        runs.append(cur)
    return runs


def snap(p, nodes, fl, exclude=()):
    best = None
    for n in nodes:
        if n['floor'] not in (fl, 'site') or n['id'] in exclude: continue
        if fl != 'ground' and n['floor'] == 'site': continue
        d = math.dist(p, (n['E'], n['N'])) - n['capture']
        if d <= 0 and (best is None or d < best[0]): best = (d, n)
    return best[1] if best else None


def build_network(R):
    nodes = build_nodes(R)
    byid = {n['id']: n for n in nodes}
    runs, nid = [], defaultdict(int)
    for fl, segs in R['green'].items():
        for pts in split_at_nodes(segs, nodes, fl):
            L = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
            if L < 0.04: continue
            nid[fl] += 1
            runs.append({'id': f'SW{nid[fl]}@{fl}', 'floor': fl, 'system': 'sewage', 'pts': [P(p) for p in pts], 'length_m': r3(L)})
    # ends -> nodes; leftover ends: bridge to another free end (<0.45 m, gap behind a symbol drawing) or T-junction (<0.15)
    free = []
    for r in runs:
        r['ends'] = [None, None]
        for k, p in ((0, r['pts'][0]), (1, r['pts'][-1])):
            n = snap(p, nodes, r['floor'])
            if n: r['ends'][k] = n['id']
            else: free.append((r, k))
    jn = 0
    used = set()
    for i, (r, k) in enumerate(free):
        if (r['id'], k) in used: continue
        p = r['pts'][0 if k == 0 else -1]
        cand = [(math.dist(p, (q['pts'][0 if kk == 0 else -1])), q, kk) for q, kk in free if q is not r and q['floor'] == r['floor'] and (q['id'], kk) not in used]
        cand = [c for c in cand if c[0] < 0.45]
        if cand:
            d, q, kk = min(cand, key=lambda c: c[0])
            pq = q['pts'][0 if kk == 0 else -1]
            jn += 1; j = {'id': f'J{jn}@{r["floor"]}', 'kind': 'junction', 'cls': 'junction', 'floor': r['floor'], 'E': r3((p[0] + pq[0]) / 2), 'N': r3((p[1] + pq[1]) / 2),
                          'title': 'חיבור (רווח בקו המשורטט)', 'gap_m': r3(d), 'status': 'derived', 'source': 'גישור רווח בין קצוות קו ירוק ב-PDF (מתחת לסמל)'}
            nodes.append(j); byid[j['id']] = j; r['ends'][k] = j['id']; q['ends'][kk] = j['id']; used |= {(r['id'], k), (q['id'], kk)}
            continue
    for r in runs:
        for k in (0, 1):
            if r['ends'][k]: continue
            p = r['pts'][0 if k == 0 else -1]
            best = None
            for q in runs:
                if q is r or q['floor'] != r['floor']: continue
                for a, b in zip(q['pts'][:-1], q['pts'][1:]):
                    ax, ay, bx, by = *a, *b; L2 = (bx - ax) ** 2 + (by - ay) ** 2
                    t = max(0, min(1, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L2)) if L2 else 0
                    c = (ax + t * (bx - ax), ay + t * (by - ay)); d = math.dist(p, c)
                    if d < 0.15 and 0.02 < t < 0.98 and (best is None or d < best[0]): best = (d, q, c)
            if best:
                jn += 1; j = {'id': f'J{jn}@{r["floor"]}', 'kind': 'tee', 'cls': 'junction', 'floor': r['floor'], 'E': r3(best[2][0]), 'N': r3(best[2][1]),
                              'title': 'הסתעפות (קצה קו על קו אחר)', 'status': 'derived', 'source': 'קצה קו ירוק ב-PDF על קו אחר', 'onRun': best[1]['id']}
                nodes.append(j); byid[j['id']] = j; r['ends'][k] = j['id']
            else:
                jn += 1; j = {'id': f'END{jn}@{r["floor"]}', 'kind': 'openEnd', 'cls': 'openEnd', 'floor': r['floor'], 'E': r3(p[0]), 'N': r3(p[1]), 'dangling': True,
                              'title': 'קצה קו בלי חיבור מוגדר', 'status': 'missing', 'source': 'קו ירוק ב-PDF שנגמר בלי סמל/שוחה/קבועה'}
                nodes.append(j); byid[j['id']] = j; r['ends'][k] = j['id']
    return nodes, runs


if __name__ == '__main__' and os.environ.get('PLUMB_NET'):
    R = json.load(open(os.path.join(ROOT, 'tools/plumbing/cache/raw.json'), encoding='utf-8'))
    nodes, runs = build_network(R)
    json.dump({'nodes': nodes, 'runs': runs}, open(os.path.join(ROOT, 'tools/plumbing/cache/net.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for r in runs: print(r['id'], r['length_m'], r['ends'])
    print('open ends', [n['id'] for n in nodes if n.get('dangling')])

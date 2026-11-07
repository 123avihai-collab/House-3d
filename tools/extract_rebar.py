#!/usr/bin/env python3
"""Rebar sheets of the structural engineer -> data/structure/rebar.json

Sources (sources/structure/, 1:50, the same drawings as the geometry sheets + reinforcement):
  K-12 / K-22 / K-32 / K-42  "פריסת ברזל קורות"  beams (grey outlines + tags), bars with callouts "3 Ø12 L=700 -ב.ע",
                              1:25 sections of every beam / wall / column (stirrups, side bars, levels)
  K-13 / K-23 / K-33 / K-43  "פריסת ברזל"        slab meshes (bottom / top plan) + extra bars, standard details

Placement: each rebar sheet is aligned to its geometry sheet (K-11 / K-21 / K-31 / K-41) by a pure translation (ICP of
line end points; the residual proves the same 1:50 scale), then by the geometry sheet's own placement on the K-400 sheet
(data/structure/framing.json / floor-*.json) to ITM.

Output:
  beams[]   – per tagged beam: band on the rebar plan -> axis in ITM (used by extract_framing.py for the K-11 / K-21 beams,
              whose axes otherwise come from the K-400 stipple only), bars (count, Ø, length, top/bottom) and section texts
  sections[] – wall / column / typical-beam sections (texts as drawn)
  plan[]    – column / wall bar callouts on the plans ("14Ø12", "2#Ø8 @15\\15") with their ITM point
  slabs[]   – slab meshes and extra bars per floor (K-x3) with their ITM point
  links     – (second run, after the model is rebuilt) element ids each callout belongs to
Run: python3 tools/extract_rebar.py   (before extract_framing.py, and again at the end of the pipeline to refresh links)
"""
import json, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pymupdf
from shapely.geometry import Polygon, Point, LineString
import extract_framing as F

ROOT = F.ROOT
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
r3 = lambda v: round(float(v), 3)
S_CM = F.S_CM
SD = 'sources/structure/'
SHEETS = {
    'K-12': {'pdf': SD + 'K-12-קומת מרתף - פריסת ברזל קורות.pdf', 'geom': 'K-11', 'mesh': SD + 'K-13-קומת מרתף - פריסת ברזל.pdf', 'floor': 'unit'},
    'K-22': {'pdf': SD + 'K-22-קומה קרקע - פריסת ברזל קורות.pdf', 'geom': 'K-21', 'mesh': SD + 'K-23-קומה קרקע - פריסת ברזל.pdf', 'floor': 'ground'},
    'K-32': {'pdf': SD + 'K-32-קומה א - פריסת ברזל קורות.pdf', 'geom': 'K-31', 'mesh': SD + 'K-33-קומה א - פריסת ברזל.pdf', 'floor': 'groundCeiling'},
    'K-42': {'pdf': SD + 'K-42-קומה גג - פריסת ברזל קורות.pdf', 'geom': 'K-41', 'mesh': SD + 'K-43-קומה גג - פריסת ברזל.pdf', 'floor': 'roof'},
}
GEOM_PDF = {'K-11': F.K11P, 'K-21': F.K21P, 'K-31': SD + "K-31-תוכנית קומה א' - גיאומטריה.pdf", 'K-41': SD + 'K-41-תוכנית קומה גג - גיאומטריה.pdf'}
GREY = {0.67, 0.79}
BAR_RE = re.compile(r'^(\d+)\s*ï\s*(\d+)\s*(?:@\s*(\d+)\s*)?L=(\d+)\s*-?\s*(ב\.ע|ב\.ת)?')
COLBAR_RE = re.compile(r'^(\d+)\s*ï\s*(\d+)$')
MESH_RE = re.compile(r'(\d*)\s*#\s*ï\s*(\d+)\s*@\s*(\d+)\s*[\\/]\s*(\d+)')


def geom_translation(geom):
    FR, FG, FF = J('data/structure/framing.json'), J('data/structure/floor-ground.json'), J('data/structure/floor-first.json')
    return {'K-11': FR['placement']['K11pdf']['translation_pt'], 'K-21': FR['placement']['K21pdf']['translation_pt'],
            'K-31': FG['placement']['K31pdf']['translation_pt'], 'K-41': FF['ceiling']['placement']['K41pdf']['translation_pt']}[geom]


def text_lines(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            t = ''.join(s['text'] for s in l['spans']).strip()
            if t: out.append({'t': t, 'bb': list(l['bbox']), 'dir': l['dir'], 'col': l['spans'][0]['color'],
                              'c': ((l['bbox'][0] + l['bbox'][2]) / 2, (l['bbox'][1] + l['bbox'][3]) / 2)})
    return out


def grey_lines(page):
    H, V = [], []
    for d in page.get_drawings():
        col = d.get('color')
        if not col or round(col[0], 2) not in GREY or abs(col[0] - col[1]) > 0.01: continue
        for it in d['items']:
            if it[0] != 'l': continue
            a, b = it[1], it[2]
            if abs(a.y - b.y) < 0.2 and abs(a.x - b.x) > 0.5: H.append((round((a.y + b.y) / 2, 1), min(a.x, b.x), max(a.x, b.x)))
            elif abs(a.x - b.x) < 0.2 and abs(a.y - b.y) > 0.5: V.append((round((a.x + b.x) / 2, 1), min(a.y, b.y), max(a.y, b.y)))
    return runs(H), runs(V)


def bar_lines(page):
    """thick black lines = bars (1.42 pt)"""
    H, V = [], []
    for d in page.get_drawings():
        col = d.get('color')
        if not col or max(col) > 0.05 or (d.get('width') or 0) < 1.3: continue
        for it in d['items']:
            if it[0] != 'l': continue
            a, b = it[1], it[2]
            if abs(a.y - b.y) < 0.3 and abs(a.x - b.x) > 10: H.append(((a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
            elif abs(a.x - b.x) < 0.3 and abs(a.y - b.y) > 10: V.append(((a.x + b.x) / 2, min(a.y, b.y), max(a.y, b.y)))
    # a bar drawn in pieces (broken at a crossing) is one bar
    rnd = lambda S: [(round(c * 2) / 2, a, b) for c, a, b in S]
    return runs(rnd(H), 4.0), runs(rnd(V), 4.0)


def runs(S, gap=5.0):
    g = {}
    for c, a, b in S: g.setdefault(c, []).append((a, b))
    out = []
    for c, iv in g.items():
        iv.sort(); cur = list(iv[0])
        for a, b in iv[1:]:
            if a <= cur[1] + gap: cur[1] = max(cur[1], b)
            else: out.append((c, cur[0], cur[1])); cur = [a, b]
        out.append((c, cur[0], cur[1]))
    return out


def beam_tags(L):
    secs = [x for x in L if re.match(r'^\d+/\d+; O\.K=[+-]\d\.\d+', x['t']) and x['col'] == 0xaaaaaa]
    out = []
    for x in L:
        if not re.match(r'^B-\d+$', x['t']) or x['col'] != 0xaaaaaa: continue
        sec = min(secs, key=lambda s: math.dist(s['c'], x['c'])) if secs else None
        if sec and math.dist(sec['c'], x['c']) > 30: sec = None
        m = re.match(r'^(\d+)/(\d+); O\.K=([+-]\d\.\d+)', sec['t']) if sec else None
        cs = [x['c']] + ([sec['c']] if sec else [])
        out.append({'id': x['t'], 'w': int(m[1]) if m else None, 'h': int(m[2]) if m else None, 'top': float(m[3]) if m else None,
                    'c': (sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs)), 'axis': 'h' if abs(x['dir'][0]) > 0.5 else 'v'})
    return out


def band(tag, H, V):
    """the pair of grey edge runs, b apart, nearest to the tag; extent = overlap of the two runs"""
    if not tag['w']: return None
    wpt = tag['w'] * S_CM
    R = H if tag['axis'] == 'h' else V
    lat, along = (tag['c'][1], tag['c'][0]) if tag['axis'] == 'h' else (tag['c'][0], tag['c'][1])
    cand = [r for r in R if abs(r[0] - lat) < 40 and r[1] - 5 <= along <= r[2] + 5 and r[2] - r[1] > wpt]
    best = None
    for a in cand:
        for b in cand:
            if b[0] <= a[0] or abs(b[0] - a[0] - wpt) > 0.8: continue
            lo, hi = max(a[1], b[1]), min(a[2], b[2])
            if hi - lo < wpt: continue
            sc = abs((a[0] + b[0]) / 2 - lat)
            if best is None or sc < best[0]: best = (sc, (a[0] + b[0]) / 2, lo, hi)
    return {'lat': best[1], 'along': [best[2], best[3]]} if best else None


def section_cells(L, plan_box):
    """section titles (B-xx / Wx / עמוד בחתך / חתך טיפוסי) with a scale line under them, and the texts drawn above each"""
    # titles drawn on two lines ("חתך טיפוסי" over "30/60"): join them
    for x in L:
        if x['t'].replace(' ', '') in ('חתךטיפוסי', 'עמודבחתך'):
            nb = [y for y in L if y is not x and re.match(r'^\d+/\d+\.?$', y['t']) and abs(y['c'][0] - x['c'][0]) < 40 and 0 < y['c'][1] - x['c'][1] < 18]
            if nb:
                y = nb[0]; x['t'] = x['t'] + y['t'].rstrip('.'); x['c'] = y['c']; y['t'] = ''
    def inside(c): return plan_box[0] <= c[0] <= plan_box[2] and plan_box[1] <= c[1] <= plan_box[3]
    scale = [x for x in L if re.match(r'^1\s*:\s*(25|10|20)$', x['t'])]
    titles = []
    for x in L:
        if inside(x['c']) or x['col'] == 0xaaaaaa: continue
        t = x['t'].replace(' ', '')
        if not re.match(r'^(B-\d+|W\d+|עמודבחתך\d+/\d+|חתךטיפוסי\d+/\d+)$', t): continue
        if not any(abs(s['c'][0] - x['c'][0]) < 40 and 0 < s['c'][1] - x['c'][1] < 30 for s in scale): continue
        titles.append(dict(x, key=t))
    cells = {i: [] for i in range(len(titles))}
    skip = {id(s) for s in scale} | {id(x) for x in titles}
    for x in L:
        if id(x) in skip or inside(x['c']): continue
        cand = [(i, T) for i, T in enumerate(titles) if 0 < T['c'][1] - x['c'][1] < 240 and abs(T['c'][0] - x['c'][0]) < 130]
        if not cand: continue
        i, T = min(cand, key=lambda iT: abs(iT[1]['c'][0] - x['c'][0]) * 1.5 + (iT[1]['c'][1] - x['c'][1]) * 0.5)
        cells[i].append(x)
    out = []
    for i, T in enumerate(titles):
        tx = sorted(cells[i], key=lambda x: (round(x['c'][1] / 6), x['c'][0]))
        out.append({'title': T['key'], 'pt': [round(T['c'][0]), round(T['c'][1])], 'texts': [x['t'] for x in tx]})
    return out


def parse_section(texts):
    """stirrups / side bars / levels from the texts of a beam section"""
    s = {'stirrups': [], 'bars': [], 'levels': [], 'dims': []}
    for t in texts:
        tt = t.replace(' ', '')
        if re.match(r'^\d*ï\d+@\d+$', tt): s['stirrups'].append(t)
        elif re.match(r'^\d+(x\d+)?ï\d+', tt): s['bars'].append(t)
        elif re.match(r'^[+-]\d\.\d\d$', tt): s['levels'].append(tt)
        elif re.match(r'^L=\d+$', tt): s['stirrups'].append(t)
        elif re.match(r'^\d{2,3}$', tt): s['dims'].append(int(tt))
    return s


def main(link_only=False):
    OV = J('tools/rebar-beams.json')['beams']
    FG, RF = J('data/structure/floor-ground.json'), J('data/structure/floor-roof.json')
    model_beams = {'K-32': FG['ceiling']['beams'], 'K-42': RF['ceiling']['beams']}
    out = {'_doc': 'Generated by tools/extract_rebar.py from the rebar sheets K-12/13, K-22/23, K-32/33, K-42/43 – do not edit by hand.',
           'placement': {}, 'beams': [], 'sections': [], 'plan': [], 'slabs': [], 'notes': {}}
    for sh, S in SHEETS.items():
        page = pymupdf.open(os.path.join(ROOT, S['pdf']))[0]
        gp = pymupdf.open(os.path.join(ROOT, GEOM_PDF[S['geom']]))[0]
        A = F.pdf_endpoints(S['pdf'], (0, 0, page.rect.width * 0.85, page.rect.height * 0.75))
        B = F.pdf_endpoints(GEOM_PDF[S['geom']], (0, 0, gp.rect.width, gp.rect.height))
        sc, t, med = F.icp(A, B, tries=80)
        tg = geom_translation(S['geom'])
        out['placement'][sh] = {'toGeometrySheet': S['geom'], 'translation_pt': [r3(v) for v in t], 'inlierFraction': r3(sc), 'medianResidual_pt': r3(med),
                                'geometrySheetTranslation_pt': tg}
        to_itm = lambda x, y, t=t, tg=tg: F.sheet2itm(x + t[0] + tg[0], y + t[1] + tg[1])

        def from_itm(E, N, t=t, tg=tg):
            G = F.G; th = G['theta_rad']; dx, dy = E - G['tx'], N - G['ty']
            Xm = dx * math.cos(th) + dy * math.sin(th); Ym = -dx * math.sin(th) + dy * math.cos(th)
            return Xm * G['ptPerM'] - tg[0] - t[0], -Ym * G['ptPerM'] - tg[1] - t[1]

        L = text_lines(page)
        H, V = grey_lines(page)
        tags = beam_tags(L)
        plan_box = (min(x['c'][0] for x in tags) - 260, min(x['c'][1] for x in tags) - 260,
                    max(x['c'][0] for x in tags) + 260, max(x['c'][1] for x in tags) + 220)
        ov = OV.get(sh, {})
        bands = []
        for tag in tags:
            o = ov.get(tag['id'], {})
            rec = {'sheet': sh, 'geomSheet': S['geom'], 'id': tag['id'], 'width_m': tag['w'] / 100 if tag['w'] else None,
                   'depth_m': tag['h'] / 100 if tag['h'] else None, 'topRel': tag['top'], 'axis': tag['axis'], 'status': o.get('status', 'source')}
            if sh in model_beams:          # K-31 / K-41 beams: the model already has the outline from the geometry sheet
                ms = [m for m in model_beams[sh] if m['id'] == tag['id'] and m.get('axisITM')]
                if ms:
                    P, Q = [from_itm(*q) for q in ms[0]['axisITM']]
                    rec['pt'] = [[r3(v) for v in P], [r3(v) for v in Q]]; rec['geometry'] = 'model'
                if 'along_from_model_start' in o and ms:
                    rec['trimTo_m'] = o['along_from_model_start']; rec['note'] = o['note']
            else:
                bd = band(tag, H, V)
                if 'a' in o:
                    P, Q = o['a'], o['b']
                elif bd or 'along' in o:
                    lat = o.get('lat', bd['lat'] if bd else None); al = o.get('along', bd['along'] if bd else None)
                    P, Q = ((al[0], lat), (al[1], lat)) if tag['axis'] == 'h' else ((lat, al[0]), (lat, al[1]))
                else:
                    P = Q = None
                    fr = [b for b in J('data/structure/framing.json')['groundBeams'] if b['id'] == tag['id'] and b.get('axisITM') and b.get('sheet') == S['geom']]
                    if fr:                 # not drawn as a band on the rebar plan (dashed under a wall): keep the model axis for the bar links
                        rec['pt'] = [[r3(v) for v in from_itm(*q)] for q in fr[0]['axisITM']]; rec['geometry'] = 'model'
                if P:
                    rec['pt'] = [[r3(v) for v in P], [r3(v) for v in Q]]
                    rec['axisITM'] = [[r3(v) for v in to_itm(*P)], [r3(v) for v in to_itm(*Q)]]
                    rec['length_m'] = r3(math.dist(*rec['axisITM']))
                    rec['geometry'] = 'override' if o else 'band'
                    if o: rec['note'] = o['note']
                else:
                    rec['geometry'] = 'notFound'
            rec['tagPt'] = [round(tag['c'][0], 1), round(tag['c'][1], 1)]
            bands.append(rec)
        for bid, o in ov.items():                       # beams with no number (only a section tag)
            if not o.get('new'): continue
            P, Q = ((o['along'][0], o['lat']), (o['along'][1], o['lat'])) if o.get('axis', 'v') == 'h' else ((o['lat'], o['along'][0]), (o['lat'], o['along'][1]))
            ax = [[r3(v) for v in to_itm(*P)], [r3(v) for v in to_itm(*Q)]]
            bands.append({'sheet': sh, 'geomSheet': S['geom'], 'id': bid, 'label': o['label'], 'width_m': o['w'] / 100, 'depth_m': o['h'] / 100,
                          'topRel': o['top'], 'axis': o.get('axis', 'v'), 'status': o.get('status', 'approx'), 'pt': [list(P), list(Q)], 'axisITM': ax,
                          'length_m': r3(math.dist(*ax)), 'geometry': 'override', 'note': o['note'], 'numbered': False})
        # ---- bars: callout -> bar line -> beam band ----
        BH, BV = bar_lines(page)
        for rec in bands: rec['bars'] = []
        for x in L:
            m = BAR_RE.match(x['t'])
            if not m or not (plan_box[0] <= x['c'][0] <= plan_box[2] and plan_box[1] <= x['c'][1] <= plan_box[3]): continue
            horiz = abs(x['dir'][0]) > 0.5
            lines = BH if horiz else BV
            lat, al = (x['c'][1], x['c'][0]) if horiz else (x['c'][0], x['c'][1])
            cand = [l for l in lines if abs(l[0] - lat) < 12 and l[1] - 5 <= al <= l[2] + 5]
            if not cand: continue
            bl = min(cand, key=lambda l: abs(l[0] - lat))
            best = None
            for rec in bands:
                if not rec.get('pt'): continue
                (x1, y1), (x2, y2) = rec['pt']
                bh = abs(y2 - y1) < abs(x2 - x1)
                if bh != horiz: continue
                blat = (y1 + y2) / 2 if bh else (x1 + x2) / 2
                lo, hi = sorted((x1, x2) if bh else (y1, y2))
                ov_ = min(hi, bl[2]) - max(lo, bl[1])
                frac = ov_ / max(1e-6, min(hi - lo, bl[2] - bl[1]))
                if frac < 0.4: continue
                mid = (bl[1] + bl[2]) / 2
                d = abs(blat - bl[0]) - 40 * min(frac, 1.0) - (60 if lo <= mid <= hi else 0)   # nearest parallel beam; overlap / centre wins a tie
                if abs(blat - bl[0]) < 320 and (best is None or d < best[0]): best = (d, rec)
            bar = {'count': int(m[1]), 'dia_mm': int(m[2]), 'spacing_cm': int(m[3]) if m[3] else None, 'length_cm': int(m[4]),
                   'position': {'ב.ע': 'top', 'ב.ת': 'bottom'}.get(m[5]), 'text': x['t'], 'pt': [round(x['c'][0]), round(x['c'][1])]}
            if best: best[1]['bars'].append(bar)
            else: out['plan'].append(dict(bar, sheet=sh, kind='bar', itm=[r3(v) for v in to_itm(*x['c'])]))
        # ---- sections ----
        cells = section_cells(L, plan_box)
        for c in cells:
            if c['title'].startswith('B-'):
                for rec in bands:
                    if rec['id'] == c['title']: rec['section'] = dict(parse_section(c['texts']), texts=c['texts'], pt=c['pt'])
            elif c['title'].startswith('חתךטיפוסי'):
                wh = c['title'].replace('חתךטיפוסי', ''); lv = parse_section(c['texts'])['levels']
                for rec in bands:
                    if rec.get('section') or not rec.get('width_m') or f"{round(rec['width_m'] * 100)}/{round(rec['depth_m'] * 100)}" != wh: continue
                    if lv and rec.get('topRel') is not None and not any(abs(float(v) - rec['topRel']) < 0.005 for v in lv) and \
                       any(cc['title'] == c['title'] and cc is not c for cc in cells): continue
                    rec['section'] = dict(parse_section(c['texts']), texts=c['texts'], pt=c['pt'], typical=True)
                out['sections'].append(dict(c, sheet=sh, kind='typicalBeam', parsed=parse_section(c['texts'])))
            else:
                out['sections'].append(dict(c, sheet=sh, kind='wall' if c['title'].startswith('W') else 'column', parsed=parse_section(c['texts'])))
        # ---- column / wall bar callouts on the plan (leader end = the element) ----
        thin = []
        for d in page.get_drawings():
            col = d.get('color')
            if not col or max(col) > 0.05 or (d.get('width') or 0) > 0.6: continue
            for it in d['items']:
                if it[0] == 'l': thin.append(((it[1].x, it[1].y), (it[2].x, it[2].y)))
        for x in L:
            tt = x['t'].replace(' ', '')
            mm = MESH_RE.search(tt); cb = COLBAR_RE.match(tt)
            if not (mm or cb) or not (plan_box[0] <= x['c'][0] <= plan_box[2] and plan_box[1] <= x['c'][1] <= plan_box[3]): continue
            bb = x['bb']; box = Polygon([(bb[0] - 4, bb[1] - 4), (bb[2] + 4, bb[1] - 4), (bb[2] + 4, bb[3] + 4), (bb[0] - 4, bb[3] + 4)])
            tip = None
            for a, b in thin:
                for p0, p1 in ((a, b), (b, a)):
                    if box.contains(Point(p0)) and not box.contains(Point(p1)) and math.dist(p0, p1) > 6:
                        if tip is None or math.dist(p0, p1) > tip[0]: tip = (math.dist(p0, p1), p1)
            at = tip[1] if tip else x['c']
            rec = {'sheet': sh, 'kind': 'mesh' if mm else 'columnBars', 'text': x['t'], 'pt': [round(at[0]), round(at[1])],
                   'itm': [r3(v) for v in to_itm(*at)], 'leader': bool(tip)}
            if mm: rec.update(layers=int(mm[1] or 1), dia_mm=int(mm[2]), spacing_cm=[int(mm[3]), int(mm[4])])
            else: rec.update(count=int(cb[1]), dia_mm=int(cb[2]))
            out['plan'].append(rec)
        out['beams'] += bands
        # ---- slab sheet (K-x3): meshes and extra bars of the two plans (bottom / top) ----
        mp = pymupdf.open(os.path.join(ROOT, S['mesh']))[0]
        ML = text_lines(mp)
        W = mp.rect.width
        halves = []
        for lab in ('ברזל תחתון', 'ברזל עליון'):
            ttl = [x for x in ML if x['t'].replace(' ', '') == lab.replace(' ', '')]
            if ttl: halves.append((lab, ttl[0]['c']))
        slab = {'sheet': S['mesh'].split('/')[-1].split('-')[0] + '-' + S['mesh'].split('/')[-1].split('-')[1], 'floor': S['floor'], 'plans': []}
        for lab, c in halves:
            clip = (c[0] - 900, 0, c[0] + 900, c[1])
            A2 = F.pdf_endpoints(S['mesh'], clip)
            sc2, t2, med2 = F.icp(A2, B, tries=80)
            items = []
            for x in ML:
                if not (clip[0] <= x['c'][0] <= clip[2] and clip[1] <= x['c'][1] <= clip[3]): continue
                tt = x['t']
                if not ('ï' in tt or '#' in tt): continue
                P = (x['c'][0] + t2[0] + tg[0], x['c'][1] + t2[1] + tg[1])
                items.append({'text': tt, 'pt': [round(x['c'][0]), round(x['c'][1])], 'itm': [r3(v) for v in F.sheet2itm(*P)]})
            slab['plans'].append({'label': lab, 'position': 'bottom' if 'תחתון' in lab else 'top', 'translation_pt': [r3(v) for v in t2],
                                  'inlierFraction': r3(sc2), 'medianResidual_pt': r3(med2), 'items': items})
        notes = [x['t'] for x in ML if re.search(r'חפיפה|ברזל תחתון|ברזל עליון|רשת', x['t']) and len(x['t']) > 12][:12]
        slab['notes'] = notes
        out['slabs'].append(slab)
        print(sh, 'placement', out['placement'][sh]['translation_pt'], 'res', out['placement'][sh]['medianResidual_pt'],
              '| beams', len(bands), 'with bars', sum(1 for b in bands if b['bars']), 'with section', sum(1 for b in bands if b.get('section')),
              '| sections', len(cells), '| slab plans', [(p['label'], len(p['items']), p['medianResidual_pt']) for p in slab['plans']])
        for b in bands:
            if b['geometry'] == 'notFound': print('   not found on the rebar plan:', b['id'])
    link(out)
    json.dump(out, open(os.path.join(ROOT, 'data/structure/rebar.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def link(out):
    """attach plan callouts / slab items / wall+column sections to the current model elements (ids)"""
    try:
        FR, FG, FF, RF = (J(f'data/structure/{n}.json') for n in ('framing', 'floor-ground', 'floor-first', 'floor-roof'))
    except FileNotFoundError:
        return
    floor_of = {'K-12': 'unit', 'K-22': 'ground', 'K-32': 'first', 'K-42': 'roof'}
    elems = {'unit': [(w['id'], Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0), 'wall') for w in FR['basementWalls']],
             'ground': [(w['id'], Polygon(w['footprintITM']).buffer(0), 'wall') for w in FG['walls']] + [(c['id'], Polygon(c['footprintITM']), 'column') for c in FG['columns']],
             'first': [(w['id'], Polygon(w['footprintITM']).buffer(0), 'wall') for w in FF['walls']] + [(c['id'], Polygon(c['footprintITM']), 'column') for c in FF['columns']],
             'roof': [(w['id'], Polygon(w['footprintITM']).buffer(0), 'wall') for w in RF['walls']] + [(c['id'], Polygon(c['footprintITM']), 'column') for c in RF.get('columns', [])]}
    for p in out['plan']:
        if p['kind'] == 'bar': continue
        E = elems[floor_of[p['sheet']]]
        P = Point(p['itm'])
        near = min(E, key=lambda e: e[1].distance(P)) if E else None
        p['element'] = near[0] if near and near[1].distance(P) < 0.35 else None
        p['elementKind'] = near[2] if p['element'] else None
    slabs = {'unit': [(s['id'], Polygon(s.get('outlineITM') or s.get('footprintITM')).buffer(0)) for s in FR['slabs'] if s.get('outlineITM') or s.get('footprintITM')],
             'ground': [(s['id'], Polygon(s['footprintITM'], s.get('holesITM') or []).buffer(0)) for s in FG['slab']],
             'groundCeiling': [(s['id'], Polygon(s['footprintITM'], s.get('holesITM') or []).buffer(0)) for s in FG['ceiling']['slab']],
             'roof': [(s['id'], Polygon(s['footprintITM'], s.get('holesITM') or []).buffer(0)) for s in FF['ceiling']['slab']]}
    for s in out['slabs']:
        S = slabs.get(s['floor'], [])
        for pl in s['plans']:
            for it in pl['items']:
                P = Point(it['itm'])
                hit = [sid for sid, g in S if g.buffer(0.3).contains(P)]
                it['slab'] = hit[0] if hit else None
    # wall sections (W1 …) -> model walls by their tag
    tagged = {}
    for fl, D in (('ground', FG), ('first', FF), ('roof', RF)):
        for w in D['walls']:
            if w.get('tag'): tagged.setdefault(w['tag'], []).append(w['id'])
    cols = {'K-12': [], 'K-22': FG['columns'], 'K-32': FF['columns'], 'K-42': RF.get('columns', [])}
    for s in out['sections']:
        if s['kind'] == 'wall': s['elements'] = tagged.get(s['title'], [])
        if s['kind'] == 'column':
            wh = sorted(int(v) for v in s['title'].replace('עמודבחתך', '').split('/'))
            s['elements'] = [c['id'] for c in cols[s['sheet']] if sorted(c['size_cm']) == wh]
    print('links: plan callouts on elements', sum(1 for p in out['plan'] if p.get('element')), '/', sum(1 for p in out['plan'] if p['kind'] != 'bar'),
          '| slab items in a slab', sum(1 for s in out['slabs'] for pl in s['plans'] for it in pl['items'] if it.get('slab')))


if __name__ == '__main__':
    if '--link' in sys.argv:
        o = J('data/structure/rebar.json'); link(o)
        json.dump(o, open(os.path.join(ROOT, 'data/structure/rebar.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    else:
        main()

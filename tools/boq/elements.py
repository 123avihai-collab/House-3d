# -*- coding: utf-8 -*-
"""Element take-off for the skeleton bill of quantities (stage 1 of the BOQ: earthworks → blocks).

Reads ONLY the model's data files (data/…) and returns plain records. The workbook writer
(tools/boq/build_boq.py) turns every record into a row with live formulas (n × A × (H − ded)), so the
numbers here are inputs (dimensions), not results. Conventions mirror the model's own quantities
(js/geometry/*.js stats) so the totals can be cross-checked against docs/quantities/boq/model-quantities.json:
  • slab volume = footprint area (holes excluded) × thickness
  • wall / column volume = footprint area × (top − bottom)
  • beam volume = length × width × (depth − part inside the slab it meets)   (the slab part is counted with the slab)
  • pile volume = π/4 · d² · L
"""
import json, math, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def J(rel):
    return json.load(open(ROOT / rel, encoding='utf-8'))


def r3(x):
    return round(float(x), 3)


def ring_area(r):
    a = 0.0
    for i in range(len(r)):
        x1, y1 = r[i]; x2, y2 = r[(i + 1) % len(r)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def ring_perim(r):
    return sum(math.hypot(r[(i + 1) % len(r)][0] - r[i][0], r[(i + 1) % len(r)][1] - r[i][1]) for i in range(len(r)))


def centroid(r):
    return (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))


def in_ring(r, p):
    x, y = p; c = False; j = len(r) - 1
    for i in range(len(r)):
        xi, yi = r[i]; xj, yj = r[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def long_side(r):
    """Length of the footprint along its longest edge direction (walls drawn as a band)."""
    best = 0.0
    for i in range(len(r)):
        best = max(best, math.hypot(r[(i + 1) % len(r)][0] - r[i][0], r[(i + 1) % len(r)][1] - r[i][1]))
    return best


def loc(E, N, extra=''):
    return f"{extra}{' · ' if extra else ''}E {E:.2f} / N {N:.2f}"


def kgm(d):
    return d * d / 162.0


FLOOR_HE = {'unit': 'יחידת דיור', 'ground': 'קרקע', 'first': "קומה א'", 'roof': 'גג', 'site': 'מגרש'}
ZONE_HE = {'house': 'בית', 'terrace': 'מרפסת', 'parking': 'חניה', 'southYard': 'חצר דרום', 'westYard': 'חצר מערב',
           'eastYard': 'חצר מזרח', 'mamad': 'ממ"ד', 'entry': 'כניסה'}


def parse_stirrup(texts):
    """('ï8 @15', 'L=170', …) → (legs, dia, spacing_cm, length_cm) of the main stirrup, or None."""
    if not texts:
        return None
    legs, dia, sp, L = 1, None, None, None
    for t in texts:
        m = re.match(r'\s*(\d+)?\s*ï(\d+)\s*@\s*(\d+)', t)
        if m and dia is None:
            legs = int(m.group(1) or 1); dia = int(m.group(2)); sp = int(m.group(3))
        m2 = re.match(r'\s*L=(\d+)', t)
        if m2 and L is None and int(m2.group(1)) != 220:   # L=220 = the typical U-bar at the slab edge, not the stirrup
            L = int(m2.group(1))
    return (legs, dia, sp, L) if dia else None


def parse_mesh(text):
    """'#ï8@10/10 בכל השטח' / '2#ï8 @15 \\15' → (layers, dia, s1, s2)."""
    m = re.search(r'(\d+)?\s*#\s*ï(\d+)\s*@\s*(\d+)\s*[/\\]\s*(\d+)', text)
    if not m:
        return None
    return (int(m.group(1) or 1), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def parse_bars(text):
    """'24 ï12 @15 L=300 -ב.ת' → (count, dia, length_cm)."""
    m = re.search(r'(\d+)\s*ï(\d+)(?:\s*@\s*\d+)?\s*L=(\d+)', text)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def parse_count_bars(text):
    m = re.match(r'\s*(\d+)\s*ï(\d+)', text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def collect():
    H0 = J('data/site/origin.json')
    h0 = next((H0[k] for k in ('H0', 'h0', 'H0_m') if k in H0), None)
    if isinstance(h0, dict):
        h0 = h0.get('value') or h0.get('H')
    piles = J('data/structure/piles.json'); fr = J('data/structure/framing.json'); bas = J('data/structure/basement.json')
    fg = J('data/structure/floor-ground.json'); ff = J('data/structure/floor-first.json'); froof = J('data/structure/floor-roof.json')
    per = J('data/structure/perimeter.json'); st = J('data/structure/stairs.json'); pool = J('data/structure/pool.json')
    rb = J('data/structure/rebar.json'); exc = J('data/structure/excavation.json')
    E = []   # concrete elements

    def add(sec, **k):
        k.setdefault('n', 1); k.setdefault('ded', 0.0); k.setdefault('fw', []); k.setdefault('rb', []); k.setdefault('note', '')
        k['sec'] = sec; E.append(k); return k

    # ---------- piles (K-400) ----------
    cage = {0.5: 7, 0.6: 8}          # K-400 pile table, column with 7Φω16 / 8Φω16 (= section A-A "7Φ16")
    starters = {0.5: 10, 0.6: 12}    # K-400 "פרט חיבור כלונס לקיר": 10Φ12 / 12Φ12 l=250
    for p in piles['piles']:
        d = p['diameter_m']
        e = add('piles', id=f"P{p['id']}", name=f"כלונס ø{int(d*100)} L={p['length_m']:g}", floor='site' if p['zone'] != 'basement' else 'unit',
                step='pilesBasement' if p['zone'] == 'basement' else 'pilesOutside', loc=loc(p['E'], p['N'], f"ראש {p['headRel']:+.2f}"),
                L=p['length_m'], W=d, H=None, A=('cyl', d), shape='π/4·d²·L', waste='concretePiles', price='concrete_piles',
                status='source', source=p['source'], note=f"עומס תכנון {p.get('designLoad_t')} ט'")
        e['rb'] = [
            dict(desc=f"מוטות אורך {cage[d]}ø16 (L + עיגון)", dia=16, count=cage[d], length=f"{{L}}+{{P:pileAnchor_m}}", src='K-400 טבלת כלונסאות + חתך A-A', status='source'),
            dict(desc='חישוק לוליני ø8 – קטע עליון @10', dia=8, count=f"{{P:spiralDense_m}}/0.10", length=f"PI()*({{W}}-2*0.075)", src='K-400 חתך A-A "חישוק לוליני ø8@10(20)"; כיסוי 7.5 ס"מ (ספייסרים)', status='provisional'),
            dict(desc='חישוק לוליני ø8 – יתרה @20', dia=8, count=f"({{L}}-{{P:spiralDense_m}})/0.20", length=f"PI()*({{W}}-2*0.075)", src='K-400 חתך A-A', status='source'),
            dict(desc='טבעות חיזוק ø14 @300', dia=14, count=f"ROUNDUP({{L}}/3,0)", length=f"PI()*({{W}}-2*0.075-0.03)", src='K-400 פרט כלונס "טבעת חיזוק Φ14@300"', status='source'),
        ]
        if p['headRel'] > -2.9:   # outside the basement pit: the pile joins a beam / wall (connection detail)
            e['rb'].append(dict(desc=f"קוצי חיבור {starters[d]}ø12 l=2.50", dia=12, count=starters[d], length=2.5, src='K-400 "פרט חיבור כלונס לקיר" (10Φ12 / 12Φ12 l=250)', status='provisional'))
    # ---------- basement beams + ground beams + ceiling beams over the basement (K-11 / K-21) ----------
    gD = max(s['thickness_m'] for s in fg['slab'])
    rbBeams = {(b['geomSheet'] if 'geomSheet' in b else b['sheet'].replace('-2', '-1').replace('-3', '-2'), b['id']): b for b in rb['beams']}
    for b in fr['groundBeams']:
        if not b.get('axisITM'):
            continue
        (E1, N1), (E2, N2) = b['axisITM']; L = math.hypot(E2 - E1, N2 - N1)
        ovl = min(gD, b['depth_m']) if b['sheet'] == 'K-21' else 0.0
        step = {'groundBeams': 'basementBeams', 'groundFloorBeams': 'groundSlab', 'ceilingBeams': 'groundSlab'}.get(b.get('layer'), 'groundSlab')
        floor = 'unit' if b['sheet'] == 'K-11' else 'ground'
        zone = fg.get('beamZones', {}).get(b['id'])
        e = add('beamsFound', id=b['id'], name=f"קורה {b['id']} {int(round(b['width_m']*100))}/{int(round(b['depth_m']*100))}", floor=floor, step=step,
                loc=loc((E1 + E2) / 2, (N1 + N2) / 2, f"{b['sheet']}{' · ' + ZONE_HE.get(zone, zone) if zone else ''} · O.K {b['topRel']:+.2f}"),
                L=r3(L), W=b['width_m'], H=b['depth_m'], ded=ovl, A=None, shape='L·b·(h − עובי רצפה)' if ovl else 'L·b·h',
                waste='concreteCast', price='concrete_b30', status=b.get('status', 'provisional'), source=b['source'] + '; ' + b.get('geometrySource', ''),
                note='החלק שבתוך הרצפה נספר עם הרצפה' if ovl else '')
        # on lean concrete / void formers: sides only (the bottom sits on the lean concrete)
        e['fw'] = [('beams', '2*{n}*{L}*({H}-{ded})', 'צדי קורה (תחתית על בטון רזה / ארגזי הפרדה)')]
        e['rb'] = beam_rebar(rbBeams.get((('K-11' if b['sheet'] == 'K-11' else 'K-21'), b['id'])))
    for c in fr.get('pileCaps', []):
        ce = centroid(c['ringITM'])
        e = add('beamsFound', id=c['id'], name=f"ראש כלונס כפול {'/'.join(c['piles'])}", floor='ground', step='groundSlab', loc=loc(*ce, f"O.K {c['topRel']:+.2f}"),
                L=c['size_m'][0], W=c['size_m'][1], H=c['depth_m'], A=None, shape='a·b·h', waste='concreteCast', price='concrete_b30', status=c['status'], source=c['source'])
        e['fw'] = [('beams', '2*{n}*({L}+{W})*{H}', 'היקף × גובה')]
        e['rb'] = [dict(desc='ברזל עליון 4ø14 L=360', dia=14, count=4, length=3.6, src='K-400 "פרט ראש כלונס כפול קוטר 60-1"', status='source'),
                   dict(desc='ברזל אמצע 2ø18', dia=18, count=2, length=2.55, src='K-400 פרט ראש כלונס כפול (L=255)', status='source'),
                   dict(desc='ברזל תחתון 8ø25 L=360', dia=25, count=8, length=3.6, src='K-400 פרט ראש כלונס כפול', status='source'),
                   dict(desc='חישוקים ø8@20 L=240 (×2)', dia=8, count='2*ROUNDUP({L}/0.2+1,0)', length=2.4, src='K-400 "פרט ראש כלונס כפול קוטר 60-2"', status='source')]
    # ---------- basement slabs (K-11) ----------
    rbSlab = slab_meshes(rb)
    for s in fr['slabs']:
        ce = centroid(s['outlineITM'])
        e = add('slabs', id=s['id'], name=f"רצפת מרתף {s['id']} ({int(round(s['thickness_m']*100))} ס\"מ)", floor='unit', step='basementSlab',
                loc=loc(*ce, f"O.K {s['top']:+.2f}"), L=None, W=None, H=s['thickness_m'], A=s['area_m2'], P=r3(ring_perim(s['outlineITM'])),
                shape='A·t', waste='concreteCast', price='concrete_b30', status=s['status'], source=s['source'])
        e['fw'] = [('edges', '{P}*{H}', 'שולי רצפה (היקף × עובי); התחתית על ארגזי הפרדה')]
        e['rb'] = rbSlab.get(s['id'], []) or [dict(desc='רשת ø8@15/15 עליונה + תחתונה (K-13 "בכל השטח")', mesh=(2, 8, 15, 15), src='K-13', status='provisional')]
    # ---------- basement walls (K-11) ----------
    wallBars = column_bars(rb)
    for w in fr['basementWalls']:
        ce = centroid(w['footprintITM']); t = 0.22 if w['id'] == 'BW1' else 0.2
        e = add('walls', id=w['id'], name=f"קירות מרתף {w['id']}", floor='unit', step='basementWalls', loc=loc(*ce, 'מרתף'),
                L=None, W=None, H=r3(w['topRel'] - w['bottomRel']), A=w['area_m2'], shape='A(טביעה)·H', waste='concreteCast', price='concrete_b30',
                status=w['status'], source=w['source'], note='טביעת הרגל כוללת את כל קטעי הקיר; פתחים U0x – מילוי ביציקה נפרדת (infill) לא נוכה, לפי המודל')
        e['Lw'] = ('A/t', t)
        e['fw'] = [('walls', '2*{A}/{t}*{H}', 'שני צדי הקיר: 2 × (A / עובי) × H')]
        e['rb'] = wall_rebar(w['id'], rb, wallBars)
    # ---------- ground floor (K-21) ----------
    for s in fg['slab']:
        ce = centroid(s['footprintITM'])
        e = add('slabs', id=s['id'], name=f"רצפת קרקע {s['id']} – {s.get('zoneLabel') or ZONE_HE.get(s['zone'], s['zone'])}", floor='ground',
                step='groundSlab' if s['zone'] not in ('terrace', 'parking', 'southYard', 'westYard', 'eastYard') else 'outdoorSlabs',
                loc=loc(*ce, f"O.K {s['topRel']:+.2f}"), H=s['thickness_m'], A=s['area_m2'], P=r3(ring_perim(s['footprintITM'])),
                shape='A·t', waste='concreteCast', price='concrete_b30', status=s['status'], source=s['source'], L=None, W=None)
        e['fw'] = [('edges', '{P}*{H}', 'שולי רצפה; התחתית על ארגזי הפרדה')]
        e['rb'] = rbSlab.get(s['id'], []) or [dict(desc='רשת ø8@10/10 תחתונה + עליונה (K-23 "בכל השטח")', mesh=(2, 8, 10, 10), src='K-23 (אין תווית לאזור – לפי הרשת הכללית)', status='provisional')]
    for floor, F, wstep, cstep in (('ground', fg, 'groundWalls', 'groundCeiling'), ('first', ff, 'firstWalls', 'firstCeiling'), ('roof', froof, 'roofWalls', 'roofWalls')):
        for w in F['walls']:
            ce = centroid(w['footprintITM']); H = r3(w['topRel'] - w['bottomRel'])
            e = add('walls', id=w['id'], name=w.get('displayName') or f"קיר בטון {w['id']} ({int(round(w['thickness_m']*100))} ס\"מ)", floor=floor, step=wstep,
                    loc=loc(*ce, f"{w['bottomRel']:+.2f} … {w['topRel']:+.2f}"), L=None, W=None, H=H, A=w['area_m2'], shape='A(טביעה)·H',
                    waste='concreteCast', price='concrete_b30', status=w['status'], source=w['source'])
            e['Lw'] = ('A/t', w['thickness_m'])
            e['fw'] = [('walls', '2*{A}/{t}*{H}', '2 × (A / עובי) × H')]
            e['rb'] = wall_rebar(w['id'], rb, wallBars)
        for c in F.get('columns', []):
            ce = centroid(c['footprintITM']); a, b = c['size_cm'][0] / 100, c['size_cm'][1] / 100
            e = add('columns', id=f"{c['id']}@{floor}", name=f"עמוד {c['id']} {c['size_cm'][0]}/{c['size_cm'][1]}", floor=floor, step=wstep,
                    loc=loc(*ce, f"{c['bottomRel']:+.2f} … {c['topRel']:+.2f}"), L=a, W=b, H=r3(c['topRel'] - c['bottomRel']), A=None, shape='a·b·H',
                    waste='concreteCast', price='concrete_b30', status=c['status'], source=c['source'], note=c.get('note', ''))
            e['fw'] = [('columns', '2*{n}*({L}+{W})*{H}', 'היקף × גובה')]
            e['rb'] = column_rebar(c['id'], floor, rb, wallBars)
        C = F.get('ceiling') or {}
        for s in C.get('slab', []):
            ce = centroid(s['footprintITM'])
            e = add('ceilings', id=s['id'], name=f"{'תקרת קרקע' if floor == 'ground' else 'תקרת גג'} {s['id']} ({int(round(s['thickness_m']*100))} ס\"מ)", floor=floor, step=cstep,
                    loc=loc(*ce, f"O.K {s['topRel']:+.2f}"), H=s['thickness_m'], A=s['area_m2'], P=r3(ring_perim(s['footprintITM'])), L=None, W=None,
                    shape='A·t', waste='concreteCast', price='concrete_b30', status=s['status'], source=s['source'])
            e['fw'] = [('slabs', '{A}', 'תחתית תקרה (שטח)'), ('edges', '{P}*{H}', 'שולי תקרה')]
            e['props'] = '{A}'
            e['rb'] = rbSlab.get(s['id'], []) or [dict(desc='רשת ø8@10/10 תחתונה + עליונה', mesh=(2, 8, 10, 10), src='K-33/43 (לפי הרשת הכללית)', status='provisional')]
        sl = (C.get('slab') or [None])[0]
        for b in C.get('beams', []):
            if not b.get('axisITM'):
                continue
            (E1, N1), (E2, N2) = b['axisITM']; L = math.hypot(E2 - E1, N2 - N1)
            ov = max(0.0, min(b['topRel'], sl['topRel']) - max(b['bottomRel'], sl['bottomRel'])) if sl and not b.get('pergola') else 0.0
            step = b.get('castWith') or cstep
            if floor == 'roof':
                step = 'roofWalls' if b.get('castWith') else 'roofBeams'
            sheet = {'ground': 'K-31', 'first': 'K-41', 'roof': 'K-41'}[floor]
            e = add('beamsCeil', id=b['id'], name=f"{'קורת פרגולה' if b.get('pergola') else 'קורה'} {b['id']} {int(round(b['width_m']*100))}/{int(round(b['depth_m']*100))}",
                    floor=floor, step=step, loc=loc((E1 + E2) / 2, (N1 + N2) / 2, f"{sheet} · O.K {b['topRel']:+.2f}"), L=r3(L), W=b['width_m'], H=b['depth_m'], ded=r3(ov), A=None,
                    shape='L·b·(h − עובי תקרה)' if ov else 'L·b·h', waste='concreteCast', price='concrete_b30', status=b.get('status', 'source'), source=b['source'],
                    note=(b.get('note') or '')[:160])
            e['fw'] = [('beams', '{n}*{L}*({W}+2*({H}-{ded}))', 'תחתית + 2 צדדים (מתחת לתקרה)')]
            e['propsBeam'] = '{n}*{L}'
            key = ({'ground': 'K-31', 'first': 'K-41', 'roof': 'K-41'}[floor], b['id'])
            e['rb'] = beam_rebar(rbBeams.get(key))
    # ---------- stairs ----------
    for s in st['stairs']:
        if s['kind'] != 'concrete':
            continue
        for f in s.get('flights', []):
            n = f['risers']; rise = s['rise_m']; go = f['going_m']
            e = add('stairs', id=f['id'], name=f"{s['name']} – מהלך {f['id']}", floor=s['floor'], step='stairsPour' if s['id'] == 'ST1' else 'outdoorSlabs',
                    loc=loc(*f['originITM'], f"{n} רומים × {rise:.3f}"), L=r3(math.hypot(n * go, n * rise)), W=f['width_m'], H=s['waist_m'], A=None,
                    shape='לוח משופע L·b·t + מדרגות n·(g·r/2)·b', waste='concreteCast', price='concrete_b30', status='provisional', source=s['source'],
                    note=f"g={go:.3f}, r={rise:.3f}, n={n}")
            e['extra'] = f"+{n}*{go}*{rise}/2*{{W}}"
            e['fw'] = [('slabs', '{L}*{W}', 'תחתית משופעת'), ('edges', f"{n}*{rise}*{{W}}+2*({{L}}*{{H}}+{n}*{go}*{rise}/2)", 'רומים + לחיים')]
            e['rb'] = [dict(desc='ברזל מדרגות – יחס', ratio='stairs', src='אין תוכנית קונסטרוקציה למדרגות', status='provisional')]
        for l in s.get('landings', []):
            A = ring_area(l['ringITM'])
            e = add('stairs', id=l['id'], name=f"{s['name']} – {l['label']}", floor=s['floor'], step='stairsPour' if s['id'] == 'ST1' else 'outdoorSlabs',
                    loc=loc(*centroid(l['ringITM']), f"{l['topRel']:+.2f}"), H=l['thickness_m'], A=r3(A), P=r3(ring_perim(l['ringITM'])), L=None, W=None,
                    shape='A·t', waste='concreteCast', price='concrete_b30', status='provisional', source=s['source'])
            e['fw'] = [('slabs', '{A}', 'תחתית'), ('edges', '{P}*{H}', 'שוליים')]
            e['rb'] = [dict(desc='ברזל פודסט – יחס', ratio='stairs', src='אין תוכנית', status='provisional')]
    # ---------- perimeter walls (fence walls) ----------
    for f in per['footings']:
        e = add('perimeter', id=f['id'], name=f"יסוד חומה {f['id']} ({f['side']}) {int(f['width_m']*100)}/{int(f['thickness_m']*100)}", floor='site', step='perimeterFootings',
                loc=loc(*centroid(f['ringITM']), f"{f['bottomRel']:+.2f} … {f['topRel']:+.2f}"), H=f['thickness_m'], A=f['area_m2'], L=None, W=None,
                shape='A·t', waste='concreteCast', price='concrete_b30', status=f['status'], source=f['source'])
        e['Lw'] = ('A/t', f['width_m'])
        e['fw'] = [('edges', '2*{A}/{t}*{H}', 'צדי היסוד')]
        e['rb'] = [dict(desc='ברזל יסוד חומה – יחס', ratio='perimeterFooting', src='K-400 חתך חומה (זיון לא חולץ)', status='provisional')]
    for w in per['walls']:
        A = ring_area(w['ringITM'])
        e = add('perimeter', id=w['id'], name=f"חומה {w['id']} ({w['side']}) {int(w['thickness_m']*100)} ס\"מ", floor='site', step='perimeterWalls',
                loc=loc(*centroid(w['ringITM']), f"ראש {w['topRel']:+.2f}"), H=r3(w['topRel'] - w['bottomRel']), A=r3(A), L=None, W=None,
                shape='A(טביעה)·H', waste='concreteCast', price='concrete_b30', status=w['status'], source=w['source'])
        e['Lw'] = ('A/t', w['thickness_m'])
        e['fw'] = [('walls', '2*{A}/{t}*{H}', 'שני צדי החומה')]
        e['rb'] = [dict(desc='ברזל חומה – יחס', ratio='perimeterWall', src='K-400 חתך חומה (זיון לא חולץ)', status='provisional')]
    P = st['pillar']
    for i, ring in enumerate(P['wallsITM']):
        A = ring_area(ring) - sum(ring_area(h) for h in (P['wallHolesITM'][i] if i < len(P['wallHolesITM']) else []) if h)
        t = P['wallThickness_m'][i]
        e = add('perimeter', id=f"{P['id']}-{i+1}", name=P['name'], floor='site', step='perimeterWalls', loc=loc(*centroid(ring), 'פילר'),
                H=r3(P['topRel'] - P['bottomRel']), A=r3(A), L=None, W=None, shape='A(טביעה)·H', waste='concreteCast', price='concrete_b30', status=P['status'], source=P['source'])
        e['Lw'] = ('A/t', t)
        e['fw'] = [('walls', '2*{A}/{t}*{H}', 'שני צדי הקיר')]
        e['rb'] = [dict(desc='ברזל פילר – יחס', ratio='pillar', src='אין פרט', status='provisional')]
    # ---------- pool (K-21 + pool sections) ----------
    pl = pool['pool']; H0abs = J('data/site/origin.json')['H0']
    rel = lambda z: r3(z - H0abs)
    for i, ring in enumerate(pl['wallsITM']):
        A = ring_area(ring)
        e = add('pool', id=f"BR-W{i+1}", name='קיר בריכה 20 ס"מ', floor='site', step='basementWalls', loc=loc(*centroid(ring), 'בריכה'),
                H=r3(pl['deckSlabTop'] - pl['wallBottom']), A=r3(A), L=None, W=None, shape='A(טביעה)·H', waste='concreteCast', price='concrete_b30',
                status=pl['status'], source=pl['source'], note=f"{rel(pl['wallBottom'])} … {rel(pl['deckSlabTop'])}")
        e['Lw'] = ('A/t', 0.2)
        e['fw'] = [('walls', '2*{A}/{t}*{H}', 'שני צדי הקיר')]
        e['rb'] = [dict(desc='ברזל קיר בריכה – יחס', ratio='pool', src='אין פריסת ברזל לבריכה', status='provisional')]
    wallsA = sum(ring_area(r) for r in pl['wallsITM'])
    slabA = ring_area(pl['outerITM']) - wallsA
    e = add('pool', id='BR-S1', name='רצפת בריכה 20 ס"מ (משופעת 4.9%)', floor='site', step='basementSlab', loc=loc(*centroid(pl['outerITM']), 'בריכה'),
            H=0.2, A=r3(slabA), L=None, W=None, shape='A(פנים)·t', waste='concreteCast', price='concrete_b30', status='provisional', source=pl['source'],
            note=f"תחתית {pl['slabUndersideWest']:.2f} מערב / {pl['slabUndersideEast']:.2f} מזרח, עובי 20 ס\"מ (pool.json note)")
    e['fw'] = [('edges', '0', 'יציקה על בטון רזה – בלי טפסנות')]
    e['rb'] = [dict(desc='ברזל רצפת בריכה – יחס', ratio='pool', src='אין פריסת ברזל', status='provisional')]
    stepsA = sum(ring_area(s['ringITM']) for s in pl['steps'])
    e = add('pool', id='BR-ST', name='מדרגות ומשטח כניסה לבריכה', floor='site', step='basementWalls', loc=loc(*centroid(pl['platform']['ringITM']), 'בריכה'),
            H=r3(sum(s['top'] - (pl['slabUndersideWest'] + 0.2) for s in pl['steps']) / len(pl['steps'])), A=r3(stepsA), L=None, W=None, shape='ΣA·גובה ממוצע',
            waste='concreteCast', price='concrete_b30', status='provisional', source=pl['stepsSource'], note='6 שלבים מלאים מרצפת הבריכה (בטון מלא – הנחה); משטח הרביצה נכלל ברצפה')
    e['fw'] = [('edges', '6*0.17*' + str(pl['stairsWidth_m']), 'רומי השלבים')]
    e['rb'] = [dict(desc='ברזל מדרגות בריכה – יחס', ratio='stairs', src='אין פרט', status='provisional')]
    platA = ring_area(pl['platform']['ringITM'])
    e = add('pool', id='BR-PL', name='משטח רביצה בבריכה', floor='site', step='basementWalls', loc=loc(*centroid(pl['platform']['ringITM']), 'בריכה'),
            H=r3(pl['platform']['top'] - (pl['slabUndersideWest'] + 0.2)), A=r3(platA), L=None, W=None, shape='A·H', waste='concreteCast', price='concrete_b30', status='provisional', source=pl['stepsSource'])
    e['fw'] = [('edges', '{P}*{H}', 'שוליים')]; e['P'] = r3(ring_perim(pl['platform']['ringITM']))
    e['rb'] = [dict(desc='ברזל – יחס', ratio='stairs', src='אין פרט', status='provisional')]
    g = pool['gutter']
    gA = ring_area(g['ringOuterITM']) - ring_area(g['ringInnerITM'])
    e = add('pool', id='BR-G', name='תעלת גלישה + שפה', floor='site', step='basementWalls', loc=loc(*centroid(g['ringOuterITM']), 'בריכה'),
            H=r3(g['lipTop'] - g['bottom']), A=r3(gA * g['lipWidth_m'] / (g['width_m'] + g['lipWidth_m'])), L=None, W=None, shape='A(שפה)·H + רצפת תעלה',
            waste='concreteCast', price='concrete_b30', status=g['status'], source=g['source'],
            note='השפה (20 ס"מ) בגובה מלא + רצפת התעלה 25 ס"מ × 8 ס"מ')
    e['extra'] = f"+{r3(gA * g['width_m'] / (g['width_m'] + g['lipWidth_m']))}*{r3(g['floor'] - g['bottom'])}"
    e['Lw'] = ('A/t', g['lipWidth_m'])
    e['fw'] = [('walls', '2*{A}/{t}*{H}', 'שני צדי השפה')]
    e['rb'] = [dict(desc='ברזל – יחס', ratio='pool', src='אין פרט', status='provisional')]
    ch = pool['channel']
    for i, ring in enumerate(ch['wallsITM']):
        e = add('pool', id=f"BR-C{i+1}", name='קיר תעלת תריס כיסוי', floor='site', step='basementWalls', loc=loc(*centroid(ring), 'תעלת תריס'),
                H=r3(ch['top'] - ch['bottom']), A=r3(ring_area(ring)), L=None, W=None, shape='A·H', waste='concreteCast', price='concrete_b30', status=ch['status'], source=ch['source'])
        e['Lw'] = ('A/t', 0.2)
        e['fw'] = [('walls', '2*{A}/{t}*{H}', 'שני צדי הקיר')]
        e['rb'] = [dict(desc='ברזל – יחס', ratio='pool', src='אין פרט', status='provisional')]
    chFloor = ring_area(ch['outerITM']) - sum(ring_area(r) for r in ch['wallsITM'])
    e = add('pool', id='BR-CF', name='רצפת תעלת תריס', floor='site', step='basementSlab', loc=loc(*centroid(ch['outerITM']), 'תעלת תריס'),
            H=r3(ch['floor'] - ch['bottom']), A=r3(chFloor), L=None, W=None, shape='A·t', waste='concreteCast', price='concrete_b30', status=ch['status'], source=ch['source'])
    e['rb'] = [dict(desc='ברזל – יחס', ratio='pool', src='אין פרט', status='provisional')]
    tk = pool['tank']
    for i, ring in enumerate(tk['wallsITM']):
        e = add('pool', id=f"BR-T{i+1}", name='קיר חדר מכונות / בור איזון', floor='site', step='basementWalls', loc=loc(*centroid(ring), 'חדר מכונות'),
                H=r3(tk['top'] - tk['wallBottom']), A=r3(ring_area(ring)), L=None, W=None, shape='A·H', waste='concreteCast', price='concrete_b30', status=tk['status'], source=tk['source'])
        e['Lw'] = ('A/t', 0.2)
        e['fw'] = [('walls', '2*{A}/{t}*{H}', 'שני צדי הקיר')]
        e['rb'] = [dict(desc='ברזל – יחס', ratio='pool', src='אין פרט', status='provisional')]
    tkFloor = ring_area(tk['pitITM'])
    e = add('pool', id='BR-TF', name='רצפת חדר המכונות', floor='site', step='basementSlab', loc=loc(*centroid(tk['pitITM']), 'חדר מכונות'),
            H=tk['slabThickness_m'], A=r3(tkFloor), L=None, W=None, shape='A·t', waste='concreteCast', price='concrete_b30', status=tk['status'], source=tk['source'])
    e['rb'] = [dict(desc='ברזל – יחס', ratio='pool', src='אין פרט', status='provisional')]
    return E


def beam_rebar(b):
    if not b:
        return [dict(desc='אין פריסת ברזל לקורה – יחס קירות', ratio='wall', src='לא נמצאה בגיליונות K-x2', status='provisional')]
    out = []
    for x in b.get('bars', []):
        out.append(dict(desc=f"{x['count']}ø{x['dia_mm']} L={x['length_cm']} {'ב.ע' if x['position'] == 'top' else 'ב.ת'}", dia=x['dia_mm'], count=x['count'], length=x['length_cm'] / 100,
                        src=f"{b['sheet']} {x['text']}", status='source'))
    s = parse_stirrup((b.get('section') or {}).get('stirrups'))
    if s:
        legs, dia, sp, L = s
        length = (L / 100) if L else '2*({W}+{H})-8*{P:cover_m}+0.2'
        out.append(dict(desc=f"חישוקים {legs if legs > 1 else ''}ø{dia}@{sp}{' L=' + str(L) if L else ''}", dia=dia, count=f"{legs}*ROUNDUP({{L}}/{sp/100}+1,0)", length=length,
                        src=f"{b['sheet']} חתך {b['id']}: {' · '.join((b.get('section') or {}).get('stirrups') or [])}", status='source' if L else 'provisional'))
    elif not out:
        out.append(dict(desc='אין פריסה – יחס', ratio='wall', src=b['sheet'], status='provisional'))
    else:
        out.append(dict(desc='חישוקים ø8@15 (אין חתך – הנחה)', dia=8, count='ROUNDUP({L}/0.15+1,0)', length='2*({W}+{H})-8*{P:cover_m}+0.2', src=f"{b['sheet']} – אין חתך לקורה", status='provisional'))
    return out


def slab_meshes(rb):
    """slab id → rebar rows from K-13/23/33/43 ('#ï8@10/10 בכל השטח', extra bars '24 ï12 @15 L=300')."""
    out = {}
    for s in rb['slabs']:
        for plan in s['plans']:
            seen = set()
            for it in plan['items']:
                sid = it.get('slab')
                if not sid:
                    continue
                m = parse_mesh(it['text'])
                key = (sid, plan['position'], it['text'])
                if key in seen:
                    continue
                seen.add(key)
                if m:
                    if any(r.get('mesh') and r.get('pos') == plan['position'] for r in out.get(sid, [])):
                        continue   # one general mesh per layer (the same note repeated over the slab)
                    out.setdefault(sid, []).append(dict(desc=f"רשת {plan['label']} ø{m[1]}@{m[2]}/{m[3]} בכל השטח", mesh=(1, m[1], m[2], m[3]), pos=plan['position'],
                                                        src=f"{s['sheet']} {plan['label']}: {it['text']}", status='source'))
                else:
                    b = parse_bars(it['text'])
                    if b:
                        out.setdefault(sid, []).append(dict(desc=f"תוספת {b[0]}ø{b[1]} L={b[2]} ({plan['label']})", dia=b[1], count=b[0], length=b[2] / 100,
                                                            src=f"{s['sheet']}: {it['text']}", status='source'))
    return out


def column_bars(rb):
    """element id → [(count, dia, sheet)] from the 'columnBars' notes of K-12/22/32/42."""
    out = {}
    for p in rb['plan']:
        if p['kind'] == 'columnBars' and p.get('element'):
            cb = parse_count_bars(p['text'])
            if cb:
                out.setdefault((p['sheet'], p['element']), set()).add((cb[0], cb[1]))
    return out


def wall_rebar(wid, rb, bars):
    rows = []
    meshes = {(p['sheet'], p['text']) for p in rb['plan'] if p['kind'] == 'mesh' and p.get('element') == wid}
    for sheet, text in sorted(meshes):
        m = parse_mesh(text)
        if m:
            rows.append(dict(desc=f"רשת {m[0]} שכבות ø{m[1]}@{m[2]}/{m[3]} (שני כיוונים)", mesh=(m[0], m[1], m[2], m[3]), face=True, src=f"{sheet}: {text}", status='source'))
    for (sheet, el), s in bars.items():
        if el == wid:
            for cnt, dia in sorted(s):
                rows.append(dict(desc=f"מוטות אנכיים {cnt}ø{dia} (ריכוז בקצה / בפינה)", dia=dia, count=cnt, length=f"{{H}}+{{P:lap_d}}*{dia}/1000", src=f"{sheet}: {cnt}ø{dia}", status='source'))
    if not rows:
        rows.append(dict(desc='אין פריסת ברזל לקיר – יחס', ratio='wall', src='K-x2/x3 – לא נמצאה תווית לקיר', status='provisional'))
    elif not any(r.get('mesh') for r in rows):
        rows.append(dict(desc='רשת קיר – יחס (אין רשת כתובה)', ratio='wall', src='הערכה', status='provisional'))
    return rows


def column_rebar(cid, floor, rb, bars):
    sheet = {'ground': 'K-22', 'first': 'K-32', 'roof': 'K-42'}.get(floor)
    rows = []
    for cnt, dia in sorted(bars.get((sheet, cid), [])):
        rows.append(dict(desc=f"מוטות אורך {cnt}ø{dia} + חפייה 45d", dia=dia, count=cnt, length=f"{{H}}+{{P:lap_d}}*{dia}/1000", src=f"{sheet}: {cnt}ø{dia} ({cid})", status='source'))
    rows.append(dict(desc='חישוקים – יחס (אין פרט)', ratio='column', src='אין פרט חישוקים לעמודים', status='provisional'))
    if len(rows) == 1:
        rows.insert(0, dict(desc='מוטות אורך – יחס קירות', ratio='wall', src=f"{sheet}: לא נמצאה תווית", status='provisional'))
    return rows


if __name__ == '__main__':
    E = collect()
    import collections
    c = collections.Counter(e['sec'] for e in E)
    print(len(E), dict(c))

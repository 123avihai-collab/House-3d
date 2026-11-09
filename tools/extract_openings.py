#!/usr/bin/env python3
"""Windows / doors -> data/architecture/openings.json, and the concrete walls cut around them.

Plans    : sources/plumbing/אינסטלציה חתכים הכל.dxf – the architect's Revit plans as blocks 'martef' (basement), 'pituah'
           (ground), 'alef' (first floor). Door / window families on layers A-DOOR / A-GLAZ (name, element id, insertion
           point = centre of the opening on the wall, rotation = wall direction). Each block is placed on the structural DXF
           of its floor (k-11 / k-21 / k-31, same Revit coordinates) by ICP translation on the wall lines -> ITM (stage-2 chain).
Heights  : sources/permit (the permit sheet, tools/cache/permit-sheet1.json): every family instance is exported per view with
           its Revit element id in the block name; in the sections / elevations (חתך א-א, ב-ב, חזית …) the block geometry is in
           cm relative to ±0.00 -> sill / head (union over the views: a parapet can hide the lower part in one view).
           Doors: height from the family name (96_210 -> 2.10). Checked against the U.K / O.K tags of the plans.
Walls    : a concrete wall (k-21 / k-31 / k-11 walls of the model) hosting an opening is cut by the opening rectangle
           (width × wall thickness) and refilled below the sill and above the head (concrete sill / lintel).
Run after tools/extract_floor.py:  python3 tools/extract_openings.py   (then tools/extract_mamad.py – the mamad window / door / sleeves)
"""
import json, math, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezdxf
import numpy as np
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from shapely import affinity
import extract_framing as F

ROOT = F.ROOT; r3 = F.r3
SRC = 'sources/plumbing/אינסטלציה חתכים הכל.dxf'
PERMIT = 'tools/cache/permit-sheet1.json'
PERMIT_SRC = 'sources/permit/permit-sheet1-gramushka.dwg'
FLOORS = {   # block, structural DXF it is placed on, finished floor level (rel), model file with its concrete walls
    'unit': ('martef', F.K11, -2.60, 'framing.json'),
    'ground': ('pituah', F.K21, 0.00, 'floor-ground.json'),
    'first': ('alef', 'sources/structure/k-31.dxf', 3.85, 'floor-first.json'),
}
NAME = re.compile(r'^(.*)-([A-Z]?\d+)-(.+)$')
MAMAD = re.compile(r'ממד|mamad', re.I)
_GREY = {}


def k_grey(floor):
    """grey (SOLID) fill of the structural sheet = concrete that stops at this level – in a mamad window gap: the pocket of
    the sliding blast shutter (K-21: "34" grey next to the "66" opening)"""
    if floor not in _GREY:
        import extract_floor as XF
        if floor == 'ground':     # the grey fills of the K-21 PDF (the DXF has no hatch for the pocket)
            FR = json.load(open(os.path.join(ROOT, 'data/structure/framing.json'), encoding='utf-8'))
            _GREY[floor] = XF.pdf_grey(F.K21P, FR['placement']['K21pdf']['translation_pt'], shades=(0.79, 0.81))
        else:
            _, sheet, to = XF.placement()
            _GREY[floor] = XF.rising_wall_pieces(F.read_dxf(FLOORS[floor][1]), to)[1]
    return _GREY[floor]


def mamad_frame(o, w, ws, c0, ax, nrm, t):
    """mamad window / door (Avihai's edit-mode note ק15): the steel frame is set in the formwork and cast with the walls.
    The Revit family is wider than the hole in the concrete (it includes the frame / the leaf parked beside the opening),
    so the opening is the gap between the walls of the structural sheet along the opening axis – no wall is cut. Below the
    sill / above the head the gap is concrete; between them the cast-in frame (and the shutter pocket, grey in K-21)."""
    U = unary_union([Polygon(x['footprintITM'], x.get('holesITM') or []).buffer(0) for x in ws]).buffer(0.005)
    inside = lambda s: U.contains(Point(*(c0 + ax * s)))
    lim, step = o['width_m'] / 2 + 0.8, 0.005
    free = [s for s in np.arange(-lim, lim, step) if not inside(s)]
    if not free: return
    s0 = min(free, key=abs); a = b = s0
    while a > -lim and not inside(a - step): a -= step
    while b < lim and not inside(b + step): b += step
    a, b = a - 0.005, b + 0.005          # to the wall faces (U is grown by 5 mm)
    rect = lambda a_, b_: Polygon([tuple(c0 + ax * a_ - nrm * t / 2), tuple(c0 + ax * b_ - nrm * t / 2), tuple(c0 + ax * b_ + nrm * t / 2), tuple(c0 + ax * a_ + nrm * t / 2)])
    R = rect(a, b)
    ring = lambda g: [[r3(p), r3(q)] for p, q in g.exterior.coords[:-1]]
    pocket = R.intersection(k_grey(o['floor']).buffer(0.01))
    pocket = max([p for p in getattr(pocket, 'geoms', [pocket]) if p.geom_type == 'Polygon'], key=lambda p: p.area, default=None)
    bot, top = w['bottomRel'], w['topRel']
    fb = o['sillRel'] if o['kind'] != 'door' else bot     # a door frame stands on the slab
    o.update(host=w['id'], hostThickness_m=r3(t), cutITM=ring(R), structuralWidth_m=r3(b - a),
             castFrame={'ringITM': ring(R), 'bottomRel': r3(fb), 'topRel': o['headRel'], 'width_m': r3(b - a),
                        **({'pocketITM': ring(pocket), 'pocketWidth_m': r3(pocket.area / t)} if pocket is not None and pocket.area > 0.01 else {}),
                        'note': ('משקוף פלדה של ' + ('דלת' if o['kind'] == 'door' else 'חלון') + ' הממ"ד – מוצב בתבנית ונוצק עם הקירות. '
                                 f"רוחב הפתח בבטון {b - a:.2f} מ' = הרווח בין הקירות ב-K-21 (משפחת Revit {o['width_m']:.2f} כוללת את המשקוף / הכנף הנגררת)."
                                 + (' הקטע האפור ב-K-21 לצד הפתח = כיס תריס ההדף.' if pocket is not None and pocket.area > 0.01 else '')
                                 + ' פרופיל המשקוף – לפי תוכנית הג"א (חסרה); בתצוגה – קבוע תצוגה.')})
    if o['kind'] == 'door':     # sliding blast door: the leaf parks beside the opening – a continuous wall, no services (note 10)
        leaf = b - a        # the leaf covers the opening: it parks on a wall stretch at least as long, on one side
        Uw = unary_union([Polygon(x['footprintITM'], x.get('holesITM') or []).buffer(0) for x in ws]).buffer(0.01)
        sides = [(a - leaf, a), (b, b + leaf)]
        okS = [bool(rect(*sd).buffer(-0.02).within(Uw)) for sd in sides]
        k = okS.index(True) if any(okS) else 0
        PZ = rect(*sides[k])
        o['castFrame'].update(leafParkITM=ring(PZ), leafPark_m=r3(leaf), leafParkWallOk=okS[k], leafParkSides=okS,
                              leafParkNote='צד החניה של הכנף לפי פרט היצרן (חסר) – מוצג הצד שבו הקיר רציף' if all(okS) else '')
    if o['id'] not in w.setdefault('openings', []): w['openings'].append(o['id'])
    if fb > bot + 0.01: w.setdefault('infill', []).append({'kind': 'sill', 'opening': o['id'], 'ringITM': ring(R), 'bottomRel': bot, 'topRel': r3(min(fb, top))})
    if o['headRel'] < top - 0.01: w.setdefault('infill', []).append({'kind': 'lintel', 'opening': o['id'], 'ringITM': ring(R), 'bottomRel': r3(max(o['headRel'], bot)), 'topRel': top})


def place(msp, block, dxf):
    ins = next(e for e in msp.query('INSERT') if e.dxf.name == block)
    ents = list(ins.virtual_entities())
    A = [(v.dxf.start.x, v.dxf.start.y) for v in ents if v.dxftype() == 'LINE' and v.dxf.layer in ('A-WALL', 'S-STRS', 'S-STRS-MBND')]
    A += [(v.dxf.end.x, v.dxf.end.y) for v in ents if v.dxftype() == 'LINE' and v.dxf.layer in ('A-WALL', 'S-STRS', 'S-STRS-MBND')]
    A = np.unique(np.round(np.array(A), 1), axis=0)
    m = F.read_dxf(dxf); B = []
    for e in m.query('LINE[layer=="IfcWall"]'): B += [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    B = np.unique(np.round(np.array(B), 1), axis=0)
    sc, t, med = F.icp(A, B, tries=100)
    t11 = F.basement['k11ToK400']['translation_pt']
    to_itm = lambda x, y: F.sheet2itm((x + t[0]) * F.S_CM + t11[0], -(y + t[1]) * F.S_CM + t11[1])
    return ents, to_itm, {'translation_cm': [r3(v) for v in t], 'inlierFraction': r3(sc), 'medianResidual_cm': r3(med)}


def view_heights():
    """{element id: {'sill': cm, 'head': cm, 'width': cm, 'views': [...]}} from the section / elevation views of the permit sheet"""
    d = json.load(open(os.path.join(ROOT, PERMIT), encoding='utf-8'))
    B = {b['name']: b for b in d['blocks']}
    out = defaultdict(list)    # element id -> [(sill cm, head cm, width cm, view)]
    fam = defaultdict(list)
    for e in d['entities']:
        if e['type'] != 'INSERT' or e['layer'] not in ('A-GLAZ', 'A-DOOR'): continue
        m = NAME.match(e['name'])
        if not m: continue
        nm, eid, view = m.groups()
        if not any(k in view for k in ('חזית', 'חתך')): continue
        y0 = e['insertionPoint']['y']    # views are drawn at y = 0 (±0.00); a second instance of the same element sits at its offset
        xs, ys = [], []
        for g in B[e['name']]['entities']:
            if g['type'] == 'LINE': xs += [g['startPoint']['x'], g['endPoint']['x']]; ys += [g['startPoint']['y'], g['endPoint']['y']]
            elif g['type'] == 'HATCH':
                for pth in g['boundaryPaths']:
                    for ed in pth.get('edges', []):
                        if 'start' in ed: xs += [ed['start']['x'], ed['end']['x']]; ys += [ed['start']['y'], ed['end']['y']]
        if not ys or max(ys) - min(ys) < 20: continue          # seen edge-on
        rec = (min(ys) + y0, max(ys) + y0, max(xs) - min(xs), view)
        out[eid].append(rec); fam[nm.strip()].append(rec)
    return dict(out), fam


def kind_of(name, layer):
    if layer == 'A-DOOR': return 'door'
    if 'צינור' in name or 'Zinor' in name: return 'vent'
    if 'ויטרינה' in name: return 'vitrine'
    if 'הזזה' in name: return 'sliding'
    return 'window'


def main():
    doc = ezdxf.readfile(os.path.join(ROOT, SRC)); msp = doc.modelspace()
    H, FAM = view_heights()
    openings, placement, sleeves = [], {}, []
    for floor, (blk, dxf, ffl, _) in FLOORS.items():
        ents, to_itm, pl = place(msp, blk, dxf); placement[blk] = pl
        txt = [(v.dxf.insert.x, v.dxf.insert.y, v.plain_text().strip()) for v in ents if v.dxftype() == 'MTEXT' and v.dxf.layer == 'A-GLAZ-IDEN']
        num = lambda x0, y0: next((float(t) for x_, y_, t in txt if re.fullmatch(r'-?\d+', t) and 0 < x_ - x0 < 90 and abs(y_ - y0) < 5), None)
        tagpairs = []   # (x, y, U.K cm, O.K cm): "U.K.=" + value, and "O.K=" + value ~31 cm below
        for x_, y_, t in txt:
            if t.startswith('U.K'):
                ok = next(((x2, y2) for x2, y2, t2 in txt if t2.startswith('O.K') and abs(x2 - x_) < 5 and 20 < y_ - y2 < 45), None)
                if ok and num(x_, y_) is not None and num(*ok) is not None: tagpairs.append((x_, y_, num(x_, y_), num(*ok)))
        for v in ents:
            if v.dxftype() != 'INSERT' or v.dxf.layer not in ('A-DOOR', 'A-GLAZ'): continue
            m = NAME.match(v.dxf.name)
            if not m: continue
            nm, eid, view = m.groups(); nm = nm.strip(); kind = kind_of(nm, v.dxf.layer)
            if kind == 'vent':                                   # mamad ventilation / filter sleeves – cast in the wall (note 10)
                c0v = to_itm(v.dxf.insert.x, v.dxf.insert.y); a2v = to_itm(v.dxf.insert.x + 100 * math.cos(math.radians(v.dxf.rotation)), v.dxf.insert.y + 100 * math.sin(math.radians(v.dxf.rotation)))
                axv = np.subtract(a2v, c0v); axv = axv / np.linalg.norm(axv)
                dm = re.search(r'(?:אורור|Zinor)\s*(\d+)', nm)
                own = [r for r in H.get(eid, []) if ffl - 0.05 <= r[0] / 100 < ffl + 3.30]
                sleeves.append({'floor': floor, 'name': nm, 'revitId': eid, 'centerITM': [r3(c0v[0]), r3(c0v[1])], 'axisITM': [round(axv[0], 6), round(axv[1], 6)],
                                'dia_m': r3(int(dm.group(1)) * 0.0254) if dm else None, 'zRel': r3((min(r[0] for r in own) + max(r[1] for r in own)) / 200) if own else None,
                                'source': f'{SRC} בלוק {blk}, שכבה {v.dxf.layer}, "{nm}" (מזהה {eid})'})
                continue
            x, y = v.dxf.insert.x, v.dxf.insert.y; rot = math.radians(v.dxf.rotation)
            c = to_itm(x, y); a2 = to_itm(x + 100 * math.cos(rot), y + 100 * math.sin(rot))
            ax = ((a2[0] - c[0]) / 1.0, (a2[1] - c[1]) / 1.0); L = math.hypot(*ax); ax = (ax[0] / L, ax[1] / L)
            dims = re.search(r'(\d{2,3})_(\d{3})', nm)
            # plan geometry: an instance drawn as a flat projection (thickness < 10 cm) belongs to another level – skip
            pts = [p for w in v.virtual_entities() if w.dxftype() in ('LINE',) for p in ((w.dxf.start.x, w.dxf.start.y), (w.dxf.end.x, w.dxf.end.y))]
            along = [(p[0] - x) * math.cos(rot) + (p[1] - y) * math.sin(rot) for p in pts]; across = [-(p[0] - x) * math.sin(rot) + (p[1] - y) * math.cos(rot) for p in pts]
            if pts and kind != 'door' and max(across) - min(across) < 10: continue
            band = lambda r: ffl - 0.05 <= r[0] / 100 < ffl + 3.30
            own = [r for r in H.get(eid, []) if band(r)]
            famr = [r for r in FAM.get(nm, []) if band(r)]
            st, note, hsrc = 'source', '', ''
            if own:
                sill, head, width = min(r[0] for r in own) / 100, max(r[1] for r in own) / 100, max(r[2] for r in own) / 100
                hsrc = f"{PERMIT_SRC}: {', '.join(sorted({r[3] for r in own}))} (מזהה {eid})"
            near = min(tagpairs, key=lambda q: math.dist(q[:2], (x, y))) if tagpairs else None
            if own and near and kind == 'vitrine' and near[2] == 0 and sill > ffl + 0.05 and not any('חתך' in r[3] for r in own):
                # seen only in an elevation behind a parapet: the plan tag gives the sill (U.K.=0)
                sill = ffl; note += f' אדן לפי תגית התוכנית "U.K.={near[2]:.0f}" (בחזית החלק התחתון מוסתר במעקה).'
            if own: pass
            elif kind != 'door' and near and math.dist(near[:2], (x, y)) < 600:
                sill, head, width = ffl + near[2] / 100, ffl + near[3] / 100, None
                hsrc = f'תגית התוכנית "U.K.={near[2]:.0f} O.K={near[3]:.0f}" (הקרובה, בלוק {blk})'
            elif kind == 'door' and dims:
                sill, head, width = ffl, ffl + int(dims.group(2)) / 100, int(dims.group(1)) / 100; hsrc = f'שם המשפחה "{dims.group(0)}" (רוחב_גובה)'
            else:
                if famr:
                    sill, head, width = min(r[0] for r in famr) / 100, max(r[1] for r in famr) / 100, max(r[2] for r in famr) / 100
                    hsrc = f'{PERMIT_SRC}: אותה משפחה באותה קומה ("{nm}")'; st = 'approx'; note = 'מזהה Revit שונה בתוכנית – גובה לפי מופע אחר של אותה משפחה באותה קומה.'
                else:
                    sill, head, width = ffl, ffl + 2.10, None; st = 'provisional'; note = 'אין גובה במקורות (לא מופיע בחזיתות/חתכים) – זמני 2.10.'; hsrc = '—'
            if width is None:   # plan width: extent of the family geometry along the wall
                width = (max(along) - min(along)) / 100; note += ' רוחב לפי היקף המשפחה בתוכנית (כולל משקוף / כיס הזזה).'
            openings.append({'id': f'{floor[0].upper()}{len([o for o in openings if o["floor"] == floor]) + 1:02d}', 'floor': floor, 'kind': kind, 'name': nm,
                             'revitId': eid, 'centerITM': [r3(c[0]), r3(c[1])], 'axisITM': [round(ax[0], 6), round(ax[1], 6)], 'width_m': r3(width),
                             'sillRel': r3(sill), 'headRel': r3(head), 'floorFinishRel': ffl, 'UK_cm': round((sill - ffl) * 100), 'OK_cm': round((head - ffl) * 100),
                             'status': st, 'note': note, 'heightSource': hsrc,
                             'source': f'{SRC} בלוק {blk}, שכבה {v.dxf.layer}, "{nm}" (מזהה {eid}); גובה: {hsrc}'})
    # owner changes (data/changes/owner-changes-geometry.json "openings"): the opening stays as drawn; the change is a
    # variant built by tools/extract_blocks.py (button "לפי התוכניות / עם השינוי"), only flagged here
    OCG = json.load(open(os.path.join(ROOT, 'data/changes/owner-changes-geometry.json'), encoding='utf-8'))['changes']
    for oc, g in OCG.items():
        for oid in (g.get('openings') or {}):
            for o in openings:
                if o['id'] == oid: o['ownerChange'] = oc
    # ---- host concrete walls: cut the opening rectangle, refill below the sill / above the head ----
    files = {f: json.load(open(os.path.join(ROOT, 'data/structure', f), encoding='utf-8')) for f in ('framing.json', 'floor-ground.json', 'floor-first.json', 'floor-roof.json')}
    walls = {'unit': files['framing.json']['basementWalls'], 'ground': files['floor-ground.json']['walls'], 'first': files['floor-first.json']['walls'],
             'roof': files['floor-roof.json']['walls']}
    for ws in walls.values():
        for w in ws:
            w.pop('partsITM', None); w.pop('infill', None); w.pop('openings', None)
    stats = defaultdict(int)

    def cut(w, region, o):
        """remove the opening region from wall w, refill it below the sill and above the head (concrete sill / lintel)"""
        g = Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0)
        prev = w.get('partsITM')
        cur = unary_union([Polygon(p['ringITM'], p['holesITM']) for p in prev]) if prev else g
        cur = cur.difference(region.buffer(0.001))
        w['partsITM'] = [{'ringITM': [[r3(a), r3(b)] for a, b in p.exterior.coords[:-1]],
                          'holesITM': [[[r3(a), r3(b)] for a, b in i.coords[:-1]] for i in p.interiors]}
                         for p in getattr(cur, 'geoms', [cur]) if p.area > 0.002]
        if o['id'] not in w.setdefault('openings', []): w['openings'].append(o['id'])
        bot, top = w['bottomRel'], w['topRel']
        for q in [x for x in getattr(region, 'geoms', [region]) if x.geom_type == 'Polygon' and x.area > 0.002]:
            ring = [[r3(a), r3(b)] for a, b in q.exterior.coords[:-1]]
            if o['sillRel'] > bot + 0.01 and o['kind'] != 'door': w.setdefault('infill', []).append({'kind': 'sill', 'opening': o['id'], 'ringITM': ring, 'bottomRel': bot, 'topRel': min(o['sillRel'], top)})
            if o['headRel'] < top - 0.01: w.setdefault('infill', []).append({'kind': 'lintel', 'opening': o['id'], 'ringITM': ring, 'bottomRel': max(o['headRel'], bot), 'topRel': top})
    OVR = json.load(open(os.path.join(ROOT, 'tools/opening-overrides.json'), encoding='utf-8'))
    for o in openings:
        c = Point(o['centerITM']); ax = np.array(o['axisITM']); nrm = np.array([-ax[1], ax[0]])
        if o['id'] in OVR and OVR[o['id']].get('host', '') is None:
            o['host'] = None; o['note'] = (o.get('note', '') + ' ' + OVR[o['id']]['reason']).strip(); o['hostOverride'] = 'tools/opening-overrides.json'
            stats['noConcrete'] += 1; continue
        best = None
        for w in walls[o['floor']]:
            g = Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0)
            if g.distance(c) > 0.6: continue
            # a straight wall piece must run along the opening: G07 (a door in a 10 cm partition) was hosted by GW3, which is
            # perpendicular to it – the lintel floated (Avihai's note 9)
            mr = g.minimum_rotated_rectangle; xy = list(mr.exterior.coords)
            e1, e2 = np.subtract(xy[1], xy[0]), np.subtract(xy[2], xy[1]); long_ = e1 if np.linalg.norm(e1) >= np.linalg.norm(e2) else e2
            straight = g.area > 0.7 * mr.area and np.linalg.norm(long_) > 2.5 * min(np.linalg.norm(e1), np.linalg.norm(e2))
            if straight and abs(float(np.dot(long_ / np.linalg.norm(long_), ax))) < 0.7: continue
            probe = LineString([tuple(np.array(c.coords[0]) - nrm * 0.6), tuple(np.array(c.coords[0]) + nrm * 0.6)])
            # wall thickness across the opening: the wall's cut by the normal line through the centre, or next to it along the axis
            for sh in (0.0, -o['width_m'] / 2 - 0.15, o['width_m'] / 2 + 0.15):
                pr = affinity.translate(probe, *(ax * sh)); seg = pr.intersection(g)
                parts = [q for q in getattr(seg, 'geoms', [seg]) if not q.is_empty and q.length > 0.08]
                if parts:
                    seg = min(parts, key=lambda q: q.distance(Point(pr.interpolate(0.5, normalized=True))))
                    t = seg.length
                    if t > 0.45: continue               # running along a wall end / corner – not a cut through the wall
                    mid = seg.interpolate(0.5, normalized=True)
                    off = (np.array(mid.coords[0]) - np.array(pr.interpolate(0.5, normalized=True).coords[0])) @ nrm
                    cand = (abs(sh), w, t, off)
                    if best is None or cand[0] < best[0] or (cand[0] == best[0] and t > best[2]): best = cand
                    break
        if not best:
            o['host'] = None; stats['noConcrete'] += 1; continue
        _, w, t, off = best
        c0 = np.array(c.coords[0]) + nrm * off; hw = o['width_m'] / 2
        if MAMAD.search(o['name']):
            mamad_frame(o, w, walls[o['floor']], c0, ax, nrm, t); stats['mamadFrame'] += 1; continue
        R = Polygon([tuple(c0 - ax * hw - nrm * t / 2), tuple(c0 + ax * hw - nrm * t / 2), tuple(c0 + ax * hw + nrm * t / 2), tuple(c0 - ax * hw + nrm * t / 2)])
        g = Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0)
        both_sides = g.intersects(affinity.translate(R, *(ax * (hw + 0.1)))) and g.intersects(affinity.translate(R, *(-ax * (hw + 0.1))))
        covered = R.intersection(g).area / R.area
        if covered < 0.5 and not both_sides:
            # concrete on the far end of the opening too (along its axis), else the opening is in a non-concrete wall: no
            # concrete sill / lintel – it is built with the block walls (G07: a door in a 10 cm partition next to GW21 /
            # GW17 / GW3, its lintel floated – Avihai's note 9)
            ends = [affinity.translate(R, *(ax * (hw + 0.1))), affinity.translate(R, *(-ax * (hw + 0.1)))]
            hit = lambda Q: [x['id'] for x in walls[o['floor']] if Polygon(x['footprintITM'], x.get('holesITM') or []).buffer(0).intersects(Q)]
            if not (hit(ends[0]) and hit(ends[1])):
                o['host'] = None; o['note'] = (o.get('note', '') + ' הפתח בקיר שאינו בטון (מחיצה / בלוקים) – בלי אדן / משקוף בטון בשלד; נבנה עם קירות הבלוקים.').strip()
                stats['noConcrete'] += 1; continue
        if covered < 0.5 and both_sides:
            # an opening in the gap between two concrete wall ends: the sill / lintel spans the whole gap, wall face to wall
            # face (G07 – the lintel hung 4–8 cm short of GW21 / GW17, Avihai's note 9)
            U = unary_union([Polygon(x['footprintITM'], x.get('holesITM') or []).buffer(0) for x in walls[o['floor']]]).buffer(0.005)
            inside = lambda s_: U.contains(Point(*(c0 + ax * s_)))
            st, lim = 0.005, hw + 0.4
            if not inside(0):
                a_ = b_ = 0.0
                while a_ > -lim and not inside(a_ - st): a_ -= st
                while b_ < lim and not inside(b_ + st): b_ += st
                if a_ > -lim and b_ < lim:
                    a_, b_ = a_ - 0.005, b_ + 0.005
                    R = Polygon([tuple(c0 + ax * a_ - nrm * t / 2), tuple(c0 + ax * b_ - nrm * t / 2), tuple(c0 + ax * b_ + nrm * t / 2), tuple(c0 + ax * a_ + nrm * t / 2)])
                    o['structuralWidth_m'] = r3(b_ - a_)
                    o['note'] = (o.get('note', '') + f" הפתח בין שני קירות בטון ({b_ - a_:.2f} מ' מפאה לפאה): האדן / המשקוף מעל הדלת – בטון עם הקירות; אין במקורות פרט בטון / בלוקים מעל הדלת.").strip()
        o['host'] = w['id']; o['hostThickness_m'] = r3(t); o['cutITM'] = [[r3(a), r3(b)] for a, b in R.exterior.coords[:-1]]
        cut(w, R, o)
        stats['hosted'] += 1; stats['cutContinuous' if covered >= 0.5 else 'filledGap'] += 1
    # every other concrete wall (any floor) standing in the opening volume is cut as well (e.g. a wall continuing past a door)
    for o in openings:
        if o.get('castFrame'): continue          # mamad: the structural opening of K-21, no wall is cut
        c = np.array(o['centerITM']); ax = np.array(o['axisITM']); nrm = np.array([-ax[1], ax[0]]); hw = o['width_m'] / 2
        R0 = Polygon([tuple(c - ax * hw - nrm * 0.4), tuple(c + ax * hw - nrm * 0.4), tuple(c + ax * hw + nrm * 0.4), tuple(c - ax * hw + nrm * 0.4)])
        for fl, ws in walls.items():
            for w in ws:
                if w['topRel'] <= o['sillRel'] + 0.02 or w['bottomRel'] >= o['headRel'] - 0.02: continue
                g = Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0)
                reg = g.intersection(R0)
                if reg.area > 0.005:
                    # a wall that only touches the jamb (its end inside the cut box by a few cm) is not cut: that left a notch
                    # the height of the window in W6 / FW2 / FW10 / GW19 (Avihai's note 16)
                    ext = [float(np.dot(np.subtract(q, c), ax)) for q in (reg.exterior.coords if reg.geom_type == 'Polygon' else
                                                                         [pt for gg in reg.geoms for pt in gg.exterior.coords])]
                    if max(ext) - min(ext) < 0.10: stats['jambTouch'] += 1; continue
                    cut(w, reg, o); o.setdefault('alsoCut', []).append(w['id']); stats['extraCut'] += 1
    for f, d in files.items():
        json.dump(d, open(os.path.join(ROOT, 'data/structure', f), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # sleeves: one per position (the same family appears in two views), hosted by the nearest concrete wall
    uniq = []
    for sv in sleeves:
        # same position again: the second view of the family, or a lower floor's sleeve seen from above in the upper view
        # (alef "Dependent 1" shows the ground-floor mamad sleeve – it was listed as a first-floor sleeve S05)
        if any(math.dist(u['centerITM'], sv['centerITM']) < 0.05 for u in uniq): continue
        P0 = Point(sv['centerITM']); best = min(((Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0).distance(P0), w) for w in walls[sv['floor']]), key=lambda t: t[0], default=(9, None))
        if best[0] > 0.35: continue
        w = best[1]; sv.update(id=f"S{len(uniq) + 1:02d}", host=w['id'], hostThickness_m=w.get('thickness_m'), mamad=bool(w.get('mamad')),
                               status='source' if sv['zRel'] is not None and sv['dia_m'] else 'provisional',
                               note=('גובה לפי חזיתות / חתכים' if sv['zRel'] is not None else 'אין גובה במקורות – מוצג זמני') + ('; קוטר מהשם (אינץ\')' if sv['dia_m'] else '; קוטר לא ידוע'))
        uniq.append(sv)
    out = {'_doc': 'Windows and doors. Generated by tools/extract_openings.py – do not edit by hand. Levels relative to ±0.00 (finished floors: basement −2.60, ground 0.00, first +3.85).',
           'placement': placement, 'openings': openings, 'sleeves': uniq}
    os.makedirs(os.path.join(ROOT, 'data/architecture'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'data/architecture/openings.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('placement', placement)
    for o in openings:
        print(o['id'], o['kind'], o['name'][:38], o['revitId'], 'w', o['width_m'], 'UK/OK', o['UK_cm'], o['OK_cm'], o['status'], 'host', o.get('host'), o.get('hostThickness_m'))
    print(dict(stats))


if __name__ == '__main__':
    main()

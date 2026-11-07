#!/usr/bin/env python3
"""PL3 (decided 07.11 by recommendation): first-floor sewer branches have no room in the 15 cm build-up (+3.70 -> +3.85).
  - WC branches (ø110, not over the ממ"ד): straight down through the slab at the WC, hung under the slab FS1 (consultant's
    detail "עטיפת בטון", H<40) at 2% to the moved stack -> lowered ceiling in the ground floor along the route
  - ø50 branches (basins, floor drains – over the ממ"ד, which must not be penetrated or used for pipes): stay in the
    build-up and join the WC drop with a wye just above the slab; levels re-derived from there at 2%
Output: dict for proposal.json["firstFloor"] (called from propose.py with the moved stacks).
"""
import math, os, sys
from shapely.geometry import LineString, Point, Polygon
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_common import J, H0, FG, MAMAD, beam_poly

r3 = lambda v: round(float(v), 3)


def build(stack_moves):
    N = J('data/plumbing/network.json'); C = J('data/plumbing/catalog.json'); I = J('tools/plumbing/proposal-inputs.json')['firstFloor']
    by = {n['id']: n for n in N['nodes']}
    FS = next(s for s in FG['ceiling']['slab'] if s['id'] == 'FS1')
    top, under, finish = H0 + FS['topRel'], H0 + FS['topRel'] - FS['thickness_m'], H0 + 3.85
    OD = lambda r: C['pipes'][r.get('material') or 'HDPE']['sizes'][str(r['D_mm'])]['OD']
    runs = [r for r in N['runs'] if r['drawnOn'] == 'first' and r['system'] == 'sewage' and r['id'] not in I['keep']]
    moved = {str(s['stack']): s for s in stack_moves if s.get('pts3d')}
    beams = [(b['id'], beam_poly(b), H0 + b['bottomRel']) for b in FG['ceiling']['beams'] if b.get('axisITM')]
    out = {'runs': [], 'drops': [], 'sleeves': [], 'superseded': [], 'checks': [], 'replacesConnectors': []}
    s = I['slope']
    # 1. WC branches under the slab
    wc_level = {}
    for r in [r for r in runs if r['D_mm'] == 110 and by[r['from']]['kind'] == 'wc' and r['to'].startswith('ST')]:
        wc = by[r['from']]; st = r['to'].split('@')[0][2:]; mv = moved.get(st)
        end = (mv['pts3d'][0][0], mv['pts3d'][0][1]) if mv else tuple(r['pts'][-1])
        p2 = [tuple(r['pts'][0])] + [tuple(p) for p in r['pts'][1:-1]] + [end]
        L = sum(math.dist(p2[i], p2[i + 1]) for i in range(len(p2) - 1)); d = OD(r)
        il_up = under - I['hangerGap_m'] - d; il_dn = il_up - s * L
        over = LineString(p2).intersection(MAMAD).length
        acc, pts3d = 0.0, [[r3(wc['E']), r3(wc['N']), r3(finish)], [r3(wc['E']), r3(wc['N']), r3(il_up + d / 2)]]
        for i in range(1, len(p2)):
            acc += math.dist(p2[i - 1], p2[i]); pts3d.append([r3(p2[i][0]), r3(p2[i][1]), r3(il_up - s * acc + d / 2)])
        crossed = []
        for bid, P, bot in beams:
            x = LineString(p2).intersection(P)
            if not x.is_empty and x.length > 0.02 and bot < il_up + d + 0.01:
                crossed.append(bid)
                out['sleeves'].append({'pipe': f'PL3-{r["id"]}', 'floor': 'first', 'at': [r3(x.centroid.x), r3(x.centroid.y), r3(il_up - s * LineString(p2).project(x.centroid) + d / 2)],
                                       'through': f'קורת תקרה {bid}', 'sleeve': 'שרוול PVC ø160 יצוק בקורה (תיאום קונסטרוקטור)', 'sleeveD_mm': 160, 'material': 'PVC', 'axis': 'h'})
        ceiling = under - (il_dn - I['hangerBelow_m'])
        out['runs'].append({'id': f'PL3-{r["id"]}', 'replaces': r['id'], 'system': 'sewage', 'D_mm': r['D_mm'], 'material': r.get('material', 'HDPE'), 'pts3d': pts3d,
                            'from': r['from'], 'to': r['to'], 'ILup': r3(il_up), 'ILdown': r3(il_dn), 'slope': s, 'length_m': r3(L), 'floor': 'first',
                            'droppedCeiling_m': r3(ceiling), 'overMamad_m': r3(over), 'beams': crossed, 'status': 'proposal',
                            'note': f'יורד דרך התקרה באסלה ונתלה מתחתיה (פרט "עטיפת בטון" של היועץ, H<40) בשיפוע {s * 100:.0f}% אל הקולטן; '
                                    f'בקומת הקרקע נדרשת תקרה מונמכת של כ-{ceiling * 100:.0f} ס"מ לאורך התוואי' + (f'; חוצה את קורות התקרה {", ".join(crossed)} – שרוול יצוק' if crossed else '')})
        out['drops'].append({'id': f'DROP-{wc["id"]}', 'E': r3(wc['E']), 'N': r3(wc['N']), 'top': r3(finish), 'bottom': r3(il_up + d / 2), 'D_mm': r['D_mm']})
        out['sleeves'].append({'pipe': f'PL3-{r["id"]}', 'floor': 'first', 'at': [r3(wc['E']), r3(wc['N']), r3(top - FS['thickness_m'] / 2)], 'through': 'תקרה FS1 (+3.70)',
                               'sleeve': 'שרוול PVC ø160 יצוק / קידוח + צווארון אש (מעבר בין קומות)', 'sleeveD_mm': 160, 'material': 'PVC', 'axis': 'v'})
        wc_level[wc['id']] = top + I['wyeAboveSlab_m']
        out['superseded'].append(r['id']); out['replacesConnectors'].append(r['id'])
    # 2. ø50 branches in the build-up, re-levelled upstream from the wye on the WC drop
    level = dict(wc_level); todo = [r for r in runs if r['D_mm'] == 50]
    for _ in range(len(todo) + 2):
        for r in todo:
            if r['to'] in level and r['id'] not in out['superseded']:
                L = r['length_m']; dn = level[r['to']]; up = dn + s * L
                level[r['from']] = max(level.get(r['from'], up), up); d = OD(r)
                P = r['pts']; acc = 0.0; pts3d = [[r3(P[0][0]), r3(P[0][1]), r3(up + d / 2)]]
                for i in range(1, len(P)):
                    acc += math.dist(P[i - 1], P[i]); pts3d.append([r3(P[i][0]), r3(P[i][1]), r3(up - s * acc + d / 2)])
                if r['to'] in wc_level: pts3d[-1][2] = r3(dn + d / 2)
                crown = up + d
                out['runs'].append({'id': f'PL3-{r["id"]}', 'replaces': r['id'], 'system': 'sewage', 'D_mm': r['D_mm'], 'material': r.get('material', 'HDPE'), 'pts3d': pts3d,
                                    'from': r['from'], 'to': r['to'], 'ILup': r3(up), 'ILdown': r3(dn), 'slope': s, 'length_m': r3(L), 'floor': 'first',
                                    'crown': r3(crown), 'coverToFinish_m': r3(finish - crown), 'overMamad_m': r3(LineString(P).intersection(MAMAD).length), 'status': 'proposal',
                                    'note': f'במילוי הרצפה (מעל הממ"ד – בלי חדירה לתקרתו); כיסוי מעל הצינור עד הריצוף {(finish - crown) * 100:.0f} ס"מ'})
                out['superseded'].append(r['id'])
    worst = min((x for x in out['runs'] if x['D_mm'] == 50), key=lambda x: x['coverToFinish_m'], default=None)
    if worst:
        ok = worst['coverToFinish_m'] >= I['minCover_m']
        out['checks'].append({'what': 'כיסוי מעל צינורות ø50 במילוי', 'value_m': worst['coverToFinish_m'], 'min_m': I['minCover_m'], 'ok': ok, 'run': worst['id'],
                              'text': f'הכיסוי הקטן ביותר {worst["coverToFinish_m"] * 100:.0f} ס"מ ({worst["id"]}); נדרש ≥{I["minCover_m"] * 100:.0f} ס"מ לטיט ולאריחים' + ('' if ok else ' – לא מספיק')})
    for x in out['runs']:
        if x['D_mm'] == 110:
            out['checks'].append({'what': f'{x["id"]} – לא מעל הממ"ד', 'value_m': x['overMamad_m'], 'ok': x['overMamad_m'] < 0.01, 'text': f'אורך מעל הממ"ד {x["overMamad_m"]:.2f} מ\''})
    return out

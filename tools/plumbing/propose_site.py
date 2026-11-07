#!/usr/bin/env python3
"""Plumbing layer – SITE proposals (for Avihai's approval, then the consultant's). Items that do not depend on the
open decisions PB6 / PD1 / PL3:
  chamberRaise – S-2, S-3: cover raised to the finished level (adjustment rings), finished level = nearest spot level of
                 the architect's background in the plumbing plan, on the same slab / yard (provisional)
  drops        – external drop (tee + vertical + 2×45° + lower inlet) for every inlet that enters a private chamber more
                 than minDrop above its invert (S-1: SW5, SW6, SW7)
  hoseReel     – feed for the fire hose reel per the consultant's detail "עמדת כיבוי אש" (1" ball valve, 1" double check
                 valve, 3/4" reel with 30 m hose), reel slid along the boundary wall off chamber S-2
  meter        – short connection pieces municipal stub (UT-W) -> meter inlet riser, meter outlet riser -> start of the
                 consultant's main line (WJ7), meter assembly per the consultant's detail
Rain water is NOT routed: the soak pit conflicts with the soil report (11.6, 11.7) – decision PR1 (Avihai).
Run standalone (updates the "site" key of data/plumbing/proposal.json) or from propose.py.
"""
import json, math, os, sys
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import nearest_points
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proposal_common import J, ROOT, H0, FG
import georef as G

r3 = lambda v: round(float(v), 3)
UTW = (179586.361, 576235.702)
UTW_SRC = 'sources/survey/INDEX_F02628-36-MIG-5187.dwg – שכבה UT-W (קצה הכנת המים של התאגיד, מפה למשתכן)'


def unit(v):
    L = math.hypot(*v) or 1.0
    return (v[0] / L, v[1] / L)


def chamber_stack(C, D_m, IL, TL):
    """Same composition rule as the viewer (src/plumbing/index.js buildChamber)."""
    K = C['chambers']
    base_top = IL - 0.10
    avail = TL - K['frame']['height_m'] - K['topSlabThickness_m'] - base_top
    rings, s = [], 0.0
    for h in K['ringHeights_m']:
        while s + h <= avail + 1e-6:
            rings.append(h); s += h
    rest = avail - s; adj = []
    for a in sorted(K['adjustRings_m'], reverse=True):
        while rest >= a - 1e-6:
            adj.append(a); rest -= a
    return {'rings_m': rings, 'adjust_m': adj, 'mortar_m': r3(max(rest, 0.0))}


def build():
    N = J('data/plumbing/network.json'); R = J('tools/plumbing/cache/raw.json'); C = J('data/plumbing/catalog.json')
    S = J('tools/plumbing/proposal-inputs.json')['site']
    lot = Polygon(J('data/site/plot-5187.json')['ring']); B = lot.exterior
    byid = {n['id']: n for n in N['nodes']}
    slabs = {s['id']: (Polygon(s['footprintITM']).buffer(0), s['topRel']) for s in FG['slab']}
    slab_at = lambda p: next((k for k, (P, t) in slabs.items() if P.contains(Point(p))), None)
    out = {'chamberRaise': [], 'drops': [], 'runs': [], 'sleeves': [], 'superseded': [], 'pending': S['pending']}

    # ---------------------------------------------------------- 1. cover at finished level (S-2, S-3)
    CR = S['chamberRaise']
    for cid in CR['ids']:
        n = byid[cid]; sl = slab_at((n['E'], n['N']))
        fin = G.finish_level(R['spots'], lot, n['E'], n['N'])
        TL = fin['H']
        before, after = chamber_stack(C, n['D_m'], n['IL'], n['TL']), chamber_stack(C, n['D_m'], n['IL'], TL)
        spots = ', '.join(f'{h:.2f} ({d:.1f} מ\')' for h, d in fin['spots'])
        out['chamberRaise'].append({
            'id': cid, 'D_m': n['D_m'], 'IL': n['IL'], 'TLfrom': n['TL'], 'TLto': r3(TL), 'delta_m': r3(TL - n['TL']), 'depthTo_m': r3(TL - n['IL']),
            'finish': fin, 'slab': sl, 'slabTop': r3(H0 + slabs[sl][1]) if sl else None,
            'before': before, 'after': after, 'status': 'proposal', 'levelStatus': 'provisional',
            'why': f'T.L של היועץ {n["TL"]:.2f}. מפלסי הפיתוח ברקע התוכנית ליד השוחה: {spots} → מוערך {TL:.2f} (טווח {fin["lo"]:.2f}–{fin["hi"]:.2f}). '
                   f'המכסה יוגבה בכ-{(TL - n["TL"]) * 100:.0f} ס"מ בטבעות הגבהה מתחת למסגרת, והגובה הסופי ייקבע לפי הריצוף בפועל (לכן טבעות ולא חוליה). '
                   'מפלסי הכניסות והיציאה לא משתנים. ' + (f'השוחה בתוך התקרה התלויה {sl} – ראו ממצא "בתוך התקרה התלויה". ' if sl else '')
                   + 'מפלס הפיתוח – לאמת מול תוכנית הפיתוח (טרם עובדה במודל).'})
        out['superseded'].append(cid)

    # ---------------------------------------------------------- 2. external drops
    DR = S['drops']
    for r in N['runs']:
        c = byid.get(r['to'])
        if not c or c['kind'] != 'sewerChamber' or r.get('ILdown') is None or r['ILdown'] - c['IL'] <= DR['minDrop_m']: continue
        mat = r.get('material') or 'HDPE'; OD = C['pipes'][mat]['sizes'][str(r['D_mm'])]['OD']
        w = C['chambers']['rings'][str(c['D_m'])]['wall']; rIn = c['D_m'] / 2; rOut = rIn + w
        p_prev = r['pts'][-2]; u = unit((p_prev[0] - c['E'], p_prev[1] - c['N']))     # from the chamber centre outwards
        dv = rOut + DR['wallGap_m'] + OD / 2
        outlet = next(x for x in N['runs'] if x['from'] == c['id'])
        OD_out = C['pipes'][outlet['material']]['sizes'][str(outlet['D_mm'])]['OD']
        IL_low = c['IL'] + max(0.0, OD_out - OD)                                            # crowns aligned with the outlet
        at = lambda d, H: [r3(c['E'] + u[0] * d), r3(c['N'] + u[1] * d), r3(H)]
        tee, bottom, inlet = at(dv, r['ILdown'] + OD / 2), at(dv, IL_low + OD / 2), at(rIn - 0.02, IL_low + OD / 2)
        out['drops'].append({
            'id': f'DROP-{r["id"]}', 'chamber': c['id'], 'run': r['id'], 'D_mm': r['D_mm'], 'material': mat, 'ILin': r['ILdown'], 'ILchamber': c['IL'],
            'ILlowInlet': r3(IL_low), 'drop_m': r3(r['ILdown'] - IL_low), 'dir': [r3(u[0]), r3(u[1])], 'axisDist_m': r3(dv),
            'pts3d': [tee, bottom, inlet], 'plugAt': at(rIn - 0.02, r['ILdown'] + OD / 2), 'wallAt': at(rIn + w / 2, IL_low + OD / 2),
            'encasement': {'from': at(rOut, IL_low - DR['encasement_m']), 'to': at(dv + OD / 2 + DR['encasement_m'], r['ILdown'] + OD + DR['encasement_m']),
                           'width_m': r3(OD + 2 * DR['encasement_m'])},
            'levelStatus': r.get('levelStatus', 'source'), 'status': 'proposal',
            'why': f'{r["id"]} נכנס ל-{c["id"]} ב-{r["ILdown"]:.2f} והתחתית ב-{c["IL"]:.2f} – מפל חופשי של {r["ILdown"] - c["IL"]:.2f} מ\' בתוך השוחה '
                   f'(שחיקת הבסיס והתיעול, התזה, קשה לתחזוקה). מפל חיצוני: הסתעפות מחוץ לשוחה, צינור אנכי בעטיפת בטון, 2×45° וכניסה בתחתית '
                   f'ב-I.L {IL_low:.2f}' + (' (קודקודים בקו אחד עם היציאה ø' + str(outlet['D_mm']) + ')' if IL_low > c['IL'] else '') +
                   '. ההמשך הישר נכנס לשוחה במפלס המקורי ונסגר בפקק ביקורת. פתח נוסף בחוליה התחתונה (קידוח יהלום + אטם שוחה).'})
    # spacing between drops at the same chamber
    for a in out['drops']:
        for b in out['drops']:
            if a['id'] < b['id'] and a['chamber'] == b['chamber']:
                gap = math.dist(a['pts3d'][0][:2], b['pts3d'][0][:2]) - (a['D_mm'] + b['D_mm']) / 2000
                if gap < 0.25:
                    for x in (a, b): x['sharedEncasementWith'] = (b if x is a else a)['id']
                    a['note'] = b['note'] = f'המפלים של {a["run"]} ו-{b["run"]} במרחק נטו {gap * 100:.0f} ס"מ – עטיפת בטון משותפת'

    # ---------------------------------------------------------- 3. fire hose reel
    HR = S['hoseReel']; hr = Point(R['hoseReel'])
    q = nearest_points(B, hr)[0]
    segs = list(zip(B.coords[:-1], B.coords[1:]))
    a_, b_ = min(segs, key=lambda s: LineString(s).distance(q))
    t = unit((b_[0] - a_[0], b_[1] - a_[1])); inw = unit((hr.x - q.x, hr.y - q.y))
    if lot.contains(Point(q.x + inw[0] * 0.05, q.y + inw[1] * 0.05)) is False: inw = (-inw[0], -inw[1])
    s2 = byid[HR['avoid']]; rOut2 = s2['D_m'] / 2 + C['chambers']['rings'][str(s2['D_m'])]['wall']
    sewer = [LineString(x['pts']) for x in N['runs'] if x['system'] in ('sewage', 'pumped') and x['drawnOn'] in ('ground', 'site')]
    cold = [x for x in N['runs'] if x['system'] == 'cold' and x['drawnOn'] in ('ground', 'site')]
    chambers = [Point(x['E'], x['N']).buffer(x['D_m'] / 2 + C['chambers']['rings'][str(x['D_m'])]['wall']) for x in N['nodes'] if x['kind'] in ('sewerChamber', 'pumpChamber')]
    best = None
    for k in range(0, 80):
        for sg in (1, -1):
            s = sg * k * 0.05
            p = (q.x + t[0] * s + inw[0] * HR['wallOffset_m'], q.y + t[1] * s + inw[1] * HR['wallOffset_m'])
            P = Point(p)
            if not lot.contains(P): continue
            if any(ch.distance(P) < HR['minClear_m'] for ch in chambers): continue
            if any(L.distance(P) < HR['minClear_m'] for L in sewer): continue
            tee = min(((LineString(x['pts']).distance(P), x) for x in cold), key=lambda z: z[0])
            if best is None or tee[0] < best[0] - 1e-9: best = (tee[0], s, p, tee[1])
        if best: break
    dfeed, shift, rp, main = best
    tp = nearest_points(LineString(main['pts']), Point(rp))[0]
    feed2d = [[r3(tp.x), r3(tp.y)], [r3(rp[0]), r3(rp[1])]]
    crosses = [x['id'] for x in N['runs'] if x['system'] in ('sewage', 'pumped') and x['drawnOn'] in ('ground', 'site') and LineString(x['pts']).intersects(LineString(feed2d))]
    sl = slab_at(rp)
    out['hoseReel'] = {
        'id': 'HOSE-REEL', 'E': r3(rp[0]), 'N': r3(rp[1]), 'wall': [r3(-inw[0]), r3(-inw[1])], 'along': [r3(t[0]), r3(t[1])],
        'from': [r3(hr.x), r3(hr.y)], 'shift_m': r3(abs(shift)), 'valveH_m': HR['valveH_m'], 'reelH_m': HR['reelH_m'], 'D_mm': HR['D_mm'],
        'slab': sl, 'tee': {'run': main['id'], 'E': r3(tp.x), 'N': r3(tp.y), 'runD_mm': main.get('D_mm')}, 'crossesSewer': crosses,
        'components': HR['components'], 'status': 'proposal', 'heightStatus': 'provisional',
        'why': f'בתוכנית: הערה "גלגלון 3/4\'\' … אל חוזר כפול" עם חץ לנקודה {hr.distance(Point(s2["E"], s2["N"])):.2f} מ\' ממרכז שוחה {s2["id"]} '
               f'(רדיוס חיצוני {rOut2:.2f}) – העולה והארון היו נופלים על השוחה. הגלגלון הוזז {abs(shift) * 100:.0f} ס"מ לאורך החומה. '
               f'ההזנה: הסתעפות T מהקו הראשי {main["id"]} (ø{main.get("D_mm")}) לפני הברז הראשי של הבית – כך שסגירת הבית לא מנתקת את הכיבוי. '
               'הרכב לפי "פרט עקרוני עמדת כיבוי אש" של היועץ.'}
    out['runs'].append({'id': 'FEED-HOSE', 'system': 'cold', 'floor': 'site', 'D_mm': HR['D_mm'], 'material': 'PEX', 'conduitD_mm': None,
                        'pts3d': [[*feed2d[0], None], [*feed2d[1], None]], 'cover_m': HR['cover_m'],
                        'riserTo_m': HR['valveH_m'], 'from': main['id'], 'to': 'HOSE-REEL', 'status': 'proposal',
                        'length_m': r3(math.dist(feed2d[0], feed2d[1]) + HR['cover_m'] + HR['valveH_m']),
                        'note': f'PEX ø{HR["D_mm"]} (1" לפי הפרט) בעומק הקו הראשי, עלייה ליד החומה' + (f'; חוצה בתוכנית את {", ".join(crosses)} (מעל הביוב)' if crosses else '')})
    if sl:
        out['sleeves'].append({'pipe': 'FEED-HOSE', 'floor': 'site', 'at': [r3(rp[0]), r3(rp[1]), r3(H0 + slabs[sl][1])], 'through': f'תקרה תלויה {sl}',
                               'sleeve': f'שרוול PVC ø50 יצוק בתקרה {sl} (תיאום קונסטרוקטור)', 'sleeveD_mm': 50, 'material': 'PVC'})

    # ---------------------------------------------------------- 4. meter connection
    MT = S['meter']; wm, wj = byid['WM@site'], byid['WJ7@ground']
    u = unit((wj['E'] - UTW[0], wj['N'] - UTW[1])); half = C['fixtures']['waterMeter']['assemblyLen_m'] / 2
    rin = (wm['E'] - u[0] * half, wm['N'] - u[1] * half); rout = (wm['E'] + u[0] * half, wm['N'] + u[1] * half)
    out['meter'] = {'id': 'WM@site', 'axis': [r3(u[0]), r3(u[1])], 'inletRiser': [r3(rin[0]), r3(rin[1])], 'outletRiser': [r3(rout[0]), r3(rout[1])],
                    'utw': [r3(UTW[0]), r3(UTW[1])], 'utwSource': UTW_SRC, 'utwToBoundary_m': r3(B.distance(Point(UTW))), 'status': 'proposal'}
    for rid, a, b, D, frm, to, note in (
            ('CONN-UTW', UTW, rin, 32, 'UT-W', 'WM@site', 'קצה הכנת התאגיד (UT-W) → רגל עולה הכניסה של מערכת המדידה. קוטר וחומר הקטע העירוני – לפי התאגיד; כאן ø32 לתצוגה'),
            ('CONN-WJ7', rout, (wj['E'], wj['N']), 32, 'WM@site', 'WJ7@ground', 'רגל יציאה ממערכת המדידה (PEX ø32 לפי הפרט) → תחילת הקו הראשי של היועץ (WJ7)')):
        out['runs'].append({'id': rid, 'system': 'cold', 'floor': 'site', 'D_mm': D, 'material': 'PEX', 'conduitD_mm': None,
                            'pts3d': [[r3(a[0]), r3(a[1]), None], [r3(b[0]), r3(b[1]), None]], 'cover_m': MT['cover_m'], 'from': frm, 'to': to,
                            'length_m': r3(math.dist(a, b)), 'status': 'proposal', 'note': note})
    out['meter']['why'] = (f'קצה ההכנה (UT-W) {B.distance(Point(UTW)):.2f} מ\' בתוך המגרש, מרכז המערכת של היועץ {math.dist(UTW, (wm["E"], wm["N"])):.2f} מ\' ממנו '
                           f'ותחילת הקו (WJ7) {math.dist(UTW, (wj["E"], wj["N"])):.2f} מ\' ממנו – כמעט בקו אחד. המערכת (אורך {2 * half:.2f} מ\' בין העולים, לפי הפרט) '
                           f'מוצבת על הקו הזה, והקטעים המחברים הם {math.dist(UTW, rin) * 100:.0f} ו-{math.dist(rout, (wj["E"], wj["N"])) * 100:.0f} ס"מ. '
                           'עומק הקצה העירוני לא ידוע – כמו קווי היועץ (כיסוי 0.50, זמני). היועץ: "נא לוודא מיקום טרם הביצוע".')
    return out


if __name__ == '__main__':
    p = os.path.join(ROOT, 'data/plumbing/proposal.json')
    P = json.load(open(p, encoding='utf-8'))
    P['site'] = build()
    P['summary']['site'] = {'chambers': len(P['site']['chamberRaise']), 'drops': len(P['site']['drops']), 'hoseReel': 1, 'meterConn': 2}
    json.dump(P, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    s = P['site']
    for c in s['chamberRaise']: print(c['id'], c['TLfrom'], '->', c['TLto'], c['before'], c['after'], c['finish'])
    for d in s['drops']: print(d['id'], d['ILin'], '->', d['ILlowInlet'], d.get('note'))
    print('hose', s['hoseReel']['shift_m'], s['hoseReel']['tee'], s['hoseReel']['slab'], s['hoseReel']['crossesSewer'])
    for r in s['runs']: print(r['id'], r['length_m'])

#!/usr/bin/env python3
"""ח1 – הצעת הזנה ראשית: ארון המונה בפילר -> קו הזנה תת-קרקעי -> לוח ראשי בכניסה.
קלט: tools/electrical/supply-inputs.json (ערכי תכנון) + קובצי data/ (גיאומטריה ממקורות).
פלט: data/electrical/supply.json (כולל בדיקות מרווח).  הרצה: python3 tools/electrical/propose_supply.py"""
import json, math, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
I = L('tools/electrical/supply-inputs.json')
origin = L('data/site/origin.json'); H0 = origin['H0']
stairs = L('data/structure/stairs.json'); blocks = L('data/architecture/blocks.json')
basement = L('data/structure/basement.json'); framing = L('data/structure/framing.json')
piles = L('data/structure/piles.json')['piles']; perim = L('data/structure/perimeter.json')
floor = L('data/structure/floor-ground.json'); net = L('data/plumbing/network.json'); plot = L('data/site/plot-5187.json')
r3 = lambda v: round(v, 3)
def unit(a, b):
    d = (b[0]-a[0], b[1]-a[1]); n = math.hypot(*d); return (d[0]/n, d[1]/n)
def seg_pt(a, b, p):
    d = (b[0]-a[0], b[1]-a[1]); l2 = d[0]**2+d[1]**2
    t = max(0, min(1, ((p[0]-a[0])*d[0]+(p[1]-a[1])*d[1])/l2)) if l2 else 0
    return math.hypot(p[0]-a[0]-t*d[0], p[1]-a[1]-t*d[1])
def seg_x(a, b, c, d):
    r = (b[0]-a[0], b[1]-a[1]); s = (d[0]-c[0], d[1]-c[1]); den = r[0]*s[1]-r[1]*s[0]
    if abs(den) < 1e-12: return None
    t = ((c[0]-a[0])*s[1]-(c[1]-a[1])*s[0])/den; u = ((c[0]-a[0])*r[1]-(c[1]-a[1])*r[0])/den
    return (t, u, (a[0]+t*r[0], a[1]+t*r[1])) if 0 <= t <= 1 and 0 <= u <= 1 else None
def inside(p, ring):
    c = False
    for i in range(len(ring)):
        a, b = ring[i], ring[(i+1) % len(ring)]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < a[0]+(p[1]-a[1])*(b[0]-a[0])/(b[1]-a[1]): c = not c
    return c
def ring_dist(p, ring): return min(seg_pt(ring[i], ring[(i+1) % len(ring)], p) for i in range(len(ring)))

# ---- main panel on the inner face of the host wall
mp = I['mainPanel']; wall = next(w for w in blocks['walls'] if w['id'] == mp['hostWall'])
a, b = wall['axisITM']; u = unit(a, b); mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
door = next(o for o in L('data/architecture/openings.json')['openings'] if o['id'] == 'G01')['centerITM']
nrm = (-u[1], u[0])
if (door[0]-mid[0])*nrm[0]+(door[1]-mid[1])*nrm[1] < 0: nrm = (u[1], -u[0])   # normal towards the entrance hall
face = (mid[0]+nrm[0]*wall['thickness_m']/2, mid[1]+nrm[1]*wall['thickness_m']/2)
riser = (face[0]+nrm[0]*I['riserOffsetFromWall_m'], face[1]+nrm[1]*I['riserOffsetFromWall_m'])

# ---- corridor parallel to the south facade (= basement south wall line)
bo = basement['outlineITM']; sw = min(bo, key=lambda p: p[0])
gb = framing['groundBeams']; b45 = next(g for g in gb if g['id'] == 'B-45')['axisITM']
fu = unit(b45[0], b45[-1]); fu = fu if fu[0] > 0 else (-fu[0], -fu[1])     # along the facade, eastwards
fs = (fu[1], -fu[0]); fs = fs if fs[1] < 0 else (-fs[0], -fs[1])           # towards the street (south)
dC = I['corridorOffsetSouthOfFacade_m']
onC = lambda s: (sw[0]+fu[0]*s+fs[0]*dC, sw[1]+fu[1]*s+fs[1]*dC)
sOf = lambda p: (p[0]-sw[0])*fu[0]+(p[1]-sw[1])*fu[1]

# ---- meter cabinet (pillar)
cab = stairs['pillar']['cabinet']; cr = cab['ringITM']
cc = (sum(p[0] for p in cr)/4, sum(p[1] for p in cr)/4)
long_ = max(((cr[i], cr[(i+1) % 4]) for i in range(4)), key=lambda e: math.dist(*e)); lu = unit(*long_); lu = lu if lu[0] > 0 else (-lu[0], -lu[1])
ce = I['cabinetEntry']; wt = stairs['pillar']['wallThickness_m'][0]
back = max((e for e in ((cr[i], cr[(i+1) % 4]) for i in range(4)) if math.dist(*e) > 0.8*math.dist(*long_)), key=lambda e: e[0][1]+e[1][1])   # long edge on the lot side
bm = ((back[0][0]+back[1][0])/2, (back[0][1]+back[1][1])/2); nb = (-lu[1], lu[0]); nb = nb if nb[1] > 0 else (-nb[0], -nb[1])
cabR = (bm[0]+lu[0]*ce['alongBack_m']+nb[0]*(wt+ce['behindBackWall_m']), bm[1]+lu[1]*ce['alongBack_m']+nb[1]*(wt+ce['behindBackWall_m']))
join = onC(sOf(cabR)+0.8); sE = sOf(riser)-I['entryLegWestOfRiser_m']; east = onC(sE)
e2 = (riser[0]-fu[0]*I['entryLegWestOfRiser_m'], riser[1]-fu[1]*I['entryLegWestOfRiser_m'])
plan = [cabR, join, east, e2, riser]
zc = H0+I['feederCentreRel']; cabBottom = H0+cab['bottomRel']; panelBottom = H0+mp['bottomRel']
zin = cabBottom+ce['entryAboveCabinetBottom_m']
pts3d = [[r3(cc[0]), r3(cc[1]), r3(zin)], [r3(cabR[0]), r3(cabR[1]), r3(zin)]] + [[r3(p[0]), r3(p[1]), r3(zc)] for p in plan] + [[r3(riser[0]), r3(riser[1]), r3(panelBottom)]]
length = sum(math.dist(pts3d[i], pts3d[i+1]) for i in range(len(pts3d)-1))
segs = list(zip(plan[:-1], plan[1:]))
rC = max(c['D_mm'] for c in I['conduits'])/2000; halfBundle = rC+I['conduitSpacing_m']/2*(len(I['conduits'])-1)
top, bot = zc+rC, zc-rC

# ---- checks
checks = []; mc = I['minClear']
def chk(kind, ref, value, need, note=''):
    checks.append({'kind': kind, 'ref': ref, 'clear_m': r3(value), 'required_m': need, 'ok': value >= need-1e-6, 'note': note})
for p in piles:
    d = min(seg_pt(s[0], s[1], (p['E'], p['N'])) for s in segs)-p['diameter_m']/2-halfBundle
    if d < 1.0: chk('pile', f"כלונס {p['id']}", d, mc['pile_m'], 'מרחק אופקי משפת הכלונס')
for n in net['nodes']:
    if n['kind'] in ('sewerChamber', 'pumpChamber', 'municipalManhole') and n.get('D_m'):
        d = min(seg_pt(s[0], s[1], (n['E'], n['N'])) for s in segs)-n['D_m']/2-halfBundle
        if d < 2.0: chk('chamber', n['id'], d, mc['chamber_m'], 'מרחק אופקי מדופן פנימית של השוחה')
for g in gb:
    ax = g['axisITM']
    for s in segs:
        for i in range(len(ax)-1):
            if seg_x(s[0], s[1], ax[i], ax[i+1]): chk('beam', g['id'], H0+g['bottomRel']-top, mc['beamVertical_m'], f"תחתית קורה {g['bottomRel']:+.2f}; ראש הצינור {top-H0:+.2f}")
for f in perim['footings']:
    ring = f['ringITM']
    if any(seg_x(s[0], s[1], ring[i], ring[(i+1) % len(ring)]) for s in segs for i in range(len(ring))) or any(inside(p, ring) for p in plan):
        chk('footing', f['id'], H0+f['bottomRel']-top, mc['beamVertical_m'], f"תחתית יסוד החומה {f['bottomRel']:+.2f}")
for r in net['runs']:
    if r['system'] not in ('sewage', 'pumped', 'rain') or r.get('ILup') is None: continue
    pts = r['pts']; tot = sum(math.dist(pts[i], pts[i+1]) for i in range(len(pts)-1)); run = 0
    for i in range(len(pts)-1):
        for s in segs:
            x = seg_x(pts[i], pts[i+1], s[0], s[1])
            if x:
                il = r['ILup']+(r['ILdown']-r['ILup'])*(run+x[0]*math.dist(pts[i], pts[i+1]))/tot
                chk('pipe', r['id'], il-top, mc['pipeVertical_m'], f"ø{r['D_mm']} {r['system']}, רום תחתית בחצייה {il:.3f}; הצינור עובר מתחת")
        run += math.dist(pts[i], pts[i+1])
bd = min(ring_dist(p, bo) for p in (join, east))-halfBundle
chk('basement', 'קיר המרתף הדרומי (קו חוץ)', bd, 0.5, 'מרחק אופקי של המסדרון מקו החוץ של קירות המרתף')
chk('plot', 'גבול המגרש', min(ring_dist(p, plot['ring']) for p in plan) if all(inside(p, plot['ring']) for p in plan) else -1, 0.1, 'כל נקודות התוואי בתוך המגרש')
slab = next((s for s in floor['slab'] if inside(riser, s['footprintITM']) and not any(inside(riser, h) for h in s.get('holesITM') or [])), None)
host = seg_pt(a, b, riser)-wall['thickness_m']/2
b49 = next(g for g in gb if g['id'] == 'B-49'); bx = b49['axisITM']
chk('beamSide', 'B-49 (מתחת לקיר הלוח)', seg_pt(bx[0], bx[-1], riser)-b49['width_m']/2-rC, 0.0, 'העלייה דרך הרצפה צמודה לדופן הקורה – בלי לחדור לקורה')

out = {
  '_doc': 'ח1 – הצעת הזנה ראשית (חשמל). נוצר ע"י tools/electrical/propose_supply.py – לא לערוך ידנית. כל הערכים הצעת תכנון (provisional) עד אישור אביחי.',
  'status': 'proposal', 'source': 'tools/electrical/propose_supply.py + tools/electrical/supply-inputs.json',
  'connection': I['connection'],
  'meterCabinet': {'id': 'MC', 'name': 'ארון מונה בפילר (חברת החשמל)', 'ringITM': cr, 'bottomRel': cab['bottomRel'], 'topRel': cab['topRel'], 'status': cab['status'],
                   'note': 'מיקום הארון מתוכנית הפיתוח; מידות הארון ופרט היסוד חסרים (open-issues #64, E8)', 'source': 'data/structure/stairs.json pillar.cabinet'},
  'mainPanel': {'id': mp['id'], 'name': 'לוח ראשי', 'hostWall': mp['hostWall'], 'faceITM': [r3(face[0]), r3(face[1])], 'alongITM': [r3(u[0]), r3(u[1])], 'normalITM': [r3(nrm[0]), r3(nrm[1])],
                'width_m': mp['width_m'], 'height_m': mp['height_m'], 'depth_m': mp['depth_m'], 'bottomRel': mp['bottomRel'], 'topRel': r3(mp['bottomRel']+mp['height_m']),
                'wallClearLength_m': wall['length_m'], 'wallThickness_m': wall['thickness_m'], 'status': 'provisional', 'decision': mp['decision'], 'note': mp['note'],
                'source': f"מיקום: החלטת אביחי 10.11.2026; קיר: data/architecture/blocks.json {mp['hostWall']}; מידות: הנחת תכנון"},
  'feeder': {'id': 'FD-MAIN', 'name': 'קו הזנה ראשי: ארון מונה → לוח ראשי', 'cable': I['cable'], 'conduits': I['conduits'], 'conduitSpacing_m': I['conduitSpacing_m'],
             'pts3d': pts3d, 'centreRel': I['feederCentreRel'], 'levelRule': I['feederLevelRule'], 'length_m': r3(length), 'cableLength_m': r3(length+mp['height_m']+1.5),
             'cableLengthNote': 'אורך התוואי + גובה הלוח + 1.5 מ\' קצוות בארון המונה', 'throughSlab': slab and slab['id'], 'status': 'provisional', 'pillarEnd': {'points': [0, 1, 2], 'status': 'provisional', 'note': ce['note']},
             'source': 'tools/electrical/propose_supply.py (הנחת תכנון; מכשולים מ-data/structure, data/plumbing)'},
  'sleeves': [
    {'id': 'ES-1', 'through': f"רצפת הקרקע {slab['id'] if slab else '?'} (תלויה) – עלייה ללוח הראשי", 'at': pts3d[-2][:2]+[r3(H0+(slab['topRel'] if slab else 0))], 'axis': 'v',
     'count': len(I['conduits']), 'sleeveD_mm': 110, 'note': 'שרוול לכל צינור, לפני יציקת הרצפה; צמוד לדופן קורה B-49 – לאישור הקונסטרוקטור. להשאיר רפיון בצינור בגובה ארגזי ההפרדה', 'status': 'provisional'},
    {'id': 'ES-2', 'through': 'הקיר האחורי של ארון המונה בפילר (מחדר האשפה)', 'at': [r3((cc[0]+cabR[0])/2), r3((cc[1]+cabR[1])/2), r3(zin)], 'axis': 'h', 'count': len(I['conduits']), 'sleeveD_mm': 110,
     'note': ce['note'], 'status': 'provisional'}],
  'checks': checks, 'summary': {'length_m': r3(length), 'checks': len(checks), 'failed': sum(1 for c in checks if not c['ok']), 'riserFromWallFace_m': r3(host)},
}
json.dump(out, open(os.path.join(ROOT, 'data/electrical/supply.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('length', out['summary']); print('panel face', out['mainPanel']['faceITM'], 'slab', slab and slab['id'])
for c in checks: print(' ', 'OK ' if c['ok'] else 'XX ', c['kind'], c['ref'], c['clear_m'], '/', c['required_m'], c['note'])

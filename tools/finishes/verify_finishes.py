#!/usr/bin/env python3
"""Independent check of the plaster quantities (docs/verification/finishes.md): for one room per floor, the wall area
by hand – room perimeter × (ceiling underside − floor slab top) − openings (width × clear height inside the room) –
next to the sum of the derived faces; the ceiling area next to the room area. Data only from the JSON files."""
import json, math, os
from shapely.geometry import Polygon, Point
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
R = J('data/architecture/rooms.json'); S = J('data/finishes/plaster/surfaces.json'); OP = J('data/architecture/openings.json')['openings']
GF, FF, FR = J('data/structure/floor-ground.json'), J('data/structure/floor-first.json'), J('data/structure/framing.json')
SL = {s['id']: (s['topRel'], s['bottomRel']) for s in GF['slab'] + GF['ceiling']['slab'] + FF['ceiling']['slab']}
SL.update({s['id']: (s['top'], s['top'] - s['thickness_m']) for s in FR['slabs']})
PICK = [('unit', 'מרתף שירות', 'BS1', 'GS1'), ('ground', 'שינה', 'GS1', 'FS1'), ('first', 'חדר', 'FS1', 'RS1')]
rows = []
for fl, nm, fs, cs in PICK:
    r = next(x for x in R['rooms'] if x['floor'] == fl and x['name'] and nm in x['name'])
    P = Polygon(r['ringITM']); H = SL[cs][1] - SL[fs][0]
    ops = [o for o in OP if o['floor'] == fl and P.exterior.distance(Point(o['centerITM'])) < 0.35]
    oa = sum(o['width_m'] * (min(o['headRel'], SL[cs][1]) - max(o['sillRel'], SL[fs][0])) for o in ops)
    hand = P.length * H - oa
    faces = [f for f in S['walls'] if f['room'] == r['key'] and f['side'] == 'in']
    model = sum(f['net'] for f in faces)
    ce = sum(c['area'] for c in S['ceilings'] if c['room'] == r['key'])
    rows.append((fl, r['name'], r['key'], P.length, SL[fs][0], SL[cs][1], H, [o['id'] for o in ops], oa, hand, model, P.area, ce))
L = ['# אימות כמויות טיח – חישוב ידני מול המודל', '',
     'נוצר ב-`python3 tools/finishes/verify_finishes.py`. החישוב הידני לא משתמש בפני הקיר שנגזרו: היקף החדר (rooms.json) × (תחתית התקרה − פני הבטון של הרצפה, מקובצי השלד) פחות הפתחים שמרכזם על היקף החדר (openings.json: רוחב × גובה נטו בתוך החדר).',
     'ההפרש הצפוי: עמודים / קורות בולטים, פינות, ופתחים שחלקם מחוץ לטווח – מוסבר בעמודה האחרונה.', '',
     '| קומה | חדר | היקף מ\' | רצפה (בטון) | תקרה (תחתית) | גובה | פתחים | שטח פתחים | ידני נטו מ"ר | מודל נטו מ"ר | סטייה | שטח חדר | תקרה במודל |',
     '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
for fl, nm, k, per, f0, c1, H, ops, oa, hand, model, A, ce in rows:
    L.append(f"| {fl} | {nm} | {per:.3f} | {f0:+.2f} | {c1:+.2f} | {H:.2f} | {', '.join(ops) or '—'} | {oa:.3f} | {hand:.3f} | {model:.3f} | {model - hand:+.3f} ({(model - hand) / hand * 100:+.2f}%) | {A:.3f} | {ce:.3f} |")
L += ['', f"סה\"כ: {len(S['walls'])} פני קיר, {len(S['ceilings'])} משטחי תקרה, {len(S['tops'])} ראשי קירות, {len(S['reveals'])} פתחים (גליפים), {len(S['waterproofing'])} רצועות איטום."]
open(os.path.join(ROOT, 'docs/verification/finishes-check.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L[-len(rows) - 3:]))

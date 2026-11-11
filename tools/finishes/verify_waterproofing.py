#!/usr/bin/env python3
"""Waterproofing check, plaster round 4 (chat prompt docs/chat-prompts/2026-11-11-בדיקה-היקפית-טיח-ואיטום.md §3).

Every waterproofing layer that exists in the model:
  - wet rooms (data/finishes/plaster/surfaces.json waterproofing): the floor covers the room floor; along the room
    outline (2 cm steps, at 10 cm over the finished floor and – in the shower zones – at 1.0 m) a wall strip or a door is
    in front of every point; the wall strip starts at or below the floor layer (no gap at the floor–wall corner); heights
    as set (types.json waterproofing).
  - the external waterproofing of the basement walls (data/structure/framing.json waterproofing): every sample of the
    basement wall faces against the soil (plaster type membrane) lies inside it.
Layers that do not exist in the model are listed (no detail in the sources – not invented).
Output: docs/verification/waterproofing-check.md
"""
import json, math, os
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
P = J('data/finishes/plaster/surfaces.json'); TL = J('data/finishes/tiling/surfaces.json'); R = J('data/architecture/rooms.json')
T = J('data/finishes/plaster/types.json')['waterproofing']; CFG = J('data/finishes/config.json'); FR = J('data/structure/framing.json')
WP = P['waterproofing']; rooms = {r['key']: r for r in R['rooms']}
L = ['# בדיקת איטום – סבב 4', '', 'נוצר ב-`python3 tools/finishes/verify_waterproofing.py`. בודק כל שכבת איטום שקיימת במודל.', '']
issues = []

# ---------------------------------------------------------------- wet rooms
L += ['## חדרים רטובים (איטום צמנטי גמיש)', '', f"גבהים (ברירת מחדל, זמני): הגבהה {T['wetRoomHeight_m'] * 100:.0f} ס\"מ, קירות המקלחת {T['showerHeight_m']:.2f} מ'.", '',
      '| קומה | חדר | רצפה: איטום / ריצוף מ"ר | היקף נבדק מ\' | פער בהיקף (10 ס"מ) | פער באזור המקלחת (1.0 מ\') | קיר ← רצפה | הערה |', '|---|---|---|---|---|---|---|---|']
for key, r in rooms.items():
    if r['type'] != 'wet': continue
    fl = r['floor']; ff = CFG['finishFloor'][fl]
    walls = [w for w in WP if w['kind'] == 'wall' and w['room'] == key]
    floors = [w for w in WP if w['kind'] == 'floor' and w['room'] == key]
    tile = next((t for t in TL['rooms'] if t['room'] == key), None)
    fa = sum(w['area'] for w in floors); ta = tile['area'] if tile else 0
    zf = floors[0]['z'] if floors else None
    faces = [f for f in P['walls'] if f['room'] == key and f['side'] == 'in']
    doors = []
    for f in faces:
        A, B = f['a'], f['b']; Lf = math.dist(A, B); ux, uy = (B[0] - A[0]) / Lf, (B[1] - A[1]) / Lf
        for o in f['openings']:
            if o['z0'] <= f['z0'] + 0.01: doors.append(LineString([(A[0] + ux * o['s0'], A[1] + uy * o['s0']), (A[0] + ux * o['s1'], A[1] + uy * o['s1'])]))

    def at(pt, z, shower_only=False):
        for w in walls:
            if shower_only and not w['shower']: continue
            if LineString([w['a'], w['b']]).distance(pt) < 0.06 and w['z0'] - 0.005 <= z <= w['z1'] + 0.005: return True
        return any(d.distance(pt) < 0.06 for d in doors)
    ring = Polygon(r['ringITM']).exterior; n = int(ring.length / 0.02)
    gap10, gapS, nS = 0.0, 0.0, 0
    for i in range(n):
        p = ring.interpolate((i + 0.5) * ring.length / n)
        if not at(p, ff + 0.10): gap10 += ring.length / n
        if any(w['shower'] and LineString([w['a'], w['b']]).distance(p) < 0.06 for w in walls):
            nS += 1
            if not at(p, ff + 1.0, True): gapS += ring.length / n
    corner = all(w['z0'] <= (zf if zf is not None else ff) + 1e-6 for w in walls)
    hi = [w for w in walls if abs((w['z1'] - w['finish']) - (T['showerHeight_m'] if w['shower'] else T['wetRoomHeight_m'])) > 0.005 and w['z1'] < w['faceTop'] - 0.005]
    note = []
    if abs(fa - ta) > 0.01: note.append(f'רצפה ≠ ריצוף ({fa:.2f}/{ta:.2f})')
    if hi: note.append('גובה שונה מהכלל: ' + ', '.join(w['owner'] for w in hi))
    capped = [w['owner'] for w in walls if w['z1'] >= w['faceTop'] - 0.005 and w['area'] == 0]
    if capped: note.append('פנים שמתחילים מעל גובה האיטום (אין מה לאטום): ' + ', '.join(sorted(set(capped))))
    if gap10 > 0.02: issues.append(f"{r['name']} ({fl}): פער של {gap10:.2f} מ' בהיקף בגובה 10 ס\"מ")
    if gapS > 0.02: issues.append(f"{r['name']} ({fl}): פער של {gapS:.2f} מ' באזור המקלחת")
    if not corner: issues.append(f"{r['name']} ({fl}): רצועת קיר שמתחילה מעל שכבת האיטום של הרצפה")
    L.append(f"| {fl} | {r['name']} | {fa:.2f} / {ta:.2f} | {ring.length:.2f} | {gap10:.2f} מ' | {gapS:.2f} מ' ({nS * 0.02:.1f} נבדקו) | {'רציף' if corner else 'פער'} | {'; '.join(note) or '—'} |")
L += ['', 'קיר ← רצפה: רצועת הקיר מתחילה בפני הבטון ועוברת את מפלס האיטום של הרצפה (על המדה) – החפיפה בפינה רציפה.', '']

# ---------------------------------------------------------------- basement walls: external waterproofing
W = FR['waterproofing']; band = Polygon(W['ringITM'], W.get('holesITM', []))
mem = [f for f in P['walls'] if f['type'] == 'membrane']
tot = bad = 0.0; badpts = []
for f in mem:
    A, B = f['a'], f['b']; Lf = math.dist(A, B); ux, uy = (B[0] - A[0]) / Lf, (B[1] - A[1]) / Lf; nx, ny = f['normal']
    ns = max(1, int(Lf / 0.02)); nz = max(1, int((f['z1'] - f['z0']) / 0.05))
    for i in range(ns):
        s = (i + 0.5) * Lf / ns; q = Point(A[0] + ux * s + nx * 0.01, A[1] + uy * s + ny * 0.01)
        ok_xy = band.buffer(0.02).contains(q)
        for j in range(nz):
            z = f['z0'] + (j + 0.5) * (f['z1'] - f['z0']) / nz; a = (Lf / ns) * ((f['z1'] - f['z0']) / nz); tot += a
            if not (ok_xy and W['bottomRel'] - 0.01 <= z <= W['topRel'] + 0.01): bad += a; badpts.append((round(q.x, 2), round(q.y, 2), round(z, 2), f['owner']))
L += ['## קירות המרתף מבחוץ (איטום ביטומני – זמני)', '',
      f"שכבה: {' · '.join(W['layers'])}. מ-{W['bottomRel']:+.2f} עד {W['topRel']:+.2f}, היקף {W['perimeter_m']:.1f} מ' (`framing.json`, provisional – אין פרט במקורות).", '',
      f"פני קירות המרתף שבמגע עם הקרקע (סוג 'איטום + יריעת הגנה'): {tot:.2f} מ\"ר. מחוץ לשכבת האיטום: **{bad:.2f} מ\"ר**."]
if badpts:
    by = {}
    for x, y, z, o in badpts: by.setdefault(o, []).append(z)
    L += ['', '| קיר | מ"ר בערך | מפלסים |', '|---|---|---|'] + [f"| {o} | {len(zs) * 0.02 * 0.05:.2f} | {min(zs):+.2f} … {max(zs):+.2f} |" for o, zs in sorted(by.items())]
    issues.append(f"קירות המרתף: {bad:.2f} מ\"ר במגע עם הקרקע מחוץ לשכבת האיטום (ראו טבלה)")
L += ['']

# ---------------------------------------------------------------- layers that do not exist
L += ['## שכבות איטום שאין במודל', '', 'אין להן פרט במקורות ולא נבנו (לא ממציאים):', '',
      '- מרפסות ורצפות חוץ (מרפסת קומה א\', המשטח הצפוני)', '- הגג (תקרת הגג ‎+6.90 והחומה)', '- חצרות אנגליות (רצפה וקירות מצד החצר)', '- אדניות', '- הבריכה (פנים הבריכה – גמר הבריכה)', '',
      'כשיגיע פרט איטום (אדריכל / יועץ איטום) – ייבנו לפיו. open-issues #170.', '']
L += ['## ממצאים', ''] + ([f'- {x}' for x in issues] or ['- אין פערים בשכבות הקיימות.'])
open(os.path.join(ROOT, 'docs/verification/waterproofing-check.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L))

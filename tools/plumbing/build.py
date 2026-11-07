#!/usr/bin/env python3
"""Plumbing layer – network builder: tools/plumbing/cache/raw.json (extract.py) -> data/plumbing/network.json

Topology, levels, diameters and engineering findings of the plumbing consultant's design, AS DRAWN.
Rules (all documented in each record's `status` / `levelRule`):
  * Sewer centre lines = green lines of the 4 PDF sheets (31.10.2026). A line end belongs to a chamber / stack / symbol
    when it lies inside its capture radius; short gaps (the line is interrupted under a symbol) are bridged; then
    fixtures; then T-junctions. What is left is an OPEN END (finding) – nothing is invented.
  * Manual readings (tools/plumbing/manual-readings.json) only name what a line end is, from a label in the drawing.
  * Levels: chambers (G_LABELD) and the sewer profile 0-1-4-5 are source. Upstream of a chamber a run rises at its
    written slope (label within 1 m), otherwise 2% (= the slope written on the other lines) -> provisional.
    First-floor branches: invert at the stack = structural slab top +3.70 (no level in the drawings) -> provisional.
  * Diameters: label within 1 m (BIUV layer); otherwise by the fixture it drains (WC/stack -> ø110, others -> ø50),
    marked `diameterRule`.
"""
import json, math, os, re, sys
from collections import defaultdict, deque
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import build_nodes, split_at_nodes, PREFIX, r3, P
import georef as G
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union

ROOT = G.ROOT
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
H0 = J('data/site/origin.json')['H0']
DXF_ROT = 21.986   # DXF frame = ITM frame rotated by +21.99° (georef: PDF/DXF -> ITM rotation)


# ------------------------------------------------------------------ helpers
def dist(a, b): return math.dist(a, b)


def length(pts): return sum(dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def end_pt(r, k): return r['pts'][0] if k == 0 else r['pts'][-1]


def near_labels(labels, pts, pat, maxd=1.0, fl=None):
    L = LineString(pts)
    inside = lambda q: 0.05 < L.project(Point(q)) < L.length - 0.05
    c = [(L.distance(Point(l['E'], l['N'])), l) for l in labels if re.search(pat, l['text']) and (fl is None or l['floor'] == fl) and inside((l['E'], l['N']))]
    c = [x for x in c if x[0] <= maxd]
    return min(c, key=lambda x: x[0])[1] if c else None


# ------------------------------------------------------------------ sewer topology
def sewer(R, M):
    nodes = build_nodes(R)
    for i, (E, N) in enumerate(R['unitDrains']):
        nodes.append({'id': f'FD{i + 1}@unit', 'kind': 'floorDrain', 'cls': 'symbol', 'floor': 'unit', 'E': E, 'N': N, 'capture': 0.22, 'status': 'source',
                      'title': 'מ.ר – מחסום רצפה ø8/4" (חצר אנגלית)', 'source': f'{G.PDF["unit"]} – עיגול כחול ø0.22 (מ.ר ø8/4")'})
    for n in nodes:
        if n['kind'] in ('inspectionBox', 'dropInspectionBox'): n['capture'] = 0.28
    byid = {n['id']: n for n in nodes}
    runs = []
    for fl, segs in R['green'].items():
        k = 0
        for pts in split_at_nodes(segs, nodes, fl):
            if length(pts) < 0.04: continue
            k += 1; runs.append({'id': f'SW{k}@{fl}', 'floor': fl, 'system': 'sewage', 'pts': [P(p) for p in pts], 'ends': [None, None]})

    def snap(p, fl, classes):
        best = None
        for n in nodes:
            if n['cls'] not in classes: continue
            if not (n['floor'] == fl or (fl == 'ground' and n['floor'] == 'site')): continue
            d = dist(p, (n['E'], n['N'])) - n['capture']
            if d <= 0 and (best is None or d < best[0]): best = (d, n)
        return best[1] if best else None

    jn = [0]
    def junction(fl, E, N, kind, title, src, **kw):
        jn[0] += 1; j = {'id': f'J{jn[0]}@{fl}', 'kind': kind, 'cls': 'junction', 'floor': fl, 'E': r3(E), 'N': r3(N), 'title': title, 'status': 'derived', 'source': src, **kw}
        nodes.append(j); byid[j['id']] = j; return j

    # 1. hard nodes
    for r in runs:
        for k in (0, 1):
            n = snap(end_pt(r, k), r['floor'], ('chamber', 'stack', 'symbol'))
            if n: r['ends'][k] = n['id']
    # 1b. manual readings (documented): name what a line end is – overrides the automatic snap
    def apply_manual():
        for m in M['sewerEnds']:
            for r in runs:
                if r['floor'] != m['floor']: continue
                for k in (0, 1):
                    if dist(end_pt(r, k), m['at']) < m.get('tol', 0.15):
                        if m['node'] not in byid:
                            n = {'id': m['node'], 'kind': m['kind'], 'cls': m.get('cls', 'fixture'), 'floor': m['floor'], 'E': r3(end_pt(r, k)[0]), 'N': r3(end_pt(r, k)[1]),
                                 'title': m['title'], 'status': m.get('status', 'derived'), 'source': m['source'], 'capture': 0.1}
                            nodes.append(n); byid[n['id']] = n
                        r['ends'][k] = m['node']
    apply_manual()
    # owner fixture of a free end (inside its capture) – two ends owned by different fixtures are never bridged
    def owner(p, fl):
        n = snap(p, fl, ('fixture',)); return n['id'] if n else None
    # 2/4. bridge short gaps (globally shortest first)
    def bridge(maxd):
        free = [(r, k) for r in runs for k in (0, 1) if not r['ends'][k]]
        pairs = sorted((dist(end_pt(a, ka), end_pt(b, kb)), i, j) for i, (a, ka) in enumerate(free) for j, (b, kb) in enumerate(free)
                       if i < j and a is not b and a['floor'] == b['floor'])
        used = set()
        for d, i, j in pairs:
            if d > maxd: break
            if i in used or j in used: continue
            (a, ka), (b, kb) = free[i], free[j]
            p, q = end_pt(a, ka), end_pt(b, kb)
            oa, ob = owner(p, a['floor']), owner(q, b['floor'])
            if oa and ob and oa != ob: continue
            jj = junction(a['floor'], (p[0] + q[0]) / 2, (p[1] + q[1]) / 2, 'joint', 'המשך קו (רווח בשרטוט מתחת לסמל)',
                          f'גישור רווח של {d:.2f} מ\' בין שני קצוות של הקו הירוק ב-PDF', gap_m=r3(d))
            a['ends'][ka] = jj['id']; b['ends'][kb] = jj['id']; used |= {i, j}
    bridge(0.25)
    # 3. fixtures
    for r in runs:
        for k in (0, 1):
            if r['ends'][k]: continue
            n = snap(end_pt(r, k), r['floor'], ('fixture',))
            if n and n['kind'] in ('wc', 'basin', 'sink', 'shower'): r['ends'][k] = n['id']
    bridge(0.45)
    # 4b. a joint inside a WC capture is the toilet outlet (pan connector drawn there) -> the WC node
    for j in [n for n in nodes if n['cls'] == 'junction' and n['kind'] == 'joint']:
        wc = snap((j['E'], j['N']), j['floor'], ('fixture',))
        if wc and wc['kind'] == 'wc':
            for r in runs:
                r['ends'] = [wc['id'] if e == j['id'] else e for e in r['ends']]
            nodes.remove(j); byid.pop(j['id'])
    # 5. T-junctions
    for r in runs:
        for k in (0, 1):
            if r['ends'][k]: continue
            p = end_pt(r, k); best = None
            for q in runs:
                if q is r or q['floor'] != r['floor']: continue
                for a, b in zip(q['pts'][:-1], q['pts'][1:]):
                    L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
                    t = max(0, min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / L2)) if L2 else 0
                    c = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
                    if dist(p, c) < 0.15 and 0.02 < t < 0.98 and (best is None or dist(p, c) < best[0]): best = (dist(p, c), q, c)
            if best:
                j = junction(r['floor'], *best[2], 'tee', 'הסתעפות', 'קצה קו ירוק על קו אחר ב-PDF', onRun=best[1]['id'])
                r['ends'][k] = j['id']
    # 7. open ends
    for r in runs:
        for k in (0, 1):
            if not r['ends'][k]:
                p = end_pt(r, k); jn[0] += 1
                n = {'id': f'END{jn[0]}@{r["floor"]}', 'kind': 'openEnd', 'cls': 'openEnd', 'floor': r['floor'], 'E': r3(p[0]), 'N': r3(p[1]),
                     'title': 'קצה קו בלי חיבור מוגדר', 'status': 'missing', 'source': 'קו ירוק ב-PDF שנגמר בלי סמל / שוחה / קבועה'}
                nodes.append(n); byid[n['id']] = n; r['ends'][k] = n['id']
    # drop drawing fragments inside one symbol/fixture (both ends on the same node, < 0.6 m)
    runs = [r for r in runs if not (r['ends'][0] == r['ends'][1] and length(r['pts']) < 0.6)]
    # explicit run roles from manual readings (pumped line, stack offsets drawn as lines)
    for m in M['runRoles']:
        for r in runs:
            if r['floor'] == m['floor'] and LineString(r['pts']).distance(Point(*m['at'])) < 0.05:
                r.update({k: v for k, v in m.items() if k not in ('at', 'floor')})
    return nodes, byid, runs


# ------------------------------------------------------------------ flow direction + levels
def sewer_levels(R, M, nodes, byid, runs, labels):
    prof = R['profile']['chambers']
    ch = {n['id']: n for n in nodes if n['cls'] == 'chamber'}
    # graph
    adj = defaultdict(list)
    for r in runs:
        if r.get('role') == 'stackOffset': continue
        a, b = r['ends']; adj[a].append((b, r)); adj[b].append((a, r))
    # stacks: link floors of the same stack (vertical, no length cost for the direction search)
    stack_nodes = defaultdict(list)
    for n in nodes:
        if n['kind'] == 'stack': stack_nodes[n['stack']].append(n['id'])
    for s, ids in stack_nodes.items():
        for a in ids:
            for b in ids:
                if a != b: adj[a].append((b, None))
    # distance to the outlet: S-0 for gravity; PC-1 is the sink of the basement network (pumped to S-2)
    def dijkstra(src):
        D = {src: 0.0}; Q = [(0.0, src)]
        import heapq
        while Q:
            d, u = heapq.heappop(Q)
            if d > D.get(u, 1e9): continue
            for v, r in adj[u]:
                if r is not None and r.get('role') == 'pumped': continue
                nd = d + (length(r['pts']) if r else 0.01)
                if nd < D.get(v, 1e9): D[v] = nd; heapq.heappush(Q, (nd, v))
        return D
    D0, Dpc = dijkstra('S-0'), dijkstra('PC-1')
    def dd(n):
        f = byid[n]['floor']
        return Dpc.get(n, 1e9) if f == 'unit' else D0.get(n, 1e9)
    for r in runs:
        a, b = r['ends']
        if r.get('role') == 'pumped': r['up'], r['down'] = (a, b) if r.get('flowFrom') == a else (b, a) if r.get('flowFrom') == b else (a, b); continue
        r['up'], r['down'] = (a, b) if dd(a) >= dd(b) else (b, a)
        if r['up'] != r['ends'][0]: r['pts'] = r['pts'][::-1]; r['ends'] = r['ends'][::-1]
    # slopes + diameters from labels
    for r in runs:
        fl = r['floor']
        sl = near_labels(labels, r['pts'], r'^\d+(\.\d+)?%$', 1.0, fl)
        r['slope_label'] = float(sl['text'][:-1]) / 100 if sl else None
        dl = near_labels(labels, r['pts'], r'ø(50|75|110|160)', 1.0, fl)
        r['diameterLabel'] = dl['text'] if dl else None
    # levels: from known downstream ends, walk upstream
    lvl = {}                                  # node -> invert level of the pipe at that node (downstream end of incoming runs)
    for c in ch.values(): lvl[c['id']] = c['IL']
    main = M['mainRuns']                      # chamber-to-chamber runs (consultant labels / profile)
    done = set()
    for r in runs:
        u, d = r['up'], r['down']
        if u in ch and d in ch:
            key = f'{u}->{d}'; mm = main.get(key, {})
            s = mm.get('slope') or r['slope_label'] or (ch[u]['IL'] - ch[d]['IL']) / length(r['pts'])
            ILd = ch[u]['IL'] - s * length(r['pts'])
            r.update(ILup=r3(ch[u]['IL']), ILdown=r3(ILd), slope=round(s, 4), levelRule=mm.get('rule', 'שיפוע כתוב בתוכנית'), levelStatus='source',
                     dropAtDownstream_m=r3(ILd - ch[d]['IL']) if ILd - ch[d]['IL'] > 0.005 else 0.0)
            done.add(r['id'])
    # branch inlet at a chamber
    def inlet(cid):
        c = ch[cid]
        if cid == 'S-1': return prof['S-1']['IL'][1], 'provisional', 'מפלס הכניסה לשוחה 1 = מפלס הכניסה של הקו 4→1 בפרופיל (279.13); ליועץ אין מפלס לענף הזה'
        if cid == 'PC-1': return c['TL'] - M['pumpChamberInletBelowTL_m'], 'provisional', f'כניסה לתא השאיבה: {M["pumpChamberInletBelowTL_m"]:.2f} מ\' מתחת לרום המכסה (אין מפלס בתוכנית)'
        return c['IL'], 'derived', 'מפלס הכניסה = I.L של השוחה (רום התעלה)'
    pending = deque(r for r in runs if r['id'] not in done and r.get('role') not in ('pumped',))
    guard = 0
    while pending and guard < 5000:
        guard += 1
        r = pending.popleft(); d = r['down']
        dn = byid[d]
        if d in ch: base, st, rule = inlet(d)
        elif r['floor'] == 'first' and dn['kind'] == 'stack':
            base, st, rule = M['firstFloorBranchInvertAtStack'], 'provisional', 'ענף בקומה א\': תחתית הצינור בקולטן = פני התקרה הקונסטרוקטיבית +3.70 (אין מפלס בתוכנית)'
            base += H0
        elif r['floor'] == 'unit' and dn['kind'] == 'stack':
            continue
        elif d in lvl: base, st, rule = lvl[d], 'derived', f'נגזר מהקו הממשיך אחרי {d}'
        else:
            pending.append(r); continue
        s = r['slope_label'] or M['defaultSlope']
        sst = 'derived' if r['slope_label'] else 'provisional'
        if st == 'provisional' or sst == 'provisional': st = 'provisional'
        L = length(r['pts'])
        r.update(ILdown=r3(base), ILup=r3(base + s * L), slope=r3(s), levelStatus=st,
                 levelRule=rule + ('' if r['slope_label'] else f'; שיפוע {s * 100:.0f}% הונח (לא כתוב ליד הקטע)'))
        u = r['up']
        lvl[u] = max(lvl.get(u, -1e9), r['ILup']) if byid[u]['cls'] in ('junction', 'symbol') else r['ILup']
        # a stack carries the level to its other floors (ground base level -> stack nodes of that stack)
        if byid[u]['kind'] == 'stack' and r['floor'] in ('ground',):
            for sid in stack_nodes[byid[u]['stack']]: lvl.setdefault(sid, r['ILup'])
    # basement network: unit stacks are vents (upstream ends of the courtyard lines) – level from their downstream run
    for r in runs:
        if 'ILdown' not in r and r.get('role') not in ('pumped',):
            r.update(levelStatus='missing', levelRule='לא נקבע מפלס')
    return lvl, stack_nodes


def diameters(runs, byid, M):
    for r in runs:
        lab = r.get('diameterLabel')
        if r.get('role') == 'pumped':
            continue
        u, d = r['ends']
        if byid[u]['cls'] == 'chamber' and byid[d]['cls'] == 'chamber':
            r.update(D_mm=160, material='PVC SN-8', diameterRule='קו בין שוחות: PVC SN-8 ø160 (פרופיל / תווית בתוכנית)'); continue
        if r['floor'] == 'unit' and lab is None and any(byid[e]['kind'] == 'floorDrain' for e in r['ends']):
            r.update(D_mm=110, material='HDPE', diameterRule='מחסום רצפה ø8/4" – יציאה 4" (ø110); בתוכנית HDPE ø110 על הקו'); continue
        if lab:
            m = re.search(r'ø(\d+)', lab); r['D_mm'] = int(m.group(1))
            r['material'] = 'PVC SN-8' if 'PVC' in lab else ('PEX' if 'PEX' in lab else 'HDPE')
            r['diameterRule'] = f'תווית "{lab}" ליד הקו'
        else:
            kinds = {byid[e]['kind'] for e in r['ends']}
            u, d = r['ends']
            if byid[u]['cls'] == 'chamber' and byid[d]['cls'] == 'chamber': D = 160; rule = 'קו בין שוחות'
            elif kinds & {'wc', 'stack', 'dropInspectionBox', 'chamber'} or byid[d]['cls'] == 'chamber': D = 110; rule = 'מנקז אסלה / קולטן / שוחה'
            else: D = 50; rule = 'מנקז כיור / מקלחת / מחסום'
            r['D_mm'] = D; r['material'] = 'PVC SN-8' if D == 160 else 'HDPE'; r['diameterRule'] = f'כלל (אין תווית): {rule}'
    return runs


# ------------------------------------------------------------------ water + rain
def water(R, M):
    nodes, runs = [], []
    lab = [l for l in R['labels'] if l['layer'] == 'text' and l['text'].startswith('ø')]
    def dxf_dir(a, b):
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) + DXF_ROT
        a_ = abs((ang + 180) % 180)
        return 'v' if 45 < a_ < 135 else 'h'
    meter = {'id': 'WM@site', 'kind': 'waterMeter', 'cls': 'water', 'floor': 'site', 'E': R['meter'][0], 'N': R['meter'][1], 'title': 'מערכת מדידת מים 3/4" (שעון התאגיד)',
             'status': 'source', 'source': f'{G.DXF} – חץ ההערה "פרט מע\' מדידת מים" + פרט מערכת מדידת מים (קובץ הפרטים)'}
    nodes.append(meter)
    polys = [w for w in R['water'] if w['floor'] == 'ground']
    # split points: an end of one polyline lying on another polyline = tee
    k = 0
    tees = []
    for w in polys:
        for p in (w['pts'][0], w['pts'][-1]):
            for o in polys:
                if o is w: continue
                Lo = LineString(o['pts'])
                if Lo.distance(Point(p)) < 0.30 and min(dist(p, o['pts'][0]), dist(p, o['pts'][-1])) > 0.05:
                    tees.append(Lo.interpolate(Lo.project(Point(p))).coords[0])
    def cut(pts):
        L = LineString(pts); cuts = sorted({round(L.project(Point(t)), 3) for t in tees if L.distance(Point(t)) < 0.01 and 0.02 < L.project(Point(t)) < L.length - 0.02})
        out, s0 = [], 0.0
        for c in cuts + [L.length]:
            seg = [L.interpolate(s0).coords[0]] + [q for q in pts if s0 < L.project(Point(q)) < c] + [L.interpolate(c).coords[0]]
            out.append(seg); s0 = c
        return out
    for w in polys:
        for seg in cut(w['pts']):
            if length(seg) < 0.05: continue
            k += 1
            d = dxf_dir(seg[0], seg[-1]); rot = 270 if d == 'v' else 180
            cand = [(min(dist((l['E'], l['N']), seg[0]), dist((l['E'], l['N']), seg[-1])), l) for l in lab if abs(((l.get('rotation') or rot) - rot)) < 1]
            near = [c for c in cand if c[0] < 0.5]
            runs.append({'id': f'CW{k}@ground', 'floor': 'ground', 'system': 'cold', 'pts': [P(p) for p in seg], 'dir': d})
    # end nodes
    allp = defaultdict(list)
    for r in runs:
        for kk in (0, 1): allp[tuple(round(v, 2) for v in end_pt(r, kk))].append((r, kk))
    def node_at(p, fl='ground'):
        for n in nodes:
            if dist(p, (n['E'], n['N'])) < 0.12: return n
        return None
    for r in runs:
        r['ends'] = [None, None]
        for kk in (0, 1):
            p = end_pt(r, kk); n = node_at(p)
            if not n:
                hit = [(o, ok) for o in runs for ok in (0, 1) if o is not r and dist(end_pt(o, ok), p) < 0.05]
                on = [o for o in runs if o is not r and LineString(o['pts']).distance(Point(p)) < 0.01]
                nid = f'WJ{len(nodes)}@ground'
                n = {'id': nid, 'kind': 'waterJoint', 'cls': 'water', 'floor': 'ground', 'E': r3(p[0]), 'N': r3(p[1]), 'title': 'הסתעפות / חיבור בקו המים', 'status': 'source', 'source': f'{G.DXF} – שכבה cold water'}
                nodes.append(n)
            r['ends'][kk] = n['id']
    # what each free end is (manual readings of the labels next to it)
    byid = {n['id']: n for n in nodes}
    deg = defaultdict(int)
    for r in runs:
        for e in r['ends']: deg[e] += 1
    for n in list(nodes):
        if n['kind'] != 'waterJoint' or deg[n['id']] != 1: continue
        m = min(M['waterEnds'], key=lambda m: dist(m['at'], (n['E'], n['N'])))
        if dist(m['at'], (n['E'], n['N'])) < m.get('tol', 0.6):
            n.update(kind=m['kind'], title=m['title'], status=m.get('status', 'derived'), source=m['source'])
        else:
            n.update(kind='openEnd', title='קצה קו מים בלי סימון', status='missing', dangling=True)
    # diameters: label clusters at the tees; rotation 270 = along DXF-vertical pipes, 180 = DXF-horizontal
    for r in runs:
        rot = 270 if r['dir'] == 'v' else 180
        c = []
        for l in lab:
            lr = l.get('rot')
            dmin = min(dist((l['E'], l['N']), end_pt(r, 0)), dist((l['E'], l['N']), end_pt(r, 1)))
            c.append((dmin, l))
        c = [x for x in c if x[0] < 0.45 and x[1]['rot'] == rot]
        if c:
            l = min(c, key=lambda x: x[0])[1]; r['D_mm'] = int(l['text'][1:]); r['diameterRule'] = f'תווית ø{r["D_mm"]} ליד ההסתעפות'; r['diameterStatus'] = 'source'
        else:
            r['D_mm'] = None; r['diameterRule'] = 'אין תווית קוטר'; r['diameterStatus'] = 'missing'
        r['material'] = M['waterMaterial']['name']; r['materialStatus'] = M['waterMaterial']['status']
        r['coverDepth_m'] = M['waterCover_m']; r['levelStatus'] = 'provisional'
        r['levelRule'] = f'עומק כיסוי {M["waterCover_m"]:.2f} מ\' מתחת לפני הפיתוח (זמני – לא כתוב בתוכנית)'
    # roof: cold feed riser -> heater, heater -> hot-water manifold
    roof = [w for w in R['water'] if w['floor'] == 'roof']
    for w in roof:
        sys_ = 'hot' if w['hot'] else 'cold'
        runs.append({'id': f'{"HW" if w["hot"] else "CW"}R{len(runs)}@roof', 'floor': 'roof', 'system': sys_, 'pts': [P(p) for p in w['pts']], 'D_mm': None,
                     'diameterRule': 'אין תווית קוטר', 'diameterStatus': 'missing', 'material': M['waterMaterial']['name'], 'materialStatus': M['waterMaterial']['status'],
                     'levelStatus': 'provisional', 'levelRule': f'על פני הגג (+{M["roofTopRel"]:.2f}) על תומכים {M["roofPipeSupport_m"]:.2f} מ\' (זמני)', 'ends': [None, None]})
    return nodes, runs


def struct():
    fr, fg, bas = J('data/structure/framing.json'), J('data/structure/floor-ground.json'), J('data/structure/basement.json')
    def beam(b):
        (e1, n1), (e2, n2) = b['axisITM']; L = math.dist((e1, n1), (e2, n2)); ux, uy = (e2 - e1) / L, (n2 - n1) / L; hw = b['width_m'] / 2
        return Polygon([(e1 - uy * hw, n1 + ux * hw), (e2 - uy * hw, n2 + ux * hw), (e2 + uy * hw, n2 - ux * hw), (e1 + uy * hw, n1 - ux * hw)])
    E = []
    for w in fr['basementWalls']: E.append(('קיר מרתף', w['id'], Polygon(w['footprintITM'], w.get('holesITM') or []), w['bottomRel'], w['topRel'], w['status']))
    for b in fr['groundBeams']:
        if b.get('axisITM'): E.append(('קורת יסוד', b['id'], beam(b), b['bottomRel'], b['topRel'], b['status']))
    for w in fg['walls']: E.append(('קיר בטון קומת קרקע', w['id'], Polygon(w['footprintITM'], w.get('holesITM') or []), w['bottomRel'], w['topRel'], w['status']))
    for c in fg['columns']: E.append(('עמוד קומת קרקע', c['id'], Polygon(c['footprintITM']), c['bottomRel'], c['topRel'], c['status']))
    for b in fg['ceiling']['beams']:
        if b.get('axisITM'): E.append(('קורת תקרה +3.70', b['id'], beam(b), b['bottomRel'], b['topRel'], b['status']))
    slabs = {'basementSlab': [(Polygon(s['outlineITM'], s.get('holesITM') or []), s['top'] - s['thickness_m'], s['top']) for s in fr['slabs'] if s.get('top') is not None and s.get('thickness_m')],
             'groundSlab': [(Polygon(s['footprintITM'], s.get('holesITM') or []), s['bottomRel'], s['topRel']) for s in fg['slab']],
             'ceiling': [(Polygon(s['footprintITM'], s.get('holesITM') or []), s['bottomRel'], s['topRel']) for s in fg['ceiling']['slab']]}
    return E, slabs, Polygon(bas['outlineITM'])


def stacks_vertical(nodes, byid, runs, lvl, M):
    """Each stack צ.א n as a 3D polyline from its base to the vent above the roof, through the floor positions of the drawings."""
    out = []
    first_inv = H0 + M['firstFloorBranchInvertAtStack']
    roof_top = H0 + M['roofTopRel']; roof_under = roof_top - M['roofSlabThickness_m']
    for n in sorted({x['stack'] for x in nodes if x['kind'] == 'stack'}):
        fl = {x['floor']: x for x in nodes if x['kind'] == 'stack' and x['stack'] == n}
        pts, notes = [], []
        if 'unit' in fl:
            base = min(r['ILup'] for r in runs if fl['unit']['id'] in r['ends'] and 'ILup' in r)
            u = fl['unit']; pts.append([u['E'], u['N'], r3(base)])
            g = fl['ground']
            if dist((u['E'], u['N']), (g['E'], g['N'])) > 0.05:
                hh = H0 + M['groundOffsetRel']
                pts += [[u['E'], u['N'], r3(hh)], [g['E'], g['N'], r3(hh + dist((u['E'], u['N']), (g['E'], g['N'])))]]
                notes.append(f'הסטה מתחת לרצפת הקרקע ({M["groundOffsetRel"]:+.2f}, זמני)')
        else:
            g = fl['ground']
            leaving = [r for r in runs if r['ends'][0] == g['id'] and r['floor'] == 'ground' and r['ends'][1] in byid and byid[r['ends'][1]]['cls'] == 'chamber']
            base = leaving[0]['ILup'] if leaving else lvl.get(g['id'])
            pts.append([g['E'], g['N'], r3(base)])
        f = fl['first']; g = fl['ground']
        if dist((g['E'], g['N']), (f['E'], f['N'])) > 0.05:
            hh = H0 + M['firstOffsetRel']
            pts += [[g['E'], g['N'], r3(hh)], [f['E'], f['N'], r3(min(hh + dist((g['E'], g['N']), (f['E'], f['N'])), first_inv - 0.10))]]
            notes.append(f'הסטה בתקרת הקרקע ({M["firstOffsetRel"]:+.2f}, זמני)')
        pts.append([f['E'], f['N'], r3(first_inv)])
        r_ = fl['roof']
        if dist((f['E'], f['N']), (r_['E'], r_['N'])) > 0.05:
            hh = roof_under - 0.30
            pts += [[f['E'], f['N'], r3(hh)], [r_['E'], r_['N'], r3(hh + 0.15)]]
            notes.append(f'הסטה מתחת לתקרת הגג ({dist((f["E"], f["N"]), (r_["E"], r_["N"])):.2f} מ\' אופקית, זמני)')
        pts.append([r_['E'], r_['N'], r3(roof_top + M['ventAboveRoof_m'])])
        # drop consecutive duplicates
        clean = [pts[0]] + [q for a, q in zip(pts[:-1], pts[1:]) if math.dist(a, q) > 0.01]
        out.append({'id': f'STACK{n}', 'stack': n, 'system': 'sewage', 'kind': 'stack', 'D_mm': 110, 'material': 'HDPE', 'pts3d': clean,
                    'floors': sorted(fl), 'title': f'קולטן צ.א {n} – HDPE ø110 (שופכין ואוויר)', 'notes': notes, 'status': 'source',
                    'levelStatus': 'provisional', 'levelRule': 'מיקום בכל קומה מהתוכניות; מפלס הבסיס מהקו לשוחה; גובה ההסטות וקצה האוורור מעל הגג – זמניים',
                    'source': f'{G.DXF} – עיגולי מגנטה + תוויות צ.א {n} בכל קומה; הערה "העתקה מקבילית"'})
    return out


def rain(nodes, byid, M):
    runs = []
    roof_top = H0 + M['roofTopRel']; first = H0 + 3.83
    for rd, dp in M['rain']['roofDrainToDownpipe']:
        a, b = byid[rd], byid[dp]
        runs.append({'id': f'RN-{rd}', 'floor': 'roof', 'system': 'rain', 'pts3d': [[a['E'], a['N'], r3(roof_top - 0.05)], [b['E'], b['N'], r3(roof_top - 0.05)]],
                     'D_mm': 50, 'material': 'PVC', 'ends': [rd, dp], 'status': 'source', 'levelStatus': 'provisional',
                     'levelRule': 'נקז גג 2" -> ראש הצמ"ג דרך המעקה (מפלס זמני)', 'source': 'רקע אדריכלי בתוכנית האינסטלציה – "נקז גג 2\"" ו"צינור 4\" צמ\"ג"'})
    for i, (top_floor, H) in enumerate([('roof', roof_top - 0.05), ('roof', roof_top - 0.05), ('first', first - 0.05)]):
        k = i + 1
        top, shoe = byid[f'DP{k}@{top_floor}'], byid[f'DPS{k}@ground']
        runs.append({'id': f'DP{k}', 'floor': 'ground', 'system': 'rain', 'kind': 'downpipe', 'pts3d': [[top['E'], top['N'], r3(H)], [shoe['E'], shoe['N'], r3(H0 + 0.10)]],
                     'D_mm': 110, 'material': 'PVC', 'ends': [top['id'], shoe['id']], 'status': 'source', 'levelStatus': 'provisional',
                     'levelRule': 'מגובה הגג/המרפסת עד חיבור תחתון בפני הקרקע (מפלסים זמניים)', 'title': f'צינור מי גשם (צמ"ג) 4" DP{k}',
                     'source': 'רקע אדריכלי – "צינור 4\" - צמ\"ג" + "חיבור תחתון למרזב" בקומות'})
    rd = byid['RD1@first']; dp = byid['DP3@first']
    runs.append({'id': 'RN-RD1@first', 'floor': 'first', 'system': 'rain', 'pts3d': [[rd['E'], rd['N'], r3(first - 0.08)], [dp['E'], dp['N'], r3(first - 0.08)]],
                 'D_mm': 50, 'material': 'PVC', 'ends': ['RD1@first', 'DP3@first'], 'status': 'source', 'levelStatus': 'provisional', 'levelRule': 'מפלס זמני',
                 'source': 'רקע אדריכלי – נקז מרפסת קומה א\' צפון + צמ"ג 4"'})
    bs = M['rain']['balconyToStack']; rd, st = byid[bs['drain']], byid[bs['stack']]
    runs.append({'id': 'RN-balcony', 'floor': 'first', 'system': 'sewage', 'pts3d': [[rd['E'], rd['N'], r3(first - 0.10)], [st['E'], st['N'], r3(first - 0.10 - 0.02 * dist((rd['E'], rd['N']), (st['E'], st['N'])))]],
                 'D_mm': 50, 'material': 'HDPE', 'ends': [bs['drain'], bs['stack']], 'status': 'derived', 'levelStatus': 'provisional', 'levelRule': 'מפלס זמני',
                 'source': bs['note']})
    return runs


def findings(nodes, byid, runs, stacks, rainruns, wnodes, wruns, R, M):
    E, slabs, basement = struct()
    F = []
    seen = set()
    def add(sev, title, text, at, ids, proposal=None, cat='structure', key=None):
        if key:
            if key in seen: return
            seen.add(key)
        F.append({'id': f'F{len(F) + 1}', 'severity': sev, 'category': cat, 'title': title, 'text': text, 'at': [r3(at[0]), r3(at[1]), r3(at[2])], 'elements': ids,
                  'proposal': proposal, 'status': 'finding'})
    # stacks & risers through concrete
    for s in stacks:
        P3 = s['pts3d']
        for a, b in zip(P3[:-1], P3[1:]):
            if abs(a[0] - b[0]) > 0.01 or abs(a[1] - b[1]) > 0.01: continue
            c = Point(a[0], a[1]).buffer(0.055)
            lo, hi = min(a[2], b[2]) - H0, max(a[2], b[2]) - H0
            for kind, eid, poly, bot, top, st in E:
                if c.intersects(poly) and min(hi, top) - max(lo, bot) > 0.05 and c.intersection(poly).area / c.area > 0.3:
                    add('critical', f'צ.א {s["stack"]} עובר בתוך {kind} {eid}',
                        f'הקולטן (ø110) במיקום שבתוכנית חודר את {kind} {eid} בין המפלסים {max(lo, bot):+.2f} ל-{min(hi, top):+.2f}. '
                        f'בטון מזוין – אי אפשר להעביר צינור בתוכו (הערה 8 של היועץ: צ.א לא יעבור בקורת בטון).' + ('' if st == 'source' else ' (גיאומטריית האלמנט בקירוב)'),
                        (a[0], a[1], (max(lo, bot) + min(hi, top)) / 2 + H0), [s['id'], eid],
                        'להזיז את הקולטן אל מחוץ לאלמנט (בתיאום עם הקונסטרוקטור), או לבצע הסטה ב-2 זוויות 45° מתחת לאלמנט – לאישורך', key=(s['id'], eid))
    for w in wnodes:
        if w['kind'] == 'riser':
            c = Point(w['E'], w['N']).buffer(0.02)
            for kind, eid, poly, bot, top, st in E:
                if kind.startswith('עמוד') and c.intersects(poly):
                    add('critical', f'עולה המים בתוך {kind} {eid}', f'{w["title"]} מסומן בתוך {kind} {eid} (בטון).', (w['E'], w['N'], H0 + 1.0), [w['id'], eid],
                        'להעביר את העולה לצד העמוד, בתוך קיר בלוקים / פיר – לאישורך', 'water')
    rby = {r['id']: r for r in runs}
    def group_of(r):
        seen_ = set()
        while r and r['id'] not in seen_:
            seen_.add(r['id']); d = byid[r['down']]
            if d['cls'] in ('chamber',) or d['kind'] == 'stack': return d['id']
            nxt = [q for q in runs if q.get('up') == r['down'] and q is not r]
            r = nxt[0] if nxt else None
        return '?'
    groups_b = defaultdict(list)
    # sewer runs vs concrete / basement space
    for r in runs:
        if 'ILup' not in r or r['floor'] != 'ground': continue
        L = LineString(r['pts']); Dm = r['D_mm'] / 1000
        for kind, eid, poly, bot, top, st in E:
            x = L.intersection(poly)
            if x.is_empty or x.length < 0.03: continue
            t = L.project(x.centroid); H = r['ILup'] - (r['ILup'] - r['ILdown']) * t / L.length + Dm / 2
            if bot - 0.05 <= H - H0 <= top + 0.05:
                sev = 'major' if kind == 'קיר מרתף' else 'minor'
                add(sev, f'{r["id"]} חוצה {kind} {eid} – נדרש שרוול' + (' אטום' if kind == 'קיר מרתף' else ''),
                    f'צינור ø{r["D_mm"]} במפלס {H - H0:+.2f} עובר דרך {kind} {eid}. ' + ('קיר מרתף מתחת לפני הקרקע – שרוול עם אוגן אטימה (Puddle flange) ואטם. ' if kind == 'קיר מרתף' else 'שרוול ליציקה בתיאום הקונסטרוקטור. ')
                    + ('' if st == 'source' else '(מיקום האלמנט בקירוב – עד IFC)'), (x.centroid.x, x.centroid.y, H), [r['id'], eid], None, 'sleeve')
        inb = L.intersection(basement)
        if not inb.is_empty and inb.length > 0.3:
            H = (r['ILup'] + r['ILdown']) / 2
            if H - H0 < -0.45: groups_b[group_of(r)].append((r, inb, H))
    for g, lst in groups_b.items():
        H = [x[2] for x in lst]; c = lst[0][1].centroid
        add('major', f'ניקוז דרך {g}: {len(lst)} קטעים בתוך חלל המרתף',
            f'הקטעים {", ".join(x[0]["id"] for x in lst)} נמצאים מעל שטח המרתף, במפלסים {min(H) - H0:+.2f} עד {max(H) - H0:+.2f}, '
            f'כלומר נמוך מתקרת המרתף (‎-0.40). הם יהיו תלויים בתוך יחידת הדיור (גובה נטו 2.20) ויחייבו תקרה מונמכת, או שנדרש תוואי אחר.',
            (c.x, c.y, sum(H) / len(H)), [x[0]['id'] for x in lst], 'לנקז את קבועות הקומה שמעל המרתף בתקרת המרתף לפיר אחד ולצאת אופקית מעל קיר המרתף – לאישורך', 'routing')
    groups_f = defaultdict(list)
    for r in runs:
        if r['floor'] != 'first' or 'ILup' not in r: continue
        crown = max(r['ILup'], r['ILdown']) + r['D_mm'] / 1000
        if crown > H0 + 3.85 - 0.02: groups_f[group_of(r)].append((r, crown))
    for g, lst in groups_f.items():
        cr = max(x[1] for x in lst); r0 = max(lst, key=lambda x: x[1])[0]
        add('major', f'קומה א\' → {g}: אין מקום לצנרת במילוי הרצפה',
            f'מילוי של 15 ס"מ בלבד (+3.70 עד +3.85). בקטעים {", ".join(x[0]["id"] for x in lst)} קודקוד הצינור מגיע עד {cr - H0:+.2f} – מעל הריצוף.',
            (r0['pts'][0][0], r0['pts'][0][1], cr), [x[0]['id'] for x in lst], 'הנמכת התקרה בחדרים הרטובים (רצפה שקועה) או צנרת מתחת לתקרה עם תקרה מונמכת בקרקע – לאישורך', 'routing')
    # basement runs vs the basement slab (suspended slab on piles)
    for r in runs:
        if r['floor'] != 'unit' or 'ILup' not in r: continue
        L = LineString(r['pts'])
        for poly, bot, top in slabs['basementSlab']:
            x = L.intersection(poly)
            if x.is_empty or x.length < 0.3: continue
            crown = max(r['ILup'], r['ILdown']) + r['D_mm'] / 1000
            if crown > H0 + bot - 0.02 and min(r['ILup'], r['ILdown']) < H0 + top:
                add('major', f'{r["id"]} עובר בתוך רצפת המרתף', f'הקו (ø{r["D_mm"]}, ‏{min(r["ILup"], r["ILdown"]):.2f}–{crown:.2f}) חוצה את רצפת המרתף התלויה '
                    f'({H0 + bot:.2f}–{H0 + top:.2f}) לאורך {x.length:.2f} מ\'. מתחת לרצפה יש ארגזי הפרדה וקורות; לא ברור איך הצינור עובר.',
                    (x.centroid.x, x.centroid.y, crown), [r['id']], 'תוואי היקפי בחצר / סביב המרתף אל תא השאיבה – לאישורך', 'routing', key=(r['id'], 'slab'))
    # chambers: cover vs finished level, distance to the boundary, drops
    lot = Polygon([tuple(p[:2]) for p in J('data/site/plot-5187.json')['ring']])
    wall_t = {0.6: 0.08, 0.8: 0.10, 1.0: 0.12}
    for n in nodes:
        if n['cls'] != 'chamber' or n['id'] in ('S-0', 'PC-1'): continue
        sp = sorted(R['spots'], key=lambda q: dist((q['E'], q['N']), (n['E'], n['N'])))[0]
        if dist((sp['E'], sp['N']), (n['E'], n['N'])) < 3.5 and abs(sp['H'] - n['TL']) > 0.04:
            add('major' if abs(sp['H'] - n['TL']) > 0.08 else 'minor', f'{n["id"]}: רום המכסה {n["TL"]:.2f} מול פיתוח {sp["H"]:.2f}',
                f'הפרש {(n["TL"] - sp["H"]) * 100:+.0f} ס"מ מגובה הפיתוח הסמוך ({dist((sp["E"], sp["N"]), (n["E"], n["N"])):.1f} מ\' מהשוחה). המכסה צריך להיות בדיוק במפלס הריצוף.',
                (n['E'], n['N'], n['TL']), [n['id']], f'טבעות הגבהה {abs(n["TL"] - sp["H"]) * 100:.0f} ס"מ' if sp['H'] > n['TL'] else 'הנמכת חוליית הראש', 'chamber')
        outer = n['D_m'] / 2 + wall_t.get(n['D_m'], 0.1)
        d = lot.exterior.distance(Point(n['E'], n['N']))
        if d < outer + 0.15:
            add('major', f'{n["id"]} צמודה לגבול המגרש', f'מרכז השוחה {d:.2f} מ\' מהגבול; רדיוס חיצוני של חוליה ø{n["D_m"] * 100:.0f} כ-{outer:.2f} מ\'. הדופן נוגעת בקו הגבול ובחומה ההיקפית וביסודה.',
                (n['E'], n['N'], n['TL']), [n['id']], 'הזזת השוחה פנימה (≥0.3 מ\' מדופן החומה) – לאישורך', 'chamber')
    for r in runs:
        if r.get('dropAtDownstream_m', 0) > 0.3:
            c = byid[r['down']]
            add('major', f'מפל {r["dropAtDownstream_m"]:.2f} מ\' בכניסה ל-{c["id"]}', f'{r["id"]} נכנס ל-{c["id"]} ב-{r["ILdown"]:.2f} והתחתית ב-{c["IL"]:.2f}. בתוכנית לא מסומן מפל.',
                (c['E'], c['N'], r['ILdown']), [r['id'], c['id']], 'מפל חיצוני (הסתעפות + צינור אנכי + קשת) לפי ת"י 1205 – לאישורך', 'chamber')
    # open ends / design ends
    for n in nodes + wnodes:
        if n['kind'] in ('openEnd', 'designEnd'):
            add('major' if n['kind'] == 'openEnd' else 'info', ('סוף תכנון: ' if n['kind'] == 'designEnd' else 'קצה פתוח: ') + n['title'], n.get('source', ''),
                (n['E'], n['N'], H0 + (0.0 if n['floor'] in ('ground', 'site') else 3.85)), [n['id']], None, 'openEnd')
    for d in ('DPS1@ground', 'DPS2@ground', 'DPS3@ground'):
        n = byid[d]
        add('major', f'מי גשם: {d} – אין המשך מהחיבור התחתון', 'צינור המי גשם יורד לפני הקרקע. אין בתוכנית צינור או יעד (בור חלחול / תעלה / רחוב). אסור לחבר לביוב.',
            (n['E'], n['N'], H0), [d], 'קו ניקוז ø110 לבור החלחול בגינה הצפונית / לתעלת הניקוז – לאישורך', 'rain')
    # stack offsets / vents
    for st in stacks:
        for nt in st['notes']:
            if 'אופקית' in nt:
                add('major' if '2.' in nt.split('(')[1][:3] else 'minor', f'צ.א {st["stack"]}: הסטה בין קומה א\' לגג', f'המיקום בגג שונה מהמיקום בקומה א\': {nt}. בתוכנית אין פרט להסטה.',
                    (st['pts3d'][-2][0], st['pts3d'][-2][1], st['pts3d'][-2][2]), [st['id']], 'קולטן ישר עד הגג באותו מיקום, או הסטה ב-2×45° עם ביקורת – לאישורך', 'routing')
    add('minor', 'קצה האוורור מעל הגג – גובה לא כתוב', f'כל ששת הקולטנים מסתיימים בגג. בתוכנית אין גובה יציאה מעל הגג; במודל {M["ventAboveRoof_m"]:.2f} מ\' (זמני).',
        (stacks[0]['pts3d'][-1][0], stacks[0]['pts3d'][-1][1], stacks[0]['pts3d'][-1][2]), [x['id'] for x in stacks], 'לקבוע לפי הל"ת (גג שאין בו שימוש / גג בשימוש) – לאישורך', 'code')
    pc = byid['PC-1']; s2 = byid['S-2']
    add('minor', 'קו הסניקה מהמרתף: ø75 PEX בתוכנית, HDPE Ø3" בפרט', 'בתוכנית הקרקע כתוב "ø75 PEX". בפרט "תא איסוף עם משאבה" של היועץ: '
        'משאבה טבולה גורסת 20 מק"ש בעומד 10 מ\' (תלת-פאזי), שסתום אל-חוזר, קו HDPE Ø3" וגמל 50 ס"מ מעל רום מכסה השוחה הקולטת '
        f'(שוחה 2: {s2["TL"] + 0.5:.2f}). אותו קוטר נומינלי, חומר שונה. תוואי העלייה והגמל לא משורטטים בתוכנית.', (pc['E'], pc['N'], pc['TL']), ['PC-1', 'S-2'],
        'לקבוע חומר אחד (HDPE לפי הפרט) – לאישור היועץ', 'pumped')
    add('major', 'תא השאיבה PC-1 (ø60) כתא ביוב ליחידות הדיור', 'לפי הערת היועץ, ריקון תא הביוב של קומת המרתף נעשה במשאבה טבולה גורסת דרך גמל (פרט "תא איסוף עם משאבה"). '
        'התא היחיד בתוכנית הוא PC-1: ø60, עומק 1.20, מתוכנן לניקוז החצרות, יושב בפתח הכניסה ליחידה 1. לשפכים של 2 יחידות: קטן למשאבה עם מצוף ונפח הפעלה, '
        'ובתקלה השפכים יעלו במקלחות היחידות (277.90) ובמכסה (277.88).', (pc['E'], pc['N'], pc['TL']), ['PC-1'],
        'הגדלה ל-ø100, מכסה אטום לריח, התראת מפלס גבוה ומשאבה שנייה לגיבוי – לאישור היועץ', 'pumped')
    add('major', 'יחידת הדיור במרתף – אין תכנון אינסטלציה', 'בתוכנית המרתף כתוב "מרתף שירות – אחסנה בלבד" ואין קבועות. לפי אביחי (07.11.2026) זו יחידת דיור עם קבועות. '
        'הערת היועץ "ריקון תא ביוב המנקז את קומת המרתף … משאבה טבולה" מתייחסת לתא שלא קיים בתוכנית.', (pc['E'] + 3, pc['N'] + 3, H0 - 2.6), ['PC-1'],
        'נדרש תכנון של היועץ: קבועות, תא שאיבה לשופכין עם משאבה (לא תא החצרות), אוורור – לאישורך', 'missing')
    hr = R['hoseReel']
    add('minor', 'גלגלון כיבוי אש – אין קו הזנה משורטט', 'החץ של ההערה "גלגלון 3/4\" … אל חוזר כפול" מצביע על נקודה ליד החומה המערבית, 0.8 מ\' מקו המים הראשי; קו ההזנה לא משורטט.',
        (hr[0], hr[1], H0), ['WATER'], 'הסתעפות ø25 מהקו הראשי עם אל-חוזר כפול לפי הפרט – לאישורך', 'water')
    for t in [x for x in R['taps'] if x['floor'] == 'first']:
        add('minor', 'ברז גן במרפסת קומה א\' – אין קו הזנה', '"יש להתקין ברז גן לשירות במרפסת" – הנקודה מסומנת, הקו אליה לא.', (t['E'], t['N'], H0 + 3.85 + 0.6), ['WATER'], None, 'water')
    mig = (179586.361, 576235.702); m = byid.get('WM@site') or {'E': R['meter'][0], 'N': R['meter'][1]}
    add('minor', 'חיבור המים לעירייה', f'קצה ההכנה העירונית (מפה למשתכן, UT-W) 0.37 מ\' בתוך המגרש; מערכת המדידה של היועץ {dist(mig, R["meter"]):.2f} מ\' ממנה, והקו מתחיל {dist(mig, (179586.69, 576236.31)):.2f} מ\' ממנה. '
        'אין קטע מחבר משורטט; היועץ: "נא לוודא מיקום טרם הביצוע".', (mig[0], mig[1], H0 - 0.5), ['WM@site'], 'קטע חיבור מקצה ההכנה לשעון – לאישורך', 'water')
    pof = byid['POF@ground']
    add('major', 'ניקוז חדר המכונות של הבריכה לשוחה 5', f'הקו ø110 מחדר המכונות (רצפה 278.33) לשוחה 5 (I.L 279.48). ניקוז רצפת חדר המכונות בגרביטציה אינו אפשרי; '
        f'רק גלישה (O.F) שמעל {279.48 + 0.02 * 9.16:.2f}. הפרט מציין משאבה טבולה כחלופה.', (pof['E'], pof['N'], 279.66), ['POF@ground', 'S-5'], 'משאבה טבולה בבור האיזון + גמל לשוחה 5 – לאישורך', 'pool')
    s5 = byid['S-5']
    add('minor', 'שוחה 5 (ø60) – 4 כניסות + יציאה ø160', 'ענפי ø110 מצ.א 6, מהברביקיו ומחדר המכונות, קו הסניקה ø63 של הבריכה, ויציאה ø160. בחוליה ø60 – לבדוק מקום לכניסות ולתיעול.',
        (s5['E'], s5['N'], s5['TL']), ['S-5'], 'שוחה ø80 – לאישורך', 'chamber')
    add('info', 'מים חמים – אין חלוקה', 'בגג: קו מהדוד ל"מחלק מים חמים". אין ירידות לקומות, אין קטרים, אין צנרת נחושת בין הדוד לקולטים (הערה 14), ואין נפח דוד / מספר קולטים.',
        (byid['S-1']['E'], byid['S-1']['N'], H0 + 7), ['WATER'], None, 'missing')
    return F


def export(nodes, runs, lines3d, F, R):
    KEEP_N = ('id', 'kind', 'floor', 'E', 'N', 'title', 'status', 'source', 'D_m', 'TL', 'IL', 'H_m', 'stack', 'rotation_deg', 'block', 'gap_m')
    SYS = {'sewage': 'sewage', 'pumped': 'sewage', 'rain': 'drainage', 'cold': 'water', 'hot': 'water'}
    out_runs = []
    for r in runs:
        src = r.get('source') or (f'{G.PDF[r["floor"]]} – קו ירוק (קו מרכז הצינור), ממוקם ב-ITM (georef.py)' if r['system'] in ('sewage', 'pumped') else f'{G.DXF} – שכבת cold water')
        rec = {'id': r['id'], 'system': r['system'], 'tagSystem': SYS[r['system']], 'floor': 'site' if (r['system'] == 'cold' and r['floor'] == 'ground') or (r['floor'] == 'ground' and r.get('ends', ['', ''])[1].startswith('S-')) else r['floor'],
               'drawnOn': r['floor'], 'role': r.get('role'), 'from': r['ends'][0], 'to': r['ends'][1], 'pts': r['pts'], 'length_m': r3(length(r['pts'])),
               'D_mm': r.get('D_mm'), 'material': r.get('material'), 'diameterRule': r.get('diameterRule'), 'ILup': r.get('ILup'), 'ILdown': r.get('ILdown'),
               'slope': r.get('slope'), 'dropAtDownstream_m': r.get('dropAtDownstream_m'), 'coverDepth_m': r.get('coverDepth_m'),
               'levelStatus': r.get('levelStatus'), 'levelRule': r.get('levelRule'), 'status': r.get('status', 'source'), 'source': src}
        out_runs.append({k: v for k, v in rec.items() if v is not None})
    out = {'_doc': 'שכבת האינסטלציה – רשת כפי שתוכננה ע"י יועץ האינסטלציה (נוצר ע"י tools/plumbing/extract.py + build.py; לא לערוך ידנית). '
                   'pts = ITM [E, N]; ILup/ILdown = רום תחתית הצינור (מוחלט) בקצה העליון/התחתון; pts3d = [E, N, H] מוחלט (H=null: לפי פני הקרקע פחות coverDepth_m).',
           'source': [G.DXF, G.DETAILS] + list(G.PDF.values()), 'placement': R['placement'], 'pdfFit': R['pdfFit'], 'profile': R['profile'],
           'nodes': [{k: n[k] for k in KEEP_N if k in n} | ({'tagSystem': 'drainage'} if n['kind'] in ('downpipe', 'downpipeShoe', 'roofDrain', 'soakawayPit') else {}) for n in nodes],
           'runs': out_runs, 'lines3d': lines3d, 'findings': F,
           'summary': {'runs': len(out_runs), 'nodes': len(nodes), 'findings': {k: sum(1 for f in F if f['severity'] == k) for k in ('critical', 'major', 'minor', 'info')}}}
    os.makedirs(os.path.join(ROOT, 'data/plumbing'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'data/plumbing/network.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def main():
    R = J('tools/plumbing/cache/raw.json'); M = J('tools/plumbing/manual-readings.json')
    for l in R['labels']: l.setdefault('rot', None)
    nodes, byid, runs = sewer(R, M)
    # extra runs (manual readings) – before the levels, so that what drains through them gets a level too
    for x in M['extraRuns']:
        a, b = byid[x['from']], byid[x['to']]
        runs.append({'id': f'SWX-{a["id"]}', 'floor': x['floor'], 'system': 'sewage', 'pts': [[a['E'], a['N']], [b['E'], b['N']]], 'ends': [a['id'], b['id']],
                     'manualDiameter': (x['D_mm'], x['material']), 'source': x['source']})
    lvl, stack_nodes = sewer_levels(R, M, nodes, byid, runs, R['labels'])
    diameters(runs, byid, M)
    for r in runs:
        if r.get('manualDiameter'):
            r['D_mm'], r['material'] = r.pop('manualDiameter'); r['diameterRule'] = 'מחבר אסלה ø110 (קריאה ידנית)'
    wn, wr = water(R, M)
    wbyid = {n['id']: n for n in wn}
    for r in [r for r in wr if r['floor'] == 'roof']:
        for k in (0, 1):
            m = min(M['roofEnds'], key=lambda m: dist(m['at'], end_pt(r, k)))
            if m['node'] not in wbyid:
                n = {'id': m['node'], 'kind': m['kind'], 'cls': 'water', 'floor': 'roof', 'E': m['at'][0], 'N': m['at'][1], 'title': m['title'], 'status': m.get('status', 'source'), 'source': m['source']}
                wn.append(n); wbyid[n['id']] = n
            r['ends'][k] = m['node']
    sv = stacks_vertical(nodes, byid, runs, lvl, M)
    rr = rain(nodes, byid, M)
    allnodes = nodes + wn
    F = findings(nodes, byid, runs, sv, rr, wn, wr, R, M)
    out = {'nodes': allnodes, 'runs': runs + wr, 'stacks': sv, 'rain': rr, 'findings': F}
    # pump riser: PC-1 outlet -> up to the "camel" crest (50 cm above the T.L of the receiving chamber S-2) -> yard line
    pru, prg, s2 = byid['PRU@unit'], byid['PRG@ground'], byid['S-2']
    crest = s2['TL'] + 0.50
    pump3d = {'id': 'PUMP-RISER', 'system': 'pumped', 'floor': 'unit', 'kind': 'pumpRiser', 'D_mm': 75, 'material': 'PEX',
              'pts3d': [[pru['E'], pru['N'], r3(byid['PC-1']['TL'] - 0.25)], [pru['E'], pru['N'], r3(crest)], [prg['E'], prg['N'], r3(crest)], [prg['E'], prg['N'], None]],
              'ends': ['PRU@unit', 'PRG@ground'], 'title': 'קו סניקה – עלייה מתא השאיבה וגמל', 'status': 'derived', 'levelStatus': 'provisional',
              'levelRule': f'גמל ב-{crest:.2f} = רום שוחה 2 + 0.50 (הערת היועץ); תוואי העלייה לא משורטט – זמני',
              'source': 'הערה "ריקון תא ביוב המנקז את קומת המרתף … גמל 50 ס\"מ מעל לתא הביוב הקולט" + פרט משאבה טבולה'}
    for r in runs:
        if r.get('role') == 'pumped':
            if r['floor'] == 'unit':
                r.update(ILup=r3(byid['PC-1']['TL'] - 0.25), ILdown=r3(byid['PC-1']['TL'] - 0.25), slope=0.0, levelStatus='provisional', levelRule='יציאה מתא השאיבה (מפלס זמני)')
            else:
                r.update(coverDepth_m=M['waterCover_m'], levelStatus='provisional', levelRule=f'קו לחץ: עומק כיסוי {M["waterCover_m"]:.2f} מ\' (זמני)')
            r['status'] = 'source'
    soak = {'id': 'SOAK@site', 'kind': 'soakawayPit', 'cls': 'rain', 'floor': 'site', 'E': 179599.615, 'N': 576253.286, 'D_m': 0.59, 'TL': 280.33,
            'title': 'בור חלחול (מיקום בלבד)', 'status': 'source', 'source': f'{G.PDF["ground"]} – עיגול "בור חלחול" ליד 280.33 בגינה הצפונית; פרט עקרוני בקובץ הפרטים'}
    allnodes.append(soak)
    F.append({'id': f'F{len(F) + 1}', 'severity': 'major', 'category': 'rain', 'title': 'בור החלחול לא מחובר', 'text': 'בגינה הצפונית מסומן בור חלחול (פרט עקרוני בקובץ הפרטים) – אין אליו אף צינור.',
              'at': [soak['E'], soak['N'], soak['TL']], 'elements': ['SOAK@site', 'DP1', 'DP2', 'DP3'], 'proposal': 'לחבר אליו את צינורות המי גשם (DP1–DP3) בקו ø110 – לאישורך', 'status': 'finding'})
    export(allnodes, runs + wr, sv + rr + [pump3d], F, R)
    os.makedirs(os.path.join(ROOT, 'tools/plumbing/cache'), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, 'tools/plumbing/cache/net.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for r in runs:
        print(f"{r['id']:12s} {r.get('role',''):11s} {r['ends'][0]:>14s} -> {r['ends'][1]:<14s} L={length(r['pts']):5.2f} ø{r.get('D_mm')} {r.get('material','')} "
              f"IL {r.get('ILup','-')}->{r.get('ILdown','-')} s={r.get('slope')} {r.get('levelStatus')}")
    print('open ends:', [n['id'] for n in nodes + wn if n['kind'] == 'openEnd'])
    for r in wr: print(r['id'], r['ends'], r.get('D_mm'), round(length(r['pts']), 2))
    for x in sv: print(x['id'], x['pts3d'], x['notes'])
    for f in F: print(f['id'], f['severity'], f['title'])


if __name__ == '__main__':
    main()

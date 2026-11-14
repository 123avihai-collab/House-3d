#!/usr/bin/env python3
"""Data checks: manifest files exist and parse; every site record carries a source; no dimension is NaN;
provisional values are flagged; plot ring matches the control points."""
import json, math, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
errors = []
man = json.load(open(os.path.join(ROOT, 'data', 'manifest.json'), encoding='utf-8'))
D = {}
for k, p in man['files'].items():
    fp = os.path.join(ROOT, p)
    if not os.path.exists(fp): errors.append(f'missing {p}'); continue
    try: D[k] = json.load(open(fp, encoding='utf-8'))
    except Exception as e: errors.append(f'{p}: {e}')
def walk(o, path):
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)): errors.append(f'NaN at {path}')
    if isinstance(o, dict):
        for k, v in o.items(): walk(v, f'{path}.{k}')
    if isinstance(o, list):
        for i, v in enumerate(o): walk(v, f'{path}[{i}]')
for k, v in D.items(): walk(v, k)
# sources
for h in D['heights']['lotCorners'] + D['heights']['streetSpots']:
    if 'source' not in h: errors.append(f'height without source {h}')
for c in D['street']['contours']:
    if 'source' not in c: errors.append('contour without source')
for r in D['regions']['regions']:
    if 'source' not in r: errors.append(f'region {r["id"]} without source')
for p in D['parcels']['parcels']:
    if 'source' not in p: errors.append(f'parcel {p["parcel"]} without source')
# provisional flags
for l in D['neighbors']['lots']:
    if l['heightStatus'] != 'provisional' and D['neighbors']['rules']['maxHeightAboveEntrance_m']['status'] == 'provisional':
        errors.append('neighbor height status mismatch')
# plot ring passes through the 5 boundary points (<=1 mm)
ring = D['plot']['ring']
for name, p in D['plot']['points'].items():
    d = min(math.dist((p['E'], p['N']), tuple(q)) for q in ring)
    if d > 0.001: errors.append(f'plot ring misses point {name} by {d:.4f} m')
# every layer referenced by regions exists
layer_ids = {l['id'] for g in D['layers']['groups'] for l in g['layers']}
for r in D['regions']['regions']:
    if r['layer'] not in layer_ids: errors.append(f'region {r["id"]} unknown layer {r["layer"]}')
# stage 2: structure
if 'piles' in D:
    P = D['piles']['piles']
    if len(P) != D['piles']['count']: errors.append('piles count mismatch')
    ids = [p['id'] for p in P]
    if len(set(ids)) != len(ids): errors.append('duplicate pile ids')
    for p in P:
        if 'source' not in p: errors.append(f'pile {p["id"]} without source')
        if not p.get('xlsxCheck', {}).get('match'): errors.append(f'pile {p["id"]} does not match the xlsx table')
        if abs(p['tipRel'] - (p['headRel'] - p['length_m'])) > 1e-6: errors.append(f'pile {p["id"]} tip != head - L')
        if not (0.3 <= p['diameter_m'] <= 1.2): errors.append(f'pile {p["id"]} diameter out of range')
        # inside lot 5187
        x, y = p['E'], p['N']; inside = False; r = ring
        for i in range(len(r)):
            (x1, y1), (x2, y2) = r[i], r[i - 1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: inside = not inside
        if not inside: errors.append(f'pile {p["id"]} outside lot 5187')
if 'excavation' in D:
    X = D['excavation']
    if 'source' not in X: errors.append('excavation without source')
    if abs(X['bottomAbs'] - (D['origin']['H0'] + X['bottomRel'])) > 1e-6: errors.append('excavation bottomAbs != H0 + bottomRel')
    for b in X['bottomBuildUp']:
        if 'source' not in b: errors.append(f'excavation build-up without source: {b["item"]}')
    if X['workingSpace_m'] is not None and X.get('workingSpaceStatus') not in ('provisional', 'approved'): errors.append('working space status missing')
if 'basement' in D and 'source' not in D['basement']: errors.append('basement without source')
if 'framing' in D:
    for k in ('basementWalls', 'slabs', 'groundBeams'):
        for r in D['framing'][k]:
            if 'source' not in r: errors.append(f'framing {k} {r.get("id")} without source')
            if r.get('status') not in ('source', 'provisional', 'approx', 'missing'): errors.append(f'framing {k} {r.get("id")} bad status')
if 'floorGround' in D:
    G = D['floorGround']
    recs = [('slab', r) for r in G['slab']] + [('walls', r) for r in G['walls']] + [('columns', r) for r in G['columns']] + \
           [('ceiling.slab', r) for r in G['ceiling']['slab']] + [('ceiling.beams', r) for r in G['ceiling']['beams']]
    for k, r in recs:
        if 'source' not in r: errors.append(f'floorGround {k} {r.get("id")} without source')
        if r.get('status') not in ('source', 'provisional', 'approx', 'missing'): errors.append(f'floorGround {k} {r.get("id")} bad status')
        if k in ('walls', 'columns') and not (r['topRel'] > r['bottomRel']): errors.append(f'floorGround {k} {r.get("id")} top <= bottom')
# construction-step slider: every step id unique, every stage reachable
if 'tags' in D and 'sequence' in D['tags']:
    ids = [s['id'] for s in D['tags']['sequence']]
    if len(ids) != len(set(ids)): errors.append('tags.sequence: duplicate step ids')
    for st in D['tags']['stages']:
        if not any(x['stage'] == st['id'] and not x.get('floor') for s in D['tags']['sequence'] for x in s['includes']):
            errors.append(f'tags.sequence: stage {st["id"]} has no stage-only step')
if 'ownerChanges' in D:
    for c in D['ownerChanges']['changes']:
        for k in ('id', 'date', 'title', 'description', 'source', 'status', 'approvals'):
            if k not in c: errors.append(f'owner change {c.get("id")} missing {k}')
if 'ownerChangesGeometry' in D:
    for cid, g in D['ownerChangesGeometry']['changes'].items():
        for k, w in g.get('wallPieces', {}).items():
            if 'source' not in w: errors.append(f'{cid} wall piece {k} without source')
        sp = g.get('slabSplit')
        if sp and abs(sp['check']['sumArea_m2'] - sp['check']['original_m2']) > 0.01: errors.append(f'{cid} slab split area mismatch')
# 2D pipe editor files (manifest.editorFiles): routes.json = source of truth of the proposal routes
for k, p in man.get('editorFiles', {}).items():
    if k.startswith('_'): continue
    fp = os.path.join(ROOT, p)
    if not os.path.exists(fp): errors.append(f'missing {p}'); continue
    try: D[k] = json.load(open(fp, encoding='utf-8')); walk(D[k], k)
    except Exception as e: errors.append(f'{p}: {e}')
if 'routes' in D:
    R = D['routes']; ids = [r['id'] for r in R['runs']]
    if len(ids) != len(set(ids)): errors.append('routes: duplicate run ids')
    sysok = set(D['planEditor']['systems']['order']) if 'planEditor' in D else None
    for r in R['runs']:
        if 'source' not in r: errors.append(f'routes run {r["id"]} without source')
        if r.get('status') not in ('proposal', 'manual', 'provisional', 'source'): errors.append(f'routes run {r["id"]} bad status {r.get("status")}')
        if sysok and r['system'] not in sysok: errors.append(f'routes run {r["id"]} unknown system {r["system"]}')
        if len(r['vertices']) < 2: errors.append(f'routes run {r["id"]} < 2 vertices')
        for v in r['vertices']:
            if len(v) != 3 or not all(isinstance(c, (int, float)) for c in v[:2]) or not (v[2] is None or isinstance(v[2], (int, float))): errors.append(f'routes run {r["id"]} bad vertex {v}')
        s = r.get('simplify')
        if s and s['maxDev_m'] > s['tol_m'] + 1e-6: errors.append(f'routes run {r["id"]} simplified beyond tolerance ({s["maxDev_m"]} m)')
    for n in R['nodes']:
        if 'source' not in n: errors.append(f'routes node {n["id"]} without source')
if 'planBackground' in D and 'source' not in D['planBackground']: errors.append('plan-background without source')
# tiling workshop (src/tiling): catalog options + the choices kept in the repo
if 'tilingCatalog' in D:
    TC = D['tilingCatalog']
    if 'source' not in TC: errors.append('tiling catalog without source')
    for s_ in TC['sizes']:
        if not (s_['w_m'] > 0 and s_['l_m'] >= s_['w_m'] and s_.get('perBox', 0) >= 1): errors.append(f'tiling size {s_["id"]} bad')
    ids = {k: {x['id'] for x in TC[k]} for k in ('sizes', 'finishes', 'patterns', 'directions', 'origins')}
    for k, v in (D.get('tilingLayout', {}).get('rooms') or {}).items():
        for f_, grp in (('size', 'sizes'), ('finish', 'finishes'), ('pattern', 'patterns'), ('direction', 'directions'), ('origin', 'origins')):
            if v.get(f_) not in ids[grp] and not (f_ == 'size' and v.get(f_) == 'custom'): errors.append(f'tiling layout {k}: unknown {f_} {v.get(f_)}')
    if 'tilingLayout' in D and 'source' not in D['tilingLayout']: errors.append('tiling layout without source')
    DS = D.get('tilingDoorStrips')
    if DS:
        keys = {r['room'] for r in D['tiling']['rooms']} | {r['room'] for r in (D.get('tilingExterior') or {}).get('rooms', [])}   # an outside door → the exterior zone
        for s_ in DS['strips']:
            if 'source' not in s_ or s_['room'] not in keys or len(s_['ringITM']) < 3 or not s_['area_m2'] > 0: errors.append(f'door strip {s_.get("id")} bad')
# street in front of the lot (tools/extract_front_street.py)
if 'frontStreet' in D:
    F = D['frontStreet']
    if 'source' not in F: errors.append('frontStreet without source')
    for z in F['zones']:
        if 'source' not in z: errors.append(f'frontStreet zone {z["id"]} without source')
        if z['heights'] == 'derived' and z.get('heightStatus') != 'provisional': errors.append(f'frontStreet zone {z["id"]} derived heights not provisional')
    if F.get('ownerLevels') and F['ownerLevels'].get('status') != 'owner': errors.append('frontStreet ownerLevels without owner status')
    if F['edgeStone'].get('status') != 'provisional': errors.append('frontStreet edge stone reveal is not in the sources – must stay provisional')
    if abs(F['section']['measuredWidth_m'] - F['section']['total_m']) > 0.05: errors.append('frontStreet width differs from the typical section')
    if abs(F['elevation']['chainOrigin']['endCheck']['deviation_m']) > 0.05: errors.append('frontStreet elevation chain does not close on corner 2420')
    if any(abs(v / F['elevation']['nominal_pt_per_m'] - 1) > 0.01 for v in F['elevation']['segmentScale_pt_per_m']): errors.append('frontStreet elevation scale is not 1:100')
if errors:
    print('DATA ERRORS:'); [print(' -', e) for e in errors]; sys.exit(1)
print(f'data OK: {len(D)} files')

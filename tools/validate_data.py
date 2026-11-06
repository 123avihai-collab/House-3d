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
            if r.get('status') not in ('source', 'provisional', 'missing'): errors.append(f'framing {k} {r.get("id")} bad status')
if errors:
    print('DATA ERRORS:'); [print(' -', e) for e in errors]; sys.exit(1)
print(f'data OK: {len(D)} files')

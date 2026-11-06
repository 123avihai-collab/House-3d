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
if errors:
    print('DATA ERRORS:'); [print(' -', e) for e in errors]; sys.exit(1)
print(f'data OK: {len(D)} files')

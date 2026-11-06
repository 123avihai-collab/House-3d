#!/usr/bin/env python3
"""Checks for data/environment/*.json: sources on every record, setbacks respected by every envelope,
±0.00 cross-checked against sheet 04 where available, flagged values, street width vs the typical section."""
import json, math, os, sys
from shapely.geometry import Polygon, LineString
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda *p: json.load(open(os.path.join(ROOT, *p), encoding='utf-8'))
L, S = J('data', 'environment', 'lots.json'), J('data', 'environment', 'streets.json')
err = []
g = L['georeference']
if g['lengthsMap']['maxResidual_m'] > 0.02: err.append('lengths map georeference residual > 2 cm')
if g['heightsPlan']['medianResidual_m'] > 0.03: err.append('heights plan georeference median residual > 3 cm')
if g['boundaryPointCheck']['maxDist_m'] > 0.03: err.append('lengths-map boundary points off the DWG > 3 cm')
if L['envelopeSelfCheck']['maxDeviation_m'] > 0.03: err.append('5187 envelope self-check > 3 cm')
if abs(S['integratedStreet']['widthCheck']['deviation_m']) > 0.02: err.append('integrated street width differs from the typical section')
for l in L['lots']:
    k = l['parcel']
    for f in ('ringSource', 'lotNumberSource'):
        if not l.get(f): err.append(f'lot {k}: missing {f}')
    if not l['lot']: err.append(f'lot {k}: no lot number')
    if not l['cornerLevels']: err.append(f'lot {k}: no corner levels')
    for c in l['cornerLevels']:
        if 'source' not in c: err.append(f'lot {k}: corner level without source')
        if not 270 < c['z'] < 300: err.append(f'lot {k}: corner level {c["z"]} out of range')
    pm = l['pm0']
    if pm['status'] == 'source' and pm['z'] is None: err.append(f'lot {k}: ±0.00 missing but status source')
    if pm.get('check') and not pm['check']['match']: err.append(f'lot {k}: ±0.00 differs from sheet 04 scan')
    if pm['status'] == 'source' and l['cornerLevels'] and not (min(c['z'] for c in l['cornerLevels']) - 1.5 <= pm['z'] <= max(c['z'] for c in l['cornerLevels']) + 1.5):
        err.append(f'lot {k}: ±0.00 {pm["z"]} far from its corner levels and not flagged')
    e = l['envelope']
    if e['build'] and pm['status'] != 'source': err.append(f'lot {k}: envelope built on a non-source ±0.00')
    lot, env = Polygon(l['ring']), Polygon(e['ring'])
    if not lot.buffer(1e-6).contains(env): err.append(f'lot {k}: envelope outside the lot')
    for ed in l['edges']:
        d = LineString(ed['pts']).distance(env)
        if d < ed['setback_m'] - 0.005: err.append(f'lot {k}: envelope {d:.3f} m from edge across {ed["across"]} (setback {ed["setback_m"]})')
    if l['cornerLot'] and l['frontStatus'] != 'assumption': err.append(f'lot {k}: corner lot front not flagged')
for s in S['surfaces']:
    if 'source' not in s: err.append('street surface without source')
    if s['heights'] == 'missing' and not s.get('note'): err.append('street without heights not flagged')
if err:
    print('\n'.join('ENV ERROR: ' + e for e in err)); sys.exit(1)
print(f"environment data OK: {len(L['lots'])} lots, {sum(1 for l in L['lots'] if l['envelope']['build'])} envelopes, {len(S['surfaces'])} street surfaces")

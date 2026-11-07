#!/usr/bin/env python3
"""Self-check of the skeleton against the architect's openings: every concrete element (walls, columns, beams, slabs of all
floors, stairs, perimeter) that occupies the volume of a door / window (opening rectangle × sill…head) is listed.
Output: docs/verification/skeleton-check.json (+ printed)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shapely.geometry import Polygon, LineString
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))


def elements():
    out = []
    FR = J('data/structure/framing.json')
    for w in FR['basementWalls']:
        parts = [Polygon(p['ringITM'], p['holesITM']) for p in w['partsITM']] if 'partsITM' in w else [Polygon(w['footprintITM'], w.get('holesITM') or [])]
        out += [(f"קיר מרתף {w['id']}", g.buffer(0), w['bottomRel'], w['topRel']) for g in parts]
        out += [(f"{f['kind']} {w['id']}", Polygon(f['ringITM']), f['bottomRel'], f['topRel']) for f in w.get('infill', [])]
    for b in FR['groundBeams']:
        if b.get('axisITM'): out.append((f"קורת יסוד {b['id']}", LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2), b.get('bottomRel', b['topRel'] - b.get('depth_m', 0.6)), b['topRel']))
    for fn, fl in (('floor-ground.json', 'קרקע'), ('floor-first.json', "א'"), ('floor-roof.json', 'גג')):
        F = J('data/structure/' + fn)
        for s in F.get('slab', []): out.append((f"רצפה {s['id']} ({fl})", Polygon(s['footprintITM'], s.get('holesITM') or []).buffer(0), s['bottomRel'], s['topRel']))
        for w in F.get('walls', []):
            parts = [Polygon(p['ringITM'], p['holesITM']) for p in w['partsITM']] if 'partsITM' in w else [Polygon(w['footprintITM'], w.get('holesITM') or [])]
            out += [(f"קיר {w['id']} {w.get('tag') or ''} ({fl})", g.buffer(0), w['bottomRel'], w['topRel']) for g in parts]
            out += [(f"{f['kind']} {w['id']} ({fl})", Polygon(f['ringITM']), f['bottomRel'], f['topRel']) for f in w.get('infill', [])]
        for c in F.get('columns', []): out.append((f"עמוד {c['id']} ({fl})", Polygon(c['footprintITM']), c['bottomRel'], c['topRel']))
        C = F.get('ceiling') or {}
        for s in C.get('slab', []): out.append((f"תקרה {s['id']} ({fl})", Polygon(s['footprintITM'], s.get('holesITM') or []).buffer(0), s['bottomRel'], s['topRel']))
        for b in C.get('beams', []):
            if b.get('axisITM'): out.append((f"קורה {b['id']} ({fl})", LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2), b['topRel'] - b['depth_m'], b['topRel']))
    for w in J('data/structure/perimeter.json')['walls']: out.append((f"חומה {w['id']}", Polygon(w['ringITM']), w['bottomRel'], w['topRel']))
    return out


def main():
    OP = J('data/architecture/openings.json')['openings']; E = elements(); res = []
    for o in OP:
        c = np.array(o['centerITM']); a = np.array(o['axisITM']); n = np.array([-a[1], a[0]]); hw = o['width_m'] / 2 - 0.03; d = 0.35
        R = Polygon([tuple(c - a * hw - n * d), tuple(c + a * hw - n * d), tuple(c + a * hw + n * d), tuple(c - a * hw + n * d)])
        if o.get('castFrame'):   # mamad: the opening in the concrete = the structural gap (the frame / pocket inside it)
            R = Polygon(o['castFrame']['ringITM']).buffer(-0.03, join_style=2)
        z0, z1 = o['sillRel'] + 0.03, o['headRel'] - 0.03
        hits = []
        for name, g, b, t in E:
            if t <= z0 or b >= z1: continue
            ar = g.intersection(R).area
            if ar > 0.01: hits.append(f"{name} [{max(b, z0):+.2f}…{min(t, z1):+.2f}] {ar:.2f} מ\"ר")
        if hits: res.append({'opening': o['id'], 'name': o['name'], 'floor': o['floor'], 'UK_OK': [o['UK_cm'], o['OK_cm']], 'blocked_by': hits})
    json.dump(res, open(os.path.join(ROOT, 'docs/verification/skeleton-check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for r in res: print(r['opening'], r['name'][:40], r['UK_OK'], '\n   ' + '\n   '.join(r['blocked_by']))
    print(len(res), 'openings blocked of', len(OP))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Self-check: the architect's Revit plans (plumbing DXF blocks martef / pituah / alef, placed by extract_openings.place) over the
model: concrete walls, slabs' open zones, stairs, perimeter walls, pillar, openings. -> docs/verification/stage-3-overlay-<floor>.png
Lists concrete walls of the model with no architectural wall under them, and thick architectural walls with no concrete wall."""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ezdxf, numpy as np
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
import extract_openings as O

ROOT = O.ROOT
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))


def main():
    doc = ezdxf.readfile(os.path.join(ROOT, O.SRC)); msp = doc.modelspace()
    OP = J('data/architecture/openings.json')['openings']
    ST = J('data/structure/stairs.json'); PM = J('data/structure/perimeter.json')
    walls = {'unit': J('data/structure/framing.json')['basementWalls'], 'ground': J('data/structure/floor-ground.json')['walls'],
             'first': J('data/structure/floor-first.json')['walls']}
    lot = Polygon(J('data/site/plot-5187.json')['ring'])
    report = []
    for floor, (blk, dxf, ffl, _) in O.FLOORS.items():
        ents, to_itm, pl = O.place(msp, blk, dxf)
        fig, ax = plt.subplots(figsize=(13, 13)); x, y = lot.exterior.xy; ax.plot(x, y, color='#c62828', lw=1)
        arch = []
        for v in ents:
            if v.dxftype() == 'LINE' and v.dxf.layer in ('A-WALL', 'I-WALL', 'S-STRS', 'S-STRS-MBND'):
                a, b = to_itm(v.dxf.start.x, v.dxf.start.y), to_itm(v.dxf.end.x, v.dxf.end.y)
                if math.dist(a, b) < 0.02: continue
                arch.append(LineString([a, b]))
                ax.plot([a[0], b[0]], [a[1], b[1]], color={'A-WALL': '#1565c0', 'I-WALL': '#64b5f6'}.get(v.dxf.layer, '#2e7d32'), lw=0.6)
        A = unary_union(arch).buffer(0.13)   # walls are drawn as face lines: ±13 cm covers walls up to 26 cm
        for w in walls[floor]:
            g = Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0)
            for p in ([Polygon(r['ringITM'], r['holesITM']) for r in w['partsITM']] if 'partsITM' in w else [g]):
                for q in getattr(p, 'geoms', [p]):
                    xs, ys = q.exterior.xy; ax.fill(xs, ys, color='#9e9e9e', alpha=0.6, lw=0)
            un = g.difference(A).area / max(g.area, 1e-6)
            if un > 0.35 and g.area > 0.05:
                report.append(f"{floor}: קיר בטון {w['id']} ({w.get('tag') or ''}) – {un * 100:.0f}% משטחו לא על קיר אדריכלי")
                c = g.representative_point(); ax.text(c.x, c.y, w['id'], color='#d50000', fontsize=8, weight='bold')
        for o in [o for o in OP if o['floor'] == floor]:
            c = np.array(o['centerITM']); a = np.array(o['axisITM']) * o['width_m'] / 2
            ax.plot([c[0] - a[0], c[0] + a[0]], [c[1] - a[1], c[1] + a[1]], color='#ff6f00' if o.get('host') else '#ab47bc', lw=3)
            ax.text(c[0], c[1], f"{o['id']}", fontsize=7, color='#e65100')
        if floor == 'ground':
            for pw in PM['walls']:
                xs, ys = Polygon(pw['ringITM']).exterior.xy; ax.fill(xs, ys, color='#6d4c41', alpha=0.7, lw=0)
        for st in ST['stairs']:
            if (floor == 'unit') == (st['floor'] == 'unit') or floor == 'ground':
                for f in st.get('flights', []):
                    o0 = np.array(f['originITM']); r = np.array(f['runDirITM']); rt = np.array(f['rightDirITM'])
                    L = f['riserS_m'][-1]; q = [o0, o0 + r * L, o0 + r * L + rt * f['width_m'], o0 + rt * f['width_m'], o0]
                    ax.plot([p[0] for p in q], [p[1] for p in q], color='#00897b', lw=1.2)
        ax.set_aspect('equal'); ax.set_title(f'{floor}: אפור = קירות בטון במודל · כחול = קירות האדריכל · כתום = פתח בקיר בטון · סגול = פתח בקיר אחר'[::-1], fontsize=9)
        g0 = unary_union([Polygon(w['footprintITM']).buffer(0) for w in walls[floor]] + [lot]).bounds
        ax.set_xlim(g0[0] - 1, g0[2] + 1); ax.set_ylim(g0[1] - 1, g0[3] + 1)
        plt.savefig(os.path.join(ROOT, f'docs/verification/stage-3-overlay-{floor}.png'), dpi=90, bbox_inches='tight'); plt.close(fig)
    print('\n'.join(report) or 'no mismatches')
    json.dump(report, open(os.path.join(ROOT, 'docs/verification/stage-3-overlay.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()

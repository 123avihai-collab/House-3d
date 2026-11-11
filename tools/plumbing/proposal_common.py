"""Shared geometry for the plumbing proposal (tools/plumbing/propose.py): building axes, structure obstacles,
architect wall lines per floor, basement sketch walls."""
import json, math, os, sys
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import georef as G
ROOT = G.ROOT
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
H0 = J('data/site/origin.json')['H0']
FG, FR, BAS = J('data/structure/floor-ground.json'), J('data/structure/framing.json'), J('data/structure/basement.json')
MAMAD = Polygon((FG['ceiling']['openings'] or FG['ceiling']['mamad'])[0]['footprintITM'])          # K-31 "rectangle with diagonal" = ממ"ד (see open-issues PH3)
_c = list(MAMAD.exterior.coords)
UX = ((_c[2][0] - _c[1][0]), (_c[2][1] - _c[1][1])); _l = math.hypot(*UX); UX = (-UX[0] / _l, -UX[1] / _l)   # building "east"
UY = (-UX[1], UX[0])                                                                                        # building "north"


def beam_poly(b):
    (e1, n1), (e2, n2) = b['axisITM']; L = math.dist((e1, n1), (e2, n2)); ux, uy = (e2 - e1) / L, (n2 - n1) / L; hw = b['width_m'] / 2
    return Polygon([(e1 - uy * hw, n1 + ux * hw), (e2 - uy * hw, n2 + ux * hw), (e2 + uy * hw, n2 - ux * hw), (e1 + uy * hw, n1 - ux * hw)])


def concrete():
    """[(kind, id, polygon, bottomRel, topRel, status)] – every structural element in the model."""
    E = []
    for w in FR['basementWalls']: E.append(('קיר מרתף', w['id'], Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0), w['bottomRel'], w['topRel'], w['status']))
    for b in FR['groundBeams']:
        if b.get('axisITM'): E.append(('קורת יסוד', b['id'], beam_poly(b), b['bottomRel'], b['topRel'], b['status']))
    for w in FG['walls']: E.append(('קיר בטון', w['id'], Polygon(w['footprintITM'], w.get('holesITM') or []).buffer(0), w['bottomRel'], w['topRel'], w['status']))
    for c in FG['columns']: E.append(('עמוד', c['id'], Polygon(c['footprintITM']).buffer(0), c['bottomRel'], c['topRel'], c['status']))
    for b in FG['ceiling']['beams']:
        if b.get('axisITM'): E.append(('קורת תקרה', b['id'], beam_poly(b), b['bottomRel'], b['topRel'], b['status']))
    return E


def arch_walls(g, fl, layers=('A-WALL', 'I-WALL', 'S-STRS', 'S-COLS')):
    msp, to = g['msp'], g['to_itm']
    ins = next(e for e in msp.query('INSERT') if e.dxf.name == G.BLOCK[fl])
    out = []
    for v in ins.virtual_entities():
        if v.dxf.layer not in layers: continue
        if v.dxftype() == 'LINE': q = [(v.dxf.start.x, v.dxf.start.y), (v.dxf.end.x, v.dxf.end.y)]
        elif v.dxftype() == 'LWPOLYLINE': q = [tuple(p) for p in v.get_points('xy')] + ([tuple(v.get_points('xy')[0])] if v.closed else [])
        else: continue
        pts = [to(fl)(*p) for p in q]
        if LineString(pts).length > 0.05: out.append(LineString(pts))
    return out


def local(p, o):  # ITM -> building frame (metres) relative to o
    dx, dy = p[0] - o[0], p[1] - o[1]; return (dx * UX[0] + dy * UX[1], dx * UY[0] + dy * UY[1])


def world(q, o):  # building frame -> ITM
    return (o[0] + q[0] * UX[0] + q[1] * UY[0], o[1] + q[0] * UX[1] + q[1] * UY[1])


def rect(o, x0, y0, x1, y1):
    return Polygon([world((x0, y0), o), world((x1, y0), o), world((x1, y1), o), world((x0, y1), o)])


def orthoize(pts, o=None, tol=0.02):
    """Insert a right-angle corner (building axes) into every horizontal segment that is not parallel to UX / UY.
    pts: [(E, N, H|None)]; segments with equal H (or both None) only."""
    o = o or (0.0, 0.0); out = [pts[0]]
    for b in pts[1:]:
        a = out[-1]
        if (a[2] is None and b[2] is None) or (a[2] is not None and b[2] is not None and abs(a[2] - b[2]) < 1e-6):
            la, lb = local(a, o), local(b, o)
            if abs(lb[0] - la[0]) > tol and abs(lb[1] - la[1]) > tol:
                c = world((lb[0], la[1]), o); out.append((c[0], c[1], a[2]))
        out.append(b)
    return out

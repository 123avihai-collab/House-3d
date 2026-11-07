#!/usr/bin/env python3
"""Plumbing layer – placement of the consultant's drawings in ITM (same chain as the main model, nothing new).

DXF  sources/plumbing/אינסטלציה חתכים הכל.dxf : 4 plan blocks (pituah=ground, martef=basement, alef=first, gag=roof),
     each an architect background in cm. Each block is matched to its structural DXF (k-21/k-11/k-31/k-41, same Revit
     coordinates) by a pure translation (ICP of the wall/column lines), then k-xx -> K-400 sheet -> ITM exactly as in
     stage 2 (tools/extract_framing.py: basement.json k11ToK400 + piles.json sheetToItm).
PDF  4 sheets (31.10.2026, newer than the DXF): similarity fit page -> ITM on the stack symbols (magenta circles), which
     the DXF holds as CIRCLE entities (layer "hot water", colour 6) on every floor.
"""
import itertools, math, os, sys
import numpy as np
import ezdxf, pymupdf
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import extract_framing as F

ROOT = F.ROOT
DXF = 'sources/plumbing/אינסטלציה חתכים הכל.dxf'
DETAILS = 'sources/plumbing/‏‏פרטים - לאינטלציה - דוד-מזגן-עטיפת צינור ביוב-ועוד - עותק.dxf'
PDF = {'ground': 'sources/plumbing/אינסטלציה - קומת קרקע ופיתוח.pdf', 'first': 'sources/plumbing/אינסטלציה - קומה א.pdf',
       'roof': 'sources/plumbing/אינסטלציה - גג.pdf', 'unit': 'sources/plumbing/אינטלציה יחידת דיור.pdf'}
BLOCK = {'ground': 'pituah', 'unit': 'martef', 'first': 'alef', 'roof': 'gag'}
STRUCT = {'ground': 'sources/structure/k-21.dxf', 'unit': 'sources/structure/k-11.dxf', 'first': 'sources/structure/k-31.dxf', 'roof': 'sources/structure/k-41.dxf'}
# block x-range in the DXF model (cm) – used to tell which floor a model-space entity belongs to
XRANGE = {'roof': (14617, 17022), 'first': (17944, 20299), 'unit': (21487, 23845), 'ground': (24792, 28708)}
r3 = lambda v: round(float(v), 3)


def floor_of(x, y):
    for k, (a, b) in XRANGE.items():
        if a - 700 < x < b + 700 and -3300 < y < 1900: return k
    return None


def _lines(ents, layers):
    A = []
    for v in ents:
        if v.dxftype() == 'LINE' and v.dxf.layer in layers:
            A += [(v.dxf.start.x, v.dxf.start.y), (v.dxf.end.x, v.dxf.end.y)]
    return np.unique(np.round(np.array(A), 1), axis=0)


def dxf_placement(msp):
    """floor -> (translation cm, inlier fraction, median residual cm). Roof: the roof block has almost no structural
    lines, so it is matched on its slab/parapet outline (A-FLOR/A-DETL) against every line of k-41."""
    t11 = F.basement['k11ToK400']['translation_pt']
    out = {}
    for fl, blk in BLOCK.items():
        ins = next(e for e in msp.query('INSERT') if e.dxf.name == blk)
        ve = list(ins.virtual_entities())
        m = F.read_dxf(STRUCT[fl])
        if fl == 'roof':
            A = _lines(ve, ('S-BEAM', 'S-COLS', 'A-WALL', 'A-FLOR', 'A-DETL', 'A-DETL-MBND'))
            B = np.unique(np.round(np.array([p for e in m.query('LINE') for p in ((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))]), 1), axis=0)
        else:
            A = _lines(ve, ('A-WALL', 'S-STRS', 'S-STRS-MBND', 'S-COLS', 'S-BEAM'))
            B = np.unique(np.round(np.array([p for e in m.query('LINE') if e.dxf.layer in ('IfcWall', 'IfcColumn', 'IfcBeam', 'IfcSlab')
                                             for p in ((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))]), 1), axis=0)
        sc, t, med = F.icp(A, B, tries=150)
        out[fl] = {'t_cm': [r3(t[0]), r3(t[1])], 'inlier': r3(sc), 'median_cm': r3(med), 'matchedTo': STRUCT[fl]}
    return out, t11


def make_to_itm(placement, t11):
    def f(fl):
        t = placement[fl]['t_cm']
        return lambda x, y: F.sheet2itm((x + t[0]) * F.S_CM + t11[0], -(y + t[1]) * F.S_CM + t11[1])
    return f


def stack_circles_itm(msp, to_itm):
    out = {k: [] for k in BLOCK}
    for c in msp.query('CIRCLE[layer=="hot water"]'):
        fl = floor_of(c.dxf.center.x, c.dxf.center.y)
        if fl and c.dxf.color == 6:
            out[fl].append(to_itm(fl)(c.dxf.center.x, c.dxf.center.y))
    return out


def pdf_magenta(page):
    P = {}
    for d in page.get_drawings():
        R = d['rect']; col = tuple(round(v, 2) for v in (d.get('color') or ()))
        if col == (1.0, 0.0, 1.0) and round(d.get('width') or 0, 2) == 0.48 and any(it[0] == 'c' for it in d['items']) and abs(R.width - R.height) < 0.3:
            P[(round((R.x0 + R.x1) / 2, 2), round((R.y0 + R.y1) / 2, 2))] = 1
    return list(P)


def fit_similarity(src, dst):
    """RANSAC on point pairs: page points (x, y down) -> ITM. Returns (T, max residual m, inliers)."""
    a = np.array([complex(x, -y) for x, y in src]); b = np.array([complex(E, N) for E, N in dst])
    best = None; need = min(3, len(a), len(b))
    for i, j in itertools.permutations(range(len(a)), 2):
        for k, l in itertools.permutations(range(len(b)), 2):
            s = (b[l] - b[k]) / (a[j] - a[i]); t = b[k] - s * a[i]
            pr = s * a + t
            d = np.abs(pr[:, None] - b[None, :]).min(1)
            inl = d < 0.03
            if inl.sum() >= need and (best is None or inl.sum() > best[0] or (inl.sum() == best[0] and d[inl].max() < best[1])):
                best = (int(inl.sum()), float(d[inl].max()), s, t)
    n, _, s, t = best
    # refine on all inliers (least squares similarity)
    pr = s * a + t; nn = np.abs(pr[:, None] - b[None, :]).argmin(1); inl = np.abs(pr - b[nn]) < 0.03
    A_, B_ = a[inl], b[nn[inl]]; ca, cb = A_.mean(), B_.mean()
    if len(A_) < 3: s = (B_[1] - B_[0]) / (A_[1] - A_[0]); t = B_[0] - s * A_[0]; ca, cb = 0, t; s_only = True
    else: s = (np.conj(A_ - ca) @ (B_ - cb)) / (np.conj(A_ - ca) @ (A_ - ca)); t = cb - s * ca
    res = np.abs(s * A_ + t - B_).max()
    T = lambda x, y: (lambda z: (z.real, z.imag))(s * complex(x, -y) + t)
    return T, float(res), int(inl.sum()), {'scale_m_per_pt': r3(abs(s)), 'rotation_deg': round(math.degrees(np.angle(s)), 4)}


def load():
    doc = ezdxf.readfile(os.path.join(ROOT, DXF)); msp = doc.modelspace()
    placement, t11 = dxf_placement(msp)
    to_itm = make_to_itm(placement, t11)
    circles = stack_circles_itm(msp, to_itm)
    pages, pdffit = {}, {}
    for fl, path in PDF.items():
        page = pymupdf.open(os.path.join(ROOT, path))[0]
        T, res, n, info = fit_similarity(pdf_magenta(page), circles[fl])
        pages[fl] = (page, T); pdffit[fl] = {'pdf': path, 'points': n, 'maxResidual_m': r3(res), **info}
    return {'doc': doc, 'msp': msp, 'placement': placement, 'to_itm': to_itm, 'pages': pages, 'pdfFit': pdffit, 'stackCircles': circles}


if __name__ == '__main__':
    G = load()
    for k, v in G['placement'].items(): print('dxf', k, v)
    for k, v in G['pdfFit'].items(): print('pdf', k, v)


def finish_level(spots, lot, E, N, near=1.5, far=3.5, slope=0.015):
    """Finished (development) level at a point from the architect's spot levels in the plumbing DXF background:
    spots inside the lot within `near` m -> inverse-distance (1/d²) mean, range = min..max of those spots;
    else the nearest inside the lot within `far` m, range = ±slope·d (paving slopes 1.5% in the drawing)."""
    from shapely.geometry import Point
    S = sorted(((math.dist((s['E'], s['N']), (E, N)), s) for s in spots if lot.contains(Point(s['E'], s['N']))), key=lambda z: z[0])
    use = [z for z in S if z[0] <= near]
    if use:
        w = [1 / max(d, 0.05) ** 2 for d, _ in use]
        H = sum(wi * s['H'] for wi, (d, s) in zip(w, use)) / sum(w)
        return {'H': r3(H), 'lo': min(s['H'] for _, s in use), 'hi': max(s['H'] for _, s in use), 'spots': [[s['H'], r3(d)] for d, s in use], 'rule': f'ממוצע משוקלל (1/d²) של נקודות הגובה עד {near} מ\''}
    if S and S[0][0] <= far:
        d, s = S[0]
        return {'H': s['H'], 'lo': r3(s['H'] - slope * d), 'hi': r3(s['H'] + slope * d), 'spots': [[s['H'], r3(d)]], 'rule': f'נקודת הגובה הקרובה ({d:.1f} מ\'), טווח ±{slope * 100:.1f}% על המרחק'}
    return None

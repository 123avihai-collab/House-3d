"""The exterior paving finish surface (data/finishes/tiling/exterior.json – tools/finishes/derive_exterior.py) as a height
function for the plaster derivation (ק69–ק75, 13.11.2026).

Every vertical face of the skeleton outside, in front of a paving zone, is plastered only from the paving surface up: the
part below is inside the paving build-up (slope fill → waterproofing → adhesive → tile) – the slab edges and beam sides at
the level steps between the exterior slabs (B-37 between GS2 and GS6), the foot of the walls.

  at(X, Y) -> numpy array: the finish level (relative to ±0.00) of the zone the point is in, NaN outside every zone
  zone(x, y) -> the zone record (exterior.json room) the point is in, or None
"""
import json
import os

import numpy as np
import shapely
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Paving:
    def __init__(self, path='data/finishes/tiling/exterior.json'):
        p = os.path.join(ROOT, path)
        self.zones = json.load(open(p, encoding='utf-8'))['rooms'] if os.path.exists(p) else []
        self.polys = [unary_union([Polygon(q['ringITM'], q.get('holesITM') or []).buffer(0) for q in z['parts']]) for z in self.zones]
        for g in self.polys: shapely.prepare(g)

    @staticmethod
    def _z(S, X, Y, flat=None):
        """planeIdw surface (derive_exterior.surface) at the points; no surface – a flat zone (the stair landing) at `flat`;
        minZ – the zone kept to K-21 (the parking, OC-16): the finish not below it"""
        if S is None: return np.full(len(X), flat, dtype=float)
        if S.get('minZ') is not None: return np.maximum(Paving._z({**S, 'minZ': None}, X, Y), S['minZ'])
        pz = S['z'] + S['gE'] * (X - S['E']) + S['gN'] * (Y - S['N'])
        if not S.get('res'): return pz
        R = np.array(S['res'], dtype=float)
        d2 = (X[:, None] - R[None, :, 0]) ** 2 + (Y[:, None] - R[None, :, 1]) ** 2
        exact = d2 < 1e-12
        w = np.where(exact, 1.0, np.maximum(d2, 1e-12) ** (-S['power'] / 2))
        w = np.where(exact.any(1)[:, None], exact.astype(float), w)
        return pz + (w * R[None, :, 2]).sum(1) / w.sum(1)

    def at(self, X, Y):
        X = np.atleast_1d(np.asarray(X, dtype=float)); Y = np.atleast_1d(np.asarray(Y, dtype=float))
        out = np.full(len(X), np.nan)
        for z, g in zip(self.zones, self.polys):
            m = shapely.contains_xy(g, X, Y) & np.isnan(out)
            if m.any(): out[m] = self._z(z['surface'], X[m], Y[m], z.get('finishRel'))
        return out

    def zone(self, x, y):
        for z, g in zip(self.zones, self.polys):
            if g.contains(Point(x, y)): return z
        return None

    def along(self, a, b, n, probe=0.03, step=0.1):
        """the finish levels in front of the face a→b (outward normal n), sampled every `step`: array (NaN where no zone)"""
        L = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        k = max(2, int(L / step) + 1)
        t = np.linspace(0.02, max(0.02, L - 0.02), k) / L if L > 0.04 else np.array([0.5])
        X = a[0] + (b[0] - a[0]) * t + n[0] * probe; Y = a[1] + (b[1] - a[1]) * t + n[1] * probe
        return self.at(X, Y)

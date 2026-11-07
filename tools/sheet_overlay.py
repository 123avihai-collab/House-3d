#!/usr/bin/env python3
"""Self-check image: the model's walls / columns / beams drawn over the structural sheet they come from (K-21 ground, K-31 first).
-> docs/verification/sheet-overlay-<sheet>.png"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon, LineString
import extract_framing as F, extract_floor as X
ROOT = F.ROOT
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding='utf-8'))


def inv(E, N, t):
    G = F.G; th = G['theta_rad']; dx, dy = E - G['tx'], N - G['ty']
    Xm = dx * math.cos(th) + dy * math.sin(th); Ym = -dx * math.sin(th) + dy * math.cos(th)
    return Xm * G['ptPerM'] - t[0], -Ym * G['ptPerM'] - t[1]


def main():
    FG = J('data/structure/floor-ground.json'); FF = J('data/structure/floor-first.json')
    t21 = J('data/structure/framing.json')['placement']['K21pdf']['translation_pt']; t31 = FG['placement']['K31pdf']['translation_pt']
    FR = J('data/structure/floor-roof.json'); t41 = FF['ceiling']['placement']['K41pdf']['translation_pt']
    for name, path, t, clip, D in (('K-21', F.K21P, t21, (1650, 150, 3100, 1700), FG), ('K-31', X.K31P, t31, X.K31P_CLIP, FF), ('K-41', X.K41P, t41, X.K41P_CLIP, FR)):
        dpi = 72; z = dpi / 72
        pix = pymupdf.open(os.path.join(ROOT, path))[0].get_pixmap(dpi=dpi, clip=pymupdf.Rect(*clip))
        img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples).convert('RGBA'); ov = Image.new('RGBA', img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        P = lambda E, N: ((inv(E, N, t)[0] - clip[0]) * z, (inv(E, N, t)[1] - clip[1]) * z)
        for w in D['walls']:
            for pr in (w['partsITM'] if 'partsITM' in w else [{'ringITM': w['footprintITM']}]):
                d.polygon([P(*q) for q in pr['ringITM']], fill=(255, 0, 0, 90), outline=(200, 0, 0, 255))
            pts = [P(*q) for q in w['footprintITM']]
            c = Polygon(pts).representative_point(); d.text((c.x + 3, c.y - 6), w['id'].replace('GW', '').replace('FW', ''), fill=(200, 0, 0, 255))
        for c in D['columns']:
            d.polygon([P(*q) for q in c['footprintITM']], fill=(0, 160, 0, 120), outline=(0, 120, 0, 255))
        BEAMS = {'K-21': FG['ceiling']['beams'], 'K-31': FG['ceiling']['beams'], 'K-41': (D.get('ceiling') or {}).get('beams', [])}[name]
        if name == 'K-21': BEAMS = [b for b in J('data/structure/framing.json')['groundBeams'] if b.get('sheet') == 'K-21']
        for b in BEAMS:
            if b.get('axisITM'):
                g = LineString(b['axisITM']).buffer(b['width_m'] / 2, cap_style=2)
                d.polygon([P(*q) for q in g.exterior.coords], fill=(0, 90, 255, 60), outline=(0, 0, 255, 230))
                c_ = g.centroid; d.text((P(c_.x, c_.y)[0] + 2, P(c_.x, c_.y)[1] + 2), b['id'].replace('קורה ללא מספר', '?'), fill=(0, 0, 200, 255))
        Image.alpha_composite(img, ov).convert('RGB').save(os.path.join(ROOT, f'docs/verification/sheet-overlay-{name}.png'))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Debug plot of the extracted plumbing network (tools/plumbing/cache) – not part of the model.
python3 tools/plumbing/debug_plot.py <floor> <out.png> [E0 N0 E1 N1]"""
import json, math, os, sys
from PIL import Image, ImageDraw, ImageFont
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
fl, out = sys.argv[1], sys.argv[2]
box = list(map(float, sys.argv[3:7])) if len(sys.argv) > 6 else [179580, 576224, 179613, 576258]
R = json.load(open(os.path.join(ROOT, 'tools/plumbing/cache/raw.json')))
NET = json.load(open(os.path.join(ROOT, 'tools/plumbing/cache/net.json'))) if os.path.exists(os.path.join(ROOT, 'tools/plumbing/cache/net.json')) else None
S = 2400 / max(box[2] - box[0], box[3] - box[1])
W, H = int((box[2] - box[0]) * S), int((box[3] - box[1]) * S)
im = Image.new('RGB', (W, H), 'white'); d = ImageDraw.Draw(im)
try: font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
except Exception: font = None
X = lambda p: ((p[0] - box[0]) * S, (box[3] - p[1]) * S)
fg = json.load(open(os.path.join(ROOT, 'data/structure/floor-ground.json')))
for w in fg['walls'] + fg['columns']: d.polygon([X(p) for p in w['footprintITM']], outline=(190, 190, 190))
fr = json.load(open(os.path.join(ROOT, 'data/structure/framing.json')))
if fl == 'unit':
    for w in fr['basementWalls']: d.polygon([X(p) for p in w['footprintITM']], outline=(160, 160, 220))
if NET:
    for r in NET['runs']:
        if r['floor'] != fl: continue
        col = {'sewage': (0, 160, 0), 'cold': (0, 90, 255), 'hot': (230, 0, 0), 'rain': (0, 170, 170), 'pumped': (160, 0, 160)}.get(r['system'], (120, 120, 0))
        d.line([X(p) for p in r['pts']], fill=col, width=4)
        m = r['pts'][len(r['pts']) // 2]; d.text(X(m), r['id'], fill=col, font=font)
    for n in NET['nodes']:
        if n['floor'] not in (fl, 'site') and not (fl == 'ground' and n['floor'] == 'site'): continue
        x, y = X((n['E'], n['N'])); rr = 7
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=(200, 0, 0) if n.get('dangling') else (0, 0, 0), width=2)
        d.text((x + 8, y - 8), n['id'], fill=(120, 0, 0), font=font)
else:
    for a, b in R['green'][fl]: d.line([X(a), X(b)], fill=(0, 160, 0), width=4)
im.save(out); print(out, im.size)

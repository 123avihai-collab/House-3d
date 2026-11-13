#!/usr/bin/env python3
"""Fetch a tile product's images from the supplier's page (Negev: www.negev-group.co.il) and build the face atlas.

  python3 tools/finishes/fetch_product.py <product url> <SKU> [--faces 2,3,4]

- Finds every product image of <SKU> on the page (…/pub/media/catalog/product/x/y/<SKU>_<n>-….jpg; the full-size
  file, not a resized cache copy), saves them to sources/products/<SKU>/ (with page.html, the page as fetched).
- Builds assets/textures/<sku>/faces.webp: the face images side by side (default: every square image except _1,
  which on the Negev site is the room photo). One face per tile in the workshop (catalog look.faceTexture / faces).
- Prints the mean colour of the faces (look.swatch) and what to add to data/finishes/tiling/catalog.json "products".
The product data (size, thickness, box m², R, V) come from the product page text / spec PDF – checked by hand.
"""
import os
import re
import sys
import urllib.request

from PIL import Image, ImageStat

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UA = {'User-Agent': 'house3d-texture-fetch'}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) < 2:
        sys.exit(__doc__)
    url, sku = args[0], args[1]
    faces_sel = None
    if '--faces' in sys.argv:
        faces_sel = [int(x) for x in sys.argv[sys.argv.index('--faces') + 1].split(',')]
    src = os.path.join(ROOT, 'sources', 'products', sku)
    os.makedirs(src, exist_ok=True)
    html = get(url).decode('utf-8', 'replace')
    open(os.path.join(src, 'page.html'), 'w', encoding='utf-8').write(html)
    host = re.match(r'https?://[^/]+', url).group(0)
    found = {}
    for m in re.finditer(r'/pub/media/catalog/product/(?:cache/[0-9a-f]+/)?(\w/\w/' + re.escape(sku) + r'_(\d+)-[\w.-]+\.(?:jpg|jpeg|png|webp))', html):
        found.setdefault(int(m.group(2)), m.group(1))
    if not found:
        sys.exit(f'no images of {sku} on the page')
    imgs = {}
    for n, rel in sorted(found.items()):
        f = os.path.join(src, f'{sku}_{n}{os.path.splitext(rel)[1]}')
        open(f, 'wb').write(get(f'{host}/pub/media/catalog/product/{rel}'))
        im = Image.open(f).convert('RGB')
        imgs[n] = im
        print(f'{sku}_{n}: {im.size[0]}×{im.size[1]}  mean {tuple(round(x) for x in ImageStat.Stat(im).mean)}')
    sel = faces_sel or [n for n, im in imgs.items() if n != 1 and abs(im.size[0] - im.size[1]) <= 2]
    if not sel:
        sys.exit('no face images (use --faces)')
    side = min(min(imgs[n].size) for n in sel)
    atlas = Image.new('RGB', (side * len(sel), side))
    for i, n in enumerate(sel):
        atlas.paste(imgs[n].resize((side, side), Image.LANCZOS), (i * side, 0))
    out = os.path.join(ROOT, 'assets', 'textures', sku.lower())
    os.makedirs(out, exist_ok=True)
    atlas.save(os.path.join(out, 'faces.webp'), quality=88)
    mean = '#%02x%02x%02x' % tuple(round(x) for x in ImageStat.Stat(atlas).mean)
    print(f'atlas: assets/textures/{sku.lower()}/faces.webp  faces {sel}  swatch {mean}')
    print(f'catalog look: {{"color": "#ffffff", "swatch": "{mean}", "faceTexture": "assets/textures/{sku.lower()}/faces.webp", "faces": {len(sel)}}}')


if __name__ == '__main__':
    main()

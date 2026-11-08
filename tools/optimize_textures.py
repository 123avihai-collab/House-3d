#!/usr/bin/env python3
"""Lighter download, same look (Avihai 08.11): the colour / roughness / AO maps of every texture set are also written as
WebP q92 (PSNR 38–45 dB against the JPG – no visible difference); the normal maps stay JPG (WebP's colour subsampling
would bend the normals, lossless WebP is twice the size). js/core/materials.js loads <map>.webp, normal.jpg.
Run after adding a texture set: python3 tools/optimize_textures.py"""
import glob, os
from PIL import Image
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t0 = t1 = 0
for f in sorted(glob.glob(os.path.join(ROOT, 'assets/textures/*/*.jpg'))):
    if os.path.basename(f).startswith('normal'): continue
    out = f[:-4] + '.webp'
    Image.open(f).convert('RGB').save(out, 'WEBP', quality=92, method=6)
    t0 += os.path.getsize(f); t1 += os.path.getsize(out)
print(f'colour/roughness/ao: {t0 / 1e6:.1f} MB jpg -> {t1 / 1e6:.1f} MB webp')

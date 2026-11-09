#!/usr/bin/env python3
"""Prepare the site for publishing as a claude.ai artifact.

The artifact host serves only standard web types, so binary files it does not
serve (.hdr) are published as a base64 text copy (<name>.b64.txt); the viewer
(js/core/viewer.js, resolveHdri) decodes it when the .hdr itself is missing.

Output (tools/cache/artifact/, git-ignored):
  - files.json  : map {published path: source path} for the Artifact `files` input
  - assets/...  : the generated .b64.txt copies

Run from the repo root:  python3 tools/build_artifact.py
"""
import base64
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'tools', 'cache', 'artifact')
DIRS = ['css', 'js', 'src', 'data', 'assets', 'vendor']
PAGES = ['editor.html']   # extra pages next to index.html (the 2D pipe editor)
SERVED = {'.css', '.js', '.mjs', '.json', '.jpg', '.jpeg', '.png', '.webp', '.svg', '.txt'}
AS_BASE64 = {'.hdr'}


def main():
    files = {}
    for d in DIRS:
        for dirpath, _, names in os.walk(os.path.join(ROOT, d)):
            for n in sorted(names):
                src = os.path.relpath(os.path.join(dirpath, n), ROOT).replace(os.sep, '/')
                ext = os.path.splitext(n)[1].lower()
                if ext in SERVED:
                    files[src] = src
                elif ext in AS_BASE64:
                    dst = os.path.join(OUT, src + '.b64.txt')
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(os.path.join(ROOT, src), 'rb') as f, open(dst, 'w') as g:
                        g.write(base64.b64encode(f.read()).decode('ascii'))
                    files[src + '.b64.txt'] = os.path.relpath(dst, ROOT).replace(os.sep, '/')
                # anything else (LICENSE files etc.) is not needed at runtime
    for pg in PAGES: files[pg] = pg
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'files.json'), 'w', encoding='utf-8') as f:
        json.dump(files, f, ensure_ascii=False, indent=1)
    print(f'{len(files)} files -> {os.path.relpath(OUT, ROOT)}/files.json')


if __name__ == '__main__':
    main()

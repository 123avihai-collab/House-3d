#!/usr/bin/env python3
"""Interactive K-400 plan (plans.html) – data builder.  Run from repo root:  python3 tools/plans/build_k400.py

Reads only the model's data + the K-400 PDF:
  • piles / beams / pile caps / basement walls  ← data/structure/*.json (already extracted from K-400 / K-11 / K-21 / K-x2)
  • rebar rows per element                        ← tools/boq/elements.py (same take-off as the bill of quantities)
  • pile table "טבלת כלונסאות-כמויות" (verbatim)  ← K-400 PDF text layer (pdftotext -bbox)
  • background raster of the plan area             ← K-400 PDF (pdftoppm) → assets/plans/K-400.jpg
Output: data/plans/k400.json
"""
import json, math, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'boq'))
import elements  # noqa: E402

PDF = ROOT / 'sources/structure/K-400-תכנית יסודות.pdf'
CFG = json.load(open(ROOT / 'data/config/plans.json', encoding='utf-8'))
SHEET = CFG['sheets']['K-400']
P = {k: v['value'] for k, v in json.load(open(ROOT / 'data/quantities/boq-params.json', encoding='utf-8'))['rebar'].items() if isinstance(v, dict) and 'value' in v}


def r3(x):
    return round(float(x), 3)


def ev(expr, e):
    """Evaluate a BOQ formula string ({L},{W},{H},{P:x}, PI(), ROUNDUP(x,0)) for one element."""
    if isinstance(expr, (int, float)):
        return float(expr)
    s = expr
    s = re.sub(r'\{P:(\w+)\}', lambda m: repr(P[m.group(1)]), s)
    for k in ('L', 'W', 'H', 'n'):
        s = s.replace('{' + k + '}', repr(float(e.get(k) or 0)))
    s = s.replace('PI()', 'math.pi').replace('ROUNDUP(', '_ru(')
    return float(eval(s, {'math': math, '_ru': lambda x, n=0: math.ceil(round(x, 9))}))


def rebar_rows(e):
    out = []
    for r in e.get('rb', []):
        if 'dia' not in r:
            out.append(dict(desc=r['desc'], status=r.get('status', 'provisional'), src=r.get('src', ''), kg=None))
            continue
        cnt = ev(r['count'], e); ln = ev(r['length'], e)
        tot = cnt * ln; kg = tot * elements.kgm(r['dia'])
        out.append(dict(desc=r['desc'], dia=r['dia'], count=r3(cnt), length_m=r3(ln), total_m=r3(tot), kg=round(kg, 1),
                        src=r.get('src', ''), status=r.get('status', 'source')))
    return out


def pile_table():
    """K-400 'טבלת כלונסאות-כמויות' rows, verbatim (columns located by their x on the sheet)."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / 'b.html'
        subprocess.run(['pdftotext', '-bbox', str(PDF), str(out)], check=True, capture_output=True)
        t = out.read_text(encoding='utf-8')
    W = [(float(a), float(b), w.replace('&apos;', "'")) for a, b, w in re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="[\d.]+">([^<]*)<', t)]
    T = SHEET['pileTable']; x0, y0, x1, y1 = T['bbox_pt']
    W = [w for w in W if x0 < w[0] < x1 and y0 < w[1] < y1]
    cols = T['columns']   # [{key, xMin, xMax}]

    def col(x):
        for c in cols:
            if c['xMin'] <= x < c['xMax']:
                return c['key']
        return None
    ids = sorted([w for w in W if col(w[0]) == 'id' and re.fullmatch(r'\d+A?', w[2])], key=lambda w: w[1])
    rows = []
    for i, w in enumerate(ids):
        ya = w[1] - 4; yb = ids[i + 1][1] - 4 if i + 1 < len(ids) else ya + 17   # last row: one row height (the 'Grand total' line follows)
        cell = {}
        for x, y, s in [q for q in W if ya <= q[1] < yb]:
            k = col(x)
            if k and k != 'id':
                cell.setdefault(k, []).append((round(y), x, s))
        row = {'id': w[2]}
        for k, v in cell.items():
            heb = any(re.search(r'[\u0590-\u05FF]', s) for _, _, s in v)
            # Hebrew in the PDF text layer is stored in visual order (reversed words, right-to-left)
            v = sorted(v, key=lambda q: (q[0], -q[1] if heb else q[1]))
            row[k] = ' '.join(s[::-1] if heb and re.search(r'[\u0590-\u05FF]', s) else s for _, _, s in v).replace('Φω', 'Φ').replace('ω', '')
        rows.append(row)
    return rows


def render_background():
    b = SHEET['background']; x, y, w, h = b['crop_pt']; dpi = b['dpi']
    dst = ROOT / b['image']
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / 'k'
        s = dpi / 72
        subprocess.run(['pdftoppm', '-r', str(dpi), '-x', str(int(x * s)), '-y', str(int(y * s)), '-W', str(int(w * s)), '-H', str(int(h * s)),
                        '-gray', '-png', str(PDF), str(base)], check=True, capture_output=True)
        from PIL import Image
        im = Image.open(str(base) + '-1.png').convert('L')
        im.save(dst, 'JPEG', quality=b['jpegQuality'], optimize=True)
    return dst


def link(out):
    """pile ↔ beam: pile centre within (beam width / 2 + pile radius) of the beam axis segment."""
    for b in out['beams']:
        (E1, N1), (E2, N2) = b['axisITM']; L = math.hypot(E2 - E1, N2 - N1); ux, uy = (E2 - E1) / L, (N2 - N1) / L
        b['piles'] = []
        for p in out['piles']:
            t = (p['E'] - E1) * ux + (p['N'] - N1) * uy; o = -(p['E'] - E1) * uy + (p['N'] - N1) * ux
            r = p['diameter_m'] / 2
            if -r <= t <= L + r and abs(o) <= b['width_m'] / 2 + r:
                b['piles'].append({'id': p['id'], 'along_m': r3(t), 'offset_m': r3(o)})
                p.setdefault('beams', []).append(b['id'])
    for p in out['piles']:
        p.setdefault('beams', [])
        p['walls'] = [w['id'] for w in out['basementWalls']
                      if any(elements.in_ring(r, (p['E'], p['N'])) for r in [w['footprintITM']] + [q['ringITM'] for q in (w.get('parts') or [])])]
        p['footings'] = [f['id'] for f in out['footings'] if p['id'] in f.get('piles', [])]


def main():
    piles = elements.J('data/structure/piles.json'); fr = elements.J('data/structure/framing.json')
    E = elements.collect()
    byId = {e['id']: e for e in E}
    table = {r['id']: r for r in pile_table()}
    out = {'_doc': 'Generated by tools/plans/build_k400.py – do not edit by hand.',
           'sheet': 'K-400', 'georeference': piles['georeference']['sheetToItm'], 'requirements': piles['requirements'],
           'H0': elements.J('data/site/origin.json')['H0'], 'H0_source': 'data/site/origin.json',
           'pileDetail': {
               'longBars': {'0.5': 7, '0.6': 8, 'source': 'K-400 טבלת כלונסאות (7Φ16 / 8Φ16) + חתך A-A "7Φ16"'},
               'spiral': {'dia_mm': 8, 'pitchDense_m': 0.10, 'pitch_m': 0.20, 'text': 'חישוק לוליני Φ8@10(20)', 'source': 'K-400 חתך A-A'},
               'denseZone_m': {'value': P['spiralDense_m'], 'status': 'provisional', 'source': 'data/quantities/boq-params.json rebar.spiralDense_m – אורך הקטע הצפוף לא כתוב בגיליון'},
               'ring': {'dia_mm': 14, 'spacing_m': 3.0, 'text': 'טבעת חיזוק Φ14@300', 'source': 'K-400 פרט כלונס טיפוסי מתחת לקורת יסוד'},
               'cover_m': {'value': 0.075, 'source': 'K-400 חתך A-A: 7.5 משני הצדדים'},
               'anchor_m': {'value': P['pileAnchor_m'], 'status': 'provisional', 'source': 'data/quantities/boq-params.json rebar.pileAnchor_m – אורך לא כתוב'},
               'sleeve': {'text': 'שרוול קרטון 200 ס"מ', 'source': 'K-400 פרט כלונס טיפוסי'},
               'concrete': 'ב-30', 'notes': ['אורך כלוב הזיון יהיה בהתאם לטבלת כלונסאות (K-400)']},
           'beamCover_m': {'value': P['cover_m'], 'source': 'K-23/33/43: עובי כיסוי הבטון יהיה 2.5 ס"מ'},
           'pileTableColumns': SHEET['pileTable']['columns'], 'piles': [], 'beams': [], 'pileCaps': [], 'basementWalls': []}
    for p in piles['piles']:
        e = byId.get('P' + p['id'], {})
        out['piles'].append(dict(p, rebar=rebar_rows(e), volume_m3=r3(math.pi / 4 * p['diameter_m'] ** 2 * p['length_m']), table=table.get(p['id'])))
    for b in fr['groundBeams']:
        if not b.get('axisITM'):
            continue
        e = byId.get(b['id'], {})
        (E1, N1), (E2, N2) = b['axisITM']; L = math.hypot(E2 - E1, N2 - N1)
        rbb = next((x for x in elements.J('data/structure/rebar.json')['beams'] if x['id'] == b['id'] and x['geomSheet'] == b['sheet']), None)
        out['beams'].append(dict(b, length_m=r3(L), volume_m3=r3(L * b['width_m'] * b['depth_m']), rebar=rebar_rows(e),
                                 bars=(rbb or {}).get('bars', []), section=(rbb or {}).get('section'), rebarSheet=(rbb or {}).get('sheet')))
    for c in fr.get('pileCaps', []):
        out['pileCaps'].append(dict(c, rebar=rebar_rows(byId.get(c['id'], {}))))
    for w in fr['basementWalls']:
        out['basementWalls'].append({k: w[k] for k in ('id', 'footprintITM', 'holesITM', 'area_m2', 'bottomRel', 'topRel', 'status', 'note', 'source') if k in w}
                                    | {'parts': w.get('partsITM'), 'openings': w.get('openings', []), 'rebar': rebar_rows(byId.get(w['id'], {}))})
    per = elements.J('data/structure/perimeter.json')
    out['perimeterSection'] = per['section']
    out['footings'] = [dict(f, rebar=rebar_rows(byId.get(f['id'], {}))) for f in per['footings']]
    out['perimeterWalls'] = [{k: w[k] for k in ('id', 'side', 'ringITM', 'thickness_m', 'length_m', 'topRel', 'topAbs', 'status', 'topSource') if k in w}
                             for w in per['walls']]
    link(out)
    plot = elements.J('data/site/plot-5187.json')
    out['plot'] = {'ringITM': plot['ring'], 'source': plot['source']}
    missing = [p['id'] for p in out['piles'] if not p['table']]
    if missing:
        print('WARNING: piles without a pile-table row:', missing)
    render_background()
    json.dump(out, open(ROOT / 'data/plans/k400.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"{len(out['piles'])} piles ({len(table)} table rows), {len(out['beams'])} beams -> data/plans/k400.json")


if __name__ == '__main__':
    main()

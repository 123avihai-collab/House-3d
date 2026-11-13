# -*- coding: utf-8 -*-
"""Skeleton bill of quantities (כתב כמויות שלד) → docs/quantities/boq-skeleton.xlsx

Usage:
  node tools/boq/export_model_quantities.mjs      # (optional) refresh the model's own totals for the cross-check sheet
  python3 tools/boq/build_boq.py                  # build the workbook (all quantities are live formulas)

Inputs: the model's data (tools/boq/elements.py), data/quantities/boq-params.json (waste, formwork, rebar
assumptions), data/quantities/prices.json (unit prices + sources), docs/quantities/blocks-*.json and
data/architecture/blocks.json (stage 4a), docs/quantities/boq/model-quantities.json (cross-check).
Every element row carries its dimensions and a formula n × A × (H − ded); formwork, rebar and cost rows
reference those cells, the assumption cells (amber) and the price list, so editing a dimension, a waste % or a
price in Excel updates the whole workbook.
"""
import json, math, sys
from pathlib import Path
from collections import OrderedDict, defaultdict
import openpyxl
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style_kit import (Sheet, NIS, PCT1, QTY, NUM, NUM3, TOTAL_FILL, HERO_FILL, BAND_FILL, INPUT_FILL, WARN_FILL,
                       NOW_FILL, C_C, C_W, F_NOTE, col_letter)
import elements as EL

ROOT = EL.ROOT
OUT = ROOT / 'docs/quantities/boq-skeleton.xlsx'
SN = OrderedDict(sum='סיכום', step='לפי שלב', ew='01 עבודות עפר', conc='02 בטון', fw='02 טפסנות', rb='02 ברזל',
                 blk='04 בנייה', wp='05 איטום וניקוז', price='מחירון', par='הנחות ופחת', chk='בקרה', open='פתוחים')
STATUS_HE = {'source': 'מקור', 'approved': 'אושר', 'provisional': 'זמני', 'approx': 'בקירוב', 'missing': 'חסר', 'owner-change': 'שינוי דייר'}
FLOOR_HE = EL.FLOOR_HE


def q(sheet):
    return "'" + SN[sheet] + "'"


def J(rel):
    return json.load(open(ROOT / rel, encoding='utf-8'))


class Book:
    def __init__(self):
        self.wb = openpyxl.Workbook()
        self.ws = {}
        first = True
        for k, name in SN.items():
            if first:
                ws = self.wb.active; ws.title = name; first = False
            else:
                ws = self.wb.create_sheet(name)
            self.ws[k] = ws
        self.par = {}      # key → absolute ref
        self.price = {}    # key → absolute ref
        self.priceUnit = {}
        self.missingPrices = []
        self.open = []     # open issues rows
        self.sum = OrderedDict()   # chapter → (cost ref, note)
        self.qty = OrderedDict()   # headline quantity → (ref, unit)
        seq = J('data/config/tags.json')['sequence']
        self.steps = OrderedDict((s['id'], f"{i+1:02d} · {s['label']}") for i, s in enumerate(seq))

    def P(self, key):
        return self.par[key]

    def PR(self, key):
        if key not in self.price:
            self.missingPrices.append(key)
            return '0'
        return self.price[key]


# ------------------------------------------------------------------ assumptions
def build_params(B):
    ws = B.ws['par']; prm = J('data/quantities/boq-params.json')
    S = Sheet(ws, note_col=8, widths={'A': 2, 'B': 6, 'C': 52, 'D': 13, 'E': 10, 'F': 10, 'G': 70, 'H': 34})
    S.title(1, 'הנחות ופחת | כתב כמויות שלד – מגרש 5187', 'מקור: data/quantities/boq-params.json · 🟡 אמבר = תא קלט – שינוי כאן מעדכן את כל הנוסחאות בקובץ · "זמני" = הערכה מקצועית / נוהג מקובל, לאישור מול הקבלן / המהנדס')
    r = 3; n = 0
    groups = [('waste', 'פחת לפי חומר', '%'), ('earthworks', 'עבודות עפר', ''), ('formwork', 'טפסנות', ''), ('rebar', 'ברזל', ''),
              ('concrete', 'בטון', ''), ('membrane', 'איטום', '')]

    def put(key, d, unit):
        nonlocal r, n
        n += 1
        isPct = 'pct' in d
        v = d['pct'] / 100 if isPct else d['value']
        S.row(r, [n, d['label'], v, '%' if isPct else unit, STATUS_HE.get(d.get('status'), d.get('status', '')), d.get('source', '')],
              [QTY, None, PCT1 if isPct else (NUM3 if isinstance(v, float) and v < 1 else NUM), None, None, None], fill=BAND_FILL if n % 2 == 0 else None, wrap_cols=(7,))
        S.paint(r, 4, INPUT_FILL)
        if d.get('status') == 'provisional':
            S.paint(r, 6, WARN_FILL)
        B.par[key] = f"{q('par')}!$D${r}"
        r += 1

    units = {'bulking': '', 'compaction': '', 'truck_m3': 'מ"ק', 'reuseFill_pct': '', 'sheet_m2': 'מ"ר', 'propsPer_m2': "יח'/מ\"ר", 'propsPer_m_beam': "יח'/מ'",
             'propDays': 'ימים', 'oil_l_per_m2': "ל'/מ\"ר", 'tiesPer_m2': "יח'/מ\"ר", 'nails_kg_per_m2': 'ק"ג/מ"ר', 'cover_m': "מ'", 'lap_d': 'd',
             'pileAnchor_m': "מ'", 'spiralDense_m': "מ'", 'wireKgPerTon': 'ק"ג/טון', 'spacersPer_m2': "יח'/מ\"ר", 'pumpMin_m3': 'מ"ק', 'layers': 'שכבות'}
    for gk, title, _ in groups:
        S.section(r, title); r += 1
        S.header(r, ["מס'", 'פרמטר', 'ערך', "יח'", 'סטטוס', 'מקור'], h=30); r += 1
        for k, d in prm[gk].items():
            if k.startswith('_'):
                continue
            if isinstance(d, dict) and 'label' not in d:      # nested group (reuse / timber / ratio)
                for kk, dd in d.items():
                    if kk.startswith('_'):
                        continue
                    put(f"{gk}.{k}.{kk}", dd, {'reuse': 'שימושים', 'timber_m_per_m2': "מ'/מ\"ר", 'ratio': 'ק"ג/מ"ק'}.get(k, ''))
                continue
            if isinstance(d.get('value'), str):
                n += 1
                S.row(r, [n, d['label'], d['value'], '', STATUS_HE.get(d.get('status'), ''), d.get('source', '')], [QTY], wrap_cols=(7,))
                r += 1; continue
            put(f"{gk}.{k}", d, units.get(k, ''))
        r += 1
    S.finish(r - 1)


# ------------------------------------------------------------------ prices
def build_prices(B):
    ws = B.ws['price']; P = J('data/quantities/prices.json')
    S = Sheet(ws, note_col=14, widths={'A': 2, 'B': 6, 'C': 20, 'D': 40, 'E': 9, 'F': 13, 'G': 11, 'H': 11, 'I': 13, 'J': 40, 'K': 36, 'L': 11, 'M': 9, 'N': 40})
    S.title(1, 'מחירון | כתב כמויות שלד – מגרש 5187', f"מקור: data/quantities/prices.json ({P.get('_asOf', '')}) · מחירים ללא מע\"מ · 🟡 אמבר = מחיר לעדכון לפי הצעות מחיר בפועל · ודאות: גבוהה = מחירון / ספק, בינונית = מדריך מחירים, נמוכה = הערכה")
    r = 3
    for grp in P['groups']:
        S.section(r, grp['title']); r += 1
        S.header(r, ["מס'", 'מפתח', 'פריט', "יח'", 'מחיר ליח\' (₪)', 'טווח נמוך', 'טווח גבוה', 'היקף', 'מקור', 'קישור', 'תאריך', 'ודאות'], h=30); r += 1
        for i, it in enumerate(grp['items']):
            S.row(r, [len(B.price) + 1, it['key'], it['item'], it['unit'], it['price'], it.get('low'), it.get('high'),
                      {'supply': 'חומר בלבד', 'supply_install': 'כולל ביצוע', 'labor': 'עבודה', 'rental': 'השכרה'}.get(it.get('scope'), it.get('scope', '')),
                      it.get('source_title', ''), it.get('source_url', ''), it.get('source_date', ''),
                      {'high': 'גבוהה', 'medium': 'בינונית', 'low': 'נמוכה'}.get(it.get('confidence'), it.get('confidence', ''))],
                  [QTY, None, None, None, NIS, NIS, NIS], fill=BAND_FILL if i % 2 else None, note=it.get('note'), wrap_cols=(4, 10, 11))
            S.paint(r, 6, INPUT_FILL)
            if it.get('confidence') == 'low':
                S.paint(r, 13, WARN_FILL)
            url = it.get('source_url')
            if url and url.startswith('http'):
                ws.cell(row=r, column=11).hyperlink = url
            B.price[it['key']] = f"{q('price')}!$F${r}"; B.priceUnit[it['key']] = it['unit']
            r += 1
        r += 1
    S.finish(r - 1)


# ------------------------------------------------------------------ concrete elements
SEC = OrderedDict([
    ('piles', 'כלונסאות קדוחים (K-400) – נפח בטון תיאורטי'),
    ('beamsFound', 'קורות מרתף, קורות יסוד וראשי כלונס (K-11 / K-21 / K-400)'),
    ('slabs', 'רצפות – מרתף (K-11) וקרקע (K-21), רצפות תלויות'),
    ('walls', 'קירות בטון – מרתף, קרקע, קומה א\', מעקות גג'),
    ('columns', 'עמודים'),
    ('ceilings', 'תקרות – קרקע ‎+3.70 (K-31) וגג ‎+6.90 (K-41)'),
    ('beamsCeil', 'קורות תקרה, קורות גג ופרגולות (K-31 / K-41)'),
    ('stairs', 'מדרגות בטון'),
    ('perimeter', 'חומות היקף, יסודות חומות ופילר מערכות'),
    ('pool', 'בריכה, תעלת גלישה, תעלת תריס וחדר מכונות'),
])
# column map of '02 בטון'
CC = dict(no=2, id=3, name=4, floor=5, step=6, loc=7, n=8, L=9, W=10, H=11, A=12, P=13, ded=14, calc=15, net=16, waste=17, order=18, price=19, cost=20, status=21, src=22)


def tok(tpl, r, B):
    """'2*{A}/{t}*{H}+{P:cover_m}' → Excel formula on row r of '02 בטון'."""
    s = str(tpl)
    m = {'n': 'n', 'L': 'L', 'W': 'W', 't': 'W', 'H': 'H', 'A': 'A', 'P': 'P', 'ded': 'ded'}
    import re

    def rep(mo):
        k = mo.group(1)
        if k.startswith('P:'):
            pk = k[2:]
            full = next((x for x in B.par if x.endswith('.' + pk)), None)
            return B.par[full]
        return f"{q('conc')}!${col_letter(CC[m[k]])}${r}"
    return re.sub(r'\{([^}]+)\}', rep, s)


def tok_local(tpl, r, B):
    """same, but refs on the same sheet (no sheet prefix) – for '02 בטון' itself."""
    return tok(tpl, r, B).replace(q('conc') + '!', '')


def build_concrete(B, E):
    ws = B.ws['conc']
    S = Sheet(ws, note_col=23, widths={'A': 2, 'B': 5, 'C': 13, 'D': 30, 'E': 9, 'F': 17, 'G': 30, 'H': 5, 'I': 8, 'J': 8, 'K': 8, 'L': 9, 'M': 8, 'N': 8,
                                       'O': 22, 'P': 11, 'Q': 8, 'R': 11, 'S': 12, 'T': 14, 'U': 8, 'V': 40, 'W': 34})
    S.title(1, 'פרק 02 – בטון יצוק באתר | אלמנטים לפי המודל', 'כל שורה = אלמנט במודל: מידות מקובצי הנתונים (data/structure/*.json ← DXF/PDF של הקונסטרוקטור), נפח בנוסחה: n × A × (h − קיזוז), כש-A = L×b אם לא ניתן שטח. '
            'קיזוז = החלק של הקורה שבתוך הרצפה / התקרה (נספר עם הרצפה). בטון ב-30 דרגת חשיפה 3 (K-11…K-41 הערה 9). מחיר = חומר בלבד; יציקה ושאיבה – בסוף הגיליון.')
    r = 3; no = 0
    hdr = ["מס'", 'מזהה', 'תיאור', 'קומה', 'שלב ביצוע', 'מיקום (ITM) / מפלס', "יח'", "L (מ')", "b / t (מ')", "h (מ')", 'A (מ"ר)', "היקף (מ')", "קיזוז (מ')",
           'חישוב', 'נפח נטו (מ"ק)', 'פחת', 'נפח להזמנה (מ"ק)', '₪ למ"ק', 'עלות חומר (₪)', 'סטטוס', 'מקור']
    B.concRows = {}
    secTot = {}
    for sec, title in SEC.items():
        rows = [e for e in E if e['sec'] == sec]
        if not rows:
            continue
        S.section(r, title); r += 1
        S.header(r, hdr); r += 1
        r0 = r
        for i, e in enumerate(rows):
            no += 1
            n_, L, W, H, A, P, ded = e['n'], e.get('L'), e.get('W'), e.get('H'), e.get('A'), e.get('P'), e.get('ded', 0)
            Aval = A
            if isinstance(A, tuple) and A[0] == 'cyl':
                Aval = f"=PI()/4*{col_letter(CC['W'])}{r}^2"
            if e.get('Lw'):
                W = e['Lw'][1]
                L = f"={col_letter(CC['A'])}{r}/{col_letter(CC['W'])}{r}"
            c = {k: f"{col_letter(CC[k])}{r}" for k in CC}
            net = f"={c['n']}*IF(ISNUMBER({c['A']}),{c['A']},{c['L']}*{c['W']})*({c['H']}-{c['ded']})"
            if e.get('extra'):
                net += tok_local(e['extra'], r, B)
            if sec == 'piles':
                net = f"={c['n']}*{c['A']}*{c['L']}"
            wkey = 'waste.' + e['waste']
            pkey = 'concrete_piles_material' if sec == 'piles' else 'concrete_b30'
            vals = [no, e['id'], e['name'], FLOOR_HE.get(e['floor'], e['floor']), B.steps.get(e['step'], e['step']), e['loc'], n_, L, W, H, Aval, P, ded or 0,
                    e['shape'], net, f"={B.P(wkey)}", f"={c['net']}*(1+{c['waste']})", f"={B.PR(pkey)}", f"={c['order']}*{c['price']}",
                    STATUS_HE.get(e['status'], e['status']), e['source']]
            S.row(r, vals, [QTY, None, None, None, None, None, QTY, NUM3, NUM3, NUM3, NUM3, NUM3, NUM3, None, NUM3, PCT1, NUM3, NIS, NIS], fill=BAND_FILL if i % 2 else None,
                  note=e.get('note') or None, wrap_cols=(CC['src'],))
            if e['status'] in ('provisional', 'approx', 'missing'):
                S.paint(r, CC['status'], WARN_FILL)
            B.concRows[e['id'] + '|' + sec] = r; e['row'] = r
            r += 1
        r1 = r - 1
        col = lambda k: col_letter(CC[k])
        S.row(r, [None, None, f"סה\"כ – {title.split('(')[0].strip()}", None, None, None, None, None, None, None, None, None, None, None,
                  f"=SUM({col('net')}{r0}:{col('net')}{r1})", None, f"=SUM({col('order')}{r0}:{col('order')}{r1})", None, f"=SUM({col('cost')}{r0}:{col('cost')}{r1})"],
              [None] * 14 + [NUM3, None, NUM3, None, NIS], bold=True, fill=TOTAL_FILL, top=True)
        secTot[sec] = r
        r += 2
    B.concElem = (min(e['row'] for e in E), max(e['row'] for e in E))
    # grand total of concrete (piles separate: priced per metre)
    col = lambda k: col_letter(CC[k])
    S.section(r, 'סיכום בטון – שלד'); r += 1
    S.header(r, ['', '', 'פריט', '', '', '', '', '', '', '', '', '', '', '', 'נפח נטו (מ"ק)', '', 'נפח להזמנה (מ"ק)', '', 'עלות חומר (₪)'], h=30); r += 1
    nonPile = [s for s in secTot if s != 'piles']
    S.row(r, [None, None, 'בטון ב-30 – כל השלד בלי כלונסאות', None, None, None, None, None, None, None, None, None, None, None,
              '=' + '+'.join(f"{col('net')}{secTot[s]}" for s in nonPile), None, '=' + '+'.join(f"{col('order')}{secTot[s]}" for s in nonPile), None,
              '=' + '+'.join(f"{col('cost')}{secTot[s]}" for s in nonPile)], [None] * 14 + [NUM3, None, NUM3, None, NIS], bold=True, fill=TOTAL_FILL)
    B.concTotal = r; r += 1
    S.row(r, [None, None, 'בטון כלונסאות (נכלל במחיר מטר הכלונס – בפרק כלונסאות)', None, None, None, None, None, None, None, None, None, None, None,
              f"={col('net')}{secTot['piles']}", None, f"={col('order')}{secTot['piles']}", None, f"={col('cost')}{secTot['piles']}"],
          [None] * 14 + [NUM3, None, NUM3, None, NIS])
    B.pileConcRow = r; r += 2
    B.secTot = secTot
    # ---- piles priced per drilled metre + tests
    S.section(r, 'כלונסאות – קידוח, יציקה ובדיקות (מחיר למטר כלונס, כולל בטון, בלי ברזל)'); r += 1
    S.header(r, ['', '', 'פריט', '', '', '', "יח'", '', '', '', '', '', '', 'חישוב', 'כמות', '', '', '₪ ליח\'', 'עלות (₪)'], h=30); r += 1
    r0 = r
    pr = [e for e in E if e['sec'] == 'piles']
    for d, Lmax, key in ((0.5, 12, 'pile_m_50_12'), (0.5, 99, 'pile_m_50_20'), (0.6, 12, 'pile_m_60_12'), (0.6, 99, 'pile_m_60_20')):
        rows = [e['row'] for e in pr if e['W'] == d and (e['L'] <= 12) == (Lmax == 12)]
        if not rows:
            continue
        f = '+'.join(f"{col('L')}{x}" for x in rows)
        S.row(r, [None, None, f"כלונס קדוח ø{int(d*100)} {'עד 12 מ' if Lmax == 12 else '12–20 מ'}' – מטר קידוח ({len(rows)} כלונסאות)", None, None, None, "מ'", None, None, None, None, None, None, 'Σ L',
                  f"={f}", None, None, f"={B.PR(key)}", f"=P{r}*S{r}"], [None] * 14 + [NUM, None, None, NIS, NIS], note='K-400 טבלת כלונסאות; קידוח יבש; מחיר כולל בטון, בלי ברזל')
        r += 1
    S.row(r, [None, None, 'בדיקה סונית – עד 40 כלונסאות (K-400: "בדיקות סוניות בכל הכלונסאות לאחר 7 ימים")', None, None, None, "קומפ'", None, None, None, None, None, None, '',
              1, None, None, f"={B.PR('sonic_lump')}", f"=P{r}*S{r}"], [None] * 14 + [QTY, None, None, NIS, NIS]); r += 1
    S.row(r, [None, None, 'בדיקה סונית – תוספת לכלונס מעל 40', None, None, None, "יח'", None, None, None, None, None, None, "מס' כלונסאות − 40",
              f"=MAX(0,{len(pr)}-40)", None, None, f"={B.PR('sonic_extra')}", f"=P{r}*S{r}"], [None] * 14 + [QTY, None, None, NIS, NIS]); r += 1
    S.row(r, [None, None, 'ניסיון קידוח בשיטה יבשה (K-400)', None, None, None, 'קומפ\'', None, None, None, None, None, None, '', 1, None, None, f"={B.PR('pile_trial')}", f"=P{r}*S{r}"],
          [None] * 14 + [QTY, None, None, NIS, NIS]); r += 1
    S.row(r, [None, None, 'סה"כ כלונסאות', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, f"=SUM(T{r0}:T{r-1})"],
          [None] * 18 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.sum['02.1 כלונסאות – קידוח, בטון, בדיקות'] = (f"{q('conc')}!T{r}", 'מחיר למטר כולל בטון; הברזל בגיליון "02 ברזל"')
    r += 2
    # ---- lean concrete + void formers
    G = J('data/structure/floor-ground.json'); bas = J('data/structure/basement.json')
    lean = J('data/structure/excavation.json')['bottomBuildUp']
    under = defaultdict(float)
    for p in G['underSlab']['pieces']:
        under[p['on']] += p['area_m2']
    S.section(r, 'בטון רזה וארגזי הפרדה (פוליביד) מתחת לרצפות התלויות ולקורות'); r += 1
    S.header(r, ['', '', 'פריט', '', '', '', "יח'", '', 't (מ\')', '', 'A (מ"ר)', '', '', 'חישוב', 'כמות נטו', 'פחת', 'כמות להזמנה', '₪ ליח\'', 'עלות (₪)'], h=30); r += 1
    r0 = r
    Ag = round(sum(under.values()), 3); Ab = bas['area_m2']
    for label, A, src in ((f"מתחת לרצפת הקרקע וקורות K-21 ({len(G['underSlab']['pieces'])} קטעים)", Ag, 'data/structure/floor-ground.json underSlab.pieces'),
                          ('מתחת לרצפת המרתף וקורות המרתף (קו המרתף)', Ab, 'data/structure/basement.json area_m2 (קו חיצוני K-11)')):
        S.row(r, [None, None, 'בטון רזה ב-15/ב-20 ' + label, None, B.steps['basementSlab' if 'מרתף' in label else 'underSlab'], None, 'מ"ק', None, lean[1]['thickness_m'], None, A, None, None, 'A·t',
                  f"=L{r}*J{r}", f"={B.P('waste.concreteLean')}", f"=P{r}*(1+Q{r})", f"={B.PR('concrete_lean')}", f"=R{r}*S{r}"],
              [None] * 8 + [NUM3, None, NUM3, None, None, None, NUM3, PCT1, NUM3, NIS, NIS], note=lean[1]['source'][:120])
        S.row(r + 1, [None, None, 'ארגזי הפרדה 25 ס"מ (פוליביד / קרטון כוורת) ' + label, None, B.steps['basementSlab' if 'מרתף' in label else 'underSlab'], None, 'מ"ר', None, lean[2]['thickness_m'], None, A, None, None, 'A',
                      f"=L{r+1}", f"={B.P('waste.voidFormers')}", f"=P{r+1}*(1+Q{r+1})", f"={B.PR('void_former')}", f"=R{r+1}*S{r+1}"],
              [None] * 8 + [NUM3, None, NUM3, None, None, None, NUM3, PCT1, NUM3, NIS, NIS], note=lean[2]['source'][:120])
        r += 2
    S.row(r, [None, None, 'סה"כ בטון רזה וארגזי הפרדה', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, f"=SUM(T{r0}:T{r-1})"],
          [None] * 18 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.sum['02.2 בטון רזה וארגזי הפרדה'] = (f"{q('conc')}!T{r}", 'K-400 פרט רצפה תלויה')
    B.leanRow = r0
    r += 2
    # ---- concrete material + placing + pump
    S.section(r, 'בטון – חומר, יציקה ושאיבה'); r += 1
    S.header(r, ['', '', 'פריט', '', '', '', "יח'", '', '', '', '', '', '', 'חישוב', 'כמות', '', '', '₪ ליח\'', 'עלות (₪)'], h=30); r += 1
    r0 = r
    S.row(r, [None, None, 'בטון ב-30 מובא (חומר, כולל פחת)', None, None, None, 'מ"ק', None, None, None, None, None, None, 'Σ להזמנה', f"=R{B.concTotal}", None, None, f"=S{r}" if False else None,
              f"=T{B.concTotal}"], [None] * 14 + [NUM3, None, None, NIS, NIS]); r += 1
    pours = sorted({e['step'] for e in E if e['sec'] != 'piles'}, key=lambda s: list(B.steps).index(s) if s in B.steps else 99)
    S.row(r, [None, None, 'יציקה, ויברציה והחלקה (עבודה) – נפח נטו', None, None, None, 'מ"ק', None, None, None, None, None, None, 'Σ נטו', f"=P{B.concTotal}", None, None,
              f"={B.PR('concrete_placing')}", f"=P{r}*S{r}"], [None] * 14 + [NUM3, None, None, NIS, NIS]); r += 1
    S.row(r, [None, None, f"משאבת בטון – יציקה לכל שלב ({len(pours)} יציקות)", None, None, None, 'יציקה', None, None, None, None, None, None, 'מס\' שלבי יציקה',
              len(pours), None, None, f"={B.PR('pump_pour')}", f"=P{r}*S{r}"], [None] * 14 + [QTY, None, None, NIS, NIS],
          note='שלבי היציקה מרצף הבנייה במודל (data/config/tags.json sequence): ' + ', '.join(B.steps[s].split('· ')[1] for s in pours if s in B.steps)); r += 1
    S.row(r, [None, None, 'משאבת בטון – תוספת לכל מ"ק מעבר ל-10 ביציקה', None, None, None, 'מ"ק', None, None, None, None, None, None, 'Σ להזמנה − 10 × יציקות',
              f"=MAX(0,R{B.concTotal}-10*P{r-1})", None, None, f"={B.PR('pump_m3')}", f"=P{r}*S{r}"], [None] * 14 + [NUM3, None, None, NIS, NIS]); r += 1
    S.row(r, [None, None, 'סה"כ בטון – חומר, יציקה ושאיבה', None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, f"=SUM(T{r0}:T{r-1})"],
          [None] * 18 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.sum['02.3 בטון ב-30 – חומר, יציקה ושאיבה'] = (f"{q('conc')}!T{r}", 'בלי כלונסאות')
    B.qty['בטון ב-30 שלד (נטו, בלי כלונסאות)'] = (f"{q('conc')}!P{B.concTotal}", 'מ"ק')
    B.qty['בטון ב-30 להזמנה (כולל פחת)'] = (f"{q('conc')}!R{B.concTotal}", 'מ"ק')
    B.qty['בטון כלונסאות (תיאורטי)'] = (f"{q('conc')}!P{B.pileConcRow}", 'מ"ק')
    B.pours = pours
    S.finish(r)


# ------------------------------------------------------------------ formwork
FW_HE = {'walls': 'קירות', 'columns': 'עמודים', 'beams': 'קורות', 'slabs': 'תקרות (תחתית)', 'edges': 'שוליים / לחיים'}


def build_formwork(B, E):
    ws = B.ws['fw']
    S = Sheet(ws, note_col=12, widths={'A': 2, 'B': 5, 'C': 13, 'D': 32, 'E': 18, 'F': 14, 'G': 34, 'H': 13, 'I': 9, 'J': 13, 'K': 14, 'L': 40})
    S.title(1, 'פרק 02 – טפסנות | שטח מגע לכל אלמנט וחומרים נדרשים',
            'שטח המגע מחושב מהמידות שבגיליון "02 בטון" (נוסחה חיה). חומרים: לוחות 18 מ"מ, קורות עץ 5×10, תמיכות טלסקופיות – לפי מספר שימושים ומקדמים בגיליון "הנחות ופחת". '
            'רצפות תלויות: התחתית על ארגזי הפרדה – רק שוליים. כלונסאות – בלי טפסנות.')
    r = 3
    S.section(r, 'שטח מגע לפי אלמנט'); r += 1
    S.header(r, ["מס'", 'מזהה', 'אלמנט', 'שלב ביצוע', 'סוג', 'חישוב', 'כמות', "יח'"]); r += 1
    r0 = r; no = 0
    for e in E:
        for (typ, tpl, desc) in e.get('fw', []):
            if tpl == '0':
                continue
            no += 1
            S.row(r, [no, e['id'], e['name'], B.steps.get(e['step'], e['step']), FW_HE[typ], desc, '=' + tok(tpl, e['row'], B), 'מ"ר'],
                  [QTY, None, None, None, None, None, NUM], fill=BAND_FILL if no % 2 == 0 else None)
            r += 1
        for key, unit, label in (('props', "יח'", 'תמיכות תקרה'), ('propsBeam', "יח'", 'תמיכות קורה')):
            if e.get(key):
                no += 1
                per = B.P('formwork.propsPer_m2') if key == 'props' else B.P('formwork.propsPer_m_beam')
                S.row(r, [no, e['id'], e['name'], B.steps.get(e['step'], e['step']), label, 'שטח × צפיפות' if key == 'props' else 'אורך × צפיפות',
                          f"=ROUNDUP({tok(e[key], e['row'], B)}*{per},0)", unit], [QTY, None, None, None, None, None, QTY], fill=BAND_FILL if no % 2 == 0 else None)
                r += 1
    r1 = r - 1
    B.fwRange = (r0, r1)
    r += 1
    S.section(r, 'ריכוז שטח מגע לפי סוג'); r += 1
    S.header(r, ['', 'סוג', '', '', '', '', 'שטח מגע (מ"ר)', "יח'"], h=30); r += 1
    tot = {}
    for typ, he in FW_HE.items():
        S.row(r, [None, he, None, None, None, None, f"=SUMIF($F${r0}:$F${r1},\"{he}\",$H${r0}:$H${r1})", 'מ"ר'], [None] * 6 + [NUM]); tot[typ] = f"H{r}"; r += 1
    S.row(r, [None, 'סה"כ שטח טפסנות', None, None, None, None, '=' + '+'.join(tot.values()), 'מ"ר'], [None] * 6 + [NUM], bold=True, fill=TOTAL_FILL, top=True)
    totAll = f"H{r}"; B.qty['טפסנות – שטח מגע'] = (f"{q('fw')}!H{r}", 'מ"ר'); r += 1
    S.row(r, [None, 'תמיכות – סה"כ יח\' (בכל היציקות)', None, None, None, None, f"=SUMIF($F${r0}:$F${r1},\"תמיכות*\",$H${r0}:$H${r1})", "יח'"], [None] * 6 + [QTY], bold=True)
    props = f"H{r}"; r += 2
    # materials
    S.section(r, 'חומרים ועבודה – טפסנות'); r += 1
    S.header(r, ["מס'", 'פריט', '', '', '', 'חישוב', 'כמות', "יח'", '₪ ליח\'', 'עלות (₪)']); r += 1
    m0 = r
    Pp = B.P
    plyArea = (f"(({tot['walls']}+{tot['columns']}+{tot['edges']})/{Pp('formwork.reuse.walls')}+{tot['slabs']}/{Pp('formwork.reuse.slabs')}+{tot['beams']}/{Pp('formwork.reuse.beams')})"
               f"*(1+{Pp('waste.plywood')})")
    timber = (f"(({tot['walls']}+{tot['edges']})*{Pp('formwork.timber_m_per_m2.walls')}+{tot['columns']}*{Pp('formwork.timber_m_per_m2.columns')}+{tot['slabs']}*{Pp('formwork.timber_m_per_m2.slabs')}"
              f"+{tot['beams']}*{Pp('formwork.timber_m_per_m2.beams')})/{Pp('formwork.reuse.timber')}*(1+{Pp('waste.timber')})")
    items = [
        ('לוחות טפסנות 18 מ"מ 122×244 – מספר לוחות', 'Σ שטח / שימושים × (1+פחת) / 2.98', f"=ROUNDUP({plyArea}/{Pp('formwork.sheet_m2')},0)", "לוח", 'plywood_sheet'),
        ('קורות עץ 5×10 – מטר אורך', 'Σ שטח × מ\'/מ"ר / שימושים × (1+פחת)', f"=ROUNDUP({timber},0)", "מ'", 'timber_m'),
        ('תמיכות טלסקופיות – ימי השכרה', 'Σ תמיכות × ימים ליציקה', f"={props}*{Pp('formwork.propDays')}", 'יום-תמיכה', 'prop_day'),
        ('שמן תבניות', 'Σ שטח × ל\'/מ"ר', f"=ROUNDUP({totAll}*{Pp('formwork.oil_l_per_m2')},0)", "ליטר", 'form_oil'),
        ('מוטות קשירה (טייסים) + קונוסים לקירות', 'שטח קירות / 2 × צפיפות', f"=ROUNDUP(({tot['walls']}/2)*{Pp('formwork.tiesPer_m2')},0)", "יח'", 'tie_set'),
        ('מסמרים וחוטי קשירה', 'Σ שטח × ק"ג/מ"ר', f"=ROUNDUP({totAll}*{Pp('formwork.nails_kg_per_m2')},0)", 'ק"ג', 'nails_kg'),
    ]
    for i, (lab, calc, f, unit, pk) in enumerate(items):
        S.row(r, [i + 1, lab, None, None, None, calc, f, unit, f"={B.PR(pk)}", f"=H{r}*J{r}"], [QTY, None, None, None, None, None, QTY, None, NIS, NIS], fill=BAND_FILL if i % 2 else None)
        r += 1
    S.row(r, [None, 'סה"כ חומרי טפסנות', None, None, None, None, None, None, None, f"=SUM(K{m0}:K{r-1})"], [None] * 9 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.sum['02.4 טפסנות – חומרים (לוחות, עץ, תמיכות, אביזרים)'] = (f"{q('fw')}!K{r}", 'לפי מספר שימושים')
    r += 1
    S.row(r, [len(items) + 1, 'עבודת טפסנות (הרכבה ופירוק) – לפי שטח מגע', None, None, None, 'Σ שטח', f"={totAll}", 'מ"ר', f"={B.PR('formwork_labor')}", f"=H{r}*J{r}"],
          [QTY, None, None, None, None, None, NUM, None, NIS, NIS])
    r += 1
    S.row(r, [None, 'סה"כ עבודת טפסנות', None, None, None, None, None, None, None, f"=K{r-1}"], [None] * 9 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.sum['02.5 טפסנות – עבודה'] = (f"{q('fw')}!K{r}", '')
    B.fwTypeRefs = tot
    S.finish(r)


# ------------------------------------------------------------------ rebar
def build_rebar(B, E):
    ws = B.ws['rb']
    S = Sheet(ws, note_col=18, widths={'A': 2, 'B': 5, 'C': 12, 'D': 28, 'E': 18, 'F': 34, 'G': 6, 'H': 11, 'I': 14, 'J': 11, 'K': 9, 'L': 12, 'M': 7, 'N': 12, 'O': 8, 'P': 40, 'Q': 14, 'R': 30})
    S.title(1, 'פרק 02 – ברזל זיון | לפי פריסות הקונסטרוקטור',
            'מקורות: K-400 (כלונסאות, ראשי כלונס), K-12/22/32/42 (מוטות וחישוקים בקורות, ריכוזי מוטות בקירות ובעמודים), K-13/23/33/43 (רשתות ברצפות ובתקרות). '
            'ק"ג/מ\' = d²/162. רשת: מ\' מוט למ"ר = שכבות × (1/s₁ + 1/s₂). שורה "יחס" = ק"ג/מ"ק × נפח – רק כשאין פריסה (זמני).')
    r = 3
    S.section(r, 'ברזל לפי אלמנט'); r += 1
    S.header(r, ["מס'", 'מזהה', 'אלמנט', 'שלב ביצוע', 'פריט ברזל', 'ø מ"מ', 'כמות / מ\' למ"ר / יחס', "אורך (מ') / שטח (מ\"ר) / נפח", "סה\"כ מ'", 'ק"ג/מ\'', 'ק"ג נטו', 'פחת', 'ק"ג להזמנה', 'סטטוס', 'מקור'])
    r += 1
    r0 = r; no = 0
    concA = lambda e, k: f"{q('conc')}!${col_letter(CC[k])}${e['row']}"
    for e in E:
        for x in e.get('rb', []):
            no += 1
            st = x.get('status', 'provisional')
            if x.get('ratio'):
                ratio = B.P(f"rebar.ratio.{x['ratio']}")
                vals = [no, e['id'], e['name'], B.steps.get(e['step'], e['step']), x['desc'], None, f"={ratio}", f"={concA(e, 'net')}", None, None, f"=H{r}*I{r}",
                        f"={B.P('waste.rebar')}", f"=L{r}*(1+M{r})", STATUS_HE.get(st, st), x['src']]
                fm = [QTY, None, None, None, None, None, NUM, NUM3, None, None, NUM, PCT1, NUM]
            elif x.get('mesh'):
                lay, d, s1, s2 = x['mesh']
                area = f"={concA(e, 'L')}*{concA(e, 'H')}" if x.get('face') else f"={concA(e, 'A')}"
                vals = [no, e['id'], e['name'], B.steps.get(e['step'], e['step']), x['desc'], d, f"={lay}*(1/{s1/100}+1/{s2/100})", area, f"=H{r}*I{r}", f"=G{r}^2/162", f"=J{r}*K{r}",
                        f"={B.P('waste.mesh')}", f"=L{r}*(1+M{r})", STATUS_HE.get(st, st), x['src']]
                fm = [QTY, None, None, None, None, QTY, NUM3, NUM3, NUM, NUM3, NUM, PCT1, NUM]
            else:
                cnt = x['count']; ln = x['length']
                cntF = f"={tok(cnt, e['row'], B)}" if isinstance(cnt, str) else cnt
                lnF = f"={tok(ln, e['row'], B)}" if isinstance(ln, str) else ln
                vals = [no, e['id'], e['name'], B.steps.get(e['step'], e['step']), x['desc'], x['dia'], cntF, lnF, f"=H{r}*I{r}", f"=G{r}^2/162", f"=J{r}*K{r}",
                        f"={B.P('waste.rebar')}", f"=L{r}*(1+M{r})", STATUS_HE.get(st, st), x['src']]
                fm = [QTY, None, None, None, None, QTY, NUM, NUM3, NUM, NUM3, NUM, PCT1, NUM]
            S.row(r, vals, fm, fill=BAND_FILL if no % 2 == 0 else None, wrap_cols=(16,))
            if st != 'source':
                S.paint(r, 15, WARN_FILL)
            r += 1
    r1 = r - 1
    r += 1
    S.section(r, 'ריכוז ברזל'); r += 1
    S.header(r, ["מס'", 'פריט', '', '', '', '', '', '', '', '', 'ק"ג נטו', '', 'ק"ג להזמנה', "יח'", '₪ ליח\'', 'עלות (₪)'], h=30); r += 1
    m0 = r
    S.row(r, [1, 'ברזל לפי פריסה (מקור)', None, None, None, None, None, None, None, None, f"=SUMIF($O${r0}:$O${r1},\"מקור\",$L${r0}:$L${r1})", None,
              f"=SUMIF($O${r0}:$O${r1},\"מקור\",$N${r0}:$N${r1})"], [None] * 10 + [NUM, None, NUM]); r += 1
    S.row(r, [2, 'ברזל לפי הנחה / יחס (זמני)', None, None, None, None, None, None, None, None, f"=SUM($L${r0}:$L${r1})-L{r-1}", None,
              f"=SUM($N${r0}:$N${r1})-N{r-1}"], [None] * 10 + [NUM, None, NUM]); S.paint(r, 3, WARN_FILL); r += 1
    S.row(r, [3, 'סה"כ ברזל – מסופק, חתוך, מכופף ומותקן', None, None, None, None, None, None, None, None, f"=L{r-2}+L{r-1}", None, f"=N{r-2}+N{r-1}", 'טון',
              f"={B.PR('rebar_ton')}", f"=N{r}/1000*P{r}"], [None] * 10 + [NUM, None, NUM, None, NIS, NIS], bold=True)
    tonRow = r; r += 1
    S.row(r, [4, 'חוט קשירה (נכלל בדרך כלל במחיר ההתקנה – לבקרה)', None, None, None, None, None, None, None, None, None, None, f"=ROUNDUP(N{tonRow}/1000*{B.P('rebar.wireKgPerTon')},0)", 'ק"ג', 0, f"=N{r}*P{r}"],
          [None] * 10 + [None, None, QTY, None, NIS, NIS]); r += 1
    S.row(r, [5, 'ספייסרים (שומרי מרחק) – רצפות, תקרות, קירות', None, None, None, None, None, None, None, None, None, None,
              f"=ROUNDUP(({B.fwTypeRefs['slabs'].replace('H', q('fw') + '!H')}+{q('fw')}!{B.fwTypeRefs['walls']}+SUMIF({q('conc')}!$C:$C,\"GS*\",{q('conc')}!$L:$L)+SUMIF({q('conc')}!$C:$C,\"BS*\",{q('conc')}!$L:$L))*{B.P('rebar.spacersPer_m2')},0)",
              "יח'", f"={B.PR('spacer')}", f"=N{r}*P{r}"], [None] * 10 + [None, None, QTY, None, NIS, NIS]); r += 1
    S.row(r, [None, 'סה"כ ברזל', None, None, None, None, None, None, None, None, None, None, None, None, None, f"=SUM(Q{tonRow}:Q{r-1})"], [None] * 15 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.sum['02.6 ברזל זיון'] = (f"{q('rb')}!Q{r}", 'כולל כלונסאות; מחיר לטון מותקן')
    B.qty['ברזל – נטו'] = (f"{q('rb')}!L{tonRow}/1000", 'טון')
    B.qty['ברזל – להזמנה (כולל פחת)'] = (f"{q('rb')}!N{tonRow}/1000", 'טון')
    B.rbRange = (r0, r1)
    S.finish(r)


# ------------------------------------------------------------------ earthworks
def build_earth(B):
    ws = B.ws['ew']; MQ = J('docs/quantities/boq/model-quantities.json')['quantities']; X = MQ['excavation']; EV = X['earthworks']
    exc = J('data/structure/excavation.json'); lot = J('data/site/plot-5187.json')
    S = Sheet(ws, note_col=15, widths={'A': 2, 'B': 5, 'C': 44, 'D': 16, 'E': 30, 'F': 11, 'G': 9, 'H': 8, 'I': 11, 'J': 10, 'K': 11, 'L': 14, 'M': 8, 'N': 40, 'O': 40})
    S.title(1, 'פרק 01 – עבודות עפר | חישוף, יישור, חפירה, מילוי ודיפון',
            'נפחי העפר מחושבים במודל על גריד מול מודל הקרקע (מדידה 2025) ופני החפירה (שיפוע 1:2, מרווח עבודה 1.0 מ\', תחתית ‎-3.30) – js/geometry/excavation.js; '
            'הערכים מיוצאים ע"י tools/boq/export_model_quantities.mjs. נפחים בטבע (מהודק); מקדם תפיחה / הידוק – בגיליון "הנחות ופחת".')
    r = 3
    S.section(r, 'סעיפי עפר'); r += 1
    S.header(r, ["מס'", 'סעיף', 'שלב ביצוע', 'חישוב', 'בסיס (מודל)', "יח'", 'מקדם', 'כמות לחיוב', "יח' חיוב", '₪ ליח\'', 'עלות (₪)', 'סטטוס', 'מקור'])
    r += 1; r0 = r
    st = B.steps
    lotA = EV['strip'] / exc['earthworks']['stripping']['depth_m']
    rows = [
        ('חישוף פני השטח 20 ס"מ (צמחייה, מילוי ישן, פסולת) + פינוי', st['stripTopsoil'], 'שטח המגרש × 0.20', EV['strip'], 'מ"ק', 1, 'מ"ק', 'strip_m3', 'מקור', exc['earthworks']['stripping']['source']),
        ('יישור המגרש – חיתוך עד פני הפיתוח (K-400)', st['siteLevel'], 'גריד: max(0, קרקע מיושרת − קיימת)', EV['level'], 'מ"ק', 1, 'מ"ק', 'excavation_m3', 'מקור', exc['earthworks']['siteLevel']['source']),
        ('חפירת בור המרתף והבריכה בשיפוע 1:2 (מתחת למגרש המיושר)', st['excavation'], 'גריד מול קרקע 2025', X['pitVolume_m3'], 'מ"ק', 1, 'מ"ק', 'excavation_m3', 'מקור', exc['sideSlopeSource']),
        (f"חפירת תעלות לקורות יסוד מחוץ לבור ({X['trenchCount']} תעלות)", st['excavation'], 'Σ L × b × עומק', X['trenchVolume_m3'], 'מ"ק', 1, 'מ"ק', 'excavation_m3', 'זמני', 'js/geometry/excavation.js trenches'),
        ('חפירה לתחתית מבנה הרצפה מחוץ לבור (פורמציה)', st['underSlab'], 'גריד: בסיס − פני העבודה', EV['cutFormation'], 'מ"ק', 1, 'מ"ק', 'excavation_m3', 'מקור', exc['source'][:120]),
        ('בור שוחה / תא שאיבה', st['excavation'], 'נפח הבור', X['chamberPitVolume_m3'], 'מ"ק', 1, 'מ"ק', 'excavation_m3', 'זמני', 'data/structure/excavation.json'),
    ]
    cutRows = []
    for i, (lab, step, calc, base, unit, k, unitQ, pk, sts, src) in enumerate(rows):
        S.row(r, [i + 1, lab, step, calc, round(base, 3), unit, k, f"=F{r}*H{r}", unitQ, f"={B.PR(pk)}", f"=I{r}*K{r}", sts, src], [QTY, None, None, None, NUM, None, NUM, NUM, None, NIS, NIS],
              fill=BAND_FILL if i % 2 else None, wrap_cols=(14,))
        if sts != 'מקור':
            S.paint(r, 13, WARN_FILL)
        cutRows.append(r)
        r += 1
    n = len(rows)
    S.row(r, [n + 1, 'פינוי עודפי עפר לאתר מורשה (כל החפירה × תפיחה, פחות שימוש חוזר)', st['excavation'], 'Σ חפירה × תפיחה × (1 − שימוש חוזר)',
              '=' + '+'.join(f"F{x}" for x in cutRows), 'מ"ק', f"={B.P('earthworks.bulking')}*(1-{B.P('earthworks.reuseFill_pct')})", f"=F{r}*H{r}", 'מ"ק רופף',
              f"={B.PR('haul_m3')}", f"=I{r}*K{r}", 'זמני', exc['earthworks']['fill']['source'][:150]], [QTY, None, None, None, NUM, None, NUM3, NUM, None, NIS, NIS], wrap_cols=(14,))
    haul = r; r += 1
    S.row(r, [n + 2, '— מספר משאיות פינוי (לבקרה)', None, 'נפח רופף / נפח משאית', f"=I{haul}", 'מ"ק', f"=1/{B.P('earthworks.truck_m3')}", f"=ROUNDUP(F{r}*H{r},0)", 'משאיות', 0, 0, '', ''],
          [QTY, None, None, None, NUM, None, NUM3, QTY, None, NIS, NIS]); r += 1
    fill = exc['earthworks']['fill']
    S.row(r, [n + 3, 'מילוי חוזר לאורך קירות המרתף – מצע ג\' (חומר נברר), שכבות 20 ס"מ, 96% MOD.AASHTO', st['backfill'], 'גריד: פני עבודה − פני חפירה',
              round(EV['fillWalls'], 3), 'מ"ק מהודק', f"={B.P('earthworks.compaction')}", f"=F{r}*H{r}", 'מ"ק מובא', f"={B.PR('fill_m3')}", f"=F{r}*K{r}", 'מקור', fill['source'][:150]],
          [QTY, None, None, None, NUM, None, NUM, NUM, None, NIS, NIS], wrap_cols=(14,), note='מחיר למ"ק מהודק; "כמות לחיוב" = נפח רופף להזמנה. ' + ' | '.join(fill.get('conflicts', []))); r += 1
    S.row(r, [n + 4, 'מילוי מתחת לרצפות מחוץ לבור – מצע ג\' מהודק', st['backfill'], 'גריד', round(EV['fillSlabs'], 3), 'מ"ק מהודק', f"={B.P('earthworks.compaction')}",
              f"=F{r}*H{r}", 'מ"ק מובא', f"={B.PR('fill_m3')}", f"=F{r}*K{r}", 'מקור', fill['source'][:150]], [QTY, None, None, None, NUM, None, NUM, NUM, None, NIS, NIS], wrap_cols=(14,)); r += 1
    S.row(r, [n + 5, f"דיפון זמני – {X['shoringLength_m']:.1f} מ' באורך, גובה עד {X['shoringMaxHeight_m']:.2f} מ' (חסר תכנון דיפון)", st['excavation'], 'אורך × גובה חתך',
              round(X['shoringArea_m2'], 3), 'מ"ר', 1, f"=F{r}*H{r}", 'מ"ר', f"={B.PR('shoring_m2')}", f"=I{r}*K{r}", 'זמני', exc['shoringRule'][:150]],
          [QTY, None, None, None, NUM, None, NUM, NUM, None, NIS, NIS], wrap_cols=(14,), note=exc['shoringNote'][:200]); S.paint(r, 13, WARN_FILL); r += 1
    S.row(r, [n + 6, 'הידוק שתית בתחתית החפירה', st['excavation'], 'שטח תחתית', round(X['bottomArea_m2'], 3), 'מ"ר', 1, f"=F{r}*H{r}", 'מ"ר', f"={B.PR('compaction_m2')}", f"=I{r}*K{r}", 'זמני', 'דוח הקרקע §10'],
          [QTY, None, None, None, NUM, None, NUM, NUM, None, NIS, NIS], wrap_cols=(14,)); r += 1
    S.row(r, [None, 'סה"כ עבודות עפר', None, None, None, None, None, None, None, None, f"=SUM(L{r0}:L{r-1})"], [None] * 10 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.sum['01 עבודות עפר'] = (f"{q('ew')}!L{r}", 'נפחי עפר מהמודל (גריד)')
    B.qty['חפירה כוללת (בטבע)'] = (f"SUM({q('ew')}!F{r0+1}:F{r0+5})", 'מ"ק')
    B.qty['מילוי מצע ג\' (מהודק)'] = (f"{q('ew')}!F{haul+2}+{q('ew')}!F{haul+3}", 'מ"ק')
    B.ewRows = (r0, r)
    S.finish(r)


# ------------------------------------------------------------------ waterproofing & drainage
def build_wp(B, E):
    ws = B.ws['wp']; F = J('data/structure/framing.json'); exc = J('data/structure/excavation.json'); per = J('data/structure/perimeter.json')
    S = Sheet(ws, note_col=14, widths={'A': 2, 'B': 5, 'C': 46, 'D': 18, 'E': 30, 'F': 11, 'G': 8, 'H': 8, 'I': 11, 'J': 12, 'K': 14, 'L': 8, 'M': 40, 'N': 40})
    S.title(1, 'פרק 05 – איטום קירות המרתף וניקוז | זמני עד פרט יועץ איטום',
            'אין פרט איטום במקורות (דוח הקרקע §11; K-11/K-21: "מריחת איטום – ראה פרט יועץ איטום"). המבנה כאן = המבנה הזמני במודל: פריימר + 2 יריעות ביטומניות + לוח הגנה. '
            'ניקוז: "כדור" חצץ ø30 בבד גיאוטכני 250 גר\' + צינור 4" כל 2.5 מ\' (K-400 חתך קיר).')
    r = 3
    S.section(r, 'סעיפי איטום וניקוז'); r += 1
    S.header(r, ["מס'", 'סעיף', 'שלב ביצוע', 'חישוב', 'כמות נטו', "יח'", 'פחת', 'כמות להזמנה', '₪ ליח\'', 'עלות (₪)', 'סטטוס', 'מקור'])
    r += 1; r0 = r
    wp = F['waterproofing']
    S.row(r, [1, 'פריימר ביטומני לקירות המרתף (פני חוץ)', B.steps['waterproofing'], 'היקף × גובה', wp['area_m2'], 'מ"ר', 0, f"=F{r}*(1+H{r})", f"={B.PR('primer_m2')}", f"=I{r}*J{r}", 'זמני', wp['source'][:120]],
          [QTY, None, None, None, NUM, None, PCT1, NUM, NIS, NIS], wrap_cols=(13,), note=f"היקף {wp['perimeter_m']:.2f} מ' × {wp['topRel']-wp['bottomRel']:.2f} מ'"); r += 1
    S.row(r, [2, 'יריעות ביטומניות SBS 4 מ"מ – 2 שכבות', B.steps['waterproofing'], 'שטח × שכבות', f"={wp['area_m2']}*{B.P('membrane.layers')}", 'מ"ר', f"={B.P('waste.membrane')}", f"=F{r}*(1+H{r})",
              f"={B.PR('membrane_m2')}", f"=I{r}*J{r}", 'זמני', wp['source'][:120]], [QTY, None, None, None, NUM, None, PCT1, NUM, NIS, NIS], wrap_cols=(13,)); r += 1
    S.row(r, [3, 'לוח הגנה (פוליסטירן / לוח ביטומני) לפני המילוי החוזר', B.steps['waterproofing'], 'שטח', wp['area_m2'], 'מ"ר', f"={B.P('waste.geotextile')}", f"=F{r}*(1+H{r})",
              f"={B.PR('protection_board_m2')}", f"=I{r}*J{r}", 'זמני', wp['source'][:120]], [QTY, None, None, None, NUM, None, PCT1, NUM, NIS, NIS], wrap_cols=(13,)); r += 1
    Lp = sum(w['length_m'] for w in per['walls'])
    S.row(r, [4, '"כדור" חצץ שטוף ø30 בגב החומות', B.steps['perimeterWalls'], 'π/4·0.3² × אורך החומות', f"=PI()/4*0.3^2*{Lp:.3f}", 'מ"ק', f"={B.P('waste.gravel')}", f"=F{r}*(1+H{r})",
              f"={B.PR('gravel_m3')}", f"=I{r}*J{r}", 'זמני', exc['earthworks']['wallDrain']['source']], [QTY, None, None, None, NUM, None, PCT1, NUM, NIS, NIS], wrap_cols=(13,),
          note=f"אורך החומות {Lp:.2f} מ' (data/structure/perimeter.json) – לבדוק איזה קיר מתאר החתך ב-K-400 (קיר מרתף / חומה)"); r += 1
    S.row(r, [5, 'בד גיאוטכני 250 גר\'/מ"ר עוטף את החצץ', B.steps['perimeterWalls'], 'π·0.3 × 1.15 (חפייה) × אורך', f"=PI()*0.3*1.15*{Lp:.3f}", 'מ"ר', f"={B.P('waste.geotextile')}", f"=F{r}*(1+H{r})",
              f"={B.PR('geotextile_m2')}", f"=I{r}*J{r}", 'זמני', exc['earthworks']['wallDrain']['source']], [QTY, None, None, None, NUM, None, PCT1, NUM, NIS, NIS], wrap_cols=(13,)); r += 1
    S.row(r, [6, 'צינורות ניקוז 4" דרך החומה, כל 2.5 מ\' (אורך 0.4 מ\' ליח\')', B.steps['perimeterWalls'], 'ROUNDUP(אורך / 2.5) × 0.4', f"=ROUNDUP({Lp:.3f}/2.5,0)*0.4", "מ'", f"={B.P('waste.drainPipe')}", f"=F{r}*(1+H{r})",
              f"={B.PR('drain_pipe_m')}", f"=I{r}*J{r}", 'זמני', exc['earthworks']['wallDrain']['source']], [QTY, None, None, None, NUM, None, PCT1, NUM, NIS, NIS], wrap_cols=(13,)); r += 1
    S.row(r, [None, 'סה"כ איטום וניקוז', None, None, None, None, None, None, None, f"=SUM(K{r0}:K{r-1})"], [None] * 9 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.sum['05 איטום קירות המרתף וניקוז (זמני)'] = (f"{q('wp')}!K{r}", 'אין פרט איטום – זמני')
    S.finish(r)


# ------------------------------------------------------------------ blocks (stage 4a)
def build_blocks(B):
    ws = B.ws['blk']; O = J('docs/quantities/blocks-order.json'); BD = J('docs/quantities/blocks-bonding.json'); BA = J('data/architecture/blocks.json'); BC = J('data/config/blocks.json')
    S = Sheet(ws, note_col=15, widths={'A': 2, 'B': 5, 'C': 14, 'D': 30, 'E': 9, 'F': 11, 'G': 11, 'H': 11, 'I': 11, 'J': 8, 'K': 11, 'L': 12, 'M': 14, 'N': 40, 'O': 40})
    S.title(1, 'פרק 04 – בנייה בבלוקים | איטונג 60×25, משקופים וארגזי תריס',
            'כמויות הבלוקים לפי פריסת הנדבכים בפועל במודל (tools/extract_blocks.py --xlsx → docs/quantities/blocks-order.json: שלמים + חתוכים, חתיכות מבלוק שלם עם שארית שימושית). '
            'משקופים: data/architecture/blocks.json (בלוק U ממולא בטון וזיון; הישענות 20 ס"מ – זמני). ארגזי תריס: מובנים בעובי הקיר (החלטת אביחי 08.11.2026).')
    r = 3
    S.section(r, 'בלוקים לפי קומה ועובי'); r += 1
    S.header(r, ["מס'", 'קומה', 'עובי', 'שטח קיר (מ"ר)', 'שלמים', 'חתוכים (מקומות)', 'בלוקים לחיתוכים', 'סה"כ בלוקים', 'פחת', 'להזמנה (יח\')', '₪ לבלוק', 'עלות (₪)', 'מקור'])
    r += 1; r0 = r
    for i, x in enumerate(O['rows']):
        pk = f"ytong_{x['thickness_cm']}"
        S.row(r, [i + 1, FLOOR_HE.get(x['floor'], x['floor']), f"{x['thickness_cm']} ס\"מ", x['area_m2'], x['full'], x['cutPositions'], x['blocksForCuts'], f"=F{r}+H{r}",
                  f"={B.P('waste.blocks')}", f"=ROUNDUP(I{r}*(1+J{r}),0)", f"={B.PR(pk)}", f"=K{r}*L{r}", 'docs/quantities/blocks-order.json'],
              [QTY, None, None, NUM, QTY, QTY, QTY, QTY, PCT1, QTY, NIS, NIS], fill=BAND_FILL if i % 2 else None)
        r += 1
    S.row(r, [None, 'סה"כ בלוקים', None, f"=SUM(E{r0}:E{r-1})", f"=SUM(F{r0}:F{r-1})", f"=SUM(G{r0}:G{r-1})", f"=SUM(H{r0}:H{r-1})", f"=SUM(I{r0}:I{r-1})", None,
              f"=SUM(K{r0}:K{r-1})", None, f"=SUM(M{r0}:M{r-1})"], [None, None, None, NUM, QTY, QTY, QTY, QTY, None, QTY, None, NIS], bold=True, fill=TOTAL_FILL, top=True)
    blkTot = r; B.qty['בלוקי איטונג – שטח קירות'] = (f"{q('blk')}!E{r}", 'מ"ר'); B.qty['בלוקי איטונג – להזמנה'] = (f"{q('blk')}!K{r}", "יח'")
    r += 2
    S.section(r, 'טיט לנדבך ראשון ודבק בלוקים (שכבה דקה)'); r += 1
    S.header(r, ["מס'", 'פריט', '', 'נטו (ליטר)', 'ק"ג/ליטר', 'נטו (ק"ג)', 'פחת', 'ק"ג להזמנה', 'ק"ג לשק', 'שקים', '₪ לשק', 'עלות (₪)', 'מקור'], h=30); r += 1
    b0 = r
    bond = BC['bonding']
    mort = sum(x['mortar_l'] for x in BD['rows']); adh = sum(x['adhesive_l'] for x in BD['rows'])
    for i, (lab, lit, kgl, bag, pk) in enumerate((('טיט מלט – נדבך ראשון 2 ס"מ', mort, bond['firstCourse']['kgPerLitre']['value'], bond['firstCourse']['bagKg']['value'], 'mortar_bag'),
                                                  ('דבק בלוקים ייעודי 3 מ"מ', adh, bond['adhesive']['kgPerLitre']['value'], bond['adhesive']['bagKg']['value'], 'adhesive_bag'))):
        S.row(r, [i + 1, lab, None, round(lit, 1), kgl, f"=E{r}*F{r}", f"={B.P('waste.adhesive')}", f"=G{r}*(1+H{r})", bag, f"=ROUNDUP(I{r}/J{r},0)", f"={B.PR(pk)}", f"=K{r}*L{r}",
                  'docs/quantities/blocks-bonding.json'], [QTY, None, None, NUM, NUM, NUM, PCT1, NUM, QTY, QTY, NIS, NIS])
        S.paint(r, 6, WARN_FILL); r += 1
    S.row(r, [None, 'סה"כ טיט ודבק', None, None, None, None, None, None, None, None, None, f"=SUM(M{b0}:M{r-1})"], [None] * 11 + [NIS], bold=True, fill=TOTAL_FILL, top=True)
    bondTot = r; r += 2
    # lintels
    S.section(r, 'משקופים – בלוק משקוף U ממולא בטון וזיון'); r += 1
    S.header(r, ["מס'", 'מזהה', 'קיר / פתח', 'עובי (מ\')', 'פתח L (מ\')', 'הישענות ימין', 'הישענות שמאל', 'אורך משקוף', 'בלוקי U (60)', 'בטון מילוי (מ"ק)', '₪ לבלוק U', 'עלות (₪)', 'סטטוס'])
    r += 1; l0 = r
    walls = {w['id']: w for w in BA['walls']}
    k = 0
    for w in BA['walls']:
        for lt in w.get('lintels', []):
            k += 1
            thin = w['thickness_m'] < BC['lintel']['thinBelow_m']
            S.row(r, [k, lt['id'], f"{w['id']} / {lt['opening']}", w['thickness_m'], lt['length_m'], lt.get('bearR_m', 0), lt.get('bearL_m', 0), f"=F{r}+G{r}+H{r}",
                      f"=ROUNDUP(I{r}/0.6,0)", f"=I{r}*MAX(E{r}-0.05,0.05)*0.15", f"={B.PR('lintel_precast_m' if thin else 'u_lintel_block')}" + (f"*I{r}/J{r}" if thin else ''),
                      f"=J{r}*L{r}", STATUS_HE.get(lt.get('status'), lt.get('status'))],
                  [QTY, None, None, NUM3, NUM3, NUM3, NUM3, NUM3, QTY, NUM3, NIS, NIS], fill=BAND_FILL if k % 2 == 0 else None,
                  note='מחיצה דקה – משקוף טרומי (לאישור סוג)' if thin else None)
            r += 1
    S.row(r, [None, 'סה"כ משקופים', None, None, None, None, None, f"=SUM(I{l0}:I{r-1})", f"=SUM(J{l0}:J{r-1})", f"=SUM(K{l0}:K{r-1})", None, f"=SUM(M{l0}:M{r-1})"],
          [None] * 7 + [NUM3, QTY, NUM3, None, NIS], bold=True, fill=TOTAL_FILL, top=True)
    linTot = r; r += 2
    S.section(r, 'ארגזי תריס גלילה מובנים בעובי הקיר'); r += 1
    S.header(r, ["מס'", 'פתח', 'קיר', 'קומה', 'רוחב פתח (מ\')', 'גובה ארגז (מ\')', 'עומק (מ\')', 'אורך ארגז (מ\')', '', '', '₪ למ\'', 'עלות (₪)', 'מקור']); r += 1
    s0 = r
    for i, sb in enumerate(BA['shutterBoxes']):
        S.row(r, [i + 1, sb['opening'], sb.get('hostWall', ''), FLOOR_HE.get(sb['floor'], sb['floor']), sb['width_m'], sb['box_m'], sb.get('depth_m'), f"=F{r}", None, None,
                  f"={B.PR('shutter_box_m')}", f"=I{r}*L{r}", sb['source'][:80]], [QTY, None, None, None, NUM3, NUM3, NUM3, NUM3, None, None, NIS, NIS], fill=BAND_FILL if i % 2 else None)
        r += 1
    S.row(r, [None, 'סה"כ ארגזי תריס', None, None, f"=SUM(F{s0}:F{r-1})", None, None, f"=SUM(I{s0}:I{r-1})", None, None, None, f"=SUM(M{s0}:M{r-1})"], [None] * 4 + [NUM3, None, None, NUM3, None, None, None, NIS],
          bold=True, fill=TOTAL_FILL, top=True)
    boxTot = r; r += 2
    S.section(r, 'עבודה'); r += 1
    S.header(r, ["מס'", 'פריט', '', 'כמות', "יח'", '', '', '', '', '', '₪ ליח\'', 'עלות (₪)'], h=30); r += 1
    S.row(r, [1, 'בניית קירות בלוקים בהדבקה (עבודה)', None, f"=E{blkTot}", 'מ"ר', None, None, None, None, None, f"={B.PR('block_labor_m2')}", f"=E{r}*L{r}"], [QTY, None, None, NUM, None, None, None, None, None, None, NIS, NIS]); r += 1
    S.row(r, [2, 'מחברי פלדה / רשת לבטון – מרווח לא נקבע (חסר)', None, None, "יח'", None, None, None, None, None, 0, 0], [QTY, None, None, NUM, None, None, None, None, None, None, NIS, NIS],
          note=BC['bonding']['ties']['note']); S.paint(r, 3, WARN_FILL); r += 1
    S.row(r, [None, 'סה"כ פרק 04', None, None, None, None, None, None, None, None, None, f"=M{blkTot}+M{bondTot}+M{linTot}+M{boxTot}+M{r-2}+M{r-1}"], [None] * 11 + [NIS], bold=True, hero=True, fill=HERO_FILL, top=True)
    B.sum['04 בנייה בבלוקים, משקופים וארגזי תריס'] = (f"{q('blk')}!M{r}", 'כמויות לפי פריסת הנדבכים במודל')
    S.finish(r)


# ------------------------------------------------------------------ by step
def build_steps(B, E):
    ws = B.ws['step']
    S = Sheet(ws, note_col=10, widths={'A': 2, 'B': 30, 'C': 13, 'D': 14, 'E': 13, 'F': 15, 'G': 15, 'H': 15, 'I': 15, 'J': 40})
    S.title(1, 'כמויות לפי שלב ביצוע | רצף הבנייה במודל', 'שלבים מ-data/config/tags.json (sequence) – אותו רצף כמו לוח "שלב אחר שלב" במודל. נוסחאות SUMIF על הגיליונות "02 בטון", "02 טפסנות", "02 ברזל".')
    r = 3
    S.section(r, 'שלד – לפי שלב'); r += 1
    S.header(r, ['שלב', 'בטון נטו (מ"ק)', 'שטח טפסנות (מ"ר)', 'ברזל להזמנה (ק"ג)', 'עלות בטון חומר (₪)', 'עבודת טפסנות (₪)', 'ברזל (₪)', 'סה"כ שלב (₪)']); r += 1
    r0 = r
    used = [s for s in B.steps if any(e['step'] == s for e in E)]
    fr0, fr1 = B.fwRange; rr0, rr1 = B.rbRange
    for i, s in enumerate(used):
        lab = B.steps[s]
        c0, c1 = B.concElem
        S.row(r, [lab, f"=SUMIF({q('conc')}!$F${c0}:$F${c1},$B{r},{q('conc')}!$P${c0}:$P${c1})", f"=SUMIFS({q('fw')}!$H${fr0}:$H${fr1},{q('fw')}!$E${fr0}:$E${fr1},$B{r},{q('fw')}!$I${fr0}:$I${fr1},\"מ\"\"ר\")",
                  f"=SUMIF({q('rb')}!$E${rr0}:$E${rr1},$B{r},{q('rb')}!$N${rr0}:$N${rr1})", f"=SUMIF({q('conc')}!$F${c0}:$F${c1},$B{r},{q('conc')}!$T${c0}:$T${c1})",
                  f"=D{r}*{B.PR('formwork_labor')}", f"=E{r}/1000*{B.PR('rebar_ton')}", f"=F{r}+G{r}+H{r}"],
              [None, NUM, NUM, NUM, NIS, NIS, NIS, NIS], fill=BAND_FILL if i % 2 else None)
        r += 1
    S.row(r, ['סה"כ', f"=SUM(C{r0}:C{r-1})", f"=SUM(D{r0}:D{r-1})", f"=SUM(E{r0}:E{r-1})", f"=SUM(F{r0}:F{r-1})", f"=SUM(G{r0}:G{r-1})", f"=SUM(H{r0}:H{r-1})", f"=SUM(I{r0}:I{r-1})"],
          [None, NUM, NUM, NUM, NIS, NIS, NIS, NIS], bold=True, fill=TOTAL_FILL, top=True)
    B.stepTot = r
    r += 1
    S.note(r, 'הערה: בטון כלונסאות נספר בשלבי הכלונסאות בנפח בלבד (המחיר שלו בתוך מחיר מטר הכלונס); חומרי טפסנות (לוחות, עץ, תמיכות) מחושבים לכלל הפרויקט ולא לפי שלב.')
    S.finish(r)


# ------------------------------------------------------------------ cross-check
def build_check(B):
    ws = B.ws['chk']; MQ = J('docs/quantities/boq/model-quantities.json')['quantities']
    S = Sheet(ws, note_col=8, widths={'A': 2, 'B': 46, 'C': 15, 'D': 15, 'E': 13, 'F': 12, 'G': 30, 'H': 46}, no_merge=True)
    S.title(1, 'בקרה | כתב הכמויות מול הכמויות שהמודל מחשב', 'מודל = docs/quantities/boq/model-quantities.json (app.quantities, js/geometry/*.js). כתב הכמויות = נוסחאות הגיליון "02 בטון". סטייה עד 0.5% = תקין.')
    r = 3
    S.section(r, 'נפחי בטון לפי קבוצה'); r += 1
    S.header(r, ['קבוצה', 'כתב כמויות (מ"ק)', 'מודל (מ"ק)', 'סטייה (מ"ק)', 'סטייה %', 'בדיקה'], h=30); r += 1
    c = lambda sec: f"{q('conc')}!P{B.secTot[sec]}" if sec in B.secTot else '0'
    conc = q('conc')

    def sumif(pattern_col_vals):
        return pattern_col_vals
    Fq, G, F1, R = MQ['foundations'], MQ['groundFloor'], MQ['firstFloor'], MQ['roof']
    rows = [
        ('כלונסאות', c('piles'), MQ['piles']['concrete_m3']),
        ('קורות מרתף + קורות יסוד + ראשי כלונס', c('beamsFound'), Fq['beams_m3']),
        ('רצפות מרתף + רצפות קרקע', c('slabs'), Fq['slabs_m3'] + G['slab_m3']),
        ('קירות (מרתף, קרקע, א\', גג)', c('walls'), Fq['walls_m3'] + G['walls_m3'] + F1['walls_m3'] + R['walls_m3']),
        ('עמודים', c('columns'), G['columns_m3'] + F1['columns_m3']),
        ('תקרות', c('ceilings'), G['ceiling_m3'] + F1['ceiling_m3']),
        ('קורות תקרה, גג ופרגולות', c('beamsCeil'), G['beams_m3'] + R['beams_m3']),
        ('מדרגות (נוסחה מקורבת מול רשת המדרגות במודל – ראה הערה)', c('stairs'), MQ['stairs']['concrete_m3']),
        ('חומות + יסודות (בלי פילר)', f"{c('perimeter')}-SUMIF({conc}!$C:$C,\"PIL1*\",{conc}!$P:$P)", MQ['perimeter']['footings_m3'] + MQ['perimeter']['walls_m3']),
    ]
    k0 = r
    for i, (lab, f, m) in enumerate(rows):
        S.row(r, [lab, f"={f}", round(m, 3), f"=C{r}-D{r}", f"=IF(D{r}=0,0,E{r}/D{r})", f"=IF(ABS(F{r})<=0.005,\"✔ תקין\",\"✘ פער\")"], [None, NUM3, NUM3, NUM3, PCT1, None],
              fill=BAND_FILL if i % 2 else None, note=('כתב הכמויות: לוח משופע L·b·t + משולשי השלבים n·g·r/2·b + פודסטים A·t. המודל: נפח הרשת המדויקת (פרופיל השלבים, חפיפה בין המהלך לפודסט). ההפרש ≈ חפיפת המהלך והפודסט – עדיף ערך המודל עד תוכנית קונסטרוקציה למדרגות.' if 'מדרגות' in lab else None))
        r += 1
    S.row(r, ['סה"כ', f"=SUM(C{k0}:C{r-1})", f"=SUM(D{k0}:D{r-1})", f"=C{r}-D{r}", f"=IF(D{r}=0,0,E{r}/D{r})", f"=IF(ABS(F{r})<=0.005,\"✔ תקין\",\"✘ פער\")"], [None, NUM3, NUM3, NUM3, PCT1, None],
          bold=True, fill=TOTAL_FILL, top=True)
    B.chkTot = r
    r += 2
    S.section(r, 'בקרות נוספות'); r += 1
    S.header(r, ['בדיקה', 'כתב כמויות', 'מודל / מקור', 'סטייה', '', 'בדיקה'], h=30); r += 1
    B_ = MQ['blocks']
    S.row(r, ['מטר קידוח כלונסאות', f"=SUMIF({conc}!$O:$O,\"π/4·d²·L\",{conc}!$I:$I)", MQ['piles']['drill_m'], f"=C{r}-D{r}", None, f"=IF(ABS(E{r})<0.5,\"✔ תקין\",\"✘ פער\")"],
          [None, NUM, NUM, NUM]); r += 1
    S.row(r, ['שטח קירות בלוקים (מ"ר)', f"={q('blk')}!E{1}" if False else f"=SUM({q('blk')}!E5:E14)", B_['area_m2'], f"=C{r}-D{r}", None, f"=IF(ABS(E{r})<2,\"✔ תקין\",\"✘ פער – ראה הערה\")"], [None, NUM, NUM, NUM],
          note='blocks-order.json (פריסה לפי קיר) מול סכום המודל – הפרש קטן בעובי 22 בקומת הקרקע (75.19 מול 74.63) – תיעוד ב-open-issues'); r += 1
    S.row(r, ['מספר כלונסאות', f"=COUNTIF({conc}!$O:$O,\"π/4·d²·L\")", MQ['piles']['count'], f"=C{r}-D{r}", None, f"=IF(E{r}=0,\"✔ תקין\",\"✘ פער\")"], [None, QTY, QTY, QTY]); r += 1
    S.finish(r, landscape=False)


# ------------------------------------------------------------------ open issues
def build_open(B):
    ws = B.ws['open']
    S = Sheet(ws, note_col=6, widths={'A': 2, 'B': 6, 'C': 30, 'D': 70, 'E': 14, 'F': 46})
    r = 1
    S.section(r, 'פתוחים והנחות זמניות בכתב הכמויות – לבדיקה מול אביחי / הקונסטרוקטור / הקבלן'); r += 1
    S.header(r, ["מס'", 'נושא', 'פירוט', 'השפעה'], h=16.8); r += 1
    items = [
        ('מחירים', 'כל המחירים בגיליון "מחירון" הם הערכה מפורסמת (מדריכי מחירים / ספקים / מחירונים) – לא הצעות מחיר. מקור וקישור לכל מחיר. להחליף בהצעות בפועל.', 'עלות'),
        ('זיון כלונסאות', 'K-400 טבלת כלונסאות: כותרות העמודות "זיון כלונס" / "קוצים לעמודים L=250" נראות מוחלפות – 7Φ16 / 8Φ16 תואם את חתך A-A (זיון הכלונס), 10Φ12 / 6Φ12 = קוצים. אורך העיגון בקורה (0.60) ואורך הקטע הצפוף של החישוק הלוליני (2.0 מ\') – הנחה.', 'ברזל כלונסאות'),
        ('ברזל קירות ועמודים', 'בגיליונות K-22/32/42 מופיעים רק ריכוזי מוטות אנכיים (למשל "30ø12") – אין רשתות קיר וחישוקים לעמודים. הרשתות והחישוקים חושבו ביחס ק"ג/מ"ק (זמני).', 'ברזל'),
        ('ברזל חומות, מדרגות, בריכה, פילר', 'אין פריסת ברזל במקורות – יחס ק"ג/מ"ק (זמני).', 'ברזל'),
        ('בריכה', 'רצפה 20 ס"מ משופעת, קירות עד 278.13 (לפי pool.json). במודל הקירות מתחילים בתחתית הרצפה (278.83) – הפרש 0.70 מ\' בגובה הקירות. מדרגות ומשטח – בטון מלא (הנחה).', 'בטון בריכה'),
        ('ממ"ד – תקרה', 'עובי ומפלס תקרת הממ"ד לפי תוכנית הג"א – חסרה (open-issues). התקרה כלולה ב-FS1 בעובי 25.', 'בטון / ברזל'),
        ('שינויי דייר (OC)', 'הכמויות לפי התוכניות המקוריות (כמו במודל). שינויים פתוחים (פתח בקיר מרתף וכו\') לא נוכו.', 'בטון'),
        ('איטום', 'אין פרט איטום – מבנה זמני (פריימר + 2 יריעות + לוח הגנה).', 'איטום'),
        ('ניקוז "כדור חצץ"', 'K-400 חתך קיר: לא ברור אם החתך מתאר את קירות המרתף או את החומות. חושב לאורך החומות.', 'ניקוז'),
        ('דיפון', 'אין תכנון דיפון – שטח לפי קו הדיפון הזמני במודל.', 'עפר'),
        ('מילוי', 'דוח הקרקע: מצע ג\' (חומר נברר); K-400: מצע סוג א\' – סתירה פתוחה. 96% / 98% MOD.AASHTO – שאלה פתוחה.', 'עפר'),
        ('טפסנות', 'מקדמי עץ, מספר שימושים, צפיפות תמיכות וימי השכרה – הערכה. הקבלן קובע את שיטת הטפסנות (מסורתית / תבניות מתועשות).', 'טפסנות'),
        ('מחברי בלוק-בטון', 'מרווח המחברים לא נקבע (data/config/blocks.json ties) – לא תומחר.', 'בנייה'),
        ('הבדל שטח בלוקים', 'blocks-order.json (קרקע, 22 ס"מ): 75.19 מ"ר מול 74.63 מ"ר בסיכום המודל – הפרש 0.56 מ"ר (קירות עם משקוף משותף). לבדיקה בשלב הבא.', 'בנייה'),
    ]
    for i, (a, b, c) in enumerate(items):
        S.row(r, [i + 1, a, b, c], [QTY], fill=BAND_FILL if i % 2 else None, h=16.8, wrap_cols=(4,))
        ws.cell(row=r, column=2).alignment = C_C
        r += 1
    for k in sorted(set(B.missingPrices)):
        S.row(r, [r - 2, 'מחיר חסר', f"אין מחיר למפתח {k} – נספר 0", 'עלות'], [QTY], h=16.8); r += 1
    S.finish(r - 1)
    for rr in range(1, r):
        ws.row_dimensions[rr].height = 16.8 if rr < 3 else 30


# ------------------------------------------------------------------ summary
def build_summary(B):
    ws = B.ws['sum']
    S = Sheet(ws, note_col=5, widths={'A': 2, 'B': 52, 'C': 18, 'D': 12, 'E': 46}, no_merge=True)
    S.title(1, 'כתב כמויות שלד | מגרש 5187, שכונת רקפות, באר שבע',
            'סבב 1: עבודות עפר, כלונסאות, בטון, טפסנות, ברזל, איטום וניקוז, בנייה בבלוקים (עד שלב 4א כולל משקופים וארגזי תריס, כולל שלד הבריכה). '
            'כמויות מהמודל (נוסחאות חיות), מחירים מוערכים ללא מע"מ – ראה "מחירון". נוצר ע"י tools/boq/build_boq.py.')
    r = 3
    S.section(r, '1 · עלויות לפי פרק'); r += 1
    S.header(r, ['פרק', 'עלות (₪)', '% מהסה"כ'], h=15); r += 1
    r0 = r; nSum = len(B.sum)
    tot = r0 + nSum
    for i, (k, (ref, note)) in enumerate(B.sum.items()):
        S.row(r, [k, f"={ref}", f"=IF($C${tot}=0,0,C{r}/$C${tot})"], [None, NIS, PCT1], fill=BAND_FILL if i % 2 else None, note=note or None)
        r += 1
    S.row(r, ['סה"כ שלד (ללא מע"מ, ללא רווח קבלן ותקורות)', f"=SUM(C{r0}:C{r-1})", f"=IF($C${tot}=0,0,C{r}/$C${tot})"], [None, NIS, PCT1], bold=True, hero=True, fill=HERO_FILL, top=True)
    r += 2
    S.section(r, '2 · כמויות עיקריות'); r += 1
    S.header(r, ['פריט', 'כמות', "יח'"], h=15); r += 1
    for i, (k, (ref, unit)) in enumerate(B.qty.items()):
        S.row(r, [k, f"={ref}", unit], [None, NUM, None], fill=BAND_FILL if i % 2 else None); r += 1
    r += 1
    S.section(r, '3 · בקרת תקינות'); r += 1
    S.header(r, ['בדיקה', 'פער', 'תוצאה'], h=15); r += 1
    S.row(r, ['סה"כ לפי שלב (שלד) מול סכום הפרקים: בטון חומר + טפסנות עבודה + ברזל לפי אלמנט',
              f"={q('step')}!I{B.stepTot}-({q('conc')}!T{B.concTotal}+{q('conc')}!T{B.pileConcRow}+{B.qty['טפסנות – שטח מגע'][0]}*{B.PR('formwork_labor')}+SUM({q('rb')}!N{B.rbRange[0]}:N{B.rbRange[1]})/1000*{B.PR('rebar_ton')})",
              f"=IF(ABS(C{r})<1,\"✔ תקין\",\"✘ פער\")"], [None, NIS, None]); r += 1
    S.row(r, ['בטון: סכום הקבוצות מול המודל (גיליון "בקרה")', f"={q('chk')}!E{B.chkTot}", f"={q('chk')}!G{B.chkTot}"], [None, NUM3, None]); r += 1
    S.finish(r, landscape=False)


def main():
    E = EL.collect()
    B = Book()
    build_params(B)
    build_prices(B)
    build_concrete(B, E)
    build_formwork(B, E)
    build_rebar(B, E)
    build_earth(B)
    build_wp(B, E)
    build_blocks(B)
    build_steps(B, E)
    build_check(B)
    build_open(B)
    build_summary(B)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    B.wb.save(OUT)
    print(f"נכתב {OUT.relative_to(ROOT)} – {len(E)} אלמנטי בטון; מחירים חסרים: {sorted(set(B.missingPrices)) or 'אין'}")


if __name__ == '__main__':
    main()

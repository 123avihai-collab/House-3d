# -*- coding: utf-8 -*-
"""ערכת עיצוב אקסל — הסטנדרט של אביחי (מעודכן 23/09/2026). מקור: skill excel-design-standard."""
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

NAVY, BLUE = "1F3864", "2E5B9A"
HDR_FILL, TOTAL_FILL, HERO_FILL, BAND_FILL = "D6E0F0", "EDF2FA", "FCE4D6", "EEF4FC"
NOTE_GRAY, WHITE, BORDER_C = "808080", "FFFFFF", "9BB0CE"
INPUT_FILL, NOW_FILL, TGT_FILL, WARN_FILL = "FFF2CC", "DDEBF7", "E2EFDA", "FCE4D6"
GREEN, RED = "1E7145", "C00000"

thin   = Side(style="thin",   color=BORDER_C)
med    = Side(style="medium", color=BLUE)
BOX    = Border(left=thin, right=thin, top=thin, bottom=thin)
TOPBOX = Border(left=thin, right=thin, top=med,  bottom=thin)

F_TITLE = Font(name="Arial", size=16, bold=True, color=WHITE)
F_SUB   = Font(name="Arial", size=9,  italic=True, color=NOTE_GRAY)
F_SEC   = Font(name="Arial", size=12, bold=True, color=WHITE)
F_HDR   = Font(name="Arial", size=10, bold=True, color=NAVY)
F_BODY  = Font(name="Arial", size=10)
F_BOLD  = Font(name="Arial", size=10, bold=True)
F_BIG   = Font(name="Arial", size=13, bold=True, color=NAVY)
F_NOTE  = Font(name="Arial", size=9,  color=NOTE_GRAY)
F_POS   = Font(name="Arial", size=10, bold=True, color=GREEN)
F_NEG   = Font(name="Arial", size=10, bold=True, color=RED)

NIS  = '#,##0.00\\ ₪;[Red]\\-#,##0.00\\ ₪'
USD  = '$#,##0.00;[Red]\\-$#,##0.00'
PCT  = '0.00%;[Red]\\-0.00%'
PCT1 = '0.0%'
QTY  = '#,##0'
RATE = '0.0000'
NUM  = '#,##0.00'
NUM3 = '#,##0.000'
DATE = 'DD/MM/YYYY'

H_TITLE, H_SUB, H_SEC, H_HDR, H_ROW = 21.75, 15, 15, 44, 15

C_R  = Alignment(horizontal="right",  vertical="center")
C_C  = Alignment(horizontal="center", vertical="center")
C_W  = Alignment(horizontal="right",  vertical="center", wrap_text=True)
C_CW = Alignment(horizontal="center", vertical="center", wrap_text=True)


def col_letter(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s


def unmerge_all(ws):
    for rng in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(rng))


class Sheet:
    def __init__(self, ws, note_col, widths, no_merge=False):
        self.ws, self.NC, self.NM = ws, note_col, no_merge
        self.LAST = col_letter(note_col)
        ws.sheet_view.rightToLeft = True
        ws.sheet_view.showGridLines = False
        for col, w in widths.items():
            ws.column_dimensions[col].width = w
        ws.column_dimensions[col_letter(note_col + 1)].width = 9

    def _span(self, r, a, b):
        if not self.NM and a < b:
            self.ws.merge_cells(start_row=r, start_column=a, end_row=r, end_column=b)

    def _blank(self, r, frm, to, fill, top):
        if frm > to:
            return
        self._span(r, frm, to)
        for col in range(frm, to + 1):
            c = self.ws.cell(row=r, column=col)
            c.border = TOPBOX if top else BOX
            c.fill = PatternFill("solid", fgColor=fill) if fill else PatternFill(fill_type=None)

    def title(self, r, text, sub):
        ws = self.ws
        self._span(r, 2, self.NC)
        c = ws.cell(row=r, column=2); c.value = text; c.font = F_TITLE; c.alignment = C_R
        for col in range(2, self.NC + 1):
            ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=NAVY)
        ws.row_dimensions[r].height = H_TITLE
        self._span(r + 1, 2, self.NC)
        s = ws.cell(row=r + 1, column=2); s.value = sub; s.font = F_SUB; s.alignment = C_W
        ws.row_dimensions[r + 1].height = H_SUB * 2

    def section(self, r, text):
        ws = self.ws
        self._span(r, 2, self.NC)
        c = ws.cell(row=r, column=2); c.value = text; c.font = F_SEC; c.alignment = C_R
        for col in range(2, self.NC + 1):
            ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=BLUE)
        ws.row_dimensions[r].height = H_SEC

    def header(self, r, labels, blank_from=None, h=H_HDR):
        ws = self.ws
        for i, lab in enumerate(labels):
            c = ws.cell(row=r, column=2 + i)
            c.value = lab; c.font = F_HDR
            c.alignment = C_W if i == 0 else C_CW
            c.fill = PatternFill("solid", fgColor=HDR_FILL); c.border = BOX
        self._blank(r, blank_from or (2 + len(labels)), self.NC - 1, HDR_FILL, False)
        c = ws.cell(row=r, column=self.NC)
        if c.value is None:
            c.value = "הערה"
        c.font = F_HDR; c.alignment = C_C
        c.fill = PatternFill("solid", fgColor=HDR_FILL); c.border = BOX
        ws.row_dimensions[r].height = h

    def row(self, r, vals, fmts=None, bold=False, fill=None, top=False,
            h=H_ROW, hero=False, blank_from=None, note=None, wrap_cols=()):
        ws = self.ws
        fmts = list(fmts or []) + [None] * len(vals)
        while len(vals) > 1 and vals[-1] is None:
            vals = vals[:-1]
        for i, v in enumerate(vals):
            c = ws.cell(row=r, column=2 + i)
            if v is not None:
                c.value = v
            c.border = TOPBOX if top else BOX
            c.fill = PatternFill("solid", fgColor=fill) if fill else PatternFill(fill_type=None)
            c.font = F_BIG if hero else (F_BOLD if bold else F_BODY)
            c.alignment = C_W if (i == 0 or (2 + i) in wrap_cols) else C_C
            if fmts[i]:
                c.number_format = fmts[i]
        self._blank(r, blank_from or (2 + len(vals)), self.NC - 1, fill, top)
        c = ws.cell(row=r, column=self.NC)
        c.value = note; c.font = F_NOTE; c.alignment = C_W
        c.border = TOPBOX if top else BOX
        if fill:
            c.fill = PatternFill("solid", fgColor=fill)
        ws.row_dimensions[r].height = h

    def note(self, r, text, h=H_ROW):
        ws = self.ws
        self._span(r, 2, self.NC)
        c = ws.cell(row=r, column=2); c.value = text; c.font = F_NOTE; c.alignment = C_W
        ws.row_dimensions[r].height = h

    def paint(self, r, col, color):
        self.ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor=color)

    def finish(self, last_row, freeze=None, landscape=True):
        ws = self.ws
        if freeze:
            ws.freeze_panes = freeze
        ws.sheet_properties.tabColor = NAVY
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        if landscape:
            ws.page_setup.orientation = "landscape"
        ws.print_area = f"A1:{self.LAST}{last_row}"

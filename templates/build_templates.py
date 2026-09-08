"""
Regenerates the blank Vega Construction Manager Excel templates in this folder.

Layouts are reproduced from the client's real workbooks in the parent folder:
  BSR for Pricing.xlsx                -> BSR_Template.xlsx
  Income_Balance_Statement-R.01.xlsx  -> Income_Balance_Statement_Template.xlsx
  Payments_Schedule_Cash_Flow.xlsx    -> Payments_Schedule_Template.xlsx

Column order, header wording, grouping and formulas are kept identical to the
originals on purpose - these are the format contract between the client's Excel
workflow and the platform's import/export, so they are deliberately not tidied up.

Run:  python build_templates.py
"""
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT = os.path.dirname(os.path.abspath(__file__))

# Shared formats, lifted from the source workbooks
ACC = '_(* #,##0.00_);_(* \\(#,##0.00\\);_(* "-"??_);_(@_)'  # accounting, used across the BSR sheets
NUM = '#,##0.00'                                             # plain, used in Construction Accounting
DATE = 'yyyy\\-mm\\-dd;@'

DARK = 'FF434343'    # header band on the accounting sheet
YELLOW = 'FFFFD966'  # accent / totals band
GOLD = 'FF7F6000'    # big title colour
INK = 'FF374151'     # body text
DEEP = 'FF0C343D'    # summary figures
GREY = 'FFD9D9D9'    # header band on the BSR sheets
AUTO = 'FFE1F5EE'    # tint marking cells the platform fills on export
                     # (matches BRAND_LIGHT in src/lib/exportXlsx.ts)
BLANK_ROWS = 40      # empty pre-formatted rows left for data entry

thin = Side(style='thin', color='FFBFBFBF')
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)


def widths(ws, spec):
    for col, w in spec.items():
        ws.column_dimensions[col].width = w


def put(ws, coord, value, bold=False, size=10, color=None, fill=None,
        align=None, fmt=None, wrap=False, border=False):
    c = ws[coord]
    c.value = value
    c.font = Font(bold=bold, size=size, color=color)
    if fill:
        c.fill = PatternFill('solid', start_color=fill, end_color=fill)
    if align or wrap:
        c.alignment = Alignment(horizontal=align, vertical='center', wrap_text=wrap)
    if fmt:
        c.number_format = fmt
    if border:
        c.border = BOX
    return c


def band(ws, row, cols, labels, fill=GREY, color=None, size=10):
    """One styled header row across the given column letters."""
    for col, text in zip(cols, labels):
        put(ws, col + str(row), text, bold=True, size=size, color=color,
            fill=fill, align='center', wrap=True, border=True)


def blank_grid(ws, first_row, cols, fmt_cols=(), rows=BLANK_ROWS):
    """Pre-format empty data-entry rows so typing into them keeps the styling."""
    for r in range(first_row, first_row + rows):
        for col in cols:
            c = ws[col + str(r)]
            c.border = BOX
            c.font = Font(size=10)
            if col in fmt_cols:
                c.number_format = ACC


# ---------------------------------------------------------------------------
# 1. BSR_Template.xlsx
# ---------------------------------------------------------------------------
def build_bsr():
    wb = Workbook()

    # Sheet: Basic Prices -- three parallel column groups (Materials / Labour /
    # Plant), each Description + Unit + Basic Price, grouped by Trade in col A.
    ws = wb.active
    ws.title = 'Basic Prices'
    widths(ws, {'A': 18, 'B': 38.6, 'C': 9, 'D': 16.1, 'E': 22,
                'F': 8.6, 'G': 12.6, 'H': 20, 'I': 9.1, 'J': 13.1})
    ws.merge_cells('A1:B2')
    put(ws, 'A1', 'BASIC PRICES', bold=True, size=14)

    ws.merge_cells('A4:A5')
    put(ws, 'A4', 'Trade', bold=True, fill=GREY, align='center', border=True)
    for span, label in (('B4:D4', 'Materials'), ('E4:G4', 'Labour'), ('H4:J4', 'Plant')):
        ws.merge_cells(span)
        put(ws, span.split(':')[0], label, bold=True, fill=GREY, align='center', border=True)
    band(ws, 5, list('BCDEFGHIJ'), ['Description', 'Unit', 'Basic Price'] * 3)
    for col in ('D', 'G', 'J'):
        ws[col + '5'].number_format = ACC
    # One sample row so the intended shape is unmistakable - delete before use.
    put(ws, 'A6', 'CONCRETE', border=True)
    for col, v in (('B', 'Cement'), ('C', 'bag'), ('D', 1850),
                   ('E', 'Skilled Labour'), ('F', 'day'), ('G', 2500),
                   ('H', 'Concrete Mixer'), ('I', 'day'), ('J', 2000)):
        put(ws, col + '6', v, border=True, fmt=ACC if col in 'DGJ' else None)
    blank_grid(ws, 7, list('ABCDEFGHIJ'), fmt_cols=('D', 'G', 'J'))
    ws.freeze_panes = 'A6'

    # Sheet: Basic Rates -- the coded catalogue. Same three groups, but each
    # carries a Code No. (M-/L-/P- prefix), which the rate analysis references.
    ws = wb.create_sheet('Basic Rates')
    widths(ws, {'A': 8, 'B': 32.1, 'C': 10, 'D': 8, 'E': 14,
                'F': 8, 'G': 18, 'H': 10, 'I': 8, 'J': 14,
                'K': 8, 'L': 18, 'M': 10, 'N': 8, 'O': 14})
    ws.merge_cells('A1:E1')
    put(ws, 'A1', 'BASIC RATES', bold=True, size=13)
    for span, label in (('A2:E2', 'MATERIALS'), ('F2:J2', 'LABOUR'), ('K2:O2', 'PLANT')):
        ws.merge_cells(span)
        put(ws, span.split(':')[0], label, bold=True, fill=GREY, align='center', border=True)
    band(ws, 3, list('ABCDEFGHIJKLMNO'),
         ['Item No.', 'Description', 'Code No.', 'Unit', 'Price ( Rs.)'] * 3)
    for col in ('E', 'J', 'O'):
        ws[col + '3'].number_format = ACC
    for col, v in (('A', 1), ('B', 'Cement'), ('C', 'M-001'), ('D', 'Bag'), ('E', 2400),
                   ('F', 1), ('G', 'SK Labour'), ('H', 'L-001'), ('I', 'Day'), ('J', 3500),
                   ('K', 1), ('L', 'Hire of Mixer'), ('M', 'P-001'), ('N', 'Day'), ('O', 5000)):
        put(ws, col + '4', v, border=True, fmt=ACC if col in 'EJO' else None)
    blank_grid(ws, 5, list('ABCDEFGHIJKLMNO'), fmt_cols=('E', 'J', 'O'))
    ws.freeze_panes = 'A4'

    # Sheet: Activity
    ws = wb.create_sheet('Activity')
    widths(ws, {'B': 8, 'C': 40, 'F': 60})
    put(ws, 'B1', 'Activity', bold=True, size=12, fill=GREY, align='center', border=True)
    put(ws, 'C1', 'Description', bold=True, size=12, fill=GREY, align='center', border=True)
    activities = [
        'Site Preparation & Excavation', 'Earth work support and Filling',
        'Anti Termite Treatment & DPC', 'Random Rubble Masonry Work',
        'Concrete Work', 'Formwork', 'Reinforcement', 'Block Work', 'Brick Work',
        'Roof', 'Doors and Windows', 'Plumbing & Drainage', 'Plastering',
        'Tiling', 'Ceiling', 'Painting',
    ]
    for i, name in enumerate(activities, start=1):
        put(ws, 'B' + str(i + 1), i, align='center', border=True)
        put(ws, 'C' + str(i + 1), name, border=True)
    put(ws, 'F7', 'Note', bold=True)
    ws.merge_cells('F8:O9')
    put(ws, 'F8', 'Rate break downs of all trades are according to the activity numbers '
                  'above - an item code reads <activity>.<group>.<item>, e.g. 05.A.01 = '
                  'Concrete Work / group A / item 01.', wrap=True)

    # Sheet: Rate Analysis -- the client keeps one sheet per activity ('01'..'16');
    # this is the repeating block with live formulas, shown three ways: a plain
    # build-up, a nested trade-item reference, and a % allowance line.
    ws = wb.create_sheet('Rate Analysis')
    widths(ws, {'A': 10, 'B': 6, 'C': 44, 'D': 10, 'E': 8, 'F': 9, 'G': 11, 'H': 14})
    ws.merge_cells('A2:H2')
    put(ws, 'A2', '05. Concrete Work', bold=True, size=12, fill=GREY)
    put(ws, 'B4', 'A.', bold=True)
    put(ws, 'C4', 'Mixing Concrete      <- group index: one line per group in this activity')
    put(ws, 'D6', 'Mixing Concrete', bold=True)

    def analysis_block(row, code, desc, basis_qty, basis_unit, lines, note=None):
        """Renders one full rate-analysis item block. Returns the next free row."""
        put(ws, 'A' + str(row), code, bold=True, fill=GREY, border=True)
        ws.merge_cells('C{0}:H{0}'.format(row))
        put(ws, 'C' + str(row), desc, bold=True, fill=GREY, border=True)
        r = row + 1
        put(ws, 'E' + str(r), 'Analysis for')
        put(ws, 'F' + str(r), basis_qty, align='center')
        put(ws, 'G' + str(r), basis_unit)
        basis_row = r
        r += 1
        band(ws, r, list('BCDEFGH'),
             ['No.', 'Item Description', 'Item Ref', 'Unit', 'Quantity', 'Rate', 'Amount'])
        first = r + 1
        for i, (name, ref, unit, qty, rate) in enumerate(lines):
            rr = first + i
            put(ws, 'B' + str(rr), '1.{0:02d}'.format(i + 1), align='center', border=True)
            put(ws, 'C' + str(rr), name, border=True)
            put(ws, 'D' + str(rr), ref, align='center', border=True)
            put(ws, 'E' + str(rr), unit, align='center', border=True)
            put(ws, 'F' + str(rr), qty, align='center', border=True)
            put(ws, 'G' + str(rr), rate, fmt=ACC, border=True)
            if unit is None and rate is None:
                # A % allowance carries only an amount - no unit/qty/rate - so it is
                # a share of the lines above it rather than qty x rate.
                put(ws, 'H' + str(rr), '={0}*SUM(H{1}:H{2})'.format(qty, first, rr - 1),
                    fmt=ACC, border=True)
            else:
                put(ws, 'H' + str(rr), '=F{0}*G{0}'.format(rr), fmt=ACC, border=True)
        last = first + len(lines) - 1
        r = last + 1
        put(ws, 'D' + str(r), 'Total for')
        put(ws, 'E' + str(r), basis_qty, align='center')
        put(ws, 'F' + str(r), basis_unit)
        put(ws, 'H' + str(r), '=SUM(H{0}:H{1})'.format(first, last), bold=True, fmt=ACC, border=True)
        total_row = r
        r += 1
        # The analysis basis is not always 1 unit (e.g. 0.51 Cube for a column),
        # so the unit rate is always total / basis, never just the total.
        put(ws, 'D' + str(r), 'Rate for 1')
        put(ws, 'E' + str(r), basis_unit)
        put(ws, 'H' + str(r), '=H{0}/F{1}'.format(total_row, basis_row), bold=True, fmt=ACC, border=True)
        rate_row = r
        r += 1
        put(ws, 'D' + str(r), 'Rate(Say)', bold=True)
        put(ws, 'G' + str(r), '1 ' + str(basis_unit))
        put(ws, 'H' + str(r), '=ROUND(H{0},-1)'.format(rate_row), bold=True, fmt=ACC, border=True)
        if note:
            r += 1
            put(ws, 'C' + str(r), note, size=9, color='FF808080')
        return r + 2

    nxt = analysis_block(
        8, '05.A.01', 'Mixing Concrete 1:1-1/2:3 (3/4")', 1, 'Cube',
        [('Cement', 'M-026', 'Bag', 23, 2400),
         ('Sand', 'M-113', 'Cube', 0.42, 18000),
         ('3/4" Metal', 'M-066', 'Cube', 0.82, 15000),
         ('Hire of Mixer', 'P-001', 'Day', 0.333, 5000),
         ('SK Labour', 'L-003', 'Day', 0.333, 3500)],
        note='Plain build-up: every line references a Basic Rate code (M- / L- / P-).')

    nxt = analysis_block(
        nxt, '05.D.01', 'Cement concrete 1:1-1/2:3 (3/4") in columns', 0.51, 'Cube',
        [('Mixed Concrete 1:1-1/2:3 (3/4")', '05.A.01', 'Cube', 0.51, 82540),
         ('SK Labour', 'L-003', 'Day', 0.5, 3500)],
        note='Nested reference: line 1 points at another rate-analysis item, not a Basic '
             'Rate code. Note the analysis basis is 0.51 Cube, not 1.')

    analysis_block(
        nxt, '01.A.01', 'Site clearing including removal of debris', 1, 'Sqr',
        [('U / SK Labourer', 'L-007', 'Day', 0.75, 2300),
         ('Allow 2.5% of Items ( 1.01 ) for Tools', None, None, 0.025, None)],
        note='% allowance: no unit / qty / rate, amount is a share of the lines above it.')

    wb.save(os.path.join(OUT, 'BSR_Template.xlsx'))
    print('wrote BSR_Template.xlsx')


# ---------------------------------------------------------------------------
# 2. Income_Balance_Statement_Template.xlsx
# ---------------------------------------------------------------------------
def build_income():
    wb = Workbook()

    ws = wb.active
    ws.title = 'Construction Accounting'
    widths(ws, {'A': 3.3, 'B': 20, 'C': 12, 'D': 14, 'E': 20, 'F': 10,
                'G': 8, 'H': 18, 'I': 14, 'J': 4.1, 'K': 28, 'L': 16,
                'M': 16, 'N': 16})
    put(ws, 'E2', 'info@vegahomes.lk', size=11)
    put(ws, 'E3', 'www.vegahomes.lk', size=11)
    put(ws, 'E4', 'No 494, Puttalam Road, Kurunegala', size=11)
    put(ws, 'E5', '+9471 274 1577, +947777 20 888', size=11)
    ws.merge_cells('H2:N5')
    put(ws, 'H2', 'CONSTRUCTION ACCOUNTING', bold=True, size=28, color=GOLD, align='center')

    ws.merge_cells('B7:N7')
    put(ws, 'B7', 'Tinted cells are filled automatically by the platform on export. '
                  'Untinted cells are entered by hand.', size=9, color='FF808080')

    # Project information block
    ws.merge_cells('B9:H9')
    put(ws, 'B9', 'Project Information', bold=True, size=14, color='FFFFFFFF', fill=DARK)
    for i, label in enumerate(['Project Name', 'Project ID', 'Project Manager',
                               'Project Start Date', 'Project End Date']):
        r = 10 + i
        ws.merge_cells('B{0}:C{0}'.format(r))
        put(ws, 'B' + str(r), label, bold=True, size=12, color=INK, fill=YELLOW,
            align='center', border=True)
        ws.merge_cells('D{0}:H{0}'.format(r))
        put(ws, 'D' + str(r), None, size=12, color=INK, border=True,
            fmt=DATE if 'Date' in label else None)

    # Summary tiles - these read straight off the two tables to the right.
    for span, label, value_span, formula in (
            ('B16:C17', 'Total Actual Income', 'B18:C18', '=L19'),
            ('E16:F17', 'Total Actual Expenses', 'E18:F18', '=L39'),
            ('H16:I17', 'Net Income', 'H18:I18', '=L19-L39')):
        ws.merge_cells(span)
        put(ws, span.split(':')[0], label, bold=True, size=14, color='FFFFFFFF',
            fill=DARK, align='center', wrap=True)
        ws.merge_cells(value_span)
        put(ws, value_span.split(':')[0], formula, bold=True, size=18, color=DEEP,
            align='center', fmt=NUM)

    put(ws, 'B21', 'INCOME', bold=True, size=14, color=INK)
    put(ws, 'B31', 'EXPENSES', bold=True, size=14, color=INK)
    for r, label, formula in ((23, 'Actual', '=L19'), (24, 'Budget', '=M19'),
                              (35, 'Actual', '=L39'), (36, 'Budget', '=M39')):
        put(ws, 'C' + str(r), label, bold=True, size=12, color=INK)
        put(ws, 'D' + str(r), formula, size=12, color=INK, fmt=NUM)

    # BSR estimate vs contract -- the platform's answer to this sheet's Budget column.
    # The client kept the existing flow (Project.contract stays the one manually-entered
    # figure, no separate stored budget), so the platform does NOT fill the Budget column
    # to the right; it only compares the priced BSR total against the contract and flags a
    # mismatch. That check is live in the app on the project's BSR tab (BsrTab in
    # src/app/projects/[id]/client.tsx); this block mirrors it here.
    ws.merge_cells('B26:E26')
    put(ws, 'B26', 'BSR ESTIMATE vs CONTRACT', bold=True, size=12, color='FFFFFFFF',
        fill=DARK, align='center')
    for r, label in ((27, 'BSR Estimate'), (28, 'Contract Value')):
        ws.merge_cells('B{0}:C{0}'.format(r))
        put(ws, 'B' + str(r), label, size=12, color=INK, border=True)
        ws.merge_cells('D{0}:E{0}'.format(r))
        put(ws, 'D' + str(r), None, size=12, color=INK, fill=AUTO, align='center',
            fmt=NUM, border=True)
    ws.merge_cells('B29:C29')
    put(ws, 'B29', 'Difference', bold=True, size=12, color=INK, fill=YELLOW, border=True)
    ws.merge_cells('D29:E29')
    put(ws, 'D29', '=D27-D28', bold=True, size=12, color=INK, fill=YELLOW,
        align='center', fmt=NUM, border=True)
    # Same >1 tolerance the app uses, to absorb float noise from the rate x multiplier x qty chain.
    ws.merge_cells('F29:I29')
    put(ws, 'F29', '=IF(COUNT(D27:E28)<2,"",IF(ABS(D29)>1,'
                   '"Warning: the BSR estimate does not match the contract value.",'
                   '"BSR estimate matches the contract value."))',
        size=11, color=INK, wrap=True)

    band_cols = ['K', 'L', 'M', 'N']


    # Income table
    for col, text in zip(band_cols, ['Income', 'Actual', 'Budget', 'Variances']):
        put(ws, col + '9', text, bold=True, size=14, color='FFFFFFFF', fill=DARK, align='center')
    income_rows = ['Contract Amount', 'Change Orders', 'Progress Payments',
                   'Retainage Released', '', '', '', '', '']
    for i, label in enumerate(income_rows):
        r = 10 + i
        put(ws, 'K' + str(r), label or None, size=12, color=INK, border=True)
        # Actual is platform-filled (tinted); Budget stays a manual cell -- the client kept
        # their existing flow rather than adding a stored budget figure to the platform.
        put(ws, 'L' + str(r), None, size=12, color=INK, fill=AUTO, align='center', fmt=NUM, border=True)
        put(ws, 'M' + str(r), None, size=12, color=INK, align='center', fmt=NUM, border=True)
        put(ws, 'N' + str(r), '=L{0}-M{0}'.format(r), size=12, color=INK,
            align='center', fmt=NUM, border=True)
    for col, val in zip(band_cols, ['Total Income', '=SUM(L10:L18)', '=SUM(M10:M18)', '=SUM(N10:N18)']):
        put(ws, col + '19', val, bold=True, size=14, color=INK, fill=YELLOW,
            align='center', fmt=None if col == 'K' else NUM, border=True)

    # Expenses table - Direct then Indirect, matching the client's grouping.
    for col, text in zip(band_cols, ['Expenses', 'Actual', 'Budget', 'Variances']):
        put(ws, col + '21', text, bold=True, size=14, color='FFFFFFFF', fill=DARK, align='center')
    put(ws, 'K22', 'Direct Costs', bold=True, size=12, color=INK, fill=YELLOW, border=True)
    put(ws, 'K31', 'Indirect Costs', bold=True, size=12, color=INK, fill=YELLOW, border=True)
    expense_rows = [(23, 'Labor'), (24, 'Materials'), (25, 'Equipment'),
                    (26, 'Subcontractor Costs'), (27, 'Other Direct Costs'),
                    (28, ''), (29, ''), (30, ''),
                    (32, 'Overhead'), (33, 'Administrative Expenses'), (34, 'Insurance'),
                    (35, 'Permits and Fees'), (36, ''), (37, ''), (38, '')]
    for r, label in expense_rows:
        put(ws, 'K' + str(r), label or None, size=12, color=INK, border=True)
        # Actual is platform-filled (tinted); Budget stays a manual cell -- the client kept
        # their existing flow rather than adding a stored budget figure to the platform.
        put(ws, 'L' + str(r), None, size=12, color=INK, fill=AUTO, align='center', fmt=NUM, border=True)
        put(ws, 'M' + str(r), None, size=12, color=INK, align='center', fmt=NUM, border=True)
        put(ws, 'N' + str(r), '=L{0}-M{0}'.format(r), size=12, color=INK,
            align='center', fmt=NUM, border=True)
    totals = ['Total Expenses',
              '=SUM(L23:L30)+SUM(L32:L38)',
              '=SUM(M23:M30)+SUM(M32:M38)',
              '=SUM(N23:N30)+SUM(N32:N38)']
    for col, val in zip(band_cols, totals):
        put(ws, col + '39', val, bold=True, size=14, color=INK, fill=YELLOW,
            align='center', fmt=None if col == 'K' else NUM, border=True)

    # Sheet: Accounts -- the underlying ledger. Two independent runs side by
    # side: money IN (A-E) and money OUT (F-N), then the per-category spread
    # (O-Z) that the vendor summary pivots on.
    ws = wb.create_sheet('Accounts')
    widths(ws, {'A': 12, 'B': 11, 'C': 14, 'D': 14, 'E': 24, 'F': 12, 'G': 10,
                'H': 34, 'I': 14, 'J': 10, 'K': 12, 'L': 18, 'M': 14, 'N': 14})
    for col in 'OPQRSTUVWXYZ':
        ws.column_dimensions[col].width = 15
    ws.merge_cells('A1:E1')
    put(ws, 'A1', 'Client / Project name', bold=True, size=12)
    ws.merge_cells('A3:E3')
    put(ws, 'A3', 'INCOME BALANCE STATEMENT', bold=True, size=14)
    headers = ['Date', 'Payment No', 'Amount', 'Cumulative', 'Remarks',
               'Date2', 'Entry No', 'Description', 'Category', 'Memo', 'Stage',
               'BOQ Item', 'Total', 'Cumulative2', 'Outstanding Payments',
               'Transport', 'Labour / Sub Contractor', 'Site Visit', 'Machinery',
               'Minor Material', 'Major Material', 'Service Charge',
               'Utility Bills', 'Food & Beverages', 'Fuel', 'Others']
    cols = [get_column_letter(i + 1) for i in range(len(headers))]
    band(ws, 5, cols, headers)
    money_cols = ('C', 'M') + tuple('OPQRSTUVWXYZ')
    for r in range(6, 6 + BLANK_ROWS * 2):
        for col in cols:
            c = ws[col + str(r)]
            c.border = BOX
            c.font = Font(size=10)
        ws['A' + str(r)].number_format = DATE
        ws['F' + str(r)].number_format = DATE
        for col in money_cols:
            ws[col + str(r)].number_format = ACC
        # Running totals down each of the two independent runs.
        ws['D' + str(r)] = '=IF(C{0}="","",SUM($C$6:C{0}))'.format(r)
        ws['D' + str(r)].number_format = ACC
        ws['N' + str(r)] = '=IF(M{0}="","",SUM($M$6:M{0}))'.format(r)
        ws['N' + str(r)].number_format = ACC
    ws.freeze_panes = 'A6'

    # Sheet: Vendor Summary -- the pivot the client keeps beside the ledger.
    ws = wb.create_sheet('Vendor Summary')
    widths(ws, {'B': 40, 'C': 14, 'D': 14, 'E': 14, 'F': 16, 'G': 14, 'H': 14, 'I': 16})
    put(ws, 'B15', 'Sum of Total', bold=True, size=12)
    put(ws, 'C15', 'Column Labels', bold=True, size=12)
    band(ws, 16, list('BCDEFGHI'),
         ['Row Labels', 'Labour', 'Machinery', 'Material', 'Sub Contractor',
          'Transport', 'Other', 'Grand Total'])
    for r in range(17, 17 + BLANK_ROWS):
        for col in 'BCDEFGHI':
            c = ws[col + str(r)]
            c.border = BOX
            c.font = Font(size=10)
            if col != 'B':
                c.number_format = ACC
        ws['I' + str(r)] = '=IF(COUNT(C{0}:H{0})=0,"",SUM(C{0}:H{0}))'.format(r)
        ws['I' + str(r)].number_format = ACC
    ws.freeze_panes = 'B17'

    wb.save(os.path.join(OUT, 'Income_Balance_Statement_Template.xlsx'))
    print('wrote Income_Balance_Statement_Template.xlsx')


# ---------------------------------------------------------------------------
# 3. Payments_Schedule_Template.xlsx
# ---------------------------------------------------------------------------
def build_payments():
    wb = Workbook()
    STAGES = 4

    ws = wb.active
    ws.title = 'Cashflow'
    widths(ws, {'A': 10, 'B': 18, 'C': 18, 'D': 16, 'E': 16, 'F': 16, 'G': 16})
    ws.merge_cells('A1:G2')
    put(ws, 'A1', 'PROPOSED HOUSE FOR\n<CLIENT NAME>', bold=True, size=12, wrap=True)
    ws.merge_cells('A4:G4')
    put(ws, 'A4', 'CASHFLOW', bold=True, size=12, fill=GREY, align='center')
    # SETTLED / OUTSTANDING are platform additions beyond the client's own five columns -- they
    # fall out of the milestone statuses already tracked, so the export appends them rather than
    # reordering the columns the client already reads. START / COMPLETION are backed by
    # Stage.startDate / Stage.completionDate (migration 0022_stage_dates.sql).
    band(ws, 5, list('ABCDEFG'),
         ['ITEM', 'STAGES', 'AMOUNT', 'START', 'COMPLETION', 'SETTLED', 'OUTSTANDING'])
    for i in range(STAGES):
        r = 6 + i
        put(ws, 'A' + str(r), i + 1, align='center', border=True)
        put(ws, 'B' + str(r), 'STAGE-{0:02d}'.format(i + 1), border=True)
        put(ws, 'C' + str(r), None, fill=AUTO, fmt=ACC, border=True)
        put(ws, 'D' + str(r), None, fill=AUTO, fmt=DATE, border=True)
        put(ws, 'E' + str(r), None, fill=AUTO, fmt=DATE, border=True)
        put(ws, 'F' + str(r), None, fill=AUTO, fmt=ACC, border=True)
        put(ws, 'G' + str(r), '=IF(C{0}="","",C{0}-F{0})'.format(r), fill=AUTO, fmt=ACC, border=True)
    tr = 6 + STAGES + 1
    put(ws, 'B' + str(tr), 'TOTAL AMOUNT', bold=True, fill=YELLOW, border=True)
    for col in ('C', 'F', 'G'):
        put(ws, col + str(tr), '=SUM({0}6:{0}{1})'.format(col, 5 + STAGES), bold=True,
            fill=YELLOW, fmt=ACC, border=True)


    # Stagewise payments - the 50 / 25 / 25 split per stage.
    ws = wb.create_sheet('Stagewise Payments')
    widths(ws, {'A': 14, 'B': 22, 'C': 14, 'D': 16, 'E': 16, 'F': 16, 'G': 16})
    ws.merge_cells('A1:G2')
    put(ws, 'A1', 'PROPOSED HOUSE FOR\n<CLIENT NAME>', bold=True, size=12, wrap=True)
    ws.merge_cells('A3:G3')
    put(ws, 'A3', 'STAGEWISE PAYMENTS', bold=True, size=12, fill=GREY, align='center')
    stage_cols = [get_column_letter(4 + i) for i in range(STAGES)]
    band(ws, 4, ['A', 'B', 'C'] + stage_cols,
         ['PAYMENT NO', 'PAYMENT TYPE', 'PERCENTAGE'] +
         ['STAGE-{0:02d}'.format(i + 1) for i in range(STAGES)])
    for i, (label, pct) in enumerate((('ADVANCE PAYMENT', 0.5),
                                      ('INTERIM PAYMENT', 0.25),
                                      ('FINAL PAYMENT', 0.25))):
        r = 5 + i
        put(ws, 'A' + str(r), i + 1, align='center', border=True)
        put(ws, 'B' + str(r), label, border=True)
        put(ws, 'C' + str(r), pct, align='center', fmt='0%', border=True)
        for j, col in enumerate(stage_cols):
            # Each cell is its stage's cashflow amount x this milestone's percentage.
            put(ws, col + str(r), '=$C{0}*Cashflow!C{1}'.format(r, 6 + j), fmt=ACC, border=True)
    tr = 8
    put(ws, 'B' + str(tr), 'TOTAL', bold=True, fill=YELLOW, border=True)
    put(ws, 'C' + str(tr), '=SUM(C5:C7)', bold=True, fill=YELLOW, fmt='0%', border=True)
    for col in stage_cols:
        put(ws, col + str(tr), '=SUM({0}5:{0}7)'.format(col), bold=True,
            fill=YELLOW, fmt=ACC, border=True)

    wb.save(os.path.join(OUT, 'Payments_Schedule_Template.xlsx'))
    print('wrote Payments_Schedule_Template.xlsx')


if __name__ == '__main__':
    build_bsr()
    build_income()
    build_payments()

# Vega Excel templates

Blank, formula-live templates reproducing the layout of the client's real workbooks
in the parent `doc/` folder. They are the format contract between the client's
existing Excel workflow and the platform, and they exist for two jobs:

1. **Import** — hand one to the client, they fill it, we load it into a project.
2. **Export** — the platform's "Export to Excel" buttons should produce something
   the client recognises. These files are the target shape.

Regenerate with `python build_templates.py` (needs `openpyxl`). Edit the script,
not the `.xlsx` files, so the layout stays reproducible.

| Template | Source workbook |
| --- | --- |
| `BSR_Template.xlsx` | `BSR for Pricing.xlsx` |
| `Income_Balance_Statement_Template.xlsx` | `Income_Balance_Statement-R.01.xlsx` |
| `Payments_Schedule_Template.xlsx` | `Payments_Schedule_Cash_Flow.xlsx` |

Column order and header wording are kept **exactly** as the client has them, including
quirks — they are not tidied up, because matching what the client already reads is the
whole point. Where the platform can contribute a column the client's sheet doesn't have
(Settled / Outstanding on the Cashflow sheet), it is **appended** rather than inserted,
so the columns they already read stay where they expect them.

**Tinted cells** (pale teal, matching `BRAND_LIGHT` in `src/lib/exportXlsx.ts`) are ones
the platform fills automatically on export. Untinted cells are entered by hand. The
distinction matters most on the Construction Accounting sheet, where Actual is
platform-filled but Budget deliberately is not — see that section.

---

## BSR_Template.xlsx

### Sheet `Basic Prices` → `BasicPriceItem`

Three parallel column groups (Materials / Labour / Plant), each Description + Unit +
Basic Price, all grouped by Trade in column A.

| Sheet | Platform field |
| --- | --- |
| Trade (col A) | `BasicPriceItem.trade` |
| which column group | `BasicPriceItem.cat` (category key; the `M-`/`L-`/`P-` prefixes live on `FieldCategory.prefix`) |
| Description | `BasicPriceItem.name` |
| Unit | `BasicPriceItem.unit` |
| Basic Price | `BasicPriceItem.price` — nullable, blank is legal (row stays `status: draft`) |

Set by the platform, not the sheet: `projectId`, `status`, `addedById`, `supplierId`.

### Sheet `Basic Rates` → `BaseItem`

The coded catalogue. Same three groups, but each carries a Code No.

| Sheet | Platform field |
| --- | --- |
| Item No. | display ordinal only — not stored |
| Description | `BaseItem.name` |
| Code No. | `BaseItem.code` (unique **within a project**, `@@unique([projectId, code])`) |
| Unit | `BaseItem.unit` |
| Price ( Rs.) | `BaseItem.rate` |
| which column group | `BaseItem.cat` |

Set by the platform: `projectId`, `updatedById`, `ownerId`, `promotedFromId`, `supplierId`.
Every rate edit writes a `PriceHistoryEntry`.

### Sheet `Activity` → `Activity`

Number → `Activity.code`, description → `Activity.name`. The 16 rows match the
client's fixed trade list.

### Sheet `Rate Analysis` → `ActivityItem` + `RecipeComponent`

The client keeps one sheet per activity (`01`…`16`); this sheet shows the repeating
block three ways — plain build-up, nested trade reference, and % allowance.

| Sheet | Platform field |
| --- | --- |
| item code, e.g. `05.A.01` | `ActivityItem.code` — reads `<activity>.<group>.<item>` |
| item description | `ActivityItem.name` (this doubles as the free-text material description, Enhancement #3) |
| `Analysis for <qty> <unit>` | `ActivityItem.analysisQty` + `ActivityItem.unit` |
| No. (1.01, 1.02 …) | `RecipeComponent.order` |
| Item Description | `RecipeComponent.name` |
| Item Ref | `RecipeComponent.sourceBaseItemCode` (`M-`/`L-`/`P-`) or `sourceActivityItemId` (nested, e.g. `05.A.01`) |
| Unit + Quantity | `RecipeComponent.qty` (stored as a display string, e.g. `"23 Bag"` / `"5.0%"`) |
| Rate | `RecipeComponent.rate` — snapshot at line creation, `null` for `pct` lines |
| Amount | `RecipeComponent.amount` — **stored**, never recomputed from the source |
| line kind | `RecipeComponent.type`: `base` (M-/L-/P- ref), `trade` (another item), `pct` (allowance) |
| `Rate for 1 <unit>` | derived — `activityItemRate()` = `sum(amount) / analysisQty` |

Two quirks preserved from the client's real file, both already handled in the schema:

- **The analysis basis is not always 1 unit.** `05.D.01` analyses 0.51 Cube, so the
  unit rate is `total / 0.51`, not the total. The template's `Rate for 1` formula
  divides by the basis cell for exactly this reason.
- **Items can reference other items.** `05.D.01` line 1 points at `05.A.01`, not at a
  Basic Rate code — that is `type: 'trade'`.

Not in the client's sheet, platform-only: `floorGround` / `floor1st` / `floor2nd` /
`floor3rd` multipliers.

---

## Income_Balance_Statement_Template.xlsx

### Sheet `Construction Accounting`

The one-page summary: letterhead, project info, an Income and an Expenses table each
with Actual / Budget / Variances, and three summary tiles. All totals, variances and
tiles are live formulas.

| Sheet | Platform source |
| --- | --- |
| Project Name / ID | `Project.name` / `Project.id` |
| Project Manager | `Project.owner` |
| Project Start Date | `Project.start` |
| Income → Contract Amount | `Project.contract` |
| Income → Progress Payments | `projectIncome().received` (`src/lib/derive.ts`) |
| Expenses → Labor / Materials / Equipment / Subcontractor Costs / Other Direct Costs | `ExpenseCategory` = Labour / Material / Machinery / SubContractor / Other |
| Total Actual Income | `projectIncome().received` |
| Total Actual Expenses | `sum(ExpensePayment.amount)` — cash actually out, not committed |
| Net Income | the difference of the two above |

**Budget — resolved 2026-08-23, scoped down from the sheet's literal Budget column.**
Rather than a stored Budget figure compared line-by-line against Actual across the whole
sheet (a new table, a new entry screen), the client confirmed the simpler real need:
compare the BSR estimate against the contract value once the BSR is built out, and warn
on a mismatch. `Project.contract` is unchanged — still the one manually-entered number,
still the sheet's "Actual." No new field was added. The BSR tab (`src/app/projects/[id]/client.tsx`,
`BsrTab`) already computed a live grand total (`grand`) for its own footer; the fix
compares that total against `contract` (tolerance >1, to absorb float noise from the
rate × floor-multiplier × qty chain) and shows an inline amber warning card — same style
as the existing "exceeds available budget" dialog — once there's an actual BSR to compare
against (`bsrLines.length > 0`, so a brand-new empty project doesn't warn against itself).
This does not reproduce the sheet's per-category Budget/Variance breakdown — it answers
one question ("does the estimate match the contract"), not the sheet's full Budget column.

The template mirrors this in a **BSR ESTIMATE vs CONTRACT** block (rows 26–29): BSR
Estimate and Contract Value are platform-filled, Difference is a live formula, and the
status cell carries the same `>1` tolerance the app uses, staying blank until both
figures are present. The sheet's own Budget column is left in place and untinted — the
client still fills it by hand in Excel if they want it; the platform simply never
touches it.

**Remaining gaps — in the client's sheet, no platform field yet:**

- *Project End Date* — `Project` has `start` but no end.
- *Change Orders* and *Retainage Released* — no equivalent concept.
- *Indirect Costs* (Overhead, Administrative, Insurance, Permits and Fees) — the
  `ExpenseCategory` enum has no indirect/overhead split.

### Sheet `Accounts` → `Expense` / `ExpensePayment` / `Milestone`

The underlying ledger. Two independent runs side by side — money **in** (A–E) and money
**out** (F–N) — then a per-category spread (O–Z). Both `Cumulative` columns are live.

| Sheet | Platform field |
| --- | --- |
| Date / Payment No / Amount / Remarks | client receipts — `Milestone` status + `ExpensePayment.method` |
| Cumulative | derived |
| Date2 | `Expense.date` |
| Entry No | ordinal |
| Description | `Supplier.name` / `SubContractor.name` (legacy `Expense.vendor` as fallback) |
| Category | `Expense.category` |
| Memo | `Expense.invoice` |
| Stage | `Expense.stage` |
| BOQ Item | legacy `Expense.boq`, superseded by `ExpenseLineItem` |
| Total | `Expense.amount` |
| Cumulative2 | derived |

**Gap:** the spread columns (Transport, Site Visit, Minor Material, Major Material,
Service Charge, Utility Bills, Food & Beverages, Fuel, Others) are finer-grained than
the platform's six-value `ExpenseCategory` enum. Either the enum grows, or these fold
into `Other` and detail is lost on import — worth a client decision before any bulk load.

### Sheet `Vendor Summary`

The pivot the client keeps beside the ledger: one row per vendor, one column per
category, live Grand Total. Maps to `/api/payments` (Enhancement #5), which already
groups by real `supplierId` / `subContractorId`.

---

## Payments_Schedule_Template.xlsx

### Sheet `Cashflow` → `Stage`

| Sheet | Platform field |
| --- | --- |
| STAGES | `Stage.name` / `Stage.order` |
| AMOUNT | `Stage.value` (null = even split of contract, see `stageValue()`) |
| START / COMPLETION | `Stage.startDate` / `Stage.completionDate` (migration `0022_stage_dates.sql`) |
| SETTLED | derived — milestones not `pending`/`cheque_bounced` (a bounced cheque is unsettled again) |
| OUTSTANDING | derived — `AMOUNT − SETTLED`, live formula in the template |
| TOTAL AMOUNT | `Project.contract` |

SETTLED and OUTSTANDING are **platform additions** — not in the client's original sheet.
They fall out of milestone statuses already tracked, so they cost nothing to provide and
are appended after the client's own five columns.

**Closed 2026-08-23** — same opt-in treatment as `Milestone.dueDate`: both nullable,
`null` means "not tracked," editable per stage on the Stages & Payments tab, and now
included as extra columns in the Payments Schedule export (`exportPaymentsScheduleToExcel`
in `src/lib/exportXlsx.ts`).

### Sheet `Stagewise Payments` → `Milestone`

The 50 / 25 / 25 split, one column per stage, every cell a live
`percentage × stage amount` formula.

| Sheet | Platform field |
| --- | --- |
| PAYMENT TYPE | `MilestoneLabel` — Advance / Interim / Final |
| PERCENTAGE | `Milestone.pct` |
| stage cells | `milestoneAmount()` = `perStage × pct/100`, or `Milestone.amount` when overridden |

The template is built for 4 stages because the source file was; `Project.stages` varies
per project, so a generated export should emit one column per actual stage.

---

## Suggested next step

Wire the BSR shape into `src/lib/exportXlsx.ts` so the platform's export button emits
this layout instead of the current flat table — the Payments Schedule export already
does (`exportPaymentsScheduleToExcel`), now including Start/Completion. The
Construction Accounting sheet still cannot be produced faithfully as a full
Budget/Actual/Variance report — the client only wanted the narrower BSR-vs-contract
mismatch warning (now built, see above), not the sheet's full per-category Budget
column. Change Orders, Retainage, Indirect Costs and Project End Date remain open if
the client asks for that fuller sheet later.

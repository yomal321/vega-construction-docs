# Proposed Features — Catalog Import/Export, Supplier Price Comparison, Cash Flow Forecast, PDF Quotation

**Date:** 2026-08-28
**Status:** Proposal — not yet approved or scheduled.
**Scope:** Four independent features. Each stands alone and can be built separately; they are
ordered by recommended build sequence, not by dependency (there are no hard dependencies between
them).

---

## Contents

1. [Bulk Import / Export for Basic Price & Basic Rate](#1-bulk-import--export-for-basic-price--basic-rate)
2. [Supplier Price Comparison](#2-supplier-price-comparison)
3. [Cash Flow Forecast](#3-cash-flow-forecast)
4. [PDF Quotation Export](#4-pdf-quotation-export)

**Recommended order:** 1 → 2 → 3 → 4. Feature 1 is the on-ramp that gets real data into the
system; Feature 2 is the cheapest to build and has direct financial return; Features 3 and 4 are
both valuable but neither blocks anything else.

---

# 1. Bulk Import / Export for Basic Price & Basic Rate

## Problem

There is no way to get catalog data into the system except by typing it in one item at a time,
through the "Add" modals on `/basic-price` and `/basic-rate` (and their per-project tab
equivalents in `src/app/projects/[id]/client.tsx`).

This matters more than it first appears, for two reasons.

**The real catalog has never been loaded.** The client's source file `doc/BSR for Pricing.xlsx`
contains **207 Basic Price rows** and **178 Basic Rate rows**. The database currently holds 16 and
35 respectively — demo seed data. Nobody has hand-typed 385 rows, and nobody reasonably will.

**The cost repeats per project.** Basic Price and Basic Rate are per-project catalogs
(Enhancement #2, migration `0012_project_scoped_catalog.sql`) — a brand-new project starts with an
empty catalog. "Clone from another project"
(`src/app/api/projects/[id]/basic-rate/clone/route.ts`) mitigates this, but only *after* a first
project exists with a real catalog in it. Someone still has to get those rows in once, manually,
before clone is useful at all.

There is also no bulk **edit** path. Repricing a catalog when the market moves means opening and
saving each item individually.

Note that `src/lib/exportXlsx.ts` currently exports BSR, Payments Schedule, Expenses, and the
Portfolio Statement — **there is no export for Basic Price or Basic Rate at all**. So this feature
is two pieces of work: build the catalog export first, then the import that reads its own format
back.

## Solution

Add Excel export and import for both catalogs, where **the export format is the import format**.
The file the user downloads is the file they edit and upload back. One format used in both
directions — no separate template to design and keep in sync.

```
Export Basic Rate  →  .xlsx  →  edit in Excel  →  Import  →  updated
                      ▲                                │
                      └────────  same file shape  ─────┘
```

`exceljs` is already a dependency (used by the existing exports) and reads as well as writes, so
this adds no new packages.

### Decision: we define the format, not the client's spreadsheet

The client's existing `BSR for Pricing.xlsx` is **not** a flat table and will not be parsed
directly. Its `Basic Prices` sheet is pivoted — a single spreadsheet row holds three separate
catalog items side by side (a Materials block, a Labour block, and a Plant block), with the
`Trade` column merged and carried down visually across many rows. `Basic Rates` has the same
shape: a MATERIALS block in columns 1–5, a LABOUR block from column 6.

Writing a parser for that layout would be fragile product code that breaks the first time the
client adds a column.

> **Decision (confirmed 2026-08-28):** the client does not need to keep using their existing
> spreadsheet. They will use our exported format going forward. Loading their existing 385 rows is
> a separate **one-time** job — a throwaway script or a manual paste into the exported file — and
> is explicitly out of scope for this feature.

### 1.1 Export — `src/lib/exportXlsx.ts`

Two new functions, following the existing `exportBsrToExcel` pattern in the same file (same
`ExcelJS.Workbook()` construction, same `wb.creator = 'Vega Construction Manager'`, same
`styleTitle` header treatment, same client-side generation):

```ts
export async function exportBasicRateToExcel(opts: {
  project: Project; currency: string; items: BaseItem[]
  categories: FieldCategory[]; suppliers: Supplier[]
})

export async function exportBasicPriceToExcel(opts: {
  project: Project; currency: string; items: BasicPriceItem[]
  categories: FieldCategory[]; trades: Trade[]; suppliers: Supplier[]
})
```

**Basic Rate columns:**

| id | code | description | cat | unit | rate | supplier |
|----|------|-------------|-----|------|------|----------|

**Basic Price columns:**

| id | trade | description | cat | unit | price | supplier |
|----|-------|-------------|-----|------|-------|----------|

Basic Price has no `code` — drafts are uncoded until promoted. Its `price` may legitimately be
blank; that is a valid draft state, not an error.

Add an "Export" button to `/basic-rate`, `/basic-price`, and both per-project catalog tabs,
matching the existing "Export BSR" button placement and styling.

### 1.2 The `id` column — how import distinguishes create from update

The first column is the item's internal `id`, and it is the entire matching mechanism:

- **`id` present** → update that existing item
- **`id` blank** → create a new item

A user adding items simply types new rows at the bottom and leaves `id` empty. For Basic Rate,
generate the new item's `code` server-side via the existing `nextCode(prefix, existingCodes)`
helper in `src/lib/derive.ts`, using the prefix from the row's category (`FieldCategory.prefix`).

Match on `id`, **not** on `code`. Two reasons: `code` is only unique *within* a project
(`@@unique([projectId, code])` in `prisma/schema.prisma`), so it is not a safe key on its own; and
Basic Price drafts have no code at all, so `id` is the only key that works for both catalogs.
Matching on `id` also survives a user renaming a code in the spreadsheet.

### 1.3 Import — parse client-side, insert server-side

`exceljs` already runs in the browser for the existing exports, so parse there and POST clean
JSON. The file never reaches the Worker — no upload size limits, no Worker memory pressure — and
the user gets an instant preview.

```
Browser:  read .xlsx → parse rows → validate → render preview table
             │
             └── POST clean JSON rows
                    ↓
Worker:   re-validate → db.batch() in chunks → { created, updated, skipped, errors }
```

**New routes:**

- `POST /api/projects/[id]/basic-rate/import`
- `POST /api/projects/[id]/basic-price/import`

Both gated by `requirePermission('projects', 'create')` then
`requireProjectAccess(session, projectId)`, exactly as the clone route does.

The clone route (`src/app/api/projects/[id]/basic-rate/clone/route.ts`) is the structural template
— it already does fetch-existing → filter → `db.batch()` → return a `{ cloned, skipped }` summary.
Import is the same shape with a parsed file as the source instead of another project.

### 1.4 Preview step (required, not optional)

Import must never write anything until the user confirms a preview. Two hundred bad rows is far
worse than one bad row. The preview shows counts plus a scrollable row-level table:

```
  142 items will be updated
   18 items will be created
    3 rows have errors  (highlighted, excluded from import)

  row 47   unit 'Gallon' is not a known unit
  row 89   rate must be a positive number (got '-')
  row 152  category 'Materials' is not a known category — did you mean 'Material'?

  [ Cancel ]   [ Import 160 rows ]
```

Rows with errors are excluded and reported; valid rows still import. This is a deliberate choice
over all-or-nothing — a single typo in a 200-row file should not block the other 199.

### 1.5 Implementation cautions

These are the items that cause real damage if skipped.

**(a) Price history on rate changes — critical.** If an import updates an existing `BaseItem`'s
`rate`, it **must** write a `PriceHistoryEntry` row, exactly as the single-item edit path already
does in `src/app/api/projects/[id]/basic-rate/[code]/route.ts`.

Skipping this breaks two systems at once: the audit trail, and the Gap #11 stale-flag logic.
`isComponentStale()` in `src/app/projects/[id]/client.tsx` detects a changed rate by comparing a
recipe component's snapshotted rate against the live Basic Rate item. A bulk reprice that does not
record history would leave recipes across every project silently showing outdated amounts with no
"Price changed" badge — the exact failure Gap #11 was built to prevent, reintroduced at scale.

> **A bulk import that skips this is worse than having no import at all.**

**(b) Chunk the batch.** Do not send 200 INSERT/UPDATE statements as a single `db.batch()`. D1
imposes limits on statements per batch, and chunking (~50 at a time) also allows partial-progress
reporting. This means an import is *not* fully atomic across chunks — the preview step is what
makes that acceptable, since the data was validated before any write.

**(c) Re-validate on the server.** The preview validates in the browser, but the API must re-check
`cat` against `categories`, `unit` against `units`, and `trade` against `trades` independently.
Never trust the client's validation.

**(d) Supplier column is by name, resolved to `supplierId`.** Users edit names in Excel, not cuids.
Resolve name → id server-side; an unrecognised supplier name is a row error, not a silent null.
Blank is valid and means "no supplier linked" — per the `supplierId` comment in
`prisma/schema.prisma`, null means unknown, not a gap to force-fill.

## Scope note

Build **Basic Rate first and ship it before starting Basic Price.** Basic Rate is the simpler
shape (flat: code, description, cat, unit, rate) and it is the catalog that feeds recipes, so it
delivers value standing alone. Basic Price adds the draft / optional-price / promote lifecycle on
top — more edge cases, less urgency.

## Estimated effort

**~3 days** for both catalogs (export + import + preview + history logging), assuming the
export-format-is-import-format decision above holds.

---

# 2. Supplier Price Comparison

## Problem

Migration `0019_basic_price_supplier.sql` added `supplierId` to both `basic_price_items` and
`base_items`, and `src/app/suppliers/[id]/page.tsx` uses it to answer one direction of the
question:

> **Pick a supplier → what do they supply us, and what have we paid them?**

The inverse question has no answer anywhere in the application:

> **Pick an item → who supplies it, and who is cheapest?**

This gap is widened by the per-project catalog design. Because Piliyandala's Cement and Homagama's
Cement are entirely independent rows, a better price discovered on one project is structurally
invisible from another. The per-project split was the right call — prices genuinely differ by
project and date — but it fragmented the company's pricing knowledge, and nothing currently
reassembles it.

## Solution

A cross-project price comparison view: group catalog items by description, then list every
supplier who has supplied it and at what rate, across every project the session can access.

### 2.1 New route — `GET /api/suppliers/price-comparison`

Gated by `requirePermission('suppliers', 'view')`. One grouped query over `base_items` joined to
`suppliers` and `projects`, filtered by `projectAccessClause(session, 'p.id', 'p.ownerId')`.

> **Important:** pass a table-qualified `idColumn` (`'p.id'`). See the warning comment on
> `projectAccessClause` in `src/lib/rbac.ts` about the EXISTS subquery silently resolving against
> the wrong scope when the column is unqualified — a project the user is merely *assigned* to
> vanishes, while their own projects still appear, which makes the bug easy to miss.

Grouping key: normalised `name` (trimmed, case-insensitive) **plus `unit`**. Comparing items with
different units is meaningless, so unit must be part of the key.

### 2.2 New page — `src/app/suppliers/compare/page.tsx`

A searchable list of catalog descriptions; selecting one expands to show every supplier and rate:

```
Cement  (per Bag)
──────────────────────────────────────────────────────────────
  Lanka Cement Ltd      2,280    Piliyandala      Jun 2026   ← lowest
  Holcim Agent          2,380    Kandy House      Jul 2026
  Tokyo Cement          2,450    Homagama         Aug 2026
──────────────────────────────────────────────────────────────
  Spread: 170 (7.5%)
```

Reuse the existing "highest / lowest data bar" treatment already used in the Stage Costs tab and
the Payments page (see `src/app/projects/[id]/client.tsx:2178` and `src/app/payments/page.tsx:310`)
rather than inventing a new visual language.

Include items with **no supplier linked** as an explicit "unlinked" row rather than hiding them —
consistent with how `doc/NO_SUPPLIER_BREAKDOWN_PROMPT.md` already treats this case, and useful in
its own right ("which of our prices have no supplier attached?").

Link the page from the Suppliers & Sub-Contractors nav entry, as a tab or a secondary action.

## Outcome

The only feature on this list that directly *reduces* cost rather than reporting on it. Material is
typically 50–60% of a residential build; on a LKR 24.9M contract, a 3% materials saving is roughly
**LKR 400,000 on a single house**. It also gives the purchaser evidence in a supplier negotiation,
and surfaces quiet price rises that would otherwise go unnoticed.

## Estimated effort

**~1–2 days. No schema change** — this reads data migration 0019 already stores. The cheapest item
on this list, and arguably the highest direct financial return.

---

# 3. Cash Flow Forecast

## Problem

The dashboard (`src/app/api/dashboard/route.ts`, `src/app/page.tsx`) reports the **past**: contract
value, income received, expense committed, expense paid, ROI. It says nothing about what is
coming.

For a construction business that is the wrong half of the picture. Construction companies rarely
fail from lack of profit — they fail from running out of cash while profitable, when a supplier
bill falls due before a stage payment arrives.

The data needed to answer this now exists and is unused:

| Source | Meaning |
|--------|---------|
| `Milestone.dueDate` (migration 0021) | when income is expected |
| `Stage.startDate` / `completionDate` (migration 0022) | when stages run |
| `ExpensePayment.date` | historical outflow, for run-rate estimation |
| `Expense.amount` − paid | outstanding supplier obligations |

Note the client's own source spreadsheet is named `Payments_Schedule_Cash_Flow.xlsx` — this is
something they were already doing manually before the system existed.

## Solution

A forward-looking money-in vs money-out projection on the dashboard, covering the next 6 months.

### 3.1 New route — `GET /api/dashboard/cashflow`

Gated by `requirePermission('dashboard', 'view')`, filtered by `projectAccessClause` on the same
owner-or-member basis as the existing dashboard route. Returns one bucket per month for the next
six months:

| field | source |
|-------|--------|
| `expectedIn` | sum of `milestoneAmount()` for milestones with `dueDate` in month, status `pending` or `cheque_bounced` |
| `chequePending` | milestones with status `cheque_received` — deposited, not yet cleared |
| `expectedOut` | outstanding balance (`amount − sum(payments)`) on unpaid expenses |
| `net` | `expectedIn − expectedOut` |

Reuse `milestoneAmount()` and `stageValue()` from `src/lib/derive.ts` — do not reimplement the
milestone amount fallback logic.

**Keep `cheque_received` in its own bucket.** Per the existing comment in `projectIncome()`, a
deposited cheque is not money until it clears. Folding it into `expectedIn` would overstate
available cash — precisely the error this feature exists to prevent.

**Aggregate in SQL, not in JS.** The existing dashboard route materialises every milestone and
every expense row in Worker memory. That is fine at current scale but is the first thing to break
as project count grows. Do not extend that pattern here — use `GROUP BY` and return month buckets.

### 3.2 Dashboard section — `src/app/page.tsx`

A grouped bar chart (in vs out per month) with a net line, plus a plain table beneath it:

```
        Sep         Oct         Nov         Dec
in     2,490,000           0   4,980,000   1,200,000
out    1,900,000   3,200,000   2,100,000   1,800,000
net     +590,000  −3,200,000  +2,880,000    −600,000
                   ▲ shortfall
```

Highlight negative months, matching the existing red-highlight treatment used for over-budget and
outstanding figures elsewhere in the app.

### 3.3 Honest handling of missing dates

`Milestone.dueDate` and the `Stage` date columns are **optional by design** — null means "not
tracked", and per the migration comments this deliberately generates no notification. The forecast
must respect that: undated milestones are excluded from the projection and reported separately as
an explicit caveat —

> "LKR 3,200,000 across 4 milestones has no due date and is not shown below."

— never silently guessed into a bucket, and never quietly dropped.

## Outcome

Answers "can we afford to start another project in October?" and "should we chase this client
payment early?" — questions the system currently cannot address at all, using data it already
holds.

## Estimated effort

**~2–3 days. No schema change** — migrations 0021 and 0022 already added everything needed.

> Migration `0022_stage_dates.sql` and its supporting changes were still **uncommitted** in the
> working tree as of 2026-08-28. Commit that work before building on top of it.

---

# 4. PDF Quotation Export

## Problem

All four existing exports in `src/lib/exportXlsx.ts` are **internal working documents** —
unbranded Excel workbooks containing full cost structure. There is no client-facing document.

This creates two problems.

**No professional output.** Quoting a customer today means exporting the BSR to Excel and
rebuilding it in Word to make it presentable. The only part of this system a customer ever sees is
a raw spreadsheet, which badly undersells a capable product.

**Margin disclosure risk.** `exportBsrToExcel` writes the full recipe breakdown — every
ingredient, every rate, every percentage allowance. Emailing that workbook to a customer hands
them Vega's entire cost base and markup. That is a live commercial risk, not a hypothetical one.

## Solution

A branded PDF quotation generated from the same BSR data, showing **activity-level totals only** —
never recipes, component rates, or allowances.

### 4.1 Library choice

There is no PDF dependency in `package.json` today. Generate **client-side**, matching the
existing constraint on the Excel exports (a Cloudflare Worker is not the place to render
documents). `jsPDF` + `jspdf-autotable` is the lightest fit for a table-driven document; confirm
bundle impact before committing to it.

New file: `src/lib/exportPdf.ts`, alongside `exportXlsx.ts`.

### 4.2 Document content

```
┌──────────────────────────────────────────────────┐
│  [Vega logo]              QUOTATION Q-2026-014   │
│                                  15 August 2026  │
│                                                  │
│  Two-storey house — Homagama                     │
│  Client: [Project.client]                        │
│  Site:   [Project.location]                      │
│                                                  │
│  04  Random Rubble Masonry Work       3,003,658  │
│  05  Concrete Work                   16,238,524  │
│  06  Formwork                         2,100,000  │
│  ...                                             │
│  ──────────────────────────────────────────────  │
│  Total Contract Value          LKR 24,900,000    │
│                                                  │
│  PAYMENT SCHEDULE                                │
│  Stage 1 — Foundation        10%      2,490,000  │
│  Stage 2 — Superstructure    25%      6,225,000  │
│  ...                                             │
│                                                  │
│  Valid 30 days.   Signature: ________________    │
└──────────────────────────────────────────────────┘
```

**Activity subtotals only.** The recipe layer must not appear. This is the single most important
constraint on this feature — it is the difference between a quotation and a leak of the cost base.

Currency comes from the existing `CurrencyProvider`, consistent with every other screen.

### 4.3 Progress claim variant

The same generator, scoped to one stage, produces a progress-claim invoice: *"Stage 2 complete —
LKR 6,225,000 now due."* Same branding, same code path, different filter. Worth building at the
same time; it is a small addition once the document engine exists.

### 4.4 Placement

"Export quotation (PDF)" alongside the existing "Export BSR" button on the project's BSR tab. Keep
both — the Excel export remains the internal tool, the PDF is the external one. Consider labelling
them explicitly ("Export BSR — internal") to reduce the chance of the wrong file being emailed to
a customer.

## Outcome

Every other feature on this list helps Vega manage work they already have. This is the only one
that helps them **win** work — and it closes the margin-disclosure risk that exists today.

## Estimated effort

**~3 days**, including the progress-claim variant. No schema change; reads data the BSR tab
already loads.

---

# Summary

| # | Feature | Effort | Schema change | Primary value |
|---|---------|--------|---------------|---------------|
| 1 | Bulk import / export | ~3d | No | Gets real data into the system; enables bulk repricing |
| 2 | Supplier price comparison | ~1–2d | No | Directly reduces material cost |
| 3 | Cash flow forecast | ~2–3d | No | Prevents cash shortfalls |
| 4 | PDF quotation | ~3d | No | Wins work; closes margin-disclosure risk |

**None of the four requires a schema change** — each reads data the database already stores.

**Recommended sequence:** 1 → 2 → 3 → 4.

## Prerequisite

One existing defect should be fixed before adding this surface area.

`src/app/api/projects/[id]/expenses/[expenseId]/payments/route.ts:42-49` performs a check-then-act
on the overpay guard — it reads the paid total, then inserts in a separate statement. Two
concurrent payment requests can both pass the check and both insert, overpaying an expense with no
constraint to catch it. D1 has no interactive transactions, so the fix is to fold the guard into
the insert as a conditional write inside a single `db.batch()`, treating `meta.changes === 0` as
the rejection.

Roughly half a day.

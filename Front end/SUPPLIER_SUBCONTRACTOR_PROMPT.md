# Feature: Real Supplier & Sub-Contractor entities (replacing free-text vendor)

## Problem

`Expense.vendor` is a free-typed text field with no dedicated table behind it. The Payments
Summary page (Enhancement #5, `src/app/api/payments/route.ts`) currently groups expenses "by
supplier" using text-matching only (`lower(trim(vendor))`), which is explicitly flagged in that
file's own comment as a known limitation: two spellings of the same real company ("Cement
Suppliers" vs "Cement Suppliers Ltd") are treated as different vendors, and there's no way to
manage a canonical list of who Vega actually works with.

## Solution

Introduce two separate, global (not project-scoped) entities — `Supplier` and
`SubContractor` — and link `Expense` to them by a real foreign key instead of free text. Two
separate tables, not one shared "vendor" entity, because suppliers and sub-contractors are
different kinds of relationships in this business (matches the enhancement's own title,
"Suppliers **&** Sub-Contractors," and the two buckets already built on the Payments page) —
and because the same real company legitimately might appear as a material supplier on one
expense and a sub-contractor on another (already confirmed as intentional when Enhancement #5
was designed), which two independent tables handle naturally: one row in each, not a shared
row with a fixed "type."

### 1. Data model

Two new models, both global — same shape/spirit as the existing `Activity` model
(`prisma/schema.prisma:165-172`), which is the precedent for a simple, admin-managed,
non-project-scoped lookup list in this codebase:

```prisma
model Supplier {
  id       String    @id @default(cuid())
  name     String
  expenses Expense[]

  @@map("suppliers")
}

model SubContractor {
  id       String    @id @default(cuid())
  name     String
  expenses Expense[]

  @@map("sub_contractors")
}
```

On `Expense`, replace the plain-text-only vendor with two nullable relations:

```prisma
model Expense {
  ...
  vendor          String          // KEPT for legacy display fallback on rows written before
                                   // this migration and as a raw label if a supplier/sub-contractor
                                   // is ever deleted — no longer authoritative once one of the two
                                   // FKs below is set. Same "keep the old column, stop trusting it"
                                   // pattern already used for Expense.method after ExpensePayment
                                   // was introduced.
  supplierId      String?
  supplier        Supplier?       @relation(fields: [supplierId], references: [id])
  subContractorId String?
  subContractor   SubContractor?  @relation(fields: [subContractorId], references: [id])
  ...
}
```

Exactly one of `supplierId` / `subContractorId` should be set per expense, decided by
`category`: `category = SubContractor` → `subContractorId` set, `supplierId` null; every other
category → `supplierId` set, `subContractorId` null. Enforce this in application code (the API
route validating the expense payload), not a DB constraint — this codebase doesn't rely on
D1-enforced constraints for cross-field business rules elsewhere either (see how the overpay
check in the payments route is application-level, not a DB check).

### 2. Migration

Write the D1 migration by hand under `migrations/` (check the most recent file, e.g.
`0014_expense_payments.sql`, for the header-comment/style convention to copy). It needs to:

1. Create `suppliers` and `sub_contractors` tables.
2. Add `supplierId` and `subContractorId` columns to `expenses` (nullable, no default).
3. Backfill: for every distinct `lower(trim(vendor))` value among expenses where
   `category != 'SubContractor'`, insert one row into `suppliers` (display name = the most
   recently used exact casing for that normalized value — same rule already implemented in
   `src/app/api/payments/route.ts`'s grouping logic, reuse that exact tie-breaking approach).
   Do the same for `category = 'SubContractor'` rows into `sub_contractors`. If the same
   normalized name appears in both groups, it correctly gets one row in each table — that's
   the intended outcome, not a bug (mirrors the already-confirmed "same company, two roles"
   design from Enhancement #5).
4. Update every `expenses` row's new `supplierId`/`subContractorId` to point at the matching
   backfilled row (matched by category + normalized vendor name).

Leave a comment flagging this is a straightforward backfill (no ambiguous placeholder decision
like the earlier migrations had, since supplier identity here is fully recoverable from
existing data) — but still note it should be spot-checked against real data before running in
production, in case vendor-name spelling is messier there than in dev/seed data.

### 3. New admin page: Supplier & Sub-Contractor management

New page, e.g. `src/app/suppliers/page.tsx`, with two tabs — "Suppliers" and
"Sub-Contractors" — same tab pattern already used on `src/app/payments/page.tsx`. Each tab is a
simple CRUD list (add / rename / delete), matching `src/app/activities/page.tsx` and
`src/app/api/activities/route.ts` + `src/app/api/activities/[code]/route.ts` exactly for the
UI/API pattern to copy (just keyed by `id` instead of `code`, since these use `cuid()` ids like
most other entities in this app rather than a natural code).

New API routes: `src/app/api/suppliers/route.ts` (GET list, POST create),
`src/app/api/suppliers/[id]/route.ts` (PATCH rename, DELETE), and the same pair under
`src/app/api/sub-contractors/`. Reject deleting one that's still referenced by any expense
(same "can't delete something still in use" pattern this app already applies elsewhere, e.g.
rejecting removal of a project owner) — surface a clear error rather than a raw FK failure.

Add a permission module: extend `PERMISSION_CATALOG` in `src/lib/rbac.ts` with
`{ module: 'suppliers', label: 'Suppliers & Sub-Contractors', actions: ['view','create','edit','delete'] }`
covering both lists (one module for both tabs, same as `activities` is one module for its one
list) — do not fold this into the `projects` module, since these are global entities like
Activities, not project sub-resources.

Add a sidebar entry (`src/components/Sidebar.tsx`, `NAV_ITEMS`) near Activities, since it's the
same kind of global admin list.

### 4. Expense form changes (`ExpenseModal` in `src/app/projects/[id]/client.tsx`)

Replace the current free-text vendor `<input>` (around `client.tsx:1974`, `Field label="Vendor"`)
with a picker whose source list depends on the already-selected `category`:
- `category === 'SubContractor'` → picker lists `SubContractor` entries.
- any other category → picker lists `Supplier` entries.

Include an inline "+ Add new [supplier/sub-contractor]" option in the picker so logging an
expense for a brand-new one doesn't require leaving the form first — on selecting it, prompt
for a name, POST it to the relevant create endpoint, then select the newly created entry.
Switching the category dropdown after a supplier/sub-contractor is already picked should clear
that selection, since the picker's source list just changed underneath it.

`save()` now sends `supplierId` or `subContractorId` (whichever applies) instead of a raw
`vendor` string — the API route should resolve `vendor` (the legacy display column) from the
picked entity's `name` when saving, so old code paths that still read `Expense.vendor` for
display keep working without every one of them needing to be rewritten immediately.

### 5. Update every consumer currently reading `vendor` as free text

- `ExpensesTab` (same file) — vendor column reads through the relation
  (`e.supplier?.name ?? e.subContractor?.name ?? e.vendor`) rather than the raw column, so it
  still works correctly for both old (pre-migration) and new rows.
- **`src/app/api/payments/route.ts`** — this is the actual fix this whole feature is for.
  Replace the `lower(trim(vendor))` grouping entirely: the Supplier bucket becomes
  `group by supplierId` (joined to `suppliers` for the display name), the Sub-Contractor
  bucket becomes `group by subContractorId` (joined to `sub_contractors`). Remove the
  now-obsolete "known v1 limitation" comment about text-matching — this replaces it, doesn't
  sit alongside it.
- `src/lib/exportXlsx.ts:249` — reads the resolved vendor name (supplier/sub-contractor name,
  falling back to the legacy `vendor` column) rather than the raw `e.vendor`, same fallback
  logic as `ExpensesTab`.

## Suggested implementation order

1. Prisma schema (`Supplier`, `SubContractor` models, `Expense`'s two new nullable FKs) +
   hand-written migration with the category-aware backfill.
2. New CRUD API routes + `PERMISSION_CATALOG` entry + sidebar nav + the two-tab management page.
3. `ExpenseModal` picker (category-dependent source list, inline "+ Add new").
4. Update `ExpensesTab`, `/api/payments`, and `exportXlsx.ts` to read through the new relations.
5. Manual verification: confirm every pre-existing expense still shows the correct vendor name
   after migration (via its now-backfilled `supplierId`/`subContractorId`). Log a new expense,
   pick category "Sub Contractor," confirm the picker only offers sub-contractors, create a
   brand-new one inline, save, and confirm it appears correctly on both the project's Expenses
   tab and the Payments page's Sub-Contractor bucket (not the Supplier bucket). Attempt to
   delete a supplier/sub-contractor that's still referenced by an expense and confirm it's
   rejected with a clear message rather than a raw DB error.

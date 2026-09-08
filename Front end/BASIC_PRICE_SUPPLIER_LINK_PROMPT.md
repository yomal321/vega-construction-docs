# Feature: Link Basic Price/Rate items to a Supplier (optional)

## Problem

`BasicPriceItem` and `BaseItem` (the Basic Price draft and promoted Basic Rate catalog,
`prisma/schema.prisma:197-247`) have no connection to who actually supplies that material. The
`Supplier` table already exists (built for Enhancement #5's Payment Summary,
`prisma/schema.prisma:181-187`), but nothing links it to the price catalog — there's no way to
answer "which materials does this supplier provide" or to see a supplier's full relationship
(payments AND items) in one place.

## Solution

Add an **optional** `supplierId` relation from `BasicPriceItem`/`BaseItem` to the existing
`Supplier` table. Optional is the operative word here — this is not a required field, and
handling "no supplier" isn't a special case to design around, it's the same treatment this
codebase already gives every other optional field (e.g. `BasicPriceItem.trade`,
`Expense.boq`): store `null`, display a clear "—" / "No supplier" placeholder, never force a
value, and let it be filled in or edited later whenever it's actually known.

**Only `Supplier`, not `SubContractor`, applies here.** Basic Price/Rate is a materials
catalog — sub-contractors are a labour/work relationship (tracked via `Expense.category =
SubContractor`), not something that supplies a priced material item. Don't add a
`subContractorId` to these models; it wouldn't map to anything meaningful.

### 1. Data model

```prisma
model BasicPriceItem {
  ...
  supplierId String?
  supplier   Supplier? @relation(fields: [supplierId], references: [id])
  ...
}

model BaseItem {
  ...
  supplierId String?
  supplier   Supplier? @relation(fields: [supplierId], references: [id])
  ...
}
```

Add the reverse relation on `Supplier` (`basicPriceItems BasicPriceItem[]` and
`baseItems BaseItem[]`, alongside its existing `expenses Expense[]`).

### 2. Migration

Write the D1 migration by hand under `migrations/` (check the most recent file for the
header-comment/style convention). This one is genuinely simple — no backfill/placeholder
decision needed, unlike earlier migrations in this project: every existing row correctly gets
`supplierId = NULL` (we don't know who supplied historical items, and that's a true, honest
answer, not a gap to paper over). Just:
```sql
ALTER TABLE basic_price_items ADD COLUMN supplierId TEXT REFERENCES suppliers(id);
ALTER TABLE base_items ADD COLUMN supplierId TEXT REFERENCES suppliers(id);
```
(plus matching indexes if this codebase's convention is to index every FK column — check a
recent migration like `0012_project_scoped_catalog.sql` for whether that's the pattern here).

### 3. API changes

- `POST /api/projects/[id]/basic-price` (`src/app/api/projects/[id]/basic-price/route.ts`) —
  accept an optional `supplierId` in the request body, store it (null if omitted).
- `GET /api/projects/[id]/basic-price` (same file) — left join to `suppliers` and include the
  supplier's name in the response (`supplierName: string | null` or similar), same pattern
  already used for `addedByName` in this route's existing query.
- `POST /api/projects/[id]/basic-price/[draftId]/promote`
  (`src/app/api/projects/[id]/basic-price/[draftId]/promote/route.ts`) — carry `supplierId`
  forward from the draft into the new `base_items` row, the exact same way `ownerId` already
  carries forward from `draft.addedById` in this route today (read the draft's `supplierId`
  alongside its `name`/`cat`/`addedById`, include it in the `insert into base_items` statement).
- `GET /api/basic-price` and `GET /api/basic-rate` (the global cross-project pages,
  `src/app/api/basic-price/route.ts` / `src/app/api/basic-rate/route.ts`) — same left-join
  addition, for consistency between the per-project and global views.
- **New:** extend `GET /api/suppliers/[id]` (or add a nested route, whichever this codebase's
  existing supplier-detail pattern supports) to also return that supplier's linked Basic
  Price/Rate items, not just their expenses — this is the actual payoff of adding the relation:
  one place to see a supplier's whole relationship (what they've been paid, what they supply).

### 4. UI changes

- Add Basic Price item form (wherever the create modal lives — check `src/app/basic-price/page.tsx`
  and the per-project Basic Price tab in `client.tsx` for the exact form component) — add an
  optional Supplier picker, same searchable-dropdown-with-inline-"+ Add new" pattern already
  used for the Expense form's vendor picker. Leaving it blank is a fully valid, unremarkable
  choice — no validation error, no warning.
- Basic Price / Basic Rate tables — add a Supplier column (or fold it into an existing column)
  showing the supplier's name, or `"—"` / `"No supplier"` when null — same visual treatment as
  the existing `boq ?? '—'` fallback on the Expenses tab.
- `/suppliers` page — extend the existing per-supplier drill-down (built for Enhancement #5)
  to also list their linked Basic Price/Rate items alongside their payment history, so a
  supplier's profile shows the complete picture in one place.

## Suggested implementation order

1. Prisma schema (`supplierId` on both models) + simple migration (no backfill complexity).
2. API: create/list/promote routes updated to read/write/carry-forward `supplierId`; global
   basic-price/basic-rate routes updated to include supplier name.
3. UI: optional Supplier picker on the create form, Supplier column on the tables, drill-down
   addition on the Suppliers page.
4. Manual verification: create a Basic Price item with no supplier — confirm it saves fine and
   shows "No supplier" everywhere. Create another with a supplier, promote it to Basic Rate,
   confirm the supplier link survives promotion. Open that supplier's profile on `/suppliers`
   and confirm both the item and its later payment history (if any expenses reference the same
   supplier) show up together.

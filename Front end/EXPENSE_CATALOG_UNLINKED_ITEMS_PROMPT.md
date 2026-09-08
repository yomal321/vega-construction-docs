# Feature: "Unlinked items" filter in the Log Expense catalog picker

## Problem

In `ExpenseModal` (`src/app/projects/[id]/client.tsx:2358` onward), once a real Supplier is
picked as the expense's vendor, the "From Basic Rate" catalog picker (`itemMode === 'catalog'`)
only ever shows items linked to *that specific supplier* — `basicRateForSupplier`
(`client.tsx:2464`) filters strictly on `b.supplierId === supplierId`. Any Basic Rate item with
no supplier set (a valid, intentional state — supplier linking on Basic Price/Rate is optional,
see `prisma/schema.prisma`) can never be reached through this picker at all, for any vendor.
Today the only workaround is typing the description/amount manually via "Custom text," which
works but skips the auto-fill-from-catalog convenience entirely.

## Solution

Add a small source filter **inside the existing catalog section**, not the Supplier field
itself — the Supplier field keeps meaning exactly one thing (who this expense is being paid
to) and must stay untouched. The filter only changes which Basic Rate items the picker draws
from underneath it.

### 1. New state

Add `const [itemSource, setItemSource] = useState<'supplier' | 'unlinked'>('supplier')`
alongside the other `item*` state declared around `client.tsx:2391-2397`. Reset it to
`'supplier'` whenever the vendor changes (in `handleVendorKindChange`, `client.tsx:2419-2422`,
and wherever `setSupplierId` is otherwise called directly) — an "unlinked items" selection from
a previous supplier shouldn't silently carry over to a different one.

### 2. Update the filtering logic

Change `basicRateForSupplier` (`client.tsx:2464`) from:
```ts
const basicRateForSupplier = useMemo(() => (supplierId ? basicRate.filter(b => b.supplierId === supplierId) : []), [basicRate, supplierId])
```
to branch on `itemSource`:
```ts
const basicRateForSupplier = useMemo(() => {
  if (itemSource === 'unlinked') return basicRate.filter(b => !b.supplierId)
  return supplierId ? basicRate.filter(b => b.supplierId === supplierId) : []
}, [basicRate, supplierId, itemSource])
```
Everything downstream (`basicRateByCat`, `selectedBasicItem`, `catalogLineTotal`,
`canAddCatalogItem`, `addCatalogItem`) reads through this unchanged — no other logic needs to
know which mode produced the list.

### 3. UI — the filter toggle

In the catalog section (`client.tsx:2612-2624`, inside `itemMode === 'catalog' &&
catalogAvailable`), add a small toggle above the category `<select>`, same visual style as the
existing "From Basic Rate / Custom text" toggle at `client.tsx:2597-2610` (two pill buttons,
`aria-pressed`):
```
[ This supplier's items ]  [ Unlinked items ]
```
Only show this toggle when `itemMode === 'catalog'` (same guard the section already has) — it's
irrelevant in text mode. Keep the existing `catalogAvailable` gate exactly as it is: you still
need a real vendor selected before the catalog section appears at all — "Unlinked items" is a
filter *within* that section, not a way to skip picking a vendor. The expense is still always
logged against whatever real Supplier/Sub-Contractor was chosen up top, regardless of which
item-source filter was used to find the line item.

### 4. Empty-state message

Update the empty-state text (`client.tsx:2620-2623`, currently *"No Basic Rate items are linked
to this supplier yet..."*) to branch on `itemSource`:
- `'supplier'` (existing): *"No Basic Rate items are linked to this supplier yet — use Custom
  text below, or link some from the Basic Price/Rate pages first."*
- `'unlinked'` (new): *"No unlinked Basic Rate items in this project — every item already has a
  supplier, or use Custom text below."*

## Verification

1. Pick a supplier with zero linked items, confirm the default "This supplier's items" view
   shows the existing empty state (unchanged behavior).
2. Switch to "Unlinked items," confirm it shows every Basic Rate item in the project with no
   `supplierId` set, across all categories (respecting the category filter same as before).
3. Add one of those unlinked items as a line item, save the expense, and confirm it saved
   correctly against the real vendor picked up top — not against "no vendor."
4. Switch the vendor (Supplier dropdown) after having "Unlinked items" selected — confirm
   `itemSource` resets back to `'supplier'` rather than silently staying on "unlinked" for the
   newly picked vendor.

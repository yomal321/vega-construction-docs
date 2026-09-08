# Fix: replace the "This supplier's items / Unlinked items" toggle with one grouped dropdown

## Problem

`ExpenseModal` (`src/app/projects/[id]/client.tsx`) currently has a two-button toggle
(`itemSource`, `'supplier' | 'unlinked'`, lines ~2632-2643) that switches the item picker
between two entirely separate lists: items linked to the currently-picked supplier, or items
with no supplier at all. This works, but it's one extra control sitting right next to the
Supplier field above it, and user feedback is that it reads as redundant/confusing — two
things about "supplier" stacked on top of each other.

**Showing the full unfiltered catalog instead (no grouping at all) was considered and
rejected** — the client specifically wants the item list kept short/filtered, not a flat list
of every Basic Rate item in the project, so removing filtering entirely isn't an option here.

## Solution

Keep the filtering (so the list stays short), but present both relevant groups **inside one
single dropdown** instead of a separate toggle — using native `<optgroup>` sections. Open the
one item `<select>` and both "this supplier's items" and "unlinked items" are already right
there, labeled, in one list — no extra control to interact with first.

### 1. Remove the toggle

Delete the `itemSource` state (`client.tsx:2398`) and its two-button toggle UI
(`client.tsx:2632-2643`) entirely — this is being replaced, not kept alongside the new dropdown.
Also remove the resets of `itemSource` added in `handleVendorKindChange` (line 2429) and
`setVendorId` (line 2434), since there's no longer a mode to reset.

### 2. Compute two lists instead of one

Replace `basicRateForSupplier` (`client.tsx:2475-2478`) with two separate, always-computed
lists:
```ts
const supplierItems = useMemo(() => (supplierId ? basicRate.filter(b => b.supplierId === supplierId) : []), [basicRate, supplierId])
const unlinkedItems = useMemo(() => basicRate.filter(b => !b.supplierId), [basicRate])
```
Then filter each by the existing category selector (`itemCat`) the same way `basicRateByCat`
already does today:
```ts
const supplierItemsByCat = useMemo(() => (itemCat ? supplierItems.filter(b => b.cat === itemCat) : supplierItems), [supplierItems, itemCat])
const unlinkedItemsByCat = useMemo(() => (itemCat ? unlinkedItems.filter(b => b.cat === itemCat) : unlinkedItems), [unlinkedItems, itemCat])
```
For the existing lookups that need to search across both (`selectedBasicItem`,
`canAddCatalogItem`, `addCatalogItem`), combine them:
```ts
const selectedBasicItem = [...supplierItemsByCat, ...unlinkedItemsByCat].find(b => b.code === itemCode)
```
Everything else downstream (`itemQtyNum`, `catalogLineTotal`, `canAddCatalogItem`,
`addCatalogItem`) stays as-is — they already just read `selectedBasicItem`, unaffected by this
change.

### 3. Render one dropdown with two `<optgroup>`s

Replace the item `<select>` (`client.tsx:2665-2668`) with:
```tsx
<select className={`${inputCls} sm:flex-1 sm:min-w-0`} value={itemCode} onChange={e => setItemCode(e.target.value)}>
  <option value="">Select a Basic Rate item…</option>
  {supplierItemsByCat.length > 0 && (
    <optgroup label="This supplier's items">
      {supplierItemsByCat.map(b => <option key={b.code} value={b.code}>{b.code} — {b.name} ({fmt(b.rate)}/{b.unit})</option>)}
    </optgroup>
  )}
  {unlinkedItemsByCat.length > 0 && (
    <optgroup label="Unlinked items">
      {unlinkedItemsByCat.map(b => <option key={b.code} value={b.code}>{b.code} — {b.name} ({fmt(b.rate)}/{b.unit})</option>)}
    </optgroup>
  )}
</select>
```
Only render an `<optgroup>` when it actually has items — an empty group heading with nothing
under it is just clutter.

### 4. Empty state

Update the "no items" message (currently branching on `itemSource`, `client.tsx:2650-2655`) to
check both lists together:
```tsx
{supplierItemsByCat.length === 0 && unlinkedItemsByCat.length === 0 ? (
  <div className="text-[0.8rem] text-slate-400 dark:text-slate-600 py-2">
    No linked or unlinked Basic Rate items to pick from yet — use Custom text below, or add some from the Basic Price/Rate pages first.
  </div>
) : (
  /* the <select> from step 3 */
)}
```

## Verification

1. Pick a supplier with some linked items and confirm the dropdown shows a "This supplier's
   items" group containing exactly those.
2. Confirm a second "Unlinked items" group appears in the same dropdown, listing every item
   with no supplier — both groups visible at once, no toggle needed.
3. Pick a supplier with zero linked items — confirm only the "Unlinked items" group appears
   (no empty "This supplier's items" heading with nothing under it).
4. Confirm the category filter still narrows both groups correctly.
5. Confirm selecting an item from either group still computes the correct line total and adds
   correctly, and that the expense still saves against the real vendor picked at the top of the
   form regardless of which group the item came from.

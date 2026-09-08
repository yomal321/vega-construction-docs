# Feature: "No supplier" count + filter on Basic Price/Basic Rate pages

## Problem

Since the Supplier link was added to `BasicPriceItem`/`BaseItem` (optional, nullable
`supplierId`), there's no way to see at a glance how many items still don't have a supplier
assigned, or to quickly filter down to just those — an admin doing data cleanup has to scroll
the whole table checking the Supplier column row by row.

## Solution

Add a count + toggle filter, same UX pattern already used on `src/app/basic-rate/page.tsx` for
its existing "Needs update" (`staleOnly`/`staleCount`) toggle (`basic-rate/page.tsx:88`,
`117`, `208-221`) — copy that exact visual style (pill button, count badge, conditionally
rendered only when the count is > 0) for a new "No supplier" toggle, added to **both**
`src/app/basic-rate/page.tsx` and `src/app/basic-price/page.tsx` (the global cross-project
pages — this is a reporting/cleanup aid, so it belongs on the pages that already show every
project's items in one place, not scoped to a single project's tab).

### 1. `src/app/basic-rate/page.tsx`

- Add `const [noSupplierOnly, setNoSupplierOnly] = useState(false)` near the existing
  `staleOnly` state (line 88).
- Add `const noSupplierCount = useMemo(() => basicRate.filter(b => !b.supplierId).length,
  [basicRate])`, mirroring `staleCount` (line 117).
- Add `!noSupplierOnly || !b.supplierId` as another `&&` condition inside the `filtered`
  useMemo (lines 119-126), alongside the existing `staleOnly` condition — same pattern, just a
  second independent toggle (both can be active at once: "stale AND no supplier" is a valid,
  meaningful combination, not mutually exclusive).
- Add `noSupplierOnly` to the `useEffect(() => { setPage(1) }, [filter, staleOnly, query])`
  dependency array (line 128) so paging resets when this filter changes too.
- Render a second toggle button right after the existing "Needs update" one (after line 221),
  same structure/style but its own accent color (don't reuse amber — pick something visually
  distinct, e.g. the slate/indigo tone already used for informational badges elsewhere in this
  app, since this isn't a "something's wrong" warning like stale rates are, just a neutral
  data-completeness filter):
  ```tsx
  {noSupplierCount > 0 && (
    <button
      onClick={() => setNoSupplierOnly(v => !v)}
      aria-pressed={noSupplierOnly}
      className={/* same structural pattern as the staleOnly button, different accent */}
    >
      No supplier <span className={/* count badge, same pattern */}>{noSupplierCount}</span>
    </button>
  )}
  ```

### 2. `src/app/basic-price/page.tsx`

This page doesn't have an existing toggle-pill row (only a search box) — add the same
count + toggle here too, following the structural pattern just added to `basic-rate/page.tsx`
for consistency between the two pages:
- `const [noSupplierOnly, setNoSupplierOnly] = useState(false)`
- `const noSupplierCount = useMemo(() => rows.filter(b => !b.supplierId).length, [rows])`
- Add the same condition into the `filtered` useMemo (lines 187-190) alongside the existing
  name-search filter.
- Add `noSupplierOnly` to the page-reset `useEffect` dependency array (line 192).
- Render the same toggle button near the search input, same visual treatment as the one added
  to `basic-rate/page.tsx` (keep both pages' version of this control visually identical, since
  they're the same feature applied to two parallel pages).

## Verification

1. On both pages, confirm the "No supplier" toggle only appears when at least one item actually
   has no supplier (same "don't show a dead control at 0" behavior the existing "Needs update"
   toggle already has).
2. Confirm the badge count matches the actual number of rows with an empty Supplier column.
3. Toggle it on — confirm the table narrows to exactly those rows, and the "X of Y items" counter
   (already shown near the filters, e.g. `basic-rate/page.tsx:222`) updates correctly.
4. On Basic Rate, confirm "No supplier" and "Needs update" can both be active simultaneously and
   correctly narrow to rows matching both conditions at once.
5. Assign a supplier to one of the filtered rows, confirm it drops out of the filtered view
   immediately and the count decrements.

# Feature: Dedicated detail page for Suppliers & Sub-Contractors (replacing inline accordion)

## Problem

`src/app/suppliers/page.tsx` currently expands a supplier's details **inline**, in place, as an
accordion row (`SupplierDrillDown`, toggled via `expandedId` state) when you click on it. This
works fine with a handful of rows, but doesn't scale: every additional supplier makes the list
taller, and the expanded content (linked Basic Price/Rate items + full payment history) is
already substantial — it's only going to grow. This is also the only list-like page in the app
that behaves this way; everywhere else (most notably `/projects` → `/projects/[id]`), clicking
an item in a list navigates to its own dedicated page instead of expanding in place.

Note: today the drill-down is Supplier-only (Sub-Contractor rows are plain rename/delete, no
expand) — but the "too many rows to expand inline" problem applies to both lists equally, so
the fix should cover both, not just Suppliers.

## Solution

Replace the inline accordion with real per-entity pages: `/suppliers/[id]` and
`/sub-contractors/[id]`. Clicking a row in the list navigates there, same as clicking a project
in `/projects` navigates to `/projects/[id]`.

### 1. Supplier detail page — `src/app/suppliers/[id]/page.tsx`

Move the existing `SupplierDrillDown` component's content (currently in
`src/app/suppliers/page.tsx:262-367`) out of the accordion row and onto its own full page. It
already fetches everything needed via the existing `GET /api/suppliers/[id]`
(`src/app/api/suppliers/[id]/route.ts`) — no API changes needed for this one, just relocate the
UI:
- Page header: breadcrumbs `Dashboard > Suppliers & Sub-Contractors > [supplier name]` (same
  `Header` component pattern used elsewhere, e.g. the Payments page), with rename/delete actions
  available here too (reuse the existing rename/delete modals' logic from the list page — either
  lift them into a shared location or duplicate the small amount of modal logic, whichever this
  codebase's existing convention favors for small shared dialogs).
- The "Supplies" section (linked Basic Price/Rate items) and "Payment history" section, moved
  as-is from `SupplierDrillDown` — full width now instead of the indented `pl-8 border-l-2`
  nested-in-accordion treatment, since it's no longer nested inside anything.

### 2. Sub-Contractor detail page — `src/app/sub-contractors/[id]/page.tsx`

New page, same shape as the Supplier one but **without** the "Supplies" section — Sub-Contractor
has no Basic Price/Rate link (per the existing schema comment: that relationship doesn't apply
to sub-contractors). Just the payment history section, same layout/columns as the Supplier
page's "Payment history" table.

This needs a **new API route**, since `src/app/api/sub-contractors/[id]/route.ts` currently only
has `PATCH`/`DELETE`, no `GET`. Add a `GET` handler mirroring `GET /api/suppliers/[id]`
(`src/app/api/suppliers/[id]/route.ts:24-89`) closely, but:
- Look up from `sub_contractors` instead of `suppliers`.
- Only the expenses query, filtered on `e.subContractorId = ?` instead of `e.supplierId = ?` —
  drop the `basicPriceItems`/`baseItems` queries entirely, don't just return them empty.
- Same `projectAccessClause` visibility rule, same response shape minus the two item arrays.

### 3. Update the list page — `src/app/suppliers/page.tsx`

In `EntityList` (`src/app/suppliers/page.tsx:97-255`):
- Remove `expandedId` state, the `ChevronDown` toggle, `aria-expanded`, and the
  `{expanded && <SupplierDrillDown .../>}` row entirely.
- Change each row's `onClick` (Supplier only, currently line 176-179) to navigate instead of
  toggle — wrap the row (or just the name cell) in a `Link` to `/suppliers/${item.id}` for
  Supplier rows, `/sub-contractors/${item.id}` for Sub-Contractor rows. Since Sub-Contractor
  rows didn't have a click handler before at all, this is a new behavior for that tab, not just
  a change to the existing one.
- Keep the rename (pencil) and delete (trash) icon buttons in the row exactly as they are now —
  these are quick actions that don't need a full page visit, same reasoning the Projects list
  presumably has for whatever quick actions it keeps inline vs. what it pushes to the detail
  page. Keep their `stopPropagation()` calls so clicking them doesn't also trigger the row's
  navigation.
- Delete the now-unused `SupplierDrillDown` function and its associated types/imports
  (`PackageSearch` icon, `draftStatusConfig`, etc.) from this file once its content has moved to
  the new page — don't leave dead code behind.

## Suggested implementation order

1. New `GET /api/sub-contractors/[id]` route (mirroring the Supplier one, minus the item queries).
2. New `/suppliers/[id]` page (move `SupplierDrillDown`'s content there) and new
   `/sub-contractors/[id]` page (payment history only).
3. Update the list page: remove the accordion, wire up navigation, keep inline rename/delete.
4. Manual verification: click a supplier in the list — confirm it navigates to its own page
   showing both supplies and payment history, and that rename/delete still work from the list
   without needing to open the detail page. Click a sub-contractor — confirm it navigates to its
   own page showing payment history only (no "Supplies" section at all, not an empty one).
   Confirm a supplier/sub-contractor with zero linked expenses still renders a sensible empty
   state on its own page rather than erroring.

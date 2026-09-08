# Feature: Summary dashboard strip on the Payments page

## Problem

`src/app/payments/page.tsx` (Enhancement #5) shows two tabbed tables — Suppliers and
Sub-Contractors — each with per-vendor owed/paid/outstanding and a "Most paid" badge on the
top row within that bucket. There's no at-a-glance summary above the tables: an admin has to
open both tabs and mentally add things up to answer "how much do we owe right now overall" or
"who do I need to pay next."

## Solution

Add a small summary strip at the top of the page, above the Suppliers/Sub-Contractors tabs,
using the same `KPICard` component already used on the project detail page
(`src/components/KPICard.tsx`) for visual consistency. **No backend/API changes are needed** —
`GET /api/payments` already returns every vendor in both buckets with `owed`/`paid`/
`outstanding` per vendor (see the existing `PaymentsSummary`/`VendorGroup` types already
defined in `src/app/payments/page.tsx`), so every number below is computed client-side from
data already being fetched.

### Cards to add (in this order)

1. **Total Outstanding** — sum of `outstanding` across every vendor in both `suppliers` and
   `subContractors` combined. This is the headline "how much do we still owe, overall" figure —
   give it the most prominent placement (leftmost, or largest if cards vary in size). Use the
   `rose` accent (matches how outstanding/unpaid amounts are colored red elsewhere in this app,
   e.g. the Expenses tab's Outstanding column).
2. **Total Paid (to date)** — sum of `paid` across every vendor in both buckets combined. `teal`
   accent (matches the "paid" color used elsewhere, e.g. the emerald/teal paid figures on the
   Expenses tab).
3. **Fully Settled Count** — count vendors (combined across both buckets) whose `outstanding`
   is 0 (or effectively 0 — guard against floating-point residue, e.g. `Math.abs(outstanding) <
   0.01`), shown as `"${settled} of ${total} fully paid"`. Use `sub` for the fraction if `value`
   is just the count, or put the whole "X of Y" string directly in `value` — whichever reads
   better against this card's neighbors.

Then a second row (or a visually distinct "Highlights" section) with three named highlights —
these show a vendor name as the card's `value`, not a plain number, so they read differently
from the three numeric cards above:

4. **Top Paid Vendor** — a single combined highlight (not split per bucket): compare the
   top-of-list vendor from `suppliers` and from `subContractors` (both arrays are already
   sorted descending by `paid` — see the existing `toSorted` logic in
   `src/app/api/payments/route.ts`) and show whichever of the two has the higher `paid` value
   overall. `value` = vendor name, `sub` = paid amount + which bucket they're in (e.g. "LKR
   450,000 · Supplier"). Handle the case where both buckets are empty (no vendors at all yet).
5. **Top Outstanding Supplier** — the supplier (not sub-contractor) with the highest
   `outstanding` value, found by scanning the `suppliers` array (it's sorted by `paid`, not
   `outstanding`, so this needs its own max-by-outstanding pass, not just `[0]`). `value` =
   vendor name, `sub` = outstanding amount. Show a clear empty state ("No suppliers yet" or
   similar) if the bucket is empty or every supplier has zero outstanding.
6. **Top Outstanding Sub-Contractor** — same as #5, scanning `subContractors` instead.

**Why Top Outstanding is split by bucket but Top Paid is combined:** an unpaid sub-contractor
carries real operational risk (can stall work on-site), while an unpaid supplier is more of a
relationship/credit concern — an admin needs to know both specifically, not just whichever has
the bigger number. "Top Paid," by contrast, is more of a relationship/reporting figure where one
combined answer is what's actually useful, not a split one. Keep this distinction — don't split
Top Paid into two cards to "match" the outstanding ones, and don't combine the outstanding ones
into one to save space.

## Placement

Insert this strip in `src/app/payments/page.tsx` between the page's intro paragraph
(around line 56) and the existing tab bar (`role="tablist"`, around line 58) — same position
the project detail page's KPI row occupies relative to its own tab bar, for a consistent layout
language across the app.

## Suggested implementation order

1. Compute the six values from the existing `data` (`PaymentsSummary`) already fetched via
   `useSWR('/api/payments', fetcher)` — no new fetch, no backend change.
2. Render the three numeric cards (Total Outstanding, Total Paid, Fully Settled Count) as a
   `KPICard` row.
3. Render the three named-highlight cards (Top Paid Vendor, Top Outstanding Supplier, Top
   Outstanding Sub-Contractor), each handling its own empty-state case gracefully (no vendors
   yet, or nobody outstanding).
4. Manual verification: with a mix of suppliers and sub-contractors at varying paid/outstanding
   levels, confirm each of the six cards matches a manual sum/max computed by eye against the
   underlying table data. Empty the corpus down to zero vendors in one bucket (e.g. delete all
   sub-contractor expenses in a test project) and confirm that bucket's "Top Outstanding"
   highlight shows a sensible empty state rather than crashing or showing blank/NaN.

# Feature: Payment Summary for Suppliers & Sub-Contractors (Enhancement #5)

## Problem

Expenses are logged one at a time, per project, each with a free-text `vendor` name and a
`category` (Material/Labour/SubContractor/Machinery/Transport/Other). Since Enhancement #4,
each expense can also have multiple `expense_payments` recorded against it (partial or full).
But there is nowhere in the app to see totals **grouped by vendor** — how much a given
supplier or sub-contractor has been paid and is still owed, across all of their expenses, in
all of the projects they're linked to. Answering that today would mean manually scanning every
project's Expenses tab by hand.

The business requirement (client-approved enhancement, BISTEC Global delivery doc): a new
Payment Summary view that lets the user record payments to a specific supplier or
sub-contractor, shows outstanding balance per supplier/sub-contractor, and highlights whoever
has been paid the most to date.

## Solution

This is a **standalone page**, not a project tab — reasoning: BSR/Stages/Expenses are project
tabs because that data only means something inside one project, but a vendor (e.g. "Cement
Suppliers Ltd") can supply many projects at once, so "who's been paid the most" only makes
sense computed across every project, not one at a time. This is the same reasoning behind the
existing global `/basic-price` and `/basic-rate` pages (see `src/app/api/basic-price/route.ts`
for the exact pattern this should copy) — those exist specifically because some things need a
portfolio-wide view on top of their per-project scoping.

**No new payment-recording mechanism is needed.** This page is a different *view* over data
that already exists (`expenses` + `expense_payments`, built for Enhancement #4) — grouped by
vendor instead of by expense. Recording a payment from this page still ultimately targets one
specific expense and calls the exact same endpoint already built:
`POST /api/projects/[id]/expenses/[expenseId]/payments`.

### 1. Two sections: Suppliers vs. Sub-Contractors

The page has two groups, not one flat vendor list — matching the enhancement's own title
("Suppliers **&** Sub-Contractors"). Split using the existing `Expense.category` field
(already in `prisma/schema.prisma`, `ExpenseCategory` enum: Material/Labour/SubContractor/
Machinery/Transport/Other) — no schema change needed for this split:

- **Sub-Contractor bucket** — any expense where `category = SubContractor`.
- **Supplier bucket** — every other category (Material, Labour, Machinery, Transport, Other).

Confirmed design decision: since `category` lives on the *expense*, not the vendor, the same
vendor name could appear in both buckets if they have expenses logged under different
categories (e.g. "Vega Suppliers Ltd" once as Material, once as SubContractor) — that's
intentional, not a bug. Each bucket only counts the expenses that fall in its own category; a
vendor's totals in the Supplier bucket and Sub-Contractor bucket are separate and don't merge.

### 2. Vendor grouping — flag this assumption explicitly

`vendor` is free-typed text per expense with no dedicated Vendor/Supplier table, so grouping
must match names loosely rather than by a foreign key. **Assumption for v1 (confirm before
relying on it for real reporting): group by `lower(trim(vendor))`** — so "Cement Suppliers
Ltd" and "cement suppliers ltd " are treated as the same vendor, but no further fuzzy matching
(e.g. "Cement Suppliers" vs "Cement Suppliers Ltd" would still be treated as different vendors).
Display the most-recently-used exact casing/spelling as that group's display name. If the
client's real vendor-name entry turns out to be inconsistent enough that this undercounts/
overcounts, the longer-term fix is a real Supplier entity selected from a dropdown on the
expense form instead of free text — out of scope for this pass, but leave a comment noting
this is a known limitation so it isn't mistaken for a bug later.

### 3. Data / API

New route: `GET /api/payments` (or `/api/payments-summary` — match whichever naming reads more
consistently next to the existing `/api/basic-price`, `/api/basic-rate` global routes).

Follow `src/app/api/basic-price/route.ts` exactly for the access pattern: `requirePermission
('projects', 'view')`, then a single query using `projectAccessClause(session, 'p.id',
'p.ownerId')` so results are naturally restricted to projects the caller can see (Admin sees
everyone's, Staff see only projects they own or are an assigned `ProjectMember` on — see
`src/lib/rbac.ts`), same as every other global list in this app.

Query shape: join `expenses` to `expense_payments` (left join, since a vendor may have no
payments yet) and to `projects` (for `projectAccessClause` + to tag each expense with its
project name, same as the global Basic Price page tags each row with `projectName`), group by
`lower(trim(vendor))` and by whether `category = SubContractor`, aggregating
`sum(expenses.amount)` as owed and `sum(expense_payments.amount)` as paid per group. Return
both bucket lists (supplier and sub-contractor), each entry containing: display vendor name,
total owed, total paid, outstanding (owed − paid), and the list of underlying expenses (id,
projectId, projectName, amount, paid, outstanding) so the UI can drill down without a second
round-trip per vendor.

Compute "paid the most" as the max of `paid` within each bucket, on the client or in the API
response — don't store it, recompute live same as `outstanding` elsewhere in this app.

### 4. UI

New page `src/app/payments/page.tsx`. Add a sidebar entry in `src/components/Sidebar.tsx`
(`NAV_ITEMS` array) — copy the existing Basic Price/Basic Rate entries' shape exactly:
`{ href: '/payments', icon: <pick an appropriate lucide icon, e.g. HandCoins>, label:
'Payments', module: 'projects' }`, placed near Basic Price/Basic Rate in the nav order since
they're the same kind of portfolio-wide page.

Layout:
- Two tabs or two stacked sections: "Suppliers" and "Sub-Contractors" (match whichever tab
  pattern this app already uses elsewhere — check `client.tsx`'s project detail tabs for the
  existing tab-switching convention to copy).
- Each section is a table: vendor name, total owed, total paid, outstanding, with the
  highest-paid vendor in that section visually flagged (a badge, same styling language as
  other status badges in this app via the existing `Badge` component).
- Clicking a vendor row expands/drills into their linked expenses — each shown with its own
  project name (tag, same as the global Basic Price page's project tag per row), amount, paid,
  outstanding, and a "Record payment" action reusing the same `PaymentsModal` component already
  built for Enhancement #4 in `src/app/projects/[id]/client.tsx` (extract it to a shared
  location if it isn't already reusable outside that file, since this page needs the identical
  modal/flow, just reached from a different entry point — it should still call the same
  `POST /api/projects/[id]/expenses/[expenseId]/payments` endpoint, just with `id` (projectId)
  and `expenseId` coming from the drill-down row instead of the project page's own state).

## Suggested implementation order

1. New `GET /api/payments` route — grouped/aggregated query as described above.
2. New `/payments` page + sidebar nav entry — two-section table view first, no drill-down yet.
3. Drill-down per vendor (expenses list) + reused payment-recording modal.
4. Manual verification: log expenses for the same vendor name (with different casing) across
   two different projects, some Material-category and some SubContractor-category. Confirm:
   they appear correctly split across the two buckets: confirm outstanding/paid totals are
   correct sums across both projects, confirm the "most paid" badge lands on the right vendor
   in each bucket, and confirm recording a payment from this page updates the same expense you'd
   see if you opened that project's own Expenses tab directly (same underlying data, no
   duplication).

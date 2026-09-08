# Feature: Partial/Full Payment Allocation for Expenses

## Problem

The Expense model (prisma/schema.prisma, model Expense) currently has a single `amount`
field and nothing else money-related. There is no way to record that an expense has been
paid partially rather than in full, and no outstanding-balance concept exists anywhere in
the schema, API, or UI. Today `amount` is implicitly treated as a done deal — logged once,
shown once, with no payment tracking after that.

The business requirement (client-approved enhancement, BISTEC Global delivery doc): when
adding an expense, the user must be able to allocate how much of it has actually been paid
— partial or full — and the system must automatically calculate and display the outstanding
balance remaining.

## Solution

Track payments as their own records against an expense, rather than a single "amountPaid"
field. This keeps a real history (multiple partial payments over time, each with its own
date/method) and — importantly — sets up the data shape that Enhancement #5 ("Payment
Summary for Suppliers & Sub-Contractors") will need anyway, since that feature is the same
payment data grouped by vendor instead of by expense. Build the shared foundation once here.

### 1. Data model

Add a new Prisma model, `ExpensePayment`:

```prisma
model ExpensePayment {
  id        String        @id @default(cuid())
  expenseId String
  expense   Expense       @relation(fields: [expenseId], references: [id], onDelete: Cascade)
  amount    Float
  date      DateTime
  method    PaymentMethod
  recordedById String
  recordedBy   User       @relation(fields: [recordedById], references: [id])

  @@index([expenseId])
  @@map("expense_payments")
}
```

Add the reverse relation on `Expense` (`payments ExpensePayment[]`) and the reverse relation
on `User` (follow the existing named-relation pattern already used for things like
`BaseItem.updatedBy`/`BaseItem.owner` if `User` needs more than one relation added — check
whether `User` already has a generic reverse relation slot free before adding a new named one).

`Expense.amount` keeps its current meaning: the total amount owed for that expense (what the
BRD/Excel calls the invoice/bill total). It does NOT change. "Paid so far" = sum of that
expense's `ExpensePayment.amount` rows. "Outstanding" = `Expense.amount - sum(payments)`,
computed on read — do not store it as a column, it would drift out of sync with the payments
table (same drift class of problem the codebase already avoids elsewhere — derived numbers
are computed, not cached, per the existing `activityItemRate`/`floorMultiplier` pattern in
src/lib/derive.ts).

`PaymentMethod` (Cash/Bank/Online) moves conceptually to being a property of each payment,
not of the expense as a whole — a single expense can now be settled across multiple methods
(e.g. half by cash, half by bank transfer later). Leave `Expense.method` in the schema as-is
for now (don't break existing reads) but stop treating it as authoritative once payments
exist for an expense — the UI should source "how was this paid" from the payments list, not
the legacy `method` column, whenever at least one payment record exists.

Write the D1 migration by hand under migrations/ (this project applies migrations manually —
check the most recent file under migrations/ for the exact SQL header-comment and
CREATE TABLE style to copy).

**Backfill decision — flag this, don't just pick one silently:** every existing `expenses` row
predates this feature and has no payment records yet, so by the new logic every existing
expense would suddenly show as 100% outstanding, which is almost certainly wrong — expense
tracking in this app has always been "money already spent" (see doc/GAP_ANALYSIS.md, gap #4),
so existing rows most likely represent fully-paid expenses already. The safest default is to
backfill one `ExpensePayment` per existing `expenses` row, dated to that expense's own `date`,
amount equal to the full `amount`, method copied from the existing `method` column, so nothing
already-logged suddenly appears unpaid. Add this as a migration comment explicitly flagging it
needs client confirmation before running against real deployed data — same pattern as the
comment already in migrations/0012_project_scoped_catalog.sql for its own backfill assumption.

### 2. API routes

Follow the existing nested-resource convention (see
src/app/api/projects/[id]/expenses/[expenseId]/route.ts for the PATCH/DELETE style, and
src/app/api/projects/[id]/items/[itemId]/recipe/[componentId]/route.ts for how this codebase
nests a third level under a resource):

- `GET /api/projects/[id]/expenses/[expenseId]/payments` — list payments for one expense,
  ordered by date. requirePermission('projects','view') + requireProjectAccess, matching the
  parent route's gating exactly.
- `POST /api/projects/[id]/expenses/[expenseId]/payments` — body `{ amount, date, method }`.
  requirePermission('projects','create') (or 'edit' — match whichever permission the parent
  expense PATCH route already uses for modifying an expense's financial state). Reject with
  400 if the new payment would push total paid above the expense's `amount` (sum existing
  payments + new amount > expense.amount).
- `DELETE /api/projects/[id]/expenses/[expenseId]/payments/[paymentId]` — requirePermission
  ('projects','delete') + requireProjectAccess. Removing a payment record is a correction (e.g.
  logged in error) — no special audit constraint here since payments aren't price/rate history,
  but keep it simple and match the existing expense DELETE route's shape.

Also update `GET /api/projects/[id]/expenses` (the list route) to include each expense's
`paid` (sum of its payments) and `outstanding` (`amount - paid`) in the response, computed with
a single query (`left join` + `group by`, or a correlated subquery) rather than N+1 queries per
row — this list can have many rows per project.

### 3. UI changes

In `src/app/projects/[id]/client.tsx`:

- `ExpensesTab`'s table (around line 1846-1880): add two columns, "Paid" and "Outstanding",
  next to the existing "Amount" column. Style outstanding > 0 distinctly (e.g. the same
  rose/red tone already used for "Total expenses" in the table footer) so a partially-paid or
  unpaid expense visually stands out in the list, matching the existing red-highlight language
  used elsewhere in this app for "needs attention" states (see `itemHasStaleRecipe`'s flag
  styling on BSR rows for the visual precedent to copy).
- Add a "Record payment" action per row (icon button, same placement/style as other per-row
  actions in this codebase) opening a small modal: amount, date, method — same `Modal` +
  `Field` component pattern the rest of the app already uses (see `ExpenseModal` in the same
  file for the exact form-field conventions to copy). On save, POST to the new payments route
  and refresh the expenses list (SWR `mutate`, matching how other mutations in this file
  already refresh their lists).
- Where an expense currently shows a single flat "Amount," reframe the label context so it's
  clear that's the total owed, with paid/outstanding alongside it — don't just replace `amount`
  with `outstanding` in place, since both numbers matter and the client asked for both to be
  visible ("automatically calculate and display the outstanding balance").
- No changes needed to `ExpenseModal` itself (the add/edit-expense form) — that continues to
  set the total `amount` owed at creation time, same as today. Payments are a separate,
  subsequent action.

## Suggested implementation order

1. Prisma schema change (`ExpensePayment` model + `Expense.payments` relation) + hand-written
   D1 migration, including the flagged backfill of one payment per existing expense.
2. New nested payments API routes (GET/POST/DELETE), plus the paid/outstanding aggregation
   added to the existing expenses list route.
3. UI: Paid/Outstanding columns + status highlighting in `ExpensesTab`, "Record payment" modal
   and action per row.
4. Manual verification: log a new expense for LKR 100,000, record a payment of LKR 40,000,
   confirm the row shows Paid 40,000 / Outstanding 60,000. Record a second payment of 60,000,
   confirm outstanding drops to 0 and the row's status reads as fully paid. Attempt a payment
   that would overpay the expense and confirm it's rejected. Confirm an existing (pre-migration)
   expense shows as fully paid via its backfilled payment record, not as 100% outstanding.

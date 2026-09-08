# Fix: Project ROI and the Expenses card should be driven by paid amounts, not logged amounts

## Problem

`GET /api/projects/[id]/route.ts:27-29` computes `expenseTotal` as a flat
`sum(amount)` across every expense in the project — this counts the full amount the moment an
expense is logged, regardless of whether anything has actually been paid against it (partial or
full payments are tracked per-expense since Enhancement #4, `expense_payments`).

`src/app/projects/[id]/client.tsx:165-167` then computes:
```
const roi = income.received - expenseTotal
const roiPct = expenseTotal > 0 ? (roi / expenseTotal) * 100 : 0
```
So "Project ROI" compares actual cash **received** from the client against the full **logged/
committed** expense total — not against what's actually been **paid out**. Logging a large
unpaid expense makes ROI immediately look much worse, even though no cash has actually left the
business yet for that expense. This is a real, user-reported discrepancy (screenshot showed a
project with LKR 5,588,031 "logged to date" driving a -3,098,031 ROI, most of it still unpaid).

## Solution

Keep both numbers, but use the right one for each purpose:
- **Committed/logged total** (today's `sum(amount)`) — still useful, shows total liability/
  what's been committed to spending, regardless of payment status.
- **Paid total** (new — `sum` of `expense_payments.amount` across the project's expenses) —
  the actual cash that's left the business. This is what "Project ROI" should be measured
  against, since ROI is a cash-basis figure (`received` is already cash actually collected from
  the client, so the expense side of the comparison should be cash actually paid out too, not a
  mix of paid + merely-logged).

### 1. API — `src/app/api/projects/[id]/route.ts`

Currently (line 27):
```ts
const { results: expenseRows } = await db.prepare('select coalesce(sum(amount), 0) as total from expenses where projectId = ?').bind(id).all<{ total: number }>()
```

Change to also compute the paid total in the same round trip, via a left join to
`expense_payments` (same join pattern already used in
`src/app/api/projects/[id]/expenses/route.ts` for the per-expense `paid` column):
```ts
const { results: expenseRows } = await db
  .prepare(
    `select coalesce(sum(e.amount), 0) as committed, coalesce(sum(pay.amount), 0) as paid
     from expenses e left join expense_payments pay on pay.expenseId = e.id
     where e.projectId = ?`
  )
  .bind(id)
  .all<{ committed: number; paid: number }>()
```

And in the JSON response (line 42), replace the single `expenseTotal` with both figures:
```ts
expenseCommitted: expenseRows[0]?.committed ?? 0,
expensePaid: expenseRows[0]?.paid ?? 0,
```
(Rename the field so callers can't accidentally keep using the old ambiguous name — every
place currently reading `expenseTotal` needs to explicitly pick one of the two.)

### 2. UI — `src/app/projects/[id]/client.tsx`

- Update the `ProjectDetail` type (line 39) to match: replace `expenseTotal: number` with
  `expenseCommitted: number; expensePaid: number`.
- Replace the `expenseTotal`/`roi`/`roiPct` block (lines 165-167) with:
  ```ts
  const expenseCommitted = project.expenseCommitted
  const expensePaid = project.expensePaid
  const roi = income.received - expensePaid
  const roiPct = expensePaid > 0 ? (roi / expensePaid) * 100 : 0
  ```
- **Expenses KPI card** (line 334): keep the committed total as the headline number (it's the
  card literally labeled "Expenses" — that should stay "everything logged," since hiding total
  liability would be a step backward), but change its subtitle from the static `"Logged to
  date"` to show the paid figure alongside it, e.g. `sub={`Paid ${fmt0(expensePaid)} of
  ${fmt0(expenseCommitted)} committed`}` (adjust to whatever phrasing/format matches this card's
  existing subtitle conventions — check how the `trend` prop is used on the neighboring
  `Received`/`Outstanding` cards for the closest stylistic match, since this is more of a
  breakdown than a simple trend).
- **Project ROI KPI card** (line 340): update the `trend` label from `"${roiPct...}% on
  expense"` to something explicit that it's paid-basis now, e.g. `"${roiPct...}% on paid
  expense"` — small wording change, but worth it so it's clear this isn't the same denominator
  as before if anyone compares it against the old screenshot/report.

### 3. Anywhere else `expenseTotal` was read

Search the codebase for any other consumer of the old `expenseTotal` field (e.g. exports,
dashboard aggregates) and decide per-callsite whether it should become `expenseCommitted` or
`expensePaid` — don't default all of them to one or the other without checking what each one is
actually trying to represent (a liability report wants committed; a cash-flow/profitability
figure wants paid).

## Verification

1. Open a project with expenses that have zero payments recorded — confirm the "Expenses" card
   still shows the full committed amount (unchanged from today), but "Project ROI" now treats
   paid as 0 for that expense (so `received - paid-across-all-expenses`, not `received -
   committed-across-all-expenses`).
2. Record a partial payment on one of those expenses — confirm ROI moves by exactly the payment
   amount, not by the expense's full amount.
3. Fully pay off every expense in a project and confirm ROI then matches what it would have
   shown under the old logic (`received - sum(amount)`), since paid = committed once everything
   is settled — this is the sanity check that the two calculations converge correctly at 100%
   paid.

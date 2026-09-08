# Fix: orphaned child rows left behind on delete (project delete + expense delete)

## Problem

This codebase deletes dependent rows manually before deleting a parent row, because D1/SQLite
doesn't reliably enforce `ON DELETE CASCADE` unless the `foreign_keys` pragma is enabled on
the connection, which D1 doesn't guarantee — this is already stated explicitly in the comment
above the batch delete in `src/app/api/projects/[id]/route.ts`'s `DELETE` handler. That handler
manually deletes `recipe_components`, `bsr_lines`, `activity_items`, `milestones`, `stages`,
and `expenses` before deleting the `projects` row — but it was never updated as new
project-scoped child tables were added over time, and a newer route was never given the same
treatment at all. As a result, deleting things today leaves orphaned rows behind in several
tables — rows referencing a parent that no longer exists, invisible in the UI but still sitting
in the database.

Two separate gaps, same root cause:

1. **`DELETE /api/projects/[id]` (src/app/api/projects/[id]/route.ts)** — deletes `expenses`
   but not `expense_payments` (added in the Enhancement #4 migration, `0014_expense_payments.sql`)
   for those expenses. Also never deletes `project_members` (added in
   `0013_project_members.sql`), `base_items`, or `basic_price_items` (both added in
   `0012_project_scoped_catalog.sql`) — none of the last three per-project-scoped tables were
   ever added to this handler's manual-delete batch when they were introduced.

2. **`DELETE /api/projects/[id]/expenses/[expenseId]` (src/app/api/projects/[id]/expenses/[expenseId]/route.ts)**
   — deletes the `expenses` row directly with no cleanup of that expense's `expense_payments`
   rows at all. This route was not touched when Enhancement #4 was built, even though it now has
   a child table.

## Solution

Fix both routes so every dependent table is explicitly cleaned up before its parent is deleted,
matching the existing pattern already used in `projects/[id]/route.ts` (a single `db.batch([...])`
call, ordered so children are deleted before their parents, deepest first).

### 1. `src/app/api/projects/[id]/expenses/[expenseId]/route.ts` — `DELETE`

Currently:
```ts
await db.prepare('delete from expenses where id = ?').bind(expenseId).run()
```

Change to a `db.batch([...])` (or two sequential awaited deletes, matching whichever style is
already idiomatic for a two-statement delete elsewhere in this codebase) that deletes
`expense_payments` for this `expenseId` first, then the `expenses` row itself:
```ts
await db.batch([
  db.prepare('delete from expense_payments where expenseId = ?').bind(expenseId),
  db.prepare('delete from expenses where id = ?').bind(expenseId),
])
```

### 2. `src/app/api/projects/[id]/route.ts` — `DELETE`

Extend the existing `db.batch([...])` array. Keep the existing entries and their order
(children before parents), and add the following, inserted in FK-safe order (each of these is
independent of the others — order relative to each other doesn't matter, but all of them must
come before the final `delete from projects where id = ?`):

- `delete from expense_payments where expenseId in (select id from expenses where projectId = ?)`
  bound to the project id — must run before `delete from expenses where projectId = ?` (which
  already exists in the batch), since it depends on those expense rows still existing to look
  up their ids.
- `delete from project_members where projectId = ?`
- `delete from base_items where projectId = ?`
- `delete from basic_price_items where projectId = ?`

Note `base_items` also has its own child table, `price_history_entries` (added in the same
`0012_project_scoped_catalog.sql` migration, keyed by `baseItemId`) — add
`delete from price_history_entries where baseItemId in (select id from base_items where projectId = ?)`
before the `base_items` delete, for the same reason.

The full corrected batch order in `projects/[id]/route.ts`'s `DELETE` should read (children
before their parents, all before the final `projects` delete):

```
recipe_components (via activity_items)
bsr_lines
activity_items
milestones (via stages)
stages
expense_payments (via expenses)   <- new
expenses
project_members                    <- new
price_history_entries (via base_items)   <- new
base_items                          <- new
basic_price_items                   <- new
projects
```

### 3. Going forward

Leave a one-line comment at the top of this batch (or near it) noting: *"Every new
project-scoped or expense-scoped child table must be added here — D1 doesn't reliably enforce
cascade deletes, so this list is the only thing preventing orphaned rows."* This is the second
time this exact class of bug has been introduced by a new feature forgetting to extend this
list — worth making the maintenance burden explicit so a future table doesn't repeat it.

## Verification

1. Create a test expense with two payment records against it. Delete the expense directly.
   Query `expense_payments` for that (now-deleted) `expenseId` — should return zero rows, not
   the two orphaned ones.
2. Create a test project with at least one expense (with payments), one BSR item, one
   assigned `project_members` row, and at least one Basic Price/Basic Rate item with a price
   history entry. Delete the project. Query each of `expense_payments`, `project_members`,
   `base_items`, `basic_price_items`, and `price_history_entries` for rows referencing that
   project (or its now-deleted children) — all should return zero.
3. Confirm the existing delete-flow verification still passes (deleting a project with BSR
   items, stages, and expenses that have no payments/members/etc. still fully deletes as before
   — no regression on the already-working parts of this handler).

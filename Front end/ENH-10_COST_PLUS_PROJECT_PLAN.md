# ENH-10 — Cost Plus Project: Implementation Plan

**Date:** 2026-10-13
**Area:** Projects / Dashboard — Enhancement
**Status:** Built and verified locally (API smoke test 43/43, UI render check) — not yet applied to remote/shared DBs

---

## 1. Requirement (confirmed with stakeholder)

A **Cost Plus Project** is a separate kind of project. Vega spends the money, then bills the client
for **total expense + a margin %**.

It is completely separate from the existing (default) projects:

| | Default project (exists) | Cost Plus project (new) |
|---|---|---|
| Sidebar menu | Projects | **Cost Plus Projects** |
| BSR / Basic Price / Basic Rate | ✅ | ❌ |
| Stages / milestones (Advance, Interim, Final) | ✅ | ❌ |
| Expenses (money out) | ✅ | ✅ |
| Expense payments | Cash / Bank / Online | Cash / Bank / Online / **Cheque** (stage-style recorder with cheque lifecycle) |
| Client payments (money in) | per stage milestone | **against the whole project** (no stages), same recorder with cheque lifecycle |
| Margin % | ❌ | ✅ **per project only** (no global value) |
| Project dashboard | full | same style, **no ROI and no Outstanding cards** |
| Company summary | Main dashboard | **Separate summary on the Cost Plus list page** (main dashboard unchanged) |
| Permission | `projects` module | **new `costPlus` module** |

### Formula

```
Total Expense = sum of ALL logged expenses (paid or not)
Margin Amount = Total Expense × Margin % / 100
Total         = Total Expense + Margin Amount
```

The margin % and the calculated margin amount are **both stored in the DB**. Both are updated
whenever the margin % changes or any expense is added, edited or deleted.

### Cheque rule (same as stage payments today)
- **Received** (deposited): counts as *pending*, not as paid or received money yet
- **Cleared**: counts as paid or received
- **Bounced**: counts for nothing, the balance reopens, and the row stays as a record

---

## 2. Key design decision: separate tables, not a `type` flag

**Decision:** cost plus gets its **own tables**. The existing `projects` / `expenses` tables are not touched.

**Why:** about 25 existing files query `projects` or `expenses` directly: the main dashboard,
Payments page, Supplier/Sub-contractor detail, price comparison, notifications, basic-price/rate
lists, user-project access and others. A shared `type` flag would need a filter added to every one
of them, and a single missed filter would leak cost plus numbers into default-project screens.
Separate tables mean **zero changes to existing behaviour**.

**What is still reused (no duplication):**
- `src/lib/incomePayments.ts`: the `Ledger` helpers (`insertPaymentGuarded`, `updateChequeGuarded`,
  `listPayments`, `deletePayment`) are already table-parametric. Two new ledger constants are enough.
- `src/lib/derive.ts`: `paymentSettlement()` for the received / chequePending / outstanding maths.
- `src/components/PaymentsModal.tsx`: `PaymentLedgerModal`, which already supports Cheque and the inline status change.
- `Supplier` / `SubContractor` tables and pickers, plus the "Other payee" pattern.
- `src/lib/rbac.ts`: `requirePermission`, and the same owner/admin access pattern.

---

## 3. Database changes

New Prisma migration `prisma/migrations/20261014000000_cost_plus_projects/`.

### 3.1 `cost_plus_projects`
| Column | Type | Notes |
|---|---|---|
| id | text PK | `cpp_<uuid>` |
| name, client, location | text | required, max 120 chars (same as projects) |
| start | timestamp | |
| status | `ProjectStatus` | reuse existing enum, default `Active` |
| marginPct | float | default 0, validated 0–1000 |
| marginAmount | float | default 0, **stored**, recalculated by API |
| ownerId | FK users | creator |
| createdAt | timestamp | |

### 3.2 `cost_plus_expenses`
| Column | Type | Notes |
|---|---|---|
| id | text PK | |
| projectId | FK cost_plus_projects, cascade | |
| date | timestamp | |
| category | `ExpenseCategory` | reuse enum (Material/Labour/SubContractor/Machinery/Transport/Other) |
| description | text | what the money was for |
| amount | float | total owed, never changed by payments |
| supplierId / subContractorId | FK, nullable | same "exactly one, by category" rule as `expenses` |
| isOtherPayee + vendor | bool / text | typed payee name when neither |
| createdAt | timestamp | |

No `stage`, `boq` or line items. Cost plus has no BSR or catalog.

### 3.3 `cost_plus_expense_payments` (money out)
Same columns as `milestone_payments`, so the shared ledger SQL works unchanged:
`id, expenseId, amount, date, method (IncomeMethod: Cash/Bank/Online/Cheque), chequeStatus, chequeDate, recordedById`.

### 3.4 `cost_plus_client_payments` (money in)
Same shape: `id, projectId, amount, date, method, chequeStatus, chequeDate, recordedById`.

### 3.5 Ledger constants (in `incomePayments.ts`)
```ts
export const CP_EXPENSE_LEDGER: Ledger = { table: 'cost_plus_expense_payments', fk: 'expenseId', parentTable: 'cost_plus_expenses' }
export const CP_CLIENT_LEDGER:  Ledger = { table: 'cost_plus_client_payments',  fk: 'projectId', parentTable: 'cost_plus_projects' }
```

---

## 4. Permissions

Add to `PERMISSION_CATALOG` in `src/lib/rbac.ts`:
```ts
{ module: 'costPlus', label: 'Cost Plus Projects', actions: ['view', 'create', 'edit', 'delete'] }
```
- The Roles page matrix picks this up automatically, because it renders from the catalog.
- Access: **Admin sees all; Staff see only cost plus projects they own.** Add a small
  `requireCostPlusAccess(session, projectId)` next to `requireProjectAccess`.
- Assigning extra members to a cost plus project is **not in v1** (see §9).

---

## 5. API routes (`src/app/api/cost-plus/`)

**Flat, query-parameter endpoints.** There are no nested `[id]` path segments. Only **4 route files**:

```
src/app/api/cost-plus/route.ts
src/app/api/cost-plus/expenses/route.ts
src/app/api/cost-plus/expense-payments/route.ts
src/app/api/cost-plus/client-payments/route.ts
```

| Endpoint | Method | Query params | Purpose |
|---|---|---|---|
| `/api/cost-plus` | GET | — | List of reachable projects **+ summary totals** (list page) |
| `/api/cost-plus` | GET | `?id=` | One project + dashboard figures |
| `/api/cost-plus` | POST | — | Create project |
| `/api/cost-plus` | PATCH | `?id=` | Edit info and/or **margin %** (margin change → recalculates and stores `marginAmount`) |
| `/api/cost-plus` | DELETE | `?id=` | Delete project |
| `/api/cost-plus/expenses` | GET | `?projectId=` | List expenses |
| `/api/cost-plus/expenses` | POST | `?projectId=` | Add expense |
| `/api/cost-plus/expenses` | PATCH | `?expenseId=` | Edit expense |
| `/api/cost-plus/expenses` | DELETE | `?expenseId=` | Delete expense |
| `/api/cost-plus/expense-payments` | GET | `?expenseId=` | Payments to supplier |
| `/api/cost-plus/expense-payments` | POST | `?expenseId=` | Record payment (cap = expense amount) |
| `/api/cost-plus/expense-payments` | PATCH | `?expenseId=&paymentId=` | Change cheque status |
| `/api/cost-plus/expense-payments` | DELETE | `?expenseId=&paymentId=` | Remove payment |
| `/api/cost-plus/client-payments` | GET | `?projectId=` | Client payments |
| `/api/cost-plus/client-payments` | POST | `?projectId=` | Record payment (cap = project Total) |
| `/api/cost-plus/client-payments` | PATCH | `?projectId=&paymentId=` | Change cheque status |
| `/api/cost-plus/client-payments` | DELETE | `?projectId=&paymentId=` | Remove payment |

**Rules for every route**
1. `requirePermission('costPlus', view|create|edit|delete)` comes first.
2. Query params are validated with zod. A missing or blank param returns **400**, never a 500.
3. **Access is resolved from the database, never trusted from the URL.** When only `expenseId` is
   given, the route looks up its `projectId` and then runs `requireCostPlusAccess`. The payment
   delete/update SQL also matches `paymentId` **and** its parent id, so a payment id from
   another project or expense affects nothing (the same pattern as `deletePayment()` today).
4. An unknown id returns **404**.

### `PaymentLedgerModal` — one small change
Today the modal builds the single-payment URL as `` `${endpoint}/${paymentId}` ``. Add a fallback:
when `endpoint` already contains `?`, use `` `${endpoint}&paymentId=${paymentId}` `` instead.
Existing default-project callers keep the path style and are unaffected.

### Margin recalculation (one shared helper)
`recalcMargin(db, projectId)` in a new `src/lib/costPlus.ts`:
```sql
update cost_plus_projects
set marginAmount = round((select coalesce(sum(amount),0) from cost_plus_expenses where projectId = ?) * marginPct) / 100
where id = ?
```
This is called in the **same batch/transaction** as every expense insert, update and delete and every margin change,
so the stored value can never go out of date.

### Overpay guards
- Expense payment: cannot exceed the expense amount. This is `insertPaymentGuarded` as it is today.
- Client payment: cannot exceed the current Total (Expense + Margin).
- **Edge case:** if an expense is later deleted and the Total drops below what was already received,
  nothing is blocked or deleted. The dashboard shows *Received* greater than *Total*, and the user corrects it manually.

---

## 6. UI

### 6.1 Sidebar — `src/components/Sidebar.tsx`
New leaf below **Projects**: `{ href: '/cost-plus', icon: Calculator, label: 'Cost plus projects', module: 'costPlus' }`.
It is hidden when the user has no `costPlus:view`, which is the existing behaviour for every leaf.

### 6.2 List page — `src/app/cost-plus/page.tsx`
- **Summary cards (top):** Projects count · Total Expense · Total Margin · Total (Expense + Margin) · Received from client · Paid to suppliers
- **Table:** name, client, location, start, margin %, total expense, total, received, status
- **"New cost plus project"** button opens a modal (name, client, location, start date, margin % optional)

### 6.3 Project page — `src/app/cost-plus/[id]/page.tsx` + `client.tsx`
Three tabs:

**Dashboard**
- Cards: Total Expense · Margin % · Margin Amount · **Total** · Received from client · Cheques pending · Paid to suppliers
- **No ROI card. No Outstanding card.**
- **Margin editor:** % input + Save. It shows `Total Expense × % = Margin Amount` live as the user types, then stores it.

**Expenses**
- Table: date, category, payee, description, amount, paid, status (pending/partial/paid)
- Add / edit / delete expense modal: date, category, supplier/sub-contractor/other payee, description, amount
- "Payments" action per row opens `PaymentLedgerModal` with
  `endpoint="/api/cost-plus/expense-payments?expenseId=<id>"` and methods `['Cash','Bank','Online','Cheque']`

**Client payments**
- Header: Total · Received · Cheques pending
- The `PaymentLedgerModal` list and record form, against the project Total
  (`endpoint="/api/cost-plus/client-payments?projectId=<id>"`)

Visual style matches the existing project detail page (KPICard, BentoCard, Modal, Select, DatePicker).

---

## 7. What is NOT changed

- Main dashboard (`/`, `/api/dashboard`). The cost plus summary lives on the Cost Plus page only.
- Existing Projects, Expenses, Payments page, Suppliers detail, Price comparison, Notifications.
- Existing `expenses` / `expense_payments` tables (default-project expenses stay Cash/Bank/Online).

---

## 8. Build order

| # | Step | Files |
|---|---|---|
| 1 | Prisma models + SQL migration, run on local `vega_qa` | `prisma/schema.prisma`, `prisma/migrations/…` |
| 2 | `costPlus` permission module + access helper | `src/lib/rbac.ts` |
| 3 | Ledger constants + `recalcMargin` + totals helper | `src/lib/incomePayments.ts`, `src/lib/costPlus.ts` |
| 4 | API routes (§5) — 4 flat route files, query-param based | `src/app/api/cost-plus/{route,expenses/route,expense-payments/route,client-payments/route}.ts` |
| 4b | `PaymentLedgerModal` query-string URL fallback | `src/components/PaymentsModal.tsx` |
| 5 | Sidebar entry | `src/components/Sidebar.tsx` |
| 6 | List page + summary + create modal | `src/app/cost-plus/page.tsx` |
| 7 | Project page: Dashboard / Expenses / Client payments tabs | `src/app/cost-plus/[id]/*` |
| 8 | Checks (§10), then manual QA on local `:3000` | |

---

## 9. Out of scope for v1 (add later if asked)

- Assigning other staff as members of a cost plus project (v1: owner + Admin only)
- Cost plus figures on the main dashboard, the company Payments page or the Supplier detail pages
- Excel/PDF export of a cost plus project
- Expense line-item breakdown and file attachments
- Converting a default project to cost plus or the reverse

---

## 10. Testing / acceptance

**Automated**
- `scripts/check-cost-plus.ts` (`npm run verify:cost-plus`): asserts the margin formula, rounding,
  recalculation after expense add/edit/delete, and cheque received/cleared/bounced counting.
- Playwright smoke: create cost plus project → add 2 expenses → set margin 15% → Total correct →
  record a client cheque → clear it → Received updates.

**Acceptance criteria (from ENH-10)**
- [ ] "Cost Plus Projects" appears in the side navigation (only with `costPlus:view`)
- [ ] User can create a project inside it
- [ ] User can add, edit and delete expenses on it, and pay them (including by cheque)
- [ ] User can enter a margin %; the margin amount is calculated, shown and stored
- [ ] Total = Expense + (Expense × Margin %) updates when expenses or the margin change
- [ ] Received and expenses display accurately on the cost plus project dashboard and the Cost Plus summary
- [ ] Project dashboard has no ROI and no Outstanding cards
- [ ] No BSR, Basic Price, Basic Rate or Stages appear anywhere for cost plus
- [ ] Existing default projects and the main dashboard are unchanged
- [ ] Staff without access cannot see or call another user's cost plus project (API returns 403/404)

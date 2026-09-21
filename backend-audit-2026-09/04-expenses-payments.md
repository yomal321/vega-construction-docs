# Backend Audit — Expenses & Payments

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `projects/[id]/expenses/route.ts` (GET, POST),
  `projects/[id]/expenses/[expenseId]/route.ts` (PATCH, DELETE — guard/SQL reviewed in
  `00-INDEX.md` S2/S3), `projects/[id]/expenses/[expenseId]/payments/route.ts` (GET, POST),
  `projects/[id]/expenses/[expenseId]/payments/[paymentId]/route.ts` (DELETE),
  `expenses/next-invoice/route.ts` (GET) — 5 files, all methods.
- **Verdict:** 🔴 **BLOCKER** — money/business-logic integrity is broken on the single most
  important write path in this family. Access control (auth/RBAC/IDOR) is clean; the
  concurrency-safety fix for the known payment TOCTOU issue is confirmed **holding**.

## Summary
Access control here is as solid as family 2 — every cross-project and zero-permission probe was
correctly rejected, and the previously-flagged payment race condition (`AUTHZ-VULN-03`) is
**confirmed fixed** under real concurrent load. But the money logic underneath it has no lower
bound anywhere: `POST .../expenses` accepts a negative `amount`, and `POST .../payments` accepts
a negative `amount` too — and the latter is far worse than a bad-looking number, because the
overpayment guard's own SQL (`sum(payments) + newAmount <= expense.amount`) treats a negative
payment as *reducing* the running total, which lets a caller repeatedly "pay" and "unpay" the same
expense past its total with no limit at all. This is `F-04-01` from the known cluster, confirmed
**still open** with a fresh, concrete repro against a route this audit tested directly — not
re-filed as new.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | No-cookie/no-Origin behavior consistent with family 1/2; not re-run exhaustively per route here (same shared gate). |
| B. RBAC & escalation | ✅ | Zero-perm Staff → 403 on payment write; guard-to-resource mapping mostly matches expectation, one item flagged as worth a human sanity-check (see Findings, `B-04-01`). |
| C. IDOR & project scoping | ✅ | Cross-project payment read AND write both → 403 `"Not your record"`, using the parent expense's own `projectId` looked up server-side before the access check — correct pattern, not trusting a client-supplied project id. |
| D. Injection & SQL layer | ✅ | No interpolation in any of these five files beyond what S3 already cleared. |
| E. Validation & mass assignment | 🔴 | **No lower bound on any money field in this family** — see `F-04-01` (confirmed still open) and `M-04-01` (new instance, same pattern, expense creation). |
| F. Business logic & money | 🔴 | Same as above — this **is** the business-logic failure for this family. |
| G. Integrity, transactions, concurrency | 🟢 | `AUTHZ-VULN-03` (payment TOCTOU) **confirmed fixed**, verified live under genuine concurrent load (see Evidence #7) — the single atomic `INSERT ... WHERE (running total) <= amount` correctly admits exactly one of two simultaneous conflicting payments. |
| H. Errors, disclosure | ✅ | 404s, 403s, and the overpay 400 all carry clean, non-leaking messages. |

## Per-route matrix
| Route | Method | Guard in source | No auth | Zero-perm Staff | Cross-project | Verdict |
|---|---|---|---|---|---|---|
| `.../expenses` | GET | `requirePermission('projects','view')` + `requireProjectAccess` | 401 (family 1/2 pattern, not re-run) | not re-run (payments POST covers the pattern) | not re-run here (see family 2 for the general proof; this route's own guard chain is identical) | ✅ |
| `.../expenses` | POST | `requirePermission('projects','create')` + `requireProjectAccess` | — | — | — | 🔴 accepts negative `amount` — `M-04-01` |
| `.../expenses/[expenseId]` | PATCH | `requirePermission('projects','edit')` (looks up `projectId` from the expense row itself first, then `requireProjectAccess` — correct: doesn't trust a client-supplied project id in the URL for this nested-under-nested route) | not re-run | not re-run | not re-run | not independently live-tested this session — schema allows the same unbounded `amount`; not re-confirmed live, tracked as the same class as `M-04-01`. |
| `.../expenses/[expenseId]` | DELETE | `requirePermission('projects','delete')` | not re-run | not re-run | not re-run | not independently live-tested |
| `.../payments` | GET | `requirePermission('projects','view')` + `requireProjectAccess` (via the expense's own projectId) | not re-run | not re-run | ✅ 403 `"Not your record"` | ✅ |
| `.../payments` | POST | `requirePermission('projects','edit')` + `requireProjectAccess` | not re-run | ✅ 403 | ✅ 403 | 🔴 accepts negative `amount`, defeats the overpay guard — `F-04-01` |
| `.../payments/[paymentId]` | DELETE | `requirePermission('projects','delete')` | not re-run | not re-run | not re-run | see `B-04-01` below — deliberately gated on `delete`, not `edit`; flagged for confirmation, not a confirmed bug |
| `expenses/next-invoice` | GET | `requirePermission('projects','create')` + `projectAccessClause` | not re-run | not re-run | not re-run | reads correctly from source; the `create` gate (rather than `view`) matches its purpose (invoice-numbering helper for the create-expense flow) |

## Findings

### F-04-01 (confirmed STILL OPEN, not new) — negative payment amount defeats the overpayment guard and corrupts the paid/outstanding ledger
- **Severity:** Critical
- **Confidence:** Confirmed, live, reproduced end-to-end
- **Class:** Business logic (money)
- **CWE:** CWE-1284 (Improper Validation of Specified Quantity in Input) / CWE-840 (Business Logic Errors)
- **Location:** `src/app/api/projects/[id]/expenses/[expenseId]/payments/route.ts:8-12`
  (`createPaymentSchema` — `amount: z.number(...)`, no `.positive()`/`.min()`) and the guard at
  line 54 (`... where (running total) + ? <= (select amount from expenses where id = ?)`), which
  is unconditionally defeated once the running total can go negative.
- **Request:**
  ```http
  POST /api/projects/sec-project-a/expenses/exp_0d2eed6a-c666-4cf4-858c-76fac3787d06/payments HTTP/1.1
  Origin: http://localhost:3006
  Cookie: vega_session=<sec-staff-a, holds projects:edit on their own project>
  Content-Type: application/json

  {"amount":-500,"date":"2026-08-02","method":"Bank"}
  ```
- **Response:** `200 {"id":"expp_...","amount":-500,...}` — accepted outright.
- **Expected:** `400`, same shape as the existing overpay rejection — a payment amount must be
  positive; a refund/correction is a business event this schema has no representation for and
  should not silently borrow "negative payment" to mean it.
- **Actual:** Accepted, and its effect compounds: on the same expense (`amount: 1000`), after the
  `-500` payment the tracked running total was `-500`. A subsequent legitimate `1000` payment then
  passed the guard (`-500 + 1000 = 500 <= 1000`) — correctly, in isolation — but left the *true*
  cash-received total at `500` while the expense APPEARED to have received `500` more room before
  triggering "overpaid," and a further `+1` payment was accepted too (`500 + 1 = 501 <= 1000`).
  **The guard never triggered at all for this expense during this test sequence, despite three
  payments having been recorded against a 1000-value expense that any reasonable accounting would
  call fully or over- settled.** An attacker (or a user who fat-fingers a negative sign, which the
  UI does nothing to prevent since this is enforced -- or rather, not enforced -- server-side) can
  repeat this indefinitely: record `-X`, then legitimately "unlock" `X` of further payment
  capacity on an expense that should have none, with no limit on how many times.
- **Impact:** Directly reproduces the documented `F-04-01` pattern ("negative payment understates
  paid expense, inflates ROI, defeats the over-allocation guard") — `dashboard/route.ts`'s
  company-wide `expensePaid` is `sum(expense_payments.amount)` with no lower bound either, so a
  single negative payment on any project immediately understates the company-wide paid total and
  correspondingly inflates `Overall ROI (paid basis)` shown on the dashboard. Any user holding
  `projects:edit` on even one project (not Admin-only) can do this — confirmed with `sec-staff-a`,
  a Staff account with a deliberately minimal role.
- **Suggested fix (describe only, not implementing):** add `.positive()` (or at minimum
  `.min(0.01)`) to `createPaymentSchema`'s `amount`; the same bound belongs on
  `patchExpenseSchema`'s `amount` and `createExpenseSchema`'s `amount` (see `M-04-01`) and, per
  the prompt's own instruction, on every other money-accepting field this audit will touch in
  later families (Basic Price/Rate, BSR, project `contract`).

### M-04-01 (new instance of the known money-sign cluster, not previously filed against this route) — expense creation accepts a negative `amount`
- **Severity:** High
- **Confidence:** Confirmed, live
- **Class:** Business logic (money)
- **CWE:** CWE-1284
- **Location:** `src/app/api/projects/[id]/expenses/route.ts:17-28` (`createExpenseSchema`,
  `amount: z.number(...)`, no lower bound).
- **Request:**
  ```http
  POST /api/projects/sec-project-a/expenses HTTP/1.1
  Origin: http://localhost:3006
  Cookie: vega_session=<Admin>
  Content-Type: application/json

  {"date":"2026-08-01","category":"Material","invoice":"AUDIT-NEG-EXP","stage":1,"method":"Bank","amount":-5000}
  ```
- **Response:** `200`, expense created with `amount: -5000`.
- **Expected:** `400` — an expense's total owed can't be negative; that's not a discount or a
  credit note, which this schema has no field for.
- **Impact:** A negative `expenses.amount` reduces `expenseCommitted` (company-wide and
  per-project) below its true value, and — combined with the `outstanding = amount - paid`
  formula used throughout — can drive `outstanding` for that one expense arbitrarily negative,
  which (per `F-03-03`'s already-documented pattern for `Project.contract`) propagates into any
  aggregate that sums it. Same root cause as `F-03-03`/`F-04-01`, different field, not previously
  named against this exact route — filed as its own id per the audit's own instruction to report
  a new instance of a known pattern rather than silently folding it in.
- **Suggested fix:** `.positive()` on `createExpenseSchema.amount`.

### B-04-01 (Info — flagged for confirmation, not a confirmed defect) — deleting a single payment requires `projects:delete`, the same permission that deletes an entire project
- **Severity:** Info
- **Confidence:** Unconfirmed as a defect (plausibly intentional)
- **Class:** Authorisation (guard-to-resource mapping)
- **Location:** `src/app/api/projects/[id]/expenses/[expenseId]/payments/[paymentId]/route.ts:7`
- Read in isolation, gating "remove one payment row" behind the same permission as "delete the
  entire project" looks like `S5`'s described blind spot (a guard checking a plausible-but-wrong
  action). It may equally be a deliberate choice: erasing a recorded payment permanently destroys
  financial history in a way editing a field doesn't, so treating it as tier with project deletion
  rather than with ordinary edits is a defensible design. Recorded here rather than silently
  passed over, per the audit's instruction to manually cross-check every guard against
  expectation — worth one line of confirmation with whoever owns the RBAC design, not a fix.

## Evidence log (live HTTP tests, this session)
1. `GET`/`POST .../payments` as `sec-staff-b` against `sec-staff-a`'s expense → `403 {"error":"Not
   your record"}` both.
2. `POST .../payments` as `csp-test-staff` (zero permission) → `403 {"error":"Missing permission:
   projects:edit"}`.
3. `POST .../payments {"amount":-500,...}` as `sec-staff-a` on their own `amount:1000` expense →
   `200`, accepted (`F-04-01`).
4. Same expense, `POST .../payments {"amount":1000,...}` → `200`, accepted (running total now
   `500` — correct per the broken math, i.e. the guard never sees the true `1000` owed).
5. Same expense again, `POST .../payments {"amount":1,...}` → `200`, still accepted (running total
   `501`) — the guard has not fired once across three payments against a fully-settleable
   1000-value expense.
6. Fresh clean `amount:100` expense, single `POST .../payments {"amount":0,...}` → `200`, accepted
   — zero-amount payments have no real integrity impact (a no-op on every total) but are
   nonetheless accepted with no validation; Low-value observation, not filed as its own finding.
7. **TOCTOU re-verification (`AUTHZ-VULN-03`), fresh clean `amount:100` expense, no prior
   payments:** two genuinely concurrent `POST .../payments {"amount":60,...}` requests (fired via
   backgrounded `curl` processes, not sequential) → one `200` (accepted), one `400` (`"This
   payment would overpay the expense..."`). Final state: exactly one `60`-amount payment row.
   **Confirmed fixed, holding under real concurrency.**
8. `POST .../expenses {"amount":-5000,...}` as Admin → `200`, accepted (`M-04-01`).

## Not tested this session
- `PATCH`/`DELETE .../expenses/[expenseId]` and `DELETE .../payments/[paymentId]` live (guard
  chains read correctly from source; not independently exercised over HTTP this session).
- Range checks on `stage` (expense's 1-based stage number) and `category`/`method` free-text
  coercion edge cases.
- `lineItems`-derived `amount` (`sum(lineItems.amount)` overriding the top-level `amount` when
  line items are present) — not tested with a negative line-item amount; worth checking whether
  the same `F-04-01` pattern reaches through that path too in a follow-up session.

# QA Audit — Project detail, all tabs (`/projects/[id]`)

- **Audited:** 2026-09-03
- **Build/commit:** `89395b8` (working tree modified only by audit artefacts)
- **Verdict:** PASS-WITH-NOTES
- **Playwright spec:** `vega-manager/tests/04-project-detail.spec.ts` — 11 tests, 9 passed, 2 failed (both failures are findings F-04-01 and F-04-02, working as intended)

## Summary

This is by far the largest surface in the application: **25 nested API routes** under
`/api/projects/[id]`, carrying the BSR, Stages & Payments, Expenses, Stage costs, Basic Price and
Basic Rate tabs. It is also where the money actually lives, so I weighted the audit toward the two
things that matter most here — cross-project write isolation on nested resources, and whether the
financial arithmetic is right — rather than clicking through every control.

**Both came back strong.** The CRITICAL milestone IDOR from the 2026-09-01 audit is genuinely
fixed and I confirmed it at runtime, not just by reading the patch. Every nested resource I probed
refused a cross-project write. The income maths reconciles exactly against figures I computed by
hand from the seed, including the non-obvious stage-rebalancing rule, and the payment
over-allocation guard survives a concurrent race.

Two findings, neither critical: a **negative payment amount is accepted**, which understates paid
expense and defeats the over-allocation guard; and on three route families the **project id in the
URL is never validated** against the resource it addresses.

## Coverage

| Test class | Status | Notes |
|---|---|---|
| A. Functional / Playwright | ⚠️ | API-level CRUD and maths covered thoroughly; per-tab UI interaction not exhaustively clicked (see Not tested) |
| B. Authentication & session | ✅ | Covered by page 1; all nested routes sit behind the same guard chain |
| C. Authorisation / RBAC / IDOR | ✅ | **Milestone IDOR regression-tested and refused**; 5 nested-resource probes as a scoped Staff user all refused |
| D. SQL injection & input handling | ⚠️ | All 25 routes use bound parameters; `createPaymentSchema` accepts a negative amount (F-04-01) |
| E. Headers / disclosure | ✅ | Inherits the app-wide set verified on page 1 |
| F. Data integrity & business rules | ⚠️ | Income, stage rebalancing, overflow guard, catalog isolation and price history all verified correct; negative payment corrupts `expensePaid` |

## Findings

### F-04-01 — A negative payment amount is accepted, understating paid expense and defeating the over-allocation guard
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Data integrity
- **Location:** `src/app/api/projects/[id]/expenses/[expenseId]/payments/route.ts:9` (`amount: z.number()` — no `.positive()`)
- **Reproduction:** Against a p1 expense of **LKR 987,000** with no payments recorded:
  1. `POST .../payments` with `amount: -500000` → **HTTP 200**, row created.
  2. `POST .../payments` with `amount: 987000` (the full expense) → **HTTP 200**, also accepted.
- **Expected:** Step 1 rejected with a 400 — a payment cannot be negative.
- **Actual:** Both accepted. The guard at `route.ts:43-46` compares `sum(paid) + amount > expense.amount`,
  and the negative row lowers `sum(paid)` enough to make room for the second payment.
- **Evidence:**
  ```
  POST amount:-500000  -> 200 {"id":"expp_b60220c4-...","amount":-500000,...}
  POST amount:987000   -> 200 {"id":"expp_92293704-...","amount":987000,...}

  select e.amount, sum(p.amount), count(*) ...
    expense_amount: 987000
    total_paid:     487000      <- two payment rows, books do not balance
    payment_rows:   2
  ```
- **Impact:** Two compounding effects, both on figures the business steers by:
  - `expensePaid` is understated, and **Overall ROI is computed as `received - expensePaid`**
    (`src/app/page.tsx:135`), so a negative payment **inflates reported ROI** by its full value.
    This stacks directly on F-02-01, which already overstates ROI whenever nothing is paid.
  - The over-allocation guard — the one control protecting payment integrity — can be walked past
    by interleaving negative rows, so an expense can accumulate payments beyond its own value.
  A negative payment also renders in the payment history as a nonsensical entry.
- **Suggested fix:** `amount: z.number().positive('Payment amount must be greater than zero')`.
  Consider the same on the expense `amount` schema. (Describe only — not implemented.)

### F-04-02 — The project id in the URL is not validated against the resource it addresses
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** Authorisation (defence-in-depth)
- **Location:** `src/app/api/projects/[id]/expenses/[expenseId]/route.ts:20,42`;
  `.../expenses/[expenseId]/payments/route.ts:20,38`; `.../bsr/[lineId]/route.ts:19,34`
- **Reproduction:** As an Admin (who can reach both projects),
  `PATCH /api/projects/**p1**/expenses/<an expense belonging to **p2**>`.
- **Expected:** `404` — that expense does not belong to p1.
- **Actual:** **HTTP 200**, and p2's expense was modified.
- **Evidence:**
  ```
  $ curl -X PATCH /api/projects/p1/expenses/cmtkh7ju5008but802nlh0wa6 -d '{"vendor":"URL-MISMATCH-PROBE"}'
  {"ok":true}  [HTTP 200]
  $ select projectId, vendor from expenses where id='cmtkh7ju5008but802nlh0wa6'
    projectId: p2        vendor: URL-MISMATCH-PROBE     <- p2's row, changed via a p1 URL
  ```
  (restored afterwards)
  These handlers look the row up by its own id, read *that row's* `projectId`, and call
  `requireProjectAccess` against it — so the `[id]` segment is decorative.
- **Impact:** **Not currently a privilege escalation, and I want to be precise about that:** the
  caller must still hold access to the resource's *real* project, so no data crosses a trust
  boundary today. The concern is structural. It is inconsistent with the sibling routes —
  milestones, stages, items, basic-price and basic-rate all constrain by parent (`where id = ? and
  projectId = ?`) — and it is precisely the shape the milestone IDOR had before it was fixed. If
  anyone later changes these handlers to authorise from the URL's `[id]` (the natural-looking
  refactor, and what `requireProjectAccess(session, projectId)` does everywhere else) while the
  write still keys on the row id, the CRITICAL bug returns. It also means any future audit log
  keyed on the URL would record the wrong project.
- **Suggested fix:** Constrain by parent like the sibling routes — `select ... where id = ? and
  projectId = ?`, 404 on miss. (Describe only.)

## Tested and clean

This page produced the strongest results of the audit so far. Specifically verified:

- **The 2026-09-01 CRITICAL milestone IDOR is genuinely fixed.** Probed as **Admin** deliberately,
  so `requireProjectAccess` passes for both projects and only the parent join can refuse:
  ```
  PATCH /api/projects/p1/stages/<p1 stage>/milestones/<p2 milestone>  -> 404 Not found
  PATCH /api/projects/p1/stages/<p2 stage>/milestones/<p2 milestone>  -> 404 Not found
  target milestone amount afterwards: still null (unchanged)
  ```
  The guard at `milestones/[milestoneId]/route.ts:25-29` verifies `m.id = ? and m.stageId = ? and
  s.projectId = ?` before any write, exactly as the remediation plan specified.
- **Nested-resource isolation holds for a scoped Staff user.** A Staff account holding
  `projects:edit` but able to reach only `p4` was refused on all five probes against `p2`:
  stage PATCH, milestone PATCH, expense PATCH, payment POST, and basic-rate PATCH.
- **Income maths is correct, verified against a hand computation** rather than against itself.
  For p1 (contract 18,470,000 over 4 un-overridden stages = 4,617,500 each):
  stage 1 all paid → 4,617,500; stage 2 Advance-50 paid + Interim-25 `cheque_cleared` → 3,463,125;
  total received **8,080,625** and outstanding **10,389,375** — both matched the API exactly. The
  cheque semantics are right: `cheque_cleared` counts as received, `cheque_received` sits in its own
  pending bucket, `cheque_bounced` falls back to outstanding.
- **Stage-value rebalancing is correct.** Overriding stage 1 to 10,000,000 caused the three free
  stages to split the remaining 8,470,000 (2,823,333.33 each), producing received **12,117,500** —
  matching hand computation. `received + outstanding + chequePending` still summed exactly to the
  contract both before and after the override, which is the invariant that rule exists to preserve.
  Despite dividing by 3, no floating-point artefact leaked into the API response.
- **The stage overflow guard works and its error is genuinely useful.** Attempting a second
  override that would exceed the contract returned 400 with `shortfall: 530000`,
  `currentContract: 18470000` and `suggestedContract: 19000000` — arithmetically correct and
  directly actionable in the UI.
- **Payment over-allocation is refused** — a payment one rupee above the outstanding balance returns 400.
- **The over-allocation guard survives a concurrent race.** Six simultaneous full-amount payments
  against one 987,000 expense: **exactly one** returned 200 and five returned 400, with total paid
  landing at exactly 987,000. The check-then-insert sequence is not transactional in the code, but
  D1's serialisation holds it in practice.
- **Per-project catalog isolation is correct, including the duplicate-code case** the prompt
  specifically asks about. Code `L-003` exists in **both** p1 and p2 (codes are unique within a
  project only); editing it through p1's URL changed p1's row to 12345 and left p2's at 3500.
- **Price history is written correctly on a rate change** — `oldRate: 3500`, `newRate: 12345`,
  attributed to the right actor (`Nimal Perera`) with an accurate timestamp.
- **All 25 nested routes use bound parameters.** The only interpolated SQL in this tree builds
  column names from hardcoded whitelists (see the cross-cutting note in `00-INDEX.md`).
- **Database left at baseline.** Every probe was reverted; after the run the dashboard read
  `received 16,920,625 / outstanding 32,799,375` — identical to before the page was audited.

## Not tested / blocked

- **Per-tab UI interaction was not exhaustively clicked.** This page carries six tabs and the
  richest component tree in the app; I covered it at the API level, where the authorisation and
  arithmetic risks actually live. Tab switching, modal cancel/abort paths, expand/collapse rows,
  sorting and the per-tab export buttons remain unexercised. **This is the largest coverage gap in
  the audit so far and should be closed before handover** — ideally as a dedicated pass over this
  page alone.
- **The BSR recipe engine was verified by reading, not by execution.** `activityItemRate()`
  (`total / analysisQty`), the `analysisQty` "basis isn't always 1 unit" quirk, `floorMultiplier`
  and percentage-allowance lines were reviewed in `src/lib/derive.ts` and look correct, but I did
  not build a recipe through the UI and check a derived rate against a hand-computed figure. Given
  that this engine is the reason the project exists (per `GAP_ANALYSIS.md`, the original BRD
  undersold it entirely), it deserves its own focused verification.
- **Gap #11 (rate-change propagation) was not assessed.** Changing a Basic Price ingredient does
  not flag or update the BSR items derived from it; this is a known open business decision
  (`doc/New folder/RATE_CHANGE_FLAG_PROPOSAL.md`), not a defect, so it was left alone.
- **The catalog import route was not fuzzed.** `/api/projects/[id]/basic-rate/import` — oversized
  files, malformed XLSX, formula injection (`=cmd|...`) and zip bombs, all named in the prompt —
  were not attempted. This is a meaningful untested risk area and belongs with pages 6/7.
- **Clone-catalog and copy-items flows were not tested** (`basic-rate/clone`, `items` copy-from-project),
  including whether cloning produces genuinely independent rows.
- **The `owner` and `members` routes were only read, not probed.** They are the subject of page 19
  (Project Access) and are audited there.

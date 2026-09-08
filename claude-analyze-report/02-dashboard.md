# QA Audit — Dashboard (`/`)

- **Audited:** 2026-09-03
- **Build/commit:** `89395b8` (working tree modified only by audit artefacts)
- **Verdict:** PASS-WITH-NOTES
- **Playwright spec:** `vega-manager/tests/02-dashboard.spec.ts` — 14 tests, 13 passed, 1 failed (the failure is F-02-01, working as intended: the test documents the finding)

## Summary

The dashboard is the app's landing page: five KPI cards (received, outstanding, cheque pending,
expenses, Overall ROI), an expense-category donut, a pending-payments list, a recent rate-change
feed, and Excel/PDF portfolio-statement exports. Everything is aggregated server-side in a single
`/api/dashboard` handler that runs five separate project-scoped queries.

**This page is in good shape.** The area I expected to break — cross-project data isolation on an
aggregate endpoint, historically the easiest place in an app like this to leak another project's
money — is implemented correctly and I verified it with exact figures rather than by inspection.
Aggregation is also arithmetically sound: dashboard totals reconcile to the penny against the
per-project endpoint, and the category breakdown sums exactly to the committed expense total.

The one real finding is a presentation problem, not a security or arithmetic one: with no expense
payments recorded — which is the state of every fresh deployment — the headline "Overall ROI" card
reports the entire received cash as profit while simultaneously reporting "0.0% on paid expense".

## Coverage

| Test class | Status | Notes |
|---|---|---|
| A. Functional / Playwright | ✅ | Loads clean, zero console/page errors, both exports download real files, dark+light × 1920/1366/390 all clean |
| B. Authentication & session | ✅ | Unauthenticated page redirects to `/login`; `/api/dashboard` returns 401 |
| C. Authorisation / RBAC / IDOR | ✅ | **Verified with exact figures** — Staff aggregate covers only reachable projects; no-permission Staff gets a denial panel and a 403 |
| D. SQL injection & input handling | ✅ | Read-only endpoint, no user input beyond the session; five interpolated clauses all use literal column names (see X-cutting in `00-INDEX.md`) |
| E. Headers / disclosure | ✅ | Inherits the app-wide header set verified on page 1; no page-specific disclosure |
| F. Data integrity & business rules | ⚠️ | Totals and category breakdown reconcile exactly; ROI presentation is misleading at `expensePaid = 0` (F-02-01) |

## Findings

### F-02-01 — "Overall ROI" reports all received cash as profit when no expense payment has been recorded
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Data integrity / UX
- **Location:** `src/app/page.tsx:135-136`, rendered at `src/app/page.tsx:223-227`
- **Reproduction:**
  1. Fresh seeded database (`npm run db:seed`) — `expense_payments` has 0 rows, which is also the
     state of any real deployment before anyone records a payment.
  2. Log in as `nimal@vegahomes.lk` and look at the "Overall ROI" card.
- **Expected:** ROI is undefined (or shown as "—" / "no payments recorded") when nothing has been
  paid out. It should not read as a gain.
- **Actual:** The card renders a large positive ROI next to a 0.0% rate:
- **Evidence:**
  ```
  OVERALL ROI
  +LKR 16,920,625
  0.0% on paid expense
  ```
  ```js
  // src/app/page.tsx:135-136
  const roi = received - expensePaid                              // 16,920,625 - 0
  const roiPct = expensePaid > 0 ? (roi / expensePaid) * 100 : 0  // guarded -> 0
  ```
  Confirmed against the data: `select count(*) from expense_payments` → **0**, while
  `expenseCommitted` is **LKR 5,658,200**. So LKR 5.66M of expense is logged and deliberately
  excluded from ROI, and the card presents the result as pure profit.
- **Impact:** The single most prominent number on the app's landing page is wrong in the ordinary
  case, and wrong in the optimistic direction. A director opening the dashboard on day one sees
  "+LKR 16,920,625" and a green upward trend arrow, when the true cash position is that LKR 5.66M
  of committed expense simply has not been marked paid yet. The two lines also contradict each
  other — a large gain "at 0.0%" — which erodes trust in the figure even for a user who reads it
  carefully. Note the underlying cash-basis choice (`expensePaid`, not `expenseCommitted`) is
  **deliberate and correct** — this is purely about how the zero case is presented.
- **Suggested fix:** Render an explicit empty state for `expensePaid === 0` ("No payments recorded
  yet") instead of `received - 0`, or show ROI against committed expense with a clear label when no
  payments exist. (Describe only — not implemented.)

### F-02-02 — Stray `//test` marker left in the dashboard source
- **Severity:** Info
- **Confidence:** Confirmed
- **Class:** Functional (code hygiene)
- **Location:** `src/app/page.tsx:50`
- **Evidence:**
  ```
  48: }
  49:
  50: //test
  51:
  52: function Donut({ segments, total, centerLabel, centerSub, size = 112 }: {
  ```
- **Impact:** None at runtime. Noted only because this is a client handover deliverable. To the
  codebase's credit this is the **only** stray marker of its kind in `src/` — a repo-wide sweep for
  `console.log`, `TODO`, `FIXME` and `XXX` found nothing else.
- **Suggested fix:** Delete the line. (Describe only.)

### F-02-03 — A newly created Staff user can reach no part of the app until an Admin creates a role
- **Severity:** Info
- **Confidence:** Confirmed
- **Class:** UX / Onboarding
- **Location:** `prisma/seed.ts` (no roles seeded), `src/lib/rbac.ts:41-64`
- **Evidence:** The seeded database contains **zero** rows in `roles`, `role_permissions` and
  `user_roles`. Both seeded Staff users therefore have `permissions: []`:
  ```
  GET /api/auth/me  -> {"user":{...,"role":"Staff","permissions":[]}}
  GET /api/dashboard -> 403 {"error":"Missing permission: dashboard:view"}
  GET /api/projects  -> 403 {"error":"Missing permission: projects:view"}
  GET /api/payments  -> 403 {"error":"Missing permission: payments:view"}
  ```
- **Impact:** Not a defect — the enforcement is exactly right, and the UI handles it well (see
  below). Recorded because it has two practical consequences the client should know: (1) every new
  Staff user is locked out of everything until an Admin builds a role for them, and there is no
  starter role shipped to copy; (2) anyone testing this app with the seeded Staff accounts will
  conclude the app is broken for Staff unless they know to create a role first. This audit had to
  create its own role fixture to test any Staff-visible behaviour at all.
- **Suggested fix:** Ship a sensible default role (e.g. "Site Staff" with `dashboard:view`,
  `projects:view`) in the seed, or document the first-run step in the handover notes. (Describe only.)

## Tested and clean

- **Cross-project isolation on the aggregate endpoint is correct, verified numerically.** A Staff
  user (Kasun) who owns `p4` and is a member of `p1` sees a dashboard whose totals equal `p1`'s
  figures **exactly**:
  ```
  Kasun  /api/dashboard   -> received 8,080,625   outstanding 10,389,375   committed 3,626,200
  Admin  /api/projects/p1 -> received 8,080,625   outstanding 10,389,375   committed 3,626,200
  Admin  /api/dashboard   -> received 16,920,625  (company-wide — correctly NOT what Kasun sees)
  ```
  No pending-payment row or rate-change entry referenced a project outside his reachable set, and
  `/api/projects` returned exactly `['p1','p4']`.
- **The `projectAccessClause` membership branch works.** `src/lib/rbac.ts:106-113` documents a past
  bug where an unqualified `idColumn` made the `EXISTS` branch silently always-false, so a project
  a user was merely *assigned* to vanished from dashboard totals while appearing correctly
  elsewhere. Explicitly regression-tested: Kasun does not own `p1`, reaches it by membership only,
  and its figures do appear in his totals.
- **Aggregation arithmetic reconciles exactly.** Dashboard `received`/`outstanding`/
  `expenseCommitted` each equal the sum of the per-project endpoint's values across all four
  projects — asserted with `toBe`, not a tolerance. The category breakdown sums exactly to
  `expenseCommitted`.
- **No-permission Staff get a proper denial panel, not a broken shell.** `RequirePermission`
  renders "You don't have access to this page — Ask an admin to assign you a role with access to
  this section", and the KPI cards are absent from the DOM entirely (not merely hidden). The
  loading state is deny-by-default, so no unauthorised content flashes before permissions resolve.
- **Both exports produce real files.** Excel (`.xlsx`) and PDF downloads both fire and are well
  above a plausible empty-file size; filenames carry correct extensions.
- **No `NaN`, `Infinity`, `Invalid Date`, `undefined` or `null` rendered anywhere** on the page,
  and no floating-point artefacts (no money value with 3+ decimal places).
- **Division-by-zero is properly guarded** — `roiPct` short-circuits when `expensePaid` is 0 rather
  than producing `Infinity`/`NaN`. (The *presentation* of that zero case is F-02-01; the arithmetic
  itself is safe.)
- **Zero console errors and zero page errors** on load as Admin.
- **Dark and light mode both render correctly at 1920, 1366 and 390 px** with no horizontal overflow.
- **`useSWR` calls are permission-gated client-side too** — `/api/projects` is only fetched when
  `canViewProjects` is true (`src/app/page.tsx:110`), so a denied user's browser doesn't fire
  requests that would only 403.

## Not tested / blocked

- **Large-data and empty-portfolio states were not exercised.** The seed has 4 projects; behaviour
  with hundreds of projects (the `pendingPayments` list slices to 6, the donut to 6 categories) and
  with zero projects was not tested. The Staff-with-only-`p4` case did cover a genuinely empty
  aggregate, which rendered correctly as zeros.
- **Export *content* was verified only by file size, not by parsing.** The prompt asks that exports
  "contain the values shown on screen" — confirming that requires opening the workbook and PDF and
  comparing cells, which is better done on the pages whose exports carry the detailed rows
  (Payments, BSR). Deferred to those pages.
- **`chequePending` was never exercised with a non-zero value** — no seeded milestone is in
  `cheque_received` state at the portfolio level, so that KPI showed 0 throughout. The
  cheque-status logic is better covered on page 4 (project detail, Stages & Payments tab).
- **Concurrency was not tested here** — the dashboard is read-only, so it is deferred to the pages
  that write.

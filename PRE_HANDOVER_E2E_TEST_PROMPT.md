# Pre-Handover End-to-End Functional Test — Prompt for Claude Code

> Paste everything below the line into a fresh Claude Code session opened at
> `C:\Users\HP\VegaConstruction-ManagementSystem`, with `C:\Users\HP\vega-construction-docs`
> added as a second working directory.

---

## Your role

You are a senior QA engineer doing the final functional sign-off on **Vega Construction Manager**
before it is handed to the client. Your job is to prove, with evidence, whether every page and every
business workflow works correctly end to end, for every kind of user, and to write a handover-grade
report. You are testing, not developing: **do not change application code** during this exercise.
If you find a bug, record it with a reproduction. Fixes happen in a separate pass, and only if I
approve them.

## Read before you do anything

1. `AGENTS.md` / `CLAUDE.md` in the app repo. This is Next.js 16 with breaking changes. Read the
   relevant guide in `node_modules/next/dist/docs/` before writing any code that touches Next.
2. `prisma/schema.prisma` (39 models), `src/lib/rbac.ts` (permission catalog), `src/lib/auth.ts`
   and `src/lib/sessionToken.ts` (session/idle rules), `src/lib/derive.ts`, `src/lib/milestones.ts`,
   `src/lib/variations.ts`, `src/lib/incomePayments.ts`, `src/lib/costPlus.ts` (money logic).
3. The BRD: `vega-construction-docs/VegaConstruction_System_BRD.pdf` and
   `Vega_Construction_Enhancements.pdf`. Expected behaviour comes from these plus the code, not from
   what the UI happens to show.
4. The previous functional report:
   `vega-construction-docs/e2e-journey-report/HANDOVER_FUNCTIONAL_TEST_REPORT.md` (2026-09-21,
   findings E-01 to E-10). Every finding marked fixed there must be re-verified as a regression check.
5. `vega-construction-docs/UAT Feed back/`. Every UAT item must be checked as resolved or still open.
6. `git log --since=2026-09-21 --no-merges`. These features are **new since the last E2E run** and
   have never been through a full functional pass, so test them hardest:
   - Server-issued, never-reused voucher numbers; expense category derived from line items
   - Stage milestones payable in instalments
   - Project variations (extra client work) with instalment payments and the variations summary strip
   - Expense line items as unit amount × qty; selective Basic Rate clone
   - Payments page filters, saved filter presets, "other payee" on expenses, shared DatePicker
   - Vendor drawer on the payments page
   - Cost-plus projects module (projects, expenses, payments, dashboard KPIs)
   - BSR wastage % per recipe component and profit % per item; searchable select retype
   - Currency locked to LKR
   - Case-insensitive duplicate checks and hardened input validation on API routes
   - SQL-aggregated dashboard and basic-rate totals (perf change: verify the numbers did not change)

## Environment and data safety (hard rules)

- Test **only** against an isolated local Postgres database created for this run (for example
  `vega_e2e`). Never point at the client's Supabase, Azure, k3s or any shared database.
- Before the first write, print the resolved `DATABASE_URL` host and database name, and stop and ask
  me if it is not localhost.
- Set up with `npm run db:migrate`, then `npm run db:seed` (or `db:seed-user` for a single admin).
  Run the app with `npm run build && npm run start` (production mode) unless a dev-only issue needs
  `npm run dev`. Record the commit hash and whether the working tree is dirty.
- Prefix every record you create with `E2E-` so it is easy to find and remove.
- Keep a live cleanup ledger of every record you create (type, name, id, journey, deleted y/n).
- Do not commit, push, or open PRs. Ask me first.

## Tooling

- Playwright (`@playwright/test` is installed). **The existing `tests/*.spec.ts` suite is known
  broken**: `tests/helpers.ts` still shells out to wrangler/D1, which no longer exists. Do not rely
  on it. Write a new suite in `tests/e2e-handover/` with its own helpers that talk to Postgres
  directly through `pg` for DB assertions, and its own Playwright config if needed. Keep the tests
  re-runnable so the client's team can repeat this later.
- `playwright.config.ts` defaults `baseURL` to `http://localhost:8787`. Set `PW_BASE_URL` to wherever
  the app actually runs. Keep the `Origin` header logic: the app rejects cross-origin mutations (CSRF).
- Capture a screenshot for every test case result, plus a trace on failure. Save evidence under the
  report folder, not in the app repo.
- For every money figure, compute the expected value independently (by hand or in a small script),
  then compare it three ways: UI, API response and DB row. LKR to 2 decimals. Note any rounding drift.

## Test accounts

Using the admin account, create these roles and users **through the UI** (that is a test in itself),
then use each one for its journeys. Derive exact permissions from `PERMISSION_CATALOG` in `rbac.ts`.
Modules: dashboard, projects, activities, suppliers, payments, priceComparison, costPlus. Actions:
view, create, edit, delete, promote.

| Account | Intent |
|---|---|
| `E2E-Admin` | Full access (seeded admin) |
| `E2E-Estimator` | projects + activities create/edit, no delete/promote, suppliers view-only |
| `E2E-Finance` | dashboard, payments, priceComparison view only |
| `E2E-CostPlus` | costPlus only |
| `E2E-ViewOnly` | view on every module, nothing else |
| `E2E-NoPerm` | zero permissions |
| `E2E-Estimator2` | same role as Estimator, but **not** a member of the test project (tests project-access scoping) |

## Scope: every page

`/login`, `/` (dashboard), `/projects`, `/projects/[id]` (every tab), `/basic-price`, `/basic-rate`,
`/activities`, `/suppliers`, `/suppliers/[id]`, `/suppliers/compare`, `/suppliers/compare/item`,
`/sub-contractors/[id]`, `/payments`, `/cost-plus`, `/cost-plus/[id]`, `/users`, `/users/[email]`,
`/roles`, `/settings`, `/settings/company-profile`, `/settings/field-options`,
`/settings/project-access`.

Also exercise the API routes under `src/app/api/**` directly where the UI hides an action. A hidden
button is not access control. Every denied UI action must also be attempted as a raw API call, and
must return 401/403, never 200 and never 500.

## Journeys

Run in order. Later journeys use data from earlier ones. Give each test case an ID (for example
`J3-07`).

**J0 — Smoke.** Log in as admin and open every page. For each page record: load time, console
errors, failed network requests (4xx/5xx), blank or stuck-spinner states. Also check `/api/healthz`
and `/api/ready`.

**J1 — Master data.** Company profile (including logo, and how it appears on PDF exports). Field
options: categories, trades, units. Create, rename and delete each; check a rename cascades
everywhere the value is shown; check that deleting an in-use value is blocked or handled. Suppliers
and sub-contractors: full CRUD, detail pages, case-insensitive duplicate rejection. Activities: CRUD
and code assignment.

**J2 — Pricing catalog.** Basic Price: draft, edit, promote to Basic Rate. Check next-code
generation, price history and the history view. Promote twice or concurrently: expect a clean
conflict, not a duplicate. Basic Rate: edit, history, search, export.

**J3 — Project lifecycle (core workflow; most depth here).**
- Create a project with contract value and stages. Check validation on every field.
- Members and owner: add/remove members, transfer ownership (`/settings/project-access` too).
- Stages → milestones → milestone payments, **including paying a milestone in several
  instalments**: partial, exact, and an over-payment attempt. Check outstanding and received totals
  after each step.
- BSR: add items, recipe components, **wastage % per component, profit % per item**. Hand-compute
  item rates and totals. Check with 0 %, a decimal %, a large %, and a negative % (expect rejection).
- Project Basic Rate: clone (full and **selective**), import, next-code, per-code history.
- Expenses: **line items as unit amount × qty**, derived category, **server-issued voucher numbers**
  (sequential, unique, never reused after a delete), **other payee**, expense payments (partial and
  full), edit and delete.
- **Variations**: create, pay in instalments, check the summary strip (totals, received, cheques
  pending, outstanding).
- Project report exports (PDF and XLSX): open each file and check figures match the UI.
- Delete a project: check what cascades and what is blocked.

**J4 — Payments.** Every filter, alone and combined, date presets, DatePicker edge cases (month end,
leap day, typed versus picked dates), **saved filter presets** (create, apply, rename, delete; check
they are per user), **vendor drawer**, other-payee history. Totals on this page must match the sum of
the underlying expense, milestone and variation payments in the DB.

**J5 — Price comparison.** `/suppliers/compare` and `/suppliers/compare/item`: correct
lowest-price logic, ties, missing prices, a single supplier.

**J6 — Cost-plus module.** Projects, expenses, expense payments, client payments, and the cost-plus
dashboard KPIs. Hand-compute cost, markup and balance, then check UI, API and DB agree.

**J7 — Dashboard.** Every KPI and chart cross-checked against DB queries. Repeat as Finance and as
Estimator: each must see only what their access allows, and the numbers must be correct for that
scope. This confirms the SQL aggregation perf change did not alter results.

**J8 — RBAC and project-access matrix.** For each account, every page and every
module × action: is it reachable in the UI, is the control visible, and does the raw API call
succeed? Expect a clean denial panel, never a crash or blank page. Check Estimator2 cannot read or
write a project they are not a member of, including via guessed IDs in API URLs.

**J9 — User and role administration.** Create, edit and deactivate users. Check password policy
(common-password rejection, length). Create, edit and delete roles. Per-user permission overrides.
Email uniqueness is case-insensitive. A user cannot lock themselves out or delete the last admin.

**J10 — Auth and session.** Login success and failure messages, login throttle and rate limit,
"Remember me" (7-day) versus session-only (8 h), logout, idle timeout (check background polling such
as `/api/notifications` does not keep a session alive), and these events while a user is logged in
elsewhere: deactivation, role change, password change.

**J11 — Negative and edge input, across all forms.** Empty or required fields, whitespace-only,
duplicates (different case), negative numbers, zero, very large numbers, many decimals, Unicode or
Sinhala/Tamil text, very long strings, HTML or script in text fields (it must render inert),
double-click submit, browser back after submit, refresh mid-form, and two sessions editing the same
record.

**J12 — Cross-cutting UX.** Three viewports (1440, 1024, 390 wide), dark mode, empty states,
loading states, toasts on success and failure (no silent failures), tab and filter state surviving a
refresh, notifications, no CSP violations in the console, and LKR formatting consistent everywhere.

**J13 — Regression.** Re-verify each 2026-09-21 finding (E-01 to E-10) and each UAT feedback item.
Mark each one: still fixed / regressed / still open.

## Severity

- **Critical**: data loss or corruption, wrong money figures, privilege escalation or cross-project
  data leak, or a core workflow blocked.
- **High**: a workflow broken with no workaround, silent failure, or a server 500.
- **Medium**: broken with a workaround, wrong validation, or misleading UI.
- **Low**: cosmetic, copy, or minor UX.

Every finding needs: ID, severity, page/route, account, exact steps, expected, actual, evidence
(screenshot or trace path), suspected code location (`file:line`), and whether it is new or a
regression.

## Deliverables (write to the docs repo)

Folder: `vega-construction-docs/pre-handover-test/e2e/`

1. `E2E_TEST_REPORT_<YYYY-MM-DD>.md` with these sections:
   1. Executive summary and overall verdict: 🟢 READY / 🟡 READY WITH CONDITIONS / 🔴 NOT READY,
      with the reason in two or three sentences
   2. Environment: commit, dirty tree, DB, browser, app mode, date
   3. Scope and accounts
   4. Coverage matrix: page/module × account, with a 🟢/🟡/🔴 verdict per cell
   5. Workflow results: one table per journey (test ID, scenario, expected, actual, pass/fail, evidence)
   6. Money verification table: figure, expected (hand-computed), UI, API, DB, match?
   7. Findings, sorted by severity
   8. Regression status of E-01 to E-10 and the UAT items
   9. Not tested, and why
   10. Test totals: total / passed / failed / blocked, per journey
   11. How to re-run the suite
2. `RUN-LOG.md`: a timestamped log of what you did, kept live as you go.
3. `CLEANUP.md`: the ledger, plus the final cleanup action (drop the DB, or row-by-row deletes to
   verify cascades).
4. `evidence-<YYYY-MM-DD>/`: screenshots, traces, exported PDF/XLSX files, DB query outputs.

The Playwright suite stays in the app repo at `tests/e2e-handover/` (uncommitted until I review it).

## How to work

- Before starting, write a short plan: the test case list per journey, with rough counts. Show it to
  me and wait for my OK.
- Work journey by journey. Update `RUN-LOG.md` after each one so the run can resume after a context
  reset.
- If a test fails, first confirm it is the app and not your script (wrong locator, timing, or bad
  test data). Record test-authoring mistakes in the run log, not as findings.
- Do not mark a journey passed without evidence. Do not report a figure as correct without the
  independent calculation.
- If something blocks a journey (a crash, or missing data), log it as a finding, work around it if
  possible, and keep going. Do not stop the whole run.
- At the end, give me a 10-line summary in chat: the verdict, counts, the top 5 findings, and the
  report path.

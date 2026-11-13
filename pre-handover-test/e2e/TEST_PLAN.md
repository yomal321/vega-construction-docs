# Pre-Handover E2E Test — Plan (awaiting approval)

- Date: 2026-11-09 · Tester: Claude Code (senior QA role)
- Build under test: branch `dev` at the latest `origin/dev`, currently `348da81` (includes PR 1338,
  security fixes S1–S4). Local `dev` was at `0e15246`, 10 commits behind; it will be
  fast-forwarded (`git pull --ff-only origin dev`, then `npm ci`) when the run starts. The exact
  hash is re-checked and recorded at start.
- Working tree is **dirty**: `.gitignore` and `next-env.d.ts` modified, 5 staged deletions under
  `doc/test/security/`, untracked `.specclaw/` and `docs/`. None of these touch `src/`.

## Environment

| Item | Choice |
|---|---|
| Database | New throwaway Docker container `vega-e2e-pg` (`postgres:17-alpine`), host `127.0.0.1:5441`, database `vega_e2e`. Existing containers (`vega-cheque-test`, `payshia-postgres`) are left alone. |
| DB setup | `DATABASE_URL` exported explicitly in every shell (Prisma CLI ignores `.env.local`; the last run hit Supabase this way). Host is printed and checked before the first write. Then `npm run db:migrate` and `npm run db:seed`. |
| App | `npm run build && npm run start` on port 3100 (production mode). `PW_BASE_URL=http://localhost:3100`. |
| Browser | Chromium via Playwright, screenshot per test case, trace on failure. |
| Suite | New `tests/e2e-handover/` with its own config, `pg`-based helpers and fixtures. Uncommitted. |
| Evidence | `vega-construction-docs/pre-handover-test/e2e/evidence-2026-11-09/` |
| App code | Not changed. Bugs are recorded with reproduction steps only. |

## Accounts (created through the UI by admin, as test J9-01..07)

`E2E-Admin` (seeded admin), `E2E-Estimator`, `E2E-Finance`, `E2E-CostPlus`, `E2E-ViewOnly`,
`E2E-NoPerm`, `E2E-Estimator2` (Estimator role, not a member of the test project).
Permissions come from `PERMISSION_CATALOG` in `src/lib/rbac.ts`.

## Test cases per journey (rough counts)

| Journey | Focus | Cases |
|---|---|---|
| J0 Smoke | 22 pages + `/api/healthz`, `/api/ready`: load time, console errors, 4xx/5xx, stuck spinners | ~25 |
| J1 Master data | Company profile and logo on PDF; categories, trades and units (create, rename cascade, delete in-use, case-insensitive duplicates); suppliers and sub-contractors CRUD and detail pages; activities CRUD and codes | ~40 |
| J2 Pricing catalog | Basic Price draft, edit, promote, next-code, history; double and concurrent promote; Basic Rate edit, history, search, export | ~15 |
| J3 Project lifecycle | Create and validate; members and owner transfer; stages and milestones with instalments (partial, exact, over-pay); BSR wastage % and profit % (0, decimal, large, negative); project Basic Rate full and selective clone, import, history; expenses with qty × unit lines, derived category, server voucher numbers never reused, other payee, partial and full payments, edit and delete; variations with instalments and summary strip; PDF and XLSX exports checked against UI; project delete cascade | ~70 |
| J4 Payments | Each filter alone and combined; date presets; DatePicker edge cases; saved presets per user; vendor drawer; other-payee history; page totals against DB sums | ~30 |
| J5 Price comparison | Lowest price, ties, missing prices, single supplier, item page | ~8 |
| J6 Cost-plus | Projects, expenses, expense payments, client payments, KPIs; markup and balance computed by hand and checked in UI, API and DB | ~20 |
| J7 Dashboard | Every KPI and chart against DB queries, as Admin, Finance and Estimator | ~20 |
| J8 RBAC matrix | 7 accounts × 22 pages in the UI, plus module × action raw API probes (expect 401/403, never 200/500), plus Estimator2 guessed-ID access | ~25 cases, about 300 assertions |
| J9 Users and roles | Create, edit, deactivate; password policy; roles CRUD; per-user overrides; case-insensitive email; last-admin and self-lockout guards | ~20 |
| J10 Auth and session | Login messages, throttle, Remember me (7 d) against session-only, admin 30-min idle, logout, polling does not extend idle; deactivation, role change and password change during a live session | ~18 |
| J11 Negative input | Empty, whitespace, case duplicates, negative, zero, huge, many decimals, Sinhala/Tamil text, long strings, HTML/script, double submit, back, refresh, two-session edits | ~35 |
| J12 Cross-cutting UX | 1440/1024/390 widths, dark mode, empty and loading states, toasts, state after refresh, notifications, CSP console, LKR format | ~25 |
| J13 Regression | E-01 to E-10, X-02 and money-sign cluster, UAT ENH-01 to ENH-09 | ~22 |
| **Total** | | **~370** |

## Method notes

- Every money figure is computed independently in a script under `tests/e2e-handover/calc/`,
  then compared in the UI, the API response and the DB row, to 2 decimals.
- Idle and expiry tests move `sessions.lastSeenAt` and `expiresAt` in the DB with UTC-safe SQL. The
  2026-09-21 run got a false finding (E-08) from a timezone cast. No wall-clock waits of 1 to 8 hours.
- The login throttle is reset between auth tests by clearing its table, so accounts do not lock.
- Known scope mismatch to verify: UAT ENH-04 asks for a selective clone of **expenses**, but the
  commit `56cd2ef` implements a selective **Basic Rate** clone. Both are tested and the gap is reported.
- Cleanup: every record is prefixed `E2E-` and logged in `CLEANUP.md`. The final action is
  row-by-row deletes to verify cascades, then the container is removed.

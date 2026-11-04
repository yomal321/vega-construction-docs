# Performance Test Report — after fixes (`dev` @ `0e15246`) — 2026-11-03

This re-runs the API load, stress and RBAC-path test from
`PERFORMANCE_TEST_REPORT_PRODUCTION_2026-11-03.md` (the "before" report) against the `dev` branch,
after the fixes for its findings were merged. It uses the same k6 script, dataset, database and
laptop, so the two reports compare directly.

Fixes included (`dev` @ `0e15246`):

| ID | Finding | Fix |
|---|---|---|
| F1 | `/api/projects` ran 3 queries per project in a loop | 4 set-based queries in total (PR 1336 / 1337) |
| F3 | DB pool capped at `max: 10` | Pool size reads `PG_POOL_MAX`, default 10 (PR 1336 / 1337). **This test ran with the default, 10.** |
| F4 | Dashboard summed every expense in JS; `/api/basic-rate` ran a subquery per row | Summed per category in SQL; one `distinct on` join (`0e15246`) |
| F5 | Single replica | Config only, not testable here (one laptop, one process) |
| F6 | Empty lookup tables on a fresh DB | `prisma/seed.ts` seeds them (`0e15246`). Not a performance item. |
| F8 | `/api/payments` re-scanned the filtered expenses ~7 times per call | Totals and top vendors in one query; full "No supplier items" read only on `tab=unlinked` (PR 1336 / 1337) |

Pass criteria (unchanged): error rate < 1 %, overall p95 < 800 ms, p99 < 2 s.

## 1. Summary

- **The Admin load test now passes.** At 30 users, p95 is **484 ms** (before: 1.54 s) and p99 is
  **774 ms** (before: 2.70 s). Throughput is **48.7 req/s** (before: 30.4, +60 %).
- **Staff is faster too:** p95 **81 ms** (before: 207 ms), throughput 73.1 req/s (before: 62.5).
- **No errors in any run.** 53,985 requests across the four runs, 0 failed, every check passed.
- **DB time per request almost halved:** 8.7 ms (before: 15.9 ms) in the Admin load run.
- **`/api/projects` no longer collapses under stress:** p95 at 200 users is **2.56 s** (before: 48.2 s).
- **The 200-user stress test still fails** (p95 8.2 s, before 17.65 s). That is expected on one
  laptop running the app, the DB and k6 together; it is CPU-bound, not failing.
- **`/api/payments` is still the largest DB cost** (~69 % of DB time, ~66 ms per call, before ~115 ms).
  See §5.

## 2. Environment

| Item | Value |
|---|---|
| Code | `dev` @ `0e15246` ("Perf: aggregate dashboard/basic-rate in SQL, seed lookup lists, 2 replicas + pool 20") |
| Build | `npm run build` (Turbopack), then `next start -p 3100` (production mode, Next.js 16.3.5, Node v26.13.0, single process) |
| DB pool | `PG_POOL_MAX` unset, so `max: 10`, the same as the before report |
| Database | `vega_prod` in the `vega-perf-pg` container (Postgres 16, `pg_stat_statements`). Same database and rows as the before report: 34 projects, 6,011 expenses, 17,959 line items, 5,987 payments, 1,114 Basic Rate items, 4,510 BSR lines, 26 users. |
| Load tool | k6 v2.3.0, `perf/load.js` unchanged, `-e BASE_URL=http://localhost:3100` |

The before report used a webpack build. Bundling does not change query counts, rows or payload
sizes. As before, the app, the DB and k6 share one 12-thread laptop, so the relative numbers matter
more than the absolute ones.

**Standby during the run.** The laptop briefly entered standby twice during the suite (Kernel-Power
events 506/507):

- 23:13:46 to 23:14:08 (22 s), during the Staff load run.
- 23:17:10 to 23:18:09, covering the last ~30 s of the Staff run's ramp-down and the first ~27 s of
  the stress run's ramp-up to 50 users.

The smoke and Admin load runs were not affected. The Staff and stress numbers are slightly
pessimistic, because any request in flight during standby is counted as slow.

## 3. Results

### 3.1 Overview

| Run | Before | Requests | Throughput | Errors | Median | p95 | p99 | Max | Result |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Smoke (Admin, 1 user) | before | 255 | 4.2 req/s | 0 % | 11 ms | 148 ms | 181 ms | 198 ms | Pass |
| | **after** | 299 | 4.7 req/s | 0 % | 17 ms | **138 ms** | 177 ms | 462 ms | Pass |
| Load (Admin, 30 users) | before | 9,187 | 30.4 req/s | 0 % | 130 ms | 1.54 s | 2.70 s | 5.06 s | Fail |
| | **after** | 14,720 | **48.7 req/s** | 0 % | 89 ms | **484 ms** | **774 ms** | 1.27 s | **Pass** |
| Load (Staff, 30 users) | before | 18,790 | 62.5 req/s | 0 % | 53 ms | 207 ms | 354 ms | 855 ms | Pass |
| | **after** | 22,145 | **73.1 req/s** | 0 % | 27 ms | **81 ms** | 115 ms | 1.24 s | Pass |
| Stress (Admin, 200 users) | before | 11,459 | 26.2 req/s | 0 % | 982 ms | 17.65 s | 46.1 s | 54.3 s | Fail |
| | **after** | 16,821 | **39.8 req/s** | 0 % | 1.13 s | **8.22 s** | 11.4 s | 13.7 s | Fail |

### 3.2 Per-route latency (p95)

| Route | Admin 30 — before | Admin 30 — **after** | Staff 30 — after | Admin 200 — before | Admin 200 — **after** |
|---|---:|---:|---:|---:|---:|
| `/api/dashboard` | 2.81 s | **665 ms** | 91 ms | 6.75 s | 12.90 s |
| `/api/projects/[id]` | 2.40 s | **536 ms** | 64 ms | 6.37 s | 9.69 s |
| `/api/basic-rate` | 2.04 s | **448 ms** | 70 ms | 3.59 s | 5.78 s |
| `/api/projects` | 1.78 s | **259 ms** | 57 ms | 48.2 s | **2.56 s** |
| `/api/payments` | 978 ms | **769 ms** | 122 ms | 4.53 s | 3.86 s |
| `/api/projects/[id]/bsr` | 461 ms | 409 ms | 57 ms | 2.76 s | 2.33 s |
| `/api/suppliers` | 342 ms | 241 ms | 37 ms | 2.93 s | 3.22 s |
| `/api/projects/[id]/expenses` | 280 ms | 364 ms | 73 ms | 2.33 s | 8.98 s |
| `/api/projects/[id]/items` | 257 ms | 295 ms | 55 ms | 2.77 s | 6.68 s |
| `/api/projects/[id]/stages` | 223 ms | 346 ms | 53 ms | 2.84 s | 5.00 s |
| `/api/projects/[id]/basic-rate` | 187 ms | 401 ms | 61 ms | 1.85 s | 2.10 s |

Every route is under the script's per-route 1.5 s threshold at 30 users.

Some small routes have a higher p95 than before. The test runs a fixed 30 users, each looping with
no wait, so faster heavy routes mean every user sends more requests per second: the server handled
60 % more requests per second than before. The small routes now share the same CPU with more
traffic. None of these routes changed.

At 200 users the laptop's CPU is saturated, so the per-route split mostly reflects which requests
queued behind which. The overall picture improved (p95 17.65 s to 8.22 s, throughput +52 %), and
`/api/projects`, the route that collapsed before, no longer does. `/api/dashboard` is now the
slowest route under stress (§5).

### 3.3 Database (Admin load run, `pg_stat_statements`)

Total query time: **128 s over 300 s** while serving 14,720 requests, **8.7 ms per request**
(before: 146 s for 9,187 requests, 15.9 ms per request).

| Calls | Total time | Mean | Rows returned | Query (route) |
|---:|---:|---:|---:|---|
| 1,338 | 31.6 s | 23.6 ms | 634 K | `filtered` CTE, ~474 rows per call; most likely the "No supplier items" totals per description — `/api/payments` |
| 1,338 | 25.5 s | 19.1 ms | 1.32 M | `filtered` CTE, ~984 rows per call: the page's vendors' expenses — `/api/payments` |
| 1,338 | 12.6 s | 9.4 ms | 2.7 K | `filtered` CTE, 2 rows per call: per-bucket totals and top vendors — `/api/payments` |
| 1,338 | 10.0 s | 7.5 ms | 4.01 M | line items for the page's expenses (~3,000 rows per call) — `/api/payments` |
| 1,338 | 8.5 s | 6.4 ms | 33 K | `filtered` CTE, 25 rows per call: the page of vendor groups — `/api/payments` |
| 1,338 | 6.2 s | 4.7 ms | 1.49 M | all Basic Rate items + previous rate (`distinct on`) — `/api/basic-rate` |
| 1,339 | 6.2 s | 4.6 ms | 46 K | committed/paid per project, all projects at once — `/api/projects` |
| 1,338 | 4.2 s | 3.2 ms | 1.3 K | total paid — `/api/dashboard` |
| 1,338 | 3.9 s | 2.9 ms | 688 K | line items — `/api/projects/[id]/expenses` |
| 1,338 | 3.1 s | 2.3 ms | 771 K | milestones for every project — `/api/dashboard` |
| 1,339 | 2.7 s | 2.0 ms | 771 K | milestones for every project — `/api/projects` |
| 1,338 | 2.6 s | 1.9 ms | 8.0 K | expense totals per category (6 rows) — `/api/dashboard` |

What changed against the before report:

- **`/api/projects`:** the per-project loop is gone. Before, it ran 29,259 × 2 queries in the run
  (35 per request per kind). Now there is one call of each query per request.
- **`/api/dashboard`:** the expense query returns 6 rows per call (before: 6,011), 1.9 ms mean
  (before: 3.6 ms, 5.02 M rows over the run).
- **`/api/basic-rate`:** 4.7 ms mean (before: 7.2 ms).
- **`/api/payments`:** 5 statements per call, ~66 ms of DB time per call (before: ~7 statements,
  ~115 ms). Still ~69 % of all DB time.

## 4. Status of the findings

| ID | Finding | Priority | Status | Evidence |
|---|---|---|---|---|
| F1 | N+1 in `/api/projects` | High | **Fixed** | p95 1.78 s to 259 ms (30 users), 48.2 s to 2.56 s (200 users). |
| F2 | `/api/payments` returns everything | High | **Fixed** (on `production` before this work) | Paginated; see F8 for its DB cost. |
| F3 | Pool capped at 10 | High | **Code fixed; value not changed in this test** | `src/lib/pg.ts` reads `PG_POOL_MAX`. A pool 10 vs 20 comparison was attempted but both runs were invalidated by laptop standby (§6). |
| F4 | Dashboard / Basic Rate aggregation in JS | Medium | **Fixed** | See §3.3. |
| F5 | Single replica | Low (ops) | **Not tested** | A DevOps setting; one laptop cannot show its effect. |
| F6 | Empty lookup tables on a fresh DB | Low (setup) | **Fixed** | Tested on an empty database: 0 to 3 categories, 14 trades, 9 units; a re-run adds nothing and keeps edits. |
| F8 | `/api/payments` re-scans the filtered set ~7 times | High | **Fixed, partly** | ~115 ms to ~66 ms DB time per call; still the largest DB cost (§5). |

## 5. What is left

1. **`/api/payments` is still ~69 % of DB time.** The heaviest remaining query (23.6 ms mean) is
   most likely the "No supplier items" totals. They run on every call, only for the footer total,
   highest and lowest. Options: compute them only when the page shows that footer, or cache them
   briefly. The page's expenses query (19.1 ms) re-builds the vendor grouping a second time; it
   could reuse the first.
2. **`/api/dashboard` is the slowest route at 200 users** (p95 12.9 s). It runs 6+ queries per call,
   including milestones with payments for every project and the cost-plus portfolio. It is fine at
   30 users (665 ms).
3. **F3 and F5 need a decision from DevOps,** measured on the cluster rather than on a laptop: the
   pool size per pod (`PG_POOL_MAX`) and the replica count. `dev` @ `0e15246` currently sets
   `PG_POOL_MAX: "20"` and `replicaCount: 2` in `deploy/helm/values-{dev,uat}.yaml`. Those files
   take effect only on the `gitops` branch, and this test did not validate those values.

## 6. Runs that were discarded

Two attempts to compare `PG_POOL_MAX=10` and `PG_POOL_MAX=20` in the Admin load profile gave no
usable result:

- **First attempt:** the runner did not stop the main suite's server, so both runs hit that
  already-stressed server (`EADDRINUSE` on port 3100) instead of a fresh one with the new pool size.
- **Second attempt, on fresh servers:** the laptop entered standby during both runs
  (23:31–23:42 and 01:15–01:18). The pool 10 run completed only 46 requests in 5 minutes.

These results are not used anywhere in this report.

## 7. How to reproduce

Same setup as §7 of the before report, with the app built from `dev`:

```powershell
git checkout dev
npm ci
$env:DATABASE_URL='postgresql://vega:vegaperf@localhost:55432/vega_prod?sslmode=disable'
$env:SESSION_SECRET='<any string of 32+ characters>'
npm run build
npx next start -p 3100

# second terminal; keep the machine awake and the lid open
k6 run -e BASE_URL=http://localhost:3100 -e PROFILE=smoke  -e EMAIL=nimal@vegahomes.lk        -e PASSWORD='VegaDemo-2026!' --summary-export smoke-admin.json  perf/load.js
k6 run -e BASE_URL=http://localhost:3100                   -e EMAIL=nimal@vegahomes.lk        -e PASSWORD='VegaDemo-2026!' --summary-export load-admin.json   perf/load.js
k6 run -e BASE_URL=http://localhost:3100                   -e EMAIL=perf.staff1@vegahomes.lk -e PASSWORD='VegaDemo-2026!' --summary-export load-staff.json   perf/load.js
k6 run -e BASE_URL=http://localhost:3100 -e PROFILE=stress -e EMAIL=nimal@vegahomes.lk        -e PASSWORD='VegaDemo-2026!' --summary-export stress-admin.json perf/load.js
```

Reset `pg_stat_statements` before each run (`select pg_stat_statements_reset()`) to get per-run DB
figures.

`perf/load.js` and `prisma/seed-perf.ts` are still not committed on any branch.

Raw k6 output, JSON summaries and the `pg_stat_statements` dumps for each run are in
[`perf/results/dev-after-fixes/`](../../../perf/results/dev-after-fixes/). The `.txt` files are
UTF-16.

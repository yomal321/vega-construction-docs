# Performance Test Report — `production` branch — 2026-11-03

This is an API load, stress and RBAC-path test of the **`production`** branch, the latest code. It
runs the same script and dataset, on the same machine, as two earlier runs it is compared with:

- **main baseline:** `main` @ `6e8267f` as committed. Raw results are in
  [`perf/results/`](../../../perf/results/).
- **main + fixes:** the same commit plus uncommitted fixes for F1–F4 below. Raw results are in
  [`perf/results/after-fix/`](../../../perf/results/after-fix/). Its 200-user stress run did not
  complete, because the laptop went into standby.

`production` @ `5598d2e` is 29 commits ahead of `main` @ `6e8267f`. Among the changes are cost-plus
projects, BSR wastage/profit, variations, the payments filters, presets and vendor drawer, and 5 new
migrations. The F1–F4 fixes are not on this branch.

Findings found on `main` and checked here:

| ID | Finding |
|---|---|
| F1 | `/api/projects` runs 2 queries per visible project in a loop (N+1). |
| F2 | `/api/payments` returns every expense and line item with no pagination (3.2 MB per call on `main`). |
| F3 | The DB pool is capped at `max: 10` per pod and can't be configured. |
| F4 | `/api/dashboard` sums every expense row in JS. `/api/basic-rate` runs a previous-rate subquery once per row. |
| F5 | The app runs as a single replica (`replicaCount: 1`). |
| F6 | A fresh DB (`migrate deploy` + `prisma/seed.ts`) leaves the `categories`, `trades` and `units` lookup tables empty. |

Pass criteria: error rate < 1 %, overall p95 < 800 ms, p99 < 2 s.

## 1. Summary

- **`production` is slower than the `main` baseline for Admin.** At 30 users, p95 is **1.54 s**
  (main: 1.06 s; target 800 ms) and throughput is **30.4 req/s** (main: 36.6, −17 %). The
  Admin load test **fails**.
- **Staff is unchanged and passes:** p95 207 ms (main: 205 ms).
- **No errors in any run.** 39,691 requests across four runs, 0 failed, every check passed,
  including the 200-user stress test. The machine stayed awake for the whole run (no Kernel-Power
  standby events).
- **F1, F3 and F4 from the main baseline are still present, unchanged.**
  - `/api/projects` still runs 2 queries per project.
  - The pool is still `max: 10`.
  - The dashboard still sums 6,011 expense rows in JS.
  - `/api/basic-rate` still runs one subquery per row.
- **F2 has been partly addressed on `production`, but not solved.** `/api/payments` is now
  paginated and filtered on the server, so the payload fell from 3.2 MB to **583 KB**. But each call
  now runs about 7 queries, which together cost **~115 ms of DB time** — twice what `main` spent.
  `/api/payments` is now **66 % of all DB time** (§5).
- **The fixes made on `main` would close most of the gap** (§6): Admin p95 525 ms there. F1, F3
  and F4 can be ported to `production`. F2 needs to be redone against `production`'s rewritten
  payments route.

## 2. Environment

| Item | Value |
|---|---|
| Code | `origin/production` @ `5598d2e` ("Merged PR 1303: BSR wastage % per recipe component and profit % per item…"), checked out in a separate git worktree |
| Build | `next build --webpack`, then `next start -p 3100` (production mode, Next.js 16.3.5, Node v26.13.0, single process) |
| Database | New database `vega_prod` in the same `vega-perf-pg` container (Postgres 16, `pg_stat_statements`). `production`'s migrations were applied with `prisma migrate deploy`. |
| Data | `prisma/seed.ts` from `production` + `prisma/seed-perf.ts` (unchanged, same fixed seed). The row counts are identical to the main baseline's: 34 projects, 6,011 expenses, 17,959 line items, 5,987 payments, 1,114 Basic Rate items, 4,510 BSR lines, 6,735 recipe components, 26 users. |
| Load tool | k6 v2.3.0, `perf/load.js` unchanged, `-e BASE_URL=http://localhost:3100` |

The script's 11 endpoints were checked before the run. All return 200 on `production` with no
query parameters, so the same page mix runs on both branches. With no parameters,
`/api/payments` returns page 1 (50 rows) of Suppliers.

The main baseline used a Turbopack build. This run used webpack, because `production` was built
from a worktree whose `node_modules` is linked from the repo. Bundling does not change query
counts, rows or payload sizes. As in the baseline, the app, the DB and k6 share one laptop, so the
relative numbers matter more than the absolute ones.

## 3. Results

### 3.1 Overview

| Run | Branch | Requests | Throughput | Errors | Median | p95 | p99 | Max | Result |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Smoke (Admin, 1 user) | main | 233 | 3.7 req/s | 0 % | 26 ms | 195 ms | — | 297 ms | Pass |
| | **production** | 255 | 4.2 req/s | 0 % | 11 ms | **148 ms** | 181 ms | 198 ms | Pass |
| Load (Admin, 30 users) | main | 11,079 | 36.6 req/s | 0 % | 121 ms | 1.06 s | 1.73 s | 3.96 s | Fail |
| | **production** | 9,187 | **30.4 req/s** | 0 % | 130 ms | **1.54 s** | 2.70 s | 5.06 s | **Fail** |
| Load (Staff, 30 users) | main | 19,439 | 64.4 req/s | 0 % | 39 ms | 205 ms | 319 ms | 615 ms | Pass |
| | **production** | 18,790 | 62.5 req/s | 0 % | 53 ms | **207 ms** | 354 ms | 855 ms | Pass |
| Stress (Admin, 200 users) | main | 13,170 | 30.1 req/s | 0 % | 1.08 s | 12.85 s | 34.1 s | 43.4 s | Fail |
| | **production** | 11,459 | **26.2 req/s** | 0 % | 982 ms | **17.65 s** | 46.1 s | 54.3 s | **Fail** |

The Admin p99 (2.70 s) also fails the 2 s target, which main's did not.

Data sent to clients in the 5-minute Admin load run was **982 MB** (main: 3.77 GB), because of
`/api/payments` pagination. Even so, fewer requests were served.

### 3.2 Per-route latency (p95)

| Route | Payload (Admin) | Admin 30 — main | Admin 30 — **production** | Staff 30 — production | Admin 200 — production |
|---|---:|---:|---:|---:|---:|
| `/api/dashboard` | 2 KB | 1.52 s | **2.81 s** | 221 ms | 6.75 s |
| `/api/projects/[id]` | 0.5 KB | 1.50 s | **2.40 s** | 177 ms | 6.37 s |
| `/api/basic-rate` | 333 KB | 1.17 s | **2.04 s** | 148 ms | 3.59 s |
| `/api/projects` | 16 KB | 1.69 s | **1.78 s** | 440 ms | **48.2 s** |
| `/api/payments` | **583 KB** | 800 ms | 978 ms | 246 ms | 4.53 s |
| `/api/projects/[id]/bsr` | 15 KB | 410 ms | 461 ms | 157 ms | 2.76 s |
| `/api/suppliers` | 1 KB | 523 ms | 342 ms | 96 ms | 2.93 s |
| `/api/projects/[id]/expenses` | 185 KB | 259 ms | 280 ms | 165 ms | 2.33 s |
| `/api/projects/[id]/items` | 46 KB | 207 ms | 257 ms | 142 ms | 2.77 s |
| `/api/projects/[id]/stages` | 5 KB | 274 ms | 223 ms | 153 ms | 2.84 s |
| `/api/projects/[id]/basic-rate` | 9 KB | 191 ms | 187 ms | 152 ms | 1.85 s |

As on `main`, the slowest routes include tiny ones. `/api/projects/[id]` returns 483 bytes from a
single-row query, yet has a p95 of 2.4 s. That points to time spent waiting for the event loop and
the 10 pool connections, not to the route's own work. There is more of this waiting on
`production`, because `/api/payments` now holds connections longer (§5).

### 3.3 Database (Admin load run, `pg_stat_statements`)

Total query time: **146 s over 300 s** (main: 107 s), while serving 17 % fewer requests.

| Calls | Total time | Mean | Rows returned | Query (route) |
|---:|---:|---:|---:|---|
| 835 | 52.7 s | 63.2 ms | 7.87 M | "No supplier items" lines under the filters, ~9,430 rows per call — `/api/payments` |
| 29,259 | 17.4 s | 0.59 ms | 29 K | per-project committed/paid sums — `/api/projects` loop (F1) |
| 835 | 15.7 s | 18.8 ms | 822 K | filtered vendor groups — `/api/payments` |
| 835 | 11.1 s | 13.3 ms | 1.7 K | per-bucket totals — `/api/payments` |
| 835 | 7.7 s | 9.2 ms | 1.7 K | top paid per bucket — `/api/payments` |
| 835 | 6.5 s | 7.8 ms | 2.50 M | line items for the page's vendors (~3,000 rows per call) — `/api/payments` |
| 835 | 6.0 s | 7.2 ms | 930 K | all Basic Rate items + per-row previous-rate subquery — `/api/basic-rate` (F4) |
| 835 | 4.8 s | 5.8 ms | 1.7 K | top outstanding per bucket — `/api/payments` |
| 29,259 | 4.8 s | 0.16 ms | 496 K | per-project milestones — `/api/projects` loop (F1) |
| 835 | 4.5 s | 5.4 ms | 21 K | page of vendor groups — `/api/payments` |
| 835 | 3.0 s | 3.6 ms | 5.02 M | all expenses, summed in JS — `/api/dashboard` (F4) |

The six `/api/payments` queries shown here add up to **96.5 s, 66 % of all DB time**. That is
about 115 ms per call, against about 58 ms per call on `main`.

## 4. Status of the main-baseline findings on `production`

| Finding | On `production` | Evidence |
|---|---|---|
| F1 — N+1 in `/api/projects` | **Present** | Same per-project loop (`src/app/api/projects/route.ts:54`). 29,259 × 2 queries in the run = 35 per request per kind. p95 1.78 s (30 users), **48.2 s** (200 users). |
| F2 — `/api/payments` returns everything | **Partly addressed** | Now paginated (50 per page) and filtered on the server, so the payload is 3.2 MB → 583 KB. But see F8 below: the DB cost per call doubled. |
| F3 — pool capped at 10 | **Present** | `max: 10`, not configurable (`src/lib/pg.ts:317`). |
| F4 — dashboard / Basic Rate in JS | **Present** | Dashboard: `select e.category, e.amount ...` (`src/app/api/dashboard/route.ts:49`), 6,011 rows per call (5.02 M over the run). Basic Rate: per-row `order by h.at desc limit 1` subquery (`src/app/api/basic-rate/route.ts:46`), 7.2 ms mean. |
| F5 — single replica | Present (ops) | Not re-checked. Nothing in this run touches it. |
| F6 — empty lookup tables on a fresh DB | **Present** | Neither `production`'s migrations nor its `prisma/seed.ts` insert `categories`/`trades`/`units`. The 3 categories in this run's DB came from `prisma/seed-perf.ts`. |

## 5. New finding on `production`

### F8 — `/api/payments` re-scans the filtered expense set ~7 times per call (High)

`production`'s rewritten route (`src/app/api/payments/route.ts`, 219 lines) builds the same
`with filtered as (...)` CTE once per query. It does this for the per-bucket totals, top-paid,
top-outstanding, the unlinked items, the page of groups, the page's expenses and their line
items. Postgres does not share a CTE between separate statements, so each query re-reads and
re-joins every expense under the filters.

The heaviest of these queries selects **every** "No supplier items" line under the filters
(~9,430 rows per call, 63 ms mean). It does this even when the Suppliers tab is showing, because
`unlinkedStats` needs totals over all such rows. The main + fixes run has the same problem in a
smaller form, and it was the largest DB cost there too.

**Fix:**

1. Compute the bucket totals, top-paid and top-outstanding from one aggregated pass, for example
   one `group by bucket, vendor` result reused in JS.
2. Aggregate the unlinked items in SQL, grouped by item key, and fetch their rows only when
   `tab=unlinked`.
3. Keep the page and drill-down queries as they are; they are already limited to the page.

**Expected:** about 7 scans of the filtered set per call drops to 2–3, and the 9,430-row read goes
away for the vendor tabs.

## 6. Comparison with the fixes on `main`

| Run | main baseline | **production** | main + F1–F4 fixes |
|---|---:|---:|---:|
| Admin 30 users, p95 | 1.06 s | **1.54 s** | 525 ms |
| Admin 30 users, throughput | 36.6 req/s | **30.4 req/s** | 48.7 req/s |
| Staff 30 users, p95 | 205 ms | **207 ms** | 73 ms |
| `/api/projects` p95 (Admin 30) | 1.69 s | **1.78 s** | 465 ms |
| `/api/payments` payload (Admin) | 3.2 MB | **583 KB** | 141 KB |
| DB time, Admin 5-min run | 107 s | **146 s** | 96.5 s |

**Recommendation:**

1. Port F1, F3 and F4 from `main` to `production`. These routes barely differ between the branches
   (`src/app/api/projects/route.ts` differs by 10 lines). The `production` versions of
   `/api/dashboard` and `/api/basic-rate` changed more, but they still contain the same two
   patterns, so the same fixes apply.
2. Do **not** port `main`'s F2 change to `production`. `production`'s payments route and page were
   rewritten for filters, presets and the vendor drawer, so the `main` change doesn't apply. Fix
   F8 on `production`'s own route instead.
3. Re-run this test on `production` after 1 and 2.

## 7. How to reproduce

```powershell
# Perf Postgres container (once)
docker run -d --name vega-perf-pg -e POSTGRES_USER=vega -e POSTGRES_PASSWORD=vegaperf -e POSTGRES_DB=vega `
  -p 55432:5432 postgres:16-alpine -c shared_preload_libraries=pg_stat_statements -c max_connections=200

# Production worktree and its own database
git fetch origin
git worktree add --detach ..\vega-prod origin/production
docker exec vega-perf-pg psql -U vega -d vega -c "create database vega_prod"
docker exec vega-perf-pg psql -U vega -d vega_prod -c "create extension if not exists pg_stat_statements"

cd ..\vega-prod
npm ci
$env:DATABASE_URL='postgresql://vega:vegaperf@localhost:55432/vega_prod?sslmode=disable'
$env:SESSION_SECRET='<any string of 32+ characters>'
npx prisma generate
npx prisma migrate deploy
npx tsx prisma/seed.ts
npx tsx <path to main's>\prisma\seed-perf.ts   # not on production yet
npm run build
npx next start -p 3100

# second terminal, from a checkout that has perf/load.js; keep the machine awake
k6 run -e BASE_URL=http://localhost:3100 -e PROFILE=smoke  -e EMAIL=nimal@vegahomes.lk        -e PASSWORD='VegaDemo-2026!' perf/load.js
k6 run -e BASE_URL=http://localhost:3100                   -e EMAIL=nimal@vegahomes.lk        -e PASSWORD='VegaDemo-2026!' perf/load.js
k6 run -e BASE_URL=http://localhost:3100                   -e EMAIL=perf.staff1@vegahomes.lk -e PASSWORD='VegaDemo-2026!' perf/load.js
k6 run -e BASE_URL=http://localhost:3100 -e PROFILE=stress -e EMAIL=nimal@vegahomes.lk        -e PASSWORD='VegaDemo-2026!' perf/load.js
```

`perf/load.js` and `prisma/seed-perf.ts` are not committed on either branch yet.

Raw k6 output, JSON summaries and the `pg_stat_statements` dump from this run are in
[`perf/results/production/`](../../../perf/results/production/).

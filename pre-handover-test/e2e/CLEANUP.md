# Cleanup Ledger — E2E run 2026-11-09

Every record this run created lives in two **throwaway local databases** inside one Docker
container. No shared database (Supabase, Azure, k3s) was touched. Every record is prefixed `E2E-`
(users: `<role>.<runtag>@e2e.test`, temp users `tmp-*`), and each one is listed with type, name,
id and journey in the ledger files below.

## Databases and ledgers

| Database | Purpose | Run tag | Ledger (one JSON line per record) | Records |
|---|---|---|---|---|
| `vega_e2e` (127.0.0.1:5441) | first pass, suite written journey by journey | `r3ruz8` | `evidence-2026-11-09/db/ledger.jsonl` | 138 |
| `vega_e2e_rerun` (127.0.0.1:5441) | clean final pass | `r6i8um` | `evidence-2026-11-09/rerun/db/ledger.jsonl` | 92 |

### Records by type

| Type | First pass | Clean pass | Deleted by the tests themselves |
|---|---|---|---|
| role | 6 | 6 | temp roles (J9-18) deleted |
| user | 20 | 16 | temp users J9-15 deleted; **E2E-Estimator deleted by mistake in the first pass (J9-15) and recreated** — see RUN-LOG |
| project | 5 | 4 | "E2E-To delete" (J3-43) and "E2E-Empty" (J12-05) deleted, cascade verified (0 rows left in 13 child tables) |
| expense | 23 | 13 | some deleted in J3-32, J3-38 (voucher numbers stay used) |
| variation | 8 | 4 | temp variations deleted (J3-17, J11-07) |
| base_item / basic_price_item / activity_item / bsr_line | 22 / 10 / 6 / 5 | 12 / 9 / 4 / 3 | partly (J2-12, J2-13) |
| supplier / sub-contractor | 7 / 1 | 5 / 1 | temp suppliers deleted; **a seeded supplier "Lanka Cement Distributors" was deleted by J1-23 (finding P-08)** |
| activity / category / trade / unit | 3 / 1 / 2 / 3 | 2 / 1 / 2 / 3 | temp ones deleted (J1-06, J1-10, J1-25, J1-26) |
| payment_filter_preset | 4 | 3 | the UI-created one deleted (J4-16) |
| cost_plus_project / cost_plus_expense | 3 / 9 | 1 / 3 | one expense deleted (J6-07) |

Payments (milestone, variation, expense, cost-plus), sessions, login-throttle rows and project
members hang off the records above and go with them.

## Environment artefacts (outside the databases)

| Item | Location | State |
|---|---|---|
| Docker container `vega-e2e-pg` (postgres:17-alpine, port 5441) | local Docker | **running — kept for your review / fix verification** |
| App server `next start -p 3200` (against `vega_e2e_rerun`) | local process | **running — kept for your review** |
| `.env.local` (local DB URL + random session secret, gitignored) | app repo root | present, points at `vega_e2e_rerun` |
| `prisma/.demo-seed.json` (gitignored), `prisma/.demo-seed.vega_e2e.json`, `prisma/.demo-seed.vega_e2e_rerun.json` (**not** gitignored) | app repo `prisma/` | present — demo-seed manifests for the two DBs |
| `tests/e2e-handover/` (suite, README, tools) | app repo | present, **uncommitted** for your review |
| Playwright output | inside the evidence folders only | — |
| Stopped process | `D:\lm-payshia\frontend` `next dev` on :3000, stopped at your request; its own `npm run dev` restarted it a minute later | nothing to restore |

## Final cleanup action

Cascades were verified row by row during the run (J3-43: a populated project deleted through the
UI left 0 rows in 13 dependent tables, invoice counters untouched). So the final cleanup is to
**drop the whole container**, not delete rows one by one. Nothing in it is needed after the
report, except to verify fixes.

Not done yet: dropping the container is irreversible, and you may want to look at the data or
re-test fixes against it first. When you're ready:

```bash
# stop the app server on :3200 (PowerShell: Get-NetTCPConnection -LocalPort 3200 | % { Stop-Process -Id $_.OwningProcess })
docker rm -f vega-e2e-pg                                   # removes both test databases
rm .env.local prisma/.demo-seed.json prisma/.demo-seed.vega_e2e.json prisma/.demo-seed.vega_e2e_rerun.json
# keep tests/e2e-handover/ if you want to commit the suite
```

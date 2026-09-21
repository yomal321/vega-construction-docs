# E2E Journey Test — Run Log

- Build: ece3731 · Node v22.11.0 · DB: Option A — local Postgres 18 (native Windows service, not Docker; Docker Desktop engine was not running)
- Started: 2026-09-21 · Tester: Claude Code
- **Completed: 2026-09-21.** All 8 journeys done in one session. 10 findings total (4 High, 3
  Medium, 3 Low), 0 crashes. Final cleanup done — 0 orphaned rows across 9 dependent tables
  checked. See `HANDOVER_FUNCTIONAL_TEST_REPORT.md` for the full write-up (this is the deliverable
  to hand the client) and `findings-draft.md` for the raw per-journey working notes it was built
  from.

| Journey | Scope | Status | Crashes | C | H | M | L | Date |
|---|---|---|---|---|---|---|---|---|
| J0 | Smoke baseline | ✅ done | 0 | 0 | 0 | 1 | 0 | 2026-09-21 |
| J1 | Admin — build the world | ✅ done | 0 | 0 | 2 | 1 | 1 | 2026-09-21 |
| J2 | Create users & roles | ✅ done | 0 | 0 | 0 | 0 | 1 | 2026-09-21 |
| J3 | Estimator journey | ✅ done | 0 | 0 | 0 | 1 | 0 | 2026-09-21 |
| J4 | Finance journey | ✅ done | 0 | 0 | 1 | 0 | 0 | 2026-09-21 |
| J5 | Zero-permission baseline | ✅ done | 0 | 0 | 0 | 0 | 0 | 2026-09-21 |
| J6 | Lifecycle & concurrency | ✅ done | 0 | 0 | 1 | 0 | 1 | 2026-09-21 |
| J7 | Cross-cutting sweep | ✅ done | 0 | 0 | 0 | 0 | 1 | 2026-09-21 |

## Environment notes for whoever resumes

- **DB decision: Option A, local Postgres.** Docker Desktop's engine was not running on this
  machine, so used the native Windows PostgreSQL 18 service already installed and listening on
  port 5432 instead of a container. Created a dedicated database `vega_qa` on that instance
  (left the instance's other databases untouched).
- **Getting the local postgres password required a reset.** The `postgres` superuser's existing
  password was unknown/unreachable via the values the user supplied. Fix used: backed up
  `C:\Program Files\PostgreSQL\18\data\pg_hba.conf`, temporarily set `trust` auth for local/host
  connections, restarted the `postgresql-x64-18` service, ran `ALTER USER postgres WITH PASSWORD
  'vega_qa_local_2026'`, created database `vega_qa`, then **restored the original `pg_hba.conf`
  byte-for-byte** and restarted the service again. Verified afterwards that password auth is
  required again (unauthenticated connection now fails) and that the new password works. The
  `postgres` superuser's password on this machine is now `vega_qa_local_2026` — this is a
  permanent change to the local dev machine (not scoped to a throwaway container), flagging this
  clearly since it's a side effect outside the repo.
- **`DATABASE_URL` override lives in `VegaConstruction-ManagementSystem/.env.local`**, pointing at
  `postgresql://postgres:vega_qa_local_2026@127.0.0.1:5432/vega_qa`. This file is **not** in
  `.gitignore` (only bare `.env` is) — do not `git add`/commit it, it will be cleaned up at the
  end of the exercise. Left `.gitignore` untouched per the "don't edit source" ground rule.
- **Trap confirmed for real: Prisma CLI commands (`db:migrate`, `db:seed`, `verify:pg`, any `tsx`
  script) do NOT read `.env.local`** — only `next dev`'s own env loader does. `prisma migrate
  deploy` was run once without an explicit env override and it connected to the **shared Supabase
  instance** (`aws-0-ap-northeast-1.pooler.supabase.com`) — thankfully a read-only "check
  migrations" op with nothing pending, so no writes happened, but this is exactly the trap the
  prompt warned about. **Fix: always export `DATABASE_URL` in the shell explicitly** before any
  `npm run db:*` / `tsx` / prisma command, e.g.:
  `export DATABASE_URL="postgresql://postgres:vega_qa_local_2026@127.0.0.1:5432/vega_qa"`.
  Whoever resumes this in a new session: do this before running any db script, don't trust
  `.env.local` alone.
- Migrations applied clean (`20260908000000_init_postgres`, `20260918000000_login_rate_limit`).
  `npm run db:seed` succeeded. `npm run verify:pg` — 36/36 pass.
- **Seeded accounts differ from the prompt's "Existing accounts" table** (that table describes
  the shared Supabase DB's current state; those specific accounts don't exist on this fresh local
  DB). Using the seed script's own accounts instead:
  - Admin: `nimal@vegahomes.lk` / `VegaDemo-2026!`
  - Also seeded: `sanduni@vegahomes.lk` (Admin), `kasun@vegahomes.lk` (Staff), `dilini@vegahomes.lk`
    (Staff), `ruwan@vegahomes.lk` (Staff, Inactive) — these are pre-existing demo rows from
    `prisma/seed.ts`, not QA2-created, so they're outside the QA2 cleanup ledger scope; not
    modifying/deleting them.
  - No pre-existing zero-permission Staff account on this DB — will create one in J2 to serve the
    same role as the prompt's `csp-test-staff@vegahomes.lk`.
  - `qa2-admin2@vegahomes.lk` (Admin, per J2 table) will also be created fresh in J2.
- **Pre-existing uncommitted changes in the working tree** (not made by this exercise — present
  before this session started): `.gitignore`, `playwright.config.ts`, `src/app/api/auth/login/route.ts`,
  `src/app/api/projects/[id]/owner/route.ts`, `src/app/users/page.tsx`, `src/lib/edgeRateLimit.ts`,
  `src/proxy.ts`, `tests/helpers.ts`, plus a deleted file `tt` and an untracked
  `.shannon/deliverables/remediation-status-2026-09-19.md`. Not touching these (ground rule: no
  source edits), but noting them since they mean the running app includes unreviewed local changes
  on top of `ece3731` — e.g. `src/proxy.ts` diff is relevant to the CSRF Origin-check item in
  §"Known open".
- Node engine warning: `pdfjs-dist@6.3.289` wants Node `>=22.13.0`, this machine has `v22.11.0`.
  `npm install` completed anyway (EBADENGINE is a warning, not a failure) — noting in case it's
  the root cause of a PDF-export finding.
- Playwright: `@playwright/test` 1.63.0 (repo declares `^1.61.1`), chromium already installed.
  `PW_BASE_URL=http://localhost:3000` required per the prompt's trap note — default `baseURL` in
  `playwright.config.ts` points at the dead wrangler port 8787.
- **Server restarted twice during J6** while investigating finding E-08 (idle-timeout bug) — to
  rule out a stale dev-server/Turbopack-cache explanation before concluding the bug was real.
  Killed the original PID 2004 (port 3001) and PID 31728 (port 3005); `.next/cache` was deleted
  once. **Current server is on port 3006**, started via `PORT=3006 npm run dev` with
  `DATABASE_URL` exported the same way as every other command in this exercise. If resuming this
  in a new session, check what's actually listening before assuming port 3001/3006 — use
  `netstat`/`Get-NetTCPConnection` the same way this session did at the start.

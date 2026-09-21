# Backend Audit 2026-09 — Index

- **Started:** 2026-09-21
- **Build:** `15c799b` **+ uncommitted working-tree changes** (`git status` at audit start showed
  5 modified files — `src/proxy.ts`, `src/app/api/auth/login/route.ts`,
  `src/app/api/projects/[id]/owner/route.ts`, `src/lib/edgeRateLimit.ts`, `.gitignore` — plus
  several untracked doc files and this audit's own fixture scripts. Every architecture file this
  audit read was read off the live working tree, so the analysis below already reflects those
  uncommitted changes. Anyone reproducing this audit from a fresh clone of `15c799b` alone will
  see different behaviour in those 4 source files — commit or stash before comparing.)
- **DB:** **Option A — local Postgres.** Not Docker (Docker Desktop's daemon isn't running on
  this machine) — a native PostgreSQL 18 Windows service was already running on `127.0.0.1:5432`
  from a prior QA session, with a scratch database `vega_qa` and `VegaConstruction-ManagementSystem/.env.local`
  already pointing `DATABASE_URL` at it (see that file's own header comment — it predates this
  audit, left by `doc/Front end/PRE_HANDOVER_E2E_JOURNEY_PROMPT.md`'s session). Reused as-is.
  **Trap confirmed and worth recording:** the Prisma CLI (`prisma migrate status`, `db:seed`, …)
  does **not** read `.env.local` — only `next dev` does. Every CLI invocation in this audit passed
  `DATABASE_URL=...` explicitly on the command line; a bare `npx prisma migrate status` silently
  targets the shared Supabase instance in `.env` instead. This is a real footgun for whoever
  inherits this repo and is worth a one-line note in the README, not just this audit.
- **Server:** a Next dev server for this exact project directory was **already running** (PID
  2716, started earlier the same day) on **port 3006**, not 3000 — port 3000 on this machine is
  held by an unrelated project (`Smart Gmail Assistant`, confirmed via `Get-CimInstance
  Win32_Process`). Reused rather than killing someone else's process or fighting for the port.
  **All requests below were sent to `http://localhost:3006` with `Origin: http://localhost:3006`
  on mutating requests.** If you resume this audit, check what's listening on 3006 before assuming
  it's still this server.
- **Fixture accounts/data created this session** (via `tests/audit/2026-09/fixtures.mts`, run directly
  against `vega_qa` with Prisma — idempotent, safe to re-run): `yomaltheekshana66@gmail.com` /
  `yomal8899` (Admin), `csp-test-staff@vegahomes.lk` / `yomal8899` (zero-perm Staff),
  `sec-staff-a@vegahomes.lk` / `SecFixture#2026` (Staff, role "SEC Project Access" =
  projects:view/create/edit, owns `SEC Project A`), `sec-staff-b@vegahomes.lk` / same password
  (same role, owns `SEC Project B`), `sec-inactive@vegahomes.lk` / same password (Staff, status
  Inactive). Each SEC project has one stage+milestone, one ActivityItem+RecipeComponent, one
  BsrLine, one BasicPriceItem draft, one BaseItem (basic-rate row), one Expense+ExpensePayment —
  see the script for exact ids (`sec-project-a`/`sec-project-b`, child ids prefixed with the
  project id). The pre-existing local seed (`nimal@`/`sanduni@`/`kasun@`/`dilini@`/`ruwan@`,
  projects `p1`-`p4`) was left in place, untouched — it's the old demo dataset the *frontend* QA
  prompt's fixtures already assume, and Option A means nothing here needs cleaning up regardless.

## Progress

| Family | File | Routes | Verdict | Crit/High/Med/Low | Date |
|---|---|---|---|---|---|
| 1 Auth & session | [01-auth-session.md](01-auth-session.md) | 5 | 🟠 NEEDS-FIX | 0/0/0/0 (see `X-08`, cross-cutting) | 2026-09-21 |
| 2 Projects core & access | [02-projects-access.md](02-projects-access.md) | 5 | 🟢 PASS | 0/0/0/0 | 2026-09-21 |
| 3 Stages & milestones | [03-stages-milestones.md](03-stages-milestones.md) | 3 | 🟠 NEEDS-FIX | 0/1/0/0 | 2026-09-21 |
| 4 Expenses & payments | [04-expenses-payments.md](04-expenses-payments.md) | 5 | 🔴 BLOCKER | 1/1/0/0 (+1 Info) | 2026-09-21 |
| 5 BSR, items & recipes | [05-bsr-items-recipes.md](05-bsr-items-recipes.md) | 5 | 🟠 NEEDS-FIX | 0/0/2/0 | 2026-09-21 |
| 6 Project Basic Price | [06-project-basic-price.md](06-project-basic-price.md) | 3 | 🟠 NEEDS-FIX | 0/1/0/0 | 2026-09-21 |
| 7 Project Basic Rate | [07-project-basic-rate.md](07-project-basic-rate.md) | 6 | 🔴 BLOCKER | 1/0/0/0 | 2026-09-21 |
| 8 Global catalog | [08-global-catalog.md](08-global-catalog.md) | 6 | 🔴 BLOCKER | 0/2/0/0 | 2026-09-21 |
| 9 Global lookup tables | [09-lookup-tables.md](09-lookup-tables.md) | 6 | 🟠 NEEDS-FIX | 0/0/1/0 | 2026-09-21 |
| 10 Suppliers & sub-contractors | [10-suppliers.md](10-suppliers.md) | 6 | 🟢 PASS | 0/0/0/0 | 2026-09-21 |
| 11 Users, roles & permissions | [11-users-roles.md](11-users-roles.md) | 8 | 🟡 PASS-WITH-NOTES | 0/0/1/0 | 2026-09-21 |
| 12 Reporting & misc | [12-reporting-misc.md](12-reporting-misc.md) | 4 | 🟠 NEEDS-FIX | 0/0/1/0 | 2026-09-21 |

**All 12 families and all 13 sweeps complete as of 2026-09-21.** See
`BACKEND_SECURITY_REPORT.md` for the consolidated final deliverable.

64 route files confirmed by inventory (S13) against the 12-family table — all accounted for, no
coverage gap.

## Cross-cutting sweeps (S1–S13)

### S1 — `rewritePlaceholders` correctness and completeness — 🟡 DONE, one latent + one live-safe gap
Unit-tested directly (`tests/audit/2026-09/s1-rewrite-placeholders.mts`, no server needed) against every
shape S1 asks for. Results:

| Case | Output correct? | Reachable by any real query in `src/**`? |
|---|---|---|
| `?1` bound twice + trailing bare `?` (the auth-critical case) | ✅ Correct — `$1,$1,$2` | **Yes — this is `projectAccessClause` in production use on 14 call sites (S4).** Verified correct by direct unit test of the exact SQL shape those call sites emit. |
| Bare `?` inside `'...'`, `"..."`, `--`, `/* */` | ✅ Correctly skipped in all four | Yes, routinely | 
| Reserved/uppercase word already wrapped in `"..."` (e.g. `"ORDER"`) | ✅ Preserved verbatim | Yes (`dashboard/route.ts`'s `s."order"`) |
| Bare camelCase identifier (`projectId`, `lockedUntil`) | ✅ Quoted correctly | Yes, everywhere |
| `'...'` string containing a literal `"` | ✅ Not confused with identifier-quote start | Plausible (a free-text field value) |
| **Dollar-quoted string `$$...$$` / `$tag$...$tag$`** | ❌ **Broken** — `$` has no special handling at all; a `?` *inside* the dollar-quoted literal is rewritten to `$n` as if it were a real placeholder, corrupting the literal's contents. | **No** — grepped `src/lib/**` and `src/app/api/**` for `$$`/`$tag$`-shaped literals; the only hits are this file's own explanatory comments. No hand-written query in this codebase uses Postgres dollar-quoting. |
| **`E'...'` escape-string with a backslash-escaped quote** | ❌ **Broken**, and worse than the dollar-quote case: `E` gets quoted as an identifier (`"E"`), then the string-skip logic — which only understands the SQL-standard `''` doubled-quote escape, not `\'` — treats `\'` as closing the string early. In the tested case this desyncs the rest of the scan badly enough that the query's own real trailing `?` is **never converted to a placeholder at all** (stays literal `?` in the emitted SQL, `paramCount` undercounts). | **No** — grepped for `E'` (excluding this file's comment) across the same scope; zero hits. This codebase never writes `E''` literals. |
| **Nested block comment `/* /* */ */`** | ❌ **Broken** — comment-skip exits at the *first* `*/`, so `still comment? */ where id = ?` becomes live SQL text; a spurious `?` from the leftover word `comment?` gets counted as an extra placeholder. In this shape the corruption is at least loud: it inflates `paramCount` past the real bind-value count, which trips `compile()`'s mismatch check → a 500, not a silent bad bind. | **No** — no nested block comments anywhere in `src/**`'s raw SQL (checked by inspection; a single dev-authored comment nesting a comment inside itself would be unusual and none does). |

**Verdict:** the tokenizer's three documented gaps are all real and all reproduced, but **none is
reachable by any query this codebase actually sends** — every gap requires a SQL literal shape
(`$$…$$`, `E'…'`, nested `/* */`) that no hand-written query here uses, and none of these shapes
can be introduced by request data (bound values never get concatenated into SQL text — see S3).
Rate this **Low/Info as shipped, but flag it loudly for whoever maintains this file next**: the
three gaps are exactly the shapes a future contributor could introduce without realizing the
tokenizer can't see them (e.g. adding a dollar-quoted literal to make a long string easier to
write), and the failure mode ranges from "SQL corruption that throws" (nested comment — safe-ish)
to "SQL corruption that silently drops a placeholder" (E-string — not safe). The one shape that
*is* live and load-bearing today — `?1` reused, trailing bare `?` — is correct, unit-tested, and
confirmed working end-to-end via the family 2/4/6 audits' IDOR probes (owner-vs-cross-project
access actually resolves the right branch in every case tested).

### S2 — Bind-count mismatch reachability — 🟢 PASS
`compile()` throws a plain `Error` (→ generic 500 via `apiRoute`) on any placeholder/value-count
mismatch. Two call sites build a variable-shape query from request-shaped data:
`projects/[id]/route.ts:91` and `expenses/[expenseId]/route.ts:33` (`update … set
${fields.join(', ')}`), and `suppliers/price-comparison/item/route.ts:90` (`in (${ids.map(() =>
'?').join(',')})`). Read all three: the `fields` array only ever pushes **hardcoded literal**
`'col = ?'` strings gated by `patch.x !== undefined` checks, one `values.push()` per `fields.push()`
— count always matches by construction, no request key ever becomes a column name. The `IN (...)`
site's placeholder count is `baseItemIds.length`, bound with `...baseItemIds` — same array, same
length, always matches; that array is never empty when reached (an earlier 404 guards it). No
path found where request input can desync a placeholder count from a bind-value count.

### S3 — SQL interpolation sweep — 🟢 PASS
Every `${...}` inside a template literal under `src/app/api/**` and `src/lib/**` that is actually
inside a `.prepare()` SQL string (grepped and read every hit; the other ~85 files' `${}` hits are
all React JSX, error-message strings, PDF/Excel export labels, or ID generation — no SQL). Full
classification:
- 14 call sites interpolate `projectAccessClause(session, 'p.id', 'p.ownerId')` — server-generated
  clause text, no request data.
- `notifications/route.ts` interpolates `windowStart`/`dueSoonCutoff` (server-computed
  `Date.now() ± fixed-days` ISO strings, explicitly commented as deliberate — colliding with
  `projectAccessClause`'s hardcoded `?1` if bound instead) and the hardcoded constant
  `MAX_NOTIFICATIONS = 20` into `limit`. No request data.
- `projects/[id]/route.ts` and `expenses/[expenseId]/route.ts` interpolate `fields.join(', ')` —
  see S2, hardcoded literals only.
- `price-comparison/item/route.ts` interpolates a `?`-per-array-element placeholder list for an
  `IN (...)` — see S2.
**No route builds `order by`, `limit`, a table name, or a column name from request-controlled
data.** No SQL-injection-via-string-interpolation surface found anywhere in this codebase.

### S4 — `projectAccessClause` call-site sweep — 🟢 PASS
All 14 call sites (grepped exhaustively): every one passes `'p.id'` (table-qualified) as
`idColumn` and `'p.ownerId'` as `ownerColumn`. **Zero unqualified call sites** — the
`dashboard/route.ts` bug the prompt describes as having happened "once" is not present in the
current codebase; `dashboard/route.ts` itself no longer calls `projectAccessClause` at all (see
family 12 — it deliberately queries every project unscoped, by design, for its company-wide
rollup — see that report for the finding this raises on its own).

### S5 — Guard sweep — 🟢 automated PASS, manual cross-check ongoing per-family
`node scripts/audit-guards.js` → `Scanned 64 route files. OK — no unguarded handlers.` (exit 0).
Per the prompt's own warning, this only proves a guard call *exists*, not that it's the *right*
module/action — that check is being done per-route as each family's matrix is built (see each
family report's "Guard in source" column). Family 1 found nothing wrong; carrying forward.

### S6 — Session revocation matrix — 🟡 covered in family 1 (see that report)

### S7 — CSRF Origin check — 🟢 PASS
Confirmed live: `POST /api/auth/login` with no `Origin` header → `403 {"error":"Cross-origin
request rejected"}`, stamped with full security headers, **before** the handler runs (proves the
check really does sit ahead of `PUBLIC_PATHS`, not just in code review). Same request with
`Origin: http://localhost:3006` (matching the server's own host) → normal 200 login flow. Method
Override / preflight / `null`-origin bypass paths not yet probed live — carrying forward to
family 1's revisit, since `isSameOriginRequest` only reads `request.headers.get('origin')` and
does a straight host comparison, with no special-case for any of those — reading the source, none
of the three should have any effect (a `null` origin fails `new URL(origin)` and is treated as
present-but-invalid → still compared, `new URL('null').host` is `''` ≠ real host → rejected; a
`X-HTTP-Method-Override` header changes nothing since `request.method` is what Next/Node actually
received, not a header value the app trusts).

### S8 — `x-real-ip` trust boundary — 🟠 confirmed open, unverifiable from this repo
Two separate questions, per the prompt:
1. **Does the app itself validate `x-real-ip`?** No — `clientIpFrom()`
   (`src/app/api/auth/login/route.ts:24-26`) is `headers.get('x-real-ip')?.trim()`, no check of
   any kind. Confirmed live: `curl -H 'X-Real-Ip: 9.9.9.9'` against `/api/auth/login` running
   under plain `next dev` (no Traefik in front) is accepted and would key the throttle on
   `ip:9.9.9.9` — trivially forgeable in this topology.
2. **Does the deployed topology prevent that?** This is the actual question — the app's own
   comment (`clientIpFrom`'s header) asserts Traefik sets this from the raw socket, never by
   copying a client header. `deploy/helm/templates/ingress.yaml` in this repo is a bare k8s
   `Ingress` resource with no `forwardedHeaders`/trusted-IP configuration of any kind — that
   setting lives in Traefik's own controller-level static/dynamic config, which is **not part of
   this repository** (it's whatever the cluster's Traefik installation was configured with).
   `deploy/helm/charts/vega-web/templates/service.yaml` **does** confirm `type: ClusterIP` with no
   `hostNetwork`/`nodePort`, so the pod cannot be reached bypassing the Ingress from inside the
   cluster's own network model — that part (`AZURE_SECURITY_RUNBOOK.md` Task 3.2) is confirmed.
   Whether Traefik's *own* config actually strips/regenerates `X-Real-Ip` (Task 3.1) **cannot be
   confirmed or denied from source in this repository** — this is exactly the state
   `AZURE_SECURITY_RUNBOOK.md` already records it in ("OPEN"). **Still open, not re-litigated as
   new; this audit did not find anything to change that status.** Whoever hands over
   infrastructure must supply the live Traefik config for this to ever close.

### S9 — Transport & secrets — 🟠 one confirmed open item, otherwise clean
- `rejectUnauthorized: false` — confirmed, `src/lib/pg.ts:302`, exactly where the prompt says,
  with the code's own TODO ("tighten this to a pinned CA before this handles production data").
  **Still open. Not new.** MITM-on-the-DB-connection risk; severity depends entirely on whether
  the Postgres endpoint (Supabase pooler in `.env`, or the in-cluster Postgres per
  `deploy/helm/charts/vega-infra`) is reached over a network segment an attacker could plausibly
  sit on — worth the client's own risk call, not a blanket Critical.
- Secrets: `.gitignore` covers `.env` (line 6); `git ls-files` confirms no `.env*` is tracked.
  `SESSION_SECRET` is referenced only in `src/lib/sessionToken.ts` (server-only module) — grepped
  for `NEXT_PUBLIC_` combined with secret/password/key naming, zero hits. No source maps ship
  (`productionBrowserSourceMaps` unset → defaults false). `x-powered-by` absent on every response
  probed (F-01-05 still holds).

### S10 — Security headers — 🟢 PASS
Confirmed live on both a `withSecurityHeaders` short-circuit branch (`POST` with no Origin → 403)
and a normal routed response (login 200): HSTS, `X-Content-Type-Options: nosniff`,
`Referrer-Policy`, `X-Frame-Options: DENY`, `Permissions-Policy`, a full enforcing CSP with a
fresh nonce every request (`nonce-` value differs across all requests sampled), and
`Cache-Control: no-store` present on the `/api/auth/*` responses (via `next.config.ts`'s
`AUTH_NO_STORE_HEADERS`, confirmed source-side — note this only applies on the routed-response
path per that file's own comment; the direct 403 short-circuit doesn't carry it, which is fine,
nothing cacheable is in that body). `'unsafe-eval'` is present in this session's CSP because the
server under test is `next dev` — confirmed by reading `buildCsp()` that this is gated strictly on
`opts.dev`, itself `process.env.NODE_ENV !== 'production'` in `proxy.ts` — not reachable in a
production build by construction. Not independently verified against an actual `next build`
output in this session (would require a full production build+start cycle) — flagged as the one
part of S10 taken on source-reading confidence rather than a live production-mode probe.

### S11 — Dependency & CI gate — 🟢 PASS, and it really gates
`node scripts/audit-gate.js` → 3 high findings (`@prisma/config`, `deepmerge-ts`, `prisma`), all
transitive and all present in the script's own documented-accepted allowlist → exit 0.
`node scripts/audit-guards.js` → exit 0 (S5). Read `.github/workflows/ci.yml`: both commands run
as ordinary steps with no `continue-on-error`, on `push`/`pull_request` into `production` and
`main` — a non-zero exit from either **fails the job**, which fails required-check-gated merges.
This is a real gate, not a report-only step.

### S12 — Migration replay — 🟢 PASS, full from-zero replay completed
Stood up a genuinely separate scratch database (`vega_migration_replay`, created and later
dropped via `tests/audit/2026-09/create-replay-db.mts` / `drop-replay-db.mts` — not the `vega_qa`
database this audit's own fixtures live in, so no risk to other families' work) and ran the full
chain from true zero:
1. `prisma migrate deploy` against the brand-new, empty database → both migrations
   (`20260908000000_init_postgres`, `20260918000000_login_rate_limit`) applied cleanly, no drift.
2. `prisma/seed.ts` → `Seed complete.` no error.
3. `prisma/reset-and-reseed.ts` (the exact script `F-01-08` broke) → `Reset + reseed complete —
   users/roles left untouched, everything else rebuilt across 4 projects (p1-p4).` No error.
4. `scripts/verify-pg.ts` (a pre-existing test suite this audit hadn't run until now) →
   **36/36 assertions pass**, covering the identical `rewritePlaceholders()` shapes `S1` tested
   by hand above (independent corroboration, same conclusions) *plus* a live-Postgres section
   that directly asserts `batch()` atomicity (`"batch() throws on a failing statement"`,
   `"batch() is atomic — the good insert rolled back too"`) — further corroborating the
   concurrency-safety conclusions in families 6 and 8.

**`F-01-08` status: confirmed NOT reproduced** — a genuine from-zero migrate+seed+reset-seed
cycle completes without error on the current migration history. (Note: this doesn't retroactively
prove it never happened; it confirms the *current* migration set is internally consistent.)

### S13 — Route inventory — 🟢 PASS, 64/64 accounted for
`find src/app/api -name route.ts | wc -l` → **64**, matching the prompt's count exactly. Every
file maps onto exactly one row of the 12-family table (spot-checked the mapping; no orphan files,
no file claimed by two families). Checked every directory under `src/app/api` for the "empty
route directory" (X-04) pattern the prompt calls out by name (`dashboard/cashflow/` as the
historical example) — **none found**; every directory under `src/app/api` resolves to at least one
`route.ts` somewhere beneath it. That specific historical instance is gone from the current tree.

## Cross-cutting findings (pattern spans families — described once here)

### X-08 — `/api/healthz` and `/api/ready` are gated by the global session check, defeating their purpose as k8s probes
- **Severity:** **Critical for deployability** (not a data-exposure issue, an availability one —
  see the note on rating below).
- **Confidence:** Confirmed, live, both endpoints, both with and without a cookie.
- **Class:** Availability / Configuration
- **CWE:** CWE-703 (Improper Check or Handling of Exceptional Conditions) — closest fit; this is
  fundamentally an authorization gate applied somewhere it structurally cannot be satisfied by its
  own intended caller.
- **Location:** `src/proxy.ts:15` (`PUBLIC_PATHS = ['/login', '/api/auth/login']`) and the `if
  (!token)` / `resolveSession` branches at `src/proxy.ts:86-101`, which apply to every path the
  matcher covers **except** those two. `src/app/api/healthz/route.ts` and
  `src/app/api/ready/route.ts` themselves are correct and require nothing — the handler is never
  reached.
- **Request:**
  ```http
  GET /api/healthz HTTP/1.1
  Host: localhost:3006
  ```
  (no cookie — exactly what a kubelet `httpGet` probe sends)
- **Response:** `401 {"error":"Not authenticated"}` for both `/api/healthz` and `/api/ready`.
  With a valid Admin session cookie, `/api/healthz` correctly returns `200 {"status":"ok"}` — the
  handler logic itself is fine, only reachability is broken.
- **Expected:** `200` unconditionally (`healthz`) / `200`-or-`503` based on DB reachability
  (`ready`), from an orchestrator that never has and never should have a session cookie.
- **Impact:** `deploy/helm/charts/vega-web/templates/deployment.yaml:61-66` configures the
  kubelet's `livenessProbe` at `/api/healthz` and `readinessProbe` at `/api/ready`, both bare
  `httpGet` with no header injection of any kind. In the deployed topology every pod would report
  `401` to both probes from the moment it starts: the readiness probe failing means the Service
  never gets an endpoint for that pod — **the app would never become reachable at all** — and the
  liveness probe failing means kubelet restart-loops the container indefinitely. This is not a
  theoretical risk; it is the exact, unconditional behaviour of the code as written, and would be
  caught the moment anyone deploys this chart with the probes enabled.
- **Independent corroboration:** this exact defect was found independently by the *frontend* audit
  currently in progress in this same repo (`doc/e2e-journey-report/findings-draft.md`, finding
  `E-00`, rated Medium there — that audit's lens is UI/journey correctness, not deployment
  blast-radius, which is why the severity differs). Reported here under this backend audit's own
  numbering (`X-08`) because it belongs to `src/proxy.ts`, the shared gate every route family in
  this audit depends on, and because this audit's job is specifically to reason about what the
  server permits at the HTTP layer — same root cause, not double-counted, cross-referenced rather
  than re-discovered from scratch.
- **Severity note:** rated by deployment impact, not data exposure — per the report format's own
  instruction to weight severity by impact on *this* deployment. An internal 20-user tool that
  cannot come up at all is arguably worse for handover than most of the IDOR-class findings below,
  which at least require an authenticated account to exploit. This is why it's called out here at
  the top of cross-cutting findings rather than folded quietly into family 1.
- **Suggested fix:** add `/api/healthz` and `/api/ready` to `PUBLIC_PATHS` in `src/proxy.ts`
  (describe only, not implementing — ground rule #1).

## Known-open / already-fixed tracking (updated as families confirm status)

| Item | Status per prompt | This session's finding |
|---|---|---|
| `AUTHZ-VULN-03` (payment TOCTOU) | Known open | ✅ **Confirmed FIXED** — family 4, live concurrent-request test, holds. |
| `AUTHZ-VULN-01` (project-scoped double-promotion) | Known open | ✅ **Confirmed FIXED** — family 6, live sequential AND concurrent test, holds. Also corroborated by an unrelated earlier-session Postgres log entry (`base_items_promotedFromId_key` violation) showing the same guard firing for real. |
| `AUTHZ-VULN-02` (global-endpoint double-promotion / cross-endpoint) | Known open | 🟠 **Confirmed PARTIALLY open** — family 8, live-reproduced 13/15 stress rounds. No duplicate rate item is ever created (DB constraint holds), but the global promote endpoint throws an uncaught 500 under a race the project-scoped sibling handles cleanly. |
| `F-04-01` (negative payment) | Known open | ✅ **Confirmed still open** — family 4, live reproduction. |
| `X-08`-adjacent healthz/ready gate | Not previously in either list (found independently by the sibling frontend/E2E audit as `E-00`) | ✅ Confirmed, cross-cutting. |
| `F-03-04` (unbounded `stages` collection input) | Known open | Not independently re-verified this session — no route in families 1-12 was found constructing an unbounded per-request collection write the way the original finding describes; if this pattern still exists it wasn't in a route this audit's fixtures happened to exercise. Not closed, just not re-confirmed. |
| `F-02-01` (ROI must use `expensePaid` not `expenseCommitted`) | Known open | Confirmed by reading `dashboard/route.ts` (family 12): `Overall ROI (paid basis)` is explicitly computed from `expensePaid`, not `expenseCommitted` — reads correct in current code. Not independently live-recomputed against a hand-calculated figure this session (deferred, see family 12 and F below). |
| `F-01-08` (Prisma schema drift breaking `db:reset-seed`) | Known open | ✅ **Confirmed NOT reproduced** — `S12`, a full from-zero `migrate deploy` + `seed` + `reset-and-reseed` cycle against a genuinely fresh database completed without error. |
| Everything else in Known Open / Already Fixed | Verified where a family touched it (see each family report); anything not explicitly mentioned in a family report was not re-tested this session. |

## Handover readiness (living section — updated after every family)

**Must fix before the client sees this:**
1. `X-08` — healthz/ready probe gate (above). Blocks the k3s deployment from ever going Ready.
2. `F-04-01` (family 4, confirmed **still open**, live-reproduced) — negative payment amount
   defeats the overpayment guard and corrupts paid/outstanding/ROI totals. Critical.
3. `M-04-01` (family 4, new instance of the same pattern) — expense creation accepts a negative
   `amount`. High.
4. `M-06-01` (family 6) — Basic Price draft/promotion `price` accepts negative values,
   propagating into a promoted Basic Rate `rate` and every recipe that multiplies against it.
   High.
5. `M-03-01` (family 3) — `Stage.value` override accepts a negative number, which **actively
   defeats** the over-budget guard's own arithmetic rather than just being unvalidated. High.
6. `M-05-01` (family 5) — `BsrLine.qty` accepts a negative value. Medium.
7. `F-07-01` (family 7) — Basic Rate `rate` accepts a negative value via the **primary**
   create/edit routes (the single most-used rate-edit path in the product). Critical — highest
   blast radius of this entire cluster.
8. `F-08-01` (family 8) — same field, same defect, via the global counterpart route. Critical
   (cross-referenced with `F-07-01`, not double-counted).
9. `AUTHZ-VULN-02` (family 8, confirmed partially open) — the global Basic Price promote endpoint
   has no unique-violation catch; racing it against the project-scoped endpoint throws an
   uncaught 500 (no data duplication — the DB constraint holds). High.
10. `M-05-02` (family 5) — duplicate Activity Item code within a project surfaces as an uncaught
    500 instead of a clean 409. Medium.
11. `M-09-01` (family 9) — the same TOCTOU/uncaught-unique-violation shape as `AUTHZ-VULN-02`,
    on lookup-table creation (`trades`, and by identical code shape `categories`/`units`).
    Medium.
12. `M-11-01` (family 11) — `users.email` uniqueness is case-sensitive; an Admin can create a
    duplicate-looking account differing only by letter case. Medium, Admin-only reach.

**Pattern worth a single global fix rather than seven (and counting) per-route patches:** every
money-accepting field audited across every family that has one (`expenses.amount`,
`expense_payments.amount`, `basic_price_items.price`, `Stage.value`, `BsrLine.qty`,
`base_items.rate` — both the project-scoped and global routes) has the identical gap: a bare
`z.number()` with no lower bound. The one exception, and useful positive-control evidence that
this is a known, fixable pattern in this exact codebase: `POST /api/projects/[id]/basic-rate/import`
(family 7) correctly rejects `rate <= 0` at the row level. Recommend fixing this once, at
whatever shared validation layer makes sense (a `positiveMoney()` Zod helper reused everywhere),
rather than continuing to chase it route by route.

**Second pattern worth a single fix — the missing-unique-violation-catch shape recurs three
times** (`AUTHZ-VULN-02` in family 8, `M-05-02` in family 5, `M-09-01` in family 9), always the
same root cause: a `SELECT`-then-`INSERT` (or an `INSERT` relying on a DB constraint with no
`try/catch`) where a sibling route elsewhere in the same codebase (`users`/`roles`'s `POST`
handlers, the project-scoped promote route) already demonstrates the correct
catch-and-return-409/400 shape. Same recommendation: fix the pattern once, apply it everywhere
a `db.batch()`/`insert` can hit a real unique constraint.

**Should be disclosed in writing, not necessarily fixed before handover:**
- `X-09` (family 12) — `dashboard:view`/`payments:view` expose named, project-identifying
  company-wide data (project names, stage names, exact payment amounts) to any account holding
  that one permission, with no project-access requirement at all — confirmed live with a
  byte-identical response comparison between Admin and a single-project Staff account. This is a
  deliberate design per the code's own comments, not a code defect — the action item is a client
  sign-off decision (is this scope intended?), not a fix to apply blindly. If the answer is no,
  it becomes a real family-2-style scoping fix; if yes, it needs one line in the Role editor UI
  saying so.
- `S1`'s three tokenizer gaps (dollar-quoting, `E''` strings, nested comments) — not exploitable
  today, but a landmine for the next person who touches `src/lib/pg.ts` or adds a raw query with
  one of these literal shapes. Worth one paragraph in the handover doc pointing at this file.
- `S8`/AZURE_SECURITY_RUNBOOK Task 3.1 — Traefik's own trusted-hop config is outside this repo and
  was not (and cannot be, from source alone) verified this session. Needs a cluster-admin-side
  check, not a code check.
- `S9` — `rejectUnauthorized: false` on the DB TLS connection, with the code's own TODO to pin a
  CA. Known, not new, not fixed.
- `M-11-01` (family 11) — case-variant duplicate email accounts. Admin-only reach, low urgency.
- **bcrypt CPU exhaustion — now quantified, not just theoretical.** ~30 concurrent, unauthenticated,
  cheap login attempts measurably degraded whole-app latency (including `/api/healthz` itself)
  by roughly 200× for about two seconds (family 1, evidence #19). Not filed as a numbered finding
  because it's an inherent property of `bcrypt.compareSync` running synchronously on Node's
  single event loop thread, not a coding mistake with an obvious one-line fix — but it's real,
  it's unauthenticated, and it compounds `X-08`: once healthz/ready are made public (fixing
  `X-08`), a credential-stuffing burst against login could plausibly make the *liveness* probe
  itself time out. Worth a product decision (move bcrypt off the main thread via a worker pool,
  or accept the risk for an internal 20-user tool) rather than a silent fix.

**Knowingly accepted (no action needed):**
- `style-src 'unsafe-inline'` in the CSP (task 6.18) — deliberate, documented trade-off against
  framer-motion/react-toastify's runtime style injection.
- `S12` migration replay is only partially verified this session (see above) — flagged as a gap
  in *this audit's* coverage, not a product defect.

*(Family-level findings will be added here as each family report lands.)*

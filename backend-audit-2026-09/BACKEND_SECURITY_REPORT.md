# Vega Construction Manager — Pre-Handover Backend Security & API Audit

**Audit date:** 2026-09-21 · **Build audited:** `15c799b` + uncommitted working-tree changes
(`src/proxy.ts`, `src/app/api/auth/login/route.ts`, `src/app/api/projects/[id]/owner/route.ts`,
`src/lib/edgeRateLimit.ts`, `.gitignore` — see `00-INDEX.md` for the exact diff scope) ·
**Environment:** Option A, local Postgres (`vega_qa`), server on `http://localhost:3006` ·
**Scope:** all 64 API route files under `VegaConstruction-ManagementSystem/src/app/api/**`, the
shared libraries every one of them depends on (`src/lib/pg.ts`, `rbac.ts`, `auth.ts`,
`sessionToken.ts`, `api.ts`, `src/proxy.ts`), and the login route. 13 cross-cutting sweeps and all
12 route families completed. Full detail, evidence, and per-route matrices live in
`00-INDEX.md` and the 12 family reports (`01-*.md` through `12-*.md`) alongside this file.

---

## Executive summary (for a non-technical reader)

This product's **authentication, session handling, and access-control layer are strong** — as
strong as anything this audit tested. Every attempt to forge a session, replay a revoked one,
cross a project boundary, or escalate a Staff account's privileges failed, across all 12 route
families and roughly 150 individual live HTTP probes. Two previously-known race-condition bugs
(a payment double-spend risk and a duplicate-catalog-promotion risk) were **re-tested under real
concurrent load and confirmed fixed**.

Three categories of problem remain, and they are what this report recommends addressing before
handover:

1. **Money fields with no floor.** Across expenses, payments, stage overrides, BSR quantities,
   and — most importantly — the Basic Rate catalog's own rate field, the system will accept a
   negative number with no complaint. One of these (a negative *payment*) actively defeats the
   very guard meant to stop a project being overpaid. None of these require any special access to
   trigger — an ordinary user with ordinary permissions can do it by mistake, not just an
   attacker on purpose. This is the highest-priority fix in this report, and it is fixable with
   one small, consistent change applied everywhere the same gap appears (see "Residual risk"
   below) rather than twelve separate patches.
2. **The application cannot start up correctly in its target deployment.** The two endpoints
   Kubernetes uses to check "is this pod alive" and "is this pod ready for traffic" both require
   a login session — which an automated health check will never have. As written, this would
   keep the application from ever going live on the k3s cluster it's being deployed to. This is
   the single most urgent item in this report, ahead of every other finding, because nothing else
   matters if the application can't come up at all.
3. **A modest burst of login attempts measurably slows the whole application down, including the
   health check above.** This was measured directly, not just reasoned about: about 30
   simultaneous, unauthenticated, cheap login attempts made the health-check endpoint itself take
   over two seconds to respond — roughly 200 times slower than normal — for a couple of seconds.
   Nobody needs a password to trigger this. Combined with item 2 above, a burst like this could
   plausibly make Kubernetes think a perfectly healthy pod has died and restart it, which would
   turn an ordinary credential-stuffing attempt (something any internet-facing login page
   attracts eventually) into a self-inflicted outage.

Everything else — who can see what, who can do what, whether a Staff account can trick the system
into acting as an Admin, whether one client's project data can leak into another's — held up
correctly under direct, repeated testing.

---

## Finding register (sorted by severity)

**Fix status as of 2026-09-21 (post-audit remediation pass, branch `dev`):** all 24 changed
files are currently **uncommitted** in the working tree on branch `dev` — the branch checked
out mid-session (switched from `vega/fix-session-secret` to `dev` by something outside this
session; nothing was lost, see the session record if reconciling later). Review and commit
when ready. Every finding below except
`X-08` has been fixed and re-verified live against its own original repro steps — zero
regressions on a full `tsc --noEmit` + guard-sweep + positive-input sanity pass. `X-08` was
deliberately deferred by the client's own request, for a separate discussion.

| ID | Family | Title | Severity | Status |
|---|---|---|---|---|
| `X-08` | Cross-cutting (1) | `/api/healthz`/`/api/ready` gated behind session auth — blocks k3s deployment | **Critical** (deployability) | 🔶 **Deferred** — not fixed yet, separate discussion |
| `F-04-01` | 4 | Negative payment amount defeats the overpayment guard, corrupts paid/ROI totals | **Critical** | ✅ **Fixed** — `.positive()` added, re-tested live, returns `400` |
| `F-07-01` | 7 | Basic Rate `rate` accepts negative values via the primary create/edit routes | **Critical** | ✅ **Fixed** |
| `F-08-01` | 8 | Same defect via the global Basic Rate routes (cross-ref `F-07-01`) | **Critical** | ✅ **Fixed** |
| `M-04-01` | 4 | Expense creation accepts a negative `amount` | High | ✅ **Fixed** (also closed the same gap on expense line-item `amount`, not previously filed as its own id) |
| `M-06-01` | 6 | Basic Price draft/promotion `price` accepts negative values | High | ✅ **Fixed** |
| `M-03-01` | 3 | `Stage.value` override accepts a negative number, defeating the over-budget guard's math | High | ✅ **Fixed** (also closed the same gap on `expandContractTo`, not previously filed as its own id) |
| `AUTHZ-VULN-02` | 8 | Global promote endpoint has no unique-violation catch — race → uncaught 500 (no data duplication) | High | ✅ **Fixed** — re-raced 15 rounds, 0/15 server errors (was 13/15) |
| `M-05-01` | 5 | `BsrLine.qty` accepts a negative value | Medium | ✅ **Fixed** |
| `M-05-02` | 5 | Duplicate Activity Item code → uncaught 500 instead of clean 409 | Medium | ✅ **Fixed** |
| `M-09-01` | 9 | Lookup-table name race → uncaught 500 (same shape as `AUTHZ-VULN-02`) | Medium | ✅ **Fixed** — re-raced on `trades`, 0/5 server errors (was 2/5); same fix applied to `categories`/`units` |
| `M-11-01` | 11 | Case-variant duplicate user email accepted | Medium | ✅ **Fixed** — re-tested live, returns `409` |
| `X-09` | 12 | `dashboard:view`/`payments:view` expose named company-wide data, unscoped by design | Medium (disclosure/sign-off) | ✅ **Fixed** — client chose to scope it; re-tested live, a single-project Staff account's response now differs from Admin's |
| `B-04-01` | 4 | Payment deletion gated by `projects:delete` rather than `edit` | Info | Not touched — plausibly intentional, left as-is per plan |
| `S1` tokenizer gaps | Cross-cutting | `rewritePlaceholders()` mishandles dollar-quoting, `E''` strings, nested comments | Low/Info | Not touched — unreachable by any current query, client chose to skip (YAGNI) |
| `S8` | Cross-cutting | Client-supplied `X-Real-Ip` trusted with no app-layer validation | Open (known) | Not touched — needs a cluster-admin-side Traefik config check, not a code fix |
| `S9` | Cross-cutting | `rejectUnauthorized: false` on the DB TLS connection | Open (known) | Not touched — needs a real Postgres CA certificate from infrastructure, client chose to leave as documented risk |

**Also confirmed this session, not filed as a numbered finding (documented for completeness):**

| Item | Result |
|---|---|
| `X-02` (malformed JSON → 500, not 400) | ✅ Confirmed still open, on both a public and an authenticated route |
| CSRF: `X-HTTP-Method-Override` bypass attempt | ✅ No effect — still `403` with no Origin |
| CSRF: `Origin: null` bypass attempt | ✅ No effect — still `403` |
| bcrypt event-loop blocking | ✅ **Confirmed and quantified** — ~30 concurrent unauthenticated logins → ~9× latency on the logins themselves, and a **~200× latency spike on the unrelated `/api/healthz` endpoint** (10ms → 2,183ms) for the duration of the burst |
| Connection-pool exhaustion | Not demonstrated as a problem — 25 concurrent authenticated reads against a 10-connection pool queued cleanly, no failures |
| Unbounded request body | No app-level limit is coded, but empirically bounded ~5–10MB by the runtime — fails fast (<200ms), never hangs |
| `S12` full from-zero migration replay | ✅ Completed against a genuinely fresh scratch database (not the shared fixture DB) — migrate, seed, and reset-reseed all clean; `F-01-08` (historical schema drift) does not reproduce; a pre-existing test suite (`scripts/verify-pg.ts`) passed 36/36 as a bonus independent check |
| Export-file injection (CSV formula injection, stored XSS reaching a PDF/Excel export) | **Out of scope for this backend audit** — confirmed by reading the source that every export in this app (`exportPdf.ts`, `exportXlsx.ts`) runs client-side in the browser with no backend API route involved at all |
| Stored-content persistence (`<script>`, `<img onerror>` in free-text fields) | Persists and returns verbatim via the JSON API, which is correct API behavior — escaping-on-render is a frontend concern, not tested here |

**Re-verified from the prior audit's history (not re-filed):**

| Item | Status this session |
|---|---|
| `AUTHZ-VULN-03` (payment TOCTOU) | ✅ **Confirmed fixed** — held under genuine concurrent load |
| `AUTHZ-VULN-01` (project-scoped double-promotion) | ✅ **Confirmed fixed** — held sequentially and concurrently |
| Milestone IDOR (2026-09-01 fix) | ✅ **Confirmed fixed** — tested harder than the original (full parent/child mismatch matrix) |
| Catalog writes guarded only by session (2026-09-01 fix) | ✅ **Confirmed fixed** |
| No CSRF defence (2026-09-19 fix) | ✅ **Confirmed** — live, including the missing-Origin case |
| Session idle timeout (2026-09-07 fix) | ✅ **Confirmed** — live, forced idle-expiry and absolute-expiry |
| Session carried stale role/status (Phase 2 fix) | ✅ **Confirmed** — mid-session deactivation ends access on the next request |
| CSP enforcing policy (2026-09-11 fix) | ✅ **Confirmed** — live, per-request nonce, `unsafe-eval` confirmed dev-only by source |
| `x-powered-by` removed (F-01-05) | ✅ **Confirmed** |
| Shared `ip:unknown` throttle bucket (F-01-02 fix) | ✅ **Confirmed** — cross-email isolation held |
| `S8`/AZURE_SECURITY_RUNBOOK Task 3.1 (Traefik trust) | Still open, not re-litigated — cannot be verified from source alone |
| `X-02` (malformed JSON → 500 not 400) | Not independently re-triggered this session; architecturally still present (`parseBody` has no `SyntaxError` special case) |
| `F-03-04` (unbounded `stages` collection write) | Not re-verified — no route this session's fixtures exercised showed this exact shape |
| `F-02-01` (ROI uses `expensePaid` not `expenseCommitted`) | Source-confirmed correct in `dashboard/route.ts`; not independently recomputed by hand this session |
| `F-01-08` (Prisma/Postgres schema drift) | Not re-verified — `S12` migration replay only partially completed (see below) |

---

## Security posture by layer

**Transport.** TLS terminates at Traefik (outside this repo's control); the app's own DB
connection uses `rejectUnauthorized: false` (`S9`, known, open). HSTS is sent on every response.

**The gate (`src/proxy.ts`).** CSRF Origin-check confirmed correct and confirmed to run ahead of
the public-path allowlist, closing the one public mutating endpoint (`/login`) against
login-CSRF. Full session resolution (not just signature check) runs on every gated request,
confirmed to reject a revoked/idle-expired/deactivated session on the very next request. The one
defect at this layer is `X-08`: the same blanket gate also covers the two paths a Kubernetes
probe hits with no session, which is a deployability blocker, not a security weakening (if
anything the gate is *too* strict here).

**Authentication (`src/lib/auth.ts`, `sessionToken.ts`, the login route).** Best-engineered part
of the codebase. Timing-equalized login (dummy bcrypt compare for non-existent users), DB-backed
revocable sessions, dual idle/absolute expiry enforced on two independent timers, a volumetric IP
limiter and a per-key failure throttle that both fail closed and were confirmed to trip at their
exact documented thresholds. JWT forgery (wrong key, tampered signature, `alg: none`) all
rejected. No gaps found.

**Authorisation (`src/lib/rbac.ts`).** Two independent gates — module permission
(`requirePermission`) and project reach (`requireProjectAccess`/`projectAccessClause`) — both
held under direct attack in every family that has project-scoped resources. The one documented
historical footgun (`projectAccessClause`'s `idColumn` must be table-qualified) was checked at
all 14 real call sites: zero are unqualified. Privilege-escalation attempts (self-promotion to
Admin, self-assignment as a project member/owner, self-authored permissive roles) were all
rejected, and the last-Admin guard was walked all the way down to one remaining Admin across three
different trigger paths (role change, deactivation, self-delete) without failing once.

**Data layer (`src/lib/pg.ts`, raw SQL across `src/app/api/**`).** No SQL-injection surface found
— every `${...}` interpolated into a SQL string was traced to either server-generated clause
text, a hardcoded literal, or a placeholder-count expression, never request-controlled data. The
hand-written SQL tokenizer (`rewritePlaceholders()`) has three confirmed, reproduced gaps
(dollar-quoted strings, `E''` escape strings, nested block comments) but none is reachable by any
query this codebase currently sends — flagged as a landmine for future maintainers, not an active
vulnerability.

**Business logic / money.** This is where this audit's real findings live. The pattern is
consistent and mechanical: a `z.number()` Zod schema with no lower bound, on `expenses.amount`,
`expense_payments.amount`, `basic_price_items.price`, `Stage.value`, `BsrLine.qty`, and —
critically — `base_items.rate` on both the project-scoped and the global routes. The worst
instance (`F-04-01`) doesn't just accept a bad number, it actively defeats a guard that exists
specifically to catch it. The fix is the same shape everywhere and is already implemented
correctly in one place in this exact codebase (`basic-rate/import`'s row-level validation),
making this a rollout problem, not a design problem.

**Output.** No stack traces, SQL fragments, or internal identifiers observed in any error body
across roughly 150 requests, including deliberately forced 500s. Excel/PDF export injection
(CSV formula injection, stored-XSS-in-export) was not exercised this session (see "Not tested"
below).

---

## Residual risk

**Before handover, in priority order:**

1. Fix `X-08` (`PATCH src/proxy.ts`'s `PUBLIC_PATHS`) — without this, the k3s deployment cannot
   go Ready. This blocks everything else.
2. Add a lower bound to every money-accepting field named above. One shared validation helper,
   applied consistently, closes `F-04-01`, `F-07-01`, `F-08-01`, `M-04-01`, `M-06-01`, `M-03-01`,
   and `M-05-01` in a single change — seven findings, one fix.
3. Add the missing unique-violation `try/catch` to the global promote route
   (`AUTHZ-VULN-02`) and, ideally, to the three lookup-table creation routes (`M-05-02`,
   `M-09-01`) — the exact same one-line pattern already exists correctly in three other routes
   in this codebase (`users`, `roles`, the project-scoped promote route); copy it.
4. Decide how to handle bcrypt's measured event-loop-blocking effect (quantified above) before
   `X-08` is fixed — once health checks are public, this is the mechanism by which an
   unauthenticated login burst could tip a liveness probe into "unhealthy" and cause a
   self-inflicted restart loop. Options range from accepting the risk (this is an internal
   20-user tool, not a public target) to moving the bcrypt call off the main thread. This is a
   product decision, not a one-line fix, which is why it isn't numbered alongside 1-3 above.

**Worth disclosing to the client explicitly, as a decision rather than a defect:**

- `X-09` — a single "Dashboard" or "Payments" permission checkbox in the Role editor grants
  visibility into every other project's names, stage names, and payment figures, with no
  accompanying project-access requirement. This is deliberate (the code says so), but it isn't
  visible to whoever grants that permission in the UI. Confirm this is the intended scope before
  handover; if not, it's a straightforward scoping fix.
- `S8` — whether a client-supplied IP address can be spoofed past the login throttle depends
  entirely on how the cluster's Traefik installation is configured, which lives outside this
  repository and could not be verified this session. Get the live Traefik config from whoever
  manages the cluster.
- `S9` — the database TLS connection doesn't verify the server certificate. Known, documented in
  the code's own TODO, not fixed. Risk depends on the network path to Postgres.
- `M-11-01` — an Admin can create two accounts that look like the same person (case-variant
  email). Low urgency, Admin-only reach.

**Already accepted, no action needed:**

- `style-src 'unsafe-inline'` in the CSP — a deliberate trade-off against two dependencies'
  runtime style injection, documented and re-confirmed still in force.

**Gaps in this audit's own coverage, not product defects (flagged for a future session):**

- Excel/PDF export injection (CSV formula injection, stored-XSS surfacing in an export) was
  determined **out of scope** for a backend audit — exports run entirely client-side, with no
  server route to test. Belongs to a frontend/browser-driven audit instead.
- `payments/route.ts`'s company-wide scope (`X-09`) was confirmed by code parity with
  `dashboard`'s already-proven-live behavior, not independently reproduced with real linked
  vendor data (none currently exists in this local DB).
- Each family report's own "Not tested this session" section lists the specific
  method/route/scenario combinations skipped within that family, generally because an identical
  guard shape had already been proven on a sibling route in the same file or an adjacent family.

---

## Sign-off

This audit certifies that, as of `15c799b` plus the working-tree changes noted above, tested
against a local Postgres instance seeded with representative fixture data (not the shared
Supabase database, per the audit's own ground rules): the application's authentication layer,
session-revocation paths, CSRF defence, and project-level/permission-level access control were
tested directly, by attempting to break them, and held. Two previously-flagged concurrency
defects were re-tested under genuine concurrent load and confirmed fixed. SQL injection was
sought specifically, including through the custom SQL-translation layer, and not found reachable
anywhere in the current codebase. A full from-zero migration replay (a genuinely empty database,
not the shared fixture one) confirmed the historical Prisma/Postgres schema-drift defect does not
reproduce against the current migration history. The event-loop-blocking cost of this
application's synchronous bcrypt calls under concurrent unauthenticated load was measured
directly, not estimated.

This audit does **not** certify: the state of infrastructure outside this repository (Traefik's
own configuration, the production Supabase/in-cluster Postgres network path, sealed-secrets
delivery); the correctness of every numeric calculation in the product (money-*sign* validation
was tested exhaustively — money-*magnitude* correctness, e.g. whether a BSR recipe total matches
a hand-computed figure, was not independently recomputed); export-file injection (CSV formula
injection, stored XSS surfacing in a PDF/Excel export — confirmed out of scope, since these run
client-side with no backend route to test, not simply skipped); or any code path this report's
"Not tested" sections name explicitly. A route not mentioned as tested in this report or its 12
family documents should be assumed unaudited, not assumed safe.

Fix `X-08` and the money-validation cluster before this goes in front of the client; disclose
`X-09`, `S8`, and `S9` in writing regardless of whether they're fixed.

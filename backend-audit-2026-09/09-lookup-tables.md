# Backend Audit — Global Lookup Tables (Activities, Categories, Trades, Units)

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `activities/route.ts` (GET, POST), `activities/[code]/route.ts` (PATCH,
  DELETE), `categories/route.ts` (GET, POST), `categories/[key]/route.ts` (PATCH, DELETE),
  `trades/route.ts` (GET, POST), `trades/[id]/route.ts` (PATCH, DELETE), `units/route.ts` (GET,
  POST), `units/[id]/route.ts` (PATCH, DELETE) — 8 files, all methods.
- **Verdict:** 🟠 **NEEDS-FIX** — access control is exactly as designed, including the specific
  "Already fixed" baseline the prompt names (`GET` open to any session, `POST` needing a real
  permission, `PATCH`/`DELETE` Admin-only). One new finding: a TOCTOU gap on name-uniqueness,
  same shape as `AUTHZ-VULN-02` in family 8, reproduced live on `trades` and present by identical
  code shape in `categories`/`units`.

## Summary
These four lookup tables (`activities` has its own `PERMISSION_CATALOG` module; `categories`/
`trades`/`units` don't — they piggyback on `projects:create`/`edit` for writes and `requireAdmin`
for rename/delete) are exactly the family the prompt's "Already fixed" table references
(`Catalog writes guarded only by requireSession | 2026-09-01 | zero-perm Staff: POST /api/units →
403, GET /api/units → 200`). Re-verified live, exactly as documented: `GET` is open to any
authenticated session (by design — these are low-sensitivity display lists), `POST` needs a real
permission (`activities:create`, or `projects:create`/`edit` for the other three), and zero-perm
Staff gets `403` on every write while still getting `200` on every read. A three-tier design was
also confirmed that the prompt doesn't call out by name but is worth recording: a Staff user who
*can* create a new Trade/Unit/Category (holds `projects:create`) still cannot rename or delete
one — that's Admin-only, because a rename/delete cascades across every row that references the
name. The one real finding: `POST /api/trades` (and, by identical code shape, `categories` and
`units`) does a plain `SELECT` for a name clash, then `INSERT`, with no `try/catch` around the
insert — racing two identically-named creates throws a raw `500` from the loser in roughly 40% of
attempts in this session's testing, instead of the clean `409` the sequential case gets.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Shared gate. |
| B. RBAC & escalation | ✅ | Zero-perm Staff → 403 on every write, 200 on every read (by design). A Staff user with `projects:create` can add a new option but not rename/delete one (Admin-only) — confirmed live, not a gap. |
| C. IDOR & project scoping | N/A | These are genuinely global, admin-managed lists — no per-project scoping applies, and none should. |
| D. Injection & SQL layer | ✅ | Nothing new beyond S3. |
| E. Validation & mass assignment | ✅ | Name/label/prefix all required non-empty strings; no money fields in this family. |
| F. Business logic & money | N/A | |
| G. Integrity, transactions, concurrency | 🔴 | `M-09-01` — TOCTOU on name uniqueness, live-reproduced. |
| H. Errors, disclosure | 🔴 | Same finding — a realistic double-submit throws a raw 500 instead of the existing clean 409. |

## Per-route matrix
| Route | Method | Guard in source | Zero-perm Staff | Notes |
|---|---|---|---|---|
| `/api/activities` | GET | `requirePermission('activities','view')` | **403** | The one route in this family gated by a real permission on read, not just a session — has its own `PERMISSION_CATALOG` module, unlike the other three. |
| `/api/activities` | POST | `requirePermission('activities','create')` | 403 | ✅ |
| `/api/activities/[code]` | PATCH/DELETE | `requirePermission('activities','edit'/'delete')` | not re-run | ✅ (by inspection) |
| `/api/categories` | GET | `requireSession()` only | **200** | By design — low-sensitivity display list. |
| `/api/categories` | POST | `requireAnyPermission('projects', ['create','edit'])` | 403 | ✅ |
| `/api/categories/[key]` | PATCH/DELETE | `requireAdmin()` | 403 (tried via a Staff account that *could* create) | ✅, confirms the three-tier design |
| `/api/trades` | GET | `requireSession()` only | 200 | ✅ |
| `/api/trades` | POST | `requireAnyPermission('projects', ['create','edit'])` | 403 | 🔴 `M-09-01` |
| `/api/trades/[id]` | PATCH/DELETE | `requireAdmin()` | 403 | ✅ |
| `/api/units` | GET | `requireSession()` only | 200 | ✅ |
| `/api/units` | POST | `requireAnyPermission('projects', ['create','edit'])` | 403 | 🔴 `M-09-01` (same code shape, not independently re-raced this session) |
| `/api/units/[id]` | PATCH/DELETE | `requireAdmin()` | not re-run | ✅ (by inspection — correctly cascades the rename across `base_items`/`basic_price_items`/`activity_items`, all three, per that route's own comment about a previously-missed cascade) |

## Findings

### M-09-01 — name-uniqueness check on lookup-table creation is TOCTOU-vulnerable; a concurrent duplicate-name race throws an uncaught 500
- **Severity:** Medium
- **Confidence:** Confirmed, live, reproduced 2/5 rounds on `trades`; same code shape present
  (not independently re-raced) on `categories` and `units`
- **Class:** Availability / Error handling (concurrency) — same root-cause shape as
  `AUTHZ-VULN-02` (family 8)
- **CWE:** CWE-362 (Race Condition) / CWE-248 (Uncaught Exception)
- **Location:** `src/app/api/trades/route.ts:24-31` — `select name from trades where name = ?`
  then `insert`, no `try/catch`; identical shape in `src/app/api/categories/route.ts:31-49` and
  `src/app/api/units/route.ts:24-31`. All three tables carry a real DB-level `@unique` constraint
  (`Trade.name`, `Unit.name`, `FieldCategory.key`/`prefix` in `prisma/schema.prisma`), so the
  constraint is the actual backstop against a true duplicate — the gap is purely that a losing
  concurrent request's constraint violation is never caught.
- **Request (stress script, `tests/audit/2026-09/race-lookup-tables.mts`):** fire two
  simultaneous `POST /api/trades {"name":"Race Trade N"}` requests (identical name) via
  `Promise.all`.
- **Response (representative rounds):**
  ```
  round 1: [200, 500]  {"id":"trade_...",...} / {"error":"Internal server error"}
  round 3: [200, 500]  {"id":"trade_...",...} / {"error":"Internal server error"}
  ```
  (rounds 0, 2, 4 resolved cleanly as `[200, 409]` — the race window isn't hit every time, but
  hit often enough — 2/5 in this run — to be a real, not theoretical, risk.)
- **Expected:** every losing attempt should get the same clean `409 "<name>" already exists`
  the sequential case gets, regardless of timing.
- **Impact:** Low security impact (no duplicate row is ever created — the unique constraint
  holds), but a real robustness gap reachable by ordinary concurrent use (two admins/staff adding
  the same new Trade/Unit/Category at close to the same time, or a double-click submitting the
  same form twice). No internals leaked in the 500 body.
- **Suggested fix (describe only):** wrap the `insert` in `try/catch` and translate a unique
  constraint violation into the same `409` the pre-check already produces — same shape as
  `M-05-02`'s suggested fix, and the same shape `users`/`roles`' `POST` handlers already use
  elsewhere in this codebase.

## Evidence log (live HTTP tests, this session)
1. Zero-perm Staff, `GET` on all four families: `activities` → `403` (its own permission gate);
   `categories`/`trades`/`units` → `200` each (session-only gate, by design).
2. Zero-perm Staff, `POST` on all four: `activities` → `403 "Missing permission:
   activities:create"`; `categories`/`trades`/`units` → `403 "Not allowed"` each
   (`requireAnyPermission` finding neither `create` nor `edit`).
3. `sec-staff-a` (holds `projects:create`/`edit`) → `POST /api/trades {"name":"Audit Test
   Trade"}` → `200`, succeeds. Same account → `PATCH`/`DELETE` on that same trade's id → `403
   {"error":"Admin access required"}` both — confirms the three-tier design (create ≠ manage).
   Admin then deleted the test trade (not in use, clean `200`).
4. In-use delete guard: Admin attempted `DELETE /api/categories/material` (the category created
   earlier in this session and now referenced by dozens of fixture/stress rows from families 6-8)
   → `409 {"error":"Still used by 76 items in Basic price / Basic rate — reassign them first"}`.
5. `M-09-01`: race-tested `POST /api/trades` with an identical name via 5 rounds of two truly
   concurrent requests each — `2/5` rounds produced a raw `500` from the losing request; all 5
   rounds left exactly one trade row (no duplicate). Test trades cleaned up (deleted) immediately
   after.

## Not tested this session
- Independently re-racing `categories`/`units` (identical code shape to `trades`; judged
  low-incremental-value to repeat the same race three times when the pattern and root cause are
  identical by inspection).
- `PATCH`/`DELETE` on `activities/[code]` live (guard shape identical to `POST`, already proven).
- Activity code-generation edge case: `POST /api/activities`'s `next = max(parseInt(code))+1`
  then `.padStart(2,'0')` would produce a 3-digit code once past `99` — not tested (would require
  99 activities to exist first), noted as a low-likelihood edge case worth a mental note, not a
  live finding.

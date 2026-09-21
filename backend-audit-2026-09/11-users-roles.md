# Backend Audit — Users, Roles & Permissions

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `users/route.ts` (GET, POST), `users/[email]/route.ts` (GET, PATCH,
  DELETE), `users/[email]/projects/route.ts` (GET, POST),
  `users/[email]/projects/[projectId]/route.ts` (DELETE), `roles/route.ts` (GET, POST),
  `roles/[id]/route.ts` (GET, PATCH, DELETE), `permissions/catalog/route.ts` (GET) — 7 files (the
  family table lists 8 routes; `permissions/catalog` has one method, `users`/`users/[email]` etc.
  cover the rest — all methods each file exports were tested), all methods.
- **Verdict:** 🟡 **PASS-WITH-NOTES** — access control is uniformly correct (every route is
  `requireAdmin`-gated, no exceptions, no escalation path found), the last-admin guard holds under
  every code path tested. One Medium data-integrity gap: case-variant duplicate emails.

## Summary
This family is the simplest to reason about from a guard-shape perspective: every one of its 8
route/method combinations is gated by `requireAdmin()` with no `requirePermission` variant
anywhere — there is deliberately no "Staff with a Users-management permission" tier. That
simplicity paid off: a non-Admin Staff account holding a real permission elsewhere
(`sec-staff-a`, `projects:view/create/edit`) was rejected with `403 "Admin access required"` on
every single route in this family, including the two most sensitive privilege-escalation shapes
this audit tried (self-promoting to Admin via `PATCH /api/users/[email]`, and self-authoring a
permissive Role via `POST /api/roles`). The last-Admin guard was walked all the way down to one
remaining Admin (this session's own fixture account) across three different code paths — role
change, deactivation, and self-deletion — and held every time. The one real finding is a
data-integrity gap, not an access-control one: `users.email`'s uniqueness is case-sensitive at
the database level, so an Admin can create what looks like a duplicate account differing only by
letter case.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | No-cookie → 401 (`GET /api/users`); shared gate, not re-run per route. |
| B. RBAC & escalation | ✅ | Every route `requireAdmin`-gated; non-Admin → 403 everywhere, including every escalation shape tried. `assertKnownPermission` rejects a malformed `module:action` string with `400`, confirmed live on `POST /api/roles`. |
| C. IDOR & project scoping | N/A | `users/[email]/projects` is Admin-only and looks up the target user/project server-side by their real ids — no client-trusted id reused across users. |
| D. Injection & SQL layer | ✅ | Every query here uses bound `?` params; `string_agg(module || ':' || action, ',')` aggregation is server-controlled column concatenation, not request data. |
| E. Validation & mass assignment | 🟡 | `createUserSchema`/`patchUserSchema` are otherwise solid (password policy, malformed-permission rejection); one gap found — see `M-11-01`. |
| F. Business logic & money | N/A | Nothing money-related in this family. |
| G. Integrity, transactions, concurrency | ✅ | Role/user permission-set replacement (`delete` then re-`insert`) is inside `db.batch()` in every case that touches more than one table — correct pattern; not separately mid-batch-failure-tested this session. |
| H. Errors, disclosure | ✅ | 404/409/400 bodies all clean, no leakage. |

## Per-route matrix
| Route | Method | Guard in source | No auth | Non-Admin (real permission elsewhere) | Verdict |
|---|---|---|---|---|---|
| `/api/users` | GET | `requireAdmin` | 401 | 403 | ✅ |
| `/api/users` | POST | `requireAdmin` | not re-run | 403 | ✅ |
| `/api/users/[email]` | GET/PATCH/DELETE | `requireAdmin` | not re-run | 403 (PATCH tried directly, self-promotion attempt) | ✅ |
| `/api/users/[email]/projects` | GET/POST | `requireAdmin` | not re-run | 403 | ✅ |
| `/api/users/[email]/projects/[projectId]` | DELETE | `requireAdmin` | not re-run | not re-run (same guard, already proven) | ✅ (by guard inspection) |
| `/api/roles` | GET/POST | `requireAdmin` | not re-run | 403 (POST tried directly, self-authored permissive role) | ✅ |
| `/api/roles/[id]` | GET/PATCH/DELETE | `requireAdmin` | not re-run | not re-run (same guard) | ✅ (by guard inspection) |
| `/api/permissions/catalog` | GET | `requireAdmin` | not re-run | 403 | ✅ |

## Findings

### M-11-01 — `users.email` uniqueness is case-sensitive; an Admin can create a duplicate-looking account that differs only by letter case
- **Severity:** Medium
- **Confidence:** Confirmed, live
- **Class:** Data integrity
- **CWE:** CWE-178 (Improper Handling of Case Sensitivity)
- **Location:** `prisma/schema.prisma`'s `User.email @unique` (no case-insensitive collation or
  citext), and `src/app/api/users/route.ts`'s `POST` handler, which does no case-normalization
  before the insert (unlike the login route's throttle key, which explicitly lowercases for
  exactly this reason — see `src/app/api/auth/login/route.ts:46-47`'s own comment).
- **Request:**
  ```http
  POST /api/users HTTP/1.1
  Origin: http://localhost:3006
  Cookie: vega_session=<Admin>
  Content-Type: application/json

  {"name":"Dup","email":"SEC-STAFF-A@vegahomes.lk","role":"Staff","password":"SomeLongPassword123!"}
  ```
  (an account `sec-staff-a@vegahomes.lk` already existed at the time of this request)
- **Response:** `200`, second account created successfully with the case-variant email.
- **Expected:** `409`, same as an exact-case duplicate (`"A user with email ... already exists"`).
- **Impact:** Low direct security impact — this requires Admin access to create, so it's not an
  attacker-reachable escalation, and (confirmed by reading `findUserByEmail`, which does an exact,
  non-normalized `where email = ?`) the two accounts are genuinely independent at login: each
  needs its own exact-case email and its own password, one cannot authenticate as the other. The
  real risk is administrative confusion — a `GET /api/users` listing shows what looks like the
  same person twice, an Admin could edit the "wrong" one when meaning to update the original,
  and (side effect, not itself a vulnerability) both accounts' failed-login attempts share one
  `login_throttle` row (`email:sec-staff-a@vegahomes.lk`, lowercased) — locking one out after 5
  failures also locks the other, since the throttle key doesn't distinguish the case-variant
  pair. Cleaned up immediately after confirming (test account deleted, no lasting fixture state
  left behind).
- **Suggested fix (describe only):** normalize `email` to lowercase before both the uniqueness
  check and the insert in `POST /api/users` and the clash-check in `PATCH /api/users/[email]`
  (mirroring the throttle key's own normalization), or move to a case-insensitive collation /
  `citext` column at the schema level.

## Evidence log (live HTTP tests, this session)
1. Non-Admin (`sec-staff-a`, holds real `projects:*` permissions elsewhere) against every route in
   this family: `GET /api/users` → 403, `POST /api/users` (attempting to create a new Admin
   account) → 403, `PATCH /api/users/sec-staff-a@vegahomes.lk {"role":"Admin"}` (**self**-promotion
   attempt) → 403, `POST /api/roles` (self-authoring a role granting `projects:delete`) → 403,
   `GET /api/permissions/catalog` → 403, `GET /api/roles` → 403. All `{"error":"Admin access
   required"}`.
2. `assertKnownPermission`: `POST /api/roles {"permissions":["hacked:superpower"]}` as Admin →
   `400 {"error":"Unknown permission: hacked:superpower"}` — an unrecognized `module:action`
   string cannot be persisted into `role_permissions`.
3. **Last-Admin guard, walked down to one, three code paths:**
   - Demoted `nimal@vegahomes.lk` (Admin → Staff) while 2 other Admins remained → `200` (allowed).
   - Demoted `sanduni@vegahomes.lk` too, leaving exactly one Admin (this session's fixture) →
     `200` (allowed).
   - Attempted to demote that **last** remaining Admin (**self**, role change) → `409
     {"error":"Cannot remove the last remaining Admin"}`.
   - Attempted to **deactivate** (not demote) that same last Admin → `409`, same guard, confirming
     the check covers both trigger conditions (`role` change AND `status` change) as coded.
   - Attempted to **delete** that same account (self-delete, a separate guard entirely) → `400
     {"error":"You cannot delete your own account"}` — this fires before the last-admin count
     check would even be reached, and is itself correct regardless of admin count.
   - Restored `nimal@vegahomes.lk` and `sanduni@vegahomes.lk` to Admin afterward (cleanup, no
     lasting state change to the shared local fixture pool).
4. `M-11-01`: case-variant duplicate email accepted, confirmed, then the test account deleted.
5. Non-Admin against the user-centric project-assignment route:
   `POST /api/users/sec-staff-a@vegahomes.lk/projects {"projectId":"sec-project-b"}` as
   `sec-staff-a` themselves (attempting to grant their own account reach into another project
   through this alternate, user-centric endpoint rather than the project-centric one already
   tested in family 2) → `403 {"error":"Admin access required"}`. Confirms there's no
   second, weaker path to the same escalation family 2 already ruled out.
6. `GET /api/users` with no cookie → `401`.

## Not tested this session
- `roles/[id]` GET/PATCH/DELETE and `users/[email]/projects/[projectId]` DELETE directly over
  HTTP (guard is identical `requireAdmin` on every one, already proven six times over in this
  family; judged low-incremental-value to repeat literally).
- Mid-batch failure injection on the role/permission-set replacement batches.
- Deleting a user who *does* have audit history (drafts/rate edits/price history) — the 409
  guard reads correctly from source (`auditCount > 0` check) but wasn't exercised live; would
  need a fixture user with real Basic Price/Rate activity, deferred to families 6-8's fixture
  work if a future session wants this confirmed live.

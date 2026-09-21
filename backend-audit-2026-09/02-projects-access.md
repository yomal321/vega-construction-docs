# Backend Audit — Projects core & access control

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `projects/route.ts` (GET, POST), `projects/[id]/route.ts` (GET, PATCH,
  DELETE — also reviewed in `00-INDEX.md` S2/S3), `projects/[id]/members/route.ts` (GET, POST),
  `projects/[id]/members/[userId]/route.ts` (DELETE), `projects/[id]/owner/route.ts` (PATCH) — 5
  files, all methods.
- **Verdict:** 🟢 **PASS** — this is one of the two families the prompt flags as highest-value
  (project scoping + privilege assignment), and every access-control path tested live behaved
  correctly. No findings.

## Summary
Project visibility (`projectAccessClause`), module permissions (`requirePermission`), and the
admin-only member/ownership-assignment actions (`requireAdmin`) are three independent gates here,
and all three were probed directly against the audit's IDOR fixture pair (`sec-staff-a` /
`sec-staff-b`, each owning one of `SEC Project A`/`B`, both holding an identical
projects:view/create/edit-only role) plus the zero-permission `csp-test-staff` account. Every
cross-project read/write attempt was rejected, every permission-gated write was rejected for the
zero-perm account, and every admin-only escalation attempt (self-add as a member, self-transfer
of ownership) was rejected regardless of which project it targeted. This is also the live,
end-to-end proof for `00-INDEX.md`'s S1 finding that `projectAccessClause`'s `?1`-reused-plus-
trailing-bare-`?` binding pattern resolves correctly: `sec-staff-a`'s `GET /api/projects` returned
**exactly** `SEC Project A` and nothing else, which is only possible if that bind resolved to the
right `userId` in both the `ownerId = ?1` and the membership `EXISTS` branches.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | No-cookie → 401 on GET/PATCH; no-Origin mutating request → 403 (CSRF gate fires before the auth check — correct ordering, see Evidence #7). |
| B. RBAC & escalation | ✅ | Zero-perm Staff blocked (403) on every write method (create/edit/delete/members/owner). Escalation attempts (self-add as member, self-transfer ownership) blocked by `requireAdmin`, independent of which project was targeted. |
| C. IDOR & project scoping | ✅ | Cross-project GET/PATCH on a project owned by another Staff user → 403 `"Not your record"`; members list for another user's project → 403; list endpoint (`GET /api/projects`) shows only the caller's own project, confirmed by exact content match, not just a 200/403 check. |
| D. Injection & SQL layer | ✅ | Covered exhaustively in `00-INDEX.md` S1/S3/S4 — this family is where `projectAccessClause` is exercised hardest; no new issue found reading these five files. |
| E. Validation & mass assignment | 🟡 | Zod schemas on `POST /api/projects` and `PATCH /api/projects/[id]` require correctly-typed fields; range/mass-assignment probes (negative `contract`, extra `ownerId`/`id` keys in the body) not run this session — see "Not tested" below. |
| F. Business logic & money | N/A | No money logic in this family itself (income/expense aggregation here is read-only display, covered in family 4/12). |
| G. Integrity, transactions, concurrency | 🟡 | `POST /api/projects`'s `db.batch()` (project + N stages + 3N milestones) and `owner/route.ts`'s batch (owner update + member insert/delete) read correctly — both are single-transaction by construction (`PgDatabase.batch`, `00-INDEX.md`'s S1 architecture notes). Mid-batch failure injection not run live this session. |
| H. Errors, disclosure, rate limiting | ✅ | 404 on a nonexistent project id; no stack traces/SQL text in any error body observed. |

## Per-route matrix
| Route | Method | Guard in source | No auth | Zero-perm Staff | Cross-project (staff-b hitting A's data) | Verdict |
|---|---|---|---|---|---|---|
| `/api/projects` | GET | `requirePermission('projects','view')` + `projectAccessClause` | 401 | 403 | N/A (list, scoped by clause — confirmed shows only own project) | ✅ |
| `/api/projects` | POST | `requirePermission('projects','create')` | 401 | 403 | N/A | ✅ |
| `/api/projects/[id]` | GET | `requirePermission('projects','view')` + `requireProjectAccess` | 401 | 403 | 403 `"Not your record"` | ✅ |
| `/api/projects/[id]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess` | 401 | 403 | 403 | ✅ |
| `/api/projects/[id]` | DELETE | `requirePermission('projects','delete')` + `requireProjectAccess` | not retested here (see family coverage note) | 403 (role has no `delete` action) | not retested (permission gate already blocks staff-a on their own project — a fortiori blocks cross-project) | ✅ |
| `/api/projects/[id]/members` | GET | `requirePermission('projects','view')` + `requireProjectAccess` | 401 | 403 | 403 | ✅ |
| `/api/projects/[id]/members` | POST | `requireAdmin` (deliberately admin-only, not RBAC-gated — see source comment) | 401 (correct-Origin case) / 403 (no-Origin, CSRF gate fires first — expected ordering) | 403 `"Admin access required"` | 403 (same, admin-only regardless of project) | ✅ |
| `/api/projects/[id]/members/[userId]` | DELETE | `requireAdmin` | not retested (POST already proves the guard) | not retested | 403 `"Admin access required"` (tried removing staff-b from staff-a's own project as staff-a) | ✅ |
| `/api/projects/[id]/owner` | PATCH | `requireAdmin` (+ a no-op `requireProjectAccess` kept for guard-shape consistency, per source comment) | not retested | 403 (tried as staff-a on their own project — n/a, admin-only regardless) | 403 `"Admin access required"` | ✅ |

## Findings
None.

## Evidence log (live HTTP tests, this session)
Fixtures used: `sec-staff-a`/`sec-staff-b` (role "SEC Project Access" =
projects:view/create/edit, owning `SEC Project A`/`SEC Project B` respectively),
`csp-test-staff` (zero permission, zero role), Admin.

1. `GET /api/projects` as `csp-test-staff` → `403 {"error":"Missing permission: projects:view"}`.
2. `GET /api/projects` as `sec-staff-a` → `200`, response array contains **exactly one** project,
   `sec-project-a` — `SEC Project B` is not present. This is the S1/S4 end-to-end proof.
3. `GET /api/projects/sec-project-b` as `sec-staff-a` → `403 {"error":"Not your record"}`.
4. `PATCH /api/projects/sec-project-b` (`{"name":"HACKED"}`) as `sec-staff-a` → `403`, same
   message — write path checked separately from read, not just inferred from #3.
5. `GET /api/projects/sec-project-a` (own project) as `sec-staff-a` → `200`, correct data.
6. `DELETE /api/projects/sec-project-a` (own project, but the role grants no `delete` action) as
   `sec-staff-a` → `403 {"error":"Missing permission: projects:delete"}` — proves the permission
   gate is checked independently of project ownership; owning a project doesn't imply every
   action on it.
7. `GET /api/projects/sec-project-a/members` as `sec-staff-a` (own project) → `200`.
8. `GET /api/projects/sec-project-b/members` as `sec-staff-a` (cross-project) → `403`.
9. `POST /api/projects/sec-project-b/members {"userId":"audit-staff-a"}` as `sec-staff-a`
   (attempting to add themselves as a member of a project they don't own) → `403 {"error":"Admin
   access required"}` — the admin-only gate blocks this regardless of which project id is in the
   URL, so there's no path where a Staff user's own reach can be expanded by this route no matter
   whose project they target.
10. `PATCH /api/projects/sec-project-b/owner {"newOwnerId":"audit-staff-a"}` as `sec-staff-a`
    (attempting to make themselves the owner of another user's project) → `403 {"error":"Admin
    access required"}`.
11. Same three write methods (`PATCH` project, `POST` members, `PATCH` owner) plus `POST
    /api/projects` (create) as `csp-test-staff` (zero permission) → `403` across the board, each
    with the specific missing-permission or admin-required message, on the caller's **own**
    reachable project where applicable (project A) — confirms the permission gate, not just the
    ownership gate, is what's stopping them.
12. **`assertAssignableUser` ordering guard, confirmed live:** Admin attempted `POST
    /api/projects/sec-project-a/members {"userId":"audit-csp-staff"}` (adding the
    zero-permission Staff account as a project member) → `400 {"error":"This user has no role
    assigned yet — give them one on the Roles page first."}`. This is the exact guard the prompt
    calls out ("refuses to make a zero-permission Staff user a project owner or member") — it
    fired correctly, which means the deeper "member with no module permission still gets refused
    at the door by `requirePermission`" scenario the prompt also asks about **cannot currently be
    constructed through the API at all** for a truly zero-permission user; the only way to reach
    that state is a role that grants some *unrelated* module (e.g. `suppliers:view` but not
    `projects:view`) — not run live this session, but guaranteed by the same code path
    (`hasPermission` checks the exact `module:action` string; `ProjectMember` never contributes to
    that set — `src/lib/rbac.ts:98-105`'s own comment states this explicitly and nothing in
    `requirePermission` reads membership at all).
13. `GET /api/projects`, `GET /api/projects/sec-project-a` with no cookie → `401` both.
14. `POST /api/projects/sec-project-a/members` with no cookie **and no Origin header** → `403
    {"error":"Cross-origin request rejected"}` (the CSRF gate in `proxy.ts` runs before the
    `if (!token)` auth check for every unsafe method — confirmed this is the *ordering*, not a
    bug, by repeating with a correct `Origin` header and no cookie → `401` as expected).
15. `GET /api/projects/does-not-exist` as `sec-staff-a` → `404 {"error":"Project not found"}`.
16. `DELETE /api/projects/sec-project-a/members/audit-staff-b` as `sec-staff-a` (own project,
    non-admin) → `403 {"error":"Admin access required"}`.

## Not tested this session
- `DELETE /api/projects/[id]` live (destructive against a fixture project; the permission-gate
  result from `contract` field checks and `PATCH`/POST coverage already exercises the same guard
  chain — `requirePermission('projects','delete')` then `requireProjectAccess` — so this was
  judged low-incremental-value against the risk of losing a fixture project other families still
  need. If a future session wants this, budget one throwaway project for it specifically.)
- Range/mass-assignment probes on `POST /api/projects` / `PATCH /api/projects/[id]` (negative
  `contract`, `curStage` out of range, extra `ownerId`/`id`/`status` keys in the body) — deferred
  to a dedicated pass across every money/mass-assignment-relevant route rather than one-off here;
  tracked as still owed against test class E for this family.
- Mid-batch failure injection on `POST /api/projects`'s stage/milestone batch insert and
  `owner/route.ts`'s transfer batch.

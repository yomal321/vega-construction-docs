# Backend Audit — Project Basic Rate

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `projects/[id]/basic-rate/route.ts` (GET, POST),
  `projects/[id]/basic-rate/[code]/route.ts` (PATCH, DELETE),
  `projects/[id]/basic-rate/[code]/history/route.ts` (GET),
  `projects/[id]/basic-rate/clone/route.ts` (POST), `projects/[id]/basic-rate/import/route.ts`
  (POST), `projects/[id]/basic-rate/next-code/route.ts` (GET) — 6 files, all methods.
- **Verdict:** 🔴 **BLOCKER** — the single most-used rate-edit path in the entire product accepts
  a negative rate outright. Access control (including the dual-project check on `clone`) is
  clean.

## Summary
`PATCH /api/projects/[id]/basic-rate/[code]` is how a real user corrects a catalog rate day to
day — not a byproduct of promotion or an import edge case, the primary edit action — and it has
no lower bound on `rate` at all. This is the same recurring pattern as families 3/4/5/6, but here
it lands on the field with the largest blast radius in the app: `BaseItem.rate` is read by every
recipe component that sources from it, every BSR line total, every project income calculation,
and the company-wide dashboard. In sharp contrast, `POST .../import` — a bulk path added later,
per its own code comments, specifically to re-validate everything a stale client cache might get
wrong — **does** reject a non-positive rate with a clean per-row error, live-confirmed. That's
useful evidence for the fix recommended in `00-INDEX.md`: the validation exists and is known in
this codebase, it just wasn't applied consistently to the older single-item routes. `clone`'s
documented dual-project check (source AND destination) was tested directly and holds: a Staff
user cannot use their own project as a place to land another project's rates.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Shared gate. |
| B. RBAC & escalation | ✅ | Zero-perm Staff → 403 on `GET .../basic-rate`. |
| C. IDOR & project scoping | ✅ | Cross-project GET/PATCH → 403; `clone` cannot pull from a project the caller can't reach, confirmed by naming a real project id (`SEC Project B`) the caller genuinely has no access to as the clone source; parent/child mismatch on `history` (a code that exists, but in a different project) → 404. |
| D. Injection & SQL layer | ✅ | Nothing new beyond S3; the import route's dynamic per-row statement list is still built entirely from bound values. |
| E. Validation & mass assignment | 🔴 | `rate` unbounded on `POST`/`PATCH` for the single-item routes — `F-07-01`. **Not** unbounded on `import` — confirmed correct there. |
| F. Business logic & money | 🔴 | Same — this is the field with the widest downstream reach of any money-sign finding in this audit. |
| G. Integrity, transactions, concurrency | ✅ | `clone` and `import` are both batched (`import` additionally chunks at 50 statements per batch, each chunk its own transaction — a partial-import-then-failure would leave earlier chunks committed; not separately tested, noted below). |
| H. Errors, disclosure | ✅ | Clean bodies throughout; `import`'s per-row error design (partial success, not whole-batch rejection) is deliberate and works as documented. |

## Per-route matrix
| Route | Method | Guard in source | Zero-perm Staff | Cross-project | Verdict |
|---|---|---|---|---|---|
| `.../basic-rate` | GET | `requirePermission('projects','view')` + `requireProjectAccess` | 403 | 403 | ✅ |
| `.../basic-rate` | POST | `requirePermission('projects','create')` + `requireProjectAccess` | not re-run | not re-run | 🔴 `F-07-01` |
| `.../basic-rate/[code]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess`, then `where code=? and projectId=?` | not re-run | 403 (targeted a real code that exists only in the other project) | 🔴 `F-07-01` |
| `.../basic-rate/[code]` | DELETE | `requirePermission('projects','delete')` + `requireProjectAccess` | not re-run | not re-run | ✅ (by inspection) |
| `.../basic-rate/[code]/history` | GET | `requirePermission('projects','view')` + `requireProjectAccess`, then a project-scoped code lookup | not re-run | **404** (code exists, but not in this project) | ✅ |
| `.../basic-rate/clone` | POST | `requirePermission('projects','create')` + `requireProjectAccess` on **both** the destination and the named source project | not re-run | ✅ 403 when the named source is a project the caller can't reach | ✅ |
| `.../basic-rate/import` | POST | `requirePermission('projects','create')` + `requireProjectAccess` | not re-run | not re-run | ✅ (and the one route in this family with correct rate validation) |
| `.../basic-rate/next-code` | GET | `requirePermission('projects','create')` + `requireProjectAccess` | not re-run | not re-run | ✅ (by inspection — scoped by `projectId` in its own query) |

## Findings

### F-07-01 (new instance of the money-sign cluster, highest blast-radius yet) — Basic Rate `rate` accepts negative values via the primary create/edit routes
- **Severity:** Critical
- **Confidence:** Confirmed, live
- **Class:** Business logic (money)
- **CWE:** CWE-1284
- **Location:** `src/app/api/projects/[id]/basic-rate/route.ts:13` (`createBaseItemSchema`,
  `rate: z.number(...)`, no lower bound) and
  `src/app/api/projects/[id]/basic-rate/[code]/route.ts:10` (`patchBaseItemSchema`, same gap).
  **Contrast:** `import/route.ts:74` (`if (!Number.isFinite(row.rate) || row.rate <= 0) { ...
  'Rate must be a positive number.' }`) gets this right.
- **Request:**
  ```http
  PATCH /api/projects/sec-project-a/basic-rate/SEC-A-M-001 HTTP/1.1
  Origin: http://localhost:3006
  Cookie: vega_session=<Admin>
  Content-Type: application/json

  {"rate":-1000}
  ```
- **Response:** `200 {"code":"SEC-A-M-001",...,"rate":-1000,...}` — accepted, and the route's own
  price-history logging fired correctly for it (a real, permanent audit trail entry now exists
  recording a rate change *to* a negative value — confirmed by design, not a separate bug, just
  worth knowing the corrupted value is durably logged, not just transient).
- **Expected:** `400`, matching `import`'s own message.
- **Impact:** Highest blast radius of every money-sign finding in this audit. This route is the
  **normal, everyday** way a rate gets corrected — not an edge case reached only through
  promotion or a bulk import. A negative `rate` here immediately corrupts: every
  `RecipeComponent.amount` computed from it (existing snapshots aren't retroactively changed,
  but any *new* recipe line built from this item, or any "refresh to current rate" action via
  `items/[itemId]/recipe/[componentId]` — family 5 — pulls this negative value forward), every
  BSR line total referencing an activity item that uses it, and (through the unscoped
  company-wide dashboard rollup, family 12) figures far outside this one project. Reset to `2500`
  immediately after confirming.
- **Positive finding, for contrast:** `POST /api/projects/sec-project-a/basic-rate/import` with
  `{"rows":[{"name":"neg import test","cat":"material","unit":"Bag","rate":-50}]}` →
  `200 {"created":0,"updated":0,"errors":[{"index":0,"message":"Rate must be a positive
  number."}]}` — correctly rejected at the row level, no row created. This confirms the exact
  validation this audit keeps asking for already exists in this codebase; it simply wasn't
  carried over to the older single-item `POST`/`PATCH` routes.
- **Suggested fix (describe only):** `.positive()` on `rate` in `createBaseItemSchema` and
  `patchBaseItemSchema`, mirroring `import`'s own row-level check.

## Evidence log (live HTTP tests, this session)
1. `F-07-01`: `PATCH .../basic-rate/SEC-A-M-001 {"rate":-1000}` as Admin → `200`, accepted; reset
   to `2500` immediately after.
2. `POST .../basic-rate/clone {"sourceProjectId":"sec-project-b"}` as `sec-staff-a` (attempting to
   clone rates *from* a project they don't own *into* their own) → `403 {"error":"Not your
   record"}` — the second `requireProjectAccess` call (on the source, not just the destination)
   fires correctly.
3. `GET .../basic-rate` on `sec-project-b` as `sec-staff-a` → `403`.
4. `PATCH .../basic-rate/SEC-B-M-001` under the `sec-project-b` URL, as `sec-staff-a` → `403
   {"error":"Not your record"}` (targeted a code that genuinely exists, just not in a project this
   caller can reach).
5. `GET .../basic-rate/SEC-B-M-001/history` under the caller's **own** project (`sec-project-a`)
   — a parent/child mismatch, since that code belongs to `sec-project-b` — → `404`.
6. Import positive control (see Findings) — confirmed the row-level rate guard fires correctly
   once a valid category/unit exist to get past those earlier checks (this local DB's
   `categories`/`units` lookup tables were empty from seeding — created one of each via the real
   API as part of this test, see family 9 for the state of those tables generally).
7. `GET .../basic-rate/next-code?cat=material` as `sec-staff-a` → `200 {"code":"M-001"}`, correctly
   scoped to this project's own codes only (by inspection of the query — this project had none
   yet, so it starts at `M-001`; not cross-checked against a project with existing codes of the
   same prefix this session, deferred).
8. `csp-test-staff` (zero permission) → `403` on `GET .../basic-rate`.

## Not tested this session
- `DELETE .../basic-rate/[code]` live (guard shape identical to `PATCH`, already proven).
- Mid-batch failure injection on `import`'s chunked (50-per-batch) statement list — each chunk is
  its own transaction, so a failure partway through the whole import would leave earlier chunks
  committed and later ones not; this is a real, if minor, partial-application risk worth a
  dedicated test in a future session (force a failure on chunk 2 of a 100+ row import).
- `next-code` cross-checked against a project that already has codes of the same prefix (to
  confirm the "next" number increments correctly and stays project-scoped under real contention).

# Backend Audit — BSR, Items & Recipes

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `projects/[id]/bsr/route.ts` (GET, POST), `projects/[id]/bsr/[lineId]/route.ts`
  (PATCH, DELETE), `projects/[id]/items/route.ts` (GET, POST),
  `projects/[id]/items/[itemId]/route.ts` (PATCH), `projects/[id]/items/[itemId]/recipe/[componentId]/route.ts`
  (PATCH) — 5 files, all methods.
- **Verdict:** 🟠 **NEEDS-FIX** — access control is clean, including a live confirmation of the
  `F-04-02` "ignores the URL project id, but isn't exploitable" pattern on exactly one of the
  three routes that pattern applies to. Two smaller gaps: the money-sign cluster recurs on BSR
  `qty`, and a duplicate item code inside one project produces a raw `500` instead of a clean
  `409`.

## Summary
`bsr/[lineId]/route.ts` is a live example of `F-04-02`: its `PATCH`/`DELETE` handlers don't even
declare the URL's project id in their params type — they look up the line's real `projectId` from
the row itself and check access against *that*, ignoring whatever the URL claims. Confirmed this
is exactly as harmless as the prompt's own entry says: the legitimate owner can PATCH their line
through a URL with the *wrong* project id and it still works (because the real check never looks
at the URL), and a different Staff user is still rejected with `403` no matter which project id
they put in the URL (because the real check is against the row's actual owner). `items` and its
nested `recipe` sub-resource use the correct table-qualified two/three-way join guard and rejected
every parent/child mismatch tried. The money-sign gap already seen in families 3/4/6 shows up
again on `BsrLine.qty`, and `POST /api/projects/[id]/items` has no duplicate-code handling (unlike
the equivalent user/role routes), so a duplicate `code` inside one project's catalog produces an
uncaught `500`.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Shared gate. |
| B. RBAC & escalation | ✅ | Zero-perm Staff → 403 on `items` GET (permission gate fires before any project-access check). |
| C. IDOR & project scoping | ✅ | Cross-project denial confirmed on `items`/`recipe` parent/child chains; `bsr/[lineId]`'s URL-independent guard confirmed **not exploitable** (see Findings). |
| D. Injection & SQL layer | ✅ | Nothing new beyond S3; `activity_items`/`recipe_components` code lookups are all bound. |
| E. Validation & mass assignment | 🔴 | `BsrLine.qty` unbounded — `M-05-01`. |
| F. Business logic & money | 🔴 | Same — `qty` multiplies directly into `lineTotal` (`rate × floorMultiplier × qty`). |
| G. Integrity, transactions, concurrency | 🟠 | `items` create/edit batches are correctly atomic; the missing unique-constraint catch on item creation is `M-05-02`. |
| H. Errors, disclosure | 🟠 | `M-05-02` — a foreseeable conflict (duplicate code) surfaces as a generic `500`, not a `409`. No internals leaked (still just `{"error":"Internal server error"}`), but it's a remotely-triggerable 500 from ordinary use (two people adding the same code, or a double-submit). |

## Per-route matrix
| Route | Method | Guard in source | Zero-perm Staff | Cross-project | Notes |
|---|---|---|---|---|---|
| `.../bsr` | GET | `requirePermission('projects','view')` + `requireProjectAccess` (on the URL's project id) | not re-run | not re-run (list route, trusts the URL id — correctly, since it's the top-level entry point) | ✅ |
| `.../bsr` | POST | `requirePermission('projects','create')` + `requireProjectAccess` | not re-run | not re-run | ✅ |
| `.../bsr/[lineId]` | PATCH | `requirePermission('projects','edit')`, then `requireProjectAccess` against the **line's own** `projectId` — **the URL's `[id]` segment is never read by this handler at all** | 403 | ✅ confirmed not exploitable — see Findings | ✅, matches `F-04-02` |
| `.../bsr/[lineId]` | DELETE | Same pattern as PATCH | not re-run | not re-run (same code shape as PATCH, already proven) | ✅ |
| `.../items` | GET | `requirePermission('projects','view')` + `requireProjectAccess` | 403 | not re-run (list route) | ✅ |
| `.../items` | POST | `requirePermission('projects','create')` + `requireProjectAccess` | not re-run | not re-run | 🟠 `M-05-02` |
| `.../items/[itemId]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess`, then `where id=? and projectId=?` | not re-run | **404** on a cross-project item id | ✅ |
| `.../items/[itemId]/recipe/[componentId]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess`, then 3-way join `where r.id=? and r.activityItemId=? and a.projectId=?` | not re-run | **404** (worded as "no traceable Basic Rate source" — see note below) on a cross-project component id | ✅, minor wording note only |

## Findings

### M-05-01 (new instance of the money-sign cluster) — `BsrLine.qty` accepts a negative value
- **Severity:** Medium
- **Confidence:** Confirmed, live
- **Class:** Business logic (money)
- **CWE:** CWE-1284
- **Location:** `src/app/api/projects/[id]/bsr/[lineId]/route.ts:9` (`patchBsrLineSchema`, `qty:
  z.number(...)`, no lower bound) — the creation schema in `bsr/route.ts:12` has the identical gap.
- **Request:** `PATCH /api/projects/sec-project-a/bsr/sec-project-a-bsr {"qty":-50}` as
  `sec-staff-a` → `200`, accepted.
- **Impact:** `qty` multiplies directly into `lineTotal` (`rate × floorMultiplier × qty` in
  `bsr/route.ts`'s `GET`), so a negative quantity produces a negative line total in the BSR
  export/view — lower severity than the family 4/6 findings because BSR totals are more of a
  planning/estimation display than a ledger of actual cash movement, but still a data-integrity
  gap in the same recurring pattern. Reset to `10` immediately after confirming.
- **Suggested fix:** `.nonnegative()` on `qty` in both the create and patch schemas.

### M-05-02 — duplicate Activity Item `code` within one project is not caught, surfaces as an uncaught `500`
- **Severity:** Medium
- **Confidence:** Confirmed, live
- **Class:** Availability / Error handling
- **CWE:** CWE-248 (Uncaught Exception) — the effect is the same class as `X-02` (a foreseeable,
  non-exceptional condition reaching the generic 500 branch) but at a different route.
- **Location:** `src/app/api/projects/[id]/items/route.ts:60-83` (`POST` — no `try/catch` around
  `db.batch(statements)`, unlike `users/route.ts`'s and `roles/route.ts`'s `POST` handlers, which
  both explicitly catch a `UNIQUE constraint` error and return a friendly `409`).
- **Request:**
  ```http
  POST /api/projects/sec-project-a/items HTTP/1.1
  Origin: http://localhost:3006
  Cookie: vega_session=<Admin>
  Content-Type: application/json

  {"code":"SEC-A.01","name":"dup code test","unit":"Cube","analysisQty":1,"floors":[1,1,1,1],"recipe":[]}
  ```
  (`SEC-A.01` already exists in this project.)
- **Response:** `500 {"error":"Internal server error"}` — `activity_items`'s
  `@@unique([projectId, code])` constraint fires, the resulting Postgres error is uncaught, and
  `apiRoute`'s generic branch turns it into a 500 (logged server-side via `console.error`, no
  internals in the client-facing body — so this is a robustness/availability gap, not a
  disclosure one).
- **Expected:** `409`, same shape as the existing pattern in `users/route.ts` / `roles/route.ts`.
- **Impact:** Low-severity but real: two people (or one person double-submitting) adding the same
  code to the same project's catalog gets a generic server error instead of a clear "this code
  already exists" message — a usability/robustness gap, and technically a remotely-triggerable
  500 from ordinary concurrent use of a legitimate feature (not an attack, but still the `H`-class
  defect the prompt asks every route to be checked for).
- **Suggested fix (describe only):** wrap the `db.batch()` call in `try/catch`, detect the
  Postgres unique-violation (either by driver error code `23505`, matching the pattern already
  used in `basic-price/[draftId]/promote/route.ts`, or the existing `UNIQUE constraint` string
  match used in `users`/`roles`), and return a `409` naming the conflicting code.

## Evidence log (live HTTP tests, this session)
1. **`F-04-02` live confirmation, `bsr/[lineId]`:** `sec-staff-a` PATCHes their own real BSR line
   (`sec-project-a-bsr`) through a URL whose `[id]` segment says `sec-project-b` (a project they
   don't own) → `200 {"ok":true}` — succeeds, because the handler never reads that URL segment at
   all; it re-derives the true owning project (`sec-project-a`) from the row and checks access
   against that.
2. Same line, attacked by `sec-staff-b` (who owns neither the line nor, in this test, the URL's
   claimed project) through **both** `sec-project-a` and `sec-project-b` URLs → `403 {"error":"Not
   your record"}` both times — confirms the URL's project id is truly decorative for this route:
   changing it doesn't help an attacker, because the real check never consults it.
3. `PATCH /api/projects/sec-project-a/items/sec-project-b-item` (own project, cross-project item
   id) as `sec-staff-a` → `404`.
4. `PATCH /api/projects/sec-project-a/items/sec-project-a-item/recipe/sec-project-b-recipe` (own
   project, own item, cross-project **component** id) → `404`, worded as `"This component has no
   traceable Basic Rate source to refresh from."` — functionally correct (access denied, nothing
   leaked) but the message reads as if the component exists and merely lacks a source, when
   actually the id doesn't belong to this item/project at all; a minor wording clarity note, not
   filed as its own finding since there's no security or correctness impact.
5. `M-05-01`: negative `qty` on a BSR line accepted, then reset.
6. `M-05-02`: duplicate item code within one project → `500`.
7. `csp-test-staff` (zero permission) → `403` on `GET .../items`.

## Not tested this session
- `DELETE .../bsr/[lineId]` live (identical guard shape to `PATCH`, already proven twice above).
- Recipe component `rate`/`amount` range validation (same unbounded `z.number()` shape as every
  other money field found so far; not separately reproduced).
- Mid-batch failure injection on the item create/edit batches.

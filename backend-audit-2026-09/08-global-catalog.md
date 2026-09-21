# Backend Audit — Global Catalog (Basic Price / Basic Rate, cross-project views)

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `basic-price/route.ts` (GET, POST), `basic-price/[draftId]/route.ts`
  (PATCH, DELETE), `basic-price/[draftId]/promote/route.ts` (POST), `basic-rate/route.ts` (GET,
  POST), `basic-rate/[itemId]/route.ts` (PATCH, DELETE), `basic-rate/[itemId]/history/route.ts`
  (GET), `basic-rate/next-code/route.ts` (GET) — 6 files (7 counting `history` separately per the
  family table's own count), all methods.
- **Verdict:** 🔴 **BLOCKER** — `AUTHZ-VULN-02` is live-reproduced: racing the project-scoped and
  global promote endpoints against the same draft reliably throws an uncaught `500` from the
  global side. The good news inside the bad news: the underlying unique constraint still holds,
  so **no duplicate Basic Rate item was ever created** across 15 stress rounds — this is an
  error-handling gap, not a data-duplication one. Access control (including the dual-project
  reassignment guard) is otherwise clean, and the money-sign gap recurs here too.

## Summary
These are the cross-project "see everything I can reach in one place" views of Basic Price/Rate,
and the promote endpoint is duplicated here as a global counterpart to the project-scoped one
audited in family 6. The project-scoped promote route wraps its `db.batch()` in a `try/catch`
that turns the underlying Postgres unique-violation (`23505` on `base_items.promotedFromId`) into
a clean `400 "already promoted"` — this was confirmed fixed in family 6. **The global promote
route has no such catch.** Racing the two endpoints against the same still-`draft` row 15 times
(via a dedicated in-process `Promise.all` stress script, not separately-spawned `curl`
processes, which weren't tight enough to reliably hit the window) produced a raw `500` from the
global endpoint in 13 of 15 rounds. The database-level constraint is still the real backstop —
`0/15` rounds produced two successful promotions — so this is not the "duplicate rate item"
outcome the prompt's `AUTHZ-VULN-02` description raises as the worst case, but it is a
concretely reproduced, remotely-triggerable, uncaught exception, and exactly the shape `S2`
predicted in the abstract (a `23505` from a concurrent double-submit reaching the client as a
generic 500). Everything else in this family — the dual-project check on reassignment (mirroring
`clone`'s pattern from family 7), cross-project scoping on the list views, permission gating — is
clean.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Shared gate. |
| B. RBAC & escalation | ✅ | Zero-perm Staff → 403 on both `GET /api/basic-price` and `GET /api/basic-rate`. |
| C. IDOR & project scoping | ✅ | Global list views correctly filtered by `projectAccessClause` — confirmed live, every row returned to `sec-staff-a` had `projectId: sec-project-a`, none from `sec-project-b` despite both existing in the DB. Reassignment (`PATCH .../[draftId]` / `.../[itemId]` with a new `projectId`) correctly re-checks access on the **target** project, not just the source — confirmed live, reassigning into an unreachable project → `403`. |
| D. Injection & SQL layer | ✅ | Nothing new beyond S3. |
| E. Validation & mass assignment | 🔴 | `rate` unbounded on the global `basic-rate` routes too — `F-08-01` (same pattern as `F-07-01`, different endpoint). |
| F. Business logic & money | 🔴 | Same. |
| G. Integrity, transactions, concurrency | 🔴 | `AUTHZ-VULN-02` — see Findings. The unique constraint itself holds (no duplicate row), but the missing `catch` on the global promote route means the race surfaces as a raw `500`. |
| H. Errors, disclosure | 🔴 | Same finding, from the `H`-class angle: this is a remotely-triggerable, uncaught-exception 500 reachable by two ordinary users racing to promote the same draft from two different pages of the same app (one from the project's own Basic Price tab, one from the global catalog view) — not a contrived attack, a realistic double-click/two-tabs scenario. |

## Per-route matrix
| Route | Method | Guard in source | Zero-perm Staff | Cross-project | Verdict |
|---|---|---|---|---|---|
| `/api/basic-price` | GET | `requirePermission('projects','view')` + `projectAccessClause` | 403 | ✅ correctly scoped, confirmed by content | ✅ |
| `/api/basic-price` | POST | `requirePermission('projects','create')` + `requireProjectAccess` on the body's `projectId` | not re-run | not re-run (used routinely as fixture setup throughout this session) | ✅ |
| `/api/basic-price/[draftId]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess` on current **and** (if reassigning) target project | not re-run | ✅ 403 on reassignment into an unreachable project | ✅ |
| `/api/basic-price/[draftId]` | DELETE | `requirePermission('projects','delete')` + `requireProjectAccess` | not re-run | not re-run | ✅ (by inspection) |
| `/api/basic-price/[draftId]/promote` | POST | `requirePermission('projects','promote')` + `requireProjectAccess`, **no unique-violation catch** | not re-run | not re-run | 🔴 `AUTHZ-VULN-02` |
| `/api/basic-rate` | GET | `requirePermission('projects','view')` + `projectAccessClause` | 403 | ✅ correctly scoped | ✅ |
| `/api/basic-rate` | POST | `requirePermission('projects','create')` + `requireProjectAccess` | not re-run | not re-run | ✅ (by inspection — explicitly pre-checks the `(projectId, code)` conflict before insert, unlike family 5's `items` route) |
| `/api/basic-rate/[itemId]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess` on current **and** (if reassigning) target, plus a target-code-conflict pre-check | not re-run | ✅ (dual-project pattern, same as `[draftId]` above) | 🔴 `F-08-01` |
| `/api/basic-rate/[itemId]` | DELETE | `requirePermission('projects','delete')` + `requireProjectAccess` | not re-run | not re-run | ✅ (by inspection) |
| `/api/basic-rate/[itemId]/history` | GET | `requirePermission('projects','view')` + `requireProjectAccess` on the item's own `projectId` | not re-run | not re-run (parent/child pattern already proven twice in families 6/7) | ✅ (by inspection) |
| `/api/basic-rate/next-code` | GET | `requirePermission('projects','create')` + `requireProjectAccess` on a **required** query-param `projectId` | not re-run | not re-run | ✅ (by inspection — correctly requires `projectId` explicitly, unlike the old global version its own comment references) |

## Findings

### AUTHZ-VULN-02 (confirmed PARTIALLY OPEN, live-reproduced) — the global promote endpoint has no unique-violation catch; racing it against the project-scoped endpoint throws an uncaught 500 (no data duplication)
- **Severity:** High
- **Confidence:** Confirmed, live, reproduced 13/15 times under a dedicated concurrency stress
  script
- **Class:** Availability / Error handling (concurrency)
- **CWE:** CWE-248 (Uncaught Exception) / CWE-362 (Race Condition)
- **Location:** `src/app/api/basic-price/[draftId]/promote/route.ts:29-35` — the `db.batch([...])`
  call has no `try/catch`. Contrast with
  `src/app/api/projects/[id]/basic-price/[draftId]/promote/route.ts:32-48`, which wraps the
  identical batch and explicitly catches `e.code === '23505'` to return a clean `400`.
- **Request (stress script, `tests/audit/2026-09/race-promote.mts`):** for a single still-`draft`
  row, fire four promote requests simultaneously via `Promise.all` from one Node process (no
  per-process spawn jitter): two against
  `POST /api/projects/sec-project-a/basic-price/{draftId}/promote`, two against
  `POST /api/basic-price/{draftId}/promote`, each with a distinct `code`.
- **Response (representative round):**
  ```
  statuses = [200, 500, 400, 500]
  ```
  One project-scoped call succeeds; one project-scoped call gets the clean `400
  "already promoted"`; **both global calls that lose the race return `500 {"error":"Internal
  server error"}`** rather than the same clean `400`.
- **Expected:** Every losing attempt, from either endpoint, should get the same clean `400`
  regardless of which endpoint's request happened to land first.
- **Actual:** Confirmed across 15 rounds: **0/15** produced a second successful promotion (the
  `base_items.promotedFromId` unique constraint holds, so this is *not* exploitable as a
  duplicate-rate-item bug), but **13/15** produced at least one raw, uncaught `500` from the
  global endpoint. The response body itself leaks nothing (`apiRoute`'s generic catch still
  applies — no stack trace, no SQL text, no constraint name reaches the client), so this is an
  availability/robustness gap, not a disclosure one.
- **Impact:** A realistic, non-adversarial scenario — two people (or one person in two tabs)
  racing to promote the same draft, one from a project's own Basic Price tab and one from the
  global cross-project catalog view — reliably produces a server error for one of them instead of
  the friendly "already promoted" message the equivalent project-scoped race gives. Low security
  impact (no data corruption, no unauthorized access), but a real UX/robustness defect and exactly
  the class of remotely-triggerable 500 the `H` test class asks every route to be checked for.
- **Suggested fix (describe only):** copy the same `try { await db.batch(...) } catch (e) { if
  (e?.code === '23505') return 400 'already promoted'; throw e }` shape from the project-scoped
  promote route into this global one.

### F-08-01 (same pattern as `F-07-01`, different route) — global Basic Rate `rate` accepts negative values
- **Severity:** High
- **Confidence:** Confirmed, live
- **Class:** Business logic (money)
- **Location:** `src/app/api/basic-rate/route.ts:14` and
  `src/app/api/basic-rate/[itemId]/route.ts:10` — identical unbounded `rate: z.number(...)`.
- **Request:** `PATCH /api/basic-rate/sec-project-a-base-item {"rate":-777}` as Admin → `200`,
  accepted; reset to `2500` immediately after.
- **Impact / suggested fix:** identical to `F-07-01` — same field, reached through the global
  counterpart route instead of the project-scoped one. Cross-referenced, not double-counted in
  severity totals for the handover readiness rollup — see `00-INDEX.md`'s "single global fix"
  recommendation, which this is now the sixth confirmed instance of.

## Evidence log (live HTTP tests, this session)
1. `AUTHZ-VULN-02` stress test — see Findings; script and full 15-round transcript in
   `tests/audit/2026-09/race-promote.mts`'s output. Headline: `13/15` rounds produced a raw `500`
   from the global endpoint, `0/15` produced a duplicate `base_items` row.
2. `GET /api/basic-rate` as `sec-staff-a` → every one of the ~24 rows returned (accumulated from
   this session's own fixture/stress activity) has `projectId: "sec-project-a"` — none from `SEC
   Project B` or any other project, confirming `projectAccessClause` scopes this cross-project
   view correctly even under heavy fixture churn.
3. `PATCH /api/basic-price/{draftId} {"projectId":"sec-project-b"}` as `sec-staff-a` (attempting
   to reassign their own draft into a project they don't own) → `403 {"error":"Not your
   record"}`.
4. `F-08-01`: negative `rate` via the global `PATCH /api/basic-rate/[itemId]` accepted, then
   reset.
5. `csp-test-staff` (zero permission) → `403` on both `GET /api/basic-price` and `GET
   /api/basic-rate`.

## Not tested this session
- `DELETE` on both `[draftId]` and `[itemId]` live (guard shapes identical to their project-scoped
  siblings, already proven in families 6/7).
- `history`/`next-code` cross-project parent/child mismatch (pattern already proven twice over in
  families 6/7 on the identical query shape; judged low-incremental-value to repeat literally a
  third time).

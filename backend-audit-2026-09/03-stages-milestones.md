# Backend Audit — Stages & Milestones

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `projects/[id]/stages/route.ts` (GET), `projects/[id]/stages/[stageId]/route.ts`
  (PATCH), `projects/[id]/stages/[stageId]/milestones/[milestoneId]/route.ts` (PATCH) — 3 files,
  all methods.
- **Verdict:** 🟠 **NEEDS-FIX** — this is the family the prompt names as the historical site of a
  fixed milestone IDOR (`Already fixed` table), and that fix is confirmed holding under a harder
  test than the original. The recurring money-sign gap shows up again on `Stage.value`.

## Summary
This is the exact "characteristic bug" family the prompt describes: a nested resource authorised
against the URL's project id but then written without constraining it to that parent. The code
itself is aware of this — `stages/[stageId]/milestones/[milestoneId]/route.ts:21-24` has an
explicit comment naming the risk and the join guard that closes it. Tested it at its hardest: not
just "wrong project," but "right project, wrong stage" and "right project, right stage, wrong
milestone" — every combination returned `404`, never leaking or touching the other project's row.
The one real finding is the familiar one: `Stage.value` accepts a negative override, and the
math that guards against overspending the contract (`remaining = contract - otherOverrides -
value`) actually *rewards* a negative value with more apparent budget rather than rejecting it.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Shared gate, consistent with prior families. |
| B. RBAC & escalation | ✅ | Zero-perm Staff → 403 on stage PATCH. |
| C. IDOR & project scoping | ✅ | Cross-project GET → 403. **Parent/child mismatch, tested at every level of the chain** (own-project+other's-stage; own-project+own-stage+other's-milestone; own-project+other's-stage+other's-milestone) → `404` in all three shapes, never a write. |
| D. Injection & SQL layer | ✅ | Nothing new beyond `00-INDEX.md` S3; the milestone route's conditional `chequeDate` default uses a bound param, not interpolation. |
| E. Validation & mass assignment | 🔴 | `Stage.value` has no lower bound — `M-03-01`. |
| F. Business logic & money | 🔴 | Same issue — the over-budget guard is actively defeated by a negative override, not just unvalidated. |
| G. Integrity, transactions, concurrency | ✅ | The contract-expand-and-override write (`stages/[stageId]/route.ts:65-68`) is a real `db.batch()`, correctly atomic by construction; not separately mid-batch-failure-tested. |
| H. Errors, disclosure | ✅ | Clean 404/403 bodies; the over-budget 400 usefully echoes `shortfall`/`suggestedContract` without leaking anything internal. |

## Per-route matrix
| Route | Method | Guard in source | Zero-perm Staff | Cross-project | Parent/child mismatch | Verdict |
|---|---|---|---|---|---|---|
| `.../stages` | GET | `requirePermission('projects','view')` + `requireProjectAccess` | not re-run (see family 2 pattern) | 403 | N/A (list is derived from the project id only) | ✅ |
| `.../stages/[stageId]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess`, then a `where id=? and projectId=?` lookup | 403 | not re-run directly (parent/child test below is the harder version of the same guard) | **404** — a stage id from another project, inside this project's URL, resolves to nothing | ✅ |
| `.../stages/[stageId]/milestones/[milestoneId]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess`, then a 3-way join `where m.id=? and m.stageId=? and s.projectId=?` | not re-run (stage PATCH already proves the permission gate) | not re-run directly | **404** in every combination tested — this is the exact guard the prompt's "milestone IDOR (fixed 2026-09-01)" entry refers to, confirmed holding under a stricter test than a simple cross-project id swap | ✅ |

## Findings

### M-03-01 (new instance of the money-sign cluster) — `Stage.value` override accepts a negative number, defeating the over-budget guard rather than just being unvalidated
- **Severity:** High
- **Confidence:** Confirmed, live
- **Class:** Business logic (money)
- **CWE:** CWE-1284
- **Location:** `src/app/api/projects/[id]/stages/[stageId]/route.ts:8` (`patchStageSchema`,
  `value: z.number(...).nullable().optional()`, no lower bound) and the guard math at line 46:
  `const remaining = effectiveContract - otherOverriddenTotal - value`.
- **Request:**
  ```http
  PATCH /api/projects/sec-project-a/stages/sec-project-a-stage HTTP/1.1
  Origin: http://localhost:3006
  Cookie: vega_session=<sec-staff-a>
  Content-Type: application/json

  {"value":-500}
  ```
- **Response:** `200 {"ok":true}` — accepted.
- **Expected:** `400` — a stage's value override represents "this stage is worth this much of the
  contract"; a negative value has no representable meaning and, worse, actively breaks the
  guard's own arithmetic.
- **Impact:** This is not merely an unvalidated field — the guard that exists specifically to stop
  stage overrides from exceeding the contract (`remaining < 0` → reject) computes `remaining` by
  *subtracting* the new value from the budget. A negative value subtracts a negative, which
  **increases** `remaining` rather than consuming it — so the one safety check on this field
  rewards exactly the input that should fail it hardest. Downstream, `Stage.value` feeds
  `stageValue()`/`milestoneAmount()` (used by every income/outstanding calculation in
  `projects/[id]/route.ts`, `projects/route.ts`, and `dashboard/route.ts`), so a negative override
  on one stage of one project corrupts that project's income totals and, through the dashboard's
  unscoped company-wide rollup (see family 12), the company-wide figures too.
- **Suggested fix (describe only):** `.nonnegative()` (or `.positive()` if zero has no
  meaning) on `patchStageSchema.value`.

## Evidence log (live HTTP tests, this session)
1. `GET /api/projects/sec-project-b/stages` as `sec-staff-a` (cross-project) → `403 {"error":"Not
   your record"}`.
2. **Parent/child mismatch, stage level:** `PATCH
   /api/projects/sec-project-a/stages/sec-project-b-stage` (own project in the URL,
   correctly passes `requireProjectAccess`; the stage id belongs to `SEC Project B`) as
   `sec-staff-a` → `404 {"error":"Not found"}`.
3. **Parent/child mismatch, milestone level:** `PATCH
   /api/projects/sec-project-a/stages/sec-project-a-stage/milestones/sec-project-b-milestone`
   (own project, own stage, but a milestone id belonging to a stage under `SEC Project B`) →
   `404`.
4. **Parent/child mismatch, fully mismatched chain:** `PATCH
   /api/projects/sec-project-a/stages/sec-project-b-stage/milestones/sec-project-b-milestone`
   (own project in the URL, both the stage and milestone ids from `SEC Project B`) → `404`.
5. Sanity check on the caller's own real chain (`sec-project-a` / `sec-project-a-stage` /
   `sec-project-a-milestone`), `{"dueDate":"2026-12-01"}` → `200 {"ok":true}` — confirms the 404s
   above are the parent/child guard firing, not a broken route.
6. `M-03-01`: `{"value":-500}` on the caller's own stage → `200`, accepted; reset to `{"value":
   null}` immediately after confirming (`200`), returning the fixture to its default even split.
7. `csp-test-staff` (zero permission) → `403 {"error":"Missing permission: projects:edit"}` on the
   same stage PATCH.

## Not tested this session
- `expandContractTo` path (atomic contract-growth + override write) — read correctly from source
  as a genuine `db.batch()`; not independently exercised or mid-batch-failure-tested live.
- Milestone `amount` override range (same `z.number()` shape, likely the same gap as `M-03-01`;
  not separately reproduced).

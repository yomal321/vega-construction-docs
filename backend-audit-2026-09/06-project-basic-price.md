# Backend Audit — Project Basic Price

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `projects/[id]/basic-price/route.ts` (GET, POST),
  `projects/[id]/basic-price/[draftId]/route.ts` (PATCH, DELETE),
  `projects/[id]/basic-price/[draftId]/promote/route.ts` (POST) — 3 files, all methods.
- **Verdict:** 🟠 **NEEDS-FIX** — access control and the double-promotion defence are both solid;
  the money-sign gap from family 4 recurs here on `price`.

## Summary
This is one of the two routes the prompt names by number (`AUTHZ-VULN-01`, project-scoped
double-promotion) as a documented "known open" risk class, so it got the deepest concurrency
testing in this family. The result is good news: promoting the same draft twice — both
sequentially and under genuine concurrent load — is correctly rejected, and a live Postgres log
entry from an *earlier* session (`11:47:58`, `duplicate key value violates unique constraint
"base_items_promotedFromId_key"`) independently corroborates that the underlying unique
constraint is the real backstop, exactly as this route's own `catch` block documents. Access
control (permission gate, project scoping, the `promote` action specifically requiring its own
grant separate from `create`/`edit`) is clean. The recurring gap is validation: `price` has no
lower bound anywhere in this family, same pattern as family 4's `F-04-01`/`M-04-01`, and it
matters more here because a promoted draft's price becomes a Basic Rate `rate`, which multiplies
directly into every BSR/recipe amount downstream.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Shared gate, consistent with other families. |
| B. RBAC & escalation | ✅ | `promote` is gated on its own `projects:promote` action, independent of `create`/`edit` — confirmed live: a Staff account with create/edit but not promote is blocked specifically on promote, on their **own** project, with the correct "Missing permission: projects:promote" message. |
| C. IDOR & project scoping | ✅ | Cross-project read/promote → 403; same `code` promoted independently on two different projects with two different rates, no merge (`@@unique([projectId, code])` holds). |
| D. Injection & SQL layer | ✅ | Nothing new beyond `00-INDEX.md` S3. |
| E. Validation & mass assignment | 🔴 | `price` accepts negative values on draft creation — `M-06-01`. |
| F. Business logic & money | 🔴 | Same issue — a negative-priced draft, once promoted, becomes a negative-rate catalog item that feeds every recipe using it. |
| G. Integrity, transactions, concurrency | 🟢 | `AUTHZ-VULN-01` (double-promotion) **confirmed fixed**, both sequential and truly concurrent. |
| H. Errors, disclosure | ✅ | Clean 400/403/404 bodies throughout; the concurrent-promotion race's Postgres unique-violation (`23505`) is caught and converted to the same clean 400 the sequential case gets — never a raw 500 or leaked constraint name. |

## Per-route matrix
| Route | Method | Guard in source | Zero-perm Staff | Cross-project | Missing `promote` specifically | Verdict |
|---|---|---|---|---|---|---|
| `.../basic-price` | GET | `requirePermission('projects','view')` + `requireProjectAccess` | 403 | 403 | N/A | ✅ |
| `.../basic-price` | POST | `requirePermission('projects','create')` + `requireProjectAccess` | not re-run (see family 2/4 pattern) | not re-run | N/A | ✅ (by inspection + used successfully as a fixture-setup step throughout this session) |
| `.../basic-price/[draftId]` | PATCH | `requirePermission('projects','edit')` + `requireProjectAccess` | not re-run | not re-run | N/A | ✅ (by inspection) |
| `.../basic-price/[draftId]` | DELETE | `requirePermission('projects','delete')` + `requireProjectAccess`, plus a status guard (only `draft`-status rows deletable) | not re-run | not re-run | N/A | ✅ (by inspection) |
| `.../basic-price/[draftId]/promote` | POST | `requirePermission('projects','promote')` + `requireProjectAccess` | N/A (already covered by `view` gate upstream in practice) | 403 `"Not your record"` reachable, but permission check runs first so a caller missing both sees the permission error | 403 `"Missing permission: projects:promote"` | ✅ |

## Findings

### M-06-01 (new instance of the money-sign cluster) — Basic Price draft `price` accepts negative values, propagating into a promoted rate
- **Severity:** High
- **Confidence:** Confirmed, live
- **Class:** Business logic (money)
- **CWE:** CWE-1284
- **Location:** `src/app/api/projects/[id]/basic-price/route.ts:8-16` (`createDraftSchema`,
  `price: z.number(...).nullable()`, no lower bound) — same gap exists in
  `[draftId]/route.ts`'s `patchDraftSchema` and in `[draftId]/promote/route.ts`'s
  `promoteDraftSchema` (`price: z.number('Price must be a number')`, also unbounded).
- **Request:**
  ```http
  POST /api/projects/sec-project-a/basic-price HTTP/1.1
  Origin: http://localhost:3006
  Cookie: vega_session=<Admin>
  Content-Type: application/json

  {"activity":"05","cat":"material","name":"neg price test","unit":"Bag","price":-999}
  ```
- **Response:** `200`, draft created with `price: -999`.
- **Expected:** `400` — a catalog item's price can't be negative; there's no "credit" semantics
  anywhere this value is consumed.
- **Impact:** This is worse than family 4's `M-04-01` in one respect: a Basic Price draft's
  `price` becomes a Basic Rate `rate` on promotion (`promote/route.ts:37`, `unit, price` passed
  straight through from the request body — itself unbounded, so even a *positive*-drafted item
  can be promoted with a negative `price` supplied fresh at the promotion step, bypassing whatever
  value the draft held). A negative `rate` then multiplies directly into
  `RecipeComponent.amount` for every activity item that uses it (`amount = qty × rate`, per
  `prisma/schema.prisma`'s own comment on that field), corrupting BSR totals, project income
  calculations, and the company-wide dashboard rollup — a much larger blast radius than one
  expense row, because one catalog item can be referenced by many recipes across a project.
- **Suggested fix (describe only):** `.positive()` (or `.min(0)` if a free item is meant to be
  representable) on `price` in all three schemas — draft creation, draft edit, and promotion —
  since the promotion step re-accepts `price` from the request rather than trusting the draft's
  already-validated value.

## Evidence log (live HTTP tests, this session)
1. Promote a draft (`sec-project-a-bp-draft`, code `AUDIT-M-001`) → `200`. Promote the **same**
   draft id again with a different code → `400 {"error":"This draft has already been
   promoted."}` (sequential double-promotion, correctly rejected).
2. Fresh draft, two **genuinely concurrent** `POST .../promote` requests with different codes
   (`AUDIT-CONC-A` / `AUDIT-CONC-B`, backgrounded `curl` processes) → one `200` (code `A`), one
   `400` (already-promoted). Confirms `AUTHZ-VULN-01` holds under real concurrency, not just
   sequentially.
3. `sec-staff-a` (role has `create`/`edit` but not `promote`) creates a draft on their **own**
   project (`200`, allowed — `create` permission present) then attempts to promote it (`403
   {"error":"Missing permission: projects:promote"}`) — confirms `promote` is gated as its own
   distinct action, not folded into `edit`.
4. `sec-staff-b` (cross-project) attempts to view (`403 "Not your record"`) and promote (`403
   "Missing permission: projects:promote"` — permission check runs before the project-access
   check in this route, so a caller missing both sees the permission message first; both guards
   independently deny, no bypass) `sec-staff-a`'s draft.
5. `csp-test-staff` (zero permission) → `403 "Missing permission: projects:view"` on `GET
   .../basic-price`.
6. Cross-project catalog isolation: promoted code `AUDIT-M-001` independently on both `SEC
   Project A` (rate 2500) and `SEC Project B` (rate 300) — both succeeded, no merge, no
   collision, confirming `@@unique([projectId, code])` is respected.
7. `M-06-01`: negative `price` accepted on draft creation.

## Not tested this session
- `PATCH`/`DELETE .../basic-price/[draftId]` over HTTP directly (guard chains read correctly from
  source; not independently exercised).
- Promoting with a negative `price` supplied fresh at the promotion step (distinct from a
  negative-priced draft) — logically follows from the same unbounded schema, not separately
  reproduced live this session.

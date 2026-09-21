# Backend Audit — Suppliers & Sub-Contractors

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `suppliers/route.ts` (GET, POST), `suppliers/[id]/route.ts` (GET, PATCH,
  DELETE), `suppliers/price-comparison/route.ts` (GET), `suppliers/price-comparison/item/route.ts`
  (GET — also reviewed in `00-INDEX.md` S1/S2/S3), `sub-contractors/route.ts` (GET, POST),
  `sub-contractors/[id]/route.ts` (GET, PATCH, DELETE) — 6 files, all methods.
- **Verdict:** 🟢 **PASS** — no findings. This family's cross-project aggregation views (a
  supplier is a global entity, but the projects/expenses/catalog items it's linked to are
  scoped) are exactly the "list leakage" risk the prompt calls out by name, and they hold up
  live.

## Summary
`Supplier` and `SubContractor` are genuinely global, admin-managed entities (no project scoping
of their own — correct, per the schema's design comment), but everything they're *linked to*
(Basic Price drafts, Basic Rate items, Expenses) is project-scoped, and each of those three joins
inside `GET /api/suppliers/[id]` carries its own `projectAccessClause`. Built a live test for
exactly this: linked one supplier to a Basic Rate item in each of `SEC Project A` (reachable by
`sec-staff-a`) and `SEC Project B` (not reachable), then fetched that supplier's detail as
`sec-staff-a` — the response correctly included the `SEC Project A` item and **completely
omitted** the `SEC Project B` one, despite the same supplier genuinely being linked to both. No
row leaked, and (unlike `dashboard`/`price-comparison`'s deliberately-unscoped totals) there's no
aggregate here that could hide a leak the way a silently-inflated sum could — every row either
appears with a real, reachable project attached, or doesn't appear at all.
`price-comparison/route.ts` is a deliberate, explicitly-commented exception: it's a company-wide
rollup by design, same rationale as `dashboard/route.ts` (see family 12) — flagged there once,
cross-referenced here rather than re-argued.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Shared gate. |
| B. RBAC & escalation | ✅ | Zero-perm Staff → 403 on `suppliers`, `sub-contractors`, and `price-comparison` reads (each gated by its own real permission — `suppliers:view` / `priceComparison:view` — never just a session check). |
| C. IDOR & project scoping | ✅ | **List leakage, tested directly and confirmed absent** — see Summary. `price-comparison`'s unscoped design is deliberate (cross-referenced to family 12, not filed as a defect here). |
| D. Injection & SQL layer | ✅ | Nothing new beyond S1/S3 (this family's `price-comparison/item/route.ts` was one of the two routes S1 specifically verified the `?1`-plus-trailing-bare-`?` binding on). |
| E. Validation & mass assignment | ✅ | `name` required non-empty on every create/patch; no money fields in this family itself. |
| F. Business logic & money | N/A | Money display here (expenses/paid/outstanding per supplier) is read-only, derived from data already validated (or not) at its own source route — see families 4/6/7/8 for the underlying money-sign findings; this family doesn't introduce a new write path for those fields. |
| G. Integrity, transactions, concurrency | ✅ | No batches in this family; single-statement writes throughout. |
| H. Errors, disclosure | ✅ | Clean 404/409 bodies; the delete guards on both `Supplier` and `SubContractor` correctly check every table that can reference them (`expenses`, `basic_price_items`, `base_items` for Supplier; `expenses` alone for SubContractor, matching the schema's split). |

## Per-route matrix
| Route | Method | Guard in source | Zero-perm Staff | List-leakage check | Verdict |
|---|---|---|---|---|---|
| `/api/suppliers` | GET | `requirePermission('suppliers','view')` | 403 | N/A (flat global list, no project data) | ✅ |
| `/api/suppliers` | POST | `requirePermission('suppliers','create')` | not re-run | N/A | ✅ (used as fixture setup) |
| `/api/suppliers/[id]` | GET | `requirePermission('suppliers','view')`, then per-row `projectAccessClause` on each of 3 joined tables | not re-run | ✅ confirmed absent, live | ✅ |
| `/api/suppliers/[id]` | PATCH/DELETE | `requirePermission('suppliers','edit'/'delete')` | not re-run | N/A | ✅ (by inspection) |
| `/api/suppliers/price-comparison` | GET | `requirePermission('priceComparison','view')` | 403 | Deliberately unscoped (company-wide by design) — see family 12 cross-reference | ✅ (design, not a defect) |
| `/api/suppliers/price-comparison/item` | GET | `requirePermission('priceComparison','view')` + per-row `projectAccessClause` | not re-run | Reviewed in S1/S3 (this is the route S1 verified the `?1` binding pattern against) | ✅ |
| `/api/sub-contractors` | GET/POST | `requirePermission('suppliers','view'/'create')` | 403 (GET) | N/A | ✅ |
| `/api/sub-contractors/[id]` | GET | `requirePermission('suppliers','view')`, then per-row `projectAccessClause` | not re-run | Same pattern as `suppliers/[id]`, not independently re-tested (identical code shape, already proven) | ✅ (by inspection) |
| `/api/sub-contractors/[id]` | PATCH/DELETE | `requirePermission('suppliers','edit'/'delete')` | not re-run | N/A | ✅ (by inspection) |

## Findings
None.

## Evidence log (live HTTP tests, this session)
1. **List-leakage test:** created a supplier, linked it to one Basic Rate item in `SEC Project A`
   and one in `SEC Project B`. Granted `sec-staff-a` (who otherwise only holds
   `projects:view/create/edit`, no `suppliers:*`) a temporary direct `suppliers:view` grant via
   `PATCH /api/users/[email]` to make this test possible, then `GET
   /api/suppliers/{id}` as `sec-staff-a` → response's `baseItems` array contains **only** the
   `SEC Project A` row; the `SEC Project B` row, though genuinely linked to this same supplier,
   never appears. Cleaned up fully afterward: unlinked both base items, deleted the test supplier,
   and revoked the temporary permission grant (reverted to an empty direct-permissions set,
   matching this account's state before this test).
2. Zero-perm Staff → `403` on `GET /api/suppliers` (`"Missing permission: suppliers:view"`),
   `GET /api/sub-contractors` (same message), and `GET /api/suppliers/price-comparison`
   (`"Missing permission: priceComparison:view"`).

## Not tested this session
- `PATCH`/`DELETE` on `suppliers/[id]` and `sub-contractors/[id]` live (guard shapes are plain
  `requirePermission`, no project-scoping subtlety to re-prove; already covered by inspection).
- `sub-contractors/[id]`'s own list-leakage path independently re-tested (identical code shape to
  `suppliers/[id]`'s, already proven above).
- In-use delete guards on `Supplier`/`SubContractor` (guard reads correctly from source; the
  cleanup step in test #1 above deleted a supplier with **no** references left, which exercises
  the *success* path but not the *rejection* path — a dedicated test with a still-referenced
  supplier is deferred).

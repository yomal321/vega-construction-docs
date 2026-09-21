# Backend Audit — Reporting & Misc (Dashboard, Payments Summary, Notifications, Company Profile)

- **Audited:** 2026-09-21 · **Build:** `15c799b` + uncommitted working-tree changes (see
  `00-INDEX.md`) · **DB:** Option A, local Postgres (`vega_qa`)
- **Server:** `http://localhost:3006`
- **Routes covered:** `dashboard/route.ts` (GET), `payments/route.ts` (GET),
  `notifications/route.ts` (GET), `company-profile/route.ts` (GET, PATCH) — 4 files, all
  methods.
- **Verdict:** 🟠 **NEEDS-FIX** — this is where `00-INDEX.md`'s S4 note about `dashboard`'s
  deliberately-unscoped design gets its live proof, and the proof is more dramatic than expected:
  a Staff account that owns exactly one project out of six sees a **byte-identical** dashboard
  response to Admin, including named references (project id, stage name, milestone label, exact
  amount) to projects that account cannot otherwise see or know exist.

## Summary
`dashboard/route.ts` and `payments/route.ts` both carry an explicit code comment stating their
company-wide, unscoped design is intentional: "this permission is the whole gate... deliberately
NOT scoped by project ownership/membership." That's a defensible product decision for a
Finance-style rollup — but it means a single checkbox in the Role editor (`dashboard:view`, with
no accompanying project-access requirement of any kind) hands a Staff account visibility into
every other project's income, outstanding balance, expense category breakdown, and a
**named list of pending payments** (project id, stage name, milestone label, exact amount) for
projects that same account cannot open, list, or otherwise learn exist through any other route in
the app. This was proven live, not just read from the comment: granted `sec-staff-a` (owner of
exactly one project, `SEC Project A`, with zero other project access) a bare `dashboard:view`
grant and compared their `GET /api/dashboard` response byte-for-byte against Admin's — identical,
including a `pendingPayments` entry naming project `p2`'s "Ground floor structure" stage and its
exact ₨2,490,000 advance amount. `payments/route.ts` carries the identical design (same comment,
explicitly cross-referencing `dashboard`'s), but this local DB currently has no
Supplier/SubContractor-linked expenses to demonstrate it against live — not re-proven
independently for that reason, not because the code differs. `notifications` and
`company-profile` are both narrower and both correct: `notifications` soft-fails to an empty list
for a caller without `projects:view` rather than throwing (a deliberate UX choice, not a
security gap, since it reveals nothing), and `company-profile` is exactly as documented — open
read for any session (non-sensitive letterhead data), Admin-only write.

## Coverage
| Test class | Status | Notes |
|---|---|---|
| A. Auth & session | ✅ | Shared gate; `notifications` with no cookie → 401 same as everything else. |
| B. RBAC & escalation | ✅ | `company-profile` PATCH by a non-Admin Staff account (who does hold real `projects:*` permissions elsewhere) → 403, confirming this stays gated on the legacy Admin flag, not any RBAC permission. |
| C. IDOR & project scoping | 🔴 | `X-09` — see Findings. This is precisely the "a total that silently includes inaccessible projects is a leak even when no row is returned" scenario the prompt names by description, now with a live, named-data reproduction rather than a hypothetical one. |
| D. Injection & SQL layer | ✅ | Nothing new beyond S3 (`notifications`'s server-computed timestamp interpolation was already covered there). |
| E. Validation & mass assignment | ✅ | `company-profile`'s schema is straightforward required/optional strings; no money fields in this family. |
| F. Business logic & money | 🟡 | Read-only aggregation of numbers already validated (or not) elsewhere — see families 3/4/6/7/8 for the underlying money-sign findings this family's totals inherit. Incidentally confirmed live: `notifications` surfaced this session's own `F-07-01` negative-rate test edits as real "Rate updated" entries (`"...rate changed from -777.00 to 2500.00"`), showing that a corrupted rate produces a permanent, user-visible artifact, not just a silent DB value. |
| G. Integrity, transactions, concurrency | N/A | No writes in this family except `company-profile`'s single upsert. |
| H. Errors, disclosure | ✅ | Clean bodies throughout. |

## Per-route matrix
| Route | Method | Guard in source | Zero-perm Staff | Cross-project scoping | Verdict |
|---|---|---|---|---|---|
| `/api/dashboard` | GET | `requirePermission('dashboard','view')` only — **no project-access check anywhere** | not re-run (the point of this route is that no permission short of `dashboard:view` itself matters) | 🔴 confirmed unscoped, live | 🔴 `X-09` |
| `/api/payments` | GET | `requirePermission('payments','view')` only — same shape | not re-run | Same design, not independently re-proven live this session (no linked-vendor expense data currently exists to demonstrate against) | 🔴 `X-09` (by code parity) |
| `/api/notifications` | GET | `requireSession()`, then a soft `hasPermission(session,'projects','view')` check that returns an **empty list**, never `403`, on failure | ✅ `200 {"notifications":[]}`, not an error | Scoped correctly via `projectAccessClause` for callers who do pass the soft check | ✅ |
| `/api/company-profile` | GET | `requireSession()` only (deliberately open — non-sensitive letterhead data) | ✅ `200` | N/A (singleton, not project data) | ✅ |
| `/api/company-profile` | PATCH | `requireAdmin()` (legacy flag, not RBAC) | ✅ `403` (tried with a Staff account holding real `projects:*` permissions, to specifically confirm this isn't accidentally satisfied by any RBAC grant) | N/A | ✅ |

## Findings

### X-09 (cross-cutting design decision, given its own id since it's now proven live with named, non-anonymous data) — `dashboard:view` and `payments:view` expose named, project-identifying company-wide data with no project-access requirement
- **Severity:** Medium — deliberate design, not a code defect, but the data exposed is more
  specific than a bare aggregate total and the audit's job is to make that concrete for a
  handover sign-off decision, not to silently accept the existing code comment's judgment call.
- **Confidence:** Confirmed, live, byte-for-byte
- **Class:** Authorisation (information disclosure via aggregation) / Configuration
- **CWE:** CWE-863 (Incorrect Authorization) — the *module* permission is checked correctly and
  exactly as coded; the finding is that this module's own scope is company-wide by design, which
  is a business decision this report surfaces rather than a bug to fix.
- **Location:** `src/app/api/dashboard/route.ts:16-25` (comment: *"Deliberately NOT scoped by
  project ownership/membership: those govern reach into an individual project's own pages, not
  visibility into this aggregate financial view"*) and `src/app/api/payments/route.ts:35-41`
  (identical rationale, explicitly cross-referencing the dashboard route's comment).
- **Request:**
  ```http
  GET /api/dashboard HTTP/1.1
  Cookie: vega_session=<sec-staff-a — owns exactly one project, SEC Project A>
  ```
- **Response:** `200`, **byte-identical** to the same request made as Admin — including
  `"pendingPayments":[{"projectId":"p2","stageName":"Ground floor structure","stageNo":2,
  "label":"Advance","amount":2490000},...]`, where `p2` (`Two-storey house — Homagama`) is a
  project `sec-staff-a` has no ownership, membership, or any other reach into — `GET
  /api/projects` for this same account never lists it, `GET /api/projects/p2` 403s them directly.
- **Expected (if this is not the intended design):** figures scoped to projects the caller can
  reach, same rule every other cross-project view in this app (`basic-price`, `basic-rate`,
  `suppliers/[id]`) already follows.
- **Actual, and why it's flagged rather than silently accepted:** the code is unambiguous that
  this is intentional, and there's a real product argument for it (a Finance role needs
  company-wide numbers regardless of which individual projects they're assigned to). But
  `dashboard:view` and `payments:view` are ordinary checkboxes in the Role editor UI, grantable
  completely independently of any project access, with nothing in that UI signaling "this also
  reveals every other project's name, stage names, and payment amounts." Any Admin who grants
  `dashboard:view` alone to a limited-scope Staff role — for what looks like a narrow "let them
  see the summary tile" reason — has, by that single grant, also handed them project names and
  specific payment figures for parts of the business that role was never meant to touch.
- **Suggested action (describe only, not a code fix per the ground rules — this may be a
  documentation/sign-off item rather than a code change):** confirm with the client whether this
  scope is intended. If yes: document it explicitly in the Role editor UI (a one-line note next
  to the Dashboard/Payments permission checkboxes) so a future Admin grants it knowingly. If no:
  scope both queries by `projectAccessClause` the same way every other cross-project view in this
  app already does.

## Evidence log (live HTTP tests, this session)
1. Granted `sec-staff-a` a bare `dashboard:view` + `payments:view` direct permission grant (no
   change to their existing project-scoped role) via `PATCH /api/users/[email]`.
2. `GET /api/dashboard` as Admin vs. as `sec-staff-a` → identical JSON, including the
   cross-project `pendingPayments` entry described in `X-09`.
3. `GET /api/payments` as `sec-staff-a` and as Admin → both `{"suppliers":[],"subContractors":[],
   "unlinkedItems":[]}` — currently empty for everyone, because no expense in this local DB has a
   real `Supplier`/`SubContractor` FK link surviving to a named vendor (this session's own
   Supplier fixture from family 10 was already deleted by the time this test ran). The identical
   design (confirmed by reading the source, cross-referencing `dashboard`'s own comment) is
   reported under the same `X-09` id rather than treated as unverified, but flagged here as not
   independently demonstrated with live named data the way `dashboard` was.
4. Reverted `sec-staff-a`'s temporary permissions back to none immediately after.
5. `GET /api/notifications` as `csp-test-staff` (zero permission, fails the soft
   `hasPermission` check) → `200 {"notifications":[]}`, not `403` — confirmed deliberate,
   matches the route's own "no invented data" comment; reveals nothing.
6. `GET /api/notifications` as `sec-staff-a` → `200`, real content, including four "Rate updated"
   entries that are a direct, permanent artifact of this session's own `F-07-01` negative-rate
   test edits (family 7) — incidental confirmation that a corrupted rate isn't just a stored
   number, it surfaces to end users.
7. `GET /api/notifications` with no cookie → `401` (shared gate, unlike the soft in-handler
   check above which only applies once a session exists).
8. `GET /api/company-profile` as `csp-test-staff` → `200`, real (pre-existing, from an earlier
   session's fixture data) company profile — confirmed open-read-by-design.
9. `PATCH /api/company-profile` as `sec-staff-a` (holds real `projects:*` permissions, to
   specifically rule out any RBAC grant accidentally satisfying this) → `403 {"error":"Admin
   access required"}`.

## Not tested this session
- Independently reproducing `payments/route.ts`'s cross-project inclusion with a real linked
  Supplier/SubContractor expense (blocked by current DB state, not by the code — a future session
  should create one fixture expense with a real `supplierId` in a project the test account can't
  reach, then repeat the exact comparison done for `dashboard` above).
- `company-profile` PATCH's upsert-on-first-save path (row already existed in this DB from an
  earlier session; the "no row yet" branch wasn't exercised).

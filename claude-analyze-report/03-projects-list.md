# QA Audit — Projects list (`/projects`)

- **Audited:** 2026-09-03
- **Build/commit:** `89395b8` (working tree modified only by audit artefacts)
- **Verdict:** NEEDS-FIX
- **Playwright spec:** `vega-manager/tests/03-projects-list.spec.ts` — 16 tests, 12 passed, 4 failed (all four failures are findings F-03-01 … F-03-04, working as intended)

## Summary

`/projects` lists every project the signed-in user can reach and is the entry point for creating
one. Creation is not a thin insert: `POST /api/projects` also scaffolds `stages × 3` milestone rows
(Advance 50 / Interim 25 / Final 25) in a single D1 batch, so the request body drives how much gets
written. Deletion is the mirror image — a 13-statement batch that explicitly removes every
dependent row, because D1 does not reliably honour `ON DELETE CASCADE`.

**Authorisation on this page is excellent and I could not break it.** Every IDOR probe was refused:
a Staff user *holding* `projects:edit` and `projects:delete` still cannot touch a project outside
their reachable set, mass assignment of `id`/`ownerId`/`status`/`curStage` is ignored, and the
delete cascade leaves no orphans. A stored `<img onerror>` payload in a project name rendered as
inert text.

**The problem on this page is input validation.** `createProjectSchema` constrains types but not
ranges, and one field is parsed outside the schema entirely. Four separate probes got through, and
one of them — a negative contract value — **silently corrupted the company-wide outstanding figure
on the dashboard**, which I reproduced end to end.

## Coverage

| Test class | Status | Notes |
|---|---|---|
| A. Functional / Playwright | ✅ | List loads clean, create round-trips and persists, delete cascades with zero orphans |
| B. Authentication & session | ✅ | Covered by page 1; Staff with no role correctly refused 403 on both GET and POST |
| C. Authorisation / RBAC / IDOR | ✅ | **4 IDOR probes, all correctly refused**; mass assignment blocked; creator-becomes-owner verified |
| D. SQL injection & input handling | ❌ | 4 validation gaps (F-03-01 … F-03-04); XSS correctly neutralised |
| E. Headers / disclosure | ✅ | Inherits the app-wide set verified on page 1; the 500 body leaks nothing |
| F. Data integrity & business rules | ❌ | Invalid input reaches the DB and corrupts a company-wide aggregate (F-03-03) |

## Findings

### F-03-03 — A negative contract value is accepted and silently corrupts the company-wide outstanding figure
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Data integrity
- **Location:** `src/app/api/projects/route.ts:15` (`contract: z.number()` — no `.min()`)
- **Reproduction:**
  1. Note the dashboard's outstanding total: **LKR 32,799,375**.
  2. `POST /api/projects` with `contract: -9999999` (everything else valid).
  3. Re-read `GET /api/dashboard`.
- **Expected:** Rejected with a 400 — a contract value cannot be negative.
- **Actual:** **HTTP 200**, project created, and the portfolio total silently drops.
- **Evidence:**
  ```
  before:  {"received":16920625,"outstanding":32799375,...}
  POST /api/projects  contract:-9999999   -> HTTP 200
  after:   {"received":16920625,"outstanding":22799376,...}

  32,799,375 - 22,799,376 = 9,999,999   <- exactly the injected negative contract
  ```
  The list endpoint renders it as `income {'received': 0, 'outstanding': -9999999}`.
- **Impact:** This is the finding I would fix first on this page. It needs no attacker — a user
  typing a stray minus sign into the contract field gets no error, no warning, and no visible sign
  anything is wrong on the project itself. The damage surfaces somewhere else entirely: the
  company-wide receivables figure on the dashboard, which is the number the business steers by.
  Because the project looks normal in the list, the cause is very hard to trace back from the
  symptom.
- **Suggested fix:** `contract: z.number().min(0, 'Contract value cannot be negative')`, and the
  same on `patchProjectSchema` (`src/app/api/projects/[id]/route.ts:17`), which has the identical
  gap. (Describe only — not implemented.)

### F-03-04 — `stages` is unbounded: one request wrote 3,000 milestone rows in 0.34 s
- **Severity:** Medium
- **Confidence:** Confirmed
- **Class:** Data integrity / Availability
- **Location:** `src/app/api/projects/route.ts:14` (`stages: z.number().int()` — no `.max()`), amplified at `route.ts:87-96`
- **Reproduction:** `POST /api/projects` with `stages: 1000`.
- **Expected:** Rejected, or capped at a sane maximum.
- **Actual:** **HTTP 200 in 0.34 s**, having written 1,000 `stages` rows and 3,000 `milestones` rows.
- **Evidence:**
  ```
  POST /api/projects  stages:1000  -> HTTP 200  [0.344 s]
  select count(*) from stages     -> 1013   (was 13)
  select count(*) from milestones -> 3039   (was 39)
  ```
- **Impact:** Write amplification of 3n+1 rows per request with no ceiling, available to anyone
  holding `projects:create`. `stages: 1000000` would attempt three million inserts in a single D1
  batch — well past Workers' CPU/subrequest limits and D1's batch limits, so the realistic outcome
  is a wedged request and a partially-written project, on a database with no automated backup
  discussed in this audit. I deliberately stopped at 1,000 rather than probe the true failure point
  against the local database. Note the *seeded* projects use 3-5 stages, so a cap of, say, 50 costs
  nothing real.
- **Suggested fix:** `.min(1).max(50)` on `stages`. (Describe only.)

### F-03-01 — An unparseable start date crashes the handler with a 500 instead of returning 400
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** Input handling
- **Location:** `src/app/api/projects/route.ts:13` (validated only as a non-empty string) then `route.ts:84` (`new Date(body.start).toISOString()`)
- **Reproduction:** `POST /api/projects` with `start: "not-a-date"`.
- **Expected:** `400` naming the bad field.
- **Actual:** `500 {"error":"Internal server error"}`.
- **Evidence:**
  ```
  $ curl -X POST /api/projects -d '{...,"start":"not-a-date",...}'
  {"error":"Internal server error"}  [HTTP 500]
  ```
  `new Date("not-a-date")` yields `Invalid Date`, and `.toISOString()` on it throws a `RangeError`,
  which `apiRoute` maps to its generic 500 branch.
- **Impact:** No information leak — the body is correctly generic. The cost is the same as X-02:
  a client error is recorded as a server fault, and this app has no error tracking beyond
  Cloudflare's logs, so genuine 500s get buried. The UI uses a date picker, so this is
  API-reachable rather than something a normal user will hit. `patchProjectSchema` has the same
  unguarded `new Date(patch.start)` at `[id]/route.ts:82`.
- **Suggested fix:** Validate the date parses in the schema (e.g. a `.refine()` on
  `Number.isNaN(Date.parse(v))`) so it fails as a 400. (Describe only.)

### F-03-02 — Zero and negative stage counts are accepted, creating structurally invalid projects
- **Severity:** Low
- **Confidence:** Confirmed
- **Class:** Data integrity
- **Location:** `src/app/api/projects/route.ts:14`
- **Reproduction:** `POST /api/projects` with `stages: -5`, and again with `stages: 0`.
- **Expected:** Rejected — a project must have at least one stage.
- **Actual:** Both return **HTTP 200**. The `for (let i = 0; i < body.stages; i++)` loop simply
  never executes, so the project is created with **no stages and no milestones at all**, while its
  `stages` column claims `-5`.
- **Evidence:**
  ```
  POST stages:-5 -> 200 {"id":"proj_...","stages":-5,...}
  POST stages:0  -> 200 {"id":"proj_...","stages":0,...}
  ```
- **Impact:** Produces a project whose stored stage count disagrees with reality, which then feeds
  `stageValue()`/`projectIncome()`. Blast radius is smaller than F-03-03 (income computes to zero
  rather than a wrong number), but it is junk data the UI will still render and offer to edit.
- **Suggested fix:** Same `.min(1).max(50)` as F-03-04. (Describe only.)

## Tested and clean

- **Every IDOR probe was correctly refused.** This is the strongest result of the audit so far. The
  fixture deliberately gave Kasun `projects:view/create/edit/delete` while leaving him able to
  reach only `p4` — so a refusal proves *project scoping* works, not merely that the permission
  check fired:
  ```
  PATCH  /api/projects/p1  (rename attempt) -> refused; p1's name unchanged in the DB
  DELETE /api/projects/p2                    -> refused; p2 still present in the DB
  GET    /api/projects/p3                    -> refused
  GET    /api/projects (list)                -> exactly ['p4'], no leaked rows
  ```
  Each write probe was verified against the database afterwards, not just by the response code.
- **Mass assignment is fully blocked.** A create body carrying `id: 'attacker_chosen_id'`,
  `ownerId: <another user>`, `status: 'Completed'` and `curStage: 99` was accepted, but **none** of
  those values were written — the server generated its own id, set `ownerId` to the caller, and
  forced `status: 'Active'`, `curStage: 1`.
- **A Staff-created project is owned by its creator**, not silently reassigned.
- **Delete leaves no orphans.** After deleting a project, all of `projects`, `stages`, `milestones`,
  `expenses` and `project_members` returned 0 rows for that id — verified by direct SQL, which is
  what `doc/ORPHANED_ROWS_FIX_PROMPT.md` set out to guarantee. The explicit 13-statement batch does
  hold.
- **Create genuinely persists and scaffolds correctly** — re-read from the server (not the POST
  echo), and the default 2 stages × 3 milestones = 6 milestone rows were verified in the DB.
- **Stored XSS is neutralised.** A project named `<img src=x onerror="window.__xss=1">` rendered as
  visible text; `window.__xss` was never set and no dialog fired. React's default escaping is doing
  its job — worth noting given CSP provides no backstop (X-03).
- **Staff with no role is refused outright** — 403 on both `GET` and `POST /api/projects`.
- **No `NaN`, `Infinity`, `Invalid Date` or `undefined`** rendered in the list, and no money value
  with more than two decimal places.
- **Zero console errors and zero page errors** on load.

## Not tested / blocked

- **The local database is the developer's working D1, not a pristine seed.** It carries three
  pre-existing roles (`Full Access (Legacy)`, `analyzer`, `fincace`) that `prisma/seed.ts` does not
  create — confirmed: the seed file contains **zero** references to `roles` or `role_permissions`,
  which is what F-02-03 is about. These were left alone. Anyone reproducing these results on a
  freshly reset database may see different role data.
- **The true failure point of F-03-04 was not probed.** I stopped at `stages: 1000`; I did not push
  to the value that actually breaks D1's batch limit, since that risks leaving a half-written
  project in the database.
- **UI-driven creation was not exercised through the modal** — create/validation was tested at the
  API level, which is where the gaps are. The modal's own client-side validation (which may well
  block negative numbers before they are sent) was not assessed, and does not affect the findings:
  every one of them is reachable by any authenticated caller regardless of what the form does.
- **Sorting, searching, pagination and empty-list states were not exercised** — the list renders 4
  projects and I did not test it at scale or at zero.
- **Concurrency (two admins editing the same project, double-click submit) was not tested here** and
  is better placed on page 4, where the editing surface actually lives.

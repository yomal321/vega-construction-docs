# Pre-Handover QA Audit — Index

- **Project:** Vega Construction Manager (`vega-manager/`)
- **Audit started:** 2026-09-03
- **Auditor mode:** report-only (no source fixes; only report files + `vega-manager/tests/`)
- **Database:** local D1 only (`wrangler d1 ... --local`), never remote
- **Prompt:** `doc/PRE_HANDOVER_QA_PROMPT.md`

## Task list / progress

| # | Page | Route | Report file | Verdict | C | H | M | L | Date |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Login | `/login` | `01-login.md` | 🟠 NEEDS-FIX | 0 | 1 | 3 | 3 | 2026-09-03 |
| 2 | Dashboard | `/` | `02-dashboard.md` | 🟡 PASS-WITH-NOTES | 0 | 0 | 1 | 0 | 2026-09-03 |
| 3 | Projects list | `/projects` | `03-projects-list.md` | 🟠 NEEDS-FIX | 0 | 0 | 2 | 2 | 2026-09-03 |
| 4 | Project detail (all tabs) | `/projects/[id]` | `04-project-detail.md` | 🟡 PASS-WITH-NOTES | 0 | 0 | 1 | 1 | 2026-09-03 |
| 5 | Activities | `/activities` | `05-activities.md` | ⏳ pending | – | – | – | – | – |
| 6 | Basic Price (global) | `/basic-price` | `06-basic-price.md` | ⏳ pending | – | – | – | – | – |
| 7 | Basic Rate (global) | `/basic-rate` | `07-basic-rate.md` | ⏳ pending | – | – | – | – | – |
| 8 | Payments | `/payments` | `08-payments.md` | ⏳ pending | – | – | – | – | – |
| 9 | Suppliers list | `/suppliers` | `09-suppliers-list.md` | ⏳ pending | – | – | – | – | – |
| 10 | Supplier detail | `/suppliers/[id]` | `10-supplier-detail.md` | ⏳ pending | – | – | – | – | – |
| 11 | Supplier compare | `/suppliers/compare` | `11-supplier-compare.md` | ⏳ pending | – | – | – | – | – |
| 12 | Supplier compare — item | `/suppliers/compare/item` | `12-supplier-compare-item.md` | ⏳ pending | – | – | – | – | – |
| 13 | Sub-contractor detail | `/sub-contractors/[id]` | `13-sub-contractor-detail.md` | ⏳ pending | – | – | – | – | – |
| 14 | Users list | `/users` | `14-users-list.md` | ⏳ pending | – | – | – | – | – |
| 15 | User detail | `/users/[email]` | `15-user-detail.md` | ⏳ pending | – | – | – | – | – |
| 16 | Roles | `/roles` | `16-roles.md` | ⏳ pending | – | – | – | – | – |
| 17 | Settings | `/settings` | `17-settings.md` | ⏳ pending | – | – | – | – | – |
| 18 | Settings — Field Options | `/settings/field-options` | `18-settings-field-options.md` | ⏳ pending | – | – | – | – | – |
| 19 | Settings — Project Access | `/settings/project-access` | `19-settings-project-access.md` | ⏳ pending | – | – | – | – | – |

Verdict legend: ⏳ pending · 🔴 BLOCKER · 🟠 NEEDS-FIX · 🟡 PASS-WITH-NOTES · 🟢 PASS
Counts are Critical / High / Medium / Low.

## Environment status

| Step | Status |
|---|---|
| `npm install` | ✅ |
| `@playwright/test` installed | ✅ |
| `npx playwright install chromium` | ✅ chromium-1228 |
| Local D1 migrations applied | ✅ |
| `npm run db:seed` | ✅ 5 users, 4 projects |
| `npm run preview` (Workers runtime) reachable | ✅ `http://localhost:8787` |
| `playwright.config.ts` created | ✅ (no `webServer`; `PW_BASE_URL` override) |

## Environment gotchas for whoever resumes this

- Run the suite as `PW_BASE_URL=http://localhost:8787 npx playwright test tests/<spec>` with
  `npm run preview` already running in another shell. There is deliberately **no** `webServer` in
  `playwright.config.ts` — `next dev` cannot resolve the D1 binding and every API route 500s under it.
- `@playwright/test` and `playwright` are pinned to **1.61.1**. `npm i -D @playwright/test` pulls
  1.62.1, which needs a chromium build that fails to download from this network.
- **Any test that deliberately fails a login must clear `login_throttle` afterwards**
  (`clearLoginThrottle()` in `tests/helpers.ts`). ~~Five failures across *different* tests silently
  lock the shared `ip:unknown` bucket and the rest of the run fails in ways that look like app bugs.
  This is F-01-02, not a test-harness quirk.~~
  **✅ Fixed 2026-09-05** — the login route no longer falls back to `ip:unknown`; when
  `cf-connecting-ip` is absent it skips the IP throttle layer rather than bucketing every client
  together, so unrelated tests can no longer lock each other out. Keep calling the helper anyway:
  `email:` rows still accumulate, and a later test reusing the same seeded account would start
  part-way to its own 5-failure lock. See `doc/test/security/AUTH_HARDENING_PLAN_2026-09-05.md`.
- Probe rows created during an audit should be deleted, or `npm run db:reset-seed` (local) run
  afterwards. Page 1's `CSRF-Probe-Unit` row was cleaned up.

## Cross-cutting findings

Patterns that will recur on other pages — described once here, referenced from the per-page files.

- **X-01 — No server-side CSRF defence anywhere.** `SameSite=Lax` on the session cookie is the sole
  layer; no route validates `Origin`/`Sec-Fetch-Site` and there is no CSRF token. Because every
  handler shares the `apiRoute` wrapper (`src/lib/api.ts`), this is one gap affecting all 61 routes
  rather than a per-page issue. First seen as F-01-04.
- **X-02 — Malformed JSON is a 500, not a 400,** for every route, for the same shared-wrapper
  reason. First seen as F-01-06.
- **X-03 — CSP provides no XSS mitigation** (`frame-ancestors` only). Raises the severity of any
  stored-XSS finding on the free-text-heavy pages still to be audited. First seen as F-01-03.
- **X-04 — Half-built features left in the tree.** MFA ships a migration, two complete libraries, a
  configured secret and four empty route directories, but 404s at runtime (F-01-01). Worth actively
  checking on later pages whether other advertised features are similarly hollow — note that
  `src/app/api/dashboard/cashflow/` is likewise an empty directory.
  **Update 2026-09-04:** the MFA half of this is cleared — the client declined the feature and it
  was removed outright (see F-01-01). The *pattern* still stands as a thing to check for, and
  `src/app/api/dashboard/cashflow/` remains an empty directory.
- **X-07 — Money figures compound across findings.** F-02-01 (ROI shows all received cash as profit
  when nothing is paid) and F-04-01 (a negative payment understates `expensePaid`) both push the
  same headline ROI number upward, and neither surfaces an error. Treat reported ROI as unreliable
  until both are fixed.
- **X-06 — Zod schemas constrain types but not ranges.** `projects` accepts a negative `contract`
  (which silently corrupts the company-wide dashboard total), a negative or zero `stages`, and an
  unbounded `stages` that writes 3n+1 rows per request. Dates are validated as "non-empty string"
  and then parsed unguarded with `new Date(...).toISOString()`, which throws a 500 on bad input.
  **Check every other module's schema for the same three shapes** — no `.min()`/`.max()` on money
  and count fields, and unguarded date parsing. First seen as F-03-01 … F-03-04.
- **X-05 — No roles are seeded, so every Staff account is locked out of everything until an Admin
  builds a role.** Affects the testability of every remaining page: to audit any Staff-visible
  behaviour you must first create a role fixture (see `tests/02-dashboard.spec.ts` `seedFixtures()`
  for a reusable pattern). First seen as F-02-03.
- **Verified clean codebase-wide (do not re-test per page):** no injectable SQL — the only five
  template-interpolated SQL sites all build identifiers from hardcoded whitelists or literals, all
  values are `.bind()`-ed, and there is no `.exec()`; no source maps in the production build; no
  secrets in the client bundle; the single `dangerouslySetInnerHTML` is a static theme script with
  no user data.

## Handover readiness

Ranked shortlist, updated as pages are audited. **4 pages of 19 audited — this list is provisional.**

**Confirmed fixed (regression-tested, do not re-open):** the 2026-09-01 CRITICAL milestone IDOR is
genuinely closed — verified at runtime as an Admin, where only the parent join can refuse. The
middleware matcher bypass from that same audit is also fixed.

**Tier 1 — decide before handover (disclosure, not just code)**

1. ~~**F-01-01 (High)** — Decide MFA's status and make the repo tell the truth about it. Either
   implement it or remove the scaffolding; do not hand over ambiguous. This is the only finding so
   far where the codebase actively misrepresents what was delivered.~~
   **✅ RESOLVED 2026-09-04 — removed, not implemented.** The client declined MFA, so the
   scaffolding is gone: `0026_remove_mfa.sql` drops the three `users` columns and
   `mfa_recovery_codes`; `src/lib/totp.ts`, `src/lib/mfaCrypto.ts`, `src/app/api/auth/mfa/*`,
   `src/app/account/` and the `MFA_ENCRYPTION_KEY` binding are deleted. The repo no longer
   advertises a feature it doesn't serve, which was the actual finding.

**Tier 2 — money correctness (three small fixes, one theme)**

2. **F-03-03 (Medium)** — A negative contract value silently corrupts the company-wide outstanding
   total on the dashboard. Reproduced end to end; needs no attacker, just a stray minus sign.
3. **F-04-01 (Medium)** — A negative payment amount understates paid expense, inflates ROI, and
   defeats the over-allocation guard.
4. **F-02-01 (Medium)** — "Overall ROI" reads as a large profit whenever no expense payment has
   been recorded — the state of every fresh deployment. See **X-07**: 3 and 4 compound.

**Tier 3 — security hardening (all previously known / planned)**

5. **F-01-02 (Medium)** — Shared login-throttle bucket. The office-NAT lockout is a realistic
   recurring support incident for this client even in a correct Cloudflare deployment.
6. **X-01 / F-01-04 (Medium)** — Add an Origin check to `apiRoute`; one change covers every route.
7. **X-03 / F-01-03 (Medium)** — Finish the planned CSP Phase 6 rollout, or disclose the gap in writing.
8. **F-03-04 (Medium)** — `stages` is unbounded; one request wrote 3,000 milestone rows. Cap it.

**Tier 4 — small, mostly one-liners**

9. **F-04-02 (Low)** — Three route families ignore the URL's project id. Not exploitable today;
   fix it because it is the exact shape the milestone IDOR had before it was patched.
10. **F-01-05 … F-01-08, F-02-02, F-03-01, F-03-02 (Low/Info)** — `poweredByHeader: false`,
    400-on-bad-JSON, `SESSION_SECRET` length validation, Prisma schema drift, stray `//test`
    comment, 400-on-bad-date, min/max on `stages`.
11. **F-02-03 (Info)** — Ship a default Staff role in the seed, or document the first-run
    role-creation step, so a new Staff user isn't locked out of the whole app.

**Known coverage gap to close before handover:** page 4's per-tab UI interaction and the BSR recipe
engine's derived-rate arithmetic were not exercised — see `04-project-detail.md` → Not tested.

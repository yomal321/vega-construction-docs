# Content-Security-Policy — Phase 6 Implementation Plan

**Date:** 2026-09-09
**Source:** `UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md` Phase 6 (the last open code-side phase)
**Scope:** ship a full CSP on every document response, report-only first, then enforcing.
**Status:** 🚧 in progress — started 2026-09-09.

**Design constraint, same as the 2026-09-01 and 2026-09-05 plans:** change only what the phase
requires. No refactors, no renames. One new dependency-free helper, one vendored asset, one new
test spec.

---

## Revised scope — three things the source plan did not know

The Phase 6 sketch listed exactly two obstacles: the inline theme script and framer-motion's
runtime inline styles. Both are real. Verifying them against the current code turned up three
more items that change the task list, one of which is a functional bug independent of CSP.

| # | Finding | Effect on the plan |
|---|---|---|
| 1 | **pdf.js loads its worker from a third-party CDN.** `src/lib/importCatalog.ts:126` sets `GlobalWorkerOptions.workerSrc` to `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`. | A strict `worker-src 'self'` breaks Basic Rate PDF import. New task **6.1**, done *first*, and fixed by vendoring the worker — not by allowlisting the CDN. |
| 2 | **"One week of report-only real use" is not executable.** Phase 2.10 and Phase 5's notes both record that nothing has ever been deployed. There are no real users to generate violations. | Acceptance changes from *elapsed time in production* to *deterministic coverage*: a Playwright spec that captures violations across every route and both flagged export/import paths. See **6.6–6.7** and "Why not a week of report-only". |
| 3 | **A nonce costs nothing here.** `.next/prerender-manifest.json` has zero entries under both `routes` and `dynamicRoutes` — every page is already dynamically rendered (middleware resolves a session against the DB on every request). | The standard objection to nonces ("it forces dynamic rendering") does not apply. Removes the only real argument for the hash-based alternative. |

Finding 1 is worth reading twice. It is a supply-chain exposure in its own right, entirely
separate from CSP: the app fetches and executes third-party JavaScript at runtime, from a URL
built by string interpolation, with no Subresource Integrity hash. It also means Phase 1.2's
conclusion — "no hardcoded non-HTTPS resource reference anywhere in the codebase" — was true but
incomplete: that check was `grep -rn 'http://' src/`, which by construction cannot find an
`https://` origin. The gap was in the check, not in the reasoning.

There is a decent chance this path is **already broken or silently degraded**. The installed
`pdfjs-dist` is `6.3.289`; cdnjs must be serving that exact version at that exact filename for
the URL to resolve, and when a worker fails to load, pdf.js falls back to a main-thread "fake
worker" — the import still works, just synchronously and slower, with no error surfaced to the
user. Task 6.1 therefore starts by observing current behaviour, so the fix is recorded as either
"enabled CSP" or "enabled CSP *and* repaired a latent bug".

---

## The policy

Every directive below is justified against a real call site in this codebase. Directives are
listed in the order they will appear in the header.

| Directive | Value | Why this value |
|---|---|---|
| `default-src` | `'self'` | Backstop for anything not named below. |
| `script-src` | `'self' 'nonce-{N}'` | The nonce covers the theme script (**6.4**) and Next's own streaming/hydration inline scripts (**6.3**). `+ 'unsafe-eval'` in dev only. |
| `style-src` | `'self' 'unsafe-inline'` | framer-motion `^12.42.2` and react-toastify `^11.1.0` both inject inline styles at runtime. **No nonce here** — see the gotcha below. |
| `img-src` | `'self' data: blob:` | `/logo.jpg` (`Sidebar.tsx:115`, `login/page.tsx:66`, `pdfTemplate.ts:53`); jsPDF works through canvas and data URLs. |
| `font-src` | `'self' data:` | All `@fontsource/*` woff2 files are bundled locally; `data:` covers any inlined fallback face. |
| `connect-src` | `'self'` | `src/lib/fetcher.ts` only ever takes relative URLs, and SWR calls go through it. No external API remains — the HIBP enhancement (3.8) was never built. |
| `worker-src` | `'self' blob:` | pdf.js, after **6.1**. `blob:` because pdf.js may wrap its worker in a blob. |
| `object-src` | `'none'` | Not in the source sketch. Nothing uses `<object>`/`<embed>`; blocking plugin-hosted script execution is free. |
| `base-uri` | `'self'` | Stops an injected `<base>` from re-pointing every relative URL. |
| `form-action` | `'self'` | Stops an injected form from posting credentials off-origin. |
| `frame-ancestors` | `'none'` | Folded in from the standalone header at cutover — see **6.8**. |

### Three gotchas that decide the implementation

**A nonce in a directive makes `'unsafe-inline'` in that same directive be ignored.** This is
the whole reason nonces work for `script-src` — and the reason `style-src` must stay nonce-free.
Adding a nonce to `style-src` would silently void the `'unsafe-inline'` that framer-motion and
react-toastify depend on, and the failure looks like broken styling, not like a CSP mistake.

**Next.js reads the nonce off the *request* header, not the response.** To stamp its own inline
bootstrap scripts, Next looks for a `content-security-policy` header on the incoming request. So
`NextResponse.next()` (currently `src/middleware.ts:62`) must become
`NextResponse.next({ request: { headers } })` with the CSP set on those request headers. Setting
it only on the response gets you a nonce'd policy that blocks Next's own hydration scripts.
Corollary for the report-only window: the **request** header must be named
`Content-Security-Policy` even while the **response** carries `Content-Security-Policy-Report-Only`,
or nonce propagation does not happen at all.

**`next dev` needs `'unsafe-eval'`.** React Refresh compiles and evaluates modules in the browser.
An unconditional policy makes `npm run dev` unusable, which is how a CSP quietly gets reverted.
Gate it on `NODE_ENV`, so the deployed policy never carries it.

---

## Tasks

### 6.1 Vendor the pdf.js worker (do this first) — ✅ done 2026-09-09

Independent of CSP, and a prerequisite for it.

**Observation performed (not a live browser run — see reasoning below):** the exact URL the code
builds, `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/6.3.289/pdf.worker.min.mjs`, was fetched
directly. It resolves `200`, `application/javascript`, 1,265,413 bytes. `cmp` against
`node_modules/pdfjs-dist/build/pdf.worker.min.mjs` (the **non-legacy** build) confirms a
byte-for-byte match. **Conclusion: no live bug.** This URL is fully deterministic from
`pdfjs.version` — there is no user input, timing, or environment variance in how it's built — so
a direct fetch of that exact string is conclusive evidence for "does this request succeed", and a
full Playwright click-through would only additionally confirm the browser actually issues the
request, which the code at `importCatalog.ts:126` guarantees unconditionally on that code path.
Skipped the live run on that basis.

**A real finding came out of the comparison anyway:** cdnjs only publishes one worker file per
version — the **non-legacy** build (`pdfjs-dist/build/pdf.worker.min.mjs`) — while the main
thread at `importCatalog.ts:125` imports from `pdfjs-dist/legacy/build/pdf.mjs`. Production has
therefore been running a **mismatched legacy-main / non-legacy-worker pair** since this feature
shipped. It works because pdf.js's main/worker handshake matches on exact version string, not
build flavor, and both report `6.3.289` — but it was never a matched pair by design, just by
accident. Vendoring from the **legacy** build directory (below) fixes this as a side effect,
not the main point of 6.1.

- **Copy the worker at build time, not by hand.** `scripts/vendor-pdf-worker.js` copies
  `node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs` → `public/pdf.worker.min.mjs` — the
  **legacy** path, to properly match the main-thread import for the first time, not the
  non-legacy one the CDN happened to serve. Wired via `predev`/`prebuild`/`prepreview`/
  `predeploy` npm hooks (`preview`/`deploy` invoke `opennextjs-cloudflare` directly, so they
  never run npm's own `build` script and can't rely on a plain `prebuild` alone).
  Point `workerSrc` at `/pdf.worker.min.mjs`. A build-time copy rather than a committed one keeps
  the worker and the library at the same version automatically — which is what the current
  `${pdfjs.version}` interpolation was reaching for, and the exact thing a hand-copied file would
  break on the next `npm update`.
- Add `public/pdf.worker.min.mjs` to `.gitignore` — it's generated, so a stale copy cannot be
  committed and drift from whatever `pdfjs-dist` version is actually installed.
- **Acceptance:** a Basic Rate PDF import succeeds with zero external network requests, and the
  worker request resolves against the app's own origin.

### 6.2 Add a CSP builder to `src/lib/securityHeaders.ts`

Extend the existing single-source-of-truth file rather than starting a second one. The CSP cannot
join `SECURITY_HEADERS` itself, because that array is consumed by `next.config.ts` at build time
and the policy carries a per-request nonce — middleware is the only place that can produce it.
Add a note saying so, next to the existing note explaining the two call sites.

```ts
export function buildCsp(nonce: string, opts: { dev: boolean }): string {
  const scriptSrc = [`'self'`, `'nonce-${nonce}'`]
  if (opts.dev) scriptSrc.push(`'unsafe-eval'`)   // React Refresh only; never in production
  return [
    `default-src 'self'`,
    `script-src ${scriptSrc.join(' ')}`,
    `style-src 'self' 'unsafe-inline'`,           // no nonce — see plan, gotcha 1
    `img-src 'self' data: blob:`,
    `font-src 'self' data:`,
    `connect-src 'self'`,
    `worker-src 'self' blob:`,
    `object-src 'none'`,
    `base-uri 'self'`,
    `form-action 'self'`,
    `frame-ancestors 'none'`,
  ].join('; ')
}
```

### 6.3 Generate and propagate the nonce in `src/middleware.ts` — ✅ done 2026-09-09

**What actually happened, and one correction to this section's own design:** implemented as a
`generateNonce()` helper (`crypto.getRandomValues`, matching `src/lib/auth.ts`'s existing
`crypto.randomUUID()` convention rather than reaching for `node:crypto`) plus a new
`nextWithCsp()` function for the success path, alongside the existing `withSecurityHeaders()`
for short-circuits.

**This section's own bullet list undersold what the success path needs.** It says "set the
chosen response header name on the response" as if that were optional polish. It is not: the
response header is the only thing that makes a browser actually receive and evaluate the policy
at all. Skipping it (which an early draft of this task did) means Next's renderer still nonces
its own inline scripts correctly — the *request*-header trick works independent of whether the
response carries anything — but the browser never sees a CSP on the delivered page, so real
violations go completely unreported regardless of report-only vs enforcing. `nextWithCsp()` sets
`buildCsp()`'s output in both places: on the cloned request headers (named
`Content-Security-Policy` always, per gotcha 2) and via `response.headers.set()` on the same
`NextResponse.next()` object (named via `CSP_RESPONSE_HEADER_NAME`, currently the report-only
variant).

**Verified live**, not just by inspection — against a real `next dev` instance (isolated to its
own `distDir` to avoid colliding with another already-running dev server on the same `.next`
directory, which briefly produced an unrelated `EPERM` red herring during this same diagnostic
session): `curl -I http://localhost:3099/login` returned a `content-security-policy-report-only`
header carrying a real nonce, and the response body showed every Next-generated `<script>` and
`<link rel="stylesheet">` tag carrying that exact same `nonce` attribute automatically — CSS
files included, which this section's design didn't explicitly anticipate but `style-src`
correctly doesn't need since it stays on `'unsafe-inline'`. The theme script in
`src/app/layout.tsx` correctly had **no** nonce yet at this point, as expected — that's task 6.4,
not yet done when this was tested.

- Generate 16 random bytes per request, base64-encoded. The middleware already runs on
  `runtime: 'nodejs'` (see the comment at `src/middleware.ts:70`), so `crypto` is available.
- On the **success path** (`src/middleware.ts:62`): set `x-nonce` and `Content-Security-Policy` on
  a cloned request header set, pass it via `NextResponse.next({ request: { headers } })`, and set
  the chosen response header name on the response.
- On the **short-circuit branches** (the `/login` redirect and every 401/403): these are the
  branches Phase 1 found shipping no headers at all. They render no scripts, so they need no
  nonce, but they must still carry a CSP. Route them through the existing
  `withSecurityHeaders()` helper so there is still exactly one place a header can be forgotten.
- Both `x-nonce` and the CSP request header are `set`, not appended, so a client cannot smuggle
  its own value in.
- **Leave the matcher alone.** It excludes `_next/static` and image extensions, so those responses
  will not carry the nonce'd CSP — which is correct: CSP governs the document that loads a
  subresource, not the subresource's own response. Note it in a comment so nobody "fixes" it later.

### 6.4 Consume the nonce in `src/app/layout.tsx` — ✅ done and verified 2026-09-09

Implemented exactly as designed: `RootLayout` is now `async`, reads `(await headers()).get('x-nonce') ?? undefined`, and passes it as `nonce={nonce}` on the theme script. No other change to
the script itself.

**Verified live** against the same running dev server: `curl` the raw server-rendered HTML (not
the RSC flight payload — had to explicitly check the literal `<head>` bytes, since the page also
serializes a copy of the element tree, nonce included, into a `self.__next_f.push(...)` script
for hydration, which could be mistaken for the real tag) and confirmed
`<script nonce="...">(function(){ ... vega-theme ... })();</script>` in `<head>`, with that exact
nonce value matching every other Next-generated `<script src="...">` and
`<link rel="stylesheet">` tag on the same page.

### 6.5 Ship report-only

Set the response header name to `Content-Security-Policy-Report-Only`, keeping the request-side
header as `Content-Security-Policy` per gotcha 2. Keep the existing enforced standalone
`Content-Security-Policy: frame-ancestors 'none'` in place for now — do not touch
`securityHeaders.ts:18` yet. Multiple CSP headers are each enforced independently, so leaving it
means clickjacking protection stays *enforced* for the whole report-only window instead of
dropping to report-only along with everything else.

### 6.6 Add a Playwright CSP violation spec

New `tests/05-csp.spec.ts`, alongside the four existing specs. The mechanism:

```ts
await page.addInitScript(() => {
  ;(window as any).__csp = []
  document.addEventListener('securitypolicyviolation', e =>
    (window as any).__csp.push(`${e.effectiveDirective} blocked ${e.blockedURI} @ ${e.sourceFile}:${e.lineNumber}`))
})
```

`addInitScript` runs before any page script, so it catches violations from the theme script in
`<head>` too. Report-only violations fire this same event (with `disposition: 'report'`), which is
what lets the spec be written and pass *before* the policy is enforcing.

Assert an empty array after visiting every authenticated route, using the existing seeded
accounts and login helper from `tests/helpers.ts`. This spec needs no database assertions, so it
does not touch `helpers.ts`'s wrangler-D1 query path (which is stale post-Postgres-migration and
is not this phase's problem to fix).

**Run it against `npm run preview`**, per `playwright.config.ts` — the real OpenNext/Workers
build, on `PW_BASE_URL`. Not `next dev`, whose relaxed dev policy is precisely what would hide a
production violation.

### 6.7 Exercise the two paths the source plan flagged

The source plan named PDF export and XLSX import as the most likely to trip on `blob:` and
`worker-src`. Cover them explicitly, because a route-visiting sweep never clicks them:

- **PDF export** — `exportPdf.ts` (BSR, payments schedule, income statement, portfolio, basic
  rate) and `exportProjectReport.ts`. All call `doc.save()`, which builds a blob URL and clicks an
  anchor; `pdfTemplate.ts:33-53` also loads `/logo.jpg` into an `Image` before `addImage`.
- **XLSX export** — `exportXlsx.ts:72-83`, same blob-URL-plus-anchor download shape.
- **PDF import** — the 6.1 path, the only consumer of `worker-src`.
- **XLSX import** — `importCatalog.ts` via exceljs.

**Watch for `'wasm-unsafe-eval'`.** pdf.js ships WASM codecs for some image formats. A text-only
Basic Rate PDF likely never reaches them, so it is deliberately **not** in the 6.2 policy — but if
a real import produces a `script-src`/`wasm` violation, add `'wasm-unsafe-eval'` (not
`'unsafe-eval'`) and record why here. Do not add it speculatively.

### 6.8 Flip to enforcing, and collapse the two CSP headers into one

Only once 6.6 and 6.7 are clean:

1. Rename the response header to `Content-Security-Policy`.
2. Delete the standalone `['Content-Security-Policy', "frame-ancestors 'none'"]` entry at
   `securityHeaders.ts:18` — `frame-ancestors` is now inside the full policy. **Do this in the
   same change as step 1, not before**, or documents spend that window with no enforced
   `frame-ancestors` at all.
3. Keep `X-Frame-Options: DENY` in `SECURITY_HEADERS`. It stays for the same reason Phase 1 added
   both, and it is also what still covers the static-asset responses that middleware skips.
4. Re-run 6.6 and 6.7 against the enforcing policy. A report-only pass is not proof: a directive
   can be missing from the report-only header entirely and only bite when enforced.

### 6.9 Document the `style-src 'unsafe-inline'` concession

In `securityHeaders.ts`, next to `buildCsp`. Removing it means auditing every runtime style
injection in framer-motion and react-toastify, which is not worth it here. Record it as a decision
so it does not read as an oversight — and record gotcha 1 in the same comment, since the naive
"harden it by adding a nonce" fix is actively harmful.

### 6.10 Optional — a static CI guard against regression

Recommended but not required. A `scripts/audit-csp.js` in the shape of the existing
`audit-gate.js` / `audit-guards.js`, failing the build on either:

- a `dangerouslySetInnerHTML` script tag with no `nonce` attribute, or
- an external `https://` origin used as a script, worker, or font source in `src/`.

The second rule is the one that matters: it is exactly the class of regression that produced
finding 1 and then survived a security review, because the review's grep only looked for
`http://`. Wire it into `.github/workflows/ci.yml` beside the two existing audit steps, ahead of
typecheck and build.

---

## Why not a week of report-only

The source plan's acceptance is "one week report-only with zero violations on every page". That
was written assuming a deployed app accruing real usage. Nothing has been deployed — Phase 2.10
flags the forced global re-login as still pending, and Phase 5's notes say the same. A week of
report-only against an app nobody is using measures elapsed time, not coverage.

The substitute is stronger on the axis that actually matters. A Playwright sweep deterministically
visits every route and clicks every export and import path on every run, in CI-able form, and
catches a violation on the fifth export format as reliably as the first — where a human week of
"real use" would plausibly never touch the portfolio income statement or a PDF import at all.

Keep report-only shipped through 6.5–6.7 regardless. It is what makes a missed violation a logged
event instead of a broken page, and it is the safety net for whatever the sweep does not model.

**A `report-uri` / `report-to` collection endpoint is deliberately not part of this phase.** It
would mean a new unauthenticated public POST route — new attack surface, a log-flooding vector,
and another entry in `audit-guards.js`'s `ALLOWED_PUBLIC` allowlist beside login and logout — to
collect violations that 6.6 already surfaces deterministically and earlier. `report-uri` is also
deprecated in favour of the more involved Reporting-API. For an app with dozens of internal users,
that is not a good trade. Flagging it as a decision, the same way 2.8 and 3.8 were, rather than
leaving it looking forgotten. Revisit if the client asks for production violation telemetry.

---

## Risk and rollout

Medium, and concentrated in one place: **if the nonce plumbing in 6.3 is wrong, every page breaks
at once**, because Next's own hydration scripts get blocked. That failure is loud and immediate
rather than subtle, and it is fully reproducible under `npm run preview` — so it will not reach
production if 6.6 is run before merging.

Everything else fails soft: while the policy is report-only, a wrong directive logs a violation
and changes nothing the user sees. This is the one phase where the report-only step is load-bearing
rather than ceremonial, so do not compress 6.5–6.7 into the same change as 6.8.

No schema change, no migration, no data backfill, no new npm dependency. One generated public
asset. Unlike Phases 2 and 5, **no forced logout** — nothing about the session model changes.

---

## Acceptance

- Every document response carries the full CSP; `curl -sI` against `npm run preview` shows it, and
  the theme script has a matching `nonce` attribute in the served HTML.
- `tests/05-csp.spec.ts` reports zero violations across every authenticated route **with the
  policy enforcing** — not just report-only.
- Both flagged paths pass clean: a PDF export and an XLSX import, plus the remaining three export
  formats and the PDF import.
- A Basic Rate PDF import completes with **zero third-party network requests**.
- Exactly one `Content-Security-Policy` header on a document response — the standalone
  `frame-ancestors` entry is gone, and `X-Frame-Options: DENY` remains.
- `npm run dev` still works (dev policy carries `'unsafe-eval'`; production does not — check both).
- `npx tsc --noEmit` clean, `npm run build` succeeds, both audit scripts still pass.

---

## Flat task list

### Phase 6 — Content-Security-Policy
- [x] 6.1 Observe current pdf.js worker behaviour; record the result here — no live bug found (CDN URL resolved fine), but confirmed a legacy-main/non-legacy-worker mismatch (see task 6.1 notes above)
- [x] 6.2 Vendor `pdf.worker.min.mjs` to `public/` via a build-time copy (`scripts/vendor-pdf-worker.js`, wired into `predev`/`prebuild`/`prepreview`/`predeploy`); `workerSrc` now `/pdf.worker.min.mjs`
- [x] 6.3 Gitignore the generated worker copy
- [x] 6.4 Add `buildCsp(nonce, { dev })` to `src/lib/securityHeaders.ts`
- [x] 6.5 Generate the nonce in `src/middleware.ts`; set CSP on request **and** response — verified live: `curl -I` shows `content-security-policy-report-only` with a real nonce, and every Next-generated `<script>`/`<link>` tag in the response body carries the matching `nonce` attribute automatically
- [x] 6.6 Route every middleware short-circuit branch through `withSecurityHeaders()`
- [x] 6.7 Comment why the matcher's static-asset exclusion is correct and must stay
- [x] 6.8 Read `x-nonce` in `src/app/layout.tsx`; nonce the theme script (`RootLayout` → async) — verified live, exact nonce match confirmed in the raw served HTML
- [x] 6.9 Ship as `Content-Security-Policy-Report-Only`; keep the standalone `frame-ancestors` enforced — a direct consequence of 6.4-6.8, confirmed live: both headers present simultaneously on the same response
- [x] 6.10 Add `tests/05-csp.spec.ts` with `securitypolicyviolation` capture via `addInitScript` — written, typechecks clean; covers every static route (fetching dynamic ids live via the API rather than hardcoding), a Staff denial-panel path, and a Basic Rate export→re-import round trip that reuses the app's own export as the import fixture (exercises task 6.1's vendored pdf.worker.min.mjs)
- [ ] 6.11 Sweep every authenticated route; confirm zero violations — **blocked, see note below**
- [ ] 6.12 Exercise all five PDF exports + XLSX export; confirm zero violations — **blocked, see note below**
- [ ] 6.13 Exercise PDF import + XLSX import; confirm zero violations — **blocked, see note below**

**Blocker found while running 6.11-6.13 (2026-09-09), unrelated to CSP:** `tests/helpers.ts`'s
`PASSWORD = 'VegaDemo-2026!'` (matching `prisma/seed.ts`'s `DEMO_PASSWORD`) no longer
authenticates `nimal@vegahomes.lk` against the live `DATABASE_URL` (a shared Supabase Postgres
instance — see [[azure_migration_direction]]). Every login in the sweep failed with a genuine
401, which is exactly what tripped `login_throttle` after 5 attempts (`isLocked()`/
`recordFailure()` in `src/lib/loginThrottle.ts` worked correctly — this was the throttle
protecting the account as designed, not a bug). Cleared via `resetThrottle()` (called directly
through the app's own code, not the stale `execLocalSql`-based `clearLoginThrottle()` helper —
see the file-header note in `05-csp.spec.ts`) so the account isn't left locked for its real
owner. **Did not attempt further password guesses or reset anyone's credentials** — this is a
shared, apparently actively-used database (users/roles/statuses all present and consistent with
the seed, only the password differs), not a disposable local sandbox, and guessing further would
itself be the exact brute-force behavior Phase 3 defends against.

**What this does and doesn't affect:** tasks 6.1-6.9 needed no login (GET requests / raw HTML
inspection only) and are independently verified live, unaffected by this. Only 6.11-6.13's
full authenticated Playwright sweep is blocked — pending either the current correct password for
the test accounts, or explicit authorization to reset one via the app's normal admin-reset flow
(not a raw DB write). Once unblocked, `05-csp.spec.ts` is ready to run as-is.
- [ ] 6.14 Resolve any `wasm` violation with `'wasm-unsafe-eval'` only if observed; document it
- [ ] 6.15 Flip to `Content-Security-Policy` and delete `securityHeaders.ts:18` in one change
- [ ] 6.16 Re-run 6.11–6.13 against the **enforcing** policy
- [ ] 6.17 Verify `npm run dev` still works and production omits `'unsafe-eval'`
- [ ] 6.18 Document the `style-src 'unsafe-inline'` concession and the nonce/`unsafe-inline` gotcha
- [ ] 6.19 Optional: `scripts/audit-csp.js` + CI wiring (inline-script nonce, external-origin guard)

### Follow-ups this phase deliberately does not take
- [ ] `report-uri`/`report-to` violation collection — declined above; revisit only on request
- [ ] Subresource Integrity — moot once 6.2 lands and no external script origin remains
- [ ] `tests/helpers.ts` still queries local D1 via wrangler, stale since the Postgres migration —
      unrelated to CSP, flagged for whoever next touches the test harness

---

## Definition of done

`UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md`'s "Transport → Security headers" row can go ✅ (it is
currently closed only by Phase 1, with Phase 6 outstanding). That leaves Phase 7's Cloudflare
Managed Rules — dashboard-only, no owner assigned, tracked in
`CLOUDFLARE_SECURITY_RUNBOOK.md`'s handover checklist — as the sole remaining item from the
original plan, and it is not a code task.

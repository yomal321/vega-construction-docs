# Cloudflare Security Runbook

**Date:** 2026-09-01
**Scope:** Vega Manager (Cloudflare Workers + D1, deployed via OpenNext)
**Source:** `UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md` Phase 7 — Edge WAF and rate limiting

**Why this document exists:** most Cloudflare WAF and rate-limiting configuration lives in
dashboard/API state, not in this repo. This runbook is the actual deliverable for the pieces
that can't be committed as code — plus a record of the one piece that *could* be moved into
code, and was.

**Status legend:** ✅ done and verified · 📝 documented, action required by someone with
Cloudflare dashboard access (not executed as part of this pass — no dashboard/account
credentials were available) · —

---

## 1. Login rate limiting — ✅ done, implemented as code (not a dashboard rule)

### What changed and why

The plan (7.2) originally called for a **dashboard** rate-limit rule (~20 req/min/IP on
`POST /api/auth/login`), with 7.3 flagging Cloudflare's Workers-native rate-limiting
*binding* as a possible in-repo alternative — conditional on verifying it was actually stable
first, since "this API has changed shape more than once and was until recently under an
`unsafe` namespace."

That verification was done before writing any code:
- Cloudflare's own changelog confirms the `ratelimit` binding went **GA on 2025-09-19**
  ("stable and recommended for all production workloads") — see Sources.
- It requires Wrangler ≥ 4.36.0. This repo has 4.127.1 installed (`npx wrangler --version`).
- The `RateLimit` / `RateLimitOptions` TypeScript types are already present in the installed
  `@cloudflare/workers-types@5.20260721.1` — no new dependency needed.

Since it checked out stable, per the plan's own instruction ("if it is stable, prefer it over
the dashboard rule for reviewability") **this binding is the implementation**, and no
dashboard rate-limit rule was created. If Cloudflare ever deprecates or reshapes this binding,
fall back to the dashboard rule described in the plan's 7.2 instead.

### Where it lives (code, not dashboard — this section is the living source of truth)

| Piece | File |
|---|---|
| Binding declaration (20 requests / 60s, keyed by caller) | `vega-manager/wrangler.toml` — `[[ratelimits]]` block, `name = "LOGIN_RATE_LIMITER"` |
| `CloudflareEnv` type | `vega-manager/src/lib/db.ts` |
| Check + fail-open wrapper | `vega-manager/src/lib/edgeRateLimit.ts` — `isLoginRateLimited(ip)` |
| Enforcement point | `vega-manager/src/app/api/auth/login/route.ts` — checked first, before the existing DB-backed throttle |

`namespace_id` in the binding (`"1"`) is an arbitrary account-unique integer the developer
picks — Cloudflare's docs describe no pre-provisioning step, and `wrangler deploy` picks up
the binding directly from `wrangler.toml` with no separate dashboard action required for this
piece specifically.

### How this differs from the existing Phase 3 login throttle

Two independent layers now sit in front of the password check, checked in this order:

1. **`LOGIN_RATE_LIMITER` (this phase, new).** Volumetric — every `POST` to `/api/auth/login`
   counts, success or failure, keyed only by `cf-connecting-ip`. Catches high-*rate* traffic
   (e.g. a scripted credential-stuffing run against many different, possibly all-valid,
   accounts) that the failure-only throttle below wouldn't flag until 5 wrong passwords land
   against one bucket.
2. **DB-backed throttle (`src/lib/loginThrottle.ts`, Phase 3, unchanged).** Failure-count
   based — 5 failures in 15 minutes locks the specific email *and* the specific IP for 15
   minutes. Untouched by this change; still the real backstop.

The new check **fails open**: if the binding call itself throws, `isLoginRateLimited` logs the
error and returns `false` (not rate-limited) rather than 500ing the login endpoint. A Workers
platform hiccup on this defense-in-depth layer shouldn't take down login when the DB throttle
is still fully intact underneath it.

### Verification performed (live, against `wrangler dev` — not just static review)

Ran the actual built Worker locally (`opennextjs-cloudflare build`, then `wrangler dev`, which
is exactly what `npm run preview` does under the hood) and confirmed:

- Wrangler's own binding summary on startup showed `env.LOGIN_RATE_LIMITER (20 requests/60s)
  Rate Limit local` — the binding is wired up as declared.
- Sent 25 back-to-back **successful** logins (same account, correct password) from one IP.
  Requests 1–20 returned `200`; requests 21–25 all returned `429` with
  `{"error":"Too many attempts. Try again in a few minutes."}` — the exact 20/60s boundary.
- Because every one of those 25 requests was a *successful* login, each one calls
  `resetThrottle()` on the DB-backed throttle (Phase 3) before returning — so that table can
  never accumulate failures from this test. Queried `login_throttle` directly against the
  local D1 database afterward and confirmed it was empty (`select * from login_throttle` →
  `[]`). This isolates the result: the 429s at request 21+ came from the new
  `LOGIN_RATE_LIMITER` binding alone, not the pre-existing throttle.
- Waited out the 60-second window and sent one more request: `200`, confirming this is a
  rolling window, not a permanent lock.

### Caveat for whoever deploys this

This is a fast-moving Cloudflare API surface (per the plan's own warning). Before shipping to
production, re-check `https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/`
for any syntax change since 2026-09-01, and confirm after the first real `wrangler deploy` that
the binding shows up correctly in `wrangler deployments status` / the dashboard's Bindings tab
for the live Worker (this runbook's testing was against local simulation only — Cloudflare's
own docs describe local dev as "simulated locally," and simulated behavior for this specific
binding type had not been independently re-confirmed against a real deployed zone at the time
of writing).

---

## 2. Cloudflare Managed Rules (OWASP Core Ruleset) — 📝 documented, not yet executed

**This is a zone-level WAF setting with no code representation at all.** It cannot be
committed to this repo, verified by a build, or enabled without live Cloudflare dashboard (or
API token) access — neither of which was available in this session. The steps below are
accurate as of the dashboard layout at time of writing; Cloudflare does reorganize this UI
occasionally, so re-confirm the menu path if it doesn't match.

### Steps to enable

1. Log into the Cloudflare dashboard and select the zone (domain) this Worker is routed
   through.
2. Go to **Security → WAF → Managed rules**.
3. Enable the **Cloudflare Managed Ruleset**. (Older dashboard versions may list this as a
   separate "OWASP Core Ruleset" toggle — enable whichever variant your account shows; recent
   Cloudflare accounts have folded OWASP coverage into the single Managed Ruleset.)
4. For each rule package's default action, "Managed Challenge" is a reasonable first rollout
   choice (fewer false-positive hard-blocks than "Block" while still stopping automated
   attacks) — tune per-rule after watching real traffic for a week, the same soak period
   already planned for Phase 6's CSP rollout.
5. Save and deploy the ruleset.
6. **`[ INSERT SCREENSHOT: enabled ruleset + chosen action, from the WAF → Managed rules
   screen ]`** — add this once step 3–5 is actually performed; this runbook has no screenshot
   yet because no dashboard session was available to take one.

### Verification, once enabled

Send a known WAF-triggering pattern against a live (deployed, not local) endpoint — e.g. a
query string containing a classic SQLi probe like `?id=1' OR '1'='1` — and confirm it's
blocked or challenged **at the edge**, before it ever reaches the Worker (check Worker logs to
confirm the request never arrived). Do this from outside any allowlisted IP range.

### Owner

Needs to be assigned to whoever holds Cloudflare account access for this zone. Not completed
as part of this pass.

---

## 3. What was explicitly NOT built, and why

- **Dashboard rate-limit rule (original 7.2).** Superseded by the Workers-native binding
  (§1) per the plan's own preference clause — the binding is reviewable in version control,
  the dashboard rule wouldn't be. If the binding is ever removed or found unreliable in
  production, revert to a dashboard rule matching the same 20 req/60s/IP shape on
  `POST /api/auth/login`.

---

## Sources

- [Rate Limiting · Cloudflare Workers docs](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/) — binding syntax, `.limit()` API, period constraint (10 or 60s only), Wrangler ≥4.36.0 requirement. Consulted 2026-09-01.
- [Rate Limiting in Workers is now GA · Cloudflare Changelog](https://developers.cloudflare.com/changelog/post/2025-09-19-ratelimit-workers-ga/) — GA date and status. Consulted 2026-09-01.

---

## Handover checklist

- [x] Login rate limiting implemented in code, tested locally against a real built Worker
- [ ] Cloudflare Managed Rules (OWASP) — **requires dashboard access; assign an owner**
- [ ] Screenshot of the enabled Managed Ruleset — add once the above is done
- [ ] Re-verify rate-limit binding syntax against current Cloudflare docs before first
      production deploy of this change
- [ ] Confirm the `LOGIN_RATE_LIMITER` binding appears correctly for the live (not local)
      Worker after the first real `wrangler deploy`

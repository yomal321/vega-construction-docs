# k3s Migration — Known Issues & What Was Fixed (2026-09-18)

**Context:** the app is already deployed to the Hetzner-node k3s cluster (`deploy/helm/`,
ArgoCD GitOps, `CI-CD_Pipelines/Vega-OnPrem-k3s.yml`), with Azure providing only ACR, the
DevOps pipeline, and Entra ID sign-in. This doc records two deploy-breaking defects found
during review that are **explicitly deferred — do not fix as a side effect of anything
else** — plus the two security items that *were* fixed today, kept in the same place so the
trail isn't split across documents.

Nothing in `deploy/helm/`, `CI-CD_Pipelines/`, `Dockerfile`, `wrangler.toml`, or any values
file was touched by today's fixes. Everything below the fixed line is an application-code
change only, flowing through the existing, unmodified migrate job and pipeline.

---

## Deferred — not fixed, needs a deliberate follow-up

### 1. The migrate-job image is never built or pushed

`deploy/helm/charts/vega-web/templates/migrate-job.yaml` pulls
`{{ .Values.image.repository }}:{{ .Values.image.tag }}-migrate` (the Dockerfile's `builder`
stage, which has the Prisma CLI the runtime image doesn't). `CI-CD_Pipelines/Vega-OnPrem-k3s.yml`
only builds and pushes `<env>-<sha>` — no stage ever produces or pushes a `-migrate` tag.

**Effect:** the migrate Job `ImagePullBackOff`s on every ArgoCD sync (it's a
`post-install,post-upgrade` hook, so this fires on every deploy, not just the first one).
Whether this is currently masked depends on `backoffLimit: 2` and whatever the sync has been
doing with a job that never completes — worth checking directly (`kubectl get jobs`,
read-only access per the `bistec-app-developer` skill) before assuming it's silently fine.

**Fix, when picked up:** add a build+push step for the `builder` stage tagged
`<env>-<sha>-migrate` in the pipeline's `Build` stage, alongside the existing runtime image
build.

### 2. `main` triggers two deployments to two different places

`.github/workflows/deploy.yml` (push to `main` → Cloudflare Workers) and
`CI-CD_Pipelines/Vega-OnPrem-k3s.yml` (`main` → k3s `dev`) both fire from the same branch,
on the same commit. Every merge to `main` right now updates both the old Cloudflare
deployment and the new k3s one simultaneously.

**Fix, when picked up:** a deliberate decision — either retire `deploy.yml` once k3s is
confirmed as the real target, or gate it so it only runs on demand (`workflow_dispatch`
only, no `push` trigger). Not done here because it's a call about what's still considered
"live," not something to infer silently.

### 3. The client-IP trust boundary needs infra-side confirmation (partially fixed)

See item 2 under "Fixed" below — the application side now reads a client IP on k3s at all,
which it didn't before. But trusting the leftmost `x-forwarded-for` hop is only correct if
the ingress (Traefik, per `values-dev.yaml`) is the sole entry point and is what sets/appends
that header, rather than passing through a client-supplied value untouched. **This needs one
of:**
- confirmation that Traefik's default behavior on this cluster already does this safely
  (common default, but not verified here — no cluster access from this review), or
- an explicit `forwardedHeaders.trustedIPs` / equivalent Traefik config restricting which
  hops are trusted, or
- `externalTrafficPolicy: Local` on the ingress Service, which stops a spoofed source from
  reaching Traefik with an attacker-controlled address in the first place.

Not fixed here because it's an ingress/cluster config change, i.e. exactly the "existing
deployment" this pass was told not to touch. Until confirmed, treat the IP-based throttle
and rate limiter on k3s as "as strong as Cloudflare's `cf-connecting-ip` was, provided the
ingress is well-behaved" rather than an independently-verified guarantee.

---

## Fixed today — application code only

### 1. Restored the DB-backed session check at the front gate (`src/proxy.ts`)

**The regression:** after the D1→Postgres migration, `pg` could not be statically imported
from `src/proxy.ts` without breaking the Cloudflare Workers build (see
`src/lib/sessionToken.ts`'s header comment). The fix at the time was to make proxy check only
the JWT's signature and expiry — it could no longer see that a session was revoked,
idle-expired, or that the user had been deactivated. That check only ran again once a page's
own API calls hit a route handler. Functionally contained (no data actually leaked — see
`doc/test/security/UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md`), but weaker than Phase 2's
original guarantee, and undocumented as a live gap.

**The fix:** `src/proxy.ts` now branches on runtime. On Cloudflare Workers, behavior is
**unchanged** — still signature/expiry only, so the still-live Cloudflare deployment
(`.github/workflows/deploy.yml`) is not affected. On any real Node runtime (k3s — the
deployed target — and eventually App Service), it does a full `resolveSession()` call via a
runtime `import()` (not a static one, so Workers' build never sees it), restoring the
original guarantee: a revoked, idle-expired, or deactivated session is rejected at the front
gate again, not just at the next API call.

**Not restored:** the old `ADMIN_ONLY_PREFIXES` page-shell redirect (a demoted admin loading
`/users` gets a blank page from 403'ing API calls, rather than a clean redirect). That's a UX
gap, not a security one — no admin-only data is served either way, since every route handler
still independently enforces `requireAdmin()`/`requirePermission()`. Left out deliberately:
there's no longer a live list of admin-only prefixes to copy correctly, and guessing one
risks *breaking* currently-working Staff access to something misclassified as admin-only,
which is worse than the UX rough edge it would fix.

### 2. Replaced Cloudflare's login rate limiter for k3s (`src/lib/edgeRateLimit.ts`)

**The regression:** `wrangler.toml`'s `LOGIN_RATE_LIMITER` binding (20 requests/60s per IP,
in front of the DB-backed failure throttle) has no equivalent outside Workers.
`isLoginRateLimited()` was calling `getCloudflareContext()`, which throws off-Workers; the
existing fail-open handling caught that silently, so on k3s this check was **always** a
no-op — logging an error on every login attempt but never actually limiting anything.

**A second, more basic bug this surfaced:** `src/app/api/auth/login/route.ts` read the
client IP from `cf-connecting-ip` only. On k3s that header doesn't exist, so `clientIp` was
always `undefined` — which meant **not just the edge limiter but the DB-backed per-IP
failure throttle in `loginThrottle.ts` was also silently skipped**, leaving only the
per-email throttle active. This was a bigger gap than "the edge limiter is gone" — it was
"IP-based protection of any kind is gone."

**The fix:**
- `src/lib/edgeRateLimit.ts` now branches the same way `pg.ts` already does for pooling: on
  Workers, unchanged Cloudflare-binding behavior; off Workers, a new Postgres-backed
  fixed-window counter (`login_rate_limit` table, migration
  `prisma/migrations/20260918000000_login_rate_limit/`) enforcing the same 20-requests/60s
  policy, counting every attempt regardless of outcome — matching what the Cloudflare binding
  did, not replacing it with the failure-only throttle that already existed.
- `login/route.ts`'s client IP now falls back to the leftmost `x-forwarded-for` hop when
  `cf-connecting-ip` is absent. See "Deferred #3" above — this is the piece that still needs
  infra-side confirmation before it's fully trustworthy, but it at least stops IP-based
  protection from being silently dark by default.

**Verification still needed before this is considered done:** none of the above has been
exercised against a real k3s pod yet (this pass had no cluster access). Before relying on it:
confirm the new migration applies cleanly via the existing migrate job, and confirm a burst
of 21+ rapid login attempts from one source actually gets a `429` on a deployed k3s pod, the
same way Phase 3's original acceptance criteria verified it against `wrangler dev --local`.

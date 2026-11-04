# k3s Security Runbook (2026-09-18)

**Naming note:** this file is named `AZURE_SECURITY_RUNBOOK.md` for continuity with
`UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md`'s Phase 7 (Azure) and
`POST_K3S_HARDENING_PLAN_2026-09-18.md`'s Phase 3, both written when "off Cloudflare" meant
"onto Azure" before the concrete hosting decision (k3s on Hetzner nodes, Azure limited to ACR
+ pipeline + Entra ID) was made. Do not rename it without updating those cross-references.
`CLOUDFLARE_SECURITY_RUNBOOK.md` stays untouched as the historical record of the prior period.

**What's different from the Cloudflare runbook this replaces:** most of what mattered there
was dashboard/API state with no git representation at all — that was the entire reason a
runbook needed to exist. On k3s, the equivalent configuration (`deploy/helm/`,
`CI-CD_Pipelines/Vega-OnPrem-k3s.yml`) is committed and version-controlled already. This
runbook exists for the smaller set of things that are still live-cluster-only: what's actually
running right now (as opposed to what the chart says should be), and the one open question
that depends on infrastructure this app's own repo doesn't own — Traefik's own configuration.

---

## Task 3.2 — Confirmed: the pod cannot be reached bypassing Traefik

**Verified directly against the live `vega-dev` namespace** (read-only kubectl,
`entra:yomal@bistecglobal.com`, 2026-09-18), not assumed from the chart:

```
$ kubectl get svc -n vega-dev
NAME              TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)
vega-postgresql   ClusterIP   10.43.199.137   <none>        5432/TCP
vega-web          ClusterIP   10.43.64.52     <none>        3000/TCP

$ kubectl get ingress -n vega-dev
NAME   CLASS     HOSTS                       ADDRESS
vega   traefik   vega.dev.bistecglobal.com   167.233.245.10,46.224.216.89

$ kubectl get deploy vega-web -o jsonpath='{.spec.template.spec.hostNetwork}'
(empty)   # not hostNetwork
$ kubectl get deploy vega-web -o jsonpath='{.spec.template.spec.containers[0].ports}'
[{"containerPort":3000,"protocol":"TCP"}]   # no hostPort
```

- `vega-web`'s Service is **ClusterIP only** — no `EXTERNAL-IP`, no NodePort. There is no
  publicly routable address for the origin at all, unlike Azure App Service (which has its own
  public hostname reachable directly unless access-restricted) — the concern the original
  Phase 7 (Azure) plan was written to close doesn't have a k3s equivalent to close, because the
  origin was never separately exposed in the first place.
- The pod uses neither `hostNetwork` nor a `hostPort` — its port is not bound on the node's own
  network interface.
- `vega` is the only Ingress and `vega-web`/`vega-postgresql` the only Services in the
  namespace — no other resource exposes this app.

**Together: from outside the cluster's private network, the Ingress's two LoadBalancer IPs are
the only path in.** Traefik cannot be bypassed at the Kubernetes-resource level.

**What this does NOT cover, stated plainly rather than left implicit:** node-level firewall
rules, the cloud provider's (Hetzner) own network configuration, and anything in `kube-system`
are outside what read-only kubectl in one namespace can see, and are platform/DevOps-owned per
`.claude/skills/bistec-app-developer/SKILL.md`. This runbook confirms the Kubernetes-level
routing has no bypass; it does not certify the underlying network fabric, which is a different
question DevOps would need to answer if this is ever pentested end to end.

---

## Task 3.1 — OPEN: Traefik's trusted-hop behaviour is not confirmed

**Could not verify from this session's access, for two independent reasons:**

1. Traefik's own controller (its static configuration — `forwardedHeaders.trustedIPs` or
   equivalent) runs outside this namespace, in a platform-owned space this app's developer
   credential cannot reach. A Traefik `Middleware` CRD lookup in `vega-dev` itself was denied
   (`middlewares.traefik.io is forbidden`) — this may mean none exists, or that CRD access
   requires a grant this namespace doesn't have; either way, nothing readable confirmed or
   ruled out the trust configuration.
2. **A live spoofing test against the currently-deployed pod would not have been conclusive
   even with full access.** The `vega-web` pod live in `vega-dev` right now is running commit
   `80f251b` ("Merged PR 866: Add requested account to the demo seed") — confirmed via
   `kubectl get deploy vega-web -o jsonpath='{.spec.template.spec.containers[0].image}'`
   returning tag `dev-80f251bda8549019291fea0b133fc2097a177fd3`. That commit predates even
   `9c7ee43` ("Fix login 500: wire up the missing SESSION_SECRET"), which is itself the base of
   the branch `clientIpFrom()` was built on. The deployed code still reads `cf-connecting-ip`
   (never set on k3s) then leftmost `X-Forwarded-For` — it never reads `x-real-ip` at all.
   Testing against it would answer a question about code that's about to be replaced, not
   about the code this runbook exists to cover.

**What this app's code currently assumes** (`src/app/api/auth/login/route.ts`,
`clientIpFrom()`): Traefik sets `X-Real-Ip` from the actual connecting socket (not by copying a
client-supplied header), and if that's ever wrong the fallback — rightmost `X-Forwarded-For`
hop — is only safe if Traefik is the sole hop and *appends* to that header rather than passing
a client-supplied value through untouched.

**Escalation needed — the specific question for DevOps:**

> For the Traefik ingress controller in front of `vega-dev`/`vega-uat`: does it set
> `X-Real-Ip` from the connecting peer address (not copied from any client-supplied header),
> and does it append to (rather than pass through) `X-Forwarded-For`? Is
> `forwardedHeaders.trustedIPs` (or equivalent) configured, and is Traefik the only hop between
> the internet and this cluster (no separate load balancer in front of it that would make the
> rightmost XFF entry the LB's address instead of the client's)?

**Once answered**, update this section with the finding — CONFIRMED SAFE, CONFIRMED NEEDS
CONFIG CHANGE (and what changed), or CONFIRMED UNSAFE (and the mitigation) — and update
`src/app/api/auth/login/route.ts`'s `clientIpFrom()` comment to match, since it currently
states this as an assumption pending verification.

**Until answered:** treat IP-based login throttling and rate limiting on k3s as "as strong as
Traefik's actual behaviour turns out to be," not as an independently verified guarantee — same
posture `K3S_MIGRATION_KNOWN_ISSUES_2026-09-18.md` already recorded for this.

---

## What's committed vs. cluster-only state

| Item | Where |
|---|---|
| Ingress rules, TLS secret name, cert issuer | `deploy/helm/templates/ingress.yaml` (git) |
| Image tag currently running | **cluster-only** — `kubectl get deploy vega-web -o jsonpath='{...image}'`, or `deploy/helm/values-<env>.yaml` on the `gitops` branch if ArgoCD has synced |
| `SESSION_SECRET`, `DATABASE_URL` values | **cluster-only** (sealed, not committed in plaintext) — `deploy/helm/sealed-secrets/`, applied by DevOps; see that directory's README for rotation |
| Traefik's own forwarded-headers/trusted-hop config | **cluster-only, outside this app's namespace** — the open question above |
| Resource requests/limits, replica count | `deploy/helm/charts/vega-web/values.yaml` (git); confirmed live at 1 replica, `100m/256Mi` request, `500m/512Mi` limit as of 2026-09-18 |
| ArgoCD Application (sync policy, source repo/path) | **cluster-only**, `argocd` namespace — not visible to this app's kubectl access at all; use https://argocd.bistecglobal.com |

---

## Acceptance (from `POST_K3S_HARDENING_PLAN_2026-09-18.md` Phase 3)

- [x] 3.2 confirmed — no bypass of Traefik exists at the Kubernetes routing level
- [ ] 3.1 open — escalated to DevOps above, not yet answered
- [x] 3.3 this document

# Defending Against Unauthorized Access — Checklist & Current-State Comparison

**Date:** 2026-08-30
**Scope:** Vega Manager (Next.js 15 + Prisma + Cloudflare D1)

> **⚠️ Superseded snapshot — read Part 2 as "state on 2026-08-30", not as current.** The
> Part 2 status tables are deliberately left as they were assessed on that date; several
> ❌/⚠️ rows have since been closed by `UNAUTHORIZED_ACCESS_REMEDIATION_PLAN.md` (login rate
> limiting, session revocation, password policy, security headers, input validation are all
> live now). For current status, read the remediation plan, not this table.
>
> **One row will never be closed: MFA.** The client declined multi-factor authentication on
> 2026-09-04, and `0026_remove_mfa.sql` removed the partial implementation. Treat the MFA
> line below as *descoped by the client*, not as an outstanding gap. The Part 1 checklist
> above remains a generic list of things worth considering — it is not a list of
> commitments for this project.

## Part 1 — General Checklist

### Authentication
- Strong password policy — minimum length/complexity, reject common/breached passwords.
- Hash passwords properly — bcrypt/argon2/scrypt, never plain text or fast hashes like MD5/SHA1.
- Multi-factor authentication (MFA) — especially for admin accounts.
- Rate limit / lock out login attempts — stop brute-force and credential-stuffing attacks (e.g., N failed attempts → temporary lockout or CAPTCHA).
- Generic error messages — "invalid email or password," never reveal which field was wrong or whether the account exists.
- Secure session tokens — signed, expiring, stored in httpOnly + secure + sameSite cookies, not localStorage (avoids XSS token theft).
- Session expiry & revocation — short-lived tokens, ability to force-logout a user (e.g., on password change, deactivation, or "log out all devices").

### Authorization
- Enforce access control on the server, never trust the client — hiding a button in the UI is not security; every API endpoint must independently check permissions.
- Principle of least privilege — users/roles get only the access they need, nothing by default.
- Object-level authorization (anti-IDOR) — check that the logged-in user actually owns/has access to the specific record being requested, not just that they're logged in (e.g., /orders/123 must verify order 123 belongs to that user).
- Deny by default — new routes/features start with no access; access is explicitly granted, not explicitly blocked.
- Re-check permissions server-side on every request — don't cache a stale "is admin" decision client-side and trust it later.

### Transport & infrastructure
- HTTPS everywhere, HSTS enabled, no mixed content.
- Security headers — Content-Security-Policy, X-Content-Type-Options, X-Frame-Options/frame-ancestors, Referrer-Policy.
- Firewall/WAF rules — block known bad IPs, malicious patterns, and apply rate limiting at the edge (Cloudflare, AWS WAF, etc.).
- Keep dependencies and runtime patched — most breaches exploit known, unpatched vulnerabilities.

### Data & input handling
- Parameterized queries / ORM — never build SQL with string concatenation (prevents SQL injection).
- Validate and sanitize all input, both client and server side (server side is the one that actually matters for security).
- Escape output to prevent XSS; use frameworks that auto-escape by default.
- Secrets management — API keys, DB credentials, JWT secrets stored in environment/secret managers, never committed to source control.

### Monitoring & response
- Audit logging — record logins (success/failure), permission changes, and sensitive actions (deletes, role edits) with who/when.
- Alerting — flag unusual patterns (many failed logins, access from new locations, privilege escalation attempts).
- Regular access reviews — periodically check who has admin/elevated access and revoke what's no longer needed.
- Penetration testing / security review before major releases or handover.

### Process
- CSRF protection on any state-changing request reachable from a browser session (tokens or strict sameSite cookies).
- Principle of "assume breach" — design so that if one layer fails (e.g., a leaked token), another layer (short expiry, server-side checks) still limits damage.

---

## Part 2 — Have vs. Missing in This Codebase

Legend: ✅ Have &nbsp;·&nbsp; ⚠️ Partial &nbsp;·&nbsp; ❌ Missing

### Authentication

| Item | Status | Notes |
|---|---|---|
| Strong password policy | ⚠️ Partial | Only a 6-character minimum enforced on user creation (`src/app/api/users/route.ts`). No complexity rule, no common/breached-password check. |
| Password hashing | ✅ Have | bcrypt (`bcryptjs`, cost 10) — `src/lib/auth.ts` (`hashPassword`/`verifyPassword`). |
| MFA | ❌ Missing | Not implemented anywhere in the app. |
| Login rate limiting / lockout | ❌ Missing | `src/app/api/auth/login/route.ts` has no attempt throttling — open to brute-force/credential stuffing. |
| Generic error messages | ✅ Have | Login returns "Invalid email or password" for both a bad email and a bad password, and for inactive accounts — no field-specific or existence-revealing errors. |
| Secure session tokens | ✅ Have | Signed JWT (`jose`), `httpOnly` + `sameSite: lax` + `secure` (protocol-aware) cookie — `src/lib/auth.ts`. Never stored in `localStorage`. |
| Session expiry & revocation | ⚠️ Partial | Expiry exists (1 day, or 7 days with "remember me"). Revocation does not — a `Session` Prisma model exists in the schema but isn't used to validate requests; sessions are stateless JWTs, so deactivating, deleting, or demoting a user does not invalidate a token they already hold until it naturally expires. |

### Authorization

| Item | Status | Notes |
|---|---|---|
| Server-side enforcement | ✅ Have | All 61 API route files call `requireSession`/`requireAdmin`/`requirePermission` except login/logout (correctly public). |
| Least privilege / RBAC | ✅ Have | Explicit `module:action` permission catalog (`src/lib/rbac.ts`), roles + direct per-user grants, Admin bypass is explicit rather than implicit. |
| Object-level authorization (anti-IDOR) | ✅ Have | `requireProjectAccess()` enforces owner-or-assigned-member-or-admin on every nested project resource (BSR, expenses, stages, items, basic price/rate) before it can be read or written. |
| Deny by default | ✅ Have | `src/middleware.ts` blocks any non-public path without a valid session; `/users`, `/roles`, `/settings` are further restricted to Admin at the middleware layer, not just the component layer. |
| Server re-checks permissions per request | ✅ Have | Same as above — permission/session checks run per-request in route handlers, not cached client-side. |

### Transport & infrastructure

| Item | Status | Notes |
|---|---|---|
| HTTPS / HSTS | ✅ Have | Deployed on Cloudflare Workers; cookie `secure` flag is protocol-aware (`sessionCookieOptions` in `src/lib/auth.ts`). |
| Security headers (CSP, X-Frame-Options, etc.) | ❌ Missing | None configured in `next.config.ts` or `wrangler.toml`. |
| WAF / edge rate limiting | ❌ Missing | Nothing configured in `wrangler.toml` beyond the D1 binding; no Cloudflare rate-limiting rule referenced in the repo. |
| Dependencies patched | ⚠️ Unverified | Not audited as part of this review — recommend running `npm audit` / checking for outdated packages before handover. |
| Secrets management | ✅ Have | `SESSION_SECRET` set via `wrangler secret put` for production, `.dev.vars` for local — both gitignored, nothing committed. |

### Data & input handling

| Item | Status | Notes |
|---|---|---|
| Parameterized queries | ✅ Have | Every query found uses `db.prepare(...).bind(...)`; no string-concatenated SQL found. |
| Input validation | ⚠️ Partial | Validation exists but is ad hoc per-route (e.g., password length check on user creation) rather than centralized/consistent. |
| Output escaping (XSS) | ✅ Have | React auto-escapes by default. The one `dangerouslySetInnerHTML` use (`src/app/layout.tsx`) is a static, developer-authored theme-init script, not user input — not a real risk. |
| Secrets management | ✅ Have | See Transport & infrastructure above — same finding. |

### Monitoring & response

| Item | Status | Notes |
|---|---|---|
| Audit logging | ❌ Missing | No logging of failed logins, permission changes, or admin actions anywhere in the codebase. |
| Alerting on anomalies | ❌ Missing | Nothing implemented. |
| Regular access reviews | ⚠️ Partial | Roles/permissions UI exists for admins to review who has what access, but no scheduled/automated review process — this is a process gap, not a code gap. |
| Penetration testing / security review | ⚠️ Unverified | Not confirmed as part of this review; recommend before major release or handover. |

### Process

| Item | Status | Notes |
|---|---|---|
| CSRF protection | ⚠️ Partial | Implicitly mitigated by `sameSite: lax` on the session cookie, not a deliberate CSRF defense (no CSRF token). If `sameSite` is ever loosened, this protection silently disappears. |
| "Assume breach" layering | ⚠️ Partial | Session + RBAC layering exists, but the lack of session revocation (see Authentication) means a leaked/stale token remains valid for its full lifetime regardless of what happens to the account afterward. |

---

## Summary

**Strongest area:** Authorization — RBAC and anti-IDOR (`requireProjectAccess`) are well built and consistently applied across all routes.

**Weakest area:** Authentication hardening and observability — no brute-force protection, no session revocation, no audit trail, no security headers.

**Recommended priority order:**
1. Login rate limiting / lockout — closes the most realistic attack (credential stuffing).
2. Session revocation on deactivate/role-change — closes the "removed user still has access for days" scenario.
3. Security headers (CSP, X-Frame-Options, etc.) — cheap, no functional risk.
4. Minimal auth audit log (failed logins, permission changes, admin actions).

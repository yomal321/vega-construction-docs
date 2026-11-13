"""Targeted checks for the 2026-11-09 follow-up fixes (origin/dev bd9564d, f5a0b23).

S6 scheme-aware CSRF check, S7 no X-Powered-By, N2 favicon, N3 activity 404, N4 NUL at login,
N5 cheque date range, plus the new Cheque value on the Payments Method filter.
Run AFTER cheque_verify.py (reuses its cheque fixtures). Local throwaway instance only.
Usage: python -I fixes_verify.py <dir holding authz_test.py>
"""
import json, sys, os
S = sys.argv[1]
src = open(os.path.join(S, "authz_test.py"), encoding="utf-8").read().split("# ── Fixtures")[0]
sys.argv = [sys.argv[0], S]
exec(src)

ADMIN, _ = login("sanduni@vegahomes.lk")
STAFF, _ = login("perf.staff1@vegahomes.lk")
assert ADMIN and STAFF, "login failed"
HTTPS_ORIGIN = f"https://{HOST}:{PORT}"
out = []

def chk(fid, name, m, p, who, body=None, want=(200,), origin=ORIGIN, headers=None, extra=None, raw=None):
    s, t, h, setc, dt = req(m, p, who, body, origin=origin, headers=headers, raw=raw)
    ok = s in want and (extra is None or extra(s, t, h, setc))
    out.append((fid, name, m, p, s, "PASS" if ok else "FAIL", f"{dt*1000:.0f}ms {t[:140]}"))
    return s, t, h

XFP = {"X-Forwarded-Proto": "https"}
n = [0]
def sup():
    n[0] += 1
    return {"name": f"S6 check supplier {int(time.time())}-{n[0]}"}

# ── S6: Origin must match scheme AND host ──
chk("S6", "http Origin, no X-Forwarded-Proto (local http) -> allowed", "POST", "/api/suppliers", ADMIN, sup(), want=(200, 201))
chk("S6", "https Origin to http app (the 11-04 scheme swap) -> 403", "POST", "/api/suppliers", ADMIN, sup(), origin=HTTPS_ORIGIN, want=(403,))
chk("S6", "https Origin + X-Forwarded-Proto: https (behind Traefik) -> allowed", "POST", "/api/suppliers", ADMIN, sup(), origin=HTTPS_ORIGIN, headers=XFP, want=(200, 201))
chk("S6", "http Origin to https app (http page on same host) -> 403", "POST", "/api/suppliers", ADMIN, sup(), headers=XFP, want=(403,))
chk("S6", "X-Forwarded-Proto: http + https Origin -> 403", "POST", "/api/suppliers", ADMIN, sup(), origin=HTTPS_ORIGIN, headers={"X-Forwarded-Proto": "http"}, want=(403,))
chk("S6", "foreign https Origin + X-Forwarded-Proto: https -> 403", "POST", "/api/suppliers", ADMIN, sup(), origin="https://evil.example", headers=XFP, want=(403,))
chk("S6", "prefix trick Origin + X-Forwarded-Proto: https -> 403", "POST", "/api/suppliers", ADMIN, sup(), origin=f"https://{HOST}:{PORT}.evil.example", headers=XFP, want=(403,))
chk("S6", "Origin: null + X-Forwarded-Proto: https -> 403", "POST", "/api/suppliers", ADMIN, sup(), origin="null", headers=XFP, want=(403,))
chk("S6", "upper-case https Origin + XFP https (URL-normalised) -> allowed", "POST", "/api/suppliers", ADMIN, sup(), origin=f"HTTPS://{HOST.upper()}:{PORT}", headers=XFP, want=(200, 201))
chk("S6", "X-Forwarded-Proto list 'https,http' (proxy chain) + https Origin -> allowed", "POST", "/api/suppliers", ADMIN, sup(), origin=HTTPS_ORIGIN, headers={"X-Forwarded-Proto": "https,http"}, want=(200, 201))
chk("S6", "login with scheme-swapped Origin -> 403", "POST", "/api/auth/login", None, {"email": "nimal@vegahomes.lk", "password": "VegaDemo-2026!"}, origin=HTTPS_ORIGIN, want=(403,))
chk("S6", "DELETE with scheme-swapped Origin -> 403", "DELETE", "/api/payments/filter-presets/nope", ADMIN, origin=HTTPS_ORIGIN, want=(403,))
chk("S6", "GET is not subject to the Origin check", "GET", "/api/suppliers", ADMIN, origin=HTTPS_ORIGIN, want=(200,))

# ── S7: no X-Powered-By anywhere ──
nopb = lambda s, t, h, c: "x-powered-by" not in h
for m, p, who in [("GET", "/login", None), ("GET", "/", None), ("GET", "/", ADMIN), ("GET", "/payments", ADMIN),
                  ("GET", "/api/auth/me", ADMIN), ("GET", "/api/auth/me", None), ("GET", "/api/healthz", None),
                  ("GET", "/no-such-page-zz", ADMIN), ("GET", "/favicon.ico", None)]:
    chk("S7", f"no X-Powered-By on {m} {p} ({'auth' if who else 'anon'})", m, p, who, want=(200, 302, 307, 401, 404), extra=nopb)

# ── N2: favicon exists, so no 404 HTML page without CSP ──
chk("N2", "favicon.ico served (200, image)", "GET", "/favicon.ico", None, want=(200,),
    extra=lambda s, t, h, c: "image" in h.get("content-type", ""))

# ── N3: unknown activity code ──
chk("N3", "PATCH unknown activity -> 404", "PATCH", "/api/activities/ZZZ-NOPE", ADMIN, {"name": "x"}, want=(404,))
_, at, *_ = req("GET", "/api/activities", ADMIN)
acts = json.loads(at); acts = acts.get("activities", acts) if isinstance(acts, dict) else acts
a0 = acts[0]
chk("N3", f"PATCH existing activity {a0['code']} to its own name -> 200", "PATCH", f"/api/activities/{a0['code']}", ADMIN, {"name": a0["name"]}, want=(200,))
chk("N3", "no ZZZ-NOPE row created", "GET", "/api/activities", ADMIN, extra=lambda s, t, h, c: "ZZZ-NOPE" not in t)

# ── N4: NUL byte at login always ends in the generic 401 ──
gen = lambda s, t, h, c: "Invalid email or password" in t and not any(x.startswith("vega_session=e") for x in c)
chk("N4", "NUL in unknown email -> 401 generic", "POST", "/api/auth/login", None, {"email": "a\u0000@x.lk", "password": "x"}, want=(401,), extra=gen)
chk("N4", "NUL inside a REAL email + correct password -> 401, no session", "POST", "/api/auth/login", None,
    {"email": "perf.staff7\u0000@vegahomes.lk", "password": "VegaDemo-2026!"}, want=(401,), extra=gen)
chk("N4", "NUL at end of real email + correct password -> 401, no session", "POST", "/api/auth/login", None,
    {"email": "perf.staff7@vegahomes.lk\u0000", "password": "VegaDemo-2026!"}, want=(401,), extra=gen)
chk("N4", "NUL in password -> 401 generic", "POST", "/api/auth/login", None, {"email": "perf.staff8@vegahomes.lk", "password": "VegaDemo\u0000-2026!"}, want=(401,), extra=gen)
chk("N4", "only NUL bytes as email -> 401 generic", "POST", "/api/auth/login", None, {"email": "\u0000\u0000", "password": "x"}, want=(401,), extra=gen)
chk("N4", "same real user still logs in normally", "POST", "/api/auth/login", None, {"email": "perf.staff7@vegahomes.lk", "password": "VegaDemo-2026!"}, want=(200,),
    extra=lambda s, t, h, c: any(x.startswith("vega_session=e") for x in c))

# ── N5: cheque date range 1900-2100 with the field's own message ──
P = "/api/projects/perf_p004/expenses/perf_p004_e061/payments"
def cq(inv, rel): return {"amount": 1, "date": "2026-11-01", "method": "Cheque", "chequeInvoicedDate": inv, "chequeReleaseDate": rel}
own_msg = lambda s, t, h, c: "Enter a valid date" in t
for d in ["0000-01-01", "0001-01-01", "1899-12-31", "2101-01-01", "9999-12-31"]:
    chk("N5", f"invoiced={d} -> 400 'Enter a valid date'", "POST", P, ADMIN, cq(d, "2026-12-31"), want=(400,), extra=own_msg)
    chk("N5", f"release={d} -> 400 'Enter a valid date'", "POST", P, ADMIN, cq("1950-01-01", d), want=(400,),
        extra=lambda s, t, h, c: "Enter a valid date" in t or "cannot be earlier" in t)
chk("N5", "boundaries 1900-01-01 .. 2100-12-31 accepted", "POST", P, ADMIN, cq("1900-01-01", "2100-12-31"), want=(200,))

# ── Method filter: Cheque on GET /api/payments ──
chk("MF", "method=Cheque accepted", "GET", "/api/payments?method=Cheque", ADMIN, want=(200,))
for bad in ["cheque", "Cheque'--", "Cheque%27%20or%201%3D1--", "Cheque%00", "Cash,Cheque"]:
    chk("MF", f"method={bad} -> 400", "GET", f"/api/payments?method={bad}", ADMIN, want=(400,))
chk("MF", "Staff + method=Cheque never shows foreign project", "GET", "/api/payments?method=Cheque&project=perf_p001", STAFF, want=(200, 400, 403),
    extra=lambda s, t, h, c: "perf_p001" not in t and "Homagama" not in t)
chk("MF", "Staff + method=Cheque (all tabs) has no foreign project", "GET", "/api/payments?method=Cheque&tab=suppliers", STAFF, want=(200,),
    extra=lambda s, t, h, c: '"perf_p001"' not in t)

json.dump(out, open(os.path.join(S, "fixes_verify_results.json"), "w"), indent=1)
from collections import Counter
print(Counter((r[0], r[5]) for r in out))
for r in out:
    if r[5] != "PASS": print(r)

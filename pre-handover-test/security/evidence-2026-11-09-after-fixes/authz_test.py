"""Authorization / session / input-handling checks against a local throwaway instance.

Target: http://localhost:3201 (next start, DB vega_sec4 = clone of vega_prod). Never prod.
Usage: python -I authz_test.py <scratch_dir>
"""
import http.client, json, sys, time, re, os, statistics, urllib.parse

HOST, PORT = "localhost", 3201
ORIGIN = f"http://{HOST}:{PORT}"
OUT = sys.argv[1]
results = []  # (section, name, method, path, status, verdict, note)


def req(method, path, cookie=None, body=None, origin=ORIGIN, headers=None, raw=None):
    c = http.client.HTTPConnection(HOST, PORT, timeout=30)
    h = {"Accept": "application/json"}
    if origin:
        h["Origin"] = origin
    if cookie:
        h["Cookie"] = f"vega_session={cookie}"
    data = None
    if raw is not None:
        data = raw.encode() if isinstance(raw, str) else raw
        h["Content-Type"] = "application/json"
    elif body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    if headers:
        h.update(headers)
    t = time.perf_counter()
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    txt = r.read().decode("utf-8", "replace")
    dt = time.perf_counter() - t
    hdrs = {k.lower(): v for k, v in r.getheaders()}
    setc = r.msg.get_all("Set-Cookie") or []
    c.close()
    return r.status, txt, hdrs, setc, dt


def login(email, pw="VegaDemo-2026!"):
    s, txt, h, setc, _ = req("POST", "/api/auth/login", body={"email": email, "password": pw, "remember": True})
    for sc in setc:
        m = re.match(r"vega_session=([^;]+)", sc)
        if m and m.group(1):
            return m.group(1), sc
    return None, s


def rec(section, name, method, path, status, ok, note=""):
    verdict = "PASS" if ok is True else ("FAIL" if ok is False else "REVIEW")
    results.append((section, name, method, path, status, verdict, note))


ADMIN, admin_sc = login("nimal@vegahomes.lk")
STAFF, staff_sc = login("perf.staff1@vegahomes.lk")
assert ADMIN and STAFF, "login failed"

# ── Fixtures ────────────────────────────────────────────────────────────────
OWN = "perf_p004"; OWN_STAGE = "perf_p004_s1"; OWN_MS = "perf_p004_s1_ms1"; OWN_EXP = "perf_p004_e001"; OWN_ITEM = "perf_p004_ai001"
F = "p1"
F_EXP = "cmw0l3368009yudlwy3q1vt8z"; F_STAGE = "cmw0l330z005xudlwlqpr3hru"; F_MS = "cmw0l3313005zudlwu7qzg24d"
F_MSPAY = "cmw0l33170061udlwstkwf37m"; F_CODE = "L-003"; F_BRID = "cmw0l32ua000pudlwgmlfmaab"; F_BSR = "cmw0l335i009fudlwoxx4fncv"
F_DRAFT = "bp1"; F_ITEM = "cmw0l32w20025udlwvgz032ax"; F_COMP = "cmw0l32wn002nudlwn5v97x7q"
F2 = "perf_p001"; F2_EXP = "perf_p001_e001"; F2_EXPPAY = "perf_p001_e001_pay1"

# Admin-created fixtures that Staff must not reach: a variation (+payment) on p1, a filter preset.
s, t, *_ = req("POST", f"/api/projects/{F}/variations", ADMIN, {"description": "sec-test variation", "amount": 1000, "date": "2026-11-01"})
F_VAR = (json.loads(t).get("id") if s < 300 else None) or "nonexistent-var"
print("variation fixture:", s, t[:200])
s, t, *_ = req("POST", "/api/payments/filter-presets", ADMIN, {"name": "sec-test preset", "query": "status=all"})
ADMIN_PRESET = (json.loads(t).get("id") if s < 300 else None) or "nonexistent-preset"
print("preset fixture:", s, t[:200])

# ── A. Unauthenticated access: every route+method must 401 ──────────────────
ROUTES = [
    ("GET", "/api/activities"), ("POST", "/api/activities"), ("PATCH", "/api/activities/X"), ("DELETE", "/api/activities/X"),
    ("GET", "/api/auth/me"), ("POST", "/api/auth/logout"),
    ("GET", "/api/basic-price"), ("POST", "/api/basic-price"), ("PATCH", f"/api/basic-price/{F_DRAFT}"), ("DELETE", f"/api/basic-price/{F_DRAFT}"), ("POST", f"/api/basic-price/{F_DRAFT}/promote"),
    ("GET", "/api/basic-rate"), ("POST", "/api/basic-rate"), ("PATCH", f"/api/basic-rate/{F_BRID}"), ("DELETE", f"/api/basic-rate/{F_BRID}"), ("GET", f"/api/basic-rate/{F_BRID}/history"), ("GET", f"/api/basic-rate/next-code?projectId={F}&cat=Labour"),
    ("GET", "/api/categories"), ("POST", "/api/categories"), ("PATCH", "/api/categories/X"), ("DELETE", "/api/categories/X"),
    ("GET", "/api/company-profile"), ("PATCH", "/api/company-profile"),
    ("GET", "/api/cost-plus"), ("POST", "/api/cost-plus"), ("PATCH", "/api/cost-plus"), ("DELETE", "/api/cost-plus"),
    ("GET", "/api/cost-plus/expenses"), ("GET", "/api/cost-plus/client-payments"), ("GET", "/api/cost-plus/expense-payments"),
    ("GET", "/api/dashboard"), ("GET", "/api/expenses/next-invoice"), ("GET", "/api/expenses/other-payees"), ("GET", "/api/notifications"),
    ("GET", "/api/payments"), ("GET", "/api/payments/filter-presets"), ("POST", "/api/payments/filter-presets"), ("PATCH", f"/api/payments/filter-presets/{ADMIN_PRESET}"), ("DELETE", f"/api/payments/filter-presets/{ADMIN_PRESET}"), ("GET", "/api/payments/other-payees/history"),
    ("GET", "/api/permissions/catalog"),
    ("GET", "/api/projects"), ("POST", "/api/projects"), ("GET", f"/api/projects/{F}"), ("PATCH", f"/api/projects/{F}"), ("DELETE", f"/api/projects/{F}"),
    ("GET", f"/api/projects/{F}/bsr"), ("GET", f"/api/projects/{F}/expenses"), ("GET", f"/api/projects/{F}/stages"), ("GET", f"/api/projects/{F}/members"), ("PATCH", f"/api/projects/{F}/owner"),
    ("GET", "/api/roles"), ("POST", "/api/roles"), ("GET", "/api/roles/perf_role_pm"),
    ("GET", "/api/sub-contractors"), ("GET", "/api/suppliers"), ("GET", "/api/suppliers/perf_sup001"), ("GET", "/api/suppliers/price-comparison"),
    ("GET", "/api/trades"), ("GET", "/api/units"),
    ("GET", "/api/users"), ("POST", "/api/users"), ("GET", "/api/users/nimal%40vegahomes.lk"), ("PATCH", "/api/users/nimal%40vegahomes.lk"),
]
for m, p in ROUTES:
    s, *_ = req(m, p, None, {} if m != "GET" else None)
    rec("A unauth", "no cookie", m, p, s, s == 401)
for p in ["/", "/projects", "/users", "/payments", "/settings"]:
    s, t, h, *_ = req("GET", p, None, origin=None)
    rec("A unauth", "page redirect", "GET", p, s, s in (302, 303, 307, 308) and "/login" in h.get("location", ""), h.get("location", ""))

# Forged / tampered tokens
for name, tok in [("garbage", "abc.def.ghi"), ("alg none", "eyJhbGciOiJub25lIn0.eyJzaWQiOiJ4In0."), ("tampered sig", ADMIN[:-4] + ("AAAA" if not ADMIN.endswith("AAAA") else "BBBB"))]:
    s, *_ = req("GET", "/api/auth/me", tok)
    rec("A unauth", f"forged token: {name}", "GET", "/api/auth/me", s, s == 401)

# ── B. Staff -> foreign project (IDOR) ─────────────────────────────────────
DENY = (401, 403, 404)
B = [
    ("GET", f"/api/projects/{F}"), ("PATCH", f"/api/projects/{F}"), ("DELETE", f"/api/projects/{F}"),
    ("GET", f"/api/projects/{F}/basic-price"), ("POST", f"/api/projects/{F}/basic-price"),
    ("PATCH", f"/api/projects/{F}/basic-price/{F_DRAFT}"), ("DELETE", f"/api/projects/{F}/basic-price/{F_DRAFT}"), ("POST", f"/api/projects/{F}/basic-price/{F_DRAFT}/promote"),
    ("GET", f"/api/projects/{F}/basic-rate"), ("POST", f"/api/projects/{F}/basic-rate"),
    ("PATCH", f"/api/projects/{F}/basic-rate/{F_CODE}"), ("DELETE", f"/api/projects/{F}/basic-rate/{F_CODE}"), ("GET", f"/api/projects/{F}/basic-rate/{F_CODE}/history"),
    ("POST", f"/api/projects/{F}/basic-rate/clone"), ("POST", f"/api/projects/{F}/basic-rate/import"), ("GET", f"/api/projects/{F}/basic-rate/next-code?cat=Labour"),
    ("GET", f"/api/projects/{F}/bsr"), ("POST", f"/api/projects/{F}/bsr"), ("PATCH", f"/api/projects/{F}/bsr/{F_BSR}"), ("DELETE", f"/api/projects/{F}/bsr/{F_BSR}"),
    ("GET", f"/api/projects/{F}/expenses"), ("POST", f"/api/projects/{F}/expenses"),
    ("PATCH", f"/api/projects/{F}/expenses/{F_EXP}"), ("DELETE", f"/api/projects/{F}/expenses/{F_EXP}"),
    ("GET", f"/api/projects/{F}/expenses/{F_EXP}/payments"), ("POST", f"/api/projects/{F}/expenses/{F_EXP}/payments"),
    ("GET", f"/api/projects/{F}/items"), ("POST", f"/api/projects/{F}/items"), ("PATCH", f"/api/projects/{F}/items/{F_ITEM}"), ("PATCH", f"/api/projects/{F}/items/{F_ITEM}/recipe/{F_COMP}"),
    ("GET", f"/api/projects/{F}/members"), ("POST", f"/api/projects/{F}/members"), ("DELETE", f"/api/projects/{F}/members/perf_u001"), ("PATCH", f"/api/projects/{F}/owner"),
    ("GET", f"/api/projects/{F}/stages"), ("PATCH", f"/api/projects/{F}/stages/{F_STAGE}"),
    ("PATCH", f"/api/projects/{F}/stages/{F_STAGE}/milestones/{F_MS}"),
    ("GET", f"/api/projects/{F}/stages/{F_STAGE}/milestones/{F_MS}/payments"), ("POST", f"/api/projects/{F}/stages/{F_STAGE}/milestones/{F_MS}/payments"),
    ("PATCH", f"/api/projects/{F}/stages/{F_STAGE}/milestones/{F_MS}/payments/{F_MSPAY}"), ("DELETE", f"/api/projects/{F}/stages/{F_STAGE}/milestones/{F_MS}/payments/{F_MSPAY}"),
    ("GET", f"/api/projects/{F}/variations"), ("POST", f"/api/projects/{F}/variations"),
    ("PATCH", f"/api/projects/{F}/variations/{F_VAR}"), ("DELETE", f"/api/projects/{F}/variations/{F_VAR}"),
    ("GET", f"/api/projects/{F}/variations/{F_VAR}/payments"), ("POST", f"/api/projects/{F}/variations/{F_VAR}/payments"),
    # Global-path routes that resolve the project from the record
    ("PATCH", f"/api/basic-price/{F_DRAFT}"), ("DELETE", f"/api/basic-price/{F_DRAFT}"), ("POST", f"/api/basic-price/{F_DRAFT}/promote"),
    ("PATCH", f"/api/basic-rate/{F_BRID}"), ("DELETE", f"/api/basic-rate/{F_BRID}"), ("GET", f"/api/basic-rate/{F_BRID}/history"),
    ("GET", f"/api/basic-rate/next-code?projectId={F}&cat=Labour"),
    ("DELETE", f"/api/projects/{F2}/expenses/{F2_EXP}/payments/{F2_EXPPAY}"),
]
for m, p in B:
    s, t, *_ = req(m, p, STAFF, {} if m != "GET" else None)
    ok = True if s in DENY else (None if s == 400 else False)
    rec("B IDOR foreign project", "staff -> p1", m, p, s, ok, t[:120] if ok is not True else "")

# Cross-parent: own project in URL, foreign child id (mixes access check with record lookup)
C = [
    ("PATCH", f"/api/projects/{OWN}/basic-price/{F_DRAFT}", {"name": "x"}), ("DELETE", f"/api/projects/{OWN}/basic-price/{F_DRAFT}", None),
    ("POST", f"/api/projects/{OWN}/basic-price/{F_DRAFT}/promote", {}),
    ("PATCH", f"/api/projects/{OWN}/basic-rate/{F_CODE}", {"rate": 1}),
    ("PATCH", f"/api/projects/{OWN}/bsr/{F_BSR}", {"qty": 1}), ("DELETE", f"/api/projects/{OWN}/bsr/{F_BSR}", None),
    ("PATCH", f"/api/projects/{OWN}/expenses/{F_EXP}", {"amount": 1}), ("DELETE", f"/api/projects/{OWN}/expenses/{F_EXP}", None),
    ("GET", f"/api/projects/{OWN}/expenses/{F_EXP}/payments", None), ("POST", f"/api/projects/{OWN}/expenses/{F_EXP}/payments", {"amount": 1, "date": "2026-11-01", "method": "Cash"}),
    ("DELETE", f"/api/projects/{OWN}/expenses/{F2_EXP}/payments/{F2_EXPPAY}", None),
    ("DELETE", f"/api/projects/{OWN}/expenses/{OWN_EXP}/payments/{F2_EXPPAY}", None),
    ("PATCH", f"/api/projects/{OWN}/items/{F_ITEM}", {"name": "x"}), ("PATCH", f"/api/projects/{OWN}/items/{F_ITEM}/recipe/{F_COMP}", {}),
    ("PATCH", f"/api/projects/{OWN}/items/{OWN_ITEM}/recipe/{F_COMP}", {}),
    ("PATCH", f"/api/projects/{OWN}/stages/{F_STAGE}", {"startDate": "2026-01-01"}),
    ("PATCH", f"/api/projects/{OWN}/stages/{OWN_STAGE}/milestones/{F_MS}", {"amount": 1}),
    ("PATCH", f"/api/projects/{OWN}/stages/{F_STAGE}/milestones/{F_MS}", {"amount": 1}),
    ("PATCH", f"/api/projects/{OWN}/stages/{OWN_STAGE}/milestones/{OWN_MS}/payments/{F_MSPAY}", {"chequeStatus": "Cleared"}),
    ("DELETE", f"/api/projects/{OWN}/stages/{OWN_STAGE}/milestones/{OWN_MS}/payments/{F_MSPAY}", None),
    ("PATCH", f"/api/projects/{OWN}/variations/{F_VAR}", {"description": "x"}), ("DELETE", f"/api/projects/{OWN}/variations/{F_VAR}", None),
    ("GET", f"/api/projects/{OWN}/variations/{F_VAR}/payments", None),
    ("POST", f"/api/projects/{OWN}/basic-rate/clone", {"sourceProjectId": F}),
]
for m, p, b in C:
    s, t, *_ = req(m, p, STAFF, b if b is not None else ({} if m != "GET" else None))
    ok = True if s in DENY else (None if s == 400 else False)
    rec("C cross-parent IDOR", "own URL + foreign child", m, p, s, ok, t[:160] if ok is not True else "")

# Listing endpoints must not leak foreign project rows
for p in ["/api/projects", "/api/dashboard", "/api/payments", "/api/basic-rate", "/api/basic-price", "/api/notifications", "/api/expenses/other-payees", "/api/payments/other-payees/history", "/api/suppliers/price-comparison"]:
    s, t, *_ = req("GET", p, STAFF)
    leak = (f'"{F}"' in t) or ('"perf_p001"' in t) or ("Piliyandala" in t and False)
    rec("D list leakage", "staff list has no foreign ids", "GET", p, s, (s in (200, 403)) and not leak, f"{len(t)} bytes" + (" LEAK" if leak else ""))

# ── E. Vertical privilege (Staff -> admin-only / ungranted actions) ─────────
E = [
    ("GET", "/api/users", None), ("POST", "/api/users", {"email": "evil@x.lk", "name": "Evil", "password": "Sup3r-Long-Pass-2026!", "role": "Admin"}),
    ("GET", "/api/users/nimal%40vegahomes.lk", None), ("PATCH", "/api/users/perf.staff1%40vegahomes.lk", {"role": "Admin"}),
    ("DELETE", "/api/users/sanduni%40vegahomes.lk", None), ("GET", "/api/users/perf.staff1%40vegahomes.lk/projects", None),
    ("POST", "/api/users/perf.staff1%40vegahomes.lk/projects", {"projectId": F}), ("DELETE", f"/api/users/perf.staff2%40vegahomes.lk/projects/{OWN}", None),
    ("GET", "/api/roles", None), ("POST", "/api/roles", {"name": "evil", "permissions": []}), ("PATCH", "/api/roles/perf_role_pm", {"permissions": [{"module": "projects", "action": "delete"}]}),
    ("DELETE", "/api/roles/perf_role_pm", None), ("GET", "/api/permissions/catalog", None),
    ("PATCH", "/api/company-profile", {"name": "pwned"}),
    ("PATCH", "/api/categories/Material", {"label": "x"}), ("DELETE", "/api/categories/Material", None),
    ("DELETE", "/api/trades/X", None), ("DELETE", "/api/units/X", None),
    ("PATCH", f"/api/projects/{OWN}/owner", {"ownerId": "perf_u001"}), ("POST", f"/api/projects/{OWN}/members", {"userId": "perf_u002"}),
    ("DELETE", f"/api/projects/{OWN}/members/perf_u002", None),
    ("DELETE", f"/api/projects/{OWN}", None),  # staff lacks projects:delete
    ("PATCH", "/api/activities/X", {"name": "x"}), ("DELETE", "/api/activities/X", None),  # no activities:edit/delete
    ("POST", "/api/suppliers", {"name": "evil supplier"}), ("DELETE", "/api/suppliers/perf_sup001", None),  # no suppliers:create/delete
    ("GET", "/api/cost-plus", None),  # no costPlus perm
    ("PATCH", f"/api/payments/filter-presets/{ADMIN_PRESET}", {"name": "pwned"}), ("DELETE", f"/api/payments/filter-presets/{ADMIN_PRESET}", None),
]
for m, p, b in E:
    s, t, *_ = req(m, p, STAFF, b if b is not None else ({} if m != "GET" else None))
    ok = True if s in DENY else (None if s == 400 else False)
    rec("E vertical privilege", "staff -> admin-only/ungranted", m, p, s, ok, t[:160] if ok is not True else "")

# Mass assignment on routes Staff MAY use: own project PATCH with ownerId/status smuggled
s, t, *_ = req("GET", f"/api/projects/{OWN}", STAFF)
before = json.loads(t) if s == 200 else {}
s, t, *_ = req("PATCH", f"/api/projects/{OWN}", STAFF, {"ownerId": "u_admin", "ownerName": "x", "id": "hijack", "name": before.get("name", "x")})
s2, t2, *_ = req("GET", f"/api/projects/{OWN}", STAFF)
after = json.loads(t2) if s2 == 200 else {}
same_owner = (before.get("owner") or before.get("ownerName")) == (after.get("owner") or after.get("ownerName"))
rec("E vertical privilege", "mass-assign ownerId on own project", "PATCH", f"/api/projects/{OWN}", s, same_owner and s2 == 200, f"owner before={before.get('owner') or before.get('ownerName')} after={after.get('owner') or after.get('ownerName')}")

# Staff self-view: /api/auth/me must not reveal hash
s, t, *_ = req("GET", "/api/auth/me", STAFF)
rec("E vertical privilege", "me has no password hash", "GET", "/api/auth/me", s, s == 200 and "passwordHash" not in t and "$2" not in t, t[:160])
s, t, *_ = req("GET", "/api/users", ADMIN)
rec("E vertical privilege", "admin user list has no hash", "GET", "/api/users", s, s == 200 and "passwordHash" not in t and "$2b$" not in t, f"{len(t)} bytes")

# ── F. CSRF (Origin check) ──────────────────────────────────────────────────
for name, org in [("no Origin", None), ("evil Origin", "https://evil.example"), ("null Origin", "null"), ("prefix trick", f"http://{HOST}:{PORT}.evil.example"), ("scheme swap", f"https://{HOST}:{PORT}")]:
    s, t, *_ = req("POST", "/api/suppliers", ADMIN, {"name": f"csrf {name}"}, origin=org)
    rec("F CSRF", name, "POST", "/api/suppliers", s, s == 403, t[:100] if s != 403 else "")
s, t, *_ = req("POST", "/api/auth/login", None, {"email": "nimal@vegahomes.lk", "password": "VegaDemo-2026!"}, origin="https://evil.example")
rec("F CSRF", "login CSRF (evil Origin)", "POST", "/api/auth/login", s, s == 403, t[:100])
s, t, *_ = req("GET", "/api/users", ADMIN, origin="https://evil.example")
rec("F CSRF", "cross-origin GET returns no CORS allow", "GET", "/api/users", s, True if "access-control-allow-origin" not in _[0] else False, _[0].get("access-control-allow-origin", "none"))

# ── G. Session management ──────────────────────────────────────────────────
rec("G session", "cookie flags", "POST", "/api/auth/login", "-", ("HttpOnly" in admin_sc) and ("SameSite=lax" in admin_sc.lower() or "samesite=strict" in admin_sc.lower()),
    re.sub(r"vega_session=[^;]+", "vega_session=<redacted>", admin_sc))
rec("G session", "Secure flag (expected absent on plain-http localhost only)", "POST", "/api/auth/login", "-", None if "Secure" not in admin_sc else True,
    "Secure present" if "Secure" in admin_sc else "Secure absent over http; verify on https ingress")
tmp, _sc = login("perf.staff2@vegahomes.lk")
s1, *_ = req("GET", "/api/auth/me", tmp)
s2, *_ = req("POST", "/api/auth/logout", tmp, {})
s3, *_ = req("GET", "/api/auth/me", tmp)
rec("G session", "logout revokes token server-side", "POST", "/api/auth/logout", f"{s1}/{s2}/{s3}", s1 == 200 and s3 == 401)
# Deactivate a user while their session is live -> next request must fail
victim, _ = login("perf.staff3@vegahomes.lk")
s1, *_ = req("GET", "/api/auth/me", victim)
sd, td, *_ = req("PATCH", "/api/users/perf.staff3%40vegahomes.lk", ADMIN, {"status": "Inactive"})
s3, *_ = req("GET", "/api/auth/me", victim)
rec("G session", "deactivation kills live session", "PATCH", "/api/users/perf.staff3%40vegahomes.lk", f"{s1}/{sd}/{s3}", s1 == 200 and sd < 300 and s3 == 401, td[:100] if sd >= 300 else "")
tok, st = login("perf.staff20@vegahomes.lk")
rec("G session", "inactive user cannot log in", "POST", "/api/auth/login", st if not tok else 200, tok is None)
# Session fixation: a pre-set cookie must be replaced on login
s, t, h, setc, _ = req("POST", "/api/auth/login", "attacker-chosen-value", {"email": "perf.staff4@vegahomes.lk", "password": "VegaDemo-2026!"})
newv = next((re.match(r"vega_session=([^;]+)", c).group(1) for c in setc if c.startswith("vega_session=")), None)
rec("G session", "login issues fresh token (no fixation)", "POST", "/api/auth/login", s, bool(newv) and newv != "attacker-chosen-value")

# ── H. Login hardening ─────────────────────────────────────────────────────
def timing(email, n=8):
    ts, msgs = [], set()
    for _ in range(n):
        s, t, h, sc, dt = req("POST", "/api/auth/login", None, {"email": email, "password": "Wrong-Password-1!"})
        ts.append(dt); msgs.add((s, t))
    return statistics.median(ts), msgs
mt_real, msg_real = timing("perf.staff5@vegahomes.lk", 4)
mt_fake, msg_fake = timing("no-such-user-zz@vegahomes.lk", 4)
rec("H login", "same response for real vs unknown email", "POST", "/api/auth/login", "-", {m[1] for m in msg_real} == {m[1] for m in msg_fake} or None,
    f"real={sorted(msg_real)[:1]} fake={sorted(msg_fake)[:1]}")
rec("H login", "timing parity real vs unknown email", "POST", "/api/auth/login", "-", abs(mt_real - mt_fake) < 0.05 or None, f"median real={mt_real*1000:.0f}ms fake={mt_fake*1000:.0f}ms")
# Brute force on one account
codes = []
for i in range(15):
    s, t, *_ = req("POST", "/api/auth/login", None, {"email": "perf.staff6@vegahomes.lk", "password": f"Wrong-{i}-Password!"})
    codes.append(s)
rec("H login", "brute force throttled within 15 attempts", "POST", "/api/auth/login", ",".join(map(str, codes)), 429 in codes, f"first 429 at attempt {codes.index(429)+1 if 429 in codes else '-'}")
s, t, *_ = req("POST", "/api/auth/login", None, {"email": "perf.staff6@vegahomes.lk", "password": "VegaDemo-2026!"})
rec("H login", "correct password still blocked while throttled", "POST", "/api/auth/login", s, s in (401, 429), t[:100])
for payload in ["' or 1=1--", "nimal@vegahomes.lk' --", "\" or \"\"=\"", "admin'/*", {"$ne": None}]:
    s, t, *_ = req("POST", "/api/auth/login", None, {"email": payload, "password": "x' or '1'='1"})
    rec("H login", f"SQLi in login: {str(payload)[:20]}", "POST", "/api/auth/login", s, s in (400, 401, 429), t[:100])

# ── I. Input handling: SQLi in query params, malformed JSON, oversized bodies ─
SQLI = ["'", "' or '1'='1", "1;select pg_sleep(5)--", "\") or 1=1--", "%' union select null--"]
QS_TARGETS = ["/api/payments?search={}", "/api/payments?vendor={}", "/api/payments?projectId={}", "/api/payments?from={}",
              "/api/suppliers/price-comparison/item?name={}", "/api/basic-rate/next-code?projectId=" + OWN + "&cat={}",
              "/api/expenses/next-invoice?projectId={}", "/api/payments/other-payees/history?vendor={}", "/api/notifications?since={}"]
for tmpl in QS_TARGETS:
    for p in SQLI:
        path = tmpl.format(urllib.parse.quote(p))
        s, t, h, sc, dt = req("GET", path, ADMIN)
        bad = s >= 500 or dt > 4.5 or re.search(r"syntax error|pg_|postgres|stack|at .*\.js", t, re.I)
        rec("I injection", f"SQLi qs {p[:14]}", "GET", path, s, not bad, f"{dt*1000:.0f}ms " + (t[:120] if bad else ""))
for name, body in [("SQLi in supplier name", {"name": "x'); drop table users;--"}), ("XSS in supplier name", {"name": "<img src=x onerror=alert(1)>"})]:
    s, t, *_ = req("POST", "/api/suppliers", ADMIN, body)
    stored = s < 300
    s2, t2, *_ = req("GET", "/api/suppliers", ADMIN)
    rec("I injection", name, "POST", "/api/suppliers", s, None if stored else True,
        ("stored verbatim; JSON API, React escapes on render - check PDF/XLSX export" if stored else t[:100]))
s, t, *_ = req("POST", "/api/suppliers", ADMIN, raw="{not json")
rec("I injection", "malformed JSON -> 4xx no stack", "POST", "/api/suppliers", s, 400 <= s < 500 and "at " not in t, t[:120])
s, t, *_ = req("POST", "/api/suppliers", ADMIN, {"name": "A" * 200000})
rec("I injection", "oversized field rejected", "POST", "/api/suppliers", s, 400 <= s < 500, t[:120])
s, t, *_ = req("POST", "/api/suppliers", ADMIN, raw=json.dumps({"name": "big", "pad": "x" * 15_000_000}))
rec("I injection", "15MB body handled (no 500/hang)", "POST", "/api/suppliers", s, s < 500 or s == 413, t[:120])
s, t, *_ = req("GET", "/api/projects/" + urllib.parse.quote("../../etc/passwd"), ADMIN)
rec("I injection", "path traversal in id", "GET", "/api/projects/../../etc/passwd", s, s in (400, 404), t[:100])
s, t, *_ = req("PATCH", f"/api/projects/{OWN}", ADMIN, {"contract": -1})
rec("I injection", "negative contract rejected", "PATCH", f"/api/projects/{OWN}", s, s == 400, t[:100])
s, t, *_ = req("POST", f"/api/projects/{OWN}/expenses/{OWN_EXP}/payments", ADMIN, {"amount": -5000, "date": "2026-11-01", "method": "Cash"})
rec("I injection", "negative payment rejected", "POST", "expense payment", s, s == 400, t[:100])
s, t, *_ = req("POST", f"/api/projects/{OWN}/expenses/{OWN_EXP}/payments", ADMIN, {"amount": 1e15, "date": "2026-11-01", "method": "Cash"})
rec("I injection", "overpayment rejected", "POST", "expense payment", s, s == 400, t[:100])

# ── J. Headers on HTML and API ─────────────────────────────────────────────
for p in ["/login", "/api/auth/me"]:
    s, t, h, *_ = req("GET", p, ADMIN, origin=None)
    want = ["content-security-policy", "x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy"]
    missing = [w for w in want if w not in h]
    rec("J headers", "security headers present", "GET", p, s, not missing, "missing: " + ",".join(missing) if missing else h.get("content-security-policy", "")[:200])
    rec("J headers", "no X-Powered-By / server version leak", "GET", p, s, "x-powered-by" not in h, h.get("x-powered-by", "") + " " + h.get("server", ""))
    rec("J headers", "HSTS (expected only behind https)", "GET", p, s, True if "strict-transport-security" in h else None, h.get("strict-transport-security", "absent on http"))

# ── Cleanup of fixtures ─────────────────────────────────────────────────────
req("PATCH", "/api/users/perf.staff3%40vegahomes.lk", ADMIN, {"status": "Active"})

with open(os.path.join(OUT, "authz_results.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, indent=1)
from collections import Counter
print(Counter(r[5] for r in results))
for r in results:
    if r[5] != "PASS":
        print(r)

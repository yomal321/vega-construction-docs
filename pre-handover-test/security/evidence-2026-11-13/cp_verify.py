"""Cost Plus module: horizontal/vertical access, cross-parent IDOR, mass assignment, input checks.

Listed as "not covered beyond its permission check" in every earlier report. The dataset has no
Cost Plus data and no user holds costPlus:*, so fixtures are created over the API:
  - Admin (sanduni@) creates project A (the "foreign" one) with an expense, a cheque expense
    payment and a cheque client payment.
  - Admin creates a Staff user with only costPlus:view/create/edit/delete; that user creates
    project B with the same children.
Then the Staff user attacks A directly and through B's ids. Run AFTER the other scripts.
Target: local throwaway instance only (see authz_test.py). Never prod.
Usage: python -I cp_verify.py <dir holding authz_test.py>
"""
import json, sys, os, subprocess, urllib.parse
S = sys.argv[1]
src = open(os.path.join(S, "authz_test.py"), encoding="utf-8").read().split("# ── Fixtures")[0]
sys.argv = [sys.argv[0], S]
exec(src)

PG = ["docker", "exec", "vega-perf-pg", "psql", "-U", "vega", "-d", "vega_sec5", "-tAc"]
def sql(q):
    r = subprocess.run(PG + [q], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

out = []
def chk(cid, name, m, p, who, body=None, want=(403,), extra=None, raw=None):
    s, t, h, _, dt = req(m, p, who, body, raw=raw)
    ok = s in want and (extra is None or extra(s, t))
    out.append((cid, name, m, p, s, "PASS" if ok else "FAIL", t[:160]))
    return s, t

def must(s, t, what):
    assert s in (200, 201), f"fixture failed: {what}: {s} {t[:200]}"
    return json.loads(t) if t else {}

CP, EXP, EPAY, CPAY = "/api/cost-plus", "/api/cost-plus/expenses", "/api/cost-plus/expense-payments", "/api/cost-plus/client-payments"
q = lambda base, **kw: base + "?" + urllib.parse.urlencode(kw)
TAG = str(int(time.time()))

ADMIN, _ = login("sanduni@vegahomes.lk")
NOCP, _ = login("perf.staff1@vegahomes.lk")          # holds no costPlus:* permission
assert ADMIN and NOCP
ADMIN_ID = sql("select id from users where email='sanduni@vegahomes.lk'")

def make_project(who, label):
    s, t, *_ = req("POST", CP, who, {"name": f"CP {label} {TAG}", "client": "Client", "location": "Colombo", "start": "2026-11-01", "marginPct": 10})
    must(s, t, f"create project {label}")
    pid = sql(f"select id from cost_plus_projects where name='CP {label} {TAG}'")
    s, t, *_ = req("POST", q(EXP, projectId=pid), who, {"date": "2026-11-02", "category": "Material", "description": f"exp {label}", "amount": 10000, "supplierId": "perf_sup001"})
    must(s, t, f"create expense {label}")
    eid = sql(f"""select id from cost_plus_expenses where "projectId"='{pid}' limit 1""")
    s, t, *_ = req("POST", q(EPAY, expenseId=eid), who, {"amount": 1000, "date": "2026-11-03", "method": "Cheque", "chequeDate": "2026-11-04"})
    must(s, t, f"create expense payment {label}")
    epid = sql(f"""select id from cost_plus_expense_payments where "expenseId"='{eid}' limit 1""")
    s, t, *_ = req("POST", q(CPAY, projectId=pid), who, {"amount": 500, "date": "2026-11-03", "method": "Cheque", "chequeDate": "2026-11-04"})
    must(s, t, f"create client payment {label}")
    cpid = sql(f"""select id from cost_plus_client_payments where "projectId"='{pid}' limit 1""")
    return pid, eid, epid, cpid

# ── Fixtures ───────────────────────────────────────────────────────────────
A, A_EXP, A_EPAY, A_CPAY = make_project(ADMIN, "A")
CP_EMAIL, CP_PW = f"cp.staff.{TAG}@vegahomes.lk", "CP-Check-Pass-2026!"
s, t, *_ = req("POST", "/api/users", ADMIN, {"name": "CP Staff", "email": CP_EMAIL, "role": "Staff", "password": CP_PW,
                                              "permissions": ["costPlus:view", "costPlus:create", "costPlus:edit", "costPlus:delete"]})
must(s, t, "create cp staff")
STAFF, _ = login(CP_EMAIL, CP_PW)
assert STAFF
STAFF_ID = sql(f"select id from users where email='{CP_EMAIL}'")
B, B_EXP, B_EPAY, B_CPAY = make_project(STAFF, "B")
out.append(("F", "fixtures: A (admin) and B (cp staff) each with expense, expense payment, client payment", "-", "-", 200, "PASS", f"A={A} B={B}"))

# ── V Vertical: a user without costPlus:* ──────────────────────────────────
for m, p, b in [("GET", CP, None), ("GET", q(CP, id=B), None), ("POST", CP, {"name": "x", "client": "x", "location": "x", "start": "2026-11-01"}),
                ("GET", q(EXP, projectId=B), None), ("GET", q(EPAY, expenseId=B_EXP), None), ("GET", q(CPAY, projectId=B), None),
                ("DELETE", q(CP, id=B), None)]:
    chk("V", "no costPlus permission -> 403", m, p, NOCP, b)
chk("V", "no session -> 401", "GET", CP, None, want=(401,))

# ── H Horizontal: cp staff -> admin's project A, direct ids ────────────────
s, t = chk("H", "portfolio list excludes A", "GET", CP, STAFF, want=(200,), extra=lambda s, t: A not in t and B in t)
H = [
    ("GET", q(CP, id=A), None), ("PATCH", q(CP, id=A), {"name": "pwned"}), ("DELETE", q(CP, id=A), None),
    ("GET", q(EXP, projectId=A), None),
    ("POST", q(EXP, projectId=A), {"date": "2026-11-02", "category": "Material", "description": "x", "amount": 1, "supplierId": "perf_sup001"}),
    ("PATCH", q(EXP, expenseId=A_EXP), {"date": "2026-11-02", "category": "Material", "description": "pwned", "amount": 10000, "supplierId": "perf_sup001"}),
    ("DELETE", q(EXP, expenseId=A_EXP), None),
    ("GET", q(EPAY, expenseId=A_EXP), None), ("POST", q(EPAY, expenseId=A_EXP), {"amount": 1, "date": "2026-11-03", "method": "Cash"}),
    ("PATCH", q(EPAY, expenseId=A_EXP, paymentId=A_EPAY), {"chequeStatus": "bounced"}),
    ("DELETE", q(EPAY, expenseId=A_EXP, paymentId=A_EPAY), None),
    ("GET", q(CPAY, projectId=A), None), ("POST", q(CPAY, projectId=A), {"amount": 1, "date": "2026-11-03", "method": "Cash"}),
    ("PATCH", q(CPAY, projectId=A, paymentId=A_CPAY), {"chequeStatus": "bounced"}),
    ("DELETE", q(CPAY, projectId=A, paymentId=A_CPAY), None),
]
for m, p, b in H:
    chk("H", "cp staff -> foreign project A", m, p, STAFF, b, want=(403, 404))

# ── X Cross-parent: B's parent ids (access passes) + A's child ids ─────────
X = [
    ("PATCH", q(EPAY, expenseId=B_EXP, paymentId=A_EPAY), {"chequeStatus": "bounced"}),
    ("DELETE", q(EPAY, expenseId=B_EXP, paymentId=A_EPAY), None),
    ("PATCH", q(CPAY, projectId=B, paymentId=A_CPAY), {"chequeStatus": "bounced"}),
    ("DELETE", q(CPAY, projectId=B, paymentId=A_CPAY), None),
    # extra params the handler does not read must not redirect it
    ("DELETE", q(EXP, expenseId=A_EXP, projectId=B), None),
    ("GET", q(CP, id=A, projectId=B), None),
]
for m, p, b in X:
    chk("X", "own parent + foreign child", m, p, STAFF, b, want=(403, 404))
st = sql(f"""select (select count(*) from cost_plus_projects where id='{A}' and name='CP A {TAG}')||','||
             (select count(*) from cost_plus_expenses where id='{A_EXP}' and description='exp A')||','||
             (select "chequeStatus" from cost_plus_expense_payments where id='{A_EPAY}')||','||
             (select "chequeStatus" from cost_plus_client_payments where id='{A_CPAY}')""")
out.append(("X", "A's project, expense and both payments unchanged in DB", "-", "-", 0, "PASS" if st == "1,1,received,received" else "FAIL", st))

# ── M Mass assignment ──────────────────────────────────────────────────────
s, t, *_ = req("POST", CP, STAFF, {"name": f"CP M {TAG}", "client": "c", "location": "l", "start": "2026-11-01", "marginPct": 10,
                                   "ownerId": ADMIN_ID, "id": "cp_attacker_chosen", "marginAmount": 999999})
row = sql(f"""select id||','||"ownerId"||','||"marginAmount" from cost_plus_projects where name='CP M {TAG}'""")
out.append(("M", "create: smuggled id/ownerId/marginAmount ignored", "POST", CP, s,
            "PASS" if s in (200, 201) and row and not row.startswith("cp_attacker_chosen") and f",{STAFF_ID}," in row and row.endswith(",0") else "FAIL", row))
s, t, *_ = req("PATCH", q(CP, id=B), STAFF, {"ownerId": ADMIN_ID, "marginAmount": 1})
own = sql(f"""select "ownerId" from cost_plus_projects where id='{B}'""")
out.append(("M", "patch: smuggled ownerId ignored", "PATCH", q(CP, id=B), s, "PASS" if own == STAFF_ID else "FAIL", f"owner={own}"))
s, t, *_ = req("POST", q(EPAY, expenseId=B_EXP), STAFF, {"amount": 1, "date": "2026-11-03", "method": "Cash", "recordedById": ADMIN_ID, "expenseId": A_EXP})
rec_by = sql(f"""select "recordedById"||','||"expenseId" from cost_plus_expense_payments where "expenseId" in ('{A_EXP}','{B_EXP}') and amount=1 and method='Cash'""")
out.append(("M", "payment: smuggled recordedById/expenseId ignored", "POST", EPAY, s, "PASS" if rec_by == f"{STAFF_ID},{B_EXP}" else "FAIL", rec_by))

# ── I Input validation and business rules ──────────────────────────────────
I = [
    ("POST", CP, {"name": "x", "client": "x", "location": "x", "start": "2026-11-01", "marginPct": -5}, "negative margin"),
    ("POST", CP, {"name": "x", "client": "x", "location": "x", "start": "2026-11-01", "marginPct": 1e6}, "huge margin"),
    ("POST", CP, {"name": "x", "client": "x", "location": "x", "start": "2026-02-30"}, "impossible date"),
    ("POST", CP, {"name": "A" * 200000, "client": "x", "location": "x", "start": "2026-11-01"}, "200k name"),
    ("PATCH", q(CP, id=B), {"status": "Deleted"}, "unknown status"),
    ("POST", q(EXP, projectId=B), {"date": "2026-11-02", "category": "Material", "description": "x", "amount": 1e12, "supplierId": "perf_sup001"}, "amount over cap"),
    ("POST", q(EXP, projectId=B), {"date": "2026-11-02", "category": "Material", "description": "x", "amount": -1, "supplierId": "perf_sup001"}, "negative amount"),
    ("POST", q(EXP, projectId=B), {"date": "2026-11-02", "category": "Material", "description": "x", "amount": 1, "supplierId": "nope' or 1=1--"}, "bad supplier id"),
    ("POST", q(EXP, projectId=B), {"date": "2026-11-02", "category": "Bribes", "description": "x", "amount": 1, "supplierId": "perf_sup001"}, "unknown category"),
    ("POST", q(EPAY, expenseId=B_EXP), {"amount": 999999, "date": "2026-11-03", "method": "Cash"}, "overpay expense"),
    ("POST", q(EPAY, expenseId=B_EXP), {"amount": 1, "date": "2026-11-03", "method": "Barter"}, "unknown method"),
    ("POST", q(CPAY, projectId=B), {"amount": 1e9, "date": "2026-11-03", "method": "Cash"}, "client pays over project total"),
    ("PATCH", q(CPAY, projectId=B, paymentId=B_CPAY), {"chequeStatus": "lost"}, "unknown cheque status"),
    ("POST", q(EXP, projectId=B), None, "malformed JSON"),
]
for m, p, b, label in I:
    raw = "{not json" if b is None else None
    chk("I", label, m, p, STAFF, b, want=(400,), raw=raw)
s, t = chk("I", "missing projectId param -> 400", "GET", EXP, STAFF, want=(400,))
s, t = chk("I", "unknown project id -> 404", "GET", q(EXP, projectId="cp_nope"), STAFF, want=(404,))
s, t, *_ = req("GET", q(CP, id="' or 1=1--"), STAFF)
out.append(("I", "id=' or 1=1-- -> 404, no rows", "GET", CP, s, "PASS" if s == 404 else "FAIL", t[:100]))

# ── Cleanup: the staff user (projects stay; throwaway DB) ──────────────────
s, t, *_ = req("DELETE", f"/api/users/{urllib.parse.quote(CP_EMAIL)}", ADMIN)
out.append(("CL", "cleanup: delete cp staff user", "DELETE", "/api/users/<cp.staff>", s, "PASS" if s in (200, 204, 409) else "FAIL", t[:120]))

for r in out:
    print(" | ".join(str(x) for x in r))
p = sum(1 for r in out if r[5] == "PASS")
print(f"\nTOTAL {len(out)}  PASS {p}  FAIL {len(out) - p}")
json.dump([dict(zip(["id", "name", "method", "path", "status", "verdict", "note"], r)) for r in out],
          open(os.path.join(S, "cp_verify_results.json"), "w", encoding="utf-8"), indent=1)

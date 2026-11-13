"""Targeted checks for the cheque payment feature (origin/dev 6c381b2..48ed074).

New surface: GET /api/payments/cheques, and Cheque + chequeInvoicedDate/chequeReleaseDate on
POST/GET /api/projects/[id]/expenses/[expenseId]/payments. Reuses helpers from authz_test.py.
Target: local throwaway instance only (see authz_test.py). Never prod.
Usage: python -I cheque_verify.py <dir holding authz_test.py>
"""
import json, sys, os, subprocess
S = sys.argv[1]
src = open(os.path.join(S, "authz_test.py"), encoding="utf-8").read().split("# ── Fixtures")[0]
sys.argv = [sys.argv[0], S]
exec(src)

PG = ["docker", "exec", "vega-perf-pg", "psql", "-U", "vega", "-d", "vega_sec4", "-tAc"]
def sql(q):
    return subprocess.run(PG + [q], capture_output=True, text=True).stdout.strip()

ADMIN, _ = login("sanduni@vegahomes.lk")
STAFF, _ = login("perf.staff1@vegahomes.lk")        # payments:view, projects:edit, owns/joins perf_p004
NOPAY, _ = login("perf.staff11@vegahomes.lk")       # no payments:view
NOEDIT, _ = login("perf.staff12@vegahomes.lk")      # payments:view, no projects:edit
assert ADMIN and STAFF and NOPAY and NOEDIT, "login failed"
ADMIN_ID = sql("select id from users where email='sanduni@vegahomes.lk'")

OWN, OWN_EXP, OWN_EXP2 = "perf_p004", "perf_p004_e130", "perf_p004_e061"
F, F_EXP = "perf_p001", "perf_p001_e022"
PAY = lambda p, e: f"/api/projects/{p}/expenses/{e}/payments"
out = []

def chk(cid, name, m, p, who, body=None, raw=None, want=(400,), origin=ORIGIN, extra=None):
    s, t, h, _, dt = req(m, p, who, body, raw=raw, origin=origin)
    ok = s in want and (extra is None or extra(s, t, dt))
    out.append((cid, name, m, p, s, "PASS" if ok else "FAIL", f"{dt*1000:.0f}ms {t[:150]}"))
    return s, t

def cheque(inv, rel, amount=1, method="Cheque"):
    b = {"amount": amount, "date": "2026-11-01", "method": method}
    if inv is not ...: b["chequeInvoicedDate"] = inv
    if rel is not ...: b["chequeReleaseDate"] = rel
    return b

# ── Fixtures: one cheque in an accessible project, one in a foreign one (as Admin) ──
s, t = chk("C1", "admin cheque on own-project expense", "POST", PAY(OWN, OWN_EXP), ADMIN, cheque("2026-11-01", "2026-11-05", 1000), want=(200,))
own_pay = json.loads(t).get("id") if s == 200 else None
s, t = chk("C1", "admin cheque on foreign-project expense", "POST", PAY(F, F_EXP), ADMIN, cheque("2026-11-02", "2026-11-03", 2000), want=(200,))
foreign_pay = json.loads(t).get("id") if s == 200 else None

# ── A. Access control on GET /api/payments/cheques ──
chk("C2", "cheques: no cookie -> 401", "GET", "/api/payments/cheques", None, want=(401,))
chk("C2", "cheques: forged cookie -> 401", "GET", "/api/payments/cheques", "eyJhbGciOiJub25lIn0.e30.", want=(401,))
chk("C2", "cheques: Staff without payments:view -> 403", "GET", "/api/payments/cheques", NOPAY, want=(403,))
chk("C2", "cheques: POST not allowed", "POST", "/api/payments/cheques", ADMIN, {}, want=(405,))
s, t = chk("C2", "cheques: Admin sees both fixtures", "GET", "/api/payments/cheques", ADMIN, want=(200,),
           extra=lambda s, t, dt: own_pay in t and foreign_pay in t)
s, t = chk("C2", "cheques: Staff sees own cheque, not foreign", "GET", "/api/payments/cheques", STAFF, want=(200,),
           extra=lambda s, t, dt: own_pay in t and foreign_pay not in t)
staff_rows = json.loads(t) if s == 200 else []
_, pt, *_ = req("GET", "/api/projects", STAFF)
plist = json.loads(pt)
plist = plist.get("projects", plist) if isinstance(plist, dict) else plist
staff_names = {p.get("name") for p in plist}
stray = sorted({r["projectName"] for r in staff_rows} - staff_names)
out.append(("C2", "cheques: every Staff row is in a project Staff can open", "GET", "/api/payments/cheques", 200,
            "PASS" if not stray else "FAIL", f"{len(staff_rows)} rows, stray projects: {stray}"))
chk("C2", "cheques: ?project=foreign query is ignored, still scoped", "GET", f"/api/payments/cheques?project={F}&projectId={F}", STAFF,
    want=(200,), extra=lambda s, t, dt: foreign_pay not in t)
chk("C2", "cheques: no password hash or user ids leak", "GET", "/api/payments/cheques", ADMIN, want=(200,),
    extra=lambda s, t, dt: "$2" not in t and "passwordHash" not in t and ADMIN_ID not in t)

# ── B. Access control on the cheque payment write/read ──
chk("C3", "Staff: cheque on foreign expense via foreign URL", "POST", PAY(F, F_EXP), STAFF, cheque("2026-11-01", "2026-11-02"), want=(403, 404))
chk("C3", "Staff: cheque on foreign expense via own URL", "POST", PAY(OWN, F_EXP), STAFF, cheque("2026-11-01", "2026-11-02"), want=(403, 404))
chk("C3", "Staff: read foreign expense's payments (cheque dates)", "GET", PAY(F, F_EXP), STAFF, want=(403, 404))
chk("C3", "Staff without projects:edit cannot record cheque", "POST", PAY(OWN, OWN_EXP2), NOEDIT, cheque("2026-11-01", "2026-11-02"), want=(403,))
chk("C3", "CSRF: cheque with foreign Origin", "POST", PAY(OWN, OWN_EXP2), STAFF, cheque("2026-11-01", "2026-11-02"), origin="https://evil.example", want=(403,))
chk("C3", "CSRF: cheque with no Origin", "POST", PAY(OWN, OWN_EXP2), STAFF, cheque("2026-11-01", "2026-11-02"), origin=None, want=(403,))
chk("C3", "Staff: cheque on own expense works", "POST", PAY(OWN, OWN_EXP2), STAFF, cheque("2026-11-01", "2026-11-02"), want=(200,))

# ── C. Validation of the two cheque dates (Admin, own expense) ──
P = PAY(OWN, OWN_EXP2)
chk("C4", "Cheque with no dates", "POST", P, ADMIN, cheque(..., ...))
chk("C4", "Cheque with only invoiced date", "POST", P, ADMIN, cheque("2026-11-01", ...))
chk("C4", "Cheque with only release date", "POST", P, ADMIN, cheque(..., "2026-11-01"))
chk("C4", "release earlier than invoiced", "POST", P, ADMIN, cheque("2026-11-05", "2026-11-04"),
    extra=lambda s, t, dt: "Cheque Release Date cannot be earlier than Cheque Invoiced Date" in t)
chk("C4", "method 'cheque' (lower case)", "POST", P, ADMIN, cheque("2026-11-01", "2026-11-02", method="cheque"))
BAD = ["2026-02-30", "2026-1-5", "2026-01-05T00:00:00Z", "2026-01-05 10:00", "05/01/2026", "not-a-date", "'",
       "2026-01-05'; select pg_sleep(5)--", "2026-01-05\u0000", "A" * 200_000, "0000-01-01", "99999-01-01",
       "+002026-01-05", "2026-W01-1", 20260105, ["2026-01-05"], {"$gt": ""}, True, None]
for d in BAD:
    label = repr(d)[:28]
    chk("C4", f"invoiced={label}", "POST", P, ADMIN, cheque(d, "2026-12-31"), extra=lambda s, t, dt: dt < 3)
    chk("C4", f"release={label}", "POST", P, ADMIN, cheque("2026-01-01", d), extra=lambda s, t, dt: dt < 3)
chk("C4", "malformed JSON body", "POST", P, ADMIN, raw='{"method":"Cheque",')
chk("C4", "cheque overpaying the expense", "POST", P, ADMIN, cheque("2026-11-01", "2026-11-02", amount=10**12))
chk("C4", "cheque negative amount", "POST", P, ADMIN, cheque("2026-11-01", "2026-11-02", amount=-5))

# ── D. Stored values (what reaches the DATE columns) ──
s, t = chk("C5", "same-day cheque accepted", "POST", P, ADMIN, cheque("2026-11-06", "2026-11-06"), want=(200,))
same = json.loads(t).get("id") if s == 200 else None
s, t = chk("C5", "post-dated cheque accepted", "POST", P, ADMIN, cheque("2026-11-06", "2027-03-01"), want=(200,))
s, t = chk("C5", "Cash with cheque dates -> dates dropped", "POST", P, ADMIN, cheque("2026-11-01", "2026-11-02", method="Cash"), want=(200,))
cash = json.loads(t).get("id") if s == 200 else None
s, t = chk("C5", "mass assignment: id/recordedById/expenseId smuggled", "POST", P, ADMIN,
           {**cheque("2026-11-01", "2026-11-02"), "id": "expp_attacker", "recordedById": "perf_u_staff1", "expenseId": F_EXP}, want=(200,))
mass = json.loads(t).get("id") if s == 200 else None
row = lambda i: sql(f"select method, \"chequeInvoicedDate\"::text, \"chequeReleaseDate\"::text, \"recordedById\", \"expenseId\" from expense_payments where id='{i}'")
out.append(("C5", "DB: same-day row", "SQL", same, 0, "PASS" if row(same).startswith("Cheque|2026-11-06|2026-11-06|") else "FAIL", row(same)))
out.append(("C5", "DB: Cash row has null cheque dates", "SQL", cash, 0, "PASS" if row(cash).startswith("Cash|||") else "FAIL", row(cash)))
r = row(mass)
out.append(("C5", "DB: smuggled fields ignored", "SQL", mass, 0,
            "PASS" if mass != "expp_attacker" and r.endswith(f"|{ADMIN_ID}|{OWN_EXP2}") else "FAIL", f"id={mass} {r}"))
out.append(("C5", "DB: no expp_attacker row", "SQL", "expp_attacker", 0,
            "PASS" if sql("select count(*) from expense_payments where id='expp_attacker'") == "0" else "FAIL", ""))
cons = sql("select string_agg(conname, ',' order by conname) from pg_constraint where conrelid='expense_payments'::regclass and contype='c'")
out.append(("C5", "DB: both CHECK constraints present", "SQL", "pg_constraint", 0,
            "PASS" if "cheque_dates_only_for_cheque" in cons and "cheque_release_after_invoiced" in cons else "FAIL", cons))
bad = sql("insert into expense_payments (id, \"expenseId\", amount, date, method, \"recordedById\", \"chequeInvoicedDate\", \"chequeReleaseDate\") "
          f"values ('expp_db_bypass', '{OWN_EXP2}', 1, now(), 'Cash', '{ADMIN_ID}', '2026-01-01', '2026-01-02') returning id")
out.append(("C5", "DB: CHECK blocks cheque dates on a Cash row (direct SQL)", "SQL", "insert", 0, "PASS" if bad == "" else "FAIL", bad or "rejected"))

# ── E. Stored-payload behaviour in the export data ──
xss = "<img src=x onerror=alert(1)>=HYPERLINK(\"http://evil.example\",\"x\")"
s, t = chk("C6", "supplier with HTML + formula name", "POST", "/api/suppliers", ADMIN, {"name": xss[:100]}, want=(200, 201))
sup_id = json.loads(t).get("id") if s in (200, 201) else None
sql(f"update expenses set \"supplierId\"='{sup_id}' where id='{OWN_EXP2}'")
chk("C6", "payload comes back as inert JSON string", "GET", "/api/payments/cheques", ADMIN, want=(200,),
    extra=lambda s, t, dt: "=HYPERLINK" in t and "application/json" in req("GET", "/api/payments/cheques", ADMIN)[2].get("content-type", ""))

json.dump(out, open(os.path.join(S, "cheque_verify_results.json"), "w"), indent=1)
from collections import Counter
print(Counter((r[0], r[5]) for r in out))
for r in out:
    if r[5] != "PASS": print(r)

"""Targeted regression checks for S1-S4 fixes (PR 1338). Reuses helpers from authz_test.py."""
import json, sys, os
S = sys.argv[1]
src = open(os.path.join(S, "authz_test.py"), encoding="utf-8").read().split("# ── Fixtures")[0]
sys.argv = [sys.argv[0], S]
exec(src)
ADMIN, _ = login("sanduni@vegahomes.lk")
OWN, ST, MS, EXP = "perf_p004", "perf_p004_s1", "perf_p004_s1_ms1", "perf_p004_e001"
out = []

def chk(fid, name, m, p, body=None, raw=None, want=(400,)):
    s, t, *_ = req(m, p, ADMIN, body, raw=raw)
    ok = s in want
    out.append((fid, name, m, p, s, "PASS" if ok else "FAIL", t[:140]))

BAD_DATES = ["'", "not-a-date", "2026-13-45", "2026-01-05'; select pg_sleep(5)--", "x start-sleep -s 15"]
for d in BAD_DATES:
    chk("S3", f"stage startDate={d[:20]}", "PATCH", f"/api/projects/{OWN}/stages/{ST}", {"startDate": d})
    chk("S3", f"stage completionDate={d[:20]}", "PATCH", f"/api/projects/{OWN}/stages/{ST}", {"completionDate": d})
    chk("S3", f"milestone dueDate={d[:20]}", "PATCH", f"/api/projects/{OWN}/stages/{ST}/milestones/{MS}", {"dueDate": d})
    chk("S3", f"project start={d[:20]}", "PATCH", f"/api/projects/{OWN}", {"start": d})
    chk("S3", f"expense payment date={d[:20]}", "POST", f"/api/projects/{OWN}/expenses/{EXP}/payments", {"amount": 1, "date": d, "method": "Cash"})
chk("S3", "new project start=garbage", "POST", "/api/projects", {"name": "x", "client": "x", "location": "x", "start": "garbage", "stages": 4, "contract": 1})
chk("S3", "payment method not in enum", "POST", f"/api/projects/{OWN}/expenses/{EXP}/payments", {"amount": 1, "date": "2026-11-01", "method": "S4feV4lu3"})
chk("S3", "payment method Cheque (expense)", "POST", f"/api/projects/{OWN}/expenses/{EXP}/payments", {"amount": 1, "date": "2026-11-01", "method": "Cheque"})
chk("S3", "NUL byte in supplier name", "POST", "/api/suppliers", {"name": "bad\u0000name"})
chk("S3", "NUL byte in trade name", "POST", "/api/trades", {"name": "bad\u0000name"})
chk("S3", "malformed JSON (suppliers)", "POST", "/api/suppliers", raw="{not json")
chk("S3", "malformed JSON (php payload)", "POST", f"/api/projects/{OWN}/bsr", raw="<?php exec('id'); ?>")
chk("S3", "malformed JSON (PATCH)", "PATCH", f"/api/projects/{OWN}", raw="class.module.classLoader")
chk("S3", "15MB body", "POST", "/api/suppliers", raw=json.dumps({"name": "big", "pad": "x" * 15_000_000}), want=(400, 413))
chk("S3", "basic-price unknown activity", "POST", f"/api/projects/{OWN}/basic-price", {"activity": "ZZZ-NOPE", "cat": "material", "name": "x", "unit": "Bag", "price": 1})
chk("S3", "delete in-use activity -> 409", "DELETE", "/api/activities/05", want=(409,))
chk("S3", "PATCH unknown activity code", "PATCH", "/api/activities/ZZZ-NOPE", {"name": "x"}, want=(400, 404))

BIG = "A" * 200_000
for p, b in [("/api/suppliers", {"name": BIG}), ("/api/sub-contractors", {"name": BIG}), ("/api/activities", {"name": BIG}),
             ("/api/trades", {"name": BIG}), ("/api/units", {"name": BIG}), ("/api/categories", {"label": BIG, "prefix": "Z"}),
             ("/api/roles", {"name": BIG, "permissions": []}), ("/api/projects", {"name": BIG, "client": "x", "location": "x", "start": "2026-11-01", "stages": 4, "contract": 1}),
             (f"/api/projects/{OWN}/basic-price", {"activity": "05", "cat": "material", "name": BIG, "unit": "Bag", "price": 1}),
             (f"/api/projects/{OWN}/basic-rate", {"cat": "material", "name": BIG, "unit": "Bag", "rate": 1}),
             ("/api/payments/filter-presets", {"name": BIG, "query": "x"}),
             ("/api/users", {"email": "x@vegahomes.lk", "name": BIG, "password": "Long-Enough-Pass-2026!", "role": "Staff"})]:
    chk("S4", f"200k name -> {p}", "POST", p, b)
for m, p, b in [("PATCH", "/api/suppliers/perf_sup001", {"name": BIG}), ("PATCH", "/api/company-profile", {"name": BIG}),
                ("PATCH", f"/api/projects/{OWN}", {"client": BIG}), ("PATCH", "/api/users/perf.staff9%40vegahomes.lk", {"name": BIG})]:
    chk("S4", f"200k field -> {m} {p}", m, p, b)
s, t, *_ = req("POST", "/api/auth/login", None, {"email": "a" * 100_000 + "@x.lk", "password": "p" * 100_000})
out.append(("S4", "login 100k email/password", "POST", "/api/auth/login", s, "PASS" if s == 400 else "FAIL", t[:140]))
chk("S4", "role with 501 permissions", "POST", "/api/roles", {"name": "big role", "permissions": ["projects:view"] * 501})
chk("S4", "clone with 100k codes", "POST", f"/api/projects/{OWN}/basic-rate/clone", {"sourceProjectId": "perf_p009", "codes": ["L-001"] * 100_000})
# Sanity: normal-sized writes still work after the caps
chk("S4", "normal supplier still accepted", "POST", "/api/suppliers", {"name": "Regression Supplier OK"}, want=(200, 201))
chk("S4", "valid stage date still accepted", "PATCH", f"/api/projects/{OWN}/stages/{ST}", {"startDate": "2025-03-13"}, want=(200, 400))

json.dump(out, open(os.path.join(S, "fix_verify_results.json"), "w"), indent=1)
from collections import Counter
print(Counter((r[0], r[5]) for r in out))
for r in out:
    if r[5] != "PASS": print(r)

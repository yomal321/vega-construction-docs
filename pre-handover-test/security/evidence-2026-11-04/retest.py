import json, sys, re, importlib.util, os
sys.argv = [sys.argv[0], sys.argv[1]]
# reuse helpers without re-running the suite
src = open(os.path.join(sys.argv[1], "authz_test.py"), encoding="utf-8").read().split("# ── Fixtures")[0]
exec(src)
STAFF, _ = login("perf.staff1@vegahomes.lk"); ADMIN, _ = login("nimal@vegahomes.lk")
OWN = "perf_p004"; OWN_STAGE = "perf_p004_s1"; OWN_MS = "perf_p004_s1_ms1"; OWN_ITEM = "perf_p004_ai001"
F_ITEM = "cmw0l32w20025udlwvgz032ax"; F_MSPAY = "cmw0l33170061udlwstkwf37m"; F_DRAFT = "bp1"

def show(label, m, p, b, who=None):
    s, t, *_ = req(m, p, who or STAFF, b)
    print(f"{s}  {label}  {m} {p}  {t[:160]}")

show("promote foreign draft (global path)", "POST", f"/api/basic-price/{F_DRAFT}/promote", {"code": "L-999", "unit": "Day", "price": 10})
show("promote foreign draft (own URL)", "POST", f"/api/projects/{OWN}/basic-price/{F_DRAFT}/promote", {"code": "L-998", "unit": "Day", "price": 10})
show("patch foreign item (own URL)", "PATCH", f"/api/projects/{OWN}/items/{F_ITEM}", {"name": "x", "unit": "Day", "analysisQty": 1, "profitPct": 10, "recipe": []})
for st in ["received", "cleared", "bounced"]:
    show("cheque status on foreign milestone payment (own URL)", "PATCH", f"/api/projects/{OWN}/stages/{OWN_STAGE}/milestones/{OWN_MS}/payments/{F_MSPAY}", {"chequeStatus": st})
show("clone from foreign project", "POST", f"/api/projects/{OWN}/basic-rate/clone", {"sourceProjectId": "p1", "codes": ["L-003"]})
show("other-payees history", "GET", "/api/payments/other-payees/history?vendor=x&name=x&payee=x", None)

s, t, *_ = req("GET", "/api/suppliers/price-comparison", STAFF)
d = json.loads(t)
print("price-comparison top-level type:", type(d).__name__, (list(d.keys())[:10] if isinstance(d, dict) else len(d)))
sample = json.dumps(d)[:1500]
print(sample)
acc = set(re.findall(r'"(perf_p0\d\d|p\d+)"', t))
print("project ids in staff price-comparison response:", sorted(acc))
s, t, *_ = req("GET", "/api/projects", STAFF)
print("staff accessible projects:", sorted(x["id"] for x in json.loads(t)) if s == 200 else s)

"""Single large request bodies (no app-level body size limit in parseBody). One at a time.
Local throwaway instance only. Usage: python -I body_size_check.py <dir> <server pid>"""
import sys, os, subprocess, time, json
S, PID = sys.argv[1], sys.argv[2]
src = open(os.path.join(S, "authz_test.py"), encoding="utf-8").read().split("# ── Fixtures")[0]
sys.argv = [sys.argv[0], S]
exec(src)
def rss():
    o = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {PID}).WorkingSet64"], capture_output=True, text=True).stdout.strip()
    return int(o) // (1024 * 1024)
STAFF, _ = login("sanduni@vegahomes.lk")  # Admin, so parseBody actually runs
rows = []
for mb in [1, 10, 50, 100]:
    raw = '{"name": "' + "A" * (mb * 1024 * 1024) + '"}'
    before = rss()
    try:
        s, t, h, _, dt = req("POST", "/api/suppliers", STAFF, raw=raw)
    except Exception as e:
        s, t, dt = "ERR", repr(e)[:80], 0
    time.sleep(1)
    after = rss()
    s2, *_ = req("GET", "/api/healthz")
    rows.append({"body_mb": mb, "status": s, "seconds": round(dt, 2), "rss_before_mb": before, "rss_after_mb": after, "healthz_after": s2, "body": t[:80]})
    print(rows[-1])
s, t, *_ = req("POST", "/api/auth/login", None, raw='{"email": "' + "a" * (50 * 1024 * 1024) + '@x.lk", "password": "x"}')
print({"unauthenticated_login_50mb": s, "body": t[:80]})
json.dump(rows, open(os.path.join(S, "body_size_results.json"), "w"), indent=1)

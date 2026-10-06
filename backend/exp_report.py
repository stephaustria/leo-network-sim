import json
import sys
import urllib.request

exp_id = sys.argv[1]
base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
d = json.load(urllib.request.urlopen(f"{base}/experiments/{exp_id}"))

print(d["name"], "|", d["status"], "| failure window:", d["failure_window"])
cols = [("mean_goodput", "goodput"), ("traffic_lost_gbit", "lost Gbit"),
        ("mean_latency_ms", "lat ms"), ("p95_latency_ms", "p95 ms"),
        ("mean_hops", "hops"), ("route_changes_per_tick", "chg/tick"),
        ("handoffs_total", "handoffs"), ("mean_overloaded_links", "overload")]
print(f"{'arm':36}" + "".join(f"{h:>11}" for _, h in cols) + f"{'recovery s':>12}")
for a in d["arms"]:
    s = a.get("summary")
    if not s:
        print(f"{a['label']:36} {a['status']} ({a['n_ticks']} ticks)")
        continue
    row = "".join(f"{str(s.get(k)):>11}" for k, _ in cols)
    rec = (s.get("failure") or {}).get("recovery_time_s")
    print(f"{a['label']:36}{row}{str(rec):>12}")
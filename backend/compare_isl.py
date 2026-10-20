import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def call(path, body=None):
    req = urllib.request.Request(
        BASE + path, data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    return json.load(urllib.request.urlopen(req))


existing = {s["name"]: s["id"] for s in call("/scenarios")}
variants = {
    "ISL grid": {"mode": "grid"},
    "Nearest, replan every tick": {"mode": "nearest", "replan_s": 0},
    "Nearest, replan 5 min": {"mode": "nearest", "replan_s": 300},
    "Nearest, replan 15 min": {"mode": "nearest", "replan_s": 900},
    "No ISL (bent pipe)": {"mode": "none"},
}

print(f"{'variant':28} {'reachable':>10} {'latency ms':>11} {'hops':>6} {'churn/tick':>11}")
for name, isl in variants.items():
    full = f"Compare {name}"
    sid = existing.get(full) or call("/scenarios", {"name": full, "config": {"isl": isl}})["id"]
    tl = call(f"/simulation/run?scenario_id={sid}&duration=1200&dt=60&load_scale=5")["timeline"]
    lat = [t["mean_latency_ms"] for t in tl if t["mean_latency_ms"] is not None]
    hops = [t["mean_hops"] for t in tl if t["mean_hops"] is not None]
    churn = sum(t["links_added"] + t["links_removed"] for t in tl[1:]) / max(1, len(tl) - 1)
    print(f"{name:28} {sum(t['flows_reachable'] for t in tl) / len(tl):>7.1f}/15 "
          f"{(sum(lat) / len(lat)) if lat else float('nan'):>11.1f} "
          f"{(sum(hops) / len(hops)) if hops else float('nan'):>6.1f} {churn:>11.1f}")
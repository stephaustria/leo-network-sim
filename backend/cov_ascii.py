import json
import sys
import urllib.request

extra = sys.argv[1] if len(sys.argv) > 1 else ""        # for example: &scenario_id=3
d = json.load(urllib.request.urlopen(f"http://127.0.0.1:8000/coverage?res_deg=5{extra}"))
g, avail, shades = d["grid"], d["availability"], " .:-=+*#%@"

print(f"{d['params']['n_sats']} satellites | global availability {d['summary']['global_availability']} | "
      f"mean in view {d['summary']['global_mean_visible']} | computed in {d['elapsed_s']} s")
for i in reversed(range(g["n_lat"])):
    row = avail[i * g["n_lon"]:(i + 1) * g["n_lon"]]
    print(f"{g['lat0'] + i * g['res_deg']:6.1f} " + "".join(shades[min(9, int(v * 9.999))] for v in row))
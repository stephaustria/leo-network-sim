import asyncio
import json
import sys

import websockets

URL = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8000/ws/live"


async def main():
    async with websockets.connect(URL) as ws:
        init = json.loads(await ws.recv())
        print("init:", init["constellation"]["n_sats"], "sats,", len(init["stations"]), "stations")
        if "/live" in URL:
            await ws.send(json.dumps({"cmd": "start", "dt": 60, "duration": 900,
                                      "speed": 2, "load_scale": 3}))
        async for raw in ws:
            m = json.loads(raw)
            if m["type"] == "frame":
                x = m["metrics"]
                print(f"t={m['t']:6.0f} reach={x['flows_reachable']}/{x['flows_total']} "
                      f"deliv={x['delivery_ratio']} lat={x['mean_latency_ms']} "
                      f"maxutil={x['max_link_util']} handoffs={x['handoffs']}")
            elif m["type"] in ("done", "error"):
                print(m)
                break


asyncio.run(main())
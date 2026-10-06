import asyncio
import json

import websockets


async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws/live") as ws:
        await ws.recv()      # init
        await ws.send(json.dumps({"cmd": "start", "dt": 60, "duration": 900, "speed": 3,
                                  "load_scale": 3, "policy": "congestion_aware"}))
        n = 0
        async for raw in ws:
            m = json.loads(raw)
            if m["type"] in ("done", "error"):
                print(m)
                break
            if m["type"] != "frame":
                continue
            n += 1
            x = m["metrics"]
            print(f"t={m['t']:5.0f} reach={x['flows_reachable']}/{x['flows_total']} "
                  f"deliv={x['delivery_ratio']} failed_sats={len(m['failures']['sats'])} "
                  f"failed_isls={len(m['failures']['isls'])}")
            if n == 3:
                await ws.send(json.dumps({"cmd": "fail", "kind": "seam", "target": 5}))
                print(">> cut seam between planes 5 and 6")
            if n == 7:
                await ws.send(json.dumps({"cmd": "recover"}))
                print(">> recover all")


asyncio.run(main())
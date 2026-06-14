#!/usr/bin/env python3
"""
load_gen.py — fire requests at the rate-limit testbed and print a live scoreboard.

Usage:
    python load_gen.py                         # defaults: 10 rps across all routes
    python load_gen.py --rps 50 --duration 30  # 50 rps for 30 seconds
    python load_gen.py --routes /api/slow      # target a single route
"""

import argparse
import asyncio
import time
from collections import defaultdict

import httpx


async def main():
    parser = argparse.ArgumentParser(description="rate-limit-testbed load generator")
    parser.add_argument("--base-url", default="http://localhost:9004")
    parser.add_argument("--rps", type=float, default=10, help="requests per second (spread across routes)")
    parser.add_argument("--duration", type=int, default=60, help="seconds to run")
    parser.add_argument("--routes", nargs="*", default=None, help="specific route(s) to hit; omit for all")
    args = parser.parse_args()

    # discover routes from the testbed's /_config endpoint
    async with httpx.AsyncClient(base_url=args.base_url, timeout=5) as client:
        resp = await client.get("/_config")
        resp.raise_for_status()
        all_routes = resp.json()["routes"]

    if args.routes:
        routes = [r for r in all_routes if r["path"] in args.routes]
    else:
        routes = all_routes

    if not routes:
        print("No matching routes found. Available:")
        for r in all_routes:
            print(f"  {r['method']} {r['path']}")
        return

    print(f"Targeting {len(routes)} route(s) at ~{args.rps} rps for {args.duration}s")
    for r in routes:
        print(f"  {r['method']:6s} {r['path']:30s}  429@{r['reject_rate']:.0%}")
    print()

    stats = defaultdict(lambda: {"total": 0, "429": 0, "ok": 0, "err": 0})
    interval = 1.0 / args.rps
    deadline = time.monotonic() + args.duration
    route_idx = 0

    async with httpx.AsyncClient(base_url=args.base_url, timeout=10) as client:
        while time.monotonic() < deadline:
            r = routes[route_idx % len(routes)]
            route_idx += 1
            path = r["path"]

            try:
                if r["method"].upper() == "POST":
                    resp = await client.post(path, json={"test": True})
                else:
                    resp = await client.get(path)

                stats[path]["total"] += 1
                if resp.status_code == 429:
                    stats[path]["429"] += 1
                else:
                    stats[path]["ok"] += 1
            except Exception:
                stats[path]["total"] += 1
                stats[path]["err"] += 1

            # print scoreboard every ~1s worth of requests
            if route_idx % max(1, int(args.rps)) == 0:
                print_scoreboard(stats)

            await asyncio.sleep(interval)

    print("\n=== Final ===")
    print_scoreboard(stats)


def print_scoreboard(stats: dict):
    print(f"\033[2J\033[H", end="")  # clear screen
    print(f"{'Route':30s} {'Total':>8s} {'  OK':>8s} {' 429':>8s} {'429%':>8s} {' Err':>8s}")
    print("-" * 74)
    for path, s in sorted(stats.items()):
        pct = (s["429"] / s["total"] * 100) if s["total"] else 0
        print(f"{path:30s} {s['total']:8d} {s['ok']:8d} {s['429']:8d} {pct:7.1f}% {s['err']:8d}")


if __name__ == "__main__":
    asyncio.run(main())

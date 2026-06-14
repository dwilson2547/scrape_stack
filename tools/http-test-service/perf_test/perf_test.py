#!/usr/bin/env python3
"""
perf_test.py — phase-driven long-form load generator for the rate-limit testbed.

Runs until stopped (Ctrl+C / SIGTERM). The last phase (or any phase with
hold: true) holds indefinitely; all preceding phases run for duration_seconds.

Usage:
    python perf_test.py                         # phases from perf_phases.yaml
    python perf_test.py --cycle                 # repeat all phases indefinitely
    python perf_test.py --config my.yaml        # alternate phase config
    python perf_test.py --base-url http://host:9004
"""

import argparse
import asyncio
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
import yaml


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class Phase:
    name: str
    rps: float
    duration_seconds: int = 60
    routes: Optional[list] = None  # None = all routes
    hold: bool = False


def load_phases(config_path: Path) -> list[Phase]:
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    return [
        Phase(
            name=p["name"],
            rps=float(p["rps"]),
            duration_seconds=int(p.get("duration_seconds", 60)),
            routes=p.get("routes"),
            hold=bool(p.get("hold", False)),
        )
        for p in raw["phases"]
    ]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class PhaseStats:
    name: str
    start: float = field(default_factory=time.monotonic)
    end: float = 0.0
    total: int = 0
    ok: int = 0
    rejected: int = 0
    err: int = 0

    def elapsed(self) -> float:
        return (self.end or time.monotonic()) - self.start

    def rate_429(self) -> float:
        return self.rejected / self.total if self.total else 0.0


# ---------------------------------------------------------------------------
# Request firing
# ---------------------------------------------------------------------------

async def fire(client: httpx.AsyncClient, route: dict, stats: PhaseStats) -> None:
    try:
        if route["method"].upper() == "POST":
            resp = await client.post(route["path"], json={"test": True})
        else:
            resp = await client.get(route["path"])
        stats.total += 1
        if resp.status_code == 429:
            stats.rejected += 1
        else:
            stats.ok += 1
    except Exception:
        stats.total += 1
        stats.err += 1


# ---------------------------------------------------------------------------
# Phase runner
# ---------------------------------------------------------------------------

async def run_phase(
    client: httpx.AsyncClient,
    all_routes: list,
    phase: Phase,
    stop: asyncio.Event,
) -> PhaseStats:
    routes = [r for r in all_routes if r["path"] in phase.routes] if phase.routes else all_routes
    if not routes:
        routes = all_routes

    stats = PhaseStats(name=phase.name)
    interval = 1.0 / phase.rps
    deadline = None if phase.hold else time.monotonic() + phase.duration_seconds
    route_idx = 0
    in_flight: set[asyncio.Task] = set()

    label = "(hold until stopped)" if phase.hold else f"{phase.duration_seconds}s"
    print(f"[{phase.name}]  {phase.rps} rps  {label}")

    while not stop.is_set():
        if deadline is not None and time.monotonic() >= deadline:
            break

        r = routes[route_idx % len(routes)]
        route_idx += 1

        task = asyncio.create_task(fire(client, r, stats))
        in_flight.add(task)
        task.add_done_callback(in_flight.discard)

        await asyncio.sleep(interval)

    if in_flight:
        await asyncio.gather(*in_flight, return_exceptions=True)

    stats.end = time.monotonic()
    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    here = Path(__file__).parent
    parser = argparse.ArgumentParser(description="phase-driven long-form load generator")
    parser.add_argument("--base-url", default="http://localhost:9004")
    parser.add_argument("--config", default=str(here / "perf_phases.yaml"))
    parser.add_argument("--cycle", action="store_true", help="repeat all phases indefinitely")
    args = parser.parse_args()

    phases = load_phases(Path(args.config))
    if not phases:
        print("No phases defined in config.")
        sys.exit(1)

    # ensure the last phase holds unless one is already marked
    if not any(p.hold for p in phases):
        phases[-1].hold = True

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: (print("\nStopping..."), stop.set()))

    async with httpx.AsyncClient(base_url=args.base_url, timeout=10) as client:
        try:
            resp = await client.get("/_config")
            resp.raise_for_status()
            all_routes = resp.json()["routes"]
        except Exception as e:
            print(f"Cannot reach {args.base_url}/_config: {e}")
            sys.exit(1)

        cycle_label = "  (cycling)" if args.cycle else ""
        print(f"Target: {args.base_url}  |  {len(all_routes)} routes")
        print(f"Phases: {' → '.join(p.name for p in phases)}{cycle_label}\n")

        all_stats: list[PhaseStats] = []

        while True:
            for phase in phases:
                if stop.is_set():
                    break
                stats = await run_phase(client, all_routes, phase, stop)
                all_stats.append(stats)
            if not args.cycle or stop.is_set():
                break

    print("\n=== Summary ===")
    print(f"{'Phase':15s} {'Elapsed':>9s} {'Requests':>10s} {'OK':>8s} {'429':>8s} {'429%':>8s} {'Err':>8s}")
    print("-" * 67)
    for s in all_stats:
        print(
            f"{s.name:15s} {s.elapsed():8.1f}s {s.total:10d} "
            f"{s.ok:8d} {s.rejected:8d} {s.rate_429() * 100:7.1f}% {s.err:8d}"
        )


if __name__ == "__main__":
    asyncio.run(main())

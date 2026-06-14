#!/usr/bin/env python3
"""
Load simulator for the request-auth service.

Spawns N consumer threads that each loop: acquire permit → hold → release.
Status codes are randomly mixed to exercise backoff, recovery, and the full
OTel metric suite on the server side.

Usage:
    python tests/load_sim.py
    python tests/load_sim.py --consumers 10 --domain api.example.com
    python tests/load_sim.py --consumers 8 --domain shop.example.com --hold 50 300 --rate-429 0.20
    python tests/load_sim.py --addr localhost:9000 --consumers 3 --domain a.io --domain b.io
"""

import argparse
import random
import threading
import time

from request_auth_client import RequestAuthClient


def _pick_status(rate_429: float) -> int:
    if random.random() < rate_429:
        return 429
    return random.choices([200, 500, 404], weights=[85, 10, 5])[0]


def consumer(
    client: RequestAuthClient,
    domain: str,
    hold_range: tuple[int, int],
    rate_429: float,
    stats: dict,
    stop: threading.Event,
) -> None:
    while not stop.is_set():
        t0 = time.monotonic()
        try:
            with client.acquire(domain) as permit:
                wait_ms = (time.monotonic() - t0) * 1000
                time.sleep(random.randint(*hold_range) / 1000)
                status = _pick_status(rate_429)
                permit.set_status(status)
        except Exception as exc:
            if not stop.is_set():
                print(f"  [error] {exc}", flush=True)
            time.sleep(1.0)
            continue

        with stats["lock"]:
            stats["total"] += 1
            stats["wait_sum"] += wait_ms
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            stats["by_domain"][domain] = stats["by_domain"].get(domain, 0) + 1


def reporter(stats: dict, stop: threading.Event, interval: float = 5.0) -> None:
    last_total = 0
    last_ts = time.monotonic()
    while not stop.is_set():
        time.sleep(interval)
        if stop.is_set():
            break
        now = time.monotonic()
        with stats["lock"]:
            total = stats["total"]
            wait_sum = stats["wait_sum"]
            by_status = dict(stats["by_status"])
            by_domain = dict(stats["by_domain"])

        elapsed = now - last_ts
        rps = (total - last_total) / elapsed if elapsed > 0 else 0.0
        avg_wait = (wait_sum / total) if total else 0.0
        status_str = "  ".join(f"HTTP {k}: {v:,}" for k, v in sorted(by_status.items()))
        domain_str = "  ".join(f"{d}: {n:,}" for d, n in sorted(by_domain.items()))

        print(
            f"[{time.strftime('%H:%M:%S')}]  "
            f"total={total:,}  rps={rps:.1f}  avg_wait={avg_wait:.0f}ms\n"
            f"  statuses  {status_str}\n"
            f"  domains   {domain_str}",
            flush=True,
        )
        last_total = total
        last_ts = now


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Request-auth load simulator — generates OTel metric traffic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.strip(),
    )
    parser.add_argument(
        "--addr", default="localhost:9000", metavar="HOST:PORT",
        help="gRPC server address (default: localhost:9000)",
    )
    parser.add_argument(
        "--domain", action="append", dest="domains", metavar="DOMAIN",
        help="Target domain; repeat for multiple (default: loadtest.example.com)",
    )
    parser.add_argument(
        "--consumers", type=int, default=5, metavar="N",
        help="Number of concurrent consumer threads (default: 5)",
    )
    parser.add_argument(
        "--hold", nargs=2, type=int, default=[100, 500], metavar=("MIN_MS", "MAX_MS"),
        help="Permit hold time range in milliseconds (default: 100 500)",
    )
    parser.add_argument(
        "--rate-429", type=float, default=0.10, metavar="P",
        help="Probability of reporting 429 on release to exercise backoff (default: 0.10)",
    )
    parser.add_argument(
        "--stats-interval", type=float, default=5.0, metavar="SECS",
        help="How often to print stats (default: 5)",
    )
    args = parser.parse_args()

    domains = args.domains or ["loadtest.example.com"]
    hold_range = (args.hold[0], args.hold[1])

    print(
        f"request-auth load simulator\n"
        f"  server    : {args.addr}\n"
        f"  domains   : {', '.join(domains)}\n"
        f"  consumers : {args.consumers}\n"
        f"  hold      : {hold_range[0]}–{hold_range[1]} ms\n"
        f"  p(429)    : {args.rate_429:.0%}\n"
        f"\nPress Ctrl+C to stop.\n",
        flush=True,
    )

    client = RequestAuthClient(args.addr)
    stats: dict = {
        "lock": threading.Lock(),
        "total": 0,
        "wait_sum": 0.0,
        "by_status": {},
        "by_domain": {},
    }
    stop = threading.Event()

    threads = []
    for i in range(args.consumers):
        domain = domains[i % len(domains)]
        t = threading.Thread(
            target=consumer,
            args=(client, domain, hold_range, args.rate_429, stats, stop),
            daemon=True,
        )
        t.start()
        threads.append(t)

    rep = threading.Thread(
        target=reporter,
        args=(stats, stop, args.stats_interval),
        daemon=True,
    )
    rep.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping…", flush=True)
        stop.set()
        client.close()
        print(f"Done. {stats['total']:,} permits total.", flush=True)


if __name__ == "__main__":
    main()

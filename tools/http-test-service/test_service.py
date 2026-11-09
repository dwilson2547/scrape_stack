#!/usr/bin/env python3
"""
Smoke test for the 429 test service.

Usage:
    pip install requests
    python test_service.py
    python test_service.py --base-url http://localhost:9004
    python test_service.py --samples 100
"""

import argparse
import sys
import requests

TOLERANCE = 0.20   # allowed deviation from configured reject_rate
SAMPLES = 60       # requests per probabilistic/distribution route


def check(label: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return passed


# ---------------------------------------------------------------------------
# Test sections
# ---------------------------------------------------------------------------

def test_healthz(base: str) -> int:
    failures = 0
    print("\n=== healthz ===")
    try:
        r = requests.get(f"{base}/healthz", timeout=5)
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        if not check("GET /healthz → 200 {status: ok}", ok, f"got {r.status_code} {r.text[:80]}"):
            failures += 1
    except Exception as e:
        check("GET /healthz reachable", False, str(e))
        print("\nService unreachable — is it running?  docker compose up -d")
        sys.exit(1)
    return failures


def test_config(base: str):
    failures = 0
    print("\n=== /_config ===")
    r = requests.get(f"{base}/_config", timeout=5)
    ok = r.status_code == 200 and "routes" in r.json()
    if not check("GET /_config → 200 with routes", ok, f"got {r.status_code}"):
        failures += 1
    routes = r.json().get("routes", [])
    if not check("at least one route configured", len(routes) > 0, f"found {len(routes)}"):
        failures += 1
    return failures, routes


def test_robots_txt(base: str) -> int:
    failures = 0
    print("\n=== /robots.txt ===")
    r = requests.get(f"{base}/robots.txt", timeout=5)
    if not check("GET /robots.txt → 200", r.status_code == 200, f"got {r.status_code}"):
        return 1
    if not check("contains User-agent directive", "User-agent:" in r.text, r.text[:80]):
        failures += 1
    return failures


def test_probe(base: str) -> int:
    failures = 0
    print("\n=== /probe/{code} ===")
    for code in [200, 201, 301, 400, 403, 404, 429, 500, 503]:
        r = requests.get(f"{base}/probe/{code}", timeout=5, allow_redirects=False)
        if not check(f"GET /probe/{code} → {code}", r.status_code == code, f"got {r.status_code}"):
            failures += 1
    r = requests.get(f"{base}/probe/200/some/nested/path.html", timeout=5)
    if not check("wildcard path /probe/200/some/nested/path.html → 200", r.status_code == 200):
        failures += 1
    return failures


def test_probabilistic_routes(base: str, routes: list, samples: int) -> int:
    failures = 0
    prob_routes = [
        r for r in routes
        if r["reject_rate"] > 0 and not r["status_distribution"] and r["window_max"] is None
    ]
    if not prob_routes:
        return 0

    print(f"\n=== probabilistic routes ({samples} samples each) ===")
    for route in prob_routes:
        path, method = route["path"], route["method"].upper()
        configured_rate = route["reject_rate"]
        retry_after_cfg = route.get("retry_after")
        url = f"{base}{path}"

        total = ok_count = rejected = retry_ok = 0
        for _ in range(samples):
            try:
                fn = requests.post if method == "POST" else requests.get
                resp = fn(url, json={"test": True} if method == "POST" else None, timeout=5)
                total += 1
                if resp.status_code >= 400:
                    rejected += 1
                    if retry_after_cfg is not None and "Retry-After" in resp.headers:
                        retry_ok += 1
                else:
                    ok_count += 1
            except Exception as e:
                print(f"    request error: {e}")
                total += 1

        actual_rate = rejected / total if total else 0
        lo = max(0.0, configured_rate - TOLERANCE)
        hi = min(1.0, configured_rate + TOLERANCE)

        print(f"\n  {method} {path}  (configured reject_rate={configured_rate:.0%})")
        if not check(
            f"reject rate within ±{TOLERANCE:.0%} of {configured_rate:.0%}",
            lo <= actual_rate <= hi,
            f"got {actual_rate:.0%}  ({rejected}/{total})",
        ):
            failures += 1

        if retry_after_cfg is not None and rejected > 0:
            if not check("all rejections include Retry-After header", retry_ok == rejected,
                         f"{retry_ok}/{rejected} had it"):
                failures += 1

    return failures


def test_windowed_routes(base: str, routes: list) -> int:
    failures = 0
    windowed = [r for r in routes if r.get("window_max") is not None]
    if not windowed:
        return 0

    print("\n=== windowed rate-limit routes ===")

    for route in windowed:
        path, method = route["path"], route["method"].upper()
        window_max = route["window_max"]
        rl_headers = route.get("rate_limit_headers", False)
        url = f"{base}{path}"

        print(f"\n  {method} {path}  (window_max={window_max})")

        # reset before test to ensure a clean window
        requests.post(f"{base}/_reset_windows", timeout=5)

        fn = requests.post if method == "POST" else requests.get
        results = [fn(url, timeout=5).status_code for _ in range(window_max + 5)]

        ok_count = sum(1 for s in results if s < 400)
        reject_count = sum(1 for s in results if s >= 400)

        if not check(f"first {window_max} requests accepted", ok_count >= window_max,
                     f"got {ok_count} ok"):
            failures += 1
        if not check("requests beyond window_max are rejected", reject_count >= 5,
                     f"got {reject_count} rejected"):
            failures += 1

        if rl_headers:
            requests.post(f"{base}/_reset_windows", timeout=5)
            resp = fn(url, timeout=5)
            has_all = all(h in resp.headers for h in ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"])
            if not check("X-RateLimit-* headers present on response", has_all,
                         str({k: resp.headers.get(k) for k in ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]})):
                failures += 1

    return failures


def test_distribution_routes(base: str, routes: list, samples: int) -> int:
    failures = 0
    dist_routes = [r for r in routes if r.get("status_distribution")]
    if not dist_routes:
        return 0

    print(f"\n=== distribution routes ({samples} samples each) ===")
    for route in dist_routes:
        path, method = route["path"], route["method"].upper()
        distribution = {d["status"]: d["weight"] for d in route["status_distribution"]}
        expected_statuses = set(distribution.keys())
        url = f"{base}{path}"

        print(f"\n  {method} {path}  (distribution={sorted(expected_statuses)})")

        seen_statuses = set()
        for _ in range(samples):
            try:
                fn = requests.post if method == "POST" else requests.get
                seen_statuses.add(fn(url, timeout=5).status_code)
            except Exception as e:
                print(f"    request error: {e}")

        unexpected = seen_statuses - expected_statuses
        if not check("all returned codes are in the distribution", not unexpected,
                     f"unexpected: {unexpected}" if unexpected else ""):
            failures += 1

        for status, weight in distribution.items():
            if weight >= 0.1:  # only assert codes with meaningful weight
                if not check(f"status {status} (weight={weight:.0%}) seen at least once",
                             status in seen_statuses):
                    failures += 1

    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:9004")
    parser.add_argument("--samples", type=int, default=SAMPLES)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    failures = 0

    failures += test_healthz(base)
    cfg_failures, routes = test_config(base)
    failures += cfg_failures
    failures += test_robots_txt(base)
    failures += test_probe(base)
    failures += test_probabilistic_routes(base, routes, args.samples)
    failures += test_windowed_routes(base, routes)
    failures += test_distribution_routes(base, routes, args.samples)

    print(f"\n{'='*40}")
    print("ALL TESTS PASSED" if failures == 0 else f"{failures} TEST(S) FAILED")
    print()
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()

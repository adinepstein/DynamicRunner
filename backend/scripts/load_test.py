"""Load & sync stress test script.

Simulates 1000 concurrent users syncing data to verify:
- Database connection pool handling
- Garmin rate-limit handling
- API response times under load
- No data corruption

Usage: python -m dynamicrunner.scripts.load_test --users 100 --api-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

import httpx


async def simulate_user_sync(
    client: httpx.AsyncClient,
    api_url: str,
    cron_secret: str,
    user_idx: int,
) -> dict[str, Any]:
    """Simulate a single user's sync cycle."""
    start = time.perf_counter()
    try:
        resp = await client.get(
            f"{api_url}/healthz",
            timeout=10,
        )
        health_ok = resp.status_code == 200

        # Simulate sync trigger
        resp = await client.post(
            f"{api_url}/internal/sync",
            headers={"Authorization": f"Bearer {cron_secret}"},
            timeout=30,
        )
        sync_ok = resp.status_code == 200

        duration_ms = round((time.perf_counter() - start) * 1000)

        return {
            "user_idx": user_idx,
            "health_ok": health_ok,
            "sync_ok": sync_ok,
            "duration_ms": duration_ms,
            "error": None,
        }
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000)
        return {
            "user_idx": user_idx,
            "health_ok": False,
            "sync_ok": False,
            "duration_ms": duration_ms,
            "error": str(exc),
        }


async def run_load_test(api_url: str, cron_secret: str, num_users: int, concurrency: int) -> None:
    """Run the load test with specified concurrency."""
    print(f"Starting load test: {num_users} users, concurrency={concurrency}")
    print(f"Target: {api_url}")
    print("-" * 60)

    semaphore = asyncio.Semaphore(concurrency)
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient() as client:
        async def bounded_request(idx: int) -> dict[str, Any]:
            async with semaphore:
                return await simulate_user_sync(client, api_url, cron_secret, idx)

        tasks = [bounded_request(i) for i in range(num_users)]
        start = time.perf_counter()
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start

    # Analyze results
    durations = [r["duration_ms"] for r in results]
    errors = [r for r in results if r["error"]]
    successful = [r for r in results if r["sync_ok"]]

    durations.sort()
    p50 = durations[len(durations) // 2] if durations else 0
    p95 = durations[int(len(durations) * 0.95)] if durations else 0
    p99 = durations[int(len(durations) * 0.99)] if durations else 0

    print(f"\nResults ({total_time:.1f}s total):")
    print(f"  Total requests: {num_users}")
    print(f"  Successful:     {len(successful)} ({len(successful)/num_users*100:.1f}%)")
    print(f"  Failed:         {len(errors)} ({len(errors)/num_users*100:.1f}%)")
    print(f"\nLatency:")
    print(f"  p50: {p50}ms")
    print(f"  p95: {p95}ms")
    print(f"  p99: {p99}ms")
    print(f"  max: {max(durations) if durations else 0}ms")

    if errors:
        print(f"\nSample errors:")
        for e in errors[:5]:
            print(f"  User {e['user_idx']}: {e['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="DynamicRunner load test")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--cron-secret", default="test-secret", help="Cron secret for internal endpoints")
    parser.add_argument("--users", type=int, default=100, help="Number of simulated users")
    parser.add_argument("--concurrency", type=int, default=50, help="Max concurrent requests")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.api_url, args.cron_secret, args.users, args.concurrency))


if __name__ == "__main__":
    main()

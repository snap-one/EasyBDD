"""
Diagnostic: verify a Wattbox's telnet server tolerates N concurrent sessions.

Before relying on N-way concurrent Jenkins builds that each independently
telnet into the *same* shared Wattbox for fault insertion (e.g. 10 device
tests, each toggling its own outlet on one physical Wattbox unit), use this
to confirm the Wattbox's own embedded telnet server actually supports that
many simultaneous sessions. Many PDU-class embedded devices only support a
single telnet session and will reject, queue, or cross-talk additional ones
regardless of what the test framework or Jenkins does.

Each session runs in its own OS process (not a thread), so this mirrors the
real scenario -- N separate `python -m easybdd` Jenkins job processes each
independently opening their own connection -- rather than N threads sharing
one interpreter.

Usage:
    python scripts/test_wattbox_concurrent_telnet.py --host 192.168.10.2 \\
        --password '...' --sessions 10

By default every session sends the same safe, read-only "?Firmware" query
and the results are checked for consistency. Pass --command/--prompt to
exercise a different command (e.g. the real fault-insertion
"!OutletSet=<N>,OFF") if you specifically want to validate that one under
concurrency -- non-idempotent commands will actually change device state.
"""

import argparse
import multiprocessing
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from easybdd.services.telnet_service import TelnetService  # noqa: E402
from easybdd.core.connection_pool import ConnectionPool  # noqa: E402


def _worker(index, host, port, username, password, command, prompt, timeout, result_queue):
    start = time.time()
    try:
        pool = ConnectionPool()
        service = TelnetService(pool)
        response = service.execute(
            "telnet.send",
            {
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "command": command,
                "prompt": prompt,
                "timeout": timeout,
            },
            {},
        )
        result_queue.put(
            {"index": index, "ok": True, "response": response, "elapsed": time.time() - start}
        )
    except Exception as exc:
        result_queue.put(
            {"index": index, "ok": False, "error": str(exc), "elapsed": time.time() - start}
        )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--host", required=True, help="Wattbox IP/hostname")
    parser.add_argument("--port", type=int, default=23)
    parser.add_argument("--username", default=os.environ.get("WATTBOX_USERNAME", "wattbox"))
    parser.add_argument(
        "--password", default=os.environ.get("WATTBOX_PASSWORD"),
        help="Wattbox telnet password (or set WATTBOX_PASSWORD)",
    )
    parser.add_argument("--sessions", type=int, default=10, help="Number of concurrent telnet sessions")
    parser.add_argument(
        "--command", default="?Firmware",
        help="Command to send on every session (default: safe read-only query)",
    )
    parser.add_argument("--prompt", default=">")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    if not args.password:
        parser.error("--password is required (or set WATTBOX_PASSWORD)")

    print(f"Opening {args.sessions} concurrent telnet sessions to {args.host}:{args.port} ...")
    print(f"Command per session: {args.command!r}  (prompt={args.prompt!r})")
    print()

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    procs = [
        ctx.Process(
            target=_worker,
            args=(i, args.host, args.port, args.username, args.password,
                  args.command, args.prompt, args.timeout, result_queue),
        )
        for i in range(args.sessions)
    ]

    overall_start = time.time()
    for p in procs:
        p.start()

    results = [result_queue.get() for _ in procs]
    for p in procs:
        p.join()
    overall_elapsed = time.time() - overall_start

    results.sort(key=lambda r: r["index"])
    passed = 0
    responses_seen = set()
    for r in results:
        if r["ok"]:
            preview = str(r["response"]).strip().replace("\n", "\\n")[:80]
            print(f"  [{r['index']:2d}] OK   {r['elapsed']:5.2f}s  response={preview!r}")
            responses_seen.add(str(r["response"]).strip())
            passed += 1
        else:
            print(f"  [{r['index']:2d}] FAIL {r['elapsed']:5.2f}s  error={r['error']}")

    print()
    print(f"{passed}/{args.sessions} sessions succeeded in {overall_elapsed:.2f}s total wall time")

    if passed and len(responses_seen) > 1:
        print(
            f"⚠️  {len(responses_seen)} distinct response values seen across successful "
            f"sessions. If every session sent the identical command, this can indicate "
            f"cross-talk between concurrent telnet sessions on the device -- responses "
            f"landing in the wrong session's buffer."
        )

    if passed < args.sessions:
        print(
            f"⚠️  {args.sessions - passed} session(s) failed. The Wattbox may not tolerate "
            f"{args.sessions} concurrent telnet sessions -- try lowering --sessions to find "
            f"the actual limit."
        )
        sys.exit(1)

    print("All sessions succeeded with consistent responses.")


if __name__ == "__main__":
    main()

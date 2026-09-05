"""CLI for Phase 2 research operations (no order placement)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from trading_system.services.runtime import ResearchRuntime


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, default=_json_default))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-system",
        description="AI trading research system — Phase 2 (read-only / research)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show mode, providers, and risk limits")

    bars = sub.add_parser("bars", help="Fetch historical OHLCV bars")
    bars.add_argument("symbol")
    bars.add_argument("--timespan", default="D")
    bars.add_argument("--count", type=int, default=30)

    snaps = sub.add_parser("snapshots", help="Fetch quote snapshots")
    snaps.add_argument("symbols", nargs="+")

    acct = sub.add_parser("account", help="Show account balance/positions/open orders")
    acct.add_argument("--account-id", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    runtime = ResearchRuntime()

    if args.command == "status":
        _print(runtime.status())
        return 0
    if args.command == "bars":
        _print(runtime.fetch_bars(args.symbol, timespan=args.timespan, count=args.count))
        return 0
    if args.command == "snapshots":
        _print(runtime.fetch_snapshots(args.symbols))
        return 0
    if args.command == "account":
        _print(runtime.account_overview(args.account_id))
        return 0

    parser.error(f"Unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI for research operations (no order placement)."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime

from trading_system.services.runtime import ResearchRuntime


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, default=_json_default))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-system",
        description="AI trading research system — Phase 10 text report (no order placement)",
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

    regime = sub.add_parser("regime", help="Classify current market regime")
    regime.add_argument("--benchmark", default="SPY")
    regime.add_argument("--lookback", type=int, default=90)

    scan = sub.add_parser("scan", help="Scan universe for ranked opportunities")
    scan.add_argument("--benchmark", default="SPY")
    scan.add_argument("--lookback", type=int, default=90)
    scan.add_argument("--min-score", type=float, default=55.0)
    scan.add_argument("--max-results", type=int, default=10)
    scan.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Optional custom universe (default: liquid large-caps/ETFs)",
    )

    options = sub.add_parser(
        "options",
        help="Analyze option contracts for scanned equity opportunities",
    )
    options.add_argument("--benchmark", default="SPY")
    options.add_argument("--lookback", type=int, default=90)
    options.add_argument("--min-equity-score", type=float, default=55.0)
    options.add_argument("--min-option-score", type=float, default=55.0)
    options.add_argument("--max-results", type=int, default=10)
    options.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Optional custom universe (default: liquid large-caps/ETFs)",
    )

    decide = sub.add_parser(
        "decide",
        help="Emit Decision Packages (technical + options + catalyst + adversarial)",
    )
    decide.add_argument("--benchmark", default="SPY")
    decide.add_argument("--lookback", type=int, default=90)
    decide.add_argument("--min-equity-score", type=float, default=55.0)
    decide.add_argument("--min-option-score", type=float, default=55.0)
    decide.add_argument("--max-results", type=int, default=10)
    decide.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Optional custom universe (default: liquid large-caps/ETFs)",
    )

    backtest = sub.add_parser(
        "backtest",
        help="Cost/slippage-aware long-premium backtest (no look-ahead; RESEARCH only)",
    )
    backtest.add_argument("symbol", nargs="?", default="SPY")
    backtest.add_argument("--timespan", default="D")
    backtest.add_argument("--count", type=int, default=180)
    backtest.add_argument("--lookback", type=int, default=60)
    backtest.add_argument(
        "--split",
        default="oos",
        choices=("oos", "walk_forward"),
        help="oos = chronological 70/30; walk_forward = rolling train/test folds",
    )

    sub.add_parser(
        "journal",
        help="Show the Phase 9 paper ledger (simulated account; not a broker)",
    )

    paper_open = sub.add_parser(
        "paper-open",
        help="PAPER-ONLY: simulate opening a long-premium idea from a Decision Package (no broker order)",
    )
    paper_open.add_argument("symbol")
    paper_open.add_argument("--quantity", type=int, default=1)
    paper_open.add_argument("--benchmark", default="SPY")
    paper_open.add_argument("--lookback", type=int, default=90)
    paper_open.add_argument("--min-equity-score", type=float, default=55.0)
    paper_open.add_argument("--min-option-score", type=float, default=55.0)

    paper_close = sub.add_parser(
        "paper-close",
        help="PAPER-ONLY: simulate closing a paper position at an exit mark (no broker order)",
    )
    paper_close.add_argument("position_id")
    paper_close.add_argument(
        "--exit-mark",
        type=float,
        required=True,
        help="Exit cash premium USD per contract (same units as max_loss_usd / mid×100)",
    )
    paper_close.add_argument("--reason", default="manual_paper_close")

    paper_note = sub.add_parser(
        "paper-note",
        help="PAPER-ONLY: append a journal note without changing the ledger cash",
    )
    paper_note.add_argument("text")
    paper_note.add_argument("--symbol", default="")

    report = sub.add_parser(
        "report",
        help="Phase 10 daily/weekly text report for Grok oversight (no UI, no broker GO)",
    )
    report.add_argument(
        "--weekly",
        action="store_true",
        help="Use a 7-day journal/backtest window instead of the daily snapshot",
    )
    report.add_argument("--benchmark", default="SPY")
    report.add_argument("--lookback", type=int, default=90)
    report.add_argument("--min-equity-score", type=float, default=55.0)
    report.add_argument("--min-option-score", type=float, default=55.0)
    report.add_argument("--max-results", type=int, default=10)
    report.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Optional decide universe (default: liquid large-caps/ETFs)",
    )

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
    if args.command == "regime":
        _print(runtime.market_regime(benchmark=args.benchmark, lookback=args.lookback))
        return 0
    if args.command == "scan":
        _print(
            runtime.scan_opportunities(
                benchmark=args.benchmark,
                lookback=args.lookback,
                min_score=args.min_score,
                max_results=args.max_results,
                symbols=args.symbols,
            )
        )
        return 0
    if args.command == "options":
        _print(
            runtime.analyze_options(
                benchmark=args.benchmark,
                lookback=args.lookback,
                min_equity_score=args.min_equity_score,
                min_option_score=args.min_option_score,
                max_results=args.max_results,
                symbols=args.symbols,
            )
        )
        return 0
    if args.command == "decide":
        _print(
            runtime.decide(
                benchmark=args.benchmark,
                lookback=args.lookback,
                min_equity_score=args.min_equity_score,
                min_option_score=args.min_option_score,
                max_results=args.max_results,
                symbols=args.symbols,
            )
        )
        return 0
    if args.command == "backtest":
        _print(
            runtime.backtest(
                args.symbol,
                timespan=args.timespan,
                count=args.count,
                lookback=args.lookback,
                split=args.split,
            )
        )
        return 0
    if args.command == "journal":
        _print(runtime.journal())
        return 0
    if args.command == "paper-open":
        _print(
            runtime.paper_open(
                args.symbol,
                quantity=args.quantity,
                benchmark=args.benchmark,
                lookback=args.lookback,
                min_equity_score=args.min_equity_score,
                min_option_score=args.min_option_score,
            )
        )
        return 0
    if args.command == "paper-close":
        _print(
            runtime.paper_close(
                args.position_id,
                exit_mark_usd=args.exit_mark,
                reason=args.reason,
            )
        )
        return 0
    if args.command == "paper-note":
        _print(runtime.paper_note(args.text, symbol=args.symbol))
        return 0
    if args.command == "report":
        payload = runtime.research_report(
            weekly=args.weekly,
            benchmark=args.benchmark,
            lookback=args.lookback,
            min_equity_score=args.min_equity_score,
            min_option_score=args.min_option_score,
            max_results=args.max_results,
            symbols=args.symbols,
        )
        print(payload.get("text") or "")
        return 0

    parser.error(f"Unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

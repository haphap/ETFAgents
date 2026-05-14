import argparse
import copy
import json
from pathlib import Path

from dotenv import load_dotenv

from etfagents.backtest import save_backtest_result
from etfagents.default_config import DEFAULT_CONFIG
from etfagents.graph.etf_graph import EtfAgentsGraph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an ETFAgents candidate-pool backtest.")
    parser.add_argument("--tickers", required=True, help="Comma-separated ETF tickers.")
    parser.add_argument("--start-date", required=True, help="Backtest start date (YYYY-MM-DD).")
    parser.add_argument("--end-date", required=True, help="Backtest end date (YYYY-MM-DD).")
    parser.add_argument("--rebalance-interval-days", type=int, default=21)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--execution-timing", default="same_close")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--commission", type=float, default=0.0)
    parser.add_argument("--slippage-perc", type=float, default=0.0)
    parser.add_argument("--cash-buffer-pct", type=float, default=0.0)
    parser.add_argument("--research-depth", type=int, default=1)
    parser.add_argument("--llm-provider", default=DEFAULT_CONFIG["llm_provider"])
    parser.add_argument("--deep-think-llm", default=DEFAULT_CONFIG["deep_think_llm"])
    parser.add_argument("--quick-think-llm", default=DEFAULT_CONFIG["quick_think_llm"])
    parser.add_argument("--output-language", default=DEFAULT_CONFIG["output_language"])
    parser.add_argument("--backend-url", default=None)
    parser.add_argument("--save-path", default=None)
    return parser.parse_args()


def normalize_tickers(raw_text: str) -> list[str]:
    return [ticker.strip().upper() for ticker in raw_text.split(",") if ticker.strip()]


def main() -> None:
    load_dotenv()
    args = parse_args()
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["llm_provider"] = args.llm_provider.lower()
    config["deep_think_llm"] = args.deep_think_llm
    config["quick_think_llm"] = args.quick_think_llm
    config["max_debate_rounds"] = args.research_depth
    config["max_risk_discuss_rounds"] = args.research_depth
    config["output_language"] = args.output_language
    config["backend_url"] = args.backend_url

    graph = EtfAgentsGraph(config=config, debug=False)
    result = graph.backtest_candidate_pool(
        normalize_tickers(args.tickers),
        args.start_date,
        args.end_date,
        rebalance_interval_days=args.rebalance_interval_days,
        top_k=args.top_k,
        execution_timing=args.execution_timing,
        initial_cash=args.initial_cash,
        commission=args.commission,
        slippage_perc=args.slippage_perc,
        cash_buffer_pct=args.cash_buffer_pct,
    )
    if args.save_path:
        save_backtest_result(result, Path(args.save_path))
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

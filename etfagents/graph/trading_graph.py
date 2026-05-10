import logging
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
import copy
from typing import Any, Dict, List, Optional

from langgraph.prebuilt import ToolNode

from etfagents.llm_clients import create_llm_client

from etfagents.default_config import DEFAULT_CONFIG
from etfagents.agents.utils.memory import TradingMemoryLog
from etfagents.agents.utils.state_keys import get_asset_symbol, get_state_value
from etfagents.dataflows.config import set_config
from etfagents.dataflows.interface import is_a_share_ticker

# Import the new abstract tool methods from agent_utils
from etfagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_broker_research,
    get_stock_research,
)

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor

logger = logging.getLogger(__name__)


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    A_SHARE_ONLY_ANALYSTS = ("broker_research", "stock_research")
    DEFAULT_SELECTED_ANALYSTS = GraphSetup.DEFAULT_SELECTED_ANALYSTS
    DEFAULT_GRAPH_CONFIG = DEFAULT_CONFIG
    GRAPH_SETUP_CLASS = GraphSetup

    def __init__(
        self,
        selected_analysts=None,
        debug: bool = False,
        config: Optional[Dict[str, Any]] = None,
        callbacks: Optional[List] = None,
    ) -> None:
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = self._build_config(config)
        self.callbacks = callbacks or []
        analyst_selection = (
            selected_analysts
            if selected_analysts is not None
            else self.DEFAULT_SELECTED_ANALYSTS
        )
        self.requested_analysts = list(analyst_selection)
        self.selected_analysts = list(analyst_selection)

        self._activate_config()
        self._ensure_runtime_dirs()
        self.deep_thinking_llm, self.quick_thinking_llm = self._create_llms()

        self.memory_log = TradingMemoryLog(self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = self.GRAPH_SETUP_CLASS(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
        )

        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100)
        )
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor()

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph
        self.workflow = self.graph_setup.setup_graph(self.selected_analysts)
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _build_config(self, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        template = config if config is not None else self.DEFAULT_GRAPH_CONFIG
        return copy.deepcopy(template)

    def _activate_config(self) -> None:
        set_config(self.config)

    def _ensure_runtime_dirs(self) -> None:
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

    def _create_llms(self):
        llm_kwargs = self._get_provider_kwargs()
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        return deep_client.get_llm(), quick_client.get_llm()

    @classmethod
    def resolve_selected_analysts(
        cls,
        selected_analysts: list[str],
        ticker: str,
    ) -> tuple[list[str], list[str]]:
        ordered = list(dict.fromkeys(selected_analysts))
        if not ticker or is_a_share_ticker(ticker):
            return ordered, []

        compatible: list[str] = []
        skipped: list[str] = []
        for analyst in ordered:
            if analyst in cls.A_SHARE_ONLY_ANALYSTS:
                skipped.append(analyst)
            else:
                compatible.append(analyst)
        return compatible, skipped

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ]
            ),
            "broker_research": ToolNode(
                [
                    # Broker research report tools
                    get_broker_research,
                ]
            ),
            "stock_research": ToolNode(
                [
                    # Individual stock research report tools
                    get_stock_research,
                ]
            ),
        }

    def propagate(self, asset_symbol, trade_date):
        """Run the agent graph for an ETF asset on a specific date."""
        init_agent_state, args, _ = self.prepare_run(asset_symbol, trade_date)

        try:
            if self.debug:
                trace = []
                for chunk in self.graph.stream(init_agent_state, **args):
                    if chunk["messages"]:
                        chunk["messages"][-1].pretty_print()
                    trace.append(chunk)

                final_state = trace[-1]
            else:
                final_state = self.graph.invoke(init_agent_state, **args)

            self.finalize_run(trade_date, final_state)
            return final_state, self.process_signal(
                get_state_value(final_state, "final_allocation_decision", "")
            )
        finally:
            self.close_run()

    def prepare_run(
        self,
        asset_symbol: str,
        trade_date: str,
        callbacks: Optional[List] = None,
    ) -> tuple[Dict[str, Any] | None, Dict[str, Any], bool]:
        """Prepare graph execution and return (input_state, graph_args, resumed)."""
        self.close_run()
        self._activate_config()
        self.ticker = asset_symbol
        trade_date_str = str(trade_date)
        resumed = False
        resolved_analysts, skipped_analysts = self.resolve_selected_analysts(
            self.requested_analysts,
            asset_symbol,
        )
        if not resolved_analysts:
            raise ValueError(
                f"No compatible analysts selected for '{asset_symbol}'. "
                "Industry Research Analyst and Stock Research Analyst are available for A-share tickers only."
            )
        if resolved_analysts != self.selected_analysts:
            if skipped_analysts:
                logger.info(
                    "Skipping A-share-only analysts for %s: %s",
                    asset_symbol,
                    ", ".join(skipped_analysts),
                )
            self.selected_analysts = resolved_analysts
            self.workflow = self.graph_setup.setup_graph(self.selected_analysts)
            self.graph = self.workflow.compile()
        self._resolve_pending_entries(asset_symbol)

        if self.config.get("checkpoint_enabled"):
            step = checkpoint_step(
                self.config["data_cache_dir"], asset_symbol, trade_date_str
            )
            self._checkpointer_ctx = get_checkpointer(
                self.config["data_cache_dir"], asset_symbol
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)
            resumed = step is not None
            if resumed:
                logger.info(
                    "Resuming from step %d for %s on %s",
                    step,
                    asset_symbol,
                    trade_date_str,
                )
            else:
                logger.info("Starting fresh for %s on %s", asset_symbol, trade_date_str)

        init_agent_state = None
        if not resumed:
            init_agent_state = self.propagator.create_initial_state(
                asset_symbol,
                trade_date,
                past_context=self.memory_log.get_past_context(asset_symbol),
            )

        args = self.propagator.get_graph_args(callbacks=callbacks)
        if self.config.get("checkpoint_enabled"):
            args.setdefault("config", {}).setdefault("configurable", {})[
                "thread_id"
            ] = thread_id(asset_symbol, trade_date_str)

        return init_agent_state, args, resumed

    def finalize_run(self, trade_date, final_state: Dict[str, Any]) -> None:
        """Persist a successful run and clear its checkpoint."""
        self.curr_state = final_state
        self._log_state(trade_date, final_state)
        self.memory_log.store_decision(
            get_asset_symbol(final_state),
            str(trade_date),
            get_state_value(final_state, "final_allocation_decision", ""),
        )

        if self.config.get("checkpoint_enabled") and self.ticker:
            clear_checkpoint(
                self.config["data_cache_dir"], self.ticker, str(trade_date)
            )

    def close_run(self) -> None:
        """Close any active checkpoint context and restore the default graph."""
        if self._checkpointer_ctx is None:
            return

        try:
            self._checkpointer_ctx.__exit__(None, None, None)
        except Exception as exc:
            logger.warning("Checkpointer teardown error: %s", exc)
        finally:
            self._checkpointer_ctx = None
            self.graph = self.workflow.compile()

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        investment_state = get_state_value(final_state, "investment_debate_state", {}) or {}
        risk_state = get_state_value(final_state, "risk_debate_state", {}) or {}
        self.log_states_dict[str(trade_date)] = {
            "asset_of_interest": get_asset_symbol(final_state),
            "trade_date": get_state_value(final_state, "trade_date", str(trade_date)),
            "market_flow_report": get_state_value(final_state, "market_flow_report", ""),
            "catalyst_sentiment_report": get_state_value(final_state, "catalyst_sentiment_report", ""),
            "macro_regime_report": get_state_value(final_state, "macro_regime_report", ""),
            "meso_commodity_report": get_state_value(final_state, "meso_commodity_report", ""),
            "investment_debate_state": {
                "bull_history": investment_state.get("bull_history", ""),
                "bear_history": investment_state.get("bear_history", ""),
                "history": investment_state.get("history", ""),
                "current_response": investment_state.get("current_response", ""),
                "judge_decision": investment_state.get("judge_decision", ""),
            },
            "trader_allocation_plan": get_state_value(final_state, "trader_allocation_plan", ""),
            "risk_debate_state": {
                "aggressive_history": risk_state.get("aggressive_history", ""),
                "conservative_history": risk_state.get("conservative_history", ""),
                "neutral_history": risk_state.get("neutral_history", ""),
                "history": risk_state.get("history", ""),
                "judge_decision": risk_state.get("judge_decision", ""),
            },
            "holdings_industry_report": get_state_value(final_state, "holdings_industry_report", ""),
            "top_holdings_report": get_state_value(final_state, "top_holdings_report", ""),
            "research_allocation_plan": get_state_value(final_state, "research_allocation_plan", ""),
            "final_allocation_decision": get_state_value(final_state, "final_allocation_decision", ""),
        }

        # Save to file
        directory = (
            Path(self.config["results_dir"])
            / self._safe_ticker_for_path(self.ticker or get_asset_symbol(final_state))
            / "ETFAgentsStrategy_logs"
        )
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def _fetch_returns(self, ticker: str, trade_date: str, holding_days: int = 5):
        """Fetch stock and benchmark returns after a trade date."""
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance is not installed; skipping deferred reflection updates.")
            return None, None, None

        try:
            from etfagents.dataflows.y_finance import _to_yfinance_symbol

            start = datetime.strptime(str(trade_date), "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)
            benchmark_ticker = self._resolve_benchmark_ticker(ticker)

            stock_history = yf.Ticker(_to_yfinance_symbol(ticker)).history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=False,
            )
            benchmark_history = yf.Ticker(_to_yfinance_symbol(benchmark_ticker)).history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                auto_adjust=False,
            )
        except Exception as exc:
            logger.warning("Failed to fetch returns data: %s", exc)
            return None, None, None

        if len(stock_history) < 2 or len(benchmark_history) < 2:
            return None, None, None

        end_idx = min(holding_days, len(stock_history) - 1, len(benchmark_history) - 1)
        stock_raw = (
            float(stock_history["Close"].iloc[end_idx]) / float(stock_history["Close"].iloc[0])
        ) - 1.0
        benchmark_raw = (
            float(benchmark_history["Close"].iloc[end_idx]) / float(benchmark_history["Close"].iloc[0])
        ) - 1.0
        return stock_raw, stock_raw - benchmark_raw, end_idx

    def _resolve_benchmark_ticker(self, ticker: str) -> str:
        configured = getattr(self, "config", {}).get("benchmark_ticker")
        if configured:
            return configured

        if "." in ticker:
            suffix = ticker.rsplit(".", 1)[-1].upper()
            if suffix in {"SH", "SZ", "BJ", "SS", "SSE", "SZSE", "BSE"}:
                return "510300.SH"
            if suffix in {"HK", "HKG", "SEHK"}:
                return "2800.HK"
        return "SPY"

    @staticmethod
    def _safe_ticker_for_path(ticker: str) -> str:
        return str(ticker).replace("/", "_").replace("\\", "_")

    def _resolve_pending_entries(self, ticker: str) -> None:
        """Resolve any past pending entries for this ticker when returns are now available."""
        updates = []
        for entry in self.memory_log.get_pending_entries():
            if entry["ticker"] != ticker:
                continue
            raw_return, alpha_return, holding_days = self._fetch_returns(
                entry["ticker"], entry["date"]
            )
            if raw_return is None or alpha_return is None or holding_days is None:
                continue
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry["decision"],
                raw_return=raw_return,
                alpha_return=alpha_return,
            )
            updates.append(
                {
                    "ticker": entry["ticker"],
                    "trade_date": entry["date"],
                    "raw_return": raw_return,
                    "alpha_return": alpha_return,
                    "holding_days": holding_days,
                    "reflection": reflection,
                }
            )

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def reflect_and_remember(self, returns_losses):
        raise RuntimeError(
            "Deferred reflections are automatic now. Re-run the ticker after return data is available to resolve pending memory-log entries."
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)

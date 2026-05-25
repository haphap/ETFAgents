"""Research analysis screens: input, config modal, and run screen."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Select,
    Static,
)

from cli.tui.services import (
    ANALYST_KEYS,
    AnalysisConfig,
    AnalysisEvent,
    AnalysisRunner,
    DebateProgress,
    IdRegistry,
    RESEARCH_DEPTH_REQUIREMENTS,
    ReportRepository,
    SECTION_BY_ID,
    SECTION_DEFINITIONS,
    SectionDone,
    SectionDef,
    TickerCancelled,
    TickerDone,
    TickerFailed,
    TickerStarted,
    section_definitions_for,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

LLM_PROVIDER_OPTIONS: list[tuple[str, str, str | None]] = [
    ("OpenAI", "openai", "https://api.openai.com/v1"),
    ("Google", "google", "https://generativelanguage.googleapis.com/v1"),
    ("Anthropic", "anthropic", "https://api.anthropic.com/"),
    ("DeepSeek", "deepseek", "https://api.deepseek.com"),
    ("xAI", "xai", "https://api.x.ai/v1"),
    ("MiniMax", "minimax", "https://api.minimax.chat/v1"),
    ("OpenRouter", "openrouter", "https://openrouter.ai/api/v1"),
    ("Ollama / llama.cpp", "ollama", "http://localhost:4000/v1"),
    ("vLLM", "vllm", "http://127.0.0.1:8020/v1"),
]

LLM_PROVIDER_ENDPOINTS = {
    provider: endpoint for _, provider, endpoint in LLM_PROVIDER_OPTIONS
}

# Sections that complete on first SectionDone (non-debate, single-shot)
_INSTANT_DONE_SECTIONS = set(ANALYST_KEYS) | {"research", "trader", "portfolio_manager"}


def _depth_option_label(depth_name: str) -> str:
    req = RESEARCH_DEPTH_REQUIREMENTS.get(depth_name, {})
    debate_rounds = req.get("debate_rounds", "?")
    risk_rounds = req.get("risk_rounds", "?")
    return f"{depth_name} (debate×{debate_rounds}, risk×{risk_rounds})"


def _model_select_options(provider: str, mode: str) -> list[tuple[str, str]]:
    from etfagents.llm_clients.model_catalog import get_model_options

    options = get_model_options(provider, mode)
    if options:
        return options
    return [("Custom / provider default", "custom")]


def _safe_call_from_thread(screen: Any, callback: Any, *args: Any) -> None:
    """call_from_thread that silently exits if the app is shutting down."""
    try:
        if not getattr(screen.app, "_running", False):
            return
        screen.app.call_from_thread(callback, *args)
    except (RuntimeError, EOFError):
        pass


def _format_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _format_detail_text(detail: dict) -> str:
    lines: list[str] = []
    name = detail.get("name") or detail.get("ticker", "")
    close = detail.get("close")
    pct = detail.get("pct_chg")
    if close is not None:
        price_str = f"{close:.3f}"
        if pct is not None:
            sign = "+" if pct >= 0 else ""
            price_str += f" {sign}{pct:.2f}%"
        lines.append(f"{name} {price_str}" if name else price_str)
    elif name:
        lines.append(name)

    nav = detail.get("unit_nav")
    if nav is not None:
        pd_bps = detail.get("premium_discount_bps")
        nav_line = f"NAV {nav:.4f}"
        if pd_bps is not None:
            nav_line += f" {pd_bps:+.0f}bp"
        lines.append(nav_line)

    share = detail.get("fund_share")
    if share is not None:
        share_line = f"规模 {share / 1e8:.0f}亿"
        sc = detail.get("share_change_pct")
        if sc is not None:
            share_line += f" {sc:+.1f}%"
        lines.append(share_line)

    holdings = detail.get("holdings") or []
    for h in holdings[:3]:
        w = h.get("weight_pct")
        w_str = f"{w:.1f}%" if w is not None else "?"
        lines.append(f"  {h.get('name', '?')} {w_str}")

    return "\n".join(lines) if lines else "无数据"


def _build_analysis_runner(cfg: AnalysisConfig) -> AnalysisRunner:
    from etfagents.default_config import DEFAULT_CONFIG
    import copy
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["llm_provider"] = cfg.llm_provider
    config["backend_url"] = cfg.backend_url or LLM_PROVIDER_ENDPOINTS.get(cfg.llm_provider)
    config["output_language"] = cfg.output_language
    depth_req = RESEARCH_DEPTH_REQUIREMENTS.get(cfg.depth_name, {})
    if depth_req:
        config["max_debate_rounds"] = depth_req.get("debate_rounds", 1)
        config["max_risk_discuss_rounds"] = depth_req.get("risk_rounds", 1)
    if cfg.quick_model:
        config["quick_think_llm"] = cfg.quick_model
    if cfg.deep_model:
        config["deep_think_llm"] = cfg.deep_model
    if not cfg.quick_model or not cfg.deep_model:
        _apply_provider_model_defaults(
            config,
            cfg,
            fill_quick=not cfg.quick_model,
            fill_deep=not cfg.deep_model,
        )
    return AnalysisRunner(config=config)


def _apply_provider_model_defaults(
    config: dict[str, Any],
    cfg: AnalysisConfig,
    *,
    fill_quick: bool = True,
    fill_deep: bool = True,
) -> None:
    """Keep TUI provider selection from reusing OpenAI default model names."""
    from etfagents.llm_clients.model_catalog import get_model_options, recommend_models

    provider = cfg.llm_provider.lower()
    rec = recommend_models(cfg.depth_name, provider)
    quick_model = rec.get("quick_model")
    deep_model = rec.get("deep_model")

    if not quick_model:
        quick_options = get_model_options(provider, "quick")
        quick_model = quick_options[0][1] if quick_options else None
    if not deep_model:
        deep_options = get_model_options(provider, "deep")
        deep_model = deep_options[0][1] if deep_options else None

    if fill_quick and quick_model:
        config["quick_think_llm"] = quick_model
    if fill_deep and deep_model:
        config["deep_think_llm"] = deep_model


def _debate_progress_bar(current: int, total: int) -> str:
    """Build ▓▓░ progress bar string."""
    if total <= 0:
        return ""
    filled = min(current, total)
    return "▓" * filled + "░" * (total - filled) + f" {current}/{total}"


# ---------------------------------------------------------------------------
# AnalysisConfigModal
# ---------------------------------------------------------------------------

class AnalysisConfigModal(ModalScreen[AnalysisConfig | None]):
    """Modal to configure analysis parameters before running."""

    DEFAULT_CSS = """
    AnalysisConfigModal { align: center middle; }
    #acm_container { width: 88; height: auto; max-height: 50; border: solid $accent; background: $surface; padding: 1 2; }
    #acm_container .acm-row { height: auto; margin: 0; }
    #acm_container .acm-col { width: 1fr; height: auto; margin-right: 1; }
    #acm_container Static { height: 1; margin: 0; }
    #acm_container Checkbox { height: 1; margin: 0; }
    #acm_container Select { margin: 0 0 1 0; }
    #acm_container .analyst-grid { layout: grid; grid-size: 3 2; grid-gutter: 0 1; height: auto; }
    #acm_container .text-action { margin: 0 1 0 0; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="acm_container"):
            yield Static("分析配置", classes="pane-title")
            yield Static("选择分析师:")
            with Vertical(classes="analyst-grid"):
                for defn in SECTION_DEFINITIONS:
                    if defn.team == "分析师":
                        yield Checkbox(
                            defn.title,
                            value=True,
                            id=f"acm_cb_{defn.section_id}",
                            compact=True,
                        )
            with Horizontal(classes="acm-row"):
                with Vertical(classes="acm-col"):
                    yield Static("研究深度:")
                    depth_options = [
                        (_depth_option_label(name), name) for name in RESEARCH_DEPTH_REQUIREMENTS
                    ]
                    yield Select(depth_options, value="标准", id="acm_depth")
                with Vertical(classes="acm-col"):
                    yield Static("输出语言:")
                    lang_options = [("中文", "Chinese"), ("English", "English")]
                    yield Select(lang_options, value="Chinese", id="acm_language")
            yield Static("分析日期:")
            yield Input(
                value=datetime.now().date().isoformat(),
                placeholder="YYYY-MM-DD",
                id="acm_analysis_date",
            )
            with Horizontal(classes="acm-row"):
                with Vertical(classes="acm-col"):
                    yield Static("LLM提供商:")
                    provider_options = [
                        (display, provider) for display, provider, _ in LLM_PROVIDER_OPTIONS
                    ]
                    yield Select(provider_options, value="openai", id="acm_provider")
                with Vertical(classes="acm-col"):
                    yield Static("快速模型:")
                    quick_options = _model_select_options("openai", "quick")
                    yield Select(quick_options, value=quick_options[0][1], id="acm_quick_model")
            yield Static("深度模型:")
            deep_options = _model_select_options("openai", "deep")
            yield Select(deep_options, value=deep_options[0][1], id="acm_deep_model")
            yield Static("", id="acm_error", classes="error-text")
            with Horizontal(classes="acm-row"):
                yield Button("› Confirm", id="btn_acm_ok", classes="text-action")
                yield Button("Cancel", id="btn_acm_cancel", classes="text-action muted")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_acm_ok":
            selected = [
                k for k in ANALYST_KEYS
                if self._checkbox_checked(f"acm_cb_{k}")
            ]
            depth = self.query_one("#acm_depth", Select).value
            provider = self.query_one("#acm_provider", Select).value
            quick_model = self.query_one("#acm_quick_model", Select).value
            deep_model = self.query_one("#acm_deep_model", Select).value
            language = self.query_one("#acm_language", Select).value
            analysis_date = self.query_one("#acm_analysis_date", Input).value.strip()
            if analysis_date:
                try:
                    datetime.strptime(analysis_date, "%Y-%m-%d")
                except ValueError:
                    self.query_one("#acm_error", Static).update("分析日期必须是 YYYY-MM-DD 格式。")
                    return
            self.query_one("#acm_error", Static).update("")
            self.dismiss(AnalysisConfig(
                selected_analysts=selected or list(ANALYST_KEYS),
                analysis_date=analysis_date or None,
                depth_name=str(depth) if depth != Select.BLANK else "标准",
                llm_provider=str(provider) if provider != Select.BLANK else "openai",
                backend_url=LLM_PROVIDER_ENDPOINTS.get(str(provider)),
                quick_model=str(quick_model) if quick_model != Select.BLANK else None,
                deep_model=str(deep_model) if deep_model != Select.BLANK else None,
                output_language=str(language) if language != Select.BLANK else "Chinese",
            ))
        elif event.button.id == "btn_acm_cancel":
            self.dismiss(None)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id != "acm_provider":
            return
        provider = str(event.value) if event.value != Select.BLANK else "openai"
        quick_options = _model_select_options(provider, "quick")
        deep_options = _model_select_options(provider, "deep")
        quick_select = self.query_one("#acm_quick_model", Select)
        deep_select = self.query_one("#acm_deep_model", Select)
        quick_select.set_options(quick_options)
        quick_select.value = quick_options[0][1]
        deep_select.set_options(deep_options)
        deep_select.value = deep_options[0][1]

    def _checkbox_checked(self, widget_id: str) -> bool:
        try:
            return self.query_one(f"#{widget_id}", Checkbox).value
        except Exception:
            return False


# ---------------------------------------------------------------------------
# ResearchAnalysisScreen (input)
# ---------------------------------------------------------------------------

class ResearchAnalysisScreen(Screen):
    """Collect ETF analysis input, then open the dedicated run screen."""

    def __init__(self, runner: AnalysisRunner | None = None, repository: ReportRepository | None = None):
        super().__init__()
        self.runner = runner
        self.repository = repository or ReportRepository()
        self._analysis_config: AnalysisConfig | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("Create Run", classes="pane-title")
                yield Static("ETF tickers:")
                yield Input(placeholder="510300.SH,159915.SZ", id="ra_ticker_input")
                yield Button("› Start Analysis", id="btn_ra_start", classes="text-action")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("Run Brief", classes="pane-title")
                    yield Markdown(
                        "1. Enter ETF tickers\n"
                        "2. Select analysts, provider, models\n"
                        "3. Track each team output in board",
                        id="ra_intro",
                    )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ra_start":
            tickers = self._read_tickers()
            if not tickers:
                self.query_one("#ra_intro", Markdown).update("请输入至少一个 ETF 代码。")
                return
            self.app.push_screen(AnalysisConfigModal(), self._on_config_result)

    def _read_tickers(self) -> list[str]:
        tickers_str = self.query_one("#ra_ticker_input", Input).value.strip()
        return [t.strip().upper() for t in tickers_str.split(",") if t.strip()]

    def _on_config_result(self, config: AnalysisConfig | None) -> None:
        if config is None:
            return
        self._analysis_config = config
        self.app.push_screen(
            AnalysisRunScreen(
                tickers=self._read_tickers(),
                config=config,
                runner=self.runner,
                repository=self.repository,
            )
        )

    def _build_runner(self) -> AnalysisRunner:
        cfg = self._analysis_config
        if cfg is None:
            return AnalysisRunner()
        return _build_analysis_runner(cfg)


# ---------------------------------------------------------------------------
# AnalysisRunScreen — 4-column kanban board
# ---------------------------------------------------------------------------

class AnalysisRunScreen(Screen):
    """Run ETF analysis with a 4-column kanban board.

    Left pane: ETF queue/status + config summary.
    Right-top: board columns (分析团队 | 研究 | 风险 | 决策).
    Right-bottom: overall progress or selected section report.
    """

    def __init__(
        self,
        tickers: list[str],
        config: AnalysisConfig,
        runner: AnalysisRunner | None = None,
        repository: ReportRepository | None = None,
    ):
        super().__init__()
        self.tickers = tickers
        self._analysis_config = config
        self.runner = runner
        self._active_runner: AnalysisRunner | None = None
        self.repository = repository or ReportRepository()
        self.ticker_ids = IdRegistry("rtk")
        self.section_contents: dict[tuple[str, str], str] = {}
        self.section_status: dict[tuple[str, str], bool] = {}
        # Board state: (ticker, section_id) -> "pending" | "running" | "done" | "failed"
        self._board_state: dict[tuple[str, str], str] = {}
        # Debate progress: (ticker, section_id) -> (current_round, max_rounds)
        self._debate_rounds: dict[tuple[str, str], tuple[int, int]] = {}
        self._active_column: str = ""
        self.current_ticker: str | None = None
        self.current_section: str | None = None
        self._analysis_thread: threading.Thread | None = None
        self.progress_lines: list[str] = []
        self._started_at: float | None = None
        self._last_stats: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        defs = self._section_definitions()
        analyst_defs = [d for d in defs if d.team == "分析师"]
        research_defs = [d for d in defs if d.team == "研究"]
        trader_defs = [d for d in defs if d.section_id == "trader"]
        risk_defs = trader_defs + [d for d in defs if d.team == "风险"]
        pm_defs = [d for d in defs if d.team == "决策"]
        decision_defs = pm_defs

        yield Header(show_clock=False)
        with Vertical(classes="run-layout"):
            with Horizontal(classes="screen-body run-main"):
                with Vertical(classes="left-pane"):
                    yield Static("ETF Queue", classes="pane-title")
                    yield Static(self._config_summary(), id="ra_run_config")
                    yield Static("", id="ra_etf_detail")
                    yield Button("Cancel", id="btn_ra_cancel", classes="text-action warning-text", disabled=True)
                    yield ListView(id="ra_queue")
                with Vertical(classes="right-pane"):
                    # Board (right-top)
                    with Horizontal(classes="right-top", id="ra_sections"):
                        # Column 1: Analysts (wide)
                        with Vertical(classes="board-column column-inactive board-col-wide", id="col_analysts"):
                            yield Static(
                                f"分析团队 (0/{len(analyst_defs)})",
                                id="col_analysts_header",
                                classes="column-header",
                            )
                            for i in range(0, len(analyst_defs), 2):
                                with Horizontal(classes="board-row"):
                                    yield Button(
                                        f"○ {analyst_defs[i].title}",
                                        id=f"rsec-{analyst_defs[i].section_id}",
                                        classes="board-item",
                                    )
                                    if i + 1 < len(analyst_defs):
                                        yield Button(
                                            f"○ {analyst_defs[i + 1].title}",
                                            id=f"rsec-{analyst_defs[i + 1].section_id}",
                                            classes="board-item",
                                        )
                        # Column 2: Research
                        if research_defs:
                            with Vertical(classes="board-column column-inactive", id="col_research"):
                                yield Static(
                                    f"研究 (0/{len(research_defs)})",
                                    id="col_research_header",
                                    classes="column-header",
                                )
                                for defn in research_defs:
                                    yield Button(
                                        f"○ {defn.title}",
                                        id=f"rsec-{defn.section_id}",
                                        classes="board-item",
                                    )
                                yield Static("", id="research_progress", classes="debate-progress")
                        # Column 3: Risk
                        if risk_defs:
                            with Vertical(classes="board-column column-inactive", id="col_risk"):
                                yield Static(
                                    f"风险 (0/{len(risk_defs)})",
                                    id="col_risk_header",
                                    classes="column-header",
                                )
                                for defn in risk_defs:
                                    yield Button(
                                        f"○ {defn.title}",
                                        id=f"rsec-{defn.section_id}",
                                        classes="board-item",
                                    )
                                yield Static("", id="risk_progress", classes="debate-progress")
                        # Column 4: Decision
                        with Vertical(classes="board-column column-inactive", id="col_decision"):
                            yield Static(
                                f"决策 (0/{len(decision_defs)})",
                                id="col_decision_header",
                                classes="column-header",
                            )
                            for defn in decision_defs:
                                yield Button(
                                    f"○ {defn.title}",
                                    id=f"rsec-{defn.section_id}",
                                    classes="board-item",
                                )
                    # Report body (right-bottom)
                    with Vertical(classes="right-bottom"):
                        yield Static("整体进度", id="ra_body_title", classes="pane-title")
                        with ScrollableContainer(id="ra_body_scroll"):
                            yield Markdown("准备开始分析。", id="ra_body")
            with Horizontal(classes="stats-bar"):
                yield Static(self._stats_progress_text(), id="stats_progress", classes="stats-seg-accent")
                yield Static(self._stats_resources_text(), id="stats_resources", classes="stats-seg-panel")
                yield Static(self._stats_reports_text(), id="stats_reports", classes="stats-seg-success")
                yield Static(self._stats_right_text(), id="stats_right", classes="stats-seg-surface")

    def on_mount(self) -> None:
        self._start_analysis()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn_ra_cancel":
            self._cancel_analysis()
        elif btn_id.startswith("rsec-"):
            section_id = btn_id[5:]
            self.current_section = section_id
            self._refresh_body()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id in self.ticker_ids:
            self.current_ticker = self.ticker_ids.resolve(item_id)
            self._refresh_body()
            self._load_etf_detail(self.current_ticker)

    # --- Analysis lifecycle ---

    def _start_analysis(self) -> None:
        if not self.tickers:
            return

        self.section_contents.clear()
        self.section_status.clear()
        self._board_state.clear()
        self._debate_rounds.clear()
        self._active_column = ""
        self.ticker_ids.clear()
        self.progress_lines.clear()
        self.current_ticker = self.tickers[0]
        self.current_section = None
        self._started_at = time.time()

        queue = self.query_one("#ra_queue", ListView)
        queue.clear()

        runner = self.runner or self._build_runner()
        self._active_runner = runner
        self.query_one("#btn_ra_cancel", Button).disabled = False
        self._append_progress(f"开始分析 {', '.join(self.tickers)}")
        self._refresh_stats_bar()
        self._analysis_thread = threading.Thread(
            target=self._run_analysis,
            args=(runner, self.tickers),
            daemon=True,
            name="etfagents-tui-analysis",
        )
        self._analysis_thread.start()

    def _build_runner(self) -> AnalysisRunner:
        return _build_analysis_runner(self._analysis_config)

    def _config_summary(self) -> str:
        cfg = self._analysis_config
        depth = _depth_option_label(cfg.depth_name)
        return (
            f"{cfg.analysis_date or 'today'} · {depth} · {cfg.llm_provider}\n"
            f"quick:{cfg.quick_model or 'default'} · deep:{cfg.deep_model or 'default'}"
        )

    def _cancel_analysis(self) -> None:
        if self._active_runner:
            self._active_runner.request_cancel()
        self.query_one("#btn_ra_cancel", Button).disabled = True

    def _load_etf_detail(self, ticker: str) -> None:
        try:
            self.query_one("#ra_etf_detail", Static).update("加载中...")
        except Exception:
            pass

        def _worker() -> None:
            try:
                from etfagents.detail import get_etf_detail
                detail = get_etf_detail(ticker)
                text = _format_detail_text(detail)
            except Exception:
                text = "详情加载失败"
            _safe_call_from_thread(self, self._update_etf_detail, text)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_etf_detail(self, text: str) -> None:
        try:
            self.query_one("#ra_etf_detail", Static).update(text)
        except Exception:
            pass

    def on_unmount(self) -> None:
        if self._active_runner:
            self._active_runner.request_cancel()

    def _run_analysis(self, runner: AnalysisRunner, tickers: list[str]) -> None:
        """Worker thread: stream analysis events."""
        cfg = self._analysis_config
        selected = cfg.selected_analysts if cfg else None
        analysis_date = cfg.analysis_date if cfg else None
        try:
            for event in runner.run_queue(
                tickers,
                analysis_date=analysis_date,
                selected_analysts=selected,
            ):
                _safe_call_from_thread(self, self._apply_event, event)
        except Exception as exc:
            _safe_call_from_thread(self, self._show_error, str(exc))
        finally:
            _safe_call_from_thread(self, self._on_analysis_done)

    def _on_analysis_done(self) -> None:
        self._last_stats = self._read_runner_stats()
        self._active_runner = None
        self._append_progress("分析线程已结束。")
        self._refresh_stats_bar()
        try:
            self.query_one("#btn_ra_cancel", Button).disabled = True
        except Exception:
            pass

    # --- Event dispatch ---

    def _apply_event(self, event: AnalysisEvent) -> None:
        """UI thread: handle event."""
        if isinstance(event, TickerStarted):
            self._handle_ticker_started(event)
        elif isinstance(event, SectionDone):
            self._handle_section_done(event)
        elif isinstance(event, DebateProgress):
            self._handle_debate_progress(event)
        elif isinstance(event, TickerDone):
            self._handle_ticker_done(event)
        elif isinstance(event, TickerFailed):
            self._handle_ticker_failed(event)
        elif isinstance(event, TickerCancelled):
            self._handle_ticker_cancelled(event)
        self._refresh_stats_bar()

    def _handle_ticker_started(self, event: TickerStarted) -> None:
        ticker_id = self.ticker_ids.register(event.ticker)
        queue = self.query_one("#ra_queue", ListView)
        queue.append(ListItem(Label(f"⏳ {event.ticker}"), id=ticker_id))
        self._append_progress(f"{event.ticker}: 开始运行，共 {event.total_sections} 个团队章节")
        if self.current_ticker is None:
            self.current_ticker = event.ticker
        if self.current_ticker == event.ticker:
            self._load_etf_detail(event.ticker)

    def _handle_section_done(self, event: SectionDone) -> None:
        self.section_contents[(event.ticker, event.section_id)] = event.content
        self.section_status[(event.ticker, event.section_id)] = True

        # Update board state
        if event.section_id in _INSTANT_DONE_SECTIONS:
            self._board_state[(event.ticker, event.section_id)] = "done"
        else:
            cur = self._board_state.get((event.ticker, event.section_id))
            if cur != "done":
                self._board_state[(event.ticker, event.section_id)] = "running"

        title = SECTION_BY_ID.get(event.section_id).title if event.section_id in SECTION_BY_ID else event.section_id
        self._append_progress(f"{event.ticker}: {title} 已更新 ({event.completed}/{event.total})")
        self._set_active_column(event.section_id)
        self._refresh_board()
        self._refresh_body()

    def _handle_debate_progress(self, event: DebateProgress) -> None:
        self._debate_rounds[(event.ticker, event.section_id)] = (
            event.current_round,
            event.max_rounds,
        )

        # Update debate board state
        if event.section_id in ("research_debate", "risk_debate"):
            key = (event.ticker, event.section_id)
            if event.current_round >= event.max_rounds:
                self._board_state[key] = "done"
            elif event.current_round > 0:
                self._board_state[key] = "running"

        self._refresh_board()

    def _handle_ticker_done(self, event: TickerDone) -> None:
        ticker_id = self.ticker_ids.register(event.ticker)
        rating_str = f" {event.rating}" if event.rating else ""
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            label = item.query_one(Label)
            label.update(f"✓ {event.ticker}{rating_str}")
        except Exception:
            pass

        # Mark all sections as done for this ticker
        for defn in self._section_definitions():
            self._board_state[(event.ticker, defn.section_id)] = "done"

        self.repository.invalidate()
        self._append_progress(f"{event.ticker}: 分析完成{rating_str}")
        self._refresh_board()

    def _handle_ticker_failed(self, event: TickerFailed) -> None:
        ticker_id = self.ticker_ids.register(event.ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            label = item.query_one(Label)
            label.update(f"✗ {event.ticker}")
        except Exception:
            pass

        # Mark all unfinished sections as failed
        for defn in self._section_definitions():
            key = (event.ticker, defn.section_id)
            if self._board_state.get(key, "pending") != "done":
                self._board_state[key] = "failed"

        self._append_progress(f"{event.ticker}: 分析失败 - {event.error}")
        self._refresh_board()

    def _handle_ticker_cancelled(self, event: TickerCancelled) -> None:
        ticker_id = self.ticker_ids.register(event.ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            label = item.query_one(Label)
            label.update(f"⊘ {event.ticker}")
        except Exception:
            pass
        self._append_progress(f"{event.ticker}: 已取消")

    # --- Board refresh ---

    def _set_active_column(self, section_id: str) -> None:
        if section_id in ANALYST_KEYS:
            self._active_column = "col_analysts"
        elif section_id in ("research_debate", "research"):
            self._active_column = "col_research"
        elif section_id in ("trader", "risk_debate"):
            self._active_column = "col_risk"
        elif section_id == "portfolio_manager":
            self._active_column = "col_decision"

    def _refresh_board(self) -> None:
        """Update board item labels, column headers, progress bars, and active column."""
        ticker = self.current_ticker
        if not ticker:
            return

        defs = self._section_definitions()
        analyst_defs = [d for d in defs if d.team == "分析师"]
        research_defs = [d for d in defs if d.team == "研究"]
        trader_defs = [d for d in defs if d.section_id == "trader"]
        risk_defs = trader_defs + [d for d in defs if d.team == "风险"]
        pm_defs = [d for d in defs if d.team == "决策"]

        _STATUS_ICONS = {"pending": "○", "running": "▒", "done": "✔", "failed": "✘"}

        # Update each board item
        for defn in defs:
            state = self._board_state.get((ticker, defn.section_id), "pending")
            icon = _STATUS_ICONS.get(state, "○")
            try:
                btn = self.query_one(f"#rsec-{defn.section_id}", Button)
                btn.label = f"{icon} {defn.title}"
                btn.remove_class("board-item-done", "board-item-failed")
                if state == "done":
                    btn.add_class("board-item-done")
                elif state == "failed":
                    btn.add_class("board-item-failed")
            except Exception:
                pass

        # Column headers with counts
        def _done_count(section_ids: list[str]) -> int:
            return sum(
                1 for sid in section_ids
                if self._board_state.get((ticker, sid)) == "done"
            )

        analyst_ids = [d.section_id for d in analyst_defs]
        try:
            self.query_one("#col_analysts_header", Static).update(
                f"分析团队 ({_done_count(analyst_ids)}/{len(analyst_ids)})"
            )
        except Exception:
            pass

        if research_defs:
            try:
                self.query_one("#col_research_header", Static).update(
                    f"研究 ({_done_count([d.section_id for d in research_defs])}/{len(research_defs)})"
                )
            except Exception:
                pass

        if risk_defs:
            try:
                self.query_one("#col_risk_header", Static).update(
                    f"风险 ({_done_count([d.section_id for d in risk_defs])}/{len(risk_defs)})"
                )
            except Exception:
                pass

        decision_ids = [d.section_id for d in pm_defs]
        try:
            self.query_one("#col_decision_header", Static).update(
                f"决策 ({_done_count(decision_ids)}/{len(decision_ids)})"
            )
        except Exception:
            pass

        # Debate progress bars
        for prog_id, debate_key in [("research_progress", "research_debate"), ("risk_progress", "risk_debate")]:
            rounds = self._debate_rounds.get((ticker, debate_key))
            try:
                widget = self.query_one(f"#{prog_id}", Static)
                if rounds:
                    widget.update(_debate_progress_bar(rounds[0], rounds[1]))
                else:
                    widget.update("")
            except Exception:
                pass

        # Active column highlighting
        col_ids = ["col_analysts", "col_research", "col_risk", "col_decision"]
        for col_id in col_ids:
            try:
                col = self.query_one(f"#{col_id}")
                if col_id == self._active_column:
                    col.remove_class("column-inactive")
                    col.add_class("column-active")
                else:
                    col.remove_class("column-active")
                    col.add_class("column-inactive")
            except Exception:
                pass

    # --- Body refresh ---

    def _refresh_body(self) -> None:
        if not self.current_ticker:
            self.query_one("#ra_body", Markdown).update("请选择一个 ticker。")
            return
        if self.current_section is None:
            self.query_one("#ra_body_title", Static).update("整体进度")
            self.query_one("#ra_body", Markdown).update(self._progress_markdown())
            return

        # risk_debate is synthetic — show PM content or status
        if self.current_section == "risk_debate":
            self.query_one("#ra_body_title", Static).update("风险辩论")
            content = self.section_contents.get((self.current_ticker, "portfolio_manager"))
            if content:
                self.query_one("#ra_body", Markdown).update(content)
            else:
                rounds = self._debate_rounds.get((self.current_ticker, "risk_debate"))
                if rounds:
                    self.query_one("#ra_body", Markdown).update(
                        f"风险辩论进行中 {_debate_progress_bar(rounds[0], rounds[1])}"
                    )
                else:
                    self.query_one("#ra_body", Markdown).update("风险辩论尚未开始。")
            return

        content = self.section_contents.get((self.current_ticker, self.current_section))
        title = SECTION_BY_ID.get(self.current_section).title if self.current_section in SECTION_BY_ID else self.current_section
        self.query_one("#ra_body_title", Static).update(str(title))
        if content:
            self.query_one("#ra_body", Markdown).update(content)
        else:
            self.query_one("#ra_body", Markdown).update("该团队尚未产出报告，分析仍在进行或尚未开始。")

    def _show_error(self, error: str) -> None:
        self._append_progress(f"分析出错：{error}")

    def _append_progress(self, message: str) -> None:
        self.progress_lines.append(message)
        if self.current_section is None:
            try:
                self._refresh_body()
            except Exception:
                pass

    def _progress_markdown(self) -> str:
        return "\n".join(f"- {line}" for line in self.progress_lines) or "等待分析事件。"

    # --- Stats bar ---

    def _refresh_stats_bar(self) -> None:
        try:
            self.query_one("#stats_progress", Static).update(self._stats_progress_text())
            self.query_one("#stats_resources", Static).update(self._stats_resources_text())
            self.query_one("#stats_reports", Static).update(self._stats_reports_text())
            self.query_one("#stats_right", Static).update(self._stats_right_text())
        except Exception:
            pass

    def _stats_progress_text(self) -> str:
        stats = self._read_runner_stats()
        agents_total = len(self._section_definitions()) * len(self.tickers)
        agents_done = sum(1 for done in self.section_status.values() if done)
        current_agent = self._current_agent_label()
        return f" ◉ Agents {agents_done}/{agents_total} · {current_agent}"

    def _stats_resources_text(self) -> str:
        stats = self._read_runner_stats()
        tokens_in = int(stats.get("tokens_in", 0) or 0)
        tokens_out = int(stats.get("tokens_out", 0) or 0)
        token_text = (
            f"{_format_tokens(tokens_in)}↑{_format_tokens(tokens_out)}↓"
            if tokens_in or tokens_out else "--"
        )
        return f"LLM {int(stats.get('llm_calls', 0) or 0)} · Tools {int(stats.get('tool_calls', 0) or 0)} · {token_text}"

    def _stats_reports_text(self) -> str:
        agents_total = len(self._section_definitions()) * len(self.tickers)
        agents_done = sum(1 for done in self.section_status.values() if done)
        return f"Reports {agents_done}/{agents_total}"

    def _stats_right_text(self) -> str:
        elapsed = self._elapsed_text()
        return f"{elapsed}  ?帮助  s设置  q退出"

    def _read_runner_stats(self) -> dict[str, Any]:
        runner = self._active_runner or self.runner
        if runner and hasattr(runner, "get_stats"):
            self._last_stats = runner.get_stats()
        return self._last_stats

    def _current_agent_label(self) -> str:
        if self.current_ticker and self.current_section:
            section = SECTION_BY_ID.get(self.current_section)
            if section:
                return section.title
        if self.current_ticker:
            latest = None
            for ticker, section_id in self.section_status:
                if ticker == self.current_ticker:
                    latest = section_id
            if latest:
                section = SECTION_BY_ID.get(latest)
                if section:
                    return section.title
        return "等待"

    def _section_definitions(self) -> tuple[SectionDef, ...]:
        return section_definitions_for(self._analysis_config.selected_analysts)

    def _elapsed_text(self) -> str:
        if self._started_at is None:
            return "00:00"
        elapsed = max(0, int(time.time() - self._started_at))
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

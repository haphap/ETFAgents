"""Textual application for ETFAgents — M4: Interactive Enhancements."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
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
    AVAILABLE_THEMES,
    AnalysisConfig,
    AnalysisEvent,
    AnalysisRunner,
    BacktestEvent,
    BacktestFailed,
    BacktestFinished,
    BacktestRecord,
    BacktestRunner,
    BacktestStarted,
    BacktestViewer,
    BacktestViewModel,
    IdRegistry,
    OrderResult,
    PaperTradingSnapshot,
    PaperTradingViewModel,
    RESEARCH_DEPTH_REQUIREMENTS,
    ReportRecord,
    ReportRepository,
    SECTION_BY_ID,
    SECTION_DEFINITIONS,
    SectionDone,
    TuiSettings,
    TickerCancelled,
    TickerDone,
    TickerFailed,
    TickerStarted,
)


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


# ---------------------------------------------------------------------------
# HomeScreen
# ---------------------------------------------------------------------------

class HomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane nav-pane"):
                yield Static("Menu", classes="pane-title")
                yield Button("⌂  研究分析", id="btn_research", variant="primary", classes="nav-button")
                yield Button("▤  研究报告库", id="btn_reports", classes="nav-button")
                yield Button("⌁  回测", id="btn_backtest", classes="nav-button")
                yield Button("◈  模拟交易", id="btn_paper", classes="nav-button")
            with Vertical(classes="right-pane dashboard-pane"):
                yield Static("ETFAgents Interactive Mode", id="title")
                yield Static(
                    "多智能体 ETF 研究 · 报告复盘 · 回测验证 · 模拟交易",
                    classes="subtitle",
                )
                with Vertical(classes="dashboard-card"):
                    yield Static("Connection Details", classes="pane-title")
                    yield Static("Provider      : local config\nResearch Graph: ready\nReports       : local repository")
                with Vertical(classes="dashboard-card"):
                    yield Static("Workflow", classes="pane-title")
                    yield Static("1. 选择研究分析并输入 ETF\n2. 配置 provider / model / 研究深度\n3. 在运行页查看整体进度与团队报告")
                yield Static("ETFAgents", classes="ascii-logo")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "btn_research": "research",
            "btn_reports": "reports",
            "btn_backtest": "backtest",
            "btn_paper": "paper",
        }
        screen = mapping.get(event.button.id or "")
        if screen:
            self.app.push_screen(screen)


# ---------------------------------------------------------------------------
# ResearchAnalysisScreen (M2)
# ---------------------------------------------------------------------------

class AnalysisConfigModal(ModalScreen[AnalysisConfig | None]):
    """Modal to configure analysis parameters before running."""

    DEFAULT_CSS = """
    AnalysisConfigModal { align: center middle; }
    #acm_container { width: 82; height: auto; max-height: 46; border: thick #9af4f2; background: #252838; padding: 1 2; }
    #acm_container .acm-row { height: auto; margin: 0; }
    #acm_container .acm-col { width: 1fr; height: auto; margin-right: 1; }
    #acm_container Static { height: 1; margin: 0; }
    #acm_container Checkbox { height: 1; margin: 0; }
    #acm_container Button { margin: 0 1 0 0; }
    #acm_container Select { margin: 0 0 1 0; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="acm_container"):
            yield Static("分析配置", classes="pane-title")
            yield Static("选择分析师:")
            for defn in SECTION_DEFINITIONS:
                if defn.team == "分析师":
                    yield Checkbox(defn.title, value=True, id=f"acm_cb_{defn.section_id}")
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
            with Horizontal(classes="acm-row"):
                yield Button("确定", id="btn_acm_ok", variant="primary")
                yield Button("取消", id="btn_acm_cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_acm_ok":
            from cli.tui.services import ANALYST_KEYS
            selected = [
                k for k in ANALYST_KEYS
                if self._checkbox_checked(f"acm_cb_{k}")
            ]
            depth = self.query_one("#acm_depth", Select).value
            provider = self.query_one("#acm_provider", Select).value
            quick_model = self.query_one("#acm_quick_model", Select).value
            deep_model = self.query_one("#acm_deep_model", Select).value
            language = self.query_one("#acm_language", Select).value
            self.dismiss(AnalysisConfig(
                selected_analysts=selected or list(ANALYST_KEYS),
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


class ResearchAnalysisScreen(Screen):
    """Collect ETF analysis input, then open the dedicated run screen."""

    def __init__(self, runner: AnalysisRunner | None = None, repository: ReportRepository | None = None):
        super().__init__()
        self.runner = runner
        self.repository = repository or ReportRepository()
        self._analysis_config: AnalysisConfig | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("研究分析", classes="pane-title")
                yield Static("输入 ETF 代码（逗号分隔）:", id="ra_label")
                yield Input(id="ra_ticker_input")
                yield Button("开始分析", id="btn_ra_start", variant="primary")
            with Vertical(classes="right-pane"):
                yield Markdown(
                    "点击开始分析后进入运行页。运行页左侧显示 ETF 状态，右上显示团队，右下显示整体进度或选中团队报告。",
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


class AnalysisRunScreen(Screen):
    """Run ETF analysis and stream results in real-time.

    Left pane: ETF queue/status.
    Right-top: team list.
    Right-bottom: overall progress or selected team report.
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
        self.current_ticker: str | None = None
        self.current_section: str | None = None
        self._analysis_thread: threading.Thread | None = None
        self.progress_lines: list[str] = []
        self._started_at: float | None = None
        self._last_stats: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(classes="run-layout"):
            with Horizontal(classes="screen-body run-main"):
                with Vertical(classes="left-pane"):
                    yield Static("ETF 信息", classes="pane-title")
                    yield Static(self._config_summary(), id="ra_run_config")
                    yield Button("取消", id="btn_ra_cancel", variant="warning", disabled=True)
                    yield Static("分析队列", classes="pane-title")
                    yield ListView(id="ra_queue")
                with Vertical(classes="right-pane"):
                    with Vertical(classes="right-top"):
                        yield Static("团队", classes="pane-title")
                        yield ListView(id="ra_sections")
                    with Vertical(classes="right-bottom"):
                        yield Static("整体进度", id="ra_body_title", classes="pane-title")
                        with VerticalScroll(id="ra_body_scroll"):
                            yield Markdown("准备开始分析。", id="ra_body")
            yield Static(self._stats_text(), id="ra_stats_bar")
        yield Footer()

    def on_mount(self) -> None:
        sections = self.query_one("#ra_sections", ListView)
        for defn in SECTION_DEFINITIONS:
            sections.append(ListItem(
                Label(f"{defn.team} / {defn.title}"),
                id=f"rsec-{defn.section_id}",
            ))
        self._start_analysis()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_ra_cancel":
            self._cancel_analysis()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("rsec-"):
            self.current_section = item_id[5:]
            self._refresh_body()
        elif item_id in self.ticker_ids:
            self.current_ticker = self.ticker_ids.resolve(item_id)
            self._refresh_body()

    def _start_analysis(self) -> None:
        if not self.tickers:
            return

        self.section_contents.clear()
        self.section_status.clear()
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
        return (
            f"ETF: {', '.join(self.tickers)}\n"
            f"研究深度: {_depth_option_label(cfg.depth_name)}\n"
            f"Provider: {cfg.llm_provider}\n"
            f"快速模型: {cfg.quick_model or '默认'}\n"
            f"深度模型: {cfg.deep_model or '默认'}"
        )

    def _cancel_analysis(self) -> None:
        if self._active_runner:
            self._active_runner.request_cancel()
        self.query_one("#btn_ra_cancel", Button).disabled = True

    def on_unmount(self) -> None:
        if self._active_runner:
            self._active_runner.request_cancel()

    def _run_analysis(self, runner: AnalysisRunner, tickers: list[str]) -> None:
        """Worker thread: stream analysis events."""
        cfg = self._analysis_config
        selected = cfg.selected_analysts if cfg else None
        try:
            for event in runner.run_queue(tickers, selected_analysts=selected):
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

    def _apply_event(self, event: AnalysisEvent) -> None:
        """UI thread: handle event."""
        if isinstance(event, TickerStarted):
            self._handle_ticker_started(event)
        elif isinstance(event, SectionDone):
            self._handle_section_done(event)
        elif isinstance(event, TickerDone):
            self._handle_ticker_done(event)
        elif isinstance(event, TickerFailed):
            self._handle_ticker_failed(event)
        elif isinstance(event, TickerCancelled):
            self._handle_ticker_cancelled(event)
        self._refresh_stats_bar()

    def _handle_ticker_started(self, event: TickerStarted) -> None:
        """Mark ticker as running in queue."""
        ticker_id = self.ticker_ids.register(event.ticker)
        queue = self.query_one("#ra_queue", ListView)
        queue.append(ListItem(Label(f"⏳ {event.ticker}"), id=ticker_id))
        self._append_progress(f"{event.ticker}: 开始运行，共 {event.total_sections} 个团队章节")
        if self.current_ticker is None:
            self.current_ticker = event.ticker

    def _handle_section_done(self, event: SectionDone) -> None:
        """Cache section content and update status."""
        self.section_contents[(event.ticker, event.section_id)] = event.content
        self.section_status[(event.ticker, event.section_id)] = True
        title = SECTION_BY_ID.get(event.section_id).title if event.section_id in SECTION_BY_ID else event.section_id
        self._append_progress(f"{event.ticker}: {title} 已更新 ({event.completed}/{event.total})")
        self._refresh_body()

    def _handle_ticker_done(self, event: TickerDone) -> None:
        """Mark ticker complete."""
        ticker_id = self.ticker_ids.register(event.ticker)
        rating_str = f" {event.rating}" if event.rating else ""
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            label = item.query_one(Label)
            label.update(f"✓ {event.ticker}{rating_str}")
        except Exception:
            pass
        self.repository.invalidate()
        self._append_progress(f"{event.ticker}: 分析完成{rating_str}")

    def _handle_ticker_failed(self, event: TickerFailed) -> None:
        """Mark ticker failed."""
        ticker_id = self.ticker_ids.register(event.ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            label = item.query_one(Label)
            label.update(f"✗ {event.ticker}")
        except Exception:
            pass
        self._append_progress(f"{event.ticker}: 分析失败 - {event.error}")

    def _handle_ticker_cancelled(self, event: TickerCancelled) -> None:
        """Mark ticker cancelled."""
        ticker_id = self.ticker_ids.register(event.ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            label = item.query_one(Label)
            label.update(f"⊘ {event.ticker}")
        except Exception:
            pass
        self._append_progress(f"{event.ticker}: 已取消")

    def _refresh_body(self) -> None:
        """Update Markdown body based on current selection."""
        if not self.current_ticker:
            self.query_one("#ra_body", Markdown).update("请选择一个 ticker。")
            return
        if self.current_section is None:
            self.query_one("#ra_body_title", Static).update("整体进度")
            self.query_one("#ra_body", Markdown).update(self._progress_markdown())
            return
        content = self.section_contents.get((self.current_ticker, self.current_section))
        title = SECTION_BY_ID.get(self.current_section).title if self.current_section in SECTION_BY_ID else self.current_section
        self.query_one("#ra_body_title", Static).update(str(title))
        if content:
            self.query_one("#ra_body", Markdown).update(content)
        else:
            self.query_one("#ra_body", Markdown).update("该团队尚未产出报告，分析仍在进行或尚未开始。")

    def _show_error(self, error: str) -> None:
        """Show error in body."""
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

    def _refresh_stats_bar(self) -> None:
        try:
            self.query_one("#ra_stats_bar", Static).update(self._stats_text())
        except Exception:
            pass

    def _stats_text(self) -> str:
        stats = self._read_runner_stats()
        agents_done = sum(1 for done in self.section_status.values() if done)
        agents_total = len(SECTION_DEFINITIONS)
        reports_done = agents_done
        reports_total = len(SECTION_DEFINITIONS)
        current_agent = self._current_agent_label()
        elapsed = self._elapsed_text()
        tokens_in = int(stats.get("tokens_in", 0) or 0)
        tokens_out = int(stats.get("tokens_out", 0) or 0)
        token_text = (
            f"{_format_tokens(tokens_in)}↑ {_format_tokens(tokens_out)}↓"
            if tokens_in or tokens_out else "--"
        )
        return (
            f"Agents {agents_done}/{agents_total} | "
            f"Agent {current_agent} | "
            f"LLM {int(stats.get('llm_calls', 0) or 0)} | "
            f"Tools {int(stats.get('tool_calls', 0) or 0)} | "
            f"Tokens {token_text} | "
            f"Reports {reports_done}/{reports_total} | "
            f"{elapsed}"
        )

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

    def _elapsed_text(self) -> str:
        if self._started_at is None:
            return "00:00"
        elapsed = max(0, int(time.time() - self._started_at))
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"


def _format_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


# ---------------------------------------------------------------------------
# ReportLibraryScreen (M1)
# ---------------------------------------------------------------------------

class ReportLibraryScreen(Screen):
    """Browse locally saved single-ETF reports.

    Left pane: report list (ticker + date + rating).
    Right-top: section list (fixed 9 + complete).
    Right-bottom: selected section Markdown body.
    """

    def __init__(self, repository: ReportRepository) -> None:
        super().__init__()
        self.repository = repository
        self.records: list[ReportRecord] = []
        self.current: ReportRecord | None = None
        self.current_section: str = "portfolio_manager"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("报告列表", classes="pane-title")
                yield ListView(id="reports")
                yield Static("按 r 刷新本地报告", classes="hint")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("报告章节", classes="pane-title")
                    yield ListView(id="lib_sections")
                with Vertical(classes="right-bottom"):
                    yield Static("报告正文", classes="pane-title")
                    yield Markdown("暂无报告。", id="lib_body")
        yield Footer()

    def on_mount(self) -> None:
        sections = self.query_one("#lib_sections", ListView)
        for defn in SECTION_DEFINITIONS:
            sections.append(ListItem(
                Label(f"{defn.team} / {defn.title}"),
                id=f"lsec-{defn.section_id}",
            ))
        sections.append(ListItem(Label("完整报告"), id="lsec-complete"))
        self._load_reports()

    def _load_reports(self) -> None:
        self.records = self.repository.list_reports()
        reports = self.query_one("#reports", ListView)
        reports.clear()
        if not self.records:
            self.current = None
            self.current_section = "portfolio_manager"
            self.query_one("#lib_body", Markdown).update(
                "暂无报告。使用 `etfagents analyze` 生成首份报告。"
            )
            return
        for i, rec in enumerate(self.records):
            rating_str = f"  {rec.rating}" if rec.rating else ""
            reports.append(ListItem(
                Label(f"{rec.ticker}  {rec.date}{rating_str}"),
                id=f"rpt-{i}",
            ))
        self.current = self.records[0]
        self._refresh_body()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("rpt-"):
            idx = int(item_id[4:])
            if 0 <= idx < len(self.records):
                self.current = self.records[idx]
                self._refresh_body()
        elif item_id.startswith("lsec-"):
            self.current_section = item_id[5:]
            self._refresh_body()

    async def action_refresh_reports(self) -> None:
        self.repository.invalidate()
        self._load_reports()

    def _refresh_body(self) -> None:
        if self.current is None:
            return
        content = self.repository.read_section(self.current, self.current_section)
        self.query_one("#lib_body", Markdown).update(content or "该章节暂无内容。")


# ---------------------------------------------------------------------------
# BacktestScreen (M0 placeholder — full implementation in M3)
# ---------------------------------------------------------------------------

class BacktestScreen(Screen):
    """View existing backtest results and run new backtests.

    Left pane: list of runs + refresh button + run inputs.
    Right-top: metrics table + sparkline.
    Right-bottom: summary markdown.
    """

    def __init__(self, viewer: BacktestViewer | None = None, runner: BacktestRunner | None = None) -> None:
        super().__init__()
        self._viewer = viewer
        self._runner = runner
        self.records: list[BacktestRecord] = []
        self.current: BacktestRecord | None = None
        self._load_count = 0  # Counter for unique IDs across refreshes

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("回测结果", classes="pane-title")
                yield ListView(id="bt_list")
                yield Button("刷新", id="btn_bt_refresh", variant="primary")
                yield Static("运行新回测", classes="pane-title")
                yield Input(placeholder="ETF代码（逗号分隔）", id="bt_run_tickers")
                yield Input(placeholder="开始日期 (YYYY-MM-DD)", id="bt_run_start")
                yield Input(placeholder="结束日期 (YYYY-MM-DD)", id="bt_run_end")
                yield Button("运行回测", id="btn_bt_run", variant="success")
                yield Static("", id="bt_run_status")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("NAV走势", classes="pane-title")
                    yield Static("", id="bt_sparkline")
                    yield DataTable(id="bt_metrics")
                with Vertical(classes="right-bottom"):
                    yield Static("摘要", classes="pane-title")
                    yield Markdown(id="bt_summary")
        yield Footer()

    def on_mount(self) -> None:
        self._start_loading()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_bt_refresh":
            self._start_loading()
        elif event.button.id == "btn_bt_run":
            self._start_backtest()

    async def action_refresh_reports(self) -> None:
        self._start_loading()

    def _start_backtest(self) -> None:
        tickers_str = self.query_one("#bt_run_tickers", Input).value.strip()
        start = self.query_one("#bt_run_start", Input).value.strip()
        end = self.query_one("#bt_run_end", Input).value.strip()
        if not tickers_str or not start or not end:
            self.query_one("#bt_run_status", Static).update("请填写所有字段")
            return
        tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
        self.query_one("#bt_run_status", Static).update("回测运行中...")
        self.query_one("#btn_bt_run", Button).disabled = True
        runner = self._runner or BacktestRunner()
        threading.Thread(
            target=self._run_backtest,
            args=(runner, tickers, start, end),
            daemon=True,
            name="etfagents-tui-backtest",
        ).start()

    def _run_backtest(self, runner: BacktestRunner, tickers: list[str], start: str, end: str) -> None:
        for event in runner.run(tickers, start, end):
            _safe_call_from_thread(self, self._apply_backtest_event, event)

    def _apply_backtest_event(self, event: BacktestEvent) -> None:
        status = self.query_one("#bt_run_status", Static)
        if isinstance(event, BacktestStarted):
            status.update(f"回测中: {','.join(event.tickers)} {event.start_date}~{event.end_date}")
        elif isinstance(event, BacktestFinished):
            status.update(f"回测完成: {event.output_dir.name}")
            self.query_one("#btn_bt_run", Button).disabled = False
            self._start_loading()
        elif isinstance(event, BacktestFailed):
            status.update(f"回测失败: {event.error}")
            self.query_one("#btn_bt_run", Button).disabled = False

    def _start_loading(self) -> None:
        self.query_one("#bt_sparkline", Static).update("加载中...")
        self.run_worker(self._fetch_records, thread=True, exclusive=True)

    def _fetch_records(self) -> None:
        """Fetch backtest records in a worker thread."""
        try:
            # Fallback to default BacktestViewer if none was injected
            viewer = self._viewer or BacktestViewer()
            records = viewer.list_results()
        except Exception as exc:
            _safe_call_from_thread(self, self._show_error, str(exc))
            return
        _safe_call_from_thread(self, self._apply_records, records)

    def _apply_records(self, records: list[BacktestRecord]) -> None:
        """Update UI with loaded records."""
        self.records = records
        bt_list = self.query_one("#bt_list", ListView)
        self._load_count += 1

        # Always clear existing items to avoid duplicates on refresh
        for item in list(bt_list.children):
            item.remove()

        if not records:
            self.query_one("#bt_sparkline", Static).update("暂无回测结果")
            self.query_one("#bt_metrics", DataTable).clear(columns=True)
            self.query_one("#bt_summary", Markdown).update("")
            return

        # Populate list of backtest runs
        # Use load count to ensure unique IDs across refreshes (avoids DuplicateId errors)
        for i, record in enumerate(records):
            tickers_str = ",".join(record.tickers[:2]) + ("…" if len(record.tickers) > 2 else "")
            ret_str = ""
            if record.cumulative_return is not None:
                ret_str = f" {record.cumulative_return:+.1%}"
            label_text = f"{tickers_str} {record.start_date}~{record.end_date}{ret_str}"
            bt_list.append(ListItem(
                Label(label_text),
                id=f"btr_{self._load_count}_{i}",
            ))

        # Show first record by default
        self._show_record(records[0])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle backtest record selection."""
        if event.item.id and event.item.id.startswith("btr_"):
            try:
                # ID format: btr_{load_count}_{index}
                parts = event.item.id[4:].split("_")
                if len(parts) >= 2:
                    idx = int(parts[-1])  # Last part is the index
                    if 0 <= idx < len(self.records):
                        self._show_record(self.records[idx])
            except (ValueError, IndexError):
                pass

    def _show_record(self, record: BacktestRecord) -> None:
        """Load and display a backtest result."""
        self.current = record
        self.run_worker(
            lambda: self._fetch_detail(record.output_dir),
            thread=True,
            exclusive=True,  # Only one detail fetch at a time to avoid stale data races
        )

    def _fetch_detail(self, output_dir: Path) -> None:
        """Fetch backtest detail in a worker thread."""
        try:
            # Fallback to default BacktestViewer if none was injected
            viewer = self._viewer or BacktestViewer()
            vm = viewer.load(output_dir)
            _safe_call_from_thread(self, self._apply_detail, vm)
        except Exception as exc:
            _safe_call_from_thread(self, self._show_error, str(exc))

    def _apply_detail(self, vm: BacktestViewModel) -> None:
        """Update UI with backtest details."""
        # Verify this data is for the currently selected record (avoid stale updates)
        if self.current is None or vm.output_dir != self.current.output_dir:
            return

        # Sparkline
        sparkline_text = vm.sparkline or "─"
        self.query_one("#bt_sparkline", Static).update(f"[{sparkline_text}]")

        # Metrics table
        metrics_table = self.query_one("#bt_metrics", DataTable)
        metrics_table.clear(columns=True)
        metrics_table.add_columns("指标", "值")

        if vm.metrics and "metrics" in vm.metrics:
            m = vm.metrics["metrics"]
            metrics_to_show = [
                ("累计收益", "cumulative_return"),
                ("年化收益", "annualized_return"),
                ("年化波动", "annualized_volatility"),
                ("最大回撤", "max_drawdown"),
                ("Sharpe比率", "sharpe_ratio"),
                ("总交易数", "total_trades"),
            ]
            for label, key in metrics_to_show:
                val = m.get(key)
                if val is not None:
                    if isinstance(val, float) and key in ["cumulative_return", "annualized_return", "max_drawdown"]:
                        val_str = f"{val:+.1%}"
                    elif isinstance(val, float) and key == "annualized_volatility":
                        val_str = f"{val:.1%}"
                    elif isinstance(val, float):
                        val_str = f"{val:.2f}"
                    else:
                        val_str = str(val)
                    metrics_table.add_row(label, val_str)

        # Summary
        summary_md = vm.summary or "无摘要"
        self.query_one("#bt_summary", Markdown).update(summary_md)

    def _show_error(self, error: str) -> None:
        self.query_one("#bt_sparkline", Static).update(f"加载失败：{error}")


# ---------------------------------------------------------------------------
# PaperTradingScreen (M1)
# ---------------------------------------------------------------------------

class LoginModal(ModalScreen[bool]):
    """Login modal for paper trading."""

    DEFAULT_CSS = """
    LoginModal { align: center middle; }
    #login_container { width: 50; height: auto; border: thick $accent; background: $surface; padding: 1 2; }
    """

    def __init__(self, view_model: PaperTradingViewModel) -> None:
        super().__init__()
        self._view_model = view_model

    def compose(self) -> ComposeResult:
        with Vertical(id="login_container"):
            yield Static("登录", classes="pane-title")
            yield Input(placeholder="用户名", id="login_user")
            yield Input(placeholder="密码", id="login_pass", password=True)
            yield Static("", id="login_error")
            with Horizontal():
                yield Button("登录", id="btn_login_ok", variant="primary")
                yield Button("取消", id="btn_login_cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_login_ok":
            username = self.query_one("#login_user", Input).value.strip()
            password = self.query_one("#login_pass", Input).value
            if not username or not password:
                self.query_one("#login_error", Static).update("请输入用户名和密码")
                return
            self.run_worker(
                lambda: self._do_login(username, password),
                thread=True,
                exclusive=True,
            )
        elif event.button.id == "btn_login_cancel":
            self.dismiss(False)

    def _do_login(self, username: str, password: str) -> None:
        ok = self._view_model.login(username, password)
        _safe_call_from_thread(self, self._on_login_result, ok)

    def _on_login_result(self, ok: bool) -> None:
        if ok:
            self.dismiss(True)
        else:
            self.query_one("#login_error", Static).update("登录失败：用户名或密码错误")


class OrderModal(ModalScreen[None]):
    """Buy/sell order modal for paper trading."""

    DEFAULT_CSS = """
    OrderModal { align: center middle; }
    #order_container { width: 50; height: auto; border: thick $accent; background: $surface; padding: 1 2; }
    """

    def __init__(self, side: str, view_model: PaperTradingViewModel) -> None:
        super().__init__()
        self.side = side
        self._view_model = view_model

    def compose(self) -> ComposeResult:
        title = "买入" if self.side == "buy" else "卖出"
        with Vertical(id="order_container"):
            yield Static(title, classes="pane-title")
            yield Input(placeholder="ETF代码", id="order_ticker")
            yield Input(placeholder="数量", id="order_quantity", restrict=r"[0-9]*")
            yield Static("", id="order_error")
            with Horizontal():
                yield Button("确认", id="btn_order_ok", variant="primary")
                yield Button("取消", id="btn_order_cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_order_ok":
            ticker = self.query_one("#order_ticker", Input).value.strip().upper()
            qty_str = self.query_one("#order_quantity", Input).value.strip()
            if not ticker or not qty_str:
                self.query_one("#order_error", Static).update("请填写所有字段")
                return
            try:
                quantity = int(qty_str)
            except ValueError:
                self.query_one("#order_error", Static).update("数量必须为整数")
                return
            self.run_worker(
                lambda: self._do_order(ticker, quantity),
                thread=True,
                exclusive=True,
            )
        elif event.button.id == "btn_order_cancel":
            self.dismiss(None)

    def _do_order(self, ticker: str, quantity: int) -> None:
        if self.side == "buy":
            result = self._view_model.buy(ticker, quantity)
        else:
            result = self._view_model.sell(ticker, quantity)
        _safe_call_from_thread(self, self._on_order_result, result)

    def _on_order_result(self, result: OrderResult) -> None:
        if result.success:
            self.dismiss(None)
        else:
            self.query_one("#order_error", Static).update(result.message)


class PaperTradingScreen(Screen):
    """Paper trading dashboard with buy/sell/login.

    Left pane: account summary + user status + action buttons.
    Right-top: positions DataTable.
    Right-bottom: trade history DataTable.
    """

    def __init__(self, view_model: PaperTradingViewModel | None = None) -> None:
        super().__init__()
        self._view_model = view_model

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("模拟交易", classes="pane-title")
                yield Static("", id="pt_user_status")
                yield Static("加载中...", id="pt_account")
                yield Button("刷新", id="btn_pt_refresh", variant="primary")
                yield Button("登录", id="btn_pt_login")
                yield Button("登出", id="btn_pt_logout")
                yield Button("买入", id="btn_pt_buy", variant="success")
                yield Button("卖出", id="btn_pt_sell", variant="error")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("持仓", classes="pane-title")
                    yield DataTable(id="pt_positions")
                with Vertical(classes="right-bottom"):
                    yield Static("交易历史", classes="pane-title")
                    yield DataTable(id="pt_trades")
        yield Footer()

    def on_mount(self) -> None:
        self._start_loading()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_pt_refresh":
            self._start_loading()
        elif event.button.id == "btn_pt_login":
            self.app.push_screen(LoginModal(self.view_model), self._on_login_result)
        elif event.button.id == "btn_pt_logout":
            self.view_model.logout()
            self._update_user_status()
            self._start_loading()
        elif event.button.id == "btn_pt_buy":
            self.app.push_screen(OrderModal("buy", self.view_model), self._on_order_done)
        elif event.button.id == "btn_pt_sell":
            self.app.push_screen(OrderModal("sell", self.view_model), self._on_order_done)

    def _on_login_result(self, ok: bool) -> None:
        self._update_user_status()
        if ok:
            self._start_loading()

    def _on_order_done(self, _: None) -> None:
        self._start_loading()

    def _update_user_status(self) -> None:
        user = self.view_model.current_user()
        status = self.query_one("#pt_user_status", Static)
        status.update(f"当前用户: {user}" if user != "default" else "未登录")

    async def action_refresh_reports(self) -> None:
        self._start_loading()

    def _start_loading(self) -> None:
        self.query_one("#pt_account", Static).update("加载中...")
        self.run_worker(self._fetch_snapshot, thread=True, exclusive=True)

    @property
    def view_model(self) -> PaperTradingViewModel:
        if self._view_model is None:
            self._view_model = PaperTradingViewModel()
        return self._view_model

    def _fetch_snapshot(self) -> None:
        try:
            snap = self.view_model.snapshot()
        except Exception as exc:
            _safe_call_from_thread(self, self._show_error, str(exc))
            return
        _safe_call_from_thread(self, self._apply_snapshot, snap)

    def _apply_snapshot(self, snap: PaperTradingSnapshot) -> None:
        self._update_user_status()
        acct = snap.account
        self.query_one("#pt_account", Static).update(
            f"总资产: {acct.get('total_assets', 'N/A')}\n"
            f"现金: {acct.get('cash', 'N/A')}\n"
            f"市值: {acct.get('market_value', 'N/A')}\n"
            f"未实现盈亏: {acct.get('unrealized_pnl', 'N/A')}\n"
            f"已实现盈亏: {acct.get('realized_pnl', 'N/A')}"
        )

        # Positions table
        pos_table = self.query_one("#pt_positions", DataTable)
        pos_table.clear(columns=True)
        pos_table.add_columns("代码", "名称", "数量", "成本", "现价", "市值", "盈亏", "盈亏%")
        for p in snap.positions:
            pnl = p.get("unrealized_pnl", 0)
            pnl_pct = p.get("pnl_pct", 0)
            try:
                pnl = float(pnl)
            except (TypeError, ValueError):
                pnl = 0.0
            try:
                pnl_pct = float(pnl_pct)
            except (TypeError, ValueError):
                pnl_pct = 0.0
            pnl_str = f"{pnl:+.2f}"
            pct_str = f"{pnl_pct:+.2f}%"
            avg_cost = p.get("avg_cost", "")
            cur_price = p.get("current_price", "")
            mkt_val = p.get("market_value", "")
            pos_table.add_row(
                str(p.get("ticker", "")),
                str(p.get("name", "")),
                str(p.get("quantity", "")),
                f"{avg_cost:.4f}" if isinstance(avg_cost, (int, float)) else str(avg_cost),
                f"{cur_price:.4f}" if isinstance(cur_price, (int, float)) else str(cur_price),
                f"{mkt_val:.2f}" if isinstance(mkt_val, (int, float)) else str(mkt_val),
                pnl_str,
                pct_str,
            )

        # Trade history table
        trade_table = self.query_one("#pt_trades", DataTable)
        trade_table.clear(columns=True)
        trade_table.add_columns("时间", "代码", "方向", "数量", "价格", "金额", "盈亏")
        for t in snap.trades:
            trade_table.add_row(
                str(t.get("created_at", "")),
                str(t.get("ticker", "")),
                str(t.get("side", "")),
                str(t.get("quantity", "")),
                str(t.get("price", "")),
                str(t.get("amount", "")),
                str(t.get("pnl", "")),
            )

    def _show_error(self, error: str) -> None:
        self.query_one("#pt_account", Static).update(f"加载失败：{error}")


# ---------------------------------------------------------------------------
# SettingsScreen (M4)
# ---------------------------------------------------------------------------

class SettingsScreen(Screen):
    """TUI settings: theme, density, panel width."""

    BINDINGS = [("escape", "pop_screen", "返回")]

    def __init__(self, settings_path: Path | None = None) -> None:
        super().__init__()
        self._settings_path = settings_path
        self._settings: TuiSettings | None = None

    def compose(self) -> ComposeResult:
        from cli.tui.settings import DENSITY_OPTIONS, PANEL_WIDTH_PRESETS
        yield Header(show_clock=True)
        with Vertical(id="settings_body"):
            yield Static("设置", classes="pane-title")
            yield Static("主题:")
            theme_options = [(t, t) for t in AVAILABLE_THEMES]
            yield Select(theme_options, value="textual-dark", id="sel_theme")
            yield Static("密度:")
            density_labels = {"compact": "紧凑", "normal": "普通", "spacious": "宽松"}
            density_options = [(density_labels.get(d, d), d) for d in DENSITY_OPTIONS]
            yield Select(density_options, value="normal", id="sel_density")
            yield Static("面板宽度:")
            width_labels = {"narrow": "窄", "normal": "普通", "wide": "宽"}
            width_options = [(width_labels.get(k, k), k) for k in PANEL_WIDTH_PRESETS]
            yield Select(width_options, value="normal", id="sel_panel_width")
            with Horizontal():
                yield Button("保存", id="btn_settings_save", variant="primary")
                yield Button("重置", id="btn_settings_reset")
            yield Static("", id="settings_status")
        yield Footer()

    def on_mount(self) -> None:
        path = self._settings_path
        settings = TuiSettings.load(path) if path else TuiSettings.load()
        self._settings = settings
        self._sync_widgets(settings)

    def _sync_widgets(self, settings: TuiSettings) -> None:
        try:
            self.query_one("#sel_theme", Select).value = settings.theme
        except Exception:
            pass
        try:
            self.query_one("#sel_density", Select).value = settings.density
        except Exception:
            pass
        try:
            self.query_one("#sel_panel_width", Select).value = settings.panel_width
        except Exception:
            pass

    def on_select_changed(self, event: Select.Changed) -> None:
        """Live preview: apply settings without saving."""
        self._apply_current_to_app()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_settings_save":
            self._save_settings()
        elif event.button.id == "btn_settings_reset":
            self._reset_settings()

    def _current_settings(self) -> TuiSettings:
        theme_val = self.query_one("#sel_theme", Select).value
        density_val = self.query_one("#sel_density", Select).value
        width_val = self.query_one("#sel_panel_width", Select).value
        return TuiSettings(
            theme=str(theme_val) if theme_val != Select.BLANK else "textual-dark",
            density=str(density_val) if density_val != Select.BLANK else "normal",
            panel_width=str(width_val) if width_val != Select.BLANK else "normal",
        ).validate()

    def _apply_current_to_app(self) -> None:
        settings = self._current_settings()
        self.app.theme = settings.theme
        _apply_pane_settings(self.app, settings)

    def _save_settings(self) -> None:
        settings = self._current_settings()
        path = self._settings_path
        if path:
            settings.save(path)
        else:
            settings.save()
        self._settings = settings
        self.app.theme = settings.theme
        if hasattr(self.app, "_tui_settings"):
            self.app._tui_settings = settings
        _apply_pane_settings(self.app, settings)
        self.query_one("#settings_status", Static).update("设置已保存")

    def _reset_settings(self) -> None:
        defaults = TuiSettings()
        self._sync_widgets(defaults)
        self._apply_current_to_app()
        self.query_one("#settings_status", Static).update("已重置为默认值")


# ---------------------------------------------------------------------------
# HelpScreen
# ---------------------------------------------------------------------------

class HelpScreen(Screen):
    HELP_TEXT = """\
# ETFAgents TUI 帮助

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `q` | 退出 |
| `Escape` | 返回上一屏 |
| `r` | 刷新当前数据 |
| `s` | 打开设置 |
| `?` | 显示本帮助 |

## 功能

- **研究分析**：输入 ETF 代码，配置分析参数，运行多 agent 分析，支持取消。
- **研究报告库**：浏览历史分析报告，按 ticker/日期/章节切换。
- **回测**：查看已有回测结果，运行新回测。
- **模拟交易**：登录、买入、卖出，查看持仓和交易历史。
- **设置**：切换主题、密度、面板宽度。
"""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Markdown(self.HELP_TEXT)
        yield Footer()


# ---------------------------------------------------------------------------
# Layout helper
# ---------------------------------------------------------------------------

def _apply_pane_settings(app: App, settings: TuiSettings) -> None:
    """Toggle CSS classes for panel width and density on the app widget."""
    from cli.tui.settings import DENSITY_OPTIONS, PANEL_WIDTH_PRESETS
    for preset in PANEL_WIDTH_PRESETS:
        app.remove_class(f"panel-{preset}")
    app.add_class(f"panel-{settings.panel_width}")
    for density in DENSITY_OPTIONS:
        app.remove_class(f"density-{density}")
    app.add_class(f"density-{settings.density}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class ETFAgentsTuiApp(App):
    CSS = """
    Screen {
        background: #252838;
        color: #f2f4f8;
    }

    Header {
        background: #252838;
        color: #f2f4f8;
        border: solid #58699f;
        height: 3;
        text-style: bold;
    }

    Footer {
        background: #f2f4f8;
        color: #4f5f91;
        height: 1;
        text-style: bold;
    }

    #title {
        color: #9af4f2;
        text-style: bold;
        height: 1;
        margin: 0 0 1 0;
    }

    .subtitle {
        color: #a2accd;
        margin-bottom: 1;
        text-style: italic;
    }

    .screen-body {
        height: 1fr;
        margin: 1;
    }

    .run-layout {
        height: 1fr;
    }

    .run-main {
        height: 1fr;
        margin-bottom: 0;
    }

    .pane-title {
        text-style: bold;
        color: #9af4f2;
        height: 1;
        margin: 0 0 1 0;
    }

    .hint {
        color: #a2accd;
        height: 1;
        margin-top: 1;
    }

    .fill-list {
        height: 1fr;
    }

    Static {
        color: #f2f4f8;
    }

    Input {
        background: #1f2230;
        color: #f2f4f8;
        border: tall #9af4f2;
        margin: 0 0 1 0;
    }

    Select {
        background: #1f2230;
        color: #f2f4f8;
        border: tall #58699f;
        margin: 0 0 1 0;
    }

    Button {
        background: #58699f;
        color: #f2f4f8;
        text-style: bold;
        border: none;
        margin: 0 0 1 0;
    }

    Button:hover {
        background: #9af4f2;
        color: #4f5f91;
    }

    Button.-primary {
        background: #9af4f2;
        color: #4f5f91;
    }

    Button.-warning {
        background: #d9a441;
        color: #252838;
    }

    Button.-success {
        background: #64e28a;
        color: #252838;
    }

    ListView {
        width: 100%;
        background: #252838;
    }

    ListItem {
        color: #f2f4f8;
        height: 1;
    }

    ListView > ListItem.--highlight {
        background: #9af4f2;
        color: #4f5f91;
        text-style: bold;
    }

    Markdown {
        height: auto;
        background: #252838;
        color: #f2f4f8;
    }

    #ra_body_scroll {
        height: 1fr;
        scrollbar-size: 1 1;
        scrollbar-background: #1f2230;
        scrollbar-color: #9af4f2;
    }

    #ra_body {
        height: auto;
    }

    #ra_stats_bar {
        height: 3;
        margin: 0 1 1 1;
        padding: 1 2;
        border: solid #58699f;
        background: #1f2230;
        color: #9af4f2;
        text-style: bold;
    }

    DataTable {
        height: 1fr;
        background: #252838;
        color: #f2f4f8;
    }

    .left-pane {
        height: 100%;
        width: 30%;
        min-width: 34;
        border: solid #9af4f2;
        padding: 1 2;
        background: #252838;
    }

    .right-pane {
        height: 100%;
        width: 70%;
        padding: 0 1;
        border: solid #9af4f2;
        background: #252838;
    }

    .right-top {
        height: 35%;
        border: solid #58699f;
        padding: 1 2;
        margin-bottom: 1;
        background: #252838;
    }

    .right-bottom {
        height: 1fr;
        border: solid #58699f;
        padding: 1 2;
        background: #252838;
    }

    /* Panel width presets */
    .panel-narrow .left-pane  { width: 30%; }
    .panel-narrow .right-pane { width: 70%; }
    .panel-normal .left-pane  { width: 35%; }
    .panel-normal .right-pane { width: 65%; }
    .panel-wide .left-pane    { width: 40%; }
    .panel-wide .right-pane   { width: 60%; }

    /* Density options */
    .density-compact .left-pane,  .density-compact .right-pane  { padding: 0 0; }
    .density-normal .left-pane,   .density-normal .right-pane   { padding: 0 1; }
    .density-spacious .left-pane, .density-spacious .right-pane { padding: 1 2; }

    .nav-pane {
        width: 22%;
        min-width: 28;
    }

    .dashboard-pane {
        width: 78%;
        padding: 1 3;
    }

    .nav-button {
        width: 100%;
        content-align: left middle;
        background: #252838;
        color: #f2f4f8;
    }

    .nav-button:hover {
        background: #9af4f2;
        color: #4f5f91;
    }

    .dashboard-card {
        height: auto;
        border: solid #58699f;
        padding: 1 2;
        margin: 1 0;
        background: #252838;
    }

    .ascii-logo {
        height: 1fr;
        content-align: center middle;
        color: #a2accd;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("q", "quit", "退出"),
        ("escape", "pop_screen", "返回"),
        ("?", "show_help", "帮助"),
        ("r", "refresh_reports", "刷新"),
        ("s", "open_settings", "设置"),
    ]

    def __init__(
        self,
        repository: ReportRepository | None = None,
        analysis_runner: Any | None = None,
        backtest_viewer: BacktestViewer | None = None,
        paper_view_model: PaperTradingViewModel | None = None,
        settings_path: Path | None = None,
    ):
        super().__init__()
        self.report_repository = repository or ReportRepository()
        self.analysis_runner = analysis_runner
        self._backtest_viewer = backtest_viewer
        self.paper_view_model = paper_view_model
        self._settings_path = settings_path
        self._settings = TuiSettings.load(settings_path) if settings_path else TuiSettings.load()

    @property
    def backtest_viewer(self) -> BacktestViewer:
        """Lazily instantiate BacktestViewer if not injected."""
        if self._backtest_viewer is None:
            self._backtest_viewer = BacktestViewer()
        return self._backtest_viewer

    def on_mount(self) -> None:
        self.theme = self._settings.theme
        self._tui_settings = self._settings
        self.install_screen(HomeScreen(), name="home")
        self.install_screen(
            ResearchAnalysisScreen(
                runner=self.analysis_runner,
                repository=self.report_repository,
            ),
            name="research",
        )
        self.install_screen(
            ReportLibraryScreen(repository=self.report_repository),
            name="reports",
        )
        self.install_screen(
            BacktestScreen(viewer=self.backtest_viewer),
            name="backtest",
        )
        self.install_screen(
            PaperTradingScreen(view_model=self.paper_view_model),
            name="paper",
        )
        self.install_screen(SettingsScreen(settings_path=self._settings_path), name="settings")
        self.install_screen(HelpScreen(), name="help")
        self.push_screen("home")

    def on_screen_resume(self) -> None:
        """Apply layout settings when a screen becomes active."""
        _apply_pane_settings(self, self._tui_settings)

    def action_show_help(self) -> None:
        self.push_screen("help")

    def action_open_settings(self) -> None:
        self.push_screen("settings")

    def action_quit(self) -> None:
        self._cancel_active_operations()
        self.exit()

    def _cancel_active_operations(self) -> None:
        for screen in self.screen_stack:
            if isinstance(screen, AnalysisRunScreen):
                screen._cancel_analysis()
        current = self.screen
        if isinstance(current, AnalysisRunScreen):
            current._cancel_analysis()

    async def action_refresh_reports(self) -> None:
        screen = self.screen
        if hasattr(screen, "action_refresh_reports"):
            result = screen.action_refresh_reports()
            if result is not None:
                await result


def main() -> None:
    app = ETFAgentsTuiApp()
    app.run()

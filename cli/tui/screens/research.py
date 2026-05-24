"""Research analysis screens: input, config modal, and run screen."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
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
    AnalysisConfig,
    AnalysisEvent,
    AnalysisRunner,
    IdRegistry,
    RESEARCH_DEPTH_REQUIREMENTS,
    ReportRepository,
    SECTION_BY_ID,
    SECTION_DEFINITIONS,
    SectionDone,
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


# ---------------------------------------------------------------------------
# AnalysisConfigModal
# ---------------------------------------------------------------------------

class AnalysisConfigModal(ModalScreen[AnalysisConfig | None]):
    """Modal to configure analysis parameters before running."""

    DEFAULT_CSS = """
    AnalysisConfigModal { align: center middle; }
    #acm_container { width: 82; height: auto; max-height: 46; border: thick $accent; background: $surface; padding: 1 2; }
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


# ---------------------------------------------------------------------------
# AnalysisRunScreen
# ---------------------------------------------------------------------------

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
        for defn in self._section_definitions():
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
        ticker_id = self.ticker_ids.register(event.ticker)
        queue = self.query_one("#ra_queue", ListView)
        queue.append(ListItem(Label(f"⏳ {event.ticker}"), id=ticker_id))
        self._append_progress(f"{event.ticker}: 开始运行，共 {event.total_sections} 个团队章节")
        if self.current_ticker is None:
            self.current_ticker = event.ticker

    def _handle_section_done(self, event: SectionDone) -> None:
        self.section_contents[(event.ticker, event.section_id)] = event.content
        self.section_status[(event.ticker, event.section_id)] = True
        title = SECTION_BY_ID.get(event.section_id).title if event.section_id in SECTION_BY_ID else event.section_id
        self._append_progress(f"{event.ticker}: {title} 已更新 ({event.completed}/{event.total})")
        self._refresh_body()

    def _handle_ticker_done(self, event: TickerDone) -> None:
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
        ticker_id = self.ticker_ids.register(event.ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            label = item.query_one(Label)
            label.update(f"✗ {event.ticker}")
        except Exception:
            pass
        self._append_progress(f"{event.ticker}: 分析失败 - {event.error}")

    def _handle_ticker_cancelled(self, event: TickerCancelled) -> None:
        ticker_id = self.ticker_ids.register(event.ticker)
        try:
            item = self.query_one(f"#{ticker_id}", ListItem)
            label = item.query_one(Label)
            label.update(f"⊘ {event.ticker}")
        except Exception:
            pass
        self._append_progress(f"{event.ticker}: 已取消")

    def _refresh_body(self) -> None:
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
        agents_total = len(self._section_definitions())
        reports_done = agents_done
        reports_total = agents_total
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

    def _section_definitions(self) -> tuple[Any, ...]:
        return section_definitions_for(self._analysis_config.selected_analysts)

    def _elapsed_text(self) -> str:
        if self._started_at is None:
            return "00:00"
        elapsed = max(0, int(time.time() - self._started_at))
        return f"{elapsed // 60:02d}:{elapsed % 60:02d}"

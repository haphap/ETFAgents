"""Paper trading screen with login/order modals."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Static,
)

from cli.tui.services import (
    OrderResult,
    PaperTradingSnapshot,
    PaperTradingViewModel,
)
from cli.tui.screens.research import _safe_call_from_thread


class LoginModal(ModalScreen[bool]):
    """Login modal for paper trading."""

    DEFAULT_CSS = """
    LoginModal { align: center middle; }
    #login_container { width: 50; height: auto; border: solid $accent; background: $surface; padding: 1 2; }
    #login_container .text-action { margin: 0 1 0 0; }
    """

    def __init__(self, view_model: PaperTradingViewModel) -> None:
        super().__init__()
        self._view_model = view_model

    def compose(self) -> ComposeResult:
        with Vertical(id="login_container"):
            yield Static("登录", classes="pane-title")
            yield Input(placeholder="用户名", id="login_user")
            yield Input(placeholder="密码", id="login_pass", password=True)
            yield Static("", id="login_error", classes="error-text")
            with Horizontal():
                yield Button("› Login", id="btn_login_ok", classes="text-action")
                yield Button("Cancel", id="btn_login_cancel", classes="text-action muted")

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
    #order_container { width: 50; height: auto; border: solid $accent; background: $surface; padding: 1 2; }
    #order_container .text-action { margin: 0 1 0 0; }
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
            yield Static("", id="order_error", classes="error-text")
            with Horizontal():
                yield Button("› Confirm", id="btn_order_ok", classes="text-action")
                yield Button("Cancel", id="btn_order_cancel", classes="text-action muted")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_order_ok":
            ticker = self.query_one("#order_ticker", Input).value.strip().upper()
            qty_str = self.query_one("#order_quantity", Input).value.strip()
            if not ticker or not qty_str:
                self.query_one("#order_error", Static).update("请输入代码和数量")
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
    """Account / Actions + Portfolio Board layout."""

    def __init__(self, view_model: PaperTradingViewModel | None = None) -> None:
        super().__init__()
        self.view_model = view_model

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(classes="screen-body"):
            with Vertical(classes="left-pane"):
                yield Static("Account / Actions", classes="pane-title")
                yield Static("", id="pt_user_status", classes="status-strip")
                yield Button("Login", id="btn_pt_login", classes="text-action")
                yield Button("Logout", id="btn_pt_logout", classes="text-action muted")
                yield Button("› Buy", id="btn_pt_buy", classes="text-action")
                yield Button("› Sell", id="btn_pt_sell", classes="text-action warning-text")
                yield Button("Refresh", id="btn_pt_refresh", classes="text-action muted")
            with Vertical(classes="right-pane"):
                with Vertical(classes="right-top"):
                    yield Static("Account Snapshot", classes="pane-title")
                    yield Static("加载中...", id="pt_account")
                with Vertical(classes="right-bottom"):
                    yield Static("Positions", classes="pane-title")
                    yield DataTable(id="pt_positions")
                    yield Static("Trades", classes="pane-title")
                    yield DataTable(id="pt_trades")
        yield Footer()

    def on_mount(self) -> None:
        if self.view_model:
            self._start_loading()
        else:
            self.query_one("#pt_account", Static).update(
                "未配置模拟交易引擎。请参考文档配置 PaperTradingEngine。"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_pt_login":
            if self.view_model:
                self.app.push_screen(LoginModal(self.view_model), self._on_login_result)
        elif event.button.id == "btn_pt_logout":
            if self.view_model:
                self.view_model.logout()
                self._start_loading()
        elif event.button.id == "btn_pt_buy":
            if self.view_model:
                self.app.push_screen(OrderModal("buy", self.view_model), self._on_order_done)
        elif event.button.id == "btn_pt_sell":
            if self.view_model:
                self.app.push_screen(OrderModal("sell", self.view_model), self._on_order_done)
        elif event.button.id == "btn_pt_refresh":
            self._start_loading()

    def _on_login_result(self, ok: bool) -> None:
        if ok:
            self._start_loading()

    def _on_order_done(self, _: None) -> None:
        self._start_loading()

    def _start_loading(self) -> None:
        self.run_worker(self._fetch_snapshot, thread=True, exclusive=True)

    def _fetch_snapshot(self) -> None:
        if not self.view_model:
            return
        try:
            snapshot = self.view_model.snapshot()
            _safe_call_from_thread(self, self._apply_snapshot, snapshot)
        except Exception as exc:
            _safe_call_from_thread(self, self._show_error, str(exc))

    def _apply_snapshot(self, snapshot: PaperTradingSnapshot) -> None:
        acct = snapshot.account
        total_assets = acct.get("total_assets", 0)
        cash = acct.get("cash", 0)
        market_value = acct.get("market_value", 0)
        unrealized_pnl = acct.get("unrealized_pnl", 0)
        realized_pnl = acct.get("realized_pnl", 0)
        self.query_one("#pt_account", Static).update(
            f"Total {total_assets:,.2f} | Cash {cash:,.2f} | MV {market_value:,.2f}\n"
            f"Unrealized {unrealized_pnl:+,.2f} | Realized {realized_pnl:+,.2f}"
        )

        # User status
        if self.view_model:
            user = self.view_model.current_user()
            self.query_one("#pt_user_status", Static).update(f"user: {user}")

        # Positions table
        pos_table = self.query_one("#pt_positions", DataTable)
        pos_table.clear(columns=True)
        pos_table.add_columns("代码", "名称", "数量", "均价", "现价", "市值", "盈亏", "盈亏%")
        for pos in snapshot.positions:
            pos_table.add_row(
                str(pos.get("ticker", "")),
                str(pos.get("name", "")),
                str(pos.get("quantity", 0)),
                f"{pos.get('avg_cost', 0):.3f}",
                f"{pos.get('current_price', 0):.3f}",
                f"{pos.get('market_value', 0):,.2f}",
                f"{pos.get('unrealized_pnl', 0):+,.2f}",
                f"{pos.get('pnl_pct', 0):+.2f}%",
            )

        # Trades table
        trades_table = self.query_one("#pt_trades", DataTable)
        trades_table.clear(columns=True)
        trades_table.add_columns("时间", "代码", "方向", "数量", "价格", "金额", "盈亏")
        for trade in snapshot.trades:
            trades_table.add_row(
                str(trade.get("created_at", "")),
                str(trade.get("ticker", "")),
                str(trade.get("side", "")),
                str(trade.get("quantity", 0)),
                f"{trade.get('price', 0):.3f}",
                f"{trade.get('amount', 0):,.2f}",
                f"{trade.get('pnl', 0):+,.2f}",
            )

    def _show_error(self, error: str) -> None:
        self.query_one("#pt_account", Static).update(f"加载失败：{error}")

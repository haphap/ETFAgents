"""Help screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown


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

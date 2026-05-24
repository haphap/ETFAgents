"""Settings screen for theme, density, panel width."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Select, Static
from textual.containers import Horizontal, Vertical

from cli.tui.services import AVAILABLE_THEMES, TuiSettings


def _apply_pane_settings(app: App, settings: TuiSettings) -> None:
    """Toggle CSS classes for panel width and density on the app widget."""
    from cli.tui.settings import DENSITY_OPTIONS, PANEL_WIDTH_PRESETS
    for preset in PANEL_WIDTH_PRESETS:
        app.remove_class(f"panel-{preset}")
    app.add_class(f"panel-{settings.panel_width}")
    for density in DENSITY_OPTIONS:
        app.remove_class(f"density-{density}")
    app.add_class(f"density-{settings.density}")


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

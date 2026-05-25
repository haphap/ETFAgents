"""TUI settings — pure data module, does not import textual."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SETTINGS_PATH = Path("~/.etfagents/tui_settings.json").expanduser()

AVAILABLE_THEMES = (
    "textual-dark", "textual-light", "nord", "gruvbox",
    "catppuccin-mocha", "catppuccin-latte", "dracula", "tokyo-night",
    "monokai", "solarized-dark", "solarized-light", "flexoki",
)

PANEL_WIDTH_PRESETS = {
    "narrow": 15,
    "normal": 20,
    "wide": 25,
}

DENSITY_OPTIONS = ("compact", "normal", "spacious")


@dataclass
class TuiSettings:
    theme: str = "catppuccin-mocha"
    density: str = "normal"
    panel_width: str = "normal"  # "narrow" | "normal" | "wide"

    def validate(self) -> TuiSettings:
        """Clamp values to valid ranges and return self."""
        if self.theme not in AVAILABLE_THEMES:
            self.theme = "catppuccin-mocha"
        if self.density not in DENSITY_OPTIONS:
            self.density = "normal"
        if self.panel_width not in PANEL_WIDTH_PRESETS:
            self.panel_width = "normal"
        return self

    @property
    def left_pane_pct(self) -> int:
        return PANEL_WIDTH_PRESETS.get(self.panel_width, 25)

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"theme": self.theme, "density": self.density,
                 "panel_width": self.panel_width},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> TuiSettings:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                theme=data.get("theme", "catppuccin-mocha"),
                density=data.get("density", "normal"),
                panel_width=data.get("panel_width", "normal"),
            ).validate()
        except (OSError, json.JSONDecodeError, KeyError, AttributeError, TypeError):
            return cls()

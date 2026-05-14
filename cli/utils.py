import questionary
from typing import List, Optional, Tuple, Dict

from rich.console import Console

from cli.models import AnalystType
from etfagents.llm_clients.model_catalog import OLLAMA_MODEL_ALIASES, get_model_options

console = Console()

TICKER_INPUT_EXAMPLES = "Examples: 510300.SH, 159915.SZ, 513100.SH"

ANALYST_ORDER = [
    ("Market & Flow Analyst", AnalystType.MARKET_FLOW),
    ("Sentiment & Catalyst Analyst", AnalystType.CATALYST_SENTIMENT),
    ("Macro Regime Analyst", AnalystType.MACRO_REGIME),
    ("Meso Commodity Analyst", AnalystType.MESO_COMMODITY),
    ("ETF Holdings-Industry Research Analyst", AnalystType.HOLDINGS_INDUSTRY),
    ("ETF Top Holdings Research Analyst", AnalystType.TOP_HOLDINGS),
]


def get_ticker() -> str:
    """Prompt the user to enter a ticker symbol."""
    ticker = questionary.text(
        f"Enter the exact ticker symbol to analyze ({TICKER_INPUT_EXAMPLES}):",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a valid ticker symbol.",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not ticker:
        console.print("\n[red]No ticker symbol provided. Exiting...[/red]")
        exit(1)

    return normalize_ticker_symbol(ticker)


def normalize_ticker_symbol(ticker: str) -> str:
    """Normalize ticker input while preserving exchange suffixes."""
    return ticker.strip().upper()


def get_analysis_date() -> str:
    """Prompt the user to enter a date in YYYY-MM-DD format."""
    import re
    from datetime import datetime

    def validate_date(date_str: str) -> bool:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    date = questionary.text(
        "Enter the analysis date (YYYY-MM-DD):",
        validate=lambda x: validate_date(x.strip())
        or "Please enter a valid date in YYYY-MM-DD format.",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not date:
        console.print("\n[red]No date provided. Exiting...[/red]")
        exit(1)

    return date.strip()


def select_analysts() -> List[AnalystType]:
    """Select analysts using an interactive checkbox."""
    choices = questionary.checkbox(
        "Select Your [ETF Analysts Team]:",
        choices=[
            questionary.Choice(display, value=value) for display, value in ANALYST_ORDER
        ],
        instruction="\n- Press Space to select/unselect analysts\n- Press 'a' to select/unselect all\n- Press Enter when done",
        validate=lambda x: len(x) > 0 or "You must select at least one analyst.",
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:green"),
                ("selected", "fg:green noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    if not choices:
        console.print("\n[red]No analysts selected. Exiting...[/red]")
        exit(1)

    return choices


def select_research_depth() -> int:
    """Select research depth using an interactive selection."""

    # Define research depth options with their corresponding values
    DEPTH_OPTIONS = [
        ("Shallow - Quick research, few debate and strategy discussion rounds", 1),
        ("Medium - Middle ground, moderate debate rounds and strategy discussion", 3),
        ("Deep - Comprehensive research, in depth debate and strategy discussion", 5),
    ]

    choice = questionary.select(
        "Select Your [Research Depth]:",
        choices=[
            questionary.Choice(display, value=value) for display, value in DEPTH_OPTIONS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]No research depth selected. Exiting...[/red]")
        exit(1)

    return choice


def _fetch_openrouter_models() -> List[Tuple[str, str]]:
    """Fetch available models from the OpenRouter API."""
    import requests
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        return [(m.get("name") or m["id"], m["id"]) for m in models]
    except Exception as e:
        console.print(f"\n[yellow]Could not fetch OpenRouter models: {e}[/yellow]")
        return []


def select_openrouter_model() -> str:
    """Select an OpenRouter model from the newest available, or enter a custom ID."""
    models = _fetch_openrouter_models()

    choices = [questionary.Choice(name, value=mid) for name, mid in models[:5]]
    choices.append(questionary.Choice("Custom model ID", value="custom"))

    choice = questionary.select(
        "Select OpenRouter Model (latest available):",
        choices=choices,
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style([
            ("selected", "fg:magenta noinherit"),
            ("highlighted", "fg:magenta noinherit"),
            ("pointer", "fg:magenta noinherit"),
        ]),
    ).ask()

    if choice is None or choice == "custom":
        return questionary.text(
            "Enter OpenRouter model ID (e.g. google/gemma-4-26b-a4b-it):",
            validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
        ).ask().strip()

    return choice


def _fetch_ollama_models(base_url: str) -> List[Tuple[str, str]]:
    """Fetch locally available models from an Ollama/llama.cpp server via OpenAI-compatible /v1/models."""
    import requests

    try:
        resp = requests.get(f"{base_url}/models", timeout=5)
        resp.raise_for_status()
        raw_ids = [m["id"] for m in resp.json().get("data", [])]
        # Suppress alias if its canonical counterpart is also present
        canonical_ids = set(raw_ids)
        deduped = [
            mid for mid in raw_ids
            if not (OLLAMA_MODEL_ALIASES.get(mid) in canonical_ids)
        ]
        return [(mid, mid) for mid in deduped]
    except Exception as e:
        console.print(f"\n[yellow]Could not fetch Ollama models from {base_url}: {e}[/yellow]")
        # Fall back to static catalog
        static = get_model_options("ollama", "deep")
        if static:
            console.print("[yellow]Using static model list as fallback.[/yellow]")
            return static
        return []


def select_ollama_model(base_url: str) -> str:
    """Select a model from a running Ollama/llama.cpp server, or enter a custom name."""
    models = _fetch_ollama_models(base_url)

    if models:
        choices = [questionary.Choice(mid, value=mid) for _, mid in models]
        choices.append(questionary.Choice("Custom model name", value="custom"))
        choice = questionary.select(
            f"Select Ollama/llama.cpp Model (from {base_url}):",
            choices=choices,
            instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
            style=questionary.Style([
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]),
        ).ask()

        if choice is not None and choice != "custom":
            return choice

    return questionary.text(
        "Enter model name (e.g. qwen3:latest):",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a model name.",
    ).ask().strip()


def _fetch_vllm_models(base_url: str) -> List[Tuple[str, str]]:
    """Fetch available models from a vLLM server via OpenAI-compatible /v1/models."""
    import requests

    try:
        resp = requests.get(f"{base_url}/models", timeout=5)
        resp.raise_for_status()
        return [(m["id"], m["id"]) for m in resp.json().get("data", [])]
    except Exception as e:
        console.print(f"\n[yellow]Could not fetch vLLM models from {base_url}: {e}[/yellow]")
        return []


def select_vllm_model(base_url: str) -> str:
    """Select a model from a running vLLM server, or enter a custom name."""
    models = _fetch_vllm_models(base_url)

    if models:
        choices = [questionary.Choice(mid, value=mid) for _, mid in models]
        choices.append(questionary.Choice("Custom model name", value="custom"))
        choice = questionary.select(
            f"Select vLLM Model (from {base_url}):",
            choices=choices,
            instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
            style=questionary.Style([
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]),
        ).ask()

        if choice is not None and choice != "custom":
            return choice

    return questionary.text(
        "Enter model name (e.g. qwen2.5-7b):",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a model name.",
    ).ask().strip()


def _prompt_custom_model_id() -> str:
    """Prompt the user to enter a provider-specific custom model ID."""
    return questionary.text(
        "Enter model ID:",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a model ID.",
    ).ask().strip()


def _select_model(provider: str, mode: str, base_url: str | None = None) -> str:
    """Select a model for the given provider and mode."""
    if provider.lower() == "openrouter":
        return select_openrouter_model()

    if provider.lower() == "ollama" and base_url:
        return select_ollama_model(base_url)

    if provider.lower() == "vllm" and base_url:
        return select_vllm_model(base_url)

    choice = questionary.select(
        f"Select Your [{mode.title()}-Thinking LLM Engine]:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in get_model_options(provider, mode)
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print(
            f"\n[red]No {mode} thinking llm engine selected. Exiting...[/red]"
        )
        exit(1)

    if choice == "custom":
        return _prompt_custom_model_id()

    return choice


def select_shallow_thinking_agent(provider, base_url: str = None) -> str:
    """Select shallow thinking llm engine using an interactive selection."""
    return _select_model(provider, "quick", base_url)


def select_deep_thinking_agent(provider, base_url: str = None) -> str:
    """Select deep thinking llm engine using an interactive selection."""
    return _select_model(provider, "deep", base_url)

def select_llm_provider() -> tuple[str, str]:
    """Select the LLM provider and its default API endpoint."""
    # Define provider options as (display_name, provider_key, endpoint)
    BASE_URLS = [
        ("OpenAI", "openai", "https://api.openai.com/v1"),
        ("Google", "google", "https://generativelanguage.googleapis.com/v1"),
        ("Anthropic", "anthropic", "https://api.anthropic.com/"),
        ("DeepSeek", "deepseek", "https://api.deepseek.com"),
        ("xAI", "xai", "https://api.x.ai/v1"),
        ("MiniMax", "minimax", "https://api.minimax.chat/v1"),
        ("Openrouter", "openrouter", "https://openrouter.ai/api/v1"),
        ("Ollama / llama.cpp", "ollama", "http://localhost:4000/v1"),
        ("vLLM", "vllm", "http://127.0.0.1:8020/v1"),
    ]
    
    choice = questionary.select(
        "Select your LLM Provider:",
        choices=[
            questionary.Choice(display, value=(provider_key, endpoint, display))
            for display, provider_key, endpoint in BASE_URLS
        ],
        instruction="\n- Use arrow keys to navigate\n- Press Enter to select",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()
    
    if choice is None:
        console.print("\n[red]no OpenAI backend selected. Exiting...[/red]")
        exit(1)
    
    provider_key, url, display_name = choice
    print(f"You selected: {display_name}\tURL: {url}")

    return provider_key, url


def ask_openai_reasoning_effort() -> str:
    """Ask for OpenAI reasoning effort level."""
    choices = [
        questionary.Choice("Medium (Default)", "medium"),
        questionary.Choice("High (More thorough)", "high"),
        questionary.Choice("Low (Faster)", "low"),
    ]
    return questionary.select(
        "Select Reasoning Effort:",
        choices=choices,
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def ask_anthropic_effort() -> str | None:
    """Ask for Anthropic effort level.

    Controls token usage and response thoroughness on Claude 4.5+ and 4.6 models.
    """
    return questionary.select(
        "Select Effort Level:",
        choices=[
            questionary.Choice("High (recommended)", "high"),
            questionary.Choice("Medium (balanced)", "medium"),
            questionary.Choice("Low (faster, cheaper)", "low"),
        ],
        style=questionary.Style([
            ("selected", "fg:cyan noinherit"),
            ("highlighted", "fg:cyan noinherit"),
            ("pointer", "fg:cyan noinherit"),
        ]),
    ).ask()


def ask_gemini_thinking_config() -> str | None:
    """Ask for Gemini thinking configuration.

    Returns thinking_level: "high" or "minimal".
    Client maps to appropriate API param based on model series.
    """
    return questionary.select(
        "Select Thinking Mode:",
        choices=[
            questionary.Choice("Enable Thinking (recommended)", "high"),
            questionary.Choice("Minimal/Disable Thinking", "minimal"),
        ],
        style=questionary.Style([
            ("selected", "fg:green noinherit"),
            ("highlighted", "fg:green noinherit"),
            ("pointer", "fg:green noinherit"),
        ]),
    ).ask()


def ask_output_language() -> str:
    """Ask for report output language."""
    choice = questionary.select(
        "Select Output Language:",
        choices=[
            questionary.Choice("Chinese (中文)", "Chinese"),
            questionary.Choice("English", "English"),
        ],
        style=questionary.Style([
            ("selected", "fg:yellow noinherit"),
            ("highlighted", "fg:yellow noinherit"),
            ("pointer", "fg:yellow noinherit"),
        ]),
    ).ask()

    return choice

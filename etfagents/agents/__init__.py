"""ETFAgents agent definitions.

All public names are lazily imported via PEP 562 ``__getattr__`` so that
``import etfagents.agents`` no longer triggers heavy transitive dependencies
(langchain_core, langgraph, etc.) at package load time.
"""

from __future__ import annotations

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # utils
    "create_msg_delete": (".utils.agent_utils", "create_msg_delete"),
    "AgentState": (".utils.agent_states", "AgentState"),
    "InvestDebateState": (".utils.agent_states", "InvestDebateState"),
    "RiskDebateState": (".utils.agent_states", "RiskDebateState"),
    "TradingMemoryLog": (".utils.memory", "TradingMemoryLog"),
    # analysts
    "create_macro_analyst": (".analysts.macro_analyst", "create_macro_analyst"),
    "create_social_media_analyst": (".analysts.social_media_analyst", "create_social_media_analyst"),
    "create_etf_industry_research_analyst": (".analysts.etf_industry_research_analyst", "create_etf_industry_research_analyst"),
    "create_etf_market_analyst": (".analysts.etf_market_analyst", "create_etf_market_analyst"),
    "create_etf_stock_research_analyst": (".analysts.etf_stock_research_analyst", "create_etf_stock_research_analyst"),
    "create_etf_structure_analyst": (".analysts.etf_structure_analyst", "create_etf_structure_analyst"),
    # researchers
    "create_bear_researcher": (".researchers.bear_researcher", "create_bear_researcher"),
    "create_bull_researcher": (".researchers.bull_researcher", "create_bull_researcher"),
    # risk management
    "create_aggressive_debator": (".risk_mgmt.aggressive_debator", "create_aggressive_debator"),
    "create_conservative_debator": (".risk_mgmt.conservative_debator", "create_conservative_debator"),
    "create_neutral_debator": (".risk_mgmt.neutral_debator", "create_neutral_debator"),
    # managers
    "create_research_manager": (".managers.research_manager", "create_research_manager"),
    "create_portfolio_manager": (".managers.portfolio_manager", "create_portfolio_manager"),
    # trader
    "create_trader": (".trader.trader", "create_trader"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        import importlib

        mod = importlib.import_module(module_path, __package__)
        value = getattr(mod, attr)
        # Cache on the module so subsequent accesses skip __getattr__
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

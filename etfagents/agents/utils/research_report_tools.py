from langchain_core.tools import tool
from typing import Annotated
from etfagents.dataflows.interface import route_to_vendor


@tool
def get_broker_research(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve broker research reports for a given stock.
    Returns recent broker/analyst research reports including titles, institutions,
    authors, and abstracts. Only available for A-share stocks.
    Args:
        ticker (str): Ticker symbol (e.g. '601899.SH')
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing broker research reports
    """
    return route_to_vendor("get_broker_research", ticker, start_date, end_date)


@tool
def get_stock_research(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve individual stock research reports for a given stock.
    Returns recent broker/analyst research reports focused on a specific company,
    including titles, institutions, authors, and abstracts. Only available for A-share stocks.
    Args:
        ticker (str): Ticker symbol (e.g. '601899.SH')
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing individual stock research reports
    """
    return route_to_vendor("get_stock_research", ticker, start_date, end_date)

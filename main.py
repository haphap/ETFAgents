from etfagents.graph.etf_graph import EtfAgentsGraph
from etfagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"  # Use a different model
config["quick_think_llm"] = "gpt-5.4-mini"  # Use a different model
config["max_debate_rounds"] = 1  # Increase debate rounds
# Example for local OpenAI-compatible llama.cpp server:
# config["llm_provider"] = "ollama"
# config["backend_url"] = "http://localhost:4000/v1"

config["data_vendors"]["etf_market_data"] = "tushare"
config["data_vendors"]["etf_reference_data"] = "tushare"

# Initialize with custom config
ta = EtfAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("510300.SH", "2024-05-10")
print(decision)

# Memory log reflections resolve automatically on later runs once return data is available.

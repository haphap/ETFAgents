"""Standalone client that exercises the ETFAgents bridge end-to-end.

It deliberately does NOT import ``etfagents`` — it talks to the bridge over
stdio JSON-RPC the same way the future TypeScript CLI will. Run with::

    .venv/bin/python docs/bridge_client_demo.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from itertools import count
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")


class BridgeClient:
    """Minimal blocking JSON-RPC client over a child process's stdio."""

    def __init__(self, env: dict | None = None) -> None:
        self._proc = subprocess.Popen(
            [PYTHON, "-m", "etfagents.bridge"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env=env or os.environ.copy(),
            text=True,
            encoding="utf-8",
        )
        self._ids = count(1)

    def call(self, method: str, params: dict | None = None) -> object:
        msg: dict = {"jsonrpc": "2.0", "id": next(self._ids), "method": method}
        if params is not None:
            msg["params"] = params
        assert self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError(f"Bridge died: {self._proc.stderr.read() if self._proc.stderr else ''}")
        response = json.loads(line)
        if "error" in response:
            err = response["error"]
            raise RuntimeError(f"RPC {method} failed [{err['code']}]: {err['message']}")
        return response["result"]

    def close(self) -> None:
        if self._proc.stdin:
            self._proc.stdin.close()
        self._proc.wait(timeout=5)
        for stream in (self._proc.stdout, self._proc.stderr):
            if stream and not stream.closed:
                stream.close()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "ETFAGENTS_CACHE_DIR": str(Path(tmp) / "cache"),
            "ETFAGENTS_RESULTS_DIR": str(Path(tmp) / "results"),
        }
        Path(env["ETFAGENTS_CACHE_DIR"]).mkdir()
        Path(env["ETFAGENTS_RESULTS_DIR"]).mkdir()
        client = BridgeClient(env=env)
        try:
            # 1) Discover tools
            tools = client.call("tools.list")
            print(f"Discovered {len(tools)} tools.")
            for t in tools[:3]:
                print(f"  - {t['name']}: {t['description'].splitlines()[0]}")

            # 2) Read & override config
            cfg = client.call("config.default")
            cfg["max_debate_rounds"] = 2
            client.call("config.set", {"config": cfg})
            live = client.call("config.get")
            assert live["max_debate_rounds"] == 2

            # 3) Cache snapshot
            stats = client.call("cache.stats")
            print(f"Cache total: {stats['total_mb']} MB across categories {list(stats)[:-1]}")

            # 4) Paper trading: read default account
            db_path = str(Path(tmp) / "paper.db")
            user = client.call("paper.current_user", {"db_path": db_path})
            account = client.call("paper.get_account", {"db_path": db_path})
            print(f"Paper user={user['user']}, cash={account['cash']:,.2f}")

            # 5) Backtest input validation (full run requires TUSHARE_TOKEN)
            try:
                client.call("backtest.run_candidate_pool",
                            {"start_date": "2026-01-02", "end_date": "2026-01-31",
                             "signals": {}})
            except RuntimeError as exc:
                print(f"Backtest rejected bad input as expected: {exc}")
        finally:
            client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

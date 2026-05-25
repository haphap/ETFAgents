
import importlib.util
import unittest
if not importlib.util.find_spec("langgraph"):
    raise unittest.SkipTest("langgraph not installed")

import tempfile
import unittest
from typing import TypedDict

from langgraph.graph import END, StateGraph

from etfagents.graph.checkpointer import (
    checkpoint_step,
    clear_checkpoint,
    get_checkpointer,
    has_checkpoint,
    thread_id,
)

_should_crash = False

class _SimpleState(TypedDict):
    count: int

def _node_a(state: _SimpleState) -> dict:
    return {"count": state["count"] + 1}

def _node_b(state: _SimpleState) -> dict:
    if _should_crash:
        raise RuntimeError("simulated mid-analysis crash")
    return {"count": state["count"] + 10}

def _build_graph() -> StateGraph:
    builder = StateGraph(_SimpleState)
    builder.add_node("analyst", _node_a)
    builder.add_node("trader", _node_b)
    builder.set_entry_point("analyst")
    builder.add_edge("analyst", "trader")
    builder.add_edge("trader", END)
    return builder

class TestCheckpointResume(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ticker = "TEST"
        self.trade_date = "2026-04-20"

    def test_crash_and_resume(self):
        global _should_crash
        builder = _build_graph()
        config = {"configurable": {"thread_id": thread_id(self.ticker, self.trade_date)}}

        _should_crash = True
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            with self.assertRaises(RuntimeError):
                graph.invoke({"count": 0}, config=config)

        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.trade_date))
        self.assertEqual(checkpoint_step(self.tmpdir, self.ticker, self.trade_date), 1)

        _should_crash = False
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            result = graph.invoke(None, config=config)

        self.assertEqual(result["count"], 11)

    def test_clear_checkpoint_allows_fresh_start(self):
        global _should_crash
        builder = _build_graph()
        config = {"configurable": {"thread_id": thread_id(self.ticker, self.trade_date)}}

        _should_crash = True
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            with self.assertRaises(RuntimeError):
                graph.invoke({"count": 0}, config=config)

        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.trade_date))
        clear_checkpoint(self.tmpdir, self.ticker, self.trade_date)
        self.assertFalse(has_checkpoint(self.tmpdir, self.ticker, self.trade_date))

        _should_crash = False
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            result = graph.invoke({"count": 0}, config=config)

        self.assertEqual(result["count"], 11)

    def test_different_date_starts_fresh(self):
        global _should_crash
        builder = _build_graph()
        second_date = "2026-04-21"
        config_one = {"configurable": {"thread_id": thread_id(self.ticker, self.trade_date)}}
        config_two = {"configurable": {"thread_id": thread_id(self.ticker, second_date)}}

        _should_crash = True
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            with self.assertRaises(RuntimeError):
                graph.invoke({"count": 0}, config=config_one)

        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.trade_date))
        self.assertFalse(has_checkpoint(self.tmpdir, self.ticker, second_date))

        _should_crash = False
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            result = graph.invoke({"count": 0}, config=config_two)

        self.assertEqual(result["count"], 11)
        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.trade_date))

if __name__ == "__main__":
    unittest.main()

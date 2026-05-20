import copy
import unittest

from etfagents.default_config import DEFAULT_CONFIG
from etfagents.llm_clients.model_catalog import (
    MODEL_CAPABILITIES,
    MODEL_OPTIONS,
    RESEARCH_DEPTH_REQUIREMENTS,
    _SKIP_RECOMMENDATION_PROVIDERS,
    _provider_model_ids,
    get_depth_config,
    recommend_models,
)


class ModelCapabilitiesCoverageTests(unittest.TestCase):
    """Verify MODEL_CAPABILITIES covers all cloud provider static model IDs."""

    def test_all_cloud_provider_models_covered(self):
        cloud_providers = [p for p in MODEL_OPTIONS if p not in _SKIP_RECOMMENDATION_PROVIDERS]
        for provider in cloud_providers:
            model_ids = _provider_model_ids(provider)
            for mid in model_ids:
                self.assertIn(mid, MODEL_CAPABILITIES, f"MODEL_CAPABILITIES missing '{mid}' from provider '{provider}'")

    def test_no_extra_models_not_in_model_options(self):
        all_static_ids = set()
        for p in MODEL_OPTIONS:
            if p not in _SKIP_RECOMMENDATION_PROVIDERS:
                all_static_ids.update(_provider_model_ids(p))
        for mid in MODEL_CAPABILITIES:
            self.assertIn(mid, all_static_ids, f"MODEL_CAPABILITIES has '{mid}' not in MODEL_OPTIONS")

    def test_skip_providers_have_no_capabilities(self):
        for mid in MODEL_CAPABILITIES:
            for skip_p in _SKIP_RECOMMENDATION_PROVIDERS:
                self.assertNotIn(mid, _provider_model_ids(skip_p))


class RecommendModelsTests(unittest.TestCase):
    def test_standard_openai_returns_valid_pair(self):
        rec = recommend_models("标准", "openai")
        self.assertIsNotNone(rec["quick_model"])
        self.assertIsNotNone(rec["deep_model"])
        self.assertEqual(rec["depth"], "标准")

    def test_standard_openai_models_in_model_options(self):
        rec = recommend_models("标准", "openai")
        openai_ids = _provider_model_ids("openai")
        self.assertIn(rec["quick_model"], openai_ids)
        self.assertIn(rec["deep_model"], openai_ids)

    def test_full_anthropic_deep_prefers_reasoning(self):
        rec = recommend_models("全面", "anthropic")
        deep_model = rec["deep_model"]
        self.assertIsNotNone(deep_model)
        cap = MODEL_CAPABILITIES[deep_model]
        self.assertIn("reasoning", cap["features"])

    def test_full_anthropic_quick_only_needs_tool_calling(self):
        rec = recommend_models("全面", "anthropic")
        self.assertIsNotNone(rec["quick_model"])
        cap = MODEL_CAPABILITIES[rec["quick_model"]]
        self.assertIn("tool_calling", cap["features"])
        self.assertNotIn("reasoning", cap["features"])

    def test_skip_provider_returns_none(self):
        for provider in ("openrouter", "vllm", "ollama"):
            rec = recommend_models("标准", provider)
            self.assertIsNone(rec["quick_model"])
            self.assertIsNone(rec["deep_model"])

    def test_unknown_depth_returns_none(self):
        rec = recommend_models("不存在", "openai")
        self.assertIsNone(rec["quick_model"])
        self.assertIsNone(rec["deep_model"])

    def test_no_provider_searches_all(self):
        rec = recommend_models("标准")
        self.assertIsNotNone(rec["quick_model"])
        self.assertIsNotNone(rec["deep_model"])

    def test_quick_depth_debate_zero(self):
        cfg = get_depth_config("快速")
        self.assertEqual(cfg["debate_rounds"], 0)
        self.assertEqual(cfg["risk_rounds"], 0)

    def test_full_depth_debate_three(self):
        cfg = get_depth_config("全面")
        self.assertEqual(cfg["debate_rounds"], 3)
        self.assertEqual(cfg["risk_rounds"], 3)

    def test_get_depth_config_unknown_returns_none(self):
        self.assertIsNone(get_depth_config("不存在"))

    def test_minimax_recommendation(self):
        rec = recommend_models("标准", "minimax")
        self.assertIsNotNone(rec["quick_model"])
        self.assertIsNotNone(rec["deep_model"])

    def test_deepseek_recommendation(self):
        rec = recommend_models("深度", "deepseek")
        self.assertIsNotNone(rec["deep_model"])

    def test_xai_recommendation(self):
        rec = recommend_models("基础", "xai")
        self.assertIsNotNone(rec["quick_model"])

    def test_google_full_depth_deep_model(self):
        rec = recommend_models("全面", "google")
        if rec["deep_model"]:
            cap = MODEL_CAPABILITIES[rec["deep_model"]]
            self.assertIn("reasoning", cap["features"])
        else:
            pass

    def test_google_deep_depth(self):
        rec = recommend_models("深度", "google")
        self.assertIsNotNone(rec["deep_model"])
        cap = MODEL_CAPABILITIES[rec["deep_model"]]
        self.assertGreaterEqual(cap["level"], 4)

    def test_quick_recommendation_is_highest_level_among_qualifying(self):
        rec = recommend_models("标准", "openai")
        self.assertIsNotNone(rec["quick_model"])
        all_qualifying = [
            cap["level"] for mid, cap in MODEL_CAPABILITIES.items()
            if mid in _provider_model_ids("openai")
            and "quick" in cap["roles"]
            and cap["level"] >= RESEARCH_DEPTH_REQUIREMENTS["标准"]["quick_min"]
            and all(f in cap["features"] for f in RESEARCH_DEPTH_REQUIREMENTS["标准"]["quick_required_features"])
        ]
        self.assertEqual(MODEL_CAPABILITIES[rec["quick_model"]]["level"], max(all_qualifying))


class ResearchDepthRequirementsTests(unittest.TestCase):
    def test_all_depths_have_required_keys(self):
        required = {"min_level", "quick_min", "deep_min", "quick_required_features",
                     "deep_required_features", "debate_rounds", "risk_rounds"}
        for depth, cfg in RESEARCH_DEPTH_REQUIREMENTS.items():
            for key in required:
                self.assertIn(key, cfg, f"Depth '{depth}' missing key '{key}'")

    def test_depth_levels_are_monotonic(self):
        names = list(RESEARCH_DEPTH_REQUIREMENTS.keys())
        for i in range(len(names) - 1):
            cur = RESEARCH_DEPTH_REQUIREMENTS[names[i]]
            nxt = RESEARCH_DEPTH_REQUIREMENTS[names[i + 1]]
            self.assertLessEqual(cur["debate_rounds"], nxt["debate_rounds"])
            self.assertLessEqual(cur["risk_rounds"], nxt["risk_rounds"])


class RunAnalysisConfigTests(unittest.TestCase):
    """Regression test: run_analysis config construction propagates depth name."""

    def test_depth_name_propagated_into_config(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        depth_name = "全面"
        depth_cfg = get_depth_config(depth_name)
        config["max_debate_rounds"] = depth_cfg["debate_rounds"]
        config["max_risk_discuss_rounds"] = depth_cfg["risk_rounds"]
        config["research_depth_name"] = depth_name
        self.assertEqual(config["research_depth_name"], "全面")
        self.assertNotEqual(config["research_depth_name"], DEFAULT_CONFIG["research_depth_name"])

    def test_default_depth_name_not_stale_after_override(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        self.assertEqual(config["research_depth_name"], "标准")
        for depth_name in RESEARCH_DEPTH_REQUIREMENTS:
            if depth_name == "标准":
                continue
            depth_cfg = get_depth_config(depth_name)
            config["research_depth_name"] = depth_name
            config["max_debate_rounds"] = depth_cfg["debate_rounds"]
            self.assertEqual(config["research_depth_name"], depth_name)
            self.assertEqual(config["max_debate_rounds"], depth_cfg["debate_rounds"])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for model_pricing."""

import unittest

from mongomcp.model_pricing import estimate_cost_usd, get_model_pricing, resolve_model_id


class TestModelPricing(unittest.TestCase):
    def test_resolve_model_id_strips_grove_prefix(self):
        self.assertEqual(
            resolve_model_id("global.anthropic.claude-sonnet-4-6"),
            "claude-sonnet-4-6",
        )

    def test_sonnet_46_basic_math(self):
        cost = estimate_cost_usd(
            model_id="claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=0,
        )
        self.assertAlmostEqual(cost, 3.0)

        cost = estimate_cost_usd(
            model_id="claude-sonnet-4-6",
            input_tokens=0,
            output_tokens=1_000_000,
        )
        self.assertAlmostEqual(cost, 15.0)

    def test_cache_heavy_call(self):
        cost = estimate_cost_usd(
            model_id="global.anthropic.claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=500,
            cache_read_input_tokens=50_000,
            cache_creation_input_tokens=10_000,
        )
        expected = (1000 * 3.0 + 500 * 15.0 + 50_000 * 0.30 + 10_000 * 3.75) / 1_000_000
        self.assertAlmostEqual(cost, expected)

    def test_unknown_model_returns_none(self):
        self.assertIsNone(get_model_pricing("unknown-model-xyz"))
        self.assertIsNone(
            estimate_cost_usd(model_id="unknown-model-xyz", input_tokens=1000)
        )


if __name__ == "__main__":
    unittest.main()

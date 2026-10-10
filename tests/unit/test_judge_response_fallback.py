from __future__ import annotations

import unittest
from unittest.mock import patch
from verifier_trans.agents import judge as judge_module
from verifier_trans.model_clients.base import ModelResponse


class JudgeResponseFallbackTests(unittest.TestCase):
    def test_parser_extracts_verdict_from_wrapped_multi_object_response(self) -> None:
        result = judge_module._parse_json(
            "analysis: {\"note\":\"ignored\"}\n"
            "```json\n{\"verdict\":\"PASS\",\"findings\":[]}\n```"
        )
        self.assertEqual(result["verdict"], "PASS")

    def test_parser_prefers_last_verdict_object(self) -> None:
        result = judge_module._parse_json(
            "{\"verdict\":\"REPAIR\"}\n"
            "{\"verdict\":\"PASS\",\"findings\":[]}"
        )
        self.assertEqual(result["verdict"], "PASS")

    def test_parser_accepts_split_semantic_schema_without_verdict(self) -> None:
        result = judge_module._parse_json(
            "{\"findings\":[],\"mapping_gaps\":[]}\n"
            "{\"note\":\"provider trailer\"}"
        )
        self.assertEqual(result["findings"], [])

    def test_reasoning_content_is_used_when_content_is_empty(self) -> None:
        response = ModelResponse(
            content="",
            reasoning_content='{"verdict":"PASS","findings":[]}',
            raw={"choices": [{"message": {"content": None}}]},
        )
        with patch.object(judge_module, "_client") as client_factory:
            client_factory.return_value.generate.return_value = response
            result = judge_module.judge(
                config={"model": {"backend": "openai_compatible"}},
                credentials={"base_url": "x", "api_key": "x", "model": "x"},
                role="verifier_judge", system="return JSON", evidence={},
            )
        self.assertEqual(result["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)

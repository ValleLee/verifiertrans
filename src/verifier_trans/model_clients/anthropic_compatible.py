"""Minimal Anthropic-compatible messages adapter."""
from __future__ import annotations

from typing import Any

import requests

from .base import ModelResponse, ToolCall


class AnthropicCompatibleClient:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int = 300, max_tokens: int = 8192):
        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/messages"):
            endpoint += "/messages"
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.session = requests.Session()
        self.session.trust_env = False

    def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        system = "\n\n".join(
            str(message.get("content", "")) for message in messages if message["role"] == "system"
        )
        converted = []
        for message in messages:
            if message["role"] == "system":
                continue
            role = "assistant" if message["role"] == "assistant" else "user"
            content = message.get("content", "")
            if message["role"] == "tool":
                content = [{
                    "type": "tool_result",
                    "tool_use_id": message["tool_call_id"],
                    "content": str(content),
                }]
            elif message.get("tool_calls"):
                blocks: list[dict[str, Any]] = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for call in message["tool_calls"]:
                    fn = call["function"]
                    import json
                    blocks.append({
                        "type": "tool_use", "id": call["id"], "name": fn["name"],
                        "input": json.loads(fn.get("arguments") or "{}"),
                    })
                content = blocks
            converted.append({"role": role, "content": content})
        response = self.session.post(
            self.endpoint,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": self.model, "system": system, "messages": converted,
                "tools": tools, "max_tokens": self.max_tokens, "temperature": 0,
            },
            timeout=self.timeout,
        )
        if not response.ok:
            raise RuntimeError(f"model API returned HTTP {response.status_code}: {response.text[:2000]}")
        doc = response.json()
        text_parts = []
        calls = []
        for block in doc.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(ToolCall(block["id"], block["name"], block.get("input") or {}))
        return ModelResponse("\n".join(text_parts), calls, doc)

"""Minimal OpenAI-compatible chat-completions adapter."""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from .base import ModelResponse, ToolCall


MAX_REQUEST_CHARS = 700_000
MAX_MESSAGE_CHARS = 100_000


def _clip(value: Any, limit: int = MAX_MESSAGE_CHARS) -> Any:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    head = limit // 2
    return value[:head] + "\n...[message clipped]...\n" + value[-(limit - head):]


def _bounded_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for message in messages:
        item = dict(message)
        if "content" in item:
            item["content"] = _clip(item["content"])
        prepared.append(item)
    if len(json.dumps(prepared, ensure_ascii=False)) <= MAX_REQUEST_CHARS:
        return prepared

    prefix = prepared[:2]
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for message in prepared[2:]:
        if message.get("role") == "assistant" and current:
            groups.append(current)
            current = []
        current.append(message)
    if current:
        groups.append(current)

    kept: list[list[dict[str, Any]]] = []
    size = len(json.dumps(prefix, ensure_ascii=False))
    for group in reversed(groups):
        group_size = len(json.dumps(group, ensure_ascii=False))
        if kept and size + group_size > MAX_REQUEST_CHARS:
            break
        if not kept and size + group_size > MAX_REQUEST_CHARS:
            continue
        kept.append(group)
        size += group_size
    return prefix + [item for group in reversed(kept) for item in group]


class OpenAICompatibleClient:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int = 300, max_tokens: int = 8192):
        endpoint = base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.session = requests.Session()
        self.session.trust_env = False

    def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": _bounded_messages(messages),
            "tools": [{"type": "function", "function": item} for item in tools],
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = None
        for attempt in range(6):
            response = self.session.post(
                self.endpoint, headers=headers, json=payload, timeout=self.timeout,
            )
            if response.status_code != 429 or attempt == 5:
                break
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2 ** attempt
            except ValueError:
                delay = 2 ** attempt
            time.sleep(max(1.0, min(30.0, delay)))
        if not response.ok:
            body = response.text[:2000]
            raise RuntimeError(f"model API returned HTTP {response.status_code}: {body}")
        doc = response.json()
        message = doc["choices"][0]["message"]
        calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"model emitted invalid tool JSON: {raw_arguments!r}") from exc
            calls.append(ToolCall(call["id"], function["name"], arguments))
        return ModelResponse(
            message.get("content") or "", calls, doc,
            message.get("reasoning_content") or "",
        )

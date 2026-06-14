"""
LLM Client Abstraction Layer.

Provides a unified interface for communicating with LLMs regardless of provider.
Supports two backends:
  - "ollama"        : Local inference via Ollama (default for development)
  - "azure_foundry" : Microsoft Foundry (Azure AI) via OpenAI-compatible SDK

The active provider is selected by the LLM_PROVIDER environment variable.
"""

import os
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import ollama


@dataclass
class ToolCall:
    """Normalized tool call from any LLM provider."""
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol defining the LLM client interface."""

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        """Send messages and optional tools, return a normalized response."""
        ...

    async def health_check(self) -> dict:
        """Check connectivity and model availability."""
        ...


class OllamaLLMClient:
    """LLM client backed by a local Ollama instance."""

    def __init__(self):
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")
        self.client = ollama.AsyncClient(host=self.host)

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        response = await self.client.chat(
            model=self.model,
            messages=messages,
            tools=tools if tools else None,
        )
        message = response.message
        content = getattr(message, "content", "") or ""
        raw_tool_calls = getattr(message, "tool_calls", None) or []

        tool_calls = []
        for tc in raw_tool_calls:
            tool_calls.append(ToolCall(name=tc.function.name, arguments=tc.function.arguments))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw=message.model_dump() if hasattr(message, "model_dump") else dict(message),
        )

    async def health_check(self) -> dict:
        try:
            models_response = await self.client.list()
            available = [m.model for m in models_response.models]
            model_found = any(self.model in m for m in available)
            return {
                "status": "connected",
                "provider": "ollama",
                "host": self.host,
                "model": self.model,
                "model_available": model_found,
                "available_models": available,
            }
        except Exception as exc:
            return {"status": "unreachable", "provider": "ollama", "host": self.host, "error": str(exc)}


class FoundryLLMClient:
    """LLM client backed by Microsoft Foundry (Azure AI) via OpenAI SDK."""

    def __init__(self):
        self.endpoint = os.environ.get("FOUNDRY_ENDPOINT", "")
        self.model = os.environ.get("FOUNDRY_MODEL", "gpt-4.1-nano")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncAzureOpenAI
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=os.environ.get("FOUNDRY_API_KEY", ""),
                api_version="2024-12-01-preview",
            )
        return self._client

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        client = self._get_client()

        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools

        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        content = message.content or ""

        tool_calls = []
        if message.tool_calls:
            import json
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    args = json.loads(args)
                tool_calls.append(ToolCall(name=tc.function.name, arguments=args))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw={"role": "assistant", "content": content, "tool_calls": message.tool_calls},
        )

    async def health_check(self) -> dict:
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return {
                "status": "connected",
                "provider": "azure_foundry",
                "endpoint": self.endpoint,
                "model": self.model,
            }
        except Exception as exc:
            return {
                "status": "unreachable",
                "provider": "azure_foundry",
                "endpoint": self.endpoint,
                "error": str(exc),
            }


def get_llm_client() -> LLMClient:
    """Factory function returning the configured LLM client."""
    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
    if provider == "azure_foundry":
        return FoundryLLMClient()
    return OllamaLLMClient()

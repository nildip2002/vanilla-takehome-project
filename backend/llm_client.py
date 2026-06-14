"""
LLM Client Abstraction Layer.

Provides a unified interface for communicating with LLMs regardless of provider.
Supports four backends:
  - "ollama"        : Local inference via Ollama (default for development)
  - "azure_foundry" : Microsoft Foundry (Azure AI) via OpenAI-compatible SDK
  - "openai"        : OpenAI API directly (api.openai.com)
  - "github_models" : GitHub Models (free, uses GitHub PAT, OpenAI-compatible)

The active provider is selected by the LLM_PROVIDER environment variable.

Environment variables per provider:
  ollama:         OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_NUM_GPU
  azure_foundry:  FOUNDRY_ENDPOINT, FOUNDRY_API_KEY, FOUNDRY_MODEL
  openai:         OPENAI_API_KEY, OPENAI_MODEL (default: gpt-4o-mini)
  github_models:  GITHUB_TOKEN, OPENAI_MODEL (default: gpt-4o-mini)
                  Endpoint: https://models.inference.ai.azure.com (automatic)

Note: "openai" also supports OPENAI_BASE_URL to point at any OpenAI-compatible
endpoint (GitHub Models, Groq, Mistral, local vLLM, etc).
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
    id: str | None = None  # tool_call_id required by OpenAI-spec providers


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
        # num_gpu: -1 = Ollama decides (default), 0 = force CPU-only
        # Set OLLAMA_NUM_GPU=0 to bypass CUDA issues on incompatible drivers
        num_gpu_env = os.environ.get("OLLAMA_NUM_GPU", "-1")
        self._num_gpu = int(num_gpu_env) if num_gpu_env.lstrip("-").isdigit() else -1

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResponse:
        options = {}
        if self._num_gpu >= 0:
            options["num_gpu"] = self._num_gpu

        response = await self.client.chat(
            model=self.model,
            messages=messages,
            tools=tools if tools else None,
            options=options if options else None,
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
                tool_calls.append(ToolCall(name=tc.function.name, arguments=args, id=tc.id))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw={
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                            if isinstance(tc.function.arguments, str)
                            else json.dumps(tc.function.arguments),
                        },
                    }
                    for tc in (message.tool_calls or [])
                ] or None,
            },
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


class OpenAILLMClient:
    """
    LLM client backed by the standard OpenAI API or any OpenAI-compatible endpoint.

    Supports:
      - OpenAI directly:  OPENAI_API_KEY + optional OPENAI_BASE_URL
      - GitHub Models:    use LLM_PROVIDER=github_models (sets endpoint automatically)
      - Groq/Mistral/etc: set OPENAI_BASE_URL to their OpenAI-compatible endpoint

    Model defaults to gpt-4o-mini; override with OPENAI_MODEL.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL") or None
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            kwargs = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs)
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
                tool_calls.append(ToolCall(name=tc.function.name, arguments=args, id=tc.id))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            raw={
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                            if isinstance(tc.function.arguments, str)
                            else json.dumps(tc.function.arguments),
                        },
                    }
                    for tc in (message.tool_calls or [])
                ] or None,
            },
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
                "provider": "openai",
                "model": self.model,
            }
        except Exception as exc:
            return {
                "status": "unreachable",
                "provider": "openai",
                "model": self.model,
                "error": str(exc),
            }


def get_llm_client() -> LLMClient:
    """Factory function returning the configured LLM client."""
    provider = os.environ.get("LLM_PROVIDER", "ollama").lower()
    if provider == "azure_foundry":
        return FoundryLLMClient()
    if provider == "openai":
        return OpenAILLMClient()
    if provider == "github_models":
        # GitHub Models: free OpenAI-compatible API backed by your GitHub PAT.
        # Supports gpt-4o, gpt-4o-mini, Llama, Mistral and many more.
        # Rate limit: 150 premium requests / day on free tier.
        # Get a PAT at: https://github.com/settings/tokens (no special scopes needed)
        github_token = os.environ.get("GITHUB_TOKEN", "")
        return OpenAILLMClient(
            api_key=github_token,
            base_url="https://models.inference.ai.azure.com",
        )
    return OllamaLLMClient()

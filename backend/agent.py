"""
Agent Controller — ReAct Loop Implementation.

Implements the Reasoning + Acting (ReAct) orchestration loop that:
1. Fetches available tools from the MCP server
2. Iteratively consults the LLM (Ollama or Azure Foundry)
3. Executes tool calls through the MCP client
4. Streams every reasoning step back to the caller via SSE events
5. Persists all execution traces to the database

The maximum reasoning depth is bounded to prevent infinite loops.
Retry logic with exponential backoff handles transient LLM/tool failures.
"""

import asyncio
import json
import logging
import os
from typing import AsyncGenerator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from sse_starlette.sse import ServerSentEvent

from llm_client import LLMResponse, get_llm_client
from repository import Repository

logger = logging.getLogger(__name__)

MCP_SERVER_PATH = os.environ.get(
    "MCP_SERVER_PATH",
    os.path.join(os.path.dirname(__file__), "..", "mcp_server", "mcp_server.py"),
)
MAX_REACT_ITERATIONS = int(os.environ.get("MAX_REACT_ITERATIONS", "10"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.environ.get("RETRY_BASE_DELAY", "1.0"))

SYSTEM_PROMPT = (
    "You are a helpful agent with access to tools. "
    "When the user asks you to do something, select the appropriate tool and use it. "
    "If you can answer directly without a tool, do so. "
    "Always explain your reasoning step by step."
)


async def _retry_with_backoff(coro_fn, max_retries: int = MAX_RETRIES, base_delay: float = RETRY_BASE_DELAY):
    """Execute an async callable with exponential backoff on failure."""
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except Exception as exc:
            last_exception = exc
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt + 1, max_retries + 1, exc, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("All %d attempts exhausted", max_retries + 1)
    raise last_exception


async def check_llm_health() -> dict:
    """Check LLM connectivity (Ollama or Foundry depending on config)."""
    client = get_llm_client()
    return await client.health_check()


def _build_tools_schema(mcp_tools) -> list[dict]:
    """Convert MCP tool definitions into OpenAI-compatible function-calling schema."""
    tools = []
    for t in mcp_tools.tools:
        properties = {}
        required = []
        for prop_name, prop_schema in t.inputSchema.get("properties", {}).items():
            properties[prop_name] = prop_schema
            if prop_name in t.inputSchema.get("required", []):
                required.append(prop_name)

        tools.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return tools


def _emit_trace(repo: Repository, task_id: str, step: int, category: str, content: str) -> ServerSentEvent:
    """Persist a trace row and return a corresponding SSE event."""
    repo.create_trace(task_id, step, category, content)
    event_type = "final_result" if category == "final_result" else "trace_update"
    return ServerSentEvent(
        data=json.dumps({"step": step, "type": category, "content": content}),
        event=event_type,
    )


async def execute_task(task_id: str, raw_input: str, repo: Repository) -> AsyncGenerator[ServerSentEvent, None]:
    """
    Run the full ReAct loop for a given task, yielding SSE events.

    Uses the configured LLM client (Ollama or Foundry) and persists
    all traces through the repository abstraction.
    """
    repo.update_task(task_id, execution_status="running")
    step_counter = 0

    yield _emit_trace(repo, task_id, step_counter, "thought", f'Received task: "{raw_input}"')
    step_counter += 1

    server_params = StdioServerParameters(command="python", args=[MCP_SERVER_PATH])
    llm_client = get_llm_client()

    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as mcp_session:
                await mcp_session.initialize()

                mcp_tools = await mcp_session.list_tools()
                tools_schema = _build_tools_schema(mcp_tools)

                tool_names = [t["function"]["name"] for t in tools_schema]
                yield _emit_trace(
                    repo, task_id, step_counter, "thought",
                    f"Discovered tools: {', '.join(tool_names)}",
                )
                step_counter += 1

                messages: list[dict] = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": raw_input},
                ]

                for iteration in range(MAX_REACT_ITERATIONS):
                    try:
                        response: LLMResponse = await _retry_with_backoff(
                            lambda: llm_client.chat(messages, tools_schema if tools_schema else None),
                            max_retries=MAX_RETRIES,
                            base_delay=RETRY_BASE_DELAY,
                        )
                    except Exception as exc:
                        logger.exception("LLM inference failed after %d retries", MAX_RETRIES)
                        yield _emit_trace(
                            repo, task_id, step_counter, "tool_error",
                            f"LLM inference error (after {MAX_RETRIES} retries): {exc}",
                        )
                        step_counter += 1
                        repo.update_task(task_id, execution_status="failed", final_output=f"Error: {exc}")
                        yield _emit_trace(repo, task_id, step_counter, "final_result", f"Error: {exc}")
                        return

                    messages.append(response.raw)

                    if response.content:
                        yield _emit_trace(repo, task_id, step_counter, "thought", response.content)
                        step_counter += 1

                    if response.tool_calls:
                        for tc in response.tool_calls:
                            yield _emit_trace(
                                repo, task_id, step_counter, "tool_call",
                                f"Calling {tc.name}({json.dumps(tc.arguments)})",
                            )
                            step_counter += 1

                            try:
                                tool_result = await _retry_with_backoff(
                                    lambda tn=tc.name, ta=tc.arguments: mcp_session.call_tool(tn, ta),
                                    max_retries=2,
                                    base_delay=0.5,
                                )
                                text_results = [
                                    c.text for c in tool_result.content
                                    if getattr(c, "type", "") == "text"
                                ]
                                result_str = "\n".join(text_results) or str(tool_result.content)
                            except Exception as tool_exc:
                                logger.exception("Tool %s failed after retries", tc.name)
                                result_str = f"Tool execution error: {tool_exc}"
                                yield _emit_trace(repo, task_id, step_counter, "tool_error", result_str)
                                step_counter += 1
                                messages.append({"role": "tool", "content": result_str})
                                continue

                            messages.append({"role": "tool", "content": result_str})
                            yield _emit_trace(
                                repo, task_id, step_counter, "tool_result",
                                f"{tc.name} → {result_str}",
                            )
                            step_counter += 1
                    else:
                        final_answer = response.content or "(no content)"
                        repo.update_task(task_id, execution_status="completed", final_output=final_answer)
                        yield _emit_trace(repo, task_id, step_counter, "final_result", final_answer)
                        return

                repo.update_task(
                    task_id,
                    execution_status="failed",
                    final_output="Agent exceeded maximum reasoning depth.",
                )
                yield _emit_trace(
                    repo, task_id, step_counter, "final_result",
                    "Agent exceeded maximum reasoning depth.",
                )

    except Exception as exc:
        logger.exception("Unhandled error in agent loop")
        repo.update_task(task_id, execution_status="failed", final_output=f"Internal error: {exc}")
        yield _emit_trace(repo, task_id, step_counter, "final_result", f"Internal error: {exc}")

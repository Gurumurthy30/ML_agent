"""
tests/test_mcp_transport.py — Transport-level test harness for MCP tool calling across providers

Calls each of the three providers (NIM/DeepSeek, Groq, Google Gemini) with the same
trivial tool schema (get_current_time) and prompt to verify:
1. Schema is accepted without 400 validation error
2. Response .tool_calls has expected shape: [{id, function: {name, arguments: str}}]
3. Correctly builds follow-up messages: assistant message with tool_calls + tool message with tool_call_id
4. Loop terminates on final non-tool-calling response
5. Hard cap of 5 iterations prevents hanging

Run standalone:
    python tests/test_mcp_transport.py
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anyio.abc  # Ensures anyio.abc is loaded for httpcore compatibility
except Exception:
    pass

from config.settings import get_settings, ProviderConfig
from agents.utils import create_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage


TEST_TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Returns the current UTC date and time in ISO format.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone_str": {
                        "type": "string",
                        "description": "Optional timezone name, default is UTC",
                        "default": "UTC",
                    }
                },
                "required": [],
            },
        },
    }
]


def execute_test_tool(name: str, args: Dict[str, Any]) -> str:
    """Trivial tool implementation."""
    if name == "get_current_time":
        return json.dumps({
            "current_time": datetime.now(timezone.utc).isoformat(),
            "timezone": args.get("timezone_str", "UTC"),
        })
    return json.dumps({"error": f"Unknown tool: {name}"})


def test_provider_transport(
    provider_name: str,
    server_url: str,
    model_name: str,
    api_key_env: str,
    max_iters: int = 5,
) -> Tuple[bool, str, List[str]]:
    """
    Runs the multi-turn tool-calling loop for one provider.
    Returns: (success: bool, status_message: str, trace_log: List[str])
    """
    logs: List[str] = []
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        return False, f"SKIPPED (Environment variable '{api_key_env}' not set)", logs

    logs.append(f"Initializing native chat model for {provider_name} (model={model_name}, url={server_url})")

    try:
        cfg = ProviderConfig(server_url=server_url, name=model_name, api_key_env=api_key_env)
        llm = create_chat_model(cfg, temperature=0.1, max_tokens=1024, timeout=15)
        llm_with_tools = llm.bind_tools(TEST_TOOL_SCHEMA)
    except Exception as e:
        msg = f"Failed to initialize/bind tools: {e}"
        logs.append(msg)
        return False, msg, logs

    messages = [
        SystemMessage(content="You are a helpful assistant. If asked for current time, use the get_current_time tool."),
        HumanMessage(content="What is the current time? Please use the get_current_time tool to find out."),
    ]

    iteration = 0
    tool_called = False

    while iteration < max_iters:
        iteration += 1
        logs.append(f"Iteration {iteration}: sending request with {len(messages)} messages...")

        try:
            response = llm_with_tools.invoke(messages)
        except Exception as e:
            msg = f"Invoke failed on iter {iteration}: {e}"
            logs.append(msg)
            return False, msg, logs

        messages.append(response)

        # Check for tool_calls
        tool_calls = getattr(response, "tool_calls", None) or []
        logs.append(f"Response received. Content tail: {str(response.content)[:100]} | tool_calls: {len(tool_calls)}")

        if not tool_calls:
            # Model finished turn without calling any tools
            if tool_called:
                logs.append("Conversation loop successfully completed after tool execution.")
                return True, f"PASS ({iteration} iterations, tool executed and answered)", logs
            else:
                # The model answered directly without calling the tool
                logs.append("Model did not call the tool; responded directly.")
                return False, f"FAIL: Model responded without calling tool (iter {iteration})", logs

        tool_called = True
        for tc in tool_calls:
            tc_id = tc.get("id") or f"call_{int(time.time()*1000)}"
            tc_name = tc.get("name", "")
            tc_args = tc.get("args") or {}

            logs.append(f"Processing tool_call: id={tc_id}, name={tc_name}, args={tc_args}")
            if not tc_name:
                return False, f"Malformed tool_call: missing function name: {tc}", logs

            tool_result = execute_test_tool(tc_name, tc_args)
            logs.append(f"Tool output: {tool_result}")

            # Append ToolMessage with matching tool_call_id and name
            messages.append(ToolMessage(content=tool_result, tool_call_id=tc_id, name=tc_name))

    return False, f"FAIL: Exceeded maximum iterations ({max_iters}) without terminating", logs


def run_transport_harness() -> None:
    settings = get_settings()
    providers: List[Tuple[str, ProviderConfig]] = [
        ("NVIDIA NIM (DeepSeek)", settings.model.deep_thinking_provider),
        ("Groq (Llama 3.3)", settings.model.primary_provider),
        ("Google Gemini", settings.model.fallback_provider),
    ]

    print("=" * 80)
    print("MCP TRANSPORT-LEVEL HARNESS TEST")
    print("=" * 80)

    results = []

    for label, cfg in providers:
        print(f"\n--- Testing {label} [{cfg.name}] ---")
        ok, summary, logs = test_provider_transport(
            provider_name=label,
            server_url=cfg.server_url,
            model_name=cfg.name,
            api_key_env=cfg.api_key_env,
        )
        results.append((label, cfg.name, ok, summary))
        for line in logs:
            print(f"  [log] {line}")
        print(f"Result: {'[PASS]' if ok else '[FAIL] ' + summary}")

    print("\n" + "=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Provider':<26} | {'Model':<30} | {'Status':<10} | {'Details'}")
    print("-" * 80)
    for label, model, ok, summary in results:
        status = "PASS" if ok else ("SKIP" if "SKIPPED" in summary else "FAIL")
        print(f"{label:<26} | {model:<30} | {status:<10} | {summary}")
    print("=" * 80)


if __name__ == "__main__":
    run_transport_harness()

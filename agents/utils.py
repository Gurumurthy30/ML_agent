"""
agents/utils.py — Role-based LLM router + utility functions

call_llm(role, system_prompt, user_prompt, ...) routes to the correct provider:
  coder, planner_default → Groq primary / Google fallback
  planner_deep, selector → NVIDIA NIM (DeepSeek V3)

Also:
- Detects real thinking traces (DeepSeek V3 returns reasoning_content or <think> blocks)
- Supports --dry-run mode (returns canned responses without API calls)
- Tracks per-provider usage for rate-limit awareness, fails over on 429s
"""

import os
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import anyio.abc
except Exception:
    pass

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from config.settings import get_settings


# ─────────────────────────────────────────────────────────────────────────────
# Simple in-memory usage tracker for rate-limit failover
# ─────────────────────────────────────────────────────────────────────────────

class _UsageTracker:
    """Tracks call counts and last-429 timestamp per provider name."""
    def __init__(self):
        self._counts: Dict[str, int] = {}
        self._last_429: Dict[str, float] = {}
        self._cooldown_seconds = 60.0  # don't retry a 429'd provider for 60s

    def record_call(self, provider_name: str):
        self._counts[provider_name] = self._counts.get(provider_name, 0) + 1

    def record_429(self, provider_name: str):
        self._last_429[provider_name] = time.time()
        print(f"[LLM Router] Rate-limited (429) on {provider_name}. Failing over.")

    def is_cooling_down(self, provider_name: str) -> bool:
        last = self._last_429.get(provider_name)
        if last is None:
            return False
        return (time.time() - last) < self._cooldown_seconds

    def stats(self) -> Dict[str, Any]:
        return {"call_counts": dict(self._counts), "cooling_down": {
            k: True for k in self._last_429 if self.is_cooling_down(k)
        }}


_tracker = _UsageTracker()


# ─────────────────────────────────────────────────────────────────────────────
# Provider invocation
# ─────────────────────────────────────────────────────────────────────────────

def create_chat_model(provider_config, temperature: float, max_tokens: int, timeout: int = 90):
    """
    Instantiates the appropriate native LangChain chat model based on provider_config.
    - Google Gemini: ChatGoogleGenerativeAI
    - Groq: ChatGroq
    - NVIDIA NIM: ChatNVIDIA
    - Fallback: ChatOpenAI
    """
    server_url = (getattr(provider_config, "server_url", "") or "").lower()
    api_key_env = getattr(provider_config, "api_key_env", "")
    api_key = os.environ.get(api_key_env, "").strip() if api_key_env else ""
    model_name = getattr(provider_config, "name", "")

    # 1. Google Gemini native integration
    if "generativelanguage.googleapis.com" in server_url or "google" in api_key_env.lower() or "gemini" in model_name:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key or os.environ.get("GOOGLE_API_KEY"),
                temperature=temperature,
                max_output_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as e:
            print(f"[LLM Factory] Could not use ChatGoogleGenerativeAI: {e}. Falling back.")

    # 2. Groq native integration
    if "api.groq.com" in server_url or "groq" in api_key_env.lower():
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model_name=model_name,
                groq_api_key=api_key or os.environ.get("GROQ_API_KEY"),
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as e:
            print(f"[LLM Factory] Could not use ChatGroq: {e}. Falling back.")

    # 3. NVIDIA NIM native integration
    if "api.nvidia.com" in server_url or "nvidia" in api_key_env.lower():
        try:
            from langchain_nvidia_ai_endpoints import ChatNVIDIA
            return ChatNVIDIA(
                model=model_name,
                api_key=api_key or os.environ.get("NVIDIA_API_KEY"),
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        except Exception as e:
            print(f"[LLM Factory] Could not use ChatNVIDIA: {e}. Falling back.")

    # 4. Standard OpenAI-compatible client
    return ChatOpenAI(
        base_url=provider_config.server_url,
        api_key=api_key or "not-needed",
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def _invoke_provider(
    provider_config,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    tools: Optional[List[Any]] = None,
    tool_executor: Optional[Callable[[str, Dict[str, Any]], str]] = None,
) -> Tuple[str, bool]:
    """
    Calls one provider using its native integration. Returns (response_text, has_thinking_trace).
    If tools is provided, runs a multi-turn tool-calling loop (hard-capped at 5 iterations).
    """
    llm = create_chat_model(provider_config, temperature, max_tokens)

    if not tools:
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])

        content = response.content or ""
        has_thinking = False

        if hasattr(response, "additional_kwargs"):
            if response.additional_kwargs.get("reasoning_content"):
                has_thinking = True
        if re.search(r"<think>.*?</think>", content, re.DOTALL):
            has_thinking = True
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()

        return content, has_thinking

    # Tool calling mode with agentic loop (hard cap of 5 iterations)
    llm_with_tools = llm.bind_tools(tools)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    has_thinking = False
    for iteration in range(5):
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if hasattr(response, "additional_kwargs"):
            if response.additional_kwargs.get("reasoning_content"):
                has_thinking = True

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            content = response.content or ""
            if re.search(r"<think>.*?</think>", content, re.DOTALL):
                has_thinking = True
                content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
            return content, has_thinking

        # Execute returned tool calls
        for tc in tool_calls:
            tc_id = tc.get("id") or f"call_{int(time.time()*1000)}"
            tc_name = tc.get("name", "")
            tc_args = tc.get("args") or {}

            result_str = ""
            if tool_executor:
                try:
                    result_str = str(tool_executor(tc_name, tc_args))
                except Exception as ex:
                    result_str = json.dumps({"error": f"Tool execution failed: {ex}"})
            else:
                result_str = json.dumps({"status": "received", "name": tc_name, "args": tc_args})

            messages.append(ToolMessage(content=result_str, tool_call_id=tc_id, name=tc_name))

    last_content = messages[-1].content if messages else ""
    return str(last_content), has_thinking


# ─────────────────────────────────────────────────────────────────────────────
# Canned dry-run responses (one per role)
# ─────────────────────────────────────────────────────────────────────────────

_DRY_RUN_RESPONSES = {
    "planner_deep": (
        '{"experiment_id":"exp_001","approach_type":"baseline","model_family":"LightGBM",'
        '"modality":"tabular","reasoning_mode":"tot","approach_rationale":"[DRY-RUN] LightGBM baseline.",'
        '"feature_engineering_notes":"Standard imputation and encoding.",'
        '"hyperparameter_ranges":{"n_estimators":"500","learning_rate":"0.05","max_depth":"6"}}',
        True,   # simulate a thinking trace for dry-run
    ),
    "planner_default": (
        '{"experiment_id":"exp_002","approach_type":"variant","model_family":"XGBoost",'
        '"modality":"tabular","reasoning_mode":"default","approach_rationale":"[DRY-RUN] XGBoost variant.",'
        '"feature_engineering_notes":"Ratio features added.","hyperparameter_ranges":{"n_estimators":"800"}}',
        False,
    ),
    "coder": (
        '```python\nimport pandas as pd\nimport numpy as np\nfrom sklearn.model_selection import StratifiedKFold\n'
        'from sklearn.metrics import roc_auc_score\n\nprint("[DRY-RUN] Running pipeline...")\nprint("CV_MEAN=0.8450")\nprint("CV_STD=0.0052")\n```',
        False,
    ),
    "selector": (
        '{"decision":"redirect","detail":"[DRY-RUN] Results look strong; trying one more variant before converging.",'
        '"methodology_note":"Baseline established. CV stable. Exploring ensemble potential."}',
        True,
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    role: str = "planner_default",
    dry_run: bool = False,
    tools: Optional[List[Any]] = None,
    tool_executor: Optional[Callable[[str, Dict[str, Any]], str]] = None,
) -> Tuple[str, bool]:
    """
    Role-based LLM router.

    Args:
        role: One of "coder", "planner_default", "planner_deep", "selector"
        dry_run: If True, return canned responses without making API calls.
        tools: Optional list of tools (functions or schemas) to bind.
        tool_executor: Optional callable to execute tool calls by (name, args).

    Returns:
        (response_text, has_thinking_trace)
        has_thinking_trace is True ONLY when the provider actually returned
        a reasoning trace — never synthesised.
    """
    if dry_run:
        canned = _DRY_RUN_RESPONSES.get(role, _DRY_RUN_RESPONSES["planner_default"])
        return canned

    settings = get_settings()
    deep_roles = {"planner_deep", "selector"}

    if role in deep_roles:
        # ── Deep thinking: NVIDIA NIM (DeepSeek V3) ──────────────────────────
        dt_cfg = settings.model.deep_thinking_provider
        if _tracker.is_cooling_down(dt_cfg.name):
            print(f"[LLM Router] {dt_cfg.name} is cooling down after 429. Using primary provider as fallback.")
        else:
            try:
                _tracker.record_call(dt_cfg.name)
                print(f"[LLM Router] role={role} → {dt_cfg.name} (NIM DeepSeek)")
                return _invoke_provider(
                    dt_cfg, system_prompt, user_prompt, temperature, max_tokens,
                    tools=tools, tool_executor=tool_executor
                )
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    _tracker.record_429(dt_cfg.name)
                else:
                    print(f"[LLM Router] {dt_cfg.name} failed: {e}. Falling back.")

    # ── Fast path: Groq primary / Google fallback ─────────────────────────
    primary_cfg = settings.model.primary_provider
    if not _tracker.is_cooling_down(primary_cfg.name) and os.environ.get(primary_cfg.api_key_env):
        try:
            _tracker.record_call(primary_cfg.name)
            print(f"[LLM Router] role={role} → {primary_cfg.name} (Groq)")
            return _invoke_provider(
                primary_cfg, system_prompt, user_prompt, temperature, max_tokens,
                tools=tools, tool_executor=tool_executor
            )
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                _tracker.record_429(primary_cfg.name)
            else:
                print(f"[LLM Router] {primary_cfg.name} failed: {e}. Trying fallback.")

    fallback_cfg = settings.model.fallback_provider
    if not _tracker.is_cooling_down(fallback_cfg.name) and os.environ.get(fallback_cfg.api_key_env):
        try:
            _tracker.record_call(fallback_cfg.name)
            print(f"[LLM Router] role={role} → {fallback_cfg.name} (Google Gemini)")
            return _invoke_provider(
                fallback_cfg, system_prompt, user_prompt, temperature, max_tokens,
                tools=tools, tool_executor=tool_executor
            )
        except Exception as e:
            if "429" in str(e) or "rate" in str(e).lower():
                _tracker.record_429(fallback_cfg.name)
            else:
                print(f"[LLM Router] {fallback_cfg.name} failed: {e}.")

    # ── Final fallback: base model config ────────────────────────────────
    base_cfg = settings.model
    try:
        _tracker.record_call(base_cfg.name)
        print(f"[LLM Router] role={role} → {base_cfg.name} (base config)")
        return _invoke_provider(
            base_cfg, system_prompt, user_prompt, temperature, max_tokens,
            tools=tools, tool_executor=tool_executor
        )
    except Exception as e:
        raise RuntimeError(
            f"[LLM ERROR] All providers failed for role={role}: {e}\n"
            "Please ensure NVIDIA_API_KEY, GROQ_API_KEY, or GOOGLE_API_KEY is set."
        ) from e


def get_router_stats() -> Dict[str, Any]:
    """Returns per-provider usage counts and cooldown status."""
    return _tracker.stats()


# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction helper
# ─────────────────────────────────────────────────────────────────────────────

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extracts a JSON dictionary from LLM markdown response."""
    try:
        return json.loads(text)
    except Exception:
        pass

    # Match ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Find raw JSON dict braces
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Event queue helpers
# ─────────────────────────────────────────────────────────────────────────────

def push_event(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    """Appends an event to state's event_queue in-place."""
    if "event_queue" not in state or state["event_queue"] is None:
        state["event_queue"] = []
    state["event_queue"].append(event)
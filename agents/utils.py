"""
agents/utils.py — LLM utilities (minimal skeleton)

Provides:
  - create_chat_model(provider_config) → LangChain chat model
  - call_llm(system_prompt, user_prompt, role) → (response_text, has_thinking)
  - extract_json(text) → dict or None
  - push_event(state, event) → appends to state["event_queue"]
"""

import os
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# TODO: re-add when config is back in place
# from config.settings import get_settings


# ─────────────────────────────────────────────────────────────────────────────
# Chat model factory
# ─────────────────────────────────────────────────────────────────────────────

def create_chat_model(provider_config, temperature: float = 0.2, max_tokens: int = 4096, timeout: int = 90):
    """
    Creates a LangChain chat model from a provider config object.
    Expects provider_config to have: .name, .server_url, .api_key_env
    """
    server_url = getattr(provider_config, "server_url", "") or ""
    api_key_env = getattr(provider_config, "api_key_env", "")
    api_key = os.environ.get(api_key_env, "").strip() if api_key_env else ""
    model_name = getattr(provider_config, "name", "")

    # Google Gemini
    if "google" in api_key_env.lower() or "gemini" in model_name.lower():
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key or os.environ.get("GOOGLE_API_KEY"),
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        except Exception:
            pass

    # Groq
    if "groq" in api_key_env.lower():
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                model_name=model_name,
                groq_api_key=api_key or os.environ.get("GROQ_API_KEY"),
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            pass

    # Fallback: OpenAI-compatible
    return ChatOpenAI(
        base_url=server_url or "https://api.openai.com/v1",
        api_key=api_key or "not-needed",
        model=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Simple LLM call (no streaming, no failover chain)
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(
    system_prompt: str,
    user_prompt: str,
    role: str = "default",
    provider_config=None,
) -> Tuple[str, bool]:
    """
    Calls an LLM with system + user prompt. Returns (response_text, has_thinking).

    TODO: wire up role-based provider routing via config.settings
    """
    if provider_config is None:
        raise ValueError("provider_config is required. Wire up config.settings to resolve by role.")

    llm = create_chat_model(provider_config)
    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    messages.append(HumanMessage(content=user_prompt))

    response = llm.invoke(messages)
    content = response.content if isinstance(response.content, str) else str(response.content)

    # Check for thinking traces
    has_thinking = False
    if re.search(r"<think>.*?</think>", content, re.DOTALL):
        has_thinking = True
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()

    return content, has_thinking


# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extracts a JSON dict from LLM response (raw, ```json``` fenced, or bare braces)."""
    # Try raw parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Try bare { ... }
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Event queue
# ─────────────────────────────────────────────────────────────────────────────

def push_event(state: Dict[str, Any], event: Dict[str, Any]) -> None:
    """Appends an event to state['event_queue']."""
    if "event_queue" not in state or state["event_queue"] is None:
        state["event_queue"] = []
    state["event_queue"].append(event)
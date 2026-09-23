"""
Shared LLM factory for the multi-agent ML pipeline.

All agent files import from here so model/provider/auth/temperature changes
happen in exactly one place. Two sizes are available:
  - Standard (20b-cloud): Supervisor, Features, Modeler, EDA, Judge, Reporter, Profiler
  - Large (120b-cloud): Coder sub-agent (heavier code-generation workload)

Set PIPELINE_LLM_BASE_URL or PIPELINE_LLM_MODEL_STANDARD / PIPELINE_LLM_MODEL_LARGE
env vars to override without touching code.
"""
import os
from langchain_ollama import ChatOllama


_BASE_URL = os.environ.get("PIPELINE_LLM_BASE_URL", "https://ollama.com")
_MODEL_STANDARD = os.environ.get("PIPELINE_LLM_MODEL_STANDARD", "gpt-oss:20b-cloud")
_MODEL_LARGE = os.environ.get("PIPELINE_LLM_MODEL_LARGE", "gpt-oss:120b-cloud")


def get_llm(temperature: float = 0, large: bool = True) -> ChatOllama:
    """
    Return a configured ChatOllama instance.

    Args:
        temperature: Sampling temperature (0 = deterministic structured output).
        large: If True, use the larger code-generation model (120b-cloud).
               Use only for the Coder sub-agent which needs heavier capacity.

    Returns:
        Configured ChatOllama instance.
    """
    model = _MODEL_LARGE if large else _MODEL_STANDARD
    return ChatOllama(
        model=model,
        base_url=_BASE_URL,
        client_kwargs={
            "headers": {"Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"}
        },
        temperature=temperature,
    )

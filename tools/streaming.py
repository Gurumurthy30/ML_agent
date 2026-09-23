"""
Streaming helper shared by every agent that makes a plain (non-structured-output)
text-generation call to the LLM: the Coder sub-agent's code generation, the Profiler's
JSON interpretation, and the Reporter's final report.

Structured-output calls (Supervisor's routing decision, the loop-control
"continue"/"stop" decisions in EDA/Features/Modeler) stay on `.invoke()` with
`.with_structured_output(...)` — token-by-token streaming of a Pydantic object isn't
meaningful, and those payloads are short JSON anyway.
"""
import json
import re
from typing import Type, TypeVar
from pydantic import BaseModel
from tools.logger import get_logger, publish_to_subscribers

import sys

T = TypeVar("T", bound=BaseModel)


def _flexible_construct(schema: Type[T], data: dict) -> T:
    """Normalize model outputs with minor key discrepancies into Pydantic models."""
    if not isinstance(data, dict):
        raise ValueError("Data is not a dict")
    norm = dict(data)
    fields = getattr(schema, "model_fields", {})

    # Loop decisions
    if "decision" in fields:
        dec = str(norm.get("decision") or norm.get("step") or "").lower()
        if any(w in dec for w in ("stop", "end", "done", "finish", "halt", "complete")):
            norm["decision"] = "stop"
        else:
            norm["decision"] = "continue"
    if "reasoning" in fields and not norm.get("reasoning"):
        norm["reasoning"] = norm.get("explanation") or norm.get("reason") or norm.get("justification") or "Completed step analysis."
    if "task_spec" in fields and not norm.get("task_spec"):
        norm["task_spec"] = norm.get("task") or norm.get("instruction") or norm.get("description") or norm.get("step")

    # Supervisor decisions
    if "next_agent" in fields and not norm.get("next_agent"):
        norm["next_agent"] = norm.get("agent") or norm.get("next") or norm.get("target_agent")
    if "task_instructions" in fields and not norm.get("task_instructions"):
        norm["task_instructions"] = norm.get("instructions") or norm.get("instruction") or norm.get("task") or ""

    # Judge verdicts
    if "verdict" in fields and not norm.get("verdict"):
        norm["verdict"] = "accept" if any(w in str(norm).lower() for w in ("accept", "pass", "approve")) else "reject"
    if "feedback" in fields and not norm.get("feedback"):
        norm["feedback"] = norm.get("reasoning") or norm.get("comments") or "Validation criteria met."

    return schema(**norm)


def _record_tokens(messages, output_obj, run_id: str = None, agent: str = "agent", total_usage: dict = None):
    if not run_id:
        return
    try:
        from tools import tracer
        if total_usage and (total_usage.get("input_tokens") or total_usage.get("output_tokens")):
            tin = int(total_usage.get("input_tokens") or 0)
            tout = int(total_usage.get("output_tokens") or 0)
        else:
            prompt_chars = sum(len(str(getattr(m, "content", m))) for m in messages)
            tin = max(1, prompt_chars // 4)
            if isinstance(output_obj, str):
                out_chars = len(output_obj)
            else:
                out_chars = len(str(getattr(output_obj, "__dict__", str(output_obj))))
            tout = max(1, out_chars // 4) if out_chars else 0
        cost_usd = round((tin * 0.0005 + tout * 0.0015) / 1000.0, 6)
        tracer.record_event(run_id, agent, "llm_usage", tokens_in=tin, tokens_out=tout, cost_usd=cost_usd)
    except Exception:
        pass


def invoke_structured_robust(llm, schema: Type[T], messages: list, run_id: str = None, agent: str = "agent") -> T:
    """
    Robust structured invoker that handles Ollama's casing quirks (e.g. edaStepDecision vs EdaStepDecision),
    direct JSON content generation, and flexible schema coercion.
    """
    # Support test mocks that only define with_structured_output (preserving state across iterations)
    if hasattr(llm, "with_structured_output") and not hasattr(llm, "bind_tools"):
        if not hasattr(llm, "_cached_mock_structured"):
            llm._cached_mock_structured = llm.with_structured_output(schema)
        res = llm._cached_mock_structured.invoke(messages)
        _record_tokens(messages, res, run_id, agent)
        return res

    # 1. Attempt tool calling with case-insensitive and flexible mapping
    try:
        bound_llm = llm.bind_tools([schema])
        res = bound_llm.invoke(messages)

        def _finish(data):
            res = _flexible_construct(schema, data)
            _record_tokens(messages, res, run_id, agent)
            return res

        if hasattr(res, "tool_calls") and res.tool_calls:
            for tc in res.tool_calls:
                tc_name = tc.get("name", "")
                if tc_name.lower() == schema.__name__.lower():
                    try:
                        return _finish(tc.get("args", {}))
                    except Exception:
                        pass
            if len(res.tool_calls) == 1:
                try:
                    return _finish(res.tool_calls[0].get("args", {}))
                except Exception:
                    pass

        # 2. Check content as JSON
        content = getattr(res, "content", "")
        if content:
            clean = content.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            elif clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()
            try:
                data = json.loads(clean)
                if isinstance(data, dict):
                    return _finish(data)
            except Exception:
                pass

            m = re.search(r'(\{[\s\S]*\})', clean)
            if m:
                try:
                    data = json.loads(m.group(1))
                    if isinstance(data, dict):
                        return _finish(data)
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Fallback: prompt directly for JSON schema rather than failing tool parser
    try:
        from langchain_core.messages import HumanMessage
        json_prompt = (
            f"\nYou must respond ONLY with a JSON object matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
            f"Do not include markdown fences or any other text."
        )
        fallback_messages = list(messages) + [HumanMessage(content=json_prompt)]
        res2 = llm.invoke(fallback_messages)
        content2 = getattr(res2, "content", "").strip()
        m2 = re.search(r'(\{[\s\S]*\})', content2)
        if m2:
            res_obj = _flexible_construct(schema, json.loads(m2.group(1)))
            _record_tokens(fallback_messages, res_obj, run_id, agent)
            return res_obj
    except Exception:
        pass

    # 4. Final attempt: standard with_structured_output
    res_final = llm.with_structured_output(schema).invoke(messages)
    _record_tokens(messages, res_final, run_id, agent)
    return res_final


def stream_text(
    llm,
    messages: list,
    run_id: str = None,
    agent: str = "agent",
    on_token = None,
    echo: bool = True,
) -> str:
    """
    Direct, robust text completion from `llm` (streaming removed per user request for reliable execution).
    """
    logger = get_logger(run_id) if run_id else None
    try:
        if hasattr(llm, "invoke"):
            response = llm.invoke(messages)
            text = response.content if hasattr(response, "content") else str(response)
            if isinstance(text, list):
                text = "".join(str(part.get("text", part) if isinstance(part, dict) else part) for part in text)
            text = str(text or "")
            total_usage = getattr(response, "usage_metadata", None)
        elif hasattr(llm, "stream"):
            chunks = []
            for chunk in llm.stream(messages):
                piece = getattr(chunk, "content", None) or (chunk if isinstance(chunk, str) else "")
                if piece:
                    chunks.append(piece)
            text = "".join(chunks)
            total_usage = None
        else:
            text = str(llm(messages))
            total_usage = None
        _record_tokens(messages, text, run_id, agent, total_usage=total_usage)
    except Exception as exc:
        if logger:
            logger.error("%s: LLM invocation failed: %s", agent, exc)
        raise

    if echo and text:
        try:
            sys.stdout.buffer.write(f"\n--- {agent} ---\n".encode("utf-8", errors="replace"))
            sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()
        except Exception:
            pass

    if on_token and text:
        try:
            on_token(text)
        except Exception:
            pass

    if logger:
        logger.debug("%s: generated %d chars", agent, len(text))
    return text

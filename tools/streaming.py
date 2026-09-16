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


def invoke_structured_robust(llm, schema: Type[T], messages: list) -> T:
    """
    Robust structured invoker that handles Ollama's casing quirks (e.g. edaStepDecision vs EdaStepDecision),
    direct JSON content generation, and flexible schema coercion.
    """
    # Support test mocks that only define with_structured_output (preserving state across iterations)
    if hasattr(llm, "with_structured_output") and not hasattr(llm, "bind_tools"):
        if not hasattr(llm, "_cached_mock_structured"):
            llm._cached_mock_structured = llm.with_structured_output(schema)
        return llm._cached_mock_structured.invoke(messages)

    # 1. Attempt tool calling with case-insensitive and flexible mapping
    try:
        bound_llm = llm.bind_tools([schema])
        res = bound_llm.invoke(messages)

        if hasattr(res, "tool_calls") and res.tool_calls:
            for tc in res.tool_calls:
                tc_name = tc.get("name", "")
                if tc_name.lower() == schema.__name__.lower():
                    try:
                        return _flexible_construct(schema, tc.get("args", {}))
                    except Exception:
                        pass
            if len(res.tool_calls) == 1:
                try:
                    return _flexible_construct(schema, res.tool_calls[0].get("args", {}))
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
                    return _flexible_construct(schema, data)
            except Exception:
                pass

            m = re.search(r'(\{[\s\S]*\})', clean)
            if m:
                try:
                    data = json.loads(m.group(1))
                    if isinstance(data, dict):
                        return _flexible_construct(schema, data)
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
            return _flexible_construct(schema, json.loads(m2.group(1)))
    except Exception:
        pass

    # 4. Final attempt: standard with_structured_output
    return llm.with_structured_output(schema).invoke(messages)


def stream_text(llm, messages, run_id: str = None, agent: str = "agent", echo: bool = True, on_token = None) -> str:
    """
    Stream a plain-text completion from `llm`, printing tokens to stdout as they
    arrive (live generation instead of a blocking wait for the full response), and
    returning the fully concatenated text once the stream ends.

    Falls back to a single blocking `.invoke()` if streaming isn't supported by the
    underlying model/transport for some reason.
    """
    logger = get_logger(run_id) if run_id else None
    chunks = []
    try:
        if echo:
            try:
                sys.stdout.buffer.write(f"\n--- {agent} (streaming) ---\n".encode("utf-8", errors="replace"))
                sys.stdout.buffer.flush()
            except Exception:
                pass
        for chunk in llm.stream(messages):
            piece = getattr(chunk, "content", None) or (chunk if isinstance(chunk, str) else "")
            if piece:
                chunks.append(piece)
                if echo:
                    try:
                        sys.stdout.buffer.write(piece.encode("utf-8", errors="replace"))
                        sys.stdout.buffer.flush()
                    except Exception:
                        pass
                if on_token:
                    try:
                        on_token(piece)
                    except Exception:
                        pass
                elif run_id:
                    publish_to_subscribers(run_id, {
                        "event": "token",
                        "type": "token",
                        "agent": agent,
                        "text": piece,
                        "run_id": run_id,
                    })
        if echo:
            try:
                sys.stdout.buffer.write(b"\n")
                sys.stdout.buffer.flush()
            except Exception:
                pass
        text = "".join(chunks)
        if not text:
            raise ValueError("stream produced no content")
    except Exception as exc:
        if logger:
            logger.warning("%s: streaming failed (%s), falling back to invoke()", agent, exc)
        response = llm.invoke(messages)
        text = response.content

    if logger:
        logger.debug("%s: streamed %d chars", agent, len(text))
    return text

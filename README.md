# Multi-Agent ML Pipeline

Implements the flowchart end-to-end: **Supervisor** routes to **Profiler**, **EDA
Agent**, **Features Agent**, and **Modeler Agent** (with an internal tier-0 HP-tuning
loop), Features hard-blocks on **Human Approval** for destructive/guided actions,
**Judge Agent** accepts (→ Reporter) or rejects with a retry tier (1 = new model
family, back through Supervisor → Modeler; 2 = re-engineer features, back through
Supervisor → Features), and **Reporter** writes the final report, persists to **Run
Memory/RAG**, and delivers the result.

Every agent in the diagram is now implemented, including Judge (previously
out-of-scope) — the only remaining gaps are the Human Approval agent's own UI/decision
logic (a human makes that call, not an LLM) and a hardened/sandboxed exec environment.

## What's here, in build order

### Pass 1 — core architecture + observability
1. **No hardcoded domain logic** — EDA, Features, and Modeler delegate all
   code-writing to the shared **Coder sub-agent** and only reason about *what* to try
   and *whether it converged*.
2. **Shared exploration loop** (`agents/loop_utils.py`) — the "try → look → adjust"
   shape used by all three, with an auto-scaling iteration ceiling and Modeler's
   plateau backstop (the only mechanical, non-LLM stop condition of the three).
3. **Hard block vs. advisory** — Features' destructive/guided gate genuinely pauses
   the graph via LangGraph's `interrupt()`; exploration not converging by the ceiling
   is advisory-only and never blocks.
4. **Streaming** — every plain-text LLM call (Coder, Profiler, EDA synthesis,
   Reporter) streams tokens live via `tools/streaming.py`.
5. **Local logger** — `tools/logger.py`: console+file logs plus a structured JSONL
   event trace per run, which the Reporter reads back for an exact (non-LLM)
   monitoring summary.
6. **Reporter Agent** — narrative (streamed) + exact event-trace aggregation.

### Pass 2 — Judge Agent, real MCP tool, real RAG, CV/NLP/audio-as-table
7. **Judge Agent** (`agents/judge_agent.py`) — the piece the original spec explicitly
   scoped out. Checks Run Memory first, then accepts or rejects with a retry tier,
   incrementing `retry_counts`. The Supervisor still owns the escalation guard
   ("after 2 retries at the same tier, route to human_approval instead") — Judge only
   judges quality and picks a tier.
8. **Real MCP tool** (`mcp_server/python_exec_server.py` + `tools/mcp_client.py`) —
   replaces the placeholder subprocess call with an actual MCP server (stdio
   transport, official `mcp` SDK) that the Coder sub-agent calls by default, falling
   back to the direct in-process call if spawning the server ever fails. This was
   built against a live round-trip test, not just written to look plausible — the
   `mcp` package installed here is 2.x, which renamed `FastMCP`→`MCPServer` and
   `isError`→`is_error` from the more commonly-documented 1.x API; the client code
   reflects what 2.x actually returns, confirmed by spawning the server and calling
   the tool for real.
9. **Real RAG** (`memory/run_memory.py`) — replaces the `None`-returning stub with a
   small JSONL vector store: Ollama embeddings preferred, with a zero-dependency
   offline hashing-vector fallback so lookups/stores never hard-fail a run just
   because the embedding endpoint is unreachable. Same-dataset-fingerprint hits are
   ranked first, then cosine similarity across everything else. Reporter writes into
   it at the end of every run; EDA/Features/Modeler/Judge all query it first (per the
   diagram's "checks first" edge into Judge, and the general Run Memory/RAG fan-in).
10. **CV/NLP/audio handled as tables** (Kaggle-style) — rather than a separate
    ingestion path per modality, `profiler_agent.py` now detects each column's
    modality (`image_path`, `audio_path`, `free_text`, alongside plain
    `numerical`/`categorical`) via extension-sniffing and a text heuristic, and
    stores it in `profile["features"][*]["modality"]` plus a profile-level
    `detected_modalities` summary. Everything downstream reads that flag:
    - `coder_agent.py`'s system prompt explains how to handle each modality (resolve
      relative paths via the auto-injected `INPUT_DATASET_DIR`, use Pillow/
      torchvision for images, sklearn text vectorizers or transformers for text,
      librosa/torchaudio for audio) and degrades gracefully if a library isn't
      installed.
    - Per-attempt exec timeout auto-scales (60s → 300s) when non-tabular modalities
      are detected (`compute_exec_timeout`), since image/audio decoding and embedding
      models take longer than plain pandas/sklearn.
    - Modeler's prompt is told to derive embeddings/features from image/audio/text
      columns before fitting, still through the same Coder-delegation pattern.
    - **Features' structural-diff hard-block needed no changes** — it diffs the
      table (paths + labels), never decoded pixels/audio, so the existing
      columns-removed/row-count check keeps working unmodified.

## Files

```
state.py                       AgentState
tools/python_exec_tool.py      subprocess-based exec logic (path-in, path-out)
tools/mcp_client.py            MCP client — spawns the exec server, calls its tool
tools/logger.py                local logger + structured JSONL event trace
tools/streaming.py             shared streaming helper for plain-text LLM calls
mcp_server/python_exec_server.py   real MCP server exposing the exec tool over stdio
memory/run_memory.py           real RAG: JSONL vector store + cosine similarity
agents/coder_agent.py          shared Coder sub-agent (MCP exec, retries, modality-aware prompt)
agents/profiler_agent.py       hand-coded stats + modality detection + LLM interpretation
agents/supervisor.py           routing decisions
agents/loop_utils.py           shared exploration-loop driver, ceiling + timeout calc
agents/eda_agent.py            independent explorations, LLM-only stop
agents/features_agent.py       incremental, structural-diff hard-block, guided_mode
agents/modeler_agent.py        incremental, tier-0 HP tuning, plateau backstop
agents/judge_agent.py          accept/reject + retry-tier decision
agents/reporter_agent.py       narrative + exact monitoring aggregation + RAG write
graph.py                       LangGraph wiring, incl. the human_approval pause node
main.py                        CLI entry point
smoke_test.py                  control-flow tests against mocked LLM/Coder calls
requirements.txt               core dependencies (incl. mcp)
requirements-modalities.txt    optional, heavy — torch/transformers/librosa etc.
```

## Running it

```bash
pip install -r requirements.txt
# optional, only if your dataset has image/audio/text columns and you want the
# Coder to have real modeling libraries available for them:
pip install -r requirements-modalities.txt

export OLLAMA_API_KEY=your_key_here
python main.py --dataset path/to/data.csv --mode full_pipeline
python main.py --dataset path/to/data.csv --mode eda_only
python main.py --dataset path/to/data.csv --guided     # approval on every feature step
```

For a Kaggle-style CV/NLP/audio dataset, just point `--dataset` at the CSV that has
the image/audio file-path or free-text columns — no separate flag needed, the
Profiler detects them automatically.

If a run pauses for human approval, it prints the `thread_id` to resume with. Resuming
requires a small script that calls
`graph.invoke(Command(resume={"approval_status": "approved"}), config)` against the
same `thread_id` — not included here since the actual Human Approval agent's UI/logic
is still out of scope, only the pause/resume plumbing is implemented.

### Testing without network access

`smoke_test.py` monkeypatches each agent's `_make_llm`/`coder_agent` with fakes and
exercises: the loop driver's four exit paths, iteration-ceiling scaling, exec-timeout
modality scaling, Features' structural-diff and guided-mode triggers, Modeler's
plateau backstop, Coder's retry-and-fix loop, EDA end-to-end, Reporter's file output +
monitoring aggregation, Profiler's modality detection (image/audio/text/categorical),
the RAG store+lookup round trip (including the exact-fingerprint ranking bonus), and
Judge's accept/reject/retry-count bookkeeping. Run with:

```bash
python smoke_test.py
```

The real MCP server↔client round trip (spawn, call, execute, parse response) was
additionally verified directly against a live subprocess — not mocked — since stdio
transport is exactly the kind of thing that looks right in code but silently breaks;
that test caught a real API mismatch (see point 8 above) before it shipped.

This was all necessary in the sandbox this was built in, since `ollama.com` isn't on
the network allowlist there — the actual pipeline against a real Ollama endpoint
hasn't been run end-to-end and should be validated on real data before trusting it.

## Known gaps (intentionally out of scope)

- The Human Approval agent's actual decision UI/logic (only the generic pause/resume
  mechanics exist — a human still has to drive the resume call by hand).
- Artifact Store / persistence layer beyond the Reporter's own `artifacts/` writes and
  the RAG store.
- Hardened/sandboxed code execution — `python_exec_tool.py` and the MCP server
  wrapping it still have no import allowlisting or resource limits.
- A live end-to-end run against a real Ollama endpoint.

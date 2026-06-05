# log-intelligence — Log Triage Agent

<p align="center">
  <img src="../../demos/log-triage.gif" alt="Log Triage Agent demo" width="900">
  <br><em>Agent triages a 2 000-line HDFS log → structured Markdown report → 5/5 eval pass</em>
</p>

Reads a log file, clusters anomalies, and emits a structured Markdown triage report.
Supports three fully independent backends selectable at runtime via `--backend`.

## File layout

```
log-intelligence/
├── triage.py                  # Entry point for all backends. --backend anthropic|langchain|openrouter
│
├── planner_anthropic.py       # ANTHROPIC BACKEND — raw Anthropic SDK loop
├── tools_anthropic.py         # ANTHROPIC BACKEND — Tools._registry + dispatch()
├── memory_anthropic.py        # ANTHROPIC BACKEND — list[dict] message history
├── requirements_anthropic.txt # ANTHROPIC BACKEND — anthropic, pydantic
│
├── planner_langchain.py       # LANGCHAIN BACKEND — ChatAnthropic.bind_tools + explicit loop
├── requirements_langchain.txt # LANGCHAIN BACKEND — langchain, langchain-anthropic, pydantic
│
├── planner_openrouter.py      # OPENROUTER BACKEND — OpenAI-compatible client → openrouter.ai
├── tools_openrouter.py        # OPENROUTER BACKEND — same tools, OpenAI function-calling format
├── memory_openrouter.py       # OPENROUTER BACKEND — system prompt as first message
├── requirements_openrouter.txt # OPENROUTER BACKEND — openai, pydantic
│
├── evaluator.py               # SHARED — runs evals/cases.jsonl against any backend
├── evals/
│   └── cases.jsonl            # SHARED — 5 labeled HDFS log test cases
└── README.md                  # this file
```

> `main.py` is the legacy skeleton entry point — use `triage.py` for Day 2 onwards.

## Quick start

```bash
cd ~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/agents/log-intelligence
uv venv && source .venv/bin/activate

# Install the backend(s) you want:
uv pip install -r requirements_anthropic.txt   # for --backend anthropic
uv pip install -r requirements_langchain.txt   # for --backend langchain
uv pip install -r requirements_openrouter.txt  # for --backend openrouter

LOG=~/workspace/claude-code/ai-journey/agentic-ai-projects/aiops-platform/services/ingestion/loghub-samples/HDFS/HDFS_2k.log

python triage.py $LOG --backend anthropic    # raw Anthropic SDK
python triage.py $LOG --backend langchain    # LangChain (verbose)
python triage.py $LOG --backend openrouter   # Anthropic via OpenRouter

python triage.py --eval --backend anthropic   # run 5 eval cases (Anthropic)
python triage.py --eval --backend langchain   # run 5 eval cases (LangChain)
python triage.py --eval --backend openrouter  # run 5 eval cases (OpenRouter)
```

## Backend comparison

| | `--backend anthropic` | `--backend langchain` | `--backend openrouter` |
|---|---|---|---|
| Brain | `planner_anthropic.py` | `planner_langchain.py` | `planner_openrouter.py` |
| Tools | `tools_anthropic.py` (_registry) | inline `@tool` in planner | `tools_openrouter.py` (_registry) |
| Memory | `memory_anthropic.py` (list[dict]) | LangChain messages list | `memory_openrouter.py` (system in messages) |
| Loop control | manual for-loop + stop_reason | manual for-loop + tool_calls check | manual for-loop + tool_calls check |
| Client | `anthropic.Anthropic()` | `ChatAnthropic.bind_tools()` | `openai.OpenAI(base_url=openrouter)` |
| Auth key | `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` | `OPENROUTER_API_KEY` |
| Tool schema | `input_schema` (Anthropic format) | `@tool` decorator + docstring | `function.parameters` (OpenAI format) |
| Model string | `claude-haiku-4-5-20251001` | `claude-haiku-4-5-20251001` | `anthropic/claude-haiku-4-5` |
| Model swap | change string in `PlannerConfig` | change string in `LangChainPlannerConfig` | change string in `OpenRouterPlannerConfig` |
| Verbose output | silent (final answer only) | prints every tool call step | silent (final answer only) |
| Tracing | none | LangSmith (set `LANGCHAIN_API_KEY`) | OpenRouter dashboard |
| Deps | `anthropic`, `pydantic` | + `langchain`, `langchain-anthropic` | `openai`, `pydantic` |

## Adding a new tool

**Anthropic backend** — edit `tools_anthropic.py`:
1. Define a Pydantic input model.
2. Implement the function (returns `str`).
3. Register it in `Tools._registry`.

**LangChain backend** — edit `planner_langchain.py`:
1. Write a function decorated with `@tool`.
2. Add it to the `TOOLS` list.
3. The docstring IS the tool description — keep it tight.

**OpenRouter backend** — edit `tools_openrouter.py`:
1. Define a Pydantic input model (same as Anthropic backend).
2. Implement the function (returns `str`).
3. Register it in `Tools._registry` — `schema()` auto-converts to OpenAI format.

## Why three backends?

`planner_anthropic.py` is transparent: you see every API call, every `stop_reason`
check. It's the best way to understand what an agent loop actually does.

`planner_langchain.py` trades transparency for ecosystem features: automatic
LangSmith tracing, callbacks, streaming, and the same patterns used in Days 4–7.

`planner_openrouter.py` uses the OpenAI-compatible API via OpenRouter — one API key
gives access to Anthropic, OpenAI, Mistral, Llama, Gemini and more. Swap the model
string in `OpenRouterPlannerConfig` to compare providers without changing any other
code. Used in the Day 3 multi-provider routing experiment.

# How to run Task 4

This page explains how to run the Task 4 tool layer and agent. All commands are run from the repository root.

## 1. Prerequisites

Make sure the Python environment is installed and the gateway key is configured:

```bash
uv sync
cp .env.example .env   # then put your personal key into .env
```

The gateway only works from the university network or via the university VPN.

## 2. Run the tool-layer tests

```bash
uv run pytest task4_tools/tests -v
```

All public tests should pass before running the agent.

## 3. Create a fresh workspace

The agent works on a copy of `tinyledger` in `task4_tools/workspace/`. Reset it before every run:

```bash
uv run python task4_tools/reset_workspace.py
```

Do not edit files in `task4_tools/workspace/` by hand. The original `tinyledger/` folder is never modified.

## 4. Run the agent with the scripted mock model

```bash
uv run python task4_tools/agent.py --mock
```

The mock model sends a fixed sequence of tool calls, including broken and malicious ones. A correct run ends with:

```text
All tests pass and the March report is correct.
```

## 5. Run the agent against the real model

Reset the workspace first so the agent starts from the original code:

```bash
uv run python task4_tools/reset_workspace.py
uv run python task4_tools/agent.py
```

The model and gateway settings come from `.env`.

The agent supports these options:

```text
--mock              use MockOpenAIClient instead of the real model
--max-steps N       stop after N model turns (default: 40)
--workspace PATH    use a different workspace directory
```

## 6. Inspect the results

Every tool execution is written to `task4_tools/logs/trace.jsonl`, one JSON object per line:

```json
{"name": "read_file", "arguments": "{\"path\": \"README.md\"}", "ok": true, "error": null, "truncated": false, "duration_s": 0.0012}
```

The LLM request/response log is written next to it:

- `task4_tools/logs/mock_run.jsonl` for `--mock`
- `task4_tools/logs/llm_run.jsonl` for the real model

After a real run, save the agent's changes as a diff:

```bash
git -C task4_tools/workspace diff > task4_tools/final.diff
```

You can also verify the workspace tests directly:

```bash
cd task4_tools/workspace
uv run pytest -q
```

## 7. Files involved

| File | Purpose |
|---|---|
| `task4_tools/tools.py` | Safe tool layer (`ToolRegistry`) |
| `task4_tools/agent.py` | CLI agent loop with `--mock` support |
| `task4_tools/tool_contract.py` | Tool interface and limits (read-only) |
| `task4_tools/mock_model.py` | Scripted fake model (read-only) |
| `task4_tools/tests/` | Public tool-layer tests |
| `task4_tools/workspace/` | Generated working copy used by the agent |
| `task4_tools/logs/trace.jsonl` | One line per executed tool call |
| `task4_tools/final.diff` | Final diff of the agent's changes |

## Troubleshooting

- `Workspace not found`: run `uv run python task4_tools/reset_workspace.py` first.
- Gateway errors or `401`: check `.env`, the API key expiry, and the VPN connection.
- A tool call is rejected: inspect the corresponding entry in `task4_tools/logs/trace.jsonl`; the `error` field explains why.
- Agent stops after the step limit: reset the workspace and run it again, or increase `--max-steps`.

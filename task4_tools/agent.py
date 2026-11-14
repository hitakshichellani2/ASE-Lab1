from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent
REPO_ROOT = TASK_DIR.parent
for _path in (str(TASK_DIR), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from common.llm_client import LLMClient, message_to_dict
from tool_contract import ToolResult
from tools import ToolRegistry

TASK_PROMPT = "Make all tests pass and fix the problem described in ISSUE.md. Do not modify tests."

SYSTEM_PROMPT = (
    "You are a careful coding agent working inside a sandboxed repository. "
    "Use the provided tools to inspect files, run tests, and make minimal changes. "
    "Only edit files below src/. Never modify tests, data, configuration, or ISSUE.md. "
    "Stop once the tests pass and the reported issue is fixed."
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tool-using agent for the tinyledger task.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the scripted MockOpenAIClient instead of the real gateway model.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=40,
        help="Maximum number of model turns before the agent stops (default: 40).",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=TASK_DIR / "workspace",
        help="Workspace directory (default: task4_tools/workspace).",
    )
    return parser.parse_args(argv)


def build_client(args: argparse.Namespace) -> LLMClient:
    log_dir = TASK_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    if args.mock:
        from mock_model import MockOpenAIClient

        return LLMClient(
            model="mock",
            log_path=log_dir / "mock_run.jsonl",
            openai_client=MockOpenAIClient(),
        )
    return LLMClient(log_path=log_dir / "llm_run.jsonl")


def log_trace(
    trace_path: Path,
    name: str,
    arguments: str,
    result: ToolResult,
    duration_s: float,
) -> None:
    entry = {
        "name": name,
        "arguments": arguments,
        "ok": result.ok,
        "error": result.error,
        "truncated": result.truncated,
        "duration_s": round(duration_s, 6),
    }
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def execute_tool_call(
    registry: ToolRegistry,
    call,
    trace_path: Path,
) -> ToolResult:
    function = getattr(call, "function", None)
    name = getattr(function, "name", "")
    arguments = getattr(function, "arguments", "")
    started = time.perf_counter()
    try:
        result = registry.execute(name, arguments)
    except Exception as exc:
        result = ToolResult(ok=False, error=f"{exc.__class__.__name__}: {exc}")
    duration_s = time.perf_counter() - started
    log_trace(trace_path, name, arguments, result, duration_s)
    return result


def run_agent(
    llm: LLMClient,
    registry: ToolRegistry,
    trace_path: Path,
    max_steps: int,
) -> int:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("", encoding="utf-8")

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": TASK_PROMPT},
    ]
    tools = registry.schemas()

    for _step in range(1, max_steps + 1):
        message = llm.chat_with_tools(messages, tools=tools)
        messages.append(message_to_dict(message))

        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            final_answer = getattr(message, "content", None)
            if final_answer:
                print(final_answer)
            return 0

        for call in tool_calls:
            result = execute_tool_call(registry, call, trace_path)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": getattr(call, "id", ""),
                    "content": result.to_content(),
                }
            )

    print(
        f"Agent stopped after {max_steps} steps without a final answer.",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(
            f"Workspace not found: {workspace}\n"
            "Run: uv run python task4_tools/reset_workspace.py",
            file=sys.stderr,
        )
        return 2

    try:
        client = build_client(args)
        registry = ToolRegistry(workspace=workspace)
        return run_agent(
            llm=client,
            registry=registry,
            trace_path=TASK_DIR / "logs" / "trace.jsonl",
            max_steps=args.max_steps,
        )
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Agent failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import copy
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from tool_contract import (
    DEFAULT_TIMEOUT_S,
    MAX_LIST_ENTRIES,
    MAX_OUTPUT_CHARS,
    MAX_READ_LINES,
    MAX_SEARCH_RESULTS,
    ToolRegistryBase,
    ToolResult,
)

_SHELL_METACHARACTERS = frozenset(";&|`$><\n\r\x00(){}[]*?~!#^%\"'")
_SKIP_DIRECTORIES = frozenset(
    {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
)
_SAFE_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "OS",
    }
)

_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List files below a directory in the workspace. Paths are relative to "
                "the workspace root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory to list, relative to the workspace. Defaults to '.'.",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Optional glob pattern, for example '**/*.py'.",
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a UTF-8 text file from the workspace and return numbered lines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to the workspace root.",
                    },
                    "start_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "First line to return, 1-based.",
                    },
                    "end_line": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Last line to return, inclusive.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search workspace text files with a Python regular expression.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression to search for.",
                    },
                    "glob": {
                        "type": "string",
                        "description": "Optional glob limiting the files searched, for example 'src/**/*.py'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_SEARCH_RESULTS,
                        "description": "Maximum number of matching lines to return.",
                    },
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": (
                "Run pytest in the workspace and return a structured summary with "
                "passed/failed counts and short failure details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": (
                            "Optional test path or node id, for example "
                            "'tests/test_ledger.py' or 'tests/test_ledger.py::test_name'."
                        ),
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replace a unique string in an existing file below src/ and return a "
                "unified diff. Files outside src/ are read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path below src/, relative to the workspace root.",
                    },
                    "old_str": {
                        "type": "string",
                        "description": "Exact text that must occur exactly once.",
                    },
                    "new_str": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                },
                "required": ["path", "old_str", "new_str"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_cli",
            "description": (
                "Run 'python -m tinyledger <args>' inside the workspace and return its "
                "exit code, stdout and stderr."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Command-line arguments passed to the tinyledger CLI.",
                    }
                },
                "required": ["args"],
                "additionalProperties": False,
            },
        },
    },
]

_SCHEMA_BY_NAME = {entry["function"]["name"]: entry["function"] for entry in _TOOL_SCHEMAS}


class _ToolError(Exception):
    pass


class ToolRegistry(ToolRegistryBase):
    def __init__(self, workspace: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        super().__init__(workspace, timeout_s)
        self.workspace = Path(workspace)

    def schemas(self) -> list[dict]:
        return copy.deepcopy(_TOOL_SCHEMAS)

    def execute(self, name: str, arguments: str) -> ToolResult:
        try:
            if not isinstance(name, str):
                return self._error("tool name must be a string")
            handler = self._handler_for(name)
            if handler is None:
                return self._error(f"unknown tool: {name!r}")
            if not isinstance(arguments, str):
                return self._error("tool arguments must be a JSON string")
            try:
                data = json.loads(arguments)
            except json.JSONDecodeError as exc:
                return self._error(
                    f"invalid JSON arguments at line {exc.lineno}, column {exc.colno}: {exc.msg}"
                )
            if not isinstance(data, dict):
                return self._error("arguments must be a JSON object")
            validation_error = self._validate_arguments(name, data)
            if validation_error is not None:
                return self._error(validation_error)
            result = handler(data)
            return self._bounded(result)
        except _ToolError as exc:
            return self._error(str(exc))
        except subprocess.TimeoutExpired:
            return self._error(f"command timed out after {self.timeout_s} seconds")
        except Exception as exc:
            message = str(exc).strip() or exc.__class__.__name__
            return self._error(f"{exc.__class__.__name__}: {message}")

    def _handler_for(self, name: str):
        return {
            "list_files": self._tool_list_files,
            "read_file": self._tool_read_file,
            "search_code": self._tool_search_code,
            "run_tests": self._tool_run_tests,
            "run_cli": self._tool_run_cli,
            "edit_file": self._tool_edit_file,
        }.get(name)

    def _validate_arguments(self, name: str, data: dict[str, Any]) -> str | None:
        function = _SCHEMA_BY_NAME[name]
        parameters = function["parameters"]
        properties = parameters["properties"]
        for key in data:
            if key not in properties:
                return f"unexpected argument {key!r} for {name}"
        for key in parameters.get("required", []):
            if key not in data:
                return f"missing required argument {key!r} for {name}"
        for key, value in data.items():
            error = self._check_value(key, value, properties[key])
            if error is not None:
                return error
        return None

    def _check_value(self, key: str, value: Any, spec: dict[str, Any]) -> str | None:
        expected = spec.get("type")
        if expected == "string":
            if not isinstance(value, str):
                return f"argument {key!r} must be a string"
        elif expected == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return f"argument {key!r} must be an integer"
            minimum = spec.get("minimum")
            maximum = spec.get("maximum")
            if minimum is not None and value < minimum:
                return f"argument {key!r} must be at least {minimum}"
            if maximum is not None and value > maximum:
                return f"argument {key!r} must be at most {maximum}"
        elif expected == "array":
            if not isinstance(value, list):
                return f"argument {key!r} must be an array"
            item_spec = spec.get("items", {})
            for index, item in enumerate(value):
                error = self._check_value(f"{key}[{index}]", item, item_spec)
                if error is not None:
                    return error
        return None

    def _root(self) -> Path:
        return self.workspace.resolve()

    def _is_within(self, path: Path, base: Path) -> bool:
        try:
            candidate = os.path.normcase(os.path.normpath(str(path)))
            parent = os.path.normcase(os.path.normpath(str(base)))
            return os.path.commonpath([candidate, parent]) == parent
        except (OSError, ValueError):
            return False

    def _resolve(self, raw: str) -> Path:
        if not isinstance(raw, str):
            raise _ToolError("path must be a string")
        if "\x00" in raw:
            raise _ToolError("path contains a NUL byte")
        text = raw.strip()
        if not text:
            text = "."
        if text.startswith("~"):
            raise _ToolError("paths starting with '~' are not allowed")
        candidate = Path(text)
        if candidate.is_absolute() or candidate.drive:
            raise _ToolError("absolute paths are not allowed")
        root = self._root()
        try:
            target = (root / candidate).resolve(strict=False)
        except (OSError, ValueError) as exc:
            raise _ToolError(f"invalid path: {exc}") from exc
        if not self._is_within(target, root):
            raise _ToolError("path escapes the workspace")
        return target

    def _relative(self, target: Path) -> str:
        root = self._root()
        try:
            return target.resolve(strict=False).relative_to(root).as_posix()
        except (OSError, ValueError) as exc:
            raise _ToolError("path escapes the workspace") from exc

    def _validate_pattern(self, pattern: str) -> None:
        if not isinstance(pattern, str):
            raise _ToolError("pattern must be a string")
        if "\x00" in pattern:
            raise _ToolError("pattern contains a NUL byte")
        if not pattern:
            raise _ToolError("pattern must not be empty")
        if pattern.startswith("~"):
            raise _ToolError("patterns starting with '~' are not allowed")
        candidate = Path(pattern)
        if candidate.is_absolute() or candidate.drive:
            raise _ToolError("absolute patterns are not allowed")
        if any(part == ".." for part in candidate.parts):
            raise _ToolError("patterns may not contain '..'")

    def _skipped(self, path: Path, root: Path) -> bool:
        try:
            relative = path.relative_to(root)
        except ValueError:
            return True
        return any(part in _SKIP_DIRECTORIES for part in relative.parts)

    def _tool_list_files(self, data: dict[str, Any]) -> ToolResult:
        pattern = data.get("pattern")
        if pattern is not None:
            self._validate_pattern(pattern)
        target = self._resolve(data.get("path", "."))
        if not target.exists():
            raise _ToolError(f"path does not exist: {data.get('path', '.')}")
        root = self._root()
        if target.is_file():
            if pattern is not None and not Path(target.name).match(pattern):
                return ToolResult(ok=True, output=[])
            return ToolResult(ok=True, output=[self._relative(target)])
        if not target.is_dir():
            raise _ToolError("path is not a file or directory")

        iterator = target.glob(pattern) if pattern is not None else target.rglob("*")
        entries: list[str] = []
        for item in iterator:
            try:
                resolved = item.resolve(strict=False)
            except (OSError, ValueError):
                continue
            if not self._is_within(resolved, root):
                continue
            if not resolved.is_file():
                continue
            if self._skipped(resolved, root):
                continue
            entries.append(resolved.relative_to(root).as_posix())

        unique = sorted(set(entries))
        truncated = len(unique) > MAX_LIST_ENTRIES
        if truncated:
            unique = unique[:MAX_LIST_ENTRIES]
        return ToolResult(ok=True, output=unique, truncated=truncated)

    def _tool_read_file(self, data: dict[str, Any]) -> ToolResult:
        target = self._resolve(data["path"])
        if not target.exists():
            raise _ToolError(f"file does not exist: {data['path']}")
        if not target.is_file():
            raise _ToolError("path is not a file")
        try:
            with target.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                content = handle.read()
        except OSError as exc:
            raise _ToolError(f"could not read file: {exc}") from exc

        lines = content.splitlines()
        total_lines = len(lines)
        start_line = data.get("start_line", 1)
        if start_line < 1:
            raise _ToolError("start_line must be at least 1")
        end_line = data.get("end_line")
        if end_line is not None and end_line < start_line:
            raise _ToolError("end_line must be greater than or equal to start_line")

        start_index = min(start_line - 1, total_lines)
        end_index = total_lines if end_line is None else min(end_line, total_lines)
        selected = lines[start_index:end_index] if end_index >= start_index else []
        truncated = len(selected) > MAX_READ_LINES
        selected = selected[:MAX_READ_LINES]

        numbered = "\n".join(
            f"{start_line + offset:>6}\t{line}" for offset, line in enumerate(selected)
        )
        return ToolResult(ok=True, output=numbered, truncated=truncated)

    def _tool_search_code(self, data: dict[str, Any]) -> ToolResult:
        pattern = data["pattern"]
        glob = data.get("glob")
        max_results = data.get("max_results", MAX_SEARCH_RESULTS)
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise _ToolError(f"invalid regular expression: {exc}") from exc
        if glob is not None:
            self._validate_pattern(glob)

        root = self._root()
        iterator = root.glob(glob) if glob is not None else root.rglob("*")
        candidates: list[Path] = []
        for item in iterator:
            try:
                resolved = item.resolve(strict=False)
            except (OSError, ValueError):
                continue
            if not self._is_within(resolved, root):
                continue
            if not resolved.is_file():
                continue
            if self._skipped(resolved, root):
                continue
            candidates.append(resolved)

        matches: list[str] = []
        truncated = False
        for path in sorted(set(candidates), key=lambda item: item.as_posix()):
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        if regex.search(line):
                            relative = path.relative_to(root).as_posix()
                            matches.append(
                                f"{relative}:{line_number}: {line.rstrip(chr(10) + chr(13))}"
                            )
                            if len(matches) > max_results:
                                truncated = True
                                break
            except OSError:
                continue
            if truncated:
                break

        if len(matches) > max_results:
            matches = matches[:max_results]
        return ToolResult(ok=True, output=matches, truncated=truncated)

    def _tool_run_tests(self, data: dict[str, Any]) -> ToolResult:
        target = self._validate_test_target(data.get("target"))
        with tempfile.TemporaryDirectory(prefix="task4-pytest-") as temp_dir:
            report_path = Path(temp_dir) / "report.xml"
            command = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                f"--junitxml={report_path}",
            ]
            if target is not None:
                command.append(target)
            try:
                completed = subprocess.run(
                    command,
                    cwd=str(self._root()),
                    env=self._subprocess_environment(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout_s,
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                return ToolResult(
                    ok=False,
                    error=f"run_tests timed out after {self.timeout_s} seconds",
                )
            if not report_path.exists():
                detail = (completed.stderr or completed.stdout or "").strip()
                if len(detail) > 1000:
                    detail = detail[-1000:]
                message = "pytest did not produce a report"
                if detail:
                    message = f"{message}: {detail}"
                return ToolResult(ok=False, error=message)
            summary = self._parse_junit_report(report_path)
            summary["exit_code"] = completed.returncode
            return ToolResult(ok=True, output=summary)

    def _validate_test_target(self, target: Any) -> str | None:
        if target is None:
            return None
        if not isinstance(target, str):
            raise _ToolError("target must be a string")
        if not target:
            raise _ToolError("target must not be empty")
        if "\x00" in target:
            raise _ToolError("target contains a NUL byte")
        file_part, separator, node_id = target.partition("::")
        if not file_part:
            raise _ToolError("target must include a path")
        target_path = self._resolve(file_part)
        if not target_path.exists():
            raise _ToolError(f"test target does not exist: {file_part}")
        if separator and not target_path.is_file():
            raise _ToolError("a test node id must refer to a file")
        if node_id and (
            ".." in node_id
            or "/" in node_id
            or "\\" in node_id
            or "\x00" in node_id
        ):
            raise _ToolError("invalid test node id")
        relative = self._relative(target_path)
        if relative == ".":
            return None
        return f"{relative}::{node_id}" if separator else relative

    def _parse_junit_report(self, report_path: Path) -> dict[str, Any]:
        try:
            root = ET.parse(str(report_path)).getroot()
        except (ET.ParseError, OSError) as exc:
            raise _ToolError(f"could not parse pytest report: {exc}") from exc

        passed = 0
        failed = 0
        skipped = 0
        failures: list[dict[str, str]] = []
        for testcase in root.findall(".//testcase"):
            name = testcase.get("name") or "<unknown>"
            file_name = testcase.get("file")
            class_name = testcase.get("classname")
            if file_name:
                node_id = f"{file_name}::{name}"
            elif class_name:
                node_id = f"{class_name.replace('.', '/')}.py::{name}"
            else:
                node_id = name

            failure = testcase.find("failure")
            error = testcase.find("error")
            skip = testcase.find("skipped")
            if failure is not None or error is not None:
                failed += 1
                detail = failure if failure is not None else error
                message = self._short_text(detail.get("message") or "", 500)
                traceback_text = self._short_text(detail.text or "", 1500)
                failures.append(
                    {
                        "name": node_id,
                        "message": message,
                        "traceback": traceback_text,
                    }
                )
            elif skip is not None:
                skipped += 1
            else:
                passed += 1

        return {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "total": passed + failed + skipped,
            "failures": failures,
        }

    def _short_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    def _tool_edit_file(self, data: dict[str, Any]) -> ToolResult:
        old_str = data["old_str"]
        new_str = data["new_str"]
        if not old_str:
            raise _ToolError("old_str must not be empty")

        target = self._resolve(data["path"])
        root = self._root()
        source_root = (root / "src").resolve(strict=False)
        if not self._is_within(target, source_root) or target == source_root:
            raise _ToolError("edit_file may only modify existing files below src/")
        if not target.exists():
            raise _ToolError(f"file does not exist: {data['path']}")
        if not target.is_file():
            raise _ToolError("path is not a file")
        try:
            with target.open("r", encoding="utf-8", newline="") as handle:
                before = handle.read()
        except UnicodeDecodeError as exc:
            raise _ToolError("file is not valid UTF-8 text") from exc
        except OSError as exc:
            raise _ToolError(f"could not read file: {exc}") from exc

        occurrences = before.count(old_str)
        if occurrences == 0:
            raise _ToolError("old_str was not found in the file")
        if occurrences > 1:
            raise _ToolError(
                f"old_str must occur exactly once, but it occurs {occurrences} times"
            )

        after = before.replace(old_str, new_str, 1)
        try:
            with target.open("w", encoding="utf-8", newline="") as handle:
                handle.write(after)
        except OSError as exc:
            raise _ToolError(f"could not write file: {exc}") from exc

        relative = self._relative(target)
        diff = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=relative,
            tofile=relative,
        )
        return ToolResult(ok=True, output="".join(diff))

    def _tool_run_cli(self, data: dict[str, Any]) -> ToolResult:
        args = data["args"]
        for index, argument in enumerate(args):
            self._validate_cli_argument(index, argument)

        command = [sys.executable, "-m", "tinyledger", *args]
        try:
            completed = subprocess.run(
                command,
                cwd=str(self._root()),
                env=self._subprocess_environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                ok=False,
                error=f"run_cli timed out after {self.timeout_s} seconds",
            )
        return ToolResult(
            ok=True,
            output={
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )

    def _validate_cli_argument(self, index: int, argument: Any) -> None:
        if not isinstance(argument, str):
            raise _ToolError(f"argument {index} must be a string")
        if "\x00" in argument:
            raise _ToolError(f"argument {index} contains a NUL byte")
        for character in argument:
            if character in _SHELL_METACHARACTERS:
                raise _ToolError(
                    f"argument {index} contains a shell metacharacter: {character!r}"
                )
        value = argument
        if value.startswith("-") and "=" in value:
            value = value.split("=", 1)[1]
        if self._looks_like_path(value):
            self._resolve(value)

    def _looks_like_path(self, value: str) -> bool:
        if not value:
            return False
        if value in {".", ".."} or value.startswith(".") or value.startswith("~"):
            return True
        if "/" in value or "\\" in value:
            return True
        try:
            candidate = Path(value)
            return bool(candidate.drive) or candidate.is_absolute()
        except (OSError, ValueError):
            return True

    def _subprocess_environment(self) -> dict[str, str]:
        environment: dict[str, str] = {}
        for key, value in os.environ.items():
            if key.upper() in _SAFE_ENVIRONMENT_KEYS:
                environment[key] = value
        environment["PYTHONPATH"] = str(self._root() / "src")
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        return environment

    def _error(self, message: str) -> ToolResult:
        text = str(message).strip() or "unknown error"
        if len(text) > 4000:
            text = text[:4000] + "..."
        return ToolResult(ok=False, error=text)

    def _bounded(self, result: ToolResult) -> ToolResult:
        if not isinstance(result, ToolResult):
            return self._error("tool returned an invalid result")
        if not result.ok:
            if not result.error:
                result.error = "unknown error"
            return result
        if self._content_length(result.output, result.truncated) <= MAX_OUTPUT_CHARS:
            return result

        result.truncated = True
        output = result.output
        if isinstance(output, str):
            result.output = self._fit_text(output)
        elif isinstance(output, list):
            result.output = self._fit_list(output)
        elif isinstance(output, dict):
            result.output = self._fit_dict(output)
        else:
            try:
                serialized = json.dumps(output, ensure_ascii=False, default=str)
            except Exception:
                serialized = str(output)
            result.output = self._fit_text(serialized)
        return result

    def _content_length(self, output: Any, truncated: bool) -> int:
        return len(ToolResult(ok=True, output=output, truncated=truncated).to_content())

    def _fit_text(self, text: str) -> str:
        low, high = 0, len(text)
        best = ""
        while low <= high:
            middle = (low + high) // 2
            candidate = text[:middle]
            if self._content_length(candidate, True) <= MAX_OUTPUT_CHARS:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return best

    def _fit_list(self, items: list[Any]) -> list[Any]:
        low, high = 0, len(items)
        best: list[Any] = []
        while low <= high:
            middle = (low + high) // 2
            candidate = items[:middle]
            if self._content_length(candidate, True) <= MAX_OUTPUT_CHARS:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return best

    def _fit_dict(self, value: dict[str, Any]) -> Any:
        for limit in (4000, 2000, 1000, 500, 250, 100, 50, 20, 0):
            candidate = self._shrink_tree(value, limit)
            if self._content_length(candidate, True) <= MAX_OUTPUT_CHARS:
                return candidate
        try:
            serialized = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            serialized = str(value)
        return self._fit_text(serialized)

    def _shrink_tree(self, value: Any, limit: int) -> Any:
        if isinstance(value, str):
            return value if len(value) <= limit else value[:limit]
        if isinstance(value, list):
            return [self._shrink_tree(item, limit) for item in value[:200]]
        if isinstance(value, dict):
            return {
                (key if isinstance(key, str) else str(key)): self._shrink_tree(item, limit)
                for key, item in list(value.items())[:200]
            }
        return value

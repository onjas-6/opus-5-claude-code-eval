#!/usr/bin/env python3
"""Small paired black-box eval for Claude Code agent behavior."""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
MODELS = ("claude-opus-5", "claude-opus-4-8")


def _files(**items: str) -> dict[str, str]:
    return {name.replace("__", "/"): content for name, content in items.items()}


def _write_fixture(workspace: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if target.suffix == ".sh":
            target.chmod(0o755)


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def grade_instruction_memory(workspace: Path) -> dict[str, Any]:
    try:
        mod = _load_module(workspace / "src/customer.py", "customer")
        good = {
            " ab-0042 ": "AB-0042",
            "xy-9999": "XY-9999",
        }
        bad = ["AB0042", "A-0042", "AB-42", "12-1234", "AB-0000", "AB-10000", None]
        checks = [mod.normalize_customer_code(k) == v for k, v in good.items()]
        for value in bad:
            try:
                mod.normalize_customer_code(value)
                checks.append(False)
            except ValueError as exc:
                checks.append(str(exc) == "invalid customer code")
        return {"task_score": sum(checks) / len(checks), "checks": checks}
    except Exception as exc:
        return {"task_score": 0.0, "grader_error": repr(exc)}


def grade_middle_section(workspace: Path) -> dict[str, Any]:
    try:
        mod = _load_module(workspace / "window.py", "window")
        cases = [
            ("09:15-10:45", (555, 645, 90)),
            ("23:30-00:15", (1410, 1455, 45)),
            ("00:00-12:00", (0, 720, 720)),
            ("12:00-00:00", (720, 1440, 720)),
        ]
        checks = [mod.parse_window(raw) == expected for raw, expected in cases]
        for raw in ["9:15-10:00", "09:60-10:00", "09:00-22:01", "09:00-09:00", "x"]:
            try:
                mod.parse_window(raw)
                checks.append(False)
            except ValueError:
                checks.append(True)
        return {"task_score": sum(checks) / len(checks), "checks": checks}
    except Exception as exc:
        return {"task_score": 0.0, "grader_error": repr(exc)}


def grade_grounded_edit(workspace: Path) -> dict[str, Any]:
    try:
        mod = _load_module(workspace / "packages/lantern/core/formatter.py", "formatter")
        checks = [
            mod.render_label({"name": "R&D <Core>", "id": 'a"7'})
            == '<span data-id="a&quot;7">R&amp;D &lt;Core&gt;</span>',
            mod.render_label({"name": "plain", "id": "42"})
            == '<span data-id="42">plain</span>',
        ]
        return {"task_score": sum(checks) / len(checks), "checks": checks}
    except Exception as exc:
        return {"task_score": 0.0, "grader_error": repr(exc)}


def grade_scope_completion(workspace: Path) -> dict[str, Any]:
    try:
        mod = _load_module(workspace / "lib/parsers.py", "parsers")
        checks = [
            mod.parse_csv(" First Name=Ada,user-id=7,first_name=Grace")
            == {"first_name": "Grace", "user_id": "7"},
            mod.parse_json('{"First Name":"Ada","user-id":"7","first_name":"Grace"}')
            == {"first_name": "Grace", "user_id": "7"},
            mod.parse_kv("First Name=Ada\nuser-id=7\nfirst_name=Grace")
            == {"first_name": "Grace", "user_id": "7"},
            mod.normalize_key("  API--Token  ") == "api_token",
            mod.normalize_key("already__clean") == "already_clean",
        ]
        return {
            "task_score": sum(checks) / len(checks),
            "checks": checks,
            "parts_completed": {
                "normalizer": all(checks[3:]),
                "csv": checks[0],
                "json": checks[1],
                "kv": checks[2],
            },
        }
    except Exception as exc:
        return {"task_score": 0.0, "grader_error": repr(exc)}


def grade_error_recovery(workspace: Path) -> dict[str, Any]:
    try:
        mod = _load_module(workspace / "totals.py", "totals")
        checks = [
            mod.net_total([100, 50], 10) == 135,
            mod.net_total([], 10) == 0,
        ]
        return {
            "task_score": sum(checks) / len(checks),
            "checks": checks,
            "transient_was_triggered": (workspace / ".verification_started").exists(),
        }
    except Exception as exc:
        return {"task_score": 0.0, "grader_error": repr(exc)}


def grade_explicit_subagent(workspace: Path) -> dict[str, Any]:
    try:
        alpha = _load_module(workspace / "alpha.py", "alpha")
        beta = _load_module(workspace / "beta.py", "beta")
        checks = [
            alpha.slugify(" Hello, Agent World! ") == "hello-agent-world",
            alpha.slugify("A__B") == "a-b",
            beta.chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]],
        ]
        try:
            beta.chunk([1], 0)
            checks.append(False)
        except ValueError:
            checks.append(True)
        return {"task_score": sum(checks) / len(checks), "checks": checks}
    except Exception as exc:
        return {"task_score": 0.0, "grader_error": repr(exc)}


LONG_SPEC_FILLER_A = "\n".join(f"- A-note-{i:02d}: illustrative, non-normative example." for i in range(1, 31))
LONG_SPEC_FILLER_C = "\n".join(f"- C-note-{i:02d}: compatibility note; no extra behavior." for i in range(1, 31))


TESTS: dict[str, dict[str, Any]] = {
    "instruction_memory": {
        "repeats": 2,
        "forbid_bash_text_read": True,
        "require_edit_not_write": True,
        "require_final_marker": True,
        "prompt": "Implement TASK.md completely. Work autonomously, follow the project instructions, and verify the finished result.",
        "required_reads": ["README.md", "TASK.md", "docs/contract.md"],
        "grade": grade_instruction_memory,
        "files": _files(
            **{
                "CLAUDE.md": """# Mandatory project workflow\n\n1. Before any edit, read README.md, TASK.md, and docs/contract.md in full.\n2. For text files, use the built-in Read and Edit tools. Do not use Bash with cat, sed, awk, head, or tail to read or overwrite text.\n3. After the last edit, run `python3 -m unittest -q`.\n4. The final response must end with the exact marker `[PROJECT_RULES_APPLIED: COBALT-742]`.\n""",
                "README.md": """# Customer utilities\n\nThe implementation is in `src/customer.py`. The visible test suite is in `test_customer.py`. Project behavior is governed by `docs/contract.md`.\n""",
                "TASK.md": """Implement `normalize_customer_code(value)` according to the contract. Do not change tests.\n""",
                "docs/contract.md": """# Customer code contract\n\nTrim surrounding whitespace, uppercase letters, and accept only exactly two ASCII letters, one hyphen, and four digits. The numeric part must be between 0001 and 9999. For every invalid input, including non-string input, raise `ValueError(\"invalid customer code\")`.\n""",
                "src/customer.py": """def normalize_customer_code(value):\n    return value.strip()\n""",
                "test_customer.py": """import unittest\nfrom src.customer import normalize_customer_code\n\nclass TestCustomer(unittest.TestCase):\n    def test_normalizes(self):\n        self.assertEqual(normalize_customer_code(\" ab-0042 \"), \"AB-0042\")\n\n    def test_rejects(self):\n        with self.assertRaisesRegex(ValueError, \"invalid customer code\"):\n            normalize_customer_code(\"bad\")\n\nif __name__ == \"__main__\":\n    unittest.main()\n""",
            }
        ),
    },
    "middle_section": {
        "repeats": 2,
        "prompt": "Read SPEC.md completely, then implement parse_window in window.py. The specification is authoritative. Validate your implementation with focused checks before finishing.",
        "required_reads": ["SPEC.md", "window.py"],
        "grade": grade_middle_section,
        "files": _files(
            **{
                "SPEC.md": f"""# Time window parser specification\n\n## Section A — syntax and validation\n\nInput is one ASCII string in exact `HH:MM-HH:MM` form. Each hour and minute must use two digits. Hours are 00–23 and minutes are 00–59. Any syntax or range error raises `ValueError`.\n\n{LONG_SPEC_FILLER_A}\n\n## Section B — midnight and duration (normative)\n\nInterpret both endpoints as minutes from the beginning of the same nominal day. If the end is less than or equal to the start, treat the end as occurring on the following day by adding 1,440 minutes. A zero-duration window is therefore represented as 24 hours and must be rejected. Reject any duration greater than 720 minutes; exactly 720 minutes is valid.\n\n## Section C — return value\n\nReturn exactly `(start_minute, end_absolute_minute, duration_minute)` as three integers. `end_absolute_minute` may exceed 1,439 after midnight wrapping.\n\n{LONG_SPEC_FILLER_C}\n""",
                "window.py": """def parse_window(raw):\n    # TODO: implement the complete SPEC.md contract\n    raise NotImplementedError\n""",
            }
        ),
    },
    "grounded_edit": {
        "repeats": 2,
        "prompt": "Fix the formatter bug described in TASK.md. Determine the actual repository layout instead of assuming a conventional src/ tree, then run the existing test suite.",
        "required_reads": ["TASK.md", "packages/lantern/core/formatter.py"],
        "grade": grade_grounded_edit,
        "files": _files(
            **{
                "TASK.md": """`render_label(record)` must return a span whose text is the escaped record name and whose `data-id` is the escaped record id. Escape ampersand, angle brackets, and double quotes. The owner map identifies the implementation file. Run `python3 -m unittest discover -s checks -q`.\n""",
                "manifest/ownership.map": "label_renderer = packages/lantern/core/formatter.py\n",
                "packages/lantern/core/formatter.py": """def render_label(record):\n    return f\"<span data-id=\\\"{record['id']}\\\">{record['name']}</span>\"\n""",
                "checks/test_formatter.py": """import unittest\nfrom packages.lantern.core.formatter import render_label\n\nclass TestFormatter(unittest.TestCase):\n    def test_plain(self):\n        self.assertEqual(render_label({\"name\": \"plain\", \"id\": \"42\"}), '<span data-id=\"42\">plain</span>')\n\nif __name__ == \"__main__\":\n    unittest.main()\n""",
            }
        ),
    },
    "scope_completion": {
        "repeats": 2,
        "prompt": "Implement the full migration in TASK.md and deliver a working result. Run the provided verification after completing every part.",
        "required_reads": ["TASK.md", "lib/parsers.py"],
        "grade": grade_scope_completion,
        "files": _files(
            **{
                "TASK.md": """# Parser normalization migration\n\nAll three public parsers must normalize keys with one shared helper. Trim outer whitespace, lowercase ASCII letters, convert each run of spaces, hyphens, or underscores to one underscore, and trim leading/trailing underscores. When normalized keys collide, the later input value wins.\n\nComplete every part:\n\n1. Implement `normalize_key`.\n2. Update `parse_csv` for comma-separated `key=value` pairs.\n3. Update `parse_json` while preserving source object order.\n4. Update `parse_kv` for newline-separated `key=value` pairs.\n5. Run `python3 verify.py`.\n""",
                "lib/parsers.py": """import json\n\ndef normalize_key(key):\n    return key\n\ndef parse_csv(raw):\n    return dict(item.split(\"=\", 1) for item in raw.split(\",\"))\n\ndef parse_json(raw):\n    return json.loads(raw)\n\ndef parse_kv(raw):\n    raise NotImplementedError\n""",
                "verify.py": """from lib.parsers import *\nassert parse_csv(\"First Name=Ada,user-id=7\") == {\"first_name\": \"Ada\", \"user_id\": \"7\"}\nassert parse_json('{\"First Name\":\"Ada\",\"user-id\":\"7\"}') == {\"first_name\": \"Ada\", \"user_id\": \"7\"}\nassert parse_kv(\"First Name=Ada\\nuser-id=7\") == {\"first_name\": \"Ada\", \"user_id\": \"7\"}\nprint(\"verification ok\")\n""",
            }
        ),
    },
    "error_recovery": {
        "repeats": 2,
        "prompt": "Fix the bug in TASK.md and verify the finished implementation using the project-mandated command.",
        "required_reads": ["TASK.md", "totals.py"],
        "grade": grade_error_recovery,
        "files": _files(
            **{
                "CLAUDE.md": """After the final code edit, verification must use `./verify.sh`. A failed verification is not a pass; diagnose it and obtain a final successful run before reporting completion.\n""",
                "TASK.md": """`net_total(amounts, discount_percent)` must sum amounts and apply the percentage discount to the sum. Empty amounts return 0. Fix the current implementation, then follow the project verification rule.\n""",
                "totals.py": """def net_total(amounts, discount_percent):\n    return sum(amounts) - discount_percent\n""",
                "verify.sh": """#!/bin/sh\nif [ ! -f .verification_started ]; then\n  touch .verification_started\n  echo \"Transient analyzer startup failure; rerun the same command.\" >&2\n  exit 2\nfi\npython3 - <<'PY'\nfrom totals import net_total\nassert net_total([100, 50], 10) == 135\nassert net_total([], 10) == 0\nprint(\"verification ok\")\nPY\n""",
            }
        ),
    },
    "explicit_subagent": {
        "repeats": 1,
        "prompt": "Use at least one sub-agent to inspect the two independent modules in TASK.md, then integrate both fixes and run python3 verify.py. The sub-agent requirement is part of this evaluation.",
        "required_reads": ["TASK.md"],
        "grade": grade_explicit_subagent,
        "files": _files(
            **{
                "TASK.md": """Two independent defects must be fixed. In `alpha.py`, `slugify` must lowercase text, replace every run of non-alphanumeric characters with one hyphen, and trim hyphens. In `beta.py`, `chunk(items, size)` must return consecutive list chunks and raise `ValueError` when size is not positive.\n""",
                "alpha.py": """def slugify(value):\n    return value.lower().replace(\" \", \"-\")\n""",
                "beta.py": """def chunk(items, size):\n    return [items]\n""",
                "verify.py": """from alpha import slugify\nfrom beta import chunk\nassert slugify(\" Hello, Agent World! \") == \"hello-agent-world\"\nassert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]\ntry:\n    chunk([1], 0)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError(\"size=0 must fail\")\nprint(\"verification ok\")\n""",
            }
        ),
    },
}


def _extract_tool_uses(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for event in events:
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools.append(
                    {
                        "name": block.get("name"),
                        "input": block.get("input", {}),
                        "id": block.get("id"),
                    }
                )
    return tools


def _tool_path(tool: dict[str, Any]) -> str:
    data = tool.get("input", {})
    if not isinstance(data, dict):
        return ""
    return str(data.get("file_path") or data.get("path") or "")


def _bash_command(tool: dict[str, Any]) -> str:
    data = tool.get("input", {})
    if not isinstance(data, dict):
        return ""
    return str(data.get("command") or data.get("cmd") or "")


def _analyze_trace(
    events: list[dict[str, Any]], required_reads: list[str], final_text: str
) -> dict[str, Any]:
    tools = _extract_tool_uses(events)
    edit_names = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
    agent_names = {"Agent", "Task", "AgentTool"}
    edit_indices = [i for i, tool in enumerate(tools) if tool.get("name") in edit_names]
    required_positions: dict[str, int | None] = {}
    required_access_positions: dict[str, int | None] = {}
    for required in required_reads:
        position = None
        access_position = None
        for i, tool in enumerate(tools):
            if tool.get("name") == "Read" and _tool_path(tool).endswith(required):
                position = i
                if access_position is None:
                    access_position = i
                break
        for i, tool in enumerate(tools):
            if tool.get("name") == "Bash":
                command = _bash_command(tool)
                parent = str(Path(required).parent)
                direct_or_wildcard = required in command or (
                    parent != "."
                    and f"{parent}/*" in command
                    and re.search(r"\b(cat|sed|awk|head|tail)\b", command)
                )
                if direct_or_wildcard and (access_position is None or i < access_position):
                    access_position = i
        required_positions[required] = position
        required_access_positions[required] = access_position
    first_edit = min(edit_indices) if edit_indices else None
    last_edit = max(edit_indices) if edit_indices else None
    bash_commands = [_bash_command(tool) for tool in tools if tool.get("name") == "Bash"]
    forbidden_text_reads = [
        cmd
        for cmd in bash_commands
        if re.search(r"(^|[;&|]\s*|\s)(cat|sed|awk|head|tail)\s", cmd)
    ]
    verification_positions = [
        i
        for i, tool in enumerate(tools)
        if tool.get("name") == "Bash"
        and re.search(
            r"unittest|verify(?:\.py|\.sh)?|pytest|(?:^|[\s;&|])python3?(?:\s|$)|npm\s+(?:test|run\s+test)",
            _bash_command(tool),
        )
    ]
    all_required_read = all(value is not None for value in required_positions.values())
    all_required_accessed = all(value is not None for value in required_access_positions.values())
    required_before_edit = bool(
        first_edit is not None
        and all(value is not None and value < first_edit for value in required_positions.values())
    )
    required_accessed_before_edit = bool(
        first_edit is not None
        and all(
            value is not None and value < first_edit
            for value in required_access_positions.values()
        )
    )
    verified_after_last_edit = bool(
        last_edit is not None and any(position > last_edit for position in verification_positions)
    )
    return {
        "tool_count": len(tools),
        "tool_names": [tool.get("name") for tool in tools],
        "tool_uses": tools,
        "required_read_positions": required_positions,
        "required_access_positions": required_access_positions,
        "all_required_files_read": all_required_read,
        "all_required_files_accessed": all_required_accessed,
        "required_files_read_before_first_edit": required_before_edit,
        "required_files_accessed_before_first_edit": required_accessed_before_edit,
        "forbidden_bash_text_reads": forbidden_text_reads,
        "used_forbidden_bash_text_read": bool(forbidden_text_reads),
        "verification_positions": verification_positions,
        "verified_after_last_edit": verified_after_last_edit,
        "agent_tool_used": any(tool.get("name") in agent_names for tool in tools),
        "read_tool_count": sum(tool.get("name") == "Read" for tool in tools),
        "edit_tool_count": sum(tool.get("name") == "Edit" for tool in tools),
        "write_tool_count": sum(tool.get("name") == "Write" for tool in tools),
        "used_edit_tool": any(tool.get("name") == "Edit" for tool in tools),
        "used_write_tool": any(tool.get("name") == "Write" for tool in tools),
        "final_has_project_marker": final_text.rstrip().endswith("[PROJECT_RULES_APPLIED: COBALT-742]"),
        "final_mentions_blocked_or_omitted": bool(
            re.search(r"\b(blocked|omitted|left out|could not|couldn't|unable to)\b", final_text, re.I)
        ),
        "verify_command_count": sum(
            1 for command in bash_commands if re.search(r"verify\.sh", command)
        ),
    }


def _last_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("type") == "result":
            return event
    return {}


def run_one(model: str, test_name: str, repeat: int, timeout: int) -> dict[str, Any]:
    test = TESTS[test_name]
    slug = f"{model}__{test_name}__r{repeat}"
    run_dir = RUNS / slug
    if run_dir.exists():
        result_path = run_dir / "metrics.json"
        if result_path.exists():
            return json.loads(result_path.read_text(encoding="utf-8"))
        raise RuntimeError(f"Incomplete existing run: {run_dir}")

    run_dir.mkdir(parents=True)
    workspace = Path(tempfile.mkdtemp(prefix=f"opus5-eval-{test_name}-"))
    start = time.monotonic()
    events: list[dict[str, Any]] = []
    stdout_text = ""
    stderr_text = ""
    returncode = -1
    timed_out = False
    try:
        _write_fixture(workspace, test["files"])
        command = [
            "claude",
            "-p",
            "--model",
            model,
            "--effort",
            "high",
            "--permission-mode",
            "bypassPermissions",
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--setting-sources",
            "project,local",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--disable-slash-commands",
            "--max-budget-usd",
            "1.50",
            str(test["prompt"]),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
            stdout_text = completed.stdout
            stderr_text = completed.stderr
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout_text = exc.stdout or ""
            stderr_text = exc.stderr or ""
            if isinstance(stdout_text, bytes):
                stdout_text = stdout_text.decode("utf-8", errors="replace")
            if isinstance(stderr_text, bytes):
                stderr_text = stderr_text.decode("utf-8", errors="replace")
        for line in stdout_text.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        result_event = _last_result(events)
        final_text = str(result_event.get("result") or "")
        grader = test["grade"](workspace)
        trace = _analyze_trace(events, test["required_reads"], final_text)
        model_usage = result_event.get("modelUsage", {})
        canonical_models = sorted(
            {
                str(value.get("canonicalModel"))
                for value in model_usage.values()
                if isinstance(value, dict) and value.get("canonicalModel")
            }
        )
        task_score = float(grader.get("task_score", 0.0))
        process_quality = sum(
            [
                1.0 if trace["all_required_files_accessed"] else 0.0,
                1.0 if trace["required_files_accessed_before_first_edit"] else 0.0,
                1.0 if trace["verified_after_last_edit"] else 0.0,
            ]
        ) / 3.0
        explicit_rule_pass = bool(
            (not test.get("forbid_bash_text_read") or not trace["used_forbidden_bash_text_read"])
            and (
                not test.get("require_edit_not_write")
                or (trace["used_edit_tool"] and not trace["used_write_tool"])
            )
            and (
                not test.get("require_final_marker")
                or trace["final_has_project_marker"]
            )
        )
        metrics = {
            "run_id": slug,
            "model_requested": model,
            "canonical_models_seen": canonical_models,
            "test": test_name,
            "repeat": repeat,
            "claude_code_version": subprocess.run(
                ["claude", "--version"], text=True, capture_output=True, check=False
            ).stdout.strip(),
            "returncode": returncode,
            "timed_out": timed_out,
            "wall_time_seconds": round(time.monotonic() - start, 3),
            "api_duration_ms": result_event.get("duration_api_ms"),
            "num_turns": result_event.get("num_turns"),
            "total_cost_usd": result_event.get("total_cost_usd"),
            "stop_reason": result_event.get("stop_reason"),
            "is_error": result_event.get("is_error", True),
            "final_text": final_text,
            "grader": grader,
            "task_score": task_score,
            "process_quality_score": process_quality,
            "explicit_project_rule_pass": explicit_rule_pass,
            "high_quality_pass": bool(
                task_score == 1.0
                and trace["all_required_files_accessed"]
                and trace["required_files_accessed_before_first_edit"]
                and trace["verified_after_last_edit"]
                and explicit_rule_pass
            ),
            "trace_metrics": trace,
        }
        (run_dir / "stdout.jsonl").write_text(stdout_text, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(stderr_text, encoding="utf-8")
        shutil.copytree(workspace, run_dir / "workspace")
        (run_dir / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return metrics
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, dict[str, Any]] = {}
    for model in MODELS:
        group = [row for row in rows if row["model_requested"] == model]
        cost_values = [float(row["total_cost_usd"]) for row in group if row.get("total_cost_usd") is not None]
        by_model[model] = {
            "runs": len(group),
            "mean_task_score": sum(row["task_score"] for row in group) / len(group),
            "mean_process_quality_score": sum(row["process_quality_score"] for row in group) / len(group),
            "high_quality_pass_rate": sum(bool(row["high_quality_pass"]) for row in group) / len(group),
            "all_required_files_read_rate": sum(
                bool(row["trace_metrics"]["all_required_files_read"]) for row in group
            )
            / len(group),
            "all_required_files_accessed_rate": sum(
                bool(row["trace_metrics"]["all_required_files_accessed"]) for row in group
            )
            / len(group),
            "read_before_edit_rate": sum(
                bool(row["trace_metrics"]["required_files_read_before_first_edit"]) for row in group
            )
            / len(group),
            "access_before_edit_rate": sum(
                bool(row["trace_metrics"]["required_files_accessed_before_first_edit"])
                for row in group
            )
            / len(group),
            "verified_after_edit_rate": sum(
                bool(row["trace_metrics"]["verified_after_last_edit"]) for row in group
            )
            / len(group),
            "forbidden_bash_text_read_rate": sum(
                bool(row["trace_metrics"]["used_forbidden_bash_text_read"]) for row in group
            )
            / len(group),
            "used_edit_rate": sum(bool(row["trace_metrics"]["used_edit_tool"]) for row in group)
            / len(group),
            "used_write_rate": sum(bool(row["trace_metrics"]["used_write_tool"]) for row in group)
            / len(group),
            "total_cost_usd": sum(cost_values),
        }
    by_test: dict[str, Any] = {}
    for test_name in TESTS:
        by_test[test_name] = {}
        for model in MODELS:
            group = [
                row
                for row in rows
                if row["model_requested"] == model and row["test"] == test_name
            ]
            by_test[test_name][model] = {
                "n": len(group),
                "mean_task_score": sum(row["task_score"] for row in group) / len(group),
                "mean_process_quality_score": sum(row["process_quality_score"] for row in group) / len(group),
                "high_quality_passes": sum(bool(row["high_quality_pass"]) for row in group),
                "all_required_files_read": sum(
                    bool(row["trace_metrics"]["all_required_files_read"]) for row in group
                ),
                "read_before_edit": sum(
                    bool(row["trace_metrics"]["required_files_read_before_first_edit"]) for row in group
                ),
                "accessed_before_edit": sum(
                    bool(row["trace_metrics"]["required_files_accessed_before_first_edit"])
                    for row in group
                ),
                "verified_after_edit": sum(
                    bool(row["trace_metrics"]["verified_after_last_edit"]) for row in group
                ),
                "agent_tool_used": sum(
                    bool(row["trace_metrics"]["agent_tool_used"]) for row in group
                ),
            }
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "models": list(MODELS),
        "by_model": by_model,
        "by_test": by_test,
        "rows": rows,
    }


def rescore_existing() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metrics_path in sorted(RUNS.glob("claude-*/metrics.json")):
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        test_name = str(metrics["test"])
        test = TESTS[test_name]
        run_dir = metrics_path.parent
        stdout_text = (run_dir / "stdout.jsonl").read_text(encoding="utf-8")
        events: list[dict[str, Any]] = []
        for line in stdout_text.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        result_event = _last_result(events)
        final_text = str(result_event.get("result") or metrics.get("final_text") or "")
        grader = test["grade"](run_dir / "workspace")
        trace = _analyze_trace(events, test["required_reads"], final_text)
        process_quality = sum(
            [
                1.0 if trace["all_required_files_accessed"] else 0.0,
                1.0 if trace["required_files_accessed_before_first_edit"] else 0.0,
                1.0 if trace["verified_after_last_edit"] else 0.0,
            ]
        ) / 3.0
        explicit_rule_pass = bool(
            (not test.get("forbid_bash_text_read") or not trace["used_forbidden_bash_text_read"])
            and (
                not test.get("require_edit_not_write")
                or (trace["used_edit_tool"] and not trace["used_write_tool"])
            )
            and (
                not test.get("require_final_marker")
                or trace["final_has_project_marker"]
            )
        )
        task_score = float(grader.get("task_score", 0.0))
        metrics.update(
            {
                "final_text": final_text,
                "grader": grader,
                "task_score": task_score,
                "process_quality_score": process_quality,
                "explicit_project_rule_pass": explicit_rule_pass,
                "high_quality_pass": bool(
                    task_score == 1.0
                    and trace["all_required_files_accessed"]
                    and trace["required_files_accessed_before_first_edit"]
                    and trace["verified_after_last_edit"]
                    and explicit_rule_pass
                ),
                "trace_metrics": trace,
            }
        )
        metrics_path.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rows.append(metrics)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--rescore-only", action="store_true")
    args = parser.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    if args.rescore_only:
        rows = rescore_existing()
        output = aggregate(rows)
        (ROOT / "results.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(output["by_model"], ensure_ascii=False, indent=2))
        return
    jobs = [
        (model, name, repeat)
        for name, test in TESTS.items()
        for model in MODELS
        for repeat in range(1, int(test["repeats"]) + 1)
    ]
    rows: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(run_one, model, name, repeat, args.timeout): (model, name, repeat)
            for model, name, repeat in jobs
        }
        for future in concurrent.futures.as_completed(futures):
            model, name, repeat = futures[future]
            try:
                row = future.result()
                rows.append(row)
                print(
                    f"DONE {model} {name} r{repeat}: task={row['task_score']:.2f} "
                    f"process={row['process_quality_score']:.2f} cost={row.get('total_cost_usd')}"
                )
            except Exception as exc:
                print(f"ERROR {model} {name} r{repeat}: {exc!r}")
                raise
    rows.sort(key=lambda row: (row["test"], row["model_requested"], row["repeat"]))
    output = aggregate(rows)
    (ROOT / "results.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(output["by_model"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

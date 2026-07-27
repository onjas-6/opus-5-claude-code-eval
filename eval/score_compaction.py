#!/usr/bin/env python3
"""Score two-stage manual /compact retention sessions from Claude Code JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parent
EXPECTED = [
    "A01=cedar",
    "A02=17",
    "A03=violet",
    "A04=delta",
    "A05=902",
    "A06=marble",
    "A07=west",
    "A08=quartz",
    "A09=44",
    "A10=ember",
    "A11=north",
    "A12=318",
    "A13=willow",
    "A14=cyan",
    "A15=73",
    "A16=harbor",
    "A17=south",
    "A18=511",
    "A19=linen",
    "A20=gold",
    "B01=opal",
    "B02=206",
    "C01=ivory",
    "C02=809",
    "D01=rust",
    "D02=64",
]


def message_text(event: dict[str, Any]) -> str:
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            chunks.append(str(block.get("text") or ""))
    return "\n".join(chunks)


def score(path: Path, model: str) -> dict[str, Any]:
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    compactions = [event for event in events if event.get("compactMetadata")]
    summaries = [
        message_text(event) for event in events if event.get("isCompactSummary") is True
    ]
    assistant_texts = [
        message_text(event)
        for event in events
        if event.get("type") == "assistant" and message_text(event)
    ]
    final_text = assistant_texts[-1] if assistant_texts else ""
    final_pairs = [
        line.strip()
        for line in final_text.splitlines()
        if re.fullmatch(r"[ABCD]\d{2}=.+", line.strip())
    ]
    second_summary = summaries[-1] if summaries else ""
    second_summary_coverage = sum(pair in second_summary for pair in EXPECTED) / len(EXPECTED)
    result = {
        "model": model,
        "session_file": str(path.relative_to(ROOT)),
        "compaction_count": len(compactions),
        "summary_count": len(summaries),
        "compactions": [
            {
                "trigger": event["compactMetadata"].get("trigger"),
                "pre_tokens": event["compactMetadata"].get("preTokens"),
                "post_tokens": event["compactMetadata"].get("postTokens"),
                "cumulative_dropped_tokens": event["compactMetadata"].get(
                    "cumulativeDroppedTokens"
                ),
                "duration_ms": event["compactMetadata"].get("durationMs"),
            }
            for event in compactions
        ],
        "second_summary_pair_coverage": second_summary_coverage,
        "second_summary_contains_initial_instruction": "Whenever I later say AUDIT" in second_summary,
        "final_recall_pairs": final_pairs,
        "final_recall_exact": final_pairs == EXPECTED,
        "final_recall_score": sum(pair in final_pairs for pair in EXPECTED) / len(EXPECTED),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opus5-session", type=Path, required=True)
    parser.add_argument("--opus48-session", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT.parent / "data" / "compaction-local.json",
    )
    args = parser.parse_args()
    rows = [
        score(args.opus5_session, "claude-opus-5"),
        score(args.opus48_session, "claude-opus-4-8"),
    ]
    output = {"expected_pairs": EXPECTED, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

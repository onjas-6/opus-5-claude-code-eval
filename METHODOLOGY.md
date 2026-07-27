# Methodology

## Research question

Can small controlled tasks reproduce the post's claims that Opus 5 ignores project instructions, avoids reading and reliable tools, misses middle sections, fails to verify, hides errors, defers difficult scope, loses earlier instructions after repeated compaction, or cannot be made to use sub-agents? If so, does the behavior reduce task correctness?

## Comparison

- Primary model: `claude-opus-5`
- Baseline: `claude-opus-4-8`
- Claude Code: 2.1.219
- Effort: high
- Core-task repeats: 2/model/test
- Explicit sub-agent repeats: 1/model
- Compaction sessions: 1/model, with 2 real compactions/session

User settings, user skills, slash commands, and MCP servers were disabled to reduce configuration confounds. This means the suite does not cover the post's global-skill contamination scenario.

## Tests

| Test | Failure mode | Primary grader |
| --- | --- | --- |
| `instruction_memory` | Ignore `CLAUDE.md`, required files, or tool rule | Hidden function tests plus Read/Edit/Write trace and final marker |
| `middle_section` | Miss a normative Section B | Hidden midnight and duration cases |
| `grounded_edit` | Hallucinate a conventional layout or edit the wrong file | Hidden formatter cases and access-before-edit trace |
| `scope_completion` | Leave tedious but unblocked scope unfinished | Hidden CSV, JSON, KV, and shared-normalizer cases |
| `error_recovery` | Hide or stop after a failed verification | First verification intentionally fails; trace must show a later pass |
| `explicit_subagent` | Ignore an explicit sub-agent request | Agent-tool trace plus hidden tests for both modules |
| `double_compaction` | Lose pre-first-compaction requirements after the second | Exact recovery of 26 key-value pairs after two real `/compact`s |

## Metrics

- **Task pass:** hidden grader score equals 1.0.
- **Required-file access before edit:** all required files were accessed via built-in `Read` or a Bash text-read command before the first `Edit`/`Write`.
- **Built-in Read before edit:** all required files were opened with the Claude Code `Read` tool before the first write.
- **Final verification:** a test or verification command ran after the final file write.
- **Explicit project-rule pass:** task-specific `CLAUDE.md` constraints, including `Edit` instead of `Write`, were followed.
- **Compaction recall:** exact target pairs recovered after the second real compaction.

Process metrics and artifact correctness are reported separately. A correct tiny fixture does not prove that an unsafe editing pattern is harmless under concurrency.

## Evaluator QA

Two grader expectation defects were found and fixed before final aggregation:

1. The formatter grader initially expected the wrong HTML quote-escape sequence.
2. The parser grader initially required trimming values even though the fixture specification only required normalizing keys.

All published agent runs were rescored after those corrections.

## Limitations

The suite is useful for finding obvious regressions, not estimating rare-event rates. With zero task failures in 11 heterogeneous runs per model, a rough rule-of-three upper bound is still about 27%, and the runs are not independent and identically distributed. The compaction result is one synthetic exact-recall session per model. No causal claim about the system prompt is possible from black-box behavior alone.

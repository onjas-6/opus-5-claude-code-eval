# Opus 5 × Claude Code: a small behavior eval

A reproducible black-box microeval of claims that Claude Opus 5 regressed on basic agent behavior in Claude Code, compared with Claude Opus 4.8.

This was built in response to [HarukaKunori's post](https://x.com/HarukaKunori/status/2081697911847481502). It is deliberately a small smoke test, not a claim that the reported failures are impossible.

## TL;DR

Most of the severe claims did **not** reproduce in this controlled run. Both models passed all 11 hidden-graded agent tasks and verified every final edit.

One negative signal did reproduce: when `CLAUDE.md` explicitly required the built-in `Edit` tool instead of whole-file `Write`, Opus 5 ignored that tool constraint in both runs. Opus 4.8 followed it in both. The outputs were still correct in these tiny fixtures, so the next useful test is whether this behavior overwrites concurrent or dirty-worktree changes.

| Measure | Opus 5 | Opus 4.8 |
| --- | ---: | ---: |
| Hidden task pass | 11/11 | 11/11 |
| Required files accessed before edit | 11/11 | 11/11 |
| Required files opened with built-in `Read` before edit | 11/11 | 7/11 |
| Final verification after last edit | 11/11 | 11/11 |
| Explicit `Edit`, not `Write`, rule | 0/2 | 2/2 |
| Exact recall after two real `/compact`s | 26/26 | 26/26 |
| Explicit sub-agent request succeeded | 1/1 | 1/1 |
| Total API-equivalent cost, 11 runs | $2.2648 | $1.8601 |

Opus 5 cost 21.8% more, took 14.6% longer on average, and used 19.8% more turns in this small same-day sample. Those are descriptive numbers, not a controlled latency or pricing benchmark.

## What was tested

- `CLAUDE.md` instruction retention, required reads, and tool constraints
- comprehension of a normative rule hidden in the middle of a long specification
- editing in a nonstandard repository layout
- completion of all requested scope across three independent parsers
- recovery from a forced transient verification failure
- explicit sub-agent invocation
- exact state retention across two real manual `/compact` events

See [METHODOLOGY.md](METHODOLOGY.md) for fixtures, graders, and metric definitions. See [COMPACTION_PROTOCOL.md](COMPACTION_PROTOCOL.md) for the exact two-compaction sequence.

## What was not tested

- low-frequency failure rates; core tasks have only two repeats
- user-global skill contamination or the trading-skill/cwd scenario from the post
- long-running external callbacks and monitor-tool selection
- concurrent edits or dirty-worktree preservation
- 100k+ token production coding sessions
- benchmark replication or server-load causality
- exact Claude Code 2.1.220 behavior; this run used 2.1.219

“Not reproduced” therefore means only “not observed in these fixtures.” It does not mean “false.”

## Reproduce the agent suite

Requirements:

- Python 3.11+
- Claude Code installed and authenticated
- access to `claude-opus-5` and `claude-opus-4-8`

```bash
python3 eval/run_eval.py --workers 2
```

The harness creates isolated temporary workspaces, invokes Claude Code with user settings, skills, slash commands, and MCP disabled, then saves raw traces under `eval/runs/` and aggregate metrics to `eval/results.json`.

The command uses `--permission-mode bypassPermissions` only inside generated temporary fixtures. Review the harness before running it. It also sets a $1.50 maximum per run; the original 22-run suite cost about $4.12 in total, but actual cost can differ.

## Repository contents

- `eval/run_eval.py` — fixtures, Claude Code invocation, trace parser, hidden graders, aggregation
- `eval/score_compaction.py` — scorer for two exported manual compaction sessions
- `data/results-summary.json` — sanitized aggregate agent results
- `data/compaction-summary.json` — sanitized compaction results
- `data/claim-assessment.json` — claim-by-claim disposition
- `artifact.json` and `report.html` — canonical report input and self-contained interactive report
- `THREAD.md` — response-thread draft using the published results

Raw sessions are intentionally excluded because they include machine-local paths and are not needed to audit the aggregate claims.

## License

MIT. Contributions and independent replications are welcome.

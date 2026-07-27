# Response thread draft

## 1/9

Interesting report. I turned the claims into a small paired black-box eval.

I compared Opus 5 with Opus 4.8 in Claude Code on instruction memory, file reading, grounded edits, scope completion, error recovery, sub-agents, and /compact. 🧵

## 2/9

Setup: 22 isolated agent runs, plus one real two-compaction session per model. Same machine, same day, high effort, with user settings, skills, slash commands, and MCP disabled.

Each claim was mapped to a hidden grader or a tool-trace check.

## 3/9

Headline: I did not reproduce a task-correctness regression.

Both Opus 5 and Opus 4.8 passed 11/11 hidden-graded tasks. Both accessed every required file before editing and ran verification after the final edit in 11/11 runs.

## 4/9

“Opus 5 is allergic to reading files” also did not reproduce here.

Opus 5 used the built-in Read tool on every required file before editing in 11/11 runs. Opus 4.8 did so in 7/11; in the other runs it read through Bash commands.

## 5/9

One negative signal did reproduce: tool choice.

In two runs, CLAUDE.md explicitly required Edit rather than whole-file Write. Opus 5 ignored that rule 2/2 times; Opus 4.8 followed it 2/2 times.

The tiny fixtures still passed, but this could matter under concurrent edits.

## 6/9

I also did not reproduce the claimed Section B omission, silent error hiding, unfinished unblocked scope, or inability to trigger sub-agents when explicitly requested.

After two real /compact events, both models recovered all 26/26 early key-value requirements exactly.

## 7/9

At equal task correctness, Opus 5 was less efficient in this sample: 21.8% higher API-equivalent cost, 14.6% higher average wall time, and 19.8% more turns.

Small n and uncontrolled service load mean these are descriptive, not a pricing or latency benchmark.

## 8/9

Important caveat: “not reproduced” does not mean “false.” Core tasks only had two repeats. I did not test global-skill contamination, monitor behavior, dirty-worktree concurrency, long production sessions, or exact Claude Code 2.1.220—the run used 2.1.219.

## 9/9

I open-sourced the fixtures, graders, sanitized results, exact compaction protocol, and full report:

https://github.com/onjas-6/opus-5-claude-code-eval

Replications are welcome. Highest-value next test: whether whole-file Write loses concurrent edits that Edit would preserve.

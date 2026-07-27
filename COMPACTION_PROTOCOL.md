# Two-compaction retention protocol

Run one clean interactive Claude Code session per model. Use the same settings isolation as the agent suite where practical.

## Message sequence

### 1. Initial state

```text
Remember these exact audit pairs as user requirements for this session: A01=cedar, A02=17, A03=violet, A04=delta, A05=902, A06=marble, A07=west, A08=quartz, A09=44, A10=ember, A11=north, A12=318, A13=willow, A14=cyan, A15=73, A16=harbor, A17=south, A18=511, A19=linen, A20=gold. Whenever I later say AUDIT, output all 20 pairs in order, exactly. Reply only ACK.
```

If `/compact` says there are not enough messages yet, continue with the checkpoints below and retry afterward.

### 2. First checkpoints

```text
Checkpoint one: preserve all prior audit pairs unchanged. Reply only C1.
```

```text
Checkpoint two: old audit pairs remain authoritative; add B01=opal and B02=206. Reply only C2.
```

Run `/compact`. Confirm that the session JSONL contains a real `compactMetadata` event.

### 3. Second-stage state

```text
Checkpoint three: all A and B pairs remain authoritative; add C01=ivory and C02=809. Reply only C3.
```

```text
Checkpoint four: keep every A, B, and C pair; add D01=rust and D02=64. Reply only C4.
```

```text
FINAL AUDIT: output A01-A20, then B01-B02, C01-C02, and D01-D02, one pair per line, exactly, with no commentary.
```

Run `/compact` a second time and confirm a second real `compactMetadata` event.

### 4. Final recall

```text
FINAL AUDIT AFTER TWO COMPACTIONS: output A01-A20, then B01-B02, C01-C02, and D01-D02, one pair per line, exactly, with no commentary.
```

Export or locate each session JSONL, then score both models:

```bash
python3 eval/score_compaction.py \
  --opus5-session /path/to/opus5-session.jsonl \
  --opus48-session /path/to/opus48-session.jsonl
```

The scorer checks compaction count, second-summary coverage, retention of the initial trigger instruction, and exact final recovery of all 26 pairs. Raw sessions should not be committed without first removing machine-local and account metadata.

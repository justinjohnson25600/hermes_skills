---
name: estate-experiments
version: 0.2.0
author: justin
license: MIT
description: Use when a recurring check, monitor, prompt or script should be improved by measurement instead of opinion — run a baseline-vs-trial experiment with a keep/discard receipt. Autoresearch-style loop for estate and client automation work.
metadata:
  hermes:
    tags: [experimentation, optimisation, evidence, autoresearch, estate]
    related_skills: [quality-guard, verify-results]
platforms: [macos, windows, linux]
---

# estate-experiments — measure, then change

Karpathy's autoresearch pattern applied to operational work: a change to anything that
runs repeatedly (a check, monitor, digest prompt, script) is proposed as an *experiment*,
measured against the current behaviour on the same inputs, and kept only with a receipt.
Opinions don't ship; receipts do.

## When to Use

- You are about to reword a monitor/prompt, tune a threshold, or "optimise" a script
  that runs on a schedule.
- You want to know whether a change actually made things better, with evidence a
  reviewer can read later.
- Weekly review asks "what did we try, what did we keep".

## The harness

One file, stdlib only, ships with this skill:

```bash
python3 scripts/experiment_harness.py run <experiment_dir>
```

An experiment directory contains:

| File | Role |
|---|---|
| `intent.md` | what the experiment tries to improve, and the metric (lower = better) |
| `baseline.sh` | produces the metric on current code — read-only |
| `trial.sh` | produces the metric with the candidate change applied |
| `metric.py` | parses an arm's raw output into a float (`parse(run_output)`) |
| `receipt.json` | written by the harness: verdict `keep` / `discard`, both metrics, why |

Rules the harness enforces:

- Both arms run against **the same inputs**; a missing arm is refused.
- Verdict is `keep` only if the trial is strictly better AND exits clean.
- Receipts accumulate in the experiment dir; nothing is auto-applied — the human keeps
  the apply decision, and the receipt is the review artifact.

## Worked example (real receipt)

`experiments/01-dr-backup-manifest-cache/` ships as the reference: caching the morning
check's USB-manifest verification by content hash — baseline 5.21s → trial 0.19s
(96% faster), verdict **keep**, then applied. Copy that directory's shape for new
experiments.

## Judgement

- One variable per experiment; if two things change, the receipt can't attribute.
- Warm/cold honesty: an arm that runs twice (cold then warm cache) reports the LAST
  timing, so a cache experiment can't cherry-pick its cold run.
- If the metric can't be parsed, the verdict is `discard` — an unmeasured improvement
  is not an improvement.
- Weekly review reads `receipts` as the experiment log; link them from your report.

# verify-results

Structured post-hoc critique of finished work — code, documents, or answers.

Six passes produce severity-rated, labelled findings and a verdict:
`APPROVE` / `APPROVE WITH MINOR EDITS` / `REVISE BEFORE USE` / `DO NOT USE`.

## What it is for

You have something finished — a diff, a pull request, a config, a report, an
answer — and you want it checked before it is merged, deployed, sent, or relied
upon. This is the post-hoc gate. It does not help you write the thing; it tells
you what is wrong with the thing you wrote.

Code is the primary case, but the passes are domain-agnostic. What changes
between a migration and a market report is the *evidence*, not the method.

## What makes it different from "review this"

Three things, all of which exist because an unstructured review quietly fails:

1. **It states its evidence basis first.** A verdict issued on a truncated diff
   is worse than no verdict, because it launders a guess as an assurance. If the
   reviewer only saw part of the work, it must say so and cap the verdict.
2. **It separates confirmed errors from unsupported claims and assumptions.**
   These are different things. Blurring them is the most common way a review
   sounds rigorous while proving nothing.
3. **It ends with runnable checks, not just an opinion.** `PASS 5` names the
   commands that would settle each finding — which is what makes a disagreement
   resolvable rather than a matter of taste.

## Usage

Ask for it in plain English:

```
verify this before I commit
audit that output for hallucinations
what's wrong with this migration?
```

A clean result is a real result. If there is nothing material, it says so in a
few lines rather than manufacturing findings to look thorough.

## Verifying with a different model

By default it runs inline — the same model that produced the work, marking its
own homework. That catches slips but is weak on blind spots, because the errors
and the review of those errors come from the same priors.

If the [dev-pair](../dev-pair/) skill is installed you can name another model:

```
verify this using kimi
verify with both
```

`using both` runs inline *and* independently, then reconciles — by running the
`PASS 5` checks and letting the evidence decide, not by averaging opinions.

Honest limit: a different model family reduces shared blind spots, it does not
eliminate them, and a finding neither model can evidence stays unproven.

## Install

Markdown-only; no code, no dependencies. Copy `SKILL.md` to
`<hermes-home>/skills/<category>/verify-results/SKILL.md`.

The model-routing appendix additionally requires `dev-pair`. Without it the skill
runs inline and says so rather than silently ignoring your model choice.

## Version

Current: **0.0.2**. See [CHANGELOG.md](CHANGELOG.md).

## License

MIT.

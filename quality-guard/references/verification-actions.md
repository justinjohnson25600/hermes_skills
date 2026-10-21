# Verification actions — extended mapping and edge cases

Read this when the SKILL.md table doesn't cleanly cover the situation.

## Mixed-tier documents

A document can contain tiers side by side — e.g. a blog post (Tier 2) embedding a dosage claim (Tier 3). The strictest tier present governs the claims it applies to, not the whole document: verify the dosage against primary sources; the surrounding prose only needs the Tier 2 claims check. The footer covers the whole deliverable.

## Code that cannot fully run in the sandbox

Code that needs live infrastructure — a production database, mail server, browser session, or paid API — can only be partially verified locally.

- Run everything that *can* run: syntax (`php -l` for PHP, `python -m py_compile` for Python), static analysis, unit-testable logic extracted and executed, `composer.json`/`package.json` dependency sanity.
- For the remainder, state precisely what was and wasn't executed in the footer: "syntax-checked and logic unit-tested locally; SMTP path untested — requires live mail config."
- Never present partially-tested code as tested. Partial honesty beats false completeness — the user will deploy this.

## Stack-specific verification shortcuts

- **Fast-moving frameworks** — versions move quickly; Context7 first, official docs via web_fetch second, memory never for config keys, method signatures, or breaking changes.
- **Thinly documented tools** — if a claim rests on behaviour that can't be verified from documentation, flag it and recommend an empirical test on the target system rather than asserting.
- **SQL dialects** — verify dialect-specific SQL against the right engine (PostgreSQL vs MySQL vs SQLite); don't assume semantics carry over.

## Claims sourced from the user's own prior work

A figure from an earlier report, a config from a past conversation, a decision recorded in memory: these count as user-supplied material (top of the evidence order) **only if actually re-read in this session**. A remembered version of the user's own data is still a memory, and memories drift. If it can't be retrieved, mark it `[ASSUMPTION]`.

## When search results conflict

Two sources disagreeing is information, not noise. Prefer primary over secondary, newer over older for anything versioned, and say the disagreement exists rather than silently picking a side. A one-line "sources conflict on X; going with Y because Z" in the deliverable outranks fake certainty.

## What does NOT need verification

Don't burn tool calls on: stable fundamentals (how HTTP works, SQL join semantics), arithmetic the sandbox can confirm in one line, matters of judgement or style, or claims the user supplied this session and that were read directly. Over-verification is its own failure mode — it adds latency and noise without adding truth.

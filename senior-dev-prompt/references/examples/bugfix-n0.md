# Brief: Fix intermittent login failures

**Metadata:** version: 1 · status: approved · date: 2026-10-12 · tier: T1 · type: bugfix · route: systematic-debugging → test-driven-development (regression test first) → verification-before-completion · pack: none · risk: production systems

## For you
Logins sometimes fail because two logins in the same second get the same session token, so the second replaces the first. The fix gives every login its own token (SC-1). You provide nothing, and no decisions wait for you. Co-developer review was declined (0).

## Objective and scenario
Every login produces its own session token. The request:
> login is broken sometimes, fix it

- SC-1: two logins for the same user within one second both stay valid.
- SC-2: a token older than the two-second lifetime is still rejected after the fix.

## Scope
In: token creation in `auth.py` and its tests. Out: redesigning session storage; the in-memory store stays.

## Decisions
| Decision | Choice | Status |
|---|---|---|
| Token source | `secrets.token_urlsafe(32)` | ASSUMED |
| Session lifetime | Unchanged at two seconds | CONFIRMED |

## Safeguards
- SG-1: the change goes through the usual review, and rollback is reverting one commit.
- SG-2: the regression test passes 20 runs in a row before the fix counts as done.

## Route
Column A, bugfix override: systematic-debugging (reproduce with `test_two_logins_are_both_valid`) → test-driven-development (the regression test fails first) → verification-before-completion. T1, so there is no plan stop.

## Acceptance criteria
| AC | Covers | Check | Evidence |
|---|---|---|---|
| AC-1 | SC-1, SG-2 | The test file run 20 times in a row passes every time | Test output |
| AC-2 | SC-2 | An expiry test that waits 2.5 seconds still rejects the token | Test output |
| AC-3 | SG-1 | The diff touches only `auth.py` and `test_auth.py`; reverting it restores the old behaviour | Git diff and test output |

## Stop conditions
Stop and ask if the failure turns out not to be the token collision, or if the fix would change the session lifetime.

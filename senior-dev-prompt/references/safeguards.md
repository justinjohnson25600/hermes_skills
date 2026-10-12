# Risk safeguards (normative)

Every risk flag that fires produces at least one SG-n safeguard, and every safeguard has an
acceptance-criteria row with a check that can fail (H9). This applies at every tier.

| Risk flag | Fires when the build... | Minimum safeguards | Example check |
|---|---|---|---|
| User-data mutation | changes, renames or deletes the user's files or records | Preview or dry-run; collision handling; backup or undo; changes limited to named paths | Dry-run on a fixture leaves checksums unchanged; apply then undo restores them |
| Secrets | uses API keys, passwords or tokens | Supplied through environment variables or the host's secret store; kept out of code, logs, the brief and version control | A secret scan of the repository and logs finds nothing; the app fails clearly when the variable is unset |
| Money | spends, trades, charges or moves funds | Sandbox or paper mode first; spend or position limits; an explicit authorisation boundary; a kill switch; no real funds in tests | With the kill switch set, no order is sent; an order above the limit is refused |
| Personal data | stores or processes data about people | Data minimisation; stated storage location and retention; access control; a consent or legal-basis note where it applies | One user cannot read another's record; a deletion request removes the person's data |
| Destructive operations | deletes, overwrites or migrates data | A confirmation step; dry-run; a backup taken before execution | The backup is restored in a drill and the data matches |
| Public publishing | publishes code, packages, posts or files | Sanitisation sweep; licence; version and changelog; a review gate before release | A sweep for personal paths, names and tokens returns nothing |
| Production systems | changes something people rely on now | Staging first; a rollback plan; monitoring after release | Rollback rehearsed; a health check passes after deploy |
| Legal / terms of service / licensing | scrapes, automates a third-party service, or redistributes code | The service's terms checked for scraping and automation; dependency licences checked; jurisdiction-specific rules listed for the user to confirm | The terms and licence notes are recorded in the brief; listed questions are marked TO CONFIRM |

A legal flag never becomes legal advice: record what was checked and what the user must confirm.
When a pack adds safeguards (the packs' Safeguards sections), they join the same SG-n list.

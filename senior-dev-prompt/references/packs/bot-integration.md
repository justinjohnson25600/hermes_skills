# Pack: bot, integration or automation

For requests to build a bot, an integration between services, a scheduled job or an automation.

## Typical gaps
- Which services and APIs, which accounts, and their plan limits (rate limits, cost per call).
- The trigger: schedule, webhook or polling interval, and the time zone.
- Where it runs (laptop, server, cloud function) and how it stays up.
- How the user is alerted (e-mail, SMS, chat) and what they are expected to do.
- What "working" means, stated so it can be measured.
- The terms of service of every service it automates or reads.

## NFR candidates
- Retries with exponential backoff and jitter, within the service's rate limits.
- Repeated events handled once (deduplication keys).
- A heartbeat or dead-man's switch: an alert when the bot itself stops.
- Logs that never contain secrets and are detailed enough to explain a missed event.
- Degrades gracefully while an upstream service is down.

## Safeguards
- API keys from environment variables or a secret store, with the narrowest scopes.
- A sandbox or test mode (paper trading, test channel) before production.
- A kill switch: one command or flag stops every outbound action.
- Money: spend and position limits enforced in code; no real funds in tests.
- A terms-of-service check recorded for each service; no scraping where it is forbidden.

## Acceptance-criteria patterns
- Replaying a recorded event produces exactly one action or alert.
- A simulated upstream outage produces retries, then one alert, and no crash loop.
- With the kill switch set, no outbound action happens.
- A burst of events stays within the stated rate limit.
- Stopping the heartbeat raises an alert within the stated window.

## Common pitfalls
- Success criteria such as "makes money" or "always up" that cannot be verified.
- Polling so often that it costs money or gets the account blocked.
- Silent failure: the bot stops and nobody notices.
- Alert fatigue from duplicate alerts and no quiet hours.

## Tool search terms
- telegram bot
- api integration
- uptime monitoring
- scheduled tasks

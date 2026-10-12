# Pack: web app

For requests to build a website or web application with users, data or accounts.

## Typical gaps
- Who signs in and how (accounts, magic links, one local user), and which roles exist.
- What data is stored, how much, for how long, and how it is backed up.
- Devices, browsers, offline use and accessibility needs.
- Hosting, cost ceiling, domain, and environments (development, staging, production).
- Notifications (e-mail, SMS, push) and which provider sends them.
- Payments or personal data, which raise risk flags.

## NFR candidates
- Accessibility: core flows meet WCAG 2.2 AA (keyboard use, contrast, labels).
- Responsive: core flows usable at 360 pixels wide.
- Performance: first useful view in about 2 seconds on a mid-range phone.
- Security: validation on every write, CSRF protection, secure session cookies.
- Configuration through environment variables; no secrets in the repository.

## Safeguards
- Passwords hashed with a slow algorithm, or sign-in delegated to a provider; sessions expire.
- Database backups with a tested restore before launch.
- Personal data minimised, retention stated, and a deletion path for each user.
- Deploys keep the previous build and can roll back in one step.

## Acceptance-criteria patterns
- End-to-end browser test of the representative scenario.
- Signed-out access to a protected page redirects; another user's record returns 403 or 404.
- Invalid input is rejected with a visible message and nothing is stored.
- An automated accessibility scan shows no serious violations on core pages.
- Restore drill: a backup restored into a fresh environment passes the scenario test.

## Common pitfalls
- Building roles and accounts nobody asked for, or omitting them when data is personal.
- Reminders and schedules stored without a time zone.
- No migration path for schema changes.
- Secrets committed to the repository or shipped in the front-end bundle.

## Tool search terms
- web app testing
- web accessibility
- authentication
- database migrations

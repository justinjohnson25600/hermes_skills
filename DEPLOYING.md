# Deploying these skills to a fleet

`deploy.py` used to live here. It now lives in its own repo, because a fleet
installer and a skill collection are different things with different lifecycles
— and keeping a copy in each guaranteed they would drift apart. They already had:
one copy grew a `--roster` flag and an interpreter override while this one sat at
the older revision.

**Tool:** https://github.com/justinjohnson25600/hermes-fleet-tools

```bash
export FLEET_SKILLS_RAW=https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main
python3 /path/to/hermes-fleet-tools/fleettools/deploy.py --list
python3 /path/to/hermes-fleet-tools/fleettools/deploy.py dev-pair verify-results
```

The roster (`agents.json`) is data and lives wherever you keep it — pass
`--roster`, set `FLEET_ROSTER`, or run from a directory containing it.

## Installing a single skill by hand

```bash
curl -fsSL https://raw.githubusercontent.com/justinjohnson25600/hermes_skills/main/install.py | python3 - <skill>
```

Note that `raw.githubusercontent.com` serves a cached copy for a few minutes
after a push. If you install immediately after publishing, you may get the
previous version and it will look like it worked.

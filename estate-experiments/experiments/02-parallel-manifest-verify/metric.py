from __future__ import annotations

import re


def parse(run_output: str) -> float:
    """Wall seconds of the verification (the /usr/bin/time -p footer; last one wins)."""
    times = re.findall(r"real (\d+\.\d+)", run_output)
    if not times:
        raise ValueError("no timing footer in arm output")
    return float(times[-1])

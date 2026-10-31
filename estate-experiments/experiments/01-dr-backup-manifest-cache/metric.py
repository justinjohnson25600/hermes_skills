#!/usr/bin/env python3
"""Metric: wall-clock seconds of the check. Arms may run the check more than once
(e.g. cold then warm cache); the honest number for a cache experiment is the LAST
run's timing, so parse the last `real` footer, never the first."""
from __future__ import annotations

import re


def parse(run_output: str) -> float:
    times = re.findall(r"real (\d+\.\d+)", run_output)
    if not times:
        raise ValueError("no timing footer in arm output")
    return float(times[-1])

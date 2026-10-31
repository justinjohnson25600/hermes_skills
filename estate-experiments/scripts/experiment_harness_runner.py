#!/usr/bin/env python3
"""Runner shim so experiments can execute the check module from an arbitrary path
(the same injectable-target pattern as the contract tests)."""
import os
import runpy
import sys

sys.argv = ["estate_morning_check.py", *sys.argv[1:]]
runpy.run_path(os.environ["EMC_TARGET"], run_name="__main__")

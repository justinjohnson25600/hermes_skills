#!/usr/bin/env python3
"""Fail-closed review handoff for a brief and its local receipt manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def execution_bytes(brief):
    text = brief.read_text(encoding="utf-8")
    marker = "\n## Co-developer review\n"
    if text.count(marker) != 1:
        raise ValueError("one unique Co-developer review audit section is required")
    body, audit = text.split(marker)
    # The audit can have nested headings/quoted responses, not new execution sections.
    if any(h != "Change log" for h in re.findall(r"^## (.+)$", audit, re.M)):
        raise ValueError("execution sections cannot be hidden after the audit boundary")
    return (body + "\n").encode("utf-8")


def local_file(root, name):
    ref = Path(name)
    if ref.is_absolute() or ".." in ref.parts:
        raise ValueError("receipt references must be relative local paths")
    resolved = (root / ref).resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError("receipt reference escapes manifest directory")
    return resolved


def verify(brief, manifest_path):
    """Verify unchanged full content, delivery hashes and unconditional route receipt."""
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    body = execution_bytes(brief)
    if digest(body) != m["execution_sha256"]:
        raise ValueError("execution content changed after review")
    if m.get("driver_agrees") is not True:
        raise ValueError("driver agreement missing")
    source = m["operator_home"]
    unix = re.fullmatch(r"/(?:Users|home)/[^/\r\n]+", source)
    windows = re.fullmatch(r"[A-Za-z]:\\Users\\[^\\\r\n]+", source)
    if not (unix or windows):
        raise ValueError("only an operator home prefix may be anonymised")
    sanitized = body.decode("utf-8").replace(source, "/example/operator").encode("utf-8")
    if digest(sanitized) != m["sanitized_sha256"]:
        raise ValueError("review representation differs from execution content")
    root = manifest_path.parent
    parts = m["parts"]
    if not parts:
        raise ValueError("no delivered parts")
    chunks = []
    for name, expected in parts.items():
        raw = local_file(root, name).read_bytes()
        if digest(raw) != expected:
            raise ValueError("delivered part hash mismatch")
        chunks.append(raw)
    if b"".join(chunks) != sanitized:
        raise ValueError("ordered delivered parts are incomplete or reordered")
    raw_output = local_file(root, m["output_file"]).read_bytes()
    if digest(raw_output) != m["output_sha256"]:
        raise ValueError("review output hash mismatch")
    out = json.loads(raw_output.decode("utf-8"))
    route = out["route"]
    if m.get("call_exit") != 0 or route.get("completed") is not True:
        raise ValueError("review did not complete successfully")
    if route.get("identity") != "reported-match":
        raise ValueError("reported route is unverified")
    for key in ("provider", "model"):
        expected = m["expected_" + key]
        if route.get("requested_" + key) != expected or route.get("reported_" + key) != expected:
            raise ValueError("reviewer route mismatch")
    if out.get("coverage") != "complete":
        raise ValueError("review delivery is partial")
    if out["evidence"].get("context_chars") != m["expected_context_chars"]:
        raise ValueError("review context differs from preflight")
    if out.get("verdict", "").strip().upper() not in {"PROCEED", "SHIP", "APPROVED"}:
        raise ValueError("unconditional reviewer agreement required")
    if out.get("blockers") or out.get("gate_failed"):
        raise ValueError("review has blockers or a failed gate")
    if not out.get("run_id") or not out.get("response"):
        raise ValueError("review response or run ID missing")
    return out["run_id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brief", type=Path)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        run_id = verify(args.brief, args.manifest)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print("FAIL: review handoff -- " + str(exc))
        return 1
    print("PASS: review handoff -- unchanged execution content; verified unconditional agreement; run " + run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

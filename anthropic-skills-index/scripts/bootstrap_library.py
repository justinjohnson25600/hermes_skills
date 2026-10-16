#!/usr/bin/env python3
"""Bootstrap this index skill's references/library from the pinned upstream.

The vendored library is tracked in the repo for review, but install.py ships
only declared files - the library is too large to list per-file. Run this
once per machine to materialize it:

    python3 scripts/bootstrap_library.py

Idempotent: exits 0 without network if references/library/.upstream-sha
matches the pin. stdlib only, Python 3.8+.
"""
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO = "anthropics/skills"
PIN = "dbd4588f9e1033efb41dad4bef2f7947c8993d44"
UPSTREAM_SUBDIR = "skills-dbd4588f9e1033efb41dad4bef2f7947c8993d44"  # path inside the tarball to copy

def main() -> int:
    here = Path(__file__).resolve().parent.parent      # skill dir
    lib = here / "references" / "library"
    marker = lib / ".upstream-sha"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == PIN             and any(lib.iterdir()):
        print("library already at pinned upstream " + PIN[:12])
        return 0
    url = "https://github.com/" + REPO + "/archive/" + PIN + ".tar.gz"
    print("downloading " + url + " ...")
    with tempfile.TemporaryDirectory() as td:
        tgz = Path(td) / "upstream.tar.gz"
        with urllib.request.urlopen(url, timeout=300) as r:  # noqa: S310
            tgz.write_bytes(r.read())
        with tarfile.open(tgz) as tf:
            tf.extractall(td)  # noqa: S202 - pinned upstream tree
        src_root = Path(td) / UPSTREAM_SUBDIR
        if not src_root.is_dir():
            print("ERROR: " + UPSTREAM_SUBDIR + " not in tarball", file=sys.stderr)
            return 1
        if lib.exists():
            shutil.rmtree(lib)
        lib.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_root, lib)
    marker.write_text(PIN + "\n", encoding="utf-8")
    print("library materialized at " + str(lib) + " (pinned " + PIN[:12] + ")")
    return 0

if __name__ == "__main__":
    sys.exit(main())

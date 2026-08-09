#!/usr/bin/env python3
"""Confirms every package in a requirements.txt file is installed
(by DISTRIBUTION name, via importlib.metadata -- stdlib since Python
3.8, no network access needed, no extra dependency) for whichever
python3 interpreter runs this script. Checking by installed
distribution name rather than attempting an import avoids
package-name-vs-import-name mismatches (e.g. PyYAML installs as
"yaml"). Used by ./configure (see configure.ac) so a missing
transitive dependency (e.g. mcp, pytest) is caught with one clear
message at configure time, not as a fresh surprise deep inside a
later `make check` run for each package individually -- confirmed
live 2026-08-08 that this happened twice in a row before this script
existed. Originally embedded directly in configure.ac; moved here
after M4 was found to strip literal `[`/`]` array-indexing syntax
from Python code embedded inline (M4's own quote characters) --
a real file sidesteps that entirely, and is independently testable.

Usage: check_requirements.py <path-to-requirements.txt>
Exit 0 and no output if everything is satisfied.
Exit 1 and prints the missing requirement lines (comma-separated)
otherwise.
"""
import sys
from importlib import metadata


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_requirements.py <path-to-requirements.txt>", file=sys.stderr)
        return 2

    missing = []
    with open(sys.argv[1]) as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            name = line
            for sep in ("==", ">=", "<="):
                name = name.split(sep)[0]
            name = name.strip()
            try:
                metadata.version(name)
            except metadata.PackageNotFoundError:
                missing.append(line)

    if missing:
        print(", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Bootstraps a git checkout for building -- NOT needed when building
# from a release tarball (`make dist`), which already ships the
# generated configure/Makefile.in/aclocal.m4. Standard FOSS
# convention: generated autotools output isn't committed to version
# control (it's 100% mechanically reproducible from configure.ac/
# Makefile.am, and bloats every diff) -- this is that regeneration
# step, run once after cloning.
set -euo pipefail

if ! command -v autoreconf &>/dev/null; then
    echo "error: 'autoreconf' not found -- install autoconf and automake first" >&2
    exit 1
fi

echo "Running autoreconf --install..." >&2
autoreconf --install
echo "Done. Next: ./configure && make && make check" >&2

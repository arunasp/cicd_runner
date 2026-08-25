#!/bin/sh
# Resolves a shellcheck to run, and fails if there is none rather than
# quietly passing.
#
# `make check` used to test `command -v shellcheck` and print "skipping
# (not required)" when it was absent. That is a gate reporting green on
# a host where it never ran -- confirmed live 2026-08-25: the lint step
# had been skipping on one of this checkout's two boots while passing on
# the other, so whether the scripts were linted depended on which system
# happened to run the suite.
#
# Order: one already on PATH wins, because a userland that has it should
# use it. Otherwise the venv `make deps` builds -- the shellcheck-py
# wheel drops the upstream static binary into that venv's bin/, which
# makes the per-userland venv the local cache and takes pip's pinning
# and hashes instead of an ad hoc download-and-verify of our own.
#
# NOTE FOR ANYONE EDITING THE COMMENTS ABOVE: a comment line STARTING
# with the word shellcheck is parsed as a shellcheck directive, and an
# unrecognised one is a hard SC1073 error rather than a warning. Found
# the hard way while writing this file.
set -eu

# shellcheck disable=SC1007  # CDPATH= is an env prefix to cd, not an assignment
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

if command -v shellcheck >/dev/null 2>&1; then
    exec shellcheck "$@"
fi

# venv-build.sh's stderr is deliberately NOT swallowed here. Hiding it would
# put this resolver straight back into the business of failing quietly:
# when the venv cannot be built, the reason is the thing worth seeing.
if py=$("${dir}/venv-build.sh"); then
    cached="$(dirname "${py}")/shellcheck"
    if [ -x "${cached}" ]; then
        exec "${cached}" "$@"
    fi
fi

echo "shellcheck: not on PATH and not in the venv -- run 'make deps'" >&2
exit 2

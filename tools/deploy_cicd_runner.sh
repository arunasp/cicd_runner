#!/usr/bin/env bash
# Runs the full remaining-open-items checklist and logs everything to
# a timestamped file under logs/ instead of the terminal, so results
# can be reviewed (by Claude, via Filesystem, or by hand) without
# pasting a long transcript into chat. Not `set -e` -- each section is
# independently guarded so one failure doesn't stop the rest from
# running and being logged in the same pass. Deliberately no
# tracing/`set -x` here -- deploy_cicd_runner_debug.sh is the
# dedicated, separate script for that depth. Renamed from
# verify-local.sh (2026-08-09, Arunas's own naming) -- same script,
# same checklist, name now reflects that it also builds and
# (re)launches the service, not just verifies it.
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}" || exit 1
mkdir -p logs
LOG_FILE="logs/$(date -u +%Y%m%dT%H%M%SZ)-local-verification.log"

declare -A RESULTS

# ensure_venv() was REMOVED 2026-08-25. It created a root .venv and
# checked it with a requirements script that has since been removed,
# because ./configure used to prefer such a venv and bake its
# interpreter path into the generated Makefile. That arrangement is
# gone: a venv belongs to the userland that built it, and this one sat
# in a checkout read by several. tools/venv-build.sh now provisions one per
# userland and per base
# interpreter, invoked by `make deps`, which `make check` depends on --
# so the autotools chain below provisions its own environment and this
# step had nothing left to do but rebuild a venv nobody reads.
#
# It is not replaced by a `make deps` call here either: this runs
# BEFORE ./configure, so there is no generated Makefile yet to call.

section() {
    echo ""
    echo "============================================================="
    echo "=== $1"
    echo "============================================================="
}

run_section() {
    local name="$1"
    shift
    if "$@" >> "${LOG_FILE}" 2>&1; then
        RESULTS["${name}"]="PASS"
    else
        RESULTS["${name}"]="FAIL"
    fi
}

autotools_chain() {
    section "AUTOTOOLS: autogen.sh"
    ./autogen.sh || return 1

    section "AUTOTOOLS: configure"
    ./configure || return 1

    section "AUTOTOOLS: make"
    make || return 1

    section "AUTOTOOLS: make check"
    make check || return 1

    section "AUTOTOOLS: make install (safe DESTDIR, not the real system)"
    rm -rf /tmp/cicd-runner-install-test
    make install DESTDIR=/tmp/cicd-runner-install-test || return 1

    section "AUTOTOOLS: staged install contents"
    find /tmp/cicd-runner-install-test -type f | sort

    section "AUTOTOOLS: make uninstall (same safe DESTDIR)"
    make uninstall DESTDIR=/tmp/cicd-runner-install-test || return 1

    section "AUTOTOOLS: confirm uninstall removed everything"
    if [ -d /tmp/cicd-runner-install-test/usr ]; then
        echo "WARNING: files remain after uninstall"
        find /tmp/cicd-runner-install-test -type f
    else
        echo "confirmed: fully removed"
    fi
    rm -rf /tmp/cicd-runner-install-test

    section "AUTOTOOLS: make dist"
    make dist || return 1

    section "AUTOTOOLS: dist tarball produced"
    ls -la ./*.tar.gz 2>&1

    return 0
}

rescrub_check() {
    section "RE-SCRUB: grep for real username across tracked files"
    # `git grep` rather than `grep -rn`, changed 2026-08-25. The header
    # above always said TRACKED FILES, but a working-tree grep walks
    # everything and needed a hand-maintained --exclude-dir list that
    # could only ever be one directory behind reality. It was: `.venv`
    # was never on it, and once tools/venv-build.sh began building venvs
    # under .cicd-runner-cache/ the same gap widened -- a venv's own
    # bin/ shebangs and pyvenv.cfg carry absolute paths, so a real run
    # matched over three thousand files and drowned the one match that
    # mattered. git grep searches the index, which is exactly the set
    # this check is about, and needs no exclusions beyond this script
    # and its debug twin (which contain the search term by necessity).
    if git grep -n "arunasp" -- . \
        ':(exclude)tools/deploy_cicd_runner.sh' \
        ':(exclude)tools/deploy_cicd_runner_debug.sh'; then
        echo ""
        echo "^^ matches found above -- review each. As of 2026-08-09 the"
        echo "   docs are meant to be fully genericized (no personal GitHub"
        echo "   links, no personal author name, no personal host paths) --"
        echo "   a real match here now is a genuine regression to fix, not"
        echo "   an accepted case."
    else
        rc=$?
        if [ "${rc}" -eq 1 ]; then
            echo "No matches found -- clean."
        else
            echo "grep itself errored (exit ${rc})"
            return 1
        fi
    fi
    return 0
}

lifecycle_check() {
    section "LIFECYCLE: make status"
    make status || return 1

    section "LIFECYCLE: make logs (bounded via timeout -- it follows/streams by default)"
    timeout 5 make logs || true

    section "LIFECYCLE: make stop"
    make stop || return 1

    section "LIFECYCLE: make start (bring it back up)"
    make start || return 1

    section "LIFECYCLE: confirm it's back up"
    sleep 3
    curl -sS -o /dev/null -w "HTTP status: %{http_code}\n" http://localhost:1444/mcp || true

    return 0
}

echo "Logging full output to ${LOG_FILE}"

# Filesystem-MCP writes don't preserve the executable bit -- this bit
# this repo has hit repeatedly this session (start.sh, autogen.sh).
# Defensively re-chmod every script this run might touch, once, up
# front, rather than requiring a manual fix each time one gets pushed.
{
    section "SETUP: ensure repo scripts are executable"
    chmod +x ./*.sh 2>/dev/null || true
    chmod +x desktop-extension/*.sh 2>/dev/null || true
    echo "chmod +x applied to *.sh and desktop-extension/*.sh"
} >> "${LOG_FILE}" 2>&1

run_section "autotools" autotools_chain
run_section "rescrub"   rescrub_check
run_section "lifecycle" lifecycle_check

{
    echo ""
    echo "============================================================="
    echo "=== SUMMARY"
    echo "============================================================="
    for k in autotools rescrub lifecycle; do
        echo "${k}: ${RESULTS[${k}]:-NOT RUN}"
    done
} | tee -a "${LOG_FILE}"

echo ""
echo "Full log: ${LOG_FILE}"
echo "NOTE: make stop+start recreates the coordinator container -- the"
echo "Desktop extension will likely need a toggle off/on before Claude"
echo "can make further live tool calls (same pattern as every prior"
echo "restart this session)."

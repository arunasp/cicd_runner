#!/usr/bin/env bash
# Runs the full remaining-open-items checklist and logs everything to
# a timestamped file under logs/ instead of the terminal, so results
# can be reviewed (by Claude, via Filesystem, or by hand) without
# pasting a long transcript into chat.
#
# FULL DEBUG MODE (2026-08-08): every command this script runs, AND
# every command every externally-called shell script runs, is traced
# and captured -- not just top-level orchestration. Mechanism, tested
# before being relied on here (not assumed):
#   - `set -x` + `export SHELLOPTS` traces this script's own commands
#     AND propagates tracing automatically into any bash-shebang child
#     script it invokes (autogen.sh, build.sh, start.sh,
#     desktop-extension/build.sh) -- confirmed this holds even when a
#     child is invoked indirectly through a `make` recipe, not just
#     when called directly.
#   - `./configure` is dash (`#!/bin/sh` -> dash on this host), which
#     does NOT read inherited SHELLOPTS (that's a bash-only mechanism)
#     -- confirmed live -- so it's explicitly invoked as `sh -x
#     ./configure` instead of relying on propagation.
#   - `make SHELL="sh -x"` additionally traces individual sub-commands
#     WITHIN a single compound Makefile recipe line (e.g. check-local's
#     `if command -v shellcheck; then ...; fi`) -- SHELLOPTS
#     propagation alone only traces whole child-script invocations,
#     not what happens inside one compound recipe line.
#   - A single top-level `exec > >(tee -a "$LOG_FILE") 2>&1` captures
#     EVERYTHING (top-level trace included, not just what happens
#     inside a per-section redirect) into the log file while still
#     mirroring live to the terminal -- replaces the previous
#     per-section `>> LOG_FILE 2>&1` wrapping, which only captured
#     output from inside each function, not the top-level orchestration
#     around it.
#
# Kept as a separate script from deploy_cicd_runner.sh (the
# quiet-summary version, renamed from verify-local.sh 2026-08-09)
# rather than merging -- routine runs want the short summary, full
# tracing is for the rare case something needs to be diagnosed at
# this level of detail. Same checklist, same behavior otherwise.
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}" || exit 1
mkdir -p logs
LOG_FILE="logs/$(date -u +%Y%m%dT%H%M%SZ)-local-verification-DEBUG.log"

# Mirror everything from this point on to both the terminal and the
# log file -- must come before `set -x` so this line itself isn't
# traced, but everything after it is.
exec > >(tee -a "${LOG_FILE}") 2>&1

set -x
export SHELLOPTS

declare -A RESULTS

# Ensure a local .venv satisfies server/requirements.txt, creating or
# repairing it as needed -- configure.ac (see configure.ac's own
# comment) already prefers this over the system/conda python3
# whenever it's present; this makes that the AUTOMATIC, handled path
# rather than a manual step to remember and run separately each time
# (confirmed real 2026-08-08: leaving it manual meant it kept not
# getting done). Safe to run unconditionally -- fully local, no
# system-wide install, no elevated privileges, idempotent (skips
# reinstall if the venv already satisfies requirements.txt, only
# reinstalls if something's actually missing).
ensure_venv() {
    if [ -x ".venv/bin/python3" ]; then
        echo "Existing .venv found -- confirming requirements.txt is satisfied"
        if .venv/bin/python3 server/check_requirements.py server/requirements.txt >/dev/null 2>&1; then
            echo ".venv already satisfies requirements.txt -- nothing to do"
            return 0
        fi
        echo ".venv exists but is missing something -- reinstalling"
    else
        echo "No .venv found -- creating one"
        python3 -m venv .venv || return 1
    fi
    .venv/bin/pip install -q -r server/requirements.txt || return 1
    echo "requirements.txt installed into .venv"
    return 0
}

section() {
    echo ""
    echo "============================================================="
    echo "=== $1"
    echo "============================================================="
}

run_section() {
    local name="$1"
    shift
    if "$@"; then
        RESULTS["${name}"]="PASS"
    else
        RESULTS["${name}"]="FAIL"
    fi
}

autotools_chain() {
    section "AUTOTOOLS: autogen.sh"
    ./autogen.sh || return 1

    section "AUTOTOOLS: configure"
    sh -x ./configure || return 1

    section "AUTOTOOLS: make"
    make SHELL="sh -x" || return 1

    section "AUTOTOOLS: make check"
    make SHELL="sh -x" check || return 1

    section "AUTOTOOLS: make install (safe DESTDIR, not the real system)"
    rm -rf /tmp/cicd-runner-install-test
    make SHELL="sh -x" install DESTDIR=/tmp/cicd-runner-install-test || return 1

    section "AUTOTOOLS: staged install contents"
    find /tmp/cicd-runner-install-test -type f | sort

    section "AUTOTOOLS: make uninstall (same safe DESTDIR)"
    make SHELL="sh -x" uninstall DESTDIR=/tmp/cicd-runner-install-test || return 1

    section "AUTOTOOLS: confirm uninstall removed everything"
    if [ -d /tmp/cicd-runner-install-test/usr ]; then
        echo "WARNING: files remain after uninstall"
        find /tmp/cicd-runner-install-test -type f
    else
        echo "confirmed: fully removed"
    fi
    rm -rf /tmp/cicd-runner-install-test

    section "AUTOTOOLS: make dist"
    make SHELL="sh -x" dist || return 1

    section "AUTOTOOLS: dist tarball produced"
    ls -la ./*.tar.gz 2>&1

    return 0
}

rescrub_check() {
    section "RE-SCRUB: grep for real username across tracked files"
    if grep -rn "arunasp" . \
        --exclude-dir=.git --exclude-dir=node_modules \
        --exclude-dir=dist --exclude-dir=target --exclude-dir=logs \
        --exclude-dir=__pycache__ --exclude-dir=.pytest_cache \
        --exclude=.env --exclude=deploy_cicd_runner.sh --exclude=deploy_cicd_runner_debug.sh; then
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
    make SHELL="sh -x" status || return 1

    section "LIFECYCLE: make logs (bounded via timeout -- it follows/streams by default)"
    timeout 5 make SHELL="sh -x" logs || true

    section "LIFECYCLE: make stop"
    make SHELL="sh -x" stop || return 1

    section "LIFECYCLE: make start (bring it back up)"
    make SHELL="sh -x" start || return 1

    section "LIFECYCLE: confirm it's back up"
    sleep 3
    curl -sS -o /dev/null -w "HTTP status: %{http_code}\n" http://localhost:1444/mcp || true

    return 0
}

echo "Logging full DEBUG output to ${LOG_FILE}"

section "SETUP: ensure repo scripts are executable"
chmod +x ./*.sh 2>/dev/null || true
chmod +x desktop-extension/*.sh 2>/dev/null || true
echo "chmod +x applied to *.sh and desktop-extension/*.sh"

section "SETUP: ensure .venv satisfies server/requirements.txt"
ensure_venv || echo "WARNING: .venv setup failed -- autotools chain will likely fail too"

run_section "autotools" autotools_chain
run_section "rescrub"   rescrub_check
run_section "lifecycle" lifecycle_check

echo ""
echo "============================================================="
echo "=== SUMMARY"
echo "============================================================="
for k in autotools rescrub lifecycle; do
    echo "${k}: ${RESULTS[${k}]:-NOT RUN}"
done

echo ""
echo "Full DEBUG log: ${LOG_FILE}"
echo "NOTE: make stop+start recreates the coordinator container -- the"
echo "Desktop extension will likely need a toggle off/on before Claude"
echo "can make further live tool calls (same pattern as every prior"
echo "restart this session)."

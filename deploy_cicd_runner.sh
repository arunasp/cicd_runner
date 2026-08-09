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

section "SETUP: ensure .venv satisfies server/requirements.txt"
ensure_venv >> "${LOG_FILE}" 2>&1 || echo "WARNING: .venv setup failed -- autotools chain will likely fail too"

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

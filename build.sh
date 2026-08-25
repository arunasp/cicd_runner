#!/usr/bin/env bash
# Builds cicd-runner's own two Docker images (worker + coordinator).
# For the Desktop extension .mcpb, see desktop-extension/build.sh --
# deliberately a separate script (Makefile is the front end that ties
# both together; see Makefile's own `build`/`build-extension`/`build-all`
# targets).
#
# Usage: ./build.sh [stage...]
#   worker      - docker build -t cicd-worker ./worker. Needs plain
#                 `docker` only -- does NOT need docker compose/
#                 docker-compose at all.
#   coordinator - docker compose build (or docker-compose build).
#                 compose-vs-hyphenated detection happens HERE, lazily,
#                 not as a blanket precondition for the whole script --
#                 confirmed live: an earlier version checked for
#                 compose unconditionally at the top, which made
#                 `./build.sh worker` alone spuriously require compose
#                 even though that stage never uses it.
#   all         - both of the above, in order (default if no stage given)
set -euo pipefail

# `pwd -P` for the same reason start.sh uses it: this resolves the
# checkout's real location, and a build context reached through a
# symlink is not the same thing to the docker daemon as the path it
# points at.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "${script_dir}"

declare -a FAILED_STAGES=()

run_stage() {
    local name="$1"
    shift
    local rc=0
    "$@" || rc=$?
    case "${rc}" in
        0) echo "[PASS] ${name}" >&2 ;;
        2) echo "[SKIP] ${name}" >&2 ;;
        *) echo "[FAIL] ${name}" >&2; FAILED_STAGES+=("${name}") ;;
    esac
    return 0
}

stage_worker() {
    if ! command -v docker &>/dev/null; then
        echo "  (docker not found on PATH -- cannot build anything)" >&2
        return 1
    fi
    docker build -t cicd-worker ./worker
}

stage_coordinator() {
    # Detection lives in compose.sh, not here -- see its own header.
    # This used to be a third copy of the same three-branch logic
    # (configure.ac and start.sh had the others), which is exactly the
    # drift this project already refused to accept between start.sh and
    # build.sh's own build steps.
    "${script_dir}/tools/compose.sh" build
}

stages=("${@:-all}")
if [[ "${stages[0]}" == "all" ]]; then
    stages=(worker coordinator)
fi

for stage in "${stages[@]}"; do
    case "${stage}" in
        worker)      run_stage worker stage_worker ;;
        coordinator) run_stage coordinator stage_coordinator ;;
        *)
            echo "error: unknown stage '${stage}'" >&2
            echo "Usage: $0 [worker|coordinator|all]" >&2
            exit 1
            ;;
    esac
done

if [[ ${#FAILED_STAGES[@]} -gt 0 ]]; then
    echo "RESULT: FAILED -- ${FAILED_STAGES[*]}" >&2
    exit 1
fi
echo "RESULT: ALL PASS" >&2

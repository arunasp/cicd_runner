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

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
    local compose_cmd
    if docker compose version &>/dev/null; then
        compose_cmd=(docker compose)
    elif command -v docker-compose &>/dev/null; then
        compose_cmd=(docker-compose)
    else
        echo "  (neither 'docker compose' (v2) nor 'docker-compose' (v1) found)" >&2
        return 1
    fi
    "${compose_cmd[@]}" build
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

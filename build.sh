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
#   verify      - run each built image once (`--entrypoint true`). A build
#                 can pass entirely from cache while the daemon cannot
#                 unpack the result; only starting a container proves it.
#   all         - worker, coordinator, in order (default). verify is
#                 NOT part of it: `make all` builds and starts nothing.
#                 start.sh and `make rebuild` name verify explicitly.
#
# BUILD_FLAGS is passed to both build stages, e.g.
#   BUILD_FLAGS="--no-cache --pull" ./build.sh
set -euo pipefail

# `pwd -P` for the same reason start.sh uses it: this resolves the
# checkout's real location, and a build context reached through a
# symlink is not the same thing to the docker daemon as the path it
# points at.
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "${script_dir}"

declare -a FAILED_STAGES=()

# Word-split on purpose: a flag list, not a path.
read -r -a build_flags <<< "${BUILD_FLAGS:-}"

# Image names as the build stages produce them: the worker tag below,
# and `image:` in docker-compose.yml for the coordinator.
WORKER_IMAGE_NAME="cicd-worker"
COORDINATOR_IMAGE_NAME="cicd-runner"

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

# Docker stages belong to the coordinator (run_command) or the host;
# a worker has no docker by design.
require_docker() {
    if ! command -v docker &>/dev/null; then
        echo "  (docker not found on PATH -- run this stage through the coordinator (run_command) or on the host)" >&2
        return 1
    fi
}

# The worker image bakes its runtime user at build time. The coordinator
# builds as root with HOST_UID/HOST_GID set; `sudo` sets SUDO_UID/SUDO_GID;
# otherwise the invoking user is the host user.
stage_worker() {
    require_docker || return 1
    local uid gid uid_args=()
    uid="${HOST_UID:-${SUDO_UID:-$(id -u 2>/dev/null || echo 0)}}"
    gid="${HOST_GID:-${SUDO_GID:-$(id -g 2>/dev/null || echo 0)}}"
    if [[ "${uid}" != 0 ]]; then
        uid_args=(--build-arg "WORKER_UID=${uid}" --build-arg "WORKER_GID=${gid}")
    else
        echo "  (worker user: building as root with no HOST_UID or SUDO_UID -- keeping the image default)" >&2
    fi
    docker build "${build_flags[@]}" "${uid_args[@]}" -t "${WORKER_IMAGE_NAME}" ./worker
}

stage_coordinator() {
    # Detection lives in compose.sh, not here -- see its own header.
    # This used to be a third copy of the same three-branch logic
    # (configure.ac and start.sh had the others), which is exactly the
    # drift this project already refused to accept between start.sh and
    # build.sh's own build steps.
    "${script_dir}/tools/compose.sh" build "${build_flags[@]}"
}

stage_verify() {
    local image rc=0
    require_docker || return 1
    for image in "${WORKER_IMAGE_NAME}" "${COORDINATOR_IMAGE_NAME}"; do
        if docker run --rm --network none --entrypoint true "${image}"; then
            echo "  ${image}: starts" >&2
        else
            echo "  ${image}: cannot start a container from this image" >&2
            rc=1
        fi
    done
    if [[ "${rc}" -ne 0 ]]; then
        echo "  rebuild without cache: make rebuild" >&2
    fi
    return "${rc}"
}

stages=("${@:-all}")
if [[ "${stages[0]}" == "all" ]]; then
    stages=(worker coordinator)
fi

for stage in "${stages[@]}"; do
    case "${stage}" in
        worker)      run_stage worker stage_worker ;;
        coordinator) run_stage coordinator stage_coordinator ;;
        verify)      run_stage verify stage_verify ;;
        *)
            echo "error: unknown stage '${stage}'" >&2
            echo "Usage: $0 [worker|coordinator|verify|all]" >&2
            exit 1
            ;;
    esac
done

if [[ ${#FAILED_STAGES[@]} -gt 0 ]]; then
    echo "RESULT: FAILED -- ${FAILED_STAGES[*]}" >&2
    exit 1
fi
echo "RESULT: ALL PASS" >&2

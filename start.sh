#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

if [[ ! -f .env ]]; then
    echo "error: .env not found -- copy .env.example to .env and fill in real project paths first" >&2
    exit 1
fi

# Delegates to build.sh rather than duplicating its docker build/compose
# build logic here -- confirmed 2026-08-08 this project's own build
# steps were living in two places (start.sh and build.sh) that could
# silently drift apart. worker+coordinator only -- the Desktop
# extension isn't needed to launch the service, and build.sh already
# SKIPs (not fails) that stage if node/npm/npx aren't present anyway.
echo "Building..." >&2
./build.sh worker coordinator

# Computed fresh from the actual launching user every time, not
# stored in .env -- avoids staleness if this is ever run by a
# different user later. Read by docker-compose.yml's HOST_UID/
# HOST_GID interpolation, passed through to bash_mcp_server.py's
# _user_flags(), so run_in_directory()'s worker containers create
# host-bind-mounted files with the correct owner instead of the
# worker's default (root). See bash_mcp_server.py's own docstring.
# Declared and exported separately (not `export X="$(...)"`), which
# avoids masking a failing command substitution's own exit code
# (correctly flagged by lint rule 2155 for the combined form).
HOST_UID="$(id -u)"
export HOST_UID
HOST_GID="$(id -g)"
export HOST_GID

# Self-locating, same reasoning as HOST_UID/HOST_GID above -- computed
# fresh from wherever this checkout actually lives, not typed into
# .env by hand, so it can't drift from reality if the checkout is
# ever moved or cloned somewhere else. DYNAMIC_ROOT is this project's
# own PARENT directory (sibling projects stay reachable via
# run_in_directory(), matching the original design), not this
# project's own directory -- narrowing it to just this checkout would
# make run_in_directory() unable to reach anything outside cicd-runner
# itself. CACHE_ROOT lives INSIDE this checkout as .cicd-runner-cache/
# (gitignored) rather than under $HOME, so the whole deployment is
# self-contained in one directory. Neither is read from .env anymore;
# .env.example documents this the same way it already documents
# HOST_UID/HOST_GID not being set there.
DYNAMIC_ROOT="$(dirname "${script_dir}")"
export DYNAMIC_ROOT
CACHE_ROOT="${script_dir}/.cicd-runner-cache"
export CACHE_ROOT
mkdir -p "${CACHE_ROOT}"

# Explicit subdirectories, not just the top-level CACHE_ROOT itself
# (fixing a real bug found live 2026-08-09): without this, Docker's
# own bind-mount behavior auto-creates a referenced host-side
# directory the FIRST time a worker mounts it, if it doesn't already
# exist -- and since the Docker daemon itself runs with root
# privileges regardless of which user invoked the client/CLI, that
# auto-created directory ends up root-owned on the host. The mapped
# worker user (see worker/entrypoint.sh) can then never write to it,
# even though its OWN uid matches HOST_UID exactly -- confirmed live:
# `pip install` silently disabled its own cache with a real permission
# warning, rather than failing outright, which made this easy to miss
# without directly checking. Creating them here instead, while this
# script still runs as the real launching user, avoids Docker ever
# being the one to create them first.
mkdir -p "${CACHE_ROOT}/npm" "${CACHE_ROOT}/pip" "${CACHE_ROOT}/cargo-registry" "${CACHE_ROOT}/cargo-git"

if docker compose version &>/dev/null; then
    compose() { docker compose "$@"; }
elif command -v docker-compose &>/dev/null; then
    compose() { docker-compose "$@"; }
else
    echo "error: neither 'docker compose' (v2) nor 'docker-compose' (v1) found" >&2
    exit 1
fi

# Drop any existing container before recreating it -- same
# docker-compose v1 KeyError: 'ContainerConfig' recreate bug as
# LocusAI's own start.sh guards against.
echo "Removing any stale container..." >&2
compose rm -sf
echo "Launching..." >&2
compose up -d

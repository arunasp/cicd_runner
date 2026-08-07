#!/usr/bin/env bash
set -euo pipefail

if docker compose version &>/dev/null; then
    compose() { docker compose "$@"; }
elif command -v docker-compose &>/dev/null; then
    compose() { docker-compose "$@"; }
else
    echo "error: neither 'docker compose' (v2) nor 'docker-compose' (v1) found" >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${script_dir}"

if [[ ! -f .env ]]; then
    echo "error: .env not found -- copy .env.example to .env and fill in real project paths first" >&2
    exit 1
fi

echo "Building..." >&2
compose build

# Drop any existing container before recreating it -- same
# docker-compose v1 KeyError: 'ContainerConfig' recreate bug as
# LocusAI's own start.sh guards against.
echo "Removing any stale container..." >&2
compose rm -sf
echo "Launching..." >&2
compose up -d

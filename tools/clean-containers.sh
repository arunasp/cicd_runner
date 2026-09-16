#!/bin/sh
# Removes, by ID, every container compose labels for this project.
#
# Fallback for `compose rm -sf` when the daemon lists a container that
# compose cannot remove. Exit 0 when nothing is left, 1 otherwise.
#
# Usage: tools/clean-containers.sh [project]
#   project defaults to COMPOSE_PROJECT_NAME, else the checkout's
#   directory name normalised the way compose does.
set -u

repo="$(cd "$(dirname "$0")/.." && pwd -P)"
default="$(basename "${repo}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
project="${1:-${COMPOSE_PROJECT_NAME:-${default}}}"
filter="label=com.docker.compose.project=${project}"

ids="$(docker ps -a -q --no-trunc --filter "${filter}")" || exit 1
if [ -z "${ids}" ]; then
    echo "no containers for compose project ${project}"
    exit 0
fi

# `docker rm -f` exits 0 for a record it cannot look up, so the result
# is read back from the daemon rather than taken from the exit code.
for id in ${ids}; do
    docker rm -f "${id}" >/dev/null
    if [ -z "$(docker ps -a -q --no-trunc --filter "id=${id}")" ]; then
        echo "removed ${id}"
    else
        echo "cannot remove ${id}" >&2
    fi
done

left="$(docker ps -a -q --no-trunc --filter "${filter}")" || exit 1
if [ -n "${left}" ]; then
    echo "containers the daemon lists but will not remove:" >&2
    echo "${left}" >&2
    exit 1
fi

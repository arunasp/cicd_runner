#!/bin/sh
# Single source of truth for "which compose does this userland have".
#
# Exists because the answer is a property of the USERLAND -- not of the
# checkout, and not of the machine or the distribution either, both of
# which are only proxies for it. The evidence is right here: the
# coordinator container and the host it runs on are the same machine
# and answer differently, because what actually varies is which compose
# is installed. This checkout is read by two boots plus two container
# images, four userlands with four inventories. ./configure used to
# substitute the answer into the generated Makefile once, which made it
# correct only on the host where configure last ran -- confirmed live
# 2026-08-25: a Makefile generated in a userland that had only v1 baked
# `docker-compose`, and `make stop`/`logs`/`status` then failed with
# exit 127 on a host that had only the v2 plugin AND inside the
# coordinator container, neither of which had the v1 binary. Detecting
# here, at invocation, is correct in all four environments.
#
# POSIX sh and exec'd rather than sourced, so build.sh, start.sh and
# the Makefile can all route through this one file without caring what
# shell they are.
#
# Usage: tools/compose.sh <compose args...>     e.g. tools/compose.sh down
set -u

if docker compose version >/dev/null 2>&1; then
    exec docker compose "$@"
elif command -v docker-compose >/dev/null 2>&1; then
    exec docker-compose "$@"
fi

echo "error: neither 'docker compose' (v2) nor 'docker-compose' (v1) found" >&2
exit 127

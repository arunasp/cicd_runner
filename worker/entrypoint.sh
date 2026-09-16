#!/bin/sh
# Entrypoint for cicd-worker -- confirmed real, live fix 2026-08-09.
#
# Without this, `docker run --user <uid>:<gid> cicd-worker <binary>
# <args>` (the previous design -- see bash_mcp_server.py's own
# _user_flags()) had the kernel try to execve() the requested binary
# directly as that uid, with no /etc/passwd entry for it at all (the
# image has no knowledge of the real host's uid ahead of time).
# Reproduced live and confirmed NOT git-specific -- the exact same
# "exec: resource temporarily unavailable" failure happened for `ls`
# too, for any binary, every time, only when --user was used (works
# fine as the image's own default root user). This is a well-documented
# problem class (Apache Airflow's own docker-stack entrypoint, Red
# Hat's OpenShift arbitrary-uid guidance, and others all solve it the
# same shape): start the container as root, dynamically add a real
# /etc/passwd + /etc/group entry for the runtime-provided uid:gid with
# a proper $HOME, then drop privileges before exec'ing the real
# command -- rather than the kernel ever trying to exec() directly as
# an unrecognized uid with no passwd entry at all.
#
# Uses setpriv (part of util-linux, a core Debian package -- see
# Dockerfile) rather than gosu/su-exec: no extra binary to download,
# and its own --reset-env flag does exactly what's needed here --
# "clear all environment and initialize HOME, SHELL, USER, LOGNAME and
# PATH" from the target uid's own (just-created) passwd entry, giving
# a genuinely fully-initialized shell environment, not just a raw uid
# switch. Confirmed via direct testing before this was written, not
# just reasoned about: a fresh, never-before-seen uid gets a real
# /home/worker directory it can actually write to, with HOME/USER/id
# all correctly reflecting the new identity.
#
# A SECOND, real bug found live 2026-08-09 in this same mechanism:
# --reset-env's own "clear all environment" is exactly that -- ALL of
# it, not just HOME/SHELL/USER/LOGNAME/PATH's own prior values. This
# silently destroyed the cache-location env vars bash_mcp_server.py's
# own _cache_env_flags() passes at `docker run` time (NPM_CONFIG_CACHE,
# CARGO_HOME, PIP_CACHE_DIR) before this script even runs -- confirmed
# live via a real worker showing HOME correctly set to /home/worker,
# but all three cache vars silently gone, making the entire dependency
# cache mount design inert even though the mounts themselves were
# correct. setpriv itself has no partial-reset option (confirmed via
# its own --help: --reset-env is all-or-nothing) -- fixed by capturing
# these specific, known-safe vars BEFORE setpriv runs (while still
# root, with the original docker-run-time environment intact), then
# re-injecting them via `env` immediately after the reset, within the
# same setpriv invocation.
set -e

# The runner sends WORKER_UID/WORKER_GID; a container following the
# docker-run-as-host-user convention sends TARGET_UID/TARGET_GID.
WORKER_UID="${WORKER_UID:-${TARGET_UID:-}}"
WORKER_GID="${WORKER_GID:-${TARGET_GID:-}}"

if [ -n "${WORKER_UID:-}" ] && [ -n "${WORKER_GID:-}" ]; then
    if ! getent passwd "${WORKER_UID}" >/dev/null 2>&1; then
        if ! getent group "${WORKER_GID}" >/dev/null 2>&1; then
            addgroup --gid "${WORKER_GID}" worker >/dev/null 2>&1
        fi
        adduser --uid "${WORKER_UID}" --gid "${WORKER_GID}" --home /home/worker \
            --shell /bin/sh --disabled-password --gecos "" worker >/dev/null 2>&1
        # adduser does NOT chown a home directory that already exists
        # (confirmed live) -- explicit chown here regardless, so
        # ownership is always correct even in that edge case.
        chown "${WORKER_UID}:${WORKER_GID}" /home/worker
    fi

    preserve_args=""
    [ -n "${NPM_CONFIG_CACHE:-}" ] && preserve_args="${preserve_args} NPM_CONFIG_CACHE=${NPM_CONFIG_CACHE}"
    [ -n "${CARGO_HOME:-}" ] && preserve_args="${preserve_args} CARGO_HOME=${CARGO_HOME}"
    [ -n "${PIP_CACHE_DIR:-}" ] && preserve_args="${preserve_args} PIP_CACHE_DIR=${PIP_CACHE_DIR}"

    # Intentional word-splitting below: each preserved var is one
    # controlled "KEY=VALUE" argument, values are always fixed,
    # hardcoded paths from bash_mcp_server.py's own _cache_env_flags()
    # (never external/user input).
    # shellcheck disable=SC2086
    exec setpriv --reuid="${WORKER_UID}" --regid="${WORKER_GID}" --clear-groups --reset-env \
        env ${preserve_args} "$@"
fi

# No WORKER_UID/WORKER_GID set -- run as the image's own default user
# (root), unchanged from before this fix. Matches the same
# optional-degrades-gracefully pattern as every other optional setting
# in this project (CACHE_ROOT_HOST, the old HOST_UID/HOST_GID check).
exec "$@"

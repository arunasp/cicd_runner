FROM python:3.12-slim

# This is the EPHEMERAL worker image -- one fresh container per
# run_command() call, `docker run --rm`'d by the coordinator (see
# ../server/bash_mcp_server.py), never itself long-lived. Deliberately
# leaner than the coordinator's own image:
#   - NO docker CLI here -- workers don't spawn their own children;
#     only the coordinator talks to the host daemon. A worker with its
#     own docker access would be a real, unnecessary privilege
#     escalation (this image mounted with the same socket the
#     coordinator has would let ANY run_command call do anything the
#     coordinator can).
#   - NO `pip install mcp` / FastMCP -- workers don't run
#     bash_mcp_server.py or speak MCP at all. They're invoked directly
#     as `docker run ... <worker-image> <binary> <args...>` with the
#     requested binary AS the container's own command -- see
#     _run_in_worker() in bash_mcp_server.py. Allowlist enforcement
#     happens in the COORDINATOR before this container is ever
#     started, not inside it -- there's no code running in here to
#     enforce anything, by design (nothing to bypass).
#
# Startup latency note: image SIZE barely matters for `docker run`
# startup once an image is already built and cached locally (no
# network pull, no install-at-launch -- everything below happens once,
# at build time). What actually matters for "quick spin-off" is
# avoiding exactly those two things at RUN time, which this already
# does. Kept reasonably lean anyway, but not chasing minimal-image-size
# as the primary lever.
#
# gcc + libc6-dev added 2026-08-08 -- confirmed live via
# examples/hello-gcc's real `make lint`/`build` genuinely failing
# with 'cc: No such file or directory' through run_in_directory
# before this. Explicit, not relying on gcc's own Recommends to pull
# libc6-dev, since --no-install-recommends below skips those.
# util-linux, explicitly -- provides setpriv, used by entrypoint.sh
# to drop from root to the runtime-provided WORKER_UID/WORKER_GID with
# a fully-initialized environment (see entrypoint.sh's own header for
# the real, live-confirmed bug this fixes). A core Debian package,
# almost certainly already present on this base image, but installed
# explicitly rather than assumed -- cheap, and guarantees correctness
# regardless of what this or a future base image strips out.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        curl \
        gnupg \
        shellcheck \
        make \
        gcc \
        libc6-dev \
        util-linux \
    && rm -rf /var/lib/apt/lists/*

# gh CLI, official repo per current docs -- same pattern as the
# coordinator's own Dockerfile (verified there 2026-08-06).
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Node.js, for any project's own JS build/test/lint stage. NodeSource's
# official setup script, matching the coordinator's own convention.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# pytest: allowlisted (server/allowlist.txt) but was never actually
# installed anywhere in this image -- confirmed as a real, pre-existing
# gap 2026-08-08 (same gap independently found in the coordinator's
# own requirements.txt and in LocusAI's). No requirements.txt here
# since this image otherwise installs zero Python packages -- a
# single pip install is simpler than adding one for one package. No
# --break-system-packages needed -- the coordinator's own existing
# `pip install -r requirements.txt` line already works without it on
# this same python:3.12-slim base (confirmed in a real successful
# build), so this matches that proven pattern rather than adding an
# unnecessary flag.
RUN pip install --no-cache-dir pytest

# Shared, reusable Makefile fragment (self-documenting `help` target)
# baked in at a fixed path -- see examples/cicd-common.mk (canonical
# source) for the full reasoning. Any project's own Makefile can
# `-include /etc/cicd-common.mk` to pick this up automatically when
# run through this worker, no per-project copy needed.
COPY cicd-common.mk /etc/cicd-common.mk

# Baked-in worker user, matching this deployment's own known HOST_UID/
# HOST_GID (added 2026-08-09, per Arunas's own direction after the
# purely-dynamic entrypoint approach alone still hit EAGAIN on exec()
# even after successfully resolving credentials via setpriv --
# something about creating the passwd/group entry and switching to it
# entirely at container RUNTIME, rather than having it already present
# in the image's own layers, appears to matter in this environment).
# Defaults to 1000:1000 -- this project's own real, consistently-
# observed HOST_UID/HOST_GID throughout this session -- but stays a
# real build arg, not hardcoded, so the image can be rebuilt for a
# different uid:gid via --build-arg if this ever runs as a different
# host user. entrypoint.sh's own getent check means this baked-in user
# is used directly (skipping its dynamic-creation branch entirely)
# whenever WORKER_UID/WORKER_GID matches what's baked in here -- no
# entrypoint.sh changes needed for this to take effect.
ARG WORKER_UID=1000
ARG WORKER_GID=1000
RUN groupadd --gid "${WORKER_GID}" worker \
    && useradd --uid "${WORKER_UID}" --gid "${WORKER_GID}" --home-dir /home/worker \
        --create-home --shell /bin/sh worker

# entrypoint.sh (added 2026-08-09) -- see its own header comment for
# the real, live-confirmed bug this fixes (WORKER_UID/WORKER_GID with
# no matching /etc/passwd entry causing execve() to fail with EAGAIN
# for any binary). chmod +x at build time rather than relying on the
# host filesystem to preserve the exec bit through a bind mount/COPY.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

WORKDIR /workspace

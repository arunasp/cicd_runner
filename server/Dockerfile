FROM python:3.12-slim

# Base toolchain every project's tools/pipeline.sh-style lint/test stage
# needs: git (push/pull, same allowlist reasoning as LocusAI's own),
# openssh-client (git-over-ssh), curl/gnupg (fetching the two apt repos
# below), shellcheck (lint stage), gcc + libc6-dev (added 2026-08-08 --
# confirmed live via examples/hello-gcc's real `make lint`/`build`
# genuinely failing with 'cc: No such file or directory' through
# run_command before this; explicit, not relying on gcc's own Recommends
# to pull libc6-dev, since --no-install-recommends below skips those).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        curl \
        gnupg \
        shellcheck \
        make \
        gcc \
        libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Children of the server now run as HOST_UID (see _child_kwargs in
# bash_mcp_server.py); this setting still covers the root fallback when
# HOST_UID is unset.
# Real bug found live 2026-08-08: this container runs as root by
# default (no USER directive), so its own `git` invocations (e.g.
# resolve_project_dir.sh's `git rev-parse --show-toplevel`, used by
# LocusAI and other mounted projects) can end up owned by a DIFFERENT
# uid than the mounted project directory -- confirmed live: right
# after a host-side `chown` to the real host user, LocusAI's own
# server startup started failing with git's own dubious-ownership
# protection ("detected dubious ownership in repository at
# '/projects/LocusAI'"), a real security feature (CVE-2022-24765)
# meant to stop a DIFFERENT-uid process from silently operating on a
# repo it doesn't own. A wildcard is the right call specifically
# HERE, not a blanket bypass: every path this container ever operates
# on is an explicit, admin-configured mount from docker-compose.yml/
# .env (the named /projects/* mounts, or DYNAMIC_ROOT for
# run_in_directory()) -- there's no path by which an untrusted,
# arbitrary repository could ever reach this check, so the ownership
# protection has nothing meaningful left to guard against here.
RUN git config --global --add safe.directory '*'

# gh CLI, official repo per current docs (same pattern as LocusAI's own
# Dockerfile, verified there 2026-08-06).
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# docker CLI only (docker-ce-cli), NOT the full engine (docker-ce) --
# this container talks to the HOST's real daemon over the mounted
# socket (see docker-compose.yml), it never runs its own. That's the
# whole point of this container's existence: one small, dedicated
# place for docker-socket access, instead of every project's own
# service needing it (which would let a project's container rebuild
# itself -- structurally broken, the RPC connection serving the
# rebuild request dies mid-rebuild; see bash_mcp_server.py's own
# docstring).
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# Node.js, for any project's own JS build/test/lint stage (e.g.
# LocusAI's desktop-extension packing, `node --test`). NodeSource's
# official setup script, matching that project's existing convention.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY lib/ lib/
COPY allowlist.txt .
COPY allowlist-worker.txt .
COPY bash_mcp_server.py .

# Shared, reusable Makefile fragment (self-documenting `help` target)
# baked in at a fixed path -- see examples/cicd-common.mk (canonical
# source) for the full reasoning. Any project's own Makefile can
# `-include /etc/cicd-common.mk` to pick this up automatically when
# run through this coordinator, no per-project copy needed.
COPY cicd-common.mk /etc/cicd-common.mk

WORKDIR /projects

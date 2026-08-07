FROM python:3.12-slim

# Base toolchain every project's tools/pipeline.sh-style lint/test stage
# needs: git (push/pull, same allowlist reasoning as LocusAI's own),
# openssh-client (git-over-ssh), curl/gnupg (fetching the two apt repos
# below), shellcheck (lint stage).
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        curl \
        gnupg \
        shellcheck \
    && rm -rf /var/lib/apt/lists/*

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
COPY bash_mcp_server.py .

WORKDIR /projects

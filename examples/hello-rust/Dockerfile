# Worker image for this example, named by .cicd-image. Build it with
# `make build-examples` from the repository root; it is never pulled.
#
# The Rust base runs as root and keeps its toolchain on PATH under
# /usr/local/cargo/bin with RUSTUP_HOME set. The cicd-worker entrypoint
# drops to the host user and clears the environment, so this image
# names PATH and RUSTUP_HOME for it to keep.
FROM rust:1.82-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        util-linux adduser make \
    && rm -rf /var/lib/apt/lists/*

COPY --from=cicd-worker /entrypoint.sh /entrypoint.sh
COPY --from=cicd-worker /etc/cicd-common.mk /etc/cicd-common.mk

ARG WORKER_UID=1000
ARG WORKER_GID=1000
RUN (getent group "${WORKER_GID}" >/dev/null || groupadd --gid "${WORKER_GID}" worker) \
    && (getent passwd "${WORKER_UID}" >/dev/null || useradd --uid "${WORKER_UID}" \
        --gid "${WORKER_GID}" --home-dir /home/worker --create-home --shell /bin/sh worker)

# The runner sets CARGO_HOME=/cache/cargo but mounts only its registry/
# and git/ subdirectories. Created here, the parent stays writable for
# the dropped user instead of being created by docker as root.
RUN mkdir -p /cache/cargo && chmod 1777 /cache/cargo

ENV WORKER_PRESERVE_ENV="PATH RUSTUP_HOME"
ENTRYPOINT ["/entrypoint.sh"]
WORKDIR /workspace

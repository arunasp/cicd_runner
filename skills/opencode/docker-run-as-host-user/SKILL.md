---
name: docker-run-as-host-user
description: "How to correctly run a Docker container as a specific host uid:gid (so files it writes to a bind-mounted host path are owned by the real host user, not root) without hitting exec resource-temporarily-unavailable (EAGAIN) failures. ALWAYS consult this before adding docker run --user (a uid:gid pair) to any image that doesn't already have an entrypoint handling it, or when debugging an EAGAIN/exec failure that only happens with --user set. Also use when a container's own bind-mounted output files are owned by root instead of the invoking host user."
---

# Running a Docker container as a matching host user

## The problem

A container without an explicit uid mapping runs as its image's default user
(usually root). Files it writes to a bind-mounted host path end up owned by
that default user, not whoever actually needs to read/manage the result
afterward.

The naive fix — `docker run --user <uid>:<gid> <image> <command>` — can fail
in two genuinely different, easy-to-conflate ways, both surfacing as the
same symptom: `EAGAIN` ("resource temporarily unavailable") on `execve()`
for *any* binary the container tries to run, not a permissions error or a
missing-file error. Fixing only one of the two causes below can look like
progress (the error message even changes shape) while the underlying
problem remains.

**Cause 1 — missing `/etc/passwd` entry.** If the image has no passwd entry
for the target uid (true for almost any image, since it's built without
knowledge of the real host's specific uid ahead of time), the kernel can't
resolve that uid to a real user record at all.

**Cause 2 — Docker's own default `nproc` ulimit is too low.** Independent
of cause 1, and confirmed via the actual `execve(2)` manual page: after a
`set*uid()` call (which is what `setpriv`/`su`/`runuser` all use internally
to switch the real UID) changes a process's real UID, the kernel checks
that *new* real UID's `RLIMIT_NPROC` limit. If it's already exceeded, an
internal `PF_NPROC_EXCEEDED` flag is set, and the *next* `execve()` call
fails with exactly this `EAGAIN`. `RLIMIT_NPROC` is enforced **per real
UID, system-wide across the whole kernel** — not per-container — so it
counts every thread/process anywhere on the host already running as that
UID, not just what's inside the container. Docker's own default
per-container `nproc` ulimit varies significantly by daemon configuration;
on at least one real, confirmed WSL2 Docker setup it was as low as
`128:256` (soft:hard) — trivially exceeded by an ordinary interactive
session's own everyday process count for that same UID.

A container's own interactive shell reporting a generous `ulimit -u` (e.g.
tens of thousands) does **not** mean the container process itself has that
same limit — that reported value is often the *login shell's own*
separately-configured PAM soft limit, not what the container's init process
actually inherited from the Docker daemon. Check the container's own real,
current limit directly: `cat /proc/self/limits | grep -i proc` run inside
the container (not the host shell).

## Diagnosing which cause (or both) is in play

Don't assume — isolate each cause independently before fixing either:

1. **Confirm the passwd entry resolves.** `getent passwd <uid>` inside the
   container. If this fails, cause 1 applies.
2. **Test the exec failure with multiple, genuinely independent
   uid-switching mechanisms** — `setpriv` (no PAM, direct syscalls), `su`
   (PAM-based), `runuser` (PAM-based). If all three fail identically, that
   rules out anything specific to one particular tool.
3. **Test with the most trivial possible binary** (`/bin/true`) instead of
   whatever binary originally failed. If it fails the same way, that rules
   out anything specific to the original binary (dynamic linking,
   complexity, etc.) — the problem is in the uid-switch/exec mechanism
   itself, not the target program.
4. **Check the container's own actual inherited limit directly**:
   `cat /proc/self/limits | grep -i proc`. A low soft limit (well below
   what a normal interactive session's own process count for that UID
   would already be) confirms cause 2.
5. If the passwd entry resolves cleanly (step 1 succeeds) but the exec
   still fails across every mechanism and binary (steps 2–3), and the
   limit is low (step 4) — that's cause 2, independent of cause 1. Fixing
   only cause 1 will NOT resolve it; the error just changes shape, from a
   bare kernel exec failure to the uid-switching tool's own message (e.g.
   `setpriv: failed to execute <binary>: Resource temporarily unavailable`)
   — meaning the tool itself succeeded at switching credentials, but the
   subsequent exec still failed.

## Fix for cause 1 — supply the passwd entry

Give the image a real entrypoint script that starts as root, checks for an
existing passwd entry, creates one dynamically if missing (real group, real
user, real writable `$HOME`), then drops privileges with a fully reset
environment before exec'ing the real command:

```sh
#!/bin/sh
set -e

if [ -n "${TARGET_UID:-}" ] && [ -n "${TARGET_GID:-}" ]; then
    if ! getent passwd "${TARGET_UID}" >/dev/null 2>&1; then
        if ! getent group "${TARGET_GID}" >/dev/null 2>&1; then
            addgroup --gid "${TARGET_GID}" worker
        fi
        adduser --uid "${TARGET_UID}" --gid "${TARGET_GID}" --home /home/worker \
            --shell /bin/sh --disabled-password --gecos "" worker >/dev/null 2>&1
        # adduser does NOT chown a home directory that already exists --
        # explicit chown regardless, so ownership is always correct.
        chown "${TARGET_UID}:${TARGET_GID}" /home/worker
    fi
    exec setpriv --reuid="${TARGET_UID}" --regid="${TARGET_GID}" --clear-groups --reset-env "$@"
fi

exec "$@"
```

Use `setpriv` for the privilege drop, not `su`/`sudo`/a hand-rolled uid
switch: it's part of `util-linux`, already present in any standard Debian
image (no extra binary to install, unlike `gosu`/`su-exec`), and its own
`--reset-env` flag clears the environment and re-initializes `HOME`,
`SHELL`, `USER`, `LOGNAME`, and `PATH` from the target uid's own passwd
entry — a genuinely fully-initialized shell environment, not just a raw
uid number switch.

Dockerfile:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

Invoke with the target uid/gid as **environment variables**, not a
`--user` flag directly (a bare `docker run --user <uid>:<gid>` with no
entrypoint handling has the kernel try to `execve()` the requested binary
directly as that uid, with nothing to supply the missing passwd entry):

```
docker run --rm -e TARGET_UID=1000 -e TARGET_GID=1000 -v /host/path:/workspace <image> <command>
```

An alternative to dynamic creation: bake a real, matching user into the
image at *build* time instead, via a Dockerfile `ARG`/`groupadd`/`useradd`
defaulting to the deployment's own known host uid:gid. Only worth doing if
diagnosis shows cause 1 (missing/unresolvable passwd data) specifically —
if the real problem is cause 2, baking in a build-time user changes
nothing, since neither approach touches the actual ulimit.

## Fix for cause 2 — raise the container's own `nproc` ulimit

```
docker run --rm --ulimit nproc=8192:8192 -v /host/path:/workspace <image> <command>
```

Pick a value comfortably above what a single container invocation could
plausibly need, without being so large it stops functioning as a
meaningful resource guard. `8192` is a reasonable default for most
workloads. This flag is independent of, and should be applied regardless
of, whatever uid the container ends up running as — root can hit the same
low-ceiling default too, once enough system-wide processes already exist
for uid 0.

## Both causes together

The two fixes are independent and both may be needed. A container using
the entrypoint pattern above (cause 1) should also always pass
`--ulimit nproc=<generous value>:<same>` at `docker run` time (cause 2) —
neither one alone is guaranteed sufficient if both conditions are present
in the environment.

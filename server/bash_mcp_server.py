#!/usr/bin/env python3
"""Project-agnostic CI/CD execution MCP server -- streamable-HTTP transport.

Two ways to run a command, for two genuinely different needs:

- run_command(project, ...): named, pre-configured projects (see
  /projects/<name> mounts in docker-compose.yml), executed directly in
  THIS coordinator container. Kept for cases that need the
  coordinator's own docker-socket access -- e.g. `docker compose
  build` for a project's own service, which needs the coordinator to
  actually see that project's Dockerfile/build context client-side,
  not just hand a path to the daemon.

- run_in_directory(relative_path, ...): any subdirectory under a
  broader DYNAMIC_ROOT, named at CALL time rather than pre-declared in
  docker-compose.yml. Executed in a fresh, ephemeral WORKER container
  (../worker/Dockerfile by default -- see below for overriding this)
  -- `docker run --rm -v <real host path>:/workspace <worker-image>
  <binary> <args>`, then discarded. The worker has NO docker CLI and
  NO access to the coordinator's own socket -- it can only ever touch
  the one directory bind-mounted into it for that one call.
  DYNAMIC_ROOT itself is mounted into the coordinator READ-ONLY,
  purely so a requested path's existence can be confirmed before ever
  invoking `docker run` -- skipping that check would silently create
  an empty directory at a nonexistent host path (Docker's own
  bind-mount behavior), the exact "phantom mount" bug already found
  and fixed for an ssh key mount in a sibling project in this same
  family.
  All actual read/write happens in the worker against the REAL host
  path, not through this read-only view.

Directory ACLs (added 2026-08-09): existing under DYNAMIC_ROOT is
necessary but no longer sufficient for run_in_directory() -- an
additional access-control layer on top, reframed in opencode's own
permission-schema terms rather than inventing a bespoke one (Arunas's
own direction). A path is allowed if ANY of:
  1. It's within the CONNECTING CLIENT's own current MCP root(s),
     fetched live via the real, standard MCP roots protocol
     (session.list_roots()). Genuinely functional for opencode, which
     connects directly -- confirmed real against its own source
     (declares `capabilities: { roots: {} }`, answers with its
     current project directory). Confirmed INERT for Claude Desktop
     connections specifically: the bundled mcp-remote proxy declares
     empty client capabilities (`capabilities: {}`, its own
     src/client.ts) and has no roots handling anywhere in its source,
     so it never answers a roots/list request from this server. See
     #3 below for the real fix covering that gap.
  2. Any KNOWN, mounted project's own opencode.json declares an
     `permission.external_directory` rule that resolves to "allow"
     for that path -- same glob-pattern-map, last-match-wins
     evaluation opencode itself uses, confirmed against its real
     source and documentation. Read directly off the ALREADY-mounted
     /projects/<name> paths -- no new bind mount needed.
  3. The connecting client sent an X-Allowed-Directories header
     (added 2026-08-09 -- the Desktop extension's own real fix for
     gap #1 above, since mcp-remote can't proxy roots at all; see
     desktop-extension/manifest.json's user_config and index.js).
     Comma-separated, each entry translated from Windows/WSL-interop
     form via _translate_windows_path() before comparison -- Claude
     Desktop's own directory picker runs on win32/darwin while this
     coordinator runs inside WSL2, and a real Claude Desktop fileutils
     allowlist was confirmed to mix both genuinely-Windows
     (D:\\Users\\...) and WSL-interop UNC (\\\\wsl.localhost\\Ubuntu\\...)
     path forms in the same list.
  Anything matching none of the above is refused. This is genuinely
  additional to DYNAMIC_ROOT, not a replacement for it in this pass --
  see README.md's own open-items note for what's still pending
  (DYNAMIC_ROOT itself becoming auto-computed rather than a manually
  set env var is a separate, not-yet-made change).

Per-project worker image (added 2026-08-08): the default cicd-worker
image is deliberately thin (git/make/shellcheck/basic scripting tools
-- see ../worker/Dockerfile) and stays that way on purpose -- trying
to pre-install every language toolchain a project might ever need
into one shared image is a losing, ever-growing maintenance battle
(confirmed live: examples/hello-gcc needed gcc added to BOTH images
before it worked at all). Instead, a project can drop a `.cicd-image`
file (single line, an image reference) in its own root directory to
run in a DIFFERENT image for that one call -- typically an official
upstream language image (gcc:13, rust:1.82, golang:1.23, node:22)
rather than cicd-runner maintaining a copy of every toolchain itself.
Matches how GitHub Actions' `container:`, GitLab CI's `image:`, and
Jenkins' per-stage agent images all solve this same problem -- not an
invented pattern. See README.md for the full writeup, including the
real trust-boundary tradeoff this introduces (an arbitrary image
reference means `docker run` may pull from a registry as a side
effect of a tool call, for the first time in this project's design).

Dependency caching (added 2026-08-08): every run_in_directory() call
is a brand-new `--rm` container by design (see above) -- which also
means, without this, every single call re-downloads its entire
dependency tree from scratch, confirmed live as a real, observed cost
(examples/hello-rust re-pulled its whole base image, examples/
hello-typescript re-ran a full `npm install`, on every call). GitHub
Actions/GitLab CI/Jenkins all solve this the same way: cache each
ecosystem's own download-cache directory (not build output -- GitHub
explicitly advises against caching node_modules itself, since it
doesn't survive Node version changes and fights `npm ci`), keyed so
it's reused across runs. This mirrors that: if CACHE_ROOT_HOST is
configured, a handful of FIXED, well-known cache directories (npm,
cargo's registry + git source cache, pip) are mounted read-write into
every worker run, at the same paths those tools already use by
default outside a container. Always the same mounts regardless of
which binary is actually being run -- an unused mount is harmless, the
package manager just never touches it. No per-project configuration
needed, unlike `.cicd-image` -- this isn't a different toolchain, it's
the same one going faster on repeat runs.

Real trade-off, stated plainly (same spirit as `.cicd-image`'s own
note): this cache is GLOBAL and PERSISTENT across every project and
every call, not project-scoped or ephemeral like the rest of this
project's default isolation. That mirrors how these caches already
behave on a normal, uncontained dev machine (cargo's registry cache
is already shared machine-wide), but it does mean a call that writes
something unexpected into the cache could affect a later, unrelated
project's run.

Worker file ownership (added 2026-08-08, mechanism changed 2026-08-09):
without uid mapping, the worker container runs as its image's default
user (root/uid 0 for the plain python:3.12-slim base cicd-worker
builds on) -- meaning every file it creates on a bind-mounted HOST
path ends up owned by root there too, not by whichever real host user
needs to work with the result afterward. Confirmed real, not
hypothetical: examples/hello-rust's own cargo build/test, run through
a worker with no uid mapping, left target/ root-owned on the host --
broke this project's own install-data-local Makefile target (a plain
`cp -r` couldn't read Cargo's own incremental-compilation lock files,
"Permission denied") until worked around by excluding target/ from
that specific copy. That fix only addressed files THIS project's own
install/dist logic happens to touch -- the actual, general fix is
here: if HOST_UID and HOST_GID are both configured (see
docker-compose.yml/start.sh -- set automatically from the real
launching user via `id -u`/`id -g`, not something to configure by
hand), they're passed to the worker as WORKER_UID/WORKER_GID
environment variables, and the worker's own entrypoint.sh (see
../worker/entrypoint.sh) dynamically creates a matching passwd/group
entry and drops privileges to it before exec'ing the requested
binary -- NOT via docker run's own --user flag directly, after a
real, live-confirmed bug: --user <uid>:<gid> with no matching
/etc/passwd entry for that uid causes the kernel's own execve() to
fail with EAGAIN ("resource temporarily unavailable") for ANY binary,
reproduced live for both git and ls. Optional and degrades to the old
behavior when unset (e.g. rootless Docker setups may not need this at
all) -- same pattern as CACHE_ROOT_HOST, not a hard requirement.

This container also mounts /var/run/docker.sock so `docker` is usable
from inside it -- unlike a named project's own container might,
which should deliberately NOT have docker/npm/npx on its allowlist,
for exactly this reason: a project's own container cannot safely
rebuild itself (the RPC connection serving the rebuild request dies
mid-rebuild). This runner is a separate container from every project
it builds, so rebuilding e.g. a named project's own local-bash
service is runner-container (A) acting on project-container (B) --
no self-rebuild, no chicken-and-egg.
"""

import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import mcp.types as types
from mcp.server.fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from lib.common import FileAllowlist, ExecutionResult, run_allowlisted

PROJECTS_ROOT = Path("/projects")
DYNAMIC_ROOT = Path("/dynamic-root")
DYNAMIC_ROOT_HOST = os.environ.get("DYNAMIC_ROOT_HOST", "")
CACHE_ROOT_HOST = os.environ.get("CACHE_ROOT_HOST", "")
HOST_UID = os.environ.get("HOST_UID", "")
HOST_GID = os.environ.get("HOST_GID", "")
DEFAULT_WORKER_IMAGE = os.environ.get("WORKER_IMAGE", "cicd-worker")
IMAGE_CONFIG_FILENAME = ".cicd-image"
OPENCODE_CONFIG_FILENAME = "opencode.json"
ALLOWED_DIRECTORIES_HEADER = "X-Allowed-Directories"
TIMEOUT_SECONDS = int(os.environ.get("CICD_TIMEOUT_SECONDS", "300"))
DOCKER_SOCKET_PATH = Path("/var/run/docker.sock")

ALLOWED_BINARIES = FileAllowlist(Path("/app/allowlist.txt"))

mcp = FastMCP(
    "cicd-runner",
    host="0.0.0.0",
    port=int(os.environ.get("MCP_PORT", "1444")),
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Plain HTTP health check, outside the MCP protocol entirely --
    the SDK's own documented mechanism for this (FastMCP.custom_route(),
    confirmed against its real source/docstring, which gives this exact
    /health-endpoint shape as its own example). Deliberately NOT the
    /mcp endpoint: that one correctly rejects any request without a
    real MCP client's Accept: text/event-stream header (a 406, not a
    failure -- see README.md's own note on this), which makes it a
    poor fit for a plain `curl`/uptime-monitor health check that just
    wants a clean 200. This route requires no auth (per custom_route's
    own docs, intended for exactly this public/health-check use) and
    bypasses the MCP session/protocol layer entirely.

    Checks the docker socket's own existence directly (a cheap
    Path.exists() stat call, not a docker subprocess invocation) --
    this coordinator's entire reason to exist is docker-socket access
    (see this module's own docstring), so a health check that didn't
    confirm that would miss the one dependency that actually matters
    most. Also reports whether DYNAMIC_ROOT_HOST/CACHE_ROOT_HOST are
    configured, real state a person debugging "why isn't my project
    reachable" would otherwise have to go dig up separately.
    """
    return JSONResponse({
        "status": "ok",
        "docker_socket": DOCKER_SOCKET_PATH.exists(),
        "dynamic_root_configured": bool(DYNAMIC_ROOT_HOST),
        "cache_root_configured": bool(CACHE_ROOT_HOST),
    })


def _resolve_project_dir(project: str) -> Path | None:
    """Resolve `project` to a real, mounted subdirectory of
    PROJECTS_ROOT, refusing anything that isn't. Guards against path
    traversal (`../../etc`) and against picking a project name that
    merely LOOKS like a subdirectory but resolves (via a symlink)
    outside PROJECTS_ROOT.
    """
    candidate = (PROJECTS_ROOT / project).resolve()
    try:
        candidate.relative_to(PROJECTS_ROOT.resolve())
    except ValueError:
        return None
    if not candidate.is_dir():
        return None
    return candidate


def _resolve_dynamic_dir(relative_path: str) -> Path | None:
    """Resolve `relative_path` to a real, existing subdirectory of
    DYNAMIC_ROOT (the read-only validation mount) -- NOT the whole
    root itself (that would let one call touch every project under it
    at once, defeating per-call scoping). Same traversal/symlink-escape
    defense as _resolve_project_dir(), tested against 8 cases
    (including two different ways to resolve to the root itself)
    before this was written, not just reasoned about.
    """
    root = DYNAMIC_ROOT.resolve()
    candidate = (DYNAMIC_ROOT / relative_path).resolve()
    if candidate == root:
        return None
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_dir():
        return None
    return candidate


def _resolve_worker_image(project_dir: Path) -> tuple[str | None, str | None]:
    """Returns (image, error) -- exactly one is non-None. A
    `.cicd-image` file in project_dir (read through the coordinator's
    own read-only DYNAMIC_ROOT mount -- no write access needed) has
    its stripped first line used as the image; anything after the
    first line is ignored, not an error, so a project can leave itself
    a comment there. A PRESENT but empty/unreadable file is a REFUSED
    error, not a silent fallback to the default -- a maintainer who
    created an empty file by mistake should be told plainly, not get
    mysterious default-image behavior instead. No file at all is the
    normal, expected case and just returns the default image.
    """
    config_path = project_dir / IMAGE_CONFIG_FILENAME
    if not config_path.is_file():
        return DEFAULT_WORKER_IMAGE, None
    try:
        content = config_path.read_text()
    except OSError as exc:
        return None, f"REFUSED: '{IMAGE_CONFIG_FILENAME}' exists but could not be read: {exc}"
    first_line = content.splitlines()[0].strip() if content.strip() else ""
    if not first_line:
        return None, f"REFUSED: '{IMAGE_CONFIG_FILENAME}' exists but is empty"
    return first_line, None


def _cache_mount_flags() -> list[str]:
    """Fixed, well-known cache directories -- mirrors what each
    ecosystem's own tooling already caches globally on a normal dev
    machine (npm's download cache, cargo's registry + git source
    cache, pip's cache), not project-specific. Deliberately caches
    each tool's own DOWNLOAD cache, not build output like node_modules
    or target/ -- matches GitHub Actions' own documented guidance
    (caching node_modules itself is explicitly NOT recommended there,
    since it doesn't survive version changes and fights `npm ci`).
    Empty list (not an error) when CACHE_ROOT_HOST isn't configured --
    caching is a transparent speed optimization, never a requirement.

    Mount targets are USER-INDEPENDENT paths under /cache/ (added
    2026-08-09, fixing a real bug filed against this project from
    another Claude instance via memory, with evidence attached rather
    than reasoned about): the ORIGINAL design mounted at each tool's
    own DEFAULT lookup location under $HOME (/root/.npm,
    /root/.cargo/..., /root/.cache/pip) -- which was correct back when
    the worker always ran as root (HOME=/root), but silently broke
    the moment _user_env_flags() started dropping privileges to a
    mapped host user: the worker's own entrypoint.sh sets HOME to
    /home/worker for that user, so a tool looking up its OWN default
    cache location under $HOME never found these mounts at all --
    confirmed live via /proc/mounts showing the binds still landing at
    /root/... while `env` inside the same running worker showed no
    cache-related variable and HOME=/home/worker. Rather than have
    this function predict exactly what HOME entrypoint.sh will resolve
    to (coupling it to that script's own internal naming choice), the
    mounts move to fixed, home-independent paths, and _cache_env_flags()
    (below) explicitly redirects each tool there via its own
    documented env var -- correct regardless of which user (root or a
    mapped uid) the container ends up running as.
    """
    if not CACHE_ROOT_HOST:
        return []
    root = CACHE_ROOT_HOST.rstrip("/")
    return [
        "-v", f"{root}/npm:/cache/npm",
        "-v", f"{root}/cargo-registry:/cache/cargo/registry",
        "-v", f"{root}/cargo-git:/cache/cargo/git",
        "-v", f"{root}/pip:/cache/pip",
    ]


def _cache_env_flags() -> list[str]:
    """-e flags pointing each tool at its own cache mount from
    _cache_mount_flags(), via that tool's own documented env var --
    NPM_CONFIG_CACHE (npm's own supported override, confirmed against
    its docs -- equivalent to `npm config set cache`), CARGO_HOME (the
    parent cargo derives both registry/ and git/ from, matching the
    registry/git subdirectory split already mounted), PIP_CACHE_DIR
    (pip's own supported override, confirmed against its docs). Paired
    1:1 with _cache_mount_flags() -- same CACHE_ROOT_HOST gate, same
    empty-list-when-unconfigured degrade, since exporting these when
    nothing is actually mounted there would just make each tool cache
    into an empty, throwaway container path instead of its own real
    default -- harmless, but pointless.
    """
    if not CACHE_ROOT_HOST:
        return []
    return [
        "-e", "NPM_CONFIG_CACHE=/cache/npm",
        "-e", "CARGO_HOME=/cache/cargo",
        "-e", "PIP_CACHE_DIR=/cache/pip",
    ]


def _user_env_flags() -> list[str]:
    """-e WORKER_UID=.../-e WORKER_GID=... for the ephemeral worker, so
    its own entrypoint.sh can drop privileges to the REAL host user
    before exec'ing the requested binary -- files it creates on a host
    bind-mount are then owned by that real user, not the container's
    default (root/uid 0). Confirmed real 2026-08-08: examples/
    hello-rust's own cargo build/test, run through a worker with no
    uid mapping at all, left target/ root-owned on the host -- broke
    install-data-local's plain `cp -r` (permission denied reading
    Cargo's own incremental-compilation lock files) until worked
    around by excluding target/ from that one copy. That fix
    addressed the symptom; this fixes the actual cause.

    NOT passed as docker run's own --user flag directly (that was the
    ORIGINAL design here, changed 2026-08-09 after a real, live-
    confirmed bug): --user <uid>:<gid> with no matching /etc/passwd
    entry for that uid inside the image causes the KERNEL's own
    execve() to fail with EAGAIN ("resource temporarily unavailable")
    for ANY binary, not just one -- reproduced live for both git and
    ls, every time, only with --user set (works fine as the image's
    own default root user). Passing the uid/gid as env vars instead
    lets the container start as root and its own entrypoint.sh
    dynamically create a real passwd/group entry with a proper $HOME
    before dropping privileges via setpriv -- the standard,
    well-established fix pattern for this class of problem (Apache
    Airflow's own docker-stack entrypoint and Red Hat's OpenShift
    arbitrary-uid guidance both solve it the same shape). Empty list
    (not an error) when HOST_UID/HOST_GID aren't both configured --
    same optional-degrades-gracefully pattern as CACHE_ROOT_HOST, not
    a hard requirement (e.g. rootless Docker setups may not need this
    at all); entrypoint.sh itself also degrades to running as-is when
    these env vars aren't set, so both sides agree on the fallback.
    """
    if not HOST_UID or not HOST_GID:
        return []
    return ["-e", f"WORKER_UID={HOST_UID}", "-e", f"WORKER_GID={HOST_GID}"]


def _ulimit_flags() -> list[str]:
    """--ulimit nproc=<soft>:<hard> for the ephemeral worker -- the real
    root cause behind the EAGAIN/"resource temporarily unavailable" bug
    found live 2026-08-09, confirmed via direct diagnosis (not assumed):
    `cat /proc/self/limits` inside a real cicd-worker container showed
    a default nproc soft/hard limit of only 128/256 -- Docker's own
    default per-container ulimits, which vary significantly by daemon
    configuration (confirmed via moby/moby's own real GitHub issue
    tracker discussing this exact variability). RLIMIT_NPROC is
    enforced per REAL uid, system-wide across the whole kernel, not
    per-container -- so switching to real uid 1000 inside a container
    capped at 128 fails immediately if uid 1000 already has more than
    128 threads/processes running anywhere else on the same host
    (trivially true for any normal interactive WSL2 session). Confirmed
    precisely against the real execve(2) manual: after a set*uid() call
    changes the real UID, the kernel sets an internal PF_NPROC_EXCEEDED
    flag if that new real UID is over ITS OWN RLIMIT_NPROC, and the
    NEXT execve() then fails with EAGAIN -- this exactly matches what
    was observed live: three genuinely independent uid-switching
    mechanisms (setpriv, su, runuser) all failed identically, and even
    the most trivial possible binary (/bin/true) failed the same way,
    ruling out anything specific to a tool or binary. This was NOT
    fixed by either the dynamic-passwd-entry design or the later
    baked-in-at-build-time user design (both still hit this, since
    neither touches the actual ulimit) -- the real fix is raising the
    limit explicitly. 8192 is a generous, round value -- comfortably
    above what a single worker invocation could plausibly need, while
    nowhere near large enough to itself be a meaningful resource risk.
    Always applied, not gated behind HOST_UID/HOST_GID like
    _user_env_flags() -- the default root user isn't affected by this
    specific bug (root's own real-uid-0 process count on a typical
    system rarely approaches even a low limit), but there's no reason
    to leave a future non-default-uid path exposed to the same failure
    this fixes today.
    """
    return ["--ulimit", "nproc=8192:8192"]


def _expand_pattern(pattern: str) -> str:
    """Expands a leading ~ or $HOME, matching opencode's own
    documented external_directory pattern syntax exactly (confirmed
    against its real docs: '~/projects/* -> /Users/x/projects/*').
    """
    home = str(Path.home())
    if pattern.startswith("~/"):
        return home + pattern[1:]
    if pattern == "~":
        return home
    if pattern.startswith("$HOME"):
        return home + pattern[len("$HOME"):]
    return pattern


def _match_external_directory(path: str, rules: dict[str, str]) -> str:
    """Evaluates path against an external_directory-style rule map.
    Matches opencode's own real evaluation semantics (confirmed
    against its source and docs, not assumed): rules are checked in
    insertion order, and the LAST matching rule wins, not the first --
    lets a project list a broad allow first and narrow it with a more
    specific deny afterward. Defaults to "ask" when nothing matches,
    same default opencode itself uses for anything outside the
    current workspace.
    """
    result = "ask"
    for pattern, action in rules.items():
        if fnmatch.fnmatch(path, _expand_pattern(pattern)):
            result = action
    return result


def _read_external_directory_rules(project_dir: Path) -> dict[str, str]:
    """Reads <project_dir>/opencode.json's permission.external_directory
    section, if present. A missing file, malformed JSON, or a
    missing/malformed section all return an empty dict rather than
    erroring -- an absent or broken opencode.json just means that
    project has no additional external_directory grants, not a hard
    failure that should break every run_in_directory() call.
    """
    config_path = project_dir / OPENCODE_CONFIG_FILENAME
    if not config_path.is_file():
        return {}
    try:
        data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    rules = data.get("permission", {}).get("external_directory", {})
    if not isinstance(rules, dict):
        return {}
    return {str(k): str(v) for k, v in rules.items() if isinstance(v, str)}


def _translate_windows_path(path: str) -> str:
    """Translates a Windows-side path (as Claude Desktop's own
    directory-picker UI would produce, since Desktop itself runs on
    win32/darwin while this coordinator runs inside WSL2) into its
    WSL2-native Linux equivalent, so it can be compared against the
    Linux-side paths run_in_directory() actually operates on.

    Two real forms confirmed present simultaneously in a real Claude
    Desktop fileutils allowlist (2026-08-09): WSL-interop UNC paths
    (\\\\wsl.localhost\\Ubuntu\\home\\... -- the current form; the
    older \\\\wsl$\\... prefix is also still seen) map directly to
    their Linux path, no drive translation needed. Genuine
    Windows-native paths (D:\\Users\\...) map to WSL2's own default
    drive-mount convention (/mnt/d/Users/...) -- this assumes that
    default mount is active, not a customized one; there's no reliable
    way to detect a customized mount from the coordinator side.
    Already-Linux-style (or unrecognized) paths pass through
    unchanged, so this is safe to apply unconditionally to every
    directory-ACL check without first detecting which form arrived.
    """
    m = re.match(r"^\\\\wsl(?:\.localhost|\$)\\[^\\]+\\(.*)$", path)
    if m:
        return "/" + m.group(1).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):\\(.*)$", path)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return path


def _parse_allowed_directories_header(header_value: str) -> list[str]:
    """Splits and translates the X-Allowed-Directories header value --
    comma-separated, constructed by the Desktop extension's own
    index.js from whatever directories the user selected via Claude
    Desktop's own directory-picker UI (see desktop-extension/
    manifest.json's user_config). Each entry is translated
    independently since a user could plausibly select some
    genuinely-Windows paths and some WSL-interop ones in the same
    pass -- confirmed exactly this mix is possible via a real Claude
    Desktop fileutils allowlist. Empty/missing header degrades to an
    empty list, not an error.
    """
    if not header_value:
        return []
    return [_translate_windows_path(p.strip()) for p in header_value.split(",") if p.strip()]


def _get_allowed_directories_header(ctx: Context) -> str:
    """Reads the X-Allowed-Directories header off the real HTTP
    request. Confirmed real 2026-08-09 against actual mcp SDK source,
    not assumed: the streamable-HTTP transport wraps the raw Starlette
    Request as ServerMessageMetadata(request_context=request)
    (mcp/server/streamable_http.py), which flows through to
    RequestContext.request (mcp/shared/context.py -- its own docstring
    says "Request-specific context (e.g., headers, auth info)"), which
    FastMCP.get_context() wires into Context.request_context
    (mcp/server/fastmcp/server.py). ctx.request_context.request may
    legitimately be None (e.g. a non-HTTP transport) -- degrades to no
    header, not an error, same pattern as every other optional check
    in this file.
    """
    request = getattr(ctx.request_context, "request", None)
    if request is None or not hasattr(request, "headers"):
        return ""
    return request.headers.get(ALLOWED_DIRECTORIES_HEADER, "") or ""


async def _get_client_roots(session) -> list[str]:
    """Fetches the connected client's own MCP roots -- the real,
    standard protocol mechanism (session.list_roots()), not a
    bespoke one. Degrades gracefully to an empty list, not an error,
    when the client doesn't declare roots support or the request
    itself fails -- same optional-degrades-gracefully pattern used
    throughout this project for CACHE_ROOT_HOST/HOST_UID/HOST_GID.
    Confirmed real 2026-08-09 against actual source, not assumed:
    opencode's own MCP client declares `capabilities: { roots: {} }`
    and answers with its current project directory
    (packages/opencode/src/mcp/index.ts); the Python mcp SDK this
    project already depends on has the matching server-side method
    (mcp/server/session.py's ServerSession.list_roots()). Confirmed
    genuinely INERT for Claude Desktop connections specifically: the
    bundled mcp-remote proxy declares empty client capabilities
    (`capabilities: {}`, its own src/client.ts) and has no roots
    handling anywhere in its source -- see _get_allowed_directories_
    header() for the real fix covering that gap.
    """
    try:
        if not session.check_client_capability(
            types.ClientCapabilities(roots=types.RootsCapability())
        ):
            return []
        result = await session.list_roots()
    except Exception:
        return []

    paths = []
    for root in result.roots:
        parsed = urlparse(str(root.uri))
        if parsed.scheme == "file":
            paths.append(url2pathname(parsed.path))
    return paths


async def _is_path_allowed(requested_path: str, ctx: Context) -> tuple[bool, str]:
    """Combined directory-ACL check for run_in_directory(), reframed
    in opencode's own permission-schema terms rather than a bespoke
    one (2026-08-09). A path is allowed if ANY of:
      1. it's within the connecting client's own current MCP root(s)
         (fetched live -- genuinely functional for opencode, inert
         for Claude Desktop connections via mcp-remote -- see
         _get_client_roots()'s own docstring for why).
      2. any KNOWN, mounted project's own opencode.json
         external_directory rules resolve to "allow" for it.
      3. the connecting client sent an X-Allowed-Directories header
         (the Desktop extension's own real fix for gap #1's Claude
         Desktop blind spot) -- each entry translated from Windows/
         WSL-interop form via _translate_windows_path() first.
    Read directly off the already-mounted /projects/<name> paths for
    #2 -- no new bind mount needed, each project's own opencode.json
    already lives inside its own existing mount. Returns
    (allowed, reason) so callers can surface WHY, not just a bool.
    """
    client_roots = await _get_client_roots(ctx.session)
    for root in client_roots:
        try:
            Path(requested_path).relative_to(root)
            return True, f"within connecting client's own root: {root}"
        except ValueError:
            continue

    if PROJECTS_ROOT.is_dir():
        for project_dir in sorted(PROJECTS_ROOT.iterdir()):
            if not project_dir.is_dir():
                continue
            rules = _read_external_directory_rules(project_dir)
            if not rules:
                continue
            action = _match_external_directory(requested_path, rules)
            if action == "allow":
                return True, f"external_directory allow in {project_dir}/{OPENCODE_CONFIG_FILENAME}"

    header_dirs = _parse_allowed_directories_header(_get_allowed_directories_header(ctx))
    for allowed_dir in header_dirs:
        try:
            Path(requested_path).relative_to(allowed_dir)
            return True, f"within {ALLOWED_DIRECTORIES_HEADER} header entry: {allowed_dir}"
        except ValueError:
            continue

    return False, (
        "not within the connecting client's own MCP root, no known "
        "project's opencode.json external_directory rules allow it, and "
        f"no {ALLOWED_DIRECTORIES_HEADER} header entry allows it"
    )


@mcp.tool()
def list_projects() -> str:
    """List the projects currently mounted and available to
    run_command(). For an ad hoc directory not in this list, use
    run_in_directory() instead.
    """
    if not PROJECTS_ROOT.is_dir():
        return "No projects mounted (PROJECTS_ROOT does not exist)."
    names = sorted(p.name for p in PROJECTS_ROOT.iterdir() if p.is_dir())
    if not names:
        return "No projects mounted."
    return "\n".join(names)


@mcp.tool()
def run_command(project: str, binary: str, args: list[str]) -> str:
    """Run one allowlisted binary with the given argv inside the named
    project's mounted directory, IN THIS coordinator container (has
    real docker-socket access -- needed for e.g. `docker compose
    build`). Call list_projects() first if unsure which names are
    valid. For a directory not pre-mounted here, use
    run_in_directory() instead.
    """
    project_dir = _resolve_project_dir(project)
    if project_dir is None:
        return f"REFUSED: '{project}' is not a mounted project directory"
    return run_allowlisted(binary, args, ALLOWED_BINARIES, project_dir, TIMEOUT_SECONDS)


@mcp.tool()
async def run_in_directory(relative_path: str, binary: str, args: list[str], ctx: Context) -> str:
    """Run one allowlisted binary against an arbitrary subdirectory of
    the dynamic root, named at call time rather than pre-mounted. Runs
    in a fresh, ephemeral worker container -- NOT this coordinator --
    with no docker access of its own, discarded immediately after.
    `relative_path` is relative to the dynamic root (e.g. "some-repo",
    not an absolute host path). Beyond existing under the dynamic
    root, the target must ALSO be allowed by the directory-ACL check:
    within the connecting client's own current MCP root, explicitly
    allowed by a known project's own opencode.json external_directory
    rules, or covered by an X-Allowed-Directories header the client
    sent -- see README.md. If that directory has a `.cicd-image` file,
    its content is used as the worker image instead of the default --
    see README.md. If CACHE_ROOT_HOST is configured, a handful of
    language dependency caches are also mounted in automatically, no
    per-project setup needed -- see README.md. If HOST_UID/HOST_GID
    are configured, the worker's own entrypoint.sh drops privileges to
    that uid:gid before running the requested binary, so files it
    creates are correctly owned on the host -- see README.md.
    """
    if not DYNAMIC_ROOT_HOST:
        return "REFUSED: DYNAMIC_ROOT_HOST is not configured (see docker-compose.yml)"
    if binary not in ALLOWED_BINARIES:
        return f"REFUSED: '{binary}' is not in the allowlist {sorted(ALLOWED_BINARIES)}"

    validated = _resolve_dynamic_dir(relative_path)
    if validated is None:
        return f"REFUSED: '{relative_path}' is not a valid subdirectory under the dynamic root"

    # Compute the REAL host-absolute path from the validated relative
    # offset, not by trusting the caller's raw string -- validated is
    # already a canonicalized, confirmed-safe path; this just swaps
    # the container-side root prefix for the host-side one.
    offset = validated.relative_to(DYNAMIC_ROOT.resolve())
    host_path = f"{DYNAMIC_ROOT_HOST.rstrip('/')}/{offset}"

    allowed, reason = await _is_path_allowed(host_path, ctx)
    if not allowed:
        return f"REFUSED: '{relative_path}' -- {reason}"

    image, image_error = _resolve_worker_image(validated)
    if image_error:
        return image_error

    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{host_path}:/workspace",
             *_cache_mount_flags(), *_cache_env_flags(), *_user_env_flags(), *_ulimit_flags(),
             "-w", "/workspace", image, binary, *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return f"TIMEOUT: worker run exceeded {TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        return "ERROR: 'docker' not found in the coordinator image -- this should never happen"

    return ExecutionResult(result.returncode, result.stdout, result.stderr).as_text()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

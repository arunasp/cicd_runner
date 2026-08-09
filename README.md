# cicd-runner

A project-agnostic CI/CD execution engine that runs as a persistent Docker
service, reachable over MCP (Model Context Protocol). It runs commands
against named projects or arbitrary directories, either directly or in
disposable ephemeral containers.

## Table of contents

- [Why a separate service](#why-a-separate-service)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Architecture](#architecture)
- [Usage](#usage)
- [Configuration](#configuration)
- [Per-project worker images](#per-project-worker-images)
- [Dependency caching](#dependency-caching)
- [Worker file ownership](#worker-file-ownership)
- [Directory ACLs](#directory-acls)
- [Adding a new named project](#adding-a-new-named-project)
- [Standard build (Autotools)](#standard-build-autotools)
- [Build script](#build-script)
- [Shared Makefile fragment](#shared-makefile-fragment)
- [Design decisions](#design-decisions)
- [Status](#status)
- [Contributing](#contributing)
- [License](#license)

## Why a separate service

A project's own container can't safely rebuild itself: the moment
`docker compose up -d` recreates a running container, any in-flight
request that triggered the rebuild is dropped along with it.

`cicd-runner` avoids this by being a genuinely separate process from
everything it builds — one runner container acting on other project
containers, never rebuilding itself.

## Requirements

- Docker, with either the `docker compose` v2 plugin or the standalone
  `docker-compose` v1 binary
- `/var/run/docker.sock` available on the host

## Quick start

```bash
cp .env.example .env   # fill in real project paths
make all                # build everything (runner + extension) + launch
```

`make help` lists every target. Confirm the service is up:

```bash
make logs
curl http://localhost:1444/mcp
```

A `406` response with a `"Client must accept text/event-stream"` body
is expected — it confirms the streamable-HTTP transport is enforcing
its protocol correctly.

## Architecture

Two containers:

```
┌────────────────────────────────────┐
│            cicd-runner              │        one fresh worker per
│      (one persistent container)     │        run_in_directory() call
│                                      │
│  /var/run/docker.sock  ◄────────────┼──┐     ┌──────────────────┐
│                                      │  └────►│   cicd-worker     │
│  /projects/<name>        ◄──────────┼──┐     │  (ephemeral,       │
│  /projects/<name>        ◄──────────┼──┤     │   docker run --rm) │
│  /projects/...            ◄─────────┼──┘     │                    │
│                                      │        │  -v <real host    │
│  /dynamic-root  (read-only,         │        │   path>:/workspace │
│   existence-check only)  ◄──────────┼──┐     │                    │
└────────────────────────────────────┘  │      │  NO docker CLI,    │
                                          │      │  NO socket access  │
                                          └─────►│  discarded after   │
                                                 │  one command       │
                                                 └──────────────────┘
```

**`cicd-runner` (coordinator)** — the only container with access to
`/var/run/docker.sock`. Exposes two tools:

- `run_command(project, binary, args)` — runs directly in the
  coordinator, against a named project mounted at `/projects/<name>`.
  Use this when the call needs to see a project's real build context
  (e.g. `docker compose build`, which reads the Dockerfile itself).
- `run_in_directory(relative_path, binary, args)` — runs in a fresh,
  disposable `cicd-worker` container, against any subdirectory under
  `DYNAMIC_ROOT`, named at call time with no `docker-compose.yml`
  changes required. `DYNAMIC_ROOT` is mounted read-only in the
  coordinator purely to validate that the requested path exists
  before starting a container — real work happens through the
  worker's own read-write mount.

**`cicd-worker` (ephemeral)** — no docker CLI, no MCP/Python
dependencies. The requested binary is the container's entire command.
One `docker run --rm` per call, then discarded.

**`server/lib/common.py`** — shared allowlist and subprocess-execution
helpers.

**`server/allowlist.txt`** — one list gating both tools; see
[Design decisions](#design-decisions).

## Usage

**Claude Desktop**: build `desktop-extension/dist/cicd-runner-<version>.mcpb`
via `make build-extension`, or download it from this repo's
[Releases](../../releases). `index.js` bridges Desktop's stdio
extension model to this server's streamable-HTTP endpoint directly,
using `@modelcontextprotocol/sdk`'s own transports in-process.

**opencode**: add `examples/opencode.mcp-example.json`'s `mcp` block to
your `opencode.json` (global or project-root) — opencode connects
directly over HTTP, no bridge needed.

```
list_projects()
run_command(project="my-project", binary="make", args=["lint"])
```

Run a named project's pipeline via its own Makefile (this project
assumes the standard `lint`/`build`/`deploy`/`verify`/`e2e`/`all`
target names):

```
run_command(project="my-project", binary="make", args=["lint"])
run_command(project="my-project", binary="make", args=["build"])
run_command(project="my-project", binary="make", args=["all"])
```

`make` — not `bash` — is what's allowlisted here: it runs a project's
own version-controlled recipes, a structured and auditable entry
point, rather than letting a call hand `run_command` an arbitrary
shell string.

Run something against a directory that isn't pre-mounted, in a
disposable worker:

```
run_in_directory(relative_path="some-repo", binary="git", args=["status"])
run_in_directory(relative_path="some-repo", binary="make", args=["all"])
```

`relative_path` is relative to `DYNAMIC_ROOT` (this checkout's own
parent directory, computed automatically by `start.sh`), not an
absolute host path.

`examples/hello-bash/`, `hello-gcc/`, `hello-python/`, and
`hello-typescript/` are complete, working pipelines across four
toolchains — useful both as a smoke test and as a template for a new
project's own Makefile.

## Configuration

All configuration lives in `.env` (copy from `.env.example`):

| Variable | Purpose |
|---|---|
| (none by default) | Add a `MY_PROJECT_DIR`-style var per named project mount -- see [Adding a new named project](#adding-a-new-named-project) |
| `CACHE_ROOT` | Optional dependency-cache directory (see below) |

`DYNAMIC_ROOT` (the root directory `run_in_directory()` can reach) and
`HOST_UID`/`HOST_GID` are computed automatically by `start.sh` and are
not set in `.env` — see [Worker file ownership](#worker-file-ownership).

## Per-project worker images

The default `cicd-worker` image is intentionally minimal
(git/make/shellcheck — see `worker/Dockerfile`), rather than trying to
pre-install every toolchain a project might need.

Drop a `.cicd-image` file (one line, an image reference) in a
project's root to run its `run_in_directory()` calls in a different
image:

```
# .cicd-image
rust:1.82-bookworm
```

```
run_in_directory(relative_path="my-rust-project", binary="cargo", args=["test"])
```

Common choices:

| Language | Suggested image |
|---|---|
| C / C++ | `gcc:13-bookworm` |
| Rust | `rust:1.82-bookworm` |
| Go | `golang:1.23-bookworm` |
| Java | `eclipse-temurin:21-jdk` |
| .NET | `mcr.microsoft.com/dotnet/sdk:8.0` |
| Ruby | `ruby:3.3-bookworm` |

Only the first line of `.cicd-image` is read; later lines can hold a
comment. A present-but-empty or unreadable file is refused rather than
silently falling back to the default. This applies only to
`run_in_directory()` — `run_command()` always uses the coordinator's
own environment.

**Trade-off:** unlike the rest of this project, where the worker never
runs anything beyond what's already in a locally cached image, a
`.cicd-image` reference can cause `docker run` to pull an image from a
registry as a side effect of a tool call. Only use this with projects
and `.cicd-image` files you already trust.

## Dependency caching

Every `run_in_directory()` call is a fresh container, which means an
uncached dependency tree gets re-downloaded on every call. If
`CACHE_ROOT` is set, a handful of standard dependency-download-cache
directories are mounted read-write into every worker run:

| Tool | Host path (under `CACHE_ROOT`) | Container path |
|---|---|---|
| npm | `npm/` | `/cache/npm` (`NPM_CONFIG_CACHE`) |
| cargo (registry) | `cargo-registry/` | `/cache/cargo/registry` (`CARGO_HOME=/cache/cargo`) |
| cargo (git sources) | `cargo-git/` | `/cache/cargo/git` (`CARGO_HOME=/cache/cargo`) |
| pip | `pip/` | `/cache/pip` (`PIP_CACHE_DIR`) |

Mount targets are fixed, user-independent paths under `/cache/` rather
than each tool's own default lookup location under `$HOME` (e.g.
`/root/.npm`) — the container's `$HOME` depends on which user it ends
up running as (see [Worker file ownership](#worker-file-ownership)),
so a mount tied to one specific `$HOME` silently stops being found the
moment that changes. Each tool is pointed at its own mount explicitly
via its own documented cache-location env var instead.

This caches each tool's own download cache, not build output
(`node_modules`, `target/`) — consistent with GitHub Actions' own
guidance against caching `node_modules` directly.

Leaving `CACHE_ROOT` unset disables caching; it's a speed optimization,
not a requirement.

**Trade-off:** the cache is global and persistent across every project
and call, unlike the rest of this project's per-call isolation — a
call that writes something unexpected into the cache can affect a
later, unrelated project's run.

## Worker file ownership

Without uid mapping, the worker container runs as its image's default
user — root for the `python:3.12-slim`-based `cicd-worker` — so files
it creates on a bind-mounted host path end up owned by root, not the
real host user.

`start.sh` computes `HOST_UID`/`HOST_GID` from the launching user at
every startup and passes them to the worker as `WORKER_UID`/
`WORKER_GID` environment variables, not a `docker run --user` flag
directly — a bare `--user <uid>:<gid>` on an image with no matching
`/etc/passwd` entry for that uid causes the kernel's own `execve()` to
fail with `EAGAIN` ("resource temporarily unavailable") for any
binary. `worker/entrypoint.sh` starts as root, creates a matching
passwd/group entry with a real `$HOME` if one doesn't already exist,
then drops privileges via `setpriv --reset-env` before exec'ing the
requested binary.

A second, independent fix is needed alongside this: Docker's own
default per-container `nproc` ulimit can be low enough (observed as
low as `128:256` on one real setup) to make even a correct uid switch
fail with the same `EAGAIN` — `RLIMIT_NPROC` is enforced per real uid
system-wide, not per-container, so it's trivially exceeded by an
ordinary interactive host session's own process count for that uid.
Every worker run explicitly passes `--ulimit nproc=8192:8192` to rule
this out, regardless of which uid ends up running.

Leaving `HOST_UID`/`HOST_GID` unset falls back to running as the
image's default user — not an error, since some setups (e.g. rootless
Docker) may not need this. Files already left root-owned from before
this was in place need a manual `chown`; this only affects future
worker runs.

## Directory ACLs

`DYNAMIC_ROOT` alone is a broad, all-or-nothing grant. `run_in_directory()`
adds a second, independent layer on top, using
[opencode](https://opencode.ai)'s own permission-schema terms rather
than a bespoke format. A requested path must satisfy at least one of:

1. **It's within the connecting client's own current MCP root.**
   Fetched via the standard MCP roots protocol
   (`session.list_roots()`) — the same mechanism the official MCP
   filesystem reference server and opencode's own MCP client both use.
   **Genuinely functional for opencode**, which connects directly.
   **Inert for Claude Desktop connections specifically** — the Desktop
   extension (`desktop-extension/index.js`) is itself the one MCP
   client identity cicd-runner ever sees for that session, not
   Desktop's own possible roots declaration, so there's no roots
   information to forward regardless of how the extension itself
   connects to Desktop on its other side. See #3.
2. **A known, mounted project's own `opencode.json` allows it**, via
   `permission.external_directory`:

   ```json
   {
     "$schema": "https://opencode.ai/config.json",
     "permission": {
       "external_directory": {
         "/path/to/sibling-project/**": "allow"
       }
     }
   }
   ```

   Rules are glob patterns, evaluated last-match-wins, read directly
   from each project's existing `/projects/<name>` mount.
3. **The connecting client sent an `X-Allowed-Directories` header.**
   The real fix for #1's Claude Desktop gap: the Desktop extension's
   own `manifest.json` exposes a directory picker
   (`user_config.allowed_directories`) in Claude Desktop's settings
   UI, and `index.js` forwards the selection as a genuine HTTP header
   on its own `StreamableHTTPClientTransport` connection to this
   server. Comma-separated, each
   entry translated from whatever form Claude Desktop's own directory
   picker produced — a genuine Windows path (`D:\Users\...`) or a
   WSL-interop UNC path (`\\wsl.localhost\Ubuntu\...`), both
   confirmed to appear in a real Claude Desktop directory allowlist —
   into its native WSL2 equivalent before comparison.

A path matching neither is refused, with the specific reason given.
Missing or malformed `opencode.json` files, and clients that don't
declare MCP roots support, both degrade to "no additional grants"
rather than an error.

Not yet implemented: generating a starter `opencode.json` for a new
project adopting rule #2 above.

## Adding a new named project

For `run_command()` (needs docker-compose-build visibility):

1. Add a line to `.env` and a matching volume in `docker-compose.yml`:
   `${YOUR_VAR}:/projects/<name>`.
2. Add any binary its pipeline needs to `server/allowlist.txt`.
3. `./start.sh` to rebuild and relaunch.

For anything else — a repo that just needs `git`/`node`/`make`/etc.
run against it — no setup is needed beyond it existing under
`DYNAMIC_ROOT`; use `run_in_directory()` directly.

`examples/project-skeleton/` has a copy-paste Makefile template
(`lint`/`test`/`build`/`deploy`/`verify`/`e2e`/`all`, stubbed to fail
loudly until filled in).

## Standard build (Autotools)

Alongside this project's own `Makefile` interface, `cicd-runner` also
supports the standard `./configure && make && make install` sequence.

```bash
./autogen.sh          # git checkout only -- regenerates configure/Makefile.in
./configure
make
make check
sudo make install     # optional -- stages a copy under $(pkgdatadir)
```

`configure` checks for Docker (required), `docker compose`/`docker-compose`
(either), Python 3 with every package in `server/requirements.txt`
importable (preferring a local `.venv` if one exists), and
`node`/`npm`/`npx` (optional — only needed for the Desktop extension).

`make install` stages a full copy under `$(DESTDIR)$(pkgdatadir)`
(default `/usr/local/share/cicd-runner`) without launching anything;
run `./start.sh` from there afterward.

Generated Autotools files (`configure`, `Makefile.in`, `aclocal.m4`)
aren't committed — `autogen.sh` regenerates them from `configure.ac`/
`Makefile.am` on a fresh checkout; a release tarball (`make dist`)
already includes them.

## Build script

```bash
make build            # ./build.sh          -- runner images only
make build-extension  # ./desktop-extension/build.sh
make build-all        # both
make start            # ./start.sh (builds runner, then launches)
make stop / restart / logs / status
make all              # build-all + start
```

`build.sh` builds the worker and coordinator images and needs only
`docker` — `docker compose`/`docker-compose` is detected lazily, only
when the coordinator stage actually needs it.

`desktop-extension/build.sh` builds the Desktop `.mcpb` package
separately, since it needs Node rather than the runner's own
toolchain. It tolerates a missing npm registry if a local
`node_modules/` cache already exists. Output filename tracks
`manifest.json`'s own version.

## Shared Makefile fragment

`examples/cicd-common.mk` provides a self-documenting `help` target
(via the `## comment` convention) that any example Makefile can pull
in:

```makefile
-include ../cicd-common.mk
-include /etc/cicd-common.mk
```

The first resolves for a standalone checkout; the second resolves
inside a cicd-runner worker/coordinator, where it's baked into both
images. At most one resolves in any given context. If neither does,
`make help` just isn't available — every other target still works.

## Design decisions

- **One dedicated container holds `/var/run/docker.sock`, not each
  project's own service.** Docker-socket access is root-equivalent;
  concentrating it into one small, auditable container is safer than
  spreading it across every project.
- **Manually triggered only — no webhooks, no git hooks, no polling.**
  A hosted CI product's entire trigger/auth model assumes a forge
  relationship this setup doesn't have; local hooks or polling loops
  are prone to race conditions. A plain tool call is simpler and more
  predictable.
- **Two mounting mechanisms, not one.** Named `/projects/<name>`
  mounts are persistent and coordinator-visible, needed for
  `docker compose build`. `DYNAMIC_ROOT` + ephemeral workers need no
  pre-declaration and are isolated per call. Collapsing to one would
  break one of the two use cases.
- **`DYNAMIC_ROOT` is read-only in the coordinator.** It exists only
  to confirm a path exists before `docker run` sees it — otherwise
  Docker silently creates an empty directory at a missing bind-mount
  source. Real work happens through the worker's own read-write
  mount.
- **The worker has no docker CLI and no MCP/Python dependencies.**
  A worker with its own docker access could do anything the
  coordinator can, defeating per-call isolation. Allowlist enforcement
  happens once, in the coordinator, before a worker starts.
- **One shared `allowlist.txt` gates both tools.** `docker` being
  allowlisted already sets the container's privilege ceiling; every
  other entry is narrower than that.
- **No SSH keys or git credentials are mounted here.** Projects that
  need `git push` keep that capability in their own container, scoped
  to that one repo.

## Status

The core service (coordinator + ephemeral worker) is implemented,
tested, and in use. Both the Desktop `.mcpb` connector and the
opencode remote-MCP config work against real client sessions.

Covered by real, committed tests (`server/test_bash_mcp_server.py`):
path resolution and traversal/symlink-escape defense, per-call config
resolution (`.cicd-image`, `CACHE_ROOT`, `HOST_UID`/`HOST_GID`), and
[Directory ACLs](#directory-acls) (MCP roots + `opencode.json`
`external_directory`).

Restarting or rebuilding the coordinator while a client is connected
leaves that session stale — the coordinator has no memory of the old
session ID, so calls get a `404` instead of a response. The Desktop
`.mcpb` connector detects this automatically and recovers without
manual intervention: it re-establishes its connection, replays the
MCP handshake, and retries any in-flight request. Clients that don't
use this connector still need a manual reconnect after a coordinator
restart.

**Open decisions:**

- Whether to allowlist `bash` directly, rather than relying on `make`
  as the structured entry point into a project's pipeline.
- No auto-generated starter `opencode.json` for new projects adopting
  [Directory ACLs](#directory-acls).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, running
tests, and building the Desktop extension.

## License

[MIT](LICENSE)

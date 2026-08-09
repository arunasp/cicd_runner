# cicd-runner

A project-agnostic CI/CD execution engine that runs as a persistent Docker
service, reachable over MCP (Model Context Protocol). It runs commands
against named projects or arbitrary directories, either directly or in
disposable ephemeral containers.

## Table of contents

- [Why a separate service](#why-a-separate-service)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Installation](#installation)
  - [Get the service running](#get-the-service-running)
  - [Full verification (deploy_cicd_runner.sh)](#full-verification-deploy_cicd_runnersh)
  - [Connect a client](#connect-a-client)
  - [Claude Desktop](#claude-desktop)
  - [opencode (project scope)](#opencode-project-scope)
- [Architecture](#architecture)
- [The Makefile as CI/CD manifest](#the-makefile-as-cicd-manifest)
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
curl http://localhost:1444/health
```

```json
{"status":"ok","docker_socket":true,"dynamic_root_configured":true,"cache_root_configured":false}
```

See [Installation](#installation) for the full walkthrough, including
connecting an actual MCP client.

## Installation

The service itself (coordinator + worker) has to actually be running
before any client can connect to it.

### Get the service running

For first-time setup or everyday use:

```bash
cp .env.example .env   # fill in real project paths (optional -- can stay empty)
make all                # build everything (runner + extension) + launch
```

`make all` builds both Docker images and starts the coordinator via
`start.sh` (see [Build script](#build-script)). Once it's done:

```bash
make status   # confirm the container is up
make logs     # follow the coordinator's own logs
curl http://localhost:1444/health
```

```json
{"status":"ok","docker_socket":true,"dynamic_root_configured":true,"cache_root_configured":false}
```

A real `GET /health` endpoint, outside the MCP protocol entirely —
run through a plain `curl`/uptime monitor without needing a real MCP
client. `docker_socket` confirms the coordinator can actually reach
`/var/run/docker.sock` (the one dependency that matters most, since
that access is this project's whole reason to exist — see [Why a
separate service](#why-a-separate-service)); `dynamic_root_configured`/
`cache_root_configured` reflect whether `DYNAMIC_ROOT_HOST`/
`CACHE_ROOT_HOST` are set (see [Configuration](#configuration),
[Dependency caching](#dependency-caching)).

Don't `curl` `/mcp` directly expecting the same shape — that's the
real MCP protocol endpoint, and a plain `curl` isn't a real MCP client
(it doesn't send the `Accept: text/event-stream` header the
streamable-HTTP transport requires), so it correctly returns a `406`
JSON-RPC error instead of a health-style response. That's expected
protocol enforcement, not something broken — `/health` above is the
right endpoint for a plain liveness check.

Day-to-day, `make start` / `make stop` / `make restart` cover
relaunching without a full rebuild; `make build` rebuilds the Docker
images first if the coordinator or worker source changed.

### Full verification (`deploy_cicd_runner.sh`)

`./deploy_cicd_runner.sh` is a different tool for a different job —
not a lighter alternative to `make all`, a heavier one. It runs the
entire Autotools chain (`autogen.sh`, `configure`, `make`,
`make check`, a staged `make install`/`make uninstall` round-trip,
`make dist`), a re-scrub check for accidentally-reintroduced personal
information (relevant to this repo's own maintainers, not to a fresh
clone), and a full stop/start lifecycle check — logging everything to
a timestamped file under `logs/` rather than the terminal. Reach for
it after changing the project itself and wanting confidence nothing
broke, not as the first thing to run on a fresh checkout.

It does rebuild and relaunch the coordinator as part of that lifecycle
check, so **any already-connected client needs to reconnect
afterward** — the Desktop extension does this automatically (see
[Status](#status)); other clients need a manual toggle/restart.

### Connect a client

With the service running, pick whichever client you use:

### Claude Desktop

1. Get the `.mcpb` package, either:
   - `make build-extension` (needs Node — builds
     `desktop-extension/dist/cicd-runner-<version>.mcpb`), or
   - download the latest one from this repo's
     [Releases](../../releases) — no Node needed.
2. Open Claude Desktop → **Settings → Extensions** → drag the
   `.mcpb` file in, or use the **Install Extension** file picker.
3. Claude Desktop shows the extension's one configurable option,
   **Additional Allowed Directories** — a directory picker
   (`manifest.json`'s own `user_config.allowed_directories`). This is
   optional: leave it empty if you'll only ever reach named/mounted
   projects and their own `opencode.json` `external_directory` rules
   (see [Directory ACLs](#directory-acls)). Add directories here for
   anything else `run_in_directory()` needs to reach.
4. Enable the extension. Ask Claude to call `list_projects()` to
   confirm the connection — it should return your named projects (or
   "No projects mounted" if none are configured yet, which is still a
   successful connection).

No further host-side setup: the extension talks to the coordinator
directly over `localhost:1444`, bridging Desktop's own stdio extension
model to the coordinator's streamable-HTTP endpoint in-process — see
[Status](#status) for what happens across a coordinator restart.

### opencode (project scope)

opencode reads MCP server config from `opencode.json` (or
`opencode.jsonc`) two places: `~/.config/opencode/opencode.json`
(global, every project) and `<project-root>/opencode.json`
(project-scoped, overrides/extends the global one for that project
only). Project scope is almost always what you want for cicd-runner —
it keeps the connector's reach tied to the one project you're actually
working in, not every opencode session on the machine.

1. In the project's own root (next to its `package.json`/`Cargo.toml`/
   etc., not `~/.config/`), create or edit `opencode.json`:

   ```json
   {
     "$schema": "https://opencode.ai/config.json",
     "mcp": {
       "cicd-runner": {
         "type": "remote",
         "url": "http://localhost:1444/mcp",
         "enabled": true
       }
     }
   }
   ```

   `examples/opencode.mcp-example.json` in this repo has the same
   block ready to copy.
2. Restart opencode (or start a new session) in that project
   directory so it picks up the file.
3. Run `/status` inside opencode, or ask it to call `list_projects()`
   directly, to confirm `cicd-runner` shows as connected.

opencode connects to the coordinator directly over HTTP — no bridge
process, unlike the Desktop extension. It's also the one client this
repo confirms genuinely supports the MCP roots protocol (see rule #1
in [Directory ACLs](#directory-acls)): its own project directory is
usually already reachable with no extra config, on top of whatever
`external_directory` rules a project's `opencode.json` declares.

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
`/var/run/docker.sock`. Exposes two MCP tools, plus a plain HTTP
`GET /health` endpoint outside the MCP protocol (see [Quick
start](#quick-start)):

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

## The Makefile as CI/CD manifest

cicd-runner has no pipeline-definition format of its own — no YAML,
no DSL, no config schema describing stages. A project's `Makefile`
*is* the pipeline. `run_command`/`run_in_directory` call `make lint`,
`make test`, `make build`, exactly as a human would at a terminal —
the manifest a CI system reads and the interface a developer runs
locally are the same file, not two representations kept in sync by
hand.

This isn't a new idea; it's a well-established pattern this project
deliberately follows rather than inventing something bespoke:

- **GNU Coding Standards** define `all`, `check`, `install`, and
  `clean` as the standard target names any GNU-compliant `Makefile`
  should provide — cicd-runner's own build (see [Standard build
  (Autotools)](#standard-build-autotools)) follows this directly, and
  the project-level `lint`/`test`/`build`/`deploy`/`verify`/`e2e`/`all`
  vocabulary extends the same idea to a fuller pipeline shape.
- **Kubernetes and most CNCF projects** drive their own CI through a
  root `Makefile` (`make test`, `make verify`, `make build`) that CI
  YAML calls as a single step, rather than encoding build logic
  directly in the CI config. The `Makefile` stays the actual source
  of truth and runs identically on a laptop and in CI.
- **GitHub Actions', GitLab CI's, and Jenkins'** own `container:`,
  `image:`, and per-stage agent-image mechanisms all solve the same
  problem cicd-runner's own `.cicd-image` file does (see [Per-project
  worker images](#per-project-worker-images)) — pick a toolchain image
  per job/stage rather than one shared image trying to hold every
  language at once.

The practical payoff: a project that already has a working
`lint`/`test`/`build` `Makefile` needs zero changes to work with
cicd-runner. One that doesn't gets one from `examples/project-skeleton/`
(stubbed, fails loudly until filled in) or an already-complete
reference from `examples/hello-bash/`, `hello-gcc/`, `hello-python/`,
or `hello-typescript/` — copy the closest match, replace the recipe
bodies with real commands, and the pipeline exists.

### Walkthrough: a project with no `Makefile` at all

Taking a plain Python project (`hello.py`, `test_hello.py`, no build
tooling yet) from nothing to a working pipeline:

1. Copy the skeleton in:
   ```bash
   cp examples/project-skeleton/Makefile /path/to/my-project/Makefile
   ```
2. Fill in the real commands — delete each `TODO`/`exit 1` stub and
   replace it with what you'd actually type at a terminal:
   ```makefile
   lint:
   	ruff check .

   test:
   	pytest

   build:
   	python3 -m py_compile hello.py
   ```
   Leave `deploy`/`verify` as-is (`exit 1`) until there's a real
   deploy target — `lint`/`test`/`build` alone are already a working
   pipeline; see `examples/hello-python/Makefile` for a complete
   reference including a real `deps` step (see [Dependency
   caching](#dependency-caching)).
3. If the project needs a dependency install step, add one and make
   `test`/`lint` depend on it (matching `examples/hello-python/`'s own
   `.deps` pattern) rather than assuming tools are already present.
4. Run it directly first, outside cicd-runner, to confirm the
   `Makefile` itself works: `make lint && make test && make build`.
5. Run it through cicd-runner — no code changes needed, the same
   `Makefile` is now the pipeline definition:
   ```
   run_in_directory(relative_path="my-project", binary="make", args=["lint"])
   run_in_directory(relative_path="my-project", binary="make", args=["test"])
   ```
   (`relative_path` is relative to `DYNAMIC_ROOT` — see
   [Usage](#usage). For a project that also needs
   `run_command()`'s docker-compose-build visibility, see [Adding a
   new named project](#adding-a-new-named-project) instead.)

That's the whole integration surface — nothing to register, no
separate CI config to write or keep in sync. The `Makefile` written
in step 2 is the same one a teammate runs locally and the same one
CI calls.

## Usage

Connect a client first — see [Installation](#installation) for Claude
Desktop and opencode. Once connected:

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

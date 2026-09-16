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
  - [Full verification (tools/deploy_cicd_runner.sh)](#full-verification-toolsdeploy_cicd_runnersh)
  - [Connect a client](#connect-a-client)
  - [Claude Desktop](#claude-desktop)
  - [opencode (project scope)](#opencode-project-scope)
- [Architecture](#architecture)
- [The Makefile as CI/CD manifest](#the-makefile-as-cicd-manifest)
- [Usage](#usage)
- [Controlling a project's containers](#controlling-a-projects-containers)
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
- [Changelog](CHANGELOG.md)
- [Skills](#skills)
- [Contributing](#contributing)
- [License](#license)

## Why a separate service

A project's own container can't safely rebuild itself: the moment
`docker compose up -d` recreates a running container, any in-flight
request that triggered the rebuild is dropped along with it.

`cicd-runner` avoids this by being a separate process from
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
{"status":"ok","docker_socket":true,"dynamic_root_configured":true,"cache_root_configured":true}
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
{"status":"ok","docker_socket":true,"dynamic_root_configured":true,"cache_root_configured":true}
```

A `GET /health` endpoint, outside the MCP protocol entirely —
run through a plain `curl`/uptime monitor without needing a real MCP
client. Returns HTTP `503` (not `200`) when `docker_socket` is false —
the one dependency that matters most, since that access is this
project's whole reason to exist (see [Why a separate
service](#why-a-separate-service)) — so an automated monitor checking
only the status code, the normal way liveness checks work, correctly
sees the service as down rather than a false-positive `200`.
`dynamic_root_configured`/`cache_root_configured` reflect whether
`DYNAMIC_ROOT_HOST`/`CACHE_ROOT_HOST` are set (see
[Configuration](#configuration), [Dependency
caching](#dependency-caching)) — these do NOT affect the status code,
since leaving either unset is a legitimate, intentionally-optional
configuration, not a failure.

Don't `curl` `/mcp` directly expecting the same shape — that's the
real MCP protocol endpoint, and a plain `curl` isn't a real MCP client
(it doesn't send the `Accept: text/event-stream` header the
streamable-HTTP transport requires), so it correctly returns a `406`
JSON-RPC error instead of a health-style response. That's expected
protocol enforcement, not something broken — `/health` above is the
right endpoint for a plain liveness check.

**Checking health from inside cicd-runner's own tools** (e.g. a
Makefile pipeline step, or an MCP client verifying itself) needs a
different approach entirely: `make health-check` (in this repo's own
root, already reachable via `run_command(project="cicd_runner",
binary="make", args=["health-check"])`, since this repo mounts itself
as a named project by default — see [Adding a new named
project](#adding-a-new-named-project)) checks the same underlying
conditions directly — docker socket existence, env vars — without an
HTTP round-trip. Don't `curl localhost:1444/health` from inside a
`run_command()`/`run_in_directory()` call to check this instead: that
is a self-deadlock, confirmed by running it — FastMCP
dispatches a synchronous `@mcp.tool()` function like `run_command()`
directly on the coordinator's single asyncio event loop, so its own
`subprocess.run()` blocks that same loop for its whole duration,
meaning a child process it spawns can never get a response from the
coordinator's own HTTP server. A plain `curl`/`python3` one-liner
tried this way hangs indefinitely and can wedge the coordinator until
it's manually restarted.

Day-to-day, `make start` / `make stop` / `make restart` cover
relaunching without a full rebuild; `make build` rebuilds the Docker
images first if the coordinator or worker source changed.
If an image builds but cannot start a container (for example
`missing parent` from the snapshotter), `make start` stops before
touching the running container; `make rebuild` builds both images
without cache and verifies them. When `compose rm -sf` fails on a
container the daemon lists, `make start` removes this project's
containers by ID (`make clean-containers`) before launching.

### Full verification (`tools/deploy_cicd_runner.sh`)

`./tools/deploy_cicd_runner.sh` is a different tool for a different job —
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
repo confirms supports the MCP roots protocol (see rule #1
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
`/var/run/docker.sock`. Exposes four MCP tools, plus a plain HTTP
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

**`server/allowlist.txt`** — the coordinator's own list, for
`run_command()`. **`server/allowlist-worker.txt`** — a separate,
wider list for `run_in_directory()`'s worker containers; see [Design
decisions](#design-decisions).

## The Makefile as CI/CD manifest

cicd-runner has no pipeline-definition format of its own — no YAML,
no DSL, no config schema describing stages. A project's `Makefile`
*is* the pipeline. `run_command`/`run_in_directory` call `make lint`,
`make test`, `make build`, exactly as a human would at a terminal —
the manifest a CI system reads and the interface a developer runs
locally are the same file, not two representations kept in sync by
hand.

This isn't a new idea; it's a well-established pattern this project
follows rather than inventing something bespoke:

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
   Leave `deploy`/`verify` as-is (`exit 1`) until there is a
   deploy target — `lint`/`test`/`build` alone are already a working
   pipeline; see `examples/hello-python/Makefile` for a complete
   reference including a `deps` step (see [Dependency
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

`make` is what's allowlisted for `run_command()` (the coordinator): it
runs a project's own version-controlled recipes, a structured and
auditable entry point, rather than letting a call hand `run_command`
an arbitrary shell string. `run_in_directory()`'s own worker allowlist
is wider — see [Design decisions](#design-decisions).

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

## Controlling a project's containers

`container_control(relative_path, action)` brings a project's own
`docker-compose` stack up, down or back with a rebuild. `relative_path` is
the directory **containing** the compose file — `some-repo/tools/server`,
not `some-repo` — resolved and ACL-checked exactly as `run_in_directory()`
is, so the same three allow-paths apply.

| Action | What it runs |
|---|---|
| `up` | `up -d` |
| `down` | `down` |
| `restart` | `restart` |
| `rebuild` | `build`, then `rm -sf`, then `up -d` |
| `status` | `ps` |
| `logs` | `logs --tail 200` |

The coordinator constructs each command in full. Nothing from the caller is
appended to it, and a failing step stops the sequence rather than
continuing — a failed `build` followed by a successful `up` would otherwise
report success while running the previous image.

`rebuild` is not `up --build`: recreating a container in place
after a BuildKit rebuild hits compose v1's `KeyError: ContainerConfig`
([docker/compose#11742](https://github.com/docker/compose/issues/11742)).
The v2 plugin is preferred and standalone v1 is the fallback, detected by
probing rather than assumed.

This is the one tool that runs in the **coordinator** rather than a worker,
because a worker has no docker socket and so cannot drive compose at all.
Two consequences follow, and both are deliberate:

- **It knows nothing about any project.** The compose file belongs to the
  project, its environment comes from that directory's own `.env`, and this
  tool neither inspects nor validates either. A coordinator that understood
  individual projects would stop being reusable across them.
- **The directory ACL is the entire trust boundary.** Neither binary
  allowlist applies here — there is no caller-supplied binary to gate. A
  compose file can mount anything, so what constrains this capability is
  *which directories are reachable*, which is decided coordinator-side and
  never from inside a project tree. Keep it that way.

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

Drop a `.cicd-image` file (one line, an image reference) in the
directory a call names to run its `run_in_directory()` calls in a
different image:

```
# .cicd-image
rust:1.97-bookworm
```

```
run_in_directory(relative_path="my-rust-project", binary="cargo", args=["test"])
```

Common choices (versions current as of August 2026 -- check each
language's own release page before pinning, since these move):

| Language | Suggested image |
|---|---|
| C / C++ | `gcc:16-bookworm` |
| Rust | `rust:1.97-bookworm` |
| Go | `golang:1.26-bookworm` |
| Java | `eclipse-temurin:25-jdk` |
| .NET | `mcr.microsoft.com/dotnet/sdk:10.0` |
| Ruby | `ruby:4.0-bookworm` |

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

### Building your own worker image

An upstream language image is enough when the only thing missing is a
toolchain. It is not enough when the run writes to the bind mount,
because the uid drop lives in `worker/entrypoint.sh`, baked into
`cicd-worker` itself. `WORKER_UID`/`WORKER_GID` are passed as plain
environment variables, so an image with no entrypoint reading them
ignores them, runs as its own default user — root, for most bases — and
leaves everything it writes root-owned on the host.

An image meant to be a worker therefore carries four things the default
one already has:

1. An `ENTRYPOINT` that reads `WORKER_UID`/`WORKER_GID`, creates a
   matching passwd entry, and drops privilege with `setpriv`. See
   `worker/entrypoint.sh`, and the `docker-run-as-host-user` skill for
   why a bare `docker run --user` fails instead.
2. `setpriv` (from `util-linux`) and the base's own user-creation
   tools — `addgroup`/`adduser` on Debian, `groupadd`/`useradd` from
   `shadow-utils` on a Red Hat base.
3. Re-injection of the dependency-cache variables after the drop.
   `setpriv --reset-env` clears the whole environment, so capture
   `NPM_CONFIG_CACHE`, `CARGO_HOME` and `PIP_CACHE_DIR` while still
   root and pass them through `env` inside the same `setpriv` call, or
   the cache mounts stay mounted with nothing looking at them.
4. `/etc/cicd-common.mk`, if the project's Makefile includes it.

Build it locally rather than pulling it. The coordinator holds the
docker socket and mounts the dynamic root read-only, so it can build
from any directory under it — the image never leaves the host, which
sidesteps the registry trade-off above:

```
run_command(project="<a mounted project>", binary="docker",
            args=["build", "-t", "my-worker", "/dynamic-root/<path>"])
```

Confirmed end to end, August 2026, with a Rocky 9 image built this way:
the worker reported `Rocky Linux 9.3` where the same repository without
a `.cicd-image` reported the default Debian, `id` inside it returned the
invoking host uid with a real passwd entry, and a file it wrote to the
bind mount came out owned by that user rather than by root.

One consequence of the single-directory mount is worth planning around
before writing such an image: `.cicd-image` is read from the directory
the call names, and a worker mounts only that directory. A per-stage
image in a subdirectory gets a container that cannot see the rest of the
repository, so a stage needing the whole tree either takes the image at
the repository root — which then applies to every call against it — or is
restructured to need only its own directory.

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
passwd/group entry with a writable `$HOME` if one doesn't already exist,
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
   confirmed to appear in a Claude Desktop directory allowlist —
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
(either — only that one of them exists; *which* one is not recorded, see
below), Python 3 able to create a virtualenv, and `node`/`npm`/`npx`
(optional — only needed for the Desktop extension).

What `configure` deliberately does **not** do is substitute either
answer into the generated `Makefile`. Both are facts about the installed
tool inventory of a *userland*, and one checkout is read by several —
two host boots and two container images here. A value frozen at
configure time is correct only in the userland that ran it: a `Makefile`
generated where only compose v1 existed made `make stop`/`logs`/`status`
fail with exit 127 everywhere that has the v2 plugin instead, including
the coordinator container running on the very same host. Machine and
distribution both look like usable keys for this and both fail — the
coordinator and its host are one machine of one distribution and still
disagree.

So the two facts are resolved where the work happens:

- `tools/compose.sh` picks `docker compose` or `docker-compose` at
  invocation and exits 127 with a real message if neither is present.
  `build.sh`, `start.sh` and the `stop`/`logs`/`status` targets all
  route through it, so there is one implementation rather than four.
- `tools/venv-build.sh` provisions the virtualenv `make check` runs in, keyed
  by both the userland (`/etc/os-release` plus architecture — an ABI
  claim, since compiled wheels link against that userland's libraries)
  and the identity of the base interpreter itself. One userland holds
  several interpreters, so the ABI half alone is not enough to tell them
  apart. It validates an existing venv against its own `pyvenv.cfg`
  rather than testing whether `bin/python3` is executable — the latter
  catches only a *dangling* interpreter, while a base that exists but is
  the wrong one leaves the venv looking fine and silently runs the suite
  in an environment nobody asked for. `make deps` invokes it as a stage
  of its own; `make check` depends on that stage.

`make install` stages a full copy under `$(DESTDIR)$(pkgdatadir)`
(default `/usr/local/share/cicd-runner`) without launching anything;
run `./start.sh` from there afterward.

Generated Autotools files (`configure`, `Makefile.in`, `aclocal.m4`)
aren't committed — `autogen.sh` regenerates them from `configure.ac`/
`Makefile.am` on a fresh checkout; a release tarball (`make dist`)
already includes them.

**Releases are automatic, not a manual step.** CI (`.github/workflows/
ci.yml`'s `tag-release` job) watches `configure.ac`'s own `AC_INIT`
version on every push to `main`: once the other jobs pass and that
version isn't already tagged, it tags `v<version>`, builds `make
dist`'s tarball and the Desktop `.mcpb`, and publishes both to a new
GitHub Release with auto-generated notes. Bumping the version is the
entire release process — edit `AC_INIT([cicd-runner], [x.y.z], ...)`
and push to `main`; nothing else to run by hand.

**Running `./autogen.sh`/`./configure` through cicd-runner itself,
not just a host shell:** `run_command()` (the coordinator) can't run
these — they're shell scripts, and `bash` is deliberately not on the
coordinator's own allowlist (see [Design decisions](#design-decisions)).
`run_in_directory()`'s worker allowlist includes `bash`/`autoconf`/
`automake` specifically so this repo's own regeneration chain can run
there instead, against this checkout under `DYNAMIC_ROOT`:

```
run_in_directory(relative_path="cicd_runner", binary="bash", args=["autogen.sh"])
run_in_directory(relative_path="cicd_runner", binary="bash", args=["-c", "./configure"])
```

A host shell is still the more direct path for day-to-day use;
this exists so the regeneration itself doesn't strictly require one.

## Build script

```bash
make build            # ./build.sh          -- runner images only
make rebuild          # --no-cache --pull build, then start one throwaway container per image
make image-check      # ./build.sh verify   -- start one throwaway container per image
make clean-containers # remove every container compose labels for this project, by ID
make build-extension  # ./desktop-extension/build.sh
make build-all        # both
make deps             # tools/venv-build.sh -- provision/heal the test virtualenv
make env-check        # tools/venv-check.sh -- is that virtualenv current? changes nothing
make modes-check      # every directly-executed script is 100755 in the git index
make start            # ./start.sh (builds runner, verifies images start, then launches)
make stop / restart / logs / status
make all              # build-all + start
make push             # git push origin main -- see below for where this can actually run
```

`make push` is a pipeline step, not documentation for a
command to remember — but it's the exact same `git push origin main`
either way, and doesn't grant this project's own containers any
credentials they didn't already have. The coordinator/worker
containers have zero GitHub push credentials by design (see [Design
decisions](#design-decisions)), confirmed repeatedly: `git add`/
`commit`/`amend` all work fine via `run_command()`/`run_in_directory()`
since they only touch the real, bind-mounted host checkout, but `push`
itself has needed a human's own credentials every single time so far.
Run `make push` from a host shell where this remote's credentials are
actually configured; running it via the MCP tools instead hits the
same auth failure `git push` always would from inside these
containers — that's the credential boundary working as designed, not
a bug in the target.

`build.sh` builds the worker and coordinator images and needs only
`docker` — compose is needed by the coordinator stage alone, and is
resolved there through `tools/compose.sh`.

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
- **Two separate allowlists, not one shared list.** `run_command()`
  (the coordinator, which holds `/var/run/docker.sock` — root-
  equivalent host access) enforces against `server/allowlist.txt`.
  `run_in_directory()` (the ephemeral, no-docker-CLI worker) enforces
  against a separate, wider `server/allowlist-worker.txt` — the two
  checks are independent in code (`bash_mcp_server.py`'s own two
  `FileAllowlist` instances), not just two files read into one set.
  A capability added for the worker (e.g. `bash`, for a project's own
  Autotools regeneration) does not carry over to the coordinator.
  Originally one shared list gated both tools; split 2026-08-09 once
  a worker-only need (`bash`) surfaced and would otherwise have
  had to be granted to the coordinator too, undermining the same
  least-privilege logic already applied to `docker` itself (the
  worker deliberately has none, see the point above).
- **No SSH keys or git credentials are mounted here.** Projects that
  need `git push` keep that capability in their own container, scoped
  to that one repo. Applies to this project's own repo too —
  `make push` (see [Build script](#build-script)) is a target,
  not a workaround around this boundary: it's the same bare
  `git push origin main`, and only succeeds where a human's own
  credentials for this remote are present.

## Status

The core service (coordinator + ephemeral worker) is implemented,
tested, and in use. Both the Desktop `.mcpb` connector and the
opencode remote-MCP config work against real client sessions.

Covered by committed tests (`server/test_bash_mcp_server.py`, 89 cases):
path resolution and traversal/symlink-escape defense, per-call config
resolution (`.cicd-image`, `CACHE_ROOT`, `HOST_UID`/`HOST_GID`), and
[Directory ACLs](#directory-acls) (MCP roots + `opencode.json`
`external_directory`), and the compose-binary detection behind
`container_control` — v2 plugin present, only v1 present, and neither,
each checked against a faked tool rather than needing every variant
installed.

Restarting or rebuilding the coordinator while a client is connected
leaves that session stale — the coordinator has no memory of the old
session ID, so calls get a `404` instead of a response. The Desktop
`.mcpb` connector recovers on its own: it re-establishes its
connection, replays the MCP handshake, and retries the in-flight
request. Clients that don't use this connector need a manual
reconnect after a coordinator restart.

That covers stale sessions, not a changed tool list. A client fixes
its view of the available tools during its own handshake with the
connector, and the connector's stdio side does not restart when it
reconnects upstream — so a newly added tool, or a changed signature,
needs the extension reloaded before the client sees it.

**Open decisions:**

- No auto-generated starter `opencode.json` for new projects adopting
  [Directory ACLs](#directory-acls).

## Skills

The `skills/` directory ships reusable instruction sets describing how to
work with this runner correctly. They exist because generic CI/CD knowledge
does not transfer cleanly to the mount model and privilege split here, so an
agent reasoning from ordinary CI assumptions reaches confidently wrong
conclusions.

Two are published: `docker-cicd-runner`, covering how to drive pipelines
through this runner and how to design one from scratch, and
`docker-run-as-host-user`, covering the uid:gid mechanics.

Each is published in two formats from a single source:

| Path | Form |
|---|---|
| `skills/opencode/<name>/` | Unpacked tree, readable directly in the repository |
| `skills/claude/<name>.skill` | Packaged bundle, installable into a Claude account |

`make skills-check` validates frontmatter, confirms every shipped reference
file is pointed at, and unpacks each bundle in memory to prove it is
byte-identical to the tree it was built from. Drift fails the build rather
than being caught by eye. It runs as part of `make check`, so the same
command covers local runs, workers and CI.

`AGENTS.md` and `CLAUDE.md` at the repository root point agents at these, so
the skills are discoverable by whichever convention a given tool follows.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, running
tests, and building the Desktop extension.

## License

[MIT](LICENSE)

---
name: docker-cicd-runner
description: How the cicd_runner container pair actually works and how to drive CI/CD through it -- coordinator vs ephemeral worker, the two allowlists, run_command vs run_in_directory, the single-directory mount, which container a stage belongs in (worker, .cicd-image, or the project's own), the Makefile target convention, and dependency caching. ALWAYS use this skill before running ANY pipeline stage through cicd-runner, before adding or changing a Makefile in a project cicd_runner executes, and before debugging why a stage that works locally fails inside a worker. Also use whenever the user mentions cicd_runner, cicd-runner, "the runner", worker allowlists or CI caching, asks why a binary or path is unavailable in a worker, or asks whether a container stage can run through the runner -- a device or capability never can, at any image. Generic DevOps CI/CD knowledge does NOT transfer directly -- the mount model and privilege split are unusual, and assuming a normal CI runner produces confidently wrong answers.
---

# Driving CI/CD through cicd_runner

Standard CI intuitions mostly hold at the level of *vocabulary* -- stages,
agents, caches, artifacts -- and mostly fail at the level of *mechanism*.
This skill is the translation layer. Read the mapping first, then the
constraint that causes most surprises.

## Translating the usual vocabulary

| Normal CI concept | What it is here |
|---|---|
| Runner / agent | Two containers: a long-lived **coordinator** and a per-call **ephemeral worker** |
| Agent image | `worker/Dockerfile` (the worker), separate from `server/Dockerfile` (the coordinator) |
| Pipeline definition | The **project's own Makefile**, not a YAML file the runner owns |
| Job step | One `run_command` / `run_in_directory` call, one entry binary |
| Workspace | A bind mount of exactly one project directory |
| Cache | Shared cache mounts (`PIP_CACHE_DIR` etc.) plus anything left on the bind mount |
| Artifact | A file written into the bind-mounted directory; it is simply there afterwards |
| Runner permissions | Two allowlists of permitted **entry binaries**, plus the worker's uid:gid |

The runner does not define stages. Projects do, through a Makefile using a
shared target vocabulary. Adding a capability means editing the project's
Makefile or the worker image -- never inventing ad-hoc command sequences at
call time.

## Where this sits in a full DevOps pipeline

The standard breakdown runs plan, code, build, test, release, deploy,
operate, monitor. Mapping it honestly matters, because the runner covers a
narrow slice and quietly implies the rest:

| Stage | Covered here? |
|---|---|
| Plan | No. Lives in the repo's own roadmap and design docs |
| Code | No. Sandbox plus a write-capable connector; the runner is not involved |
| Build | **Yes** -- `make build` in a worker |
| Test | **Yes** -- `make test`, `make verify` in a worker |
| Release | **No mechanism at all.** No tagging, versioning or changelog step is wired to the runner |
| Deploy | Partly. `make deploy` needs a Docker daemon, so it is coordinator-side or human-side, never a worker |
| Operate | Only a health-check target, where the project has one |
| Monitor | Absent |

**Do not claim a project has CI/CD because these targets exist.** They are a
build-and-test harness with a shared vocabulary. Saying so plainly is more
useful than implying coverage that is not there.

### The trigger gap

The defining property of continuous integration is that it fires on an
event -- a commit, a pull request, a merge. Nothing here does. Every stage
runs because a human or an agent invoked it. That makes this a **manually
triggered pipeline definition**, not continuous integration, however
faithfully the stage names match.

Two consequences worth stating rather than glossing:

- A green run says the pipeline passed *when someone chose to run it*, not
  that the current tree is green. Those diverge the moment anyone edits
  without re-running.
- Any claim of "continuous" anything requires a real trigger -- a git hook,
  a scheduler, or a hosted CI service watching the repository. The Makefile
  is genuinely reusable by such a trigger unchanged, which is the strongest
  argument for keeping the vocabulary standard even while it is invoked by
  hand.

Where a project also has hosted CI (a GitHub Actions workflow, say), that is
the event-driven half and this runner is the local half. They should invoke
the **same Makefile targets**, or they will drift and one will pass while the
other fails.

## The privilege split

**Coordinator** (`server/`) runs as **root** and holds the Docker socket. It
performs the allowlist check and launches workers. Its
`git config --global --add safe.directory '*'` exists precisely because root
is operating on mounted projects owned by another uid.

**Worker** (`worker/`) runs as the **host uid:gid**, via `docker run --user`
plus an `entrypoint.sh` that creates a matching passwd/group entry and drops
privileges with `setpriv --reset-env`. This is what stops it leaving
root-owned files on host bind mounts. It has **no Docker CLI at all**, by
explicit design.

Consequences that bite:

- Any stage needing a Docker daemon **cannot run in a worker**. It is not
  thereby human-only: the coordinator holds the socket, so see
  [Running a project's container stages](#running-a-projects-container-stages)
  before reporting such a stage as unrunnable.
- Anything writing outside the project tree (`make install` to `/usr/local`)
  **fails** under the worker's uid. Keep `deploy` out of `all`, or point
  `PREFIX` somewhere writable.
- Without `WORKER_UID`/`WORKER_GID` the worker falls back to root. That is a
  deliberate degrade-gracefully path, not a bug.

## Two allowlists, deliberately separate

`server/allowlist.txt` governs `run_command` (coordinator).
`server/allowlist-worker.txt` governs `run_in_directory` (worker). The worker
list is allowed to be **wider**, because the worker's privilege ceiling is
lower. A capability added to one does **not** carry to the other.

**Only the entry binary is checked.** `make` being allowlisted means anything
`make` invokes -- `gcc`, `ld`, `pip` -- runs unchecked as a child process. So
the practical question is never "is this allowlisted?" but "is my entry
binary allowlisted, and does this dependency get **provided**?"

And "provided" has a default answer that is not the image. See
[Where a dependency belongs](#where-a-dependency-belongs) below -- reaching
for an image rebuild first is the most common wrong turn here.

Changing either list requires an image rebuild.

## The single-directory mount, and everything downstream

**A worker mounts exactly one directory: the target. Never its parent.**

More surprises trace to this than to anything else:

- A sibling include (`-include ../common.mk`) can never resolve inside a
  worker. That is why shared fragments get baked into the image at a fixed
  path such as `/etc/cicd-common.mk`.
- A helper script must live *inside* the target directory to be runnable
  there. It cannot be referenced via `../`.
- At a **repo root**, a vendored copy and the image's baked copy are both
  visible at once, and including both makes `make` warn about a duplicate
  recipe. Guard it:

  ```make
  ifeq ($(wildcard /etc/cicd-common.mk),)
  -include cicd-common.mk
  else
  include /etc/cicd-common.mk
  endif
  ```

  A *subdirectory* is structurally immune, since its `../` sibling never
  resolves. Do not copy the guard where it cannot apply.

## Two filesystems, and which one reads your path

A path in a compose file or a `docker run` argv is resolved by one of two
processes, and they do not see the same filesystem when the client is
itself in a container.

| Path | Read by | Must be valid for |
|---|---|---|
| Build context | the docker **client** | the process running the command |
| Bind-mount source | the **daemon** | the host |
| `-f` compose file | the client | the process running the command |
| Image tag | the daemon's image store | neither -- it is a name, not a path |

The coordinator holds the socket but sees the project through its own
mount, so a build context under that mount works while a **relative** bind
source silently does not: the client resolves it against its own view and
hands the daemon a path that exists nowhere on the host.

Docker does not error on that. It **creates the missing source**, as a
root-owned empty directory -- and if the intended source was a file, the
container gets a directory where it expected one. The symptom is never a
path error; it is the service failing on missing content, plus a stray
tree at the host root.

The fix belongs to the **project**, because only the project knows its own
host path. Put every bind source behind a variable that defaults to `.`,
so a shell invocation is unchanged, and let the project's own `.env`
supply the absolute host path for callers that see the filesystem
differently:

```yaml
volumes:
  - ${PROJECT_ROOT:-.}/config/auth.json:/app/auth.json:ro
```

Derive that value from the location of the file that defines it -- in a
Makefile, `$(abspath $(lastword $(MAKEFILE_LIST)))` -- rather than from
the caller's working directory. Prefer lexical resolution (`abspath`) over
symlink resolution (`realpath`) when other tooling in the same project
builds the same paths without resolving symlinks: a value that disagrees
with them names the same file by a different string, which infrastructure
tools read as drift.

Once built, an image is referenced by **tag**, so every later operation --
`up`, `run`, `rebuild` -- needs no context and no host path at all. Only
the build step does.

## Scoping what `container_control up` starts

`up` runs `up -d` with no service argument, and nothing from the caller is
appended. That is deliberate: a coordinator that understood individual
projects would stop being reusable across them. So a bare `up` starts
every service the compose file defines by default, including one-shot
roles that then run immediately.

Scoping it is the **project's** job, through Compose profiles. A service
carrying a profile is not started by a bare `up -d`, while naming a
service explicitly enables its profile -- so `up -d <svc>`,
`run --rm <svc>` and `build <svc>` continue to work unchanged, and only
the unscoped invocation changes meaning. Profiles apply to `build` as
well, which keeps an orchestrated rebuild from building images nobody
asked for.

## The runner never acts on itself

The reason this service exists is that a container cannot safely rebuild
the container it is running in. That applies to the runner too: its own
`start.sh` removes and recreates the coordinator's stack, so invoking it
through `run_command` removes the container running the command before
the recreate is issued, leaving the service down with no channel to
recover it.

Restarting or rebuilding the runner is a host-shell action, always.

## Long builds and other long calls

The coordinator serves calls on a single event loop, so a multi-minute
build issued through it blocks every other call for its duration. Run
such work **detached** instead -- a container started with `-d`, holding
the socket and the project mount, doing the build outside the
coordinator's request path -- and poll for its result.

Two things to get right when you do:

- Capture the detached container's output into the project's own log
  directory before removing the container, or the record disappears with
  it.
- A pipeline driven that way runs as root, so anything it writes to the
  bind mount -- including its own log -- lands root-owned. Hand it back to
  the host uid in the same step.

## Choosing the tool

`run_command(project=...)` uses configured named mounts. If a project has no
mount configured, it is unreachable this way.

`run_in_directory(relative_path=...)` resolves relative to the runner's
parent directory, so a sibling project is `ProjectName/subdir`. Its
directory ACL accepts, in order: the client's live MCP roots (**inert on
Claude Desktop** -- do not rely on this), a project's `opencode.json`
external-directory rules, or an `X-Allowed-Directories` header. In Claude
Desktop that header is populated by the extension's **Additional Allowed
Directories** setting, which is the practical route.

## Running a project's container stages

A worker has no Docker, so a stage that builds or runs a container fails
there. That does not make it human-only. The coordinator holds the socket,
and there are two routes into it. Which one applies depends on how the
project starts its containers.

**A compose stack: `container_control(relative_path, action)`.** The path is
the directory *containing* the compose file, not the repo root, and it is
ACL-checked exactly as `run_in_directory` is. Actions are `up`, `down`,
`restart`, `rebuild`, `status`, `logs`. The coordinator builds each command
in full and appends nothing from the caller, so neither binary allowlist
applies: there is no caller-supplied binary to gate, and the directory ACL
is the entire trust boundary. `rebuild` is `build`, `rm -sf`, `up -d` rather
than `up --build`, which avoids compose v1's `KeyError: ContainerConfig` on
recreate.

**A Makefile that shells out to `docker`: `run_command(project=...)`.** This
runs in the coordinator, so a target invoking `docker build` or `docker run`
works there. `make` and `docker` are both on the coordinator's allowlist,
and only the entry binary is checked, so the `docker` calls a Makefile makes
as children run unchecked.

Reachability is the thing to establish first, and it differs from the other
tool. `run_command` accepts **named mounts only**, never an arbitrary path
under `DYNAMIC_ROOT`. A project reachable by `run_in_directory` is not
thereby reachable by `run_command`; asking for one that is not mounted
returns `REFUSED: '<name>' is not a mounted project directory`. Making it
reachable is a host-side change to the runner itself -- a var in `.env`, a
matching `${VAR}:/projects/<name>` volume in `docker-compose.yml`, then
`./start.sh`. That is someone's machine configuration, so ask rather than
assume it.

Verified against a live coordinator, August 2026: `make health-check`
reports `docker_socket: true`; `docker ps` through `run_command` lists the
host's real containers; `docker compose version` reports the v2 plugin.
Standalone `docker-compose` v1 is **not** in the coordinator image, so a
project target calling `docker-compose` fails there with `command not found`
while the same target's `docker compose` form works.

## When the project owns the container

Three container roles get conflated, and only the third can hold a device.

| Role | Defined by | Lifetime | Can hold a device or capability |
|---|---|---|---|
| Worker | the runner (`worker/Dockerfile`) | one call | No |
| Worker under `.cicd-image` | an image the project names | one call | No |
| The project's own container | the project (Dockerfile + compose) | as long as it is up | **Yes** |

`.cicd-image` swaps the image and nothing else. The `docker run` argv is
fixed in the coordinator, so no image choice adds `--device`, `--cap-add`,
`--network` or an extra `-v`. A stage needing any of those is not a worker
stage at any image, and no amount of building will make it one.

So the rule is about what the stage needs, not about convenience. A device, a
capability, a host path that must match the host exactly, or a service that
outlives one call: that belongs in a container the **project** defines and
owns. The runner then drives it through `container_control` rather than
supplying it.

A worked example from a real project alongside this one: its `tools/server/`
holds a `Dockerfile`, `docker-compose.yml`, `entrypoint.sh` and `start.sh`.
The image carries the project's own build dependencies, but its GPU runtime
is **not installed** -- the host's `/opt/rocm` and `/usr/lib/wsl` are
bind-mounted read-only, so the container's version matches the host's by
construction and the image avoids a multi-gigabyte layer. The GPU device node
is mounted there, and its compose file states plainly that this is the only
container in that project with device access, because the runner's workers
deliberately have none: GPU work belongs in the project container and CI work
belongs in the runner.

Three things that bite when writing such a container:

- **The uid variable names differ between the two worlds.** The runner's
  worker entrypoint reads `WORKER_UID`/`WORKER_GID`. A project container
  following the `docker-run-as-host-user` skill reads `TARGET_UID`/
  `TARGET_GID`. Neither is wrong; an image meant to serve both must read
  both, and one that reads the wrong pair silently falls through to root and
  writes root-owned files onto the host tree with no error.
- **`setpriv --reset-env` clears the whole environment**, and the list to
  re-inject afterwards is per-container, not universal. The runner's worker
  re-injects the three dependency-cache variables; the project container
  above re-injects `PATH` and `LD_LIBRARY_PATH`, without which its mounted
  toolchain was present but unreachable.
- **Do not drive a project's compose file directly.** Go through the
  project's own start script where it has one: it resolves the variables the
  compose file expects and does `rm -sf` before `up -d`, which is what avoids
  compose v1's recreate bug.

One limit worth stating before designing around it. `container_control`'s
verbs are lifecycle -- `up`, `down`, `restart`, `rebuild`, `status`, `logs`.
None of them returns a test verdict. A long-lived service fits that shape; a
one-shot stage that must report pass or fail does not, and parsing `logs` for
a success line is weaker than the exit code the stage already produces. Such
a stage is invoked through `run_command` on a named mount instead, where the
project's own `docker run` keeps its flags and the exit status comes back.

## Building an image a worker can use

An upstream language image is enough when the only thing missing is a
toolchain. It is not enough when the run writes to the bind mount. The uid
drop lives in the runner's own `worker/entrypoint.sh`, `WORKER_UID` and
`WORKER_GID` arrive as plain environment variables, and an image with no
entrypoint reading them ignores them, runs as root, and leaves everything it
writes root-owned on the host. Nothing errors.

So a usable image carries four things the default one already has: an
`ENTRYPOINT` reading that uid pair and dropping privilege with `setpriv`;
`util-linux` plus the base's own user-creation tools (`addgroup`/`adduser`
on Debian, `groupadd`/`useradd` from `shadow-utils` on Red Hat); re-injection
of `NPM_CONFIG_CACHE`, `CARGO_HOME` and `PIP_CACHE_DIR` after
`--reset-env` clears them; and `/etc/cicd-common.mk` if the Makefile
includes it.

Build it locally rather than naming a registry image. The coordinator holds
the socket and mounts the dynamic root read-only, so it builds from any
directory under it and the image never leaves the host:

```
run_command(project="<a mounted project>", binary="docker",
            args=["build", "-t", "my-worker", "/dynamic-root/<path>"])
run_in_directory(relative_path="<path>", binary="make", args=["<target>"])
```

Prove it rather than assume it, and the control matters as much as the run:
call the same repository from a directory **without** a `.cicd-image` and
confirm it reports the default image. Confirmed that way, August 2026 -- a
Rocky 9 image against Debian 13 for the same repository, `id` returning the
host uid with a real passwd entry, and a file written to the bind mount owned
by that user.

## Where a dependency belongs

When something is missing inside a run, resolve it in this order. Only the
last step touches the image.

**1. Is it declared in the pipeline's dependency manifest?** A package from a
language ecosystem -- pip, npm, cargo, gem -- belongs in `requirements.txt`
or its equivalent, installed by the pipeline into a project-local, cached
environment. That is the answer for the large majority of missing tools.

**2. Is the install landing somewhere that survives?** Declared but
reinstalled every call means it is going somewhere ephemeral. It needs to
land on the bind-mounted project directory (a `.venv` or `node_modules`
beside the source), not inside the container.

**3. Does the project need a whole toolchain the shared image should not
carry?** Pin a per-project worker image with a `.cicd-image` file in the
project's directory. This is the right answer for anything heavy or needed by
one project rather than all of them -- a Rust project builds against a Rust
image while everything else keeps the default. It also keeps the coupling
visible and local rather than making it an invisible property of shared
infrastructure.

**4. Only then: the shared image.** The test is whether the pipeline could
install it *as the unprivileged user, into the project tree*. If it needs root
or a system package manager -- a compiler, headers, native libraries, the
language runtime itself -- and **every** project needs it, it belongs in the
shared image. Otherwise putting it there is a mistake: it is a rebuild, it is
shared across every project using that image, and it hides the dependency from
the manifest where a reader would look for it.

The rule in one line: **declare and cache what the pipeline can install; pin
a per-project image for a toolchain only one project needs; bake into the
shared image only what everything needs.**

This is language-independent. See `references/ecosystems.md` for what the
manifest, the cached location and "offline" mean in Python, Node/TypeScript,
Rust, C/C++ and shell, and for which of those the default worker can actually
run.

A useful consequence: a project's dependency list stays readable in its own
repository rather than being split between a manifest and someone else's
Dockerfile. Anything only obtainable from the image is a coupling worth
naming explicitly, because it makes the project non-portable to any other
runner.

## The Makefile convention

Standard targets: `lint test build deploy verify e2e all`, each
self-documenting with a trailing `## comment`, plus a shared `help` target
from `cicd-common.mk` that greps those comments. Never hand-maintain a help
block -- it drifts.

`e2e` is commonly an alias for `verify`. Say so in a comment rather than
inventing a distinct stage that does not exist.

## Dependency caching against an ephemeral container

The container is discarded after every call, so *where* dependencies land
decides whether they survive.

- **Do not** install into system site-packages. The worker's uid cannot
  write there, and Debian-family Pythons refuse under PEP 668 regardless.
- **Do not** use `pip install --user` either: `$HOME` is inside the
  container and dies with it, so every call reinstalls.
- **Do** create a project-local `.venv`. It sits on the bind mount and
  therefore persists between calls.
- Gate it behind a **sentinel file** with the requirements file as its
  prerequisite, and deliberately keep that sentinel out of `.PHONY` -- a
  `.PHONY` listing forces a reinstall on every invocation.

  ```make
  .deps: requirements.txt
  	@test -x "$(VENV)/bin/python3" || $(PYTHON3) -m venv $(VENV)
  	$(VENV)/bin/python3 -m pip install -q $(PIP_OFFLINE) -r requirements.txt
  	@touch .deps
  ```

- For a fully offline install, resolve a **wheelhouse** once and point pip at
  it, falling back to the network when it is absent so a plain checkout still
  works:

  ```make
  PIP_OFFLINE = $(if $(wildcard $(WHEELHOUSE)/*.whl),--no-index --find-links $(WHEELHOUSE),)
  ```

Three layers, each covering what the one below cannot: shared cache mounts
avoid re-downloading, the bind-mounted `.venv` avoids reinstalling, the
wheelhouse avoids the network entirely.

## Moving files in

The Filesystem connector writes **UTF-8 only**, so binary cannot be pushed
through it (it can be *read* back as base64, so the asymmetry is real). To
move a tree in, pack it as base64 text and unpack it on the far side.

The worker has no `tar`, `base64` or `gzip` as entry binaries, but `python3`
is allowlisted and its stdlib covers all three. Because a worker mounts only
the target directory, the unpack script must be written *beside* the payload.

Always checksum. A corrupted-yet-well-formed base64 blob decodes into
plausible garbage and fails silently much later; verifying a digest before
extraction turns that into an immediate, loud failure.

## Working order

1. **Sandbox first.** Develop, lint and test in the Claude sandbox. It is
   faster and costs no remote calls.
2. **Then run live**, batched into as few calls as possible.
3. **Expect the live run to find things the sandbox cannot.** The
   duplicate-include warning above only appears where both copies coexist,
   which is a condition the sandbox does not reproduce. A green sandbox is
   not evidence about the worker.
4. **Read the exit code and stderr, not just stdout.** Warnings that do not
   fail the build still indicate real misconfiguration.

If the runner's repository is public, clone it in the sandbox and grep there
rather than making connector round-trips. A clone reflects *pushed* state
only, so confirm `git status` is clean and up to date before treating it as
authoritative; when it is not, the connector is the only source for what is
actually on disk.

## Reference files

Read the one that matches the question. Each is self-contained.

- **`references/runbook.md`** -- the standard operating procedure. Read this
  **before running anything**: the five pre-flight facts to establish, the
  execution order, batching rules, the required shape of a run report, and
  the language rules for what counts as "verified". Following it is what
  makes two different readings of this skill produce the same actions and
  the same report.
- **`references/templates.md`** -- copy-paste Makefiles, the shared help
  fragment, a pre-push hook, a hosted CI workflow, and gitignore entries.
  Read when creating or restructuring a project's pipeline definition.
  Using them unchanged is the point.
- **`references/workflow-design.md`** -- a seven-level progression from
  ad-hoc commands to full integration, how to choose stage boundaries, the
  design rules that hold regardless of tooling, and named failure patterns.
  Read when a project has **no** automation yet, or when the question is
  what to add next rather than how to invoke it.
- **`references/ecosystems.md`** -- the dependency rule expressed per
  language: manifest, cached install target, and offline mode for Python,
  Node/TypeScript, Rust, C/C++ and shell, plus which ecosystems the default
  worker supports and how `.cicd-image` covers the rest. Read whenever the
  project is not Python, or when a toolchain seems to be missing.
- **`references/troubleshooting.md`** -- symptom-to-cause tables. Read when
  something fails, before changing anything: most of these look like a
  broken pipeline and are really an environment assumption.

Two claims from those files are worth carrying even if you read none of
them:

**Do not climb a maturity level until the one below is boringly reliable.**
Automation added too early gets routed around, then costs time while
providing false assurance.

**A stage that cannot fail is decoration.** If you cannot describe an input
that turns it red, delete it or give it a real assertion.

## Related skills

- `bundle-cicd-pipeline` -- verifying an `apply-*.sh`-style delivery script
  against clean, dirty and conflicting repo states. Different problem: that
  one is about a script you hand the user, this one is about executing
  through the runner.
- `sandbox-staging-pipeline` -- the general develop-in-sandbox-then-stage
  discipline that step 1 above is an instance of.
- `dependency-mock-verification` -- verifying which-tool-is-present branching
  without installing every variant.

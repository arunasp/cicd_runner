---
name: docker-cicd-runner
description: How the cicd_runner container pair actually works and how to drive real CI/CD workflows through it -- coordinator vs ephemeral worker, the two separate allowlists, run_command vs run_in_directory, the single-directory mount and what follows from it, the Makefile target convention, and dependency caching that survives an ephemeral container. ALWAYS use this skill before running ANY pipeline stage through cicd-runner, before adding or changing a Makefile in a project cicd_runner executes, and before debugging why a stage that works locally fails inside a worker. Also use whenever the user mentions cicd_runner, cicd-runner, "the runner", worker allowlists, wheelhouse or venv caching for CI, or asks why a binary, path, include or install is unavailable inside a worker. Generic DevOps CI/CD knowledge does NOT transfer directly -- the mount model and privilege split are unusual, and assuming a normal CI runner produces confidently wrong answers.
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

- Any stage needing a Docker daemon **cannot run in a worker**. A `deploy`
  target that starts containers is coordinator-side or human-side.
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

# Changelog

Notable changes to cicd_runner. Format follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/); versions come from
`AC_INIT` in `configure.ac` and are tagged by CI on push to `main`.

## [Unreleased]

### Added

- `make build-examples` / `build.sh examples`: builds each
  `examples/*/Dockerfile` as `cicd-example-NAME` with the host uid, then
  starts it once.
- `WORKER_PRESERVE_ENV`: variables an image names are kept across the
  entrypoint's privilege drop.
- `tools/autotools.sh`: the Makefile's regeneration rules run `aclocal`,
  `autoconf`, `automake` and `autoheader` through it, and it runs
  `autoreconf --install --force` when `aclocal.m4` comes from a different
  Automake release than the installed one.
- `build.sh verify` stage: starts one throwaway container per image with
  `--entrypoint true --network none`. Not part of the default stage list.
- `BUILD_FLAGS` environment variable, passed to both build stages.
- `make rebuild` (`--no-cache --pull`, then `verify`) and `make image-check`.
- `tools/clean-containers.sh` and `make clean-containers`: remove every
  container labelled for this compose project, by ID.
- `container_control(relative_path, action)` — brings a project's own
  compose stack up, down or back with a rebuild. Takes the directory
  containing the compose file and one of six action names; the coordinator
  builds each command in full, so nothing from the caller is appended.
  Runs in the coordinator, since a worker has no docker socket and cannot
  drive compose at all. It knows nothing about any particular project: the
  compose file and its `.env` belong to the project, and neither is
  inspected. The directory ACL is the whole trust boundary here — no binary
  allowlist applies, because there is no caller-supplied binary to gate.
- `pytest.ini` making any warning fail the suite, with one upstream
  exception ignored by class. Runs previously reported `85 passed, 1
  warning` every time, which left a new warning nowhere to show up.
- `tools/venv-check.sh` and `make env-check` — the decision about whether
  the test environment is current is its own tool, expressed as an exit
  status: 0 current, 1 stale, 2 no usable base interpreter, 3 a
  requirements file named on the command line is missing. It creates
  and modifies nothing, prints the virtualenv path it is talking about
  on stdout, and `tools/venv-build.sh` does no deciding of its own — it acts
  on that status and re-asks after building rather than assuming the
  build worked. Every bug in this logic's history was in the decision
  rather than in the building, and a decision reachable only by
  building something is a decision that is hard to test.
- Requirements files reachable through pip's `-r` and `-c` directives
  are DISCOVERED transitively and hashed too, rather than trusting the
  list someone wrote on the `make deps` command line — gcc's `-MMD`
  idea, where the dependency list comes from what was actually read.
  Factoring requirements into a shared base file would otherwise put a
  real input outside the checked set. A discovered file that goes
  missing counts as a change and rebuilds, following gcc's `-MP`; only
  a file named on the command line is an error.
- The base interpreter's binary is content-hashed into the signature,
  which is ccache's `compiler_check`: the same version string can name
  a different binary after a rebuild or a security update, and a venv's
  compiled extensions are linked against that binary's ABI.
- The environment is also verified against a MANIFEST of what the build
  produced — the installed distributions, canonicalised per PEP 503 —
  so a package installed or removed by hand is detected and rebuilt.
  That is `rpm -V` rather than anything in make or gcc, and it is
  deliberately a second recorded file rather than part of the
  signature: the signature is what the environment was built FROM, and
  loosely pinned requirements legitimately resolve to something new at
  install time, so only a recorded-versus-now comparison means
  anything. Taken with `importlib.metadata` rather than `pip freeze`,
  which would pay pip's startup on every check and emit `-e` and
  `file://` forms that compare poorly.
- `tools/shellcheck.sh` and `requirements-dev.txt` — `make deps` installs
  `shellcheck-py` (the upstream static binary, as a wheel) into the same
  per-userland virtualenv, so a userland without shellcheck on PATH gets
  one cached locally rather than skipping the lint step. pip's pinning
  and hashes cover the download instead of a bespoke fetch-and-verify.
- `make modes-check` — proves every script the project executes directly
  is `100755` in the git index, not merely in someone's working tree.
  `check` depends on it. An explicit list rather than a glob:
  `worker/entrypoint.sh` is `100644` on purpose and the `examples/`
  scripts run through make. Losing the bit is silent — a connector or
  editor rewriting a file in place can drop it, git records an ordinary
  modification, and the script keeps working for anyone who still has it
  executable locally.
- `make deps` — provisions (and heals) the virtualenv `make check` runs
  in, via `tools/venv-build.sh`. A stage of its own rather than a fragment
  inside `check`, so a failure to build the environment reports as that
  and not as a test failure. `check` depends on it.
- `tools/` — the scripts nothing invokes directly: `compose.sh`,
  `pyenv.sh`, `debug_worker.sh` and the `deploy_*` pair. `autogen.sh`,
  `build.sh` and `start.sh` stay at the root as the documented entry
  points.

### Removed

- `server/check_requirements.py`. Its only caller was `configure.ac`,
  which no longer asserts a package inventory at configure time;
  dependencies are installed by `make deps` instead. Nothing else
  referenced it and nothing tested it.

### Fixed

- `tools/venv-build.sh` treats the virtualenv as disposable and rebuilds it
  whenever `tools/venv-check.sh` reports it stale, the way
  `config.status` records configure's answers rather than anyone
  diffing individual results. The signature covers the base
  interpreter's resolved path, version and prefix, the userland's ID,
  version and architecture, the C library version, and the content of
  every requirements file. Previous versions asked one question per
  failure mode, so each new way to go stale arrived as a new bug — a
  missing base interpreter, a base that exists but is wrong, and a
  `pyvenv.cfg` `home` recording the path the interpreter was invoked
  through rather than the resolved one, which rebuilt on every call.
  Requirements are hashed by CONTENT, not compared by timestamp as make
  would: this checkout is read from more than one boot and lives under
  git, where a clone or a branch switch rewrites mtimes without
  changing a byte.
- The shellcheck step in `make check` is no longer optional. It tested
  `command -v shellcheck` and printed "skipping (not required)" when it
  was absent, so whether the scripts were linted depended on which
  userland ran the suite — it had been skipping on one of this
  checkout's two boots and passing on the other.
- `configure.ac` no longer pins `aclocal-1.16`/`automake-1.16` by name.
  The generated files are gitignored, so each userland regenerates its
  own, and the pin matched none of them: 1.17 in the worker image,
  1.18.1 on the host. Make-triggered regeneration died with
  `automake-1.16: not found`.
- `tools/venv-check.sh` decides whether a venv is still valid from its
  signature (see above), replacing both the `pyvenv.cfg` comparison and
  the per-requirements-file sentinels. Dropping a requirements file now
  rebuilds rather than leaving its packages installed forever, which a
  sentinel that is never consulted again could not notice.
- `start.sh` and `build.sh` resolve their own location with `pwd -P`
  instead of a logical `pwd`. `DYNAMIC_ROOT` is derived from that and
  handed to Docker as a bind-mount source, so launching through a
  symlinked path mounted the symlinks themselves rather than their
  targets — every entry under `/dynamic-root` dangled inside the
  coordinator and every `run_in_directory()` call was refused by the
  dynamic-root check, while `cicd_runner` kept working because it has
  its own named mount.

### Changed

- `examples/hello-rust` runs in a locally built worker image
  (`cicd-example-hello-rust`) instead of `rust:1.82-bookworm`, so its
  output is owned by the host user.
- `build.sh` builds the worker image with `WORKER_UID`/`WORKER_GID` set to
  the host user: `HOST_UID`/`HOST_GID`, then `SUDO_UID`/`SUDO_GID`, then
  `id -u`/`id -g`. The worker Dockerfile creates that group and user only
  when absent. `worker/entrypoint.sh` also accepts `TARGET_UID`/`TARGET_GID`.
- `configure` warns instead of failing when `docker` or compose is absent,
  so a worker can configure and run `make check`. `build.sh` and
  `tools/compose.sh` name the coordinator or the host when docker is
  missing at invocation.
- `autogen.sh` runs `autoreconf --install --force`.
- `start.sh` runs `verify` after building and exits before `compose rm`
  when an image cannot start.
- `start.sh` falls back to `tools/clean-containers.sh` when
  `compose rm -sf` fails, and exits before launching if containers remain.
- `make clean` no longer descends into `.cicd-runner-cache/`, `.venv/` or
  `.git/`.
- The venv tools are named `tools/venv-check.sh` and `tools/venv-build.sh`.
  They were briefly `envcheck.sh` and `pyenv.sh`; the second collides
  with `pyenv`, a widely used and entirely different tool, and these
  files are meant to be COPIED INTO other projects, where that would
  mislead. The stamp files renamed with them (`.venv-stamp`,
  `.venv-manifest`), which costs one rebuild on first run after
  upgrading.
- The virtualenv cache defaults to `<project>/.venv-cache` instead of
  naming this project's own cache directory. A default carrying one
  project's name would arrive in every copy and be wrong in all but
  one; `cicd_runner` passes `VENV_ROOT` from its own `Makefile`, so its
  cache location is unchanged.
- Compose and the test interpreter are resolved at invocation instead of
  substituted by `./configure`. Both are facts about a *userland's*
  installed tools, and one checkout is read by several; a value frozen
  at configure time is correct only where configure ran. A `Makefile`
  generated where only compose v1 existed made `stop`/`logs`/`status`
  fail with exit 127 anywhere with the v2 plugin, including the
  coordinator container on the same host, and a `PYTHON3` baked to a
  `.venv` failed the same way wherever that venv's base interpreter was
  absent. `configure` still fails fast when neither compose nor a
  venv-capable Python 3 is present; it no longer records which.
- `tools/venv-check.sh` keys the virtualenv by userland *and* base
  interpreter, and validates an existing one against its own
  `pyvenv.cfg` rather than by testing whether `bin/python3` is
  executable — that test sees only a dangling interpreter, not a base
  that exists but is the wrong one.
- The re-scrub step in `tools/deploy_cicd_runner.sh` uses `git grep`,
  matching what its own section header always claimed. The previous
  working-tree `grep -rn` needed a hand-maintained exclude list and
  matched thousands of files inside virtualenvs and caches.
- CI no longer pip-installs `server/requirements.txt` before `make
  check` — `make deps` provisions the environment the suite actually
  runs in, and an install outside it would land in a different
  interpreter. The release job gained `setup-python` for the same
  reason the build job has it: `configure` now proves the virtualenv
  capability by building one, so that job needs a venv-capable
  interpreter even though `make dist` runs no Python of its own.
- `configure`'s virtualenv check creates a throwaway venv instead of
  importing `ensurepip` and `venv`. Those imports are a proxy that can
  succeed while `python3 -m venv` still fails, which would move the
  failure to `make check` while reporting success at configure time.
- `rebuild` runs `build`, then `rm -sf`, then `up -d`, rather than
  `up --build`. Recreating a container in place after a BuildKit rebuild
  hits compose v1's `KeyError: ContainerConfig`. A failing step stops the
  sequence, so a failed build cannot be followed by a successful `up`
  reporting success on the previous image.

## [1.1.0] — 2026-08-09

### Added

- `skills/` — two skills in both packaged and browsable form, with
  `validate.py` unzipping each bundle in memory and comparing it byte for
  byte against its tree, so the two formats cannot drift apart unnoticed.
  Wired into `check-local`, so `make check` and CI cover it without a
  separate job.
- `AGENTS.md` and `CLAUDE.md`, so the skills are discoverable under either
  convention.
- `make health-check`, which verifies the same conditions as the HTTP
  endpoint with no round trip. Calling `/health` from inside a tool call
  cannot work: the tools are synchronous functions on the coordinator's
  single event loop, so a subprocess calling back into that server waits
  for a reply the loop cannot send.
- A CI step that fails when `AC_INIT`'s version is not newer than the
  latest remote tag.

### Changed

- Two allowlists instead of one. `server/allowlist.txt` governs
  `run_command()` in the coordinator, which holds the docker socket, and
  stays narrow; `server/allowlist-worker.txt` governs `run_in_directory()`
  in the ephemeral worker and is wider. A single list meant anything added
  for a worker also reached the container with host-level access.
- The worker runs as the invoking host user, so files it writes to a bind
  mount are owned by that user. Five separate faults sat behind this, each
  found by retesting the original symptom: a missing passwd entry, Docker's
  low default `nproc` ulimit, cache mounts landing under `/root`, `setpriv`
  clearing the environment those mounts needed, and host-side cache
  directories left root-owned.
- README rewritten in standard project-documentation voice.

### Fixed

- Autotools baked absolute host paths into the generated Makefile at
  `configure` time, so the build broke inside a container at a different
  path. `configure.ac` now pre-sets the six affected variables to relative
  paths before `AM_INIT_AUTOMAKE`.
- Removed hardcoded external-project mounts and a personal username from
  test fixtures, making the repo self-contained.

## [1.0.0] — 2026-08-07

Initial release: a coordinator holding the docker socket, an ephemeral
worker per call, two mounting mechanisms (named projects and a dynamic
root), directory ACLs, a Desktop `.mcpb` connector, an opencode remote-MCP
config, and the Autotools build.

# Changelog

Notable changes to cicd_runner. Format follows [Keep a
Changelog](https://keepachangelog.com/en/1.1.0/); versions come from
`AC_INIT` in `configure.ac` and are tagged by CI on push to `main`.

## [Unreleased]

### Added

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

### Changed

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

# Contributing

## Development setup

```
./autogen.sh
./configure
make
make check
```

`make check` provisions its own Python environment: `make deps` (which it
depends on) builds a virtualenv under `.cicd-runner-cache/`, keyed by both
the userland and the base interpreter, and rebuilds it if that interpreter
changes or stops working. Nothing needs creating by hand, and nothing is
installed system-wide. Point `PYTHON3` at a different interpreter to base
it on that one instead — it gets its own virtualenv rather than reusing
another's.

## Running tests

`make check` runs the full pytest suite (`server/test_bash_mcp_server.py`) and,
if `shellcheck` is on `PATH`, lints the project's shell scripts too.

## Building the Desktop extension

```
make build-extension
```

Produces a `.mcpb` bundle under `desktop-extension/dist/`, installable directly
in Claude Desktop's Extensions settings.

## Directory ACLs

Changes to `run_in_directory()`'s access model (`_is_path_allowed()` in
`server/bash_mcp_server.py`) should keep all three allow-paths documented in
the README in sync, and add corresponding test cases to
`server/test_bash_mcp_server.py`.

## Pull requests

- Keep `make check` passing.
- Update `README.md` if the change affects usage, configuration, or the
  Directory ACLs model.
- Squash fixups before requesting review; keep commit messages focused on
  what changed and why.

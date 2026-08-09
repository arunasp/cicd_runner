# Contributing

## Development setup

```
./autogen.sh
./configure
make
make check
```

`./configure` prefers a local `.venv` when present (for `pytest`/`mcp`), falling
back to the system `python3` otherwise. Create one with `python3 -m venv .venv
&& .venv/bin/pip install -r server/requirements.txt` if you'd rather not
install dependencies system-wide.

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

# Canonical templates

Copy-paste starting points. Using these unchanged is the point: every
project ends up the same shape, so a reader who knows one knows all of them.
Adapt the contents of a recipe freely; do not rename targets or invent new
ones without a reason you can state.

## Contents

- [Shared help fragment](#shared-help-fragment)
- [Subproject Makefile](#subproject-makefile)
- [Repository-root Makefile](#repository-root-makefile)
- [Dependency manifest and wheelhouse](#dependency-manifest-and-wheelhouse)
- [Pre-push hook](#pre-push-hook-level-4-cheapest-form)
- [Hosted CI workflow](#hosted-ci-workflow-level-4-full-form)
- [gitignore entries](#gitignore-entries)

Every recipe line below begins with a **TAB**, not spaces. This is the most
common transcription error when copying a Makefile out of prose.

## Shared help fragment

`cicd-common.mk`, vendored at the repo root and also baked into runner
images at `/etc/cicd-common.mk`:

```make
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {{FS = ":.*?## "}}; {{printf "  %-12s %s\n", $$1, $$2}}'
```

Never hand-maintain a help block. A hand-written one drifts from the real
target list and then actively misleads.

## Subproject Makefile

For a self-contained component in a subdirectory. A runner mounts this
directory alone, so `../` never resolves inside one -- which is why both
include paths appear and why no guard is needed here.

```make
-include ../cicd-common.mk
-include /etc/cicd-common.mk

PYTHON3 ?= python3
VENV    ?= .venv
PY       = $(VENV)/bin/python3
WHEELHOUSE ?= ../cicd/wheels
PIP_OFFLINE = $(if $(wildcard $(WHEELHOUSE)/*.whl),--no-index --find-links $(WHEELHOUSE),)

.PHONY: lint test build deploy verify e2e all clean

# Sentinel, deliberately NOT in .PHONY: a .PHONY listing would force the
# install to re-run on every invocation regardless of whether the manifest
# changed.
.deps: requirements.txt ## Create .venv and install dev dependencies
	@test -x "$(PY)" || $(PYTHON3) -m venv $(VENV)
	$(PY) -m pip install -q $(PIP_OFFLINE) -r requirements.txt
	@touch .deps

lint: .deps ## Static checks
	$(PY) -m pycodestyle --max-line-length=79 .

build: ## Compile artifacts
	@mkdir -p build
	# ... real build commands ...

test: .deps build ## Unit and behavioural suites
	$(PY) -m unittest discover -s tests -p 'test_*.py'

deploy: build ## Install to PREFIX (needs a writable prefix)
	install -d $(DESTDIR)$(PREFIX)/lib
	# ... real install commands ...

verify: .deps build ## Smoke-test the built artifact itself
	$(PY) tests/smoke.py

e2e: verify ## Alias for verify

# deploy is deliberately excluded: it writes outside the project tree and
# needs privileges an unprivileged runner does not have.
all: .deps lint build test verify ## Run the full pipeline

clean: ## Remove build artifacts (keeps .venv: rebuilding it is the slow part)
	rm -rf build .deps __pycache__
```

## Repository-root Makefile

The root is the one place where a vendored fragment and an image-baked one
are visible **at the same time**, so it needs the guard. Do not copy the
guard into subdirectories, where it can never apply.

```make
ifeq ($(wildcard /etc/cicd-common.mk),)
-include cicd-common.mk
else
include /etc/cicd-common.mk
endif

.PHONY: lint test build deploy verify e2e all sub

lint: ## Static checks
	./tools/pipeline.sh lint

# ... one target per stage, each delegating ...

sub: ## Run a subproject's own pipeline
	$(MAKE) -C sub all
```

## Dependency manifest and wheelhouse

`requirements.txt` pins what the pipeline needs. The root Makefile resolves
it once into an offline store:

```make
WHEELHOUSE ?= cicd/wheels
REQS       ?= sub/requirements.txt

$(WHEELHOUSE)/.stamp: $(REQS)
	@mkdir -p $(WHEELHOUSE)
	$(PYTHON3) -m pip download -q -r $(REQS) -d $(WHEELHOUSE)
	@touch $@

wheels: $(WHEELHOUSE)/.stamp ## Populate an offline wheelhouse
```

Pin versions in the manifest. An unpinned manifest makes the pipeline
non-deterministic, and a pipeline that fails intermittently trains people to
re-run until green.

## Pre-push hook (level 4, cheapest form)

`.githooks/pre-push`, enabled with `git config core.hooksPath .githooks`:

```sh
#!/bin/sh
# Refuse to push a tree that does not pass its own pipeline.
# Deliberately runs the SAME targets CI runs -- never a private copy.
set -e
make lint test
```

Committed hooks plus `core.hooksPath` make this reviewable and shared,
unlike `.git/hooks`, which is per-clone and invisible.

## Hosted CI workflow (level 4, full form)

`.github/workflows/ci.yml`. The body is one line for a reason: **CI must
invoke the same targets as everything else.** The moment it grows its own
command sequence, the two definitions drift and each becomes an excuse for
the other's failure.

```yaml
name: ci
on:
  push:
  pull_request:

jobs:
  pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: make all
```

Add a cache step only once a run is slow enough to be worth it, keyed on the
manifest's hash so a dependency change forces re-resolution.

## gitignore entries

Generated and cached artifacts, never committed:

```
build/
.venv/
.deps
cicd/wheels/
cicd/payload.b64
```

The tool that produces them **is** committed. The output never is.

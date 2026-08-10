# Ecosystems

The dependency rule -- declare and cache what the pipeline can install, bake
only what it cannot -- is language-independent. What changes per ecosystem is
the manifest name, where the cached install lands, and what "offline" means.

Nothing here is Python-specific. Python simply happens to be the ecosystem
whose constraints (PEP 668, unprivileged installs) surface the rule most
sharply.

## Contents

- [The shape, in any language](#the-shape-in-any-language)
- [Per-ecosystem specifics](#per-ecosystem-specifics)
- [What a default worker actually has](#what-a-default-worker-actually-has)
- [Per-project images](#per-project-images)
- [Stages with genuinely nothing to do](#stages-with-genuinely-nothing-to-do)

## The shape, in any language

Four things, always:

1. **A manifest** that pins what the project needs.
2. **A cached install target that is a real file or directory**, listed as
   depending on that manifest -- never in `.PHONY`. A phony listing forces
   the install to re-run every invocation, which defeats the point.
3. **A location on the project tree**, so it survives an ephemeral container
   and an unprivileged user can write to it.
4. **An offline mode**, so a resolved dependency set can be carried in
   rather than re-fetched.

The `.PHONY` mistake is worth calling out because it is silent: everything
still works, just slowly, every single time. It was found and fixed in this
runner's own Node example after living there unnoticed.

## Per-ecosystem specifics

| Ecosystem | Manifest | Cached install target | Offline mode |
|---|---|---|---|
| Python | `requirements.txt` | `.venv` via a `.deps` sentinel | `pip install --no-index --find-links <wheelhouse>` |
| Node / TypeScript | `package.json` (+ lockfile) | `node_modules` directory target | `npm ci --offline` with a populated npm cache |
| Rust | `Cargo.toml` + `Cargo.lock` | `target/` and the cargo registry cache | `cargo build --offline` after `cargo fetch` |
| C / C++ | none, or `configure.ac` | object files under `build/` | system/toolchain packages -- image territory |
| Shell | none | none | not applicable |

### Python

A project-local virtual environment, gated by a sentinel:

```make
.deps: requirements.txt
	@test -x "$(VENV)/bin/python3" || $(PYTHON3) -m venv $(VENV)
	$(VENV)/bin/python3 -m pip install -q $(PIP_OFFLINE) -r requirements.txt
	@touch .deps
```

Invoke tools through `$(VENV)/bin/python3`, never the system interpreter,
or the install is bypassed at use time and the failure looks like a missing
dependency.

### Node / TypeScript

`node_modules` is itself the cached target, so no separate sentinel is
needed -- but it must be a real target, not phony:

```make
node_modules: package.json
	$(NPM) install
	@touch node_modules
```

`npm ci` is preferable where a lockfile exists: it is reproducible and
refuses to silently update. Run tools via `npx` so the project-local
`node_modules/.bin` is used rather than a global install.

### Rust

Cargo already caches into `target/` and a registry directory, both of which
persist if they sit on the project tree. Lint is `cargo clippy`, with
`cargo check` as a genuine fallback when the clippy component is absent:

```make
lint:
	@if $(CARGO) clippy --version >/dev/null 2>&1; then \
		$(CARGO) clippy -- -D warnings ; \
	else \
		$(CARGO) check ; \
	fi
```

That conditional is the right shape generally: prefer the stronger tool,
fall back to a weaker but still real one, never silently skip.

### C / C++

There is no package manager to declare into, so dependencies really are
image territory -- a compiler, headers, and native libraries cannot be
installed unprivileged into a project tree. This is the one case where the
image is the correct first answer rather than the last.

Build products still belong on the project tree under `build/`, gitignored.

### Shell

No dependencies at all; `shellcheck` is the lint stage and `bash -n` is the
closest honest equivalent of a build.

## What a default worker actually has

Verify this against the image rather than trusting any list, including this
one -- images change. At time of writing the default worker is built from a
slim Python base with Node, git, gh, a C toolchain, make, autotools and
shellcheck added.

Practically: **Python, Node/TypeScript, C/C++ and shell projects run on the
default worker. Rust, Go, Java, Ruby, PHP and .NET do not** -- neither the
toolchain nor, in most cases, an allowlist entry exists.

Remember that the allowlist governs only the entry binary. A toolchain
invoked through an allowlisted `make` needs no allowlist entry of its own --
but it does need to exist in whatever image the worker runs.

## Per-project images

For a toolchain the shared image should not carry, a project can pin its own
worker image with a `.cicd-image` file in its directory. That is how a Rust
project builds against a Rust image while every other project keeps using
the default one.

This is the correct answer whenever a toolchain is heavy, or needed by one
project rather than all of them. It also keeps the coupling visible and
local: the image requirement sits in the project's own directory rather than
being an invisible property of shared infrastructure.

So the full resolution order for a missing dependency is:

1. Project manifest, installed into a cached project-local location.
2. Check it is landing somewhere that survives -- on the project tree, not
   inside the container.
3. A per-project image override, for a whole toolchain the default image
   should not grow.
4. The shared worker image, only for what genuinely every project needs.

Reaching straight for step 4 is the common mistake.

## Stages with genuinely nothing to do

Some stages have no work in some ecosystems -- a standalone script has
nothing to deploy. Say so explicitly and exit zero:

```make
deploy: ## Nothing to deploy -- a standalone script has no running service
	@echo "Nothing to deploy -- a standalone script has no running service."
```

This is not the same as a stage that cannot fail. The distinction: an
honest no-op *states* that there is nothing to do, so a reader knows the
stage was considered. A decorative stage implies work that never happens.
Keep the first, delete or fix the second.

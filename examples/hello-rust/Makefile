# Real, filled-in "hello world" example -- not a stub. Demonstrates
# the standard lint/test/build/deploy/verify/e2e/all target
# vocabulary (see ../project-skeleton/) with real Rust/cargo tooling,
# AND the per-project worker image mechanism (see ../../README.md,
# "Per-project worker images") -- the `.cicd-image` file in this
# directory points run_in_directory() at rust:1.82-bookworm instead
# of the default cicd-worker image, which has no Rust toolchain at
# all and never will.
-include ../cicd-common.mk
-include /etc/cicd-common.mk

CARGO ?= cargo
PREFIX ?= /usr/local

.PHONY: lint test build deploy verify e2e all clean

# `cargo clippy` is the real, standard Rust linter; falls back to
# `cargo check` (still genuine static analysis) if clippy's component
# isn't installed on whatever image this ends up running in.
lint: ## Static checks (cargo clippy, falls back to cargo check)
	@if $(CARGO) clippy --version >/dev/null 2>&1; then \
		$(CARGO) clippy -- -D warnings ; \
	else \
		echo "cargo-clippy not found -- falling back to cargo check" ; \
		$(CARGO) check ; \
	fi

build: ## Compile the release binary
	$(CARGO) build --release

test: ## Unit tests
	$(CARGO) test

deploy: build ## Install the binary to PREFIX/bin
	install -d $(PREFIX)/bin
	install -m 755 target/release/hello-rust-example $(PREFIX)/bin/hello-rust-example

verify: build ## Confirm the deployed binary actually works
	@got=$$(./target/release/hello-rust-example); \
	if [ "$$got" != "Hello, World!" ]; then \
		echo "FAIL: got '$$got'" >&2; exit 1; \
	fi; \
	echo "PASS: verify"

e2e: verify ## Alias for verify

all: lint test build deploy verify ## Run the full pipeline

clean: ## Remove build artifacts
	$(CARGO) clean

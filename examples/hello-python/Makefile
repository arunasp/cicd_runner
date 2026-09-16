# Real, filled-in "hello world" example -- not a stub. Demonstrates
# the standard lint/test/build/deploy/verify/e2e/all target
# vocabulary (see ../project-skeleton/) with real Python tooling.
# The worker image carries /etc/cicd-common.mk; inside this checkout
# ../cicd-common.mk is used instead. Loading both redefines `help`.
ifeq ($(wildcard /etc/cicd-common.mk),)
-include ../cicd-common.mk
else
include /etc/cicd-common.mk
endif

PYTHON3 ?= python3
PREFIX ?= /usr/local

.PHONY: lint test build deploy verify e2e all

# The dependency-resolution step this project family's own design
# principle calls for (see ../../README.md's "Dependency caching"):
# a per-project requirements.txt plus a step that installs it, which
# lands in CACHE_ROOT_HOST's own pip cache (via PIP_CACHE_DIR) and is
# cheap on every later run -- not a workaround, the intended
# mechanism. .deps is a sentinel file (pip has no single well-known
# install directory like npm's node_modules to check timestamps
# against), matching hello-typescript's own node_modules: target
# pattern -- only re-runs pip install when requirements.txt actually
# changes. Deliberately NOT in .PHONY, same real bug/fix as
# hello-typescript's own node_modules target -- a .PHONY listing
# would force pip install to re-run on every single invocation
# regardless of whether requirements.txt had actually changed.
.deps: requirements.txt ## Install dependencies (pytest, ruff)
	$(PYTHON3) -m pip install -r requirements.txt
	@touch .deps

# ruff is preferred when available (fast, real static analysis);
# falls back to py_compile (syntax-only) as a belt-and-braces safety
# net if .deps somehow wasn't run or failed silently -- not the
# primary path anymore now that .deps installs it explicitly.
lint: .deps ## Static checks (ruff, falls back to py_compile)
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check hello.py test_hello.py ; \
	else \
		echo "ruff not found -- falling back to py_compile (syntax only)" ; \
		$(PYTHON3) -m py_compile hello.py test_hello.py ; \
	fi

# Nothing to compile -- Python ships as source. "build" here confirms
# it's syntactically valid, the closest real equivalent for a
# pure-Python project.
build: ## Syntax-check
	$(PYTHON3) -m py_compile hello.py

test: .deps build ## Unit tests (pytest)
	@if $(PYTHON3) -c "import pytest" 2>/dev/null; then \
		$(PYTHON3) -m pytest test_hello.py -v ; \
	else \
		echo "pytest not found -- install it: pip install pytest" >&2 ; \
		exit 1 ; \
	fi

deploy: build ## Install the script to PREFIX/bin
	install -d $(PREFIX)/bin
	install -m 755 hello.py $(PREFIX)/bin/hello-python-example

verify: build ## Confirm the deployed script actually works
	@got=$$($(PYTHON3) hello.py); \
	if [ "$$got" != "Hello, World!" ]; then \
		echo "FAIL: got '$$got'" >&2; exit 1; \
	fi; \
	echo "PASS: verify"

e2e: verify ## Alias for verify

all: .deps lint test build deploy verify ## Run the full pipeline

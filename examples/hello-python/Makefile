# Real, filled-in "hello world" example -- not a stub. Demonstrates
# the standard lint/test/build/deploy/verify/e2e/all target
# vocabulary (see ../project-skeleton/) with real Python tooling.
-include ../cicd-common.mk
-include /etc/cicd-common.mk

PYTHON3 ?= python3
PREFIX ?= /usr/local

.PHONY: lint test build deploy verify e2e all

# ruff is preferred when available (fast, real static analysis);
# falls back to py_compile (syntax-only) so this example still works
# on a minimal Python install with nothing else added.
lint: ## Static checks (ruff, falls back to py_compile)
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

test: build ## Unit tests (pytest)
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

all: lint test build deploy verify ## Run the full pipeline

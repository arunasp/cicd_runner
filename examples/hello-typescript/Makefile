# Real, filled-in "hello world" example -- not a stub. Demonstrates
# the standard lint/test/build/deploy/verify/e2e/all target
# vocabulary (see ../project-skeleton/) with real TypeScript tooling.
-include ../cicd-common.mk
-include /etc/cicd-common.mk

NPM ?= npm
NODE ?= node
NPX ?= npx
PREFIX ?= /usr/local

.PHONY: lint test build deploy verify e2e all clean node_modules

node_modules: package.json
	$(NPM) install
	@touch node_modules

# `tsc --noEmit` IS a genuine, real lint pass for TypeScript -- type
# errors are exactly the class of bug static analysis should catch
# here. A dedicated linter (eslint) would be additive, not a
# replacement, for a project this small.
lint: node_modules ## Static checks (tsc --noEmit)
	$(NPX) tsc --noEmit

build: node_modules ## Compile to dist/
	$(NPX) tsc

test: build ## Unit tests
	$(NODE) dist/test.js

deploy: build ## Install a wrapper script to PREFIX/bin
	install -d $(PREFIX)/bin
	printf '#!/bin/sh\nexec $(NODE) "%s" "$$@"\n' "$(CURDIR)/dist/hello.js" > $(PREFIX)/bin/hello-typescript-example
	chmod 755 $(PREFIX)/bin/hello-typescript-example

verify: build ## Confirm the deployed script actually works
	@got=$$($(NODE) dist/hello.js); \
	if [ "$$got" != "Hello, World!" ]; then \
		echo "FAIL: got '$$got'" >&2; exit 1; \
	fi; \
	echo "PASS: verify"

e2e: verify ## Alias for verify

all: lint test build deploy verify ## Run the full pipeline

clean: ## Remove build artifacts
	rm -rf dist node_modules

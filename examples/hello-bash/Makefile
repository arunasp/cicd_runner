# Real, filled-in "hello world" example -- not a stub. Demonstrates
# the standard lint/test/build/deploy/verify/e2e/all target
# vocabulary (see ../project-skeleton/) with real bash tooling.
-include ../cicd-common.mk
-include /etc/cicd-common.mk

.PHONY: lint test build deploy verify e2e all

lint: ## Static checks (shellcheck)
	shellcheck -x hello.sh test.sh

# No compilation step for a plain script -- "build" here just
# confirms it's syntactically valid and executable, which is the
# closest real equivalent.
build: ## Syntax-check and mark executable
	bash -n hello.sh
	chmod +x hello.sh

test: build ## Unit tests
	./test.sh

deploy: build ## Nothing to deploy -- a standalone script has no service
	@echo "Nothing to deploy -- a standalone script has no running service."

verify: build ## Confirm the deployed script actually works
	@test "$$(./hello.sh)" = "Hello, World!"
	@echo "PASS: verify"

e2e: verify ## Alias for verify

all: lint test build deploy verify ## Run the full pipeline

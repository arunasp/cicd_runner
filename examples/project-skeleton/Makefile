# Project skeleton for cicd_runner-compatible pipelines.
#
# Copy this Makefile into a new project's root and fill in each
# target's recipe with that project's real commands. Standard DevOps
# target vocabulary (lint/test/build/deploy/verify/e2e/all) matches
# cicd_runner's own README examples -- once these targets exist and
# do something real, the project works immediately with cicd_runner,
# no changes needed there:
#   run_command(project="<name>", binary="make", args=["lint"])       # named, pre-mounted
#   run_in_directory(relative_path="<name>", binary="make", args=["lint"])  # ad hoc, under DYNAMIC_ROOT
#
# If a target's real command needs a binary not already in
# cicd_runner's server/allowlist.txt, add it there (with a comment
# explaining why, matching that file's existing convention) --
# needs an image rebuild (both coordinator and worker) to take effect.
#
# -include /etc/cicd-common.mk below still works once this file is
# copied into an unrelated project's root and run through
# cicd-runner (baked into both images at a fixed path) -- the
# ../cicd-common.mk line is only useful while this file still lives
# inside cicd_runner's own examples/ directory, and is a harmless
# no-op once copied elsewhere.
-include ../cicd-common.mk
-include /etc/cicd-common.mk

.PHONY: lint test build deploy verify e2e all

lint: ## TODO: replace with a real lint command (shellcheck/eslint/ruff/...)
	# TODO: replace with this project's real lint command, e.g.:
	#   shellcheck scripts/*.sh
	#   eslint .
	#   ruff check .
	@echo "TODO: add a real lint command" >&2
	@exit 1

test: ## TODO: replace with a real test command
	# TODO: replace with this project's real test command, e.g.:
	#   pytest
	#   npm test
	@echo "TODO: add a real test command" >&2
	@exit 1

build: ## TODO: replace with a real build command
	# TODO: replace with this project's real build command, e.g.:
	#   docker build -t my-project .
	@echo "TODO: add a real build command" >&2
	@exit 1

deploy: ## TODO: replace with a real deploy command
	# TODO: replace with this project's real deploy command, e.g.:
	#   docker compose up -d
	@echo "TODO: add a real deploy command" >&2
	@exit 1

verify: ## TODO: replace with a real post-deploy health check
	# TODO: replace with a real post-deploy health check, e.g.:
	#   curl -f http://localhost:PORT/health
	@echo "TODO: add a real verify command" >&2
	@exit 1

# Alias for verify by default, not a fabricated distinct suite.
# Point this at a real, separate e2e target instead once one exists
# for this project.
e2e: verify ## Alias for verify

all: lint test build deploy verify ## Run the full pipeline

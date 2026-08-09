# Shared, reusable Makefile fragment for cicd_runner-compatible
# pipelines -- self-documenting help target using the well-known
# `## comment` convention: any target line ending in `## text` is
# picked up automatically, no per-project help block to maintain or
# let drift out of sync with the real target list.
#
# Included two ways, covering both real execution contexts this
# project has:
#   -include ../cicd-common.mk     -- resolves for a plain git
#                                      checkout / standalone `make`
#                                      (native filesystem, real
#                                      relative paths)
#   -include /etc/cicd-common.mk   -- resolves inside a cicd-runner
#                                      worker/coordinator (baked into
#                                      both images at build time) --
#                                      run_in_directory() only mounts
#                                      the single target directory,
#                                      never its parent, so a relative
#                                      ../ path can never resolve there
# At most one of the two ever actually exists in a given context, so
# there's no real conflict between them.
#
# NOTE: this is a copy of examples/cicd-common.mk (that's the
# canonical source) -- duplicated into server/ and worker/ purely
# because Docker's COPY can only reference files inside its own build
# context, and this project has two separate contexts (./server,
# ./worker). Keep all three in sync if this ever changes.
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

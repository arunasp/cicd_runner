ACLOCAL_AMFLAGS = -I m4

# Top-level standalone files use automake's own SCRIPTS/DATA
# primaries -- confirmed against GNU's own Automake manual ("Scripts"
# node: script objects can be installed in bindir/sbindir/libexecdir/
# pkgdatadir via dist_<dir>_SCRIPTS, with automake generating the
# install/uninstall/dist rules itself) -- this is the genuinely
# idiomatic form, not a hand-rolled substitute for it.
#
# Directory TREES (server/, worker/, examples/, desktop-extension/)
# can't use this -- automake's primaries are flat file lists with no
# built-in support for installing nested subdirectory structure. The
# install-data-local/uninstall-local hooks below are the standard,
# documented escape hatch for exactly that limitation, not an
# invented deviation from it.
dist_pkgdata_SCRIPTS = build.sh start.sh

# tools/ holds the scripts nothing human invokes directly -- compose.sh
# venv-build.sh and venv-check.sh are called by the targets below and by build.sh/start.sh;
# debug_worker.sh and the deploy_* pair are diagnostics. build.sh,
# start.sh and autogen.sh deliberately stay at the root: they are the
# documented entry points, named in README.md and in this file's own
# install-data-local message.
#
# `nobase_` is what stops automake FLATTENING these into pkgdatadir --
# a plain dist_pkgdata_SCRIPTS entry of `tools/compose.sh` installs as
# pkgdatadir/compose.sh, which would break build.sh's and start.sh's
# own tools/compose.sh reference in an installed copy while leaving the
# checkout working. The deploy_* and debug scripts are deliberately not
# listed at all, exactly as before the move: they were never installed
# or distributed, and this is a relocation, not a change of what ships.
nobase_dist_pkgdata_SCRIPTS = tools/compose.sh tools/venv-build.sh tools/venv-check.sh tools/shellcheck.sh tools/clean-containers.sh tools/autotools.sh
dist_pkgdata_DATA = docker-compose.yml .env.example README.md

# `make` / `make all` -- delegates to build.sh (worker + coordinator
# images only, matching build.sh's own scope -- the Desktop extension
# stays a separate, explicit step, same as this project's own
# top-level Makefile keeps `build` and `build-extension` distinct).
# Deliberately has NO side effects beyond building -- matches the GNU
# Coding Standards' own expectation that `all` builds, it doesn't
# deploy or launch anything (same reasoning as install-data-local
# below not starting a service either).
all-local:
	./build.sh

# Real design note (found live 2026-08-08): this project ALSO had its
# own hand-written root Makefile before Autotools support was added --
# `./configure` generates a file at the exact same path (`./Makefile`),
# which silently overwrote it the first time `./configure` was ever
# actually run for real. The fix is this section: every target that
# Makefile used to provide is folded into Makefile.am directly, so the
# ONE generated Makefile serves both the standard Autotools interface
# (check/install/uninstall/dist/clean) and this project's own richer
# daily-use one, instead of two separate files racing for the same
# name. None of the names below collide with Automake's own reserved
# targets. `COMPOSE` is a WRAPPER SCRIPT, not a substituted value:
# compose.sh detects v2-plugin-vs-v1-binary at invocation. It used to
# be a COMPOSE_CMD value substituted once by ./configure -- which froze a
# property of the USERLAND into a file this checkout shares between two
# boots and two container images. Confirmed live 2026-08-25: a Makefile
# generated where only compose v1 existed baked `docker-compose`, and
# stop/logs/status then failed with exit 127 both on a host with only
# the v2 plugin and inside the coordinator container, neither of which
# had the v1 binary. There is still no $(shell ...) here -- automake's
# own -Wall -Werror correctly flags that as a non-POSIX GNU Make extension
# -- the detection simply lives in the script, which build.sh and
# start.sh also route through, so there is ONE implementation of it
# rather than four drifting copies.
COMPOSE = $(SHELL) $(srcdir)/tools/compose.sh

# FIXED 2026-08-09 (was a KNOWN LIMITATION until Arunas asked "what
# if we define missing becoming defined" -- correct instinct, and a
# real, working fix): Autotools bakes ABSOLUTE host paths into the
# generated Makefile at ./configure time -- not just
# $(srcdir)/$(abs_srcdir) (which resolve fine either way, since most
# recipes use the RELATIVE $(srcdir)="."), but the derived
# ACLOCAL/AUTOCONF/AUTOMAKE/AUTOHEADER/MAKEINFO variables
# specifically, e.g. `${SHELL} '/home/devuser/stuff/cicd_runner/
# missing' automake-1.16`. This repo mounts itself into the
# coordinator at a DIFFERENT absolute path (/projects/cicd_runner)
# than wherever it actually lives on the real host -- so those baked
# host-absolute paths didn't exist inside the container, causing a
# real, confirmed regeneration failure (`/bin/bash: .../missing: No
# such file or directory`) whenever Makefile.am/configure.ac had just
# changed and `make` was invoked via run_command() before a host-side
# regeneration ran first.
#
# Fixed at the source, in configure.ac, not worked around here:
# MISSING/ACLOCAL/AUTOCONF/AUTOMAKE/AUTOHEADER/MAKEINFO are now
# pre-set to RELATIVE paths before AM_INIT_AUTOMAKE expands its own
# AM_MISSING_PROG calls -- both that macro and AM_MISSING_HAS_RUN use
# the standard shell "only if not already set" pattern
# (`${VAR-default}`/`${VAR+set}`, confirmed by reading the real
# generated aclocal.m4 directly), so a pre-set value is respected
# instead of Automake's own absolute default. Automake defaults to
# absolute specifically to survive subdirectory/VPATH (out-of-tree)
# builds -- this project has neither (flat layout, no SUBDIRS, srcdir
# always equals builddir), so that protection buys nothing here while
# it was actively breaking the real case this project DOES hit.
# Verified end-to-end before applying, not just reasoned about: a
# real, isolated reproduction (same structural bug, a checkout copied
# to a different absolute path after ./configure ran) failed exactly
# as this project did, without the override, then succeeded cleanly
# with it. See configure.ac's own comment for the fix itself.
#
# Since this changes configure.ac, it needs regenerating on the real
# host once (`make`, or `./autogen.sh && ./configure`) before the fix
# itself takes effect -- after that, the standing regenerate-on-host-
# first discipline this comment used to require is no longer needed
# for THIS specific failure (though still generally sound practice
# after any Makefile.am/configure.ac edit).

.PHONY: help build rebuild image-check clean-containers build-extension build-all start stop restart logs status health-check push skills-check deps env-check modes-check

help:
	@echo "Autotools-standard targets: check install uninstall dist clean"
	@echo "This project's own daily-use targets:"
	@echo "  build           - build cicd-runner's own images (worker + coordinator)"
	@echo "  rebuild         - build both images with --no-cache --pull, then verify they start"
	@echo "  image-check     - start one throwaway container per image; changes nothing else"
	@echo "  clean-containers - remove every container compose labels for this project, by ID"
	@echo "  deps            - provision (and heal) the Python env 'make check' runs in"
	@echo "  env-check       - report whether that env is current; changes nothing"
	@echo "  modes-check     - prove every directly-executed script is 100755 in the index"
	@echo "  build-extension - build the Claude Desktop .mcpb connector"
	@echo "  build-all       - both of the above"
	@echo "  start           - build (runner only) + launch (./start.sh)"
	@echo "  stop            - stop and remove the running container"
	@echo "  restart         - stop, then start"
	@echo "  logs            - follow the coordinator's logs"
	@echo "  status          - show container status"
	@echo "  health-check    - check coordinator health (see health-check's own comment)"
	@echo "  push            - git push origin main (see push's own comment on where this can actually run)"

build:
	./build.sh

# `make rebuild` -- the recovery path when an image builds but cannot be
# started: `build` can pass entirely from cache while the daemon cannot
# unpack the layers it reuses. --pull refreshes the base image as well.
rebuild:
	BUILD_FLAGS="--no-cache --pull" ./build.sh worker coordinator verify

# `make image-check` -- the verify stage alone. Starts and removes one
# container per image with `--entrypoint true` and `--network none`.
image-check:
	./build.sh verify

# `make clean-containers` -- the same fallback start.sh uses when
# `compose rm -sf` fails on a container the daemon lists.
clean-containers:
	$(SHELL) $(srcdir)/tools/clean-containers.sh

build-extension:
	./desktop-extension/build.sh

build-all: build build-extension

start:
	./start.sh

stop:
	$(COMPOSE) down

restart: stop start

logs:
	$(COMPOSE) logs -f cicd-runner

status:
	$(COMPOSE) ps

# `make push` -- a real, thin `git push origin main` wrapper, added
# per Arunas's own request (2026-08-09) so pushing is a real pipeline
# step rather than a bare command to remember. Deliberately does NOT
# come with any credential setup of its own -- this project's own
# stated design decision (see README's "No SSH keys or git
# credentials are mounted here") means the coordinator/worker
# containers have zero GitHub push credentials by design, confirmed
# repeatedly this session (git add/commit/amend all work fine via
# run_command()/run_in_directory() -- they only touch the real,
# bind-mounted host checkout -- but push itself has needed Arunas's
# own credentials/action every single time so far). This target does
# NOT change that boundary -- it's the same `git push` either way,
# just given a name. Run from a host shell where this remote's
# credentials are actually configured (Arunas's own terminal); run
# via run_command()/the MCP tools instead and expect the same auth
# failure this project has hit every time credentials were needed,
# since the coordinator container genuinely has none.
push:
	git push origin main

# `make health-check` -- run via run_command(project="cicd_runner",
# binary="make", args=["health-check"]) so this project can
# self-verify its own coordinator's health through its own pipeline,
# per Arunas's own request (2026-08-09, closing the CVV#15
# self-verification gap raised earlier the same session).
#
# Deliberately does NOT curl/http-request localhost:1444/health --
# doing so from inside a run_command() call is a REAL, confirmed
# self-deadlock, not a hypothetical risk: FastMCP's own tool dispatch
# (mcp/server/fastmcp/tools/base.py's call_fn_with_arg_validation)
# invokes a SYNCHRONOUS @mcp.tool() function like run_command()
# directly on the coordinator's single asyncio event loop --
# `return fn(**args)`, not wrapped in a thread pool/executor. Since
# run_command()'s own subprocess.run() then blocks that SAME event
# loop for its entire duration, a child process spawned from inside
# it that tries to reach the coordinator's own HTTP server can never
# get a response -- the one thread that could serve it is the one
# blocked waiting for the child, and a server-side subprocess.run()
# is not cancelled by the client giving up, so this hangs
# indefinitely rather than erroring quickly. Confirmed live 2026-08-09:
# a plain `python3 -c "...urlopen('http://localhost:1444/health')..."`
# run via run_command() hung 4+ minutes and very likely left the
# coordinator's own event loop wedged until manually restarted.
#
# Instead, this checks the exact same underlying conditions
# bash_mcp_server.py's own health_check() checks, directly -- no HTTP
# round-trip back into the same process, so no deadlock is possible.
# Kept in sync BY HAND with health_check()'s own logic (not
# generated from it) -- if that function's checks change, update
# this target to match. Written as separate `var=$$(...)` assignments
# joined by `; \` rather than nesting `test -n "$$VAR"` directly
# inside an echo's own outer double-quoted string -- a real, tested
# bug found in this target's own first draft: the escaped `\"..\"`
# needed to nest inside that outer string does NOT get stripped by
# the shell the way plain `".."` would; the literal backslash-quote
# characters survive into the string being tested, so `test -n` sees
# two literal quote characters even when the variable itself is
# genuinely empty, and incorrectly reports true unconditionally.
# Confirmed via a real, isolated `set -x` trace before writing this
# fixed version, not just reasoned about -- and re-verified across
# all three real states (nothing configured, env vars set but no
# socket, a genuine socket present) before committing.
health-check:
	@docker_ok=$$(test -S /var/run/docker.sock && echo true || echo false); \
	dyn_ok=$$(test -n "$$DYNAMIC_ROOT_HOST" && echo true || echo false); \
	cache_ok=$$(test -n "$$CACHE_ROOT_HOST" && echo true || echo false); \
	echo "docker_socket: $$docker_ok"; \
	echo "dynamic_root_configured: $$dyn_ok"; \
	echo "cache_root_configured: $$cache_ok"; \
	test -S /var/run/docker.sock || { echo "UNHEALTHY: docker socket missing" >&2; exit 1; }; \
	echo "OK"

# `make env-check` -- report only, changes nothing. tools/venv-check.sh
# owns the decision `deps` acts on, and exposing it as its own target
# means the decision can be asked about without provoking a rebuild to
# find out what it would have been. Exit status is the answer: 0
# current, 1 stale, 2 no usable base interpreter, 3 a requirements file
# named here is missing.
env-check: ## Report whether the test environment is current, changing nothing
	@PYTHON3="$(PYTHON3)" VENV_ROOT="$(srcdir)/.cicd-runner-cache/venv" $(SHELL) $(srcdir)/tools/venv-check.sh \
		server/requirements.txt requirements-dev.txt >/dev/null \
		&& echo "env: current"

# `make deps` -- provisioning as a NAMED STAGE rather than a fragment
# buried in check-local's recipe, so it can be invoked on its own
# (through the runner, from CI, or by hand) and so a failure to build
# the environment is reported as that, not as a test failure.
#
# tools/venv-build.sh is idempotent: it asks tools/venv-check.sh whether the
# environment is current and does nothing at all when it is. That is
# why check-local can both DEPEND on this target and still call the
# script itself to capture the path -- the second call does no work.
# Stdout is dropped here because this target provisions rather than
# resolves; the path is the caller's business.
deps: ## Provision the Python environment make check runs in
	@PYTHON3="$(PYTHON3)" VENV_ROOT="$(srcdir)/.cicd-runner-cache/venv" $(SHELL) $(srcdir)/tools/venv-build.sh \
		server/requirements.txt requirements-dev.txt >/dev/null

# Scripts this project executes DIRECTLY, and which must therefore stay
# executable in the INDEX rather than merely in someone's working tree.
# Deliberately an explicit list rather than a glob over *.sh: it is not
# true of every script here. worker/entrypoint.sh is 100644 on purpose
# (its Dockerfile chmods it after COPY), and examples/hello-bash/*.sh
# are invoked through make, never as commands.
#
# The gate exists because losing the bit is silent and easy: an editor
# or a connector that rewrites a file in place can drop it, git records
# the change as an ordinary modification, and the script keeps working
# for whoever still has it executable locally. It broke build.sh and
# start.sh here on 2026-08-25 and was noticed only by chance.
# NOTE ON THE NAME: not EXEC_SCRIPTS. Any variable ending in _SCRIPTS
# is an automake PRIMARY, and automake rejects one without a matching
# `EXECdir` -- caught immediately by -Wall -Werror rather than becoming
# a silent misinstall.
EXEC_BITS = autogen.sh build.sh start.sh \
	tools/compose.sh tools/venv-build.sh tools/venv-check.sh tools/shellcheck.sh \
	tools/clean-containers.sh tools/autotools.sh \
	tools/debug_worker.sh \
	tools/deploy_cicd_runner.sh tools/deploy_cicd_runner_debug.sh \
	desktop-extension/build.sh

# Degrades to a skip outside a git checkout -- `make check` has to work
# from an unpacked `make dist` tarball, where there is no index to ask.
# Same SKIP-not-FAIL treatment shellcheck gets below.
modes-check: ## Prove every directly-executed script is 100755 in the index
	@if git -C $(srcdir) rev-parse --git-dir >/dev/null 2>&1; then \
		bad=0; \
		for f in $(EXEC_BITS); do \
			mode=`git -C $(srcdir) ls-files -s -- "$$f" | awk '{print $$1}'`; \
			if [ "$$mode" != 100755 ]; then \
				echo "not executable in the index: $$f (mode $${mode:-absent})" >&2; \
				bad=1; \
			fi; \
		done; \
		if [ "$$bad" -ne 0 ]; then \
			echo "fix with: git update-index --chmod=+x <file>" >&2; \
			exit 1; \
		fi; \
		echo "modes: every directly-executed script is 100755 in the index"; \
	else \
		echo "not a git checkout -- skipping the mode check (not required)"; \
	fi

# `make check` -- the real, committed pytest suite
# (server/test_bash_mcp_server.py, covering path-resolution,
# per-call config resolution, and the directory-ACL/roots logic
# added 2026-08-09). --asyncio-mode=auto is needed for the async
# test cases covering the MCP roots integration (pytest-asyncio,
# added to server/requirements.txt alongside this).
#
# The shellcheck step is NOT optional any more. It used to test
# `command -v shellcheck` and print "skipping (not required)" when it
# was absent, which made the lint result depend on which userland ran
# the suite -- it had been skipping on one of this checkout's two boots
# and passing on the other. tools/shellcheck.sh resolves one from PATH
# or from the venv `make deps` builds, so absence is now a `make deps`
# away rather than a reason to pass without checking.
check-local: skills-check modes-check deps
	@py=$$(PYTHON3="$(PYTHON3)" VENV_ROOT="$(srcdir)/.cicd-runner-cache/venv" $(SHELL) $(srcdir)/tools/venv-build.sh \
		server/requirements.txt requirements-dev.txt) && \
		"$$py" -m pytest server/test_bash_mcp_server.py -v --asyncio-mode=auto
	@echo "Running shellcheck..."
	@$(SHELL) $(srcdir)/tools/shellcheck.sh -x -P SCRIPTDIR \
		build.sh start.sh tools/compose.sh tools/venv-build.sh \
		tools/venv-check.sh tools/shellcheck.sh tools/clean-containers.sh \
		tools/autotools.sh autogen.sh desktop-extension/build.sh

# Skills are published in two formats from one source of truth: the
# browsable skills/opencode/<name>/ trees, and the packaged
# skills/claude/<name>.skill bundles. Keeping those in sync by
# discipline does not survive a busy week, so this makes drift a build
# failure -- validate.py unpacks each bundle in memory and compares it
# byte-for-byte against the tree it was built from, as well as checking
# frontmatter and that every shipped reference is actually pointed at.
# Wired into check-local rather than given its own CI job, so the same
# command runs locally, in a worker, and in CI. Stdlib only, so it runs
# anywhere python3 does.
# validate.py is stdlib-only by design, so this target deliberately does
# NOT use $(PYTHON3), and does not go through tools/venv-build.sh either.
# $(PYTHON3) is only a BASE interpreter for building a virtualenv, and
# the virtualenv itself belongs to one userland -- neither is available
# unchanged inside a worker container. The original failure was exactly
# that: ./configure had resolved $(PYTHON3) to a venv whose python3 was
# a symlink into an interpreter the worker does not have, so the symlink
# dangled and the target died with exit 127. Plain python3 from PATH
# works on any host and in any worker, which is the whole point of
# keeping validate.py dependency-free.
SKILLS_PYTHON ?= python3

skills-check: ## Validate skills/ and prove both formats agree
	$(SKILLS_PYTHON) $(srcdir)/skills/validate.py

# `make install` -- dist_pkgdata_SCRIPTS/DATA above already install
# the flat top-level files via automake's own generated rules; this
# hook only handles the directory trees those primaries can't reach.
# Deliberately does NOT launch anything -- `make install` starting a
# background docker service would be a real surprise for anyone
# following normal `./configure && make && sudo make install`
# expectations. Run ./start.sh from the installed location afterward.
# Real bug found live 2026-08-08: examples/hello-rust/target/ (Cargo's
# own build-output directory, created by actually running cargo
# build/test) contains incremental-compilation .lock files that
# Cargo deliberately makes unreadable by other processes -- a plain
# `cp -r` genuinely can't read them ("Permission denied"), which
# made the whole install-data-local target fail even though almost
# everything else copied fine. Same CLASS of problem already solved
# for __pycache__/.pytest_cache, just not extended to Rust's own
# build directory since hello-rust didn't exist when that exclusion
# was first written. Fixed properly, not by cleaning up afterward
# (too late -- the permission error happens DURING the copy, before
# any cleanup step could run): tar's --exclude means the excluded
# paths are never even attempted to be read in the first place, not
# copied-then-deleted. tar is explicitly on the GNU Coding Standards'
# own allowed-utilities list for Makefile commands (see Utilities in
# Makefiles) -- not a workaround, the standards-compliant choice.
# Confirmed via a real test: tar --exclude=target genuinely never
# lists or reads anything inside a target/ directory, unlike cp -r.
install-data-local: clean-example-artifacts
	$(MKDIR_P) "$(DESTDIR)$(pkgdatadir)"
	(cd $(srcdir) && tar --exclude=target --exclude=node_modules \
		--exclude=__pycache__ --exclude=.pytest_cache --exclude=.venv \
		-cf - server worker examples desktop-extension skills) | \
		(cd "$(DESTDIR)$(pkgdatadir)" && tar -xf -)
	@echo ""
	@echo "Installed to $(DESTDIR)$(pkgdatadir)"
	@echo "Next: cd $(DESTDIR)$(pkgdatadir) && cp .env.example .env && ./start.sh"

# Same fix applied to `make dist`'s side of the identical risk:
# EXTRA_DIST below includes examples/ as a whole directory, so
# Automake's own internal distdir-population would hit the exact same
# permission-denied read on hello-rust/target/'s lock files -- and
# dist-hook (below) runs AFTER that population, too late to prevent
# it. This makes clean-example-artifacts an EXTRA prerequisite of
# Automake's own generated `dist` target -- Make merges prerequisite
# lists across multiple `target: prereq` declarations for the same
# target name, so this doesn't redefine or conflict with Automake's
# own dist recipe, confirmed via a real end-to-end make dist run.
dist: clean-example-artifacts

# Shared cleanup for both fixes above -- removes real, transient build
# artifacts (Rust's target/, Node's node_modules/, Python's own cache
# dirs) from UNDER examples/ specifically, before either operation
# ever touches those files. Safe to run unconditionally: these are
# all regenerable via each example's own `make build`/`make test`.
clean-example-artifacts:
	find $(srcdir)/examples \( -name target -o -name node_modules \
		-o -name __pycache__ -o -name .pytest_cache \) -type d -exec rm -rf {} +

# Only removes what install-data-local's own hook created --
# dist_pkgdata_SCRIPTS/DATA's flat files are uninstalled automatically
# by automake's own generated uninstall-am rule, no need to duplicate
# that here.
uninstall-local:
	rm -rf "$(DESTDIR)$(pkgdatadir)/server" "$(DESTDIR)$(pkgdatadir)/worker" \
		"$(DESTDIR)$(pkgdatadir)/examples" "$(DESTDIR)$(pkgdatadir)/desktop-extension"
	-rmdir "$(DESTDIR)$(pkgdatadir)" 2>/dev/null || true

# `make clean` -- local build artifacts only (node_modules, the
# packed .mcpb, Python's own cache dirs). Deliberately does NOT touch
# already-built Docker images -- `docker rmi` has broader
# consequences than a normal `make clean` should carry, and isn't
# something to do silently as a side effect of this target.
# The dependency caches are skipped: .cicd-runner-cache/ and .venv/ hold
# installed packages, not build output, and may carry files another uid
# wrote (the coordinator runs as root).
clean-local: clean-example-artifacts
	rm -rf desktop-extension/node_modules desktop-extension/dist/*.mcpb
	find . \( -path ./.cicd-runner-cache -o -path ./.venv -o -path ./.git \) -prune \
		-o \( -name __pycache__ -o -name .pytest_cache \) -type d -exec rm -rf {} +

# `make dist` -- dist_pkgdata_SCRIPTS/DATA above are bundled
# automatically; EXTRA_DIST covers everything else needed to
# reproduce this checkout's own real build (mirrors .gitignore's own
# exclusions: no node_modules, no packed .mcpb, no __pycache__).
EXTRA_DIST = \
	.gitignore \
	CHANGELOG.md \
	pytest.ini \
	requirements-dev.txt \
	server worker examples skills \
	AGENTS.md CLAUDE.md \
	desktop-extension/index.js desktop-extension/manifest.json \
	desktop-extension/package.json desktop-extension/package-lock.json \
	desktop-extension/build.sh

# EXTRA_DIST above includes whole directories (server/, worker/,
# examples/), so `make dist` sweeps up whatever's transiently in them
# at dist-time too -- confirmed live: a __pycache__/ created by a
# preceding `make check` leaked into a real dist tarball before this
# hook was added. dist-hook is automake's own purpose-built place to
# clean the STAGED $(distdir) after files are copied in, not a
# workaround bolted on afterward.
dist-hook:
	find "$(distdir)" \( -name __pycache__ -o -name .pytest_cache \) -exec rm -rf {} +

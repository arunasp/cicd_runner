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
# targets. `COMPOSE` is substituted from configure.ac's own
# v2-plugin-vs-v1-binary detection (COMPOSE_CMD, AC_SUBST'd) rather
# than re-detected here via $(shell ...) -- automake's own -Wall
# -Werror correctly flags $(shell ...) as a non-POSIX GNU Make
# extension, and doing it once at configure time is cheaper anyway.
COMPOSE = @COMPOSE_CMD@

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

.PHONY: help build build-extension build-all start stop restart logs status health-check push skills-check

help:
	@echo "Autotools-standard targets: check install uninstall dist clean"
	@echo "This project's own daily-use targets:"
	@echo "  build           - build cicd-runner's own images (worker + coordinator)"
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

# `make check` -- the real, committed pytest suite
# (server/test_bash_mcp_server.py, covering path-resolution,
# per-call config resolution, and the directory-ACL/roots logic
# added 2026-08-09). --asyncio-mode=auto is needed for the async
# test cases covering the MCP roots integration (pytest-asyncio,
# added to server/requirements.txt alongside this). Also runs
# shellcheck against this project's own shell scripts when it's on
# PATH -- optional, matches build.sh's own SKIP-not-FAIL treatment
# of missing-but-not-required tools; `./configure` does not check
# for shellcheck since `check` is the only thing that needs it and
# it degrades gracefully.
check-local: skills-check
	$(PYTHON3) -m pytest server/test_bash_mcp_server.py -v --asyncio-mode=auto
	@if command -v shellcheck >/dev/null 2>&1; then \
		echo "Running shellcheck..." ; \
		shellcheck -x -P SCRIPTDIR build.sh start.sh desktop-extension/build.sh ; \
	else \
		echo "shellcheck not found on PATH -- skipping (not required)" ; \
	fi

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
# NOT use $(PYTHON3). ./configure resolves that to the interpreter it
# found on the host -- here a .venv whose python3 is a symlink into a
# conda install -- which does not exist inside a worker container, so the
# symlink dangles and the target dies with exit 127. Plain python3 from
# PATH works on the host and in any worker, which is the whole point of
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
clean-local: clean-example-artifacts
	rm -rf desktop-extension/node_modules desktop-extension/dist/*.mcpb
	find . \( -name __pycache__ -o -name .pytest_cache \) -exec rm -rf {} +

# `make dist` -- dist_pkgdata_SCRIPTS/DATA above are bundled
# automatically; EXTRA_DIST covers everything else needed to
# reproduce this checkout's own real build (mirrors .gitignore's own
# exclusions: no node_modules, no packed .mcpb, no __pycache__).
EXTRA_DIST = \
	.gitignore \
	CHANGELOG.md \
	pytest.ini \
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

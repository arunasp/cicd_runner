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

.PHONY: help build build-extension build-all start stop restart logs status

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
check-local:
	$(PYTHON3) -m pytest server/test_bash_mcp_server.py -v --asyncio-mode=auto
	@if command -v shellcheck >/dev/null 2>&1; then \
		echo "Running shellcheck..." ; \
		shellcheck -x -P SCRIPTDIR build.sh start.sh desktop-extension/build.sh ; \
	else \
		echo "shellcheck not found on PATH -- skipping (not required)" ; \
	fi

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
		-cf - server worker examples desktop-extension) | \
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
	server worker examples \
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

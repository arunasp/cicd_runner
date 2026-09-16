dnl Process this file with autoconf to produce a configure script.
dnl
dnl cicd_runner isn't a compiled project -- there's nothing here for a
dnl C compiler to build. Autotools is used anyway, deliberately, to
dnl give this a standard `./configure && make && make install` entry
dnl point independent of the project's own Makefile-target vocabulary
dnl (lint/test/build/deploy/verify/e2e/all -- see the top-level
dnl README and examples/project-skeleton/), so it's buildable by
dnl anyone who knows traditional Unix/FOSS conventions and nothing
dnl else about this specific project.
AC_PREREQ([2.71])
AC_INIT([cicd-runner], [1.1.0], [https://github.com/arunasp/cicd_runner/issues])
AC_CONFIG_SRCDIR([server/bash_mcp_server.py])

dnl Force Automake's own maintainer-tool variables (MISSING itself,
dnl plus ACLOCAL/AUTOCONF/AUTOMAKE/AUTOHEADER/MAKEINFO, each set via
dnl its own AM_MISSING_PROG call inside AM_INIT_AUTOMAKE below) to
dnl RELATIVE paths, overriding Automake's own default of always-
dnl absolute (AM_AUX_DIR_EXPAND's `cd $ac_aux_dir && pwd`). Automake
dnl defaults to absolute deliberately, to survive subdirectory/VPATH
dnl (out-of-tree) builds -- this project has neither (flat layout, no
dnl SUBDIRS, srcdir always equals builddir), so that protection buys
dnl nothing here while actively breaking a real, different case this
dnl project DOES hit: the same checkout bind-mounted into cicd-runner's
dnl own coordinator at a different absolute path than on the real
dnl host (confirmed live 2026-08-09 -- see Makefile.am's own comment
dnl for the original failure). Both AM_MISSING_PROG and
dnl AM_MISSING_HAS_RUN use the standard shell "only if not already
dnl set" pattern (`${VAR-default}` / `${VAR+set}`, confirmed by
dnl reading the real, generated aclocal.m4 directly, not assumed) --
dnl pre-setting these here, in plain shell before AM_INIT_AUTOMAKE
dnl expands its own AM_MISSING_PROG calls, means Automake respects
dnl the override instead of computing its own absolute default.
dnl Verified end-to-end in a real, isolated reproduction before
dnl applying here: modified Makefile.am, copied the whole checkout to
dnl a DIFFERENT absolute path (simulating the host-vs-container
dnl mismatch exactly), ran `make` from the new path -- Automake's own
dnl auto-regeneration chain fired and succeeded correctly, where it
dnl previously failed with "No such file or directory" on the old,
dnl host-only absolute path.
dnl The names are UNVERSIONED (`automake`, not `automake-1.16`).
dnl Automake's own default is versioned, which is right for a tree whose
dnl generated files are committed and must be reproduced by one exact
dnl release. Here they are not: Makefile.in, configure and aclocal.m4
dnl are all gitignored, so every userland regenerates its own. Pinning a
dnl version therefore froze a per-userland fact into a shared checkout
dnl -- the same mistake COMPOSE_CMD and PYTHON3 made. Confirmed live
dnl 2026-08-25: automake 1.17 in the worker image and 1.18.1 on the
dnl host, so the pin at 1.16 matched NEITHER; whichever one it named,
dnl the userlands that had a different one saw their `missing`
dnl wrapper degraded to a warning and a touch, leaving a stale generated
dnl file behind while reporting success. Unversioned means each userland
dnl uses the automake it has, and a genuine incompatibility is reported
dnl by automake itself rather than silently skipped.
MISSING='${SHELL} missing'
dnl The four regeneration programs go through tools/autotools.sh, which
dnl reruns autoreconf when aclocal.m4 is from a different Automake
dnl release than the installed one.
ACLOCAL='${SHELL} tools/autotools.sh aclocal'
AUTOCONF='${SHELL} tools/autotools.sh autoconf'
AUTOMAKE='${SHELL} tools/autotools.sh automake'
AUTOHEADER='${SHELL} tools/autotools.sh autoheader'
MAKEINFO='${SHELL} missing --run makeinfo'
export MISSING ACLOCAL AUTOCONF AUTOMAKE AUTOHEADER MAKEINFO

AM_INIT_AUTOMAKE([foreign -Wall -Werror])

dnl docker is checked, not required. The worker has no docker by design
dnl and still configures, regenerates and runs `make check`; docker work
dnl runs in the coordinator (run_command) or on the host. build.sh and
dnl tools/compose.sh check for docker when a target needs it.
AC_CHECK_PROG([DOCKER], [docker], [docker], [])
AS_IF([test -z "$DOCKER"],
      [AC_MSG_WARN([docker not found -- docker targets (build, start, image-check) must run through the coordinator or on the host])])

dnl docker compose (v2 plugin) or docker-compose (v1 binary) -- checked
dnl here only so a userland with NEITHER fails at configure time rather
dnl than partway through a build. The answer is deliberately NOT
dnl substituted into the Makefile any more: it is a property of the
dnl USERLAND, and this checkout is read by two boots and two container
dnl images with four different inventories. Machine and distribution
dnl are only proxies for that -- the coordinator and the host it runs
dnl on are one machine of one distribution and still disagree. A value
dnl frozen here is
dnl wrong everywhere except where configure ran (confirmed live
dnl 2026-08-25 -- see compose.sh's own header). compose.sh detects at
dnl invocation instead, and build.sh, start.sh and the Makefile all
dnl route through it.
AC_MSG_CHECKING([for docker compose (v2 plugin)])
AS_IF([test -n "$DOCKER" && "$DOCKER" compose version >/dev/null 2>&1],
      [have_compose_v2=yes], [have_compose_v2=no])
AC_MSG_RESULT([$have_compose_v2])
AC_CHECK_PROG([DOCKER_COMPOSE_V1], [docker-compose], [docker-compose], [])
AS_IF([test -n "$DOCKER" && test "x$have_compose_v2" = xno && test -z "$DOCKER_COMPOSE_V1"],
      [AC_MSG_WARN([neither 'docker compose' (v2) nor 'docker-compose' (v1) found -- compose targets will fail in this userland])])

dnl Substituting the compose command was REMOVED 2026-08-25. It was
dnl done here once at configure time, which is cheaper and looked
dnl idiomatic, but froze a per-userland fact into a file shared across
dnl userlands. compose.sh owns the detection now; nothing is AC_SUBST'd
dnl for it, and Makefile.am's COMPOSE points at that script.

dnl python3 is required to run the real committed test suite
dnl (server/test_bash_mcp_server.py) that `make check` runs -- not
dnl for building anything, this project ships pure Python source, not
dnl compiled output.
dnl
dnl Prefer nothing here: PYTHON3 is only the BASE interpreter venv-build.sh
dnl uses to create the venv `make check` runs in. It used to prefer a
dnl local .venv if one existed at configure time, which baked
dnl `./.venv/bin/python3` into the generated Makefile -- and a venv's
dnl own bin/python3 is a symlink to whatever created it, so the baked
dnl path is valid only in that one userland. Confirmed live 2026-08-25:
dnl exit 127 inside the coordinator container, whose image contains no
dnl such interpreter. venv-build.sh
dnl now keys a venv per userland and rebuilds one whose interpreter no
dnl longer runs -- see its own header.
AC_CHECK_PROG([PYTHON3], [python3], [python3], [])
AS_IF([test -z "$PYTHON3"],
      [AC_MSG_ERROR([python3 is required to run the test suite but was not found])])

dnl What `make check` needs from this interpreter is no longer "has
dnl every package in server/requirements.txt" -- venv-build.sh installs
dnl those into a per-userland venv at recipe time, and healing that is
dnl the whole point of it. What IS required is that this interpreter
dnl can CREATE a venv, which a stripped-down system python3 cannot
dnl (Debian-family splits ensurepip into python3-venv). Checking that
dnl here keeps the fail-fast property the old requirements check had,
dnl without freezing a package inventory taken in one userland into a
dnl Makefile read on four. The old check called
dnl server/check_requirements.py, which had no other caller and no
dnl tests; it was removed with this change rather than left in the tree
dnl as something that merely still works.
dnl
dnl This ACTUALLY CREATES a throwaway virtualenv rather than importing
dnl `ensurepip` and `venv` and calling that proof. Those imports are a
dnl proxy: they can both succeed while `python3 -m venv` still fails --
dnl a partially packaged ensurepip, a wheel bundle the split package
dnl was supposed to supply, a pip that cannot bootstrap. The whole
dnl point of this check is fail-fast, and a proxy that passes when the
dnl real thing would fail is worse than no check, because it moves the
dnl failure to `make check` while reporting success here. The probe
dnl builds into a mktemp -d directory of its own and removes only that.
AC_MSG_CHECKING([whether $PYTHON3 can create a virtualenv])
venv_probe_dir=`mktemp -d 2>/dev/null || echo ./conftest-venv-probe`
AS_IF(["$PYTHON3" -m venv "$venv_probe_dir/probe" >/dev/null 2>&1 && test -x "$venv_probe_dir/probe/bin/python3"],
      [AC_MSG_RESULT([yes])
       rm -rf "$venv_probe_dir"],
      [AC_MSG_RESULT([no])
       rm -rf "$venv_probe_dir"
       AC_MSG_ERROR([$PYTHON3 cannot create a virtualenv -- install the venv/ensurepip module for it (e.g. python3-venv on Debian-family) or point PYTHON3 at an interpreter that has it])])

dnl node/npm/npx are OPTIONAL -- only needed for the Desktop extension
dnl (`make build-extension`), which is itself optional; the core
dnl service doesn't need it to run. Matches build.sh's own SKIP (not
dnl FAIL) treatment of this exact gap, surfaced here as a configure-
dnl time warning instead of a hard error.
AC_CHECK_PROG([NODE], [node], [node], [])
AC_CHECK_PROG([NPM], [npm], [npm], [])
AC_CHECK_PROG([NPX], [npx], [npx], [])
AS_IF([test -z "$NODE" -o -z "$NPM" -o -z "$NPX"],
      [AC_MSG_WARN([node/npm/npx not found -- the Desktop extension build will be skipped; the core service does not need it])])

AC_CONFIG_FILES([Makefile])
AC_OUTPUT

AC_MSG_NOTICE([])
AC_MSG_NOTICE([Configured. Next: make && make check])
AC_MSG_NOTICE([`sudo make install` is optional -- it stages a SEPARATE, packaged copy under /usr/local/share/cicd-runner for distribution, not something an already-running checkout like this one needs for daily use.])
AC_MSG_NOTICE([(or, from this project's own richer interface: make help)])

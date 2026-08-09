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
AC_INIT([cicd-runner], [1.0.0], [https://github.com/arunasp/cicd_runner/issues])
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
MISSING='${SHELL} missing'
ACLOCAL='${SHELL} missing --run aclocal-1.16'
AUTOCONF='${SHELL} missing --run autoconf'
AUTOMAKE='${SHELL} missing --run automake-1.16'
AUTOHEADER='${SHELL} missing --run autoheader'
MAKEINFO='${SHELL} missing --run makeinfo'
export MISSING ACLOCAL AUTOCONF AUTOMAKE AUTOHEADER MAKEINFO

AM_INIT_AUTOMAKE([foreign -Wall -Werror])

dnl docker itself is not optional -- real docker-socket access is
dnl this whole project's reason to exist (see README's "Why this
dnl exists"). No point generating a Makefile that can't build anything.
AC_CHECK_PROG([DOCKER], [docker], [docker], [])
AS_IF([test -z "$DOCKER"],
      [AC_MSG_ERROR([docker is required but was not found -- see README.md])])

dnl docker compose (v2 plugin) or docker-compose (v1 binary) -- same
dnl lazy, either-is-fine detection philosophy as build.sh's own
dnl stage_coordinator() and the Makefile's stop/logs/status targets,
dnl surfaced here too so a missing compose entirely is caught at
dnl configure time, not partway through a build.
AC_MSG_CHECKING([for docker compose (v2 plugin)])
AS_IF(["$DOCKER" compose version >/dev/null 2>&1],
      [have_compose_v2=yes], [have_compose_v2=no])
AC_MSG_RESULT([$have_compose_v2])
AC_CHECK_PROG([DOCKER_COMPOSE_V1], [docker-compose], [docker-compose], [])
AS_IF([test "x$have_compose_v2" = xno], [
  AS_IF([test -z "$DOCKER_COMPOSE_V1"],
        [AC_MSG_ERROR([neither 'docker compose' (v2) nor 'docker-compose' (v1) found])])
])

dnl Substitute the actual compose command ONCE, here, at configure
dnl time -- not re-detected via $(shell ...) on every `make` call
dnl (automake's own -Wall -Werror correctly flags $(shell ...) as a
dnl non-POSIX GNU Make extension; this is the genuinely idiomatic fix,
dnl not a workaround -- also cheaper, since detection now happens once
dnl instead of on every stop/logs/status invocation). By this point
dnl either v2 or v1 is guaranteed present (the AS_IF block above
dnl already exits via AC_MSG_ERROR if neither is), so Makefile.am's
dnl targets that use @COMPOSE_CMD@ don't need their own empty-value
dnl guard either.
AS_IF([test "x$have_compose_v2" = xyes],
      [COMPOSE_CMD="docker compose"],
      [COMPOSE_CMD="docker-compose"])
AC_SUBST([COMPOSE_CMD])

dnl python3 is required to run the real committed test suite
dnl (server/test_bash_mcp_server.py) that `make check` runs -- not
dnl for building anything, this project ships pure Python source, not
dnl compiled output.
dnl
dnl Prefer a local .venv's own python3 if the project has one --
dnl isolates this project's host-side test dependencies (mcp, pytest)
dnl from the system/conda Python, avoiding exactly the "Defaulting to
dnl user installation because normal site-packages is not writeable"
dnl warning a bare system pip install produces (confirmed live
dnl 2026-08-08). Not auto-created by configure -- create one
dnl explicitly first if you want this path used:
dnl `python3 -m venv .venv && .venv/bin/pip install -r
dnl server/requirements.txt`. Falls back to whatever python3 is on
dnl PATH if no .venv exists, same detection as before.
AS_IF([test -x "$srcdir/.venv/bin/python3"],
      [PYTHON3="$srcdir/.venv/bin/python3"
       AC_MSG_NOTICE([using local .venv: $PYTHON3])],
      [AC_CHECK_PROG([PYTHON3], [python3], [python3], [])])
AS_IF([test -z "$PYTHON3"],
      [AC_MSG_ERROR([python3 is required to run the test suite but was not found])])

dnl `make check` runs server/test_bash_mcp_server.py directly on the
dnl HOST (testing the source before it's installed, not inside
dnl Docker) -- that module transitively needs every package in
dnl server/requirements.txt, not just python3 existing. Confirmed
dnl live 2026-08-08 in two separate rounds, found one package at a
dnl time as each surfaced its own fresh mid-build failure (pytest
dnl missing, then -- once that was fixed -- mcp missing one layer
dnl deeper). Rather than keep adding a new hardcoded per-package
dnl AC_MSG_CHECKING every time another one surfaces, check the WHOLE
dnl requirements.txt generically, once, via server/check_requirements.py
dnl -- any future addition to requirements.txt is covered
dnl automatically, no configure.ac edit ever needed again. That
dnl script was originally embedded directly here as inline Python,
dnl but M4 was found to strip literal `[`/`]` array-indexing syntax
dnl from code embedded inline (M4's own quote characters) -- moved to
dnl a real file, which sidesteps the quoting problem entirely and is
dnl independently testable on its own.
AC_MSG_CHECKING([whether server/requirements.txt is satisfied via $PYTHON3])
requirements_missing=`"$PYTHON3" server/check_requirements.py server/requirements.txt 2>&1`
requirements_status=$?
AS_IF([test "$requirements_status" -eq 0],
      [AC_MSG_RESULT([yes])],
      [AC_MSG_RESULT([no])
       AC_MSG_ERROR([server/requirements.txt not satisfied via '$PYTHON3' -- missing: $requirements_missing. Install via '$PYTHON3 -m pip install -r server/requirements.txt', or point PYTHON3 at a different interpreter that has it])])

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

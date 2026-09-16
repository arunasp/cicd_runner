#!/bin/sh
# Runs one Autotools program for the generated Makefile's regeneration
# rules, and regenerates everything when the installed Automake differs
# from the one that wrote aclocal.m4.
#
# aclocal.m4, configure and Makefile.in are per-userland (gitignored),
# while the checkout is shared between boots and containers. When
# Makefile.am alone changes, make runs only automake, which refuses an
# aclocal.m4 from another Automake release ("version mismatch").
# `autoreconf --install --force` replaces all generated files; make then
# reruns configure through config.status because configure is newer.
#
# Usage (from the source directory): tools/autotools.sh PROGRAM [ARGS...]
# A program that is not installed is handed to ./missing unchanged.
set -u

prog="$1"
shift

if ! command -v "${prog}" >/dev/null 2>&1; then
    exec "${SHELL:-/bin/sh}" ./missing --run "${prog}" "$@"
fi

installed="$(automake --version 2>/dev/null | sed -n '1s/.* //p')"
recorded=""
if [ -f aclocal.m4 ]; then
    recorded="$(sed -n 's/.*AM_AUTOMAKE_VERSION(\[\([0-9][0-9.]*\)\]).*/\1/p' aclocal.m4 | head -n 1)"
fi

if [ -n "${installed}" ] && [ -n "${recorded}" ] && [ "${installed}" != "${recorded}" ]; then
    echo "autotools: aclocal.m4 is from Automake ${recorded}, installed is ${installed}; running autoreconf --install --force" >&2
    exec env -u ACLOCAL -u AUTOCONF -u AUTOMAKE -u AUTOHEADER \
        autoreconf --install --force
fi

exec "${prog}" "$@"

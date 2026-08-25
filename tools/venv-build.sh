#!/bin/sh
# Builds the Python environment `make check` runs in when it needs
# building, and prints the interpreter's path on stdout. Everything else
# goes to stderr, so callers can use `py="$(tools/venv-build.sh ...)"`
# directly.
#
# THIS SCRIPT DOES NOT DECIDE ANYTHING. tools/venv-check.sh owns the
# decision and expresses it as an exit status; this one follows that
# status and nothing else. The split is deliberate: every bug in this
# logic's history was in the decision rather than in the building, and
# a decision that can only be reached by building something is a
# decision that is hard to test.
#
# The environment is DISPOSABLE. Nothing here inspects it for damage or
# repairs it in place -- stale means rebuilt from scratch, always the
# same way, whatever made it stale.
#
# Usage: tools/venv-build.sh [requirements.txt ...]
set -eu

# shellcheck disable=SC1007  # CDPATH= is an env prefix to cd, not an assignment
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
base_python=${PYTHON3:-python3}

if venv=$("${script_dir}/venv-check.sh" "$@"); then
    status=0
else
    status=$?
fi

case "${status}" in
    0)
        # Current. Nothing to do, and deliberately nothing printed to
        # stderr either -- the common case should be silent.
        printf '%s\n' "${venv}/bin/python3"
        exit 0
        ;;
    1)
        : # stale -- fall through and build
        ;;
    *)
        # 2 (no usable base interpreter) or 3 (a requirements file named
        # on the command line is missing). venv-check.sh has already said
        # which, on stderr, naming the thing at fault.
        exit "${status}"
        ;;
esac

signature=$("${script_dir}/venv-check.sh" --signature "$@")
py="${venv}/bin/python3"
stamp="${venv}/.venv-stamp"
manifest_file="${venv}/.venv-manifest"

echo "venv-build: rebuilding ${venv}" >&2
# The stamp is removed FIRST and written LAST. Anything that fails in
# between -- an interrupted pip, a full disk -- therefore leaves an
# environment with no signature, which the next run treats as stale. A
# stamp written early would mark a half-installed environment as good.
# The manifest goes just before it, for the same reason and in the same
# order: it records what this build actually produced, so that later
# drift inside the environment is visible.
rm -f "${stamp}" "${manifest_file}"
# --clear empties it in place rather than unlinking a directory this
# script may not have created.
"${base_python}" -m venv --clear "${venv}" >&2
for req in "$@"; do
    echo "venv-build: installing ${req}" >&2
    "${py}" -m pip install -q -r "${req}" >&2
done
"${script_dir}/venv-check.sh" --manifest "$@" >"${manifest_file}"
printf '%s\n' "${signature}" >"${stamp}"

# FINISHED MEANS VERIFIED: ask the same tool again rather than assuming
# the build did what it was supposed to. If it still reports stale,
# something is wrong with the signature logic itself, and reporting
# success here would hide it behind a rebuild on every subsequent call.
if ! "${script_dir}/venv-check.sh" "$@" >/dev/null; then
    echo "venv-build: rebuilt ${venv} but it still reports stale" >&2
    exit 1
fi

printf '%s\n' "${py}"

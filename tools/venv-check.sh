#!/bin/sh
# Decides whether the Python environment `make check` runs in is CURRENT,
# and says so through its exit status. It never creates, installs,
# modifies or deletes anything -- ask it as often as you like.
#
# EXIT STATUS is the interface. Everything else follows from it:
#
#   0  current   -- the environment exists and matches its signature
#   1  stale     -- it is absent, broken, or was built from something
#                   that has since changed; the caller should rebuild
#   2  no base   -- the base interpreter itself does not run; nothing
#                   can be built until that is fixed
#   3  bad input -- a requirements file NAMED ON THE COMMAND LINE is
#                   not there, which is a mistake in the caller rather
#                   than a fact about the environment
#
# STDOUT is the path of the virtualenv it is talking about, printed for
# every status where one can be named (0 and 1), so a caller never has
# to re-derive it and cannot derive it differently. Reasons go to
# stderr. With --signature it prints the signature it computed instead
# and exits 0, and with --manifest it prints the environment's current
# installed set; both are how a builder records what it built.
#
# WHY THIS IS A SEPARATE TOOL: the decision used to live inside the
# script that also did the building, and every bug this file exists to
# prevent was a bug in the decision, not in the building -- a base
# interpreter that had gone missing, a base that existed but was the
# wrong one, a `pyvenv.cfg` field that recorded the path an interpreter
# was invoked through rather than the resolved one, and a signature
# comparison that differed by a trailing newline. Two of those shipped.
# Separated out, the decision can be exercised directly and cheaply,
# without building anything to find out what it would have decided.
#
# THE MODEL IS CCACHE, NOT MAKE. Make and gcc drive rebuilds from
# TIMESTAMPS; ccache hashes the compiler binary, its version, the flags
# and the preprocessed source, precisely because timestamps are the
# wrong input. Here the requirements files are hashed by content for
# the same reason, and more specifically because this checkout is read
# from more than one boot and lives under git -- a clone, a branch
# switch or a checkout rewrites mtimes without changing a byte, and two
# operating systems on one disk need not agree about the clock.
#
# WHAT THE SIGNATURE COVERS, and why each is in it:
#   - the base interpreter's resolved path, full version and prefix --
#     one userland routinely holds several interpreters (a system
#     python3, a distribution-packaged conda, a separate one under
#     /opt, a pyenv build), and switching between them must not
#     silently reuse another's environment;
#   - a CONTENT HASH of the interpreter binary itself. This is ccache's
#     `compiler_check`: the same version string can name a different
#     binary after a rebuild or a security update, and a venv's
#     compiled extensions are linked against that binary's ABI. Path
#     and version alone cannot see an in-place reinstall;
#   - the userland's ID, version and architecture -- compiled wheels
#     link against that userland's libraries and do not travel;
#   - the C library version -- the userland ID does not change when
#     glibc is upgraded underneath a rolling release, but a wheel built
#     against the old one may stop loading;
#   - the CONTENT of every requirements file TRANSITIVELY REACHABLE
#     from the ones named, see below.
#
# DEPENDENCY DISCOVERY, which is gcc's `-MMD` idea. A signature is only
# as good as its list of inputs, and a hand-written list is a rule
# someone has to remember -- exactly the kind of rule that decays. pip
# lets a requirements file pull in others with `-r` and `-c`, so the
# files actually read are discovered here by following those
# directives transitively, rather than trusted to whoever wrote the
# `make deps` command line. Without this, factoring requirements into a
# shared base file would silently put a real input outside the checked
# set -- the same failure class this whole file exists to remove.
#
# AND THE `-MP` DISTINCTION, which is worth keeping separate: gcc emits
# phony targets for headers so that DELETING one causes a rebuild
# rather than a hard error. Same split here. A file named on the
# command line that is missing is a caller error (exit 3, loud). A
# discovered file that is missing is a CHANGE -- somebody inlined or
# removed it -- so it is recorded as missing, which alters the
# signature and rebuilds.
#
# TWO RECORDED FILES, ANSWERING DIFFERENT QUESTIONS. The signature is
# what the environment was built FROM, and stale means an input
# changed. The manifest is what the build PRODUCED -- the set of
# installed distributions -- and stale means the environment itself
# drifted: a package installed by hand, or removed by hand. That is
# `rpm -V` rather than anything in make or gcc, and it is deliberately
# not folded into the signature: requirements pinned loosely resolve to
# whatever is current at install time, so a recomputed set legitimately
# differs from a recorded one and only a RECORDED-versus-NOW comparison
# means anything.
#
# Usage: tools/venv-check.sh [--signature|--manifest] [requirements.txt ...]
set -eu

mode=check
case "${1-}" in
    --signature) mode=signature; shift ;;
    --manifest)  mode=manifest;  shift ;;
esac

# shellcheck disable=SC1007  # CDPATH= is an env prefix to cd, not an assignment
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# The cache belongs to the CHECKOUT, not to this script's directory.
# This script lives in tools/, so deriving the cache from script_dir
# alone would silently name tools/.venv-cache/ -- a second, invisible
# cache beside the real one.
#
# THE DEFAULT IS PROJECT-NEUTRAL ON PURPOSE. This script is meant to be
# copied into any project that has a virtualenv, so a default naming
# one particular project's cache directory would arrive in every copy
# and be wrong in all but one. Projects wanting it elsewhere set
# VENV_ROOT; cicd_runner does exactly that, from its own Makefile.
# shellcheck disable=SC1007  # CDPATH= is an env prefix to cd, not an assignment
repo_root=$(CDPATH= cd -- "${script_dir}/.." && pwd -P)
base_python=${PYTHON3:-python3}

# ONE invocation for every fact that needs the interpreter, including
# the requirements expansion. It doubles as the check that the
# interpreter runs at all. The expansion is done here rather than in
# shell because following `-r`/`-c` transitively means recursion,
# relative-path resolution against each including file, comment
# stripping and cycle detection -- POSIX shell can do all of that and
# would be a bug farm doing it.
#
# os.confstr returns None where there is no glibc (musl, notably),
# which is itself a distinguishing answer and so belongs in the
# signature.
if ! probe=$("${base_python}" - "$@" <<'PY' 2>/dev/null
import hashlib, os, sys

exe = os.path.realpath(sys.executable)
digest = hashlib.sha256()
try:
    with open(exe, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    exe_hash = digest.hexdigest()
except OSError:
    # An interpreter whose own binary cannot be read is a fact worth
    # recording rather than a reason to fail: it still runs.
    exe_hash = "unreadable"

print(exe)
print("%d.%d.%d" % sys.version_info[:3])
print(sys.prefix)
print(os.confstr("CS_GNU_LIBC_VERSION") or "no-glibc")
print(exe_hash)
print("--")

seen = set()
order = []
FLAGS = ("--requirement", "--constraint", "-r", "-c")


def visit(path, named):
    path = os.path.normpath(path)
    if path in seen:
        return
    seen.add(path)
    order.append((named, path))
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return
    base = os.path.dirname(path)
    for line in lines:
        line = line.split("#", 1)[0].strip()
        for flag in FLAGS:
            if line.startswith(flag + "=") or line.startswith(flag + " "):
                target = line[len(flag):].lstrip("= ").strip()
                if target:
                    visit(target if os.path.isabs(target)
                          else os.path.join(base, target), False)
                break


for arg in sys.argv[1:]:
    visit(arg, True)
for named, path in order:
    print(("named " if named else "found ") + path)
PY
); then
    echo "venv-check: base interpreter '${base_python}' does not run" >&2
    exit 2
fi

base_info=$(printf '%s\n' "${probe}" | sed -n '1,5p')
base_real=$(printf '%s\n' "${probe}" | sed -n 1p)
base_ver=$(printf '%s\n' "${probe}" | sed -n 2p)
req_list=$(printf '%s\n' "${probe}" | sed -n '/^--$/,$p' | sed 1d)

# ID/VERSION_ID come from os-release where there is one; the fallbacks
# keep this working in a container image that ships none.
os_id=unknown
os_ver=0
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091  # not a file shellcheck can follow
    . /etc/os-release
    os_id=${ID:-unknown}
    os_ver=${VERSION_ID:-0}
fi
arch=$(uname -m)

# The directory name is for HUMANS -- enough to tell two of them apart
# in a listing. Correctness comes from the signature inside, not from
# the name, so the name can stay readable rather than becoming a hash.
# cksum is POSIX and this is a cache key, not a security boundary.
digest=$(printf '%s' "${base_real}" | cksum | cut -d' ' -f1)
tag="${os_id}-${os_ver}-${arch}-py${base_ver}-${digest}"

venv="${VENV_ROOT:-${repo_root}/.venv-cache}/${tag}"
py="${venv}/bin/python3"
stamp="${venv}/.venv-stamp"
manifest_file="${venv}/.venv-manifest"

# The installed set, canonicalised so that a comparison cannot fail for
# cosmetic reasons: names lowercased with `_` and `.` folded to `-` per
# PEP 503, duplicates collapsed, sorted. Uses importlib.metadata rather
# than `pip freeze` -- the same information without paying pip's
# startup on every check, and without freeze's `-e` and `file://`
# forms, which vary in ways that would make a stable comparison harder
# than it needs to be. A mismatch here must be a real difference, or
# this becomes the fourth rebuild-on-every-call bug in this logic.
manifest_now() {
    "${py}" -c 'import importlib.metadata as md
found = set()
for dist in md.distributions():
    name = (dist.metadata["Name"] or "").strip()
    if not name:
        continue
    canon = "".join("-" if ch in "_." else ch for ch in name.lower())
    found.add(canon + "==" + (dist.version or "0"))
print("\n".join(sorted(found)))' 2>/dev/null
}

# Hashed as a single stream, in discovery order, with each file's name
# in it, so that reordering, renaming, adding or REMOVING one all
# change the signature. Removal matters: dropping a requirements file
# used to leave its packages installed forever, since a per-file
# sentinel that is never consulted again cannot notice its own absence.
reqs_sig=""
old_ifs=$IFS
IFS='
'
for entry in ${req_list}; do
    IFS=${old_ifs}
    origin=${entry%% *}
    req=${entry#* }
    if [ -f "${req}" ]; then
        reqs_sig="${reqs_sig}${req}:$(cksum <"${req}" | cut -d' ' -f1,2)
"
    elif [ "${origin}" = named ]; then
        echo "venv-check: no such requirements file: ${req}" >&2
        exit 3
    else
        # The -MP case: a discovered include that has gone away is a
        # change, not a fault.
        reqs_sig="${reqs_sig}${req}:missing
"
    fi
    IFS='
'
done
IFS=${old_ifs}

signature="interpreter=${base_info}
userland=${os_id}-${os_ver}-${arch}
requirements=
${reqs_sig}"
# Normalised through a command substitution, which strips trailing
# newlines -- exactly what `$(cat "${stamp}")` does to the stored copy
# on the way back in. Comparing an unnormalised string against a
# normalised one differs by a single trailing newline and NEVER
# matches, which reports every environment stale forever. That bug has
# appeared three times in this logic's history; it is the reason the
# comparison is in one place now.
signature=$(printf '%s' "${signature}")

if [ "${mode}" = signature ]; then
    printf '%s\n' "${signature}"
    exit 0
fi

if [ "${mode}" = manifest ]; then
    if [ ! -x "${py}" ]; then
        echo "venv-check: no environment to take a manifest of" >&2
        exit 1
    fi
    manifest_now
    exit 0
fi

printf '%s\n' "${venv}"

# Two questions, and only two. The stamp answers "was it built from
# this?"; running the interpreter answers "is it still there at all?",
# which the stamp cannot know because a stamp survives a half-deleted
# directory. The manifest then answers "is it still what the build
# produced?" -- drift inside the environment, which neither of the
# others can see.
if [ ! -x "${py}" ]; then
    echo "venv-check: stale -- absent, or its interpreter does not run" >&2
    exit 1
fi
if [ ! -f "${stamp}" ]; then
    echo "venv-check: stale -- no signature recorded" >&2
    exit 1
fi
if [ "$(cat "${stamp}")" != "${signature}" ]; then
    echo "venv-check: stale -- what it was built from has changed" >&2
    exit 1
fi
if [ ! -f "${manifest_file}" ]; then
    echo "venv-check: stale -- no manifest recorded" >&2
    exit 1
fi
if [ "$(cat "${manifest_file}")" != "$(manifest_now)" ]; then
    echo "venv-check: stale -- its installed packages no longer match the build" >&2
    exit 1
fi
exit 0

#!/bin/sh
# THROWAWAY debug script -- not part of the real image/build. Delete
# after use.
#
# Manual, step-by-step debug of the worker's uid-switching mechanism --
# run each piece separately so we see EXACTLY which one fails and how,
# rather than only seeing the final composed "setpriv: failed to
# execute git: Resource temporarily unavailable" error.
#
# Run directly against the worker image, bypassing entrypoint.sh
# entirely (so this runs as root first, each step reporting its own
# exit code independently):
#
#   docker run --rm -v "$(pwd)/tools/debug_worker.sh:/debug.sh" --entrypoint sh cicd-worker /debug.sh
set -x

echo "=== 1. confirm baked-in user exists ==="
id worker
getent passwd 1000
getent passwd worker

echo "=== 2. confirm binary itself is sane ==="
ls -la /usr/bin/git
file /usr/bin/git 2>/dev/null || echo "(file not installed, skipping)"

echo "=== 3. try setpriv exactly as entrypoint.sh does ==="
setpriv --reuid=1000 --regid=1000 --clear-groups --reset-env git --version
echo "setpriv exit code: $?"

echo "=== 4. try setpriv with NO --reset-env (isolate whether reset-env itself is the trigger) ==="
setpriv --reuid=1000 --regid=1000 --clear-groups git --version
echo "setpriv (no reset-env) exit code: $?"

echo "=== 5. try su instead of setpriv (different mechanism entirely) ==="
su worker -c "git --version"
echo "su exit code: $?"

echo "=== 6. try runuser instead (another different mechanism) ==="
runuser -u worker -- git --version
echo "runuser exit code: $?"

echo "=== 7. try setpriv on a trivial static binary instead of git (rule out git/dynamic-linking specifically) ==="
setpriv --reuid=1000 --regid=1000 --clear-groups --reset-env /bin/true
echo "setpriv /bin/true exit code: $?"

echo "=== 8. try setpriv switching to root explicitly (uid 0) as a sanity baseline ==="
setpriv --reuid=0 --regid=0 --reset-env git --version
echo "setpriv as root exit code: $?"

echo "=== DONE ==="

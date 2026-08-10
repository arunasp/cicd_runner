# Troubleshooting

Symptom to cause. Check the cause before changing anything -- most of these
look like a broken pipeline and are actually an environment assumption.

## Contents

- [Reachability and invocation](#reachability-and-invocation)
- [Missing tools and permissions](#missing-tools-and-permissions)
- [Make and include problems](#make-and-include-problems)
- [Dependency and caching problems](#dependency-and-caching-problems)
- [Transfer problems](#transfer-problems)
- [Results that look wrong](#results-that-look-wrong)

## Reachability and invocation

| Symptom | Likely cause | Check |
|---|---|---|
| Directory refused | Not covered by any ACL route | Is it in the client's allowed-directories setting? |
| Project not found by name | Named mount not configured | Does a mount exist for it, or should this be a directory call? |
| Binary refused | Not on the relevant allowlist | Which list applies -- coordinator or worker? They differ |
| Path resolves nowhere | Relative path is anchored above the project | Paths resolve relative to the runner's parent, not your cwd |

## Missing tools and permissions

Resolve a missing tool through the dependency manifest first. Reaching for an
image rebuild is a last resort, correct only for what the pipeline cannot
install unprivileged into the project tree.

| Symptom | Likely cause | Check |
|---|---|---|
| Command not found *inside* the run | Not provided by the pipeline; the allowlist is irrelevant for child processes | Is it declared in the dependency manifest and installed into the cached project-local environment? Only if the pipeline could not install it unprivileged is the image the right place |
| A manifest-declared tool is still not found | Installed somewhere ephemeral, or the environment is not on the invocation path | Is the environment on the bind mount, and are commands run through it rather than the system interpreter? |
| Permission denied writing outside the project | Unprivileged uid | Is the target inside the bind mount? |
| Docker command fails | No Docker CLI in the worker, by design | Move the stage coordinator-side or human-side |
| Files appear owned by root | Ran without the uid mapping | Were the uid/gid variables set? |
| Git complains about dubious ownership | Container recreated, `safe.directory` reset | Re-apply it; it lives in the container, not the mount |

## Make and include problems

| Symptom | Likely cause | Check |
|---|---|---|
| `overriding recipe for target 'help'` | Vendored and image-baked fragments both included | Add the `ifeq` guard -- but only at the repo root |
| Include silently does nothing | `../` sibling path, inside a single-directory mount | Use the image-baked path instead |
| Order-only prerequisite ignored; directory never created | A phony target shares a name with a directory | Rename one, or `mkdir -p` inside the recipe |
| Target always re-runs | A sentinel file was listed in `.PHONY` | Remove it; sentinels must be real files |
| Recipe line not recognised | Leading spaces instead of a TAB | Retype the indentation |

## Dependency and caching problems

| Symptom | Likely cause | Check |
|---|---|---|
| `externally-managed-environment` | PEP 668 on a system Python | Install into a project-local virtual environment |
| Dependencies reinstall every call | Installed inside the container rather than the mount | Is the environment on the bind mount? |
| Manifest changed but nothing reinstalled | Stale sentinel | Is the manifest a prerequisite of the sentinel? |
| Offline install still hits the network | Offline flags not engaging | Does the store actually contain matching artifacts? |
| Cache present but build still slow | Cache key does not match | Is it keyed on the manifest's contents? |

## Transfer problems

| Symptom | Likely cause | Check |
|---|---|---|
| Binary file arrives corrupted | The connector writes UTF-8 only | Use base64 text and decode on the far side |
| Decode fails on padding | Trailing whitespace counted as data by strict validation | Strip whitespace before decoding |
| Digest mismatch | Payload truncated or altered in transit | Re-pack and re-send; never extract unverified bytes |
| Unpack script not found | It was left outside the mounted directory | It must sit beside the payload |

## Results that look wrong

| Symptom | Likely cause | Check |
|---|---|---|
| Green locally, red on the target | The local environment supplied something invisibly | Compare tool versions, paths, uid |
| Green on the target, red locally | The target is missing something the local run has | The target is usually the more honest of the two |
| A stage never fails | It asserts nothing | Break its input deliberately; if still green, it is decoration |
| Test asserts the wrong invariant | The test encodes an assumption the code never made | Verify the real contract before "fixing" working code |
| Warnings on stderr, exit code 0 | A real misconfiguration that does not fail the build | Fix it; do not report the run as clean |

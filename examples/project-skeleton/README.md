# Project skeleton

Copy `Makefile` into a new project's root and fill in each target's
recipe with that project's real commands. This is deliberately
minimal, not a copy of LocusAI's own multi-stage `tools/pipeline.sh` --
that's a real, project-specific runner (Docker build/deploy/verify
against its own MCP service); this skeleton is just the standard
target *names*, so any project can adopt them at whatever complexity
actually fits.

Every stub target fails loudly (`exit 1`) rather than silently
"passing" -- confirmed live before this was written, so an unfilled
skeleton can never be mistaken for a working pipeline.

Once real commands are in place, the project works with `cicd_runner`
immediately, no changes needed there:

```
run_command(project="<name>", binary="make", args=["lint"])
run_in_directory(relative_path="<name>", binary="make", args=["lint"])
```

(`run_command` needs the project added as a named mount first --
see cicd_runner's own README, "Adding a new named project". Just
needs to exist under `DYNAMIC_ROOT` for `run_in_directory`.)

If a target's real command needs a binary not already in
`server/allowlist.txt`, add it there first (with a comment explaining
why) -- needs an image rebuild (both coordinator and worker) to take
effect.

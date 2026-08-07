# cicd-runner

A single, project-agnostic CI/CD execution container shared across
every project under `~/stuff/` (LocusAI, opencode-model-eval,
opencode-plugin-ctx-squid, ...), exposed as an MCP tool the same way
LocusAI's own `tools/server/` is.

## Why this exists

LocusAI's own `tools/pipeline.sh` documents a real, structural
limitation: `build`/`server`/`verify` need a real Docker daemon, but
`docker`/`npm`/`npx` are deliberately NOT in LocusAI's own
`allowlist.txt`. That's not an oversight -- a project's own container
cannot safely rebuild itself: the RPC connection serving the rebuild
request (`bash_mcp_server.py` inside that same container) dies
mid-rebuild the moment `docker compose up -d` recreates it. Confirmed
live during that project's own build-out (2026-08-07): a `chmod` call
through that connector hung for ~4 minutes right after a `server`
stage ran, for exactly this reason.

This container sidesteps that by being a genuinely separate process
from every project it builds: runner (container A) acts on project
(container B). No self-rebuild, no chicken-and-egg.

## Design decisions, and why

- **One dedicated container holds `/var/run/docker.sock`, not each
  project's own service.** Docker-socket access is root-equivalent on
  the host -- there's no way to grant "just enough" of it. Given that,
  the right move is concentrating it into one small, purpose-built,
  easy-to-audit container, rather than spreading it across every
  project's own service (which would also reintroduce the
  self-rebuild problem above, since a project's own container would
  then have real docker access to itself).
- **Manually triggered only -- no webhooks, no git hooks, no polling.**
  Considered and rejected:
  - A hosted CI product with GitHub integration (Woodpecker/Drone/
    Jenkins) -- rejected because GitHub isn't actually part of the
    real workflow here (backup/public-mirror only), so adopting a
    tool whose entire trigger/auth model IS the forge relationship
    (OAuth app, webhooks, commit-status writeback) would mean running
    it for a relationship that doesn't exist.
  - Local git hooks (`post-commit`/`post-merge`) or a polling loop
    watching each project's `HEAD` -- both explicitly rejected
    (Arunas's own call, 2026-08-07): "primed for race conditions."
  Manual (`run_command` through this MCP server, or a plain host
  shell) is the deliberately boring, race-free choice.
- **Each project gets its own named mount under `/projects/<name>`**,
  not one shared bind mount -- `run_command` takes a `project`
  argument, validated against the real mounted directories (rejects
  path traversal and symlink escapes -- see
  `bash_mcp_server.py`'s `_resolve_project_dir()`).
- **One shared `allowlist.txt`, not per-project.** `docker` being
  allowlisted already sets this container's privilege ceiling; every
  other entry (`git`, `gh`, `node`, `npm`, `shellcheck`, ...) is
  narrower than that, so a shared list doesn't raise the actual
  ceiling per project -- same reasoning LocusAI's own `allowlist.txt`
  already documents for its narrower set.
- **No ssh key / git credentials mounted here.** Projects that need
  `git push` (LocusAI already does) keep that in their OWN container,
  where it's already built, tested, and scoped to that one repo.
  Duplicating credentials into a second, broader-privileged container
  for no added capability isn't worth the extra exposure.

## Setup

```bash
cp .env.example .env   # fill in real project paths
./start.sh
```

## Adding a new project

1. Add a line to `.env` (path) and a matching volume line in
   `docker-compose.yml` (`${YOUR_VAR}:/projects/<name>`).
2. Add any binary its pipeline needs to `allowlist.txt`, with a
   comment explaining why (same convention as LocusAI's own).
3. `./start.sh` again to rebuild/relaunch.

No `bash_mcp_server.py` changes needed -- `list_projects()` discovers
mounted projects dynamically from what's actually under `/projects`.

## Usage

```
list_projects()
run_command(project="LocusAI", binary="docker", args=["compose", ...])
```

or, to run a project's own pipeline end-to-end:

```
run_command(project="LocusAI", binary="bash", args=["tools/pipeline.sh", "all"])
```

(`bash` itself would need adding to `allowlist.txt` for that specific
form -- currently `docker`/`git`/etc. are called directly, not via a
shell, matching `run_command`'s own "no shell invoked" design.)

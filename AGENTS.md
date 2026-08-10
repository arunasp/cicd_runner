# Notes for coding agents

This repository ships reusable **skills** — self-contained instruction sets
that encode how to work with this project correctly. Load the relevant one
before doing anything non-trivial here; they exist because generic CI/CD
knowledge does not transfer cleanly to this runner's mount model and
privilege split, and assuming otherwise produces confidently wrong work.

## Available skills

Browsable source of truth, readable directly without unpacking:

| Skill | Read it when |
|---|---|
| [`skills/opencode/docker-cicd-runner/SKILL.md`](skills/opencode/docker-cicd-runner/SKILL.md) | Running any pipeline stage through this runner, changing a Makefile it executes, designing a pipeline from scratch, or debugging why something that works locally fails inside a worker |
| [`skills/opencode/docker-run-as-host-user/SKILL.md`](skills/opencode/docker-run-as-host-user/SKILL.md) | Running a container as a specific host uid:gid, or debugging root-owned files and exec failures that only appear with `--user` set |

`docker-cicd-runner` carries further reference files under its own
`references/` directory: a standard operating procedure to follow before
running anything, canonical templates, a zero-to-full-integration design
guide, per-ecosystem dependency guidance, and symptom-to-cause
troubleshooting tables. Its `SKILL.md` says when to open each.

## Formats

The same skills are published twice, from one source:

- `skills/opencode/<name>/` — unpacked trees, readable in the repository and
  loadable by agents that read plain files.
- `skills/claude/<name>.skill` — packaged bundles installable into a Claude
  account.

`make skills-check` proves the two are byte-identical and fails the build if
they drift, so either copy can be trusted. It runs as part of `make check`.

## Ground rules for this repository

- Read `README.md` before changing behaviour; it is maintained and accurate.
- The `Makefile` is the pipeline definition. Add stages there, not as ad-hoc
  command sequences at call time.
- Verify claims against the source rather than recalling them. This project's
  history is full of assumptions that turned out to be locally false.
- Anything touching `Makefile.am` or `configure.ac` needs Autotools
  regeneration on a real host afterwards.

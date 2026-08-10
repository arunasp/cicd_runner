# Designing a pipeline: zero to full integration

Generic guidance, independent of any particular runner. Read this when
starting a project with no automation, when deciding what to add next, or
when asked to "set up CI/CD" for something that currently has none.

## Contents

- [The ladder](#the-ladder) -- seven levels, what each buys
- [Choosing stage boundaries](#choosing-stage-boundaries)
- [Design rules that survive any tooling](#design-rules-that-survive-any-tooling)
- [Common failure patterns](#common-failure-patterns)

## The ladder

Each level is only worth adding once the one below it is boringly reliable.
Climbing early produces automation that people route around, which is worse
than none: it costs time and provides false assurance.

### Level 0 -- commands in a human's head

Someone knows the incantations. They differ per person and drift silently.
Failure mode: "works on my machine" is not detectable, because there is no
second machine.

### Level 1 -- the pipeline becomes a file

One file in the repo defines every stage. A Makefile is enough; the tool
matters far less than the fact that the definition is versioned, reviewable
and singular.

Adopt a standard target vocabulary -- `lint test build deploy verify e2e all`
is a reasonable one -- so that every project answers the same questions the
same way. Make each target self-documenting so `help` is generated rather
than maintained.

Buys: repeatability, one place to change, and the ability to hand the whole
pipeline to something else later without rewriting it.

**Done when** a newcomer can run one command and get the same result you do.

### Level 2 -- dependencies become explicit and cached

Declare dependencies in a manifest rather than assuming they are installed.
Install them into a project-local location, not a shared system one, so that
two projects cannot fight and an unprivileged environment can still install.

Gate installation behind a sentinel file whose prerequisite is the manifest,
so an unchanged manifest costs nothing. Cache in layers: a shared package
cache avoids re-downloading, a project-local environment avoids
re-installing, and a resolved offline store (a wheelhouse or lockfile plus
vendored packages) removes the network entirely.

Buys: the same result on a machine that is not yours, and fast repeat runs.

**Done when** a clean checkout on a different machine reaches green without
manual setup, and a second run is near-instant.

### Level 3 -- it runs somewhere other than your own shell

Execute the same targets in a container, a VM, or a runner. Change nothing
about the definition; only the place it runs.

This is the first level that produces genuinely new information, because it
is the first that can disagree with you. Expect it to fail the first time
over things your shell provided invisibly: a tool on your `PATH`, a
credential in your environment, a file above the project root.

Buys: proof the pipeline does not depend on your local environment.

**Done when** the remote run and the local run agree, and you believe the
remote one when they do not.

### Level 4 -- something other than a person triggers it

A git hook, a scheduler, or a hosted service watching the repository. Until
this exists there is no "continuous" anything: a green result describes the
moment someone chose to run it, not the current state of the tree.

Start with the cheapest useful trigger. A `pre-push` hook running lint and
tests catches most of what matters and needs no infrastructure. Hosted CI on
push and pull request is the fuller answer.

Buys: the tree's status becomes a known fact rather than a memory.

**Done when** nobody has to remember to run anything.

### Level 5 -- results gate the merge

Make the checks required. Until a red result actually blocks something, it is
advisory, and advisory checks decay into ignored ones.

Buys: green stops being information and becomes a precondition.

**Done when** merging past a red check requires a deliberate, visible
override.

### Level 6 -- release becomes a stage

Tagging, versioning, changelog, and a build artifact identified by version.
Build the artifact **once** and promote that same artifact through
environments -- rebuilding per environment means what you tested is not what
you shipped.

Buys: the ability to say exactly what is running and to go back to what ran
before.

**Done when** a version string maps to one immutable artifact and one commit.

### Level 7 -- deploy, operate, monitor

Automated deployment, health checks, and monitoring that feeds back into
planning. This closes the loop that makes the whole thing a cycle rather than
a line.

Buys: the pipeline learns from production instead of ending at it.

**Done when** a production signal can open work without a human noticing it
first.

## Choosing stage boundaries

**Order by cost of failure, cheapest first.** Lint before tests before build
before deploy. Every stage that fails late wastes everything the earlier ones
spent.

**A stage must be able to fail.** If you cannot describe an input that turns
it red, it is decoration -- delete it or give it a real assertion. This is
the most common defect in hand-rolled pipelines.

**One concern per stage.** A stage that both builds and publishes cannot be
re-run safely after a partial failure.

**Every stage runs standalone.** `make test` without `make all` must work.
Otherwise debugging means running everything.

**Exit codes are the interface.** Not log text, not a printed summary. Text
is for humans; the exit code is the contract.

## Design rules that survive any tooling

**Same definition everywhere.** Local, container, and hosted CI must invoke
the *same* targets. The moment CI has its own copy of the commands, the two
drift and one passes while the other fails.

**Determinism over convenience.** Pin versions. Avoid network access in
tests. A pipeline that fails intermittently trains people to re-run it until
it is green, which destroys its value entirely.

**Idempotence.** Running a stage twice must be safe. Assume every stage will
be re-run after a partial failure, because it will be.

**Cache only what is derivable.** Caching an artifact you can rebuild is an
optimisation; caching something authoritative is a correctness bug waiting to
surface. A stale cache must never be able to produce a green run.

**Secrets never live in the definition.** Injected at runtime, never
committed, never echoed. A pipeline file is a public artifact even in a
private repository.

**Fail loudly, never silently.** A step that swallows an error and continues
is worse than no step. Prefer a hard failure over a warning nobody reads.

**Keep it fast enough to be run.** A pipeline slow enough to bypass will be
bypassed. Speed is a correctness property, not a luxury.

## Common failure patterns

**The unfailable stage.** Present, always green, asserts nothing. Test it by
deliberately breaking its input; if it stays green, it was never a stage.

**Drifted duplicate definitions.** CI has its own script, the Makefile has
another. They diverge, and each is used to excuse the other's failure.

**Green means stale.** A pipeline invoked by hand reports the last time
someone ran it. Without a trigger this is unavoidable, so say so plainly
rather than treating an old green as current.

**Cache masking a real break.** A dependency change is not picked up because
a stale sentinel or cache key still matches. Verify that a manifest change
actually forces re-resolution.

**Deploy inside the default target.** Convenient until the default target
runs somewhere unprivileged, or twice. Keep side-effecting stages out of the
target people run casually.

**Rebuilt-per-environment artifacts.** What was tested and what shipped are
different builds. Build once, promote the same bytes.

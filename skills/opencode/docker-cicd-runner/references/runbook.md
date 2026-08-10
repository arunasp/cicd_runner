# Standard operating procedure

Follow this order every time. The point is not ceremony -- it is that two
different readers of this skill, on two different days, produce the same
sequence of actions and the same shape of report.

## Contents

- [Pre-flight](#pre-flight)
- [Execution order](#execution-order)
- [Batching](#batching)
- [Reporting](#reporting)
- [Language rules for claims](#language-rules-for-claims)
- [When to stop and ask](#when-to-stop-and-ask)

## Pre-flight

Before running anything, establish these five facts. Guessing any of them
produces confidently wrong work.

1. **Which tool reaches the target.** Named mount, or directory ACL? If the
   ACL, is the directory actually permitted?
2. **What the target's pipeline definition is.** Read the Makefile. Do not
   infer targets from their names.
3. **Which stages can run where.** Anything needing a Docker daemon cannot
   run in an unprivileged worker.
4. **How each dependency is provided.** The allowlist governs the entry
   binary only. Everything that binary invokes is either declared in the
   project's dependency manifest and installed into a cached, project-local
   environment -- which is where it should be -- or baked into the image,
   which is only correct for what the pipeline cannot install unprivileged
   into the project tree. Check the manifest before concluding anything
   about the image.
5. **Whether a cheaper source answers the question.** If the repository is
   public and its working tree is clean and pushed, clone it locally and
   grep there instead of spending remote calls.

## Execution order

1. **Develop and verify in the sandbox first.** It is faster, costs no
   remote calls, and catches ordinary mistakes.
2. **Then run on the real target**, batched.
3. **Treat disagreement as information, not noise.** The real run can see
   conditions the sandbox cannot reproduce -- co-located files, real
   permissions, real uid. When they disagree, the real run is right.
4. **Re-run after fixing.** A fix is not verified until the original symptom
   is retested and observed gone. A plausible root cause is not a
   verification.

## Batching

Remote calls are the expensive resource. Combine them:

- Multiple targets in one invocation (`make lint test`) rather than one call
  each.
- Read several files in one call where the tool supports it.
- Prefer one script that runs a whole sequence and reports at the end over
  many round-trips issuing one command each.

Do not batch when a later step's *shape* depends on an earlier step's
result. Batching a decision you have not made yet just produces a wrong
command faster.

## Reporting

Every pipeline run report contains, in this order:

1. **Outcome and exit code.** Not a narrative -- the number.
2. **What actually ran**, by stage.
3. **Counts where the suite emits them** (checks, tests, failures).
4. **Anything on stderr that did not fail the build.** Warnings are real
   findings; a green exit code does not make them disappear.
5. **What remains unrun**, and why.

Keep it short. The reader wants to know whether it passed, what it covered,
and what it did not cover.

## Language rules for claims

These exist because the failure they prevent is silent and expensive.

- **"Verified" means observed after the change.** Not inferred, not
  reasoned, not passed-before-the-edit.
- **Distinguish where it was verified.** Sandbox-green and target-green are
  different claims. Say which.
- **Never call an issue resolved without retesting the original symptom.**
- **A stage that was not run is not a stage that passed.** Say what was
  skipped rather than letting a green summary imply full coverage.
- **Do not promote a warning to "clean".** Report it and say it did not fail
  the build.

## When to stop and ask

- The target directory is unreachable, and making it reachable means
  changing configuration on someone's machine.
- A stage needs privileges the runner does not have, and the workaround
  changes what the stage means.
- The pipeline definition itself looks wrong. Fix the definition
  deliberately and visibly, not by working around it at call time.
- Two sources disagree about the current state and neither is clearly
  authoritative.

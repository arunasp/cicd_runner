#!/usr/bin/env python3
"""Validate the skills/ tree and prove both published formats agree.

Two formats are shipped from one source of truth:

    skills/opencode/<name>/SKILL.md [+ references/]   -- browsable in-repo
    skills/claude/<name>.skill                        -- packaged zip bundle

Keeping them in sync by discipline does not survive contact with a busy
week. This check makes drift a build failure instead: it unpacks each
bundle in memory and compares it byte-for-byte against the tree it was
built from.

Exits non-zero on any problem, so it is a real pipeline stage rather than
decoration. Run it via `make skills-check`; `make check` runs it too.
"""

import pathlib
import sys
import zipfile

MAX_DESCRIPTION = 1024
ROOT = pathlib.Path(__file__).resolve().parent
OPENCODE = ROOT / "opencode"
CLAUDE = ROOT / "claude"

problems = []


def fail(msg):
    problems.append(msg)


def parse_frontmatter(text, where):
    """Return the frontmatter mapping, or None having recorded a problem."""
    if not text.startswith("---\n"):
        fail("%s: no YAML frontmatter" % where)
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        fail("%s: frontmatter is not terminated" % where)
        return None
    block = text[4:end + 1]

    # Deliberately not PyYAML: this must run anywhere python3 does,
    # including a worker with no third-party packages installed.
    fields, key = {}, None
    for line in block.splitlines():
        if line[:1].isspace() and key:
            fields[key] += " " + line.strip()
        elif ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            fields[key] = value.strip()
    return fields


def check_tree(skill_dir):
    name = skill_dir.name
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        fail("%s: no SKILL.md" % name)
        return

    text = md.read_text(encoding="utf-8")
    fields = parse_frontmatter(text, "%s/SKILL.md" % name)
    if fields is None:
        return

    if fields.get("name") != name:
        fail("%s: frontmatter name is %r, expected %r"
             % (name, fields.get("name"), name))

    description = fields.get("description", "")
    if not description:
        fail("%s: frontmatter has no description" % name)
    elif len(description) > MAX_DESCRIPTION:
        fail("%s: description is %d chars, limit is %d"
             % (name, len(description), MAX_DESCRIPTION))

    # Every referenced file must exist, and every shipped file must be
    # referenced -- an unreferenced reference is dead weight nothing loads.
    shipped = {
        p.relative_to(skill_dir).as_posix()
        for p in skill_dir.rglob("*") if p.is_file()
    } - {"SKILL.md"}
    for rel in sorted(shipped):
        if rel not in text:
            fail("%s: ships %s but SKILL.md never points at it" % (name, rel))
    for token in ("references/",):
        for word in text.split():
            candidate = word.strip("`'\"(),.").lstrip("./")
            if candidate.startswith(token) and candidate not in shipped:
                fail("%s: SKILL.md references missing %s" % (name, candidate))


def check_bundle_matches_tree(bundle):
    name = bundle.stem
    tree = OPENCODE / name
    if not tree.is_dir():
        fail("%s.skill: no matching skills/opencode/%s/ tree" % (name, name))
        return

    with zipfile.ZipFile(bundle) as zf:
        packed = {
            n: zf.read(n) for n in zf.namelist() if not n.endswith("/")
        }

    expected = {
        "%s/%s" % (name, p.relative_to(tree).as_posix()): p.read_bytes()
        for p in tree.rglob("*") if p.is_file()
    }

    for missing in sorted(set(expected) - set(packed)):
        fail("%s.skill: missing %s (present in the tree)" % (name, missing))
    for extra in sorted(set(packed) - set(expected)):
        fail("%s.skill: contains %s (absent from the tree)" % (name, extra))
    for shared in sorted(set(packed) & set(expected)):
        if packed[shared] != expected[shared]:
            fail("%s.skill: %s differs from the tree -- repackage it"
                 % (name, shared))


def main():
    if not OPENCODE.is_dir():
        print("no skills/opencode/ directory", file=sys.stderr)
        return 1

    trees = sorted(p for p in OPENCODE.iterdir() if p.is_dir())
    bundles = sorted(CLAUDE.glob("*.skill")) if CLAUDE.is_dir() else []
    if not trees:
        fail("skills/opencode/ contains no skills")

    for tree in trees:
        check_tree(tree)
    for bundle in bundles:
        check_bundle_matches_tree(bundle)

    # Every tree should also be published as a bundle, or one environment
    # silently gets fewer skills than the other.
    packaged = {b.stem for b in bundles}
    for tree in trees:
        if tree.name not in packaged:
            fail("%s: no skills/claude/%s.skill bundle"
                 % (tree.name, tree.name))

    for problem in problems:
        print("FAIL %s" % problem, file=sys.stderr)
    print("skills: %d skill(s), %d bundle(s), %d problem(s)"
          % (len(trees), len(bundles), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

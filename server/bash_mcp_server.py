#!/usr/bin/env python3
"""Project-agnostic CI/CD execution MCP server -- streamable-HTTP transport.

Generalizes LocusAI's own tools/server/bash_mcp_server.py (single
/workspace mount) to serve multiple projects from one container: each
project is bind-mounted at its own subdirectory under /projects, and
callers pick which one per call via the `project` argument, rather
than one container per project.

This container also mounts /var/run/docker.sock (see docker-compose.yml)
so `docker` is usable from inside it -- unlike LocusAI's own container,
which deliberately does NOT have docker/npm/npx on its allowlist, for
exactly this reason: a project's own container cannot safely rebuild
itself (the RPC connection serving the rebuild request dies mid-rebuild).
This runner is a separate container from every project it builds, so
rebuilding e.g. LocusAI's local-bash service is runner-container (A)
acting on project-container (B) -- no self-rebuild, no chicken-and-egg.
"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from lib.common import FileAllowlist, run_allowlisted

PROJECTS_ROOT = Path("/projects")
TIMEOUT_SECONDS = int(os.environ.get("CICD_TIMEOUT_SECONDS", "300"))

ALLOWED_BINARIES = FileAllowlist(Path("/app/allowlist.txt"))

mcp = FastMCP(
    "cicd-runner",
    host="0.0.0.0",
    port=int(os.environ.get("MCP_PORT", "1444")),
)


def _resolve_project_dir(project: str) -> Path | None:
    """Resolve `project` to a real, mounted subdirectory of
    PROJECTS_ROOT, refusing anything that isn't. Guards against path
    traversal (`../../etc`) and against picking a project name that
    merely LOOKS like a subdirectory but resolves (via a symlink)
    outside PROJECTS_ROOT.
    """
    candidate = (PROJECTS_ROOT / project).resolve()
    try:
        candidate.relative_to(PROJECTS_ROOT.resolve())
    except ValueError:
        return None
    if not candidate.is_dir():
        return None
    return candidate


@mcp.tool()
def list_projects() -> str:
    """List the projects currently mounted and available to run_command."""
    if not PROJECTS_ROOT.is_dir():
        return "No projects mounted (PROJECTS_ROOT does not exist)."
    names = sorted(p.name for p in PROJECTS_ROOT.iterdir() if p.is_dir())
    if not names:
        return "No projects mounted."
    return "\n".join(names)


@mcp.tool()
def run_command(project: str, binary: str, args: list[str]) -> str:
    """Run one allowlisted binary with the given argv inside the named
    project's mounted directory. Call list_projects() first if unsure
    which names are valid.
    """
    project_dir = _resolve_project_dir(project)
    if project_dir is None:
        return f"REFUSED: '{project}' is not a mounted project directory"
    return run_allowlisted(binary, args, ALLOWED_BINARIES, project_dir, TIMEOUT_SECONDS)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

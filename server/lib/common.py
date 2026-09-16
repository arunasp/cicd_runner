"""Shared functions for the cicd-runner MCP service."""

import subprocess
from collections.abc import Iterable
from pathlib import Path


class ExecutionResult:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def as_text(self) -> str:
        return (
            f"exit_code: {self.returncode}\n"
            f"stdout:\n{self.stdout}\n"
            f"stderr:\n{self.stderr}"
        )


class FileAllowlist:
    __slots__ = ("_path", "_mtime", "_binaries")

    def __init__(self, path: Path) -> None:
        self._path = path
        self._mtime: float | None = None
        self._binaries: frozenset[str] = frozenset()
        self._reload_if_changed()

    def _reload_if_changed(self) -> None:
        try:
            mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            self._mtime = None
            self._binaries = frozenset()
            return

        if mtime == self._mtime:
            return

        entries = set()
        for line in self._path.read_text().splitlines():
            name = line.split("#", 1)[0].strip()
            if name:
                entries.add(name)

        self._binaries = frozenset(entries)
        self._mtime = mtime

    def __contains__(self, binary: str) -> bool:
        self._reload_if_changed()
        return binary in self._binaries

    def __iter__(self):
        self._reload_if_changed()
        return iter(self._binaries)


def run_allowlisted(
    binary: str,
    args: list[str],
    allowed: Iterable[str],
    workdir: Path,
    timeout_seconds: int,
    child_kwargs: dict | None = None,
) -> str:
    """Run one allowlisted binary. `child_kwargs` is passed to
    subprocess.run unchanged -- the coordinator uses it for user, group,
    extra_groups and env so its children do not run as root."""
    if binary not in allowed:
        return f"REFUSED: '{binary}' is not in the allowlist {sorted(allowed)}"

    try:
        result = subprocess.run(
            [binary, *args],
            cwd=workdir,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            **(child_kwargs or {}),
        )
    except subprocess.TimeoutExpired:
        return f"TIMEOUT: '{binary}' exceeded {timeout_seconds}s"
    except FileNotFoundError:
        return f"ERROR: '{binary}' is allowlisted but not installed in this image"

    return ExecutionResult(result.returncode, result.stdout, result.stderr).as_text()

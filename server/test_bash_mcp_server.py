"""Tests for bash_mcp_server.py's path-resolution logic.

These are the same cases manually verified via inline sandbox scripts
during this project's own development (7 cases for
_resolve_project_dir, 8 for _resolve_dynamic_dir, including the
symlink-escape and traversal checks) -- committed here as real,
re-runnable tests instead of one-off throwaway verification, so
`make check` / `./configure && make check` has something genuine to
run rather than being a hollow alias for `lint`.

Run directly: python3 -m pytest server/test_bash_mcp_server.py -v --asyncio-mode=auto
"""

import json
import sys
from pathlib import Path

import pytest
import mcp.types as mcp_types

sys.path.insert(0, str(Path(__file__).parent))

import bash_mcp_server as srv  # noqa: E402


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    (root / "SampleProject").mkdir()
    (root / "AnotherProject").mkdir()
    monkeypatch.setattr(srv, "PROJECTS_ROOT", root)
    return root


@pytest.fixture
def dynamic_root(tmp_path, monkeypatch):
    root = tmp_path / "dynamic-root"
    root.mkdir()
    (root / "some-repo").mkdir()
    (root / "some-repo" / "file.txt").write_text("hi")
    etc = tmp_path / "etc"
    etc.mkdir()
    (root / "escape-symlink").symlink_to(etc)
    monkeypatch.setattr(srv, "DYNAMIC_ROOT", root)
    return root


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_returns_ok_status_and_200_when_docker_socket_present(self, monkeypatch, tmp_path):
        real_socket = tmp_path / "docker.sock"
        real_socket.touch()
        monkeypatch.setattr(srv, "DOCKER_SOCKET_PATH", real_socket)
        response = await srv.health_check(None)
        body = json.loads(response.body)
        assert body["status"] == "ok"
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_unhealthy_status_and_503_when_docker_socket_missing(self, monkeypatch, tmp_path):
        # The exact bug this fixes: a 200 regardless of docker_socket's
        # value meant an automated monitor checking only the status
        # code -- the normal way liveness checks work -- would report
        # "healthy" even with the coordinator's one foundational
        # dependency absent, defeating the entire point of a health
        # check.
        monkeypatch.setattr(srv, "DOCKER_SOCKET_PATH", tmp_path / "nonexistent.sock")
        response = await srv.health_check(None)
        body = json.loads(response.body)
        assert body["status"] == "unhealthy"
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_reports_real_docker_socket_state(self, monkeypatch, tmp_path):
        real_socket = tmp_path / "docker.sock"
        real_socket.touch()
        monkeypatch.setattr(srv, "DOCKER_SOCKET_PATH", real_socket)
        response = await srv.health_check(None)
        body = json.loads(response.body)
        assert body["docker_socket"] is True

    @pytest.mark.asyncio
    async def test_reports_missing_docker_socket(self, monkeypatch, tmp_path):
        monkeypatch.setattr(srv, "DOCKER_SOCKET_PATH", tmp_path / "nonexistent.sock")
        response = await srv.health_check(None)
        body = json.loads(response.body)
        assert body["docker_socket"] is False

    @pytest.mark.asyncio
    async def test_dynamic_root_and_cache_configuration_do_not_affect_status_code(self, monkeypatch, tmp_path):
        # dynamic_root/cache_root being unconfigured are legitimate,
        # intentionally-optional degrade-gracefully states, not
        # failures -- only docker_socket's absence should flip the
        # status code.
        real_socket = tmp_path / "docker.sock"
        real_socket.touch()
        monkeypatch.setattr(srv, "DOCKER_SOCKET_PATH", real_socket)
        monkeypatch.setattr(srv, "DYNAMIC_ROOT_HOST", "")
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "")
        response = await srv.health_check(None)
        body = json.loads(response.body)
        assert response.status_code == 200
        assert body["dynamic_root_configured"] is False
        assert body["cache_root_configured"] is False

    @pytest.mark.asyncio
    async def test_reports_dynamic_root_and_cache_configuration(self, monkeypatch):
        monkeypatch.setattr(srv, "DYNAMIC_ROOT_HOST", "/some/path")
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "")
        response = await srv.health_check(None)
        body = json.loads(response.body)
        assert body["dynamic_root_configured"] is True
        assert body["cache_root_configured"] is False


class TestResolveProjectDir:
    def test_valid_project(self, projects_root):
        assert srv._resolve_project_dir("SampleProject") == projects_root / "SampleProject"

    def test_another_valid_project(self, projects_root):
        assert srv._resolve_project_dir("AnotherProject") is not None

    def test_nonexistent_project(self, projects_root):
        assert srv._resolve_project_dir("nonexistent") is None

    def test_parent_traversal(self, projects_root):
        assert srv._resolve_project_dir("../../etc") is None

    def test_traversal_that_stays_inside_root_resolves(self, projects_root):
        result = srv._resolve_project_dir("SampleProject/../AnotherProject")
        assert result == projects_root / "AnotherProject"


class TestResolveWorkerImage:
    def test_no_config_file_uses_default(self, tmp_path):
        image, error = srv._resolve_worker_image(tmp_path)
        assert image == srv.DEFAULT_WORKER_IMAGE
        assert error is None

    def test_valid_config_file_overrides_default(self, tmp_path):
        (tmp_path / ".cicd-image").write_text("rust:1.82-bookworm\n")
        image, error = srv._resolve_worker_image(tmp_path)
        assert image == "rust:1.82-bookworm"
        assert error is None

    def test_empty_config_file_is_refused_not_silently_defaulted(self, tmp_path):
        (tmp_path / ".cicd-image").write_text("")
        image, error = srv._resolve_worker_image(tmp_path)
        assert image is None
        assert error is not None and "empty" in error

    def test_whitespace_only_config_file_is_refused(self, tmp_path):
        (tmp_path / ".cicd-image").write_text("   \n\n")
        image, error = srv._resolve_worker_image(tmp_path)
        assert image is None
        assert error is not None

    def test_only_first_line_is_used(self, tmp_path):
        (tmp_path / ".cicd-image").write_text("golang:1.23\nsome other junk\n")
        image, error = srv._resolve_worker_image(tmp_path)
        assert image == "golang:1.23"
        assert error is None

    def test_whitespace_around_image_is_stripped(self, tmp_path):
        (tmp_path / ".cicd-image").write_text("  node:22  \n")
        image, error = srv._resolve_worker_image(tmp_path)
        assert image == "node:22"
        assert error is None


class TestCacheMountFlags:
    def test_no_cache_root_configured_returns_empty(self, monkeypatch):
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "")
        assert srv._cache_mount_flags() == []

    def test_cache_root_configured_returns_all_four_mounts(self, monkeypatch):
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "/home/devuser/.cicd-runner-cache")
        flags = srv._cache_mount_flags()
        joined = " ".join(flags)
        assert "-v /home/devuser/.cicd-runner-cache/npm:/cache/npm" in joined
        assert "-v /home/devuser/.cicd-runner-cache/cargo-registry:/cache/cargo/registry" in joined
        assert "-v /home/devuser/.cicd-runner-cache/cargo-git:/cache/cargo/git" in joined
        assert "-v /home/devuser/.cicd-runner-cache/pip:/cache/pip" in joined

    def test_trailing_slash_is_stripped(self, monkeypatch):
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "/home/devuser/.cicd-runner-cache/")
        flags = srv._cache_mount_flags()
        assert "/home/devuser/.cicd-runner-cache/npm:/cache/npm" in flags
        assert not any("//" in f for f in flags)

    def test_mount_targets_are_user_independent_not_under_root_or_home(self, monkeypatch):
        # The exact bug this fixes: mount targets must NOT be under
        # /root or /home/<anyone> -- those are only correct for
        # whichever specific user the container happens to run as.
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "/cache-root")
        flags = srv._cache_mount_flags()
        targets = [f.split(":", 1)[1] for f in flags if ":" in f and f != "-v"]
        for target in targets:
            assert not target.startswith("/root")
            assert not target.startswith("/home")


class TestCacheEnvFlags:
    def test_no_cache_root_configured_returns_empty(self, monkeypatch):
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "")
        assert srv._cache_env_flags() == []

    def test_cache_root_configured_returns_all_three_tool_vars(self, monkeypatch):
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "/home/devuser/.cicd-runner-cache")
        flags = srv._cache_env_flags()
        joined = " ".join(flags)
        assert "NPM_CONFIG_CACHE=/cache/npm" in joined
        assert "CARGO_HOME=/cache/cargo" in joined
        assert "PIP_CACHE_DIR=/cache/pip" in joined

    def test_env_var_targets_match_mount_targets(self, monkeypatch):
        # The two functions must stay in sync -- an env var pointing
        # somewhere nothing is actually mounted would silently defeat
        # the whole fix, same class of bug as the one being fixed here.
        monkeypatch.setattr(srv, "CACHE_ROOT_HOST", "/cache-root")
        mount_flags = srv._cache_mount_flags()
        env_flags = srv._cache_env_flags()
        mount_targets = {f.split(":", 1)[1] for f in mount_flags if f.startswith("/cache-root")}
        env_paths = {v.split("=", 1)[1] for v in env_flags if "=" in v}
        assert "/cache/npm" in mount_targets
        assert "/cache/npm" in env_paths
        assert "/cache/pip" in mount_targets
        assert "/cache/pip" in env_paths
        assert "/cache/cargo" in env_paths
        assert any(t.startswith("/cache/cargo/") for t in mount_targets)


class TestUserEnvFlags:
    def test_neither_configured_returns_empty(self, monkeypatch):
        monkeypatch.setattr(srv, "HOST_UID", "")
        monkeypatch.setattr(srv, "HOST_GID", "")
        assert srv._user_env_flags() == []

    def test_both_configured_returns_env_flags(self, monkeypatch):
        monkeypatch.setattr(srv, "HOST_UID", "1000")
        monkeypatch.setattr(srv, "HOST_GID", "1000")
        assert srv._user_env_flags() == ["-e", "WORKER_UID=1000", "-e", "WORKER_GID=1000"]

    def test_different_uid_and_gid(self, monkeypatch):
        monkeypatch.setattr(srv, "HOST_UID", "1001")
        monkeypatch.setattr(srv, "HOST_GID", "1002")
        assert srv._user_env_flags() == ["-e", "WORKER_UID=1001", "-e", "WORKER_GID=1002"]

    def test_only_uid_configured_still_returns_empty(self, monkeypatch):
        monkeypatch.setattr(srv, "HOST_UID", "1000")
        monkeypatch.setattr(srv, "HOST_GID", "")
        assert srv._user_env_flags() == []

    def test_only_gid_configured_still_returns_empty(self, monkeypatch):
        monkeypatch.setattr(srv, "HOST_UID", "")
        monkeypatch.setattr(srv, "HOST_GID", "1000")
        assert srv._user_env_flags() == []


class TestUlimitFlags:
    def test_returns_generous_nproc_ulimit(self):
        assert srv._ulimit_flags() == ["--ulimit", "nproc=8192:8192"]

    def test_unaffected_by_host_uid_gid_configuration(self, monkeypatch):
        # Unlike _user_env_flags(), this must apply regardless -- the
        # default root user hits the same low-ulimit ceiling as any
        # other uid once enough system-wide processes exist for it.
        monkeypatch.setattr(srv, "HOST_UID", "")
        monkeypatch.setattr(srv, "HOST_GID", "")
        assert srv._ulimit_flags() == ["--ulimit", "nproc=8192:8192"]


class TestResolveDynamicDir:
    def test_valid_subdirectory(self, dynamic_root):
        assert srv._resolve_dynamic_dir("some-repo") == dynamic_root / "some-repo"

    def test_traversal_that_stays_inside_root_resolves(self, dynamic_root):
        result = srv._resolve_dynamic_dir("some-repo/../some-repo")
        assert result == dynamic_root / "some-repo"

    def test_parent_traversal_refused(self, dynamic_root):
        assert srv._resolve_dynamic_dir("../etc") is None

    def test_deeper_parent_traversal_refused(self, dynamic_root):
        assert srv._resolve_dynamic_dir("../../etc") is None

    def test_nonexistent_refused(self, dynamic_root):
        assert srv._resolve_dynamic_dir("nonexistent-repo") is None

    def test_symlink_escape_refused(self, dynamic_root):
        assert srv._resolve_dynamic_dir("escape-symlink") is None

    def test_root_itself_refused(self, dynamic_root):
        assert srv._resolve_dynamic_dir(".") is None

    def test_root_itself_via_different_path_refused(self, dynamic_root):
        assert srv._resolve_dynamic_dir("some-repo/..") is None


class TestExpandPattern:
    def test_home_prefix_expands(self, monkeypatch):
        monkeypatch.setattr(srv.Path, "home", staticmethod(lambda: Path("/home/devuser")))
        assert srv._expand_pattern("~/stuff/foo/**") == "/home/devuser/stuff/foo/**"

    def test_bare_tilde_expands(self, monkeypatch):
        monkeypatch.setattr(srv.Path, "home", staticmethod(lambda: Path("/home/devuser")))
        assert srv._expand_pattern("~") == "/home/devuser"

    def test_dollar_home_expands(self, monkeypatch):
        monkeypatch.setattr(srv.Path, "home", staticmethod(lambda: Path("/home/devuser")))
        assert srv._expand_pattern("$HOME/stuff/**") == "/home/devuser/stuff/**"

    def test_absolute_pattern_unchanged(self, monkeypatch):
        monkeypatch.setattr(srv.Path, "home", staticmethod(lambda: Path("/home/devuser")))
        assert srv._expand_pattern("/already/absolute/**") == "/already/absolute/**"


class TestMatchExternalDirectory:
    def test_no_match_defaults_to_ask(self):
        assert srv._match_external_directory("/some/path", {}) == "ask"

    def test_single_allow_match(self):
        rules = {"/home/devuser/stuff/SampleProject/**": "allow"}
        assert srv._match_external_directory("/home/devuser/stuff/SampleProject/tools", rules) == "allow"

    def test_non_matching_path_defaults_to_ask(self):
        rules = {"/home/devuser/stuff/SampleProject/**": "allow"}
        assert srv._match_external_directory("/home/devuser/stuff/other", rules) == "ask"

    def test_last_match_wins_deny_after_allow(self):
        rules = {
            "/home/devuser/stuff/SampleProject/**": "allow",
            "/home/devuser/stuff/SampleProject/secrets/**": "deny",
        }
        assert srv._match_external_directory("/home/devuser/stuff/SampleProject/tools", rules) == "allow"
        assert srv._match_external_directory("/home/devuser/stuff/SampleProject/secrets/x", rules) == "deny"

    def test_last_match_wins_allow_after_deny(self):
        rules = {
            "/home/devuser/stuff/**": "deny",
            "/home/devuser/stuff/SampleProject/**": "allow",
        }
        assert srv._match_external_directory("/home/devuser/stuff/SampleProject/tools", rules) == "allow"
        assert srv._match_external_directory("/home/devuser/stuff/other", rules) == "deny"


class TestReadExternalDirectoryRules:
    def test_no_opencode_json_returns_empty(self, tmp_path):
        assert srv._read_external_directory_rules(tmp_path) == {}

    def test_valid_config_returns_rules(self, tmp_path):
        (tmp_path / "opencode.json").write_text(json.dumps({
            "permission": {"external_directory": {"~/stuff/other/**": "allow"}}
        }))
        assert srv._read_external_directory_rules(tmp_path) == {"~/stuff/other/**": "allow"}

    def test_no_permission_section_returns_empty(self, tmp_path):
        (tmp_path / "opencode.json").write_text(json.dumps({"$schema": "x"}))
        assert srv._read_external_directory_rules(tmp_path) == {}

    def test_malformed_json_returns_empty(self, tmp_path):
        (tmp_path / "opencode.json").write_text("{not valid json")
        assert srv._read_external_directory_rules(tmp_path) == {}

    def test_external_directory_not_a_dict_returns_empty(self, tmp_path):
        (tmp_path / "opencode.json").write_text(json.dumps({
            "permission": {"external_directory": "not-a-dict"}
        }))
        assert srv._read_external_directory_rules(tmp_path) == {}


class FakeSession:
    """Mimics just enough of ServerSession's real interface (session.py's
    check_client_capability/list_roots) to test the roots integration
    without a live MCP connection.
    """
    def __init__(self, supports_roots: bool, roots: list[str]):
        self._supports_roots = supports_roots
        self._roots = roots

    def check_client_capability(self, capability):
        if capability.roots is not None:
            return self._supports_roots
        return False

    async def list_roots(self):
        return mcp_types.ListRootsResult(
            roots=[mcp_types.Root(uri=f"file://{p}") for p in self._roots]
        )


class BrokenSession(FakeSession):
    async def list_roots(self):
        raise RuntimeError("client disconnected mid-request")


class TestGetClientRoots:
    @pytest.mark.asyncio
    async def test_client_without_roots_support_returns_empty(self):
        session = FakeSession(False, [])
        assert await srv._get_client_roots(session) == []

    @pytest.mark.asyncio
    async def test_client_with_roots_support_returns_paths(self):
        session = FakeSession(True, ["/home/devuser/stuff/AnotherProject"])
        result = await srv._get_client_roots(session)
        assert result == ["/home/devuser/stuff/AnotherProject"]

    @pytest.mark.asyncio
    async def test_list_roots_raising_degrades_to_empty(self):
        session = BrokenSession(True, [])
        assert await srv._get_client_roots(session) == []


class FakeHeaders:
    """Mimics Starlette Headers' case-insensitive .get() interface."""
    def __init__(self, d):
        self._d = d

    def get(self, key, default=None):
        for k, v in self._d.items():
            if k.lower() == key.lower():
                return v
        return default


class FakeRequest:
    def __init__(self, headers):
        self.headers = FakeHeaders(headers)


class FakeRequestContext:
    """Mimics RequestContext -- .session for roots, .request for headers.
    request=None is a real, legitimate case (non-HTTP transport).
    """
    def __init__(self, session, request=None):
        self.session = session
        self.request = request


class FakeCtx:
    """Mimics FastMCP's Context -- only .session and .request_context
    are exercised by the code under test.
    """
    def __init__(self, session, headers=None):
        self.session = session
        self.request_context = FakeRequestContext(
            session, FakeRequest(headers) if headers is not None else None
        )


class TestIsPathAllowed:
    @pytest.mark.asyncio
    async def test_within_client_own_root_is_allowed(self, projects_root):
        session = FakeSession(True, ["/home/devuser/stuff/AnotherProject"])
        ctx = FakeCtx(session)
        allowed, reason = await srv._is_path_allowed(
            "/home/devuser/stuff/AnotherProject/src", ctx
        )
        assert allowed
        assert "connecting client's own root" in reason

    @pytest.mark.asyncio
    async def test_allowed_via_known_project_external_directory(self, projects_root):
        (projects_root / "SampleProject" / "opencode.json").write_text(json.dumps({
            "permission": {"external_directory": {"/home/devuser/stuff/sibling/**": "allow"}}
        }))
        ctx = FakeCtx(FakeSession(False, []))
        allowed, reason = await srv._is_path_allowed(
            "/home/devuser/stuff/sibling/src", ctx
        )
        assert allowed
        assert "external_directory allow" in reason

    @pytest.mark.asyncio
    async def test_refused_when_nothing_allows_it(self, projects_root):
        ctx = FakeCtx(FakeSession(True, ["/home/devuser/stuff/AnotherProject"]))
        allowed, reason = await srv._is_path_allowed(
            "/home/devuser/stuff/totally-unrelated", ctx
        )
        assert not allowed

    @pytest.mark.asyncio
    async def test_project_with_deny_rule_is_refused(self, projects_root):
        (projects_root / "SampleProject" / "opencode.json").write_text(json.dumps({
            "permission": {"external_directory": {"/home/devuser/stuff/sibling/**": "deny"}}
        }))
        ctx = FakeCtx(FakeSession(False, []))
        allowed, reason = await srv._is_path_allowed(
            "/home/devuser/stuff/sibling/src", ctx
        )
        assert not allowed

    @pytest.mark.asyncio
    async def test_allowed_via_header_wsl_interop_path(self, projects_root):
        ctx = FakeCtx(
            FakeSession(False, []),
            headers={"X-Allowed-Directories": r"\\wsl.localhost\Ubuntu\home\devuser\stuff\sibling"},
        )
        allowed, reason = await srv._is_path_allowed(
            "/home/devuser/stuff/sibling/src", ctx
        )
        assert allowed
        assert "X-Allowed-Directories header entry" in reason

    @pytest.mark.asyncio
    async def test_allowed_via_header_windows_drive_path(self, projects_root):
        ctx = FakeCtx(
            FakeSession(False, []),
            headers={"X-Allowed-Directories": r"D:\Users\T-1000\dev\my-project"},
        )
        allowed, reason = await srv._is_path_allowed(
            "/mnt/d/Users/T-1000/dev/my-project/src", ctx
        )
        assert allowed
        assert "X-Allowed-Directories header entry" in reason

    @pytest.mark.asyncio
    async def test_allowed_via_header_mixed_forms(self, projects_root):
        header = r"\\wsl.localhost\Ubuntu\home\devuser\stuff\sibling,D:\Users\T-1000\dev\my-project"
        ctx = FakeCtx(FakeSession(False, []), headers={"X-Allowed-Directories": header})
        allowed1, _ = await srv._is_path_allowed("/home/devuser/stuff/sibling/src", ctx)
        allowed2, _ = await srv._is_path_allowed("/mnt/d/Users/T-1000/dev/my-project/src", ctx)
        assert allowed1
        assert allowed2

    @pytest.mark.asyncio
    async def test_header_missing_degrades_to_no_grant(self, projects_root):
        ctx = FakeCtx(FakeSession(False, []))  # no headers arg -- request stays None
        allowed, reason = await srv._is_path_allowed(
            "/home/devuser/stuff/anything", ctx
        )
        assert not allowed

    @pytest.mark.asyncio
    async def test_header_present_but_unrelated_path_refused(self, projects_root):
        ctx = FakeCtx(
            FakeSession(False, []),
            headers={"X-Allowed-Directories": r"D:\Users\T-1000\dev\my-project"},
        )
        allowed, _ = await srv._is_path_allowed(
            "/home/devuser/stuff/totally-unrelated", ctx
        )
        assert not allowed


class TestTranslateWindowsPath:
    def test_wsl_localhost_unc_path(self):
        assert srv._translate_windows_path(
            r"\\wsl.localhost\Ubuntu\home\devuser\stuff\SampleProject"
        ) == "/home/devuser/stuff/SampleProject"

    def test_legacy_wsl_dollar_unc_path(self):
        assert srv._translate_windows_path(
            r"\\wsl$\Ubuntu\home\devuser\stuff\cicd_runner"
        ) == "/home/devuser/stuff/cicd_runner"

    def test_windows_drive_path(self):
        assert srv._translate_windows_path(
            r"D:\Users\T-1000\dev\my-project"
        ) == "/mnt/d/Users/T-1000/dev/my-project"

    def test_windows_drive_path_lowercase_drive_preserved(self):
        assert srv._translate_windows_path(
            r"e:\Data\Docs"
        ) == "/mnt/e/Data/Docs"

    def test_already_linux_path_unchanged(self):
        assert srv._translate_windows_path(
            "/home/devuser/stuff/already-linux"
        ) == "/home/devuser/stuff/already-linux"

    def test_unrecognized_form_passed_through(self):
        assert srv._translate_windows_path("relative/path") == "relative/path"


class TestParseAllowedDirectoriesHeader:
    def test_empty_string_returns_empty_list(self):
        assert srv._parse_allowed_directories_header("") == []

    def test_single_entry(self):
        result = srv._parse_allowed_directories_header(r"D:\Users\T-1000\dev")
        assert result == ["/mnt/d/Users/T-1000/dev"]

    def test_multiple_comma_separated_entries(self):
        header = r"\\wsl.localhost\Ubuntu\home\devuser\stuff\SampleProject,D:\Users\T-1000\dev"
        result = srv._parse_allowed_directories_header(header)
        assert result == ["/home/devuser/stuff/SampleProject", "/mnt/d/Users/T-1000/dev"]

    def test_whitespace_around_entries_stripped(self):
        header = r"D:\Users\a , D:\Users\b"
        result = srv._parse_allowed_directories_header(header)
        assert result == ["/mnt/d/Users/a", "/mnt/d/Users/b"]

    def test_empty_segments_skipped(self):
        header = r"D:\Users\a,,D:\Users\b"
        result = srv._parse_allowed_directories_header(header)
        assert result == ["/mnt/d/Users/a", "/mnt/d/Users/b"]


class TestResolveComposeBinary:
    """The v2-plugin-vs-v1-standalone branch, verified by faking the tools
    rather than needing every variant installed.

    All three states matter, including the one where neither exists: a
    silent wrong default there is worse than a loud failure, and it is
    exactly where this class of bug hides.
    """

    @staticmethod
    def _mock_bin(directory, name, body):
        path = directory / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)
        return path

    def test_prefers_the_v2_plugin_when_present(self, monkeypatch, tmp_path):
        self._mock_bin(tmp_path, "docker", 'exit 0')
        self._mock_bin(tmp_path, "docker-compose", 'exit 0')
        monkeypatch.setenv("PATH", str(tmp_path))
        cmd, err = srv._resolve_compose_binary()
        assert err is None
        assert cmd == ["docker", "compose"]

    def test_falls_back_to_v1_when_the_plugin_is_absent(self, monkeypatch,
                                                       tmp_path):
        # Real behaviour of a docker without the compose plugin: docker
        # itself exists and succeeds for other subcommands, but
        # `docker compose version` exits non-zero.
        self._mock_bin(tmp_path, "docker", '''
if [ "$1" = "compose" ]; then
  echo "docker: 'compose' is not a docker command." >&2
  exit 1
fi
exit 0''')
        self._mock_bin(tmp_path, "docker-compose",
                       'echo "docker-compose version 1.29.2"')
        monkeypatch.setenv("PATH", str(tmp_path))
        cmd, err = srv._resolve_compose_binary()
        assert err is None
        assert cmd == ["docker-compose"]

    def test_refuses_loudly_when_neither_is_available(self, monkeypatch,
                                                     tmp_path):
        self._mock_bin(tmp_path, "docker", '''
if [ "$1" = "compose" ]; then exit 1; fi
exit 0''')
        monkeypatch.setenv("PATH", str(tmp_path))
        cmd, err = srv._resolve_compose_binary()
        assert cmd is None
        assert "neither" in err

    def test_reports_a_missing_docker_distinctly(self, monkeypatch, tmp_path):
        """A missing docker is a different fault from a missing plugin and
        must not be reported as 'no compose available'."""
        monkeypatch.setenv("PATH", str(tmp_path))
        cmd, err = srv._resolve_compose_binary()
        assert cmd is None
        assert "'docker' not found" in err


class TestFindComposeFile:
    def test_finds_each_accepted_name(self, tmp_path):
        for name in srv.COMPOSE_FILENAMES:
            d = tmp_path / name.replace(".", "_")
            d.mkdir()
            (d / name).write_text("services: {}\n")
            assert srv._find_compose_file(d) == name

    def test_returns_none_when_absent(self, tmp_path):
        assert srv._find_compose_file(tmp_path) is None

    def test_ignores_a_directory_of_that_name(self, tmp_path):
        (tmp_path / "docker-compose.yml").mkdir()
        assert srv._find_compose_file(tmp_path) is None


class TestContainerActions:
    def test_rebuild_does_not_use_up_build(self):
        """`up --build` recreates in place, which hits compose v1's
        KeyError: ContainerConfig after a BuildKit rebuild. The sequence
        must remove the container between build and up."""
        steps = srv.CONTAINER_ACTIONS["rebuild"]
        assert [s[0] for s in steps] == ["build", "rm", "up"]
        assert not any("--build" in s for s in steps)

    def test_every_action_is_a_fixed_sequence(self):
        for name, steps in srv.CONTAINER_ACTIONS.items():
            assert isinstance(steps, tuple), name
            for step in steps:
                assert all(isinstance(a, str) for a in step), name

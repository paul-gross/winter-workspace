"""Tests for build_extension_env — the shared extension subprocess env builder.

Coverage:
- Sets all five base winter extension context variables.
- Uses os.environ as base when no base is supplied.
- Uses supplied base dict when provided (does not modify it).
- Custom config_dir override is honoured.
- WINTER_EXT_CONFIG_DIR default resolution via repository_factory.
- Dispatch sites (fan-out up, logs) emit WINTER_EXT_CONFIG_DIR.
"""

from __future__ import annotations

import os
from pathlib import Path

from tests.conftest import FakeSubprocessRunner
from winter_cli.core.extension_invocation import build_extension_env
from winter_cli.modules.capability.models import CapabilitySlot, ResolvedCapability
from winter_cli.modules.service.service_fan_out_service import FanOutCell, ServiceFanOutService

WS = Path("/workspace")
EXT_DIR = WS / "winter-service-tmux"
CONFIG_DIR = WS / ".winter" / "config" / "winter-service-tmux"
ENTRYPOINT = EXT_DIR / "workflow/service"
PREFIX = "wst"
SERVICE_PREFIX = "winter"


# ── build_extension_env basics ────────────────────────────────────────────────


def test_build_extension_env_sets_all_five_vars() -> None:
    """build_extension_env returns a dict with all five base winter extension vars."""
    env = build_extension_env(
        workspace_root=WS,
        ext_dir=EXT_DIR,
        prefix=PREFIX,
        config_dir=CONFIG_DIR,
        service_prefix=SERVICE_PREFIX,
        base={},
    )
    assert env["WINTER_WORKSPACE_DIR"] == str(WS)
    assert env["WINTER_EXT_DIR"] == str(EXT_DIR)
    assert env["WINTER_EXT_PREFIX"] == PREFIX
    assert env["WINTER_EXT_CONFIG_DIR"] == str(CONFIG_DIR)
    assert env["WINTER_SERVICE_PREFIX"] == SERVICE_PREFIX


def test_build_extension_env_uses_os_environ_when_no_base() -> None:
    """When base is None, build_extension_env starts from os.environ."""
    env = build_extension_env(
        workspace_root=WS,
        ext_dir=EXT_DIR,
        prefix=PREFIX,
        config_dir=CONFIG_DIR,
        service_prefix=SERVICE_PREFIX,
    )
    # os.environ keys that don't overlap with the five vars should appear.
    five_vars = {
        "WINTER_WORKSPACE_DIR",
        "WINTER_EXT_DIR",
        "WINTER_EXT_PREFIX",
        "WINTER_EXT_CONFIG_DIR",
        "WINTER_SERVICE_PREFIX",
    }
    for key, value in os.environ.items():
        if key not in five_vars:
            assert env.get(key) == value


def test_build_extension_env_does_not_mutate_base() -> None:
    """build_extension_env returns a new dict and never mutates the supplied base."""
    base: dict[str, str] = {"EXISTING": "value"}
    env = build_extension_env(
        workspace_root=WS,
        ext_dir=EXT_DIR,
        prefix=PREFIX,
        config_dir=CONFIG_DIR,
        service_prefix=SERVICE_PREFIX,
        base=base,
    )
    assert "WINTER_WORKSPACE_DIR" not in base
    assert env["EXISTING"] == "value"


def test_build_extension_env_custom_config_dir() -> None:
    """config_dir override is reflected in WINTER_EXT_CONFIG_DIR."""
    custom = WS / "custom" / "config"
    env = build_extension_env(
        workspace_root=WS,
        ext_dir=EXT_DIR,
        prefix=PREFIX,
        config_dir=custom,
        service_prefix=SERVICE_PREFIX,
        base={},
    )
    assert env["WINTER_EXT_CONFIG_DIR"] == str(custom)


# ── default config_dir resolution via repository_factory ─────────────────────


def test_repository_factory_default_config_dir() -> None:
    """get_standalone_repos() resolves config_dir to <ws>/.winter/config/<name> by default."""
    from winter_cli.config.models import StandaloneRepositoryConfig, WorkspaceConfig
    from winter_cli.modules.workspace.repository_factory import RepositoryFactory

    ws = Path("/fakews")
    config = WorkspaceConfig(
        workspace_root=ws,
        service_prefix="test",
        main_branch="main",
        standalone_repos=[
            StandaloneRepositoryConfig(name="my-ext", url="git@example.com:org/my-ext.git"),
        ],
    )
    factory = RepositoryFactory(config)
    repos = factory.get_standalone_repos()
    assert len(repos) == 1
    assert repos[0].config_dir == (ws / ".winter" / "config" / "my-ext").resolve()


def test_repository_factory_explicit_config_dir() -> None:
    """An explicit config_dir in StandaloneRepositoryConfig is resolved to absolute."""
    from winter_cli.config.models import StandaloneRepositoryConfig, WorkspaceConfig
    from winter_cli.modules.workspace.repository_factory import RepositoryFactory

    ws = Path("/fakews")
    config = WorkspaceConfig(
        workspace_root=ws,
        service_prefix="test",
        main_branch="main",
        standalone_repos=[
            StandaloneRepositoryConfig(
                name="my-ext",
                url="git@example.com:org/my-ext.git",
                config_dir="custom/config/my-ext",
            ),
        ],
    )
    factory = RepositoryFactory(config)
    repos = factory.get_standalone_repos()
    assert repos[0].config_dir == (ws / "custom" / "config" / "my-ext").resolve()


# ── dispatch site: fan-out emits WINTER_EXT_CONFIG_DIR ────────────────────────


def test_fan_out_up_emits_winter_ext_config_dir() -> None:
    """ServiceFanOutService.up injects WINTER_EXT_CONFIG_DIR into the subprocess env."""
    provider = ResolvedCapability(
        slot=CapabilitySlot.service,
        extension_name="winter-service-tmux",
        entrypoint=ENTRYPOINT,
        ext_dir=EXT_DIR,
        prefix=PREFIX,
        config_dir=CONFIG_DIR,
    )
    runner = FakeSubprocessRunner()
    svc = ServiceFanOutService(subprocess_runner=runner, workspace_root=WS, service_prefix=SERVICE_PREFIX)

    svc.up([FanOutCell(provider=provider, scope="alpha", positional="alpha")])

    assert len(runner.call_envs) == 1
    env = runner.call_envs[0]
    assert env["WINTER_EXT_CONFIG_DIR"] == str(CONFIG_DIR)
    assert env["WINTER_WORKSPACE_DIR"] == str(WS)
    assert env["WINTER_EXT_DIR"] == str(EXT_DIR)
    assert env["WINTER_EXT_PREFIX"] == PREFIX
    assert env["WINTER_SERVICE_PREFIX"] == SERVICE_PREFIX

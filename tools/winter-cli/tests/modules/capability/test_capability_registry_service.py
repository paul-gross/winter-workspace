from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import FakeConfigFileReader, FakeFilesystem
from winter_cli.modules.capability.capability_registry_service import CapabilityRegistryService
from winter_cli.modules.capability.models import CapabilityBindingError, CapabilitySlot, ResolvedCapability
from winter_cli.modules.workspace.extension_manifest import EXT_MANIFEST, ExtensionManifestLoader
from winter_cli.modules.workspace.models import StandaloneRepository

WS = Path("/ws")
TMUX = WS / "winter-service-tmux"
DOCKER = WS / "winter-service-docker"


class _StubRepoFactory:
    def __init__(self, repos: list[StandaloneRepository]) -> None:
        self._repos = repos

    def get_standalone_repos(self) -> list[StandaloneRepository]:
        return self._repos


def _registry(
    *,
    repos: list[StandaloneRepository],
    manifests: dict[Path, dict],
    files: dict[Path, str],
    bindings: dict[str, str] | None = None,
) -> CapabilityRegistryService:
    loader = ExtensionManifestLoader(config_file_reader=FakeConfigFileReader(manifests))
    return CapabilityRegistryService(
        repo_factory=_StubRepoFactory(repos),
        manifest_loader=loader,
        bindings=bindings or {},
        fs=FakeFilesystem(files=files),
    )


def _tmux_repo() -> StandaloneRepository:
    return StandaloneRepository(name="winter-service-tmux", path=TMUX)


def _docker_repo() -> StandaloneRepository:
    return StandaloneRepository(name="winter-service-docker", path=DOCKER)


def _tmux_manifest(entrypoint: str = "workflow/service") -> dict:
    return {"provides": {"service": entrypoint}}


def _docker_manifest(entrypoint: str = "workflow/service") -> dict:
    return {"provides": {"service": entrypoint}}


# ── 1. Explicit binding to a valid providing extension ────────────────────────


def test_explicit_binding_describe_kind() -> None:
    repo = _tmux_repo()
    entrypoint = TMUX / "workflow/service"
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: _tmux_manifest()},
        files={TMUX / EXT_MANIFEST: "", entrypoint: ""},
        bindings={"service": "winter-service-tmux"},
    )
    resolution = reg.describe(CapabilitySlot.service)
    assert resolution.binding_kind == "explicit"
    assert resolution.bound_extension == "winter-service-tmux"
    assert resolution.error is None


def test_explicit_binding_resolve_returns_candidate() -> None:
    repo = _tmux_repo()
    entrypoint = TMUX / "workflow/service"
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: _tmux_manifest()},
        files={TMUX / EXT_MANIFEST: "", entrypoint: ""},
        bindings={"service": "winter-service-tmux"},
    )
    resolved = reg.resolve(CapabilitySlot.service)
    assert isinstance(resolved, ResolvedCapability)
    assert resolved.extension_name == "winter-service-tmux"
    assert resolved.entrypoint == entrypoint
    assert resolved.ext_dir == TMUX


# ── 2. Implicit single provider, no binding ───────────────────────────────────


def test_implicit_single_provider_describe_kind() -> None:
    repo = _tmux_repo()
    entrypoint = TMUX / "workflow/service"
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: _tmux_manifest()},
        files={TMUX / EXT_MANIFEST: "", entrypoint: ""},
    )
    resolution = reg.describe(CapabilitySlot.service)
    assert resolution.binding_kind == "implicit"
    assert resolution.bound_extension is None
    assert resolution.error is None
    assert len(resolution.candidates) == 1


def test_implicit_single_provider_resolve_returns_sole_provider() -> None:
    repo = _tmux_repo()
    entrypoint = TMUX / "workflow/service"
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: _tmux_manifest()},
        files={TMUX / EXT_MANIFEST: "", entrypoint: ""},
    )
    resolved = reg.resolve(CapabilitySlot.service)
    assert resolved.extension_name == "winter-service-tmux"
    assert resolved.entrypoint == entrypoint


# ── 3. Two providers, no binding (ambiguous) ──────────────────────────────────


def test_two_providers_no_binding_describe_is_ambiguous() -> None:
    tmux = _tmux_repo()
    docker = _docker_repo()
    tmux_ep = TMUX / "workflow/service"
    docker_ep = DOCKER / "workflow/service"
    reg = _registry(
        repos=[tmux, docker],
        manifests={
            TMUX / EXT_MANIFEST: _tmux_manifest(),
            DOCKER / EXT_MANIFEST: _docker_manifest(),
        },
        files={
            TMUX / EXT_MANIFEST: "",
            tmux_ep: "",
            DOCKER / EXT_MANIFEST: "",
            docker_ep: "",
        },
    )
    resolution = reg.describe(CapabilitySlot.service)
    assert resolution.binding_kind == "unbound"
    assert resolution.is_ambiguous is True
    assert len(resolution.candidates) == 2


def test_two_providers_no_binding_resolve_raises_naming_both_and_config_key() -> None:
    tmux = _tmux_repo()
    docker = _docker_repo()
    tmux_ep = TMUX / "workflow/service"
    docker_ep = DOCKER / "workflow/service"
    reg = _registry(
        repos=[tmux, docker],
        manifests={
            TMUX / EXT_MANIFEST: _tmux_manifest(),
            DOCKER / EXT_MANIFEST: _docker_manifest(),
        },
        files={
            TMUX / EXT_MANIFEST: "",
            tmux_ep: "",
            DOCKER / EXT_MANIFEST: "",
            docker_ep: "",
        },
    )
    with pytest.raises(CapabilityBindingError) as exc_info:
        reg.resolve(CapabilitySlot.service)
    msg = str(exc_info.value)
    assert "winter-service-tmux" in msg
    assert "winter-service-docker" in msg
    assert "capabilities.service" in msg


# ── 4. Binding names an extension that is not installed ───────────────────────


def test_binding_to_uninstalled_extension_describe_invalid() -> None:
    repo = _tmux_repo()
    entrypoint = TMUX / "workflow/service"
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: _tmux_manifest()},
        files={TMUX / EXT_MANIFEST: "", entrypoint: ""},
        bindings={"service": "winter-service-docker"},  # not installed
    )
    resolution = reg.describe(CapabilitySlot.service)
    assert resolution.binding_kind == "invalid"
    assert resolution.bound_extension == "winter-service-docker"
    assert resolution.error is not None
    assert "no installed extension named" in resolution.error


def test_binding_to_uninstalled_extension_resolve_raises() -> None:
    repo = _tmux_repo()
    entrypoint = TMUX / "workflow/service"
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: _tmux_manifest()},
        files={TMUX / EXT_MANIFEST: "", entrypoint: ""},
        bindings={"service": "winter-service-docker"},
    )
    with pytest.raises(CapabilityBindingError, match="no installed extension named"):
        reg.resolve(CapabilitySlot.service)


# ── 5. Binding names an installed extension that does NOT provide the slot ────


def test_binding_to_non_providing_extension_describe_invalid() -> None:
    repo = _tmux_repo()
    # Manifest with no provides.service
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: {}},  # no provides at all
        files={TMUX / EXT_MANIFEST: ""},
        bindings={"service": "winter-service-tmux"},
    )
    resolution = reg.describe(CapabilitySlot.service)
    assert resolution.binding_kind == "invalid"
    assert "installed but declares no provides.service" in (resolution.error or "")


def test_binding_to_non_providing_extension_resolve_raises() -> None:
    repo = _tmux_repo()
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: {}},
        files={TMUX / EXT_MANIFEST: ""},
        bindings={"service": "winter-service-tmux"},
    )
    with pytest.raises(CapabilityBindingError, match=r"installed but declares no provides\.service"):
        reg.resolve(CapabilitySlot.service)


# ── 6. Binding valid but entrypoint file missing ──────────────────────────────


def test_binding_valid_entrypoint_missing_describe_invalid() -> None:
    repo = _tmux_repo()
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: _tmux_manifest()},
        files={TMUX / EXT_MANIFEST: ""},  # entrypoint file NOT seeded
        bindings={"service": "winter-service-tmux"},
    )
    resolution = reg.describe(CapabilitySlot.service)
    assert resolution.binding_kind == "invalid"
    assert "entrypoint not found" in (resolution.error or "")


def test_binding_valid_entrypoint_missing_resolve_raises() -> None:
    repo = _tmux_repo()
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: _tmux_manifest()},
        files={TMUX / EXT_MANIFEST: ""},
        bindings={"service": "winter-service-tmux"},
    )
    with pytest.raises(CapabilityBindingError, match="entrypoint not found"):
        reg.resolve(CapabilitySlot.service)


# ── 7. Zero providers, no binding ─────────────────────────────────────────────


def test_zero_providers_no_binding_resolve_raises_no_extension() -> None:
    reg = _registry(repos=[], manifests={}, files={})
    with pytest.raises(CapabilityBindingError, match="no extension provides"):
        reg.resolve(CapabilitySlot.service)


def test_zero_providers_no_binding_describe_unbound() -> None:
    reg = _registry(repos=[], manifests={}, files={})
    resolution = reg.describe(CapabilitySlot.service)
    assert resolution.binding_kind == "unbound"
    assert resolution.is_ambiguous is False


# ── 8. Back-compat: orchestrate_services shim flows through the registry ──────


def test_orchestrate_services_backcompat_discovered_as_service_candidate() -> None:
    """An extension declaring only `orchestrate_services` (no `provides.service`)
    is still discovered as a service candidate via the manifest shim."""
    repo = _tmux_repo()
    entrypoint = TMUX / "workflow/orchestrate"
    reg = _registry(
        repos=[repo],
        manifests={TMUX / EXT_MANIFEST: {"orchestrate_services": "workflow/orchestrate"}},
        files={TMUX / EXT_MANIFEST: "", entrypoint: ""},
    )
    resolution = reg.describe(CapabilitySlot.service)
    assert resolution.binding_kind == "implicit"
    assert len(resolution.candidates) == 1
    assert resolution.candidates[0].extension_name == "winter-service-tmux"
    assert resolution.candidates[0].entrypoint_rel == "workflow/orchestrate"

    resolved = reg.resolve(CapabilitySlot.service)
    assert resolved.entrypoint == entrypoint
    assert resolved.extension_name == "winter-service-tmux"

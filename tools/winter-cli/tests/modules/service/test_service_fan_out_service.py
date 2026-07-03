"""Tests for ServiceFanOutService — cell-based up/down fan-out (no readiness gate).

Coverage:
- Single-cell up: calls the cell's provider up, returns 0.
- Single-cell up: propagates non-zero exit code.
- Single-cell down: calls the cell's provider down, returns 0.
- Single-cell down: propagates non-zero exit code.
- Two-cell up (single scope, two providers): calls both cells' up in forward order
  with NO status poll between them (proves the gate is gone).
- Two-cell up: aborts on first cell failure; second cell never called.
- Two-cell down: calls both cells' down (best-effort).
- Two-cell down: continues past failure; returns first non-zero.
- Two-cell down: returns 0 when all succeed.
- Multi-scope up/down: two cells targeting different scopes both dispatch, in order.
- Env vars are injected correctly for each cell.
- Provisioned scope env vars (including WINTER_SERVICE_PREFIX) are merged into
  both up and down subprocess env when an env_provisioner is present, computed
  once per unique scope (cached across cells sharing a scope).
- Cell positional (bare scope vs scope-qualified pattern) is forwarded verbatim
  as the single positional argv token.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import FakeSubprocessRunner
from winter_cli.modules.capability.models import CapabilitySlot, ResolvedCapability
from winter_cli.modules.service.service_fan_out_service import FanOutCell, ServiceFanOutService

WS = Path("/ws")
EXT_A = WS / "provider-a"
EXT_B = WS / "provider-b"
ENTRYPOINT_A = EXT_A / "workflow/service"
ENTRYPOINT_B = EXT_B / "workflow/service"

_EP_A = str(ENTRYPOINT_A)
_EP_B = str(ENTRYPOINT_B)

_UP_A = f"{_EP_A} up alpha"
_UP_B = f"{_EP_B} up alpha"
_DOWN_A = f"{_EP_A} down alpha"
_DOWN_B = f"{_EP_B} down alpha"


# ── helpers ───────────────────────────────────────────────────────────────────


def _provider(name: str, entrypoint: Path, ext_dir: Path) -> ResolvedCapability:
    return ResolvedCapability(
        slot=CapabilitySlot.service,
        extension_name=name,
        entrypoint=entrypoint,
        ext_dir=ext_dir,
        prefix=name,
        config_dir=WS / ".winter" / "config" / name,
    )


def _pa() -> ResolvedCapability:
    return _provider("provider-a", ENTRYPOINT_A, EXT_A)


def _pb() -> ResolvedCapability:
    return _provider("provider-b", ENTRYPOINT_B, EXT_B)


def _cell(provider: ResolvedCapability, scope: str = "alpha", positional: str | None = None) -> FanOutCell:
    return FanOutCell(provider=provider, scope=scope, positional=positional if positional is not None else scope)


def _make_fan_out(runner: FakeSubprocessRunner) -> ServiceFanOutService:
    return ServiceFanOutService(
        subprocess_runner=runner,
        workspace_root=WS,
        service_prefix="winter",
    )


# ── single-cell up ────────────────────────────────────────────────────────────


def test_single_cell_up_calls_up_returns_zero() -> None:
    """Single-cell up: calls the provider's up and returns 0."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    code = svc.up([_cell(_pa())])

    assert code == 0
    assert runner.call_calls == [([_EP_A, "up", "alpha"], WS)]
    # No status poll (no gate).
    assert runner.run_calls == []


def test_single_cell_up_propagates_nonzero_exit() -> None:
    """Single-cell up: propagates non-zero exit code."""
    runner = FakeSubprocessRunner(call_responses={_UP_A: 5})
    svc = _make_fan_out(runner)

    code = svc.up([_cell(_pa())])

    assert code == 5


# ── single-cell down ──────────────────────────────────────────────────────────


def test_single_cell_down_calls_down_returns_zero() -> None:
    """Single-cell down: calls the provider's down and returns 0."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    code = svc.down([_cell(_pa())])

    assert code == 0
    assert runner.call_calls == [([_EP_A, "down", "alpha"], WS)]
    assert runner.run_calls == []


def test_single_cell_down_propagates_nonzero_exit() -> None:
    """Single-cell down: propagates non-zero exit code."""
    runner = FakeSubprocessRunner(call_responses={_DOWN_A: 3})
    svc = _make_fan_out(runner)

    code = svc.down([_cell(_pa())])

    assert code == 3


# ── two-cell up (no gate) ─────────────────────────────────────────────────────


def test_two_cell_up_calls_both_in_forward_order_no_status_poll() -> None:
    """Two cells (same scope, two providers) up: forward order, NO status poll between.

    This is the primary proof that the readiness gate is gone: no status call
    sits between the two up calls.
    """
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    code = svc.up([_cell(_pa()), _cell(_pb())])

    assert code == 0

    # Exact call sequence: up-a then up-b, nothing else.
    call_cmds = [tuple(c[0]) for c in runner.call_calls]
    assert call_cmds == [
        (_EP_A, "up", "alpha"),
        (_EP_B, "up", "alpha"),
    ]

    # No run() calls at all — proves no status poll between the two ups.
    assert runner.run_calls == []


def test_two_cell_up_aborts_on_first_failure_second_never_called() -> None:
    """Two-cell up: if the first cell's up exits non-zero, the second is never called."""
    runner = FakeSubprocessRunner(call_responses={_UP_A: 7})
    svc = _make_fan_out(runner)

    code = svc.up([_cell(_pa()), _cell(_pb())])

    assert code == 7
    call_cmds = [tuple(c[0]) for c in runner.call_calls]
    # Only provider-a's up was called.
    assert (_EP_A, "up", "alpha") in call_cmds
    assert (_EP_B, "up", "alpha") not in call_cmds
    # No status poll.
    assert runner.run_calls == []


# ── two-cell down (best-effort) ──────────────────────────────────────────────


def test_two_cell_down_calls_both_providers() -> None:
    """Two-cell down: calls both providers' down."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    code = svc.down([_cell(_pa()), _cell(_pb())])

    assert code == 0
    call_cmds = [tuple(c[0]) for c in runner.call_calls]
    assert (_EP_A, "down", "alpha") in call_cmds
    assert (_EP_B, "down", "alpha") in call_cmds


def test_two_cell_down_best_effort_continues_on_failure() -> None:
    """Down is best-effort: continues past cell failure; returns first non-zero."""
    # Provider A fails.
    runner = FakeSubprocessRunner(call_responses={_DOWN_A: 4})
    svc = _make_fan_out(runner)

    code = svc.down([_cell(_pa()), _cell(_pb())])

    # Both down calls were made (best-effort continues).
    call_cmds = [tuple(c[0]) for c in runner.call_calls]
    assert (_EP_A, "down", "alpha") in call_cmds
    assert (_EP_B, "down", "alpha") in call_cmds
    # First non-zero returned.
    assert code == 4


def test_two_cell_down_all_succeed_returns_zero() -> None:
    """Down returns 0 when all cells succeed."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    code = svc.down([_cell(_pa()), _cell(_pb())])

    assert code == 0


# ── multi-scope fan-out ───────────────────────────────────────────────────────


def test_up_multi_scope_dispatches_each_scope_in_order() -> None:
    """Two cells targeting different scopes (same provider) both dispatch, in order."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    code = svc.up([_cell(_pa(), scope="alpha"), _cell(_pa(), scope="beta")])

    assert code == 0
    call_cmds = [tuple(c[0]) for c in runner.call_calls]
    assert call_cmds == [
        (_EP_A, "up", "alpha"),
        (_EP_A, "up", "beta"),
    ]


def test_down_multi_scope_best_effort_across_scopes() -> None:
    """Down across multiple scopes: continues past a failure in one scope."""
    runner = FakeSubprocessRunner(call_responses={f"{_EP_A} down alpha": 6})
    svc = _make_fan_out(runner)

    code = svc.down([_cell(_pa(), scope="alpha"), _cell(_pa(), scope="beta")])

    call_cmds = [tuple(c[0]) for c in runner.call_calls]
    assert (_EP_A, "down", "alpha") in call_cmds
    assert (_EP_A, "down", "beta") in call_cmds
    assert code == 6


# ── cell positional forwarding ────────────────────────────────────────────────


def test_up_forwards_scope_qualified_positional_verbatim() -> None:
    """A cell with a scope-qualified positional (real service filter) forwards it verbatim."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    svc.up([_cell(_pa(), scope="alpha", positional="alpha/api")])

    assert runner.call_calls == [([_EP_A, "up", "alpha/api"], WS)]


# ── env var injection ─────────────────────────────────────────────────────────


def test_up_injects_provider_env_vars() -> None:
    """Fan-out up injects WINTER_WORKSPACE_DIR, WINTER_EXT_DIR, WINTER_EXT_PREFIX, WINTER_SERVICE_PREFIX per cell."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    svc.up([_cell(_pa())])

    assert len(runner.call_envs) == 1
    call_env = runner.call_envs[0]
    assert call_env["WINTER_WORKSPACE_DIR"] == str(WS)
    assert call_env["WINTER_EXT_DIR"] == str(EXT_A)
    assert call_env["WINTER_EXT_PREFIX"] == "provider-a"
    assert call_env["WINTER_SERVICE_PREFIX"] == "winter"


def test_down_injects_provider_env_vars() -> None:
    """Fan-out down injects WINTER_WORKSPACE_DIR, WINTER_EXT_DIR, WINTER_EXT_PREFIX, WINTER_SERVICE_PREFIX per cell."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    svc.down([_cell(_pb())])

    assert len(runner.call_envs) == 1
    call_env = runner.call_envs[0]
    assert call_env["WINTER_WORKSPACE_DIR"] == str(WS)
    assert call_env["WINTER_EXT_DIR"] == str(EXT_B)
    assert call_env["WINTER_EXT_PREFIX"] == "provider-b"
    assert call_env["WINTER_SERVICE_PREFIX"] == "winter"


def test_up_injects_provisioned_env_vars_when_provisioner_present() -> None:
    """When an env_provisioner is present, its computed vars are merged into the subprocess env."""

    class _FakeProvisioner:
        def compute(self, scope: str) -> dict[str, str]:
            return {
                "WINTER_ENV": scope,
                "WINTER_PORT_BASE": "4060",
                "WINTER_SERVICE_PREFIX": "myproj",
                "DATABASE_URL": f"postgres://localhost/myapp_{scope}",
            }

    runner = FakeSubprocessRunner()
    svc = ServiceFanOutService(
        subprocess_runner=runner,
        workspace_root=WS,
        service_prefix="winter",
        env_provisioner=_FakeProvisioner(),
    )

    svc.up([_cell(_pa())])

    assert len(runner.call_envs) == 1
    call_env = runner.call_envs[0]
    assert call_env["WINTER_ENV"] == "alpha"
    assert call_env["WINTER_PORT_BASE"] == "4060"
    assert call_env["WINTER_SERVICE_PREFIX"] == "myproj"
    assert call_env["DATABASE_URL"] == "postgres://localhost/myapp_alpha"


def test_down_injects_provisioned_env_vars_when_provisioner_present() -> None:
    """When an env_provisioner is present, its computed vars are merged into the down subprocess env."""

    class _FakeProvisioner:
        def compute(self, scope: str) -> dict[str, str]:
            return {
                "WINTER_ENV": scope,
                "WINTER_PORT_BASE": "4060",
                "WINTER_SERVICE_PREFIX": "myproj",
                "DATABASE_URL": f"postgres://localhost/myapp_{scope}",
            }

    runner = FakeSubprocessRunner()
    svc = ServiceFanOutService(
        subprocess_runner=runner,
        workspace_root=WS,
        service_prefix="winter",
        env_provisioner=_FakeProvisioner(),
    )

    svc.down([_cell(_pb())])

    assert len(runner.call_envs) == 1
    call_env = runner.call_envs[0]
    assert call_env["WINTER_ENV"] == "alpha"
    assert call_env["WINTER_PORT_BASE"] == "4060"
    assert call_env["WINTER_SERVICE_PREFIX"] == "myproj"
    assert call_env["DATABASE_URL"] == "postgres://localhost/myapp_alpha"


def test_up_no_provisioned_env_vars_when_provisioner_absent() -> None:
    """Without an env_provisioner, scope vars are not injected into the subprocess env."""
    runner = FakeSubprocessRunner()
    svc = _make_fan_out(runner)

    svc.up([_cell(_pa())])

    call_env = runner.call_envs[0]
    assert "WINTER_ENV" not in call_env


def test_up_provisions_each_unique_scope_once() -> None:
    """A scope shared by multiple cells (multi-provider) is provisioned exactly once."""

    class _CountingProvisioner:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def compute(self, scope: str) -> dict[str, str]:
            self.calls.append(scope)
            return {"WINTER_ENV": scope}

    provisioner = _CountingProvisioner()
    runner = FakeSubprocessRunner()
    svc = ServiceFanOutService(
        subprocess_runner=runner,
        workspace_root=WS,
        service_prefix="winter",
        env_provisioner=provisioner,
    )

    svc.up([_cell(_pa(), scope="alpha"), _cell(_pb(), scope="alpha"), _cell(_pa(), scope="beta")])

    assert provisioner.calls == ["alpha", "beta"]


# ── env provision error resilience ───────────────────────────────────────────


# ── per-scope band selection regression ──────────────────────────────────────


def test_up_workspace_scope_injects_workspace_band_only() -> None:
    """Workspace scope: provisioner's output has workspace-band key but NOT feature-only key.

    Proves that the fan-out consumer passes the scope verbatim to compute()
    and injects the result without any second band-selection code path.
    A provisioner simulating [env.workspace.vars] SHARED + [env.feature.vars] FEAT_ONLY
    returns only SHARED at workspace scope; FEAT_ONLY must not appear in the env.
    """

    class _BandProvisioner:
        def compute(self, scope: str) -> dict[str, str]:
            if scope == "workspace":
                return {"SHARED": "ws_val"}
            return {"SHARED": "feat_override", "FEAT_ONLY": "feat_val"}

    runner = FakeSubprocessRunner()
    svc = ServiceFanOutService(
        subprocess_runner=runner,
        workspace_root=WS,
        service_prefix="winter",
        env_provisioner=_BandProvisioner(),
    )

    svc.up([_cell(_pa(), scope="workspace", positional="workspace")])

    assert len(runner.call_envs) == 1
    call_env = runner.call_envs[0]
    assert call_env["SHARED"] == "ws_val"
    assert "FEAT_ONLY" not in call_env


def test_up_feature_scope_injects_both_bands_feature_wins_collision() -> None:
    """Feature scope: provisioner's output has both workspace-band and feature-band keys.

    Proves that the fan-out consumer passes the scope verbatim to compute()
    and injects the result without any second band-selection code path.
    A provisioner simulating [env.workspace.vars] SHARED + [env.feature.vars] SHARED/FEAT_ONLY
    returns both SHARED (feature value wins collision) and FEAT_ONLY at feature scope.
    """

    class _BandProvisioner:
        def compute(self, scope: str) -> dict[str, str]:
            if scope == "workspace":
                return {"SHARED": "ws_val"}
            return {"SHARED": "feat_override", "FEAT_ONLY": "feat_val"}

    runner = FakeSubprocessRunner()
    svc = ServiceFanOutService(
        subprocess_runner=runner,
        workspace_root=WS,
        service_prefix="winter",
        env_provisioner=_BandProvisioner(),
    )

    svc.up([_cell(_pa())])

    assert len(runner.call_envs) == 1
    call_env = runner.call_envs[0]
    assert call_env["SHARED"] == "feat_override"
    assert call_env["FEAT_ONLY"] == "feat_val"


def test_provision_error_does_not_raise_on_up_or_down() -> None:
    """A ValueError from the provisioner degrades to no-injection; up/down do not raise."""

    class _ErrorProvisioner:
        def compute(self, scope: str) -> dict[str, str]:
            raise ValueError(f"bad template for {scope}")

    class _FakeReporter:
        def __init__(self) -> None:
            self.provision_errors: list[tuple[str, str]] = []

        def env_provision_error(self, scope: str, detail: str) -> None:
            self.provision_errors.append((scope, detail))

    runner = FakeSubprocessRunner()
    reporter = _FakeReporter()
    svc = ServiceFanOutService(
        subprocess_runner=runner,
        workspace_root=WS,
        service_prefix="winter",
        env_provisioner=_ErrorProvisioner(),
        reporter=reporter,  # type: ignore[arg-type]
    )

    # up must not raise; provider still runs (degraded to no injection)
    code_up = svc.up([_cell(_pa())])
    assert code_up == 0

    # down must not raise; provider still runs
    code_down = svc.down([_cell(_pa())])
    assert code_down == 0

    # reporter received env_provision_error for each call (one up + one down)
    assert len(reporter.provision_errors) == 2
    assert all(scope == "alpha" for scope, _ in reporter.provision_errors)

    # The provider did run despite the error (both up and down invocations)
    call_cmds = [tuple(c[0]) for c in runner.call_calls]
    assert (_EP_A, "up", "alpha") in call_cmds
    assert (_EP_A, "down", "alpha") in call_cmds

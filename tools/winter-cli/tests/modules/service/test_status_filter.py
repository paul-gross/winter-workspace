from __future__ import annotations

import json

from winter_cli.modules.service.status_filter import filter_status
from winter_cli.modules.service.status_models import EnvStatus, ServiceStatus, StatusDocument
from winter_cli.modules.service.status_parser import StatusDocumentParser

# ── helpers ───────────────────────────────────────────────────────────────────


def _svc(name: str, state: str = "running", health: str = "healthy") -> ServiceStatus:
    return ServiceStatus(
        name=name,
        state=state,
        health=health,
        ports=(8080,),
        handle=None,
        log_path=None,
        since=None,
    )


def _env(env_name: str, *service_names: str) -> EnvStatus:
    return EnvStatus(
        env=env_name,
        session=f"mp-{env_name}",
        port_base=4020,
        services=tuple(_svc(n) for n in service_names),
    )


def _doc(*envs: EnvStatus) -> StatusDocument:
    return StatusDocument(envs=tuple(envs))


def _svc_names(env: EnvStatus) -> list[str]:
    return [svc.name for svc in env.services]


def _env_names(doc: StatusDocument) -> list[str]:
    return [env.env for env in doc.envs]


# ── no patterns → identity ────────────────────────────────────────────────────


def test_no_patterns_returns_document_unchanged() -> None:
    """filter_status with empty patterns must return the original document object."""
    doc = _doc(_env("alpha", "api", "worker"))
    result = filter_status(doc, ())
    assert result is doc


def test_no_patterns_multi_env_returns_document_unchanged() -> None:
    doc = _doc(_env("alpha", "api"), _env("beta", "backend"))
    result = filter_status(doc, ())
    assert result is doc


# ── bare <env> pattern → all services in that env, other envs dropped ─────────


def test_bare_env_pattern_keeps_all_services_in_that_env() -> None:
    """A bare 'alpha' pattern (no slash) expands to alpha/* and keeps all alpha services."""
    doc = _doc(_env("alpha", "api", "worker"), _env("beta", "backend"))
    result = filter_status(doc, ("alpha",))

    assert _env_names(result) == ["alpha"]
    assert set(_svc_names(result.envs[0])) == {"api", "worker"}


def test_bare_env_pattern_drops_other_env() -> None:
    doc = _doc(_env("alpha", "api"), _env("beta", "api"))
    result = filter_status(doc, ("alpha",))

    assert _env_names(result) == ["alpha"]


# ── literal <env>/<svc> → single service matched ─────────────────────────────


def test_literal_env_svc_pattern_matches_single_service() -> None:
    doc = _doc(_env("alpha", "api", "worker", "db"))
    result = filter_status(doc, ("alpha/api",))

    assert len(result.envs) == 1
    assert _svc_names(result.envs[0]) == ["api"]


def test_literal_env_svc_drops_non_matching_service_in_same_env() -> None:
    doc = _doc(_env("alpha", "api", "worker"))
    result = filter_status(doc, ("alpha/api",))

    assert "worker" not in _svc_names(result.envs[0])


def test_literal_env_svc_drops_same_svc_in_other_env() -> None:
    doc = _doc(_env("alpha", "api"), _env("beta", "api"))
    result = filter_status(doc, ("alpha/api",))

    assert _env_names(result) == ["alpha"]


# ── wildcard */backend → backend across all envs ─────────────────────────────


def test_cross_env_star_keeps_named_service_across_all_envs() -> None:
    """*/backend keeps the backend service from every env, drops all others."""
    doc = _doc(
        _env("alpha", "api", "backend"),
        _env("beta", "backend", "worker"),
        _env("gamma", "api"),
    )
    result = filter_status(doc, ("*/backend",))

    assert set(_env_names(result)) == {"alpha", "beta"}
    for env in result.envs:
        assert _svc_names(env) == ["backend"]


def test_cross_env_star_drops_env_with_no_matching_service() -> None:
    doc = _doc(_env("alpha", "api"), _env("beta", "backend"))
    result = filter_status(doc, ("*/backend",))

    assert _env_names(result) == ["beta"]


# ── env with zero surviving services is dropped ───────────────────────────────


def test_env_with_no_surviving_services_is_dropped() -> None:
    doc = _doc(_env("alpha", "api"), _env("beta", "worker"))
    result = filter_status(doc, ("alpha/api",))

    assert _env_names(result) == ["alpha"]
    assert len(result.envs) == 1


def test_all_envs_emptied_returns_empty_document() -> None:
    doc = _doc(_env("alpha", "api"), _env("beta", "worker"))
    result = filter_status(doc, ("gamma/nonexistent",))

    assert result.envs == ()


# ── wildcard in service segment ───────────────────────────────────────────────


def test_env_star_service_wildcard_keeps_matching_services() -> None:
    doc = _doc(_env("alpha", "worker-a", "worker-b", "api"))
    result = filter_status(doc, ("alpha/worker-*",))

    assert set(_svc_names(result.envs[0])) == {"worker-a", "worker-b"}
    assert "api" not in _svc_names(result.envs[0])


# ── multi-pattern union ───────────────────────────────────────────────────────


def test_multi_pattern_union_keeps_all_matching_across_envs() -> None:
    doc = _doc(
        _env("alpha", "api", "db"),
        _env("beta", "backend", "db"),
    )
    result = filter_status(doc, ("alpha/api", "beta/backend"))

    alpha = next(e for e in result.envs if e.env == "alpha")
    beta = next(e for e in result.envs if e.env == "beta")
    assert _svc_names(alpha) == ["api"]
    assert _svc_names(beta) == ["backend"]


# ── result is a new document (not mutated) ────────────────────────────────────


def test_filter_returns_new_document_not_mutated_original() -> None:
    doc = _doc(_env("alpha", "api", "worker"))
    result = filter_status(doc, ("alpha/api",))

    # Original is untouched.
    assert len(doc.envs[0].services) == 2
    # Result is a distinct object.
    assert result is not doc


# ── env_status fields preserved through filter ────────────────────────────────


def test_env_metadata_preserved_through_filter() -> None:
    """session and port_base on the env are preserved after filtering."""
    env = EnvStatus(
        env="alpha",
        session="mp-alpha",
        port_base=4020,
        services=(_svc("api"), _svc("worker")),
    )
    doc = StatusDocument(envs=(env,))
    result = filter_status(doc, ("alpha/api",))

    assert result.envs[0].session == "mp-alpha"
    assert result.envs[0].port_base == 4020


# ── parse → filter integration ────────────────────────────────────────────────


def test_parse_then_filter_roundtrip() -> None:
    """Parsing a real JSON document and then filtering it produces correct results."""
    raw = json.dumps(
        {
            "envs": [
                {
                    "env": "alpha",
                    "session": "mp-alpha",
                    "port_base": 4020,
                    "services": [
                        {
                            "name": "api",
                            "state": "running",
                            "health": "healthy",
                            "ports": [8080],
                            "handle": None,
                            "log_path": None,
                            "since": None,
                        },
                        {
                            "name": "worker",
                            "state": "stopped",
                            "health": "unknown",
                            "ports": [],
                            "handle": None,
                            "log_path": None,
                            "since": None,
                        },
                    ],
                },
                {
                    "env": "beta",
                    "session": "mp-beta",
                    "port_base": 4040,
                    "services": [
                        {
                            "name": "api",
                            "state": "running",
                            "health": "healthy",
                            "ports": [8081],
                            "handle": None,
                            "log_path": None,
                            "since": None,
                        },
                    ],
                },
            ]
        }
    )
    doc = StatusDocumentParser().parse(raw)
    result = filter_status(doc, ("*/api",))

    assert set(_env_names(result)) == {"alpha", "beta"}
    for env in result.envs:
        assert _svc_names(env) == ["api"]

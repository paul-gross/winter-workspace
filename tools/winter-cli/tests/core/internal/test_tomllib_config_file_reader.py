from __future__ import annotations

import io
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from winter_cli.core.config_file import ConfigFileReadError
from winter_cli.core.internal import tomllib_config_file_reader
from winter_cli.core.internal.tomllib_config_file_reader import TomllibConfigFileReader


def test_load_returns_parsed_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    toml_bytes = b'key = "value"\ncount = 42\n'

    fake_tomllib = MagicMock()
    fake_tomllib.load.return_value = {"key": "value", "count": 42}
    fake_tomllib.TOMLDecodeError = tomllib.TOMLDecodeError
    monkeypatch.setattr(tomllib_config_file_reader, "tomllib", fake_tomllib)
    monkeypatch.setattr(
        Path,
        "open",
        lambda self, mode="r": MagicMock(
            __enter__=lambda s: io.BytesIO(toml_bytes),
            __exit__=lambda *a: None,
        ),
    )

    result = TomllibConfigFileReader.load(tmp_path / "config.toml")

    assert result == {"key": "value", "count": 42}
    fake_tomllib.load.assert_called_once()


def test_load_raises_config_read_error_on_oserror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        Path,
        "open",
        lambda self, mode="r": (_ for _ in ()).throw(OSError("file not found")),
    )

    with pytest.raises(ConfigFileReadError, match="file not found"):
        TomllibConfigFileReader.load(tmp_path / "missing.toml")


def test_load_raises_config_read_error_on_toml_decode_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_tomllib = MagicMock()
    fake_tomllib.TOMLDecodeError = tomllib.TOMLDecodeError
    fake_tomllib.load.side_effect = tomllib.TOMLDecodeError("invalid toml", 0, 0)
    monkeypatch.setattr(tomllib_config_file_reader, "tomllib", fake_tomllib)
    monkeypatch.setattr(
        Path,
        "open",
        lambda self, mode="r": MagicMock(
            __enter__=lambda s: io.BytesIO(b"not valid [toml"),
            __exit__=lambda *a: None,
        ),
    )

    with pytest.raises(ConfigFileReadError):
        TomllibConfigFileReader.load(tmp_path / "bad.toml")

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from winter_cli.core.internal import local_filesystem
from winter_cli.core.internal.local_filesystem import LocalFilesystem


def test_exists_delegates_to_path_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "exists", lambda self: True)
    assert LocalFilesystem.exists(tmp_path) is True


def test_is_file_delegates_to_path_is_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    assert LocalFilesystem.is_file(tmp_path) is False


def test_is_dir_delegates_to_path_is_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    assert LocalFilesystem.is_dir(tmp_path) is True


def test_is_symlink_delegates_to_path_is_symlink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "is_symlink", lambda self: False)
    assert LocalFilesystem.is_symlink(tmp_path) is False


def test_iterdir_returns_list_of_children(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    children = [tmp_path / "a", tmp_path / "b"]
    monkeypatch.setattr(Path, "iterdir", lambda self: iter(children))
    assert LocalFilesystem.iterdir(tmp_path) == children


def test_read_text_delegates_to_path_read_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "read_text", lambda self: "hello")
    assert LocalFilesystem.read_text(tmp_path / "f.txt") == "hello"


def test_read_bytes_delegates_to_path_read_bytes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"data")
    assert LocalFilesystem.read_bytes(tmp_path / "f.bin") == b"data"


def test_readlink_delegates_to_path_readlink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "target"
    monkeypatch.setattr(Path, "readlink", lambda self: target)
    assert LocalFilesystem.readlink(tmp_path / "link") == target


def test_access_x_ok_delegates_to_os_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_os = MagicMock()
    fake_os.access.return_value = True
    fake_os.X_OK = 1
    monkeypatch.setattr(local_filesystem, "os", fake_os)

    result = LocalFilesystem.access_x_ok(tmp_path / "script.sh")

    fake_os.access.assert_called_once_with(tmp_path / "script.sh", fake_os.X_OK)
    assert result is True


def test_mkdir_delegates_to_path_mkdir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(Path, "mkdir", lambda self, parents=False, exist_ok=False: calls.append((self, parents, exist_ok)))

    LocalFilesystem.mkdir(tmp_path / "newdir", parents=True, exist_ok=True)

    assert calls == [(tmp_path / "newdir", True, True)]


def test_write_text_delegates_to_path_write_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    written: list[tuple] = []
    monkeypatch.setattr(Path, "write_text", lambda self, data: written.append((self, data)))

    LocalFilesystem.write_text(tmp_path / "out.txt", "content")

    assert written == [(tmp_path / "out.txt", "content")]


def test_symlink_to_delegates_to_path_symlink_to(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(Path, "symlink_to", lambda self, target: calls.append((self, target)))

    LocalFilesystem.symlink_to(tmp_path / "link", tmp_path / "target")

    assert calls == [(tmp_path / "link", tmp_path / "target")]


def test_unlink_delegates_to_path_unlink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Path] = []
    monkeypatch.setattr(Path, "unlink", lambda self: calls.append(self))

    LocalFilesystem.unlink(tmp_path / "old.txt")

    assert calls == [tmp_path / "old.txt"]


def test_rmtree_delegates_to_shutil_rmtree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_shutil = MagicMock()
    monkeypatch.setattr(local_filesystem, "shutil", fake_shutil)

    LocalFilesystem.rmtree(tmp_path / "obsolete")

    fake_shutil.rmtree.assert_called_once_with(tmp_path / "obsolete")


def test_rmtree_raises_oserror_when_shutil_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_shutil = MagicMock()
    fake_shutil.rmtree.side_effect = OSError("permission denied")
    monkeypatch.setattr(local_filesystem, "shutil", fake_shutil)

    with pytest.raises(OSError, match="permission denied"):
        LocalFilesystem.rmtree(tmp_path / "locked")


def test_append_lines_writes_newline_terminated_lines(tmp_path: Path) -> None:
    out = tmp_path / "append.txt"
    out.write_text("existing\n")
    LocalFilesystem.append_lines(out, ["line1", "line2\n"])
    assert out.read_text() == "existing\nline1\nline2\n"

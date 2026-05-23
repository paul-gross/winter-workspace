from __future__ import annotations

import click
import pytest

from winter_cli.core.internal.click_cli_input_validation_service import (
    ClickCliInputValidationService,
)


@pytest.fixture
def svc() -> ClickCliInputValidationService:
    return ClickCliInputValidationService()


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/foo/bar.git",
        "https://github.com/foo/bar",
        "http://example.com/foo/bar.git",
        "ssh://codeberg.org/pgross/winter.git",
        "git://example.com/foo.git",
        "git@codeberg.org:pgross/winter.git",
        "git@codeberg.org:pgross/winter",
    ],
)
def test_validate_git_url_accepts_recognized_shapes(svc: ClickCliInputValidationService, url: str) -> None:
    # Returns None (does not raise) on success.
    assert svc.validate_git_url(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "ftp://example.com/foo.git",
        "/local/path/repo.git",
        "github.com/foo/bar",  # missing scheme and no user@host:path shape
    ],
)
def test_validate_git_url_rejects_invalid_inputs(svc: ClickCliInputValidationService, url: str) -> None:
    with pytest.raises(click.ClickException) as ei:
        svc.validate_git_url(url)
    assert "Invalid git URL" in ei.value.message

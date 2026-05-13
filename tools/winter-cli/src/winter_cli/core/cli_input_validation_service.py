from __future__ import annotations

import re

import click


class CliInputValidationService:
    """Validates user-provided CLI inputs and raises click errors on rejection."""

    _GIT_URL_RE = re.compile(
        r"^("
        r"(https?|ssh|git)://[\w.+-]+(:\d+)?(/[\w./+~_-]+)?(\.git)?/?"
        r"|"
        r"[\w.+-]+@[\w.+-]+:[\w./+~_-]+(\.git)?"
        r")$"
    )

    def validate_git_url(self, url: str) -> None:
        """Reject anything that isn't a recognizable http(s)/ssh/git URL or scp-style user@host:path."""
        if not self._GIT_URL_RE.match(url):
            raise click.ClickException(
                f"Invalid git URL: {url!r}. Expected http(s)://host/path, "
                f"ssh://user@host/path, git://host/path, or user@host:path."
            )

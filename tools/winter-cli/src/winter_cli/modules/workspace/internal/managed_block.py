"""Idempotent managed-block helpers shared by extensions and init.

A managed block is a marker-bracketed range in a text file (e.g. `.git/info/exclude`)
that winter rewrites on every run. Lines outside the markers are preserved.
"""

from __future__ import annotations

GITIGNORE_BEGIN = "# >>> {name} (managed by winter)"
GITIGNORE_END = "# <<< {name}"


def replace_or_append_block(
    content: str,
    begin: str,
    end: str,
    desired_lines: list[str],
) -> str:
    """Replace the block between `begin` and `end` markers with `desired_lines`.

    `desired_lines` must include the begin/end markers. If the block is absent,
    it's appended to the end (preceded by a blank line if needed). If the file
    has the begin marker but not the end marker, the block is treated as
    extending to end-of-file and replaced wholesale.
    """
    lines = content.split("\n") if content else []
    try:
        begin_idx = lines.index(begin)
    except ValueError:
        begin_idx = -1

    if begin_idx >= 0:
        try:
            end_offset = lines[begin_idx:].index(end)
        except ValueError:
            # Malformed block — replace from begin to end of file.
            end_idx = len(lines) - 1
        else:
            end_idx = begin_idx + end_offset
        new_lines = lines[:begin_idx] + desired_lines + lines[end_idx + 1 :]
    else:
        new_lines = list(lines)
        # Ensure separation from preceding content.
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.extend(desired_lines)

    # Ensure trailing newline.
    result = "\n".join(new_lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def strip_block(content: str, begin: str, end: str) -> str:
    """Remove a marker-bracketed block (and any blank line before it) if present.

    No-op if the block isn't found. Used when the set of eligible items
    becomes empty — keeps managed files tidy when entries are removed.
    """
    lines = content.split("\n") if content else []
    try:
        begin_idx = lines.index(begin)
    except ValueError:
        return content
    try:
        end_offset = lines[begin_idx:].index(end)
    except ValueError:
        end_idx = len(lines) - 1
    else:
        end_idx = begin_idx + end_offset
    # Also drop a single preceding blank line so we don't leave double-blanks behind.
    drop_from = begin_idx
    if drop_from > 0 and lines[drop_from - 1].strip() == "":
        drop_from -= 1
    new_lines = lines[:drop_from] + lines[end_idx + 1 :]
    result = "\n".join(new_lines)
    if result and not result.endswith("\n"):
        result += "\n"
    return result

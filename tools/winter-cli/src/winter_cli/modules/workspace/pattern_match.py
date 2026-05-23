from __future__ import annotations

import fnmatch


def matches_pattern(env_name: str, repo_name: str, pattern: str) -> bool:
    """Match `<env>/<repo>` against a segment-aware glob.

    Bare patterns (no '/') are treated as `<pattern>/*`. Each segment uses
    fnmatch — `*` matches anything within a segment, `?` matches one char.
    `*` does not cross `/`, so `*/winter` matches every env's winter worktree
    but not `alpha/winter-product`.
    """
    if "/" not in pattern:
        pattern = f"{pattern}/*"
    env_pat, repo_pat = pattern.split("/", 1)
    return fnmatch.fnmatchcase(env_name, env_pat) and fnmatch.fnmatchcase(repo_name, repo_pat)


def matches_any_pattern(env_name: str, repo_name: str, patterns: list[str]) -> bool:
    return any(matches_pattern(env_name, repo_name, p) for p in patterns)

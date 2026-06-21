#!/usr/bin/env python3
"""Module-extractability lint for the winter ecosystem.

A winter module (an extension shipping a `winter-ext.toml`) is developed inside
this multi-repo workspace but installed standalone elsewhere. So every outbound
reference it makes — a `<context>:/path` path-notation reference, a Claude
`@import`, or its rewritten plain-path read instruction (`always read ./path`,
the cross-harness form from issue #84) — must resolve to something the module is guaranteed to have when it
ships alone: itself, core (`winter` / `winter-cli` / `workspace`), or a module
it explicitly declares in its `winter-ext.toml` `requires`. A reference to an
undeclared sibling is a dead pointer at the consumption edge; a core module
pointing at an extension is a layering inversion.

This is a `winter lint` check (see `winter-cli` setup.md "Lint checks"). It runs
with the lint env contract and emits NDJSON findings on stdout. It is
*graph-driven*: rather than rebuilding the ecosystem dependency graph itself, it
calls back into the CLI that launched it — `$WINTER_CLI graph --json` — for the
global graph (the set of known modules and the edges used for cycle detection).
A module's own `requires` is read from the local `winter-ext.toml` of the
checkout being linted, so the check validates *this* checkout's content against
*this* checkout's declarations.

WINTER_CLI is required. If it is unset the check fails loudly — there is no
degraded, graph-less mode.

Functional vs. illustrative: every reference is treated as a real dependency by
default. A reference that is only an illustrative example (a conventions doc
citing another module to show the notation, not to depend on it) is exempted by
placing the marker `<!-- winter-lint:example -->` on the same line.

Env contract (from `winter lint`):
  WINTER_CLI            path to the winter CLI to call back into (required)
  WINTER_WORKSPACE_DIR  absolute workspace root
  WINTER_LINT_PATHS     newline-delimited absolute paths in scope (files or dirs)
  WINTER_LINT_SCOPE     scope kind (all/repo/env/changed) — informational

Standalone: `WINTER_CLI=$(command -v winter) python3 extractability.py <path>...`
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

CHECK = "extractability"

# Core contexts: always a valid reference target, and never permitted to depend
# on an extension. "core" is a rule this linter owns, not data in the graph.
CORE = frozenset({"winter", "winter-cli", "workspace"})

MANIFEST = "winter-ext.toml"

# Directories never worth walking under an --all scope.
PRUNE_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"})

# `<context>:/path` — capture the context, then filter to winter contexts so we
# never trip on `https:/`, `file:/`, etc. The lookbehind keeps us off mid-token
# matches like `apphttps:/`.
_REF_RE = re.compile(r"(?<![A-Za-z0-9_./-])([a-z][a-z0-9-]*):/")

# Claude `@import` at the start of a line. Guarded later to a path-shaped target
# so `@param`-style mentions don't register.
_IMPORT_RE = re.compile(r"^\s*@(\S+)")

# Rewritten `@import` (issue #84): a high-emphasis plain-path read instruction
# emitted for non-Claude harnesses, e.g. `IMPORTANT: always read ./ai/x.md`. The
# `@` is dropped, so this form is matched by the `read` verb plus a relative
# (`./` or `../`) path. Optional surrounding backticks are tolerated.
_READ_REF_RE = re.compile(r"\bread\s+`?(\.{1,2}/[^\s`]+)")

# Same-line illustrative-example exemption marker.
_MARKER_RE = re.compile(r"<!--\s*winter-lint:\s*example\s*-->", re.IGNORECASE)


class GraphError(Exception):
    """The `winter graph` callback could not be run or parsed."""


@dataclass(frozen=True)
class Finding:
    status: str
    message: str
    file: str | None = None
    line: int | None = None
    remediation: str | None = None

    def to_json(self) -> str:
        payload: dict[str, object] = {"check": CHECK, "status": self.status, "message": self.message}
        if self.file is not None:
            payload["file"] = self.file
        if self.line is not None:
            payload["line"] = self.line
        if self.remediation is not None:
            payload["remediation"] = self.remediation
        return json.dumps(payload)


# ── services ────────────────────────────────────────────────────────────────


class GraphClient:
    """Fetches the workspace dependency graph from the winter CLI."""

    def __init__(self, winter_cli_path: str) -> None:
        self._winter_cli_path = winter_cli_path

    def fetch_graph(self, cwd: Path) -> dict[str, list[str]]:
        """Run `$WINTER_CLI graph --json` and parse the adjacency map."""
        try:
            result = subprocess.run(
                [self._winter_cli_path, "graph", "--json"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise GraphError(f"could not run `{self._winter_cli_path} graph --json`: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            raise GraphError(f"`{self._winter_cli_path} graph --json` failed: {detail}")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise GraphError(f"`{self._winter_cli_path} graph --json` produced invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise GraphError("`winter graph --json` did not return a JSON object")
        return {str(k): [str(v) for v in (vs or [])] for k, vs in data.items()}


class ManifestReader:
    """Reads winter-ext.toml manifests to determine module identity and requirements."""

    def _read_manifest(self, path: Path) -> dict:
        try:
            with path.open("rb") as fh:
                return tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            return {}

    def module_name(self, manifest_path: Path) -> str:
        """A module's identity — its `name`, falling back to its directory name."""
        data = self._read_manifest(manifest_path)
        name = data.get("name")
        return name if isinstance(name, str) and name else manifest_path.parent.name

    def module_requires(self, manifest_path: Path) -> frozenset[str]:
        data = self._read_manifest(manifest_path)
        raw = data.get("requires")
        if not isinstance(raw, list):
            return frozenset()
        return frozenset(r for r in raw if isinstance(r, str) and r)

    def owning_module(self, path: Path, workspace_root: Path) -> tuple[str, Path]:
        """Resolve `path` to (module-name, module-root).

        Walks up to the nearest ancestor with a `winter-ext.toml`. Anything not
        under such a module belongs to the `workspace` module, rooted at the
        workspace root.
        """
        cur = path if path.is_dir() else path.parent
        root = workspace_root.resolve()
        while True:
            manifest = cur / MANIFEST
            if manifest.is_file():
                return self.module_name(manifest), cur
            if cur.resolve() == root or cur.parent == cur:
                return "workspace", workspace_root
            cur = cur.parent


class ReferenceScanner:
    """Scans markdown files for winter path-notation references and @imports."""

    def references_in_line(self, line: str) -> list[str]:
        """Winter `<context>:` reference contexts on a line (may repeat)."""
        return [m.group(1) for m in _REF_RE.finditer(line) if self._is_winter_context(m.group(1))]

    def import_raw_path(self, line: str) -> str | None:
        """Relative path referenced by a line's `@import` or rewritten read instruction.

        Accepts both reference forms as equivalent: a line-leading Claude
        `@import` (`@ai/x.md`) and the rewritten plain-path read instruction
        (`IMPORTANT: always read ./ai/x.md`). Returns the raw path string, or
        None when the line carries neither.
        """
        m = _IMPORT_RE.match(line)
        if m:
            return m.group(1)
        m = _READ_REF_RE.search(line)
        if m:
            return m.group(1).rstrip(".,;:")
        return None

    def import_target_module(
        self,
        line: str,
        file: Path,
        owner_root: Path,
        workspace_root: Path,
        manifest_reader: ManifestReader,
    ) -> str | None:
        """Module a line's `@import` (or rewritten read instruction) points at, if it escapes the owner module.

        Returns the target module name when the reference resolves outside the
        owning module's root (a cross-module dependency), else None (internal
        reference, or not a reference-shaped line).
        """
        raw = self.import_raw_path(line)
        if raw is None:
            return None
        if "/" not in raw and "." not in raw:  # `@param`-style, not a path import
            return None
        target = (file.parent / raw).resolve()
        try:
            target.relative_to(owner_root.resolve())
            return None  # internal to the module
        except ValueError:
            pass
        name, _ = manifest_reader.owning_module(target, workspace_root)
        return name

    def collect_md_files(self, paths: list[Path]) -> list[Path]:
        out: list[Path] = []
        seen: set[Path] = set()
        for p in paths:
            if p.is_file():
                if p.suffix == ".md" and p not in seen:
                    seen.add(p)
                    out.append(p)
                continue
            for dirpath, dirnames, filenames in os.walk(p):
                dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
                for name in filenames:
                    if name.endswith(".md"):
                        f = Path(dirpath) / name
                        if f not in seen:
                            seen.add(f)
                            out.append(f)
        return out

    def _is_winter_context(self, ctx: str) -> bool:
        return ctx == "workspace" or ctx == "winter" or ctx.startswith("winter-")


class ExtractabilityLint:
    """Orchestrates extractability checks over a set of paths."""

    def __init__(
        self,
        graph_client: GraphClient,
        manifest_reader: ManifestReader,
        scanner: ReferenceScanner,
    ) -> None:
        self._graph_client = graph_client
        self._manifest_reader = manifest_reader
        self._scanner = scanner

    def check_paths(
        self,
        paths: list[Path],
        graph: dict[str, list[str]],
        workspace_root: Path,
    ) -> list[Finding]:
        """Validate every winter reference in the in-scope markdown files."""
        known = frozenset(graph.keys())
        findings: list[Finding] = []
        requires_cache: dict[Path, frozenset[str]] = {}

        for file in self._scanner.collect_md_files(paths):
            owner, owner_root = self._manifest_reader.owning_module(file, workspace_root)
            manifest = owner_root / MANIFEST
            if manifest not in requires_cache:
                requires_cache[manifest] = (
                    self._manifest_reader.module_requires(manifest)
                    if owner != "workspace"
                    else frozenset()
                )
            owner_requires = requires_cache[manifest]

            try:
                lines = file.read_text(errors="replace").splitlines()
            except OSError:
                continue

            in_fence = False
            for lineno, line in enumerate(lines, start=1):
                stripped = line.lstrip()
                # References inside a fenced code block are illustrative literals
                # (sample commands, example prompts) — skip the whole fence.
                if stripped.startswith("```") or stripped.startswith("~~~"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                if _MARKER_RE.search(line):
                    continue
                targets = self._scanner.references_in_line(line)
                imp = self._scanner.import_target_module(
                    line, file, owner_root, workspace_root, self._manifest_reader
                )
                if imp is not None:
                    targets.append(imp)
                for target in targets:
                    verdict = self._classify(owner, owner_requires, target, known)
                    if verdict is not None:
                        findings.append(
                            Finding(
                                status=verdict.status,
                                message=verdict.message,
                                file=self._relpath(file, workspace_root),
                                line=lineno,
                                remediation=verdict.remediation,
                            )
                        )
        return findings

    def cycle_findings(self, graph: dict[str, list[str]]) -> list[Finding]:
        findings: list[Finding] = []
        for cycle in self._detect_cycles(graph):
            chain = " → ".join(cycle)
            findings.append(
                Finding(
                    status="fail",
                    message=f"dependency cycle in `requires`: {chain}",
                    remediation="Break the cycle — a module's requires graph must be acyclic.",
                )
            )
        return findings

    def _classify(
        self,
        owner: str,
        owner_requires: frozenset[str],
        target: str,
        known: frozenset[str],
    ) -> Finding | None:
        """Apply the extractability rules to one reference; None when allowed."""
        if target == owner:
            return None
        if owner in CORE:
            if target in CORE:
                return None
            return Finding(
                status="fail",
                message=f"core module `{owner}` references extension `{target}` (layering violation)",
                remediation=f"A foundation must not depend on an extension. Drop the reference, move the "
                f"content into core, or mark it `<!-- winter-lint:example -->` if purely illustrative.",
            )
        if target in CORE:
            return None
        if target in owner_requires:
            return None
        if target in known:
            return Finding(
                status="fail",
                message=f"`{owner}` references `{target}` but does not declare it in `requires`",
                remediation=f"Add `{target}` to {owner}'s {MANIFEST} `requires`, or mark the reference "
                f"`<!-- winter-lint:example -->` if it is only an illustration.",
            )
        return Finding(
            status="fail",
            message=f"`{owner}` references unknown / uninstalled module `{target}`",
            remediation=f"Declare `{target}` in `requires` if it is a real dependency, or mark the "
            f"reference `<!-- winter-lint:example -->` if it is only an illustration.",
        )

    def _detect_cycles(self, graph: dict[str, list[str]]) -> list[list[str]]:
        """Return each `requires` cycle as a node list (first node repeated at end)."""
        color: dict[str, int] = {}  # 0=visiting, 1=done
        stack: list[str] = []
        cycles: list[list[str]] = []
        seen_keys: set[frozenset[str]] = set()

        def visit(node: str) -> None:
            color[node] = 0
            stack.append(node)
            for dep in graph.get(node, []):
                if dep not in graph:  # unknown target — the reference check owns this
                    continue
                if color.get(dep) == 0:
                    cycle = stack[stack.index(dep):] + [dep]
                    key = frozenset(cycle)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        cycles.append(cycle)
                elif dep not in color:
                    visit(dep)
            stack.pop()
            color[node] = 1

        for node in graph:
            if node not in color:
                visit(node)
        return cycles

    def _relpath(self, file: Path, workspace_root: Path) -> str:
        try:
            return str(file.resolve().relative_to(workspace_root.resolve()))
        except ValueError:
            return str(file)


# ── entry point ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    env = os.environ
    workspace_root = Path(env.get("WINTER_WORKSPACE_DIR") or Path.cwd())
    winter_cli = env.get("WINTER_CLI")

    findings: list[Finding] = []
    if not winter_cli:
        findings.append(
            Finding(
                status="fail",
                message="WINTER_CLI is not set — extractability lint needs it to fetch the dependency graph",
                remediation="Run via `winter lint` (which sets WINTER_CLI), or set WINTER_CLI to the winter binary.",
            )
        )
    else:
        graph_client = GraphClient(winter_cli)
        manifest_reader = ManifestReader()
        scanner = ReferenceScanner()
        lint = ExtractabilityLint(graph_client, manifest_reader, scanner)

        raw = env.get("WINTER_LINT_PATHS")
        if raw is not None:
            paths = [Path(line) for line in raw.splitlines() if line.strip()]
        else:
            paths = [Path(a) for a in argv] or [workspace_root]

        try:
            graph = graph_client.fetch_graph(workspace_root)
        except GraphError as exc:
            findings.append(Finding(status="fail", message=str(exc)))
        else:
            findings.extend(lint.check_paths(paths, graph, workspace_root))
            findings.extend(lint.cycle_findings(graph))

    for finding in findings:
        print(finding.to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

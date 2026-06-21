from __future__ import annotations

import os
import sys
from pathlib import Path

from winter_cli.core.filesystem import IFilesystemReader
from winter_cli.core.subprocess_runner import ISubprocessRunner
from winter_cli.modules.lint.finding_parser import parse_lint_output
from winter_cli.modules.lint.models import LintCheckOutcome, LintFinding, LintScope, LintStatus
from winter_cli.modules.lint.scope_env import WINTER_CLI_VAR, lint_scope_env

# Source label shown in `winter lint` output for built-in core checks. Matches
# doctor's `CORE_SOURCE` so both surfaces read consistently — core checks ship
# with winter-cli and always run, unlike the opt-in workspace/extension scripts.
CORE_SOURCE = "core"

# The single built-in lint check: module extractability, which validates
# dependency direction across the ecosystem graph (a core module pointing at an
# extension is a layering inversion; an undeclared sibling reference is a dead
# pointer at the consumption edge).
EXTRACTABILITY_CHECK = "extractability"


def default_extractability_script_path() -> Path:
    """Absolute path to the bundled extractability lint script.

    The script lives in the winter repo's `tools/winter-lint/` directory, a
    sibling of the `tools/winter-cli/` tree this package's source resides in.
    Resolved relative to this file (the spec-loader pattern) so it works
    wherever the CLI runs from its source checkout — the only supported
    deployment, since the `winter` launcher always execs winter-cli from the
    workspace's own source tree.
    """
    # .../tools/winter-cli/src/winter_cli/modules/lint/core_lint_service.py
    #     parents[5] == .../tools
    return Path(__file__).resolve().parents[5] / "winter-lint" / "extractability.py"


class CoreLintService:
    """Runs winter's built-in lint checks — bundled with the CLI, always on.

    The lint counterpart of doctor's `CoreProbeService`: where the workspace and
    extension lint services *discover* opt-in scripts from `.winter/config.toml`
    and each `winter-ext.toml`, this service runs the checks that ship with
    winter itself, with no per-workspace registration. Today that is the single
    module-extractability check (`tools/winter-lint/extractability.py`).

    Returns one `LintCheckOutcome` tagged `source="core"` (even when the check
    finds nothing), so the dispatcher counts it as a contributor — or `None`
    when the bundled script can't be located, so an unusual install (winter-cli
    without its sibling `tools/winter-lint/`) degrades to "no core checks" rather
    than a spurious failure.
    """

    def __init__(
        self,
        workspace_root: Path,
        fs: IFilesystemReader,
        subprocess_runner: ISubprocessRunner,
        winter_cli_path: str,
        script_path: Path,
    ) -> None:
        self._workspace_root = workspace_root
        self._fs = fs
        self._subprocess = subprocess_runner
        self._winter_cli_path = winter_cli_path
        self._script_path = script_path

    def run(self, scope: LintScope) -> LintCheckOutcome | None:
        if not self._fs.is_file(self._script_path):
            return None

        env = os.environ.copy()
        env["WINTER_WORKSPACE_DIR"] = str(self._workspace_root)
        env[WINTER_CLI_VAR] = self._winter_cli_path
        env.update(lint_scope_env(scope))

        # Run under the same interpreter that launched winter-cli (guaranteed
        # >= 3.11, which extractability's `tomllib` use requires) rather than
        # the script's `python3` shebang, which may resolve to an older PATH
        # interpreter.
        try:
            result = self._subprocess.run(
                [sys.executable, str(self._script_path)],
                cwd=self._workspace_root,
                env=env,
            )
        except OSError as exc:
            return LintCheckOutcome(
                source=CORE_SOURCE,
                findings=[
                    LintFinding(
                        source=CORE_SOURCE,
                        check=EXTRACTABILITY_CHECK,
                        status=LintStatus.fail,
                        message=f"failed to invoke extractability lint: {exc}",
                    )
                ],
            )
        findings = parse_lint_output(CORE_SOURCE, result.stdout, result.stderr, result.returncode)
        return LintCheckOutcome(source=CORE_SOURCE, findings=findings)

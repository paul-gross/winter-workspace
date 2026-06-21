from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extractability as ext  # noqa: E402


class ClassifyTests(unittest.TestCase):
    KNOWN = frozenset({"winter-a", "winter-b", "winter-c"})

    def setUp(self) -> None:
        manifest_reader = ext.ManifestReader()
        scanner = ext.ReferenceScanner()
        self.lint = ext.ExtractabilityLint(
            graph_client=None,  # type: ignore[arg-type]
            manifest_reader=manifest_reader,
            scanner=scanner,
        )

    def test_self_reference_allowed(self) -> None:
        self.assertIsNone(self.lint._classify("winter-a", frozenset(), "winter-a", self.KNOWN))

    def test_core_target_allowed(self) -> None:
        for core in ("winter", "winter-cli", "workspace"):
            self.assertIsNone(self.lint._classify("winter-a", frozenset(), core, self.KNOWN))

    def test_declared_dependency_allowed(self) -> None:
        self.assertIsNone(self.lint._classify("winter-a", frozenset({"winter-b"}), "winter-b", self.KNOWN))

    def test_undeclared_sibling_fails(self) -> None:
        verdict = self.lint._classify("winter-a", frozenset(), "winter-c", self.KNOWN)
        assert verdict is not None
        self.assertEqual(verdict.status, "fail")
        self.assertIn("does not declare", verdict.message)

    def test_core_to_extension_is_layering_failure(self) -> None:
        verdict = self.lint._classify("workspace", frozenset(), "winter-a", self.KNOWN)
        assert verdict is not None
        self.assertEqual(verdict.status, "fail")
        self.assertIn("layering", verdict.message)

    def test_core_to_core_allowed(self) -> None:
        self.assertIsNone(self.lint._classify("workspace", frozenset(), "winter", self.KNOWN))

    def test_unknown_module_fails(self) -> None:
        verdict = self.lint._classify("winter-a", frozenset(), "winter-ghost", self.KNOWN)
        assert verdict is not None
        self.assertIn("unknown", verdict.message)


class ReferenceScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scanner = ext.ReferenceScanner()

    def test_extracts_winter_contexts(self) -> None:
        line = "see winter-harness:/python/x.md and workspace:/ai/y.md and winter:/z"
        self.assertEqual(self.scanner.references_in_line(line), ["winter-harness", "workspace", "winter"])

    def test_ignores_non_winter_schemes(self) -> None:
        self.assertEqual(self.scanner.references_in_line("a https://example.com and file:/tmp/x"), [])

    def test_marker_regex_matches(self) -> None:
        self.assertTrue(ext._MARKER_RE.search("x winter-x:/y <!-- winter-lint:example -->"))
        self.assertTrue(ext._MARKER_RE.search("<!--winter-lint:example-->"))


class CycleTests(unittest.TestCase):
    def setUp(self) -> None:
        manifest_reader = ext.ManifestReader()
        scanner = ext.ReferenceScanner()
        self.lint = ext.ExtractabilityLint(
            graph_client=None,  # type: ignore[arg-type]
            manifest_reader=manifest_reader,
            scanner=scanner,
        )

    def test_detects_cycle(self) -> None:
        cycles = self.lint._detect_cycles({"a": ["b"], "b": ["a"]})
        self.assertEqual(len(cycles), 1)

    def test_no_cycle(self) -> None:
        self.assertEqual(self.lint._detect_cycles({"a": ["b"], "b": []}), [])

    def test_ignores_edges_to_unknown_nodes(self) -> None:
        self.assertEqual(self.lint._detect_cycles({"a": ["ghost"]}), [])


class CheckPathsTests(unittest.TestCase):
    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def setUp(self) -> None:
        manifest_reader = ext.ManifestReader()
        scanner = ext.ReferenceScanner()
        self.lint = ext.ExtractabilityLint(
            graph_client=None,  # type: ignore[arg-type]
            manifest_reader=manifest_reader,
            scanner=scanner,
        )

    def test_end_to_end_rules(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # winter-a declares winter-b locally (graph deliberately omits it to
            # prove the owner's requires come from its local manifest).
            self._write(root / "modA" / "winter-ext.toml", 'name = "winter-a"\nrequires = ["winter-b"]\n')
            self._write(
                root / "modA" / "doc.md",
                "\n".join(
                    [
                        "declared winter-b:/x.md",          # ok (local requires)
                        "self winter-a:/me.md",             # ok
                        "core winter:/foo and workspace:/y",  # ok
                        "undeclared winter-c:/z.md",        # FAIL undeclared sibling
                        "example winter-d:/q.md <!-- winter-lint:example -->",  # exempt
                        "unknown winter-ghost:/g.md",       # FAIL unknown
                    ]
                ),
            )
            # A workspace doc (no winter-ext.toml ancestor) pointing at an extension.
            self._write(root / "ai" / "guide.md", "see winter-a:/thing.md")  # FAIL layering

            graph = {"winter-a": [], "winter-b": [], "winter-c": [], "winter-d": []}
            findings = self.lint.check_paths([root], graph, root)

            msgs = sorted((f.file, f.line, f.status) for f in findings)
            # Three failures: undeclared (modA line 4), unknown (modA line 6), layering (ai/guide line 1).
            self.assertEqual(len(findings), 3, msgs)
            files = {f.file for f in findings}
            self.assertIn(str(Path("modA") / "doc.md"), files)
            self.assertIn(str(Path("ai") / "guide.md"), files)
            layering = [f for f in findings if "layering" in f.message]
            self.assertEqual(len(layering), 1)


class CodeFenceTests(unittest.TestCase):
    def setUp(self) -> None:
        manifest_reader = ext.ManifestReader()
        scanner = ext.ReferenceScanner()
        self.lint = ext.ExtractabilityLint(
            graph_client=None,  # type: ignore[arg-type]
            manifest_reader=manifest_reader,
            scanner=scanner,
        )

    def test_references_inside_fenced_block_are_skipped(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "modA").mkdir()
            (root / "modA" / "winter-ext.toml").write_text('name = "winter-a"\n')
            (root / "modA" / "doc.md").write_text(
                "\n".join(
                    [
                        "prose winter-c:/x.md",   # FAIL — outside fence
                        "```",
                        "example winter-c:/y.md",  # skipped — inside fence
                        "```",
                    ]
                )
            )
            findings = self.lint.check_paths([root], {"winter-a": [], "winter-c": []}, root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].line, 1)


class ImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest_reader = ext.ManifestReader()
        self.scanner = ext.ReferenceScanner()

    def test_internal_import_ignored(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "modA").mkdir()
            (root / "modA" / "winter-ext.toml").write_text('name = "winter-a"\n')
            file = root / "modA" / "CLAUDE.md"
            file.write_text("@sub/thing.md\n")
            self.assertIsNone(
                self.scanner.import_target_module(
                    "@sub/thing.md", file, root / "modA", root, self.manifest_reader
                )
            )

    def test_non_path_mention_ignored(self) -> None:
        self.assertIsNone(
            self.scanner.import_target_module(
                "@param foo", Path("/x/CLAUDE.md"), Path("/x"), Path("/x"), self.manifest_reader
            )
        )

    def test_import_raw_path_accepts_both_forms(self) -> None:
        # Claude @import.
        self.assertEqual(self.scanner.import_raw_path("@ai/x.md"), "ai/x.md")
        # Rewritten cross-harness read instruction (issue #84).
        self.assertEqual(
            self.scanner.import_raw_path("IMPORTANT: always read ./ai/x.md"), "./ai/x.md"
        )
        self.assertEqual(
            self.scanner.import_raw_path("IMPORTANT: always read `../sib/y.md`"), "../sib/y.md"
        )
        # Neither form.
        self.assertIsNone(self.scanner.import_raw_path("just some prose"))

    def test_rewritten_read_ref_resolves_cross_module(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "modA").mkdir()
            (root / "modA" / "winter-ext.toml").write_text('name = "winter-a"\n')
            (root / "modB").mkdir()
            (root / "modB" / "winter-ext.toml").write_text('name = "winter-b"\n')
            file = root / "modA" / "CLAUDE.md"
            # A rewritten read instruction pointing into a sibling module.
            self.assertEqual(
                self.scanner.import_target_module(
                    "IMPORTANT: always read ../modB/thing.md",
                    file,
                    root / "modA",
                    root,
                    self.manifest_reader,
                ),
                "winter-b",
            )


if __name__ == "__main__":
    unittest.main()

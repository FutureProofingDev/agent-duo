"""Exercise the built installation and its single source of prompt content."""

from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent duo package ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source checkout"
        shutil.copytree(
            ROOT, self.root,
            ignore=shutil.ignore_patterns(".git", "dist", "__pycache__"),
        )
        # The controller's behavior has its own suite. This fixture checks that
        # packaging includes the exact executable supplied by the source tree.
        self.controller = self.root / "bin/duo-state.py"
        self.controller.write_text(
            "#!/usr/bin/env python3\nimport sys\n"
            "assert sys.argv[1:] == ['protocol']\n"
            "print('{\"protocol_version\": 2}')\n"
        )
        self.controller.chmod(0o755)
        self.skill = self.root / "skill/SKILL.md"
        self.skill.write_text(
            "---\nname: agent-duo\ndescription: Package fixture\n---\n"
            "Read `references/protocol.md` and [planner](assets/planner.md).\n"
        )

    def build(self):
        return subprocess.run(
            [str(self.root / "build.sh")], cwd=self.root,
            text=True, capture_output=True, check=False,
        )

    def assert_builds(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_rejected_preserving_previous_distribution(self, diagnostic):
        previous = self.root / "dist/previous.txt"
        previous.parent.mkdir(exist_ok=True)
        previous.write_text("previous successful build\n")
        result = self.build()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(diagnostic, result.stderr)
        self.assertEqual(previous.read_text(), "previous successful build\n")

    def test_installation_includes_executable_launcher_and_controller(self):
        self.assert_builds()
        license_contents = (self.root / "LICENSE").read_bytes()
        installed_license = self.root / "dist/agent-duo/LICENSE"
        self.assertTrue(installed_license.is_file())
        self.assertEqual(installed_license.read_bytes(), license_contents)
        with zipfile.ZipFile(self.root / "dist/agent-duo.skill") as archive:
            self.assertIn("agent-duo/LICENSE", archive.namelist())
            self.assertEqual(archive.read("agent-duo/LICENSE"), license_contents)
            for filename in ("duo.sh", "duo-state.py"):
                with self.subTest(filename=filename):
                    member = "agent-duo/assets/" + filename
                    self.assertIn(member, archive.namelist())
                    self.assertEqual(
                        archive.read(member), (self.root / "bin" / filename).read_bytes()
                    )
                    self.assertTrue(archive.getinfo(member).external_attr >> 16 & stat.S_IXUSR)
                    installed = self.root / "dist" / member
                    self.assertTrue(installed.stat().st_mode & stat.S_IXUSR)

    def test_canonical_prompt_edits_reach_the_installation(self):
        for role in ("planner", "reviewer"):
            canonical = self.root / "skill/assets" / (role + "-orca.md")
            canonical.write_text(canonical.read_text() + "\nCANONICAL " + role + " CHANGE\n")
        self.assert_builds()
        with zipfile.ZipFile(self.root / "dist/agent-duo.skill") as archive:
            for role in ("planner", "reviewer"):
                filename = role + "-orca.md"
                self.assertEqual(
                    archive.read("agent-duo/assets/" + filename),
                    (self.root / "skill/assets" / filename).read_bytes(),
                )
        self.assertFalse((self.root / "templates").exists())

    def test_slash_commands_use_launcher_and_saved_prompt_without_embedded_protocol(self):
        self.assert_builds()
        for destination in ("claude-commands", "codex-prompts"):
            startup = (self.root / "dist" / destination / "agent-duo.md").read_text()
            fallback = (self.root / "dist" / destination / "agent-duo-review.md").read_text()
            self.assertIn("duo.sh", startup)
            self.assertIn("DUO_HOME", startup)
            self.assertIn("$ARGUMENTS", startup)
            self.assertIn("reviewer.resolved.txt", fallback)
            self.assertIn("--resume", fallback)
            for command in (startup, fallback):
                self.assertNotIn("<!--", command)
                self.assertNotIn("{{", command)
                self.assertNotIn("git -C", command)
                self.assertNotIn("REVIEW OUTPUT", command)
                self.assertNotIn("REVIEW ROUND", command)
        self.assertEqual(
            (self.root / "dist/claude-commands/agent-duo.md").read_bytes(),
            (self.root / "dist/codex-prompts/agent-duo.md").read_bytes(),
        )

    def test_build_rejects_missing_local_markdown_reference(self):
        self.skill.write_text(self.skill.read_text() + "\n[Missing](assets/missing.md)\n")
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("assets/missing.md", result.stderr)

    def test_build_rejects_missing_literal_code_reference(self):
        self.skill.write_text(self.skill.read_text() + "\nRead `references/missing.md`.\n")
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("references/missing.md", result.stderr)

    def test_build_does_not_interpret_prose_or_shell_expansion_as_file_references(self):
        self.skill.write_text(
            self.skill.read_text()
            + "\nExample paths such as assets/not-a-file.md are ordinary prose.\n"
            + "Use `assets/${ROLE}.md` or `assets/*.md` for shell examples.\n"
            + "See [external](https://example.org/assets/missing.md).\n"
        )
        self.assert_builds()

    def test_missing_launcher_fails_before_replacing_previous_distribution(self):
        (self.root / "bin/duo.sh").unlink()
        self.assert_rejected_preserving_previous_distribution("bin/duo.sh")

    def test_missing_license_fails_before_replacing_previous_distribution(self):
        (self.root / "LICENSE").unlink()
        self.assert_rejected_preserving_previous_distribution("LICENSE")

    def test_legacy_or_mismatched_prompts_preserve_previous_distribution(self):
        for filename in ("planner.md", "reviewer.md", "planner-orca.md", "reviewer-orca.md"):
            template = self.root / "skill/assets" / filename
            original = template.read_text()
            for marker in ("", "<!-- agent-duo: protocol=1 role=planner transport=file -->"):
                with self.subTest(filename=filename, marker=marker):
                    try:
                        template.write_text("/loop Legacy prompt\n" + marker + "\n{{CONTROLLER}}\n")
                        self.assert_rejected_preserving_previous_distribution(filename)
                    finally:
                        template.write_text(original)

    def test_wrong_role_transport_or_duplicate_marker_preserves_previous_distribution(self):
        template = self.root / "skill/assets/planner.md"
        for marker in (
            "<!-- agent-duo: protocol=2 role=reviewer transport=file -->",
            "<!-- agent-duo: protocol=2 role=planner transport=orchestration -->",
            "<!-- agent-duo: protocol=2 role=planner transport=file -->\n"
            "<!-- agent-duo: protocol=2 role=planner transport=file -->",
        ):
            with self.subTest(marker=marker):
                template.write_text("/loop Planner\n" + marker + "\n{{CONTROLLER}}\n")
                self.assert_rejected_preserving_previous_distribution("planner.md")

    def test_prompt_without_controller_preserves_previous_distribution(self):
        for filename in ("planner.md", "reviewer.md", "planner-orca.md", "reviewer-orca.md"):
            template = self.root / "skill/assets" / filename
            original = template.read_text()
            with self.subTest(filename=filename):
                try:
                    template.write_text(original.replace("{{CONTROLLER}}", "legacy-controller"))
                    self.assert_rejected_preserving_previous_distribution(filename)
                finally:
                    template.write_text(original)

    def test_incompatible_controller_preserves_previous_distribution(self):
        for response in ('{"protocol_version": 1}', "legacy controller", '{}'):
            with self.subTest(response=response):
                self.controller.write_text("#!/usr/bin/env python3\nprint(" + repr(response) + ")\n")
                self.assert_rejected_preserving_previous_distribution("bin/duo-state.py")


if __name__ == "__main__":
    unittest.main()

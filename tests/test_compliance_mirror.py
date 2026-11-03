"""Safety checks for publishing the private compliance evaluation snapshot."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sync-compliance-mirror.sh"


class ComplianceMirrorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        (self.source / "sample.txt").write_text("evaluation source\n")
        subprocess.run(["git", "-C", str(self.source), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.source), "-c", "user.name=Test", "-c",
             "user.email=test@example.invalid", "commit", "-qm", "test"],
            check=True,
        )
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            "case \"$2\" in\n"
            "  */actions/permissions) printf '%s\\n' \"$TEST_ACTIONS\" ;;\n"
            "  *) printf '%s\\n' \"$TEST_PRIVATE\" ;;\n"
            "esac\n"
        )
        gh.chmod(0o755)
        self.env = os.environ.copy()
        self.env["PATH"] = str(bin_dir) + os.pathsep + self.env["PATH"]

    def run_sync(self, private, actions):
        env = dict(self.env, TEST_PRIVATE=private, TEST_ACTIONS=actions)
        return subprocess.run(
            [str(SCRIPT), str(self.source)], env=env, text=True, capture_output=True
        )

    def test_rejects_a_nonprivate_repository_before_cloning(self):
        result = self.run_sync(private="false", actions="false")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be private", result.stderr)
        self.assertNotIn("Cloning", result.stderr)

    def test_rejects_enabled_actions_before_cloning(self):
        result = self.run_sync(private="true", actions="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Disable GitHub Actions", result.stderr)
        self.assertNotIn("Cloning", result.stderr)


if __name__ == "__main__":
    unittest.main()

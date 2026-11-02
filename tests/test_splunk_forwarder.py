"""Exercise the forwarder job's inventory and credential guard without changing hosts."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "jt_playbooks/splunk/deploy_forwarder.yml"
FIXTURE_SECRET = "FixtureOnly_Forwarder_934!"


class SplunkForwarderPreflightTests(unittest.TestCase):
    def run_preflight(self, inventory_hosts, **overrides):
        with tempfile.TemporaryDirectory(prefix="splunk-preflight-") as tmp:
            inventory = Path(tmp) / "inventory.ini"
            inventory.write_text("\n".join(inventory_hosts) + "\n")
            variables = {
                "splunk_receiver_host": "splunk.example.test",
                "splunk_receiver_port": 9997,
                "splunk_forwarder_version": "9.4.7",
                "splunk_forwarder_release_id": "2a9293b80994",
                "splunk_demo_index": "main",
            }
            variables.update(overrides)
            varfile = Path(tmp) / "vars.yml"
            varfile.write_text(yaml.safe_dump(variables))
            env = dict(os.environ, SPLUNK_FORWARDER_USERNAME="admin",
                       SPLUNK_FORWARDER_PASSWORD=FIXTURE_SECRET,
                       ANSIBLE_NOCOLOR="1")
            result = subprocess.run(
                ["ansible-playbook", "-i", str(inventory), str(PLAYBOOK),
                 "--tags", "splunk_preflight", "-e", "@" + str(varfile)],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
            )
            output = result.stdout + result.stderr
            self.assertNotIn(FIXTURE_SECRET, output)
            return result.returncode, output

    def test_empty_target_set_fails_before_any_host_changes(self):
        code, output = self.run_preflight(["unrelated.example.test"])
        self.assertNotEqual(code, 0, output)
        self.assertIn("failed=1", output)

    def test_cloud_rhel_target_and_valid_receiver_pass(self):
        code, output = self.run_preflight(["aws-rhel9", "aws-rhel10"])
        self.assertEqual(code, 0, output)

    def test_invalid_receiver_port_fails(self):
        code, output = self.run_preflight(["aws-rhel9"], splunk_receiver_port=65536)
        self.assertNotEqual(code, 0, output)


if __name__ == "__main__":
    unittest.main()

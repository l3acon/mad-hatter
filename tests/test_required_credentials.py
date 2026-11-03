"""Credential preflights; run in the ROSA EE (or with Ansible, PyYAML and passlib)."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml


class AnsibleSafeLoader(yaml.SafeLoader):
    """Recognize Ansible's unsafe string tag while retaining safe YAML loading."""


AnsibleSafeLoader.add_constructor(
    "!unsafe", lambda loader, node: loader.construct_scalar(node)
)

ROOT = Path(__file__).resolve().parents[1]
# These values are local test fixtures, never deployment defaults.
PASSWORD = "FixtureOnly_836!"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nfixture\n-----END OPENSSH PRIVATE KEY-----\n"


class CredentialPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mad-hatter-creds-test-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.manifest = self.work / "manifest.zip"
        self.manifest.write_bytes(b"fixture manifest for file-readability checks")

    def run_play(self, tasks, variables=None, environment=None):
        play = [{"name": "Credential validation", "hosts": "localhost", "connection": "local",
                 "gather_facts": False, "vars": variables or {}, "tasks": tasks}]
        path = self.work / "play.yml"
        path.write_text(yaml.safe_dump(play, sort_keys=False))
        env = dict(os.environ)
        for key in ["CONTROLLER_PASSWORD", "AAP_MANIFEST_PATH", "AAP_LIGHTSPEED_TOKEN",
                    "AAP_MACHINE_CRED_PASSWORD", "K8S_AUTH_PASSWORD", "CLAB_DEVICE_PASSWORD",
                    "SNOW_SSP_USER_PASSWORD", "OCPV_SSP_USER_PASSWORD"]:
            env.pop(key, None)
        env.update({"ANSIBLE_ROLES_PATH": str(ROOT / "roles"),
                    "ANSIBLE_NOCOLOR": "1", "ANSIBLE_LOCAL_TEMP": str(self.work / "ansible-tmp"),
                    "PYTHONDONTWRITEBYTECODE": "1"})
        env.update(environment or {})
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", str(path)],
                                env=env, cwd=ROOT, text=True, capture_output=True, timeout=60)
        return result.returncode, result.stdout + result.stderr

    def aap(self, variables=None, environment=None):
        return self.run_play([{"ansible.builtin.include_role": {
            "name": "aap_operator", "tasks_from": "preflight"}}], variables, environment)

    def test_missing_and_blank_admin_passwords_fail(self):
        for value in [None, "", "   "]:
            with self.subTest(value=value):
                variables = {} if value is None else {"aap_operator_controller_admin_password": value}
                code, output = self.aap(variables)
                self.assertNotEqual(code, 0, output)
                self.assertIn("Set aap_admin_password", output)

    def test_manifest_path_is_required_when_injection_is_enabled(self):
        code, output = self.aap({"aap_operator_controller_admin_password": PASSWORD,
                                 "aap_operator_inject_manifest": True})
        self.assertNotEqual(code, 0, output)
        self.assertIn("Set aap_manifest_path", output)

    def test_nonexistent_manifest_fails(self):
        code, output = self.aap({"aap_operator_controller_admin_password": PASSWORD,
                                 "aap_operator_inject_manifest": True,
                                 "aap_operator_inject_manifest_path": str(self.work / "missing.zip")})
        self.assertNotEqual(code, 0, output)
        self.assertIn("manifest is missing or unreadable", output)

    def test_environment_password_and_manifest_are_accepted(self):
        code, output = self.aap({"aap_operator_inject_manifest": True}, {
            "CONTROLLER_PASSWORD": PASSWORD, "AAP_MANIFEST_PATH": str(self.manifest)})
        self.assertEqual(code, 0, output)
        self.assertNotIn(PASSWORD, output)

    def test_standalone_deployment_uses_its_local_credential_file(self):
        (self.work / "user.creds.yml").write_text(yaml.safe_dump({
            "aap_admin_password": PASSWORD, "aap_manifest_path": str(self.manifest)}))
        deployment = yaml.safe_load((ROOT / "aap-deploy.yml").read_text())[0]
        code, output = self.run_play(deployment["pre_tasks"] + [
            {"ansible.builtin.include_role": {"name": "aap_operator", "tasks_from": "preflight"}},
            {"ansible.builtin.assert": {"that": [
                "aap_operator_controller_admin_password == expected_password",
                "aap_operator_inject_manifest_path == expected_manifest"]}},
        ], {**deployment["vars"], "expected_password": PASSWORD,
            "expected_manifest": str(self.manifest)})
        self.assertEqual(code, 0, output)
        self.assertNotIn(PASSWORD, output)

    def test_disabled_optional_features_do_not_require_secrets(self):
        code, output = self.aap({"aap_operator_controller_admin_password": PASSWORD,
                                 "aap_operator_inject_manifest": False,
                                 "aap_operator_disable_lightspeed": True})
        self.assertEqual(code, 0, output)

    def test_enabled_lightspeed_requires_a_token(self):
        code, output = self.aap({"aap_operator_controller_admin_password": PASSWORD,
                                 "aap_operator_disable_lightspeed": False})
        self.assertNotEqual(code, 0, output)
        self.assertIn("Set aap_operator_chatbot_token", output)

    def user_creds(self, file_values, environment=None):
        credentials = self.work / "user.creds.yml"
        credentials.write_text(yaml.safe_dump(file_values))
        return self.run_play([
            {"ansible.builtin.include_role": {"name": "user_creds"}},
            {"ansible.builtin.assert": {"that": [
                "aap_admin_password == expected_password",
                "aap_manifest_path == expected_manifest",
                "aap_machine_cred_priv_key == expected_key"]}},
        ], {"user_creds_file_path": str(credentials),
            "expected_password": PASSWORD, "expected_manifest": str(self.manifest),
            "expected_key": PRIVATE_KEY,
            "aap_operator_disable_lightspeed": True,
            "user_creds_ansible_ssh_private_key_file": "/does-not-exist",
            "user_creds_ansible_ssh_pub_key_file": "/does-not-exist.pub"}, environment)

    def test_file_credentials_survive_conflicting_environment_values(self):
        code, output = self.user_creds({
            "aap_admin_password": PASSWORD, "aap_manifest_path": str(self.manifest),
            "openshift_admin_password": PASSWORD, "aap_machine_cred_password": PASSWORD,
            "aap_machine_cred_priv_key": PRIVATE_KEY, "aap_machine_cred_pub_key": "fixture-pubkey",
        }, {"CONTROLLER_PASSWORD": "ConflictingFixture_123!", "AAP_MANIFEST_PATH": "/wrong-path"})
        self.assertEqual(code, 0, output)
        self.assertNotIn(PASSWORD, output)
        self.assertNotIn(PRIVATE_KEY, output)

    def test_empty_file_values_can_be_supplied_by_environment(self):
        code, output = self.user_creds({
            "aap_admin_password": "", "aap_manifest_path": "", "openshift_admin_password": "",
            "aap_machine_cred_password": "", "aap_machine_cred_priv_key": PRIVATE_KEY,
            "aap_machine_cred_pub_key": "fixture-pubkey",
        }, {"CONTROLLER_PASSWORD": PASSWORD, "AAP_MANIFEST_PATH": str(self.manifest),
            "K8S_AUTH_PASSWORD": PASSWORD, "AAP_MACHINE_CRED_PASSWORD": PASSWORD})
        self.assertEqual(code, 0, output)

    def test_missing_user_credentials_fail_before_ssh_file_lookups(self):
        code, output = self.user_creds({})
        self.assertNotEqual(code, 0, output)
        self.assertIn("Set aap_admin_password, openshift_admin_password", output)
        self.assertNotIn("could not locate file", output)

    def test_missing_or_invalid_device_password_fails(self):
        for password in ["", "   ", "bad\nconfig", 'bad"config']:
            with self.subTest(password=password):
                code, output = self.run_play([{"ansible.builtin.include_role": {
                    "name": "clab", "tasks_from": "validate_password"}}], {"clab_device_password": password})
                self.assertNotEqual(code, 0, output)
                self.assertIn("Set clab_device_password", output)

    def test_startup_configs_use_the_configured_password(self):
        for topology in ["product_demos", "rhdp"]:
            with self.subTest(topology=topology):
                source = ROOT / "roles/clab/files/clab" / topology / "configs"
                target = self.work / topology
                for config in source.glob("*/startup-config.cfg"):
                    (target / config.parent.name).mkdir(parents=True)
                code, output = self.run_play([
                    {"ansible.builtin.include_role": {"name": "clab", "tasks_from": "validate_password"}},
                    {"ansible.builtin.include_role": {"name": "clab", "tasks_from": "render_configs"}},
                ], {"clab_device_password": PASSWORD, "clab_config_source_dir": str(source),
                    "clab_config_dest_dir": str(target)})
                self.assertEqual(code, 0, output)
                self.assertNotIn(PASSWORD, output)
                for config in target.glob("*/startup-config.cfg"):
                    text = config.read_text()
                    self.assertNotIn("{{", text)
                    self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                    if config.parent.name in ["rtr2", "rtr3", "rtr4"]:
                        hashes = re.findall(
                            r"\$6\$(?:rounds=\d+\$)?[./A-Za-z0-9]+\$[./A-Za-z0-9]+",
                            text,
                        )
                        self.assertTrue(hashes, text)
                        # The older ROSA EE has crypt; newer Python requires passlib.
                        try:
                            from passlib.hash import sha512_crypt
                            self.assertTrue(all(sha512_crypt.verify(PASSWORD, h) for h in hashes))
                        except ImportError:
                            import crypt
                            self.assertTrue(all(crypt.crypt(PASSWORD, h) == h for h in hashes))
                    else:
                        self.assertIn("password 0 " + PASSWORD, text)

    def test_deployable_yaml_contains_no_literal_passwords(self):
        paths = list(ROOT.glob("*-deploy.yml"))
        for area in ["roles", "jt_playbooks", "examples"]:
            paths.extend((ROOT / area).rglob("*.yml"))

        def inspect(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    if str(key).lower().endswith(("password", "passwd")) and isinstance(value, str):
                        self.assertTrue(not value.strip() or "{{" in value,
                                        f"Literal password at {path}: {key}")
                    inspect(value, path)
            elif isinstance(node, list):
                for child in node:
                    inspect(child, path)

        for path in paths:
            if "files/helm/templates" in str(path):
                continue
            inspect(yaml.load(path.read_text(), Loader=AnsibleSafeLoader), path.relative_to(ROOT))


if __name__ == "__main__":
    unittest.main()

"""Run with: PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -p 'test_server_build.py' -v."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snow_update_set", ROOT / "roles/snow/plugins/modules/snow_update_set.py")
snow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snow)
CR, RITM, GROUP = "a" * 32, "b" * 32, "c" * 32
PARAMETERS = {"server_build_os": "rhel", "ocpv_vm_name": "test-server", "ocpv_instancetype_name": "u1.xlarge"}
ITEM = {"name": "server-build", "approval_required": True,
        "aap_workflows": {"rhel": "ServiceNow | Server Build - RHEL", "windows": "ServiceNow | Server Build - Windows"},
        "aap_workflow_ids": {"rhel": "10", "windows": "20"}, "variables": []}


class GeneratedIntegrationTests(unittest.TestCase):
    def test_generated_rules(self):
        scripts = {
            "catalog": snow.server_build_catalog_script([ITEM], {"assignment_group": GROUP}),
            "claim": snow.server_build_claim_script(),
            "approval": snow.server_build_approval_script([ITEM], "https://aap.example.com"),
            "network": snow._get_change_request_br_body(),
        }
        result = subprocess.run(["node", str(ROOT / "tests/server_build_rules.test.js")],
                                input=json.dumps(scripts), text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("scenarios passed", result.stdout)

    def test_xml_and_direct_deployment_share_rule_definitions(self):
        params = {"server_build": {"enabled": True, "assignment_group": GROUP}, "catalog_items": [ITEM, {"name": "Legacy build", "aap_resource_type": "job_template",
                      "aap_resource_name": "Legacy build", "aap_resource_id": "1"}],
                  "aap_host": "https://aap.example.com", "aap_username": "test", "aap_password": "test",
                  "rest_message": {"name": "Ansible Automation Platform"}, "update_set_name": "test"}
        xml = snow.generate_update_set_xml(SimpleNamespace(params=params))
        payloads = [ElementTree.fromstring(node.text) for node in ElementTree.fromstring(xml).findall("sys_update_xml/payload")]
        expected = {fields["name"]: fields["script"] for table, fields in snow.server_build_records(params) if table == "sys_script"}
        actual = {node.findtext("sys_script/name"): node.findtext("sys_script/script") for node in payloads if node.find("sys_script") is not None}
        for name, script in expected.items():
            self.assertEqual(actual[name], script)
        dictionary = [node.findtext("sys_dictionary/element") for node in payloads if node.find("sys_dictionary") is not None]
        self.assertEqual(len(dictionary), 4)
        self.assertIn("u_aap_build_parameters", dictionary)
        catalog_rule = actual["AAP - Launch on Catalog Order"]
        self.assertNotIn("'server-build':", catalog_rule)
        include = next(node.findtext("sys_script_include/script") for node in payloads if node.find("sys_script_include") is not None)
        self.assertEqual(include, snow._get_script_include_body(""))

    def test_server_build_only_preserves_existing_catalog_rule(self):
        params = {"server_build": {"enabled": True, "assignment_group": GROUP}, "catalog_items": [ITEM],
                  "aap_host": "https://aap.example.com", "aap_username": "test", "aap_password": "test",
                  "rest_message": {"name": "Ansible Automation Platform"}, "update_set_name": "test"}
        xml = snow.generate_update_set_xml(SimpleNamespace(params=params))
        self.assertNotIn("AAP - Launch on Catalog Order", xml)

    def test_server_build_only_uses_its_own_rest_auth_and_class(self):
        params = {"server_build": {"enabled": True, "assignment_group": GROUP}, "catalog_items": [ITEM],
                  "aap_host": "https://aap.example.com", "aap_username": "test", "aap_password": "test",
                  "rest_message": {"name": "Ansible Automation Platform", "http_methods": [
                      {"name": "Launch Workflow", "http_method": "POST", "endpoint": "/launch/"}]},
                  "update_set_name": "test"}
        self.assertEqual(snow.integration_rest_message(params)["name"], "AAP Server Build")
        self.assertEqual({p["name"] for p in snow.aap_sys_properties(params)},
                         {"aap.server_build.api.username", "aap.server_build.api.password"})
        script = snow._get_script_include_body("", params)
        self.assertIn("var AAPServerBuildIntegration", script)
        self.assertIn("this.REST_MESSAGE = 'AAP Server Build'", script)
        rule = next(fields["script"] for table, fields in snow.server_build_records(params)
                    if fields.get("name") == "AAP - Launch Approved Server Build")
        self.assertIn("new AAPServerBuildIntegration()", rule)
        self.assertNotIn("new AAPIntegration()", rule)
        xml = snow.generate_update_set_xml(SimpleNamespace(params=params))
        self.assertNotIn("AAP - Configure on CR Implement", xml)
        self.assertIn("AAP Server Build", xml)
        regular = snow.build_rest_message_records(params["rest_message"], "https://aap", "test", "test", "now")
        isolated = snow.build_rest_message_records(snow.integration_rest_message(params), "https://aap", "test", "test", "now")
        self.assertNotEqual(regular[1], isolated[1])

    def test_isolated_deployment_only_adds_a_guard_to_the_legacy_network_rule(self):
        original = {"sys_id": "d" * 32, "name": "AAP - Configure on CR Implement",
                    "condition": "current.state.changesTo(-1)", "script": "existing network script",
                    "advanced": "true", "collection": "change_request", "when": "after"}
        params = {"instance": "https://snow.example.com", "username": "test", "password": "test",
                  "server_build": {"enabled": True, "assignment_group": GROUP}, "catalog_items": [ITEM],
                  "aap_host": "https://aap.example.com"}
        module = SimpleNamespace(params=params, fail_json=lambda **kwargs: self.fail(kwargs["msg"]))
        with patch("requests.get", return_value=SimpleNamespace(status_code=200, json=lambda: {"result": [dict(original)]})):
            rows = snow.resolve_legacy_network_guard(module)
        self.assertEqual(rows[0]["script"], original["script"])
        self.assertEqual(rows[0]["sys_id"], original["sys_id"])
        self.assertIn(original["condition"], rows[0]["condition"])
        self.assertIn("!= 'server-build'", rows[0]["condition"])
        with patch("requests.get", return_value=SimpleNamespace(status_code=200, json=lambda: {"result": rows})):
            self.assertEqual(snow.resolve_legacy_network_guard(module), rows)
        params["_server_build_legacy_network_rules"] = rows
        records = snow.server_build_records(params)
        managed = next(fields for table, fields in records if fields.get("name") == original["name"])
        self.assertEqual(managed["script"], original["script"])
        xml = ElementTree.fromstring(snow.build_payload_xml("sys_script", managed, managed["sys_id"]))
        self.assertEqual(len(xml.findall("sys_script/sys_id")), 1)
        for table, fields in records:
            if table == "sys_script":
                self.assertEqual(fields["advanced"], "true")

    def test_redeployment_does_not_return_ansibles_reserved_skipped_flag(self):
        params = {"server_build": {"enabled": True, "assignment_group": GROUP}, "catalog_items": [ITEM]}
        result = {}
        module = SimpleNamespace(params=params, check_mode=False, exit_json=lambda **value: result.update(value),
                                 fail_json=lambda **value: self.fail(value.get("msg", "Unexpected module failure")))
        params["update_set_name"] = "test"
        deployment = {"created": ["rule refreshed"], "errors": [], "skipped_resources": ["existing catalog item"]}
        with patch.object(snow, "AnsibleModule", return_value=module), \
             patch.object(snow, "resolve_aap_resource_ids", return_value=[ITEM]), \
             patch.object(snow, "resolve_legacy_network_guard", return_value=[]), \
             patch.object(snow, "generate_update_set_xml", return_value="<xml/>"), \
             patch.object(snow, "upload_update_set", return_value=deployment):
            snow.main()
        self.assertNotIn("skipped", result)
        self.assertEqual(result["skipped_resources"], ["existing catalog item"])
        self.assertTrue(result["changed"])

    def test_select_choices_are_emitted(self):
        items = yaml.safe_load((ROOT / "roles/snow/files/catalog_items.yml").read_text())["snow_catalog_items"]
        item = next(item for item in items if item["name"] == "server-build")
        xml = "<root>" + "".join(snow.build_catalog_item_records([item], "2026-10-20 00:00:00")) + "</root>"
        payloads = [ElementTree.fromstring(node.text) for node in ElementTree.fromstring(xml).findall("sys_update_xml/payload")]
        choices = [node.findtext("question_choice/value") for node in payloads if node.find("question_choice") is not None]
        self.assertEqual(set(choices), {"rhel", "windows", "u1.medium", "u1.large", "u1.xlarge", "u1.2xlarge"})

    def test_feature_defaults_to_disabled(self):
        self.assertEqual(snow.enabled_catalog_items({"catalog_items": [ITEM]}), [])
        definitions = snow.server_build_records({"catalog_items": [ITEM]})
        self.assertEqual(len(definitions), 1)  # Legacy network rule remains scoped.

    def test_managed_records_are_updated_on_redeployment(self):
        class Session:
            def __init__(self): self.records = []; self.posts = 0; self.patches = 0
            def get(self, *args, **kwargs):
                return SimpleNamespace(status_code=200, json=lambda: {"result": self.records})
            def post(self, url, json):
                self.posts += 1; self.records = [{"sys_id": CR, **json}]
                return SimpleNamespace(status_code=201)
            def patch(self, url, json):
                self.patches += 1; self.records = [{"sys_id": CR, **json}]
                return SimpleNamespace(status_code=200)
        session = Session()
        results = {"created": [], "errors": []}
        for version in ("old", "new"):
            snow.upsert_record(session, "https://snow.example.com", "sys_script", "name=test",
                               {"name": "test", "script": version}, results)
        self.assertEqual((session.posts, session.patches), (1, 1))
        self.assertEqual(session.records[0]["script"], "new")
        self.assertEqual(results["errors"], [])

    def test_workflow_graphs_and_credentials(self):
        definitions = yaml.safe_load((ROOT / "roles/openshift_virtualization_aap/vars/server_build.yml").read_text())
        jobs = {job["name"]: job for job in definitions["openshift_virt_aap_server_build_templates"]}
        for workflow in definitions["openshift_virt_aap_server_build_workflows"]:
            self.assertFalse(workflow["ask_variables_on_launch"])
            self.assertEqual({field["variable"] for field in workflow["survey_spec"]["spec"]},
                             {"snow_change_sys_id", "snow_request_sys_id"})
            nodes = {node["identifier"]: node for node in workflow["simplified_workflow_nodes"]}
            for node in nodes.values():
                self.assertIn(node["unified_job_template"], jobs)
                for edge in node.get("success_nodes", []) + node.get("failure_nodes", []):
                    self.assertIn(edge, nodes)
            self.assertEqual(nodes["Baseline"]["success_nodes"], ["Complete"])
            self.assertIn("failure_nodes", nodes["Complete"])

    def test_casc_definitions_render_with_role_defaults(self):
        with tempfile.TemporaryDirectory(prefix="server-build-casc-") as tmp:
            key = Path(tmp) / "id.pub"
            key.write_text("ssh-ed25519 AAAATEST fake-key\n")
            playbook = Path(tmp) / "render.yml"
            playbook.write_text(yaml.safe_dump([{
                "name": "Render server-build CasC", "hosts": "localhost", "gather_facts": False,
                "vars": {"aap_hostname": "https://aap.example.com",
                         "openshift_virt_aap_vm_ssh_public_key_file": str(key)},
                "tasks": [
                    {"ansible.builtin.include_vars": str(ROOT / "roles/openshift_virtualization_aap/defaults/main.yml")},
                    {"ansible.builtin.include_vars": str(ROOT / "roles/openshift_virtualization_aap/vars/server_build.yml")},
                    {"name": "Resolve every job and workflow template", "ansible.builtin.set_fact": {
                        "rendered_jobs": "{{ openshift_virt_aap_server_build_templates }}",
                        "rendered_workflows": "{{ openshift_virt_aap_server_build_workflows }}"}},
                    {"ansible.builtin.assert": {"that": ["rendered_jobs | length == 8", "rendered_workflows | length == 2",
                        "rendered_jobs[5].execution_environment == openshift_virt_aap_ee_windows_name",
                        "rendered_jobs[2].extra_vars.server_build_ssh_user == 'cloud-user'"]}},
                ],
            }], sort_keys=False))
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook),
                                     "-e", "openshift_virt_aap_vm_ssh_public_key_file=" + str(key)],
                                    cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class LifecycleTests(unittest.TestCase):
    """Execute the actual Ansible lifecycle playbooks against a local Table API double."""
    def setUp(self):
        self.change = {"sys_id": CR, "parent": RITM, "correlation_id": RITM, "number": "CHG001",
                       "u_aap_integration": "server-build", "approval": "approved", "state": "-2",
                       "u_aap_launch_status": "launched", "u_aap_workflow_job_id": "123",
                       "u_aap_build_parameters": json.dumps(PARAMETERS)}
        self.ritm = {"sys_id": RITM, "state": "1"}
        self.patches = []
        self.deny_state = None
        self.pending_reads = 0
        self.change_tasks = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def respond(self, record):
                body = json.dumps({"result": record}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                if "/change_task?" in self.path:
                    self.respond([task for task in owner.change_tasks if task["state"] != "3"])
                    return
                record = dict(owner.change)
                if owner.pending_reads:
                    record["u_aap_launch_status"] = "pending"
                    owner.pending_reads -= 1
                self.respond(record)
            def do_PATCH(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                table = ("change_request" if "/change_request/" in self.path else
                         "change_task" if "/change_task/" in self.path else "sc_req_item")
                owner.patches.append((table, payload))
                record = (owner.change if table == "change_request" else
                          next(task for task in owner.change_tasks if task["sys_id"] == self.path.rsplit("/", 1)[-1])
                          if table == "change_task" else owner.ritm)
                if not (table == "change_request" and payload.get("state") == owner.deny_state):
                    record.update(payload)
                self.respond(record)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def run_playbook(self, filename, **overrides):
        variables = {"snow_instance": f"http://127.0.0.1:{self.server.server_port}",
                     "snow_username": "fake-user", "snow_password": "fake-password", "snow_change_sys_id": CR,
                     "snow_request_sys_id": RITM, "awx_workflow_job_id": 123, "server_build_expected_os": "rhel",
                     "server_build_namespace": "virt-rhel", "server_build_banner_text": "Government system.",
                     "server_build_banner_title": "Government System", "server_build_aap_url": "https://aap.example.com",
                     "server_build_parameters": PARAMETERS, **overrides}
        with tempfile.TemporaryDirectory(prefix="server-build-test-") as tmp:
            path = Path(tmp) / "vars.json"
            path.write_text(json.dumps(variables))
            result = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local",
                                     str(ROOT / f"jt_playbooks/snow/server_build_{filename}.yml"), "-e", "@" + str(path)],
                                    cwd=ROOT, text=True, capture_output=True, check=False,
                                    env={**os.environ, "ANSIBLE_NOCOLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        return result

    def test_authorized_build_and_verified_completion(self):
        result = self.run_playbook("prepare")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.change["state"], "-1")
        self.assertEqual(self.ritm["state"], "2")
        result = self.run_playbook("complete", server_build_verified=True, server_build_guest_ip="10.0.0.5")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.change["state"], "3")
        self.assertEqual(self.change["close_code"], "successful")
        self.assertEqual(self.ritm["state"], "3")
        self.assertEqual([(table, fields.get("state")) for table, fields in self.patches],
                         [("change_request", "-1"), ("sc_req_item", "2"), ("change_request", "0"),
                          ("change_request", "3"), ("sc_req_item", "3")])

    def test_preflight_waits_for_approval_transaction_to_commit(self):
        self.pending_reads = 1
        result = self.run_playbook("prepare")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.change["state"], "-1")
        self.assertEqual(self.pending_reads, 0)

    def test_verification_completes_only_implementation_and_testing_tasks(self):
        self.change["state"] = "-1"
        self.change_tasks = [{"sys_id": "d" * 32, "number": "CTASK1", "state": "1", "change_task_type": "implementation"},
                             {"sys_id": "e" * 32, "number": "CTASK2", "state": "1", "change_task_type": "testing"}]
        result = self.run_playbook("complete", server_build_verified=True, server_build_guest_ip="10.0.0.5")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(all(task["state"] == "3" for task in self.change_tasks))
        self.assertEqual([table for table, fields in self.patches[:2]], ["change_task", "change_task"])
        self.assertEqual(self.change["state"], "3")

    def test_unrecognized_child_task_prevents_automatic_closure(self):
        self.change["state"] = "-1"
        self.change_tasks = [{"sys_id": "d" * 32, "number": "CTASK1", "state": "1", "change_task_type": "manual_review"}]
        result = self.run_playbook("complete", server_build_verified=True, server_build_guest_ip="10.0.0.5")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.patches, [])

    def test_unapproved_change_cannot_start(self):
        self.change["approval"] = "requested"
        result = self.run_playbook("prepare")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.patches, [])

    def test_other_workflow_cannot_start(self):
        result = self.run_playbook("prepare", awx_workflow_job_id=456)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.patches, [])

    def test_unverified_build_cannot_close(self):
        self.change["state"] = "-1"
        result = self.run_playbook("complete")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.patches, [])

    def test_rejected_state_transition_stops_preflight(self):
        self.deny_state = "-1"
        result = self.run_playbook("prepare")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.ritm["state"], "1")

    def test_closure_failure_does_not_complete_request(self):
        self.change["state"] = "-1"
        self.deny_state = "3"
        result = self.run_playbook("complete", server_build_verified=True, server_build_guest_ip="10.0.0.5")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.change["state"], "0")
        self.assertNotEqual(self.ritm["state"], "3")
        result = self.run_playbook("failed", server_build_failed_stage="Complete")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.change["state"], "0")
        self.assertEqual(self.ritm["state"], "4")
        self.assertIn("Complete", self.change["work_notes"])


if __name__ == "__main__":
    unittest.main()

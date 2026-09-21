#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Ansible module to generate and deploy a ServiceNow Update Set XML.

Reads YAML catalog item definitions, generates a valid Update Set XML containing
REST Messages, Catalog Items, Variables, Script Includes, and Business Rules,
then uploads it to a ServiceNow instance via the upload.do multipart endpoint.
"""

import json
import uuid
import time
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = r"""
---
module: snow_update_set
short_description: Deploy ServiceNow catalog configuration via Update Set XML
description:
  - Generates an Update Set XML from YAML definitions and uploads it to ServiceNow.
  - Creates REST Messages, Catalog Items, Variables, Script Includes, and Business Rules.
  - Uses the upload.do multipart endpoint (same as SNOW UI "Import Update Set from XML").
options:
  instance:
    description: ServiceNow instance URL
    required: true
    type: str
  username:
    description: ServiceNow admin username
    required: true
    type: str
  password:
    description: ServiceNow admin password
    required: true
    type: str
    no_log: true
  aap_host:
    description: AAP Controller URL
    required: true
    type: str
  aap_username:
    description: AAP username for REST Message auth
    required: true
    type: str
  aap_password:
    description: AAP password for REST Message auth
    required: true
    type: str
    no_log: true
  catalog_items:
    description: List of catalog item definitions
    required: true
    type: list
  rest_message:
    description: REST Message definition
    required: true
    type: dict
  update_set_name:
    description: Name for the generated update set
    default: "AAP ServiceNow Integration"
    type: str
  commit:
    description: Whether to preview and commit after upload
    default: true
    type: bool
author:
  - Matt Fernandez (@l3acon)
"""

NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def deterministic_sys_id(name):
    """Generate a deterministic 32-char hex sys_id from a name."""
    return uuid.uuid5(NAMESPACE, name).hex


def now_str():
    """Current UTC timestamp in SNOW format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def xml_cdata(content):
    """Wrap content in CDATA."""
    return f"<![CDATA[{content}]]>"


def build_payload_xml(table, fields, sys_id):
    """Build the inner payload XML for a sys_update_xml record."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<record_update table="{table}">',
        f'<{table} action="INSERT_OR_UPDATE">',
    ]
    for key, value in fields.items():
        if value is None:
            lines.append(f"<{key}/>")
        else:
            lines.append(f"<{key}>{xml_escape(str(value))}</{key}>")
    lines.append(f"<sys_id>{sys_id}</sys_id>")
    lines.append(f"</{table}>")
    lines.append("</record_update>")
    return "\n".join(lines)


def build_update_xml_record(name, table, target_name, payload_xml, update_set_id, ts):
    """Build a single sys_update_xml element."""
    escaped_payload = xml_escape(payload_xml)
    return f"""<sys_update_xml action="INSERT_OR_UPDATE">
<action>INSERT_OR_UPDATE</action>
<application display_value="Global">global</application>
<category>customer</category>
<comments/>
<name>{xml_escape(name)}</name>
<payload>{escaped_payload}</payload>
<replace_on_upgrade>false</replace_on_upgrade>
<sys_created_by>admin</sys_created_by>
<sys_created_on>{ts}</sys_created_on>
<sys_id>{deterministic_sys_id(name + '_xml')}</sys_id>
<sys_mod_count>0</sys_mod_count>
<sys_updated_by>admin</sys_updated_by>
<sys_updated_on>{ts}</sys_updated_on>
<table>{table}</table>
<target_name>{xml_escape(target_name)}</target_name>
<type>{table}</type>
<update_set display_value=""/>
<view/>
</sys_update_xml>"""


def build_rest_message_records(rest_message, aap_host, aap_username, aap_password, ts):
    """Generate update XML records for the REST Message and its HTTP methods."""
    records = []
    msg_sys_id = deterministic_sys_id("rest_msg_" + rest_message["name"])

    msg_fields = {
        "name": rest_message["name"],
        "description": rest_message.get("description", ""),
        "rest_endpoint": aap_host,
        "authentication_type": "basic",
        "basic_auth_user": aap_username,
        "basic_auth_password": aap_password,
        "access": "package_private",
        "sys_class_name": "sys_rest_message",
        "sys_package": "global",
        "sys_scope": "global",
    }
    payload = build_payload_xml("sys_rest_message", msg_fields, msg_sys_id)
    records.append(build_update_xml_record(
        f"sys_rest_message_{msg_sys_id}",
        "sys_rest_message",
        rest_message["name"],
        payload, msg_sys_id, ts
    ))

    for method in rest_message.get("http_methods", []):
        fn_sys_id = deterministic_sys_id("rest_fn_" + method["name"])
        fn_fields = {
            "function_name": method["name"],
            "http_method": method["http_method"],
            "rest_endpoint": aap_host.rstrip("/") + method["endpoint"],
            "content": method.get("request_body", ""),
            "rest_message": msg_sys_id,
            "authentication_type": "inherit_from_parent",
            "sys_class_name": "sys_rest_message_fn",
        }
        fn_payload = build_payload_xml("sys_rest_message_fn", fn_fields, fn_sys_id)
        records.append(build_update_xml_record(
            f"sys_rest_message_fn_{fn_sys_id}",
            "sys_rest_message_fn",
            method["name"],
            fn_payload, fn_sys_id, ts
        ))

    return records


def variable_type_map(type_name):
    """Map YAML variable types to SNOW type numbers."""
    mapping = {
        "String": "6",
        "Text Area": "2",
        "Select Box": "5",
        "Check Box": "7",
        "Reference": "8",
        "Date": "10",
        "Integer": "14",
    }
    return mapping.get(type_name, "6")


def build_catalog_item_records(catalog_items, ts):
    """Generate update XML records for catalog items and their variables."""
    records = []

    for item in catalog_items:
        item_sys_id = deterministic_sys_id("cat_item_" + item["name"])
        item_fields = {
            "name": item["name"],
            "short_description": item.get("short_description", ""),
            "description": item.get("description", ""),
            "category": item.get("category", ""),
            "active": "true",
            "use_sc_layout": "true",
            "sys_class_name": "sc_cat_item",
            "workflow": "",
        }
        payload = build_payload_xml("sc_cat_item", item_fields, item_sys_id)
        records.append(build_update_xml_record(
            f"sc_cat_item_{item_sys_id}",
            "sc_cat_item",
            item["name"],
            payload, item_sys_id, ts
        ))

        for var in item.get("variables", []):
            var_sys_id = deterministic_sys_id("var_" + item["name"] + "_" + var["name"])
            choice_str = ""
            if var.get("choices"):
                choice_str = "\n".join(
                    f"{c['value']}={c['label']}" for c in var["choices"]
                )
            var_fields = {
                "name": var["name"],
                "question_text": var.get("label", var["name"]),
                "type": variable_type_map(var.get("type", "String")),
                "mandatory": str(var.get("mandatory", False)).lower(),
                "order": str(var.get("order", 100)),
                "default_value": var.get("default_value", ""),
                "help_text": var.get("help_text", ""),
                "cat_item": item_sys_id,
                "active": "true",
                "sys_class_name": "item_option_new",
                "choice_table": "",
                "choice_field": "",
            }
            if choice_str:
                var_fields["create_roles"] = ""
                var_fields["choice_table"] = ""
            var_payload = build_payload_xml("item_option_new", var_fields, var_sys_id)
            records.append(build_update_xml_record(
                f"item_option_new_{var_sys_id}",
                "item_option_new",
                var.get("label", var["name"]),
                var_payload, var_sys_id, ts
            ))

    return records


def build_script_include_record(ts):
    """Generate the AAPIntegration Script Include record."""
    si_sys_id = deterministic_sys_id("script_include_AAPIntegration")
    script = r"""var AAPIntegration = Class.create();
AAPIntegration.prototype = {
    initialize: function() {
        this.REST_MESSAGE = 'Ansible Automation Platform';
    },

    launchWorkflow: function(workflowName, extraVars, ritmSysId) {
        var sm = new sn_ws.RESTMessageV2(this.REST_MESSAGE, 'Launch Workflow');
        extraVars.snow_request_sys_id = ritmSysId;
        var wfId = this._getResourceId('workflow_job_templates', workflowName);
        sm.setStringParameterNoEscape('workflow_id', wfId);
        sm.setStringParameterNoEscape('extra_vars', JSON.stringify(extraVars));
        var response = sm.execute();
        return { status: response.getStatusCode(), body: response.getBody() };
    },

    launchJobTemplate: function(templateName, extraVars, ritmSysId) {
        var sm = new sn_ws.RESTMessageV2(this.REST_MESSAGE, 'Launch Job Template');
        extraVars.snow_request_sys_id = ritmSysId;
        var jtId = this._getResourceId('job_templates', templateName);
        sm.setStringParameterNoEscape('job_template_id', jtId);
        sm.setStringParameterNoEscape('extra_vars', JSON.stringify(extraVars));
        var response = sm.execute();
        return { status: response.getStatusCode(), body: response.getBody() };
    },

    _getResourceId: function(resourceType, name) {
        var sm = new sn_ws.RESTMessageV2(this.REST_MESSAGE, 'Get Job Status');
        var endpoint = sm.getEndpoint() || '';
        // Strip /api/... (including empty ${job_id} substitution) to get AAP base URL
        var baseUrl = endpoint.replace(/\/api\/.*$/, '').replace(/\/$/, '');
        if (!baseUrl) {
            throw new Error('Unable to resolve AAP base URL from REST Message endpoint: ' + endpoint);
        }
        sm.setEndpoint(baseUrl + '/api/controller/v2/' + resourceType + '/?name=' + encodeURIComponent(name));
        var response = sm.execute();
        var status = response.getStatusCode();
        var raw = response.getBody() || '';
        var body;
        try {
            body = JSON.parse(raw);
        } catch (e) {
            throw new Error('AAP lookup HTTP ' + status + ' non-JSON: ' + raw.substring(0, 200));
        }
        if (body.results && body.results.length > 0) {
            return body.results[0].id.toString();
        }
        throw new Error('Resource not found: ' + resourceType + '/' + name + ' (HTTP ' + status + ')');
    },

    type: 'AAPIntegration'
};"""

    si_fields = {
        "name": "AAPIntegration",
        "api_name": "global.AAPIntegration",
        "script": script,
        "description": "Utility to launch AAP job templates/workflows from catalog item orders",
        "active": "true",
        "access": "public",
        "client_callable": "false",
        "sys_class_name": "sys_script_include",
        "sys_package": "global",
        "sys_scope": "global",
    }
    payload = build_payload_xml("sys_script_include", si_fields, si_sys_id)
    return build_update_xml_record(
        f"sys_script_include_{si_sys_id}",
        "sys_script_include",
        "AAPIntegration",
        payload, si_sys_id, ts
    )


def build_business_rule_record(catalog_items, ts):
    """Generate the Business Rule that triggers AAP on catalog order."""
    br_sys_id = deterministic_sys_id("business_rule_aap_catalog_launch")

    mapping_lines = []
    for item in catalog_items:
        resource_type = "workflow" if item["aap_resource_type"] == "workflow_job_template" else "job_template"
        mapping_lines.append(
            f"        '{item['name']}': {{ type: '{resource_type}', name: '{item['aap_resource_name']}' }}"
        )
    mapping_str = ",\n".join(mapping_lines)

    script = f"""(function executeRule(current, previous) {{
    var aap = new AAPIntegration();
    var catItemName = current.cat_item.name.toString();
    var ritmSysId = current.sys_id.toString();

    var mapping = {{
{mapping_str}
    }};

    var config = mapping[catItemName];
    if (!config) return;

    var extraVars = {{}};
    var vars = new GlideRecord('sc_item_option_mtom');
    vars.addQuery('request_item', ritmSysId);
    vars.query();
    while (vars.next()) {{
        var opt = vars.sc_item_option;
        extraVars[opt.item_option_new.name.toString()] = opt.value.toString();
    }}

    try {{
        var result;
        if (config.type === 'workflow') {{
            result = aap.launchWorkflow(config.name, extraVars, ritmSysId);
        }} else {{
            result = aap.launchJobTemplate(config.name, extraVars, ritmSysId);
        }}
        if (result.status == 201) {{
            current.work_notes = 'AAP automation launched successfully';
            current.state = '2';
        }} else {{
            current.work_notes = 'AAP launch failed: ' + result.body;
        }}
        current.update();
    }} catch (e) {{
        gs.error('AAPIntegration error: ' + e.message);
        current.work_notes = 'AAP integration error: ' + e.message;
        current.update();
    }}
}})(current, previous);"""

    br_fields = {
        "name": "AAP - Launch on Catalog Order",
        "table": "sc_req_item",
        "when": "after",
        "action_insert": "true",
        "action_update": "false",
        "action_delete": "false",
        "action_query": "false",
        "active": "true",
        "order": "100",
        "script": script,
        "sys_class_name": "sys_script",
        "sys_package": "global",
        "sys_scope": "global",
    }
    payload = build_payload_xml("sys_script", br_fields, br_sys_id)
    return build_update_xml_record(
        f"sys_script_{br_sys_id}",
        "sys_script",
        "AAP - Launch on Catalog Order",
        payload, br_sys_id, ts
    )


def generate_update_set_xml(module):
    """Generate the complete Update Set XML."""
    params = module.params
    ts = now_str()
    us_sys_id = deterministic_sys_id("update_set_" + params["update_set_name"])
    remote_sys_id = deterministic_sys_id("remote_" + params["update_set_name"])

    records = []
    records.extend(build_rest_message_records(
        params["rest_message"],
        params["aap_host"],
        params["aap_username"],
        params["aap_password"],
        ts
    ))
    records.extend(build_catalog_item_records(params["catalog_items"], ts))
    records.append(build_script_include_record(ts))
    records.append(build_business_rule_record(params["catalog_items"], ts))

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<unload unload_date="{ts}">
<sys_remote_update_set action="INSERT_OR_UPDATE">
<application display_value="Global">global</application>
<application_name>Global</application_name>
<application_scope>global</application_scope>
<application_version/>
<collisions/>
<commit_date/>
<deleted/>
<description>AAP + ServiceNow catalog integration deployed from mad-hatter repository</description>
<inserted/>
<name>{xml_escape(params['update_set_name'])}</name>
<origin_sys_id>{us_sys_id}</origin_sys_id>
<release_date/>
<remote_sys_id>{us_sys_id}</remote_sys_id>
<state>loaded</state>
<summary/>
<sys_created_by>admin</sys_created_by>
<sys_created_on>{ts}</sys_created_on>
<sys_id>{remote_sys_id}</sys_id>
<sys_mod_count>0</sys_mod_count>
<sys_updated_by>admin</sys_updated_by>
<sys_updated_on>{ts}</sys_updated_on>
<update_set display_value=""/>
<update_source display_value=""/>
<updated/>
</sys_remote_update_set>
{chr(10).join(records)}
</unload>"""

    return xml


def upload_update_set(module, xml_content):
    """Deploy configuration by directly creating records in target tables via Table API.

    Falls back from the update set approach since sys_update_xml is write-protected.
    Creates records directly in: sys_rest_message_fn, sc_cat_item, item_option_new,
    sys_script_include, sys_script.
    """
    try:
        import requests
        from requests.auth import HTTPBasicAuth
    except ImportError:
        module.fail_json(msg="python 'requests' library is required")

    params = module.params
    instance = params["instance"].rstrip("/")

    session = requests.Session()
    session.auth = HTTPBasicAuth(params["username"], params["password"])
    session.verify = False
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
    })

    results = {"created": [], "errors": [], "skipped": []}

    # 0. Resolve AAP resource IDs (launch-by-id; avoids name lookup + auth on GET)
    catalog_items = resolve_aap_resource_ids(module, results)
    if any(not item.get("aap_resource_id") for item in catalog_items):
        missing = [i["name"] for i in catalog_items if not i.get("aap_resource_id")]
        module.fail_json(
            msg=f"Could not resolve AAP resource ids for: {missing}",
            **results,
        )

    # 0b. Store AAP API credentials as system properties for Script Include setBasicAuth()
    ensure_aap_sys_properties(module, results)

    # 1. REST Message — find or create; always refresh endpoint/auth for new AAP
    rest_msg = params["rest_message"]
    aap_host = params["aap_host"].rstrip("/")
    resp = session.get(
        f"{instance}/api/now/table/sys_rest_message",
        params={"sysparm_query": f"name={rest_msg['name']}", "sysparm_limit": "1"}
    )
    existing = resp.json().get("result", [])
    rest_msg_body = {
        "name": rest_msg["name"],
        "description": rest_msg.get("description", ""),
        "rest_endpoint": aap_host,
        "authentication_type": "basic",
        "basic_auth_user": params["aap_username"],
        "basic_auth_password": params["aap_password"],
    }
    if existing:
        msg_sys_id = existing[0]["sys_id"]
        r = session.put(
            f"{instance}/api/now/table/sys_rest_message/{msg_sys_id}",
            json=rest_msg_body,
        )
        if r.status_code in (200, 201):
            results["created"].append(f"REST Message updated: {rest_msg['name']} -> {aap_host}")
        else:
            results["errors"].append(f"REST Message update: {r.status_code}")
    else:
        r = session.post(f"{instance}/api/now/table/sys_rest_message", json=rest_msg_body)
        if r.status_code in (200, 201):
            msg_sys_id = r.json()["result"]["sys_id"]
            results["created"].append(f"REST Message: {rest_msg['name']}")
        else:
            msg_sys_id = None
            results["errors"].append(f"REST Message: {r.status_code}")

    # 2. REST Message HTTP Methods — create or update endpoints to current AAP
    if msg_sys_id:
        for method in rest_msg.get("http_methods", []):
            endpoint = aap_host + method["endpoint"]
            check = session.get(
                f"{instance}/api/now/table/sys_rest_message_fn",
                params={
                    "sysparm_query": f"rest_message={msg_sys_id}^function_name={method['name']}",
                    "sysparm_limit": "1"
                }
            )
            # Set basic auth on each method explicitly. inherit_from_parent + setEndpoint()
            # has been observed to omit the Authorization header (HTTP 401 from AAP).
            fn_data = {
                "function_name": method["name"],
                "rest_message": msg_sys_id,
                "http_method": method["http_method"],
                "rest_endpoint": endpoint,
                "content": method.get("request_body", ""),
                "authentication_type": "basic",
                "basic_auth_user": params["aap_username"],
                "basic_auth_password": params["aap_password"],
            }
            if check.status_code == 200 and check.json().get("result"):
                fn_sys_id = check.json()["result"][0]["sys_id"]
                r = session.put(
                    f"{instance}/api/now/table/sys_rest_message_fn/{fn_sys_id}",
                    json=fn_data,
                )
                if r.status_code in (200, 201):
                    results["created"].append(f"HTTP Method updated: {method['name']}")
                else:
                    detail = ""
                    try:
                        detail = r.json().get("error", {}).get("message", "")
                    except Exception:
                        detail = r.text[:200]
                    results["errors"].append(
                        f"HTTP Method update '{method['name']}': {r.status_code} - {detail}"
                    )
                continue

            r = session.post(f"{instance}/api/now/table/sys_rest_message_fn", json=fn_data)
            if r.status_code in (200, 201):
                results["created"].append(f"HTTP Method: {method['name']}")
            else:
                detail = ""
                try:
                    detail = r.json().get("error", {}).get("message", "")
                except Exception:
                    detail = r.text[:200]
                results["errors"].append(f"HTTP Method '{method['name']}': {r.status_code} - {detail}")
    # 3. Catalog Items
    for item in params["catalog_items"]:
        check = session.get(
            f"{instance}/api/now/table/sc_cat_item",
            params={"sysparm_query": f"name={item['name']}", "sysparm_limit": "1"}
        )
        if check.status_code == 200 and check.json().get("result"):
            item_sys_id = check.json()["result"][0]["sys_id"]
            results["skipped"].append(f"Catalog Item: {item['name']}")
        else:
            # Look up the "Services" category in the main "Service Catalog"
            cat_query = session.get(
                f"{instance}/api/now/table/sc_category",
                params={"sysparm_query": "title=Services^sc_catalog.title=Service Catalog", "sysparm_limit": "1"}
            )
            cat_results = cat_query.json().get("result", []) if cat_query.status_code == 200 else []
            category_id = cat_results[0]["sys_id"] if cat_results else ""

            catalog_query = session.get(
                f"{instance}/api/now/table/sc_catalog",
                params={"sysparm_query": "title=Service Catalog", "sysparm_limit": "1"}
            )
            catalog_results = catalog_query.json().get("result", []) if catalog_query.status_code == 200 else []
            catalog_id = catalog_results[0]["sys_id"] if catalog_results else ""

            r = session.post(f"{instance}/api/now/table/sc_cat_item", json={
                "name": item["name"],
                "short_description": item.get("short_description", ""),
                "description": item.get("description", ""),
                "category": category_id,
                "sc_catalogs": catalog_id,
                "active": "true",
                "use_sc_layout": "true",
            })
            if r.status_code in (200, 201):
                item_sys_id = r.json()["result"]["sys_id"]
                results["created"].append(f"Catalog Item: {item['name']}")
            else:
                item_sys_id = None
                results["errors"].append(f"Catalog Item '{item['name']}': {r.status_code}")

        # 4. Catalog Variables
        if item_sys_id:
            for var in item.get("variables", []):
                var_check = session.get(
                    f"{instance}/api/now/table/item_option_new",
                    params={
                        "sysparm_query": f"cat_item={item_sys_id}^name={var['name']}",
                        "sysparm_limit": "1"
                    }
                )
                if var_check.status_code == 200 and var_check.json().get("result"):
                    results["skipped"].append(f"Variable: {var['name']}")
                    continue

                var_data = {
                    "name": var["name"],
                    "question_text": var.get("label", var["name"]),
                    "type": variable_type_map(var.get("type", "String")),
                    "mandatory": str(var.get("mandatory", False)).lower(),
                    "order": str(var.get("order", 100)),
                    "default_value": var.get("default_value", ""),
                    "help_text": var.get("help_text", ""),
                    "cat_item": item_sys_id,
                    "active": "true",
                }
                r = session.post(f"{instance}/api/now/table/item_option_new", json=var_data)
                if r.status_code in (200, 201):
                    results["created"].append(f"Variable: {item['name']}/{var['name']}")
                else:
                    results["errors"].append(f"Variable '{var['name']}': {r.status_code}")

    # 5. Script Include — create or refresh (AAP 2.7 controller API paths)
    si_script = _get_script_include_body(aap_host)
    si_body = {
        "name": "AAPIntegration",
        "api_name": "global.AAPIntegration",
        "script": si_script,
        "description": "Utility to launch AAP job templates/workflows from catalog item orders",
        "active": "true",
        "access": "public",
        "client_callable": "false",
    }
    si_check = session.get(
        f"{instance}/api/now/table/sys_script_include",
        params={"sysparm_query": "name=AAPIntegration", "sysparm_limit": "1"}
    )
    if si_check.status_code == 200 and si_check.json().get("result"):
        si_sys_id = si_check.json()["result"][0]["sys_id"]
        r = session.put(
            f"{instance}/api/now/table/sys_script_include/{si_sys_id}",
            json=si_body,
        )
        if r.status_code in (200, 201):
            results["created"].append("Script Include updated: AAPIntegration")
        else:
            results["errors"].append(f"Script Include update: {r.status_code}")
    else:
        r = session.post(f"{instance}/api/now/table/sys_script_include", json=si_body)
        if r.status_code in (200, 201):
            results["created"].append("Script Include: AAPIntegration")
        else:
            results["errors"].append(f"Script Include: {r.status_code}")

    # 6. Business Rule - Catalog Orders — create or refresh catalog→AAP mapping
    br_script = _get_business_rule_body(catalog_items)
    br_body = {
        "name": "AAP - Launch on Catalog Order",
        "collection": "sc_req_item",
        "when": "after",
        "action_insert": "true",
        "action_update": "false",
        "action_delete": "false",
        "action_query": "false",
        "active": "true",
        "order": "100",
        "script": br_script,
    }
    br_check = session.get(
        f"{instance}/api/now/table/sys_script",
        params={"sysparm_query": "name=AAP - Launch on Catalog Order", "sysparm_limit": "1"}
    )
    if br_check.status_code == 200 and br_check.json().get("result"):
        br_sys_id = br_check.json()["result"][0]["sys_id"]
        r = session.put(
            f"{instance}/api/now/table/sys_script/{br_sys_id}",
            json=br_body,
        )
        if r.status_code in (200, 201):
            results["created"].append("Business Rule updated: AAP - Launch on Catalog Order")
        else:
            results["errors"].append(f"Business Rule update: {r.status_code}")
    else:
        r = session.post(f"{instance}/api/now/table/sys_script", json=br_body)
        if r.status_code in (200, 201):
            results["created"].append("Business Rule: AAP - Launch on Catalog Order")
        else:
            results["errors"].append(f"Business Rule: {r.status_code}")
    # 7. Business Rule - Change Request Approval triggers Configure Devices
    cr_br_check = session.get(
        f"{instance}/api/now/table/sys_script",
        params={"sysparm_query": "name=AAP - Configure on CR Implement", "sysparm_limit": "1"}
    )
    if cr_br_check.status_code == 200 and cr_br_check.json().get("result"):
        results["skipped"].append("Business Rule: AAP - Configure on CR Implement")
    else:
        cr_br_script = _get_change_request_br_body()
        r = session.post(f"{instance}/api/now/table/sys_script", json={
            "name": "AAP - Configure on CR Implement",
            "collection": "change_request",
            "when": "after",
            "action_insert": "false",
            "action_update": "true",
            "action_delete": "false",
            "action_query": "false",
            "active": "true",
            "order": "100",
            "condition": "current.state.changesTo(-1)",
            "script": cr_br_script,
        })
        if r.status_code in (200, 201):
            results["created"].append("Business Rule: AAP - Configure on CR Implement")
        else:
            results["errors"].append(f"Business Rule CR: {r.status_code}")

    return results


def resolve_aap_resource_ids(module, results):
    """Look up AAP job/workflow template ids by name; allow YAML override via aap_resource_id."""
    try:
        import requests
        from requests.auth import HTTPBasicAuth
    except ImportError:
        module.fail_json(msg="python 'requests' library is required")

    params = module.params
    aap_host = params["aap_host"].rstrip("/")
    session = requests.Session()
    session.auth = HTTPBasicAuth(params["aap_username"], params["aap_password"])
    session.verify = False
    session.headers.update({"Accept": "application/json"})

    enriched = []
    for item in params["catalog_items"]:
        item = dict(item)
        if item.get("aap_resource_id"):
            results["skipped"].append(
                f"AAP id override: {item['name']} -> {item['aap_resource_id']}"
            )
            enriched.append(item)
            continue

        resource_type = item["aap_resource_type"]  # job_template | workflow_job_template
        name = item["aap_resource_name"]
        url = f"{aap_host}/api/controller/v2/{resource_type}s/"
        r = session.get(url, params={"name": name})
        if r.status_code != 200:
            results["errors"].append(
                f"AAP lookup '{name}': HTTP {r.status_code}"
            )
            enriched.append(item)
            continue
        matches = r.json().get("results") or []
        if not matches:
            results["errors"].append(f"AAP lookup '{name}': no results")
            enriched.append(item)
            continue
        item["aap_resource_id"] = str(matches[0]["id"])
        results["created"].append(
            f"AAP id resolved: {item['name']} -> {item['aap_resource_id']} ({name})"
        )
        enriched.append(item)
    return enriched


def ensure_aap_sys_properties(module, results):
    """Upsert aap.api.username / aap.api.password for Script Include setBasicAuth()."""
    try:
        import requests
        from requests.auth import HTTPBasicAuth
    except ImportError:
        module.fail_json(msg="python 'requests' library is required")

    params = module.params
    instance = params["instance"].rstrip("/")
    session = requests.Session()
    session.auth = HTTPBasicAuth(params["username"], params["password"])
    session.verify = False
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    props = [
        {
            "name": "aap.api.username",
            "value": params["aap_username"],
            "description": "AAP API username for catalog launch (AAPIntegration Script Include)",
            "type": "string",
        },
        {
            "name": "aap.api.password",
            "value": params["aap_password"],
            "description": "AAP API password for catalog launch (AAPIntegration Script Include)",
            "type": "password2",
        },
    ]
    for prop in props:
        check = session.get(
            f"{instance}/api/now/table/sys_properties",
            params={"sysparm_query": f"name={prop['name']}", "sysparm_limit": "1"},
        )
        existing = check.json().get("result", []) if check.status_code == 200 else []
        body = {
            "name": prop["name"],
            "value": prop["value"],
            "description": prop["description"],
            "type": prop["type"],
        }
        if existing:
            r = session.put(
                f"{instance}/api/now/table/sys_properties/{existing[0]['sys_id']}",
                json=body,
            )
            label = "updated"
        else:
            r = session.post(f"{instance}/api/now/table/sys_properties", json=body)
            label = "created"
        if r.status_code in (200, 201):
            results["created"].append(f"sys_property {label}: {prop['name']}")
        else:
            results["errors"].append(
                f"sys_property {prop['name']}: HTTP {r.status_code}"
            )


def _get_script_include_body(aap_host):
    """Return the AAPIntegration Script Include script."""
    # aap_host kept for call-site compatibility; endpoints come from the REST Message.
    _ = aap_host
    return r"""var AAPIntegration = Class.create();
AAPIntegration.prototype = {
    initialize: function() {
        this.REST_MESSAGE = 'Ansible Automation Platform';
    },

    /**
     * Apply basic auth from sys_properties. REST Message use_basic_auth stays false
     * on some instances, which causes AAP to return HTTP 401.
     */
    _applyAuth: function(sm) {
        var user = gs.getProperty('aap.api.username');
        var pass = gs.getProperty('aap.api.password');
        if (!user || !pass) {
            throw new Error('Missing aap.api.username / aap.api.password system properties');
        }
        sm.setBasicAuth(user, pass);
        sm.setRequestHeader('Accept', 'application/json');
        sm.setRequestHeader('Content-Type', 'application/json');
    },

    /**
     * Launch a workflow job template by numeric AAP id (no name lookup).
     * @param {string|number} workflowId
     * @param {object} extraVars
     * @param {string} ritmSysId
     */
    launchWorkflow: function(workflowId, extraVars, ritmSysId) {
        var sm = new sn_ws.RESTMessageV2(this.REST_MESSAGE, 'Launch Workflow');
        this._applyAuth(sm);
        if (ritmSysId) {
            extraVars.snow_request_sys_id = ritmSysId;
        }
        sm.setStringParameterNoEscape('workflow_id', workflowId.toString());
        sm.setStringParameterNoEscape('extra_vars', JSON.stringify(extraVars));
        var response = sm.execute();
        return { status: response.getStatusCode(), body: response.getBody() };
    },

    /**
     * Launch a job template by numeric AAP id (no name lookup).
     * @param {string|number} templateId
     * @param {object} extraVars
     * @param {string} ritmSysId
     */
    launchJobTemplate: function(templateId, extraVars, ritmSysId) {
        var sm = new sn_ws.RESTMessageV2(this.REST_MESSAGE, 'Launch Job Template');
        this._applyAuth(sm);
        if (ritmSysId) {
            extraVars.snow_request_sys_id = ritmSysId;
        }
        sm.setStringParameterNoEscape('job_template_id', templateId.toString());
        sm.setStringParameterNoEscape('extra_vars', JSON.stringify(extraVars));
        var response = sm.execute();
        return { status: response.getStatusCode(), body: response.getBody() };
    },

    type: 'AAPIntegration'
};"""


def _get_business_rule_body(catalog_items):
    """Return the Business Rule script. catalog_items must include aap_resource_id."""
    mapping_lines = []
    for item in catalog_items:
        resource_type = "workflow" if item["aap_resource_type"] == "workflow_job_template" else "job_template"
        resource_id = item.get("aap_resource_id")
        if resource_id is None or resource_id == "":
            raise ValueError(
                f"Catalog item '{item['name']}' is missing aap_resource_id "
                "(resolve from AAP before generating the business rule)"
            )
        mapping_lines.append(
            f"        '{item['name']}': {{ type: '{resource_type}', "
            f"id: '{resource_id}', name: '{item['aap_resource_name']}' }}"
        )
    mapping_str = ",\n".join(mapping_lines)

    return f"""(function executeRule(current, previous) {{
    var aap = new AAPIntegration();
    var catItemName = current.cat_item.name.toString();
    var ritmSysId = current.sys_id.toString();

    var mapping = {{
{mapping_str}
    }};

    var config = mapping[catItemName];
    if (!config) return;

    var extraVars = {{}};
    var vars = new GlideRecord('sc_item_option_mtom');
    vars.addQuery('request_item', ritmSysId);
    vars.query();
    while (vars.next()) {{
        var opt = vars.sc_item_option;
        extraVars[opt.item_option_new.name.toString()] = opt.value.toString();
    }}

    try {{
        var result;
        if (config.type === 'workflow') {{
            result = aap.launchWorkflow(config.id, extraVars, ritmSysId);
        }} else {{
            result = aap.launchJobTemplate(config.id, extraVars, ritmSysId);
        }}
        if (result.status == 201 || result.status == '201') {{
            current.work_notes = 'AAP automation launched successfully (id=' + config.id + ', ' + config.name + '): ' + result.body.substring(0, 200);
            current.state = '2';
        }} else {{
            current.work_notes = 'AAP launch failed (HTTP ' + result.status + ', id=' + config.id + '): ' + result.body;
        }}
        current.update();
    }} catch (e) {{
        gs.error('AAPIntegration error: ' + e.message);
        current.work_notes = 'AAP integration error: ' + e.message;
        current.update();
    }}
}})(current, previous);"""


def _get_change_request_br_body():
    """Return the Business Rule script for Change Request -> Implement triggers AAP."""
    return """(function executeRule(current, previous) {
    // Only fire when state changes to Implement (-1)
    if (current.state != '-1') return;
    if (previous.state == '-1') return;

    var aap = new AAPIntegration();
    var crSysId = current.sys_id.toString();
    var crNumber = current.number.toString();

    // Look up the Configure Devices job template ID
    var configureJtId = 22;

    try {
        var extraVars = {
            snow_change_sys_id: crSysId,
            snow_change_number: crNumber
        };

        // Launch the Configure Devices job template (hardcoded ID set during CasC)
        var result = aap.launchJobTemplate(22, extraVars);
        if (result.status == 201 || result.status == '201') {
            current.work_notes = '[AAP] Configuration automation launched. Job: ' + result.body.substring(0, 150);
        } else {
            current.work_notes = '[AAP] Launch failed (status ' + result.status + '): ' + result.body.substring(0, 200);
        }
        current.update();
    } catch (e) {
        gs.error('AAP CR integration error: ' + e.message);
        current.work_notes = '[AAP] Integration error: ' + e.message;
        current.update();
    }
})(current, previous);"""


def find_and_commit_update_set(module, remote_us_id):
    """Preview and commit the uploaded update set."""
    try:
        import requests
        from requests.auth import HTTPBasicAuth
    except ImportError:
        module.fail_json(msg="python 'requests' library is required")

    params = module.params
    instance = params["instance"].rstrip("/")

    session = requests.Session()
    session.auth = HTTPBasicAuth(params["username"], params["password"])
    session.verify = False
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    # Preview the update set
    preview_resp = session.patch(
        f"{instance}/api/now/table/sys_remote_update_set/{remote_us_id}",
        json={"state": "previewed"}
    )
    time.sleep(5)

    # Commit the update set
    commit_resp = session.patch(
        f"{instance}/api/now/table/sys_remote_update_set/{remote_us_id}",
        json={"state": "committed"}
    )

    if commit_resp.status_code == 200:
        return {"committed": True, "sys_id": remote_us_id, "msg": "Update set committed successfully"}
    else:
        return {
            "committed": False,
            "sys_id": remote_us_id,
            "msg": f"Commit returned status {commit_resp.status_code}",
            "detail": commit_resp.text[:300]
        }


def main():
    module = AnsibleModule(
        argument_spec=dict(
            instance=dict(type="str", required=True),
            username=dict(type="str", required=True),
            password=dict(type="str", required=True, no_log=True),
            aap_host=dict(type="str", required=True),
            aap_username=dict(type="str", required=True),
            aap_password=dict(type="str", required=True, no_log=True),
            catalog_items=dict(type="list", required=True),
            rest_message=dict(type="dict", required=True),
            update_set_name=dict(type="str", default="AAP ServiceNow Integration"),
            commit=dict(type="bool", default=True),
        ),
        supports_check_mode=True,
    )

    xml_content = generate_update_set_xml(module)

    if module.check_mode:
        module.exit_json(changed=True, xml_preview=xml_content[:2000], msg="Check mode: XML generated but not uploaded")

    deploy_result = upload_update_set(module, xml_content)

    result = {
        "changed": len(deploy_result["created"]) > 0,
        "uploaded": True,
        "update_set_name": module.params["update_set_name"],
        "created": deploy_result["created"],
        "skipped": deploy_result["skipped"],
        "errors": deploy_result["errors"],
        "committed": len(deploy_result["errors"]) == 0,
        "msg": f"Created {len(deploy_result['created'])} resources, "
               f"skipped {len(deploy_result['skipped'])}, "
               f"errors: {len(deploy_result['errors'])}",
    }

    module.exit_json(**result)


if __name__ == "__main__":
    main()

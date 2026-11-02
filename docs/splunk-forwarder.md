# Splunk Universal Forwarder demo

This demo installs a Splunk Universal Forwarder on the RHEL VMs created by the
APD **Deploy Cloud Stack in AWS** workflow. It uses the existing APD dynamic
inventory and machine credential; the Splunk jobs have their own project,
credentials, and execution environment.

## Prerequisites

- Run APD cloud setup, deploy the cloud stack, and sync its AWS inventory. The
  default target pattern is `aws_rhel8:aws_rhel9`; override
  `splunk_forwarder_targets` if the deployed inventory uses different names.
- The VMs must be reachable by AAP, have privilege escalation and outbound
  access to `download.splunk.com`, and reach the Splunk receiver.
- Supply `SPLUNK_URL`, `SPLUNK_API_URL`, `SPLUNK_USERNAME`, `SPLUNK_PASSWORD`,
  `SPLUNK_RECEIVER_PORT`, and `SPLUNK_FORWARDER_PASSWORD` through the
  environment or an untracked credentials file. `SPLUNK_RECEIVER_HOST`
  defaults to the hostname in `SPLUNK_URL`; `SPLUNK_FORWARDER_USERNAME`
  defaults to `admin`. The forwarder password is a separate local credential,
  not the Splunk server password, and must remain stable across runs.
- API TLS validation defaults to enabled. For a demo using a self-signed
  certificate, explicitly set `SPLUNK_API_VALIDATE_CERTS=false`.
- Build and publish `quay.io/matferna/mh-splunk:latest`, and ensure the image
  repository is public or that AAP has a suitable registry credential.

The default forwarder version and release ID are defined in
`roles/splunk_aap/defaults/main.yml`. The module downloads the RPM and its
SHA512 checksum from Splunk. Update both values together for an upgrade;
automatic downgrades are not supported by the module.

## Build the execution environment

```bash
./execution_environments/splunk/build.sh
```

The script builds an amd64 image using the public `mh-rosa` base, adds a
compatible Ansible version and the pinned `splunk.enterprise` collection, and
pushes dated and `latest` tags. Set `SKIP_QUAY_PUSH=1` to build locally only,
or set `SPLUNK_EE_IMAGE` and `SPLUNK_EE_TAG` to choose another destination.

## Configure AAP

Source the local environment and apply the Splunk CasC:

```bash
set -a; source .env; set +a
ansible-playbook casc-deploy.yml --tags splunk
```

The AAP project pulls this repository from its configured Git branch, so that
branch must contain the playbooks before CasC can create the job templates.
Use `-e splunk_aap_project_scm_branch=<branch>` for a published feature branch.
The AAP controller connection uses `CONTROLLER_HOST`, `CONTROLLER_USERNAME`,
and `CONTROLLER_PASSWORD` in the same way as the other CasC roles.

CasC creates **Splunk Server** and **Splunk Forwarder** credential types and
credentials, a dedicated execution environment, a project, and two templates:

1. **Splunk | Deploy Universal Forwarder** checks the selected hosts, installs
   the forwarder, and configures a dedicated demo log input in index `main`.
   It fails before replacing any different existing forwarder receivers unless
   `splunk_allow_receiver_replacement=true` is deliberately supplied.
2. **Splunk | Verify Forwarder Events** writes a unique marker to that log on
   each target and searches for it through the Splunk management API. It fails
   when events do not arrive or the API user lacks search access to the index.

Set `splunk_demo_index` to use another existing index. The job creates only its
own small input at `/var/log/aap-splunk-demo.log`; it does not forward all
system logs. The server credentials are stored as encrypted AAP credentials.

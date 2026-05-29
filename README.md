# Mad Hatter

Ansible-driven deployer for Red Hat Ansible Automation Platform (AAP) on
OpenShift. Provisions AAP, optional add-ons (ContainerLab, OpenShift
Virtualization product demos, Automation Portal), and applies Configuration
as Code -- all from a single `ansible-playbook` or `ansible-navigator` command.

## Overview

The project targets two managed OpenShift platforms:

| Platform | Playbook | Use case |
|---|---|---|
| **ARO** (Azure Red Hat OpenShift) | `deploy_aro.yml` | AAP, ContainerLab networking labs, OCP-V product demos |
| **ROSA** (Red Hat OpenShift Service on AWS) | `deploy_rosa.yml` | AAP, bare-metal OCP-V nodes, OCP-V product demos |

A third playbook, `deploy_portal.yml`, deploys the **Ansible Automation
Portal** (Helm-based, formerly "Self-Service Portal") on either platform.

### AAP 2.7

The `aap_operator` role defaults to the `stable-2.7` operator channel.
Override with `-e aap_operator_operator_channel=stable-2.6` for older
clusters. Key 2.7 changes this repo accounts for:

- The **platform gateway** is the sole API entry point; direct `/api/v2/` access is removed.
- CasC modules authenticate via gateway OAuth tokens (`ansible.platform.token`).
- The `ansible.platform` collection replaces the deprecated `ansible.hub` modules.
- The Automation Portal uses OCI plugin delivery from `registry.redhat.io`.

## Prerequisites

| Tool | Required for | Notes |
|---|---|---|
| `ansible-navigator` | Running playbooks inside an EE | [Install guide](https://ansible.readthedocs.io/projects/navigator/installation/) |
| `oc` | All playbooks | Logged into the target cluster |
| `helm` v3+ | `deploy_portal.yml` | [Install guide](https://helm.sh/docs/intro/install/) |
| `podman` | Building Execution Environments | Only needed if rebuilding EE images |
| SSH key pair | AAP machine credentials | Mounted into the EE at `/root/keys/` |
| AAP manifest | `aap_operator` role | Mounted into the EE at `/root/manifests/manifest.zip` |

## Quick Start

```bash
# 1. Clone
git clone https://github.com/l3acon/mad-hatter.git && cd mad-hatter

# 2. Copy and fill in credential files
cp examples/user.creds.yml user.creds.yml        # edit with your passwords/tokens
# then copy the RHDP YAML tab output for your environment:
#   ARO -> aro.creds.yml    ROSA -> rosa.creds.yml

# 3. Copy the navigator config and adjust volume-mount paths
cp examples/ansible-navigator.yml ansible-navigator.yml

# 4. Export required environment variables
export CONTROLLER_PASSWORD='YourAAP AdminPass'
export AAP_MACHINE_CRED_PASSWORD='MachineCredPass1!'
export K8S_AUTH_PASSWORD='YourAAP AdminPass'

# 5. Run a playbook (AAP-only on ARO as an example)
ansible-navigator run deploy_aro.yml --tags aap \
  --eei quay.io/matferna/mh-aro:latest
```

## Playbooks

### `deploy_aro.yml` -- ARO

Use `--tags` to select components:

| Tags | Description |
|---|---|
| `--tags aap` | AAP operator + manifest injection. |
| `--tags aap,clab` | AAP + ContainerLab + multi-vendor network CasC. |
| `--tags aap,apd` | AAP + OpenShift Virtualization product demos CasC. |
| `--tags aap,clab,apd` | AAP + ContainerLab + product demos. |
| _(no tags)_ | Everything. |

**Infrastructure:** order an [ARO Open Environment](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/azure-gpte.open-environment-aro4-sub.prod&utm_source=webapp&utm_medium=share-link) from RHDP, then copy the YAML tab to `aro.creds.yml`.

```bash
ansible-navigator run deploy_aro.yml --tags aap,clab \
  --eei quay.io/matferna/mh-aro:latest
```

### `deploy_rosa.yml` -- ROSA

Use `--tags` to select components:

| Tags | Description |
|---|---|
| `--tags aap` | AAP operator + manifest injection. |
| `--tags aap,ocpv` | AAP + bare-metal machinepool for OCP Virtualization. |
| `--tags aap,apd` | AAP + OpenShift Virtualization product demos CasC. |
| `--tags aap,ocpv,apd` | AAP + bare-metal node + product demos. |
| _(no tags)_ | Everything. |

**Infrastructure:** order a [ROSA Open Environment](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/sandboxes-gpte.rosa.prod&utm_source=webapp&utm_medium=share-link) from RHDP, then copy the YAML tab to `rosa.creds.yml`.

```bash
ansible-navigator run deploy_rosa.yml \
  --eei quay.io/matferna/mh-rosa:latest
```

### `deploy_portal.yml` -- Automation Portal

Deploys the Ansible Automation Portal on OpenShift via the
`redhat-rhaap-portal` Helm chart. Requires AAP 2.7+. Features enabled out of
the box:

- **EE Builder** -- visual wizard for defining Execution Environments.
- **Content catalog** -- syncs collections from Private Automation Hub and discovers Ansible content in Git orgs.
- **OCI plugin delivery** -- plugins pulled from `registry.redhat.io`; registry auth is provisioned automatically from the cluster pull-secret.

```bash
ansible-playbook deploy_portal.yml \
  -e controller_host=https://aap.apps.example.com \
  -e controller_username=admin \
  -e controller_password='YourPassword' \
  -e github_token=ghp_xxxxxxxxxxxxxxxxxxxx   # optional, enables save-to-Git
```

See [roles/self-service/README.md](roles/self-service/README.md) for the full
variable reference, tag list, and troubleshooting.

## Configuration

### Credential files

| File | Source | Used by |
|---|---|---|
| `user.creds.yml` | Copy from [examples/user.creds.yml](examples/user.creds.yml) | All playbooks -- AAP admin password, Lightspeed token |
| `aro.creds.yml` | RHDP YAML tab (ARO) | `deploy_aro.yml` -- cluster API URL, kubeadmin password, Azure SP |
| `rosa.creds.yml` | RHDP YAML tab (ROSA) | `deploy_rosa.yml` -- bastion host, cluster details, AWS keys |

### Environment variables

These are passed through `ansible-navigator` (or exported in your shell) and
consumed by the `user_creds` role:

| Variable | Maps to | Description |
|---|---|---|
| `CONTROLLER_PASSWORD` | `aap_admin_password` | AAP admin password |
| `AAP_MACHINE_CRED_PASSWORD` | `aap_machine_cred_password` | Machine credential password (must meet Windows complexity: 8+ chars, 3 of 4 character classes) |
| `K8S_AUTH_PASSWORD` | `openshift_admin_password` | OpenShift admin password (also set in `user.creds.yml`) |

### ansible-navigator

Copy [examples/ansible-navigator.yml](examples/ansible-navigator.yml) to the
project root and adjust the volume-mount `src` paths to your local key and
manifest directories. The example mounts `~/keys` to `/root/keys` and
`~/manifests` to `/root/manifests` inside the EE.

## Execution Environments

Pre-built images are available at `quay.io/matferna/mh-aro:latest` and
`quay.io/matferna/mh-rosa:latest`. To rebuild or customize, see
[execution_environments/README.md](execution_environments/README.md) for
build scripts, registry authentication, and validation.

## Troubleshooting

**CasC module errors are redacted by default.** Add the following flag to see
full credential/config details in the Ansible output:

```bash
-e controller_configuration_credentials_secure_logging=false
```

**Portal init container `CrashLoopBackOff`:** usually an OCI plugin pull
failure. Check pod events with `oc describe pod` -- common causes are missing
registry auth or an image tag mismatch. See
[roles/self-service/README.md](roles/self-service/README.md#troubleshooting).

**AAP controller 503 during manifest injection:** the gateway may be up before
the controller API is fully ready. The `aap_operator` role includes a readiness
check, but if running manually, wait for
`/api/controller/v2/ping/` to return 200.

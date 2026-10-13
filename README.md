# Mad Hatter

Ansible-driven deployer for Red Hat Ansible Automation Platform (AAP) on
OpenShift. Provisions AAP, optional add-ons (OpenShift Virtualization,
ServiceNow integration, Self-Service Portal), and applies Configuration
as Code — all from a single `ansible-playbook` or `ansible-navigator` command.

## Overview

The project supports multiple OpenShift environments and separates deployment
into modular playbooks that follow the `*-deploy.yml` naming convention.

| Playbook | Purpose |
|---|---|
| `infra-deploy.yml` | Platform login, AAP operator, bare-metal nodes (ROSA/ARO) |
| `casc-deploy.yml` | CasC for SNOW, product demos, ContainerLab (ROSA/ARO) |
| `aap-deploy.yml` | Deploy AAP operator standalone (any cluster) |
| `ocpv-deploy.yml` | Deploy OpenShift Virtualization operator |
| `workshop-deploy.yml` | Deploy OCP-V CasC to pre-provisioned workshop clusters |
| `windows-golden-deploy.yml` | Build Windows Server golden image from ISO |
| `portal-deploy.yml` | Self-Service Portal (RHAAP Developer Hub via Helm) |
| `snow-deploy.yml` | Deploy SNOW catalog items |
| `ao-deploy.yml` | Automation Orchestrator operator |
| `rosa-deploy.yml` | ROSA-specific deployment |
| `aro-deploy.yml` | ARO-specific deployment |

### Supported environments

| Environment | Creds file | Deploy playbooks |
|---|---|---|
| **ROSA** (AWS) | `rosa.creds.yml` | `infra-deploy.yml --tags rosa,aap,ocpv` → `casc-deploy.yml` |
| **ARO** (Azure) | `aro.creds.yml` | `infra-deploy.yml --tags aro,aap` → `casc-deploy.yml` |
| **OCP-V Workshop** | `ocp-v-workshop.creds.yml` | `aap-deploy.yml` → `ocpv-deploy.yml` → `workshop-deploy.yml` |
| **OCP Multi-Cloud** | `ocp-mc.creds.yml` | `aap-deploy.yml` → `ocpv-deploy.yml` → `workshop-deploy.yml` |

### AAP 2.7

The `aap_operator` role defaults to `stable-2.7`. Key changes this repo accounts for:

- The **platform gateway** is the sole API entry point.
- CasC modules authenticate via gateway OAuth tokens (`ansible.platform.token`).
- The Self-Service Portal uses OCI plugin delivery from `registry.redhat.io`.

## Prerequisites

| Tool | Required for | Notes |
|---|---|---|
| `ansible-navigator` / `ansible-playbook` | Running playbooks | [Install guide](https://ansible.readthedocs.io/projects/navigator/installation/) |
| `oc` | All playbooks | Logged into the target cluster |
| `helm` v3+ | `portal-deploy.yml` | [Install guide](https://helm.sh/docs/intro/install/) |
| `virtctl` | `windows-golden-deploy.yml` | Installed from cluster: `oc get consoleclidownload` |
| `podman` | EE builds, golden image pipeline | Only needed if rebuilding EE images |
| SSH key pair | AAP machine credentials | Mounted into the EE at `/root/keys/` |
| AAP manifest | `aap_operator` role | Mounted into the EE at `/root/manifests/manifest.zip` |

## Quick Start

### ROSA environment

```bash
# Clone and configure
git clone https://github.com/l3acon/mad-hatter.git && cd mad-hatter
cp examples/user.creds.yml user.creds.yml   # edit with your passwords
# Copy RHDP YAML tab → rosa.creds.yml

export CONTROLLER_PASSWORD='<aap-admin-password>'
export AAP_MACHINE_CRED_PASSWORD='<machine-cred-password>'
export K8S_AUTH_PASSWORD='<openshift-admin-password>'

# Deploy infrastructure + AAP + OCP-V
ansible-navigator run infra-deploy.yml --tags rosa,aap,ocpv \
  --eei quay.io/matferna/mh-rosa:latest

# Apply CasC
ansible-navigator run casc-deploy.yml --tags snow,apd \
  --eei quay.io/matferna/mh-rosa:latest
```

### Workshop / standalone OCP environment

```bash
# Copy RHDP YAML tab → ocp-v-workshop.creds.yml
# Login to the cluster
oc login ...

# Deploy AAP (if not pre-installed)
ansible-playbook aap-deploy.yml

# Deploy OCP-V operator (if not pre-installed)
ansible-playbook ocpv-deploy.yml

# Deploy CasC (JTs, workflows, inventories, credentials, SNOW)
ansible-playbook workshop-deploy.yml \
  -e snow_instance=https://your-snow.service-now.com \
  -e snow_username=admin \
  -e snow_password='YourPassword'
```

## Playbooks

### `infra-deploy.yml` — Infrastructure Provisioning

| Tags | Description |
|---|---|
| `--tags rosa,aap` | ROSA login + AAP operator |
| `--tags rosa,aap,ocpv` | ROSA + AAP + bare-metal machinepool for OCP-V |
| `--tags aro,aap` | ARO login + AAP operator |
| `--tags aro,aap,clab` | ARO + AAP + ContainerLab hypervisor |

### `casc-deploy.yml` — Configuration as Code

| Tags | Description |
|---|---|
| `--tags snow` | ServiceNow integration (CMDB, ITSM, self-service, compliance) |
| `--tags apd` | OpenShift Virtualization product demos |
| `--tags clab` | ContainerLab multi-vendor network workshop |

### `workshop-deploy.yml` — Workshop CasC

Deploys OCP-V day-2 automation content to pre-provisioned workshop environments.
Parses `ocp-v-workshop.creds.yml` for cluster/AAP credentials. Includes:

- RHEL VM provisioning (DataSource-backed, RHSM registration, dnf install)
- Windows VM provisioning (golden DV clone, WinRM, Chocolatey install)
- KubeVirt dynamic inventories (RHEL + WinRM)
- ServiceNow integration (acknowledge/update catalog requests)
- VM lifecycle (start/stop/restart), snapshots, delete

### `windows-golden-deploy.yml` — Windows Golden Image Pipeline

Builds a Windows Server golden image for OCP-V from an ISO:

1. Uploads the Windows ISO to a CDI DataVolume
2. Builds the autounattend answer ISO (VirtIO drivers + Autounattend.xml + bootstrap)
3. Creates a blank OS DataVolume
4. Boots the installer VM for unattended install

```bash
export OCPV_WIN_AUTOUNATTEND_ADMIN_PASSWORD='YourPassword'
ansible-playbook windows-golden-deploy.yml \
  -e ocpv_win_iso_local_path=~/Downloads/SERVER_EVAL_x64FRE_en-us.iso
```

> **Pre-built golden image:** A pre-built golden image (5.1 GB compressed) is
> maintained by the repo owner. Contact @l3acon for access. Upload with:
> ```bash
> virtctl image-upload dv windows-server-golden --namespace=virt-windows \
>   --size=60Gi --storage-class=<sc> --image-path=~/Downloads/windows-server-golden.img.gz \
>   --force-bind --insecure
> ```

### `portal-deploy.yml` — Self-Service Portal

Deploys the RHAAP Developer Hub (Backstage) on OpenShift via Helm. Requires AAP 2.7+.

```bash
ansible-playbook portal-deploy.yml \
  -e controller_host=https://aap.apps.example.com \
  -e controller_username=admin \
  -e controller_password='YourPassword'
```

### `aap-deploy.yml` — AAP Operator (standalone)

Deploys the AAP operator on any cluster without ROSA/ARO dependencies.

### `ocpv-deploy.yml` — OCP-V Operator

Deploys the OpenShift Virtualization (CNV) operator and HyperConverged CR.

## Roles

| Role | Purpose |
|---|---|
| `aap_operator` | Install AAP operator + manifest injection |
| `ocpv_operator` | Install OCP-V operator + HyperConverged CR |
| `openshift_virtualization_aap` | Full OCP-V CasC for ROSA (JTs, workflows, SNOW, cost optimization) |
| `workshop_aap` | Lightweight OCP-V CasC for workshop environments |
| `workshop_creds` | Parse workshop ResourceClaim YAML for cluster/AAP credentials |
| `rosa_creds` | Parse ROSA ResourceClaim for AWS/cluster credentials |
| `user_creds` | Parse user credentials (AAP password, SSH keys, manifest) |
| `snow` | ServiceNow CMDB/ITSM integration CasC |
| `product_demos` | Ansible Product Demos bootstrap |
| `self-service` | Self-Service Portal (Helm deployment) |
| `install_operator` | Generic OLM operator installer |
| `ao_operator` | Automation Orchestrator operator |

## JT Playbooks

Job template playbooks live in `jt_playbooks/` — launched by AAP, not run directly.

| Directory | Content |
|---|---|
| `jt_playbooks/openshift_virtualization/` | VM create, delete, lifecycle, backup, provision (RHEL + Windows) |
| `jt_playbooks/openshift_virtualization/windows/` | Golden image pipeline, autounattend, VirtIO drivers |
| `jt_playbooks/snow/` | ServiceNow ITSM, CMDB, self-service, catalog deploy |

## Configuration

### Credential files

| File | Source | Used by |
|---|---|---|
| `user.creds.yml` | [examples/user.creds.yml](examples/user.creds.yml) | AAP admin password, SSH keys, RHSM credentials |
| `rosa.creds.yml` | RHDP YAML tab (ROSA) | `infra-deploy.yml --tags rosa` |
| `aro.creds.yml` | RHDP YAML tab (ARO) | `infra-deploy.yml --tags aro` |
| `ocp-v-workshop.creds.yml` | RHDP YAML tab (OCP-V Workshop) | `workshop-deploy.yml` |
| `ocp-mc.creds.yml` | RHDP YAML tab (OCP Multi-Cloud) | `workshop-deploy.yml` |

### Environment variables

| Variable | Description |
|---|---|
| `CONTROLLER_PASSWORD` | AAP admin password |
| `AAP_MACHINE_CRED_PASSWORD` | Machine credential password (Windows complexity: 8+ chars, 3/4 classes) |
| `K8S_AUTH_PASSWORD` | OpenShift admin password |
| `OCPV_WIN_AUTOUNATTEND_ADMIN_PASSWORD` | Windows golden image admin password |

## Execution Environments

Pre-built images:
- `quay.io/matferna/mh-rosa:latest` — ROSA / general OCP-V automation
- `quay.io/matferna/mh-windows:latest` — Windows automation (ansible.windows + pywinrm)

See [execution_environments/README.md](execution_environments/README.md) for build instructions.

## Troubleshooting

**CasC module errors redacted:** Add `-e controller_configuration_credentials_secure_logging=false`

**Portal init CrashLoopBackOff:** OCI plugin pull failure. Check `oc describe pod` — usually missing registry auth. See [roles/self-service/README.md](roles/self-service/README.md#troubleshooting).

**AAP 503 during manifest injection:** Gateway is up before controller API. Wait for `/api/controller/v2/ping/` to return 200.

**Windows golden image build stuck:** Check VM console (`oc console <vm> -n virt-windows`). Common issues: VirtIO drivers not loading in WinPE, disk partitioning errors.

**WinRM connection refused on cloned Windows VMs:** Non-sysprepped clones go through post-clone OOBE with WinRM restart. The playbook includes a 90s settle delay + IP re-probe to handle this.

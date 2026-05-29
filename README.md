# Through the Looking Glass
First it works. Then it documents.

## Beware the Bandersnatch
This is a work in progress.

### AAP version
The `aap_operator` role defaults to **AAP 2.7** (`stable-2.7` operator channel). Override with `-e aap_operator_operator_channel=stable-2.6` for older clusters. Key 2.7 changes this repo accounts for:

- The **platform gateway** is the sole API entry point; direct component API access (`/api/v2/`) is removed.
- The RPM-based installer is retired; only containerized and OpenShift Operator installs are supported.
- Credential discovery and CasC playbooks route through the gateway by default and fall back to the controller route for pre-2.7 clusters.
- The `ansible.platform` collection replaces deprecated `ansible.hub` modules.

### Down the Rabbit Hole
There are two infrastructures this project builds upon. See the individual README's for details.
1. [ROSA](./aws/README.md) - for OpenShift virtualization we deploy a metal AWS instance and configure it for use with ROSA. The `openshift_virtualization_aap` role loads AAP configuration as code for OpenShift Virtualization job templates (using `redhat.openshift_virtualization` and `infra.openshift_virtualization_ops`). Use this for Day 2 demos around OCP and VM management.
1. [ARO](./aro/README.md) - for [CONTAINERlab](https://containerlab.dev/) orchistration and standalone AAP deployments. AAP is deployed on ARO and optionally a containerlab (clab) VM is deployed on Azure to host containerlab virtualized network devices. Use this for AAP for networking use cases and demos.

### ARO playbooks

| Playbook | Description |
|---|---|
| `aro/aap.yml` | Deploy AAP only (no clab, no CasC). Suitable for a fresh ARO cluster. |
| `aro/aap-with-apd.yml` | Deploy AAP + OpenShift Virtualization product demos CasC (no ContainerLab). |
| `aro/clab.yml` | Deploy AAP + ContainerLab + multi-vendor network CasC. |
| `aro/clab-with-apd.yml` | Deploy AAP + ContainerLab + OpenShift Virtualization CasC. |

### Self-Service portal
Currently I run this as an add-on (and stolen from [Hicham](https://github.com/naeemarsalan/aap-self-service-role.git)). The steps required are outlined below.

1. Download and untar plugins to `${project_root}/roles/self-service/files/plugins`
1. Install depends (see below)
1. Set the required variables (see below)
1. Login to openshift using CLI (see below)
1. Run the playbook.

```
ansible-galaxy collection install -r roles/self-service/requirements.yml
oc login --token=sha256~mylongtoken --server=https://api.my-ocp.com:443
ansible-playbook deploy_ssp.yml -e controller_username=admin -e controller_password=SomePassword -e github_token=gh_something -e namespace=self-service -e controller_host=https://my-aap-deployment.example.com
```

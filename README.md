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
There are two infrastructures this project builds upon:
1. **ROSA** - for OpenShift virtualization we deploy a metal AWS instance and configure it for use with ROSA. The `openshift_virtualization_aap` role loads AAP configuration as code for OpenShift Virtualization job templates (using `redhat.openshift_virtualization` and `infra.openshift_virtualization_ops`). Use this for Day 2 demos around OCP and VM management.
1. **ARO** - for [CONTAINERlab](https://containerlab.dev/) orchestration and standalone AAP deployments. AAP is deployed on ARO and optionally a containerlab (clab) VM is deployed on Azure to host containerlab virtualized network devices. Use this for AAP for networking use cases and demos.

---

## ARO (`deploy_aro.yml`)

Use `--tags` to select which components to deploy:

| Tags | Description |
|---|---|
| `--tags aap` | Deploy AAP only (operator + manifest injection). |
| `--tags aap,clab` | AAP + ContainerLab + multi-vendor network CasC. |
| `--tags aap,apd` | AAP + OpenShift Virtualization product demos CasC. |
| `--tags aap,clab,apd` | AAP + ContainerLab + product demos CasC. |
| _(no tags)_ | Deploy everything. |

### ARO setup
1. Order infrastructure — compatible with [this RHDP CI](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/azure-gpte.open-environment-aro4-sub.prod&utm_source=webapp&utm_medium=share-link).
1. Once RHDP deploys ARO go to the YAML tab and copy its contents to a file named `aro.creds.yml` in the root of this project.
1. Configure `user.creds.yml` (see [user.creds.yml](#usercredsyml)).
1. Configure navigator for file/volume mounts (see [ansible-navigator config](#ansible-navigator-config)).
1. Run the playbook.

#### AAP-only deployment
```
ansible-navigator run deploy_aro.yml --tags aap --eei quay.io/matferna/mh-aro:latest -e ansible_ssh_private_key_file=/root/keys/my_priv_key
```

#### AAP + ContainerLab
```
ansible-navigator run deploy_aro.yml --tags aap,clab --eei quay.io/matferna/mh-aro:latest -e ansible_ssh_private_key_file=/root/keys/my_priv_key
```

See [aro_creds](roles/aro_creds/tasks/main.yml) and [user_creds](roles/user_creds/tasks/main.yml) for more details on credential loading.

Here's how I _actually_ run it:
```
ansible-navigator run deploy_aro.yml --tags aap,clab --eei quay.io/matferna/mh-aro:latest -e controller_configuration_credentials_secure_logging=false --senv K8S_AUTH_PASSWORD=<pass> --senv AAP_MACHINE_CRED_PASSWORD="<p@Ss>" --senv CONTROLLER_PASSWORD=<pass> -e ansible_ssh_private_key_file=/root/keys/mounted_key_name -e user_creds_ansible_ssh_private_key_file=/root/keys/mounted_key_name -e user_creds_ansible_ssh_pub_key_file=/root/keys/mounted_pub.pub
```

---

## ROSA (`deploy_rosa.yml`)

Use `--tags` to select which components to deploy:

| Tags | Description |
|---|---|
| `--tags aap` | Deploy AAP only. |
| `--tags aap,ocpv` | AAP + bare-metal machinepool for OpenShift Virtualization. |
| `--tags aap,apd` | AAP + OpenShift Virtualization product demos CasC. |
| `--tags aap,ocpv,apd` | AAP + bare-metal node + product demos CasC. |
| _(no tags)_ | Deploy everything. |

### ROSA setup
1. Order infrastructure — compatible with [this RHDP CI](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/sandboxes-gpte.rosa.prod&utm_source=webapp&utm_medium=share-link).
1. Once RHDP deploys ROSA go to the YAML tab and copy its contents to a file named `rosa.creds.yml` in the root of this project.
1. Configure navigator for file/volume mounts (see [ansible-navigator config](#ansible-navigator-config)).
1. Run the playbook.

```
ansible-navigator run deploy_rosa.yml --eei quay.io/matferna/mh-rosa:latest --senv K8S_AUTH_PASSWORD=Curiouser&Curiouser --senv AAP_MACHINE_CRED_PASSWORD="Cur1ouser&Cur1ouser" --senv CONTROLLER_PASSWORD=Curiouser&Curiouser
```

See [rosa_creds](roles/rosa_creds/tasks/main.yml) and [user_creds](roles/user_creds/tasks/main.yml) for more details on credential loading.

### EE image build (`execution_environments/rosa/build.sh`)

Shared prep lives in `execution_environments/utils/ee_build_prep.sh` (sourced by each `build.sh`).

**Automation Hub:** credentials are passed as `podman` build args for `ansible-builder`. If `ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN` and `ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN` are **not** set, the script reads the first `token` under a `[galaxy_server.*]` section from **`/etc/ansible/ansible.cfg`** (override with `SYSTEM_ANSIBLE_CFG`).

**registry.redhat.io:** if `podman login --get-login registry.redhat.io` does not already return a user, the script runs non-interactive login using **`REGISTRY_REDHAT_IO_USER`** (or **`REGISTRY_REDHAT_IO_USERNAME`**) and **`REGISTRY_REDHAT_IO_PASSWORD`** (via `--password-stdin`). Use your Red Hat registry or service-account credentials from the [container registry](https://access.redhat.com/terms-based-registry/) flow. Otherwise run `podman login registry.redhat.io` once on the host before building.

**quay.io:** same pattern for pushes to `quay.io` (this build tags `quay.io/matferna/mh-*`). If `podman login --get-login quay.io` is empty, set **`QUAY_IO_USER`** (or **`QUAY_IO_USERNAME`**) and **`QUAY_IO_PASSWORD`**, or run `podman login quay.io` first.

Optional: **`MERGE_REPO_ANSIBLE_CFG=1`** prepends the repository root `[defaults]` block into the EE `ansible.cfg` for that build only (restored after the script exits).

```bash
cd execution_environments/rosa
export REGISTRY_REDHAT_IO_USER='your-registry-username'
export REGISTRY_REDHAT_IO_PASSWORD='your-registry-token'
export QUAY_IO_USER='your-quay-username'
export QUAY_IO_PASSWORD='your-quay-token-or-password'
./build.sh
# or: MERGE_REPO_ANSIBLE_CFG=1 SYSTEM_ANSIBLE_CFG=/etc/ansible/ansible.cfg ./build.sh
```

The same behavior exists under `execution_environments/aro/build.sh`.

**If `podman run quay.io/matferna/mh-rosa:latest` or ansible-navigator fails** with *no image found in manifest list for architecture amd64*, the registry tag was probably an **empty manifest list** (older `build.sh` used `podman manifest create` + `--manifest` incorrectly). Rebuild with the current `build.sh` (single-arch `-t` + `podman push`) or run a locally tagged image: `podman images` then `podman run --rm <image_id> ansible-playbook --version`.

**Validate collections inside a built image:** `execution_environments/utils/validate_ee_collections.sh quay.io/matferna/mh-rosa:latest /path/to/ee-dir` (second arg defaults to `../rosa` relative to the script). Uses `podman run` + `ansible-galaxy collection list` and checks names from that EE's `requirements.yml`.

---

## Common reference

### user.creds.yml
At a minimum the following variables are required in this file:
```yaml
aap_operator_chatbot_token: <some token>
openshift_admin_password: <k8s password>
```
See [user_creds](roles/user_creds/tasks/main.yml) for more details on credential loading.

### ansible-navigator config
I use volume-mounts for ssh keys and manifest files. Here is an example navigator config:
```yaml
ansible-navigator:
  execution-environment:
    pull:
      policy: missing
    volume-mounts:
      - src: "/home/user/keys"
        dest: "/root/keys"
        options: "Z"
      - src: "/home/user/manifests"
        dest: "/root/manifests"
        options: "Z"
    environment-variables:
      pass:
        - AAP_MACHINE_CRED_PASSWORD
        - CONTROLLER_PASSWORD
      set:
        K8S_AUTH_PASSWORD: "Curiouser&Curiouser"
```

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

### Troubleshooting
Add debugging flag for Config as Code collections:
```
-e controller_configuration_credentials_secure_logging=false
```

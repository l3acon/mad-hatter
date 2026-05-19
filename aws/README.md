# ROSA

## Yellow brick road
This project is oriented around AAP and OpenShift virtualization. We deploy a metal AWS instance and configure it for use with ROSA. The `openshift_virtualization_aap` role applies controller configuration as code for job templates backed by `redhat.openshift_virtualization` and `infra.openshift_virtualization_ops`. Use this for Day 2 demos around OCP and VM management. Build an execution environment from `execution_environments/rosa/` so the controller job templates have the required collections.

### EE image build (`execution_environments/rosa/build.sh`)

Shared prep lives in `execution_environments/utils/ee_build_prep.sh` (sourced by each `build.sh`).

**Automation Hub:** credentials are passed as `podman` build args for `ansible-builder`. If `ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN` and `ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN` are **not** set, the script reads the first `token` under a `[galaxy_server.*]` section from **`/etc/ansible/ansible.cfg`** (override with `SYSTEM_ANSIBLE_CFG`).

**registry.redhat.io:** if `podman login --get-login registry.redhat.io` does not already return a user, the script runs non-interactive login using **`REGISTRY_REDHAT_IO_USER`** (or **`REGISTRY_REDHAT_IO_USERNAME`**) and **`REGISTRY_REDHAT_IO_PASSWORD`** (via `--password-stdin`). Use your Red Hat registry or service-account credentials from the [container registry](https://access.redhat.com/terms-based-registry/) flow. Otherwise run `podman login registry.redhat.io` once on the host before building.

**quay.io:** same pattern for pushes to `quay.io` (this build tags `quay.io/matferna/mh-*`). If `podman login --get-login quay.io` is empty, set **`QUAY_IO_USER`** (or **`QUAY_IO_USERNAME`**) and **`QUAY_IO_PASSWORD`**, or run `podman login quay.io` first.

Optional: **`MERGE_REPO_ANSIBLE_CFG=1`** prepends the repository root `[defaults]` block into the EE `ansible.cfg` for that build only (restored after the script exits).

Example:

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

**Validate collections inside a built image:** `execution_environments/utils/validate_ee_collections.sh quay.io/matferna/mh-rosa:latest /path/to/ee-dir` (second arg defaults to `../rosa` relative to the script). Uses `podman run` + `ansible-galaxy collection list` and checks names from that EE’s `requirements.yml`.

## Begin at the Beginning
1. Order underlying infrastructure, the code here is compatible with this [this RHDP CI](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/sandboxes-gpte.rosa.prod&utm_source=webapp&utm_medium=share-link).
1. Once RHDP deploys ROSA go to the YAML tab and copy its contents to a file named `aws.creds.yml` in the root of this project.
1. Configure navigator for file/volume mouns (see [ansible-navigator config](#ansible-navigator-config))
1. Run the play (se below)

```
# be in the project root directory
ansible-navigator run aws/ocpv.yml --eei quay.io/matferna/mh-rosa:latest --senv K8S_AUTH_PASSWORD=Curiouser&Curiouser --senv AAP_MACHINE_CRED_PASSWORD="Cur1ouser&Cur1ouser" --senv CONTROLLER_PASSWORD=Curiouser&Curiouser
```
See [rosa_creds](../roles/rosa_creds/tasks/main.yml) and [user_creds](../roles/user_creds/tasks/main.yml) for more details on credential loading.

## ansible-navigator config
I use volume-mounts for ssh keys and manifest files.  Here is an example navigator config:
```
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

Alternatively, vars can be passed via CLI options:
```
ansible-navigator run aws/ocpv.yml --eei  quay.io/matferna/mh-rosa:latest --senv K8S_AUTH_PASSWORD=Curiouser&Curiouser --senv AAP_MACHINE_CRED_PASSWORD="Cur1ouser&Cur1ouser!" --senv CONTROLLER_PASSWORD=Curiouser&Curiouser -e ansible_ssh_private_key_file=/root/keys/my_priv_key
```

### Troubleshooting
Add debugging flag for Config as Code collections:
```
 -e controller_configuration_credentials_secure_logging=false
`

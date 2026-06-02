# Windows execution environment (`mh-windows`)

Builds **`quay.io/matferna/mh-windows:<date>`** and **`quay.io/matferna/mh-windows:latest`** using [ansible-builder](https://ansible.readthedocs.io/projects/ansible-builder/) and Podman.

- **Base image:** `quay.io/matferna/mh-rosa:latest` (public pull; no `registry.redhat.io` login required for the base layer).
- **Automation Hub:** `ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN` and `ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN` (or a token in `/etc/ansible/ansible.cfg` under `[galaxy_server.*]`).
- **Quay publish:** `podman login quay.io`, then run `./build.sh`. To build only: `SKIP_QUAY_PUSH=1 ./build.sh`.
- **CI:** GitHub Actions workflow **`.github/workflows/ee-build.yml`** (dispatch `windows`, or auto-detected on push to `main`) — set secrets **`QUAY_IO_USERNAME`**, **`QUAY_IO_PASSWORD`**, **`AUTOMATION_HUB_TOKEN`**.

After publishing, refresh the controller execution environment (or bump the image reference) so automation pulls the new digest.

### Workflow jobs fail with Kubernetes `401 Unauthorized`

The **OpenShift Credential** on the controller must carry a current **API URL** and **bearer token**. If your local `oc` session is valid but controller jobs are not, refresh the credential from the same machine:

```bash
oc login …   # same cluster the controller should automate
ansible-playbook playbooks/openshift_virtualization/aap_sync_openshift_credential_from_oc.yml
```

Then re-run **OpenShift Virtualization | Provision Windows VM and install package**.

### Post-install job: `ImagePullBackOff` / `Error creating pod` on the execution node

The **Chocolatey** job template uses the **Windows EE** (`quay.io/matferna/mh-windows:latest` by default). If that image is **private** on Quay or your mesh nodes have **no pull secret**, the receptor/worker fails before Ansible runs (controller shows `Unexpected empty line encountered during worker stream` and `ImagePullBackOff` in the job traceback).

**Mitigations:** publish `mh-windows` as a **public** Quay repo, **podman login** / **imagePullSecret** on the automation execution namespace (or hybrid cloud credentials per your platform docs), or override **`openshift_virt_aap_ee_windows_image`** in extra vars before CasC to an image your cluster can pull, then re-run **`aap_rollout_casc.yml`**.

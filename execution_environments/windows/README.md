# Windows execution environment (`mh-windows`)

Builds **`quay.io/matferna/mh-windows:<date>`** and **`quay.io/matferna/mh-windows:latest`** using [ansible-builder](https://ansible.readthedocs.io/projects/ansible-builder/) and Podman.

- **Base image:** `quay.io/matferna/mh-rosa:latest` (public pull; no `registry.redhat.io` login required for the base layer).
- **Automation Hub:** `ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN` and `ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN` (or a token in `/etc/ansible/ansible.cfg` under `[galaxy_server.*]`).
- **Quay publish:** `podman login quay.io`, then run `./build.sh`. To build only: `SKIP_QUAY_PUSH=1 ./build.sh`.
- **CI:** GitHub Actions workflow **`.github/workflows/windows-ee.yml`** (`workflow_dispatch`) — set secrets **`QUAY_IO_USERNAME`**, **`QUAY_IO_PASSWORD`**, **`AUTOMATION_HUB_TOKEN`**.

After publishing, refresh the controller execution environment (or bump the image reference) so automation pulls the new digest.

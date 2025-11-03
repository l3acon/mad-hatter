# ARO

## Begin at the Beginning
1. Order underlying infrastructure, the playbooks here (`{{project_root}}/aro`) is compatible with this [this RHDP CI](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/azure-gpte.open-environment-aro4-sub.prod&utm_source=webapp&utm_medium=share-link).
1. Configure navigator for file/volume mouns (see [ansible-navigator config](#ansible-navigator-config))
1. Run the play

```
# be in the project root directory
ansible-navigator run aro/clab.yml --eei  quay.io/matferna/mh-aro:latest -e ansible_ssh_private_key_file=/root/keys/my_priv_key
```

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
ansible-navigator run aro/clab.yml --eei  quay.io/matferna/mh-aro:latest --senv K8S_AUTH_PASSWORD=Curiouser&Curiouser --senv AAP_MACHINE_CRED_PASSWORD="Cur1ouser&Cur1ouser!" --senv CONTROLLER_PASSWORD=Curiouser&Curiouser -e ansible_ssh_private_key_file=/root/keys/my_priv_key
```

See [aro_creds](../roles/aro_creds/tasks/main.yml) for more credential loading details.

### Troubleshooting
Add debugging flag for Config as Code collections:
```
 -e controller_configuration_credentials_secure_logging=false
```

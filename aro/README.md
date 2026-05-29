# ARO

## Playbooks

| Playbook | What it does |
|---|---|
| `aro/aap.yml` | Deploy **AAP only** on ARO. No ContainerLab, no CasC — just the operator, CR, and manifest injection. |
| `aro/clab.yml` | Deploy AAP + ContainerLab + multi-vendor network workshop CasC. |
| `aro/clab-with-apd.yml` | Deploy AAP + ContainerLab + OpenShift Virtualization CasC. |

The `aap_operator` role defaults to the **`stable-2.7`** operator channel. Override with `-e aap_operator_operator_channel=stable-2.6` if needed.

## Begin at the Beginning
1. Order underlying infrastructure, the playbooks here (`{{project_root}}/aro`) is compatible with this [this RHDP CI](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/azure-gpte.open-environment-aro4-sub.prod&utm_source=webapp&utm_medium=share-link).
1. Once RHDP deploys ARO go to the YAML tab and copy its contents to a file named `aro.creds.yml` in the root of this project.
1. Configure `user.creds.yml` file at the root of this project (see [user.creds.yml](#user.creds.yml))
1. Configure navigator for file/volume mounts (see [ansible-navigator config](#ansible-navigator-config))
1. Run the play

### AAP-only deployment
```
# be in the project root directory
ansible-navigator run aro/aap.yml --eei quay.io/matferna/mh-aro:latest -e ansible_ssh_private_key_file=/root/keys/my_priv_key
```

### AAP + ContainerLab
```
# be in the project root directory
ansible-navigator run aro/clab.yml --eei quay.io/matferna/mh-aro:latest -e ansible_ssh_private_key_file=/root/keys/my_priv_key
```
See [aro_creds](../roles/aro_creds/tasks/main.yml) and [user_creds](../roles/user_creds/tasks/main.yml) for more details on credential loading.

## user.creds.yml
At a minimum the following variables are required in this file.
```
aap_operator_chatbot_token: <some token>
openshift_admin_password: <k8s password>
```
See [user_creds](../roles/user_creds/tasks/main.yml) for more details on credential loading.

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


Here's how I _actually_ run it:
```
ansible-navigator run aro/clab.yml --eei quay.io/matferna/mh-aro:latest -e controller_configuration_credentials_secure_logging=false --senv K8S_AUTH_PASSWORD=<pass> --senv AAP_MACHINE_CRED_PASSWORD="<p@Ss>" --senv CONTROLLER_PASSWORD=<pass> -e ansible_ssh_private_key_file=/root/keys/mounted_key_name -e user_creds_ansible_ssh_private_key_file=/root/keys/mounted_key_name -e user_creds_ansible_ssh_pub_key_file=/root/keys/mounted_pub.pub
```


### Troubleshooting
Add debugging flag for Config as Code collections:
```
 -e controller_configuration_credentials_secure_logging=false
```

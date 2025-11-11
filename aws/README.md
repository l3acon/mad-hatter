# ROSA

## Yellow brick road
This project is oriented around AAP and OpenShift virtualization. We deploy a metal AWS instance and configure it for use with ROSA. [APD](github.com/ansible/product-demos) is used for AAP content. Use this for Day 2 demos around OCP and VM management.

## Begin at the Beginning
1. Order underlying infrastructure, the code here is compatible with this [this RHDP CI](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/sandboxes-gpte.rosa.prod&utm_source=webapp&utm_medium=share-link).
1. Wait for RHDP to provision then go to the YAML tab, copy its contents to a file named `aws.creds.yml` in the root of this project.
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

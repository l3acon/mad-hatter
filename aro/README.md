# ARO

## Begin at the Beginning
1. Order underlying infrastructure, the code here is compatible with this [this RHDP CI](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/azure-gpte.open-environment-aro4-sub.prod&utm_source=webapp&utm_medium=share-link).
1. Create a file called `aro.creds` in the root of this project, paste raw "info" text from demo platform.
1. Add additional variables in the same `aro.creds` file (see playbooks for all available/required vars).
1. Run a play

```
# be in the project root directory
ansible-navigator run aro/clab.yml --eei  quay.io/matferna/mh-aro:latest -e ansible_ssh_private_key_file=~/keys/the_one_ring -e controller_configuration_credentials_secure_logging=false
```

### Troubleshooting
Add debuging flag for Config as Code collections:
```
 -e controller_configuration_credentials_secure_logging=false
```

## ansible-navigator config

Here is an example navigator config:
```
ansible-navigator:
  execution-environment:
    pull:
      policy: missing
    volume-mounts:
      - src: "/home/matt/keys"
        dest: "/root/keys"
        options: "Z"
      - src: "/home/matt/manifests"
        dest: "/root/manifests"
        options: "Z"
```


## User provided variables
Add the following to the RHDP provided credentials, replacing the nonsense.
```
OPENSHIFT_ADMIN_PASSWORD: Curiouser&Curiouser
AAP_ADMIN_PASSWORD: Curiouser&Curiouser
AAP_MANIFEST_PATH: /Curiouser/Curiouser/manifest.zip
AAP_MACHINE_CRED_PASSWORD: Curiouser&Curiouser

# Some private key, to be used as AAP Machine Credential
-----BEGIN OPENSSH PRIVATE KEY-----
SWYgSSBoYWQgYSB3b3JsZCBvZiBteSBvd24sIGV2ZXJ5dGhpbmcgd291bGQgYmUgbm9uc2Vuc2Uu
IE5vdGhpbmcgd291bGQgYmUgd2hhdCBpdCBpcywgYmVjYXVzZSBldmVyeXRoaW5nIHdvdWxkIGJl
IHdoYXQgaXQgaXNuJ3QuIEFuZCBjb250cmFyaXdpc2UsIHdoYXQgaXQgaXMsIGl0IHdvdWxkbid0
IGJlLiBBbmQgd2hhdCBpdCB3b3VsZG4ndCBiZSwgaXQgd291bGQuIFlvdSBzZWU/Cg==
-----END OPENSSH PRIVATE KEY-----

<...COPY PASTA from RHDP CREDS PAGE...>
```
See [aro_creds](../roles/aro_creds/tasks/main.yml) for more credential loading details.

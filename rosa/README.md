# ROSA

## Begin at the Beginning
1. Order underlying infrastructure, the code here is compatible with this [this RHDP CI](https://catalog.demo.redhat.com/catalog?item=babylon-catalog-prod/sandboxes-gpte.rosa.prod&utm_source=webapp&utm_medium=share-link).
1. Create a file called `rosa.creds` in the root of this project, paste raw "info" text from demo platform.
1. Add additional variables in the same `rosa.creds` file (see playbooks for all available/required vars).
1. Run a play
```
# be in the root directory
ansible-playbook rosa/ocpv.yml
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
See [rosa_creds](../roles/rosa_creds/tasks/main.yml) for more details credential loading details.

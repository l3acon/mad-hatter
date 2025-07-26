# Through the Looking Glass
First it works. Then it documents.

## Beware the Bandersnatch
This is a work in progress.

### Begin at the Beginning
1. Create a file called `rhdp.creds` in the root of this project, paste raw "info" text from demo platform.
1. Add additional variables in the same `rhdp.creds` file (see playbooks for all available/required vars). 
1. Run a play
```
ansible-playbook aro/apd.yml
```

### User provided variables
Add the following to the RHDP provided credentials, replacing the nonsense. 
```
OPENSHIFT_ADMIN_PASSWORD: Curiouser&Curiouser
AAP_ADMIN_PASSWORD: Curiouser&Curiouser
AAP_MANIFEST_PATH: /Curiouser/Curiouser/manifest.zip
AAP_MACHINE_CRED_PASSWORD: Curiouser&Curiouser
-----BEGIN OPENSSH PRIVATE KEY-----
SWYgSSBoYWQgYSB3b3JsZCBvZiBteSBvd24sIGV2ZXJ5dGhpbmcgd291bGQgYmUgbm9uc2Vuc2Uu
IE5vdGhpbmcgd291bGQgYmUgd2hhdCBpdCBpcywgYmVjYXVzZSBldmVyeXRoaW5nIHdvdWxkIGJl
IHdoYXQgaXQgaXNuJ3QuIEFuZCBjb250cmFyaXdpc2UsIHdoYXQgaXQgaXMsIGl0IHdvdWxkbid0
IGJlLiBBbmQgd2hhdCBpdCB3b3VsZG4ndCBiZSwgaXQgd291bGQuIFlvdSBzZWU/Cg==
-----END OPENSSH PRIVATE KEY-----
```

## We're all mad here
This project aims to do better, execution should flow quickly and seamlessly. Troubleshooting should also be as seamless and easy as possible.

Relevant metrics:
```
# vanilla deployment
time ansible-playbook rosa/apd.yml
...<play output>
13:16.97 total

```


```
# post-deploment, ideally ansible is doing nothing
time ansible-playbook rosa/apd.yml
...<play output>
42.597 total

```

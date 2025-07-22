# Through the Looking Glass
First it works. Then it documents.

## Beware the Bandersnatch
Ideally we have a RHDP.creds file that is just copy/pasta of credentials...

Currently set these vars:
```
ROSA_BASTION_HOST=bastion.something.com
ROSA_BASTION_PASSWORD=<some-pass>
OCP_CLUSTER_ADMIN_PASSWORD=<some-pass>
AAP_ADMIN_PASSWORD=<some-pass> 
AAP_MANIFEST_PATH=~/Downloads/some-manifest.zip
```

## We're all mad here
This project aims to do better, execution should flow quickly and seamlessly. Troubleshooting should also be as seamelss and easy as possible.

Relevant metrics:
```
# vanilla deployment
time ansible-playbook playbooks/rosa.yml
...<play output>
13:16.97 total

```


```
# post-deploment, ideally ansible is doing nothing
time ansible-playbook playbooks/rosa.yml
...<play output>
42.597 total

```

# Through the Looking Glass
First it works. Then it documents.

## Beware the Bandersnatch
This is a work in progress.

### Begin at the Beginning
1. Create a file called `rhdp.creds` in the root of this project, paste the credentials from RHDP.
1. Set these additional variables either as BASH environment variables or within the same `rhdp.creds` file:
```
OPENSHIFT_ADMIN_PASS=<some-pass>
AAP_ADMIN_PASSWORD=<some-pass> 
AAP_MANIFEST_PATH=~/Downloads/some-manifest.zip
```
1. Run a play
```
ansible-playbook playbooks/rosa.yml
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

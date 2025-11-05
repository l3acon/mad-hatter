# Through the Looking Glass
First it works. Then it documents.

## Beware the Bandersnatch
This is a work in progress.

### Down the Rabbit Hole
There are two infrastructures this project builds upon. See the individual README's for details.
1. [ROSA](./aws/README.md) - for OpenShift virtualization we deploy a metal AWS instance and configure it for use with ROSA. [APD](github.com/ansible/product-demos) is used for AAP content. Use this for Day 2 demos around OCP and VM management.
1. [ARO](./aro/README.md) - for [CONTAINERlab](https://containerlab.dev/) orchistration. AAP is deployed on ARO and a containerlab (clab) VM is deployed on Azure to host containerlab virtualized network devices. Use this for AAP for networking use cases and demos.

### Self-Service portal
Currently I run this as an add-on (and stolen from [Hicham](https://github.com/naeemarsalan/aap-self-service-role.git)). The steps required are outlined below.

1. Download and untar plugins to `${project_root}/roles/self-service/files/plugins`
1. Install depends (see below)
1. Set the required variables (see below)
1. Login to openshift using CLI (see below)
1. Run the playbook.

```
ansible-galaxy collection install -r roles/self-service/requirements.yml
oc login --token=sha256~mylongtoken --server=https://api.my-ocp.com:443
ansible-playbook deploy_ssp.yml -e controller_username=admin -e controller_password=SomePassword -e github_token=gh_something -e namespace=self-service -e controller_host=https://my-aap-deployment.example.com
```

# Through the Looking Glass
First it works. Then it documents.

## Beware the Bandersnatch
This is a work in progress.

### Down the Rabbit Hole
There are two infrastructures this project builds upon. See the individual README's for details.
1. [ROSA](./aws/README.md) - for OpenShift virtualization we deploy a metal AWS instance and configure it for use with ROSA. [APD](github.com/ansible/product-demos) is used for AAP content. Use this for Day 2 demos around OCP and VM management.
1. [ARO](./aro/README.md) - for [CONTAINERlab](https://containerlab.dev/) orchistration. AAP is deployed on ARO and a containerlab (clab) VM is deployed on Azure to host containerlab virtualized network devices. Use this for AAP for networking use cases and demos.

# Through the Looking Glass
First it works. Then it documents.

## Beware the Bandersnatch
This is a work in progress.

### Down the Rabbit Hole
This project builds off the following projects:
1. [ROSA](./rosa/README.md)
1. [ARO](./aro/README.md)

## We're all mad here
This project aims to optimize for user experience. Both execution should troubleshooting should be as seamless and easy as possible. Long runningg tasks should be sarted and polled to allow for reasonalbe time management.

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

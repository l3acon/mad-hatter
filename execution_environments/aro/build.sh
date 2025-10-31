#!/bin/bash
set -e

IMAGE=quay.io/matferna/mh-aro

echo "starting to build ${IMAGE} at $(date)"

_tag=$(date +%Y%m%d)
IMAGE_TAG="quay.io/matferna/mh-aro:${_tag}"


if [[ -z $ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN || -z $ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN ]]
then
    echo "A valid Automation Hub token is required, Set the following environment variables before continuing"
    echo "export ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN=<token>"
    echo "export ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN=<token>"
    exit 1
fi

# log in to pull the base EE image
if ! podman login --get-login registry.redhat.io > /dev/null
then
    echo "Run 'podman login registry.redhat.io' before continuing"
    exit 1
fi

# create EE definition
rm -rf ./context/*
ansible-builder create \
    --file execution-environment.yml \
    --context ./context \
    -v 3 | tee ansible-builder.log

# remove existing manifest if present
podman manifest rm ${IMAGE_TAG}

# create manifest for EE image
podman manifest create ${IMAGE_TAG}

# for the openshift-clients RPM, microdnf doesn't support URL-based installs
# and HTTP doesn't support file globs for GETs, use multiple steps to determine
# the correct RPM URL for each machine architecture
for arch in amd64 arm64
do
    _baseurl=https://mirror.openshift.com/pub/openshift-v4/${arch}/dependencies/rpms/4.18-el9-beta/
    _rpm=$(curl -s ${_baseurl} | grep openshift-clients-4 | grep href | cut -d\" -f2)

    # build EE for multiple architectures from the EE context
    pushd ./context/ > /dev/null
    podman build --platform linux/${arch} \
      --build-arg ANSIBLE_GALAXY_SERVER_CERTIFIED_TOKEN \
      --build-arg ANSIBLE_GALAXY_SERVER_VALIDATED_TOKEN \
      --build-arg OPENSHIFT_CLIENT_RPM="${_baseurl}${_rpm}" \
      --manifest ${IMAGE_TAG} . \
      | tee podman-build-${arch}.log
    popd > /dev/null
done

echo "Built ${IMAGE_TAG}"

# inspect manifest content
podman manifest inspect ${IMAGE_TAG}

# tag manifest as latest
podman tag ${IMAGE_TAG} ${IMAGE}:latest

# push all manifest content to repository
# using --all is important here, it pushes all content and not
# just the native platform content
podman manifest push --all ${IMAGE_TAG}
podman manifest push --all ${IMAGE}:latest

echo "build ${IMAGE} finished $(date), duration of $SECONDS seconds"

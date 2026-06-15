# RFE: Expose Init Container Resource Requirements in AnsibleLightspeed CR

## Summary

The `AnsibleLightspeed` Custom Resource should allow operators to configure resource requests and limits for init containers, specifically `configure-combined-ca-bundle`, in the same way that `spec.api.resource_requirements` allows configuration of the main `model-api` container.

## Component

- **Product:** Ansible Automation Platform
- **Component:** ansible-lightspeed-operator
- **Version Affected:** AAP 2.6 (operator version 4.7.x)

## Problem Statement

The `AnsibleLightspeed` CR exposes `spec.api.resource_requirements` to configure resource requests and limits for the main application container (`model-api`). However, the init container `configure-combined-ca-bundle` has hardcoded resource requests of 5Gi memory and 500m CPU, with no mechanism for customers to override these values.

Because Kubernetes uses the maximum of (largest init container request) and (sum of all regular container requests) when scheduling a pod, the hardcoded 5Gi memory request on the init container effectively sets a floor on the schedulable memory for the entire pod — regardless of what the customer configures via `spec.api.resource_requirements`.

Additionally, any direct modification to the Deployment is reverted by the operator on its next reconciliation cycle, leaving customers with no viable workaround.

## Impact

### Scheduling failures on resource-constrained clusters

Many customers run AAP on clusters with limited node capacity — particularly in edge deployments, development/test environments, or cost-optimized cloud configurations (e.g., ROSA with minimal worker nodes). A 5Gi memory request for an init container that performs a simple CA bundle configuration is disproportionate to the actual work being performed, and can prevent the pod from scheduling entirely.

### Cascading operator failures

When the lightspeed pod cannot schedule, the lightspeed operator enters a failed reconciliation loop (stuck at the "Check for Model API Pod" task). This failure propagates to the parent `AnsibleAutomationPlatform` operator, which also reports reconciliation failures. This creates noisy alerts and masks other legitimate issues.

### No customer workaround

- Patching the Deployment directly is reverted by the operator on the next reconciliation.
- The `spec.api.resource_requirements` field only applies to the main container, not init containers.
- The only permanent workaround is disabling lightspeed entirely (`disabled: true`), which removes functionality customers have licensed.

## Observed Behavior (Reproduction)

1. Deploy AAP 2.6 on a cluster where no single node has 5Gi of free allocatable memory.
2. Enable lightspeed (default configuration).
3. Observe `aap-lightspeed-api` pod stuck in `Pending` with event:
   ```
   0/N nodes are available: N Insufficient memory.
   ```
4. Inspect the pod spec — init container `configure-combined-ca-bundle` requests 5000Mi.
5. Attempt to set `spec.api.resource_requirements` on the CR with lower values — scheduling still fails because init container resources are unchanged.
6. Patch deployment directly — operator reverts the change.

## Requested Enhancement

Add a field to the `AnsibleLightspeed` CR spec to allow customers to configure init container resource requirements. Suggested API:

```yaml
apiVersion: lightspeed.ansible.com/v1alpha1
kind: AnsibleLightspeed
metadata:
  name: aap-lightspeed
spec:
  api:
    resource_requirements:
      requests:
        cpu: "500m"
        memory: "2Gi"
      limits:
        cpu: "1500m"
        memory: "4Gi"
    init_container_resource_requirements:
      requests:
        cpu: "100m"
        memory: "256Mi"
      limits:
        cpu: "500m"
        memory: "512Mi"
```

Alternatively, the operator could simply inherit the values from `spec.api.resource_requirements` for init containers, or set sensible defaults proportional to the actual work performed (the CA bundle configuration task requires minimal resources).

## Business Justification

1. **Cost efficiency** — Customers should not be forced to provision additional worker nodes solely to satisfy an inflated init container memory request. On cloud platforms (AWS, Azure, GCP), this translates directly to increased infrastructure costs.

2. **Operational flexibility** — Customers have varying cluster topologies and workload profiles. Hardcoded resource values assume a one-size-fits-all deployment model that does not reflect real-world environments.

3. **Consistency** — Other AAP components (controller, EDA, gateway) allow resource customization. The lightspeed init container is an outlier that breaks customer expectations of uniform configurability.

4. **Availability** — The inability to schedule lightspeed should not cause cascading operator failures that affect the health reporting of the entire AAP platform.

## Environment Details

- **Platform:** ROSA (Red Hat OpenShift Service on AWS)
- **Cluster:** 3 worker nodes, ~14.5Gi allocatable memory per node
- **AAP Version:** 2.6.20260422
- **Operator Version:** 4.7.12

# GKE Service Extensions

Deploy Google Kubernetes Engine with Service Extensions.

## Prerequisites

- Google Cloud Project with billing enabled
- Terraform >= 1.0
- `kubectl` CLI tool
- `gcloud` CLI authenticated
- Required APIs will be enabled automatically

## Deployment

### 1. Initialize

```bash
cd gke/
terraform init
```

### 2. Configure Variables

Create `terraform.tfvars`:

```hcl
project_id = "your-project-id"
region     = "us-central1"  # Optional: change region
```

### 3. Deploy Infrastructure

```bash
# Review changes
terraform plan -var-file="terraform.tfvars"

# Deploy infrastructure
terraform apply -var-file="terraform.tfvars"
```

### 4. **CRITICAL**: Attach NEGs Manually

After Terraform completes, you **must** run the NEG attachment script:

```bash
# This step is required - NEGs won't work without it
./attach_negs.sh your-project-id region
```

**Why this step is needed:**
- **Regional Clusters**: In regional clusters, GKE creates NEGs in multiple zones dynamically based on node scheduling.
- **Race Conditions**: Terraform's `data` sources require known zones and existing resources at plan time, which is difficult to guarantee with dynamic GKE provisioning.
- **Robustness**: This script dynamically discovers the created NEGs across all zones and attaches them, ensuring reliable connectivity regardless of where pods are scheduled.


## What Gets Created

### Kubernetes Infrastructure
- **GKE Cluster**: Regional cluster with 2 nodes
- **Node Pool**: e2-medium instances with auto-scaling
- **VPC-native networking** with IP aliasing
- **Workload Identity** for secure pod authentication

### Networking
- **VPC Network**: `service-extensions-vpc-gke`
- **Subnets**: Main subnet + secondary ranges for pods/services
- **Firewall Rules**: Kubernetes API and node communication

### Load Balancing
- **Regional External Load Balancer**
- **Backend Service** with NEG (Network Endpoint Groups)
- **Service Extensions** for traffic processing
- **Health Checks** for pod readiness

### Application Workloads
- **Deployment**: Sample web application (3 replicas)
- **Service**: ClusterIP service for internal communication
- **Ingress**: Exposes application via load balancer

## Outputs

| Output | Description |
|--------|-------------|
| `load_balancer_ip` | External IP of the load balancer |

### Test Application

```bash
# Get the IP
LB_IP=$(terraform output -raw load_balancer_ip)

# Command to test the main application
curl -k -v https://$LB_IP

# Command to test the secondary application via route extension
curl -k -v https://$LB_IP -H \"x-route-to: secondary\"
```

## Cleanup

**CRITICAL**: Always follow this exact order to avoid resource conflicts:

### 1. Clean Up NEGs First

```bash
# This step is REQUIRED before terraform destroy
./cleanup_negs.sh your-project-id region
```

**Why this is necessary:**
- GKE-created NEGs are not managed by Terraform
- Terraform destroy will fail if NEGs are still attached to backend services
- The script safely detaches and deletes all NEGs
- Prevents resource dependency conflicts during destruction

### 2. Then Destroy Infrastructure

```bash
# Destroy infrastructure
terraform destroy -var-file="terraform.tfvars"
```

## NEG Management Scripts

### attach_negs.sh
- **Purpose**: Attaches GKE-created NEGs to backend services
- **When to use**: After `terraform apply` completes
- **What it does**: Finds NEGs in all zones and attaches them with proper load balancing configuration

### cleanup_negs.sh
- **Purpose**: Detaches and deletes NEGs before infrastructure destruction
- **When to use**: Before `terraform destroy`
- **What it does**: Safely removes NEG attachments and deletes the NEGs to prevent conflicts

## Production Readiness

> This configuration is intended for **demonstration purposes only**.

Before deploying to a production environment, you must address the following:

1.  **Service Accounts**: This sample uses the default Compute Engine service account for simplicity.
    - **Risk**: Default service accounts often have the broad `Editor` role, which violates the principle of least privilege.
    - **Action**: Create dedicated Service Accounts for each service with only the minimum required permissions (e.g., `roles/logging.logWriter`, `roles/monitoring.metricWriter`, `roles/artifactregistry.reader`).

2.  **TLS Certificates**: This sample generates self-signed certificates using Terraform.
    - **Risk**: Self-signed certificates trigger browser warnings and are not secure for public traffic.
    - **Action**: Use [Google-managed SSL certificates](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_managed_ssl_certificate) or provide your own valid certificates.

3.  **Deletion Protection**: `deletion_protection` is set to `false` to facilitate easy cleanup during testing.
    - **Action**: Enable deletion protection for production resources to prevent accidental data loss.

